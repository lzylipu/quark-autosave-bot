"""订阅执行编排：用假 client 跑通「扫本地 → 搜索 → 筛选 → 建任务 → 删任务」。"""

import re
from typing import Any

import nonebot_plugin_quark_autosave as plugin
from nonebot_plugin_quark_autosave.client import ShareNode
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
    def __init__(
        self,
        local,
        results,
        details,
        output=None,
        land: Any = "all",
        records=None,
        nodes=None,
    ):
        self.local = local
        self.results = results
        self.details = details
        self.output = output or ["✅《甄嬛传》新增文件:\n/自动/甄嬛传\n├── S01E10.mkv"]
        # 转存后真正落盘哪些文件：'all' = 该分享里命名规则命中的全落；
        # 'none' = 一个都不落（复现 QASx 按 file_id + 任务名去重把整轮挡掉）；
        # 一组子串 = 只有文件名含这些子串的落下。
        self.land = land
        self.records = records or []
        self.cleared_records = []
        self.added = []
        self.deleted = []
        # 探过详情的分享：早停测试要数「到底探了几个」
        self.probed = []
        # 分享目录树：{shareurl: [ShareNode, ...]}；不给就是「一层根目录，文件全在根下」
        self.nodes = nodes or {}

    def _files(self, url):
        """这条链接（根或 `#/list/share/<fid>` 子目录）下能转存的文件。"""
        for node in self.nodes.get(url.split("#", 1)[0], []):
            if node.url == url:
                return list(node.videos)
        detail = self.details.get(url)
        if detail is None:
            detail = self.details[url.split("#", 1)[0]]
        return list(detail.file_list)

    async def list_savepath_files(self, savepath):
        return self.local

    async def task_suggestions(self, query):
        return self.results

    async def get_share_detail(self, task):
        return self.details[task.shareurl]

    async def get_share_nodes(self, shareurl, max_depth=6, max_dirs=80):
        self.probed.append(shareurl)
        if shareurl in self.nodes:
            return list(self.nodes[shareurl])
        return [ShareNode(url=shareurl, path="/", depth=0, videos=self._files(shareurl))]

    async def get_share_files(self, shareurl, max_depth=6, max_dirs=80):
        # 真实实现会递归展开子目录；测试里 details 直接给全量文件
        self.probed.append(shareurl)
        return self._files(shareurl)

    async def history_records(self, task_name, page_size=100):
        return list(self.records)

    async def delete_history_records(self, record_ids):
        self.cleared_records.extend(record_ids)
        return len(record_ids)

    async def add_task(self, task):
        self.added.append(task)
        return task

    async def run_script(self, task):
        spec = self.land
        if isinstance(spec, dict):
            spec = spec.get(task.shareurl, "all")
        if spec:
            names = [f.file_name for f in self._files(task.shareurl)]
            if spec != "all":
                names = [n for n in names if any(k in n for k in spec)]
            for name in names:
                if re.search(task.pattern, name):
                    self.local.append(
                        {
                            "file_name": re.sub(task.pattern, task.replace, name),
                            "dir": False,
                        }
                    )
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
    # 同一集已有 mkv 时不再存一份 mp4（QASx 不开这个按完整文件名去重）
    assert task.ignore_extension is True
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
    assert "别的季" in report and "第 5 季" in report


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
    """带季的分享里只下目标季，别的季不碰、也不算进「新增几集」。

    真机：法警小队 选中一个混排分享，报「新增 15 集」，实际落盘只有 3 个。
    """
    share_files = [_file(f"Marshals.S01E{i:02d}.1080p.mkv", 4.6) for i in range(1, 6)]
    share_files += [
        _file("Marshals.S02E04.2160p.mkv", 4.35),
        _file("Marshals.S02E05.2160p.mkv", 7.52),
    ]
    client = FakeClient([], [{"shareurl": "u1"}], {"u1": _detail(*share_files)})

    report = await plugin._run_one_subscription(client, "法警小队")

    assert len(client.added) == 1
    assert "新增 E01~E05（5 集）" in report
    assert "S02" not in report  # 第二季不参与
    # 命名规则换成「本季标记可有可无」的版本，捕获组整体后移，落到 S01E05.mkv
    assert re.sub(client.added[0].pattern, client.added[0].replace,
                  "Marshals.S01E05.1080p.mkv") == "S01E05.mkv"
    assert not re.search(client.added[0].pattern, "Marshals.S02E04.2160p.mkv")


