from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    qas_endpoint: str = "http://127.0.0.1:5005"
    qas_token: str | None = None
    qas_path_base: str = "夸克自动转存"
    simple_save_root: str = "自动"
    # 单次转存整体超时（秒）；QAS 子进程卡死时不至于让 bot 无限等待
    qas_run_timeout: int = 1800
    # 同一分享在多少秒内重复发送时直接返回上次结果
    dedupe_seconds: int = 600
    # 分享需要提取码时是否在聊天里追问
    ask_passcode: bool = True
    # ===== 追剧订阅 =====
    # 每天几点跑一次订阅（本地时间 HH:MM）
    sub_check_time: str = "17:00"
    # 每集大小下限/上限（GB），用于筛选分享
    sub_min_size_gb: float = 1.5
    sub_max_size_gb: float = 8.0
    # 每个订阅最多检查多少个搜索结果；0 = 搜到多少看多少（默认）
    # 原来写死 10：走马上任 71 条结果里前 10 条全不合格、第 25 条才符合，
    # 结果直接报「检查了 10 个分享，都不在 1.5~8.0G 区间」（真机复现）
    sub_max_candidates: int = 0
    # 已经凑够这么多个合格分享就不再继续扫；0 = 扫完全部再挑（默认）
    # 默认 0：合格分享是「越往后集数越全」的，提前停会拿着第一个碰到的
    # 就下（走马上任 第 25 条只有前 9 集，第 43 条是 7 集，得比完才知道谁全）
    sub_max_ok_candidates: int = 0
    # 全部都不在区间内时退一档：每集中位数 >= 这个值就当正片下（0.5G 挡枪版）
    sub_fallback_min_size_gb: float = 0.5
    # 订阅列表存放路径
    sub_store_file: str = "data/subscriptions.json"


plugin_config: Config = get_plugin_config(Config)
