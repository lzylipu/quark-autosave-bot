"""诊断「检查了 10 个分享，都不在 1.5~8.0G 区间」。

对指定片名：列出 /task_suggestions 返回的全部结果（不止前 10 条），逐个探分享详情，
打印每个分享的视频数、每集大小区间、是否落在 1.5~8.0G。

只读，不建任务、不转存、不删任何东西。

用法：
    QAS_ENDPOINT=... QAS_TOKEN=... PYTHONPATH=src python3 tests/e2e/probe_sub_sizes.py 走马上任 尚公主
"""
import asyncio
import os
import sys

import nonebot

nonebot.init()

from nonebot_plugin_quark_autosave.client import QASClient  # noqa: E402
from nonebot_plugin_quark_autosave.subscribe import (  # noqa: E402
    VIDEO_EXTS,
    episode_keys,
    video_names_from_share,
)

GB = 1024**3
MIN_GB = float(os.environ.get("MIN_GB", "1.5"))
MAX_GB = float(os.environ.get("MAX_GB", "8.0"))


def _sizes(files):
    """返回 [(name, gb)]，只统计视频文件。"""
    out = []
    for f in files:
        name = getattr(f, "file_name", "") or ""
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in VIDEO_EXTS:
            continue
        size = getattr(f, "size", 0) or 0
        out.append((name, size / GB))
    return out


async def probe(c: QASClient, title: str):
    print(f"\n===== 「{title}」")
    sug = await c.task_suggestions(title)
    print(f"搜索结果: {len(sug)} 条")
    ok_count = 0
    for i, item in enumerate(sug, 1):
        url = str(item.get("shareurl") or "").split("#", 1)[0]
        name = str(item.get("taskname") or "")[:60]
        mark = "  " if i <= 10 else ">>"  # >> = 前 10 之外，程序当前根本没看
        if not url:
            print(f"{mark}[{i:2d}] {name}  无链接")
            continue
        try:
            files = await c.get_share_files(url)
        except Exception as exc:
            print(f"{mark}[{i:2d}] {name}  打不开: {str(exc)[:50]}")
            continue
        vids = _sizes(files)
        if not vids:
            print(f"{mark}[{i:2d}] {name}  0 个视频")
            continue
        eps = sorted({s for _, s in vids})
        lo, hi = min(eps), max(eps)
        keys = episode_keys(video_names_from_share(files), 1)
        in_range = lo >= MIN_GB and hi <= MAX_GB
        ok_count += 1 if in_range else 0
        flag = "OK " if in_range else "-- "
        print(
            f"{mark}[{i:2d}] {flag}{name}  {len(vids)}视频/{len(keys)}集  "
            f"每集 {lo:.2f}~{hi:.2f}G"
        )
    print(f"--- 落在 {MIN_GB}~{MAX_GB}G 的分享: {ok_count} 个")


async def main():
    titles = sys.argv[1:] or ["走马上任"]
    async with QASClient() as c:
        for t in titles:
            try:
                await probe(c, t)
            except Exception as exc:
                print(f"「{t}」探测失败: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
