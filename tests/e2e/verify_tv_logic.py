"""真机验收：电视剧「甄嬛传」76 集资源的命名规则 + 订阅补缺逻辑（不转存、不建任务）。

验证点：
  1. 产品自己的 rename_rules(1) 能把 76 集全部改成 S01E01~S01E76，不重名、不漏
  2. 本地已有 E01~E05 时，订阅算出的「要补的集」正好是 E06~E76
  3. 本地已全 76 集时，判定「已经是最新」，不会重复下
  4. 大小区间筛选（1.5~8G）对这部剧是否通过
"""
import asyncio
import os
import re
import sys
from collections import Counter

import nonebot

nonebot.init()

from nonebot_plugin_quark_autosave import subscribe as sub  # noqa: E402
from nonebot_plugin_quark_autosave.client import QASClient  # noqa: E402

SHARE = os.environ.get("SHARE", "https://pan.quark.cn/s/910b31e32f38")
MIN_GB, MAX_GB = 1.5, 8.0
OK, FAIL = [], []


def check(name, cond, detail=""):
    (OK if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'} {name} {detail}", flush=True)


async def main():
    async with QASClient() as c:
        files = await c.get_share_files(SHARE)
        videos = [f for f in files if not f.dir and f.file_name.rsplit(".", 1)[-1].lower() in sub.VIDEO_EXTS]
        print(f"分享视频数: {len(videos)}")

        # ---- 1. 命名规则 ----
        pattern, replace = sub.rename_rules(1)
        mapped, unmatched = [], []
        for f in videos:
            if re.search(pattern, f.file_name):
                mapped.append(re.sub(pattern, replace, f.file_name))
            else:
                unmatched.append(f.file_name)

        dup = {k: v for k, v in Counter(mapped).items() if v > 1}
        print(f"匹配到 {len(mapped)} 个，未匹配 {len(unmatched)} 个")
        print("前 5 个映射:")
        for f in videos[:5]:
            print(f"   {f.file_name[:80]}\n     -> {re.sub(pattern, replace, f.file_name) if re.search(pattern, f.file_name) else '未匹配'}")
        print(f"重名: {dup}")
        check("76 集全部匹配到重命名规则", not unmatched, f"未匹配 {len(unmatched)} 个: {unmatched[:3]}")
        check("重命名后没有重名", not dup, str(list(dup.items())[:3]))

        want = {f"S01E{e:02d}.mp4" for e in range(1, 77)}
        got = set(mapped)
        check("命名结果正好是 S01E01~S01E76", got == want, f"缺 {sorted(want - got)[:5]} 多 {sorted(got - want)[:5]}")

        # ---- 2. 大小筛选 ----
        ok_size, note = sub.check_share(files, MIN_GB, MAX_GB)
        sizes = sorted(round(f.size / 1024**3, 2) for f in videos)
        print(f"每集大小 {sizes[0]}~{sizes[-1]}G")
        check(f"{MIN_GB}~{MAX_GB}G 区间筛选通过", ok_size, note)

        # ---- 3. 补缺：本地已有 E01~E05 ----
        have = {f"S01E{e:02d}.mp4" for e in range(1, 6)}
        local_keys = sub.episode_keys(have, 1)
        cand = sub.assess_share(SHARE, files, local_keys, MIN_GB, MAX_GB, 1)
        episodes = sorted(e for _, e in cand.new_episodes)
        print(f"本地已有 E01~E05 → 待补 {len(episodes)} 集: E{episodes[0]:02d}~E{episodes[-1]:02d}")
        check("待补正好 E06~E76", episodes == list(range(6, 77)), f"{len(episodes)} 集")

        # ---- 4. 已全 76 集 ----
        full = {f"S01E{e:02d}.mp4" for e in range(1, 77)}
        cand_full = sub.assess_share(SHARE, files, sub.episode_keys(full, 1), MIN_GB, MAX_GB, 1)
        check("本地已齐时不再补集", not cand_full.new_episodes, str(sorted(cand_full.new_episodes)[:5]))
        check("已齐时不会被选中建任务", sub.pick_best([cand_full]) is None)

    print(f"\n通过 {len(OK)} / 失败 {len(FAIL)}")
    if FAIL:
        print(f"失败项: {FAIL}")
    return 1 if FAIL else 0


sys.exit(asyncio.run(main()))
