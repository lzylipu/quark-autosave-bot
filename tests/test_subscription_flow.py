"""订阅执行编排：用假 client 跑通「扫本地 → 搜索 → 筛选 → 建任务 → 删任务」。"""

import re

import nonebot_plugin_quark_autosave as plugin
from nonebot_plugin_quark_autosave.model import DetailInfo, FileItem

GB = 1024**3


def _detail(*files: FileItem) -> DetailInfo:
    # share 字段用不上，model_construct 跳过校验
    return DetailInfo.model_construct(
        is_owner=1, share=None, file_list=list(files), paths=[], stoken=""
    )


def _file(name: str, size: float) -> FileItem:
    return FileItem(fid=name, file_name=name, updated_at=0, size=int(size * GB))


class FakeClient:
    def __init__(self, local, results, details, output=None):
        self.local = local
        self.results = results
        self.details = details
        self.output = output or ["✅《甄嬛传》新增文件:\n/自动/甄嬛传\n├── S01E10.mkv"]
        self.added = []
        self.deleted = []
        # 探过详情的分享：早停测试要数「到底探了几个」
        self.probed = []

    async def list_savepath_files(self, savepath):
        return self.local

    async def task_suggestions(self, query):
        return self.results

    async def get_share_detail(self, task):
        return self.details[task.shareurl]

    async def get_share_files(self, shareurl, max_depth=3, max_dirs=40):
        # 真实实现会递归展开子目录；测试里 details 直接给全量文件
        self.probed.append(shareurl)
        return list(self.details[shareurl].file_list)

    async def add_task(self, task):
        self.added.append(task)
        return task

    async def run_script(self, task):
        for chunk in self.output:
            yield chunk

    async def delete_task(self, task):
        self.deleted.append(task)
        return task.taskname


async def test_flow_adds_task_with_season_prefix_and_cleans_up():
    local = [{"file_name": f"E{i:02d}.mkv", "dir": False} for i in range(1, 10)]
    share_files = [_file(f"甄嬛传.E{i:02d}.mkv", 2) for i in range(1, 13)]
    client = FakeClient(
        local,
        [{"shareurl": "https://pan.quark.cn/s/newest"}],
        {"https://pan.quark.cn/s/newest": _detail(*share_files)},
    )

    report = await plugin._run_one_subscription(client, "甄嬛传")

    assert len(client.added) == 1
    task = client.added[0]
    assert task.taskname == "甄嬛传"
    assert task.savepath == "/自动/甄嬛传"
    assert task.replace == "S01E\\2.\\3"  # 统一补季数
    assert task.addition == {}  # 插件设置交给 QASx 默认；不能是 None，否则 /update 500
    assert task.pattern
    assert client.deleted and client.deleted[0].shareurl == task.shareurl
    assert "E10~E12" in report  # 本地 1~9，新增 10~12


async def test_flow_skips_when_nothing_new():
    local = [{"file_name": f"S01E{i:02d}.mkv", "dir": False} for i in range(1, 13)]
    share_files = [_file(f"E{i:02d}.mkv", 2) for i in range(1, 13)]
    client = FakeClient(
        local, [{"shareurl": "u1"}], {"u1": _detail(*share_files)}
    )

    report = await plugin._run_one_subscription(client, "甄嬛传")

    assert client.added == []  # 已经是最新，不建任务
    assert "已经是最新" in report


async def test_flow_rejects_oversized_share():
    share_files = [_file(f"E{i:02d}.mkv", 20) for i in range(1, 5)]
    client = FakeClient([], [{"shareurl": "u1"}], {"u1": _detail(*share_files)})

    report = await plugin._run_one_subscription(client, "甄嬛传")

    assert client.added == []
    assert "1.5~8.0G" in report or "都不在" in report


async def test_flow_picks_share_with_most_new_episodes():
    local = [{"file_name": f"E{i:02d}.mkv", "dir": False} for i in range(1, 10)]
    small = [_file(f"E{i:02d}.mkv", 2) for i in (10, 11)]
    big = [_file(f"E{i:02d}.mkv", 2) for i in range(10, 15)]
    client = FakeClient(
        local,
        [{"shareurl": "small"}, {"shareurl": "big"}],
        {"small": _detail(*small), "big": _detail(*big)},
    )

    await plugin._run_one_subscription(client, "甄嬛传")

    assert client.added[0].shareurl == "big"


