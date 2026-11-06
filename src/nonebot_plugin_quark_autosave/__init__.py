import asyncio
import re
from time import monotonic

from nonebot import get_driver, logger, on_message
from nonebot.adapters import Bot, Event
from nonebot.exception import FinishedException
from nonebot.permission import Permission
from nonebot.rule import Rule
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

from .client import QASClient
from .config import Config, plugin_config
from .exception import QASException
from .model import DetailInfo, TaskItem, sanitize_title
from .perms import allow_user
from .result import (
    classify_error,
    extract_passcode,
    extract_share_url,
    parse_run_output,
    share_key,
    with_passcode,
)
from .subscribe import (
    Candidate,
    SubscriptionStore,
    assess_share,
    episode_keys,
    episode_limited_rules,
    fmt_episode_keys,
    parse_season,
    pick_best,
    persistence_warning,
    rename_rules,
    season_or_bare_rules,
    seconds_until,
    split_season,
    video_names_from_dir,
)

__plugin_meta__ = PluginMetadata(
    name="夸克自动转存",
    description="发夸克链接直接转存，智能检测链接有效性",
    usage=(
        "直接发夸克链接即可转存，如 https://pan.quark.cn/s/xxxxx?pwd=1234\n"
        "AD 片名 订阅追剧（AD 某剧 S02 指定第二季）\n"
        "列表 看订阅　del 片名 取消　执行 立刻跑一轮（执行 片名 只跑一部）"
    ),
    type="application",
    homepage="https://github.com/lzylipu/quark-autosave-bot",
    config=Config,
    supported_adapters=inherit_supported_adapters(),
    extra={"author": "lzylipu"},
)


# 探分享详情时的并发数：QAS 单机 + 夸克接口，压太高容易被限流
_PROBE_CONCURRENCY = 4


def _is_private_chat(event: Event) -> bool:
    """判断是否私聊（Telegram 适配器下 original_message.chat.type == private）。"""
    chat = getattr(getattr(event, "original_message", None), "chat", None)
    return getattr(chat, "type", None) == "private"


async def _allowed(bot: Bot, event: Event) -> bool:
    superusers = getattr(get_driver().config, "superusers", set())
    return allow_user(str(event.get_user_id()), superusers, _is_private_chat(event))


async def _reject_hint(bot: Bot, event: Event) -> bool:
    """没权限但发了夸克链接：提示一下，免得以为 bot 挂了。"""
    return bool(extract_share_url(get_text(event))) and not await _allowed(bot, event)


qas_handler = on_message(permission=Permission(_allowed), block=False, priority=10)
qas_reject = on_message(rule=Rule(_reject_hint), block=False, priority=11)

# 分享 ID -> (完成时间, 任务名, 保存路径)，用于短时间内的重复链接去重
_recent: dict[str, tuple[float, str, str]] = {}
# 正在处理中的分享 ID
_inflight: dict[str, float] = {}


def get_text(event: Event) -> str:
    try:
        return str(event.get_plaintext()).strip()
    except Exception:
        return str(getattr(event, "message", "")).strip()


async def send(message: str) -> None:
    await qas_handler.send(message, at_sender=True)


async def _ask_passcode() -> str | None:
    """在聊天里追问提取码；依赖不可用或超时则返回 None。"""
    if not plugin_config.ask_passcode:
        return None
    try:
        from nonebot_plugin_waiter import prompt

        reply = await prompt("🔑 这个分享需要提取码，请直接发送 4 位提取码（60 秒内有效）", timeout=60)
    except Exception as exc:  # waiter 不可用时不要拖垮整个流程
        logger.warning(f"passcode prompt unavailable: {exc}")
        return None
    code = get_text(reply)
    return code if re.fullmatch(r"[0-9a-zA-Z]{4}", code) else None


