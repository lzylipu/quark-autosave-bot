"""找一部集数少的电视剧，用于真跑定时订阅整链（避免一次转存上百 G）。

输出每个剧的前几个候选分享：集数 / 每集大小 / 是否在 1.5~8G 区间。
"""
import asyncio
import os
import sys

import nonebot

nonebot.init()

from nonebot_plugin_quark_autosave import subscribe as sub  # noqa: E402
from nonebot_plugin_quark_autosave.client import QASClient  # noqa: E402

SHOWS = [s for s in os.environ.get("SHOWS", "我的阿勒泰,黑镜,开端,隐秘的角落").split(",") if s]
TOP = int(os.environ.get("TOP", "4"))


async def main():
    async with QASClient() as c:
        for show in SHOWS:
            print(f"\n===== {show}")
            try:
                sug = await c.task_suggestions(show)
            except Exception as exc:
                print(f"   搜索失败: {exc}")
                continue
            print(f"   搜到 {len(sug)} 条")
            for i, item in enumerate(sug[:TOP], 1):
                url = str(item.get("shareurl", "")).split("#", 1)[0]
                title = str(item.get("taskname", ""))[:50]
                try:
                    files = await c.get_share_files(url)
                except Exception as exc:
                    print(f"   [{i}] {title} | 打不开: {str(exc)[:40]}")
                    continue
                videos = [f for f in files
                          if not f.dir and f.file_name.rsplit(".", 1)[-1].lower() in sub.VIDEO_EXTS]
                if not videos:
                    print(f"   [{i}] {title} | 无视频")
                    continue
                keys = sub.episode_keys(sub.video_names_from_share(files), 1)
                sizes = sorted(round(f.size / 1024**3, 2) for f in videos)
                ok, note = sub.check_share(files, 1.5, 8.0)
                print(f"   [{i}] {title} | {len(videos)} 个视频 / 识别 {len(keys)} 集 | "
                      f"{sizes[0]}~{sizes[-1]}G | {'大小OK' if ok else '大小NG'}")
                print(f"       {url}")
                print(f"       样本: {[f.file_name for f in videos][:2]}")
    return 0


sys.exit(asyncio.run(main()))
