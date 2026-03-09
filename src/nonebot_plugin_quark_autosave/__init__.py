import re

from nonebot import on_command, require
from nonebot.plugin import PluginMetadata, inherit_supported_adapters
from nonebot.permission import SUPERUSER
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

SIMPLE_FLOW_KEY = "QAS_SIMPLE_FLOW"

# 兼容：
# pan.quark.cn/s/xxxx
# https://pan.quark.cn/s/xxxx
# https://pan.quark.cn/s/xxxx?pwd=xxxx#/list/share/xxxx
SHARE_URL_REGEX_SIMPLE = (
    r"(?:https://|http://)?pan\.quark\.cn/s/[0-9a-zA-Z]+"
    r"(?:\?pwd=[0-9a-zA-Z]+)?"
    r"(?:#/list/share/[0-9a-zA-Z]+)?"
)

simple_qas = on_command(
    plugin_config.simple_command,
    permission=SUPERUSER,
    block=True,
)


@simple_qas.handle()
async def _(state: T_State):
    state[SIMPLE_FLOW_KEY] = {}
    await simple_qas.send("继续")


@simple_qas.got("shareurl", prompt="继续")
@handle_exception()
async def _(state: T_State, shareurl: str):
    shareurl = shareurl.strip()

    if not re.fullmatch(SHARE_URL_REGEX_SIMPLE, shareurl):
        await simple_qas.reject("继续")

    if not shareurl.startswith("http://") and not shareurl.startswith("https://"):
        shareurl = "https://" + shareurl

    async with QASClient() as client:
        # 先读取分享详情，拿根目录标题
        temp_task = TaskItem.simple_from_title("临时任务", shareurl)
        detail = await client.get_share_detail(temp_task)

        root_title = sanitize_title(detail.share.title)

        # 自动创建任务：
        # 任务名称 = 根目录名称
        # 保存路径 = /自动/根目录名称
        task = TaskItem.simple_from_title(root_title, shareurl)

        # 先添加任务
        await client.add_task(task)

        # 重新获取任务列表，拿最后一条索引（刚创建的任务）
        data = await client.get_data()
        task_idx = len(data.tasklist)

        # 只执行这一条新任务
        async for _ in client.run_script(task_idx):
            pass

        # 执行完立即删除这个任务
        await client.delete_task(task_idx)

    await simple_qas.finish("好了")
