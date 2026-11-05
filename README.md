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
- 📏 **按集大小筛选** — 优先挑「每集都在 1.5~8G」的分享；实在没有（4K 压得小的剧）才退一档用每集 ≥0.5G 的，并在回执里说明
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
列表             → 查看订阅列表和上次结果
del 甄嬛传       → 取消订阅
执行             → 不用等到点，立刻跑一轮全部订阅
执行 甄嬛传      → 只跑这一部
```

`LIST` / `DL` 这两个旧写法仍然能用，和「列表」/「del」是同一个命令。

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

> ⚠️ **必须挂 `/app/data` 卷**。订阅列表、TG 会话绑定都在 `/app/data/subscriptions.json`，
> 不挂卷的话 `docker rm` / 升级镜像重建容器时**全部丢失**，只能重新 `AD 片名`。
> 启动日志里如果看到「`/app/data` 没有挂载卷」，就是这个原因。
>
> 绑定宿主机目录**不用管权限**：镜像启动时会自己把 `/app/data` 的属主改成运行用户
> （uid 1000）再降权运行，目录属主是 root 也照跑。
>
> ```bash
> mkdir -p /volume1/docker/quarkbot/data
> # compose 里写  - /volume1/docker/quarkbot/data:/app/data
> ```
>
> 只有 NFS/SMB/cifs 这类改不了属主的挂载点才会退回以 root 运行，功能不受影响。

```bash
docker run -d \
  --name quarkbot \
  -v quarkbot-data:/app/data \
  -e TELEGRAM_BOT_TOKEN=*** \
  -e QAS_ENDPOINT="http://你的QAS地址:5005" \
  -e QAS_TOKEN=*** \
  -e TZ=Asia/Shanghai \
  --restart unless-stopped \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  lzylipu/quarkbot:latest
