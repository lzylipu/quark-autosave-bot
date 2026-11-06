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
import os
import re
import shutil
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

# 正则里用的扩展名分支（和 VIDEO_EXTS 同一份，别各写一套）。
# 原来只写 mp4|mkv，分享里给 avi/ts/rmvb 的整集会被 pattern 挡掉——pattern 同时是
# QASx 的筛选条件，匹配不上就不转存，等于「这个格式的集永远补不上」。
# (?i:...) 让 .MKV/.MP4 这种大写后缀也认——QASx 是 re.search(pattern, name)，没带 flags
EXT_GROUP = "((?i:" + "|".join(sorted(VIDEO_EXTS)) + "))"

# QASx 内置 $TV 规则的正则：第 1 组季、第 2 组集数、第 3 组扩展名。
# 区别只在替换模板——QASx 原版是 "\1E\2.\3"（原文件名没有 S01 就补不上），
# 我们固定写成 "S01E\2.\3"，让落盘文件统一带季数。
#
# 相比原版的三处收紧/放宽（都有测试兜底）：
# - 分隔符加上 "["，能认 [05].mkv 这种写法；
# - 集数后面禁止紧跟字母数字，否则 4K / 1080p / 2160p 里的数字会被当成集数，
#   把第 12 集重命名成 E4、E160 这种错名；
# - 允许「整个文件名就是集数」（01.mkv / 05.mp4）：原版要求集数前必须有分隔符，
#   这类分享一个文件都匹配不上 → QASx 判「没有新文件」→ 任务成功但落 0 个文件
#   （真机：我的阿勒泰 8 集全是 01.mkv~08.mkv）。
TV_PATTERN = (
    r"(?:.*?([Ss]\d{1,2})?(?:[第EePpXx\.\-_\\(\[]|\s){1,2}|^)"
    r"(\d{1,3})(?![\dA-Za-z]).*?\." + EXT_GROUP
)

# 文件名里已经带 season 的分享（合集里常见）用这个：强制捕获季数。
# TV_PATTERN 的季数捕获是可选的，遇到「…2020.S03.EP07…」会先匹配到
# 不带季的分支，结果只剩 E07——所以合集必须换这条。
SEASON_TV_PATTERN = (
    r".*?[Ss](\d{1,2})\s*[\.\-_ ]*\s*(?:[Ee][Pp]?)?\s*(\d{1,3})(?![\dA-Za-z]).*?\."
    + EXT_GROUP
)

_CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

# 订阅名结尾的季数：S05 / 第二季 / Season 2。split_season 与 has_explicit_season 共用。
_SEASON_SUFFIX_RE = re.compile(
    r"[\s\.\-_]*(?:[Ss](\d{1,2})|第\s*([0-9一二三四五六七八九十]+)\s*季|[Ss]eason\s*(\d{1,2}))\s*$",
    re.IGNORECASE,
)


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# 订阅存储
# ---------------------------------------------------------------------------


