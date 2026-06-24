<div align="center">

# 🍭 Quark AutoSave Bot

**Telegram Bot · Forward Quark Cloud links, auto-save to your own drive**

[![Python](https://img.shields.io/badge/python-3.12-blue.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![NoneBot2](https://img.shields.io/badge/NoneBot2-2.4+-orange.svg?style=flat-square)](https://v2.nonebot.dev/)
[![Docker](https://img.shields.io/docker/pulls/lzylipu/quarkbot?style=flat-square&logo=docker&logoColor=white)](https://hub.docker.com/r/lzylipu/quarkbot)
[![License](https://img.shields.io/github/license/lzylipu/quark-autosave-bot?style=flat-square)](./LICENSE)
[![GitHub](https://img.shields.io/badge/_repo-quark--autosave--bot-181717.svg?style=flat-square&logo=github&logoColor=white)](https://github.com/lzylipu/quark-autosave-bot)

简体中文 · [English](./README.en.md)

</div>

---

## 📖 Table of Contents

- [Features](#-features)
- [How It Works](#-how-it-works)
- [Quick Start](#-quick-start)
  - [Docker](#-docker)
  - [Docker Compose](#-docker-compose-recommended)
- [Environment Variables](#-environment-variables)
- [QAS Service Variables](#-qas-service-variables)
- [Chat Example](#-chat-example)
- [BotFather Setup](#-botfather-setup)
- [Tech Stack](#-tech-stack)
- [Acknowledgements](#-acknowledgements)
- [License](#-license)

---

## ✨ Features

- 🔗 **One-Click Save** — Just send a Quark Cloud sharing link — auto-saved instantly
- 🤖 **Telegram Native** — Send link directly, no trigger command needed
- 🐳 **Docker One-Command Deploy** — Image `lzylipu/quarkbot:latest`, up in 30 seconds
- 🧹 **Auto Cleanup** — Tasks are deleted after save completes, keeping the backend tidy
- 🔒 **Access Control** — Only the Superuser can trigger the bot

---

## 🔄 How It Works

```
User sends Quark link  ──→  Validate link format
                          │
                    Fetch share details
                          │
                    Add save task (aria2 auto-download)
                          │
                    Execute save script
                          │
                    Delete task & reply "Done"
```

---

## 🚀 Quick Start

### 🐳 Docker

```bash
docker run -d \
  --name quarkbot \
  -e TELEGRAM_BOT_TOKEN="your_bot_token" \
  -e SUPERUSER="your_telegram_user_id" \
  -e QAS_ENDPOINT="http://your-qas-host:5005" \
  -e QAS_TOKEN="your_qas_key" \
  -e TZ=Asia/Shanghai \
  --restart unless-stopped \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  lzylipu/quarkbot:latest
```

### 📦 Docker Compose (Recommended)

The project includes a `compose.yml` that orchestrates both the Bot and QAS service with internal networking:

```bash
cp .env.example .env   # Edit .env with your configuration
docker compose up -d
```

> 💡 In Compose mode, `QAS_ENDPOINT` defaults to `http://quark-auto-save:5005` via Docker's internal network — no need to expose the QAS port.

---

## ⚙️ Environment Variables

**Bot Service**

| Variable | Required | Default | Description |
|----------|:--------:|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | ✅ | | Telegram Bot Token from [@BotFather](https://t.me/BotFather) |
| `SUPERUSER` | ✅ | | Telegram User ID from [@userinfobot](https://t.me/userinfobot) |
| `QAS_ENDPOINT` | ✅ | `http://quark-auto-save:5005` | QAS service address; change to actual URL for standalone deployment |
| `QAS_TOKEN` | ✅ | | QAS API key |
| `SIMPLE_SAVE_ROOT` | | `auto` | Root folder name for saved files in your drive |

---

## 🗄️ QAS Service Variables

When using Compose, a QAS service (`cp0204/quark-auto-save:latest`) is included automatically:

| Variable | Required | Default | Description |
|----------|:--------:|---------|-------------|
| `QAS_PORT` | | `5005` | QAS WebUI port mapping |
| `QAS_WEBUI_USER` | | `admin` | QAS WebUI username |
| `QAS_WEBUI_PASS` | | | QAS WebUI password (recommended) |

---

## 💬 Chat Example

```
You:  https://pan.quark.cn/s/xxxxxxxx
Bot:  Saving...
Bot:  Done
```

---

## 🔧 BotFather Setup

For the bot to read **all messages** (not just `/` commands), disable privacy mode in BotFather:

1. Open [@BotFather](https://t.me/BotFather)
2. Send `/setprivacy`
3. Select your bot
4. Choose **Disable**

---

## 🛠 Tech Stack

| Component | Version / Notes |
|-----------|----------------|
| Python | 3.12 |
| [NoneBot2](https://v2.nonebot.dev/) | Async bot framework (FastAPI + httpx driver) |
| [nonebot-adapter-telegram](https://github.com/nonebot/adapter-telegram) | Telegram adapter |
| [httpx](https://www.python-httpx.org/) | Async HTTP client (keepalive + auto-retry) |
| [Quark Auto Save](https://github.com/Cp0204/quark-auto-save) | Quark Cloud auto-save backend service |

---

## 🙏 Acknowledgements

- [Cp0204/quark-auto-save](https://github.com/Cp0204/quark-auto-save) — Quark Cloud auto-save backend
- [fllesser/nonebot-plugin-quark-autosave](https://github.com/fllesser/nonebot-plugin-quark-autosave) — Original NoneBot plugin
- [NoneBot2](https://v2.nonebot.dev/) — Async bot framework

---

## 📄 License

This project is licensed under the [MIT License](./LICENSE).
