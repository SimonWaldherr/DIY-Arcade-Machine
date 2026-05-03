# Makefile for DIY Arcade Machine

# Default behavior is to show help
.PHONY: all help run upload build clean clean-all install

all: help

# Show available commands
help:
	@echo "\033[1;36mDIY Arcade Machine Makefile\033[0m"
	@echo "Available commands:"
	@echo "  \033[1;32mmake install\033[0m   - Install desktop dependencies (PyGame)"
	@echo "  \033[1;32mmake run\033[0m       - Run the emulator on the desktop (Python PyGame needed)"
	@echo "  \033[1;32mmake upload\033[0m    - Upload the game to the microcontroller (runs upload.sh)"
	@echo "  \033[1;32mmake build\033[0m     - Compile arcade_app.py to arcade_app.mpy (requires mpy-cross)"
	@echo "  \033[1;32mmake clean\033[0m     - Remove built .mpy and temporary files"
	@echo "  \033[1;32mmake clean-all\033[0m - Remove all temporary files and the Python virtual environment"

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
	rm -rf *.mpy __pycache__ .mypy_cache *.pyc web-cache build tmp
	@echo "Cleaned up built files."

# Clean up everything including the virtual environment
clean-all: clean
	rm -rf .venv
	@echo "Cleaned up all files and virtual environment."
