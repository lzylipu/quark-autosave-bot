import sys

import nonebot
from nonebot.adapters.telegram import Adapter as TelegramAdapter

# 强制优先从源码目录加载插件
sys.path.insert(0, "/app/src")

nonebot.init()

driver = nonebot.get_driver()
driver.register_adapter(TelegramAdapter)

# 从源码目录加载插件，而不是加载 site-packages 里的已安装版本
nonebot.load_plugins("/app/src")

if __name__ == "__main__":
    nonebot.run()
