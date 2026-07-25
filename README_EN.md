<div align="center">

# 🍭 Quark AutoSave Bot

**Telegram Bot for Quark Cloud Auto-Save**

Forward Quark Cloud links and auto-save to your drive 🚀

[![Python](https://img.shields.io/badge/python-3.12-blue.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![NoneBot2](https://img.shields.io/badge/NoneBot2-2.4+-orange.svg?style=flat-square)](https://v2.nonebot.dev/)
[![Docker](https://img.shields.io/docker/pulls/lzylipu/quarkbot?style=flat-square&logo=docker&logoColor=white)](https://hub.docker.com/r/lzylipu/quarkbot)
[![License](https://img.shields.io/github/license/lzylipu/quark-autosave-bot?style=flat-square)](./LICENSE)
[![GitHub](https://img.shields.io/badge/_repo-quark--autosave--bot-181717.svg?style=flat-square&logo=github&logoColor=white)](https://github.com/lzylipu/quark-autosave-bot)

English · [简体中文](./README.md)

</div>

---

## 📖 Table of Contents

- [✨ Features](#-features)
- [📂 Project Structure](#-project-structure)
- [🔄 How It Works](#-how-it-works)
- [🚀 Quick Start](#-quick-start)
  - [🐳 Docker](#-docker)
  - [📦 Docker Compose (Recommended)](#-docker-compose-recommended)
- [⚙️ Environment Variables](#️-environment-variables)
- [🗄️ QAS Service Variables](#️-qas-service-variables)
- [💬 Chat Example](#-chat-example)
- [🔧 BotFather Setup](#-botfather-setup)
- [🛠️ Tech Stack](#️-tech-stack)
- [🙏 Acknowledgements](#-acknowledgements)
- [📄 License](#-license)

---

## ✨ Features

- 🔗 **One-Click Save** — Just send a Quark Cloud sharing link, auto-saved instantly
- 🤖 **Telegram Native** — Send link directly, no trigger command needed
- 🐳 **Docker One-Command Deploy** — Image `lzylipu/quarkbot:latest`, up in 30 seconds
- 🧹 **Auto Cleanup** — Tasks are deleted after save completes, keeping the backend tidy
- 🔒 **Access Control** — Only the Superuser can trigger the bot
- 🔁 **Auto Retry** — Built-in httpx retry mechanism for network resilience
- ⬇️ **Aria2 Auto-Download** — Automatically downloads saved files via Aria2

---

## 📂 Project Structure

```
quark-autosave-bot/
├── 📄 bot.py                          # 🤖 NoneBot2 entry point, registers Telegram adapter
├── 🐳 Dockerfile                      # Docker image definition (Python 3.12-slim)
├── 📦 compose.yml                     # Docker Compose orchestration (Bot + QAS service)
├── ⚙️ .env.example                    # Environment variable template
├── 🔧 start.sh                        # Container startup script, generates .env.prod
├── 📄 pyproject.toml                  # Project metadata and dependencies
├── 📜 LICENSE                         # MIT License
├── 📖 README.md                       # Chinese documentation
├── 📖 README_EN.md                    # English documentation
├── 📁 .github/
│   └── workflows/
│       └── docker.yml                 # GitHub Actions Docker build workflow
└── 📁 src/
    └── nonebot_plugin_quark_autosave/
        ├── __init__.py                # Plugin main logic: link matching → save pipeline
        ├── client.py                  # QAS API async client (with retry)
        ├── config.py                  # Pydantic configuration model
        ├── model.py                   # Data models: TaskItem / DetailInfo / Addition
        └── exception.py               # Custom exception: QASException
```

---

## 🔄 How It Works

```
User sends Quark link ──→  Validate link format
                         │
                   Fetch share details (get root folder name)
                         │
                   Build save task (enable Aria2 auto-download)
                         │
                   Add task → Run save script → Delete task
                         │
                   Reply "Done" ✅
```

---

## 🚀 Quick Start

### 🐳 Docker

```bash
docker run -d \
  --name quarkbot \
  -e TELEGRAM_BOT_TOKEN=*** \
  -e SUPERUSER="your_telegram_user_id" \
  -e QAS_ENDPOINT="http://your-qas-address:5005" \
  -e QAS_TOKEN=*** \
  -e TZ=Asia/Shanghai \
  --restart unless-stopped \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  lzylipu/quarkbot:latest
```

### 📦 Docker Compose (Recommended)

The project includes a `compose.yml` that orchestrates both the Bot and the QAS service with internal networking:

```bash
cp .env.example .env   # Edit .env with your configuration
docker compose up -d
```

> 💡 In Compose mode, `QAS_ENDPOINT` defaults to `http://quark-auto-save:5005` via Docker internal network — no port exposure needed.

---

## ⚙️ Environment Variables

**Bot Service**

| Variable | Required | Default | Description |
|----------|:--------:|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | ✅ | | Telegram Bot Token from [@BotFather](https://t.me/BotFather) |
| `SUPERUSER` | ✅ | | Telegram User ID from [@userinfobot](https://t.me/userinfobot) |
| `QAS_ENDPOINT` | ✅ | `http://quark-auto-save:5005` | QAS service address; change to actual address for standalone deploy |
| `QAS_TOKEN` | ✅ | | QAS API key |
| `SIMPLE_SAVE_ROOT` | | `auto` | Root folder name for saving to Quark drive |

---

## 🗄️ QAS Service Variables

The Compose setup includes a QAS service (`cp0204/quark-auto-save:latest`). The following variables control its behavior:

| Variable | Required | Default | Description |
|----------|:--------:|---------|-------------|
| `QAS_PORT` | | `5005` | QAS WebUI port mapping |
| `QAS_WEBUI_USER` | | `admin` | QAS WebUI username |
| `QAS_WEBUI_PASS` | | | QAS WebUI password (recommended to set) |

---

## 💬 Chat Example

```
You:  https://pan.quark.cn/s/xxxxxxxx
Bot:  Saving…
Bot:  Done
```

---

## 🔧 BotFather Setup

For the bot to read **all messages** you send (not just `/` commands), you need to disable privacy mode in BotFather:

1. Open [@BotFather](https://t.me/BotFather) 🤖
2. Send `/setprivacy`
3. Select your Bot
4. Select **Disable** 🔓

---

## 🛠️ Tech Stack

| Component | Version / Description |
|-----------|----------------------|
| 🐍 Python | 3.12 |
| 🤖 [NoneBot2](https://v2.nonebot.dev/) | Async bot framework (FastAPI + httpx driver) |
| 📡 [nonebot-adapter-telegram](https://github.com/nonebot/adapter-telegram) | Telegram adapter |
| 🌐 [httpx](https://www.python-httpx.org/) | Async HTTP client (keepalive + auto-retry) |
| 💾 [Quark Auto Save](https://github.com/Cp0204/quark-auto-save) | Quark Cloud auto-save backend service |
| ⬇️ Aria2 | Built-in auto-download support |

---

## 🙏 Acknowledgements

- 💜 [Cp0204/quark-auto-save](https://github.com/Cp0204/quark-auto-save) — Quark Cloud auto-save backend
- 🎯 [fllesser/nonebot-plugin-quark-autosave](https://github.com/fllesser/nonebot-plugin-quark-autosave) — Original NoneBot plugin
- 🤖 [NoneBot2](https://v2.nonebot.dev/) — Async bot framework

---

## 📄 License

This project is licensed under the [MIT License](./LICENSE).
