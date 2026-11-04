"""真机整链验收（会真的转存）：订阅选源 → 建任务 → 转存 → 删任务 → 清文件。

用 SIMPLE_SAVE_ROOT=_bot自检 把落盘隔离到 /_bot自检/<剧名>，跑完删掉，
任务列表与基线逐项比对。挑「集数少」的剧（法警小队 / 幻视任务）以免一次下几十 G。

用法：
    SIMPLE_SAVE_ROOT=_bot自检 PYTHONPATH=src python3 tests/e2e/verify_sub_real.py 法警小队
"""
import asyncio
import sys

import nonebot

nonebot.init()

from nonebot_plugin_quark_autosave import _run_one_subscription  # noqa: E402
from nonebot_plugin_quark_autosave.client import QASClient  # noqa: E402
from nonebot_plugin_quark_autosave.model import sanitize_title  # noqa: E402
from nonebot_plugin_quark_autosave.config import plugin_config  # noqa: E402
from nonebot_plugin_quark_autosave.subscribe import split_season  # noqa: E402

OK, FAIL = [], []


def check(name, cond, detail=""):
    (OK if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'} {name} {detail}", flush=True)


async def main():
    titles = sys.argv[1:] or ["法警小队"]
    root = plugin_config.simple_save_root
    print(f"落盘根目录: /{root}", flush=True)
    async with QASClient() as c:
        base = await c.list_tasks()
        base_names = sorted(t.taskname for t in base)
        print(f"基线任务 {len(base)} 个", flush=True)

        for title in titles:
            savepath = f"/{root}/{sanitize_title(split_season(title)[0])}"
            print(f"\n===== 订阅「{title}」 → {savepath}", flush=True)
            report = await _run_one_subscription(c, title)
            print(report, flush=True)

            files = await c.list_savepath_files(savepath)
            vids = [f for f in files if not f.get("dir")]
            check(f"「{title}」真的落了文件", len(vids) > 0, f"{len(vids)} 个")
            for f in vids[:6]:
                print(
                    f"    {f.get('file_name_saved') or f.get('file_name')}  "
                    f"{round((f.get('size') or 0) / 1024**3, 2)}G",
                    flush=True,
                )

            now = await c.list_tasks()
            leaked = [t.taskname for t in now if t.taskname == sanitize_title(split_season(title)[0])]
            check(f"「{title}」任务已删", not leaked, str(leaked))

            # 清理本轮回执目录里的文件
            removed = 0
            for f in vids:
                if await c.delete_file(str(f.get("fid"))):
                    removed += 1
            print(f"    清理 {removed}/{len(vids)} 个文件", flush=True)
            await asyncio.sleep(3)
            left = await c.list_savepath_files(savepath)
            check(f"「{title}」临时文件已清空", not [x for x in left if not x.get("dir")])

        await asyncio.sleep(60)
        final = await c.list_tasks()
        final_names = sorted(t.taskname for t in final)
        check("60 秒后任务列表与基线一致", final_names == base_names,
              f"{len(final_names)} vs {len(base_names)}")

    print(f"\n通过 {len(OK)} / 失败 {len(FAIL)}")
    if FAIL:
        for n in FAIL:
            print(f"  FAIL: {n}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
