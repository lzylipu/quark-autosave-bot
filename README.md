# Quark AutoSave Bot

<div align="center">

[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/github/license/lzylipu/quark-autosave-bot.svg)](./LICENSE)
[![Docker](https://img.shields.io/docker/pulls/lzylipu/quarkbot)](https://hub.docker.com/r/lzylipu/quarkbot)

**Smart Telegram bot for Quark cloud auto-save with link validity check**

</div>

---

## Features

- **Direct link detection**: Send a Quark link, bot handles the rest. No command needed
- **Link validity check**: Automatically detects expired/deleted/invalid shares
- **Smart status feedback**: Precise status at every stage (checking, saving, done, failed)
- **Auto pipeline**: Check validity -> create task -> execute -> cleanup
- **Privacy-first**: Only responds to configured superuser
- **Docker-ready**: Single command deployment

## Usage

```
You: https://pan.quark.cn/s/xxxxx
Bot: Detecting link...
Bot: Title (3 files)
Bot: Save complete

You: https://pan.quark.cn/s/expired-link
Bot: Detecting link...
Bot: Link expired
```

Just send any message containing a `pan.quark.cn/s/xxx` link. No activation word, no timeout.

## Status Feedback

| Status | Reply | When |
|--------|------|------|
| Received | Detecting link... | Link found in message |
| Expired | Link expired | Share deleted/cancelled/expired |
| QAS error | QAS service error: detail | Cookie expired, QAS down |
| Check failed | Check failed: detail | Unknown QAS error |
| Saving | Title (N files) | Link valid, starting save |
| Save failed | Save failed: detail | add_task or run_script error |
| Partial | Partially done (some failed) | Script output has errors |
| Done | Save complete | Full pipeline success |
| Runtime error | Runtime error: detail | Unexpected exception |

## Prerequisites

> **This bot is a Telegram interface for [quark-auto-save](https://github.com/Cp0204/quark-auto-save) (QAS).**
> You MUST deploy QAS first - this bot alone does nothing.

### QAS (quark-auto-save) Required

[![Stars](https://img.shields.io/github/stars/Cp0204/quark-auto-save?style=social)](https://github.com/Cp0204/quark-auto-save)

QAS is the core engine that handles:
- Quark cookie management and sign-in
- Share link parsing and validity checking
- Auto-save to your Quark drive
- Aria2 auto-download
- Media library refresh (Alist/Emby/Strm)

| Item | |
|------|------|
| Project | [Cp0204/quark-auto-save](https://github.com/Cp0204/quark-auto-save) |
| Stars | 2.8k+ |
| Docker | `docker pull cp0204/quark-auto-save:latest` |
| Port | 5005 |
| Docs | [README](https://github.com/Cp0204/quark-auto-save#readme) |

**Quick deploy:**

```bash
docker run -d \
  --name qas \
  -p 5005:5005 \
  -v /path/to/config:/config \
  -v /path/to/downloads:/downloads \
  --restart unless-stopped \
  cp0204/quark-auto-save:latest
```

> After deploy, note the QAS API **endpoint** (e.g. `http://qas:5005`) and **token** from QAS web UI settings.

### NoneBot2

[![Stars](https://img.shields.io/github/stars/nonebot/nonebot2?style=social)](https://github.com/nonebot/nonebot2)

| Item | |
|------|------|
| Project | [nonebot/nonebot2](https://github.com/nonebot/nonebot2) |
| Stars | 7.5k+ |
| Docs | [v2.nonebot.dev](https://v2.nonebot.dev/) |

Bundled in the Docker image - no separate install needed.

## Quick Start

### Docker

```bash
docker run -d \
  --name quarkbot \
  -e SUPERUSER="your_telegram_user_id" \
  -e TELEGRAM_BOT_TOKEN="your_bot_token" \
  -e QAS_ENDPOINT="http://your-qas:5005" \
  -e QAS_TOKEN="your_qas_token" \
  --restart unless-stopped \
  lzylipu/quarkbot:latest
```

### Docker Compose

```bash
cp .env.example .env
docker compose up -d
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|:--------:|---------|-------------|
| TELEGRAM_BOT_TOKEN | Yes | | Bot token from [@BotFather](https://t.me/BotFather) |
| SUPERUSER | Yes | | Your Telegram user ID ([@userinfobot](https://t.me/userinfobot)) |
| QAS_ENDPOINT | Yes | | QAS service URL |
| QAS_TOKEN | Yes | | QAS API token |
| QAS_PATH_BASE | | default | Save base path |
| SIMPLE_SAVE_ROOT | | auto | Auto-save subfolder |

## BotFather Setup

Disable privacy mode: `/setprivacy` -> select bot -> **Disable**

This allows the bot to read all messages (needed for link detection).

## Architecture

```
Telegram User
     |  (sends Quark link)
     v
  This Bot (NoneBot2 + Telegram Adapter)
     |  1. Check link validity via QAS
     |  2. Auto-save if valid
     |  3. Report status to user
     v
  QAS (quark-auto-save)
     |  (parse -> save -> download)
     v
  Quark Drive / Aria2 / Media Server
```

## Credits

- [Cp0204/quark-auto-save](https://github.com/Cp0204/quark-auto-save) - Core engine (sign-in, auto-save, download, media refresh)
- [fllesser/nonebot-plugin-quark-autosave](https://github.com/fllesser/nonebot-plugin-quark-autosave) - Original NoneBot plugin
- [nonebot/nonebot2](https://github.com/nonebot/nonebot2) - Bot framework

## License

[MIT](./LICENSE)