async def _get_detail(client: QASClient, shareurl: str) -> tuple[str, DetailInfo]:
    """获取分享详情；遇到「需要提取码」时追问一次并带上 pwd 重试。"""
    task = TaskItem.simple_from_title("temp", shareurl)
    try:
        return shareurl, await client.get_share_detail(task)
    except QASException as exc:
        message = str(exc)
        if classify_error(message) != "passcode" or extract_passcode(shareurl):
            raise
        logger.info(f"QAS requests passcode for {shareurl}")

    passcode = await _ask_passcode()
    if not passcode:
        raise QASException("该分享需要提取码，请带上提取码重发，如 https://pan.quark.cn/s/xxxx?pwd=1234")
    resolved_url = with_passcode(shareurl, passcode)
    return resolved_url, await client.get_share_detail(
        TaskItem.simple_from_title("temp", resolved_url)
    )


async def _cleanup(client: QASClient, task: TaskItem) -> bool:
    try:
        await client.delete_task(task)
    except Exception as exc:
        logger.error(f"QAS cleanup failed for {task.taskname}: {exc}")
        return False
    return True


def _prune_recent() -> None:
    ttl = max(plugin_config.dedupe_seconds, 60) * 6
    now = monotonic()
    for key, value in list(_recent.items()):
        if now - value[0] > ttl:
            _recent.pop(key, None)


async def _handle_share(shareurl: str, key: str) -> None:
    await send("🔍 检测链接...")

    async with QASClient() as client:
        # ===== 1. 检测链接有效性 =====
        try:
            shareurl, detail = await _get_detail(client, shareurl)
        except QASException as exc:
            err_type = classify_error(str(exc))
            if err_type == "passcode":
                await send(f"🔑 {exc}")
            elif err_type == "expired":
                await send("🔴 链接已失效")
            elif err_type == "auth":
                await send("🔒 夸克登录态失效，请到 QAS WebUI 重新登录后再发一次")
            else:
                await send(f"❌ 检测失败: {exc}")
            return

        # ===== 2. 链接有效，构建任务 =====
        root_title = sanitize_title(detail.share.title)
        file_count = getattr(detail.share, "file_num", 0)
        task = TaskItem.simple_from_title(root_title, shareurl)
        task.addition = {
            "aria2": {
                "auto_download": True,
                "download_subdir": True,
                "pause": False,
                "save_path": "",
            }
        }

        file_info = f" ({file_count}个文件)" if file_count else ""
        logger.info(f"QAS: {task.taskname}{file_info} | {shareurl}")
        await send(f"📥 {task.taskname}{file_info}")

        # ===== 3. 执行转存 =====
        task_added = False
        script_output: list[str] = []
        try:
            await client.add_task(task)
            task_added = True
            async for res in client.run_script(task):
                script_output.append(res)
        except QASException as exc:
            if task_added:
                await _cleanup(client, task)
            err_type = classify_error(str(exc))
            if err_type == "auth":
                await send("🔒 夸克登录态失效，请到 QAS WebUI 重新登录后再发一次")
            elif err_type == "expired":
                await send(f"🔴 链接已失效: {exc}")
            else:
                await send(f"❌ 转存失败: {exc}")
            return

        # ===== 4. 清理任务（失败也要让用户知道）=====
        cleaned = await _cleanup(client, task)

        # ===== 5. 汇报结果 =====
        result = parse_run_output(script_output)
        await send(result.render(fallback_savepath=task.savepath))
        if not cleaned:
            await send("⚠️ 转存已执行，但任务未从 QAS 删除，请到 QAS WebUI 手动清理")

        if result.status in ("success", "partial"):
            _recent[key] = (monotonic(), task.taskname, result.savepath or task.savepath)


@qas_handler.handle()
async def handle_message(event: Event):
    shareurl = extract_share_url(get_text(event))
    if not shareurl:
        return

    key = share_key(shareurl)
    now = monotonic()

    if key in _inflight:
        await send("⏳ 这条链接正在处理中，稍等一下")
        return

    hit = _recent.get(key)
    if hit and now - hit[0] < plugin_config.dedupe_seconds:
        await send(f"♻️ 这条链接 {int(now - hit[0])} 秒前刚转过，跳过\n📁 {hit[2]}")
        return

    _inflight[key] = now
    try:
        await _handle_share(shareurl, key)
    except FinishedException:
        raise
    except Exception as exc:
        logger.exception(f"QAS unexpected error: {exc}")
        await send(f"💥 运行错误: {exc}")
    finally:
        _inflight.pop(key, None)
        _prune_recent()


