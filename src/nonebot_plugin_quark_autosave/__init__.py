import re
import asyncio

from nonebot import logger, on_message
from nonebot.adapters import Event
from nonebot.exception import FinishedException
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

from .client import QASClient
from .config import Config, plugin_config
from .model import TaskItem, sanitize_title

__plugin_meta__ = PluginMetadata(
    name="夸克自动转存",
    description="Minimal QAS plugin: 1 -> link -> auto save -> cleanup",
    usage="发送 1 后按提示发送夸克链接",
    type="application",
    homepage="https://github.com/lzylipu/quark-autosave-bot",
    config=Config,
    supported_adapters=inherit_supported_adapters(),
    extra={"author": "lzylipu"},
)

SHARE_URL_REGEX = re.compile(
    r"^(?:https://|http://)?pan\.quark\.cn/s/[0-9a-zA-Z]+"
    r"(?:\?pwd=[0-9a-zA-Z]+)?"
    r"(?:#/list/share/[0-9a-zA-Z]+)?$"
)

# 等待状态 + 60秒自动超时清理
WAITING_USERS: dict[str, float] = {}  # user_key -> timestamp
WAIT_TIMEOUT = 60.0

qas_handler = on_message(permission=SUPERUSER, block=True)


def _cleanup_expired_users():
    """清理超时的等待状态"""
    now = asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else 0
    if now == 0:
        return
    expired = [k for k, t in WAITING_USERS.items() if now - t > WAIT_TIMEOUT]
    for k in expired:
        del WAITING_USERS[k]


def get_user_key(event: Event) -> str:
    try:
        return str(event.get_user_id())
    except Exception:
        return "unknown"


def get_text(event: Event) -> str:
    try:
        return str(event.get_plaintext()).strip()
    except Exception:
        return str(getattr(event, "message", "")).strip()


@qas_handler.handle()
async def handle_message(event: Event):
    _cleanup_expired_users()
    text = get_text(event)
    user_key = get_user_key(event)

    # 触发等待模式
    if text == str(plugin_config.simple_command):
        WAITING_USERS[user_key] = asyncio.get_event_loop().time()
        await qas_handler.finish("继续")

    # 非等待状态，忽略
    if user_key not in WAITING_USERS:
        return

    # 检查是否超时
    elapsed = asyncio.get_event_loop().time() - WAITING_USERS[user_key]
    if elapsed > WAIT_TIMEOUT:
        del WAITING_USERS[user_key]
        await qas_handler.finish("超时，请重新发送指令")

    # 校验链接格式
    if not SHARE_URL_REGEX.fullmatch(text):
        del WAITING_USERS[user_key]
        await qas_handler.finish("错")

    # 确保链接有协议头
    shareurl = text
    if not shareurl.startswith(("http://", "https://")):
        shareurl = "https://" + shareurl

    try:
        async with QASClient() as client:
            # 先获取分享详情，取根目录名作为任务名
            temp_task = TaskItem.simple_from_title("temp", shareurl)
            detail = await client.get_share_detail(temp_task)

            root_title = sanitize_title(detail.share.title)
            task = TaskItem.simple_from_title(root_title, shareurl)

            # 强制启用 aria2 自动下载
            task.addition = {
                "aria2": {
                    "auto_download": True,
                    "download_subdir": True,
                    "pause": False,
                    "save_path": "",
                }
            }

            logger.info(f"Adding task: {task.taskname} | {shareurl}")

            # 添加 -> 执行 -> 删除（原子流程）
            await client.add_task(task)
            data = await client.get_data()
            task_idx = len(data.tasklist)

            async for _ in client.run_script(task_idx):
                pass

            await client.delete_task(task_idx)

    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"QAS pipeline failed: {e}")
        del WAITING_USERS[user_key]
        await qas_handler.finish("错")

    del WAITING_USERS[user_key]
    await qas_handler.finish("好了")
