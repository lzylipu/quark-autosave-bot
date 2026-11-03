# 🍭 Quark AutoSave Bot

**夸克网盘自动转存 Telegram 机器人**

转发夸克网盘链接，自动转存到你的网盘 🚀

[English](./README_EN.md) · 简体中文

---

## 📖 目录

- [✨ 功能特性](#-功能特性)
- [📂 项目结构](#-项目结构)
- [🔄 工作流程](#-工作流程)
- [🚀 快速开始](#-快速开始)
  - [🐳 Docker](#-docker)
  - [📦 Docker Compose（推荐）](#-docker-compose推荐)
- [⚙️ 环境变量](#️-环境变量)
- [🗄️ QAS 服务说明](#️-qas-服务说明)
- [💬 聊天示例](#-聊天示例)
- [🧪 本地测试](#-本地测试)
- [🔧 BotFather 配置](#-botfather-配置)
- [🛠️ 技术栈](#️-技术栈)
- [📝 更新日志](#-更新日志)
- [🙏 致谢](#-致谢)
- [📄 许可证](#-许可证)

---

## ✨ 功能特性

- 🔗 **一键转存** — 直接发送夸克网盘分享链接，自动转存到你的网盘
- 🔑 **提取码支持** — 链接自带 `?pwd=xxxx` 直接可用；没带会追问一次提取码，回你 4 位码即可
- 🤖 **Telegram 原生交互** — 发链接即转存，不用记任何命令
- 🐳 **Docker 一键部署** — 镜像 `lzylipu/quarkbot:latest`，30 秒上线
- 🧹 **任务零残留** — 转存结束按「任务名 + 分享链接」精确删除 QAS 任务，并回读校验；删除失败会明确告诉你，不再静默
- 📁 **回执带路径** — 直接回复转存到哪个目录、几个文件
- ♻️ **重复去重** — 同一条链接限时内重复发送，直接返回上次结果，不重复跑批
- ⏱️ **整体超时保护** — 单次转存超过 `QAS_RUN_TIMEOUT` 秒自动放弃并告知，不会无限挂起
- 🔁 **自动重试** — 网络异常与 5xx/429 自动退避重试，QAS 重启期间的请求不会直接失败
- 🔒 **权限可选** — 留空 `SUPERUSER` = 私聊直接能用，不用先查自己的 ID；填了只认名单，群里一律不响应
- ⬇️ **Aria2 自动下载** — 转存后通过 Aria2 自动下载到本地
- 📺 **追剧订阅** — `AD 甄嬛传` 订阅后，每天 17:00 自动搜索最新资源并补缺转存，转完就删任务
- 📏 **按集大小筛选** — 只挑「每集都在 1.5~8G」的分享，杂项文件不干扰判断
- 🧩 **集数补缺** — 扫网盘保存目录算出本地已有哪几集，只补缺的那些，全集齐了就跳过
- 🏷️ **统一命名** — 落盘文件名自动补齐季数：`E05.mkv`、`第5集` → `S01E05.mkv`

---

## 📂 项目结构

```
quark-autosave-bot/
├── 📄 bot.py                          # 🤖 NoneBot2 入口，注册 Telegram 适配器
├── 🐳 Dockerfile                      # Docker 镜像定义（Python 3.12-slim，非 root 运行）
├── 📦 compose.yml                     # Docker Compose 编排（Bot + QAS 服务）
├── 📋 requirements.txt                # 运行时依赖（固定版本）
├── 📋 requirements-dev.txt            # 测试依赖
├── ⚙️ .env.example                    # 环境变量示例文件
├── 🔧 start.sh                        # 容器启动脚本，生成 .env.prod
├── 📄 pyproject.toml                  # 项目元数据与工具配置
├── 📜 LICENSE                         # MIT 开源许可证
├── 📖 README.md                       # 中文说明文档
├── 📖 README_EN.md                    # 英文说明文档
├── 📁 .github/
│   └── workflows/
│       └── docker.yml                 # GitHub Actions：先跑测试，再构建推送镜像
├── 📁 tests/
│   ├── conftest.py                    # NoneBot 初始化（插件 import 需要）
│   ├── test_client_requests.py        # 重试、报错信息、执行参数、超时
│   ├── test_client_cleanup.py         # 任务删除与回读校验
│   ├── test_result.py                 # 链接提取 / 输出解析 / 错误分类
│   ├── test_perms.py                  # 权限判定（空 SUPERUSER = 私聊放行）
│   ├── test_plugin_helpers.py         # 提取码追问、去重缓存
│   ├── test_subscribe.py              # 集数解析、季数拆分、大小筛选、差集选源
│   ├── test_subscription_flow.py      # 订阅全流程编排（假 client）
│   ├── test_client_share_files.py     # 分享递归展开（根目录是文件夹时）
│   ├── test_client_delete_safety.py   # 删任务不丢字段 / addition=null 不炸
│   └── e2e/                           # 对着真 QASx 跑的验证脚本（见 tests/e2e/README.md）
└── 📁 src/
    └── nonebot_plugin_quark_autosave/
        ├── __init__.py                # 插件主逻辑：去重 → 检测 → 转存 → 清理 → 回执
        ├── client.py                  # QAS API 异步客户端（重试 / 并发锁 / 超时）
        ├── result.py                  # 分享链接提取、QAS 输出解析、错误分类
        ├── perms.py                   # 权限判定
        ├── subscribe.py               # 追剧订阅：集数/季数解析、筛选、定时计算
        ├── config.py                  # Pydantic 配置模型
        ├── model.py                   # 数据模型：TaskItem / DetailInfo / Addition
        └── exception.py               # 自定义异常 QASException
```

---

## 🔄 工作流程

```
用户发送夸克链接 ──→ 提取链接（保留 ?pwd= 与 #/ 子目录）
                    │
              去重检查（处理中 / 刚刚转过）
                    │
              解析分享详情 ──需要提取码──→ 聊天里追问 4 位码
                    │
              构建转存任务（全周有效 + Aria2 自动下载）
                    │
              添加任务 → 执行转存（带整体超时）→ 精确删除任务 + 回读校验
                    │
              回执：完成/部分完成/失败 + 保存路径
```

### 追剧订阅

```
AD 甄嬛传        → 加入订阅（也可以写 AD 庆余年 S02 指定季）
LIST             → 查看订阅列表和上次结果
DL 甄嬛传        → 取消订阅
```

每天 `SUB_CHECK_TIME`（默认 17:00）对每部订阅执行：

```
扫网盘保存目录 ──→ 本地已有哪几集（E05 / S01E05 / 第5集 都认）
                    │
            搜片名（QASx 聚合 PanSou / CloudSaver）
                    │
       逐个候选分享：探详情 → 每集 1.5~8G 筛选 → 算能补几集
                    │
        选「能补最多集」的分享（一个都不合格就跳过，不硬转）
                    │
       建任务（重命名统一成 S01E05）→ 转存 → 删任务
                    │
            回执：本地已有 / 本次新增 / 保存路径
```

> 分享链接失效是常态：任务每轮都用当天搜到的新链接重建，不用人工维护。
> 已下载的集由 QASx 扫描保存目录去重（大小 + 扩展名 + 时间），不会重复下载。

---

## 🚀 快速开始

### 🐳 Docker

```bash
docker run -d \
  --name quarkbot \
  -e TELEGRAM_BOT_TOKEN=*** \
  -e QAS_ENDPOINT="http://你的QAS地址:5005" \
  -e QAS_TOKEN=*** \
  -e TZ=Asia/Shanghai \
  --restart unless-stopped \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  lzylipu/quarkbot:latest
```

### 📦 Docker Compose（推荐）

项目自带 `compose.yml`，同时编排 Bot 和 QAS 服务，内网互联：

```bash
cp .env.example .env   # 编辑 .env 填入你的配置
docker compose up -d
```

> 💡 Compose 方式下 `QAS_ENDPOINT` 默认为 `http://quark-auto-save:5005`，走 Docker 内网，无需暴露端口。
> QAS WebUI 只绑定 `127.0.0.1:5005`，需要远程访问请自己加反向代理，别直接把面板暴露到公网。

---

## ⚙️ 环境变量

**Bot 服务**

| 变量 | 必填 | 默认值 | 说明 |
|------|:----:|--------|------|
| `TELEGRAM_BOT_TOKEN` | ✅ | | Telegram Bot Token，从 [@BotFather](https://t.me/BotFather) 获取 |
| `SUPERUSER` | | 空 | 你的 Telegram 用户 ID。留空 = 私聊谁都能用；填了就只认名单 |
| `QAS_ENDPOINT` | ✅ | `http://quark-auto-save:5005` | QAS 服务地址；独立部署时改为实际地址 |
| `QAS_TOKEN` | ✅ | | QASx 的 `api_token`：登录 WebUI 后打开 `http://<QASx地址>/data`，JSON 里的 `api_token` 字段 |
| `SIMPLE_SAVE_ROOT` | | `自动` | 转存到网盘的根目录文件夹名 |
| `QAS_PATH_BASE` | | `夸克自动转存` | 模板任务使用的根目录（本 Bot 用 `SIMPLE_SAVE_ROOT`） |
| `QAS_RUN_TIMEOUT` | | `1800` | 单次转存整体超时（秒） |
| `DEDUPE_SECONDS` | | `600` | 同一链接多少秒内重复发送时直接返回上次结果 |
| `ASK_PASSCODE` | | `true` | 分享需要提取码时是否在聊天里追问 |
| `SUB_CHECK_TIME` | | `17:00` | 追剧订阅每天执行时间（HH:MM） |
| `SUB_MIN_SIZE_GB` | | `1.5` | 每集大小下限（GB） |
| `SUB_MAX_SIZE_GB` | | `8.0` | 每集大小上限（GB） |
| `SUB_MAX_CANDIDATES` | | `10` | 每个订阅最多检查多少个搜索结果 |
| `SUB_STORE_FILE` | | `/app/data/subscriptions.json` | 订阅列表存放路径（compose 已挂 `bot-data` 卷） |
| `ASK_PASSCODE` | | `true` | 分享需要提取码时是否在聊天里追问 |

---

## 🗄️ QAS 服务说明

Compose 方式自带 QAS 服务（`cp0204/quark-auto-save:latest`）：

| 变量 | 必填 | 默认值 | 说明 |
|------|:----:|--------|------|
| `QAS_PORT` | | `5005` | QAS WebUI 端口（仅绑定本机） |
| `QAS_WEBUI_USER` | | `admin` | QAS WebUI 用户名 |
| `QAS_WEBUI_PASS` | | | QAS WebUI 密码（建议设置） |

> ⚠️ QASx 没有「API 密钥」设置项。它认的是 `?token=` 参数，值由 WebUI 用户名+密码派生，等于 `/data` 返回里的 `api_token`。拿不到就先用浏览器登录 WebUI，再访问 `/data` 复制。

---

## 💬 聊天示例

```
你:  https://pan.quark.cn/s/xxxxxxxx
机器人:  🔍 检测链接...
机器人:  📥 剧集名字 (12个文件)
机器人:  ✅ 转存完成，12 个文件
         📁 /自动/剧集名字

你:  https://pan.quark.cn/s/yyyyyyyy?pwd=4f2a
机器人:  🔍 检测链接...
机器人:  📥 电影名字 (1个文件)
机器人:  ✅ 转存完成，1 个文件
         📁 /自动/电影名字

你:  https://pan.quark.cn/s/zzzzzzzz        # 需要提取码
机器人:  🔑 这个分享需要提取码，请直接发送 4 位提取码（60 秒内有效）
你:  4f2a
机器人:  📥 …（正常继续转存）

你:  https://pan.quark.cn/s/xxxxxxxx        # 刚转过
机器人:  ♻️ 这条链接 42 秒前刚转过，跳过
         📁 /自动/剧集名字
```

---

## 🧪 本地测试

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests/ -q
```

测试不需要连真实 QAS：请求层用 `httpx.MockTransport` 打桩，覆盖重试、报错信息保留、执行参数、整体超时、任务删除与回读校验等分支。

### 对着真 QASx 验证

单元测试证明逻辑自洽，但不证明接口对得上。`tests/e2e/` 下是打真 QASx 实例的脚本，
不用你的夸克账号也能跑（除转存那一步）：

```bash
PYTHONPATH=src python3 tests/e2e/e2e_real_qasx.py       # 接口契约 + 删任务（9 项）
PYTHONPATH=src python3 tests/e2e/e2e_dirty_config.py    # 脏配置 / 字段保全（11 项）
PYTHONPATH=src python3 tests/e2e/e2e_share_expand.py    # 真分享递归展开、真文件大小
```

起本地 QASx 的方法见 [`tests/e2e/README.md`](tests/e2e/README.md)。

### 对着真实例发现并已修的坑

| 现象 | 根因 | 处理 |
|---|---|---|
| 删除任务在真机上报 500 | QASx `sync_task_plugins_config()` 对 `task["addition"].keys()` 取值，配置里只要有任务 `addition=null` 整份 `/update` 就 500 | 写回前把所有 `addition` 统一成 `{}`；`add_task` 也不再发 null |
| 删任务后追剧日历/插件配置丢了 | 用 pydantic 模型全量读写配置，会抹掉 QASx 自己维护的 `calendar_info`、`source` 等字段 | 删任务改成读**原始 dict**、只写回 `tasklist` |
| 订阅永远「分享里没有视频文件」 | 分享根目录通常只是一个文件夹，`/get_share_detail` 只返回当前层 | 按 `shareurl#/list/share/<fid>` 递归展开（实测有效），带深度与目录数上限防死循环 |
| 建了任务但一个文件都没转存，QAS 只打印「没有新的文件需要转存」 | 建任务时没设 `update_subdir`，QASx 遇到「文件夹套文件夹」的分享不递归，直接判定无新文件 | 建任务统一带 `update_subdir=".*"`（实测同一分享从 0 文件变成 2 个 mkv 落地） |
| 订阅判断「已有几集」永远数成 0，反复重复转存 | QASx 按分享目录结构嵌套落盘（`/自动/某剧/<子目录>/x.mkv`），只读顶层看不到文件 | `list_savepath_files` 递归子目录收集文件 |
| 删掉的任务过几秒又出现在配置里 | QASx 的 `/update` 会起后台线程（元数据匹配/日历初始化），线程手里攥着写盘前的任务列表，回头整份写盘把删掉的写回去 | 建任务带 `skip_calendar=true`（QASx 的一次性任务标记，`app/run.py:3189` 直接跳过日历匹配，后台线程不再写盘）；删除后仍按递增间隔复查兜底 |
| 删文件成功却抛「未知错误」 | `/delete_file` 不返回 `{success,data}` 包装，直接吐夸克原始响应 `{status,code}`，且是异步任务 | 按 `code==0` 判成功，是否真删干净自己回读目录 |
| 同一个分享重复测转存时 QAS 说「没有新的文件」 | QASx 有转存记录库，按 `file_id + taskname` 查重 | 这是**想要**的行为：bot 用固定任务名+固定目录，同一集不会重复转存，新集自动补进去；只有自检脚本需要每次换分享 |

---

## 🔧 BotFather 配置

为了让 bot 能读取你发送的**所有消息**（而不仅是以 `/` 开头的命令），需要在 BotFather 中关闭隐私模式：

1. 打开 [@BotFather](https://t.me/BotFather) 🤖
2. 发送 `/setprivacy`
3. 选择你的 Bot
4. 选择 **Disable** 🔓

---

## 🛠️ 技术栈

| 组件 | 版本 / 说明 |
|------|------------|
| 🐍 Python | 3.12 |
| 🤖 [NoneBot2](https://v2.nonebot.dev/) | 异步机器人框架（FastAPI + httpx 驱动） |
| 📡 [nonebot-adapter-telegram](https://github.com/nonebot/adapter-telegram) | Telegram 适配器 |
| ⌛ [nonebot-plugin-waiter](https://github.com/RF-Tar-Railt/nonebot-plugin-waiter) | 提取码追问 |
| 🌐 [httpx](https://www.python-httpx.org/) | 异步 HTTP 客户端（keepalive + 重试） |
| 💾 [Quark Auto Save](https://github.com/Cp0204/quark-auto-save) | 夸克网盘自动转存后端服务 |
| ⬇️ Aria2 | 内置自动下载支持 |

---

## 📝 更新日志

### v0.3.0

- 📺 新增追剧订阅：`AD 片名` / `DL 片名` / `LIST`，每天定时自动搜索并补缺转存
- 📏 按每集大小区间筛选分享（默认 1.5~8G），海报等杂项不参与判定
- 🧩 扫网盘保存目录算本地已有集数，只补缺的；全集齐自动跳过
- 🏷️ 建任务时下发重命名规则，落盘统一成 `S01E05`（订阅名带 S02 就用 S02）
- 🐳 compose 新增 `bot-data` 卷持久化订阅列表
- ✅ 新增 26 个单测：集数解析、季数拆分、差集选源、订阅全流程编排

### v0.2.1

- 🐛 修复登录态失效被误报成「链接已失效」（`Cookie 已失效` 同时命中两类关键词，顺序错了）
- 🔒 `SUPERUSER` 改为可选：留空即私聊可用，不用先去查自己的 ID；群里始终不响应
- 💬 没权限却发了链接时，bot 会回你的 TG 用户 ID，方便直接填进配置
- 🐛 修复 `SUPERUSER` 留空时生成 `[""]` 导致谁都匹配不上的问题
- ✅ 补 32 个单测：错误分类、权限判定、提取码、去重、删除校验

### v0.2.0

- 🐛 修复带提取码的分享链接（`?pwd=xxxx`）被截断导致转存失败
- 🐛 修复 QAS 的报错信息被吞成 `HTTP 4xx`，现在能看到真实原因（未登录、空间不足等）
- 🐛 修复执行输出里所有 `=` 被删除
- 🐛 修复「转存成功但 QAS 任务不删除」：改为按任务名 + 分享链接精确删除并回读校验
- ✨ 新增提取码追问、重复链接去重、保存路径回执、登录态失效提示
- ✨ 新增整体超时保护与 5xx/429 退避重试
- 🔒 转存期间对 QAS 配置读写加锁，避免并发互相覆盖任务列表
- 🏗️ CI 先跑测试再构建镜像，依赖固定版本，镜像改为非 root + HEALTHCHECK

### v0.1.9

- 首个可用版本：发链接即转存，Aria2 自动下载

---

## 🙏 致谢

- 💜 [Cp0204/quark-auto-save](https://github.com/Cp0204/quark-auto-save) — 夸克网盘自动转存后端
- 🎯 [fllesser/nonebot-plugin-quark-autosave](https://github.com/fllesser/nonebot-plugin-quark-autosave) — 原始 NoneBot 插件
- 🤖 [NoneBot2](https://v2.nonebot.dev/) — 异步机器人框架

---

## 📄 许可证

本项目基于 [MIT License](./LICENSE) 开源。
