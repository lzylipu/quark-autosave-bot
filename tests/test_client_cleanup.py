from copy import deepcopy

import pytest

from nonebot_plugin_quark_autosave.client import QASClient
from nonebot_plugin_quark_autosave.exception import QASException
from nonebot_plugin_quark_autosave.model import AutosaveData, TaskItem


def make_task(name: str, url: str) -> TaskItem:
    return TaskItem.simple_from_title(name, url)


def make_data(tasks: list[TaskItem]) -> AutosaveData:
    return AutosaveData(
        cookie=[],
        api_token="",
        crontab="",
        tasklist=tasks,
        magic_regex={},
        source={},
        push_config={},
        plugins={},
        task_plugins_config_default={},
    )


@pytest.mark.asyncio
async def test_delete_task_removes_matching_task_even_if_list_order_changes(monkeypatch):
    target = make_task("目标", "https://pan.quark.cn/s/target")
    state = make_data(
        [
            target,
            make_task("其他", "https://pan.quark.cn/s/other"),
        ]
    )
    client = QASClient()

    async def get_data():
        return deepcopy(state)

    async def update(data):
        nonlocal state
        state = deepcopy(data)
        return "ok"

    monkeypatch.setattr(client, "get_data", get_data)
    monkeypatch.setattr(client, "update", update)

    deleted_name = await client.delete_task(target)

    assert deleted_name == "目标"
    assert [task.taskname for task in state.tasklist] == ["其他"]


@pytest.mark.asyncio
async def test_delete_task_only_removes_one_matching_duplicate(monkeypatch):
    target = make_task("目标", "https://pan.quark.cn/s/target")
    state = make_data([target, deepcopy(target)])
    client = QASClient()

    async def get_data():
        return deepcopy(state)

    async def update(data):
        nonlocal state
        state = deepcopy(data)
        return "ok"

    monkeypatch.setattr(client, "get_data", get_data)
    monkeypatch.setattr(client, "update", update)

    await client.delete_task(target)

    assert len(state.tasklist) == 1


@pytest.mark.asyncio
async def test_delete_task_raises_when_update_does_not_persist(monkeypatch):
    target = make_task("目标", "https://pan.quark.cn/s/target")
    state = make_data([target])
    client = QASClient()

    async def get_data():
        return deepcopy(state)

    async def update(_data):
        return "ok"

    monkeypatch.setattr(client, "get_data", get_data)
    monkeypatch.setattr(client, "update", update)

    with pytest.raises(QASException, match="任务删除未生效"):
        await client.delete_task(target)


@pytest.mark.asyncio
async def test_delete_task_does_not_delete_unrelated_task(monkeypatch):
    state = make_data([make_task("其他", "https://pan.quark.cn/s/other")])
    client = QASClient()

    async def get_data():
        return deepcopy(state)

    monkeypatch.setattr(client, "get_data", get_data)

    with pytest.raises(QASException, match="未找到任务"):
        await client.delete_task(
            make_task("目标", "https://pan.quark.cn/s/target")
        )

    assert [task.taskname for task in state.tasklist] == ["其他"]