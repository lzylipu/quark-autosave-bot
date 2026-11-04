"""诊断「根目录只有一个文件夹」的分享能不能递归展开出剧集文件。

对搜索结果的每个分享：打印 shareurl、根层条目，再用 get_share_files 递归展开，
对比两者。用法：
    TITLE=尚公主 TOP=8 PYTHONPATH=src python3 tests/e2e/expand_check.py
"""
import asyncio
import os

import nonebot

nonebot.init()

from nonebot_plugin_quark_autosave.client import QASClient  # noqa: E402
from nonebot_plugin_quark_autosave.model import TaskItem  # noqa: E402
from nonebot_plugin_quark_autosave.subscribe import VIDEO_EXTS  # noqa: E402

TITLE = os.environ.get("TITLE", "尚公主")
TOP = int(os.environ.get("TOP", "8"))


def _ext(n: str) -> str:
    return n.rsplit(".", 1)[-1].lower() if "." in n else ""


async def main():
    async with QASClient() as c:
        sug = await c.task_suggestions(TITLE)
        print(f"搜索结果 {len(sug)} 条")
        for i, item in enumerate(sug[:TOP], 1):
            url = str(item.get("shareurl") or "").split("#", 1)[0]
            name = str(item.get("taskname") or "")[:40]
            if not url:
                continue
            print(f"\n[{i}] {name}\n    {url}")
            try:
                detail = await c.get_share_detail(
                    TaskItem.simple_from_title("probe", url)
                )
            except Exception as exc:
                print(f"    根层失败: {str(exc)[:60]}")
                continue
            print(f"    根层 {len(detail.file_list)} 项")
            for f in detail.file_list[:5]:
                print(f"      dir={f.dir} name={f.file_name[:50]} fid={f.fid[:16]}")
            try:
                flat = await c.get_share_files(url)
            except Exception as exc:
                print(f"    递归失败: {str(exc)[:60]}")
                continue
            vids = [f for f in flat if _ext(f.file_name) in VIDEO_EXTS]
            print(f"    递归共 {len(flat)} 项，视频 {len(vids)} 个")
            for f in vids[:4]:
                print(f"      {f.file_name[:70]} {int((f.size or 0)/1024**3*100)/100}G")


if __name__ == "__main__":
    asyncio.run(main())
