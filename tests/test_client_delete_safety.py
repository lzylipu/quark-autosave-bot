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

    async def update_tasklist(self, tasklist, *, removing=()):
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

    from nonebot_plugin_quark_autosave.model import TaskItem as T

    seen = {}

    class Cap(QASClient):
        async def get_data_raw(self):
            return {"tasklist": [], "webui": {"username": "u"}}

        async def update_tasklist(self, tasklist, *, removing=()):
            seen["tasklist"] = tasklist
            return "ok"

    async def run():
        await Cap().add_task(T(taskname="t", shareurl="u", savepath="/x", addition=None))

    asyncio.run(run())
    assert seen["tasklist"][-1]["addition"] == {}


def test_add_task_does_not_use_server_side_append():
    """add_task 必须先读文件再写回，不能走 /api/add_task 的内存态 append。

    实测：QASx 内存态落后于配置文件时，/api/add_task 会把文件里其他任务整份覆盖掉。
    """
    import asyncio

    from nonebot_plugin_quark_autosave.model import TaskItem as T

    existing = [{"taskname": "别人刚加的", "shareurl": "u-x", "savepath": "/x", "addition": {}}]
    calls = []

    class Cap(QASClient):
        async def get_data_raw(self):
            return {"tasklist": [dict(t) for t in existing]}

        async def update_tasklist(self, tasklist, *, removing=()):
            calls.append(tasklist)
            return "ok"

        async def _request_with_retry(self, method, url, **kw):
            calls.append(("RAW", url))
            raise AssertionError(f"不该调 {url}")

    async def run():
        await Cap().add_task(T(taskname="new", shareurl="u-new", savepath="/x"))

    asyncio.run(run())
    assert len(calls) == 1, f"应只调用一次 update_tasklist，实际 {calls}"
    assert [t["taskname"] for t in calls[0]] == ["别人刚加的", "new"]


def test_delete_retries_when_qasx_writes_task_back(monkeypatch):
    """QASx 进程把内存态整份写回时，删掉的任务会“复活”，必须再删一次。

    实测：正式 QASx 里外部删掉的自检任务一段时间后又出现在配置里。
    """
    import asyncio

    from nonebot_plugin_quark_autosave import client as client_mod

    monkeypatch.setattr(client_mod, "DELETE_VERIFY_DELAY", 0)

    class Resurrecting(RawClient):
        def __init__(self, tasklist, resurrect_times=1):
            super().__init__(tasklist)
            self.resurrect_times = resurrect_times

        async def update_tasklist(self, tasklist, *, removing=()):
            res = await super().update_tasklist(tasklist)
            if self.resurrect_times > 0 and not any(
                t["taskname"] == "victim" for t in tasklist
            ):
                self.resurrect_times -= 1
                self.tasklist = list(tasklist) + [_task("victim", "u3")]
            return res

    victim = TaskItem(taskname="victim", shareurl="u3", savepath="/x")

    c = Resurrecting([_task("a", "u1"), _task("victim", "u3")], resurrect_times=1)
    assert asyncio.run(c.delete_task(victim)) == "victim"
    assert [t["taskname"] for t in c.tasklist] == ["a"]
    assert c.resurrect_times == 0

    # 一直复活 → 不能假装成功
    c2 = Resurrecting([_task("a", "u1"), _task("victim", "u3")], resurrect_times=99)
    with pytest.raises(QASException):
        asyncio.run(c2.delete_task(victim))


def test_simple_from_title_recurses_into_subdirs():
    """分享根常是「文件夹套文件夹」，必须带 update_subdir 否则 QASx 一个文件都不转存。"""
    task = TaskItem.simple_from_title("某剧", "https://pan.quark.cn/s/abc")
    assert task.update_subdir == ".*"
    assert task.pattern == "" and task.replace == ""
    assert TaskItem.template("t", "u").update_subdir == ".*"


