"""订阅功能：集数解析、季数拆分、大小筛选、差集选源、订阅存取、定时计算。"""

import re
from datetime import datetime

import pytest

from nonebot_plugin_quark_autosave.model import FileItem
from nonebot_plugin_quark_autosave.subscribe import (
    SubscriptionStore,
    assess_share,
    check_share,
    episodes_of,
    fmt_episodes,
    parse_episode,
    pick_best,
    rename_rules,
    seconds_until,
    split_season,
    video_names_from_dir,
)

GB = 1024**3


def _file(name: str, size_bytes: int = 2 * GB, dir_: bool = False) -> FileItem:
    return FileItem(fid=name, file_name=name, updated_at=0, size=size_bytes, dir=dir_)


class TestParseEpisode:
    def test_all_naming_styles(self):
        # 带不带 S01 都必须认成同一集
        assert parse_episode("甄嬛传.S01E05.1080p.mkv") == 5
        assert parse_episode("甄嬛传.E05.mp4") == 5
        assert parse_episode("甄嬛传 EP05.mkv") == 5
        assert parse_episode("甄嬛传 第05集.mkv") == 5
        assert parse_episode("甄嬛传.05.mp4") == 5
        assert parse_episode("[05].mp4") == 5
        assert parse_episode("05.mkv") == 5

    def test_year_is_not_episode(self):
        assert parse_episode("琅琊榜.2015.1080p.mkv") is None

    def test_no_episode(self):
        assert parse_episode("花絮.mkv") is None


class TestSplitSeason:
    def test_default_season_one(self):
        assert split_season("甄嬛传") == ("甄嬛传", 1)

    def test_english_season_suffix(self):
        assert split_season("庆余年 S02") == ("庆余年", 2)
        assert split_season("庆余年.S2") == ("庆余年", 2)

    def test_chinese_season_suffix(self):
        assert split_season("琅琊榜 第二季") == ("琅琊榜", 2)
        assert split_season("琅琊榜 第2季") == ("琅琊榜", 2)


class TestRenameRules:
    """重命名规则必须真的把各种命名统一成 S01Exx（用 re.sub 实测，不靠猜）。"""

    @staticmethod
    def _apply(name: str, season: int = 1) -> str:
        pattern, replace = rename_rules(season)
        return re.sub(pattern, replace, name) if re.search(pattern, name) else name

    def test_common_naming_styles(self):
        assert self._apply("甄嬛传.05.mkv") == "S01E05.mkv"
        assert self._apply("甄嬛传.E05.mkv") == "S01E05.mkv"
        assert self._apply("甄嬛传 第05集.mp4") == "S01E05.mp4"
        assert self._apply("[05].mkv") == "S01E05.mkv"
        assert self._apply("甄嬛传 EP12.mkv") == "S01E12.mkv"
        assert self._apply("甄嬛传-13.mkv") == "S01E13.mkv"
        assert self._apply("甄嬛传.S01E05.1080p.mkv") == "S01E05.mkv"

    def test_resolution_is_not_episode(self):
        # 4K/1080p/2160p 里的数字不能被当成集数，否则会错命名成 E4/E160
        assert self._apply("甄嬛传.4K.第12集.mkv") == "S01E12.mkv"
        assert self._apply("甄嬛传.2160p.WEB-DL.第01集.mkv") == "S01E01.mkv"
        assert self._apply("甄嬛传.[1080p].05.mkv") == "S01E05.mkv"

    def test_season_two(self):
        assert self._apply("庆余年.01.mkv", season=2) == "S02E01.mkv"
        assert self._apply("庆余年.S02E07.mkv", season=2) == "S02E07.mkv"

    def test_rename_forces_season_prefix(self):
        pattern, replace = rename_rules(1)
        assert pattern
        assert replace == "S01E\\2.\\3"
        assert rename_rules(2)[1] == "S02E\\2.\\3"


class TestEpisodes:
    def test_episodes_of_mixed_names(self):
        names = ["S01E01.mkv", "E02.mp4", "03.mkv", "poster.jpg"]
        assert episodes_of(names) == {1, 2, 3}

    def test_fmt_range_and_scattered(self):
        assert fmt_episodes({1, 2, 3}) == "E01~E03"
        assert fmt_episodes({10, 11, 12}) == "E10~E12"
        assert fmt_episodes({2}) == "E02"
        assert fmt_episodes(set()) == "无"