@qas_reject.handle()
async def handle_reject(event: Event):
    user_id = str(event.get_user_id())
    logger.info(f"QAS rejected message from {user_id}")
    await qas_reject.send(
        f"🔒 你没有使用权限。你的 TG 用户 ID 是 {user_id}，"
        "把它填到 SUPERUSERS 里就能用了（填好后重启 bot）。"
    )



# ======================================================================
# 追剧订阅：AD / 列表 / del / 执行 + 每天定时搜索补缺转存
# ======================================================================

store = SubscriptionStore(plugin_config.sub_store_file)

# 中文命令是主入口；DL / LIST 保留成别名，老用户和旧文档里的写法照样能用
_SUB_ALIASES = {
    "AD": "AD",
    "列表": "LIST",
    "LIST": "LIST",
    "DEL": "DL",
    "DL": "DL",
    "执行": "RUN",
    "RUN": "RUN",
}
_SUB_CMD_RE = re.compile(
    r"^\s*(AD|列表|LIST|DEL|DL|执行|RUN)(?=\s|$)\s*(.*)$", re.IGNORECASE | re.DOTALL
)


async def _is_sub_command(bot: Bot, event: Event) -> bool:
    return bool(_SUB_CMD_RE.match(get_text(event)))


sub_handler = on_message(
    rule=Rule(_is_sub_command), permission=Permission(_allowed), priority=9, block=True
)


def _chat_id_of(event: Event) -> str | None:
    """取真正能用来发消息的 chat id。

    注意不能用 get_session_id()：Telegram 适配器返回的是 "private_<id>" 这种
    会话标识，直接当 chat_id 发消息会 400。
    """
    chat = getattr(event, "chat", None)
    chat_id = getattr(chat, "id", None)
    if chat_id is None:
        chat_id = getattr(getattr(event, "original_message", None), "chat", None)
        chat_id = getattr(chat_id, "id", None)
    return str(chat_id) if chat_id is not None else None


@sub_handler.handle()
async def handle_sub_command(event: Event):
    match = _SUB_CMD_RE.match(get_text(event))
    if match is None:  # rule 已过滤，这里只是给类型检查器一个交代
        return
    cmd = _SUB_ALIASES[match.group(1).upper()]
    arg = match.group(2).strip()

    if cmd == "RUN":
        # 手动唤起一轮定时任务：不等到点，立刻按当前订阅跑一遍
        names = [arg.strip()] if arg.strip() else store.list_all()
        if not names:
            await sub_handler.finish("📭 订阅列表是空的，用「AD 片名」订阅")
        missing = [n for n in names if n not in store.list_all()]
        if missing:
            await sub_handler.finish(
                f"❓ 没有这个订阅: {'、'.join(missing)}\n用「列表」看看有哪些"
            )
        # 后台跑：一轮要搜十几条分享，几十秒到几分钟，命令 handler 不能干等
        asyncio.get_running_loop().create_task(_run_all_subscriptions(names))
        await sub_handler.finish(
            f"⏳ 开始执行 {len(names)} 个订阅（{'、'.join(names)}），跑完会发结果"
        )

    if cmd == "AD":
        # 记住会话，定时任务的报告发回这里（写不进去不影响下面存订阅，但要提示）
        chat_saved = True
        if chat_id := _chat_id_of(event):
            chat_saved = store.set_chat_id(chat_id)
        _, msg = store.add(arg)
        if not chat_saved:
            msg += "\n⚠️ 会话绑定没存下来，定时报告可能发不出去（检查 /app/data 是否可写）"
        await sub_handler.finish(msg)

    if cmd == "DL":
        _, msg = store.remove(arg)
        await sub_handler.finish(msg)

    names = store.list_all()
    if not names:
        await sub_handler.finish("📭 订阅列表是空的，用「AD 片名」订阅")
    data = store.load()
    lines = [
        f"📋 订阅列表（每天 {plugin_config.sub_check_time} 自动执行）:",
        "　 发「执行」立刻跑一轮，「del 片名」取消订阅",
    ]
    for i, name in enumerate(names, 1):
        last = data.get(name, {}).get("last_result", "")
        lines.append(f"{i}. {name}" + (f"\n   └ 上次: {last}" if last else "\n   └ 还没跑过"))
    # 顺带把存储位置和「会不会因升级丢」说清楚，省得再踩一次
    if persistence_warning(store.path):
        lines.append(f"\n⚠️ 存在 {store.path}，但这个目录没挂卷：升级/重建容器后会丢")
    else:
        lines.append(f"\n💾 存在 {store.path}（已挂卷，升级不丢）")
    await sub_handler.finish("\n".join(lines))


