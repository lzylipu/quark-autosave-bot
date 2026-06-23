# 🍭 夸克自动存 — Telegram 机器人

> 📦 一键转发夸克网盘链接给你的机器人，自动存到你的网盘里 ✨

[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/github/license/lzylipu/quark-autosave-bot.svg)](./LICENSE)
[![Docker](https://img.shields.io/docker/pulls/lzylipu/quarkbot)](https://hub.docker.com/r/lzylipu/quarkbot)

---

## ✨ 它能做什么？

| 你发 | 机器人做 |
|------|---------|
| `1` | 进入"等待收链接"模式 🤖 |
| `夸克盘链接` | 解析 → 转存到你的网盘 → 自动清理 🎉 |
| 😴 不用管了 | 后台帮你跑完整个流程 |

---

## 🚀 跑起来（30秒）

### 🐳 Docker

```bash
docker run -d \
  --name quarkbot \
  -e SUPERUSER="你的TG用户ID" \
  -e TELEGRAM_BOT_TOKEN="BotFather给的token" \
  -e QAS_ENDPOINT="http://你的QAS地址:5005" \
  -e QAS_TOKEN="你的QAS密钥" \
  --restart unless-stopped \
  lzylipu/quarkbot:latest
```

### 📦 Docker Compose

```bash
cp .env.example .env   # 填上你的配置
docker compose up -d
```

就是这么简单 👆

---

## ⚙️ 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|:----:|--------|------|
| `TELEGRAM_BOT_TOKEN` | ✅ | | 去 [@BotFather](https://t.me/BotFather) 领一个 |
| `SUPERUSER` | ✅ | | 你的 TG 用户 ID，去 [@userinfobot](https://t.me/userinfobot) 查 |
| `QAS_ENDPOINT` | ✅ | | QAS 服务地址（内网直连 `http://10.10.0.2:5005`） |
| `QAS_TOKEN` | ✅ | | QAS API 密钥 |
| `SIMPLE_COMMAND` | | `1` | 触发指令，可以改成你喜欢的关键词 |
| `SIMPLE_SAVE_ROOT` | | `auto` | 转存到网盘的根目录文件夹名 |

---

## 💬 聊天示例

```
你:  1
机器人: 继续，发链接给我～

你:  https://pan.quark.cn/s/xxxxxxxx
机器人: 搞定 ✅
```

---

## 🔧 配置小贴士

在 [@BotFather](https://t.me/BotFather) 里关闭隐私模式：
`/setprivacy` → 选择你的 bot → `Disable`

这样机器人才能看到你发的消息 📨

---

## 🙏 感谢

- [Cp0204/quark-auto-save](https://github.com/Cp0204/quark-auto-save) — 后端服务
- [fllesser/nonebot-plugin-quark-autosave](https://github.com/fllesser/nonebot-plugin-quark-autosave) — 原始插件
- [NoneBot2](https://v2.nonebot.dev/) — 机器人框架

## 📄 License

[MIT](./LICENSE)