async def test_flow_skips_share_missing_a_pending_episode():
    """本地 E01~E10、该补 E11+E12：只有 E12 的链接必须跳过，选 E11+E12 的那条。

    用户原话：「他只有个 12，他没有 11……你这样再去下，他就错过了，所以这条链接忽略掉」。
    """
    local = [{"file_name": f"S01E{i:02d}.mkv", "dir": False} for i in range(1, 11)]
    only12 = [_file("甄嬛传.S01E12.mkv", 2)]
    both = [_file("甄嬛传.S01E11.mkv", 2), _file("甄嬛传.S01E12.mkv", 2)]
    client = FakeClient(
        local,
        [{"shareurl": "partial"}, {"shareurl": "full"}],
        {"partial": _detail(*only12), "full": _detail(*both)},
    )

    report = await plugin._run_one_subscription(client, "甄嬛传")

    assert client.added and client.added[0].shareurl == "full"
    assert "E11~E12" in report


async def test_flow_reports_missing_when_no_share_covers_everything():
    """一个能补全的链接都没有时，仍然下，但必须写明这条缺哪几集。"""
    local = [{"file_name": f"S01E{i:02d}.mkv", "dir": False} for i in range(1, 11)]
    only12 = [_file("甄嬛传.S01E12.mkv", 2)]
    client = FakeClient(
        local, [{"shareurl": "partial"}], {"partial": _detail(*only12)}
    )

    report = await plugin._run_one_subscription(client, "甄嬛传")

    assert len(client.added) == 1
    assert "缺 E11" in report


async def test_flow_fills_gap_when_local_is_missing_middle_episodes():
    """本地被手动删掉两集时，优先挑全集分享把那两集补回来。

    用户实测「有个电视剧缺两集」：只收更新包的话，中间缺的永远补不上。
    """
    local = [{"file_name": f"S01E{i:02d}.mkv", "dir": False} for i in (1, 2, 3, 4, 5, 8)]
    update = [_file(f"某剧.S01E{i:02d}.mkv", 2) for i in (9, 10, 11, 12)]
    full = [_file(f"某剧.S01E{i:02d}.mkv", 2) for i in range(1, 13)]
    client = FakeClient(
        local,
        [{"shareurl": "update"}, {"shareurl": "full"}],
        {"update": _detail(*update), "full": _detail(*full)},
    )

    report = await plugin._run_one_subscription(client, "某剧")

    assert client.added and client.added[0].shareurl == "full"
    assert "E06" in report  # 缺的中间集一起补


async def test_flow_locks_first_season_when_name_has_no_season():
    """订阅名没写季就只下第一季，不会把第二季的集当成本季缺集。"""
    share_files = [_file(f"某美剧.S02E{i:02d}.mkv", 2) for i in range(1, 4)]
    client = FakeClient([], [{"shareurl": "u1"}], {"u1": _detail(*share_files)})

    report = await plugin._run_one_subscription(client, "某美剧")

    assert client.added == []
    assert "别的季" in report  # 是第二季的分享，没写季就当第一季，不下


async def test_flow_refuses_share_when_pattern_matches_nothing():
    """分享里全是裸 E01 且混了别的季时，不猜归属：一个都匹配不上就不建任务。"""
    share_files = [
        _file("Marshals.S02E04.2160p.mkv", 4.35),
        _file("Marshals.S02E05.2160p.mkv", 7.52),
    ] + [_file(f"E{i:02d}.mkv", 4.6) for i in range(1, 14)]
    client = FakeClient([], [{"shareurl": "u1"}], {"u1": _detail(*share_files)})

    report = await plugin._run_one_subscription(client, "法警小队")

    assert client.added == []
    assert "别的季" in report  # 带季的只有第二季，裸 E01 不猜归属


