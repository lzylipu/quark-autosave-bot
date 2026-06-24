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
    description="直接发送夸克网盘链接即可自动转存",
    usage="直接发送夸克网盘分享链接，自动转存到网盘",
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


qas_handler = on_message(permission=SUPERUSER, block=True)


def get_text(event: Event) -> str:
    try:
        return str(event.get_plaintext()).strip()
    except Exception:
        return str(getattr(event, "message", "")).strip()


@qas_handler.handle()
async def handle_message(event: Event):
    text = get_text(event)

    # 直接匹配夸克链接，无需触发词
    if not SHARE_URL_REGEX.fullmatch(text):
        return

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

            # 通知用户正在处理
            await qas_handler.send("转存中…")

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
        await qas_handler.finish("错")

    await qas_handler.finish("好了")
