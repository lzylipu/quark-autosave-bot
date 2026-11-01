"""权限判定：配了 SUPERUSERS 只认名单，没配就私聊放行。"""

from nonebot_plugin_quark_autosave.perms import allow_user


def test_configured_superuser_only():
    assert allow_user("42", {"42"}, is_private=True)
    assert not allow_user("43", {"42"}, is_private=True)
    assert not allow_user("43", {"42"}, is_private=False)


def test_empty_superusers_allows_private_only():
    assert allow_user("42", set(), is_private=True)
    assert not allow_user("42", set(), is_private=False)


def test_empty_string_superuser_is_not_a_wildcard():
    # start.sh 空 SUPERUSER 必须写成 []，而不是 [""]，否则这里会误判
    assert not allow_user("42", {""}, is_private=True)
