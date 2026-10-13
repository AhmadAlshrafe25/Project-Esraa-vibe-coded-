#!/usr/bin/env bash
# ==============================================================================
# EZRA NATIVE GO SIDECAR BUILDER (Cross-compatible: Arch Linux & Pop!_OS)
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR" || exit 1

if command -v go >/dev/null 2>&1; then
    echo "[+] Compiling static native Go sidecar (zero glibc dependencies)..."
    mkdir -p bin
    CGO_ENABLED=0 go build -ldflags="-s -w" -o bin/ezra-core sidecar/ezra_core.go
    chmod +x bin/ezra-core
    echo "[✓] Native binary compiled: bin/ezra-core ($(du -h bin/ezra-core | cut -f1))"
else
    echo "[!] 'go' compiler not found on this machine. Using Python native fallback."
fi
