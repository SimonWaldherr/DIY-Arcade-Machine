#!/usr/bin/env python3
"""Validate regular and touch web bundles after pygbag packaging."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REQUIRED = (
    "index.html",
    "manifest.webmanifest",
    "coi-serviceworker.js",
    "favicon.ico",
    "icons/icon-192.png",
    "icons/maskable-512.png",
    "archives/0.9/pythons.js",
    "archives/0.9/cpython312/main.js",
    "archives/0.9/cpython312/main.wasm",
    "archives/repo/cp312/pygame_static-1.0-cp312-cp312-wasm32_bi_emscripten.whl",
)
FORBIDDEN_RUNTIME_DIRS = (
    "archives/0.9/cpython313",
    "archives/0.9/pkpy14",
)


def validate(name, directory):
    missing = [path for path in REQUIRED if not (directory / path).is_file()]
    if missing:
        raise RuntimeError(name + " bundle is missing: " + ", ".join(missing))
    unexpected = [
        path for path in FORBIDDEN_RUNTIME_DIRS if (directory / path).exists()
    ]
    if unexpected:
        raise RuntimeError(name + " bundle contains unused runtimes: " + ", ".join(unexpected))
    index = (directory / "index.html").read_text(encoding="utf-8")
    for marker in (
        "DIYArcadeTouchInput",
        "DIYArcadeLoaderWatchTimer",
        "role=\"application\"",
        "coi-serviceworker.js",
    ):
        if marker not in index:
            raise RuntimeError(name + " index is missing marker " + marker)


def main():
    validate("browser", ROOT / "build" / "web")
    validate("iOS/touch", ROOT / "build" / "web" / "ios")
    print("web targets OK: regular and iOS/touch bundles are complete")


if __name__ == "__main__":
    main()
