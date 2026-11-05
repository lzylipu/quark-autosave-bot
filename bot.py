import sys

import httpx
import nonebot
from nonebot.adapters.telegram import Adapter as TelegramAdapter
from nonebot.log import logger

# 优先从源码加载插件
sys.path.insert(0, "/app/src")

from quarkbot_keepalive import wrap_poll  # noqa: E402

nonebot.init()

driver = nonebot.get_driver()

# 长轮询断线自愈：adapter 启动阶段 get_me() 失败会直接抛死 poll task，
# 进程还活着但再也收不到消息（TG 出网抖动/官方侧重置都会触发）。
TelegramAdapter.poll = wrap_poll(TelegramAdapter.poll, logger=logger)

driver.register_adapter(TelegramAdapter)


# Monkey-patch httpx: 增加 keepalive + 自动重试
# 防止 Telegram long polling 长时间 idle 后断连崩溃
_original_init = httpx.AsyncClient.__init__


def _patched_init(self, *args, **kwargs):
    kwargs.setdefault("timeout", httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0))
    kwargs.setdefault("limits", httpx.Limits(
        max_keepalive_connections=10,
        max_connections=20,
        keepalive_expiry=120,
    ))
    if "transport" not in kwargs:
        kwargs["transport"] = httpx.AsyncHTTPTransport(retries=3)
    _original_init(self, *args, **kwargs)


httpx.AsyncClient.__init__ = _patched_init

nonebot.load_plugins("/app/src")

if __name__ == "__main__":
    nonebot.run()