async def test_flow_retries_next_share_when_nothing_lands():
    """真机 bug：走马上任的 11 集早就在 QASx 的 transfer_records 里（file_id + 任务名），
    同名片子再建任务只会回「没有新的文件需要转存」，一个都不落 → 必须换下一条分享。

    A/B 实测：taskname 换成别的 → 13 个文件全落盘；只换 savepath → 仍 0 个。
    """
    dead = [_file(f"走马上任.E{i:02d}.mkv", 2.5) for i in range(1, 6)]
    alive = [_file(f"走马上任.{i:02d}.mkv", 2.5) for i in range(1, 6)]
    client = FakeClient(
        [],
        [{"shareurl": "dead"}, {"shareurl": "alive"}],
        {"dead": _detail(*dead), "alive": _detail(*alive)},
        land={"dead": "none"},
    )

    report = await plugin._run_one_subscription(client, "走马上任")

    assert [t.shareurl for t in client.added] == ["dead", "alive"]
    assert "前面 1 条分享没落下文件" in report
    assert "E01~E05" in report
    # 试过的任务都要删干净，不能留在 QAS 里
    assert [t.shareurl for t in client.deleted] == ["dead", "alive"]


async def test_flow_reports_failure_when_no_share_lands_anything():
    """全都落 0 个时不许假装成功，要写明是转存记录挡住的。"""
    files = [_file(f"走马上任.E{i:02d}.mkv", 2.5) for i in range(1, 6)]
    client = FakeClient(
        [],
        [{"shareurl": "a"}, {"shareurl": "b"}],
        {"a": _detail(*files), "b": _detail(*files)},
        land="none",
    )

    report = await plugin._run_one_subscription(client, "走马上任")

    assert len(client.added) == 2
    assert "试了 2 条分享，一个文件都没落下" in report
    assert "转存记录" in report


async def test_flow_warns_about_duplicate_episode_files():
    """真机：走马上任 的分享里 07.mkv 和 S01E07.mkv 是同一集，QASx 认不出，各落一份。

    落盘就成了 S01E07.mkv + 07.mkv（改名撞名保留原名），命名不统一。只提示，不弃用。
    """
    files = [_file(f"走马上任.S01E{i:02d}.mkv", 2.5) for i in range(1, 8)]
    files += [_file("07.mkv", 2.9)]  # 同一集的第二份
    client = FakeClient([], [{"shareurl": "u1"}], {"u1": _detail(*files)})

    report = await plugin._run_one_subscription(client, "走马上任")

    assert "各有两份文件" in report
    assert "E07" in report


async def test_flow_clears_stale_records_for_missing_episodes():
    """真机：走马上任 11 集全在 QASx 转存记录里，目录却是空的，于是永远「没有新文件」。

    记录说转过、目录里却没有 = 记录过期，先清掉这几条才能重下。
    """
    share_files = [_file(f"走马上任.S01E{i:02d}.mkv", 2.5) for i in range(1, 4)]
    records = [
        {"id": 11, "task_name": "走马上任", "save_path": "/自动/走马上任",
         "renamed_to": "S01E01.mkv"},
        {"id": 12, "task_name": "走马上任", "save_path": "/自动/走马上任",
         "renamed_to": "S01E02.mkv"},
        # 别的目录的记录不归这次管
        {"id": 13, "task_name": "走马上任", "save_path": "/别处/走马上任",
         "renamed_to": "S01E03.mkv"},
        # 别的季的记录也不能删
        {"id": 14, "task_name": "走马上任", "save_path": "/自动/走马上任",
         "renamed_to": "S02E03.mkv"},
    ]
    client = FakeClient(
        [], [{"shareurl": "u1"}], {"u1": _detail(*share_files)}, records=records
    )

    report = await plugin._run_one_subscription(client, "走马上任")

    assert client.cleared_records == [11, 12]
    assert "清掉 2 条过期转存记录" in report


