"""初始化 NoneBot 运行环境，使插件模块可以在测试中被导入。"""

import nonebot

nonebot.init(driver="~none")
