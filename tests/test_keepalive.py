"""长轮询断线自愈：启动期断一次不能让 poll task 死掉（真机：TG 出网抖动后静默失联）。"""

import asyncio

import pytest

from quarkbot_keepalive import wrap_poll


class _FakeAdapter:
    pass


async def test_retries_after_startup_failure():
    calls = []

    async def inner(self, bot):
        calls.append(bot)
        if len(calls) < 3:
            raise ConnectionError("api.telegram.org unreachable")
        # 第三次「连上」后模拟长轮询被取消（进程退出）
        raise asyncio.CancelledError

    poll = wrap_poll(inner, delay=0)
    with pytest.raises(asyncio.CancelledError):
        await poll(_FakeAdapter(), "bot")

    assert calls == ["bot", "bot", "bot"]  # 失败两次都重试了，第三次取消不再重试


async def test_returns_when_inner_finishes():
    async def inner(self, bot):
        return None

    await asyncio.wait_for(wrap_poll(inner, delay=0)(_FakeAdapter(), "bot"), timeout=1)


async def test_logs_each_failure():
    class _Logger:
        def __init__(self):
            self.lines = []

        def error(self, msg):
            self.lines.append(msg)

    calls = []

    async def inner(self, bot):
        calls.append(1)
        if len(calls) == 1:
            raise TimeoutError("read timeout")
        raise asyncio.CancelledError

    logger = _Logger()
    with pytest.raises(asyncio.CancelledError):
        await wrap_poll(inner, delay=0, logger=logger)(_FakeAdapter(), "bot")

    assert len(logger.lines) == 1
    assert "第 1 次" in logger.lines[0]
