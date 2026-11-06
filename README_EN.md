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
- 📏 **Per-Episode Size Filter** — prefers shares where every episode falls in 1.5~8 GB; when none exists (heavily compressed 4K) it falls back to episodes ≥0.5 GB and says so in the reply. Posters and extras don't affect the check
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

> ⚠️ **Mount `/app/data` before anything else.** Subscriptions and the Telegram chat
> binding live in `/app/data/subscriptions.json`. Without the volume, `docker rm` or
> upgrading the image wipes them and you have to re-send `AD <title>` for every show.
> If the startup log says "/app/data is not a mounted volume", that is exactly this.
>
> **No permission fiddling needed** for a bind mount: on startup the container hands
> `/app/data` to its runtime user (uid 1000) and then drops privileges, so a
> root-owned host directory works as-is.
>
> ```bash
> mkdir -p /volume1/docker/quarkbot/data
> # compose:  - /volume1/docker/quarkbot/data:/app/data
> ```
>
> Only filesystems that refuse ownership changes (NFS/SMB/cifs) fall back to running
> as root; everything still works.

```bash
docker run -d \
  --name quarkbot \
  -v quarkbot-data:/app/data \
  -e TELEGRAM_BOT_TOKEN=*** \
  -e QAS_ENDPOINT="http://your-qas-address:5005" \
  -e QAS_TOKEN=*** \
  -e TZ=Asia/Shanghai \
  --restart unless-stopped \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  lzylipu/quarkbot:latest
```

> ⚠️ **One bot token = one instance.** Two containers long-polling with the same token make
> Telegram answer `409 Conflict: terminated by other getUpdates request`; they keep kicking each
> other and the bot looks flaky or mute. Stop the old container before starting a new one.

