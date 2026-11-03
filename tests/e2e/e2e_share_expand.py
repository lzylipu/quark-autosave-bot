"""验证 get_share_files 递归展开：真分享 → 真视频文件 → 真大小 → 真集数。"""
import asyncio
import os
import sys

os.environ["QAS_ENDPOINT"] = "http://127.0.0.1:5599"
os.environ["QAS_TOKEN"] = "231436838b70dc9a"
os.environ["DRIVER"] = "~httpx"
sys.path.insert(0, "/home/agent/.hermes/workspace/quark-autosave-bot/src")

import nonebot

nonebot.init()

from nonebot_plugin_quark_autosave.client import QASClient
from nonebot_plugin_quark_autosave import subscribe as sub

KW = ["庆余年", "狂飙", "三体", "漫长的季节", "甄嬛传", "隐秘的角落"]


async def main():
    async with QASClient() as c:
        sug = []
        for kw in KW:
            sug = await c.task_suggestions(kw)
            if sug:
                print(f"搜索「{kw}」→ {len(sug)} 条")
                break
            await asyncio.sleep(2)
        if not sug:
            print("!! 搜索源无结果")
            return 1

        hit = 0
        for s in sug[:5]:
            url = str(s.get("shareurl") or "")
            if not url:
                continue
            try:
                files = await c.get_share_files(url)
            except Exception as exc:
                print(f"  展开失败: {str(exc)[:90]}")
                continue
            names = sub.video_names_from_share(files)
            if not names:
                print(f"  [{(s.get('taskname') or '')[:20]}] {len(files)} 文件, 无视频")
                continue
            hit += 1
            eps = sorted(sub.episodes_of(names))
            sizes = sorted(round(f.size / sub.GB, 2) for f in files
                           if f.file_name.rsplit(".", 1)[-1].lower() in sub.VIDEO_EXTS)
            print(f"  [{(s.get('taskname') or '')[:20]}] {len(files)} 文件 / {len(names)} 视频")
            print(f"     集数 {eps[:10]}{'...' if len(eps) > 10 else ''}  大小(GB) {sizes[:5]}")
            print(f"     例: {names[0]}")
        print(f"\n真正解析出视频的分享: {hit}/{min(5, len(sug))}")
        return 0 if hit else 1


sys.exit(asyncio.run(main()))
