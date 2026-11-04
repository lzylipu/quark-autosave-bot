"""完整订阅流程实跑：真插件函数 _run_one_subscription + 真 QASx 实例。"""
import asyncio
import os
import sys

os.environ.setdefault("QAS_ENDPOINT", "http://127.0.0.1:5599")
os.environ.setdefault("QAS_TOKEN", "231436838b70dc9a")
os.environ.setdefault("DRIVER", "~httpx")
os.environ.setdefault("QAS_RUN_TIMEOUT", "60")
os.environ.setdefault("SUB_MIN_SIZE_GB", "0.05")
os.environ.setdefault("SUB_MAX_SIZE_GB", "8.0")
os.environ.setdefault("SUB_MAX_CANDIDATES", "6")
os.environ.setdefault("SIMPLE_SAVE_ROOT", "自动")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2] / "src"))

import nonebot

nonebot.init()

import nonebot_plugin_quark_autosave as plugin
from nonebot_plugin_quark_autosave.client import QASClient

NAME = sys.argv[1] if len(sys.argv) > 1 else "狂飙"


async def main():
    async with QASClient() as c:
        print(f"=== 跑订阅: {NAME} ===")
        report = await plugin._run_one_subscription(c, NAME)
        print("---- Telegram 报告 ----")
        print(report)
        print("-----------------------")

        tasks = await c.list_tasks()
        names = [t.taskname for t in tasks]
        print(f"\nQASx 任务列表: {names}")
        leftover = [n for n in names if n in (NAME, "狂飙", "三体", "庆余年")]
        print("残留任务:", leftover if leftover else "无（已清理干净）")
        return 0 if not leftover else 1


sys.exit(asyncio.run(main()))