```

> ⚠️ **同一个 Bot Token 只能跑一个实例**。两个容器（比如正式一个、测试一个）同时用同一个
> token 长轮询，Telegram 会返回 `409 Conflict: terminated by other getUpdates request`，
> 两边互相踢，表现就是「机器人时好时坏、忽然不理人」。旧容器要 `docker stop` 掉再起新的。

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
| `SUB_MAX_CANDIDATES` | | `0` | 每个订阅最多检查多少个搜索结果；`0`=搜到多少看多少（热门资源常排在几十条之后） |
| `SUB_MAX_OK_CANDIDATES` | | `1` | 找到这么多个合格分享就停止继续扫（默认 1=扫到符合条件就下，不再往后翻）；`0`=扫完全部再挑最全的 |
| `SUB_FALLBACK_MIN_SIZE_GB` | | `0.5` | 全部都不在区间内时退一档的下限：每集中位数 ≥ 这个值就当正片下（挡枪版） |
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

### v0.5.2

- 🗣 **命令改成中文更好记**：`列表` 看订阅、`del 片名` 取消订阅（`LIST` / `DL` 老写法仍可用）
- ⚡ **`执行` 立刻跑一轮**：不用等到 17:00，`执行 片名` 只跑那一部；正在跑的时候再发不会重复跑
- 🐞 **修掉整轮报告全丢**：手写的 `subscriptions.json` 把 `__chat_id__` 写成数字时，取会话 ID 会抛异常，整轮定时任务被标失败、结果一条都发不出去
- 🧪 新增 7 个单测（中文命令 / 旧写法兼容 / 相似词不误触 / 只跑指定订阅 / 两种会话 ID 写法），共 138 passed

### v0.5.1

- 🧩 **同一分享里两种写法都能转**：`幻视任务.S01E07.mkv` 和裸 `E06.mkv` 混在一起时，以前只认一种，7 集只转了 1 集；现在本季标记可有可无，别的季仍然一个都不碰
- 🛡 **目录不存在不再「借」别的剧的集**：QASx 对不存在的保存目录会静默回退到父目录（传 `/自动/某剧` 返回 `/自动` 的内容），以前会把隔壁剧的文件当成本剧已有的集，导致该补的集永远不补
- 🔌 **Telegram 断线自愈**：长轮询在启动阶段（`get_me`/`delete_webhook`）断一次，adapter 的 poll 任务就直接结束、进程还活着但再也收不到消息；现在断了一律 10 秒后重连。官方 API 本身也会抖，这层必须有
- 🧪 新增 5 个单测（混排两种写法 / 父目录回退 / 断线重试），共 131 passed

### v0.5.0

- 🎯 **选源改成「缺的集必须它全有」**：本地 E01~E10、该补 E11+E12 时，只有 E12 的链接直接跳过，继续找 E11+E12 那条。以前只要有一集新就下单，漏掉的那集永远补不上
- 🕳 **本地被手动删掉的中间集也算缺**：优先挑全集分享把 E06/E07 这种空洞一起补回来，只收更新包补不上
- ⚠️ 一个能补全的链接都没有时，仍然下载，但报告里写明「这条缺 E11（1 集）」，不假装成功
- 🔒 **没写季就锁第一季**：美剧 S01/S02/S03 不再混在一起算缺集（以前会「订第二季、下第一季第 10 集」）。要看第二季写 `AD 某剧 S02`
- 🚫 分享里带季标记但没有目标季 → 直接跳过看下一条，不硬猜、不白建任务
- 🧪 新增 5 个单测（缺集跳过 / 找不到全的报缺 / 锁第一季 / 别季跳过 / 补空洞），共 126 passed

### v0.4.7

- 🎞 **不再只认 mp4/mkv**：`avi`/`ts`/`rmvb`/`mov`/`m2ts` 等视频格式也能转存（以前这些集被 pattern 挡掉，永远补不上）
- 🔠 `.MKV`/`.MP4` 这种大写后缀也认（QASx 是 `re.search` 不带 flags，靠内联 `(?i:)` 解决）
- ♻️ **开启 QASx 的「忽略后缀」**：同一集已有 `S01E05.mkv` 时，再来 `S01E05.mp4` 不再重复存一份
- 🧪 新增 3 个单测（其它视频格式 / 大写后缀 / 海报字幕不误转），共 121 passed

### v0.4.6

- 🔧 **不用再手动 `chown`**：镜像改为 root 启动，`start.sh` 自己把 `/app/data` 交给运行用户（uid 1000）再降权运行，宿主机目录属主是 root 也直接能写
- 🧯 NFS/SMB/cifs 这类改不了属主的挂载点自动退回 root 运行，功能不受影响，日志里会说明
- 📄 README 去掉 `chown -R 1000:1000` 的手动步骤

### v0.4.5

- 🗂 启动时主动创建 `subscriptions.json`（内容 `{}`）并检查目录可写：以前只有第一次写订阅才落文件，挂了卷看到空目录会以为没生效
- 🚨 目录属主不对 / 只读挂载时启动就报错（日志 + TG），不用等某天发 `AD` 才发现存不上
- 🧪 新增 3 个单测（自动创建 / 保留已有 / 不可写报错），共 118 passed

### v0.4.4

- 🩹 会话绑定写不进去（`/app/data` 只读）时不再把 `AD` 命令搞崩：一句提示「会话绑定没存下来」，订阅照存
- 🧪 新增 1 个单测（写失败返回 False 不抛异常），共 115 passed

### v0.4.3

- 💾 **订阅不会因为升级/重启丢了**：README 里的 `docker run` 示例原来没有 `-v`，容器一重建 `/app/data/subscriptions.json` 就跟着消失。现在示例带 `-v quarkbot-data:/app/data`，并加了一节红字提醒「必须挂卷」
- 🚨 没挂卷会在启动日志和 TG 里直接喊（`/app/data` 没有挂载卷），`LIST` 也会显示「已挂卷/没挂卷」，不用等丢完才发现
- 🛟 写订阅改成「临时文件 + 原子替换」，每次保存前把上一份留成 `subscriptions.json.bak`；主文件写坏了自动从备份读回
- 🧪 新增 6 个单测：备份留存 / 半截文件回退备份 / 无残留临时文件 / 挂卷检测与提示文案

### v0.4.2

- ⏹️ 扫到符合条件就停，不再把整张搜索结果表跑完：`SUB_MAX_OK_CANDIDATES` 默认 `1`。合格 = 片名对得上 + 每集大小在区间 + 本地确实缺这集；集数不够或大小不对都算不合格，继续往后看，一旦碰到合格的立刻下。原来 v0.4.1 要扫完全部 170 多条才挑，纯浪费时间
- ⚡ 探详情按 4 个一批：命中早的剧一两秒就下完，同批 4 个探完再挑集数最多的那个，不吃亏
- 📊 日志写明「找到 N 个合格分享，共探 X 个，停止继续扫描」，一眼能看出停在哪

### v0.4.1

- 🔎 一度改成扫完全部搜索结果再挑（`SUB_MAX_OK_CANDIDATES=0`）；v0.4.2 又改回「扫到合格就停」，因为全集扫描只是白等
- ⚡ 探详情改并发：尚公主 169 条结果从 90 秒压到十几秒
- 📊 报告里的「检查了 N 个分享」现在统计的是真正探成功的数量

### v0.4.0

- 🔍 订阅不再只看前 10 个分享：`SUB_MAX_CANDIDATES` 默认 `0`（搜到多少看多少）。走马上任 71 条结果里前 10 条全不合格、第 25 条才有 1.5~8G 的，原来直接报「检查了 10 个分享，都不在 1.5~8.0G 区间」
- ⏹️ 默认把搜索结果扫完再挑「集数最全」的那份，不拿到第一个合格的就下；探详情改成 4 路并发，170 多条结果从两分钟压到十几秒
- 🎯 片名对不上不下：盘搜会把同档期别的剧混进结果（尚公主 曾选中 7.85G 的《黄金时段/Primetime》），现在按「搜索结果标题 + 文件名」匹配片名，匹配不上的一律不参与选择
- ⚖️ 区间外偏小的正片也能下：全都不在 1.5~8G 时退一档，用每集中位数 ≥ `SUB_FALLBACK_MIN_SIZE_GB`（默认 0.5G）的分享，报告里标明「改用每集 X G（画质可能一般）」；0.3G 的枪版仍然不要
- 📊 失败报告说清原因：检查了多少个、几个链接失效、几个没有视频、实测每集中位数区间
- 🐞 修「纯数字文件名一集都转不了」：`01.mkv`~`08.mkv` 这种分享原来一个文件都匹配不上命名规则，任务报成功但落 0 个文件（我的阿勒泰 8 集真机复现）；`24-4K-S.mp4` 这类改写名也能认了
- 🔢 「新增几集」只算真会转存的那几集：法警小队 曾报「新增 15 集」实际只落 3 个
- ✅ 新增 4 个单测；真机用走马上任（9 集）、尚公主（24 集）、伟大的长征（39 集）、幻视任务、法警小队、黑帮领地六个订阅验过选源，法警小队真转存 2 集并删任务

### v0.3.1

- 🎯 订阅名写死季数时只下这一季：`AD 黑镜 S05` 之前会选中第七季的分享，把 `S07E01~E06` 当成「第五季缺的集」全下进来（真机复现）
- 🏷️ 写死季的订阅，任务 `pattern` 同时当筛选条件用，合集分享里别的季不会再被转存
- 💬 订阅结果先落日志再写订阅文件：订阅文件不可写时不再让整轮报「执行失败」，报告照常发出
- 🧪 `tests/e2e` 从 pytest 收集里排除（那些是连真机 QAS 的验收脚本，会让 CI 直接中断），CI 恢复绿色
- ✅ 新增 3 个单测覆盖上面两个缺陷；真机用《甄嬛传》76 集、《黑镜 S05》3 集验收

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
