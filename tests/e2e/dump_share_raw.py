"""诊断「分享详情返回 0 个视频」：把搜索结果里的原始 file_list 打出来。

用法：
    TITLE=尚公主 TOP=25 PYTHONPATH=src python3 tests/e2e/dump_share_raw.py
"""
import asyncio
import os

import nonebot

nonebot.init()

from nonebot_plugin_quark_autosave.client import QASClient  # noqa: E402
from nonebot_plugin_quark_autosave.model import TaskItem  # noqa: E402

TITLE = os.environ.get("TITLE", "尚公主")
TOP = int(os.environ.get("TOP", "25"))


async def main():
    async with QASClient() as c:
        sug = await c.task_suggestions(TITLE)
        print(f"搜索结果 {len(sug)} 条")
        for i, item in enumerate(sug[:TOP], 1):
            url = str(item.get("shareurl") or "").split("#", 1)[0]
            name = str(item.get("taskname") or "")[:50]
            if not url:
                continue
            try:
                detail = await c.get_share_detail(
                    TaskItem.simple_from_title("probe", url)
                )
            except Exception as exc:
                print(f"[{i:2d}] {name} ERR {str(exc)[:60]}")
                continue
            print(f"[{i:2d}] {name}  files={len(detail.file_list)}")
            for f in detail.file_list[:6]:
                print(
                    f"      dir={f.dir} size={int((f.size or 0) / 1024**3 * 100) / 100}G "
                    f"name={f.file_name[:70]}"
                )


if __name__ == "__main__":
    asyncio.run(main())
