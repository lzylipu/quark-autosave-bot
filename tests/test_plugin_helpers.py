"""插件层辅助逻辑测试：错误分类、去重缓存、提取码开关。"""

import nonebot_plugin_quark_autosave as plugin
from nonebot_plugin_quark_autosave.config import plugin_config
from nonebot_plugin_quark_autosave.result import classify_error


def test_classify_error_recognises_passcode_first():
    assert classify_error("该分享需要提取码") == "passcode"


def test_classify_error_auth_beats_expired():
    # "Cookie 已失效" 同时命中 auth 和 expired 关键词，必须判成 auth，
    # 否则用户会被误导去重新分享（以为链接挂了）
    assert classify_error("Cookie 已失效，请重新登录") == "auth"
    assert classify_error("账号失效") == "auth"


def test_classify_error_expired_and_unknown():
    assert classify_error("分享资源已失效") == "expired"
    assert classify_error("未知问题") == "unknown"


def test_run_result_reports_auth_not_expired():
    from nonebot_plugin_quark_autosave.result import parse_run_output

    result = parse_run_output(["❌《任务》转存失败: Cookie 已失效"])
    assert result.status == "failed"
    assert result.auth_failed and not result.expired
    assert "重新登录" in result.render()


def test_waiter_dependency_is_installed():
    # Dockerfile/requirements.txt 里必须有这个包，否则提取码追问会静默降级
    import nonebot_plugin_waiter

    assert hasattr(nonebot_plugin_waiter, "prompt")


async def test_ask_passcode_disabled_returns_none(monkeypatch):
    monkeypatch.setattr(plugin_config, "ask_passcode", False)
    assert await plugin._ask_passcode() is None


def test_prune_recent_drops_expired_entries(monkeypatch):
    plugin._recent.clear()
    plugin._recent["old"] = (0.0, "老任务", "/自动/老任务")
    monkeypatch.setattr(plugin, "monotonic", lambda: 10_000.0)
    plugin._prune_recent()
    assert "old" not in plugin._recent
    plugin._recent.clear()
