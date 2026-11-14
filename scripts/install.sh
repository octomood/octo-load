#!/usr/bin/env bash
# Install OctoLoad on a fresh Ubuntu/Debian VM (systemd, no Docker).
#
#   sudo bash scripts/install.sh
#
# Override paths with env vars if needed:
#   APP_DIR=/opt/octo-load DATA_DIR=/var/lib/octo-load sudo -E bash scripts/install.sh
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/octo-load}"
DATA_DIR="${DATA_DIR:-/var/lib/octo-load}"
ENV_FILE="${ENV_FILE:-/etc/octo-load.env}"
SERVICE_NAME="octo-load"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ${EUID} -ne 0 ]]; then
    echo "Запусти от root: sudo bash scripts/install.sh" >&2
    exit 1
fi

echo "==> пакеты"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv ffmpeg ca-certificates tar

if ! id -u octo >/dev/null 2>&1; then
    useradd --system --user-group --home-dir "$APP_DIR" --shell /usr/sbin/nologin octo
fi

echo "==> файлы в $APP_DIR"
mkdir -p "$APP_DIR" "$DATA_DIR"
tar -C "$SRC_DIR" \
    --exclude=.git --exclude=.venv --exclude=data --exclude=secrets \
    --exclude=.env --exclude=__pycache__ --exclude='*.pyc' \
    -cf - . | tar -C "$APP_DIR" -xf -

echo "==> virtualenv"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip wheel >/dev/null
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

chown -R octo:octo "$APP_DIR" "$DATA_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
    cp "$APP_DIR/.env.example" "$ENV_FILE"
    sed -i "s#^WORK_DIR=.*#WORK_DIR=$DATA_DIR#" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    echo "==> создан $ENV_FILE"
fi

echo "==> systemd"
install -m 0644 "$APP_DIR/deploy/octo-load.service" "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME" >/dev/null

cat > /etc/cron.d/octo-load <<EOF
# Weekly extractor refresh: sites change and old yt-dlp builds stop working.
15 4 * * 1 root $APP_DIR/scripts/update.sh >> /var/log/octo-load-update.log 2>&1
EOF
chmod 644 /etc/cron.d/octo-load

if grep -Eq '^BOT_TOKEN=.+' "$ENV_FILE"; then
    systemctl restart "$SERVICE_NAME"
    echo "==> OctoLoad запущен. Статус: systemctl status $SERVICE_NAME"
else
    echo "==> BOT_TOKEN пока не заполнен."
    echo "    Открой $ENV_FILE, вставь токен от @BotFather и выполни:"
    echo "    systemctl restart $SERVICE_NAME"
fi
