import asyncio
import json
import weakref
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
# 这些状态码属于瞬态错误，值得重试
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
# 这些异常在重试后仍然失败才算真失败
RETRY_EXCEPTIONS = (
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.ReadError,
    httpx.RemoteProtocolError,
    httpx.ConnectTimeout,
)


# QAS 的 /update 是「整份 JSON 全量覆盖写」。
# 所有「读 /data → 改 → 写 /update」的操作必须串行，否则并发会互相覆盖配置。
# 锁按事件循环存放：asyncio.Lock 一旦绑定某个 loop 就不能跨 loop 复用。
_config_locks: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock]" = (
    weakref.WeakKeyDictionary()
)


def _config_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _config_locks.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _config_locks[loop] = lock
    return lock


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

    # ---------- 基础请求 ----------

    async def _request_with_retry(self, method: str, url: str, **kwargs) -> httpx.Response:
        """带重试的请求：网络异常 + 5xx/429 都重试。"""
        last_error = "未知错误"
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await self.client.request(method, url, **kwargs)
            except RETRY_EXCEPTIONS as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < MAX_RETRIES:
                    logger.warning(f"QAS request failed (attempt {attempt + 1}/{MAX_RETRIES + 1}): {url} {last_error}")
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                raise QASException(f"请求失败（重试{MAX_RETRIES}次）: {last_error}") from exc

            if response.status_code in RETRY_STATUS and attempt < MAX_RETRIES:
                delay = _retry_after_seconds(response.headers.get("Retry-After")) or 1.0 * (attempt + 1)
                logger.warning(
                    f"QAS HTTP {response.status_code} (attempt {attempt + 1}/{MAX_RETRIES + 1}): "
                    f"{url}, {delay:.1f}s 后重试"
                )
                await asyncio.sleep(delay)
                continue
            return response
        raise QASException(f"请求失败（重试{MAX_RETRIES}次）: {last_error}")

    def _check_response(self, response: httpx.Response) -> dict[str, Any]:
        if response.status_code >= 400:
            raise QASException(self._error_message(response.status_code, response.text))
        try:
            resp_json = response.json()
        except ValueError:
            raise QASException(f"QAS 返回的不是 JSON（HTTP {response.status_code}）") from None
        if not isinstance(resp_json, dict):
            raise QASException("QAS 返回了非预期的响应结构")
        if bool(resp_json.get("success")):
            return resp_json.get("data", resp_json)
        data = resp_json.get("data")
        error_msg = resp_json.get("message") or (data.get("error") if isinstance(data, dict) else "") or "未知错误"
        raise QASException(error_msg)

    @staticmethod
    def _error_message(status_code: int, body_text: str) -> str:
        """从错误响应里尽量抠出 QAS 的原始报错，别丢掉信息。"""
        message = ""
        try:
            payload = json.loads(body_text)
        except (ValueError, TypeError):
            payload = None
        if isinstance(payload, dict):
            data = payload.get("data")
            message = str(
                payload.get("message") or (data.get("error") if isinstance(data, dict) else "") or ""
            ).strip()
        elif body_text.strip():
            message = body_text.strip()[:200]
        if status_code == 401:
            return f"未登录或 QAS_TOKEN 无效{': ' + message if message else ''}"
        if status_code == 403:
            return f"QAS 拒绝访问{': ' + message if message else ''}"
        return message or f"HTTP {status_code}"

    # ---------- 业务接口 ----------

    async def add_task(self, task: TaskItem) -> TaskItem:
        async with _config_lock():
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

    @staticmethod
    def _same_task(left: Any, right: TaskItem) -> bool:
        return left.taskname == right.taskname and left.shareurl == right.shareurl

    async def delete_task(self, task: TaskItem) -> str:
        """按任务身份（名称 + 分享链接）删除，并回读校验确实删掉了一条。"""
        async with _config_lock():
            data = await self.get_data()
            matched = [idx for idx, item in enumerate(data.tasklist) if self._same_task(item, task)]
            if not matched:
                raise QASException(f"未找到任务: {task.taskname}")
            task_item = data.tasklist.pop(matched[-1])
            await self.update(data)

            remaining = await self.get_data()
            remaining_count = sum(self._same_task(item, task) for item in remaining.tasklist)
            if remaining_count != len(matched) - 1:
                raise QASException(f"任务删除未生效: {task.taskname}")
            return task_item.taskname

    async def list_tasks(self) -> list[TaskItem]:
        data = await self.get_data()
        return data.tasklist

    async def run_script(self, task: TaskItem | None = None):
        """执行转存，逐段 yield QAS 的输出。整体有超时上限。"""
        payload: dict[str, Any] = {}
        if task is not None:
            payload["tasklist"] = [model_dump(task)]
            # 带上 original_index 让 QAS 走「手动运行」分支，
            # 它会设置 IGNORE_EXECUTION_RULES=1，绕过执行周期与进度限制；
            # 否则 execution_mode=auto 且进度 100% 时任务会被静默跳过。
            payload["original_index"] = 1

        async with self.client.stream(
            "POST", "/run_script_now", json=payload, timeout=REQUEST_TIMEOUT
        ) as response:
            if response.status_code >= 400:
                raw = (await response.aread()).decode("utf-8", "replace")
                raise QASException(self._error_message(response.status_code, raw))

            loop = asyncio.get_running_loop()
            deadline = loop.time() + plugin_config.qas_run_timeout
            iterator = response.aiter_lines().__aiter__()
            task_res: list[str] = []
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise QASException(f"转存超时（超过 {plugin_config.qas_run_timeout} 秒未完成）")
                try:
                    chunk = await asyncio.wait_for(anext(iterator), remaining)
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    raise QASException(f"转存超时（超过 {plugin_config.qas_run_timeout} 秒未完成）") from None

                line = chunk.removeprefix("data:").strip()
                if not line:
                    continue
                if line.startswith("#") and task_res:
                    yield "\n".join(task_res)
                    task_res.clear()
                    continue
                if line.startswith("分享链接"):
                    continue
                task_res.append(line)
            if task_res:
                yield "\n".join(task_res)


def _retry_after_seconds(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0
