"""诊断：为什么 QASx 判定「没有新的文件需要转存」。

建一个临时任务，跑一轮，打印**完整**输出、分享详情里的文件名与扩展名、
目标目录当前内容，最后删任务。
"""
import asyncio
import os
import sys

import nonebot

nonebot.init()

from nonebot_plugin_quark_autosave import subscribe as sub
from nonebot_plugin_quark_autosave.client import QASClient
from nonebot_plugin_quark_autosave.model import TaskItem

NAME = "_诊断_无新文件"
SAVEPATH = "/自动/_诊断"
QUERY = os.environ.get("DIAG_QUERY", "舌尖上的中国")


async def main():
    async with QASClient() as c:
        shareurl = os.environ.get("DIAG_URL", "").strip()
        files = []
        if shareurl:
            print(f"用指定分享 {shareurl}")
            files = await c.get_share_files(shareurl, max_depth=3, max_dirs=12)
        else:
            sug = await c.task_suggestions(QUERY)
            print(f"搜索 {QUERY} → {len(sug)} 条")
            for s in sug[:10]:
                url = str(s.get("shareurl") or "").split("#", 1)[0]
                if not url:
                    continue
                try:
                    fs = await c.get_share_files(url, max_depth=3, max_dirs=12)
                except Exception as exc:
                    print(f"  跳过 {url}: {str(exc)[:60]}")
                    continue
                vids = [f for f in fs if not f.dir]
                if not vids:
                    continue
                shareurl, files = url, fs
                break
        if not shareurl:
            print("!! 没拿到可用分享")
            return 1
        print(f"选中 {shareurl}")
        exts = sorted({(f.file_name.rsplit(".", 1)[-1].lower() if "." in f.file_name else "?")
                       for f in files if not f.dir})
        print(f"文件 {len(files)} 个，扩展名分布: {exts}")
        for f in files[:15]:
            print(f"  {'DIR ' if f.dir else 'FILE'} {f.file_name}  {getattr(f, 'size', 0) / 1024 ** 3:.2f}GB")

        print(f"\n保存目录 {SAVEPATH} 现有:")
        for f in await c.list_savepath_files(SAVEPATH):
            print("   ", f.get("file_name"), f.get("size"))

        task = TaskItem.simple_from_title(NAME, shareurl)
        task.taskname = NAME
        task.savepath = SAVEPATH
        task.pattern, task.replace = sub.rename_rules(1)
        task.addition = {}
        await c.add_task(task)
        print(f"\npattern={task.pattern!r} replace={task.replace!r}")

        print("\n===== 完整输出 =====")
        chunks = [chunk async for chunk in c.run_script(task)]
        print("\n".join(chunks))
        print("===== 输出结束 =====\n")

        landed = await c.list_savepath_files(SAVEPATH)
        print(f"落盘 {len(landed)} 个: {[f.get('file_name') for f in landed]}")

        ok = await c.delete_task(task)
        print(f"删任务 {ok}")
        for f in landed:
            if f.get("fid"):
                await c.delete_file(str(f["fid"]))
        left = await c.list_savepath_files(SAVEPATH)
        print(f"清理后剩 {len(left)} 个")
    return 0


sys.exit(asyncio.run(main()))
