#!/usr/bin/env python3
"""Compile deployable modules with mpy-cross in an isolated directory."""

from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parent.parent


def main():
    compiler = shutil.which("mpy-cross")
    if compiler is None:
        raise SystemExit("mpy-cross is required; install MicroPython or mpy-cross")

    outputs = []
    with tempfile.TemporaryDirectory(prefix="diy-arcade-mpy-") as temp_dir:
        target_dir = Path(temp_dir)
        for source_name in ("main.py", "arcade_app.py"):
            output = target_dir / source_name.replace(".py", ".mpy")
            subprocess.run(
                [
                    compiler,
                    "-X",
                    "heapsize=8388608",
                    "-o",
                    str(output),
                    str(ROOT / source_name),
                ],
                check=True,
            )
            if not output.is_file() or output.stat().st_size == 0:
                raise RuntimeError("mpy-cross did not create " + output.name)
            outputs.append((output.name, output.stat().st_size))

    summary = ", ".join("%s=%d bytes" % item for item in outputs)
    print("MicroPython target OK:", summary)


if __name__ == "__main__":
    main()
