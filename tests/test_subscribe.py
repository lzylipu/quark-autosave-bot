"""订阅功能：集数解析、季数拆分、大小筛选、差集选源、订阅存取、定时计算。"""

import json
import re
from datetime import datetime

import pytest

from nonebot_plugin_quark_autosave.model import FileItem
from nonebot_plugin_quark_autosave.subscribe import (
    TV_PATTERN,
    SubscriptionStore,
    assess_share,
    check_share,
    episode_keys,
    episodes_of,
    fmt_episode_keys,
    fmt_episodes,
    parse_episode,
    parse_season,
    pick_best,
    rename_rules,
    season_or_bare_rules,
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

    def test_bare_episode_number_file(self):
        """整份分享就是 01.mkv~08.mkv 这种：必须能匹配，否则一集都转不了。

        真机：我的阿勒泰 8 集全是 01.mkv，原正则要求集数前有分隔符，
        一个文件都匹配不上 → QASx 判「没有新文件」→ 任务成功但落 0 个文件。
        """
        assert self._apply("01.mkv") == "S01E01.mkv"
        assert self._apply("08.mp4") == "S01E08.mp4"
        assert self._apply("2024.01.mkv") == "S01E01.mkv"
        # 纯分辨率/年份不能变成集数
        assert self._apply("1080p.mkv") == "1080p.mkv"
        assert self._apply("2160p.mkv") == "2160p.mkv"

    def test_other_video_extensions_are_not_dropped(self):
        """avi/ts/rmvb 也是视频集，不能因为 pattern 只写 mp4|mkv 就被整集漏掉。

        pattern 同时是 QASx 的筛选条件，匹配不上就不转存——等于这种格式永远补不上，
        还会让本地「已有几集」和分享里的集数对不上。
        """
        assert self._apply("甄嬛传.E05.avi") == "S01E05.avi"
        assert self._apply("甄嬛传.第07集.ts") == "S01E07.ts"
        assert self._apply("12.rmvb") == "S01E12.rmvb"

    def test_uppercase_extension(self):
        """QASx 用 re.search 不带 flags，.MKV/.MP4 必须靠内联 (?i:) 才认。"""
        assert self._apply("甄嬛传.E05.MKV") == "S01E05.MKV"
        assert self._apply("08.MP4") == "S01E08.MP4"

    def test_non_video_files_never_match(self):
        # 海报/字幕/种子混在分享里时不能当作剧集转存
        for name in ("poster.jpg", "a.nfo", "sample.srt", "readme.txt"):
            assert self._apply(name) == name

    def test_season_two(self):
        assert self._apply("庆余年.01.mkv", season=2) == "S02E01.mkv"
        assert self._apply("庆余年.S02E07.mkv", season=2) == "S02E07.mkv"

    def test_season_or_bare_mixes_both_styles(self):
        """同一个分享里 `S01E07` 和裸 `E06` 混着写时两种都要转。

        真机：幻视任务 7 集分享里 E01~E06 是裸集数、E07 带季标记，
        旧规则只认一种 → 只转存了 1 集，报「新增 E07」。
        """
        pattern, replace = season_or_bare_rules(1)
        for name, want in (
            ("幻视任务.S01E07.4K.mkv", "S01E07.mkv"),
            ("幻视任务.E06.4K.mkv", "S01E06.mkv"),
            ("01.mkv", "S01E01.mkv"),
        ):
            assert re.sub(pattern, replace, name) == want
        # 别的季一个都不许碰
        for name in ("Marshals.S02E04.2160p.mkv", "S07E01.mkv"):
            assert not re.search(pattern, name)

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
        assert cand.new_episodes == {(1, ep) for ep in range(4, 13)}

    def test_multi_season_episodes_are_not_confused(self):
        """合集里 S03E01 和 S01E01 是两集，本地有 S01E01 不能算 S03E01 已有。"""
        files = [
            _file("航拍中国第三季.Aerial.China.2020.S03.EP01.mp4"),
            _file("航拍中国第三季.Aerial.China.2020.S03.EP02.mp4"),
        ]
        cand = assess_share("u", files, {(1, 1), (1, 2)}, 1.5, 8)
        assert cand.new_episodes == {(3, 1), (3, 2)}

    def test_season_in_name_keeps_its_own_season(self):
        pattern, replace = rename_rules(1, keep_season_in_name=True)
        assert replace == r"S\1E\2.\3"
        src = "航拍中国第三季.Aerial.China.2020.S03.EP07.1080p.HD国语中字无水印.mp4"
        assert re.sub(pattern, replace, src) == "S03E07.mp4"
        assert parse_season(src) == 3

    def test_single_season_share_still_forced_to_subscription_season(self):
        pattern, replace = rename_rules(2)
        assert re.sub(pattern, replace, "某剧.E05.mkv") == "S02E05.mkv"

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

    def test_keeps_backup_of_previous_version(self, tmp_path):
        """每存一次都留一份 .bak，主文件写坏了还能捞回来。"""
        store = SubscriptionStore(tmp_path / "subs.json")
        store.add("甄嬛传")
        store.add("庆余年")
        backup = json.loads(store.backup_path.read_text(encoding="utf-8"))
        # 备份是「上一次的内容」：加了庆余年之后，备份里只有甄嬛传
        assert list(backup) == ["甄嬛传"]

    def test_truncated_file_falls_back_to_backup(self, tmp_path):
        """真机事故：容器被 kill 时文件写了半截，只有主文件就当没订阅了。"""
        store = SubscriptionStore(tmp_path / "subs.json")
        store.add("甄嬛传")
        store.add("庆余年")
        store.path.write_text('{"甄嬛传": {"created', encoding="utf-8")
        assert SubscriptionStore(store.path).list_all() == ["甄嬛传"]

    def test_ensure_ready_creates_missing_file(self, tmp_path):
        """只挂目录不落文件是正常的；启动时主动建出来，别让人以为没生效。"""
        store = SubscriptionStore(tmp_path / "subs.json")
        assert not store.path.exists()
        ok, msg = store.ensure_ready()
        assert ok
        assert store.path.exists()
        assert json.loads(store.path.read_text(encoding="utf-8")) == {}
        assert "已创建" in msg

    def test_ensure_ready_keeps_existing(self, tmp_path):
        store = SubscriptionStore(tmp_path / "subs.json")
        store.add("甄嬛传")
        ok, msg = store.ensure_ready()
        assert ok and "已存在" in msg
        assert store.list_all() == ["甄嬛传"]

    def test_ensure_ready_reports_unwritable(self, tmp_path, monkeypatch):
        """目录写不进去（属主不对 / 只读挂载）要在启动时就说，而不是等发 AD。"""
        store = SubscriptionStore(tmp_path / "subs.json")

        def boom(data):
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr(store, "save", boom)
        ok, msg = store.ensure_ready()
        assert ok is False
        assert "/app/data" in msg or "写不进去" in msg

    def test_set_chat_id_returns_false_when_unwritable(self, tmp_path, monkeypatch):
        """目录不能写时不能抛异常把 AD 命令搞崩，只返回 False 让上层提示。"""
        store = SubscriptionStore(tmp_path / "subs.json")

        def boom(data):
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr(store, "save", boom)
        assert store.set_chat_id("12345") is False
        assert store.record_result("甄嬛传", "x") is False

    def test_save_is_atomic_no_tmp_left(self, tmp_path):
        store = SubscriptionStore(tmp_path / "subs.json")
        store.add("甄嬛传")
        assert not store.path.with_suffix(".json.tmp").exists()
        assert store.list_all() == ["甄嬛传"]


class TestPersistenceCheck:
    def test_warns_when_not_mounted(self, tmp_path, monkeypatch):
        """没挂 /app/data 的容器，升级一次订阅全丢——启动就要喊出来。"""
        from nonebot_plugin_quark_autosave import subscribe as sub_mod

        monkeypatch.setattr(sub_mod, "path_is_mounted", lambda p: False)
        msg = sub_mod.persistence_warning("/app/data/subscriptions.json")
        assert msg and "不在挂载卷上" in msg and "-v quarkbot-data:/app/data" in msg

    def test_silent_when_mounted(self, monkeypatch):
        from nonebot_plugin_quark_autosave import subscribe as sub_mod

        monkeypatch.setattr(sub_mod, "path_is_mounted", lambda p: True)
        assert sub_mod.persistence_warning("/app/data/subscriptions.json") is None

    def test_root_mount_does_not_count(self):
        """根目录 / 是所有路径的祖先，不能因为它在就认为「已挂卷」。"""
        from nonebot_plugin_quark_autosave import subscribe as sub_mod

        assert sub_mod.path_is_mounted("/nonexistent-quarkbot-dir/x.json") is False


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


class TestSeasonHelpers:
    def test_parse_season_variants(self):
        assert parse_season("航拍中国第三季.Aerial.China.2020.S03.EP07.1080p.mp4") == 3
        assert parse_season("某剧 s2e05.mkv") == 2
        assert parse_season("某剧 第二季 05.mp4") == 2
        assert parse_season("某剧.E05.mkv") is None

    def test_episode_keys_defaults_to_subscription_season(self):
        assert episode_keys(["某剧.E05.mkv"], 2) == {(2, 5)}
        assert episode_keys(["某剧.S03E05.mkv"], 2) == {(3, 5)}

    def test_fmt_episode_keys_single_and_multi_season(self):
        assert fmt_episode_keys({(1, 1), (1, 2), (1, 3)}) == "E01~E03"
        assert fmt_episode_keys({(1, 1), (3, 5)}) == "S01E01、S03E05"
        assert fmt_episode_keys(set()) == "无"