def _only_season(cand: Candidate, season: int, enabled: bool) -> Candidate:
    """订阅写死了季时，把候选的「待补集」砍到只剩这一季。

    assess_share 按文件名里的季建 (季, 集)；「黑镜 S05」搜到第七季的分享时，
    S07E01~E06 会全被算成待补 → 结果下错季（真机复现）。这里只保留目标季。
    """
    if enabled:
        cand.new_episodes = {key for key in cand.new_episodes if key[0] == season}
        cand.missing = {key for key in cand.missing if key[0] == season}
    return cand


async def _clear_stale_records(
    client: QASClient, taskname: str, savepath: str, local_keys: set, season: int
) -> int:
    """清掉「记录说有、目录里却没有」的转存记录，返回清掉的条数。

    QASx 按 `file_id + 任务名` 去重：云盘里的文件被删了、记录还留着，同一个任务名
    就永远转不进来（真机：走马上任 11 集全在记录里，`/自动/走马上任` 却是空的，
    每次跑都回「没有新的文件需要转存」）。这里只删同时满足三条的记录：
    ① 任务名就是这次要用的 ② 保存目录就是这次的 ③ 这一集本地确实没有了。
    别的任务、别的目录、别的季的记录一律不碰。
    """
    try:
        records = await client.history_records(taskname)
    except Exception as exc:  # noqa: BLE001 — 记录读不到不该挡住转存
        logger.warning(f"读转存记录失败（跳过清理）: {exc}")
        return 0

    want = savepath.strip("/")
    stale: list[int] = []
    for record in records:
        if str(record.get("save_path") or "").strip("/") != want:
            continue
        name = record.get("renamed_to") or record.get("original_name") or ""
        keys = episode_keys([str(name)], season)
        if not keys or not any(key[0] == season for key in keys):
            continue  # 别的季的记录不归这次管
        if keys & local_keys:
            continue  # 这一集还在目录里，记录是有效的
        rid = record.get("id")
        if rid is not None:
            stale.append(rid)

    if not stale:
        return 0
    cleared = await client.delete_history_records(stale)
    if cleared:
        logger.info(
            f"清掉 {cleared} 条过期转存记录（{taskname} / {savepath}）："
            f"这些集本地已经没有了，不清就永远转不进来"
        )
    return cleared


