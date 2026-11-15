#!/usr/bin/env bash
# Refresh yt-dlp/gallery-dl and restart the local user service.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"$DIR/.venv/bin/pip" install --upgrade yt-dlp gallery-dl
systemctl --user restart octo-load
echo "OctoLoad updated: $(date -Is)"
