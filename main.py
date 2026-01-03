import asyncio

"""Tiny bootstrap for the arcade app.

This minimal entry avoids large import-time memory pressure on constrained
targets (RP2040/MicroPython). It imports and runs `arcade_app` so the bulk of
the code can live in a separate file. For device deployment, compile
`arcade_app.py` with `mpy-cross` and upload `arcade_app.mpy` to reduce boot-time
compilation and memory usage.

For web builds using pygbag, run: `python -m pygbag ./main.py` (starts the
pygbag runtime and serves the app in a browser environment backed by
Emscripten/WebAssembly).
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
