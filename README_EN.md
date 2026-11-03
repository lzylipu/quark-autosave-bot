# 🍭 Quark AutoSave Bot

**Telegram Bot for Quark Cloud Auto-Save**

Forward Quark Cloud links and auto-save to your drive 🚀

English · [简体中文](./README.md)

---

## 📖 Table of Contents

- [✨ Features](#-features)
- [📂 Project Structure](#-project-structure)
- [🔄 How It Works](#-how-it-works)
- [🚀 Quick Start](#-quick-start)
  - [🐳 Docker](#-docker)
  - [📦 Docker Compose (Recommended)](#-docker-compose-recommended)
- [⚙️ Environment Variables](#️-environment-variables)
- [🗄️ QAS Service Notes](#️-qas-service-notes)
- [💬 Chat Example](#-chat-example)
- [🧪 Local Tests](#-local-tests)
- [🔧 BotFather Setup](#-botfather-setup)
- [🛠️ Tech Stack](#️-tech-stack)
- [📝 Changelog](#-changelog)
- [🙏 Acknowledgements](#-acknowledgements)
- [📄 License](#-license)

---

## ✨ Features

- 🔗 **One-Click Save** — Just send a Quark Cloud sharing link, auto-saved instantly
- 🔑 **Passcode Aware** — Links carrying `?pwd=xxxx` work as-is; otherwise the bot asks for the 4-character code once
- 🤖 **Telegram Native** — Send a link, no commands to remember
- 🐳 **Docker One-Command Deploy** — Image `lzylipu/quarkbot:latest`, up in 30 seconds
- 🧹 **No Leftover Tasks** — Deletes the QAS task by task name + share URL and re-reads `/data` to verify; failures are reported instead of silently swallowed
- 📁 **Save Path in Reply** — Tells you the destination folder and file count
- ♻️ **Duplicate Guard** — Re-sending the same link returns the previous result instead of running again
- ⏱️ **Overall Timeout** — A run exceeding `QAS_RUN_TIMEOUT` seconds is aborted with a clear message
- 🔁 **Auto Retry** — Network errors and 5xx/429 are retried with backoff
- 🔒 **Optional Access Control** — leave `SUPERUSER` empty and private chats just work; set it to pin the allowed IDs (groups are always ignored)
- ⬇️ **Aria2 Auto-Download** — Automatically downloads saved files via Aria2
- 📺 **Series Subscriptions** — `AD <title>` and every day at 17:00 the bot searches for fresh releases, fills in missing episodes and deletes the task
- 📏 **Per-Episode Size Filter** — only shares where every episode falls in 1.5~8 GB are used; posters and extras don't affect the check
- 🧩 **Episode Gap Filling** — scans the save folder for episodes you already have and transfers only what's missing
- 🏷️ **Consistent Naming** — saved files always carry a season prefix: `E05.mkv` or `第5集` → `S01E05.mkv`

---

## 📂 Project Structure

```
quark-autosave-bot/
├── 📄 bot.py                          # 🤖 NoneBot2 entry point, registers Telegram adapter
├── 🐳 Dockerfile                      # Docker image (Python 3.12-slim, runs as non-root)
├── 📦 compose.yml                     # Docker Compose orchestration (Bot + QAS service)
├── 📋 requirements.txt                # Pinned runtime dependencies
├── 📋 requirements-dev.txt            # Test dependencies
├── ⚙️ .env.example                    # Environment variable template
├── 🔧 start.sh                        # Startup script, generates .env.prod
├── 📄 pyproject.toml                  # Project metadata and tooling config
├── 📜 LICENSE                         # MIT License
├── 📖 README.md                       # Chinese documentation
├── 📖 README_EN.md                    # English documentation
├── 📁 .github/
│   └── workflows/
│       └── docker.yml                 # GitHub Actions: test first, then build & push
├── 📁 tests/
│   ├── conftest.py                    # NoneBot init (needed to import the plugin)
│   ├── test_result.py                 # Link extraction / parsing / error classification
│   ├── test_client_requests.py        # Retry, error messages, run payload, timeout
│   ├── test_client_cleanup.py         # Task deletion and verification
│   ├── test_perms.py                  # Access rules (empty SUPERUSER = private chat allowed)
│   ├── test_plugin_helpers.py         # Passcode prompt, dedupe cache
│   ├── test_subscribe.py              # Episode/season parsing, size filter, candidate pick
│   ├── test_subscription_flow.py      # Full subscription run (fake client)
│   ├── test_client_share_files.py     # Recursive share expansion (root is a folder)
│   ├── test_client_delete_safety.py   # Delete keeps unknown fields / survives null addition
│   └── e2e/                           # Scripts that hit a real QASx (see tests/e2e/README.md)
└── 📁 src/
    └── nonebot_plugin_quark_autosave/
        ├── __init__.py                # Pipeline: dedupe → verify → save → cleanup → report
        ├── client.py                  # QAS async client (retry / lock / timeout)
        ├── result.py                  # Share URL extraction, QAS output parsing, error classification
        ├── perms.py                   # Access rules
        ├── subscribe.py               # Subscriptions: parsing, filtering, scheduling
        ├── config.py                  # Pydantic configuration model
        ├── model.py                   # Data models: TaskItem / DetailInfo / Addition
        └── exception.py               # Custom exception: QASException
```

---

## 🔄 How It Works

```
User sends a Quark link ──→ Extract URL (keeps ?pwd= and #/ subfolder)
                          │
                    Dedupe check (in-flight / just finished)
                          │
                    Fetch share details ──passcode needed──→ ask for 4 chars
                          │
                    Build save task (whole week + Aria2 auto-download)
                          │
                    Add task → run (with overall timeout) → delete by identity + verify
                          │
                    Reply: done / partial / failed + save path
```

---

## 🚀 Quick Start

### 🐳 Docker

```bash
docker run -d \
  --name quarkbot \
  -e TELEGRAM_BOT_TOKEN=*** \
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
> The QAS WebUI is bound to `127.0.0.1:5005` only. Put it behind a reverse proxy if you need remote access; never expose it publicly.

---

### Series Subscriptions

```
AD Downton        → subscribe (AD 庆余年 S02 pins a season)
LIST              → list subscriptions and their last result
DL Downton        → unsubscribe
```

Every day at `SUB_CHECK_TIME` (default 17:00):

```
scan save folder ──→ episodes you already have (E05 / S01E05 / 第5集 all recognised)
                    │
        search the title (QASx aggregates PanSou / CloudSaver)
                    │
  for each candidate: read details → 1.5~8 GB filter → count new episodes
                    │
       pick the share covering the most missing episodes (skip if none qualify)
                    │
        add task (renamed to S01E05) → transfer → delete task
                    │
            reply: already have / newly added / save path
```

> Share links die every day or two; each run rebuilds the task from a freshly
> searched link, so nothing needs manual maintenance. Episodes already saved are
> skipped by QASx's own dedup (size + extension + mtime).

---

## ⚙️ Environment Variables

**Bot Service**

| Variable | Required | Default | Description |
|----------|:--------:|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | ✅ | | Telegram Bot Token from [@BotFather](https://t.me/BotFather) |
| `SUPERUSER` | | empty | Your Telegram User ID. Empty = anyone can use it in private chat; set = allow-list only |
| `QAS_ENDPOINT` | ✅ | `http://quark-auto-save:5005` | QAS service address; change to actual address for standalone deploy |
| `QAS_TOKEN` | ✅ | | QASx `api_token`: log into the WebUI, open `http://<qasx>/data`, copy the `api_token` field |
| `SIMPLE_SAVE_ROOT` | | `自动` | Root folder name for saving to Quark drive |
| `QAS_PATH_BASE` | | `夸克自动转存` | Root folder for template tasks (this bot uses `SIMPLE_SAVE_ROOT`) |
| `QAS_RUN_TIMEOUT` | | `1800` | Overall timeout per run in seconds |
| `DEDUPE_SECONDS` | | `600` | Window in which a repeated link returns the previous result |
| `ASK_PASSCODE` | | `true` | Ask for the passcode in chat when a share requires one |
| `SUB_CHECK_TIME` | | `17:00` | Daily subscription run time (HH:MM) |
| `SUB_MIN_SIZE_GB` | | `1.5` | Minimum size per episode in GB |
| `SUB_MAX_SIZE_GB` | | `8.0` | Maximum size per episode in GB |
| `SUB_MAX_CANDIDATES` | | `10` | Max search results checked per subscription |
| `SUB_STORE_FILE` | | `/app/data/subscriptions.json` | Subscription list path (`bot-data` volume in compose) |
| `ASK_PASSCODE` | | `true` | Ask for the passcode in chat when a share requires one |

---

## 🗄️ QAS Service Notes

The Compose setup includes a QAS service (`cp0204/quark-auto-save:latest`):

| Variable | Required | Default | Description |
|----------|:--------:|---------|-------------|
| `QAS_PORT` | | `5005` | QAS WebUI port (bound to localhost only) |
| `QAS_WEBUI_USER` | | `admin` | QAS WebUI username |
| `QAS_WEBUI_PASS` | | | QAS WebUI password (recommended) |

> ⚠️ QASx has no "API token" setting. It authenticates via a `?token=` query param derived from the WebUI username/password — the same value as `api_token` in `/data`. Log into the WebUI in a browser, then open `/data` and copy it.

---

## 💬 Chat Example

```
You:  https://pan.quark.cn/s/xxxxxxxx
Bot:  🔍 Checking link...
Bot:  📥 Show name (12 files)
Bot:  ✅ Saved, 12 files
      📁 /自动/Show name

You:  https://pan.quark.cn/s/yyyyyyyy?pwd=4f2a
Bot:  🔍 Checking link...
Bot:  📥 Movie name (1 file)
Bot:  ✅ Saved, 1 file
      📁 /自动/Movie name

You:  https://pan.quark.cn/s/zzzzzzzz        # passcode required
Bot:  🔑 This share needs a passcode, send the 4-character code (valid for 60s)
You:  4f2a
Bot:  📥 ... (continues normally)

You:  https://pan.quark.cn/s/xxxxxxxx        # already saved
Bot:  ♻️ Saved 42s ago, skipping
      📁 /自动/Show name
```

---

## 🧪 Local Tests

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests/ -q
```

No real QAS instance is needed: the request layer is stubbed with `httpx.MockTransport`, covering retry, error message preservation, run payload, overall timeout, and task deletion with verification.

### Against a real QASx

Unit tests prove the logic is self-consistent, not that the API matches. `tests/e2e/` holds
scripts that hit a real QASx instance — no Quark account needed except for the actual save step:

```bash
PYTHONPATH=src python3 tests/e2e/e2e_real_qasx.py       # API contract + task deletion (9 checks)
PYTHONPATH=src python3 tests/e2e/e2e_dirty_config.py    # dirty config / field preservation (11)
PYTHONPATH=src python3 tests/e2e/e2e_share_expand.py    # real recursive share expansion
```

How to launch a local QASx: see [`tests/e2e/README.md`](tests/e2e/README.md).

### Bugs found against the real instance (all fixed)

| Symptom | Root cause | Fix |
|---|---|---|
| Task deletion returns 500 on a real instance | QASx `sync_task_plugins_config()` calls `task["addition"].keys()`; a single `addition=null` in the config makes the whole `/update` fail | Normalise every `addition` to `{}` before writing; `add_task` no longer sends null |
| Calendar/plugin config lost after deletion | Reading and writing the config through pydantic drops fields QASx maintains (`calendar_info`, `source`, ...) | Read the raw dict, write back only `tasklist` |
| Subscription always says "no video files in share" | Share roots are usually a single folder; `/get_share_detail` returns only the current level | Recursively expand via `shareurl#/list/share/<fid>` (verified), bounded by depth and folder count |

---

## 🔧 BotFather Setup

For the bot to read **all messages** you send (not just `/` commands), disable privacy mode in BotFather:

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
| ⌛ [nonebot-plugin-waiter](https://github.com/RF-Tar-Railt/nonebot-plugin-waiter) | Passcode prompt |
| 🌐 [httpx](https://www.python-httpx.org/) | Async HTTP client (keepalive + retry) |
| 💾 [Quark Auto Save](https://github.com/Cp0204/quark-auto-save) | Quark Cloud auto-save backend service |
| ⬇️ Aria2 | Built-in auto-download support |

---

## 📝 Changelog

### v0.3.0

- 📺 Series subscriptions: `AD <title>` / `DL <title>` / `LIST`, daily auto-search and gap filling
- 📏 Per-episode size window filter (default 1.5~8 GB); posters and extras ignored
- 🧩 Scans the save folder for existing episodes and only adds the missing ones
- 🏷️ Per-task rename rule so files land as `S01E05` (S02 when the name says so)
- 🐳 New `bot-data` volume persists the subscription list
- ✅ 26 new unit tests: parsing, season split, candidate picking, full run orchestration

### v0.2.1

- 🐛 Auth failure was reported as "link expired" (`Cookie 已失效` matched both keyword sets, wrong order)
- 🔒 `SUPERUSER` is now optional: empty means private chats just work, no need to look up your ID first; groups never respond
- 💬 An unauthorized user who sends a link gets their Telegram ID back, ready to paste into the config
- 🐛 Fixed empty `SUPERUSER` producing `[""]`, which matched nobody
- ✅ 32 unit tests: error classification, access rules, passcode, dedupe, delete verification

### v0.2.0

- 🐛 Share links with `?pwd=xxxx` were truncated and always failed — fixed
- 🐛 QAS error messages were swallowed into a bare `HTTP 4xx` — real reasons now surface
- 🐛 Every `=` in run output was stripped — fixed
- 🐛 Tasks were not deleted after a successful save — now deleted by name + URL and verified by re-reading `/data`
- ✨ Passcode prompt, duplicate guard, save-path reply, login-expired hint
- ✨ Overall run timeout and 5xx/429 backoff retry
- 🔒 Serialized QAS config read-modify-write to avoid clobbering the task list
- 🏗️ CI runs tests before building; pinned dependencies; non-root image with HEALTHCHECK

### v0.1.9

- First usable release: forward a link, auto-save with Aria2 download

---

## 🙏 Acknowledgements

- 💜 [Cp0204/quark-auto-save](https://github.com/Cp0204/quark-auto-save) — Quark Cloud auto-save backend
- 🎯 [fllesser/nonebot-plugin-quark-autosave](https://github.com/fllesser/nonebot-plugin-quark-autosave) — Original NoneBot plugin
- 🤖 [NoneBot2](https://v2.nonebot.dev/) — Async bot framework

---

## 📄 License

This project is licensed under the [MIT License](./LICENSE).