async def test_flow_keeps_records_when_file_is_still_there():
    """目录里那集还在 → 记录有效，不许删。"""
    local = [{"file_name": "S01E01.mkv", "dir": False}]
    share_files = [_file(f"走马上任.S01E{i:02d}.mkv", 2.5) for i in range(1, 4)]
    records = [
        {"id": 21, "task_name": "走马上任", "save_path": "/自动/走马上任",
         "renamed_to": "S01E01.mkv"},
    ]
    client = FakeClient(
        local, [{"shareurl": "u1"}], {"u1": _detail(*share_files)}, records=records
    )

    await plugin._run_one_subscription(client, "走马上任")

    assert client.cleared_records == []


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


async def test_flow_picks_clean_version_folder_in_nested_share():
    """嵌套分享：根目录把两个版本并成一份，只有子目录里是干净的一整套。

    真机：尚公主 一条分享是 `剧名/4K 高码率/…` 和 `剧名/4K 杜比视界/…`。
    选中根目录 = 每集两份文件，QASx 会把两个版本都转进来（落盘 `S01E07.1.mkv`）。
    正确做法是把任务链接指到其中一层（`shareurl#/list/share/<fid>`）。
    """
    local = [{"file_name": f"S01E{i:02d}.mkv", "dir": False} for i in range(1, 10)]
    dv = [_file(f"S01E{i:02d}.DV.mkv", 2.5) for i in range(1, 28)]
    sdr = [_file(f"S01E{i:02d}.SDR.mkv", 2.4) for i in range(1, 28)]
    url = "https://pan.quark.cn/s/abc"
    client = FakeClient(
        local,
        [{"shareurl": url, "taskname": "尚公主"}],
        {url: _detail(*(dv + sdr))},
        nodes={
            url: [
                ShareNode(url=url, path="/", depth=0, videos=dv + sdr),
                ShareNode(
                    url=f"{url}#/list/share/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    path="/4K DV 60帧",
                    depth=1,
                    videos=dv,
                ),
                ShareNode(
                    url=f"{url}#/list/share/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                    path="/4K SDR 60帧",
                    depth=1,
                    videos=sdr,
                ),
            ]
        },
    )

    report = await plugin._run_one_subscription(client, "尚公主")

    assert len(client.added) == 1
    task = client.added[0]
    # 选中干净的版本目录，而不是把两个版本都并进去的根目录
    assert task.shareurl.endswith("#/list/share/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    assert "4K DV 60帧" in report
    # 只补 E10~E27，本地已有的 E01~E09 一个都不许重下
    assert "E10~E27" in report
    landed = sorted(f["file_name"] for f in client.local[9:])
    assert landed == [f"S01E{i:02d}.mkv" for i in range(10, 28)]
    # 落盘不能出现 .1 副本
    assert not [n for n in landed if ".1." in n]


async def test_flow_transfers_only_missing_episodes():
    """本地已有的集不许重下：只把缺的那几集交给 QASx。

    真机：尚公主 本地 E01~E09、E16~E27，一条 27 集的分享整份转存会落 18 个文件
    （只有 8 集是新的），夸克对同名文件追加 `.1`，目录里就开始出现 S01E07.1.mkv。
    """
    local = [{"file_name": f"S01E{i:02d}.mp4", "dir": False} for i in list(range(1, 10)) + list(range(16, 28))]
    before = len(local)
    share = [_file(f"尚公主.S01E{i:02d}.4K.mkv", 2.2) for i in range(1, 28)]
    client = FakeClient(
        local, [{"shareurl": "u1", "taskname": "尚公主"}], {"u1": _detail(*share)}
    )

    report = await plugin._run_one_subscription(client, "尚公主")

    task = client.added[0]
    assert "E10~E15" in report
    # 只有 6 个新文件落地，其余 21 集一次都没碰
    landed = sorted(f["file_name"] for f in client.local[before:])
    assert landed == [f"S01E{i:02d}.mkv" for i in range(10, 16)]
    # 已有的集不会出现在命名规则里
    for ep in (7, 16, 27):
        assert not re.search(task.pattern, f"尚公主.S01E{ep:02d}.4K.mkv")
