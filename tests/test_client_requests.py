"""QAS 请求层测试：错误信息保留、重试、执行参数、整体超时。"""

import json

import httpx
import pytest

import nonebot_plugin_quark_autosave.client as client_module
from nonebot_plugin_quark_autosave.client import QASClient
from nonebot_plugin_quark_autosave.config import plugin_config
from nonebot_plugin_quark_autosave.exception import QASException
from nonebot_plugin_quark_autosave.model import TaskItem

EMPTY_DATA = {
    "cookie": [],
    "api_token": "",
    "crontab": "",
    "tasklist": [],
    "magic_regex": {},
    "source": {},
    "push_config": {},
    "plugins": {},
    "task_plugins_config_default": {},
}


def make_client(handler) -> QASClient:
    client = QASClient()
    client.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://qas.test",
        params={"token": "test-token"},
    )
    return client


@pytest.mark.asyncio
async def test_http_error_keeps_qas_message(monkeypatch):
    async def handler(request):
        return httpx.Response(401, json={"success": False, "message": "token 已失效"})

    client = make_client(handler)
    with pytest.raises(QASException, match="token 已失效"):
        await client.get_data()
    await client.client.aclose()


@pytest.mark.asyncio
async def test_business_error_keeps_qas_message():
    async def handler(request):
        return httpx.Response(200, json={"success": False, "message": "保存路径不存在"})

    client = make_client(handler)
    with pytest.raises(QASException, match="保存路径不存在"):
        await client.get_data()
    await client.client.aclose()


@pytest.mark.asyncio
async def test_server_error_is_retried(monkeypatch):
    calls = {"count": 0}

    async def handler(request):
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, json={"success": True, "data": EMPTY_DATA})

    async def fast_sleep(_seconds):
        return None

    monkeypatch.setattr(client_module.asyncio, "sleep", fast_sleep)
    client = make_client(handler)
    data = await client.get_data()
    assert data.tasklist == []
    assert calls["count"] == 2
    await client.client.aclose()


@pytest.mark.asyncio
async def test_rate_limit_gives_up_after_retries(monkeypatch):
    calls = {"count": 0}

    async def handler(request):
        calls["count"] += 1
        return httpx.Response(429, headers={"Retry-After": "0"}, text="slow down")

    async def fast_sleep(_seconds):
        return None

    monkeypatch.setattr(client_module.asyncio, "sleep", fast_sleep)
    client = make_client(handler)
    with pytest.raises(QASException):
        await client.get_data()
    assert calls["count"] == client_module.MAX_RETRIES + 1
    await client.client.aclose()


@pytest.mark.asyncio
async def test_run_script_sends_task_and_keeps_equals():
    seen = {}

    async def handler(request):
        seen["body"] = json.loads(request.content)
        body = "data: ✅《剧集》新增文件:\n\ndata: /自动/剧集\n\ndata: ├── a=x.mkv\n\ndata: [DONE]\n\n"
        return httpx.Response(200, text=body)

    client = make_client(handler)
    task = TaskItem.simple_from_title("剧集", "https://pan.quark.cn/s/abc")
    chunks = [chunk async for chunk in client.run_script(task)]

    payload = seen["body"]
    assert payload["tasklist"][0]["taskname"] == "剧集"
    assert payload["original_index"] == 1
    assert payload["tasklist"][0]["runweek"] == [1, 2, 3, 4, 5, 6, 7]
    joined = "\n".join(chunks)
    assert "a=x.mkv" in joined
    assert "data:" not in joined
    await client.client.aclose()


@pytest.mark.asyncio
async def test_run_script_times_out(monkeypatch):
    async def handler(request):
        return httpx.Response(200, text="data: 开始\n\n")

    monkeypatch.setattr(plugin_config, "qas_run_timeout", 0)
    client = make_client(handler)
    with pytest.raises(QASException, match="超时"):
        [chunk async for chunk in client.run_script(TaskItem.simple_from_title("剧集", "https://pan.quark.cn/s/abc"))]
    await client.client.aclose()