### 📦 Docker Compose (recommended)

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
列表 (or LIST)    → list subscriptions and their last result
del Downton       → unsubscribe
执行 (or RUN)     → run one round now instead of waiting for the scheduled time
执行 Downton      → run that single subscription
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
| `SUB_MAX_CANDIDATES` | | `0` | Max search results checked per subscription; `0` = scan all (good copies often rank dozens deep) |
| `SUB_MAX_OK_CANDIDATES` | | `1` | Stop scanning once this many usable shares were found (default 1 = take the first match instead of paging through everything); `0` = scan all results, then pick the fullest |
| `SUB_FALLBACK_MIN_SIZE_GB` | | `0.5` | Fallback floor: when nothing is in range, accept shares whose median episode is at least this size |
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
| Task created, but QAS saves nothing and only prints "no new files to save" | The task had no `update_subdir`, so QASx refuses to recurse into a share that is "folder inside folder" and concludes there is nothing new | Always set `update_subdir=".*"` on created tasks (same share: 0 files → 2 mkv files actually landed) |
| Subscription counts "episodes already downloaded" as 0 and re-downloads forever | QASx mirrors the share tree on disk (`/auto/<show>/<subdir>/x.mkv`); reading only the top level sees no files | `list_savepath_files` walks sub-directories |
| A deleted task reappears in the config seconds later | QASx `/update` spawns background threads (metadata match, calendar init) that dump the whole config back, restoring the deleted task | Create the task with `skip_calendar=true` (QASx's one-shot marker; `app/run.py:3189` skips calendar matching, so those writers never run); the post-delete re-read loop stays as a safety net |
| File deletion succeeds but raises "unknown error" | `/delete_file` does not wrap its response in `{success,data}` — it returns Quark's raw `{status,code}`, and it is asynchronous | Treat `code==0` as success; re-read the folder yourself to confirm |
| Repeating a save test on the same share prints "no new files" | QASx keeps a transfer-record DB keyed by `file_id + taskname` | Expected (prevents duplicate copies); self-test scripts use a unique task name and folder per run |

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

### v0.5.6

- 🎬 **Episode 0 / previews are no longer treated as episodes**: shares containing `第00集`, `E00` or `00.mkv` used to produce a phantom "missing E00", so that share was re-selected every round and files were written again and again — it could never finish (measured live: two consecutive rounds both reported "added E00"). Episode 0 is now excluded from episode parsing
- 🧪 3 new assertions (`第00集` / `E00` / `00.mkv`), 152 passed

### v0.5.5

- 🗂 **Only folders holding the videos themselves are selected**: a nested share's root often contains nothing but version folders. Pointing a task at that root makes QASx recurse into the subfolders, and its dedupe inside a subfolder only compares against that subfolder — so episodes already stored locally get copied again (measured on a live instance: 27 episodes at the top level of one show, plus 11 more under `4K DV 60帧` and 5 under `4K SDR 60帧`). Candidates are now scored on each folder's own files and the task points at the folder that really holds the videos
- 🎯 **Exactly one file per episode**: transferring a whole share re-downloads episodes already present, and Quark appends `.1` to duplicate names; the task pattern is narrowed to the episodes actually missing, so existing files are never touched again
- 🔁 **The share that can complete the missing episodes wins**: a share covering every missing episode is preferred; when none does, the best partial one is transferred and the rest is left to the next round or the next share — never dumping the entire parent directory just to transfer everything at once
- ⬇️ **Subtree fallback only for hollow folders**: if no layer exposes direct files and content lives deeper, the subtree is still expanded — a folder with no files is never a reason to give up
- 🧪 3 new regressions (hollow root picks the child folder / nested variants already local are not re-downloaded / hollow-only share falls back to the subtree), 151 passed

### v0.5.4

- 📂 **Nested shares are selected per folder level**: `#/list/share/<fid>` folders are fully expanded and assessed independently. When the root combines several quality variants, the bot selects a complete child folder with one file per episode instead of transferring the flattened tree
- 🎯 **Only genuinely missing episodes are transferred**: the QASx task `pattern` is narrowed to an episode allowlist, so episodes already stored locally are not downloaded again and duplicates such as `S01E07.1.mkv` are avoided
- 🧩 **Existing nested share URLs remain expandable**: a search result already pointing to `https://pan.quark.cn/s/...#/list/share/<fid>` can still be scanned for deeper folders
- 🧪 Added regression coverage for nested quality variants, nested-URL entry points and missing-episode-only transfers, 148 passed

### v0.5.3

- 🐞 **"No new files to transfer" no longer means nothing happened**: QASx dedupes on `file_id + task name`, so once the cloud files are deleted while the transfer records remain, that show can never be downloaded again (real case: all 11 episodes of a show were in the records while its folder was empty — every run answered "no new files")
- 🧹 **Stale records are cleaned automatically**: only records with the same task name, the same save path and an episode that is genuinely gone locally are removed — other shows, paths and seasons are untouched
- 🔁 **Zero files landed means try the next share**: after a transfer the folder is re-read and counted; if nothing landed the next candidate share is tried (up to 3), and if all fail the report says so instead of pretending success
- ⚠️ **Warning when one episode ships twice**: a share containing both `07.mkv` and `S01E07.mkv` looks like two episodes to QASx, so one extra file lands — now called out in the report
- 🧪 5 new unit tests (record-clearing boundaries / share retry / all-failed report / duplicate warning / fake landed-file simulation), 143 passed

### v0.5.2

- 🗣 **Friendlier commands**: `列表` lists subscriptions, `del <title>` unsubscribes (`LIST` / `DL` still work)
- ⚡ **`执行` runs a round right now** — no need to wait for 17:00; `执行 <title>` runs just that one, and a second request while one is running is ignored
- 🐞 **A whole round of reports could vanish**: when a hand-written `subscriptions.json` stored `__chat_id__` as a plain number, reading it raised and the scheduled run was marked failed with nothing delivered
- 🧪 7 new unit tests (Chinese commands / legacy aliases / lookalike words ignored / single-subscription run / both chat-id shapes), 138 passed

### v0.5.1

- 🧩 **Both naming styles in one share are transferred**: with `Show.S01E07.mkv` and bare `E06.mkv` mixed together, only one style used to match and just 1 of 7 episodes was transferred. The season marker is now optional while other seasons are still excluded
- 🛡 **A missing folder no longer borrows another show's episodes**: QASx silently falls back to the parent folder for a nonexistent save path (`/auto/show` returns `/auto`). Those files used to be counted as "already have", so the pending episodes were never filled in
- 🔌 **Telegram polling self-heals**: when the long poll fails during startup (`get_me`/`delete_webhook`), the adapter's poll task dies and the process stays alive but stops receiving messages. It now retries every 10 seconds — the official API itself has hiccups
- 🧪 5 new unit tests (mixed naming / parent fallback / reconnect), 131 passed

### v0.5.0

- 🎯 **A share must contain every pending episode**: local E01~E10 needing E11+E12 — a share with only E12 is skipped, scanning continues for one with both. Previously any single new episode triggered a download and the missing one was lost forever
- 🕳 **Episodes deleted by hand also count as pending**: a full-set share is preferred so gaps like E06/E07 get filled instead of only the newest update pack
- ⚠️ When no share covers everything, it still downloads but reports exactly what is missing ("this share lacks E11"), instead of pretending success
- 🔒 **No season written = season 1 only**: US shows no longer mix S01/S02/S03 into one pending set (which used to download S01E10 when S02 was wanted). Write `AD Show S02` for season 2
- 🚫 A share whose season markers never match the target season is skipped, not guessed
- 🧪 5 new unit tests, 126 passed

### v0.4.7

- 🎞 **Not just mp4/mkv anymore**: `avi`/`ts`/`rmvb`/`mov`/`m2ts` episodes are transferred too (the pattern used to filter them out, so those episodes could never be filled in)
- 🔠 Uppercase extensions like `.MKV`/`.MP4` now match (QASx calls `re.search` without flags, fixed with an inline `(?i:)` group)
- ♻️ **QASx "ignore extension" is now enabled**: when `S01E05.mkv` already exists, a later `S01E05.mp4` is not stored twice
- 🧪 3 new unit tests (other video formats / uppercase extensions / posters and subtitles still excluded), 121 passed

### v0.4.6

- 🔧 **No manual `chown` anymore**: the image now starts as root and `start.sh` hands `/app/data` to the runtime user (uid 1000) before dropping privileges, so a root-owned host directory just works
- 🧯 On filesystems that refuse ownership changes (NFS/SMB/cifs) it falls back to running as root; behavior is unchanged and the log says so
- 📄 README no longer asks you to run `chown -R 1000:1000`

### v0.4.5

- 🗂 `subscriptions.json` is created at startup (content `{}`) and the directory is checked for writability; previously the file only appeared on the first write, so a mounted-but-empty directory looked broken
- 🚨 Wrong ownership / read-only mount now fails loudly at startup (log + Telegram) instead of surfacing on the first `AD`
- 🧪 3 new unit tests (auto-create / keep existing / unwritable), 118 passed

### v0.4.4

- 🩹 When the chat binding cannot be written (`/app/data` read-only) the `AD` command no longer crashes; it reports "chat binding not saved" and still stores the subscription
- 🧪 1 new unit test (write failure returns False instead of raising), 115 passed

### v0.4.3

- 💾 **Subscriptions survive upgrades and restarts**: the `docker run` sample had no `-v`, so recreating the container wiped `/app/data/subscriptions.json`. It now ships with `-v quarkbot-data:/app/data` plus a red-box warning that the volume is mandatory
- 🚨 A container without the volume says so loudly at startup (log + Telegram), and `LIST` shows whether storage is mounted
- 🛟 Saves are atomic (temp file + replace) and keep the previous version as `subscriptions.json.bak`; a truncated main file is read back from the backup
- 🧪 6 new unit tests: backup retention / truncated-file fallback / no leftover temp file / mount detection and message

### v0.4.2

- ⏹️ Stops at the first usable share instead of scanning the whole result list: `SUB_MAX_OK_CANDIDATES` defaults to `1`. Usable = title matches + every episode within the size window + it really has episodes you are missing; a share with no new episodes or wrong sizes keeps scanning. v0.4.1 scanned all 170+ results before choosing, which was pure wasted time
- ⚡ Probes 4 shares per batch: shows that match early finish in a second or two, and when a batch has several usable shares the one with the most episodes wins
- 📊 Logs "found N usable shares after probing X, stop scanning" so you can see where it stopped

### v0.4.1

- 🔎 Briefly switched to scanning every result before choosing (`SUB_MAX_OK_CANDIDATES=0`); v0.4.2 goes back to "stop at the first usable one" because full scans just waste time
- ⚡ Share probing is concurrent: 169 results for one show dropped from 90s to a dozen seconds
- 📊 "checked N shares" in the report now counts the probes that actually succeeded

### v0.4.0

- 🔍 Subscriptions no longer stop at the first 10 shares: `SUB_MAX_CANDIDATES` now defaults to `0` (scan everything). For 《走马上任》 the first 10 of 71 results had no 1.5~8G copy; the qualifying share was #25
- ⏹️ Scans all results and picks the share with the most episodes instead of taking the first in-range one; detail probing runs 4-way concurrent, cutting a 170-result search from two minutes to seconds
- 🎯 Title must match: search results contain other shows from the same slot (《尚公主》 once picked a 7.85G 《黄金时段/Primetime》); matching now uses both the result title and the file names
- ⚖️ Smaller episodes can still download: when nothing is in range, fall back to shares whose median episode is at least `SUB_FALLBACK_MIN_SIZE_GB` (default 0.5G), and say so in the report; 0.3G cam-rips are still rejected
- 📊 Failure reports now state how many shares were checked, how many were dead links / had no videos, and the measured median size range
- 🐞 Fixed shares named purely by episode number transferring nothing: `01.mkv`~`08.mkv` never matched the rename pattern, so the task reported success while saving 0 files (reproduced live with 我的阿勒泰, 8 eps). Rewritten names like `24-4K-S.mp4` now match too
- 🔢 The reported episode count now counts only files that will actually transfer (法警小队 used to claim 15 eps and save 3)
- ✅ 4 new unit tests; verified on a live instance against six subscriptions (走马上任 9 eps, 尚公主 24 eps, 伟大的长征 39 eps, 幻视任务, 法警小队, 黑帮领地), with 法警小队 actually transferred (2 eps) and its task deleted

### v0.3.1

- 🎯 A subscription with an explicit season only saves that season: `AD 黑镜 S05` used to pick a season-7 share and save `S07E01~E06` as "missing episodes of season 5" (reproduced on a real instance)
- 🏷️ For season-locked subscriptions the task `pattern` also filters files, so other seasons in a multi-season share are not saved
- 💬 Subscription results are logged before the store write: an unwritable subscriptions file no longer fails the whole run, and the report is still delivered
- 🧪 `tests/e2e` excluded from pytest collection (those scripts hit a real QAS and aborted the whole CI session), CI is green again
- ✅ 3 new unit tests for the two bugs; verified on a real instance with 《甄嬛传》 (76 episodes) and 《黑镜 S05》 (3 episodes)

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
