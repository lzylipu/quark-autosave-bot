# quark-autosave-bot

<div align="center">
    <a href="https://github.com/lzylipu/quark-autosave-bot">
        <img src="https://raw.githubusercontent.com/fllesser/nonebot-plugin-template/refs/heads/resource/.docs/NoneBotPlugin.svg" width="310" alt="logo">
    </a>
    <p>✨ 一个极简的夸克自动转存 Telegram 机器人 ✨</p>

[![Python Version](https://img.shields.io/badge/python-3.10|3.11|3.12|3.13-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/github/license/lzylipu/quark-autosave-bot.svg)](./LICENSE)
[![Docker Pulls](https://img.shields.io/docker/pulls/lzylipu/quarkbot)](https://hub.docker.com/r/lzylipu/quarkbot)

</div>

## 📖 项目介绍

**quark-autosave-bot** 是一个基于 [NoneBot2](https://v2.nonebot.dev/) 和 [Telegram Adapter](https://github.com/nonebot/adapter-telegram) 的极简机器人。它专为配合 [quark-auto-save (QAS)](https://github.com/Cp0204/quark-auto-save) 服务使用而设计，旨在提供一个**最简单、最直接**的夸克链接转存体验。

本项目从 [nonebot-plugin-quark-autosave](https://github.com/fllesser/nonebot-plugin-quark-autosave) 改造而来，专注于私聊场景下的自动化流程。

### ✨ 核心特性

*   **极致精简的交互**：告别繁琐的命令和参数。发送 `1` -> 机器人回复 `继续` -> 发送夸克链接 -> 机器人自动完成一切。
*   **全自动任务处理**：自动获取分享目录名、自动创建QAS任务、自动执行任务、并在完成后自动清理任务记录，整个过程无需人工干预。
*   **智能路径命名**：自动读取夸克分享链接的根目录名称，并将其作为QAS中的**任务名称**和**最终保存文件夹名**。
*   **固定的保存规则**：保存路径统一为 `/自动/分享根目录名称`，清晰明了，方便管理。
*   **安全私密**：仅响应你设定的Telegram超级用户指令，适合个人自用。

### 🎯 工作流程

当您与机器人交互时，背后会自动完成以下步骤：

| 步骤 | 操作方 | 动作 | 说明 |
|:----:|:------:|:-----|:-----|
| **1** | **用户** | 发送指令 `1` | 启动一次转存流程 |
| **2** | **机器人** | 回复 `继续` | 提示用户下一步 |
| **3** | **用户** | 发送夸克分享链接 | 例如 `https://pan.quark.cn/s/xxx` |
| **4** | **机器人** | 请求 QAS 解析链接 | 调用 QAS API 获取分享详情 |
| **5** | **QAS后端** | 返回根目录名称 | 例如 "电影XX" |
| **6** | **机器人** | 自动创建任务 | 任务名 = 根目录名称<br>保存路径 = `/自动/根目录名称` |
| **7** | **机器人** | 自动执行任务 | 仅执行刚创建的这一个任务 |
| **8** | **机器人** | 自动删除任务 | 清理临时任务记录 |
| **9** | **机器人** | 回复最终结果 | 成功回复 `好了`<br>失败回复 `错` |

---

## 💿 快速开始

### 🐳 使用 Docker (推荐)

这是最便捷的部署方式。

**前提条件**：
1.  一个可访问的 [quark-auto-save](https://github.com/Cp0204/quark-auto-save) 服务实例及其 `API Token`。
2.  一个 Telegram Bot Token (通过 [@BotFather](https://t.me/BotFather) 创建)。
3.  你的 Telegram 用户ID (通过 [@userinfobot](https://t.me/userinfobot) 获取)。

**运行容器**：

```bash
docker run -d \
  --name quarkbot \
  -e PORT=8080 \
  -e SUPERUSER="你的Telegram用户ID" \
  -e TELEGRAM_BOT_TOKEN="你的Bot Token" \
  -e QAS_ENDPOINT="http://你的QAS地址:5005" \
  -e QAS_TOKEN="你的QAS API Token" \
  --restart unless-stopped \
  lzylipu/quarkbot:latest
```

**使用 Docker Compose**：

创建 `compose.yml` 文件：

```yaml
services:
  quarkbot:
    image: lzylipu/quarkbot:latest
    container_name: quarkbot
    environment:
      PORT: 8080
      SUPERUSER: "你的Telegram用户ID"
      TELEGRAM_BOT_TOKEN: "你的Bot Token"
      QAS_ENDPOINT: "http://quark-auto-save:5005" # 如果QAS在另一个容器中，可使用服务名
      QAS_TOKEN: "你的QAS API Token"
      # QAS_PATH_BASE: "夸克自动转存"   # 可选，保持默认即可
      # SIMPLE_COMMAND: "1"            # 可选，自定义启动指令
      # SIMPLE_SAVE_ROOT: "自动"        # 可选，自定义保存根目录
    restart: unless-stopped
```

然后运行：
```bash
docker compose up -d
```

### ⚙️ 环境变量配置

| 变量名 | 必填 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | **是** | 无 | Telegram Bot Token |
| `SUPERUSER` | **是** | 无 | 允许使用机器人的Telegram用户ID |
| `QAS_ENDPOINT` | **是** | 无 | QAS服务地址，如 `http://192.168.1.10:5005` |
| `QAS_TOKEN` | **是** | 无 | QAS的API Token |
| `PORT` | 否 | `8080` | NoneBot2服务端口 |
| `SIMPLE_COMMAND` | 否 | `1` | 触发机器人的指令 |
| `SIMPLE_SAVE_ROOT` | 否 | `自动` | QAS中保存路径的根目录名 |
| `QAS_PATH_BASE` | 否 | `夸克自动转存` | 上游插件兼容字段，保持默认即可 |

### 📝 重要：Telegram Bot 设置

为了让机器人能够响应 `1` 这样的普通文本消息，你需要在 [@BotFather](https://t.me/BotFather) 处**关闭机器人的隐私模式**：

1.  向 BotFather 发送 `/setprivacy`。
2.  选择你的机器人。
3.  选择 `Disable`。

否则，机器人只能响应以 `/` 开头的命令。

## 🚀 使用示例

当一切就绪后，与机器人的对话将非常简单：

> **你**：`1`  
> **机器人**：`继续`  
> **你**：`https://pan.quark.cn/s/461b6af90a65`  
> **机器人**：`好了`  *(处理成功)*  
> 或  
> **机器人**：`错` *(处理失败)*

## ❓ 常见问题

**Q: 机器人运行了，但没有任何响应？**
A: 请按以下顺序排查：
1.  确认 `SUPERUSER` 配置的是正确的数字ID。
2.  确认已在 BotFather 处关闭了隐私模式 (`/setprivacy -> Disable`)。
3.  确认服务器网络可以正常访问 Telegram API。

**Q: 总是返回“错”，但QAS服务是好的？**
A: 请检查：
1.  `QAS_ENDPOINT` 和 `QAS_TOKEN` 是否正确无误。
2.  QAS服务能否正常解析你发送的夸克分享链接。
3.  QAS服务本身是否能正常执行转存任务。

**Q: 为什么在QAS的Web UI里看不到创建的任务？**
A: 这是设计使然。机器人采用“创建 -> 执行 -> 删除”的临时任务模式，任务执行完成后即被清理，不会在任务列表中留下记录。

**Q: 为什么保存路径不是我想要的？**
A: 当前版本为了极简体验，固定了保存路径规则为 `/SIMPLE_SAVE_ROOT/分享根目录名称`。如果你需要更灵活的配置，可以考虑使用上游功能更全的插件版本。

## 🏗️ 本地开发与运行

1.  **克隆仓库**
    ```bash
    git clone https://github.com/lzylipu/quark-autosave-bot.git
    cd quark-autosave-bot
    ```

2.  **创建虚拟环境**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # Linux/MacOS
    # .venv\Scripts\activate  # Windows
    ```

3.  **安装依赖**
    ```bash
    pip install -r requirements.txt
    # 或使用 pip install nonebot2[fastapi,httpx] nonebot-adapter-telegram nonebot-plugin-waiter httpx
    ```

4.  **配置环境变量**
    创建 `.env.prod` 文件：
    ```env
    HOST=0.0.0.0
    PORT=8080
    SUPERUSERS=["你的Telegram用户ID"]
    COMMAND_START=["/",""]

    DRIVER=~fastapi+~httpx

    telegram_bots=[{"token":"你的Bot Token"}]

    QAS_ENDPOINT=http://你的QAS地址:5005
    QAS_TOKEN=你的QAS API Token
    ```

5.  **运行机器人**
    ```bash
    python bot.py
    ```

## 🙏 致谢

*   [Cp0204/quark-auto-save](https://github.com/Cp0204/quark-auto-save) - 提供强大的后端支持。
*   [fllesser/nonebot-plugin-quark-autosave](https://github.com/fllesser/nonebot-plugin-quark-autosave) - 本项目的基础和灵感来源。
*   [NoneBot2](https://v2.nonebot.dev/) - 优雅的跨平台机器人框架。

## 📄 许可证

本项目采用 [MIT License](./LICENSE) 开源。
