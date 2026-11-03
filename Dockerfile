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
ENV SIMPLE_SAVE_ROOT="自动"
ENV QAS_RUN_TIMEOUT="1800"
ENV DEDUPE_SECONDS="600"
ENV ASK_PASSCODE="true"
ENV SUB_CHECK_TIME="17:00"
ENV SUB_MIN_SIZE_GB="1.5"
ENV SUB_MAX_SIZE_GB="8.0"
ENV SUB_MAX_CANDIDATES="10"
ENV SUB_STORE_FILE="/app/data/subscriptions.json"

# 依赖先单独安装，利用 Docker 构建缓存
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

RUN mkdir -p /app/data && chmod +x /app/start.sh && \
    useradd --create-home --shell /usr/sbin/nologin appuser && \
    chown -R appuser:appuser /app

USER appuser

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import os, socket, sys; s = socket.socket(); s.settimeout(5); sys.exit(0 if s.connect_ex(('127.0.0.1', int(os.environ.get('PORT', '8080')))) == 0 else 1)"

CMD ["/bin/bash", "/app/start.sh"]
