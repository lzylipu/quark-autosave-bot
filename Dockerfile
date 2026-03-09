FROM ghcr.io/astral-sh/uv:0.9.7-python3.12-bookworm-slim

WORKDIR /app

ENV TZ=Asia/Shanghai
ENV PORT=8080
ENV SUPERUSER=""
ENV TELEGRAM_BOT_TOKEN=""
ENV QAS_ENDPOINT="http://quark-auto-save:5005"
ENV QAS_TOKEN=""
ENV QAS_PATH_BASE="夸克自动转存"
ENV SIMPLE_COMMAND="1"
ENV SIMPLE_SAVE_ROOT="自动"

COPY pyproject.toml uv.lock README.md /app/
COPY src /app/src
COPY bot.py /app/bot.py
COPY start.sh /app/start.sh

RUN chmod +x /app/start.sh

# 只装运行 Telegram bot 需要的依赖，不装 dev/test
RUN uv sync --locked --no-dev --only-group telebot

CMD ["/bin/bash", "/app/start.sh"]
