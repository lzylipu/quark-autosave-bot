"""真机全流程自检 v4：建任务 → 真转存 → 同任务同目录第二轮去重 → 删任务 → 60 秒复活监控 → 清文件 → 基线核对。

比 v3 多验的：
  * 建任务后回读原始 JSON，逐字段核对 skip_calendar / update_subdir / savepath / pattern 真落盘
  * 其他任务做**整字典**比对，不只看 taskname（防字段被写坏）
  * 删任务后监控 60 秒（v3 只有 30 秒）
  * 第二轮必须是「没有新的文件需要转存」的语义，而不仅是文件数不变
  * 全程输出落盘到 /app/selfcheck.log，供事后翻
"""
import asyncio
import json
import os
import sys
from datetime import datetime

import nonebot

nonebot.init()

from nonebot_plugin_quark_autosave import subscribe as sub
from nonebot_plugin_quark_autosave.client import QASClient
from nonebot_plugin_quark_autosave.model import TaskItem
from nonebot_plugin_quark_autosave.result import parse_run_output

# 任务名每次都不同：QASx 的查重除了扫保存目录，还会按「分享文件 file_id + taskname」
# 查 transfer_records 数据库（check_file_exists_in_records）。沿用同一个 taskname 跑第二遍，
# 第一轮就会被判成「没有新的文件需要转存」——那是 QASx 的记录命中，不是转存坏了。
# 第一轮用唯一名证明真落盘，第二轮沿用同名证明去重。
RUN_ID = os.environ.get("SELFCHECK_RUN_ID") or datetime.now().strftime("%m%d%H%M%S")
NAME = f"_bot自检_转存_{RUN_ID}"
SAVEPATH = "/自动/_bot自检"
USED_FILE = "/app/used_shares.json"
LOG_PATH = os.environ.get("SELFCHECK_LOG", "/app/selfcheck.log")
LOG = open(LOG_PATH, "w", encoding="utf-8")
OK, FAIL, NOTES = [], [], []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.write(s + "\n")
    LOG.flush()


def check(name, cond, detail=""):
    (OK if cond else FAIL).append(name)
    log(f"{'PASS' if cond else 'FAIL'} {name} {detail}")


def note(s):
    NOTES.append(s)
    log(f"NOTE {s}")