class TestCheckShare:
    def test_all_in_range(self):
        ok, why = check_share([_file("E01.mkv", 2 * GB), _file("E02.mkv", 5 * GB)], 1.5, 8)
        assert ok
        assert "2 个视频" in why

    def test_any_out_of_range_rejects(self):
        ok, _ = check_share([_file("E01.mkv", int(0.9 * GB)), _file("E02.mkv", 5 * GB)], 1.5, 8)
        assert not ok

    def test_poster_ignored(self):
        ok, _ = check_share([_file("E01.mkv", 2 * GB), _file("poster.jpg", 100 * 1024)], 1.5, 8)
        assert ok

    def test_no_video_rejects(self):
        ok, _ = check_share([_file("cover.jpg", 100 * 1024)], 1.5, 8)
        assert not ok


class TestAssessAndPick:
    def test_new_episodes_diff(self):
        files = [_file(f"甄嬛传.E{i:02d}.mkv") for i in range(1, 13)]
        cand = assess_share("https://pan.quark.cn/s/aaa", files, {1, 2, 3}, 1.5, 8)
        assert cand.size_ok
        assert cand.new_episodes == set(range(4, 13))

    def test_no_new_episodes_when_local_complete(self):
        files = [_file(f"E{i:02d}.mkv") for i in (1, 2, 3)]
        cand = assess_share("https://pan.quark.cn/s/aaa", files, {1, 2, 3}, 1.5, 8)
        assert cand.new_episodes == set()
        assert pick_best([cand]) is None

    def test_pick_prefers_most_new_episodes(self):
        small = assess_share(
            "u1", [_file(f"E{i:02d}.mkv") for i in (10, 11)], set(range(1, 10)), 1.5, 8
        )
        big = assess_share(
            "u2", [_file(f"E{i:02d}.mkv") for i in range(10, 15)], set(range(1, 10)), 1.5, 8
        )
        best = pick_best([small, big])
        assert best is not None and best.shareurl == "u2"

    def test_oversized_candidate_rejected(self):
        cand = assess_share("u1", [_file("E01.mkv", int(12 * GB))], set(), 1.5, 8)
        assert not cand.size_ok
        assert pick_best([cand]) is None


class TestDirScan:
    def test_video_names_from_dir_filters(self):
        files = [
            {"file_name": "S01E01.mkv", "dir": False},
            {"file_name": "海报.jpg", "dir": False},
            {"file_name": "子目录", "dir": True},
            {"file_name": "S01E02.mp4", "dir": False},
        ]
        assert video_names_from_dir(files) == ["S01E01.mkv", "S01E02.mp4"]


class TestSubscriptionStore:
    def test_add_list_remove(self, tmp_path):
        store = SubscriptionStore(tmp_path / "subs.json")
        ok, _ = store.add("甄嬛传")
        assert ok
        ok, _ = store.add("甄嬛传")
        assert not ok
        assert store.list_all() == ["甄嬛传"]
        store.record_result("甄嬛传", "✅ 转存完成")
        ok, _ = store.remove("甄嬛传")
        assert ok
        assert store.list_all() == []

    def test_chat_id_hidden_from_list(self, tmp_path):
        store = SubscriptionStore(tmp_path / "subs.json")
        store.add("甄嬛传")
        store.set_chat_id("12345")
        assert store.list_all() == ["甄嬛传"]
        assert store.get_chat_id() == "12345"

    def test_broken_file_recovers(self, tmp_path):
        path = tmp_path / "subs.json"
        path.write_text("not json", encoding="utf-8")
        assert SubscriptionStore(path).list_all() == []


class TestSecondsUntil:
    def test_next_run(self):
        now = datetime(2026, 11, 1, 10, 0)
        assert seconds_until("17:00", now) == pytest.approx(7 * 3600)

    def test_already_passed_goes_tomorrow(self):
        now = datetime(2026, 11, 1, 18, 0)
        assert seconds_until("17:00", now) == pytest.approx(23 * 3600)

    def test_invalid_falls_back(self):
        now = datetime(2026, 11, 1, 18, 0)
        assert seconds_until("bad", now) == pytest.approx(23 * 3600)
