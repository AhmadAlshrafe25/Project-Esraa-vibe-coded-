#!/usr/bin/env bash
# ==============================================================================
# PROJECT EZRA // INSTANT LAPTOP AUTO-ACTIVATION INSTALLER
# Dual Distro Parity: Arch Linux (KDE Plasma 6 Wayland) & Pop!_OS (GNOME/COSMIC)
#
# Configures:
# 1. Systemd User Service: ~/.config/systemd/user/ezra.service
# 2. XDG Autostart Entry: ~/.config/autostart/project-ezra.desktop
# 3. Direct Lid-Open & Wake-from-Suspend Hardware Monitor
# ==============================================================================

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║      ⚡ PROJECT EZRA: INSTANT LAPTOP AUTO-ACTIVATION          ║"
echo "║          Dual Distro: Arch Linux & Pop!_OS Parity             ║"
echo "╚═══════════════════════════════════════════════════════════════╝"

# 1. Identify Distro
DISTRO="Linux"
if [ -f /etc/os-release ]; then
    . /etc/os-release
    DISTRO="$NAME"
fi
echo "[+] Detected Environment: $DISTRO ($(uname -m))"

EXEC_PATH="$DIR/run_ezra.sh"
ICON_PATH="$DIR/assets/ezra_icon.png"
chmod +x "$EXEC_PATH"

# 2. Setup Systemd User Service Directory
USER_SYSTEMD_DIR="$HOME/.config/systemd/user"
mkdir -p "$USER_SYSTEMD_DIR"
SERVICE_FILE="$USER_SYSTEMD_DIR/ezra.service"

echo "[+] Creating systemd user service at: $SERVICE_FILE"
cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=Project Ezra Autonomous AI Desktop Companion (Instant Laptop Activation)
After=graphical-session.target pipewire.service pulseaudio.service sound.target
Wants=pipewire.service sound.target

[Service]
Type=simple
WorkingDirectory=$DIR
ExecStart=$EXEC_PATH --daemon
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1
Environment=DISPLAY=:0
Environment=WAYLAND_DISPLAY=wayland-0
Environment=XDG_CURRENT_DESKTOP=$XDG_CURRENT_DESKTOP

[Install]
WantedBy=default.target
EOF

# 3. Reload and Enable Systemd Service
echo "[+] Configuring systemd user service..."
SYSTEMD_ENABLED=0
if command -v systemctl >/dev/null 2>&1; then
    if systemctl --user daemon-reload 2>/dev/null && systemctl --user enable ezra.service 2>/dev/null; then
        SYSTEMD_ENABLED=1
        echo "[+] Systemd user service successfully enabled!"
        if systemctl --user is-active --quiet ezra.service 2>/dev/null; then
            echo "[+] Restarting active Ezra service with new lid-wake core..."
            systemctl --user restart ezra.service || true
        else
            echo "[+] Starting Ezra service now..."
            systemctl --user start ezra.service || true
        fi
    fi
fi

# 4. Autostart Deduplication & XDG Desktop Fallback
# If Systemd user service is enabled, remove or avoid duplicate XDG autostart entry to prevent concurrent instances
AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"
DESKTOP_AUTOSTART="$AUTOSTART_DIR/project-ezra.desktop"

if [ "$SYSTEMD_ENABLED" -eq 1 ]; then
    echo "[+] Systemd user service is managing autostart. Removing redundant XDG desktop entry to prevent competing instances..."
    rm -f "$DESKTOP_AUTOSTART"
else
    echo "[+] Systemd user service not available. Configuring XDG desktop autostart entry at: $DESKTOP_AUTOSTART"
    cat <<EOF > "$DESKTOP_AUTOSTART"
[Desktop Entry]
Version=1.0
Type=Application
Name=Project Ezra (Instant Laptop Wake)
GenericName=AI Desktop Assistant
Comment=Autonomous AI Desktop Companion with Instant Lid-Open Activation
Exec=$EXEC_PATH --daemon
Icon=$ICON_PATH
Terminal=false
Categories=Utility;AudioVideo;System;
StartupNotify=false
X-GNOME-Autostart-enabled=true
X-KDE-autostart-after=panel
EOF
    chmod +x "$DESKTOP_AUTOSTART"
fi

# 5. Check if user has sudo for systemd sleep hook (optional extra redundancy)
SLEEP_HOOK="/etc/systemd/system-sleep/ezra-wake.sh"
if [ "$EUID" -eq 0 ]; then
    echo "[+] Installing systemd sleep hook at $SLEEP_HOOK..."
    cat <<'HOOK_EOF' > "$SLEEP_HOOK"
#!/bin/sh
if [ "$1" = "post" ]; then
    for u in $(users | tr ' ' '\n' | sort -u); do
        uid=$(id -u "$u" 2>/dev/null)
        sock="/run/user/$uid/ezra_wake.sock"
        if [ -S "$sock" ]; then
            echo "WAKE:system_sleep_post" | nc -U "$sock" 2>/dev/null || true
        fi
    done
fi
HOOK_EOF
    chmod +x "$SLEEP_HOOK"
    echo "[+] System-wide sleep hook active!"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  🎉 SUCCESS: Ezra is now primed for instant laptop activation!"
echo "═══════════════════════════════════════════════════════════════"
echo "  • Boot / Login: Starts automatically in background."
echo "  • Lid Open: Activates the exact second you open the laptop."
echo "  • Sleep / Wake: Resumes and listens immediately without delay."
echo ""
echo "  To inspect status anytime:"
echo "    systemctl --user status ezra.service"
echo "  To view live voice logs:"
echo "    journalctl --user -u ezra.service -f"
echo "═══════════════════════════════════════════════════════════════"
