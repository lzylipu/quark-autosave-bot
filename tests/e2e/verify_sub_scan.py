"""真机验收：订阅「扫全部搜索结果 + 选源 + 报告」逻辑（只读，不建任务、不转存）。

用真 QASx 的搜索和分享详情，只把「写」的动作（建任务/执行/删任务）换成本地记录，
所以不会往网盘里下任何东西。

用法：
    PYTHONPATH=src python3 tests/e2e/verify_sub_scan.py 走马上任 尚公主
"""
import asyncio
import sys

import nonebot

nonebot.init()

from nonebot_plugin_quark_autosave import plugin_config  # noqa: E402
from nonebot_plugin_quark_autosave import _run_one_subscription  # noqa: E402
from nonebot_plugin_quark_autosave.client import QASClient  # noqa: E402

OK, FAIL = [], []


def check(name, cond, detail=""):
    (OK if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'} {name} {detail}", flush=True)


class ReadOnlyClient:
    """真读（搜索/分享详情），假写（建任务/执行/删任务）。"""

    def __init__(self, real: QASClient, local=None):
        self.real = real
        self.local = local  # None = 真读网盘保存目录（要验「本地已有几集」必须真读）
        self.added = []
        self.deleted = []

    async def task_suggestions(self, query):
        return await self.real.task_suggestions(query)

    async def get_share_files(self, shareurl, max_depth=3, max_dirs=40):
        return await self.real.get_share_files(shareurl, max_depth, max_dirs)

    async def list_savepath_files(self, savepath):
        if self.local is not None:
            return self.local
        return await self.real.list_savepath_files(savepath)

    async def add_task(self, task):
        self.added.append(task)
        return task

    async def run_script(self, task):
        yield "✅ 新增文件（只读验收，未真转存）"

    async def delete_task(self, task):
        self.deleted.append(task)
        return task.taskname


async def main():
    titles = sys.argv[1:] or ["走马上任"]
    print(
        f"上限 sub_max_candidates={plugin_config.sub_max_candidates}"
        f"（0=全部） 合格即停 sub_max_ok_candidates={plugin_config.sub_max_ok_candidates}"
        f" 区间 {plugin_config.sub_min_size_gb}~{plugin_config.sub_max_size_gb}G"
        f" 退档下限 {plugin_config.sub_fallback_min_size_gb}G",
        flush=True,
    )
    async with QASClient() as real:
        for title in titles:
            print(f"\n===== 订阅「{title}」", flush=True)
            client = ReadOnlyClient(real)
            report = await _run_one_subscription(client, title)
            print(report, flush=True)
            if client.added:
                task = client.added[0]
                print(
                    f"  -> 选中 {task.shareurl}\n"
                    f"     pattern={task.pattern}\n"
                    f"     replace={task.replace}\n"
                    f"     已删任务={len(client.deleted)}",
                    flush=True,
                )
                check(f"「{title}」选中了可下资源", True)
                check(f"「{title}」任务被清理", len(client.deleted) == 1)
            else:
                check(f"「{title}」选中了可下资源", False, report.splitlines()[0])

    print(f"\n通过 {len(OK)} / 失败 {len(FAIL)}")
    if FAIL:
        for name in FAIL:
            print(f"  FAIL: {name}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
