#!/bin/bash
set -euo pipefail

# Interactive device selection if PORT not already set
if [ -z "${PORT:-}" ]; then
	echo "Scanning for USB devices..."
	DEVICES=($(ls /dev/cu.usbmodem* 2>/dev/null || true))
	
	if [ ${#DEVICES[@]} -eq 0 ]; then
		echo "Error: No USB devices found matching /dev/cu.usbmodem*"
		echo "Please connect your device and try again."
		exit 1
	elif [ ${#DEVICES[@]} -eq 1 ]; then
		PORT="${DEVICES[0]}"
		echo "Auto-selected: $PORT"
	else
		echo "Multiple devices found:"
		for i in "${!DEVICES[@]}"; do
			echo "  [$i] ${DEVICES[$i]}"
		done
		read -p "Select device number [0]: " choice
		choice=${choice:-0}
		if [ "$choice" -ge 0 ] && [ "$choice" -lt "${#DEVICES[@]}" ] 2>/dev/null; then
			PORT="${DEVICES[$choice]}"
			echo "Selected: $PORT"
		else
			echo "Invalid choice. Exiting."
			exit 1
		fi
	fi
fi

# If mpy-cross is available, compile the big module on the host to avoid
# MicroPython running out of RAM compiling ~180KB source on boot.
if command -v mpy-cross >/dev/null 2>&1; then
	echo "Compiling arcade_app.py with mpy-cross..."
	if [ ! -f ./arcade_app.mpy ] || [ ./arcade_app.py -nt ./arcade_app.mpy ]; then
		mpy-cross ./arcade_app.py
		echo "✓ Compiled to arcade_app.mpy"
	else
		echo "✓ arcade_app.mpy is up to date"
	fi
fi

echo "Uploading to $PORT..."

# Upload tiny bootstrap first.
echo "  → main.py"
ampy --port "$PORT" put ./main.py

# Prefer compiled module to avoid on-device compilation MemoryErrors.
if [ -f ./arcade_app.mpy ]; then
	echo "  → arcade_app.mpy"
	ampy --port "$PORT" put ./arcade_app.mpy
else
	echo "  → arcade_app.py (warning: may cause MemoryError on boot)"
	ampy --port "$PORT" put ./arcade_app.py
fi

echo "✓ Upload complete!"