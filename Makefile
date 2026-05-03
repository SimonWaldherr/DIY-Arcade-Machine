# Makefile for DIY Arcade Machine

# Default behavior is to show help
.PHONY: all help run upload build clean

all: help

# Show available commands
help:
	@echo "Available commands:"
	@echo "  make install - Install desktop dependencies (PyGame)"
	@echo "  make run    - Run the emulator on the desktop (Python PyGame needed)"
	@echo "  make upload - Upload the game to the microcontroller (runs upload.sh)"
	@echo "  make build  - Compile arcade_app.py to arcade_app.mpy (requires mpy-cross)"
	@echo "  make clean  - Remove built .mpy and temporary files"

# Install dependencies for desktop execution in a virtual environment
install: .venv/bin/activate

.venv/bin/activate:
	python3 -m venv .venv
	.venv/bin/pip install pygame

# Run the PyGame emulator locally (installs dependencies in venv first)
run: install
	.venv/bin/python main.py

# Upload the scripts via the interactive bash script
upload:
	./upload.sh

# Build bytecode locally if mpy-cross is available
build:
	@if command -v mpy-cross >/dev/null 2>&1; then \
		echo "Compiling arcade_app.py..."; \
		mpy-cross arcade_app.py; \
		echo "Done."; \
    else \
		echo "mpy-cross not found. Cannot compile ahead-of-time."; \
	fi

# Clean up built artifacts and python cache
clean:
	rm -rf *.mpy __pycache__ .mypy_cache *.pyc
	@echo "Cleaned up built files."
