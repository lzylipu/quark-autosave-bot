import sys
import ssl

import httpx
import nonebot
from nonebot.adapters.telegram import Adapter as TelegramAdapter

# 强制优先从源码目录加载插件
sys.path.insert(0, "/app/src")

nonebot.init()

driver = nonebot.get_driver()
driver.register_adapter(TelegramAdapter)

# ===== 修复：替换 driver 的 httpx client，配置长连接和自动重试 =====
# 默认可导致长时间闲置后连接断开时报 RemoteProtocolError 崩溃
_driver = driver

def _patch_httpx_client():
    """
    给 httpx AsyncClient 配置更长的 keepalive 和自动重试，
    防止 Telegram long polling 长时间闲置后断连崩溃。
    """
    limits = httpx.Limits(
        max_keepalive_connections=10,
        max_connections=20,
        keepalive_expiry=120,  # 保持连接 120 秒（默认 5s 太短）
    )
    timeout = httpx.Timeout(
        connect=10.0,
        read=60.0,      # Telegram get_updates timeout=30，这里给 60
        write=10.0,
        pool=10.0,
    )
    transport = httpx.AsyncHTTPTransport(
        limits=limits,
        retries=3,       # 自动重试 3 次
    )

    client = httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
        transport=transport,
    )

    # 替换 driver 的 httpx session
    if hasattr(_driver, "_session"):
        _driver._session = client

    return client

# 注：NoneBot 的 FastAPI+httpx driver 会在内部创建 client，
# 我们需要在 driver 启动前替换它。
# 更简洁的方式是 monkey-patch httpx.AsyncClient 的默认参数
_original_init = httpx.AsyncClient.__init__

def _patched_async_client_init(self, *args, **kwargs):
    kwargs.setdefault("timeout", httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0))
    kwargs.setdefault("limits", httpx.Limits(
        max_keepalive_connections=10,
        max_connections=20,
        keepalive_expiry=120,
    ))
    if "transport" not in kwargs:
        kwargs["transport"] = httpx.AsyncHTTPTransport(retries=3)
    _original_init(self, *args, **kwargs)

httpx.AsyncClient.__init__ = _patched_async_client_init

# 从源码目录加载插件，不加载 site-packages 里的旧版本
nonebot.load_plugins("/app/src")

if __name__ == "__main__":
    nonebot.run()