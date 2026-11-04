"""真机验收：电视剧「甄嬛传」单集转存链路。

验证点（全部用真实 QAS + 真实夸克）：
  1. 建任务（带 SxxExx 重命名规则，只取 E01/E02 两集）
  2. 真转存 → 文件真的落到网盘，文件名被改成 S01E01/S01E02
  3. 同任务第二遍 → QASx 去重，输出「没有新的文件需要转存」，文件数不变
  4. 删任务 → 立刻查不到 → 监控 60 秒不复活
  5. 清理文件 → 任务列表整字典回到基线

不改产品代码，只调用插件自己的客户端。
"""
import asyncio
import json
import os
import sys
import time

import nonebot

nonebot.init()

from nonebot_plugin_quark_autosave.client import QASClient  # noqa: E402
from nonebot_plugin_quark_autosave.model import TaskItem  # noqa: E402
from nonebot_plugin_quark_autosave.result import parse_run_output  # noqa: E402

SHARE = os.environ["SHARE"]
NAME = os.environ.get("TASK_NAME", "_bot自检_甄嬛传")
SAVEPATH = os.environ.get("SAVEPATH", "/_bot自检订阅/甄嬛传")
# 只取这两集：pattern 同时是 QASx 的筛选和重命名规则
PATTERN = os.environ.get("PATTERN", r".*\.(E0[12])\.WEB-DL.*?\.(mp4|mkv)")
REPLACE = os.environ.get("REPLACE", r"S01E\1.\2")
WANT = [n.strip() for n in os.environ.get("WANT", "S01E01.mp4,S01E02.mp4").split(",")]

OK, FAIL = [], []


def check(name, cond, detail=""):
    (OK if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'} {name} {detail}", flush=True)


async def main():
    async with QASClient() as c:
        base = (await c.get_data_raw()).get("tasklist") or []
        print(f"基线任务 {len(base)} 个: {[t.get('taskname') for t in base]}")

        task = TaskItem.simple_from_title(NAME, SHARE)
        task.taskname = NAME
        task.savepath = SAVEPATH
        task.pattern, task.replace = PATTERN, REPLACE
        task.addition = {}
        await c.add_task(task)

        got = next((t for t in (await c.get_data_raw()).get("tasklist") or [] if t.get("taskname") == NAME), None)
        check("建任务成功", got is not None)
        if got:
            check("skip_calendar 落盘", got.get("skip_calendar") is True, str(got.get("skip_calendar")))
            check("update_subdir 落盘", got.get("update_subdir") == ".*", repr(got.get("update_subdir")))
            check("savepath 落盘", got.get("savepath") == SAVEPATH, str(got.get("savepath")))
            check("重命名规则落盘", got.get("replace") == REPLACE, str(got.get("replace")))

        print("\n---- 第一轮：真转存 ----")
        out1 = []
        async for chunk in c.run_script(task):
            out1.append(chunk)
        res1 = parse_run_output(out1)
        print("\n".join(out1[-8:]))
        check("第一轮 status=success", res1.status == "success", res1.status)

        landed = [f.get("file_name") for f in await c.list_savepath_files(SAVEPATH)]
        print(f"落盘文件: {landed}")
        check("两集都落到网盘", len(landed) >= 2, f"{len(landed)} 个")
        for want in WANT:
            check(f"命名统一为 {want}", want in landed)

        print("\n---- 第二轮：同名同目录去重 ----")
        out2 = []
        async for chunk in c.run_script(task):
            out2.append(chunk)
        res2 = parse_run_output(out2)
        print("\n".join(out2[-6:]))
        check("第二轮识别为 no_new", res2.status == "no_new", res2.status)
        landed2 = [f.get("file_name") for f in await c.list_savepath_files(SAVEPATH)]
        check("第二轮文件数不变", len(landed2) == len(landed), f"{len(landed)} -> {len(landed2)}")

        print("\n---- 删任务 + 防复活 ----")
        ok = await c.delete_task(task)
        check("删任务返回成功", bool(ok), str(ok))
        left = [t.get("taskname") for t in (await c.get_data_raw()).get("tasklist") or []]
        check("删完立刻查不到", NAME not in left, str(len(left)))

        ghosts = []
        start = time.time()
        while time.time() - start < 60:
            await asyncio.sleep(5)
            names = [t.get("taskname") for t in (await c.get_data_raw()).get("tasklist") or []]
            if NAME in names:
                ghosts.append(round(time.time() - start))
        check("60 秒内不复活", not ghosts, f"复活时刻(秒): {ghosts}")

        print("\n---- 清理文件 ----")
        for item in await c.list_savepath_files(SAVEPATH):
            if item.get("fid"):
                await c.delete_file(str(item["fid"]))
        for _ in range(10):
            await asyncio.sleep(3)
            if not await c.list_savepath_files(SAVEPATH):
                break
        for item in (c._check_response(
            await c._request_with_retry("GET", "/get_savepath_detail", params={"path": SAVEPATH})
        ) or {}).get("list") or []:
            if item.get("fid"):
                await c.delete_file(str(item["fid"]))
        await asyncio.sleep(4)
        for parent in ("/_bot自检订阅",):
            for item in (c._check_response(
                await c._request_with_retry("GET", "/get_savepath_detail", params={"path": parent})
            ) or {}).get("list") or []:
                if item.get("fid"):
                    await c.delete_file(str(item["fid"]))
        await asyncio.sleep(4)
        check("自检文件已清理", not await c.list_savepath_files(SAVEPATH))

        final = (await c.get_data_raw()).get("tasklist") or []
        check("最终任务与基线完全一致(整字典)", final == base, f"{len(final)} vs {len(base)}")

    print(f"\n通过 {len(OK)} / 失败 {len(FAIL)}")
    if FAIL:
        print(f"失败项: {FAIL}")
    return 1 if FAIL else 0


sys.exit(asyncio.run(main()))