async def test_flow_season_two_uses_s02():
    share_files = [_file("庆余年.E01.mkv", 2)]
    client = FakeClient([], [{"shareurl": "u1"}], {"u1": _detail(*share_files)})

    await plugin._run_one_subscription(client, "庆余年 S02")

    assert client.added[0].taskname == "庆余年"
    assert client.added[0].replace == "S02E\\2.\\3"


async def test_flow_without_results_reports():
    client = FakeClient([], [], {})
    report = await plugin._run_one_subscription(client, "甄嬛传")
    assert "没搜到" in report


async def test_flow_scans_beyond_first_ten_candidates(monkeypatch):
    """真机 bug：走马上任 71 条结果里，前 10 条全不合格，第 25 条才有 1.5~8G 的。

    程序当时只看前 10 条就报「检查了 10 个分享，都不在 1.5~8.0G 区间」，实际有资源。
    """
    from nonebot_plugin_quark_autosave import subscribe as sub_mod

    monkeypatch.setattr(sub_mod.plugin_config, "sub_max_candidates", 10)
    monkeypatch.setattr(sub_mod.plugin_config, "sub_max_ok_candidates", 5)

    shares = [f"u{i}" for i in range(1, 13)]
    details = {
        u: _detail(*[_file(f"E{i}.mkv", 0.3) for i in (1, 2)]) for u in shares[:-1]
    }
    details[shares[-1]] = _detail(*[_file(f"E{i}.mkv", 2.5) for i in (1, 2)])
    client = FakeClient([], [{"shareurl": u} for u in shares], details)

    # 限制 10 条时确实只看 10 条（保留可配置语义）
    report = await plugin._run_one_subscription(client, "走马上任")
    assert client.added == []
    assert "检查了 10 个分享" in report

    client2 = FakeClient([], [{"shareurl": u} for u in shares], details)
    monkeypatch.setattr(sub_mod.plugin_config, "sub_max_candidates", 0)
    await plugin._run_one_subscription(client2, "走马上任")
    assert client2.added and client2.added[0].shareurl == shares[-1]


async def test_flow_falls_back_when_nothing_in_size_window(monkeypatch):
    """真机 bug：尚公主 4K 每集只有 1.15~1.4G，全部落在 1.5G 下限之外，一张都下不来。

    没有 1.5~8G 的分享时，退一步用每集中位数 >= 0.5G 的（正片偏小 ≠ 枪版），
    并在报告里说清楚用的是哪一档。
    """
    from nonebot_plugin_quark_autosave import subscribe as sub_mod

    monkeypatch.setattr(sub_mod.plugin_config, "sub_fallback_min_size_gb", 0.5)
    files = [_file(f"尚公主.{i:02d}.mp4", 1.2) for i in (20, 21, 22)]
    client = FakeClient([], [{"shareurl": "u1"}], {"u1": _detail(*files)})

    report = await plugin._run_one_subscription(client, "尚公主")

    assert client.added, "没有合格分享时应该退一档把偏小的正片下下来"
    assert "改用" in report


async def test_flow_still_rejects_tiny_garbage(monkeypatch):
    """退档也不能把 0.3G 的枪版当正片下。"""
    from nonebot_plugin_quark_autosave import subscribe as sub_mod

    monkeypatch.setattr(sub_mod.plugin_config, "sub_fallback_min_size_gb", 0.5)
    files = [_file(f"E{i:02d}.mkv", 0.3) for i in (1, 2)]
    client = FakeClient([], [{"shareurl": "u1"}], {"u1": _detail(*files)})

    report = await plugin._run_one_subscription(client, "甄嬛传")

    assert client.added == []
    assert "都不在" in report


