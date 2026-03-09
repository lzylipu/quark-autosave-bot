import re

from nonebot import on_command, require
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata, inherit_supported_adapters
from nonebot.typing import T_State

require("nonebot_plugin_alconna")

from .client import QASClient
from .config import Config, plugin_config
from .exception import handle_exception
from .model import TaskItem, sanitize_title

__plugin_meta__ = PluginMetadata(
    name="夸克自动转存",
    description="配合 quark-auto-save 使用的极简 TG 私聊插件：1 -> 链接 -> 自动取根目录名 -> 建任务 -> 执行 -> 删除任务",
    usage="发送 1 后按提示发送夸克链接",
    type="application",
    homepage="https://github.com/fllesser/nonebot-plugin-quark-autosave",
    config=Config,
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
    extra={"author": "fllesser / co-created"},
)

# 兼容：
# https://pan.quark.cn/s/461b6af90a65
# pan.quark.cn/s/461b6af90a65
# https://pan.quark.cn/s/461b6af90a65?pwd=xxxx#/list/share/xxxxxxxx
SHARE_URL_REGEX_SIMPLE = (
    r"(?:https://|http://)?pan\.quark\.cn/s/[0-9a-zA-Z]+"
    r"(?:\?pwd=[0-9a-zA-Z]+)?"
    r"(?:#/list/share/[0-9a-zA-Z]+)?"
)

simple_qas = on_command(
    str(plugin_config.simple_command),
    permission=SUPERUSER,
    block=True,
)


@simple_qas.handle()
async def _(state: T_State):
    state["QAS_SIMPLE_FLOW"] = {}
    await simple_qas.send("继续")


@simple_qas.got("shareurl", prompt="继续")
@handle_exception()
async def _(state: T_State, shareurl: str):
    try:
        shareurl = shareurl.strip()

        if not re.fullmatch(SHARE_URL_REGEX_SIMPLE, shareurl):
            await simple_qas.reject("继续")

        if not shareurl.startswith("http://") and not shareurl.startswith("https://"):
            shareurl = "https://" + shareurl

        async with QASClient() as client:
            temp_task = TaskItem.simple_from_title("临时任务", shareurl)
            detail = await client.get_share_detail(temp_task)

            root_title = sanitize_title(detail.share.title)

            task = TaskItem.simple_from_title(root_title, shareurl)

            await client.add_task(task)

            data = await client.get_data()
            task_idx = len(data.tasklist)

            async for _ in client.run_script(task_idx):
                pass

            await client.delete_task(task_idx)

        await simple_qas.finish("好了")
    except Exception:
        await simple_qas.finish("错")
