#!/usr/bin/env bash
set -e

cat > /app/.env.prod <<EOF
HOST=0.0.0.0
PORT=${PORT}
SUPERUSERS=["${SUPERUSER}"]
COMMAND_START=["/",""]

DRIVER=~fastapi+~httpx

telegram_bots=[{"token":"${TELEGRAM_BOT_TOKEN}"}]

QAS_ENDPOINT=${QAS_ENDPOINT}
QAS_TOKEN=${QAS_TOKEN}
QAS_PATH_BASE=${QAS_PATH_BASE}
SIMPLE_COMMAND="${SIMPLE_COMMAND}"
SIMPLE_SAVE_ROOT="${SIMPLE_SAVE_ROOT}"
EOF

exec python /app/bot.py
