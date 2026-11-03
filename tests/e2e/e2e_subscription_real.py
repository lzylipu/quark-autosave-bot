"""用真 QASx 搜到的真分享链接，跑通订阅完整链路。"""
import asyncio
import json
import os
import sys

os.environ["QAS_ENDPOINT"] = "http://127.0.0.1:5599"
os.environ["QAS_TOKEN"] = "231436838b70dc9a"
os.environ["DRIVER"] = "~httpx"
os.environ["SUB_MIN_SIZE_GB"] = "0.05"
os.environ["SUB_MAX_SIZE_GB"] = "8.0"

sys.path.insert(0, "/home/agent/.hermes/workspace/quark-autosave-bot/src")

import nonebot

nonebot.init()

from nonebot_plugin_quark_autosave.client import QASClient
from nonebot_plugin_quark_autosave.model import TaskItem
from nonebot_plugin_quark_autosave import subscribe as sub

KEYWORDS = ["庆余年", "三体", "狂飙", "漫长的季节", "甄嬛传", "琅琊榜"]


async def main():
    async with QASClient() as c:
        sug = []
        for kw in KEYWORDS:
            sug = await c.task_suggestions(kw)
            print(f"搜索「{kw}」→ {len(sug)} 条")
            if sug:
                break
            await asyncio.sleep(2)

        if not sug:
            print("!! 所有关键词都没结果（公开搜索源抽风），无法继续")
            return 1

        for s in sug[:3]:
            print("  -", (s.get("taskname") or "")[:30], "|", s.get("source"), "|", s.get("publish_date"))
        open("real_suggestions_sample.json", "w").write(
            json.dumps(sug[:5], ensure_ascii=False, indent=2)
        )

        # 真实探测分享详情 —— 这一步用 Quark("",0)，不需要登录 cookie
        for s in sug[:4]:
            url = str(s.get("shareurl") or "")
            if not url:
                continue
            try:
                detail = await c.get_share_detail(TaskItem.simple_from_title("probe", url))
            except Exception as exc:
                print(f"  探详情失败 {url}: {str(exc)[:90]}")
                continue
            files = detail.file_list
            if files:
                f0 = files[0]
                print(f"  文件字段: {sorted(f0.model_dump().keys())}")
            names = sub.video_names_from_share(files)
            eps = sorted(sub.episodes_of(names))
            cand = sub.assess_share(url, files, set(), 0.05, 8.0)
            sizes = [round(getattr(f, "size", 0) / sub.GB, 2) for f in files][:5]
            print(f"  分享[{(s.get('taskname') or '')[:16]}]: {len(files)} 文件, "
                  f"视频 {len(names)}, 集数 {eps[:6]}, 前几个大小(GB) {sizes}")
            print(f"     → 大小合格={cand.size_ok} 可补集数={len(cand.new_episodes)} 备注={cand.note}")
    return 0


sys.exit(asyncio.run(main()))
