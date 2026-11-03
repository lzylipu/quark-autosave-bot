"""订阅用到的两个新接口：搜索结果解析、保存目录扫描（含目录不存在）。"""

import httpx
import pytest

from nonebot_plugin_quark_autosave.client import QASClient


def make_client(handler) -> QASClient:
    client = QASClient()
    client.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://qas.test",
        params={"token": "test-token"},
    )
    return client


@pytest.mark.asyncio
async def test_task_suggestions_keeps_only_urls():
    async def handler(request):
        assert request.url.path == "/task_suggestions"
        assert request.url.params["q"] == "甄嬛传"
        return httpx.Response(
            200,
            json={
                "success": True,
                "source": "PanSou",
                "data": [
                    {"taskname": "甄嬛传 4K", "shareurl": "https://pan.quark.cn/s/aaa"},
                    {"taskname": "没有链接的条目"},
                    "垃圾数据",
                ],
            },
        )

    client = make_client(handler)
    results = await client.task_suggestions("甄嬛传")
    assert [r["shareurl"] for r in results] == ["https://pan.quark.cn/s/aaa"]
    await client.client.aclose()


@pytest.mark.asyncio
async def test_task_suggestions_empty_list():
    async def handler(request):
        return httpx.Response(200, json={"success": True, "data": []})

    client = make_client(handler)
    assert await client.task_suggestions("不存在") == []
    await client.client.aclose()


@pytest.mark.asyncio
async def test_list_savepath_files_returns_entries():
    seen_paths = []

    async def handler(request):
        assert request.url.path == "/get_savepath_detail"
        path = request.url.params["path"]
        seen_paths.append(path)
        if path == "/自动/甄嬛传":
            items = [
                {"file_name": "S01E01.mkv", "dir": False, "size": 2000},
                {"file_name": "海报.jpg", "dir": False, "size": 100},
                {"file_name": "花絮", "dir": True},
            ]
        elif path == "/自动/甄嬛传/花絮":
            items = [{"file_name": "S01E01花絮.mkv", "dir": False, "size": 300}]
        else:
            return httpx.Response(200, json={"success": False, "data": {"error": "获取fid失败"}})
        return httpx.Response(
            200,
            json={"success": True, "data": {"list": items, "paths": []}},
        )

    client = make_client(handler)
    files = await client.list_savepath_files("/自动/甄嬛传")
    # 递归进子目录，只返回文件（目录不算「已有的一集」）
    assert [f["file_name"] for f in files] == ["S01E01.mkv", "海报.jpg", "S01E01花絮.mkv"]
    assert seen_paths == ["/自动/甄嬛传", "/自动/甄嬛传/花絮"]
    await client.client.aclose()


@pytest.mark.asyncio
async def test_list_savepath_files_missing_dir_is_empty():
    """首次订阅时保存目录还不存在——必须当成「一集都没有」，不能抛异常。"""

    async def handler(request):
        return httpx.Response(200, json={"success": False, "data": {"error": "获取fid失败"}})

    client = make_client(handler)
    assert await client.list_savepath_files("/自动/新剧") == []
    await client.client.aclose()
