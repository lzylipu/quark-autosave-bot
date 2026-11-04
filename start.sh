#!/usr/bin/env bash
set -e

# SUPERUSER 可选：留空表示「私聊谁都能用」，填了就只认这些 TG 用户 ID。
# 必须写成 JSON 列表，空值时给 [] 而不是 [""]，否则会变成一个叫空字符串的
# 超级用户，结果谁都匹配不上。
if [ -n "${SUPERUSER}" ]; then
  SUPERUSERS_JSON="[\"${SUPERUSER}\"]"
else
  SUPERUSERS_JSON="[]"
fi

cat > /app/.env.prod <<ENDENV
HOST=0.0.0.0
PORT=${PORT:-8080}
SUPERUSERS=${SUPERUSERS_JSON}
COMMAND_START=["/", ""]

DRIVER=~fastapi+~httpx

telegram_bots=[{"token": "${TELEGRAM_BOT_TOKEN}"}]

QAS_ENDPOINT=${QAS_ENDPOINT}
QAS_TOKEN=${QAS_TOKEN}
QAS_PATH_BASE=${QAS_PATH_BASE:-夸克自动转存}
SIMPLE_SAVE_ROOT=${SIMPLE_SAVE_ROOT:-自动}
QAS_RUN_TIMEOUT=${QAS_RUN_TIMEOUT:-1800}
DEDUPE_SECONDS=${DEDUPE_SECONDS:-600}
ASK_PASSCODE=${ASK_PASSCODE:-true}
SUB_CHECK_TIME=${SUB_CHECK_TIME:-17:00}
SUB_MIN_SIZE_GB=${SUB_MIN_SIZE_GB:-1.5}
SUB_MAX_SIZE_GB=${SUB_MAX_SIZE_GB:-8.0}
SUB_MAX_CANDIDATES=${SUB_MAX_CANDIDATES:-0}
SUB_MAX_OK_CANDIDATES=${SUB_MAX_OK_CANDIDATES:-1}
SUB_FALLBACK_MIN_SIZE_GB=${SUB_FALLBACK_MIN_SIZE_GB:-0.5}
SUB_STORE_FILE=${SUB_STORE_FILE:-/app/data/subscriptions.json}
ENDENV

# 订阅文件持久化自检：/app/data 必须是挂载卷，否则重建/升级容器订阅全丢
if grep -q " /app/data " /proc/self/mountinfo 2>/dev/null; then
  echo "[quarkbot] 数据目录 /app/data 已挂卷，订阅/聊天绑定会保留"
else
  echo "============================================================"
  echo "[quarkbot] 警告：/app/data 没有挂载卷！"
  echo "[quarkbot] 现在能正常用，但重建或升级容器后订阅会全部丢失。"
  echo "[quarkbot] 修法：docker run 加  -v quarkbot-data:/app/data"
  echo "[quarkbot]       compose 加  volumes: - bot-data:/app/data"
  echo "============================================================"
fi

# ---- 数据目录权限：容器自己修，不需要用户 chown ----
# 镜像以 root 启动，这里把挂进来的数据目录交给 appuser(1000)，再降权运行。
# 这样 bind mount 的宿主目录不管是 root 还是别的属主，都直接能用；
# 极少数改不了属主的挂载点（NFS/SMB/cifs）就退回以 root 运行，功能不受影响。
DATA_DIR="$(dirname "${SUB_STORE_FILE:-/app/data/subscriptions.json}")"
DROP_TO_APPUSER=0
if [ "$(id -u)" = "0" ]; then
  mkdir -p "$DATA_DIR" 2>/dev/null || true
  chown -R 1000:1000 "$DATA_DIR" 2>/dev/null || true
  chmod u+rwx "$DATA_DIR" 2>/dev/null || true
  if su appuser -s /bin/sh -c "test -w '$DATA_DIR'" 2>/dev/null; then
    DROP_TO_APPUSER=1
  else
    echo "[quarkbot] 提示：$DATA_DIR 改不了属主（NFS/SMB 之类的挂载），本次以 root 运行，功能不受影响"
  fi
fi

if [ "$DROP_TO_APPUSER" = "1" ]; then
  if command -v setpriv >/dev/null 2>&1; then
    exec setpriv --reuid=1000 --regid=1000 --init-groups python /app/bot.py
  fi
  exec su -s /bin/sh appuser -c "exec python /app/bot.py"
fi
exec python /app/bot.py
