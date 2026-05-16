# Makefile for DIY Arcade Machine

PORT           ?= 8000
PYGBAG_VERSION ?= 0.9.2
RUNTIME_VERSION ?= 0.9
RUNTIME_INDEX   ?= $(subst .,,$(RUNTIME_VERSION))0
PYTHON_ABI      ?= cp312
WEB_TEMPLATE   ?= web/default.tmpl
WEB_TITLE      ?= DIY Arcade Machine
WEB_SRC        ?= build/web-src
WEB_CDN        ?= ./archives/$(RUNTIME_VERSION)/
WEB_ARCHIVES_URL ?= https://github.com/pygame-web/archives/archive/refs/heads/main.zip
WEB_ARCHIVES_ZIP ?= build/pygame-web-archives.zip
WEB_ARCHIVES_SRC ?= build/archives-main/$(RUNTIME_VERSION)
WEB_REPO_URL     ?= https://pygame-web.github.io/archives/repo
WEB_REPO_CACHE   ?= build/pygame-web-repo
WEB_PYGAME_STATIC_WHEEL ?= pygame_static-1.0-$(PYTHON_ABI)-$(PYTHON_ABI)-wasm32_bi_emscripten.whl

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
	.venv/bin/pip install pygbag==$(PYGBAG_VERSION)

# Download and prepare the pygbag runtime (cached: only re-downloads if missing).
# Browser support:
#   Chrome / Firefox : works out of the box
#   Safari           : requires Cross-Origin-Isolation headers → use `make web-safari`
web-runtime:
	@mkdir -p build/archives-main
	@if [ ! -f "$(WEB_ARCHIVES_ZIP)" ]; then \
		echo "Downloading pygbag runtime archive..."; \
		curl -fsSL "$(WEB_ARCHIVES_URL)" -o "$(WEB_ARCHIVES_ZIP)"; \
	fi
	@if [ ! -f "$(WEB_ARCHIVES_SRC)/pythons.js" ]; then \
		echo "Extracting pygbag runtime..."; \
		unzip -q "$(WEB_ARCHIVES_ZIP)" 'archives-main/$(RUNTIME_VERSION)/*' -d build; \
		find "$(WEB_ARCHIVES_SRC)" -type f -name '*.js' \
			-exec perl -ni -e 'print unless m{^//# sourceMappingURL=.*\.map\s*$$}' {} +; \
	fi
	@mkdir -p "$(WEB_REPO_CACHE)/$(PYTHON_ABI)"
	@if [ ! -f "$(WEB_REPO_CACHE)/$(PYTHON_ABI)/$(WEB_PYGAME_STATIC_WHEEL)" ]; then \
		echo "Downloading pygbag pygame runtime wheel..."; \
		curl -fsSL "$(WEB_REPO_URL)/$(PYTHON_ABI)/$(WEB_PYGAME_STATIC_WHEEL)" \
			-o "$(WEB_REPO_CACHE)/$(PYTHON_ABI)/$(WEB_PYGAME_STATIC_WHEEL)"; \
	fi

web-build: web-install web-runtime
	@echo "Building WebAssembly version..."
	rm -rf $(WEB_SRC)
	mkdir -p $(WEB_SRC)
	cp main.py arcade_app.py logo.png $(WEB_SRC)/
	[ -f highscores.json ] && cp highscores.json $(WEB_SRC)/ || true
	PYTHONUNBUFFERED=1 .venv/bin/python -m pygbag \
		--ume_block 0 --width 640 --height 640 \
		--title "$(WEB_TITLE)" --icon logo.png \
		--cdn "$(WEB_CDN)" --template $(abspath $(WEB_TEMPLATE)) \
		--build $(WEB_SRC)
	cp web/coi-serviceworker.js $(WEB_SRC)/build/web/
	cp web/manifest.webmanifest $(WEB_SRC)/build/web/
	cp web/favicon.ico web/favicon-16.png web/favicon-32.png web/og-image.png $(WEB_SRC)/build/web/
	cp -R web/icons $(WEB_SRC)/build/web/
	mkdir -p $(WEB_SRC)/build/web/archives
	cp -R $(WEB_ARCHIVES_SRC) $(WEB_SRC)/build/web/archives/
	mkdir -p $(WEB_SRC)/build/web/archives/repo
	mkdir -p $(WEB_SRC)/build/web/archives/repo/$(PYTHON_ABI)
	cp "$(WEB_REPO_CACHE)/$(PYTHON_ABI)/$(WEB_PYGAME_STATIC_WHEEL)" \
		$(WEB_SRC)/build/web/archives/repo/$(PYTHON_ABI)/
	# pygbag expects -CDN- in package indexes as the wheel base URL.
	printf '{"-CDN-":"./archives/repo/"}\n' > $(WEB_SRC)/build/web/archives/repo/index-$(RUNTIME_INDEX)-$(PYTHON_ABI).json
	printf '{"packages":{}}\n' > $(WEB_SRC)/build/web/archives/repo/repodata.json
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
	@if [ ! -f build/web/index.html ] || [ ! -f "build/web/archives/repo/$(PYTHON_ABI)/$(WEB_PYGAME_STATIC_WHEEL)" ]; then \
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
		mpy-cross -X heapsize=8388608 arcade_app.py; \
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