class SubscriptionStore:
    """订阅列表，JSON 文件持久化（文件里以 __ 开头的键是内部状态）。

    写盘是「临时文件 + os.replace」的原子替换，替换前把上一份留成 .bak；
    读的时候主文件坏了/丢了就退回 .bak。订阅是用户手敲进来的，丢一次就得重敲，
    不能因为一次断电或半截写入全没。
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)

    @property
    def backup_path(self) -> Path:
        return self.path.with_suffix(self.path.suffix + ".bak")

    def load(self) -> dict[str, dict]:
        for candidate in (self.path, self.backup_path):
            if not candidate.exists():
                continue
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.error(f"订阅文件 {candidate} 读不出来: {exc}")
                continue
            if not isinstance(data, dict):
                continue
            if candidate is not self.path:
                logger.warning(f"订阅主文件损坏，已从备份 {candidate.name} 恢复")
            return data
        return {}

    def save(self, data: dict[str, dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if self.path.exists():
            try:
                shutil.copy2(self.path, self.backup_path)
            except OSError as exc:
                logger.warning(f"订阅备份没写成（不影响本次保存）: {exc}")
        os.replace(tmp, self.path)

    def ensure_ready(self) -> tuple[bool, str]:
        """启动时把订阅文件先建出来，并确认这个目录真能写。

        空目录不等于坏：订阅文件是「第一次写的时候才创建」的，所以光挂卷不落文件
        是正常的。但目录属主不对 / 只读挂载时，用户要等到某天发 AD 才发现存不上，
        这里提前把 {} 写一遍，写不进去当场报出来。
        """
        if self.path.exists():
            try:
                json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                pass  # 坏了也没关系，load() 会回退到 .bak
            if not os.access(self.path, os.W_OK):
                return False, _save_failed_msg(self.path)
            return True, f"订阅文件已存在: {self.path}"
        if not self._save_or_explain({}):
            return False, _save_failed_msg(self.path)
        return True, f"订阅文件已创建: {self.path}"

    def _save_or_explain(self, data: dict[str, dict]) -> bool:
        """写盘失败时只记日志、返回 False，交给调用方给出人话提示。"""
        try:
            self.save(data)
        except OSError as exc:
            logger.error(f"订阅文件写不进去 {self.path}: {exc}")
            return False
        return True

    def add(self, name: str) -> tuple[bool, str]:
        name = name.strip()
        if not name:
            return False, "用法: AD 片名"
        data = self.load()
        if name in data:
            return False, f"已经订阅过「{name}」"
        data[name] = {"created_at": _now_str(), "last_result": ""}
        if not self._save_or_explain(data):
            return False, _save_failed_msg(self.path)
        return True, f"✅ 已订阅「{name}」，每天 {plugin_config.sub_check_time} 自动搜索转存"

    def remove(self, name: str) -> tuple[bool, str]:
        name = name.strip()
        data = self.load()
        if not name:
            names = self.list_all()
            return False, "用法: del 片名（当前订阅: " + ("、".join(names) if names else "空") + "）"
        if name not in data:
            return False, f"没有订阅过「{name}」"
        data.pop(name)
        self.save(data)
        return True, f"🗑 已取消订阅「{name}」"

    def list_all(self) -> list[str]:
        return [k for k in self.load() if not k.startswith("__")]

    def record_result(self, name: str, result: str) -> bool:
        data = self.load()
        if name not in data:
            return False
        data[name]["last_result"] = f"{_now_str()} {result}"
        return self._save_or_explain(data)

    def get_chat_id(self) -> str | None:
        """取报告发往的会话。

        手写的 subscriptions.json 常把 __chat_id__ 直接写成数字
        （`{"__chat_id__": 1516374642}`），以前这里直接 `.get("id")` 会抛
        AttributeError，把整轮定时任务的报告全吞掉。两种写法都认。
        """
        raw = self.load().get("__chat_id__")
        if isinstance(raw, dict):
            value = raw.get("id")
        else:
            value = raw
        return str(value) if value not in (None, "") else None

    def set_chat_id(self, chat_id: str) -> bool:
        """记住报告发往哪个会话；写不进去返回 False（不抛异常，别把 AD 命令搞崩）。"""
        data = self.load()
        if self.get_chat_id() == str(chat_id):
            return True
        data["__chat_id__"] = {"id": chat_id}
        return self._save_or_explain(data)


# ---------------------------------------------------------------------------
# 片名 / 季数
# ---------------------------------------------------------------------------


def split_season(taskname: str) -> tuple[str, int]:
    """从订阅名里拆出「片名 + 季数」。

    「甄嬛传」→ ("甄嬛传", 1)、「庆余年 S02」→ ("庆余年", 2)、
    「琅琊榜 第二季」→ ("琅琊榜", 2)。搜索和建任务都用片名，季数只影响命名。
    """
    name = taskname.strip()
    match = _SEASON_SUFFIX_RE.search(name)
    if match:
        raw = match.group(1) or match.group(2) or match.group(3)
        season = int(raw) if raw.isdigit() else _CN_NUM.get(raw, 1)
        return name[: match.start()].strip() or name, season
    return name, 1


def has_explicit_season(taskname: str) -> bool:
    """订阅名里有没有明确写季数（「黑镜 S05」「琅琊榜 第二季」）。

    写了的订阅只下这一季：否则「黑镜 S05」会搜到并选中第七季的分享，
    把 S07E01~E06 当成「S05 缺的集」全转存进来（真机复现过）。
    """
    return bool(_SEASON_SUFFIX_RE.search(taskname.strip()))


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


def season_or_bare_rules(season: int) -> tuple[str, str]:
    """本季的文件 + 没标季的文件都转，明确排除别的季。

    同一个分享里经常混着两种写法（真机幻视任务：`E01~E06` 裸集数 +
    `S01E07`），只认一种就会漏掉另外几集。这里在通用规则前面加一条
    「不许出现别的季」的前瞻，本季标记可有可无。
    """
    other = rf"[Ss]0?(?!0?{season}(?!\d))\d{{1,2}}(?!\d)"
    pattern, replace = rename_rules(season, keep_season_in_name=False)
    return rf"^(?!.*{other})" + pattern, replace


def episode_limited_rules(season: int, episodes: Iterable[int]) -> tuple[str, str]:
    """只转指定的那几集：本地已经有的集一个都不碰。

    为什么需要它：QASx 转存是「整份分享」——`pattern` 既是命名规则、又是筛选条件，
    把集数这一段收窄成白名单，QASx 就只转这几集。不收窄的话，一条 27 集的分享
    会把本地早就有的 21 集再转一遍，夸克遇到同名文件就存成 `S01E07.1.mkv`，
    目录里越攒越乱（真机就是 18 个文件落进来、只新增了 8 集）。

    组号与 TV_PATTERN 保持一致（1=季、2=集、3=扩展名），`replace` 不用改。
    """
    alt = "|".join(sorted({str(int(e)) for e in episodes}, key=lambda s: (-len(s), s)))
    other = rf"[Ss]0?(?!0?{season}(?!\d))\d{{1,2}}(?!\d)"
    pattern = (
        rf"^(?!.*{other})"
        rf"(?:.*?([Ss]\d{{1,2}})?(?:[第EePpXx\.\-_\(\[]|\s){{1,2}}|^)"
        # 0* 必须在捕获组里：`05.mkv` 要落成 S01E05.mkv，不能在替换时把零吃掉
        rf"(0*(?:{alt}))(?![\dA-Za-z]).*?\." + EXT_GROUP
    )
    return pattern, f"S{season:02d}E\\2.\\3"


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
            if num < 1:
                # 第 0 集是预告/花絮，不是正片。当成集数会让订阅一直追着一个补不到的
                # 「E00」跑（真机：分享里带 第00集 预告，每轮都选中它并落一次盘）。
                continue
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
    # 每集大小的中位数（GB）：区间外时用它判断「正片偏小」还是「枪版/花絮」
    median_gb: float = 0.0
    # 文件名里出现了订阅的片名（排除盘搜混进来的别的剧）
    title_hit: bool = False
    # 这条分享「本该有却没给」的集：本地已有 E01~E10、分享里只有 E12，
    # 那 E11 就是 missing —— 缺集的更新包不能选中，否则 E11 永久跳过
    missing: set = field(default_factory=set)
    # 同一集在分享里出现两次的文件（如 S01E07.mkv + 07.mkv）：QASx 按文件名查重时
    # 认不出它们是一集，会各落一份，落盘名也就统一不了。只做提示，不当不合格。
    dup_episodes: set = field(default_factory=set)
    # 这条候选对应分享里的哪一层目录（根目录是 "/"）。嵌套分享常把不同版本
    # 各放一个子目录，只有某个子目录里的内容是全的 —— 那就直接把任务指到那一层。
    path: str = "/"
    depth: int = 0
    # 视频是不是**直接躺在这层目录里**（而不是要靠 QASx 递归进子目录才拿得到）。
    # 只有 direct 的候选才能真的「只补缺集」：QASx 递归进子目录时，子目录里的
    # 查重是拿子目录自己的列表比的，本地已有的集会被整批再落一份。
    direct: bool = False


def video_median_gb(files) -> float:
    """视频文件每集大小的中位数（GB）。没有视频返回 0。

    用中位数而不是最小值：分享里常混一个预告片/花絮，取最小值会把整份判成枪版。
    """
    sizes = sorted(
        (getattr(f, "size", 0) or 0) / GB
        for f in files
        if not getattr(f, "dir", False)
        and f.file_name.rsplit(".", 1)[-1].lower() in VIDEO_EXTS
    )
    if not sizes:
        return 0.0
    mid = len(sizes) // 2
    if len(sizes) % 2:
        return sizes[mid]
    return (sizes[mid - 1] + sizes[mid]) / 2


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


def missing_episodes(share_keys, local_keys) -> set:
    """分享里「本该有却没给」的集。

    判定依据：从 E01 到分享里最大集，凡是本地没有的集，分享都得给。
    本地 E01~E10、分享只有 E12 → 缺 E11；本地少了 E06/E07 → 那两个也算缺。
    这样「只有第 12 集」的更新包不会被当成能补全的链接，会继续看下一条；
    本地被手动删掉的集也会优先挑全集分享补回来。
    """
    share_keys = set(share_keys)
    local_keys = set(local_keys)
    gap: set = set()
    for season in {s for s, _ in share_keys}:
        eps = {e for s, e in share_keys if s == season}
        gap |= {
            (season, e)
            for e in range(1, max(eps) + 1)
            if e not in eps and (season, e) not in local_keys
        }
    return gap


def duplicate_episodes(names, season: int = 1) -> set:
    """同一集在分享里出现了两次的集。

    真机：走马上任 的分享里既有 `07.mkv`（2.92G）又有 `S01E07.mkv`（0.97G），
    QASx 按文件名查重（忽略后缀）认不出它们是一集，各转一份 —— 落盘就是
    `S01E07.mkv` + `07.mkv`（改名撞名，第二份保留原名）。这里只统计出来提示用户。
    """
    seen: dict = {}
    for name in names:
        for key in episode_keys([name], season):
            seen[key] = seen.get(key, 0) + 1
    return {key for key, count in seen.items() if count > 1}


def assess_share(
    shareurl: str,
    files,
    local_eps,
    min_gb: float,
    max_gb: float,
    season: int = 1,
    title: str = "",
    share_title: str = "",
    path: str = "/",
    depth: int = 0,
    direct: bool = False,
) -> Candidate:
    """评估一个分享（或分享里某一层目录）：大小是否合格 + 能补多少新集。"""
    size_ok, note = check_share(files, min_gb, max_gb)
    names = video_names_from_share(files)
    share_keys = episode_keys(names, season)
    local_keys = _as_keys(local_eps, season)
    new_eps = share_keys - local_keys
    # 片名要对得上才算「这部剧」：盘搜会混进同档期别的剧，只按大小筛会下错内容
    # （真机：尚公主 选中过 7.85G 的「黄金时段 / Primetime」）。
    # 文件名常被改成 24.4K-S.mp4 这种，所以搜索结果的标题也算一次匹配。
    hit = bool(title) and (
        title in share_title or any(title in name for name in names)
    )
    return Candidate(
        shareurl=shareurl,
        video_files=names,
        new_episodes=new_eps,
        size_ok=size_ok,
        note=note,
        median_gb=video_median_gb(files),
        title_hit=hit,
        missing=missing_episodes(share_keys, local_keys),
        dup_episodes=duplicate_episodes(names, season),
        path=path,
        depth=depth,
        direct=direct,
    )


def pick_best(
    candidates: Iterable[Candidate], require_size_ok: bool = True
) -> Candidate | None:
    """选「能补最多集」的合格分享；同分取先搜到的（盘搜按时间倒序）。"""
    usable = [
        c
        for c in candidates
        if (c.size_ok or not require_size_ok) and c.new_episodes
    ]
    if not usable:
        return None
    # 排序理由（从重要到次要）：
    # 1) 整份覆盖：缺集的分享会把漏掉的那几集永久跳过（实测「只有 E12」的
    #    更新包被选中，E11 再也没补上）。
    # 2) 视频就在这一层：靠递归子目录的候选会把本地已有的集在子目录里再落一份
    #    （真机：/自动/尚公主 顶层 27 集，子目录又多了「4K DV 60帧」11 集）。
    # 3) 同一集只有一份文件：同一层里两版并存时每集都会多落一份。
    # 4) 能补的集数多；5) 目录层数浅（同样的内容优先用根目录，少建子目录）。
    return max(
        usable,
        key=lambda c: (
            not c.missing,
            c.direct,
            not c.dup_episodes,
            len(c.new_episodes),
            -c.depth,
        ),
    )


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


def _save_failed_msg(path: str | Path) -> str:
    return (
        f"❌ 订阅没存下来（{path} 写不进去）\n"
        "　　容器启动时会自动把数据目录交给运行用户（uid 1000），正常不该出现这句。\n"
        "　　还报这个说明挂载点不让改属主、或者是只读挂载（常见于 NFS/SMB/cifs 共享）。\n"
        "　　换成 Docker 命名卷就好：docker run 加 -v quarkbot-data:/app/data\n"
        "　　（compose 写 volumes: - bot-data:/app/data），不用管权限。"
    )


def path_is_mounted(path: str | Path) -> bool:
    """这个路径是否落在挂载卷上（容器重建后数据还在）。

    读 /proc/self/mountinfo 判断：只要某个挂载点（根目录 "/" 除外）是该路径的
    祖先或本身，就算已挂载。读不到 mountinfo 时按「没挂」处理，宁可多提醒一次。
    """
    try:
        target = Path(path).resolve()
        info = Path("/proc/self/mountinfo").read_text(encoding="utf-8")
    except OSError as exc:
        logger.debug(f"读不到 mountinfo，跳过挂载检测: {exc}")
        return False
    for line in info.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        mount_point = Path(parts[4].replace("\\040", " "))
        if mount_point == Path("/"):
            continue
        if target == mount_point or mount_point in target.parents:
            return True
    return False


def persistence_warning(path: str | Path) -> str | None:
    """订阅文件不在挂载卷上时返回一句警告，正常情况返回 None。"""
    if path_is_mounted(path):
        return None
    return (
        f"⚠️ 订阅文件 {path} 不在挂载卷上：现在能正常用，但升级/重建容器后"
        "所有订阅和聊天绑定会全部丢失。\n"
        "　　修法：容器加 -v quarkbot-data:/app/data（compose 用 "
        "volumes: - bot-data:/app/data），再把现有订阅重发一遍 AD 即可。"
    )
