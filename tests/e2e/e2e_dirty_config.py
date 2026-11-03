"""脏配置 / 字段保全验证：addition=null 不炸，删除不丢 calendar_info。"""
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
from nonebot_plugin_quark_autosave.model import TaskItem

OK, FAIL = [], []


def check(name, cond, detail=""):
    (OK if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'} {name} {detail}")


async def main():
    async with QASClient() as c:
        # 0. 清空历史遗留
        for t in await c.list_tasks():
            try:
                await c.delete_task(t)
            except Exception:
                pass
        check("清空起始状态", (await c.list_tasks()) == [])

        # 1. 造一个「WebUI 风格」的任务：带 calendar_info / source 等模型里没有的字段
        rich = {
            "taskname": "追剧任务-带日历",
            "shareurl": "https://pan.quark.cn/s/richcal",
            "savepath": "/自动/追剧",
            "pattern": "",
            "replace": "",
            "addition": {"aria2": {"enable": True}},
            "calendar_info": {"match": {"tmdb_id": 12345, "title": "某剧"}},
            "source": "webui",
            "task_plugins": {"plex": {"enable": True}},
        }
        await c._request_with_retry("POST", "/api/add_task", json=rich)
        # 2. 再造一个 addition 显式 null 的脏任务
        dirty = {
            "taskname": "脏任务-null",
            "shareurl": "https://pan.quark.cn/s/dirty",
            "savepath": "/自动/脏",
            "addition": None,
        }
        await c._request_with_retry("POST", "/api/add_task", json=dirty)
        # 3. 再来一个要删的正常任务
        victim = TaskItem(taskname="待删任务", shareurl="https://pan.quark.cn/s/victim",
                          savepath="/自动/待删", addition={})
        await c.add_task(victim)

        raw = (await c.get_data_raw())["tasklist"]
        check("三个任务都在", len(raw) == 3, str([t["taskname"] for t in raw]))

        # 4. 删 victim —— 此时配置里有 addition=null 的脏任务，旧实现会 500
        try:
            await c.delete_task(victim)
            check("脏任务在场时删除成功（不再 500）", True)
        except Exception as exc:
            check("脏任务在场时删除成功（不再 500）", False, str(exc)[:120])

        # 5. 关键：另外两个任务的字段必须原样保留
        raw = (await c.get_data_raw())["tasklist"]
        names = [t["taskname"] for t in raw]
        check("victim 已删", "待删任务" not in names, str(names))

        rich_after = next((t for t in raw if t["taskname"] == "追剧任务-带日历"), None)
        cal = (rich_after or {}).get("calendar_info") or {}
        # QASx 的 /update 会自动补 extracted 等字段，所以只校验关键值仍在
        check("calendar_info.tmdb_id 保留", (cal.get("match") or {}).get("tmdb_id") == 12345,
              str(cal.get("match")))
        check("source 保留", bool(rich_after) and rich_after.get("source") == "webui")
        check("task_plugins 保留", bool(rich_after) and rich_after.get("task_plugins") == {"plex": {"enable": True}})
        # addition 会被上游补全成完整默认配置，只要求 aria2.enable 仍在
        add = (rich_after or {}).get("addition") or {}
        check("addition.aria2.enable 保留", (add.get("aria2") or {}).get("enable") is True, str(add)[:100])

        dirty_after = next((t for t in raw if t["taskname"] == "脏任务-null"), None)
        check("脏任务 addition 已从 null 修成 dict", isinstance((dirty_after or {}).get("addition"), dict),
              str((dirty_after or {}).get("addition"))[:100])

        # 6. 删脏任务本身
        try:
            await c.delete_task(TaskItem(taskname="脏任务-null", shareurl="https://pan.quark.cn/s/dirty",
                                         savepath="/自动/脏"))
            check("删除脏任务成功", True)
        except Exception as exc:
            check("删除脏任务成功", False, str(exc)[:120])

        # 7. 收尾
        for t in await c.list_tasks():
            try:
                await c.delete_task(t)
            except Exception:
                pass
        check("最终清空", (await c.list_tasks()) == [])

    print(f"\n通过 {len(OK)} / 失败 {len(FAIL)}")
    return 1 if FAIL else 0


sys.exit(asyncio.run(main()))
