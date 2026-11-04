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

    async def list_savepath_files(self, savepath):
        return self.local

    async def task_suggestions(self, query):
        return self.results

    async def get_share_detail(self, task):
        return self.details[task.shareurl]

    async def get_share_files(self, shareurl, max_depth=3, max_dirs=40):
        # 真实实现会递归展开子目录；测试里 details 直接给全量文件
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
