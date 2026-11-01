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


plugin_config: Config = get_plugin_config(Config)
