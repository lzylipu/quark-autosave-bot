"""删掉 probe 残留的 /自动/_bot自检复现（内含 2 个 mkv + 1 个子目录 + 自身目录）。"""
import asyncio

import nonebot

nonebot.init()

from nonebot_plugin_quark_autosave.client import QASClient

ROOT = "/自动/_bot自检复现"
FIDS = [
    "ba87983a3e2a45038d07e9f1eed8198b",  # E01.mkv
    "272ca9709e604fe7b51660975f91ed34",  # E02.mkv
    "8740d78b29774841a469ee3d3f9b4d2b",  # 内层目录
]


async def main():
    async with QASClient() as client:
        for fid in FIDS:
            print(fid, "->", await client.delete_file(fid))
        await asyncio.sleep(6)

        parent = client._check_response(
            await client._request_with_retry(
                "GET", "/get_savepath_detail", params={"path": "/自动"}
            )
        )
        fid = next((i.get("fid") for i in (parent or {}).get("list") or []
                    if i.get("file_name") == "_bot自检复现"), None)
        if fid:
            print("根目录", fid, "->", await client.delete_file(str(fid)))
        await asyncio.sleep(6)

        top = client._check_response(
            await client._request_with_retry(
                "GET", "/get_savepath_detail", params={"path": "/自动"}
            )
        )
        names = [i.get("file_name") for i in (top or {}).get("list") or []]
        bad = [n for n in names if n.startswith("_bot自检")]
        print("残留:", bad if bad else "无", f"| /自动 共 {len(names)} 项")


asyncio.run(main())
