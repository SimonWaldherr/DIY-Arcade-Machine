#!/usr/bin/env python3
"""Exercise the real PyGame display backend without opening a window."""

import os
from pathlib import Path
import sys


os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import arcade_app as app  # noqa: E402


def main():
    if not app.IS_DESKTOP:
        raise RuntimeError("desktop smoke test selected a non-desktop backend")
    app.display.start()
    app.display.clear()
    app.draw_rectangle(1, 1, 8, 8, 255, 80, 40)
    app.draw_text_small(12, 2, "OK", 220, 240, 255)
    app.display_flush()

    surface = getattr(app.display, "_surface", None)
    screen = getattr(app.display, "_screen", None)
    if surface is None or surface.get_size() != (app.WIDTH, app.HEIGHT):
        raise RuntimeError("logical 64x64 PyGame surface was not created")
    if screen is None:
        raise RuntimeError("PyGame output surface was not created")

    import pygame

    pygame.quit()
    print("desktop target OK: PyGame initialized, drew, scaled and presented a frame")


if __name__ == "__main__":
    main()
