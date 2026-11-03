"""真机自检（v3）：同名任务+同目录跑两轮 → 去重生效 → 删任务 → 不复活 → 清文件。

验证的是线上真实用法：追剧用固定任务名和固定目录，QAS 自己认「已有集数」，
有新集才补。所以这里不搞唯一名字。
"""
import asyncio
import sys

import nonebot

nonebot.init()

from nonebot_plugin_quark_autosave import subscribe as sub
from nonebot_plugin_quark_autosave.client import QASClient
from nonebot_plugin_quark_autosave.model import TaskItem
from nonebot_plugin_quark_autosave.result import parse_run_output

NAME = "_bot自检_转存"
SAVEPATH = "/自动/_bot自检"
OK, FAIL = [], []


def check(name, cond, detail=""):
    (OK if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'} {name} {detail}", flush=True)


async def main():
    async with QASClient() as c:
        base = [(t.get("taskname"), t.get("shareurl"))
                for t in (await c.get_data_raw()).get("tasklist") or []]
        print(f"基线任务 {len(base)} 个\n", flush=True)

        sug = await c.task_suggestions("幻视")
        check("搜索有结果", len(sug) > 0, f"{len(sug)} 条")
        best = None
        for s in sug[:10]:
            url = str(s.get("shareurl") or "")
            if not url:
                continue
            try:
                files = await c.get_share_files(url, max_depth=3, max_dirs=12)
            except Exception:
                continue
            videos = [f for f in files if not f.dir
                      and f.file_name.rsplit(".", 1)[-1].lower() in sub.VIDEO_EXTS]
            if not videos:
                continue
            total = sum(f.size for f in videos)
            if best is None or total < best[0]:
                best = (total, url, len(videos))
        if not best:
            print("!! 没找到可用分享")
            return 1
        total_gb, shareurl, n_video = best
        print(f"选中 {total_gb/1024**3:.2f}GB / {n_video} 个视频\n{shareurl}\n", flush=True)

        task = TaskItem.simple_from_title(NAME, shareurl)
        task.taskname = NAME
        task.savepath = SAVEPATH
        print(f"任务字段: update_subdir={task.update_subdir!r} "
              f"skip_calendar={task.skip_calendar} runweek={task.runweek}\n", flush=True)
        await c.add_task(task)
        mid = [x.get("taskname") for x in (await c.get_data_raw()).get("tasklist") or []]
        check("建任务成功", NAME in mid)
        check("没吞掉别人的任务", all(p[0] in mid for p in base), f"{len(mid)} 个")

        # --- 第一轮：真转存 ---
        chunks1 = []
        async for chunk in c.run_script(task):
            chunks1.append(chunk)
        text1 = "\n".join(chunks1)
        res1 = parse_run_output(chunks1)
        print("---- 第一轮输出尾部 ----")
        print(text1[-700:])
        print("------------------------", flush=True)
        landed = await c.list_savepath_files(SAVEPATH)
        check("第一轮转存成功", res1.status in ("success", "partial"),
              f"status={res1.status} / {len(res1.files)} 文件")
        check("文件真落到网盘", len(landed) > 0,
              f"{len(landed)} 个: {[f.get('file_name') for f in landed][:2]}")

        # --- 第二轮：同名同目录再跑，必须被自动去重 ---
        chunks2 = []
        async for chunk in c.run_script(task):
            chunks2.append(chunk)
        text2 = "\n".join(chunks2)
        res2 = parse_run_output(chunks2)
        check("第二轮自动去重", "没有新的文件需要转存" in text2,
              f"status={res2.status}")
        landed2 = await c.list_savepath_files(SAVEPATH)
        check("第二轮文件数没变", len(landed2) == len(landed),
              f"{len(landed)} -> {len(landed2)}")

        # --- 删任务 ---
        try:
            await c.delete_task(task)
            check("删任务成功", True, f"已删 {NAME}")
        except Exception as exc:
            check("删任务成功", False, str(exc)[:150])

        # --- 复活观察 30 秒（QASx 后台线程写回的高发窗口）---
        alive = []
        for i in range(6):
            await asyncio.sleep(5)
            if NAME in [x.taskname for x in await c.list_tasks()]:
                alive.append(5 * (i + 1))
        check("30 秒内没复活", not alive, f"复活时刻(秒): {alive}")

        # --- 清文件 ---
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

        final = [(x.get("taskname"), x.get("shareurl"))
                 for x in (await c.get_data_raw()).get("tasklist") or []]
        check("最终任务与基线完全一致", final == base, f"{len(final)} vs {len(base)}")

    print(f"\n通过 {len(OK)} / 失败 {len(FAIL)}", flush=True)
    if FAIL:
        print("失败项:", FAIL, flush=True)
    return 1 if FAIL else 0


sys.exit(asyncio.run(main()))
