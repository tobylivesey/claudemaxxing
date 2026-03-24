#!/usr/bin/env bash
# burn.sh — claudemaxxing auto-burn entry point (Linux/macOS).
# Add to cron to run periodically; autoburn.py enforces allowed_hours from
# config.json, so you can run this every 30 min all day without worrying.
#
# Cron setup (every 30 min, all hours — autoburn.py gates by allowed_hours):
#   crontab -e
#   */30 * * * * /path/to/claudemaxxing/burn.sh >> /path/to/claudemaxxing/cron.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Use the venv python if present, otherwise fall back to system python3
if [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/.venv/bin/python"
elif [ -f "$SCRIPT_DIR/venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/venv/bin/python"
else
    PYTHON="python3"
fi

exec "$PYTHON" "$SCRIPT_DIR/autoburn.py"
