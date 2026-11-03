"""清理自检残留目录：只删空的 _bot自检* 目录和本次自动化测试建的「舌尖上的中国」空目录。"""
import asyncio

import nonebot

nonebot.init()

from nonebot_plugin_quark_autosave.client import QASClient

TARGETS = [
    "/自动/舌尖上的中国",
    "/自动/_bot自检",
    "/自动/_bot自检复现",
    "/自动/_bot自检11031603",
    "/自动/_bot自检11031557",
]


async def main():
    async with QASClient() as client:
        for path in TARGETS:
            detail = client._check_response(
                await client._request_with_retry(
                    "GET", "/get_savepath_detail", params={"path": path}
                )
            )
            items = (detail or {}).get("list") or []
            if items:
                print(f"跳过 {path}：非空 {len(items)} 项")
                continue
            # 取父目录里该目录自身的 fid
            parent, _, name = path.rpartition("/")
            pd = client._check_response(
                await client._request_with_retry(
                    "GET", "/get_savepath_detail", params={"path": parent}
                )
            )
            fid = next((i.get("fid") for i in (pd or {}).get("list") or []
                        if i.get("file_name") == name and i.get("dir")), None)
            if not fid:
                print(f"跳过 {path}：找不到目录 fid")
                continue
            ok = await client.delete_file(str(fid))
            print(f"{'已删除' if ok else '删除失败'} {path} (fid={fid})")

        await asyncio.sleep(5)
        for path in TARGETS:
            d = client._check_response(
                await client._request_with_retry(
                    "GET", "/get_savepath_detail", params={"path": path}
                )
            )
            exists = bool((d or {}).get("paths") or d.get("success"))
            print(f"复查 {path}: {'仍存在' if exists else '已不存在'}")

        tasks = (await client.get_data_raw()).get("tasklist") or []
        print("任务数:", len(tasks), [t.get("taskname") for t in tasks])


asyncio.run(main())
