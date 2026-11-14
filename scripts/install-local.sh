#!/usr/bin/env bash
# Local install: venv + systemd user service (Linux, no root).
# Run after filling BOT_TOKEN in .env.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

if [[ ! -f .env ]]; then
    cp .env.example .env
    echo "Создан .env — вставь BOT_TOKEN и запусти скрипт ещё раз."
    exit 0
fi

if ! grep -Eq '^BOT_TOKEN=.+' .env; then
    echo "В .env пустой BOT_TOKEN. Вставь токен от @BotFather и запусти скрипт ещё раз."
    exit 0
fi

if [[ ! -x .venv/bin/python ]]; then
    python3 -m venv .venv
fi
.venv/bin/pip install --upgrade pip wheel >/dev/null
.venv/bin/pip install -r requirements.txt

UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR"
sed "s#%h/octo-load#$DIR#g" deploy/octo-load-user.service > "$UNIT_DIR/octo-load.service"

systemctl --user daemon-reload
systemctl --user enable --now octo-load

if command -v loginctl >/dev/null; then
    loginctl enable-linger "$USER" 2>/dev/null || true
fi

echo "==> Готово. Статус: systemctl --user status octo-load"
echo "==> Логи:        journalctl --user -u octo-load -f"
