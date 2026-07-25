<div align="center">

# 🍭 Quark AutoSave Bot

**夸克网盘自动转存 Telegram 机器人**

转发夸克网盘链接，自动转存到你的网盘 🚀

[![Python](https://img.shields.io/badge/python-3.12-blue.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![NoneBot2](https://img.shields.io/badge/NoneBot2-2.4+-orange.svg?style=flat-square)](https://v2.nonebot.dev/)
[![Docker](https://img.shields.io/docker/pulls/lzylipu/quarkbot?style=flat-square&logo=docker&logoColor=white)](https://hub.docker.com/r/lzylipu/quarkbot)
[![License](https://img.shields.io/github/license/lzylipu/quark-autosave-bot?style=flat-square)](./LICENSE)
[![GitHub](https://img.shields.io/badge/_repo-quark--autosave--bot-181717.svg?style=flat-square&logo=github&logoColor=white)](https://github.com/lzylipu/quark-autosave-bot)

[English](./README_EN.md) · 简体中文

</div>

---

## 📖 目录

- [✨ 功能特性](#-功能特性)
- [📂 项目结构](#-项目结构)
- [🔄 工作流程](#-工作流程)
- [🚀 快速开始](#-快速开始)
  - [🐳 Docker](#-docker)
  - [📦 Docker Compose（推荐）](#-docker-compose推荐)
- [⚙️ 环境变量](#️-环境变量)
- [🗄️ QAS 服务变量](#️-qas-服务变量)
- [💬 聊天示例](#-聊天示例)
- [🔧 BotFather 配置](#-botfather-配置)
- [🛠️ 技术栈](#️-技术栈)
- [🙏 致谢](#-致谢)
- [📄 许可证](#-许可证)

---

## ✨ 功能特性

- 🔗 **一键转存** — 直接发送夸克网盘分享链接，自动转存到你的网盘
- 🤖 **Telegram 原生交互** — 直接发链接即转存，无需触发词
- 🐳 **Docker 一键部署** — 镜像 `lzylipu/quarkbot:latest`，30 秒上线
- 🧹 **自动清理** — 转存完成后自动删除任务，保持后台整洁
- 🔒 **权限控制** — 仅 Superuser 可触发，安全可控
- 🔁 **自动重试** — 内置 httpx 重试机制，网络波动自动恢复
- ⬇️ **Aria2 自动下载** — 转存后通过 Aria2 自动下载到本地

---

## 📂 项目结构

```
quark-autosave-bot/
├── 📄 bot.py                          # 🤖 NoneBot2 入口，注册 Telegram 适配器
├── 🐳 Dockerfile                      # Docker 镜像定义（Python 3.12-slim）
├── 📦 compose.yml                     # Docker Compose 编排（Bot + QAS 服务）
├── ⚙️ .env.example                    # 环境变量示例文件
├── 🔧 start.sh                        # 容器启动脚本，生成 .env.prod
├── 📄 pyproject.toml                  # 项目元数据与依赖声明
├── 📜 LICENSE                         # MIT 开源许可证
├── 📖 README.md                       # 中文说明文档
├── 📖 README_EN.md                    # 英文说明文档
├── 📁 .github/
│   └── workflows/
│       └── docker.yml                 # GitHub Actions Docker 构建流程
└── 📁 src/
    └── nonebot_plugin_quark_autosave/
        ├── __init__.py                # 插件主逻辑：链接匹配 → 转存流程
        ├── client.py                  # QAS API 异步客户端（带重试）
        ├── config.py                  # Pydantic 配置模型
        ├── model.py                   # 数据模型：TaskItem / DetailInfo / Addition
        └── exception.py               # 自定义异常 QASException
```

---

## 🔄 工作流程

```
用户发送夸克链接 ──→ 验证链接格式
                    │
              解析分享详情（获取根目录名）
                    │
              构建转存任务（启用 Aria2 自动下载）
                    │
              添加任务 → 执行转存脚本 → 删除任务
                    │
              回复 "好了" ✅
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

---

## ⚙️ 环境变量

**Bot 服务**

| 变量 | 必填 | 默认值 | 说明 |
|------|:----:|--------|------|
| `TELEGRAM_BOT_TOKEN` | ✅ | | Telegram Bot Token，从 [@BotFather](https://t.me/BotFather) 获取 |
| `SUPERUSER` | ✅ | | Telegram 用户 ID，从 [@userinfobot](https://t.me/userinfobot) 查询 |
| `QAS_ENDPOINT` | ✅ | `http://quark-auto-save:5005` | QAS 服务地址；独立部署时改为实际地址 |
| `QAS_TOKEN` | ✅ | | QAS API 密钥 |
| `SIMPLE_SAVE_ROOT` | | `auto` | 转存到网盘的根目录文件夹名 |

---

## 🗄️ QAS 服务变量

Compose 方式自带 QAS 服务（`cp0204/quark-auto-save:latest`），以下变量控制 QAS 行为：

| 变量 | 必填 | 默认值 | 说明 |
|------|:----:|--------|------|
| `QAS_PORT` | | `5005` | QAS WebUI 端口映射 |
| `QAS_WEBUI_USER` | | `admin` | QAS WebUI 用户名 |
| `QAS_WEBUI_PASS` | | | QAS WebUI 密码（建议设置） |

---

## 💬 聊天示例

```
你:  https://pan.quark.cn/s/xxxxxxxx
机器人:  转存中…
机器人:  好了
```

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
| 🌐 [httpx](https://www.python-httpx.org/) | 异步 HTTP 客户端（keepalive + 自动重试） |
| 💾 [Quark Auto Save](https://github.com/Cp0204/quark-auto-save) | 夸克网盘自动转存后端服务 |
| ⬇️ Aria2 | 内置自动下载支持 |

---

## 🙏 致谢

- 💜 [Cp0204/quark-auto-save](https://github.com/Cp0204/quark-auto-save) — 夸克网盘自动转存后端
- 🎯 [fllesser/nonebot-plugin-quark-autosave](https://github.com/fllesser/nonebot-plugin-quark-autosave) — 原始 NoneBot 插件
- 🤖 [NoneBot2](https://v2.nonebot.dev/) — 异步机器人框架

---

## 📄 许可证

本项目基于 [MIT License](./LICENSE) 开源。
