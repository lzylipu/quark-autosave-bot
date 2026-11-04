"""诊断真转存：建任务 → 跑脚本 → 打印 QASx 原始输出 → 列落盘 → 删任务。

用法：
    SHARE=https://pan.quark.cn/s/xxx SAVE=_bot自检/诊断 PYTHONPATH=src python3 tests/e2e/diag_run2.py
"""
import asyncio
import os

import nonebot

nonebot.init()

from nonebot_plugin_quark_autosave.client import QASClient  # noqa: E402
from nonebot_plugin_quark_autosave.config import plugin_config  # noqa: E402
from nonebot_plugin_quark_autosave.model import TaskItem  # noqa: E402
from nonebot_plugin_quark_autosave.subscribe import rename_rules  # noqa: E402

SHARE = os.environ["SHARE"]
SAVE = os.environ.get("SAVE", "_bot自检/诊断")
TITLE = os.environ.get("TITLE", "诊断任务")


async def main():
    async with QASClient() as c:
        task = TaskItem.simple_from_title(TITLE, SHARE)
        task.savepath = "/" + SAVE
        task.pattern, task.replace = rename_rules(1)
        task.addition = {}
        print(f"taskname={task.taskname} savepath={task.savepath}", flush=True)
        print(f"pattern={task.pattern}", flush=True)
        print(f"update_subdir={task.update_subdir!r} skip_calendar={task.skip_calendar}", flush=True)
        await c.add_task(task)
        out = []
        async for chunk in c.run_script(task):
            out.append(chunk)
            print(chunk, end="", flush=True)
        print("\n--- 原始输出完 ---", flush=True)
        files = await c.list_savepath_files(task.savepath)
        vids = [f for f in files if not f.get("dir")]
        print(f"落盘 {len(vids)} 个", flush=True)
        for f in vids[:12]:
            print(f"    {f.get('file_name_saved') or f.get('file_name')}", flush=True)
        # 清理
        for f in files:
            if f.get("dir"):
                await c.delete_file(task.savepath, [f])
        for f in files:
            if not f.get("dir"):
                await c.delete_file(task.savepath, [f])
        await c.delete_task(task)
        print(f"SIMPLE_SAVE_ROOT={plugin_config.simple_save_root}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
