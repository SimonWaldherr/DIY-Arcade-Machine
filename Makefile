# Makefile for DIY Arcade Machine

PORT ?= 8000
WEB_TEMPLATE ?= web/default.tmpl
WEB_TITLE ?= DIY Arcade Machine
WEB_SRC ?= build/DIY-Arcade-Machine
WEB_CDN ?= ./archives/0.9/
WEB_ARCHIVES_URL ?= https://github.com/pygame-web/archives/archive/refs/heads/main.zip
WEB_ARCHIVES_ZIP ?= build/pygame-web-archives.zip
WEB_ARCHIVES_SRC ?= build/pygame-web-archives-main/archives-main/0.9

# Default behavior is to show help
.PHONY: all help run upload build clean clean-all install web-install web-build web web-safari

all: help

# Show available commands
help:
	@echo "\033[1;36mDIY Arcade Machine Makefile\033[0m"
	@echo "Available commands:"
	@echo "  \033[1;32mmake install\033[0m   - Install desktop dependencies (PyGame)"
	@echo "  \033[1;32mmake run\033[0m       - Run the emulator on the desktop (Python PyGame needed)"
	@echo "  \033[1;32mmake upload\033[0m    - Upload the game to the microcontroller (runs upload.sh)"
	@echo "  \033[1;32mmake build\033[0m     - Compile arcade_app.py to arcade_app.mpy (requires mpy-cross)"
	@echo "  \033[1;32mmake web-install\033[0m - Install pygbag for browser builds"
	@echo "  \033[1;32mmake web-build\033[0m - Build the browser version into build/web/"
	@echo "  \033[1;32mmake web\033[0m       - Build and serve the browser version (Chrome/Firefox)"
	@echo "  \033[1;32mmake web-safari\033[0m - Serve with COOP+COEP headers for Safari"
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

# Install pygbag for browser/WebAssembly builds
web-install: install
	.venv/bin/pip install pygbag

# Build and serve the WebAssembly version in the browser.
# pygbag bundles main.py + arcade_app.py + logo.png into build/web/.
# Override port with: make web PORT=8080
#
# Browser support:
#   Chrome / Firefox : works out of the box
#   Safari           : requires Cross-Origin-Isolation headers (COOP+COEP).
#                      Use `make web-safari` which starts a wrapper server
#                      that injects the required headers.
# Build the WebAssembly version into build/web/.
# Keep a local template and download the pygbag runtime during builds so the
# deployed app does not depend on cross-origin assets at runtime.
web-runtime:
	@mkdir -p build/pygame-web-archives-main
	@if [ ! -f "$(WEB_ARCHIVES_ZIP)" ]; then \
		echo "Downloading pygbag runtime archive..."; \
		curl -L "$(WEB_ARCHIVES_URL)" -o "$(WEB_ARCHIVES_ZIP)"; \
	fi
	@if [ ! -f "$(WEB_ARCHIVES_SRC)/pythons.js" ]; then \
		unzip -q "$(WEB_ARCHIVES_ZIP)" 'archives-main/0.9/*' -d build/pygame-web-archives-main; \
	fi
	find "$(WEB_ARCHIVES_SRC)" -type f -name '*.js' -exec perl -ni -e 'print unless m{^//# sourceMappingURL=.*\.map\s*$$}' {} +

web-build: web-install web-runtime
	@echo "Building WebAssembly version..."
	rm -rf $(WEB_SRC)
	mkdir -p $(WEB_SRC)
	cp main.py arcade_app.py logo.png $(WEB_SRC)/
	@if [ -f highscores.json ]; then cp highscores.json $(WEB_SRC)/; fi
	PYTHONUNBUFFERED=1 .venv/bin/python -m pygbag --ume_block 0 --width 640 --height 640 --title "$(WEB_TITLE)" --icon logo.png --cdn "$(WEB_CDN)" --template $(abspath $(WEB_TEMPLATE)) --build $(WEB_SRC)
	cp web/coi-serviceworker.js $(WEB_SRC)/build/web/
	mkdir -p $(WEB_SRC)/build/web/archives
	cp -R $(WEB_ARCHIVES_SRC) $(WEB_SRC)/build/web/archives/
	rm -rf build/web
	cp -R $(WEB_SRC)/build/web build/web

web: web-build
	@echo "Open \033[1;32mhttp://localhost:$(PORT)\033[0m in Chrome or Firefox."
	@echo "(Safari users: run \033[1;33mmake web-safari\033[0m instead)"
	.venv/bin/python -m http.server $(PORT) --directory build/web

# Safari-compatible server: serves build/web/ with Cross-Origin-Isolation
# headers so SharedArrayBuffer (needed by pygbag's WASM timing) works in Safari.
# Uses COEP credentialless to match the static GitHub Pages service-worker
# behavior; pygbag runtime files are served from build/web/archives.
# Run `make web` first to build, then `make web-safari` to serve.
web-safari: web-install
	@if [ ! -f build/web/index.html ]; then \
		echo "No build found – building first..."; \
		$(MAKE) web-build; \
	fi
	@echo "Serving with COOP+COEP headers for Safari..."
	@echo "Open \033[1;32mhttp://localhost:$(PORT)\033[0m in Safari."
	.venv/bin/python serve_safari.py $(PORT)

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
