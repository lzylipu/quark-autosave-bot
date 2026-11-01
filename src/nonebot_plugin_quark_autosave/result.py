"""解析夸克分享链接与 QAS 转存输出。

QAS（quark_auto_save.py）的输出格式：
    ✅《任务名》新增文件:
    /保存路径
    ├── 文件A
    └── 文件B
    ❌《任务名》转存失败: 原因
    ❗《任务名》分享资源已失效: 原因
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

QUARK_SHARE_RE = re.compile(r"https?://pan\.quark\.cn/s/[0-9a-zA-Z]+(?:[?#][^\s<>\"']*)?")

# 链接后面常跟着中文标点或右括号，需要从尾部剥掉
_TRAILING_CHARS = "，。、,;；:：!！?？)]}）】》>&"

SUCCESS_MARK = "✅"
FAILURE_MARKS = ("❌", "❗")
SKIP_MARK = "任务不在执行周期内"

# QAS 明确表示分享/链接失效的措辞（见 quark_auto_save.py）
EXPIRED_KEYWORDS = (
    "失效",
    "过期",
    "已取消",
    "已删除",
    "不存在",
    "已关闭",
    "分享为空",
    "提取链接参数失败",
    "expired",
    "deleted",
    "cancelled",
    "not found",
)

# 夸克登录态/cookie 异常
AUTH_ERROR_KEYWORDS = (
    "cookie",
    "未登录",
    "登录失效",
    "登录失败",
    "账号失效",
    "unauthorized",
    "401",
)

# 需要提取码
PASSCODE_KEYWORDS = ("提取码", "密码", "passcode", "pwd=")

TREE_PREFIXES = ("├──", "└──", "│──")


def extract_share_url(text: str) -> str | None:
    """从任意文本里取出夸克分享链接（保留 ?pwd= 之类的提取码参数）。"""
    match = QUARK_SHARE_RE.search(text)
    if not match:
        return None
    url = match.group(0).rstrip(_TRAILING_CHARS)
    return url if "/s/" in url else None


def share_key(shareurl: str) -> str:
    """分享的唯一标识（不含提取码），用于去重。"""
    match = re.search(r"/s/([0-9a-zA-Z]+)", shareurl)
    return match.group(1) if match else shareurl


def extract_passcode(shareurl: str) -> str:
    match = re.search(r"[?&]pwd=([0-9a-zA-Z]+)", shareurl)
    return match.group(1) if match else ""


def with_passcode(shareurl: str, passcode: str) -> str:
    base = shareurl.split("?", 1)[0]
    return f"{base}?pwd={passcode}"


def contains_any(text: str, keywords: Iterable[str]) -> bool:
    lower = text.lower()
    return any(keyword.lower() in lower for keyword in keywords)


@dataclass
class RunResult:
    """一次转存执行的结果。"""

    status: str = "unknown"  # success / partial / failed / skipped / unknown
    files: list[str] = field(default_factory=list)
    savepath: str | None = None
    error: str | None = None

    @property
    def auth_failed(self) -> bool:
        return bool(self.error) and contains_any(self.error, AUTH_ERROR_KEYWORDS)

    @property
    def expired(self) -> bool:
        return bool(self.error) and contains_any(self.error, EXPIRED_KEYWORDS)

    def render(self, fallback_savepath: str | None = None) -> str:
        """转成给用户看的一句话（可带保存路径）。"""
        if self.status == "success":
            head = "✅ 转存完成"
            if self.files:
                head += f"，{len(self.files)} 个文件"
        elif self.status == "partial":
            head = f"⚡ 部分完成：{len(self.files)} 个成功，其余失败"
        elif self.status == "failed":
            if self.auth_failed:
                return "🔒 夸克登录态失效，请到 QAS WebUI 重新登录后再发一次"
            if self.expired:
                return f"🔴 链接已失效：{self.error}"
            return f"❌ 转存失败：{self.error or '未知原因'}"
        elif self.status == "skipped":
            return "⏭ QAS 跳过了这次执行，请检查该任务的执行周期/进度设置"
        else:
            return "⚠️ 转存已执行，但没解析到结果，请查看 QAS 日志"

        savepath = self.savepath or fallback_savepath
        if savepath:
            head += f"\n📁 {savepath}"
        return head


def parse_run_output(chunks: Iterable[str]) -> RunResult:
    """把 QAS 的流式输出解析成结构化结果。"""
    result = RunResult()
    failures: list[str] = []
    has_success = False
    in_success_block = False
    text = "\n".join(chunks)

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(SUCCESS_MARK):
            has_success = True
            in_success_block = True
            continue
        if line.startswith(FAILURE_MARKS):
            in_success_block = False
            failures.append(line.lstrip("".join(FAILURE_MARKS)).strip(" :《》"))
            continue
        if line.startswith(TREE_PREFIXES):
            name = line[3:].strip()
            if name:
                result.files.append(name)
            continue
        if in_success_block and line.startswith("/") and result.savepath is None:
            result.savepath = line

    if has_success and failures:
        result.status = "partial"
        result.error = failures[0]
    elif has_success:
        result.status = "success"
    elif failures:
        result.status = "failed"
        result.error = failures[0]
    elif result.files:
        # 只拿到了文件列表，没有醒目头部（旧版本 QAS）
        result.status = "success"
    elif SKIP_MARK in text:
        result.status = "skipped"
    return result
