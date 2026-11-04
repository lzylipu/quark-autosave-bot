"""追剧订阅：片名列表 + 每天定时搜索 + 大小筛选 + 补缺转存。

每天 SUB_CHECK_TIME 时间点，对订阅里的每部剧：
1. 扫网盘保存目录，算出本地已有哪几集（E05 / S01E05 / 第05集 / 05.mp4 都认）；
2. 调 QASx 的 /task_suggestions 搜片名（CloudSaver/PanSou 聚合，同 WebUI）；
3. 逐个候选分享取文件列表：先按每集大小区间筛，再算能补几集；
4. 选「能补最多集」的那个分享，建任务时带上统一重命名规则（S01E05）；
5. 执行转存 → 删除任务 → 结果回报到 Telegram。

链接隔天失效也没关系：任务每轮都用当天搜到的新链接重建，
已下载的集数由 QASx 扫描保存目录去重（大小 + 扩展名 + 时间），不会重复下。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from nonebot import logger

from .config import plugin_config

# 视频扩展名：命中才算「剧集文件」，海报/nfo 之类的杂项不参与大小与集数判定
VIDEO_EXTS = frozenset({
    "mp4", "mkv", "avi", "rmvb", "rm", "wmv", "flv", "mov",
    "m2ts", "ts", "iso", "mpg", "mpeg", "webm",
})

GB = 1024**3

# QASx 内置 $TV 规则的正则：第 1 组季、第 2 组集数、第 3 组扩展名。
# 区别只在替换模板——QASx 原版是 "\1E\2.\3"（原文件名没有 S01 就补不上），
# 我们固定写成 "S01E\2.\3"，让落盘文件统一带季数。
#
# 相比原版的两处收紧（都有测试兜底）：
# - 分隔符加上 "["，能认 [05].mkv 这种写法；
# - 集数后面禁止紧跟字母数字，否则 4K / 1080p / 2160p 里的数字会被当成集数，
#   把第 12 集重命名成 E4、E160 这种错名。
TV_PATTERN = r".*?([Ss]\d{1,2})?(?:[第EePpXx\.\-\_\(\[]|\s){1,2}(\d{1,3})(?![\dA-Za-z]).*?\.(mp4|mkv)"

# 文件名里已经带 season 的分享（合集里常见）用这个：强制捕获季数。
# TV_PATTERN 的季数捕获是可选的，遇到「…2020.S03.EP07…」会先匹配到
# 不带季的分支，结果只剩 E07——所以合集必须换这条。
SEASON_TV_PATTERN = (
    r".*?[Ss](\d{1,2})\s*[\.\-_ ]*\s*(?:[Ee][Pp]?)?\s*(\d{1,3})(?![\dA-Za-z]).*?\.(mp4|mkv)"
)

_CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# 订阅存储
# ---------------------------------------------------------------------------


class SubscriptionStore:
    """订阅列表，JSON 文件持久化（文件里以 __ 开头的键是内部状态）。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            logger.error(f"订阅文件损坏，忽略: {exc}")
            return {}

    def save(self, data: dict[str, dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def add(self, name: str) -> tuple[bool, str]:
        name = name.strip()
        if not name:
            return False, "用法: AD 片名"
        data = self.load()
        if name in data:
            return False, f"已经订阅过「{name}」"
        data[name] = {"created_at": _now_str(), "last_result": ""}
        self.save(data)
        return True, f"✅ 已订阅「{name}」，每天 {plugin_config.sub_check_time} 自动搜索转存"

    def remove(self, name: str) -> tuple[bool, str]:
        name = name.strip()
        data = self.load()
        if not name:
            names = self.list_all()
            return False, "用法: DL 片名（当前订阅: " + ("、".join(names) if names else "空") + "）"
        if name not in data:
            return False, f"没有订阅过「{name}」"
        data.pop(name)
        self.save(data)
        return True, f"🗑 已取消订阅「{name}」"

    def list_all(self) -> list[str]:
        return [k for k in self.load() if not k.startswith("__")]

    def record_result(self, name: str, result: str) -> None:
        data = self.load()
        if name in data:
            data[name]["last_result"] = f"{_now_str()} {result}"
            self.save(data)

    def get_chat_id(self) -> str | None:
        return self.load().get("__chat_id__", {}).get("id")

    def set_chat_id(self, chat_id: str) -> None:
        data = self.load()
        if data.get("__chat_id__", {}).get("id") != chat_id:
            data["__chat_id__"] = {"id": chat_id}
            self.save(data)


# ---------------------------------------------------------------------------
# 片名 / 季数
# ---------------------------------------------------------------------------


def split_season(taskname: str) -> tuple[str, int]:
    """从订阅名里拆出「片名 + 季数」。

    「甄嬛传」→ ("甄嬛传", 1)、「庆余年 S02」→ ("庆余年", 2)、
    「琅琊榜 第二季」→ ("琅琊榜", 2)。搜索和建任务都用片名，季数只影响命名。
    """
    name = taskname.strip()
    match = re.search(r"[\s\.\-_]*[Ss](\d{1,2})\s*$", name)
    if match:
        return name[: match.start()].strip() or name, int(match.group(1))
    match = re.search(r"[\s\.\-_]*(?:第\s*([0-9一二三四五六七八九十]+)\s*季|Season\s*(\d+))\s*$", name, re.IGNORECASE)
    if match:
        raw = match.group(1) or match.group(2)
        season = int(raw) if raw.isdigit() else _CN_NUM.get(raw, 1)
        return name[: match.start()].strip() or name, season
    return name, 1


def rename_rules(season: int, keep_season_in_name: bool = False) -> tuple[str, str]:
    """建任务时随任务下发的重命名规则：统一成 S01E05 这种格式。

    `keep_season_in_name=True` 用于**文件名里已经带季数**的分享
    （「航拍中国第三季…S03.EP07…mp4」这种）：此时用捕获到的季数，
    而不是订阅名里的季数。否则一个「1-4 季合集」里 S03/S04 的集
    会被统一写成 S01Exx，互相撞名，本地「已有哪几集」也会算错。
    """
    if keep_season_in_name:
        return SEASON_TV_PATTERN, r"S\1E\2.\3"
    return TV_PATTERN, f"S{season:02d}E\\2.\\3"


# ---------------------------------------------------------------------------
# 集数识别
# ---------------------------------------------------------------------------


def parse_episode(filename: str) -> int | None:
    """从文件名里解析集数——带不带 S01 都认。

    认：S01E05 / E05 / EP05 / 第05集 / 「甄嬛传.05.mp4」/「[05]」
    不认：年份（2015）当成集数
    """
    stem = filename.rsplit(".", 1)[-2] if filename.count(".") >= 1 else filename
    for pattern in (
        r"(?:e|ep|episode)\s*0*(\d{1,4})(?!\d)",
        r"第\s*0*(\d{1,4})\s*[集话話期]",
        r"[\[\s_\-.]0*(\d{1,4})(?=[\]\s_\-.]|$)",
        # 整个名字就是集数（"05.mkv"、"03.mp4"）
        r"^0*(\d{1,4})(?=[\s_\-.]|$)",
    ):
        for match in re.finditer(pattern, stem, re.IGNORECASE):
            raw = match.group(1)
            num = int(raw)
            if len(raw) == 4 and 1900 < num < 2100:
                continue  # 年份不是集数
            return num
    return None


def video_names_from_share(files: Iterable[Any]) -> list[str]:
    """分享文件列表里的视频文件名（排除目录和杂项）。"""
    return [
        f.file_name
        for f in files
        if not getattr(f, "dir", False)
        and f.file_name.rsplit(".", 1)[-1].lower() in VIDEO_EXTS
    ]


def video_names_from_dir(files: Iterable[dict]) -> list[str]:
    """保存目录里的视频文件名（QASx /get_savepath_detail 返回的原始 dict）。"""
    return [
        str(f.get("file_name", ""))
        for f in files
        if not f.get("dir", False)
        and str(f.get("file_name", "")).rsplit(".", 1)[-1].lower() in VIDEO_EXTS
    ]


def parse_season(filename: str) -> int | None:
    """文件名里带的季数：S03 / s3 / 第三季 / Season 3。没有就返回 None。"""
    stem = filename.rsplit(".", 1)[0] if filename.count(".") >= 1 else filename
    match = re.search(r"[Ss](\d{1,2})(?!\d)", stem)
    if match:
        return int(match.group(1))
    match = re.search(r"第\s*([0-9一二三四五六七八九十]+)\s*季|Season\s*(\d{1,2})", stem, re.IGNORECASE)
    if match:
        raw = match.group(1) or match.group(2)
        return int(raw) if raw.isdigit() else _CN_NUM.get(raw, 1)
    return None


def episodes_of(names: Iterable[str]) -> set[int]:
    return {ep for name in names if (ep := parse_episode(name)) is not None}


def episode_keys(names: Iterable[str], default_season: int = 1) -> set[tuple[int, int]]:
    """集数按「(季, 集)」记，避免合集里 S03E01 被当成 S01E01。

    文件名带季数就用文件名的，不带就用 default_season（订阅名里的季，
    通常是 1）。
    """
    keys: set[tuple[int, int]] = set()
    for name in names:
        ep = parse_episode(name)
        if ep is None:
            continue
        keys.add((parse_season(name) or default_season, ep))
    return keys


def _as_keys(items: Iterable, default_season: int = 1) -> set[tuple[int, int]]:
    keys: set[tuple[int, int]] = set()
    for item in items:
        if isinstance(item, tuple):
            keys.add((int(item[0]), int(item[1])))
        else:
            keys.add((default_season, int(item)))
    return keys


def fmt_episodes(eps: Iterable[int], limit: int = 8) -> str:
    """[10, 11, 12] → "E10~E12"；零散时列前几个。"""
    ordered = sorted(set(eps))
    if not ordered:
        return "无"
    if len(ordered) == 1:
        return f"E{ordered[0]:02d}"
    if ordered == list(range(ordered[0], ordered[-1] + 1)):
        return f"E{ordered[0]:02d}~E{ordered[-1]:02d}"
    shown = "、".join(f"E{e:02d}" for e in ordered[:limit])
    return shown + ("…" if len(ordered) > limit else "")


def fmt_episode_keys(keys: Iterable[tuple[int, int]], limit: int = 8) -> str:
    """{(1,1),(1,2),(3,5)} → "S01E01~E02、S03E05"；单季时省略季前缀。"""
    keys = sorted(set(keys))
    if not keys:
        return "无"
    seasons = {s for s, _ in keys}
    parts = []
    for s in sorted(seasons):
        eps = [e for ss, e in keys if ss == s]
        prefix = "" if len(seasons) == 1 else f"S{s:02d}"
        parts.append(prefix + fmt_episodes(eps, limit))
    return "、".join(parts)


def episode_report(names: Iterable[str]) -> str:
    """集数概况：共几集、编号范围、有没有断档。"""
    names = list(names)
    episodes = episodes_of(names)
    if not episodes:
        return f"共 {len(names)} 个视频文件"
    lo, hi = min(episodes), max(episodes)
    missing = sorted(set(range(lo, hi + 1)) - episodes)
    gap = "" if not missing else f"，编号缺 {len(missing)} 集（如 E{missing[0]:02d}）"
    return f"共 {len(names)} 个文件，E{lo:02d}~E{hi:02d}{gap}"


# ---------------------------------------------------------------------------
# 分享筛选
# ---------------------------------------------------------------------------


@dataclass
class Candidate:
    """一个候选分享的评估结果。"""

    shareurl: str
    video_files: list = field(default_factory=list)
    # (季, 集) 对；合集里 S03E01 和 S01E01 是两集，不能混
    new_episodes: set = field(default_factory=set)
    size_ok: bool = False
    note: str = ""


def check_share(files, min_gb: float, max_gb: float) -> tuple[bool, str]:
    """大小筛选：分享里所有视频每集都在 [min, max] GB 区间内。"""
    videos = [f for f in files if not getattr(f, "dir", False)
              and f.file_name.rsplit(".", 1)[-1].lower() in VIDEO_EXTS]
    if not videos:
        return False, "分享里没有视频文件"
    lo_bytes, hi_bytes = min_gb * GB, max_gb * GB
    bad = [f for f in videos if not (lo_bytes <= getattr(f, "size", 0) <= hi_bytes)]
    if bad:
        sizes = sorted(round(getattr(f, "size", 0) / GB, 2) for f in bad)
        return False, f"{len(bad)}/{len(videos)} 个文件不在 {min_gb}~{max_gb}G 区间（如 {sizes[0]}G）"
    return True, f"全部 {len(videos)} 个视频都在 {min_gb}~{max_gb}G"


def assess_share(
    shareurl: str,
    files,
    local_eps,
    min_gb: float,
    max_gb: float,
    season: int = 1,
) -> Candidate:
    """评估一个分享：大小是否合格 + 能补多少新集（按「季-集」比）。"""
    size_ok, note = check_share(files, min_gb, max_gb)
    names = video_names_from_share(files)
    share_keys = episode_keys(names, season)
    new_eps = share_keys - _as_keys(local_eps, season)
    return Candidate(
        shareurl=shareurl,
        video_files=names,
        new_episodes=new_eps,
        size_ok=size_ok,
        note=note,
    )


def pick_best(candidates: Iterable[Candidate]) -> Candidate | None:
    """选「能补最多集」的合格分享；同分取先搜到的（盘搜按时间倒序）。"""
    usable = [c for c in candidates if c.size_ok and c.new_episodes]
    if not usable:
        return None
    return max(usable, key=lambda c: len(c.new_episodes))


def seconds_until(hhmm: str, now: datetime | None = None) -> float:
    """距离下一个 hhmm（本地时间）的秒数，最小 60 秒。"""
    now = now or datetime.now()
    try:
        hour, minute = (int(x) for x in hhmm.split(":")[:2])
        assert 0 <= hour < 24 and 0 <= minute < 60
    except (ValueError, IndexError, AssertionError):
        logger.warning(f"SUB_CHECK_TIME 配置无效: {hhmm}，回退 17:00")
        hour, minute = 17, 0
    run_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if run_at <= now:
        run_at += timedelta(days=1)
    return max((run_at - now).total_seconds(), 60.0)
