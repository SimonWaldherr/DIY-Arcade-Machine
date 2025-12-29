#!/bin/bash
set -euo pipefail

PORT=${PORT:-/dev/cu.usbmodem213401}

# If mpy-cross is available, compile the big module on the host to avoid
# MicroPython running out of RAM compiling ~180KB source on boot.
if command -v mpy-cross >/dev/null 2>&1; then
	if [ ! -f ./arcade_app.mpy ] || [ ./arcade_app.py -nt ./arcade_app.mpy ]; then
		mpy-cross ./arcade_app.py
	fi
fi

# Upload tiny bootstrap first.
ampy --port "$PORT" put ./main.py

# Prefer compiled module to avoid on-device compilation MemoryErrors.
if [ -f ./arcade_app.mpy ]; then
	ampy --port "$PORT" put ./arcade_app.mpy
else
	ampy --port "$PORT" put ./arcade_app.py
fi