async def _run_one_subscription(client: QASClient, name: str) -> str:
    """跑一个订阅：扫本地 → 搜索 → 找能把缺集补全的那条分享 → 转存 → 删任务。"""
    title, season = split_season(name)
    # 一律只下这一季：订阅名写死了季（「黑镜 S05」）就下那一季，没写就当第一季。
    # 原来「没写季就不锁季」，于是美剧 S01/S02/S03 的集混在一起算缺集，
    # 最后挑中一季第 10 集就下了（实测两次都下错季）。要第二季写「S02」。
    only_season = True
    savepath = f"/{plugin_config.simple_save_root}/{sanitize_title(title)}"

    # 1. 本地已有哪几集
    local_files = await client.list_savepath_files(savepath)
    local_keys = episode_keys(video_names_from_dir(local_files), season)
    local_desc = f"本地已有 {fmt_episode_keys(local_keys)}" if local_keys else "本地还没有剧集"

    # 1.5 记录的集本地却没有：这条记录挡住重下，先清掉（只清同名同目录同季的）
    cleared = await _clear_stale_records(
        client, sanitize_title(title), savepath, local_keys, season
    )

    # 2. 搜资源
    try:
        results = await client.task_suggestions(title)
    except QASException as exc:
        return f"❌ 搜索失败: {exc}\n　　{local_desc}"
    if not results:
        return f"❌ 没搜到「{title}」的资源\n　　{local_desc}"

    # 3. 逐个探分享：大小合格 + 能补几集
    # sub_max_candidates=0（默认）表示搜到多少看多少：盘搜按热度排序，合格资源常在
    # 几十条之后（走马上任第 25 条才有 1.5~8G 的），原来只看前 10 条会漏掉全部。
    # 分批探：一批 _PROBE_CONCURRENCY 个，凑够合格的就停，剩下的不再探。
    # 合格 = 片名对得上 + 每集大小在区间内 + 确实有本地缺的集。集数不够/大小不对
    # 都算不合格，继续往后看；同一批里挑集数最多的（已经花掉的请求不能浪费）。
    limit = plugin_config.sub_max_candidates
    max_ok = plugin_config.sub_max_ok_candidates
    pending = results if limit <= 0 else results[:limit]
    checked = failed = empty = off_season = 0
    candidates: list[Candidate] = []

    async def _probe(idx: int, item: dict) -> tuple[int, list[Candidate], str]:
        """探一个分享。返回 (序号, 候选列表, 失败原因)；失败原因空表示成功。

        候选是**按目录层**给的：嵌套分享里不同版本各占一个子目录，根目录会把
        它们并成一份（同一集两份文件 → 落盘多一个 `.1` 副本），只有某一层是干净的。
        所以这里把每层都当候选交出去，谁最合适由 pick_best 判。
        """
        shareurl = str(item.get("shareurl", "")).strip()
        if not shareurl:
            return idx, [], ""
        try:
            nodes = await client.get_share_nodes(shareurl)
        except QASException as exc:
            # 链接失效是常态，换下一个
            logger.info(f"订阅[{name}] 跳过分享 {shareurl}: {exc}")
            return idx, [], str(exc)

        cands: list[Candidate] = []
        off_season = False
        for node in nodes:
            videos = [f for f in node.videos if not getattr(f, "dir", False)]
            if not videos:
                continue
            # 这一层里带季标记、但没有一集属于目标季 → 跳过这一层。
            # 不能选中它：pattern 只认目标季，选中也一集都转不了，白建一轮任务。
            marks = {parse_season(f.file_name) for f in videos}
            marks.discard(None)
            if marks and season not in marks:
                off_season = True
                continue
            cand = _only_season(
                assess_share(
                    node.url,
                    videos,
                    local_keys,
                    plugin_config.sub_min_size_gb,
                    plugin_config.sub_max_size_gb,
                    season,
                    title,
                    str(item.get("taskname") or ""),
                    path=node.path,
                    depth=node.depth,
                ),
                season,
                only_season,
            )
            cands.append(cand)
        if not cands:
            if off_season:
                logger.info(f"订阅[{name}] 跳过分享 {shareurl}: 是别的季")
                return idx, [], "季:off_season"
            return idx, [], ""
        return idx, cands, ""

    scan_pos = 0

    async def _scan_batches() -> None:
        """往后探分享，探到合格的就停；可续扫（这条试过不落文件，接着往后看）。"""
        nonlocal scan_pos, checked, failed, empty, off_season
        while scan_pos < len(pending):
            batch = pending[scan_pos : scan_pos + _PROBE_CONCURRENCY]
            start = scan_pos
            scan_pos += len(batch)
            # 一条一条串行的话，热门剧 170 多条要跑好几分钟；这里只并发一批，
            # 探到合格的就停，不把剩下的全探完（用户明确要求：扫到就停，别复盘全表）
            probed = await asyncio.gather(
                *(_probe(start + i, item) for i, item in enumerate(batch))
            )
            for _idx, cands, err in sorted(probed, key=lambda x: x[0]):
                if err:
                    if err.startswith("季:"):
                        off_season += 1
                    else:
                        failed += 1
                    continue
                if not cands:
                    continue
                checked += 1
                if not any(c.video_files for c in cands):
                    empty += 1
                    continue
                candidates.extend(cands)
            # 合格 = 片名对得上 + 大小在区间 + 有可补的集 + 这几集它全都给了
            #        + 同一集只有一份文件（否则整份分享会把已有集再转一遍）。
            # 少一集就算不合格：本地 E01~E10、分享只有 E12 时，选中它 E11 就永久跳过
            # （用户实测的原话：「那 11 就有，没有 11 你这样再去下，他就错过了」）。
            usable = [
                c
                for c in candidates
                if c.title_hit
                and c.size_ok
                and c.new_episodes
                and not c.missing
                and not c.dup_episodes
            ]
            if max_ok > 0 and len(usable) >= max_ok:
                logger.info(
                    f"订阅[{name}] 找到 {len(usable)} 个合格分享"
                    f"（片名对得上 + 大小在区间 + 缺的集它全有），"
                    f"共探 {checked} 个，停止继续扫描"
                )
                return

    def _pool() -> list[Candidate]:
        """先只看「文件名里确实带这部剧片名」的分享，盘搜混进来的别的剧不参与竞争；
        一个都没带片名时（文件名用英文/缩写）退回全体，避免全军覆没。"""
        return [c for c in candidates if c.title_hit] or candidates

    def _select(skip: set[str]) -> tuple[Candidate | None, bool]:
        """从候选池挑一条（跳过已经跑过的），返回（候选, 是否退档）。"""
        left = [c for c in _pool() if c.shareurl not in skip]
        pick = pick_best(left)
        if pick is not None:
            return pick, False
        # 没有落在 1.5~8G 的：退一档用「每集中位数 >= sub_fallback_min_size_gb」的。
        # 有些剧 4K 压得小（尚公主每集 1.15~1.4G），卡死下限就一集都下不来。
        relaxed = [
            c
            for c in left
            if plugin_config.sub_fallback_min_size_gb
            <= c.median_gb
            <= plugin_config.sub_max_size_gb
        ]
        pick = pick_best(relaxed, require_size_ok=False)
        return pick, pick is not None

    async def _next(skip: set[str]) -> tuple[Candidate | None, bool]:
        """挑下一条：池里挑不到就接着往后扫，扫完再挑。"""
        while True:
            pick, fell_back = _select(skip)
            if pick is not None:
                return pick, fell_back
            if scan_pos >= len(pending):
                return None, False
            await _scan_batches()

    await _scan_batches()

    best, fallback = await _next(set())
    if best is None:
        stats = f"检查了 {checked} 个分享（{failed} 个链接失效、{empty} 个没有视频文件"
        if off_season:
            stats += f"、{off_season} 个是别的季"
        stats += "）"
        if not candidates:
            hint = f"，没有第 {season} 季的资源" if off_season else "，没有可用资源"
            return f"❌ {stats}{hint}\n　　{local_desc}"
        if not any(c.size_ok for c in _pool()):
            medians = sorted(round(c.median_gb, 2) for c in candidates if c.median_gb)
            span = f"，实测每集中位数 {medians[0]}~{medians[-1]}G" if medians else ""
            return (
                f"❌ {stats}，都不在 "
                f"{plugin_config.sub_min_size_gb}~{plugin_config.sub_max_size_gb}G 区间"
                f"{span}（退一档下限 {plugin_config.sub_fallback_min_size_gb}G）\n"
                f"　　{local_desc}"
            )
        return f"✅ 已经是最新，没有新集\n　　{local_desc}（{stats}）"

    # 4. 建任务（统一重命名成 SxxExx）→ 转存 → 删任务
    # 落 0 个就换下一条：QASx 的 transfer_records 是按 file_id + 任务名去重的。
    # 同一条分享以前转过、之后目录被人清空了，再建任务 QASx 只会回「没有新的文件
    # 需要转存」，一个都不落（真机：走马上任 11 集全在记录里，目录却是空的）。
    # 光看回执会当成成功，所以跑完必须回目录数一遍，没落下就换下一条再试。
    tried: list[str] = []
    while best is not None:
        tried.append(best.shareurl)
        task = TaskItem.simple_from_title(title, best.shareurl)
        task.taskname = sanitize_title(title)
        task.savepath = savepath
        # 只转本地缺的那几集：pattern 同时是 QASx 的筛选条件，把集数收窄成白名单，
        # 已有集一个都不会被再转一遍（不收窄时 27 集的分享会把已有的集全重下，
        # 夸克遇同名就存成 S01E07.1.mkv，目录越攒越乱）。
        wanted_eps = sorted({ep for _s, ep in best.new_episodes if _s == season})
        if not wanted_eps:
            best, fallback = await _next(set(tried))
            continue
        task.pattern, task.replace = episode_limited_rules(season, wanted_eps)
        transferable = [n for n in best.video_files if re.search(task.pattern, n)]
        if not transferable:
            logger.info(
                f"订阅[{name}] 分享 {best.shareurl} 文件名和命名规则对不上，换下一条"
            )
            best, fallback = await _next(set(tried))
            continue
        transfer_keys = best.new_episodes & episode_keys(transferable, season)
        dropped = best.new_episodes - transfer_keys
        if not transfer_keys:
            transfer_keys = best.new_episodes
        # 交给 QASx 任务默认配置；注意别写成 None —— null 会让 QASx 的 /update 直接 500
        task.addition = {}

        new_desc = f"新增 {fmt_episode_keys(transfer_keys)}（{len(transfer_keys)} 集）"
        logger.info(
            f"订阅[{name}] 选中 {best.shareurl}（{best.path}）{new_desc}"
            f"，只转这 {len(transfer_keys)} 集"
        )
        try:
            await client.add_task(task)
        except QASException as exc:
            await _cleanup(client, task)
            logger.error(f"订阅[{name}] 添加任务失败: {exc}")
            best, fallback = await _next(set(tried))
            continue

        script_output: list[str] = []
        run_error = ""
        try:
            async for chunk in client.run_script(task):
                script_output.append(chunk)
        except QASException as exc:
            run_error = str(exc)
            logger.error(f"订阅[{name}] 转存失败: {exc}")

        cleaned = await _cleanup(client, task)
        if run_error:
            best, fallback = await _next(set(tried))
            continue

        result = parse_run_output(script_output)
        head = result.render(fallback_savepath=savepath).strip()
        # 回目录数一遍：QASx 回「转存完成」不等于文件真在里面
        after = episode_keys(
            video_names_from_dir(await client.list_savepath_files(savepath)), season
        )
        landed = transfer_keys & after
        if not landed and len(tried) < max(1, plugin_config.sub_transfer_attempts):
            logger.info(
                f"订阅[{name}] 分享 {best.shareurl} 一个都没落下（{head}），换下一条再试"
            )
            best, fallback = await _next(set(tried))
            continue

        # 「没有新文件」时不能再说「新增了哪些集」——那句预测和实际结果会互相打架
        detail = f"{local_desc} → {new_desc}" if landed else local_desc
        lines = [head, f"　　{detail}"]
        if best.path not in ("/", ""):
            lines.append(f"　　ℹ️ 用的是分享里的「{best.path.lstrip('/')}」目录（那一层版本最全）")
        if landed:
            lines.append(f"　　ℹ️ 只转这 {len(transfer_keys)} 集，本地已有的集不会再下")
        if cleared:
            lines.append(f"　　ℹ️ 清掉 {cleared} 条过期转存记录（本地已没有这些集）")
        if not landed:
            lines.append(
                "　　⚠️ 一个文件都没落下：这些集在 QASx 的转存记录里已经有了"
                "（按 file_id + 任务名去重），本地目录却是空的，只能清记录"
            )
        if len(tried) > 1:
            lines.append(f"　　ℹ️ 前面 {len(tried) - 1} 条分享没落下文件，已换到下一条")
        if fallback:
            lines.append(
                f"　　⚠️ 没有 {plugin_config.sub_min_size_gb}~{plugin_config.sub_max_size_gb}G 的分享，"
                f"改用每集约 {best.median_gb:.2f}G 的（正片偏小，画质可能一般）"
            )
        if best.missing:
            lines.append(
                f"　　⚠️ 没找到能补全的链接，这条缺 {fmt_episode_keys(best.missing)}"
                f"（{len(best.missing)} 集），缺的下轮再补"
            )
        if dropped:
            lines.append(
                f"　　⚠️ 另有 {len(dropped)} 集文件名和命名规则对不上，本轮跳过"
                f"（{fmt_episode_keys(dropped)}）"
            )
        if best.dup_episodes:
            lines.append(
                f"　　⚠️ 这条分享里 {fmt_episode_keys(best.dup_episodes)} 各有两份文件，"
                f"会多落一份（QASx 认不出同集异名）"
            )
        if not cleaned:
            lines.append("　　⚠️ 任务未从 QAS 删除，请手动清理")
        return "\n".join(lines)

    return (
        f"❌ 试了 {len(tried)} 条分享，一个文件都没落下\n"
        f"　　{local_desc}\n"
        f"　　（这些分享的集数在 QASx 转存记录里已经有了，本地目录却是空的；"
        f"清掉转存记录后下轮才能重下）"
    )


