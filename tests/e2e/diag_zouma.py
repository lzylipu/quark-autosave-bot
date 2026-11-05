"""诊断：走马上任 为什么落 0 个文件。保留任务，把 QAS 原始输出全打出来。"""
import asyncio
import sys

import nonebot

nonebot.init()

from nonebot_plugin_quark_autosave import _cleanup  # noqa: E402
from nonebot_plugin_quark_autosave.client import QASClient  # noqa: E402
from nonebot_plugin_quark_autosave.config import plugin_config  # noqa: E402
from nonebot_plugin_quark_autosave.model import TaskItem, sanitize_title  # noqa: E402
from nonebot_plugin_quark_autosave.subscribe import season_or_bare_rules  # noqa: E402

SHARE = sys.argv[1] if len(sys.argv) > 1 else "https://pan.quark.cn/s/9bfcbdb8f5ba"
TITLE = sys.argv[2] if len(sys.argv) > 2 else "走马上任"


async def main():
    root = plugin_config.simple_save_root
    savepath = sys.argv[3] if len(sys.argv) > 3 else f"/{root}/{sanitize_title(TITLE)}"
    async with QASClient() as c:
        task = TaskItem.simple_from_title(TITLE, SHARE)
        task.taskname = sanitize_title(TITLE)
        task.savepath = savepath
        task.pattern, task.replace = season_or_bare_rules(1)
        task.addition = {}
        print(f"PATTERN {task.pattern}", flush=True)
        print(f"REPLACE {task.replace}", flush=True)
        print(f"SAVEPATH {savepath}", flush=True)
        try:
            await c.add_task(task)
            print("task added", flush=True)
        except Exception as exc:  # noqa: BLE001
            print("add failed:", exc, flush=True)
            return
        print("---- QAS 原始输出 ----", flush=True)
        try:
            async for chunk in c.run_script(task):
                print(chunk, flush=True)
        except Exception as exc:  # noqa: BLE001
            print("run failed:", exc, flush=True)
        print("---- 落盘 ----", flush=True)
        files = await c.list_savepath_files(savepath)
        for f in files:
            print(f"  {f.get('file_name_saved') or f.get('file_name')} "
                  f"{round((f.get('size') or 0)/1024**3, 2)}G", flush=True)
        print(f"共 {len([f for f in files if not f.get('dir')])} 个文件", flush=True)
        await _cleanup(c, task)
        print("task cleaned", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
