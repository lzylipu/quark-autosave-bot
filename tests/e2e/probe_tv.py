"""真机验收 1：电视剧资源搜索 + 分享结构 + 订阅选源决策（不改任何东西）。

用法：
  SHOW=甄嬛传 python3 tests/e2e/probe_tv.py
"""
import asyncio
import os
import sys

import nonebot

nonebot.init()

from nonebot_plugin_quark_autosave import subscribe as sub  # noqa: E402
from nonebot_plugin_quark_autosave.client import QASClient  # noqa: E402

SHOW = os.environ.get("SHOW", "甄嬛传")
TOP = int(os.environ.get("TOP", "8"))


async def main():
    async with QASClient() as c:
        print(f"== 搜索「{SHOW}」")
        sug = await c.task_suggestions(SHOW)
        print(f"   共 {len(sug)} 条")
        for i, item in enumerate(sug[:TOP], 1):
            print(f"   [{i}] {str(item.get('taskname'))[:70]}")
            print(f"       {str(item.get('shareurl'))[:100]}")

        print(f"\n== 逐个探前 {TOP} 个分享")
        for i, item in enumerate(sug[:TOP], 1):
            url = str(item.get("shareurl", "")).split("#", 1)[0]
            try:
                files = await c.get_share_files(url)
            except Exception as exc:
                print(f"   [{i}] 打不开: {str(exc)[:70]}")
                continue
            videos = [f for f in files if not f.dir and f.file_name.rsplit(".", 1)[-1].lower() in sub.VIDEO_EXTS]
            sizes = sorted(round(f.size / 1024**3, 2) for f in videos)
            names = sub.video_names_from_share(files)
            keys = sub.episode_keys(names, 1)
            print(f"   [{i}] 视频 {len(videos)} 个，大小 {sizes[:3]}…{sizes[-2:] if sizes else ''}")
            print(f"       识别集数 {len(keys)} 个: {sub.fmt_episode_keys(keys)}")
            print(f"       样本: {[f.file_name for f in videos][:4]}")
            ok, note = sub.check_share(files, 0.1, 20)
            print(f"       大小筛选(0.1~20G): {'通过' if ok else '不通过'} — {note}")
    return 0


sys.exit(asyncio.run(main()))
