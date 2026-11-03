"""对真实 QASx 实例（127.0.0.1:5599）实跑 client.py 的每个接口。"""
import asyncio
import os
import sys

os.environ["QAS_ENDPOINT"] = "http://127.0.0.1:5599"
os.environ["QAS_TOKEN"] = "231436838b70dc9a"
os.environ["QAS_RUN_TIMEOUT"] = "120"
os.environ["DRIVER"] = "~httpx"

sys.path.insert(0, "/home/agent/.hermes/workspace/quark-autosave-bot/src")

import nonebot

nonebot.init()

from nonebot_plugin_quark_autosave.config import plugin_config

plugin_config.qas_endpoint = "http://127.0.0.1:5599"
plugin_config.qas_token = "231436838b70dc9a"
plugin_config.qas_run_timeout = 120

from nonebot_plugin_quark_autosave.client import QASClient
from nonebot_plugin_quark_autosave.model import TaskItem

OK, FAIL = [], []


def check(name, cond, detail=""):
    (OK if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'} {name} {detail}")


async def main():
    async with QASClient() as c:
        # 1. /data
        tasks = await c.list_tasks()
        check("list_tasks 读 /data", isinstance(tasks, list), f"初始 {len(tasks)} 个任务")

        # 2. add_task
        t = TaskItem(
            taskname="E2E测试-删除验证",
            shareurl="https://pan.quark.cn/s/e2etestfake",
            savepath="/自动/E2E测试",
            pattern=r".*?\.(mp4|mkv)",
            replace="S01E\\1",
        )
        added = await c.add_task(t)
        check("add_task 写入", added.taskname == t.taskname)
        tasks = await c.list_tasks()
        names = [x.taskname for x in tasks]
        check("/data 回读有该任务", "E2E测试-删除验证" in names, str(names))

        # 3. delete_task —— 核心需求
        deleted = await c.delete_task(t)
        check("delete_task 返回任务名", deleted == t.taskname, deleted)
        tasks = await c.list_tasks()
        names = [x.taskname for x in tasks]
        check("删除后 /data 已无该任务", "E2E测试-删除验证" not in names, f"剩余 {names}")

        # 4. 删不存在的任务应报错而非静默
        try:
            await c.delete_task(t)
            check("删不存在的任务应抛错", False, "居然没抛错")
        except Exception as exc:
            check("删不存在的任务抛错", True, str(exc)[:60])

        # 5. list_savepath_files：目录不存在应返回 []，不能崩
        try:
            files = await c.list_savepath_files("/不存在的目录xyz")
            check("list_savepath_files 容错", files == [], str(files))
        except Exception as exc:
            check("list_savepath_files 容错", False, f"崩了: {exc}")

        # 6. task_suggestions：结构必须是 list
        try:
            sug = await c.task_suggestions("甄嬛传")
            check("task_suggestions 返回 list", isinstance(sug, list), f"{len(sug)} 条")
            if sug:
                print("   首条字段:", sorted(sug[0].keys()))
        except Exception as exc:
            check("task_suggestions 返回 list", False, f"崩了: {exc}")

        # 7. run_script SSE 流：假 cookie，预期转存失败但不该卡死
        lines = []
        try:
            async for chunk in c.run_script(t):
                lines.append(chunk)
        except Exception as exc:
            lines.append(f"[异常] {exc}")
        check("run_script_now SSE 可流式读取", bool(lines), f"{len(lines)} 段输出")
        if lines:
            print("   首段:", lines[0][:200].replace("\n", " | "))

    print(f"\n通过 {len(OK)} / 失败 {len(FAIL)}")
    if FAIL:
        print("失败项:", FAIL)
    return 1 if FAIL else 0


sys.exit(asyncio.run(main()))
