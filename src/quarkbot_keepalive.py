"""让 Telegram 长轮询断线后自己爬起来。

nonebot2 的 telegram adapter 在启动阶段要 `get_me()` + `delete_webhook()`，
这一步失败（出网抖动、被墙、TG 侧重置）会直接 `raise` 出 `poll()`，
整个 poll task 结束、进程还活着 —— 表现就是「机器人忽然不理人了」。
运行期的 getUpdates 有 while + except 会自愈，启动期却没有，这是最常见的失联原因。
"""

import asyncio
from typing import Awaitable, Callable

RETRY_DELAY = 10.0

Poll = Callable[..., Awaitable[None]]


def wrap_poll(inner: Poll, *, delay: float = RETRY_DELAY, logger=None) -> Poll:
    """给 adapter.poll 套一层无限重试：只要断线就等一会儿重来，进程不退出。"""

    async def poll(self, bot, *args, **kwargs) -> None:
        attempt = 0
        while True:
            try:
                await inner(self, bot, *args, **kwargs)
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - 断线原因五花八门，一律重试
                attempt += 1
                if logger is not None:
                    logger.error(
                        f"Telegram 长轮询断开（第 {attempt} 次），{delay:.0f} 秒后重连: {exc!r}"
                    )
                await asyncio.sleep(delay)

    return poll
