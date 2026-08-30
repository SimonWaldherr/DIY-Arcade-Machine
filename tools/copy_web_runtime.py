#!/usr/bin/env python3
"""Copy only the pygbag runtime files used by the configured Python ABI."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT_FILES = (
    "browserfs.min.js",
    "cpythonrc.py",
    "empty.html",
    "empty.ogg",
    "favicon.ico",
    "favicon.png",
    "pythons.js",
    "vt.js",
    "vtx.js",
)


def copy_runtime(source: Path, destination: Path, abi: str) -> None:
    runtime_name = "cpython" + abi[2:] if abi.startswith("cp") else abi
    runtime_source = source / runtime_name
    required = [source / name for name in ROOT_FILES]
    required.extend((source / "vt", runtime_source))
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("missing web runtime files: " + ", ".join(missing))

    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    for name in ROOT_FILES:
        shutil.copy2(source / name, destination / name)
    shutil.copytree(source / "vt", destination / "vt")
    shutil.copytree(runtime_source, destination / runtime_name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("abi")
    args = parser.parse_args()
    copy_runtime(args.source, args.destination, args.abi)
    print("copied minimal", args.abi, "web runtime to", args.destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
