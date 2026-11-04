"""QAS 输出解析与分享链接提取的测试。"""

from nonebot_plugin_quark_autosave.result import (
    extract_share_url,
    parse_run_output,
    share_key,
    with_passcode,
)

SUCCESS_BLOCK = "\n".join(
    [
        "✅《某某剧集》新增文件:",
        "/自动/某某剧集",
        "├── 某某剧集.E01.mkv",
        "└── 某某剧集.E02.mkv",
    ]
)


def test_extract_share_url_keeps_passcode():
    text = "转存一下 https://pan.quark.cn/s/abc123def?pwd=4f2a 谢谢"
    url = extract_share_url(text)
    assert url == "https://pan.quark.cn/s/abc123def?pwd=4f2a"


def test_extract_share_url_strips_trailing_punctuation():
    assert extract_share_url("看这个 https://pan.quark.cn/s/abc123，不错") == "https://pan.quark.cn/s/abc123"
    assert extract_share_url("(https://pan.quark.cn/s/abc123)") == "https://pan.quark.cn/s/abc123"
    assert extract_share_url("https://pan.quark.cn/s/abc123#/list/share") == "https://pan.quark.cn/s/abc123#/list/share"


def test_extract_share_url_ignores_other_links():
    assert extract_share_url("https://example.com/s/abc123") is None
    assert extract_share_url("没有链接") is None


def test_share_key_and_with_passcode():
    assert share_key("https://pan.quark.cn/s/abc123?pwd=4f2a") == "abc123"
    assert with_passcode("https://pan.quark.cn/s/abc123", "4f2a") == "https://pan.quark.cn/s/abc123?pwd=4f2a"


def test_parse_success_with_savepath_and_files():
    result = parse_run_output([SUCCESS_BLOCK])
    assert result.status == "success"
    assert result.savepath == "/自动/某某剧集"
    assert result.files == ["某某剧集.E01.mkv", "某某剧集.E02.mkv"]
    assert "转存完成" in result.render()
    assert "/自动/某某剧集" in result.render()


def test_parse_nested_tree_does_not_count_directory_as_file():
    """嵌套分享的树里有一行是目录，报数时不能算成文件。"""
    output = """✅《某某剧集》新增文件:
/自动/某某剧集
├── 📁 S01-S03
│   ├── 🎞️ S01E01.mkv
│   └── 🎞️ S01E02.mkv
└── 🎞️ S01E03.mkv"""
    result = parse_run_output([output])
    assert result.files == ["S01E01.mkv", "S01E02.mkv", "S01E03.mkv"]
    assert "3 个文件" in result.render()


def test_parse_failure_messages_are_preserved():
    result = parse_run_output(["❌《某某剧集》转存失败: 空间不足"])
    assert result.status == "failed"
    assert "空间不足" in (result.error or "")
    assert "空间不足" in result.render()


def test_parse_expired_is_reported_as_expired():
    result = parse_run_output(["❗《某某剧集》分享资源已失效: 分享已取消"])
    assert result.status == "failed"
    assert result.expired
    assert "已失效" in result.render()


def test_parse_auth_error_gets_login_hint():
    result = parse_run_output(["❌《某某剧集》转存失败: Cookie失效"])
    assert result.status == "failed"
    assert result.auth_failed
    assert "重新登录" in result.render()


def test_parse_partial_completion():
    output = "\n".join([SUCCESS_BLOCK, "❌《某某剧集》转存失败: 单个文件保存失败"])
    result = parse_run_output([output])
    assert result.status == "partial"


def test_parse_skipped_task():
    result = parse_run_output(["任务不在执行周期内，跳过"])
    assert result.status == "skipped"


def test_parse_empty_output_is_unknown():
    result = parse_run_output([""])
    assert result.status == "unknown"
    assert "QAS 日志" in result.render()


def test_render_falls_back_to_task_savepath():
    result = parse_run_output([SUCCESS_BLOCK])
    result.savepath = None
    assert "/自动/兜底路径" in result.render(fallback_savepath="/自动/兜底路径")


def test_parse_no_new_files_is_not_an_error():
    """QASx 明确说没有新文件 = 正常结果，不能报成「没解析到结果/登录失效」。"""
    out = """===============程序开始===============
任务完成: 没有新的文件需要转存
===============程序结束==============="""
    result = parse_run_output([out])
    assert result.status == "no_new"
    assert "已是最新" in result.render()
    assert "登录态" not in result.render()


def test_no_new_mark_does_not_hide_real_success():
    out = """✅《某剧》新增文件:
/自动/某剧
└── 🎞️ S01E01.mkv
任务完成: 没有新的文件需要转存"""
    result = parse_run_output([out])
    assert result.status == "success"
    assert result.files == ["S01E01.mkv"]
