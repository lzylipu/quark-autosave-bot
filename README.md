# Quark AutoSave Bot

<div align="center">

[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/github/license/lzylipu/quark-autosave-bot.svg)](./LICENSE)
[![Docker](https://img.shields.io/docker/pulls/lzylipu/quarkbot)](https://hub.docker.com/r/lzylipu/quarkbot)

**极简夸克网盘转存 Telegram 机器人**

</div>

---

## 简介

基于 [NoneBot2](https://v2.nonebot.dev/) 的 Telegram 机器人，配合 [quark-auto-save](https://github.com/Cp0204/quark-auto-save) 实现夸克网盘链接自动转存。

**特点**：
- 极简交互：发送 `1` → `继续` → 发送链接 → `好了`
- 全自动：自动解析、创建任务、执行、清理
- 私密安全：仅响应设定的超级用户

---

## 快速开始

### Docker 部署

```bash
docker run -d \
  --name quarkbot \
  -e SUPERUSER="你的Telegram用户ID" \
  -e TELEGRAM_BOT_TOKEN="你的Bot Token" \
  -e QAS_ENDPOINT="http://你的QAS地址:5005" \
  -e QAS_TOKEN="你的QAS Token" \
  --restart unless-stopped \
  lzylipu/quarkbot:latest
```

### Docker Compose

```yaml
services:
  quarkbot:
    image: lzylipu/quarkbot:latest
    container_name: quarkbot
    environment:
      SUPERUSER: "你的Telegram用户ID"
      TELEGRAM_BOT_TOKEN: "你的Bot Token"
      QAS_ENDPOINT: "http://quark-auto-save:5005"
      QAS_TOKEN: "你的QAS Token"
    restart: unless-stopped
```

---

## 环境变量

| 变量 | 必填 | 说明 |
|------|:----:|------|
| `TELEGRAM_BOT_TOKEN` | ✓ | Bot Token（从 [@BotFather](https://t.me/BotFather) 获取）|
| `SUPERUSER` | ✓ | 用户 ID（从 [@userinfobot](https://t.me/userinfobot) 获取）|
| `QAS_ENDPOINT` | ✓ | QAS 服务地址 |
| `QAS_TOKEN` | ✓ | QAS API Token |
| `SIMPLE_COMMAND` | | 触发指令，默认 `1` |
| `SIMPLE_SAVE_ROOT` | | 保存根目录，默认 `自动` |

---

## 使用方法

```
你：1
机器人：继续
你：https://pan.quark.cn/s/xxxxx
机器人：好了
```

---

## 重要设置

在 [@BotFather](https://t.me/BotFather) 执行 `/setprivacy` → 选择机器人 → `Disable`，关闭隐私模式。

---

## 致谢

- [Cp0204/quark-auto-save](https://github.com/Cp0204/quark-auto-save) - 后端服务
- [fllesser/nonebot-plugin-quark-autosave](https://github.com/fllesser/nonebot-plugin-quark-autosave) - 原始插件
- [NoneBot2](https://v2.nonebot.dev/) - 机器人框架

## 许可证

[MIT License](./LICENSE)
