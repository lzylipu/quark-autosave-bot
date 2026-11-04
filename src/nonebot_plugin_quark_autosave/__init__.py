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
    fmt_episode_keys,
    has_explicit_season,
    parse_season,
    pick_best,
    rename_rules,
    season_rename_rules,
    seconds_until,
    split_season,
    video_names_from_dir,
)

__plugin_meta__ = PluginMetadata(
    name="夸克自动转存",
    description="发夸克链接直接转存，智能检测链接有效性",
    usage="直接发送夸克网盘链接即可，如: https://pan.quark.cn/s/xxxxx?pwd=1234",
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
# 追剧订阅：AD / DL / LIST 命令 + 每天定时搜索补缺转存
# ======================================================================

store = SubscriptionStore(plugin_config.sub_store_file)

_SUB_CMD_RE = re.compile(r"^\s*(AD|DL|LIST)(?=\s|$)\s*(.*)$", re.IGNORECASE | re.DOTALL)


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
    cmd, arg = match.group(1).upper(), match.group(2).strip()

    if cmd == "AD":
        # 记住会话，定时任务的报告发回这里
        if chat_id := _chat_id_of(event):
            store.set_chat_id(chat_id)
        _, msg = store.add(arg)
        await sub_handler.finish(msg)

    if cmd == "DL":
        _, msg = store.remove(arg)
        await sub_handler.finish(msg)

    names = store.list_all()
    if not names:
        await sub_handler.finish("📭 订阅列表是空的，用「AD 片名」订阅")
    data = store.load()
    lines = [f"📋 订阅列表（每天 {plugin_config.sub_check_time} 自动执行）:"]
    for i, name in enumerate(names, 1):
        last = data.get(name, {}).get("last_result", "")
        lines.append(f"{i}. {name}" + (f"\n   └ 上次: {last}" if last else "\n   └ 还没跑过"))
    await sub_handler.finish("\n".join(lines))


def _only_season(cand: Candidate, season: int, enabled: bool) -> Candidate:
    """订阅写死了季时，把候选的「待补集」砍到只剩这一季。

    assess_share 按文件名里的季建 (季, 集)；「黑镜 S05」搜到第七季的分享时，
    S07E01~E06 会全被算成待补 → 结果下错季（真机复现）。这里只保留目标季。
    """
    if enabled:
        cand.new_episodes = {key for key in cand.new_episodes if key[0] == season}
    return cand


async def _run_one_subscription(client: QASClient, name: str) -> str:
    """跑一个订阅：扫本地 → 搜索 → 筛大小 → 选能补最多的 → 转存 → 删任务。"""
    title, season = split_season(name)
    # 订阅名写死了季（「黑镜 S05」）就只下这一季，否则会把别的季当成本季缺集
    only_season = has_explicit_season(name)
    savepath = f"/{plugin_config.simple_save_root}/{sanitize_title(title)}"

    # 1. 本地已有哪几集
    local_files = await client.list_savepath_files(savepath)
    local_keys = episode_keys(video_names_from_dir(local_files), season)
    local_desc = f"本地已有 {fmt_episode_keys(local_keys)}" if local_keys else "本地还没有剧集"

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
    limit = plugin_config.sub_max_candidates
    max_ok = plugin_config.sub_max_ok_candidates
    pending = results if limit <= 0 else results[:limit]
    checked = failed = empty = 0
    sem = asyncio.Semaphore(_PROBE_CONCURRENCY)

    async def _probe(idx: int, item: dict) -> tuple[int, Candidate | None, str]:
        """探一个分享。返回 (序号, 候选, 失败原因)；失败原因空表示成功。"""
        shareurl = str(item.get("shareurl", "")).strip()
        if not shareurl:
            return idx, None, ""
        async with sem:
            try:
                files = await client.get_share_files(shareurl)
            except QASException as exc:
                # 链接失效是常态，换下一个
                logger.info(f"订阅[{name}] 跳过分享 {shareurl}: {exc}")
                return idx, None, str(exc)
        cand = _only_season(
            assess_share(
                shareurl,
                files,
                local_keys,
                plugin_config.sub_min_size_gb,
                plugin_config.sub_max_size_gb,
                season,
                title,
                str(item.get("taskname") or ""),
            ),
            season,
            only_season,
        )
        return idx, cand, ""

    # 并发探详情：一条一条串行的话，热门剧 170 多条要跑好几分钟。
    # 结果按原始搜索顺序排序，同分时仍然取先搜到的（盘搜按时间倒序）。
    probed = await asyncio.gather(
        *(_probe(i, item) for i, item in enumerate(pending))
    )
    candidates: list[Candidate] = []
    for idx, cand, err in sorted(probed, key=lambda x: x[0]):
        if err or cand is None:
            if err:
                failed += 1
            continue
        checked += 1
        if not cand.video_files:
            empty += 1
            continue
        candidates.append(cand)
        if max_ok > 0 and sum(1 for c in candidates if c.size_ok) >= max_ok:
            logger.info(f"订阅[{name}] 已够 {max_ok} 个合格分享")
            break

    # 先只看「文件名里确实带这部剧片名」的分享，盘搜混进来的别的剧不参与竞争；
    # 一个都没带片名时（文件名用英文/缩写）退回全体，避免全军覆没。
    pool = [c for c in candidates if c.title_hit] or candidates

    best = pick_best(pool)
    fallback = False
    if best is None:
        # 没有落在 1.5~8G 的：退一档用「每集中位数 >= sub_fallback_min_size_gb」的。
        # 有些剧 4K 压得小（尚公主每集 1.15~1.4G），卡死下限就一集都下不来。
        relaxed = [
            c
            for c in pool
            if plugin_config.sub_fallback_min_size_gb
            <= c.median_gb
            <= plugin_config.sub_max_size_gb
        ]
        best = pick_best(relaxed, require_size_ok=False)
        fallback = best is not None
    if best is None:
        stats = f"检查了 {checked} 个分享（{failed} 个链接失效、{empty} 个没有视频文件）"
        if not candidates:
            return f"❌ {stats}，没有可用资源\n　　{local_desc}"
        if not any(c.size_ok for c in pool):
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
    task = TaskItem.simple_from_title(title, best.shareurl)
    task.taskname = sanitize_title(title)
    task.savepath = savepath
    # 文件名里已经带季数（合集常见：…S03.EP07…）就沿用文件里的季，
    # 否则统一按订阅名的季补前缀
    keep_season = any(parse_season(n) for n in best.video_files)
    if only_season and keep_season:
        # 写死了季 + 文件名带季：pattern 同时当筛选用，只转存这一季
        task.pattern, task.replace = season_rename_rules(season)
    else:
        task.pattern, task.replace = rename_rules(season, keep_season_in_name=keep_season)
    # pattern 同时是 QASx 的筛选条件：匹配不上文件名不转存。所以「新增几集」
    # 只能算真正会被转存的那几集——合集里既有 S02E05 又有 E01 时，E01 会被跳过
    # （真机：法警小队 报「新增 15 集」，落盘只有 3 个）。
    # 预算不出来时（文件名写法比本地正则更野）不能拦，交给 QASx 自己判断。
    transferable = [n for n in best.video_files if re.search(task.pattern, n)]
    transfer_keys = best.new_episodes & episode_keys(transferable, season)
    dropped = best.new_episodes - transfer_keys if transfer_keys else set()
    if not transfer_keys:
        transfer_keys = best.new_episodes
    # 交给 QASx 任务默认配置；注意别写成 None —— null 会让 QASx 的 /update 直接 500
    task.addition = {}

    new_desc = f"新增 {fmt_episode_keys(transfer_keys)}（{len(transfer_keys)} 集）"
    logger.info(f"订阅[{name}] 选中 {best.shareurl} {new_desc}")
    try:
        await client.add_task(task)
    except QASException as exc:
        return f"❌ 添加任务失败: {exc}\n　　{local_desc}"

    script_output: list[str] = []
    try:
        async for chunk in client.run_script(task):
            script_output.append(chunk)
    except QASException as exc:
        await _cleanup(client, task)
        return f"❌ 转存失败: {exc}\n　　{local_desc}"

    cleaned = await _cleanup(client, task)
    result = parse_run_output(script_output)
    head = result.render(fallback_savepath=savepath).strip()
    # 「没有新文件」时不能再说「新增了哪些集」——那句预测和实际结果会互相打架
    detail = local_desc if result.status == "no_new" else f"{local_desc} → {new_desc}"
    lines = [head, f"　　{detail}"]
    if fallback:
        lines.append(
            f"　　⚠️ 没有 {plugin_config.sub_min_size_gb}~{plugin_config.sub_max_size_gb}G 的分享，"
            f"改用每集约 {best.median_gb:.2f}G 的（正片偏小，画质可能一般）"
        )
    if dropped:
        lines.append(
            f"　　⚠️ 另有 {len(dropped)} 集文件名不带季数，按命名规则转不了，本轮跳过"
            f"（{fmt_episode_keys(dropped)}）"
        )
    if not cleaned:
        lines.append("　　⚠️ 任务未从 QAS 删除，请手动清理")
    return "\n".join(lines)


async def _report(text: str) -> None:
    chat_id = store.get_chat_id()
    if not chat_id:
        logger.info(f"订阅报告（无会话记录，只打日志）: {text}")
        return
    try:
        import nonebot

        bot = nonebot.get_bot()
        await bot.call_api("send_message", chat_id=chat_id, text=text)
    except Exception as exc:
        logger.error(f"订阅报告发送失败: {exc}")


async def _run_all_subscriptions() -> None:
    names = store.list_all()
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

    names = store.list_all()
    logger.info(
        f"订阅定时器已启动，共 {len(names)} 个订阅，每天 {plugin_config.sub_check_time} 执行"
    )

    async def _loop():
        while True:
            await asyncio.sleep(seconds_until(plugin_config.sub_check_time))
            try:
                await _run_all_subscriptions()
            except Exception as exc:
                logger.exception(f"订阅任务执行失败: {exc}")

    asyncio.get_running_loop().create_task(_loop())
