#!/usr/bin/env bash
# Refresh yt-dlp/gallery-dl and restart the bot. Install script adds a weekly cron.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/octo-load}"

if [[ ! -x "$APP_DIR/.venv/bin/pip" ]]; then
    echo "Не нашёл virtualenv в $APP_DIR" >&2
    exit 1
fi

"$APP_DIR/.venv/bin/pip" install --upgrade yt-dlp gallery-dl
systemctl restart octo-load
echo "Обновлено: $(date -Is)"
