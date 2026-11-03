"""删除任务：走原始 dict 写回，行为锁死。"""

from copy import deepcopy

import pytest

from nonebot_plugin_quark_autosave.client import QASClient
from nonebot_plugin_quark_autosave.exception import QASException
from nonebot_plugin_quark_autosave.model import TaskItem


def make_task(name: str, url: str) -> TaskItem:
    return TaskItem.simple_from_title(name, url)


def raw_task(name: str, url: str) -> dict:
    return {"taskname": name, "shareurl": url, "savepath": "/x", "addition": {}}


class FakeConfig:
    """模拟 QAS 的 /data（原始 dict）与 /update 写回。"""

    def __init__(self, tasklist, persist=True):
        self.tasklist = tasklist
        self.persist = persist
        self.writes = 0

    def client(self) -> QASClient:
        client = QASClient()
        fake = self

        async def get_data_raw():
            return {"tasklist": deepcopy(fake.tasklist), "webui": {"username": "u"}}

        async def update_tasklist(tasklist, *, removing=()):
            fake.writes += 1
            client._sanitize(tasklist)  # 真实实现同样会清洗
            if fake.persist:
                fake.tasklist = deepcopy(tasklist)
            return "ok"

        client.get_data_raw = get_data_raw
        client.update_tasklist = update_tasklist
        return client


async def test_delete_removes_target_even_if_order_changes():
    cfg = FakeConfig([raw_task("目标", "u1"), raw_task("其他", "u2")])
    deleted = await cfg.client().delete_task(make_task("目标", "u1"))
    assert deleted == "目标"
    assert [t["taskname"] for t in cfg.tasklist] == ["其他"]


async def test_delete_only_removes_one_duplicate():
    cfg = FakeConfig([raw_task("目标", "u1"), raw_task("目标", "u1")])
    await cfg.client().delete_task(make_task("目标", "u1"))
    assert len(cfg.tasklist) == 1


async def test_delete_raises_when_write_does_not_persist():
    cfg = FakeConfig([raw_task("目标", "u1")], persist=False)
    with pytest.raises(QASException, match="任务删除未生效"):
        await cfg.client().delete_task(make_task("目标", "u1"))


async def test_delete_does_not_touch_unrelated_task():
    cfg = FakeConfig([raw_task("其他", "u2")])
    with pytest.raises(QASException, match="未找到任务"):
        await cfg.client().delete_task(make_task("目标", "u1"))
    assert cfg.writes == 0
    assert [t["taskname"] for t in cfg.tasklist] == ["其他"]


async def test_delete_by_name_and_url_both_required():
    """同名但不同链接不能误删。"""
    cfg = FakeConfig([raw_task("目标", "u-other")])
    with pytest.raises(QASException, match="未找到任务"):
        await cfg.client().delete_task(make_task("目标", "u-target"))
