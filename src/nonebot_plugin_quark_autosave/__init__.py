import re
from time import monotonic

from nonebot import logger, on_message
from nonebot.adapters import Event
from nonebot.exception import FinishedException
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

from .client import QASClient
from .config import Config, plugin_config
from .exception import QASException
from .model import DetailInfo, TaskItem, sanitize_title
from .result import (
    AUTH_ERROR_KEYWORDS,
    EXPIRED_KEYWORDS,
    PASSCODE_KEYWORDS,
    contains_any,
    extract_passcode,
    extract_share_url,
    parse_run_output,
    share_key,
    with_passcode,
)

__plugin_meta__ = PluginMetadata(
    name="夸克自动转存",
    description="发夸克链接直接转存，智能检测链接有效性",
    usage="直接发送夸克网盘链接即可，如: https://pan.quark.cn/s/xxxxx?pwd=1234",
    type="application",
    homepage="https://github.com/lzylipu/quark-autosave-bot",
    config=Config,
    supported_adapters=inherit_supported_adapters(),
    extra={"author": "lzylipu"},
)

qas_handler = on_message(permission=SUPERUSER, block=False, priority=10)

# 分享 ID -> (完成时间, 任务名, 保存路径)，用于短时间内的重复链接去重
_recent: dict[str, tuple[float, str, str]] = {}
# 正在处理中的分享 ID
_inflight: dict[str, float] = {}


def get_text(event: Event) -> str:
    try:
        return str(event.get_plaintext()).strip()
    except Exception:
        return str(getattr(event, "message", "")).strip()


async def send(message: str) -> None:
    await qas_handler.send(message, at_sender=True)


def _classify_error(err_msg: str) -> str:
    """分类 QAS 错误信息。"""
    if contains_any(err_msg, PASSCODE_KEYWORDS):
        return "passcode"
    if contains_any(err_msg, EXPIRED_KEYWORDS):
        return "expired"
    if contains_any(err_msg, AUTH_ERROR_KEYWORDS):
        return "auth"
    return "unknown"


async def _ask_passcode() -> str | None:
    """在聊天里追问提取码；依赖不可用或超时则返回 None。"""
    if not plugin_config.ask_passcode:
        return None
    try:
        from nonebot_plugin_waiter import prompt

        reply = await prompt("🔑 这个分享需要提取码，请直接发送 4 位提取码（60 秒内有效）", timeout=60)
    except Exception as exc:  # waiter 不可用时不要拖垮整个流程
        logger.warning(f"passcode prompt unavailable: {exc}")
        return None
    code = get_text(reply)
    return code if re.fullmatch(r"[0-9a-zA-Z]{4}", code) else None


async def _get_detail(client: QASClient, shareurl: str) -> tuple[str, DetailInfo]:
    """获取分享详情；遇到「需要提取码」时追问一次并带上 pwd 重试。"""
    task = TaskItem.simple_from_title("temp", shareurl)
    try:
        return shareurl, await client.get_share_detail(task)
    except QASException as exc:
        message = str(exc)
        if _classify_error(message) != "passcode" or extract_passcode(shareurl):
            raise
        logger.info(f"QAS requests passcode for {shareurl}")

    passcode = await _ask_passcode()
    if not passcode:
        raise QASException("该分享需要提取码，请带上提取码重发，如 https://pan.quark.cn/s/xxxx?pwd=1234")
    resolved_url = with_passcode(shareurl, passcode)
    return resolved_url, await client.get_share_detail(
        TaskItem.simple_from_title("temp", resolved_url)
    )


async def _cleanup(client: QASClient, task: TaskItem) -> bool:
    try:
        await client.delete_task(task)
    except Exception as exc:
        logger.error(f"QAS cleanup failed for {task.taskname}: {exc}")
        return False
    return True


def _prune_recent() -> None:
    ttl = max(plugin_config.dedupe_seconds, 60) * 6
    now = monotonic()
    for key, value in list(_recent.items()):
        if now - value[0] > ttl:
            _recent.pop(key, None)


async def _handle_share(shareurl: str, key: str) -> None:
    await send("🔍 检测链接...")

    async with QASClient() as client:
        # ===== 1. 检测链接有效性 =====
        try:
            shareurl, detail = await _get_detail(client, shareurl)
        except QASException as exc:
            err_type = _classify_error(str(exc))
            if err_type == "passcode":
                await send(f"🔑 {exc}")
            elif err_type == "expired":
                await send("🔴 链接已失效")
            elif err_type == "auth":
                await send("🔒 夸克登录态失效，请到 QAS WebUI 重新登录后再发一次")
            else:
                await send(f"❌ 检测失败: {exc}")
            return

        # ===== 2. 链接有效，构建任务 =====
        root_title = sanitize_title(detail.share.title)
        file_count = getattr(detail.share, "file_num", 0)
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
        await send(f"📥 {task.taskname}{file_info}")

        # ===== 3. 执行转存 =====
        task_added = False
        script_output: list[str] = []
        try:
            await client.add_task(task)
            task_added = True
            async for res in client.run_script(task):
                script_output.append(res)
        except QASException as exc:
            if task_added:
                await _cleanup(client, task)
            err_type = _classify_error(str(exc))
            if err_type == "auth":
                await send("🔒 夸克登录态失效，请到 QAS WebUI 重新登录后再发一次")
            elif err_type == "expired":
                await send(f"🔴 链接已失效: {exc}")
            else:
                await send(f"❌ 转存失败: {exc}")
            return

        # ===== 4. 清理任务（失败也要让用户知道）=====
        cleaned = await _cleanup(client, task)

        # ===== 5. 汇报结果 =====
        result = parse_run_output(script_output)
        await send(result.render(fallback_savepath=task.savepath))
        if not cleaned:
            await send("⚠️ 转存已执行，但任务未从 QAS 删除，请到 QAS WebUI 手动清理")

        if result.status in ("success", "partial"):
            _recent[key] = (monotonic(), task.taskname, result.savepath or task.savepath)


@qas_handler.handle()
async def handle_message(event: Event):
    shareurl = extract_share_url(get_text(event))
    if not shareurl:
        return

    key = share_key(shareurl)
    now = monotonic()

    if key in _inflight:
        await send("⏳ 这条链接正在处理中，稍等一下")
        return

    hit = _recent.get(key)
    if hit and now - hit[0] < plugin_config.dedupe_seconds:
        await send(f"♻️ 这条链接 {int(now - hit[0])} 秒前刚转过，跳过\n📁 {hit[2]}")
        return

    _inflight[key] = now
    try:
        await _handle_share(shareurl, key)
    except FinishedException:
        raise
    except Exception as exc:
        logger.exception(f"QAS unexpected error: {exc}")
        await send(f"💥 运行错误: {exc}")
    finally:
        _inflight.pop(key, None)
        _prune_recent()