async def test_flow_ignores_share_of_another_show(monkeypatch):
    """真机 bug：尚公主搜到「黄金时段」的 7.85G 单集，大小正好在区间内被选中。

    真实分享的文件名常被改成 `24.4K-S.mp4`，所以片名匹配同时看搜索结果标题。
    """
    from nonebot_plugin_quark_autosave import subscribe as sub_mod

    monkeypatch.setattr(sub_mod.plugin_config, "sub_fallback_min_size_gb", 0.5)
    other = [_file("Primetime.2026.1080p.AMZN.WEB-DL.mkv", 7.85)]
    # 真机里这类分享的文件名常被改成 `24-4K-S.mp4`，QASx 的命名正则匹配不上，
    # 一个都转不了；这里用能匹配的写法，只验「别的剧不能选」
    real = [_file(f"尚公主.E{i}.4K.mkv", 1.2) for i in (22, 23, 24)]
    client = FakeClient(
        [],
        [
            {"shareurl": "other", "taskname": "【黄金时段 】1080p高码[中英字幕][2026]"},
            {"shareurl": "real", "taskname": "尚公主 4K更至24"},
        ],
        {"other": _detail(*other), "real": _detail(*real)},
    )

    await plugin._run_one_subscription(client, "尚公主")

    assert client.added and client.added[0].shareurl == "real"


async def test_flow_explicit_season_ignores_other_seasons():
    """真机 bug：订阅「黑镜 S05」选中了第七季的分享，把 S07E01~E06 下进了黑镜目录。"""
    other = [_file(f"Little.Black.Mirror.S07E{i:02d}.mkv", 2) for i in range(1, 7)]
    target = [_file(f"Little.Black.Mirror.S05E{i:02d}.mkv", 2) for i in range(1, 4)]
    client = FakeClient(
        [],
        [{"shareurl": "s07"}, {"shareurl": "s05"}],
        {"s07": _detail(*other), "s05": _detail(*target)},
    )

    await plugin._run_one_subscription(client, "黑镜 S05")

    task = client.added[0]
    assert task.shareurl == "s05"  # 不许选第七季那个
    # 任务 pattern 必须限定到第 5 季，别的季即使在同一分享里也不会被转存
    assert re.search(task.pattern, "Little.Black.Mirror.S05E02.2018.1080p.mkv")
    assert not re.search(task.pattern, "Little.Black.Mirror.S07E02.2018.1080p.mkv")
    assert re.sub(task.pattern, task.replace, "Little.Black.Mirror.S05E02.2018.1080p.mkv") == "S05E02.mkv"


async def test_flow_explicit_season_reports_no_season_match():
    """搜到的全是别的季 → 明确说没这季的资源，不要硬下。"""
    other = [_file(f"某剧.S07E{i:02d}.mkv", 2) for i in range(1, 4)]
    client = FakeClient([], [{"shareurl": "s07"}], {"s07": _detail(*other)})

    report = await plugin._run_one_subscription(client, "某剧 S05")

    assert client.added == []
    assert "最新" in report or "没有新集" in report


async def test_flow_scans_every_share_before_picking():
    """同一批探完再挑「集数最全」的，不能拿到第一个合格的就下。

    真机：走马上任 71 条里合格的有 6 个（9 集 / 9 集 / 7 集 / 2 集 / 7 集 / 5 集），
    同批还有别的合格分享时挑集数最多的那份。
    """
    from nonebot_plugin_quark_autosave import subscribe as sub_mod

    small = [_file(f"走马上任.E{i}.mkv", 2.5) for i in range(1, 4)]
    mid = [_file(f"走马上任.E{i}.mkv", 2.5) for i in range(1, 6)]
    big = [_file(f"走马上任.E{i}.mkv", 2.5) for i in range(1, 10)]
    client = FakeClient(
        [],
        [{"shareurl": "s"}, {"shareurl": "m"}, {"shareurl": "b"}],
        {"s": _detail(*small), "m": _detail(*mid), "b": _detail(*big)},
    )

    assert sub_mod.plugin_config.sub_max_ok_candidates == 1  # 默认扫到合格的就停
    await plugin._run_one_subscription(client, "走马上任")

    assert client.added[0].shareurl == "b"


