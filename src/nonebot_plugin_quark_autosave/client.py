import asyncio
import json
import weakref
from typing import Any, Sequence

import httpx
from nonebot import logger
from nonebot.compat import model_dump

from .model import TaskItem, DetailInfo, AutosaveData, ShareDetailPayload, FileItem
from .config import plugin_config
from .exception import QASException

# 请求超时配置
REQUEST_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)
MAX_RETRIES = 2
# 删除任务后回读复查的间隔（秒）。QASx 进程会把内存态整份写回磁盘，外部删除
# 可能被这次写回覆盖（任务“复活”），所以隔一会儿要再确认一次。测试里调成 0。
DELETE_VERIFY_DELAY = 1.5
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


def _sanitize_tasklist(payload: dict[str, Any]) -> None:
    """兼容旧调用点：写回配置前把 addition=null 修成 {}。

    实测（x1ao4/quark-auto-save-x 的 app/run.py:2477 `sync_task_plugins_config`）：
        for plugin_name in list(task["addition"].keys()):
    只要**配置里任何一个任务**的 `addition` 是 null，`/update` 就直接 500，
    整份配置写不进去——连带「删除任务」也会失败。原版 WebUI 保存的任务都是
    `{}`，所以平时看不出来；API 写入 null 才会踩到。
    """
    QASClient._sanitize(payload.get("tasklist") or [])


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
        """加任务：走「读文件 → append → 写回」，不用 /api/add_task。

        为什么不用 /api/add_task：它是 `config_data["tasklist"].append(...)` 后再
        `write_json`，用的是**服务进程内存态**。一旦配置文件被别的写入者（另一个
        bot、手动改文件、订阅流程）改过而服务没重载，内存就是旧的，append 写盘会
        把别人的改动整份覆盖掉——实测在正式环境吞过一个任务。
        改成先读文件再写回，服务端内存会被本次 payload 纠正成文件内容。
        """
        async with _config_lock():
            raw = await self.get_data_raw()
            tasklist = raw.get("tasklist")
            tasklist = list(tasklist) if isinstance(tasklist, list) else []
            payload = model_dump(task)
            # 不能发 addition=null，否则之后任何 /update 都会被 QASx 的
            # sync_task_plugins_config() 打 500（见 _sanitize 注释）
            payload["addition"] = payload.get("addition") or {}
            tasklist.append(payload)
            await self.update_tasklist(tasklist)
            return TaskItem(**payload)

    async def get_share_detail(self, task: TaskItem) -> DetailInfo:
        payload = ShareDetailPayload(shareurl=task.shareurl, task=task)
        response = await self._request_with_retry("POST", "/get_share_detail", json=model_dump(payload))
        return DetailInfo(**self._check_response(response))

    async def task_suggestions(self, query: str) -> list[dict[str, Any]]:
        """按片名搜索资源（QASx 聚合 CloudSaver/PanSou 的接口，同 WebUI）。"""
        response = await self._request_with_retry("GET", "/task_suggestions", params={"q": query})
        data = self._check_response(response)
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict) and item.get("shareurl")]

    async def list_savepath_files(
        self, savepath: str, max_depth: int = 4, max_dirs: int = 60
    ) -> list[dict[str, Any]]:
        """列出网盘某个保存目录里的**全部文件**（递归进子目录）。

        为什么要递归：QASx 转存嵌套结构的分享时会按分享里的目录层级落盘
        （`/自动/某剧/<分享里的子目录>/xx.mkv`），只看顶层会把「已经有哪几集」
        数成 0，订阅就会反复重复转存。

        目录还不存在（首次订阅）时 QASx 会报错，这里当作「一集都没有」。
        """
        collected: list[dict[str, Any]] = []
        queue: list[tuple[str, int]] = [(savepath, 0)]
        seen: set[str] = set()
        expanded = 0

        while queue:
            path, depth = queue.pop(0)
            try:
                response = await self._request_with_retry(
                    "GET", "/get_savepath_detail", params={"path": path}
                )
                data = self._check_response(response)
            except QASException as exc:
                logger.info(f"保存目录 {path} 读取失败（可能还不存在）: {exc}")
                continue
            if not isinstance(data, dict) or data.get("error"):
                if depth == 0:
                    logger.info(f"保存目录 {path} 不存在: {(data or {}).get('error')}")
                continue
            files = data.get("list")
            if not isinstance(files, list):
                continue
            for item in files:
                if not isinstance(item, dict):
                    continue
                if item.get("dir"):
                    name = str(item.get("file_name") or "")
                    child = f"{path.rstrip('/')}/{name}"
                    if depth < max_depth and expanded < max_dirs and child not in seen:
                        seen.add(child)
                        expanded += 1
                        queue.append((child, depth + 1))
                else:
                    collected.append(item)
        return collected

    async def get_share_files(
        self, shareurl: str, max_depth: int = 3, max_dirs: int = 40
    ) -> list[FileItem]:
        """取分享里的**全部文件**，自动递归展开子目录。

        实测：分享根目录经常只是一个文件夹（`dir=True`, `size=0`），
        `/get_share_detail` 只返回当前层。子目录靠 `shareurl#/list/share/<fid>`
        展开——这是 QASx 的 `extract_url` 支持的写法，已对真实实例验证过。
        """
        base = shareurl.split("#", 1)[0]
        collect: list[FileItem] = []
        queue: list[tuple[str, int]] = [(shareurl, 0)]
        seen_fids: set[str] = set()
        expanded = 0

        while queue:
            url, depth = queue.pop(0)
            detail = await self.get_share_detail(TaskItem.simple_from_title("probe", url))
            for item in detail.file_list:
                if item.dir:
                    if depth >= max_depth or expanded >= max_dirs or item.fid in seen_fids:
                        continue
                    seen_fids.add(item.fid)
                    expanded += 1
                    queue.append((f"{base}#/list/share/{item.fid}", depth + 1))
                else:
                    collect.append(item)
        return collect

    async def get_data(self) -> AutosaveData:
        response = await self._request_with_retry("GET", "/data")
        return AutosaveData(**self._check_response(response))

    async def get_data_raw(self) -> dict[str, Any]:
        """拿配置的**原始 dict**（不过 pydantic）。

        写回配置必须走这条：QASx 自己会往任务里塞 calendar_info、source、
        task_plugins 之类的字段，模型里没有的字段一旦被 model_dump 抹掉，
        追剧日历绑定、插件配置就跟着废。
        """
        response = await self._request_with_retry("GET", "/data")
        data = self._check_response(response)
        if not isinstance(data, dict):
            raise QASException("QAS /data 返回了非预期的响应结构")
        return data

    @staticmethod
    def _sanitize(tasklist: list[Any]) -> list[Any]:
        """把 addition=null 之类会让 /update 崩掉的字段修好（原地改）。"""
        for task in tasklist:
            if isinstance(task, dict) and not isinstance(task.get("addition"), dict):
                task["addition"] = {}
        return tasklist

    async def update(self, data: AutosaveData) -> str:
        payload = model_dump(data)
        self._sanitize(payload.get("tasklist") or [])
        response = await self._request_with_retry("POST", "/update", json=payload)
        return self._check_response(response).get("message", "ok")

    async def update_tasklist(
        self,
        tasklist: list[dict[str, Any]],
        *,
        removing: Sequence[Any] = (),
    ) -> str:
        """只写回 tasklist（原始 dict，其余字段不动）。

        QASx 的 /update 是「内存态 + 整份写盘」，遇到别的写入者并发改配置会互相覆盖。
        这里在写前记下服务端当前的完整配置，写后回读，发现「我没打算删的任务消失了」
        就记 error，别让它静默吞数据。

        removing：本次**故意**删掉的任务，不算「丢失」。
        """
        before = await self.get_data_raw()
        before_tasks = [(t.get("taskname"), t.get("shareurl"))
                        for t in (before.get("tasklist") or []) if isinstance(t, dict)]
        expected = {(t.get("taskname"), t.get("shareurl"))
                    for t in tasklist if isinstance(t, dict)}

        response = await self._request_with_retry(
            "POST", "/update", json={"tasklist": self._sanitize(tasklist)}
        )
        message = self._check_response(response).get("message", "ok")

        after = await self.get_data_raw()
        after_set = {(t.get("taskname"), t.get("shareurl"))
                     for t in (after.get("tasklist") or []) if isinstance(t, dict)}
        intended = {(getattr(t, "taskname", None) or (t.get("taskname") if isinstance(t, dict) else None),
                     getattr(t, "shareurl", None) or (t.get("shareurl") if isinstance(t, dict) else None))
                    for t in removing}
        lost = [
            pair for pair in before_tasks
            if pair not in expected and pair not in after_set and pair not in intended
        ]
        if lost:
            logger.error(f"QASx 配置写回时丢失了其他任务: {lost}（可能有并发写入者）")
        return message

    @staticmethod
    def _same_task(left: Any, right: TaskItem | dict[str, Any]) -> bool:
        def _get(obj, key):
            return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)

        return (
            _get(left, "taskname") == _get(right, "taskname")
            and _get(left, "shareurl") == _get(right, "shareurl")
        )

    async def delete_task(self, task: TaskItem, *, verify_rounds: int = 15) -> str:
        """按任务身份（名称 + 分享链接）删除，并回读校验确实没了。

        走原始 dict 写回：既避免丢 QASx 维护的字段，也避免 addition=null 触发
        /update 500（见 _sanitize）。

        为什么要反复复查：QASx 主进程内存里也有一份 config_data，`/update` 之后它会
        起后台线程（元数据匹配、日历初始化）再整份写盘。这些线程手里还攥着**写盘前**
        的任务列表，于是刚删掉的任务会被写回去——实测在正式环境一次删不掉，
        隔 1.5s/3s 回读都还在。这里改成「删 → 等 → 回读 → 还在就再删」，
        verify_rounds 次仍删不掉才报错（总窗口约 3 分钟）。
        """
        async with _config_lock():
            raw = await self.get_data_raw()
            tasklist = raw.get("tasklist") or []
            if not isinstance(tasklist, list):
                raise QASException("QAS 配置里的 tasklist 格式异常")
            matched = [idx for idx, item in enumerate(tasklist) if self._same_task(item, task)]
            if not matched:
                raise QASException(f"未找到任务: {task.taskname}")

            target_idx = matched[-1]
            removed_name = str(tasklist[target_idx].get("taskname") or task.taskname)
            remaining = [item for idx, item in enumerate(tasklist) if idx != target_idx]
            await self.update_tasklist(remaining, removing=[task])
            # 同名同链接的重复任务可能不止一条：每次只删一条，剩下的保留
            # （调用方说「删这个任务」就是删一条，不是把重复的全清了）
            expected_left = len(matched) - 1

            for round_no in range(1, verify_rounds + 1):
                # 前几轮等短一点（后台线程通常几秒内就写完了），后面拉长
                await asyncio.sleep(min(DELETE_VERIFY_DELAY * round_no, 20))
                after = (await self.get_data_raw()).get("tasklist") or []
                left = [item for item in after if self._same_task(item, task)]
                if len(left) <= expected_left:
                    return removed_name
                if round_no == verify_rounds:
                    raise QASException(
                        f"任务删除未生效（已重试 {verify_rounds} 次，"
                        f"可能被 QASx 进程写回覆盖）: {task.taskname}"
                    )
                logger.warning(
                    f"任务 {task.taskname} 删除后被 QASx 写回复活，第 {round_no} 次重删"
                )
                trimmed, kept = list(after), 0
                for idx in range(len(trimmed) - 1, -1, -1):
                    if kept < expected_left and self._same_task(trimmed[idx], task):
                        kept += 1
                        continue
                    if self._same_task(trimmed[idx], task):
                        trimmed.pop(idx)
                await self.update_tasklist(trimmed, removing=[task])
            return removed_name

    async def delete_file(self, fid: str, *, delete_records: bool = False, save_path: str = "") -> bool:
        """删网盘里的一个文件/目录（QASx `/delete_file`，按 fid）。

        bot 正常流程用不到；只有自检/清理临时转存内容时才用。

        注意：这个接口不像其它接口那样包 `{"success":true,"data":...}`，它直接吐
        夸克原始响应 `{"status":200,"code":0,"data":{"task_id":...,"finish":false}}`，
        而且是**异步任务**（finish 可能还是 false）。所以按 `code==0` 判成功，
        调用方想确认真删干净得自己回读目录。
        """
        payload: dict[str, Any] = {"fid": fid}
        if delete_records and save_path:
            payload["delete_records"] = True
            payload["save_path"] = save_path
        response = await self._request_with_retry("POST", "/delete_file", json=payload)
        try:
            data = response.json()
        except Exception:
            response.raise_for_status()
            return False
        if isinstance(data, dict) and data.get("code") == 0:
            return True
        logger.warning(f"QASx 删除文件 {fid} 失败: {str(data)[:200]}")
        return False

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
