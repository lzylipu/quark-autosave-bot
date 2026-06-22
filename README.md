# Quark AutoSave Bot

<div align="center">

[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/github/license/lzylipu/quark-autosave-bot.svg)](./LICENSE)
[![Docker](https://img.shields.io/docker/pulls/lzylipu/quarkbot)](https://hub.docker.com/r/lzylipu/quarkbot)

**Minimal Telegram bot for Quark cloud auto-save**

</div>

---

## Features

- **One-tap save**: Send `1` → link → done
- **Auto pipeline**: Parse → create task → execute → cleanup
- **Privacy-first**: Only responds to configured superuser
- **Docker-ready**: Single command deployment

## Quick Start

### Docker

```bash
docker run -d \
  --name quarkbot \
  -e SUPERUSER="your...en" \
  -e TELEGRAM_BOT_TOKEN="your...en" \
  -e QAS_ENDPOINT="http://your-qas:5005" \
  -e QAS_TOKEN="your...en" \
  --restart unless-stopped \
  lzylipu/quarkbot:latest
```

### Docker Compose

```bash
cp .env.example .env  # fill in your values
docker compose up -d
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|:--------:|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | ✓ | | Bot token from [@BotFather](https://t.me/BotFather) |
| `SUPERUSER` | ✓ | | Your Telegram user ID from [@userinfobot](https://t.me/userinfobot) |
| `QAS_ENDPOINT` | ✓ | | QAS service URL |
| `QAS_TOKEN` | ✓ | | QAS API token |
| `SIMPLE_COMMAND` | | `1` | Trigger command |
| `SIMPLE_SAVE_ROOT` | | `auto` | Save root folder name |

## Usage

```
You: 1
Bot: continue
You: https://pan.quark.cn/s/xxxxx
Bot: done
```

## Setup

Disable privacy mode in [@BotFather](https://t.me/BotFather): `/setprivacy` → select bot → `Disable`.

## Credits

- [Cp0204/quark-auto-save](https://github.com/Cp0204/quark-auto-save) - Backend service
- [fllesser/nonebot-plugin-quark-autosave](https://github.com/fllesser/nonebot-plugin-quark-autosave) - Original plugin
- [NoneBot2](https://v2.nonebot.dev/) - Bot framework

## License

[MIT](./LICENSE)