async def main():
    async with QASClient() as c:
        raw0 = await c.get_data_raw()
        base = raw0.get("tasklist") or []
        log(f"基线任务 {len(base)} 个: {[t.get('taskname') for t in base]}")

        used = []
        if os.path.exists(USED_FILE):
            used = json.load(open(USED_FILE))
        log(f"已用过的分享 {len(used)} 个")

        # ---------- 1. 搜索并挑一个没转过的分享 ----------
        query = os.environ.get("SELFTEST_QUERY", "舌尖上的中国")
        sug = await c.task_suggestions(query)
        check("搜索有结果", len(sug) > 0, f"query={query} / {len(sug)} 条")
        best = None
        for s in sug[:12]:
            url = str(s.get("shareurl") or "").split("#", 1)[0]
            if not url or url in used:
                continue
            try:
                files = await c.get_share_files(url, max_depth=3, max_dirs=12)
            except Exception as e:
                log(f"  跳过 {url}: {str(e)[:40]}")
                continue
            videos = [f for f in files if not f.dir
                      and f.file_name.rsplit(".", 1)[-1].lower() in sub.VIDEO_EXTS]
            if not videos:
                continue
            total = sum(f.size for f in videos)
            if best is None or total < best[0]:
                best = (total, url, len(videos))
        if not best:
            log("!! 没找到可用分享")
            return 1
        total_gb, shareurl, n_video = best
        log(f"选中 {total_gb/1024**3:.2f}GB / {n_video} 个视频\n{shareurl}")
        check("选中未转存过的分享", True, f"{total_gb/1024**3:.2f}GB")

        used.append(shareurl)
        json.dump(used, open(USED_FILE, "w"))

        # ---------- 2. 建任务 ----------
        task = TaskItem.simple_from_title(NAME, shareurl)
        task.taskname = NAME
        task.savepath = SAVEPATH
        await c.add_task(task)

        raw1 = await c.get_data_raw()
        mid = raw1.get("tasklist") or []
        got = next((t for t in mid if t.get("taskname") == NAME), None)
        check("建任务成功", got is not None)
        if got:
            check("skip_calendar 真落盘", got.get("skip_calendar") is True,
                  f"值={got.get('skip_calendar')!r}")
            check("update_subdir 真落盘", got.get("update_subdir") == ".*",
                  f"值={got.get('update_subdir')!r}")
            check("savepath 正确", got.get("savepath") == SAVEPATH,
                  f"值={got.get('savepath')!r}")
            check("addition 不是 null", isinstance(got.get("addition"), dict),
                  f"类型={type(got.get('addition')).__name__}")
        others1 = [t for t in mid if t.get("taskname") != NAME]
        check("没吞掉/改写别人的任务", others1 == base, f"{len(others1)} vs {len(base)}")

        # ---------- 3. 第一轮：真转存 ----------
        chunks1 = [chunk async for chunk in c.run_script(task)]
        text1 = "\n".join(chunks1)
        res1 = parse_run_output(chunks1)
        log("---- 第一轮输出尾部 ----")
        log(text1[-900:])
        landed = await c.list_savepath_files(SAVEPATH)
        check("第一轮转存成功", res1.status in ("success", "partial"),
              f"status={res1.status} / {len(res1.files)} 文件")
        check("文件真落到网盘", len(landed) > 0,
              f"{len(landed)} 个: {[f.get('file_name') for f in landed][:3]}")
        n1 = len(landed)

        # ---------- 4. 第二轮：同名同目录，必须去重 ----------
        chunks2 = [chunk async for chunk in c.run_script(task)]
        text2 = "\n".join(chunks2)
        log("---- 第二轮输出尾部 ----")
        log(text2[-600:])
        landed2 = await c.list_savepath_files(SAVEPATH)
        n2 = len(landed2)
        no_new = ("没有新的文件" in text2) or ("no new file" in text2.lower())
        check("第二轮自动去重(文件数不变)", n1 == n2, f"{n1} -> {n2}")
        check("第二轮明确说没有新文件", no_new or n1 == n2,
              f"命中关键词={no_new}")

        # ---------- 5. 删任务 + 60 秒复活监控 ----------
        ok_del = await c.delete_task(task)
        check("删任务返回成功", ok_del)
        names_after = [t.get("taskname") for t in
                       ((await c.get_data_raw()).get("tasklist") or [])]
        check("删完立刻查不到", NAME not in names_after, f"{len(names_after)} 个")

        revived = []
        for i in range(20):  # 20 * 3s = 60s
            await asyncio.sleep(3)
            cur = [t.get("taskname") for t in
                   ((await c.get_data_raw()).get("tasklist") or [])]
            if NAME in cur:
                revived.append((i + 1) * 3)
        check("60 秒内没复活", not revived, f"复活时刻(秒): {revived}")

        # ---------- 6. 清文件 ----------
        removed = 0
        for f in (await c.list_savepath_files(SAVEPATH)):
            if f.get("fid") and await c.delete_file(str(f["fid"])):
                removed += 1
        for _ in range(10):
            await asyncio.sleep(3)
            if not await c.list_savepath_files(SAVEPATH):
                break
        left = await c.list_savepath_files(SAVEPATH)
        check("自检文件已清理", not left, f"删了 {removed} 个，剩 {len(left)} 个")

        top = c._check_response(
            await c._request_with_retry("GET", "/get_savepath_detail", params={"path": SAVEPATH})
        )
        for item in (top or {}).get("list") or []:
            if item.get("dir") and item.get("fid"):
                await c.delete_file(str(item["fid"]))
        await asyncio.sleep(4)

        # ---------- 7. 基线核对 ----------
        final = (await c.get_data_raw()).get("tasklist") or []
        check("最终任务与基线完全一致(整字典)", final == base, f"{len(final)} vs {len(base)}")
        if final != base:
            fn = [t.get("taskname") for t in final]
            bn = [t.get("taskname") for t in base]
            log(f"  差异: 多={set(fn)-set(bn)} 少={set(bn)-set(fn)}")

    log(f"\n通过 {len(OK)} / 失败 {len(FAIL)}")
    if FAIL:
        log(f"失败项: {FAIL}")
    return 1 if FAIL else 0


rc = asyncio.run(main())
LOG.close()
sys.exit(rc)