def test_add_task_payload_carries_update_subdir():
    import asyncio

    seen = {}

    class Cap(QASClient):
        async def get_data_raw(self):
            return {"tasklist": []}

        async def update_tasklist(self, tasklist, *, removing=()):
            seen["tasklist"] = tasklist
            return "ok"

    async def run():
        await Cap().add_task(TaskItem.simple_from_title("某剧", "https://pan.quark.cn/s/abc"))

    asyncio.run(run())
    assert seen["tasklist"][-1]["update_subdir"] == ".*"


def test_delete_task_does_not_report_intentional_removal_as_lost(monkeypatch):
    """删自己这条任务不该报「丢失了其他任务」——之前真机上刷了假 error。"""
    import asyncio

    import httpx

    from nonebot_plugin_quark_autosave import client as client_mod

    monkeypatch.setattr(client_mod, "DELETE_VERIFY_DELAY", 0)
    errors = []
    monkeypatch.setattr(client_mod.logger, "error", lambda msg: errors.append(msg))

    state = {"tasklist": [_task("a", "u1"), _task("victim", "u3")]}

    class Real(QASClient):
        async def get_data_raw(self):
            return {"tasklist": [dict(t) for t in state["tasklist"]]}

        async def _request_with_retry(self, method, url, **kw):
            assert url == "/update"
            state["tasklist"] = [dict(t) for t in kw["json"]["tasklist"]]
            return httpx.Response(200, json={"success": True, "data": {"message": "ok"}})

    asyncio.run(Real().delete_task(TaskItem(taskname="victim", shareurl="u3", savepath="/x")))
    assert [t["taskname"] for t in state["tasklist"]] == ["a"]
    assert not errors, errors


def test_update_tasklist_reports_real_concurrent_loss(monkeypatch):
    """别的写入者把任务吞了，必须报 error（这是真有并发时的护栏）。"""
    import asyncio

    import httpx

    from nonebot_plugin_quark_autosave import client as client_mod

    errors = []
    monkeypatch.setattr(client_mod.logger, "error", lambda msg: errors.append(msg))

    state = {"tasklist": [_task("a", "u1"), _task("b", "u2"), _task("victim", "u3")]}

    class Real(QASClient):
        async def get_data_raw(self):
            return {"tasklist": [dict(t) for t in state["tasklist"]]}

        async def _request_with_retry(self, method, url, **kw):
            # 服务端写回时把 b 弄丢了（模拟内存态覆盖）
            state["tasklist"] = [
                dict(t) for t in kw["json"]["tasklist"] if t["taskname"] != "b"
            ]
            return httpx.Response(200, json={"success": True, "data": {"message": "ok"}})

    asyncio.run(
        Real().update_tasklist(
            [_task("a", "u1"), _task("victim", "u3")], removing=["victim"]
        )
    )
    assert any("丢失了其他任务" in e and "b" in e for e in errors), errors


def test_delete_file_reads_raw_quark_response():
    """/delete_file 不像其它接口那样包 success/data，是夸克原始响应（code==0）。"""
    import asyncio

    import httpx

    class Cap(QASClient):
        def __init__(self, payload):
            self.payload = payload

        async def _request_with_retry(self, method, url, **kw):
            assert url == "/delete_file"
            return httpx.Response(200, json=self.payload)

    assert asyncio.run(Cap({"status": 200, "code": 0, "data": {"finish": False}}).delete_file("f1"))
    assert not asyncio.run(Cap({"status": 400, "code": 23004, "message": "文件不存在"}).delete_file("f2"))


def test_bot_tasks_are_one_shot_skip_calendar():
    """bot 建的任务必须是一次性任务（skip_calendar），否则 QASx 后台线程会把配置写回。

    上游 app/run.py:3189 用 skip_calendar 跳过日历匹配；不跳过时
    process_single_task_async 会 Config.write_json(CONFIG_PATH, config_data) 整份写盘，
    实测把刚删掉的任务写回来。
    """
    from nonebot_plugin_quark_autosave.model import TaskItem as T

    assert T.simple_from_title("某剧", "https://pan.quark.cn/s/abc").skip_calendar is True
    assert T.template("t", "u").skip_calendar is True
    # 手搓任务默认关，避免影响别的调用
    assert T(taskname="t", shareurl="u", savepath="/x").skip_calendar is False
