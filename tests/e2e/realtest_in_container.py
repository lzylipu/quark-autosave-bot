"""真机全链路 v2：搜索 → 建任务(带 update_subdir) → 真转存 → 校验落地 → 删任务 → 清文件 → 基线核对。

只在 /自动/_bot自检 下操作，任务名带 _bot自检_ 前缀。
"""
import asyncio
import sys

import nonebot

nonebot.init()

from nonebot_plugin_quark_autosave.client import QASClient
from nonebot_plugin_quark_autosave.model import TaskItem
from nonebot_plugin_quark_autosave.result import parse_run_output
from nonebot_plugin_quark_autosave import subscribe as sub

# 每轮用独立目录：QASx 有「转存记录」数据库（file_id + savepath 命中就跳过），
# 用同一个目录重跑会直接打印「没有新的文件需要转存」，测不到真转存。
_RUN_TAG = __import__("datetime").datetime.now().strftime("%m%d%H%M")
SAVEPATH = f"/自动/_bot自检{_RUN_TAG}"
NAME = "_bot自检_转存"
OK, FAIL = [], []


def check(name, cond, detail=""):
    (OK if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'} {name} {detail}", flush=True)


async def main():
    async with QASClient() as c:
        base = [(t.get("taskname"), t.get("shareurl"))
                for t in (await c.get_data_raw()).get("tasklist") or []]
        print(f"基线任务 {len(base)} 个: {[b[0] for b in base]}\n", flush=True)

        # 1. 搜一个确定性强的片子
        sug = await c.task_suggestions("幻视")
        check("搜索有结果", len(sug) > 0, f"{len(sug)} 条")

        # 2. 挑最小的一个合格分享（少占网盘空间）
        best = None
        for s in sug[:10]:
            url = str(s.get("shareurl") or "")
            if not url:
                continue
            try:
                files = await c.get_share_files(url, max_depth=3, max_dirs=12)
            except Exception:
                continue
            videos = [f for f in files if not f.dir
                      and f.file_name.rsplit(".", 1)[-1].lower() in sub.VIDEO_EXTS]
            if not videos:
                continue
            total = sum(f.size for f in videos)
            print(f"  候选 [{(s.get('taskname') or '')[:22]}] "
                  f"{len(videos)} 视频 / {total/1024**3:.2f}GB", flush=True)
            if best is None or total < best[0]:
                best = (total, url, len(videos), len(files))
        if not best:
            print("!! 没找到可用分享")
            return 1
        total_gb, shareurl, n_video, n_all = best
        print(f"\n选中最小的：{total_gb/1024**3:.2f}GB / {n_video} 个视频\n{shareurl}\n", flush=True)

        # 3. 建任务（用 bot 自己的建任务口径：带 update_subdir）
        t = TaskItem.simple_from_title("_bot自检_转存", shareurl)
        t.taskname = NAME
        t.savepath = SAVEPATH
        print(f"任务字段 update_subdir={t.update_subdir!r} pattern={t.pattern!r} "
              f"runweek={t.runweek}\n", flush=True)
        await c.add_task(t)
        check("建任务成功", NAME in [x.taskname for x in await c.list_tasks()])
        mid = [(x.get("taskname"), x.get("shareurl"))
               for x in (await c.get_data_raw()).get("tasklist") or []]
        check("建任务没吞掉别人的任务", [p for p in base if p in mid] == base, f"{len(mid)} 个")

        # 4. 真转存
        print("转存中（可能要几分钟）…", flush=True)
        chunks = []
        try:
            async for chunk in c.run_script(t):
                chunks.append(chunk)
        except Exception as exc:
            chunks.append(f"[异常] {exc}")
        text = "\n".join(chunks)
        print("---- QAS 输出（尾部）----")
        print(text[-1200:])
        print("-------------------------", flush=True)

        res = parse_run_output(chunks)
        check("转存有明确结果", res.status in ("success", "partial", "failed"),
              f"status={res.status} error={res.error}")
        check("转存成功", res.status in ("success", "partial"), f"{len(res.files)} 个文件")

        # 5. 回读网盘目录（递归）
        landed = await c.list_savepath_files(SAVEPATH)
        names = [f.get("file_name") for f in landed]
        check("文件真的落到网盘", len(names) > 0,
              f"{len(names)} 个: {names[:3]}")

        # 6. 删任务（核心需求）
        try:
            await c.delete_task(t)
            left = [x.taskname for x in await c.list_tasks()]
            check("转存后任务已删除", NAME not in left)
        except Exception as exc:
            check("转存后任务已删除", False, str(exc)[:160])

        # 7. 删任务后等一会儿再看（防 QASx 内存态写回复活）
        await asyncio.sleep(8)
        again = [x.taskname for x in await c.list_tasks()]
        check("删完 8 秒没复活", NAME not in again, str(again))

        # 8. 清理测试文件（只删本次自检目录下的）
        removed = 0
        for f in landed:
            if not f.get("fid"):
                continue
            if await c.delete_file(str(f["fid"])):
                removed += 1
        # 删的是异步任务，且目录本身（转存时按分享结构建的）也要清掉
        left_files = landed
        for _ in range(10):
            await asyncio.sleep(3)
            left_files = await c.list_savepath_files(SAVEPATH)
            if not left_files:
                break
        check("自检文件已清理", len(left_files) == 0,
              f"删了 {removed}/{len(landed)} 个，剩 {len(left_files)} 个")
        # 空目录壳也清掉（只看顶层）
        top = await c._request_with_retry(
            "GET", "/get_savepath_detail", params={"path": SAVEPATH}
        )
        top_list = (c._check_response(top) or {}).get("list") or []
        for item in top_list:
            if item.get("dir") and item.get("fid"):
                await c.delete_file(str(item["fid"]))
        await asyncio.sleep(4)
        top = await c._request_with_retry(
            "GET", "/get_savepath_detail", params={"path": SAVEPATH}
        )
        top_list = (c._check_response(top) or {}).get("list") or []
        check("自检目录已清空", not top_list, f"剩 {[i.get('file_name') for i in top_list]}")

        # 9. 基线核对
        final = [(x.get("taskname"), x.get("shareurl"))
                 for x in (await c.get_data_raw()).get("tasklist") or []]
        check("最终任务与基线完全一致", final == base, f"{len(final)} vs {len(base)}")

    print(f"\n通过 {len(OK)} / 失败 {len(FAIL)}", flush=True)
    if FAIL:
        print("失败项:", FAIL, flush=True)
    return 1 if FAIL else 0


sys.exit(asyncio.run(main()))
