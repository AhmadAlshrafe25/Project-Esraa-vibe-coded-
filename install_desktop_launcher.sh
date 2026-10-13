#!/usr/bin/env bash
# ==============================================================================
# INSTALL PROJECT EZRA DESKTOP LAUNCHER
# Installs .desktop launcher to ~/Desktop and ~/.local/share/applications
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ICON_PATH="$DIR/assets/ezra_icon.png"
EXEC_PATH="$DIR/run_ezra.sh"

chmod +x "$EXEC_PATH"

# Resolve Desktop folder
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
APPS_DIR="$HOME/.local/share/applications"

mkdir -p "$DESKTOP_DIR"
mkdir -p "$APPS_DIR"

DESKTOP_FILE="$DESKTOP_DIR/Project-Ezra.desktop"
APP_FILE="$APPS_DIR/Project-Ezra.desktop"

CONTENT="[Desktop Entry]
Version=1.0
Type=Application
Name=Project Ezra
GenericName=AI Desktop Assistant
Comment=Autonomous AI Desktop Companion (JARVIS-Class)
Exec=$EXEC_PATH
Icon=$ICON_PATH
Terminal=false
Categories=Utility;AudioVideo;System;
StartupNotify=true
"

echo "$CONTENT" > "$DESKTOP_FILE"
echo "$CONTENT" > "$APP_FILE"

chmod +x "$DESKTOP_FILE"
chmod +x "$APP_FILE"

# Trust desktop file on GNOME/KDE if gio is available
if command -v gio >/dev/null 2>&1; then
    gio set "$DESKTOP_FILE" metadata::trusted true 2>/dev/null || true
fi

echo "[+] Project Ezra Desktop Launcher successfully installed!"
echo "    -> Desktop: $DESKTOP_FILE"
echo "    -> App Grid: $APP_FILE"
