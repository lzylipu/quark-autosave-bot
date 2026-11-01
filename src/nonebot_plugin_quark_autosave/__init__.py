import re

from nonebot import logger, on_message
from nonebot.adapters import Event
from nonebot.exception import FinishedException
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

from .client import QASClient
from .config import Config, plugin_config
from .model import TaskItem, sanitize_title
from .exception import QASException

__plugin_meta__ = PluginMetadata(
    name="夸克自动转存",
    description="发夸克链接直接转存，智能检测链接有效性",
    usage="直接发送夸克网盘链接即可，如: https://pan.quark.cn/s/xxxxx",
    type="application",
    homepage="https://github.com/lzylipu/quark-autosave-bot",
    config=Config,
    supported_adapters=inherit_supported_adapters(),
    extra={"author": "lzylipu"},
)

# 只匹配核心部分 pan.quark.cn/s/xxx
QUARK_LINK_REGEX = re.compile(r"https?://pan\.quark\.cn/s/[0-9a-zA-Z]+")

# 链接失效关键词 — QAS返回的错误信息中包含这些
EXPIRED_KEYWORDS = [
    "失效", "过期", "已取消", "已删除", "不存在", "已关闭",
    "expired", "deleted", "cancelled", "not found", "closed",
    "违规", "审核", "ban", "audit",
]
# QAS服务异常关键词
SERVICE_ERROR_KEYWORDS = [
    "cookie", "登录", "login", "unauthorized", "401", "403",
    "服务端", "server", "500", "502", "503",
    "连接", "timeout", "超时", "connect",
]

qas_handler = on_message(permission=SUPERUSER, block=False, priority=10)


def get_text(event: Event) -> str:
    try:
        return str(event.get_plaintext()).strip()
    except Exception:
        return str(getattr(event, "message", "")).strip()


def _classify_error(err_msg: str) -> str:
    """分类QAS错误信息"""
    lower = err_msg.lower()
    for kw in EXPIRED_KEYWORDS:
        if kw in lower:
            return "expired"
    for kw in SERVICE_ERROR_KEYWORDS:
        if kw in lower:
            return "service"
    return "unknown"


@qas_handler.handle()
async def handle_message(event: Event):
    text = get_text(event)

    match = QUARK_LINK_REGEX.search(text)
    if not match:
        return

    shareurl = match.group(0)
    await qas_handler.send("\U0001f50d 检测链接...", at_sender=True)

    try:
        async with QASClient() as client:

            # ===== 1. 检测链接有效性 =====
            try:
                temp_task = TaskItem.simple_from_title("temp", shareurl)
                detail = await client.get_share_detail(temp_task)
            except QASException as e:
                err_type = _classify_error(str(e))
                if err_type == "expired":
                    await qas_handler.send("\U0001f534 链接已失效", at_sender=True)
                elif err_type == "service":
                    await qas_handler.send(f"\u26a0 QAS服务异常: {e}", at_sender=True)
                else:
                    await qas_handler.send(f"\u2753 检测失败: {e}", at_sender=True)
                return

            # ===== 2. 链接有效（QAS已确认，get_share_detail不报错即有效） =====
            share = detail.share
            # 注意: 夸克share.status=1是正常，audit_status=4也是正常
            # 链接有效性完全依赖QAS的get_share_detail返回判断

            # ===== 3. 链接有效，开始转存 =====
            root_title = sanitize_title(detail.share.title)
            file_count = getattr(share, "file_num", 0)
            task = TaskItem.simple_from_title(root_title, shareurl)
            task.addition = {
                "aria2": {
                    "auto_download": True,
                    "download_subdir": True,
                    "pause": False,
                    "save_path": "",
                }
            }

            file_info = f" ({file_count}个文件)" if file_count else ""
            logger.info(f"QAS: {task.taskname}{file_info} | {shareurl}")
            await qas_handler.send(f"\U0001f4e5 {task.taskname}{file_info}", at_sender=True)

            # ===== 4. 执行转存 =====
            task_added = False
            try:
                await client.add_task(task)
                task_added = True

                script_output = []
                async for res in client.run_script(task):
                    script_output.append(res)

            except QASException as e:
                # 清理残留任务
                if task_added:
                    try:
                        await client.delete_task(task)
                    except Exception as cleanup_error:
                        logger.error(f"QAS cleanup failed after transfer error: {cleanup_error}")
                err_type = _classify_error(str(e))
                if err_type == "service":
                    await qas_handler.send(f"\u274c 转存服务异常: {e}", at_sender=True)
                else:
                    await qas_handler.send(f"\u274c 转存失败: {e}", at_sender=True)
                return

            # 清理任务
            try:
                await client.delete_task(task)
            except Exception as cleanup_error:
                logger.error(f"QAS cleanup failed after transfer success: {cleanup_error}")
                await qas_handler.send(
                    f"⚠️ 转存已执行，但任务清理失败: {cleanup_error}",
                    at_sender=True,
                )
                return

            # ===== 5. 分析脚本结果 =====
            full_output = "\n".join(script_output) if script_output else ""
            lower_output = full_output.lower()
            has_error = any(k in lower_output for k in ["失败", "error", "超时", "timeout", "异常"])
            has_success = any(k in lower_output for k in ["成功", "完成", "下载", "转存", "save"])

            if has_error and not has_success:
                await qas_handler.send("\u274c 执行失败，请检查QAS日志", at_sender=True)
            elif has_error and has_success:
                await qas_handler.send("\u26a1 部分完成（有文件失败）", at_sender=True)
            else:
                await qas_handler.send("\u2705 转存完成", at_sender=True)

    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"QAS unexpected: {e}")
        await qas_handler.send(f"\U0001f4a5 运行错误: {e}", at_sender=True)