async def test_flow_stops_after_first_usable_batch():
    """扫到符合条件（片名对 + 大小对 + 有缺集）的就停，别把剩下 170 多条全探一遍。

    用户要求：扫到一个看一个，符合条件就下，不要复盘整张搜索结果表。
    """
    files = [_file(f"甄嬛传.E{i:02d}.mkv", 2) for i in range(1, 9)]
    shares = [f"u{i}" for i in range(1, 21)]
    client = FakeClient(
        [],
        [{"shareurl": u, "taskname": "甄嬛传 更至08"} for u in shares],
        {u: _detail(*files) for u in shares},
    )
    await plugin._run_one_subscription(client, "甄嬛传")

    assert client.added and client.added[0].shareurl == "u1"
    assert len(client.probed) == 4  # 只探了第一批，后面 16 个没碰


async def test_flow_keeps_scanning_when_share_has_no_new_episodes():
    """集数不够也算不合格：本地已到 E05，分享只给 E01~E05，就得继续往后看。"""
    local = [{"file_name": f"E{i:02d}.mkv", "dir": False} for i in range(1, 6)]
    old = [_file(f"甄嬛传.E{i:02d}.mkv", 2) for i in range(1, 6)]
    new = [_file(f"甄嬛传.E{i:02d}.mkv", 2) for i in range(1, 10)]
    shares = [f"u{i}" for i in range(1, 10)]
    details = {u: _detail(*old) for u in shares[:5]}
    details.update({u: _detail(*new) for u in shares[5:]})
    client = FakeClient(
        local, [{"shareurl": u, "taskname": "甄嬛传"} for u in shares], details
    )
    await plugin._run_one_subscription(client, "甄嬛传")

    # 第一批 4 个都没新集 → 继续扫，第二批才命中
    assert client.added and client.added[0].shareurl == "u6"
    assert len(client.probed) == 8


async def test_flow_counts_only_episodes_the_pattern_will_transfer():
    """合集里混排「S02E04」和「E01」时，只能把真会转存的那几集算成新增。

    真机：法警小队 选中一个 20 个视频的分享，报「新增 S01E01~E13、S02E04~E05（15 集）」，
    实际落盘只有 3 个——因为命名规则要求文件名带季数，E01 这种被 QASx 直接跳过。
    """
    share_files = [
        _file("Marshals.S02E04.2160p.mkv", 4.35),
        _file("Marshals.S02E05.2160p.mkv", 7.52),
    ] + [_file(f"E{i:02d}.mkv", 4.6) for i in range(1, 14)]
    client = FakeClient([], [{"shareurl": "u1"}], {"u1": _detail(*share_files)})

    report = await plugin._run_one_subscription(client, "法警小队")

    assert len(client.added) == 1
    assert "新增 E04~E05（2 集）" in report
    assert "另有 13 集" in report


async def test_run_all_survives_unwritable_store(tmp_path, monkeypatch):
    """订阅文件写不进去（权限/磁盘）时，仍然要把报告发出去。

    真机复现：/app/data/subscriptions.json 只读 → record_result 抛 PermissionError，
    整轮被标成「执行失败」，用户收不到这一轮的转存结果。
    """
    from nonebot_plugin_quark_autosave import subscribe as sub_mod

    sent = []
    monkeypatch.setattr(plugin.store, "list_all", lambda: ["黑镜 S05"])
    monkeypatch.setattr(sub_mod.SubscriptionStore, "save", _raise_perm)
    monkeypatch.setattr(plugin, "_run_one_subscription", _fake_run)
    monkeypatch.setattr(plugin, "_report", _capture(sent))

    await plugin._run_all_subscriptions()

    assert sent and "S05E01~E03" in sent[0]


def _raise_perm(*_a, **_k):
    raise PermissionError("read-only")


async def _fake_run(client, name):
    return "✅ 《黑镜 S05》新增文件:\n/_bot自检订阅/黑镜\n├── S05E01~E03（3 集）"


def _capture(bucket):
    async def _report(text):
        bucket.append(text)

    return _report
