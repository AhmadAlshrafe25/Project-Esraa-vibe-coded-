#!/usr/bin/env bash
# ==============================================================================
# PROJECT EZRA // AUTONOMOUS AI DESKTOP ASSISTANT RUNNER
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR" || exit 1

# If user requested UI mode, run Holographic JARVIS UI
if [ "$1" == "--ui" ] || [ "$1" == "-u" ] || [ "$1" == "ui" ]; then
    shift
    exec "$DIR/run_ui.sh" "$@"
fi

# If launched from GUI/Desktop without a terminal, spawn an interactive terminal
if [ "$1" != "terminal" ] && [ "$1" != "--daemon" ] && [ "$1" != "-d" ] && [ "$1" != "--auto" ] && { [ ! -t 0 ] || [ ! -t 1 ]; }; then
    for term in kitty alacritty gnome-terminal konsole xfce4-terminal ptyxis foot wezterm xterm cosmic-term; do
        if command -v "$term" >/dev/null 2>&1; then
            case "$term" in
                kitty)
                    exec kitty --title "Project Ezra // Neural Core" -d "$DIR" "$0" terminal ;;
                alacritty)
                    exec alacritty --title "Project Ezra // Neural Core" --working-directory "$DIR" -e "$0" terminal ;;
                gnome-terminal)
                    exec gnome-terminal --title="Project Ezra // Neural Core" --working-directory="$DIR" -- "$0" terminal ;;
                konsole)
                    exec konsole --title "Project Ezra // Neural Core" --workdir "$DIR" -e "$0" terminal ;;
                xfce4-terminal)
                    exec xfce4-terminal --title="Project Ezra // Neural Core" --working-directory="$DIR" -e "\"$0\" terminal" ;;
                foot)
                    exec foot --title="Project Ezra // Neural Core" -D "$DIR" "$0" terminal ;;
                wezterm)
                    exec wezterm start --cwd "$DIR" "$0" terminal ;;
                cosmic-term)
                    exec cosmic-term --title "Project Ezra // Neural Core" -- bash -c "\"$0\" terminal; exec bash" ;;
                xterm)
                    exec xterm -title "Project Ezra // Neural Core" -geometry 110x32 -e "\"$0\" terminal" ;;
            esac
        fi
    done
fi

# Set window title
echo -ne "\033]0;Project Ezra // JARVIS AI Desktop Core\007"

export PYTHONUNBUFFERED=1

# Run Ezra in virtual environment
if [ -f "$DIR/venv/bin/python3" ]; then
    "$DIR/venv/bin/python3" "$DIR/app.py" "$@"
else
    python3 "$DIR/app.py" "$@"
fi

EXIT_CODE=$?
if [ "$EXIT_CODE" -ne 0 ] && [ "$1" != "--daemon" ] && [ "$1" != "-d" ]; then
    echo ""
    echo "[!] Ezra exited with code $EXIT_CODE."
    read -r -p "Press ENTER to close..."
fi
