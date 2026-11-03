"""删除任务走原始 dict 写回：不丢字段、不被 addition=null 打成 500。"""

import pytest

from nonebot_plugin_quark_autosave.client import QASClient
from nonebot_plugin_quark_autosave.exception import QASException
from nonebot_plugin_quark_autosave.model import TaskItem


class RawClient(QASClient):
    """模拟 QAS 的 /data + /update；update 严格模仿上游：addition 非 dict 就 500。"""

    def __init__(self, tasklist):
        self.tasklist = tasklist
        self.updates = []

    async def get_data_raw(self):
        return {"tasklist": self.tasklist, "webui": {"username": "u"}}

    async def update_tasklist(self, tasklist):
        self._sanitize(tasklist)
        for t in tasklist:
            if not isinstance(t.get("addition"), dict):
                raise QASException("500 sync_task_plugins_config: addition is None")
        self.updates.append(tasklist)
        self.tasklist = tasklist
        return "ok"


def _task(name, url, **extra):
    return {"taskname": name, "shareurl": url, "savepath": "/x", "addition": {}, **extra}


async def test_delete_works_when_some_task_has_null_addition():
    client = RawClient([
        _task("a", "u1"),
        {"taskname": "dirty", "shareurl": "u2", "savepath": "/x", "addition": None},
        _task("victim", "u3"),
    ])
    removed = await client.delete_task(TaskItem(taskname="victim", shareurl="u3", savepath="/x"))
    assert removed == "victim"
    assert [t["taskname"] for t in client.tasklist] == ["a", "dirty"]
    # 脏任务被修好，不再是 None
    assert isinstance(client.tasklist[1]["addition"], dict)


async def test_delete_preserves_fields_model_does_not_know():
    client = RawClient([
        _task("rich", "u1", calendar_info={"match": {"tmdb_id": 9}}, source="webui",
              task_plugins={"plex": {"enable": True}}),
        _task("victim", "u3"),
    ])
    await client.delete_task(TaskItem(taskname="victim", shareurl="u3", savepath="/x"))
    rich = client.tasklist[0]
    assert rich["calendar_info"] == {"match": {"tmdb_id": 9}}
    assert rich["source"] == "webui"
    assert rich["task_plugins"] == {"plex": {"enable": True}}


async def test_delete_missing_task_raises():
    client = RawClient([_task("a", "u1")])
    with pytest.raises(QASException):
        await client.delete_task(TaskItem(taskname="nope", shareurl="u9", savepath="/x"))
    assert client.updates == []


async def test_delete_same_name_twice_only_removes_one():
    client = RawClient([_task("dup", "u1"), _task("dup", "u1")])
    await client.delete_task(TaskItem(taskname="dup", shareurl="u1", savepath="/x"))
    assert len(client.tasklist) == 1


def test_add_task_payload_never_has_null_addition():
    """add_task 不能把 addition 写成 null，否则后续任何 /update 都会 500。"""
    import asyncio

    seen = {}

    class Cap(QASClient):
        async def _request_with_retry(self, method, url, **kw):
            seen["json"] = kw.get("json")
            from nonebot_plugin_quark_autosave.model import TaskItem as T

            class R:
                status_code = 200

                @staticmethod
                def json():
                    return {"success": True, "data": seen["json"]}

            return R()

    async def run():
        await Cap().add_task(TaskItem(taskname="t", shareurl="u", savepath="/x", addition=None))

    asyncio.run(run())
    assert seen["json"]["addition"] == {}
