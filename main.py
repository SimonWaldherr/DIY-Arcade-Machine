import asyncio

"""Tiny bootstrap.

On MicroPython (RP2040), importing/compiling a very large `main.py` can fail at boot
with `MemoryError`.

This file stays intentionally small and simply imports and runs `arcade_app`.
For best results on-device, upload `arcade_app.mpy` (compiled with `mpy-cross`)
so the Pico doesn't have to compile ~180KB of Python source at boot.

Desktop (CPython/PyGame) remains supported: `python main.py` runs the same app.
"""


def _print_exception(exc):
    try:
        import sys

        pe = getattr(sys, "print_exception", None)
        if pe:
            pe(exc)
            return
    except Exception:
        pass

    try:
        import traceback

        traceback.print_exc()
    except Exception:
        pass


def _run():
    try:
        import gc

        gc.collect()
    except Exception:
        pass

    try:
        import arcade_app as app
    except Exception as exc:
        _print_exception(exc)
        raise

    try:
        app.main()
    except Exception as exc:
        _print_exception(exc)
        raise


if __name__ == "__main__":
    asyncio.run(_run())
