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
    # 每个订阅最多检查多少个搜索结果（都是要逐个探分享详情的，别太大）
    sub_max_candidates: int = 10
    # 订阅列表存放路径
    sub_store_file: str = "data/subscriptions.json"


plugin_config: Config = get_plugin_config(Config)
