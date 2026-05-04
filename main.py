"""Bootstrap entry point for all platforms.

MicroPython (RP2040)
    Runs at boot; imports arcade_app.mpy (pre-compiled bytecode).

Desktop (CPython + PyGame)
    python main.py

Browser (pygbag / WebAssembly)
    pygbag requires `async def main()` and `asyncio.run(main())` at module
    level (NOT inside `if __name__ == "__main__"`).  Print output appears in
    the xterm console pane inside the browser tab.
"""

import sys


def _print_exception(exc):
    try:
        import traceback
        traceback.print_exc()
    except Exception:
        try:
            pe = getattr(sys, "print_exception", None)
            if pe:
                pe(exc)
                return
        except Exception:
            pass
        print("Exception:", exc)


async def main():
    print("DIY Arcade Machine – bootstrap starting")

    try:
        import gc
        gc.collect()
    except Exception:
        pass

    # ── Early pygame canvas smoke-test ──────────────────────────────────────
    # Show a coloured loading screen immediately so the browser canvas is
    # known-good before the large arcade_app module is imported.
    # arcade_app.main() will reinitialise the display once it starts.
    try:
        import asyncio as _aio
        import pygame
        pygame.init()
        _surf = pygame.display.set_mode((640, 640))
        pygame.display.set_caption("DIY Arcade Machine")
        _surf.fill((10, 0, 30))                        # dark purple

        pygame.display.flip()
        await _aio.sleep(0)          # yield so the browser renders this frame
        print("pygame canvas OK")
    except Exception as e:
        print("pygame init warning:", e)

    # ── Import the main application ─────────────────────────────────────────
    try:
        import arcade_app as app
        print("arcade_app loaded OK")
    except Exception as exc:
        print("ERROR: could not import arcade_app:", exc)
        _print_exception(exc)
        return

    # ── Run ─────────────────────────────────────────────────────────────────
    try:
        await app.main()
    except Exception as exc:
        print("ERROR in arcade_app.main():", exc)
        _print_exception(exc)


# ── Entry point ─────────────────────────────────────────────────────────────
# asyncio.run() MUST be at module level for pygbag to schedule the coroutine.
# This also works on desktop Python 3.7+ and MicroPython (uasyncio).
try:
    import asyncio
except ImportError:
    import uasyncio as asyncio  # type: ignore

asyncio.run(main())
