import re

from nonebot import on_message
from nonebot.adapters import Event
from nonebot.exception import FinishedException
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

from .client import QASClient
from .config import Config, plugin_config
from .model import TaskItem, sanitize_title

__plugin_meta__ = PluginMetadata(
    name="夸克自动转存",
    description="配合 quark-auto-save 使用的极简 TG 私聊插件：1 -> 链接 -> 自动取根目录名 -> 建任务 -> 执行 -> 删除任务",
    usage="发送 1 后按提示发送夸克链接",
    type="application",
    homepage="https://github.com/fllesser/nonebot-plugin-quark-autosave",
    config=Config,
    supported_adapters=inherit_supported_adapters(),
    extra={"author": "fllesser / co-created"},
)

SHARE_URL_REGEX_SIMPLE = (
    r"^(?:https://|http://)?pan\.quark\.cn/s/[0-9a-zA-Z]+"
    r"(?:\?pwd=[0-9a-zA-Z]+)?"
    r"(?:#/list/share/[0-9a-zA-Z]+)?$"
)

WAITING_USERS: dict[str, bool] = {}

simple_qas = on_message(permission=SUPERUSER, block=True)


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


@simple_qas.handle()
async def _(event: Event):
    text = get_text(event)
    user_key = get_user_key(event)

    if text == str(plugin_config.simple_command):
        WAITING_USERS[user_key] = True
        await simple_qas.finish("继续")

    if not WAITING_USERS.get(user_key, False):
        return

    if not re.fullmatch(SHARE_URL_REGEX_SIMPLE, text):
        WAITING_USERS[user_key] = False
        await simple_qas.finish("错")

    shareurl = text
    if not shareurl.startswith("http://") and not shareurl.startswith("https://"):
        shareurl = "https://" + shareurl

    try:
        async with QASClient() as client:
            temp_task = TaskItem.simple_from_title("临时任务", shareurl)
            detail = await client.get_share_detail(temp_task)

            root_title = sanitize_title(detail.share.title)
            task = TaskItem.simple_from_title(root_title, shareurl)

            # 强制写入插件配置，确保 aria2 自动下载生效
            task.addition = {
                "aria2": {
                    "auto_download": True,
                    "pause": False,
                }
            }

            print("[quark-autosave-bot] add task payload:", task.model_dump())

            await client.add_task(task)

            data = await client.get_data()
            task_idx = len(data.tasklist)

            async for _ in client.run_script(task_idx):
                pass

            await client.delete_task(task_idx)

    except FinishedException:
        raise

    except Exception as e:
        print(f"[nonebot_plugin_quark_autosave] error: {e}")
        WAITING_USERS[user_key] = False
        await simple_qas.finish("错")

    WAITING_USERS[user_key] = False
    await simple_qas.finish("好了")
