"""get_share_files 递归展开：分享根是文件夹时也要能拿到里面的视频。"""

import pytest

from nonebot_plugin_quark_autosave.client import QASClient
from nonebot_plugin_quark_autosave.exception import QASException
from nonebot_plugin_quark_autosave.model import DetailInfo, FileItem

BASE = "https://pan.quark.cn/s/abc"


def _file(name, fid, size=0, dir_=False):
    return FileItem(fid=fid, file_name=name, updated_at=0, size=size, dir=dir_)


def _detail(files):
    return DetailInfo(
        is_owner=1,
        share={
            "title": "t",
            "share_type": 0,
            "share_id": "s",
            "pwd_id": "p",
            "share_url": BASE,
            "url_type": 1,
            "first_fid": "d1",
            "expired_type": 1,
            "file_num": len(files),
            "created_at": 0,
            "updated_at": 0,
            "expired_at": 0,
            "expired_left": 0,
            "audit_status": 4,
            "status": 1,
            "click_pv": 0,
            "save_pv": 0,
            "download_pv": 0,
        },
        list=files,
        stoken="st",
    )


class FakeDetailClient(QASClient):
    """把 get_share_detail 换成本地图，记录调用过的 URL。"""

    def __init__(self, tree):
        self.tree = tree
        self.calls: list[str] = []

    async def get_share_detail(self, task):
        self.calls.append(task.shareurl)
        key = task.shareurl
        if key not in self.tree:
            raise QASException("分享地址已失效")
        return self.tree[key]


async def test_expands_nested_folder():
    tree = {
        BASE: _detail([_file("三体", "d1", dir_=True), _file("说明.txt", "f1")]),
        f"{BASE}#/list/share/d1": _detail([_file("S01E01.mkv", "v1", 2 ** 30), _file("S01E02.mkv", "v2", 2 ** 30)]),
    }
    c = FakeDetailClient(tree)
    files = await c.get_share_files(BASE)
    assert [f.file_name for f in files] == ["说明.txt", "S01E01.mkv", "S01E02.mkv"]
    assert c.calls == [BASE, f"{BASE}#/list/share/d1"]


async def test_respects_max_depth():
    tree = {
        BASE: _detail([_file("a", "d1", dir_=True)]),
        f"{BASE}#/list/share/d1": _detail([_file("b", "d2", dir_=True)]),
        f"{BASE}#/list/share/d2": _detail([_file("S01E01.mkv", "v1")]),
    }
    c = FakeDetailClient(tree)
    files = await c.get_share_files(BASE, max_depth=1)
    assert files == []  # d2 超出深度，被跳过
    assert f"{BASE}#/list/share/d2" not in c.calls


async def test_does_not_revisit_same_folder():
    # 自我引用的目录不会死循环
    tree = {
        BASE: _detail([_file("loop", "d1", dir_=True), _file("x.mkv", "v1")]),
        f"{BASE}#/list/share/d1": _detail([_file("loop", "d1", dir_=True), _file("y.mkv", "v2")]),
    }
    c = FakeDetailClient(tree)
    files = await c.get_share_files(BASE)
    assert sorted(f.file_name for f in files) == ["x.mkv", "y.mkv"]
    assert c.calls.count(f"{BASE}#/list/share/d1") == 1


async def test_expired_nested_link_propagates():
    tree = {BASE: _detail([_file("a", "d1", dir_=True)])}
    c = FakeDetailClient(tree)
    with pytest.raises(QASException):
        await c.get_share_files(BASE)


async def test_share_nodes_expose_each_nested_folder_as_candidate():
    tree = {
        BASE: _detail(
            [
                _file("4K DV", "dv", dir_=True),
                _file("4K SDR", "sdr", dir_=True),
            ]
        ),
        f"{BASE}#/list/share/dv": _detail(
            [
                _file("S01E01.DV.mkv", "dv1", 2**30),
                _file("S01E02.DV.mkv", "dv2", 2**30),
            ]
        ),
        f"{BASE}#/list/share/sdr": _detail(
            [
                _file("S01E01.SDR.mkv", "sdr1", 2**30),
                _file("S01E02.SDR.mkv", "sdr2", 2**30),
            ]
        ),
    }
    c = FakeDetailClient(tree)

    nodes = await c.get_share_nodes(BASE)

    assert [(node.path, node.depth) for node in nodes] == [
        ("/", 0),
        ("/4K DV", 1),
        ("/4K SDR", 1),
    ]
    assert sorted(f.file_name for f in nodes[0].videos) == [
        "S01E01.DV.mkv",
        "S01E01.SDR.mkv",
        "S01E02.DV.mkv",
        "S01E02.SDR.mkv",
    ]
    assert [f.file_name for f in nodes[1].videos] == [
        "S01E01.DV.mkv",
        "S01E02.DV.mkv",
    ]
    assert nodes[1].url == f"{BASE}#/list/share/dv"


async def test_share_nodes_can_start_from_an_existing_nested_url():
    nested = f"{BASE}#/list/share/d1"
    tree = {
        nested: _detail(
            [
                _file("版本 A", "d2", dir_=True),
                _file("S01E01.mkv", "v1", 2**30),
            ]
        ),
        f"{BASE}#/list/share/d2": _detail(
            [_file("S01E02.mkv", "v2", 2**30)]
        ),
    }
    c = FakeDetailClient(tree)

    nodes = await c.get_share_nodes(nested)

    assert nodes[0].url == nested
    assert [f.file_name for f in nodes[0].videos] == [
        "S01E01.mkv",
        "S01E02.mkv",
    ]
    assert nodes[1].url == f"{BASE}#/list/share/d2"
    assert nodes[1].path == "/版本 A"
