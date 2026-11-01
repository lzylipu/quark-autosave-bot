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
- 🔒 **权限控制** — 仅 Superuser 可触发，安全可控
- ⬇️ **Aria2 自动下载** — 转存后通过 Aria2 自动下载到本地

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
│   ├── test_result.py                 # 链接提取 / 输出解析
│   ├── test_client_requests.py        # 重试、报错信息、执行参数、超时
│   └── test_client_cleanup.py         # 任务删除与回读校验
└── 📁 src/
    └── nonebot_plugin_quark_autosave/
        ├── __init__.py                # 插件主逻辑：去重 → 检测 → 转存 → 清理 → 回执
        ├── client.py                  # QAS API 异步客户端（重试 / 并发锁 / 超时）
        ├── result.py                  # 分享链接提取与 QAS 输出解析
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

---

## 🚀 快速开始

### 🐳 Docker

```bash
docker run -d \
  --name quarkbot \
  -e TELEGRAM_BOT_TOKEN=*** \
  -e SUPERUSER="你的TG用户ID" \
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
| `SUPERUSER` | ✅ | | Telegram 用户 ID，从 [@userinfobot](https://t.me/userinfobot) 查询 |
| `QAS_ENDPOINT` | ✅ | `http://quark-auto-save:5005` | QAS 服务地址；独立部署时改为实际地址 |
| `QAS_TOKEN` | ✅ | | QAS WebUI「设置 → API 密钥」里的值 |
| `SIMPLE_SAVE_ROOT` | | `自动` | 转存到网盘的根目录文件夹名 |
| `QAS_PATH_BASE` | | `夸克自动转存` | 模板任务使用的根目录（本 Bot 用 `SIMPLE_SAVE_ROOT`） |
| `QAS_RUN_TIMEOUT` | | `1800` | 单次转存整体超时（秒） |
| `DEDUPE_SECONDS` | | `600` | 同一链接多少秒内重复发送时直接返回上次结果 |
| `ASK_PASSCODE` | | `true` | 分享需要提取码时是否在聊天里追问 |

---

## 🗄️ QAS 服务说明

Compose 方式自带 QAS 服务（`cp0204/quark-auto-save:latest`）：

| 变量 | 必填 | 默认值 | 说明 |
|------|:----:|--------|------|
| `QAS_PORT` | | `5005` | QAS WebUI 端口（仅绑定本机） |
| `QAS_WEBUI_USER` | | `admin` | QAS WebUI 用户名 |
| `QAS_WEBUI_PASS` | | | QAS WebUI 密码（建议设置） |

> ⚠️ QAS 的 API 密钥保存在它的配置文件里（首次进 WebUI 设置），不是通过容器环境变量注入。`QAS_TOKEN` 只给 Bot 用，两边必须一致。

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
