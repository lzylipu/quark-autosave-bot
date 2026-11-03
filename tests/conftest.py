"""测试全局装点。

注意：有了 tests/conftest.py 后 pytest 会先导入它，nonebug 的自动初始化不一定会
先跑，于是 `nonebot.get_plugin_config()` 会抛 `NoneBot has not been initialized`。
这里显式兜底初始化（e2e 脚本里也各自 init，互不影响）。
"""

import os

os.environ.setdefault("DRIVER", "~httpx")
os.environ.setdefault("ENVIRONMENT", "prod")

import nonebot  # noqa: E402
import pytest  # noqa: E402

try:
    nonebot.get_driver()
except ValueError:
    nonebot.init()


@pytest.fixture(autouse=True)
def _fast_delete_verify(monkeypatch):
    """删除后的复查等待在测试里没必要真等（真实默认 1.5s 起）。"""
    from nonebot_plugin_quark_autosave import client as client_mod

    monkeypatch.setattr(client_mod, "DELETE_VERIFY_DELAY", 0)