async def _report(text: str) -> None:
    try:
        chat_id = store.get_chat_id()
    except Exception as exc:  # 订阅文件写坏/格式怪，不能让整轮任务陪葬
        logger.error(f"读取报告会话失败: {exc}")
        logger.info(f"订阅报告（只打日志）: {text}")
        return
    if not chat_id:
        logger.info(f"订阅报告（无会话记录，只打日志）: {text}")
        return
    try:
        import nonebot

        bot = nonebot.get_bot()
        await bot.call_api("send_message", chat_id=chat_id, text=text)
    except Exception as exc:
        logger.error(f"订阅报告发送失败: {exc}")


# 「执行」和定时任务可能撞车：同一时间只跑一轮，避免两边同时建任务/删任务
_sub_running = False


async def _run_all_subscriptions(names: list[str] | None = None) -> None:
    """跑一轮订阅。names 为空则跑全部（定时任务走这条）。"""
    global _sub_running
    if _sub_running:
        logger.info("上一轮订阅还在跑，本次跳过")
        return
    _sub_running = True
    try:
        await _run_subscriptions(names or store.list_all())
    finally:
        _sub_running = False


async def _run_subscriptions(names: list[str]) -> None:
    if not names:
        logger.info("订阅列表为空，跳过本轮")
        return
    logger.info(f"开始执行订阅任务: {names}")
    async with QASClient() as client:
        for name in names:
            try:
                report = await _run_one_subscription(client, name)
            except Exception as exc:
                logger.exception(f"订阅[{name}] 执行异常: {exc}")
                report = f"💥 执行异常: {exc}"
            # 结果先落日志：写订阅文件/发 TG 任一失败都不该让整轮报「执行失败」
            logger.info(f"订阅[{name}] 结果:\n{report}")
            try:
                store.record_result(name, report.splitlines()[0])
            except Exception as exc:
                logger.error(f"订阅[{name}] 结果写入失败（不影响本轮转存）: {exc}")
            await _report(f"📺「{name}」\n{report}")


@get_driver().on_startup
async def _start_subscription_scheduler() -> None:
    import asyncio

    # 先把文件建出来：光挂卷不落文件是正常的（订阅文件第一次写才创建），
    # 但目录属主不对 / 只读挂载必须当场报出来，别等用户发 AD 才发现存不上
    ready, msg = store.ensure_ready()
    if ready:
        logger.info(msg)
    else:
        logger.error(msg)
        await _report(msg)

    names = store.list_all()
    logger.info(
        f"订阅文件: {store.path}（{len(names)} 个订阅）"
        f"，每天 {plugin_config.sub_check_time} 执行"
    )
    # 没挂卷的容器升级一次就把订阅全丢了 —— 启动时立刻喊出来，别等丢完才知道
    warning = persistence_warning(store.path)
    if warning:
        logger.warning(warning)
        await _report(warning)

    async def _loop():
        while True:
            await asyncio.sleep(seconds_until(plugin_config.sub_check_time))
            try:
                await _run_all_subscriptions()
            except Exception as exc:
                logger.exception(f"订阅任务执行失败: {exc}")

    asyncio.get_running_loop().create_task(_loop())
