#!/usr/bin/env bash
# ==============================================================================
# PROJECT EZRA // AUTONOMOUS AI DESKTOP ASSISTANT RUNNER
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR" || exit 1

# If launched from GUI/Desktop without a terminal, spawn an interactive terminal
if [ "$1" != "terminal" ] && { [ ! -t 0 ] || [ ! -t 1 ]; }; then
    if command -v cosmic-term >/dev/null 2>&1; then
        exec cosmic-term --title "Project Ezra // Neural Core" -- bash -c "\"$0\" terminal; exec bash"
    elif command -v xterm >/dev/null 2>&1; then
        exec xterm -title "Project Ezra // Neural Core" -geometry 100x30 -e "\"$0\" terminal"
    fi
fi

# Set window title
echo -ne "\033]0;Project Ezra // JARVIS AI Desktop Core\007"

export PYTHONUNBUFFERED=1

# Run Ezra in virtual environment
if [ -f "$DIR/venv/bin/python3" ]; then
    "$DIR/venv/bin/python3" "$DIR/app.py"
else
    python3 "$DIR/app.py"
fi

EXIT_CODE=$?
if [ "$EXIT_CODE" -ne 0 ]; then
    echo ""
    echo "[!] Ezra exited with code $EXIT_CODE."
    read -r -p "Press ENTER to close..."
fi
