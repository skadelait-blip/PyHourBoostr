#!/usr/bin/env bash
set -euo pipefail

# Build script for HourBoostr (Linux)
# Creates a standalone executable in dist/

cd "$(dirname "$0")"

echo "=== HourBoostr Linux Builder ==="
echo ""

# Check Python
PYTHON=$(command -v python3 || command -v python)
if [ -z "$PYTHON" ]; then
    echo "ERROR: Python 3 not found. Install it first:"
    echo "  sudo apt install python3 python3-pip python3-venv"
    exit 1
fi

echo "Using: $($PYTHON --version)"

# Venv setup
if [ ! -d build_venv ]; then
    echo ""
    echo "--- Creating virtual environment ---"
    $PYTHON -m venv build_venv
fi

source build_venv/bin/activate

echo ""
echo "--- Installing Python dependencies ---"
pip install --upgrade pip -q
pip install -r requirements.txt pyinstaller -q

echo ""
echo "--- Installing system dependencies ---"
if command -v apt-get &>/dev/null; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq \
        libxcb-xinerama0 libegl1-mesa libgl1-mesa-glx \
        libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 \
        libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 \
        libxcb-shape0 libxcb-xfixes0 libxcb-xkb1 \
        libdbus-1-3 patchelf 2>/dev/null || true
elif command -v dnf &>/dev/null; then
    sudo dnf install -y qt6-qtbase-gui patchelf 2>/dev/null || true
elif command -v pacman &>/dev/null; then
    sudo pacman -S --noconfirm qt6-base patchelf 2>/dev/null || true
fi

echo ""
echo "--- Building executable ---"
pyinstaller --onefile \
    --name HourBoostr \
    --add-data "README.md:." \
    --hidden-import steam \
    --hidden-import steam.client \
    --hidden-import steam.core.cm \
    --hidden-import steam.core.msg \
    --hidden-import steam.enums \
    --hidden-import steam.enums.emsg \
    --hidden-import steam.exceptions \
    --hidden-import steam.webapi \
    --hidden-import steam.webauth \
    --hidden-import gevent \
    --hidden-import gevent.monkey \
    --hidden-import gevent.pool \
    --hidden-import eventemitter \
    --hidden-import protobuf \
    --hidden-import requests \
    --hidden-import xml.etree.ElementTree \
    --collect-all steam \
    --collect-all gevent \
    run_gui.py 2>&1 | tail -20

echo ""
echo "=== Build complete ==="
echo "Executable: dist/HourBoostr"
echo ""
echo "Run it: ./dist/HourBoostr"
echo ""
echo "NOTE: If you get Qt library errors, install system deps:"
echo "  sudo apt install libxcb-xinerama0 libegl1-mesa libgl1-mesa-glx"
