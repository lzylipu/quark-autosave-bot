"""打印单个分享递归展开后的全部文件（排查「只落了部分集数」）。

用法：
    SHARE=https://pan.quark.cn/s/xxxx PYTHONPATH=src python3 tests/e2e/dump_share_url.py
"""
import asyncio
import os

import nonebot

nonebot.init()

from nonebot_plugin_quark_autosave.client import QASClient  # noqa: E402
from nonebot_plugin_quark_autosave.model import TaskItem  # noqa: E402

SHARE = os.environ.get("SHARE", "")


async def main():
    async with QASClient() as c:
        task = TaskItem.simple_from_title("probe", SHARE)
        files = await c.get_share_files(task.shareurl)
        vids = [f for f in files if not f.dir and f.file_name.lower().endswith(
            (".mp4", ".mkv", ".avi", ".ts", ".mov", ".m4v", ".wmv"))]
        print(f"共 {len(files)} 项，视频 {len(vids)} 个")
        for f in vids:
            print(f"  {int((f.size or 0) / 1024**3 * 100) / 100:>6.2f}G  {f.file_name}")


if __name__ == "__main__":
    asyncio.run(main())
