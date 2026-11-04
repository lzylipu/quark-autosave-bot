import asyncio
import nonebot

nonebot.init()

from nonebot_plugin_quark_autosave.client import QASClient

TEST_PATH = "/自动/舌尖上的中国"
TEST_TASK = "舌尖上的中国"


async def main():
    async with QASClient() as client:
        tasks = (await client.get_data_raw()).get("tasklist") or []
        matches = [item for item in tasks if item.get("taskname") == TEST_TASK]
        print(f"测试任务残留: {len(matches)}")

        detail = client._check_response(
            await client._request_with_retry(
                "GET", "/get_savepath_detail", params={"path": TEST_PATH}
            )
        )
        items = (detail or {}).get("list") or []
        print("清理前顶层项目:", [(item.get("file_name"), item.get("fid")) for item in items])

        deleted = 0
        for item in items:
            fid = item.get("fid")
            if fid and await client.delete_file(str(fid)):
                deleted += 1
                print("已提交删除:", item.get("file_name"))

        for attempt in range(20):
            await asyncio.sleep(3)
            detail = client._check_response(
                await client._request_with_retry(
                    "GET", "/get_savepath_detail", params={"path": TEST_PATH}
                )
            )
            remaining = (detail or {}).get("list") or []
            if not remaining:
                break
            print(f"等待异步删除 {attempt + 1}/20，剩余 {len(remaining)} 项")

        final_tasks = (await client.get_data_raw()).get("tasklist") or []
        final_matches = [item for item in final_tasks if item.get("taskname") == TEST_TASK]
        print(f"已提交删除: {deleted}")
        print(f"清理后项目数: {len(remaining)}")
        print(f"清理后测试任务数: {len(final_matches)}")
        print(f"最终 QAS 任务数: {len(final_tasks)}")
        print("最终任务:", [item.get("taskname") for item in final_tasks])

        return 0 if not remaining and not final_matches and len(final_tasks) == 9 else 1


raise SystemExit(asyncio.run(main()))
