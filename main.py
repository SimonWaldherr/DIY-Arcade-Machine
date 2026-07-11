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

import os
import sys

try:
    import importlib.util as _importlib_util
except ImportError:
    _importlib_util = None

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
if getattr(sys, "platform", "") == "emscripten":
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


def _logo_candidates():
    paths = []
    for base in (
        os.getcwd(),
        os.path.dirname(os.path.abspath(__file__)),
        os.path.dirname(os.path.abspath(sys.argv[0])) if sys.argv else "",
    ):
        if base:
            path = os.path.join(base, "logo.png")
            if path not in paths:
                paths.append(path)
    return paths


def _hide_web_loader():
    if getattr(sys, "platform", "") != "emscripten":
        return
    try:
        import platform

        try:
            platform.window.DIYArcadeLoaderReady = True
        except Exception:
            pass
        try:
            hide_loader = getattr(platform.window, "DIYArcadeHideLoader", None)
            if hide_loader:
                hide_loader()
        except Exception:
            pass
        try:
            platform.window.transfer.hidden = True
        except Exception:
            pass
        try:
            platform.window.eval(
                "const t=document.getElementById('transfer');"
                "if(t){t.classList.add('loader-hidden');t.hidden=true;"
                "t.style.display='none';}"
                "document.title='DIY Arcade Machine';"
                "window.DIYArcadeLoaderReady=true;"
            )
        except Exception:
            pass
    except Exception:
        pass


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
        try:
            if (
                _importlib_util is not None
                and _importlib_util.find_spec("pygame.mixer") is not None
            ):
                mixer = pygame.mixer
                mixer.quit()
        except Exception:
            pass
        flags = 0
        size = (640, 640)
        existing = pygame.display.get_surface()
        if existing is not None:
            size = existing.get_size()
            _surf = existing
        else:
            _surf = pygame.display.set_mode(size, flags)
        pygame.display.set_caption("DIY Arcade Machine")
        logo = None
        for path in _logo_candidates():
            try:
                logo = pygame.image.load(path)
                break
            except Exception:
                pass
        if logo is not None:
            _surf.blit(pygame.transform.scale(logo, size), (0, 0))
        else:
            _surf.fill((10, 0, 30))  # dark purple fallback

        pygame.display.flip()
        await _aio.sleep(0)  # yield so the browser renders this frame
        _hide_web_loader()
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
# Desktop and MicroPython run this file as __main__. pygbag's browser loader
# can execute it with a different module name, so also key off emscripten.
try:
    import asyncio
except ImportError:
    import uasyncio as asyncio  # type: ignore

if __name__ == "__main__" or getattr(sys, "platform", "") == "emscripten":
    asyncio.run(main())
