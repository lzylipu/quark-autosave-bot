"""谁能用这个 bot。

显式配了 ``SUPERUSERS`` 就只认这些人；没配的话当作个人自建 bot：私聊放行，
群聊不放行（避免被拉进群当成公共转存机）。
"""

from __future__ import annotations

from collections.abc import Iterable


def allow_user(user_id: str, superusers: Iterable[str], is_private: bool) -> bool:
    allowed = {str(uid) for uid in superusers}
    if allowed:
        return user_id in allowed
    return is_private
