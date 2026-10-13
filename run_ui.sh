#!/usr/bin/env bash
# ==============================================================================
# PROJECT EZRA // HOLOGRAPHIC JARVIS UI LAUNCHER
# Starts the async Web & WebSocket server and opens the 3D Hologram window.
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR" || exit 1

echo -ne "\033]0;Project Ezra // Holographic JARVIS Core\007"

export PYTHONUNBUFFERED=1

if [ -f "$DIR/venv/bin/python3" ]; then
    exec "$DIR/venv/bin/python3" -m jarvis.ui.server "$@"
else
    exec python3 -m jarvis.ui.server "$@"
fi
