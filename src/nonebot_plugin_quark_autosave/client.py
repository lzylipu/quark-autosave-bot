from typing import Any

import httpx
from nonebot import logger
from nonebot.compat import model_dump

from .model import TaskItem, DetailInfo, AutosaveData, ShareDetailPayload
from .config import plugin_config
from .exception import QASException

# 请求超时配置
REQUEST_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)
MAX_RETRIES = 2


class QASClient:
    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            base_url=plugin_config.qas_endpoint,
            params={"token": plugin_config.qas_token},
            timeout=REQUEST_TIMEOUT,
        )
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.client.aclose()

    async def _request_with_retry(self, method: str, url: str, **kwargs) -> httpx.Response:
        """带重试的请求，处理瞬态错误"""
        last_error = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await self.client.request(method, url, **kwargs)
                return response
            except httpx.ConnectError as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    logger.warning(f"Connect failed (attempt {attempt+1}/{MAX_RETRIES+1}): {url}")
                    import asyncio
                    await asyncio.sleep(1.0 * (attempt + 1))
            except httpx.ReadTimeout as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    logger.warning(f"Read timeout (attempt {attempt+1}/{MAX_RETRIES+1}): {url}")
        raise QASException(f"请求失败（重试{MAX_RETRIES}次）: {last_error}")

    async def add_task(self, task: TaskItem) -> TaskItem:
        response = await self._request_with_retry("POST", "/api/add_task", json=model_dump(task))
        return TaskItem(**self._check_response(response))

    async def get_share_detail(self, task: TaskItem) -> DetailInfo:
        payload = ShareDetailPayload(shareurl=task.shareurl, task=task)
        response = await self._request_with_retry("POST", "/get_share_detail", json=model_dump(payload))
        return DetailInfo(**self._check_response(response))

    async def get_data(self) -> AutosaveData:
        response = await self._request_with_retry("GET", "/data")
        return AutosaveData(**self._check_response(response))

    async def update(self, data: AutosaveData) -> str:
        response = await self._request_with_retry("POST", "/update", json=model_dump(data))
        return self._check_response(response).get("message", "ok")

    async def delete_task(self, task_idx: int) -> str:
        data = await self.get_data()
        if not (0 < task_idx <= len(data.tasklist)):
            raise QASException(f"任务索引 {task_idx} 无效")
        task_item = data.tasklist.pop(task_idx - 1)
        await self.update(data)
        return task_item.taskname

    async def list_tasks(self) -> list[TaskItem]:
        data = await self.get_data()
        return data.tasklist

    async def run_script(self, task_idx: int | None = None):
        payload = {}
        if task_idx is not None:
            data = await self.get_data()
            idx = (task_idx - 1) % len(data.tasklist)
            task_dict = model_dump(data.tasklist[idx])
            del task_dict["runweek"]
            payload["tasklist"] = [task_dict]

        async with self.client.stream("POST", "/run_script_now", json=payload, timeout=REQUEST_TIMEOUT) as response:
            response.raise_for_status()
            task_res: list[str] = []
            async for chunk in response.aiter_lines():
                if chunk := chunk.removeprefix("data:").replace("=", "").strip():
                    if chunk.startswith("#") and task_res:
                        yield "\n".join(task_res)
                        task_res.clear()
                        continue
                    if chunk.startswith("分享链接"):
                        continue
                    task_res.append(chunk)
            if task_res:
                yield "\n".join(task_res)

    def _check_response(self, response: httpx.Response) -> dict[str, Any]:
        # 5xx: 服务端错误
        if response.status_code >= 500:
            raise QASException(f"服务端错误 HTTP {response.status_code}")
        # 4xx: 客户端错误
        if response.status_code >= 400:
            try:
                body = response.json()
                raise QASException(body.get("message", f"HTTP {response.status_code}"))
            except Exception:
                raise QASException(f"HTTP {response.status_code}")
        # 正常响应
        resp_json = response.json()
        if bool(resp_json.get("success")):
            return resp_json.get("data", resp_json)
        # QAS业务层错误
        error_msg = resp_json.get("message") or resp_json.get("data", {}).get("error", "未知错误")
        raise QASException(error_msg)
