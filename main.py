"""
Tiny bootstrap entry point for DIY Arcade Machine.

This file stays intentionally small to avoid memory issues on MicroPython devices.
It simply imports and runs the main arcade application, with proper async support
for browser deployment via pygbag.

Platform Support:
  - MicroPython (RP2040): Synchronous execution (upload as arcade_app.mpy for best results)
  - Desktop (CPython + PyGame): Synchronous execution
  - Browser (pygbag/WASM): Asynchronous execution with proper event loop yielding

For browser deployment, the async entry point ensures cooperative multitasking with
the browser event loop by yielding control via `await asyncio.sleep(0)`.
"""

import sys


def _print_exception(exc):
    """Print exception with fallback for platforms without traceback support."""
    try:
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


def main():
    """
    Synchronous entry point for desktop and MicroPython platforms.

    Imports the arcade application and runs the main game loop directly.
    """
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
        # Run synchronous main loop
        app.main()
    except Exception as exc:
        _print_exception(exc)
        raise


async def async_main():
    """
    Asynchronous entry point for browser/pygbag platform.

    This async wrapper is required for pygbag browser deployment. It imports
    and runs the arcade application's async_main() function, which includes
    proper event loop yielding to keep the browser responsive.

    Note: No code should follow asyncio.run() as per pygbag best practices.
    """

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
        # Run async main loop with browser-friendly yielding
        await app.async_main()
    except Exception as exc:
        _print_exception(exc)
        raise


if __name__ == "__main__":
    # Platform detection: use sys.platform for reliable browser detection
    is_browser = sys.platform == "emscripten"

    if is_browser:
        # Browser/pygbag: use async entry point
        import asyncio

        asyncio.run(async_main())
        # IMPORTANT: No code after asyncio.run() - browser execution ends here
    else:
        # Desktop/MicroPython: use synchronous entry point
        main()
