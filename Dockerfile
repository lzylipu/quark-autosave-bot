FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV TZ=Asia/Shanghai
ENV PORT=8080
ENV SUPERUSER=""
ENV TELEGRAM_BOT_TOKEN=""
ENV QAS_ENDPOINT="http://quark-auto-save:5005"
ENV QAS_TOKEN=""
ENV QAS_PATH_BASE="夸克自动转存"
ENV SIMPLE_COMMAND="1"
ENV SIMPLE_SAVE_ROOT="自动"

COPY . /app

RUN chmod +x /app/start.sh

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    "httpx>=0.27.0,<1.0.0" \
    "nonebot-plugin-alconna>=0.59.4,<1.0.0" \
    "nonebot2[fastapi,httpx]>=2.4.3,<3.0.0" \
    "nonebot-adapter-telegram>=0.1.0b20"

CMD ["/bin/bash", "/app/start.sh"]
