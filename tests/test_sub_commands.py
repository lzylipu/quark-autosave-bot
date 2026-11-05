"""订阅命令解析：「列表 / del / 执行」为主，AD 与英文旧写法仍可用。"""

import re

import nonebot_plugin_quark_autosave as plugin


def _parse(text: str):
    match = plugin._SUB_CMD_RE.match(text)
    assert match, text
    return plugin._SUB_ALIASES[match.group(1).upper()], match.group(2).strip()


def test_chinese_commands():
    assert _parse("列表") == ("LIST", "")
    assert _parse("del 甄嬛传") == ("DL", "甄嬛传")
    assert _parse("执行") == ("RUN", "")
    assert _parse("执行 甄嬛传") == ("RUN", "甄嬛传")
    assert _parse("AD 甄嬛传") == ("AD", "甄嬛传")


def test_old_english_commands_still_work():
    assert _parse("LIST") == ("LIST", "")
    assert _parse("DL 甄嬛传") == ("DL", "甄嬛传")
    assert _parse("list") == ("LIST", "")


def test_similar_words_are_not_commands():
    # 「列表里有什么」这种自然说话不能当命令吞掉
    for text in ("执行完了吗", "删除任务", "deluxe 电影", "x列表"):
        assert plugin._SUB_CMD_RE.match(text) is None, text


async def test_run_subset_only_runs_named_subscription(monkeypatch):
    """「执行 某剧」只跑这一部，不能把整个订阅列表都跑一遍。"""
    ran = []

    async def _fake(client, name):
        ran.append(name)
        return "✅ 完成"

    monkeypatch.setattr(plugin.store, "list_all", lambda: ["甲", "乙"])
    monkeypatch.setattr(plugin, "_run_one_subscription", _fake)
    monkeypatch.setattr(plugin, "_report", _fake_report)

    await plugin._run_all_subscriptions(["乙"])
    assert ran == ["乙"]


async def _fake_report(*_a, **_k):
    return None


def test_regex_has_all_command_words():
    pattern = plugin._SUB_CMD_RE.pattern
    for word in ("AD", "列表", "DEL", "DL", "执行", "RUN"):
        assert re.search(word, pattern), word
