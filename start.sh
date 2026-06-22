#!/usr/bin/env bash
set -e

cat > /app/.env.prod <<EOF
HOST=0.0.0.0
PORT=${PORT:-8080}
SUPERUSERS=["${SUPERUSER}"]
COMMAND_START=["/", ""]

DRIVER=~fastapi+~httpx

telegram_bots=[{"token": "${TELEGRAM_BOT_TOKEN}"}]

QAS_ENDPOINT=${QAS_ENDPOINT}
QAS_TOKEN=${QAS_TOKEN}
QAS_PATH_BASE=${QAS_PATH_BASE:-夸克自动转存}
SIMPLE_COMMAND="${SIMPLE_COMMAND:-1}"
SIMPLE_SAVE_ROOT="${SIMPLE_SAVE_ROOT:-自动}"
EOF

exec python /app/bot.py
