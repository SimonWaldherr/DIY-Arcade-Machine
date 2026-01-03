"""
This file contains the core logic for the arcade application, including runtime detection,
display handling, and utility functions for game development. It supports both MicroPython
and desktop environments, ensuring compatibility across platforms.
"""

import random
import time
import math
import gc
import asyncio
import traceback
import sys
from typing import Any

# Module-level runtime objects. Some names are bound conditionally
# below (depending on MicroPython vs desktop). Avoid pre-annotating
# names that will later be bound via imports to prevent mypy
# redefinition warnings.
display: Any = None
rtc: Any = None
Nunchuck: Any = None
Joystick: Any = None


def _boot_log(tag):
    """
    Log a boot-time message with the current free memory (if available).
    This function is useful for debugging startup issues and tracking memory usage.

    Args:
        tag (str): A descriptive tag for the log message.
    """
    try:
        print("BOOT:", tag, gc.mem_free())
    except Exception:
        pass


# Early import-time debug marker — printed during module import.
# Visible in browser (pygbag) console and desktop logs; useful for startup diagnostics.
try:
    print("ARCADE_APP: import start")
except Exception:
    pass

# Placeholder for the optional 2048 game module. Keeps runtime binding safe
# and prevents NameError when code checks or injects this module at runtime.
mod_2048 = None


def _shuffle_in_place(seq):
    """
    Perform an in-place Fisher-Yates shuffle on the given sequence.
    This function avoids relying on `random.shuffle`, which may not be available
    on some MicroPython builds.

    Args:
        seq (list): The sequence to shuffle.
    """
    n = len(seq)
    for i in range(n - 1, 0, -1):
        j = random.randint(0, i)
        seq[i], seq[j] = seq[j], seq[i]


# ---------- Runtime detection ----------
try:
    IS_MICROPYTHON = sys.implementation.name == "micropython"
except Exception:
    IS_MICROPYTHON = False

# Detect pygbag (Emscripten) browser environment used for web builds.
# Pygbag runs CPython in WebAssembly and requires cooperative yielding to the browser.
# Use sys.platform for reliable browser detection (pygbag best practice).
try:
    IS_PYGBAG = sys.platform == "emscripten"
except Exception:
    IS_PYGBAG = False

_boot_log("runtime detect")

if IS_MICROPYTHON:
    _boot_log("before hub75 import")
    import hub75

    _boot_log("after hub75 import")
    import machine

    _boot_log("after machine import")
else:
    hub75 = None
    machine = None

# ---------- Const / Timing ----------
try:
    from micropython import const
except ImportError:

    def const(x):
        """
        Compatibility shim for MicroPython's `const()`.

        On CPython this just returns the passed value; on MicroPython the
        real `const` may help the compiler optimize constants.
        """
        return x


WIDTH = const(64)
HEIGHT = const(64)

HUD_HEIGHT = const(6)
PLAY_HEIGHT = const(HEIGHT - HUD_HEIGHT)  # 58

_boot_log("constants")

# GRID_W / GRID_H are the dimensions used by the nibble-packed grid
# (Maze / Qix). Set them from runtime display constants so they don't
# get accidentally shadowed by inlined games.
GRID_W = WIDTH
GRID_H = PLAY_HEIGHT

# pygbag yield mechanism: count CPU-bound operations and request a cooperative
# yield so the browser event loop can run. Games should call `pygbag_check_yield()`
# and yield control when it returns True.
_pygbag_op_counter = 0
_pygbag_yield_interval = 100  # force yield after this many sleep_ms calls
_pygbag_needs_yield = False


def sleep_ms(ms):
    """
    Sleep for the specified number of milliseconds, flushing the display if needed.
    On pygbag, this function also tracks operations and signals when a cooperative
    yield is required to keep the browser responsive.

    Args:
        ms (int): The number of milliseconds to sleep.
    """
    global _pygbag_op_counter, _pygbag_needs_yield

    try:
        display_flush()
    except Exception:
        pass

    if IS_PYGBAG:
        # In browser/pygbag mode, display_flush() already yields via pygame.event.pump()
        # so we don't need to sleep - just flush is enough for cooperative multitasking.
        # For longer sleeps, do a minimal non-blocking wait.
        _pygbag_op_counter += 1
        if _pygbag_op_counter >= _pygbag_yield_interval:
            _pygbag_op_counter = 0
            _pygbag_needs_yield = True
        # Don't use time.sleep() in browser as it blocks the event loop
        # The display flush above (via pygame.event.pump) handles yielding
    elif hasattr(time, "sleep_ms"):
        time.sleep_ms(ms)
    else:
        time.sleep(ms / 1000)


def pygbag_check_yield():
    """
    Check if a cooperative yield is requested by the pygbag runtime.
    This function is used to prevent the browser from becoming unresponsive
    during long-running synchronous loops.

    Returns:
        bool: True if a yield is requested, False otherwise.
    """
    global _pygbag_needs_yield
    if IS_PYGBAG and _pygbag_needs_yield:
        _pygbag_needs_yield = False
        return True
    return False


def ticks_ms():
    """
    Return the current time in milliseconds.

    Uses `time.ticks_ms()` when available (MicroPython) or falls back to
    `time.time() * 1000` on desktop runtimes. On desktop this function also
    attempts a lightweight display flush at ~60Hz to keep the window
    responsive.
    """
    now = time.ticks_ms() if hasattr(time, "ticks_ms") else int(time.time() * 1000)
    if not IS_MICROPYTHON:
        try:
            # On desktop runtimes, attempt a lightweight display flush at ~60Hz
            # to keep the window responsive without forcing a full frame every call.
            last = getattr(ticks_ms, "_last_flush", 0)
            if (now - last) >= 16:
                setattr(ticks_ms, "_last_flush", now)
                display_flush()
        except Exception:
            pass
    return now


def ticks_diff(a, b):
    """
    Return the difference between two tick values (a - b) using
    `time.ticks_diff` when available to handle wraparound.
    """
    return time.ticks_diff(a, b) if hasattr(time, "ticks_diff") else (a - b)


_gc_ctr = 0


def maybe_collect(period=90):
    """
    Perform garbage collection periodically to free up memory.

    Args:
        period (int): The number of calls before triggering garbage collection.
    """
    global _gc_ctr
    _gc_ctr += 1
    if _gc_ctr >= period:
        _gc_ctr = 0
        gc.collect()


def draw_line(x0: float, y0: float, x1: float, y1: float, *color) -> None:
    """Draw a Bresenham line between two points.

    The color may be supplied as a single (r, g, b) tuple/list or as three
    separate integers `r, g, b`.

    Args:
        x0 (float): Start x coordinate.
        y0 (float): Start y coordinate.
        x1 (float): End x coordinate.
        y1 (float): End y coordinate.
        *color: Either a single sequence (r,g,b) or three ints r, g, b.

    Raises:
        ValueError: If the color arguments are malformed.
    """
    if not color:
        raise ValueError("color must be provided as (r,g,b) or r,g,b")
    if len(color) == 1 and isinstance(color[0], (tuple, list)):
        r, g, b = color[0]
    elif len(color) == 3:
        r, g, b = color  # type: ignore[assignment]
    else:
        raise ValueError("color must be a tuple/list or three integers")

    x0_i = int(x0)
    y0_i = int(y0)
    x1_i = int(x1)
    y1_i = int(y1)

    dx = abs(x1_i - x0_i)
    dy = -abs(y1_i - y0_i)
    sx = 1 if x0_i < x1_i else -1
    sy = 1 if y0_i < y1_i else -1
    err = dx + dy
    sp = display.set_pixel

    while True:
        if 0 <= x0_i < WIDTH and 0 <= y0_i < PLAY_HEIGHT:
            sp(x0_i, y0_i, int(r), int(g), int(b))
        if x0_i == x1_i and y0_i == y1_i:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0_i += sx
        if e2 <= dx:
            err += dx
            y0_i += sy


def make_explosion(x: float, y: float, max_r: int, color) -> dict:
    """Create a normalized explosion dict used by animation code.

    Args:
        x: Explosion center x.
        y: Explosion center y.
        max_r: Maximum radius for the explosion animation.
        color: (r,g,b) color tuple.

    Returns:
        dict: Explosion entry with typed fields used by update/draw code.
    """
    return {"x": float(x), "y": float(y), "r": 0, "dr": 1, "max": max_r, "col": color}


def render_explosion(ex: dict) -> None:
    """Render a single explosion ring described by `ex` onto `display`.

    This extracts the drawing logic out of game classes so it can be reused.
    """
    r = ex.get("r", 0)
    if r <= 0:
        return
    x0 = ex.get("x", 0)
    y0 = ex.get("y", 0)
    col = ex.get("col", (255, 255, 255))
    sp = display.set_pixel
    for deg in range(0, 360, 18):
        a = math.radians(deg)
        x = int(x0 + math.cos(a) * r)
        y = int(y0 + math.sin(a) * r)
        if 0 <= x < WIDTH and 0 <= y < PLAY_HEIGHT:
            sp(x, y, col[0], col[1], col[2])


# ---------- Display ----------
if IS_MICROPYTHON:
    _boot_log("before display")
    try:
        display = hub75.Hub75(WIDTH, HEIGHT)
        _boot_log("after display")
    except MemoryError as e:
        print("MemoryError creating display:", e)
        raise
    rtc = machine.RTC()
    _boot_log("after rtc")
else:
    # Desktop (Python) runtime: emulate HUB75 LED matrix using pygame.
    class _DesktopRTC:
        def datetime(self):
            """
            Return the current localtime in a MicroPython `machine.RTC`-compatible
            tuple: (year, month, day, weekday, hour, minute, second, subseconds).
            """
            # machine.RTC().datetime() layout: (year, month, day, weekday, hour, minute, second, subseconds)
            lt = time.localtime()
            # weekday: MicroPython usually uses 0=Mon..6=Sun
            return (lt[0], lt[1], lt[2], lt[6], lt[3], lt[4], lt[5], 0)

    class _PyGameDisplay:
        def __init__(self, w, h, scale=10):
            """
            Initialize the PyGame-based display emulator.

            Args:
                w (int): Display width in pixels.
                h (int): Display height in pixels.
                scale (int): Window scaling factor for desktop display.
            """
            self.w = int(w)
            self.h = int(h)
            self.scale = int(scale)
            self._pg = None
            self._screen = None
            self._surface = None
            self._inited = False

        def start(self):
            """
            Initialize the PyGame display and internal surfaces.

            This method is idempotent and will do nothing if initialization
            has already been performed.
            """
            if self._inited:
                return
            try:
                import pygame  # type: ignore
            except Exception as e:
                raise RuntimeError(
                    "PyGame not installed. Install with: pip install pygame"
                ) from e
            self._pg = pygame
            pygame.init()
            # In browser (pygbag) pygame's audio/mixer init may trigger
            # user-gesture blocking or unsupported audio device errors.
            # Quit the mixer immediately in that environment to avoid
            # blocking the startup; desktop audio remains available when
            # not running in WASM.
            try:
                if IS_PYGBAG and hasattr(pygame, "mixer"):
                    try:
                        pygame.mixer.quit()
                    except Exception:
                        pass
            except Exception:
                pass
            pygame.display.set_caption("DIY Arcade Machine (Desktop)")
            self._screen = pygame.display.set_mode(
                (self.w * self.scale, self.h * self.scale)
            )
            self._surface = pygame.Surface((self.w, self.h))
            self.clear()
            self.show()
            self._inited = True

        def set_pixel(self, x, y, r, g, b):
            """
            Set a pixel on the internal surface with bounds checking.

            Args:
                x, y (int): Pixel coordinates.
                r, g, b (int): Color channels (0-255).
            """
            if not self._surface:
                return
            if 0 <= x < self.w and 0 <= y < self.h:
                self._surface.set_at(
                    (int(x), int(y)), (int(r) & 255, int(g) & 255, int(b) & 255)
                )

        def clear(self):
            """
            Clear the internal surface by filling it with black.
            """
            if self._surface:
                self._surface.fill((0, 0, 0))

        def show(self):
            """
            Present the internal surface to the PyGame window (scaled).

            Also pumps the event queue to keep the desktop window responsive.
            """
            if not self._pg or not self._screen or not self._surface:
                return
            # keep window responsive
            self._pg.event.pump()
            scaled = self._pg.transform.scale(
                self._surface, (self.w * self.scale, self.h * self.scale)
            )
            self._screen.blit(scaled, (0, 0))
            self._pg.display.flip()

    display = _PyGameDisplay(WIDTH, HEIGHT, scale=10)
    rtc = _DesktopRTC()

# Wrap the low-level `display` with `ShadowBuffer` from `game_utils`.
# The ShadowBuffer provides a software diff layer to minimize per-pixel writes
# and reduce expensive I/O on HUB75 hardware or desktop emulation.
try:
    import game_utils

    display = game_utils.ShadowBuffer(WIDTH, HEIGHT, display)
    _boot_log("display wrapped with ShadowBuffer")
except Exception:
    _boot_log("display wrap failed")

# Prefer the software framebuffer diff layer on constrained MicroPython
# HUB75 targets to reduce write amplification. Delay allocating large
# framebuffers until after `display.start()` to avoid early heap pressure
# or hub75 driver allocation failures during boot.
USE_BUFFERED_DISPLAY_DESIRED = IS_MICROPYTHON
USE_BUFFERED_DISPLAY = False

_boot_log("buffer flags")

# ---------- Framebuffer diff / buffered drawing ----------
# Maintain a software framebuffer and push only changed pixels to the
# hardware. This reduces I/O and CPU on embedded targets with limited
# bandwidth (HUB75 panels) while keeping the API compatible with desktop
# emulation.
_fb_w = WIDTH
_fb_h = HEIGHT
_fb_size = _fb_w * _fb_h * 3
_fb_current = None
_fb_prev = None
_dirty_mask = None
_force_full_flush = False

_boot_log("framebuffer vars")

_display_set_pixel_orig = display.set_pixel
_display_clear_orig = getattr(display, "clear", None)

_boot_log("display refs")


def init_buffered_display():
    """
    Allocate and initialize the software framebuffer for buffered drawing.
    This reduces write amplification on HUB75 hardware and improves performance.
    """
    global USE_BUFFERED_DISPLAY, _fb_current, _fb_prev, _dirty_mask, _force_full_flush
    if USE_BUFFERED_DISPLAY:
        return
    if not USE_BUFFERED_DISPLAY_DESIRED:
        return

    try:
        gc.collect()
    except Exception:
        pass

    try:
        if _fb_current is None or len(_fb_current) != _fb_size:
            _fb_current = bytearray(_fb_size)
        if _fb_prev is None or len(_fb_prev) != _fb_size:
            _fb_prev = bytearray(_fb_size)
    except MemoryError:
        _fb_current = None
        _fb_prev = None
        return

    try:
        if _dirty_mask is None or len(_dirty_mask) != (_fb_w * _fb_h):
            _dirty_mask = bytearray(_fb_w * _fb_h)
        _force_full_flush = True
    except MemoryError:
        _dirty_mask = None
        return

    # Apply our buffered hooks if the hardware object exposes the expected methods.
    try:
        display.set_pixel = _set_pixel_buf
        display.clear = _clear_buf
        USE_BUFFERED_DISPLAY = True
    except Exception:
        USE_BUFFERED_DISPLAY = False


def _mark_dirty_pixel(px):
    """
    Mark a pixel (by linear index) as dirty in the dirty mask.

    This is a legacy stub kept for compatibility with existing call-sites.
    """
    # legacy stub (kept to avoid touching other call-sites)
    if _dirty_mask is not None:
        _dirty_mask[px] = 1


def _set_pixel_buf(x, y, r, g, b):
    """
    Buffered set_pixel: write into the software framebuffer and mark pixel dirty.
    This prevents immediate hardware writes and allows efficient diffs.

    Args:
        x, y (int): Coordinates.
        r, g, b (int): Color components.
    """
    if x < 0 or x >= _fb_w or y < 0 or y >= _fb_h:
        return
    pix = y * _fb_w + x
    idx = pix * 3
    if _fb_current is None:
        return
    if _fb_current[idx] != r or _fb_current[idx + 1] != g or _fb_current[idx + 2] != b:
        _fb_current[idx] = r
        _fb_current[idx + 1] = g
        _fb_current[idx + 2] = b
        if _dirty_mask is not None:
            _dirty_mask[pix] = 1


def _clear_buf():
    """
    Clear the software framebuffer and mark the full buffer dirty so the
    next flush rewrites all pixels to the hardware/display.
    """
    w = _fb_w * _fb_h
    global _force_full_flush
    if _fb_current is not None:
        for i in range(w * 3):
            if _fb_current[i] != 0:
                _fb_current[i] = 0
    # Avoid building a large Python list of dirty indices; use a compact
    # bytearray mask instead to track modified pixels.
    _force_full_flush = True
    if _dirty_mask is not None:
        for i in range(w):
            _dirty_mask[i] = 0
    # Also clear the underlying hardware/display quickly if supported.
    if _display_clear_orig:
        try:
            _display_clear_orig()
        except Exception:
            pass


def display_flush():
    """
    Flush pending framebuffer changes to the underlying display.
    If buffered drawing is disabled, call the display's `show()` method.
    """
    if not USE_BUFFERED_DISPLAY:
        try:
            if hasattr(display, "show"):
                display.show()
        except Exception:
            pass
        return
    # Push changed pixels to the hardware/display and update the previous
    # frame buffer snapshot for future diffs.
    if _fb_current is None or _fb_prev is None or _dirty_mask is None:
        return
    sp = _display_set_pixel_orig
    w = _fb_w * _fb_h
    global _force_full_flush
    if _force_full_flush:
        for pix in range(w):
            idx = pix * 3
            r = _fb_current[idx]
            g = _fb_current[idx + 1]
            b = _fb_current[idx + 2]
            if _fb_prev[idx] != r or _fb_prev[idx + 1] != g or _fb_prev[idx + 2] != b:
                try:
                    sp(pix % _fb_w, pix // _fb_w, r, g, b)
                except Exception:
                    pass
                _fb_prev[idx] = r
                _fb_prev[idx + 1] = g
                _fb_prev[idx + 2] = b
        _force_full_flush = False
    else:
        for pix in range(w):
            if _dirty_mask[pix] == 0:
                continue
            _dirty_mask[pix] = 0
            idx = pix * 3
            r = _fb_current[idx]
            g = _fb_current[idx + 1]
            b = _fb_current[idx + 2]
            if _fb_prev[idx] != r or _fb_prev[idx + 1] != g or _fb_prev[idx + 2] != b:
                try:
                    sp(pix % _fb_w, pix // _fb_w, r, g, b)
                except Exception:
                    pass
                _fb_prev[idx] = r
                _fb_prev[idx + 1] = g
                _fb_prev[idx + 2] = b
    # Desktop display needs an explicit present; HUB75 hardware does not.
    try:
        if hasattr(display, "show"):
            display.show()
    except Exception:
        pass


# Note: hooks are installed by init_buffered_display() after display.start().


# Helper for games: use this to push changed pixels to the hardware.
def push_frame():
    """
    Convenience helper for games to push the current frame to hardware.
    Wraps `display_flush()` and swallows exceptions for robustness.
    """
    try:
        display_flush()
    except Exception:
        pass


# Shared helper for playfield-aware rectangles
def draw_play_rect(x, y, w, h, r, g, b):
    """
    Draw a filled rectangle restricted to the play area (leaving HUD untouched).

    Args:
        x, y, w, h (int): Rectangle position and size.
        r, g, b (int): Color.
    """
    x1 = x
    y1 = y
    x2 = x + w - 1
    y2 = y + h - 1
    if y2 < 0 or y1 >= PLAY_HEIGHT:
        return
    if y1 < 0:
        y1 = 0
    if y2 >= PLAY_HEIGHT:
        y2 = PLAY_HEIGHT - 1
    draw_rectangle(x1, y1, x2, y2, r, g, b)


# ---------- Global state ----------
global_score = 0
game_over = False

# ---------- Colors ----------
COLORS_BRIGHT = [
    (255, 0, 0),  # Red
    (0, 255, 0),  # Green
    (0, 0, 255),  # Blue
    (255, 255, 0),  # Yellow
]
# Pre-computed to avoid list comprehension allocations during import
colors = (
    (127, 0, 0),
    (0, 127, 0),
    (0, 0, 127),
    (127, 127, 0),
)
inactive_colors = (
    (51, 0, 0),
    (0, 51, 0),
    (0, 0, 51),
    (51, 51, 0),
)

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)

# ---------- Joystick directions ----------
JOYSTICK_UP = "UP"
JOYSTICK_DOWN = "DOWN"
JOYSTICK_LEFT = "LEFT"
JOYSTICK_RIGHT = "RIGHT"
JOYSTICK_UP_LEFT = "UP-LEFT"
JOYSTICK_UP_RIGHT = "UP-RIGHT"
JOYSTICK_DOWN_LEFT = "DOWN-LEFT"
JOYSTICK_DOWN_RIGHT = "DOWN-RIGHT"

# ---------- Fonts ----------
# NOTE: On MicroPython, even defining large dicts at module level can trigger
# MemoryError during import. We define them inside functions (lazy) to avoid
# any allocation until first use.


def _get_char_dict():
    """
    Return a mapping of characters to their 8x8 hex font rows.

    This is defined lazily to avoid allocating large tables at import time
    on memory-constrained MicroPython targets.
    """
    return {
        "A": "3078ccccfccccc00",
        "B": "fc66667c6666fc00",
        "C": "3c66c0c0c0663c00",
        "D": "f86c6666666cf800",
        "E": "fe6268786862fe00",
        "F": "fe6268786860f000",
        "G": "3c66c0c0ce663e00",
        "H": "ccccccfccccccc00",
        "I": "7830303030307800",
        "J": "1e0c0c0ccccc7800",
        "K": "f6666c786c66f600",
        "L": "f06060606266fe00",
        "M": "c6eefefed6c6c600",
        "N": "c6e6f6decec6c600",
        "O": "386cc6c6c66c3800",
        "P": "fc66667c6060f000",
        "Q": "78ccccccdc781c00",
        "R": "fc66667c6c66f600",
        "S": "78cce0380ccc7800",
        "T": "fcb4303030307800",
        "U": "ccccccccccccfc00",
        "V": "cccccccccc783000",
        "W": "c6c6c6d6feeec600",
        "X": "c6c66c38386cc600",
        "Y": "cccccc7830307800",
        "Z": "fec68c183266fe00",
        "0": "78ccdcfceccc7c00",
        "1": "307030303030fc00",
        "2": "78cc0c3860ccfc00",
        "3": "78cc0c380ccc7800",
        "4": "1c3c6cccfe0c1e00",
        "5": "fcc0f80c0ccc7800",
        "6": "3860c0f8cccc7800",
        "7": "fccc0c1830303000",
        "8": "78cccc78cccc7800",
        "9": "78cccc7c0c187000",
        "!": "3078783030003000",
        "#": "6c6cfe6cfe6c6c00",
        "$": "307cc0780cf83000",
        "%": "00c6cc183066c600",
        "&": "386c3876dccc7600",
        "?": "78cc0c1830003000",
        " ": "0000000000000000",
        ".": "0000000000003000",
        ":": "0030000000300000",
        "(": "0c18303030180c00",
        ")": "6030180c18306000",
        "-": "000000fc00000000",
    }


def _get_nums_dict():
    """
    Return the 5x5 bitmap font definitions used for small-text rendering.

    The mapping is defined lazily to avoid allocating the full table at
    import time on memory-constrained MicroPython targets.
    """
    return {
        "0": ["01110", "10001", "10001", "10001", "01110"],
        "1": ["00100", "01100", "00100", "00100", "01110"],
        "2": ["11110", "00001", "01110", "10000", "11111"],
        "3": ["11110", "00001", "00110", "00001", "11110"],
        "4": ["10000", "10010", "10010", "11111", "00010"],
        "5": ["11111", "10000", "11110", "00001", "11110"],
        "6": ["01110", "10000", "11110", "10001", "01110"],
        "7": ["11111", "00010", "00100", "01000", "10000"],
        "8": ["01110", "10001", "01110", "10001", "01110"],
        "9": ["01110", "10001", "01111", "00001", "01110"],
        "A": ["01110", "10001", "10001", "11111", "10001"],
        "B": ["11110", "10001", "11110", "10001", "11110"],
        "C": ["01110", "10001", "10000", "10001", "01110"],
        "D": ["11100", "10010", "10001", "10010", "11100"],
        "E": ["11111", "10000", "11110", "10000", "11111"],
        "F": ["11111", "10000", "11110", "10000", "10000"],
        "G": ["01110", "10000", "10111", "10001", "01110"],
        "H": ["10001", "10001", "11111", "10001", "10001"],
        "I": ["01110", "00100", "00100", "00100", "01110"],
        "J": ["00111", "00010", "00010", "10010", "01100"],
        "K": ["10010", "10100", "11000", "10100", "10010"],
        "L": ["10000", "10000", "10000", "10000", "11111"],
        "M": ["10001", "11011", "10101", "10001", "10001"],
        "N": ["10001", "11001", "10101", "10011", "10001"],
        "O": ["01110", "10001", "10001", "10001", "01110"],
        "P": ["11110", "10001", "11110", "10000", "10000"],
        "Q": ["01110", "10001", "10001", "10011", "01111"],
        "R": ["11110", "10001", "11110", "10010", "10001"],
        "S": ["01111", "10000", "01110", "00001", "11110"],
        "T": ["11111", "00100", "00100", "00100", "00100"],
        "U": ["10001", "10001", "10001", "10001", "01110"],
        "V": ["10001", "10001", "10001", "01010", "00100"],
        "W": ["10001", "10001", "10101", "11011", "10001"],
        "X": ["10001", "01010", "00100", "01010", "10001"],
        "Y": ["10001", "01010", "00100", "00100", "00100"],
        "Z": ["11111", "00010", "00100", "01000", "11111"],
        " ": ["00000", "00000", "00000", "00000", "00000"],
        ".": ["00000", "00000", "00000", "00000", "00001"],
        ":": ["00000", "00100", "00000", "00100", "00000"],
        "/": ["00001", "00010", "00100", "01000", "10000"],
        "|": ["00100", "00100", "00100", "00100", "00100"],
        "-": ["00000", "00000", "11111", "00000", "00000"],
        "=": ["00000", "11111", "00000", "11111", "00000"],
        "+": ["00000", "00100", "01110", "00100", "00000"],
        "*": ["00000", "10101", "01110", "10101", "00000"],
        "(": ["00010", "00100", "00100", "00100", "00010"],
        ")": ["00100", "00010", "00010", "00010", "00100"],
    }


def _hex_to_bytes(hex_str):
    """
    Convert a hex string to bytes, with a fallback for Python versions
    that don't provide `bytes.fromhex`.
    """
    try:
        return bytes.fromhex(hex_str)
    except AttributeError:
        out = bytearray(len(hex_str) // 2)
        oi = 0
        for i in range(0, len(hex_str), 2):
            out[oi] = int(hex_str[i : i + 2], 16)
            oi += 1
        return bytes(out)


# Lazy caches (created on first use to reduce MicroPython import pressure)
_FONT8_CACHE = None
_FONT5_CACHE = None


def _get_font8(ch):
    """Return 8 row-bytes for a character (8x8 font)."""
    global _FONT8_CACHE
    cache = _FONT8_CACHE
    if cache is None:
        cache = {}
        _FONT8_CACHE = cache

    v = cache.get(ch)
    if v is not None:
        return v

    hs = _get_char_dict().get(ch)
    if not hs:
        hs = _get_char_dict().get(" ")
        if not hs:
            cache[ch] = b"\x00" * 8
            return cache[ch]

    rows = _hex_to_bytes(hs)
    # Ensure we always return exactly 8 rows
    if not rows or len(rows) != 8:
        rows = (rows or b"")[:8] + (b"\x00" * (8 - len(rows or b"")))

    cache[ch] = rows
    return rows


def _get_font5(ch):
    """Return 5 row bitmasks for a character (5x5 font)."""
    global _FONT5_CACHE
    cache = _FONT5_CACHE
    if cache is None:
        cache = {}
        _FONT5_CACHE = cache

    v = cache.get(ch)
    if v is not None:
        return v

    rows = _get_nums_dict().get(ch)
    if rows is None:
        rows = _get_nums_dict().get(" ")
    if rows is None:
        cache[ch] = (0, 0, 0, 0, 0)
        return cache[ch]

    out = [0, 0, 0, 0, 0]
    for i in range(5):
        try:
            out[i] = int(rows[i], 2)
        except Exception:
            out[i] = 0
    out = tuple(out)
    cache[ch] = out
    return out


# ---------- Drawing ----------
def draw_rectangle(x1, y1, x2, y2, r, g, b):
    """
    Draw a filled rectangle between two coordinates on the full display.
    Handles out-of-bounds clipping to the display extents.
    """
    if x1 > x2:
        x1, x2 = x2, x1
    if y1 > y2:
        y1, y2 = y2, y1
    if x2 < 0 or y2 < 0 or x1 >= WIDTH or y1 >= HEIGHT:
        return
    if x1 < 0:
        x1 = 0
    if y1 < 0:
        y1 = 0
    if x2 >= WIDTH:
        x2 = WIDTH - 1
    if y2 >= HEIGHT:
        y2 = HEIGHT - 1
    sp = display.set_pixel
    for y in range(y1, y2 + 1):
        for x in range(x1, x2 + 1):
            sp(x, y, r, g, b)


def draw_character(x, y, ch, r, g, b):
    """
    Draw an 8x8 character at the given coordinates using the 8x8 font.
    """
    rows = _get_font8(ch)
    if not rows:
        return
    sp = display.set_pixel
    for dy in range(8):
        yy = y + dy
        if yy < 0 or yy >= HEIGHT:
            continue
        row = rows[dy]
        mask = 0x80
        for dx in range(8):
            if row & (mask >> dx):
                xx = x + dx
                if 0 <= xx < WIDTH:
                    sp(xx, yy, r, g, b)


def draw_text(x, y, text, r, g, b):
    """
    Draw a string using the 8x8 font. Characters are spaced by 9 pixels.
    """
    ox = x
    for ch in text:
        draw_character(ox, y, ch, r, g, b)
        ox += 9


def draw_character_small(x, y, ch, r, g, b):
    """
    Draw a 5x5 (small) character at the given coordinates using the 5x5 font.
    """
    rows = _get_font5(ch)
    if not rows:
        return
    sp = display.set_pixel
    for dy in range(5):
        yy = y + dy
        if yy < 0 or yy >= HEIGHT:
            continue
        row = rows[dy]  # 5 bits
        for dx in range(5):
            if row & (1 << (4 - dx)):
                xx = x + dx
                if 0 <= xx < WIDTH:
                    sp(xx, yy, r, g, b)


def draw_text_small(x, y, text, r, g, b):
    """
    Draw a string using the small 5x5 font. Characters are spaced by 6 pixels.
    """
    ox = x
    for ch in text:
        draw_character_small(ox, y, ch, r, g, b)
        ox += 6


# ---------- HUD ----------
_hud_last_ms = 0
_hud_time_str = "00:00"
_hud_last_text = None


def display_score_and_time(score, force=False):
    """
    Update and render the HUD (score and clock) when values change.

    Redraws only when the displayed text differs or when `force` is True
    to minimize unnecessary framebuffer updates.
    """
    global _hud_last_ms, _hud_time_str, _hud_last_text, global_score
    global_score = int(score or 0)

    now = ticks_ms()
    if force or ticks_diff(now, _hud_last_ms) >= 1000:
        try:
            year, month, day, weekday, hour, minute, second, _ = rtc.datetime()
            _hud_time_str = "{:02}:{:02}".format(hour, minute)
        except Exception:
            _hud_time_str = "00:00"
        _hud_last_ms = now

    score_str = str(global_score)
    text = score_str + " " + _hud_time_str

    if text != _hud_last_text:
        _hud_last_text = text
        draw_rectangle(0, PLAY_HEIGHT, WIDTH - 1, HEIGHT - 1, 0, 0, 0)

    draw_text_small(1, PLAY_HEIGHT, score_str, 255, 255, 255)
    time_x = WIDTH - (len(_hud_time_str) * 6)
    draw_text_small(time_x, PLAY_HEIGHT, _hud_time_str, 255, 255, 255)
    # flush buffered drawing to hardware (only changed pixels)
    try:
        display_flush()
    except Exception:
        pass


# ---------- Grid (nibble-packed) for Maze/Qix ----------
# GRID_W = WIDTH
# GRID_H = PLAY_HEIGHT
grid = None  # lazy-allocated to reduce import-time RAM usage on MicroPython


def initialize_grid():
    """
    Allocate or reset the nibble-packed grid used by grid-based games.

    The grid stores two 4-bit cells per byte to reduce memory usage on
    constrained targets.
    """
    global grid
    size = (GRID_W * GRID_H + 1) // 2
    if grid is None or len(grid) != size:
        grid = bytearray(size)
    else:
        for i in range(size):
            grid[i] = 0


def _ensure_grid():
    """
    Ensure the global `grid` bytearray exists (lazy allocation).

    Avoids allocating the large grid at import time on memory-constrained
    MicroPython targets; allocates on first use.
    """
    # Small helper to avoid allocating at import-time.
    global grid
    if grid is None:
        grid = bytearray((GRID_W * GRID_H + 1) // 2)


def get_grid_value(x, y):
    """
    Return the 4-bit value stored at grid coordinate (x, y).

    Treats out-of-bounds coordinates as walls (returns 1).
    """
    _ensure_grid()
    if x < 0 or x >= GRID_W or y < 0 or y >= GRID_H:
        return 1  # treat out-of-bounds as wall/border
    idx = y * GRID_W + x
    b = grid[idx >> 1]
    if idx & 1:
        return (b >> 4) & 0x0F
    return b & 0x0F


def set_grid_value(x, y, value):
    """
    Set the 4-bit value at grid coordinate (x, y) in the nibble-packed buffer.

    Performs bounds checking and masks the value to 4 bits.
    """
    _ensure_grid()
    if x < 0 or x >= GRID_W or y < 0 or y >= GRID_H:
        return
    idx = y * GRID_W + x
    bi = idx >> 1
    if idx & 1:
        grid[bi] = (grid[bi] & 0x0F) | ((value & 0x0F) << 4)
    else:
        grid[bi] = (grid[bi] & 0xF0) | (value & 0x0F)


def flood_fill(x, y, accessible_mark=3, max_steps=9000):
    """
    Flood-fill from (x, y) marking reachable empty cells with `accessible_mark`.

    Uses a packed integer stack ((y << 8) | x) to reduce tuple allocations
    and limit memory pressure on embedded targets.
    """
    # use packed integer stack to reduce tuple allocations and memory pressure
    # pack: (y << 8) | x  -- works for WIDTH, GRID_H < 256
    if x < 0 or x >= GRID_W or y < 0 or y >= GRID_H:
        return False
    pack = (y << 8) | x
    stack = [pack]
    steps = 0
    while stack and steps < max_steps:
        v = stack.pop()
        px = v & 0xFF
        py = v >> 8
        if px < 0 or px >= GRID_W or py < 0 or py >= GRID_H:
            continue
        if get_grid_value(px, py) != 0:
            continue
        set_grid_value(px, py, accessible_mark)
        steps += 1
        # push neighbors only if they are inside bounds and empty to avoid extra pushes
        nx = px + 1
        if nx < GRID_W and get_grid_value(nx, py) == 0:
            stack.append((py << 8) | nx)
        nx = px - 1
        if nx >= 0 and get_grid_value(nx, py) == 0:
            stack.append((py << 8) | nx)
        ny = py + 1
        if ny < GRID_H and get_grid_value(px, ny) == 0:
            stack.append((ny << 8) | px)
        ny = py - 1
        if ny >= 0 and get_grid_value(px, ny) == 0:
            stack.append((ny << 8) | px)
    return bool(stack)


def count_cells_with_mark(mark, width, height):
    """
    Count how many cells in a width*height nibble-packed grid equal `mark`.

    Operates directly on the packed bytearray representation.
    """
    cells = width * height
    nbytes = (cells + 1) // 2
    last_has_high = (cells & 1) == 0  # even -> last high nibble used
    cnt = 0
    for i in range(nbytes):
        b = grid[i]
        if (b & 0x0F) == mark:
            cnt += 1
        if i == nbytes - 1 and (not last_has_high):
            continue
        if ((b >> 4) & 0x0F) == mark:
            cnt += 1
    return cnt


# ---------- Control exception ----------
class RestartProgram(Exception):
    """
    Special exception used to trigger a soft restart of the program.
    Raised by input handlers on special button combinations.
    """

    pass


# ---------- Nunchuk / Joystick ----------
NEW_CONTROLLER_SIGNATURE = b"\xa0\x20\x10\x00\xff\xff\x00\x00"

if IS_MICROPYTHON:

    class NunchuckMicro:
        def __init__(self, i2c, poll=True, poll_interval=50):
            """
            Initialize the Nunchuck controller wrapper.

            Performs initial I2C setup and attempts to auto-detect the newer
            controller variant by reading a fixed signature; adjusts read
            length and decoding accordingly.
            """
            self.i2c = i2c
            self.address = 0x52
            self.is_new_controller = False
            self.read_len = 6
            self.buffer = bytearray(self.read_len)
            self.i2c.writeto(self.address, b"\xf0\x55")
            self.i2c.writeto(self.address, b"\xfb\x00")

            # Auto-detect new controller: first 8-byte read matches fixed signature
            # Signature given by user: "A0 20 10 00 FF FF 00 00"
            try:
                self.i2c.writeto(self.address, b"\x00")
                sig = self.i2c.readfrom(self.address, 8)
                if sig == NEW_CONTROLLER_SIGNATURE:
                    self.is_new_controller = True
                    self.read_len = 8
                    self.buffer = bytearray(8)
                    self.buffer[:] = sig
            except Exception:
                # fall back to old controller behavior
                self.is_new_controller = False
                self.read_len = 6
                self.buffer = bytearray(6)

            self.last_poll = ticks_ms()
            self.polling_threshold = poll_interval if poll else -1

        def update(self):
            """
            Read the latest controller packet into the internal buffer.
            """
            self.i2c.writeto(self.address, b"\x00")
            self.i2c.readfrom_into(self.address, self.buffer)

        def _new_decode(self):
            """
            Decode button bitfields from the new (8-byte) controller packet.

            Returns a tuple of booleans for (up, down, left, right, A, B, start, select).
            """
            # New controller mapping derived from captured packets.
            # Active-low bitfields:
            # byte4: right(bit7), down(bit6), select(bit4), start(bit2)
            # byte5: up(bit0), left(bit1), A(bit4), B(bit6)
            b4 = self.buffer[4]
            b5 = self.buffer[5]
            up = not (b5 & 0x01)
            left = not (b5 & 0x02)
            a_btn = not (b5 & 0x10)
            b_btn = not (b5 & 0x40)

            right = not (b4 & 0x80)
            down = not (b4 & 0x40)
            select = not (b4 & 0x10)
            start = not (b4 & 0x04)
            return up, down, left, right, a_btn, b_btn, start, select

        def __poll(self):
            """
            Poll the controller when the polling threshold has elapsed.

            This method is called internally to refresh the input buffer at
            a regular interval controlled by `polling_threshold`.
            """
            if (
                self.polling_threshold > 0
                and ticks_diff(ticks_ms(), self.last_poll) > self.polling_threshold
            ):
                self.update()
                self.last_poll = ticks_ms()

        def buttons(self):
            """
            Return the current button state as a tuple (c_button, z_button).
            May raise `RestartProgram` on special restart combinations.
            """
            self.__poll()
            if not self.is_new_controller:
                c_button = not (self.buffer[5] & 0x02)
                z_button = not (self.buffer[5] & 0x01)
                if c_button and z_button:
                    raise RestartProgram()
                return c_button, z_button

            up, down, left, right, a_btn, b_btn, start, select = self._new_decode()
            # Map to existing API:
            # - z_button: primary action (A)
            # - c_button: secondary/back (B)
            c_button = bool(b_btn)
            z_button = bool(a_btn)
            # Restart combo on new controller: START + SELECT
            if start and select:
                raise RestartProgram()
            return c_button, z_button

        def joystick(self):
            """
            Return a 2-tuple (x, y) representing analog joystick position (0-255).
            For new digital controllers this synthesizes values from the D-pad.
            """
            self.__poll()
            if not self.is_new_controller:
                return (self.buffer[0], self.buffer[1])

            # New controller does not provide analog joystick in the same way.
            # Synthesize analog-like values from the D-pad so the existing
            # read_direction() threshold logic keeps working.
            up, down, left, right, a_btn, b_btn, start, select = self._new_decode()
            x = 128
            y = 128
            if left and not right:
                x = 0
            elif right and not left:
                x = 255
            if up and not down:
                y = 255
            elif down and not up:
                y = 0
            return (x, y)

    class JoystickMicro:
        def __init__(self):
            """Initialize a MicroPython I2C Nunchuck-backed joystick wrapper.

            This wrapper provides a `read_direction()` helper compatible with the
            desktop joystick API by delegating to a connected Wii Nunchuck over
            I2C.
            """
            self.i2c = machine.I2C(0, scl=machine.Pin(21), sda=machine.Pin(20))
            self.nunchuck = Nunchuck(self.i2c, poll=True, poll_interval=50)

        def read_direction(self, possible_directions, debounce=True):
            """
            Map raw analog joystick values into one of the named directions.
            Returns a direction string from the possible_directions set.
            """
            x, y = self.nunchuck.joystick()

            # diagonals first
            if x < 100 and y < 100 and JOYSTICK_DOWN_LEFT in possible_directions:
                return JOYSTICK_DOWN_LEFT
            if x > 150 and y < 100 and JOYSTICK_DOWN_RIGHT in possible_directions:
                return JOYSTICK_DOWN_RIGHT
            if x < 100 and y > 150 and JOYSTICK_UP_LEFT in possible_directions:
                return JOYSTICK_UP_LEFT
            if x > 150 and y > 150 and JOYSTICK_UP_RIGHT in possible_directions:
                return JOYSTICK_UP_RIGHT

            if x < 100 and JOYSTICK_LEFT in possible_directions:
                return JOYSTICK_LEFT
            if x > 150 and JOYSTICK_RIGHT in possible_directions:
                return JOYSTICK_RIGHT
            if y < 100 and JOYSTICK_DOWN in possible_directions:
                return JOYSTICK_DOWN
            if y > 150 and JOYSTICK_UP in possible_directions:
                return JOYSTICK_UP
            return None

        def is_pressed(self):
            """Return whether the primary action button is pressed.

            Delegates to the underlying `Nunchuck.buttons()` tuple and
            returns the `z` (primary) button state.
            """
            _, z = self.nunchuck.buttons()
            return z
else:

    class NunchuckDesktop:
        # Desktop keyboard input emulating the nunchuck API.
        def __init__(self):
            """Initialize a keyboard-driven Nunchuck emulator for desktop.

            Maps arrow keys and common letter keys to the Nunchuck API used
            by the rest of the code so desktop testing matches embedded input.
            """
            self._z = False
            self._c = False
            self._x = 128
            self._y = 128

        def _poll(self):
            """
            Poll keyboard state via PyGame and update emulated joystick/buttons.
            """
            try:
                import pygame  # type: ignore
            except Exception:
                return
            pygame.event.pump()
            keys = pygame.key.get_pressed()
            left = keys[pygame.K_LEFT]
            right = keys[pygame.K_RIGHT]
            up = keys[pygame.K_UP]
            down = keys[pygame.K_DOWN]

            # Z button: z/space/enter
            self._z = bool(
                keys[pygame.K_z] or keys[pygame.K_SPACE] or keys[pygame.K_RETURN]
            )
            # C button: x/escape
            self._c = bool(keys[pygame.K_x] or keys[pygame.K_ESCAPE])

            x = 128
            y = 128
            if left and not right:
                x = 0
            elif right and not left:
                x = 255
            if up and not down:
                y = 255
            elif down and not up:
                y = 0
            self._x = x
            self._y = y

        def buttons(self):
            """
            Return emulated (c_button, z_button) from keyboard input.
            Raises `RestartProgram` when the restart combo is pressed.
            """
            self._poll()
            if self._c and self._z:
                raise RestartProgram()
            return self._c, self._z

        def joystick(self):
            """
            Return emulated analog joystick coordinates (x, y) from keyboard
            directional keys.
            """
            self._poll()
            return (self._x, self._y)

    class JoystickDesktop:
        def __init__(self):
            """Initialize the desktop `Joystick` wrapper using `Nunchuck`.

            Provides `read_direction()` compatible API for desktop testing.
            """
            self.nunchuck = Nunchuck()

        def read_direction(self, possible_directions, debounce=True):
            """
            Convert emulated joystick analog values to a direction string.
            """
            x, y = self.nunchuck.joystick()

            # diagonals first
            if x < 100 and y < 100 and JOYSTICK_DOWN_LEFT in possible_directions:
                return JOYSTICK_DOWN_LEFT
            if x > 150 and y < 100 and JOYSTICK_DOWN_RIGHT in possible_directions:
                return JOYSTICK_DOWN_RIGHT
            if x < 100 and y > 150 and JOYSTICK_UP_LEFT in possible_directions:
                return JOYSTICK_UP_LEFT
            if x > 150 and y > 150 and JOYSTICK_UP_RIGHT in possible_directions:
                return JOYSTICK_UP_RIGHT

            if x < 100 and JOYSTICK_LEFT in possible_directions:
                return JOYSTICK_LEFT
            if x > 150 and JOYSTICK_RIGHT in possible_directions:
                return JOYSTICK_RIGHT
            if y < 100 and JOYSTICK_DOWN in possible_directions:
                return JOYSTICK_DOWN
            if y > 150 and JOYSTICK_UP in possible_directions:
                return JOYSTICK_UP
            return None

        def is_pressed(self):
            """Return whether the primary action is pressed (desktop).

            Delegates to the underlying `Nunchuck.buttons()` emulation.
            """
            _, z = self.nunchuck.buttons()
            return z


# Expose platform-appropriate names to the rest of the code.
if IS_MICROPYTHON:
    Nunchuck = NunchuckMicro
    Joystick = JoystickMicro
else:
    Nunchuck = NunchuckDesktop
    Joystick = JoystickDesktop


# ---------- Color helper ----------
def hsb_to_rgb(hue, saturation, brightness):
    """
    Convert HSB/HSV color to RGB tuple with each component in 0-255 range.

    Args:
        hue (float): Hue angle in degrees.
        saturation (float): Saturation (0.0-1.0).
        brightness (float): Brightness/value (0.0-1.0).

    Returns:
        tuple: (r, g, b) each in 0-255.
    """
    hue_normalized = (hue % 360) / 60
    i = int(hue_normalized)
    f = hue_normalized - i

    p = brightness * (1 - saturation)
    q = brightness * (1 - saturation * f)
    t = brightness * (1 - saturation * (1 - f))

    if i == 0:
        r, g, b = brightness, t, p
    elif i == 1:
        r, g, b = q, brightness, p
    elif i == 2:
        r, g, b = p, brightness, t
    elif i == 3:
        r, g, b = p, q, brightness
    elif i == 4:
        r, g, b = t, p, brightness
    else:
        r, g, b = brightness, p, q

    return int(r * 255), int(g * 255), int(b * 255)


def hypot(x, y):
    """Return the Euclidean distance sqrt(x*x + y*y)."""
    return math.sqrt(x * x + y * y)


# ---------- Highscores ----------
try:
    import ujson as json
except ImportError:
    import json


class HighScores:
    """
    Manage persistent high scores stored in a JSON file.

    Provides load/save and lookup helpers used by menus and games.
    """

    FILE = "highscores.json"

    def __init__(self):
        """Initialize high score storage and load existing scores from disk."""
        self.scores = {}
        self.load()

    def load(self):
        """Load high scores from the configured JSON file.

        On any error (missing file, parse error) the scores dictionary is
        reset to an empty mapping.
        """
        try:
            with open(self.FILE, "r") as f:
                self.scores = json.load(f)
        except Exception:
            self.scores = {}

    def save(self):
        """Persist the current high scores to disk as JSON.

        Errors during write are ignored to avoid crashing the running game.
        """
        try:
            with open(self.FILE, "w") as f:
                json.dump(self.scores, f)
        except Exception:
            pass

    def best(self, game):
        """Return the best score (integer) for the named game.

        Safely handles older score formats where the entry may be a plain
        integer or a dict with a `score` key.
        """
        try:
            v = self.scores.get(game, 0)
            if isinstance(v, dict):
                return int(v.get("score", 0) or 0)
            return int(v or 0)
        except Exception:
            return 0

    def best_name(self, game):
        """Return the 3-character name associated with the best score.

        If no name is present, returns the placeholder "---".
        """
        try:
            v = self.scores.get(game)
            if isinstance(v, dict):
                n = v.get("name")
                if isinstance(n, str) and n:
                    return n
        except Exception:
            pass
        return "---"

    def update(self, game, score, name=None):
        """Update the stored high score for `game` if `score` is higher.

        Optionally store a 3-character `name` alongside the score.
        Returns True when the stored value changed.
        """
        score = int(score or 0)
        if score > self.best(game):
            if isinstance(name, str) and name:
                self.scores[game] = {"score": score, "name": name[:3].upper()}
            else:
                self.scores[game] = score
            self.save()
            return True
        return False


class InitialsEntryMenu:
    """
    3-letter initials entry UI used when a new highscore is achieved.

    Navigates letters with the joystick and returns a 3-letter name.
    """

    def __init__(self, joystick, score, best, best_name="---", title="NEW HS"):
        """Create a 3-letter initials entry menu for a new high score.

        `joystick` is used to navigate letters; `score`, `best` and `best_name`
        are shown to the player. `title` is the top-line label.
        """
        self.joystick = joystick
        self.score = score
        self.best = best
        self.best_name = best_name
        self.title = title
        self.letters = ["A", "A", "A"]
        self.idx = 0

    def run(self):
        """Run the initials entry loop and return the entered 3-char name."""
        last_move = ticks_ms()
        move_delay = 140

        while True:
            display.clear()
            draw_text(2, 6, self.title, 0, 220, 0)

            # score line
            draw_rectangle(0, PLAY_HEIGHT, WIDTH - 1, HEIGHT - 1, 0, 0, 0)
            draw_text_small(1, PLAY_HEIGHT, str(self.score), 255, 255, 255)
            bn = self.best_name if isinstance(self.best_name, str) else "---"
            bs = "B" + str(self.best) + " " + bn
            draw_text_small(WIDTH - len(bs) * 6, 1, bs, 140, 140, 140)

            # letters
            y0 = 28
            for i in range(3):
                col = (255, 255, 255) if i == self.idx else (120, 120, 120)
                draw_text(10 + i * 18, y0, self.letters[i], *col)
                if i == self.idx:
                    draw_rectangle(
                        8 + i * 18, y0 + 13, 20 + i * 18, y0 + 14, 255, 255, 255
                    )

            draw_text_small(2, 50, "A=OK B=BACK", 120, 120, 120)

            now = ticks_ms()
            if ticks_diff(now, last_move) > move_delay:
                d = self.joystick.read_direction(
                    [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
                )
                if d == JOYSTICK_LEFT and self.idx > 0:
                    self.idx -= 1
                    last_move = now
                elif d == JOYSTICK_RIGHT and self.idx < 2:
                    self.idx += 1
                    last_move = now
                elif d == JOYSTICK_UP:
                    c = ord(self.letters[self.idx])
                    c = 65 if c >= 90 else (c + 1)
                    self.letters[self.idx] = chr(c)
                    last_move = now
                elif d == JOYSTICK_DOWN:
                    c = ord(self.letters[self.idx])
                    c = 90 if c <= 65 else (c - 1)
                    self.letters[self.idx] = chr(c)
                    last_move = now

            c_button, z_button = self.joystick.nunchuck.buttons()
            if c_button:
                # cancel
                while True:
                    cb, zb = self.joystick.nunchuck.buttons()
                    if not cb:
                        break
                    sleep_ms(10)
                return None

            if z_button:
                while True:
                    cb, zb = self.joystick.nunchuck.buttons()
                    if not zb:
                        break
                    sleep_ms(10)
                return "".join(self.letters)

            sleep_ms(20)


# ======================================================================
#                                 GAMES
# ======================================================================


class SimonGame:
    """
    Simple Simon memory game: repeat an increasing color sequence.

    Uses joystick input for color selection and highlights the sequence.
    """

    def __init__(self):
        """Initialize Simon game state (sequence and user input buffer)."""
        self.sequence = []
        self.user_input = []

    async def main_loop_async(self, joystick):
        """Cooperative async Simon main loop for browsers.

        Reimplements the turn-based logic without blocking sleeps so the
        event loop stays responsive in WASM environments.
        """
        global game_over, global_score
        game_over = False
        self.sequence = []
        self.user_input = []
        display.clear()
        self.draw_quad_screen()
        display_score_and_time(0, force=True)

        while True:
            c_button, _ = joystick.nunchuck.buttons()
            if c_button:
                return

            self.sequence.append(random.randint(0, 3))
            display_score_and_time(len(self.sequence) - 1)

            # play sequence asynchronously
            for c in self.sequence:
                x = c % 2
                y = c // 2
                hw = WIDTH // 2
                hh = PLAY_HEIGHT // 2
                x1 = x * hw
                y1 = y * hh
                x2 = (x + 1) * hw - 1
                y2 = (y + 1) * hh - 1
                if y2 >= PLAY_HEIGHT:
                    y2 = PLAY_HEIGHT - 1

                draw_rectangle(x1, y1, x2, y2, *colors[c])
                await asyncio.sleep(0.3)
                draw_rectangle(x1, y1, x2, y2, *inactive_colors[c])
                await asyncio.sleep(0.2)

            self.user_input = []

            for _ in range(len(self.sequence)):
                # poll for input without blocking
                sel = None
                while sel is None:
                    d = joystick.read_direction(
                        [
                            JOYSTICK_UP_LEFT,
                            JOYSTICK_UP_RIGHT,
                            JOYSTICK_DOWN_LEFT,
                            JOYSTICK_DOWN_RIGHT,
                        ]
                    )
                    if d:
                        sel = {
                            JOYSTICK_UP_LEFT: 0,
                            JOYSTICK_UP_RIGHT: 1,
                            JOYSTICK_DOWN_LEFT: 2,
                            JOYSTICK_DOWN_RIGHT: 3,
                        }.get(d, None)
                        break
                    await asyncio.sleep(0.03)

                if sel is None:
                    continue
                # flash selected
                x = sel % 2
                y = sel // 2
                hw = WIDTH // 2
                hh = PLAY_HEIGHT // 2
                x1 = x * hw
                y1 = y * hh
                x2 = (x + 1) * hw - 1
                y2 = (y + 1) * hh - 1
                if y2 >= PLAY_HEIGHT:
                    y2 = PLAY_HEIGHT - 1
                draw_rectangle(x1, y1, x2, y2, *colors[sel])
                await asyncio.sleep(0.12)
                draw_rectangle(x1, y1, x2, y2, *inactive_colors[sel])

                self.user_input.append(sel)
                if self.user_input != self.sequence[: len(self.user_input)]:
                    global_score = len(self.sequence) - 1
                    game_over = True
                    return

            await asyncio.sleep(0.3)
            maybe_collect(120)

    def draw_quad_screen(self):
        """Draw the four colored quadrants used by the Simon game."""
        hw = WIDTH // 2
        hh = PLAY_HEIGHT // 2
        draw_rectangle(0, 0, hw - 1, hh - 1, *inactive_colors[0])
        draw_rectangle(hw, 0, WIDTH - 1, hh - 1, *inactive_colors[1])
        draw_rectangle(0, hh, hw - 1, PLAY_HEIGHT - 1, *inactive_colors[2])
        draw_rectangle(hw, hh, WIDTH - 1, PLAY_HEIGHT - 1, *inactive_colors[3])

    def flash_color(self, idx, duration_ms=250):
        """Temporarily highlight the quadrant at index `idx` for `duration_ms`."""
        x = idx % 2
        y = idx // 2
        hw = WIDTH // 2
        hh = PLAY_HEIGHT // 2
        x1 = x * hw
        y1 = y * hh
        x2 = (x + 1) * hw - 1
        y2 = (y + 1) * hh - 1
        if y2 >= PLAY_HEIGHT:
            y2 = PLAY_HEIGHT - 1

        draw_rectangle(x1, y1, x2, y2, *colors[idx])
        sleep_ms(duration_ms)
        draw_rectangle(x1, y1, x2, y2, *inactive_colors[idx])

    def play_sequence(self):
        """Play back the stored color sequence with delays."""
        for c in self.sequence:
            self.flash_color(c, 300)
            sleep_ms(200)

    def get_user_input(self, joystick):
        """Read a single directional input from `joystick`, blocking briefly.

        Returns one of the diagonal direction constants.
        """
        while True:
            d = joystick.read_direction(
                [
                    JOYSTICK_UP_LEFT,
                    JOYSTICK_UP_RIGHT,
                    JOYSTICK_DOWN_LEFT,
                    JOYSTICK_DOWN_RIGHT,
                ]
            )
            if d:
                return d
            sleep_ms(30)

    def translate(self, direction):
        """Map a diagonal direction constant to a quadrant index (0-3)."""
        m = {
            JOYSTICK_UP_LEFT: 0,
            JOYSTICK_UP_RIGHT: 1,
            JOYSTICK_DOWN_LEFT: 2,
            JOYSTICK_DOWN_RIGHT: 3,
        }
        return m.get(direction, None)

    def main_loop(self, joystick):
        """Run the main game loop for Simon, returning when the game exits."""
        global game_over, global_score
        game_over = False
        self.sequence = []
        self.user_input = []
        display.clear()
        self.draw_quad_screen()
        display_score_and_time(0, force=True)

        while True:
            c_button, _ = joystick.nunchuck.buttons()
            if c_button:
                return

            self.sequence.append(random.randint(0, 3))
            display_score_and_time(len(self.sequence) - 1)
            self.play_sequence()
            self.user_input = []

            for _ in range(len(self.sequence)):
                direction = self.get_user_input(joystick)
                sel = self.translate(direction)
                if sel is None:
                    continue
                self.flash_color(sel, 120)
                self.user_input.append(sel)
                # check prefix
                if self.user_input != self.sequence[: len(self.user_input)]:
                    global_score = len(self.sequence) - 1
                    game_over = True
                    return

            sleep_ms(300)
            maybe_collect(120)


class SnakeGame:
    """
    Classic Snake implementation on the LED matrix playfield.

    Manages snake movement, food spawning, and collision detection.
    """

    def __init__(self):
        """Initialize snake game state and start a fresh round."""
        self.restart_game()

    async def main_loop_async(self, joystick):
        """Cooperative async Snake main loop for browsers."""
        global game_over
        game_over = False
        self.restart_game()

        while True:
            c_button, _ = joystick.nunchuck.buttons()
            if c_button:
                return
            if game_over:
                return

            self.step_counter += 1

            if self.step_counter % 1024 == 0:
                self.place_green_target()
            self.update_green_targets()

            direction = joystick.read_direction(
                [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
            )
            if direction:
                self.snake_direction = direction

            self.check_self_collision()
            if game_over:
                return

            self.update_snake_position()
            self.check_target_collision()
            self.check_green_target_collision()
            self.draw_snake()

            display_score_and_time(self.score)

            delay = 90 - max(10, self.snake_length // 3)
            if delay < 30:
                delay = 30
            await asyncio.sleep(delay / 1000)
            maybe_collect(120)

    def restart_game(self):
        """Reset snake position, length, direction, and spawn targets."""
        self.snake = [(WIDTH // 2, PLAY_HEIGHT // 2)]
        self.snake_length = 3
        self.snake_direction = JOYSTICK_UP
        self.score = 0
        self.green_targets = []
        self.target = None
        self.step_counter = 0
        self.step_counter2 = 0
        display.clear()
        self.place_target()
        display_score_and_time(0, force=True)

    def random_target(self):
        """Return a random valid target coordinate within the play area."""
        return (random.randint(1, WIDTH - 2), random.randint(1, PLAY_HEIGHT - 2))

    def place_target(self):
        """Place the primary (red) target on the display and record it."""
        self.target = self.random_target()
        display.set_pixel(self.target[0], self.target[1], 255, 0, 0)

    def place_green_target(self):
        """Spawn a temporary green target with a decay counter."""
        x, y = random.randint(1, WIDTH - 2), random.randint(1, PLAY_HEIGHT - 2)
        self.green_targets.append((x, y, 256))
        display.set_pixel(x, y, 0, 255, 0)

    def update_green_targets(self):
        """Decrease life counters for green targets and clear expired ones."""
        new_list = []
        for x, y, life in self.green_targets:
            if life > 1:
                new_list.append((x, y, life - 1))
            else:
                display.set_pixel(x, y, 0, 0, 0)
        self.green_targets = new_list

    def check_self_collision(self):
        """Detect collisions of the snake head with its body and end game."""
        global game_over, global_score
        hx, hy = self.snake[0]
        body = self.snake[1:]
        moves = {
            JOYSTICK_UP: (hx, hy - 1),
            JOYSTICK_DOWN: (hx, hy + 1),
            JOYSTICK_LEFT: (hx - 1, hy),
            JOYSTICK_RIGHT: (hx + 1, hy),
        }
        safe = {d: p for d, p in moves.items() if p not in body}
        if moves[self.snake_direction] not in safe.values():
            if safe:
                self.snake_direction = random.choice(list(safe.keys()))
            else:
                global_score = self.score
                game_over = True

    def update_snake_position(self):
        """Advance the snake head according to direction and handle wrapping.

        Also handles growth and collision detection with tail/body.
        """
        hx, hy = self.snake[0]
        if self.snake_direction == JOYSTICK_UP:
            hy -= 1
        elif self.snake_direction == JOYSTICK_DOWN:
            hy += 1
        elif self.snake_direction == JOYSTICK_LEFT:
            hx -= 1
        elif self.snake_direction == JOYSTICK_RIGHT:
            hx += 1

        hx %= WIDTH
        hy %= PLAY_HEIGHT

        # detect self-collision: if new head would hit body, lose
        new_head = (hx, hy)
        # tail position (may be freed this move)
        tail = self.snake[-1]
        # collision if new head is in current body, except when it's exactly the tail
        # and the snake is not growing (tail will be popped)
        occupying = new_head in self.snake
        tail_will_move = len(self.snake) == self.snake_length
        if occupying and not (tail_will_move and new_head == tail):
            global game_over, global_score
            global_score = self.score
            game_over = True
            return

        self.snake.insert(0, new_head)
        if len(self.snake) > self.snake_length:
            tx, ty = self.snake.pop()
            display.set_pixel(tx, ty, 0, 0, 0)

    def check_target_collision(self):
        """Handle collision with the primary target (red).

        Grow the snake, increment score, and place a new target.
        """
        hx, hy = self.snake[0]
        if (hx, hy) == self.target:
            self.snake_length += 2
            self.score += 1
            self.place_target()

    def check_green_target_collision(self):
        """Handle collision with green targets (halve length and remove)."""
        hx, hy = self.snake[0]
        for x, y, life in self.green_targets:
            if (hx, hy) == (x, y):
                self.snake_length = max(self.snake_length // 2, 2)
                self.green_targets.remove((x, y, life))
                display.set_pixel(x, y, 0, 0, 0)
                break

    def draw_snake(self):
        """Render the snake segments on the display.

        Head is drawn with a different color from the body.
        """
        hue = 0
        for x, y in self.snake[: self.snake_length]:
            hue = (hue + 7) % 360
            r, g, b = hsb_to_rgb(hue, 1, 1)
            display.set_pixel(x, y, r, g, b)

    def main_loop(self, joystick, mode="single"):
        """Run the Snake main loop until exit or restart.

        `mode` may change behavior for single/multi variations.
        """
        global game_over
        game_over = False
        self.restart_game()

        while True:
            c_button, _ = joystick.nunchuck.buttons()
            if c_button:
                return
            if game_over:
                return

            self.step_counter += 1

            # Spawn green targets
            if self.step_counter % 1024 == 0:
                self.place_green_target()
            self.update_green_targets()

            direction = joystick.read_direction(
                [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
            )
            if direction:
                self.snake_direction = direction

            self.check_self_collision()
            if game_over:
                return

            self.update_snake_position()
            self.check_target_collision()
            self.check_green_target_collision()
            self.draw_snake()

            display_score_and_time(self.score)

            delay = 90 - max(10, self.snake_length // 3)
            if delay < 30:
                delay = 30
            sleep_ms(delay)
            maybe_collect(120)


class PongGame:
    """
    Minimal Pong clone with two paddles and a bouncing ball.

    Supports single-player AI and basic scoring/hud display.
    """

    def __init__(self):
        """Initialize Pong game state: paddles, ball, scores and lives."""
        self.paddle_height = 10
        self.paddle_speed = 2
        self.left_paddle_y = PLAY_HEIGHT // 2 - self.paddle_height // 2
        self.right_paddle_y = PLAY_HEIGHT // 2 - self.paddle_height // 2
        self.ball_speed = [1, 1]
        self.ball_position = [WIDTH // 2, PLAY_HEIGHT // 2]
        self.left_score = 0
        self.lives = 3
        # track paddle vertical velocity for spin
        self.left_paddle_v = 0
        self.right_paddle_v = 0

    def reset_ball(self):
        """Center the ball and reset its velocity for a new rally."""
        self.ball_position = [WIDTH // 2, PLAY_HEIGHT // 2]
        self.ball_speed = [random.choice([-1, 1]), random.choice([-1, 1])]

    def draw_paddles(self):
        """Render both paddles into the left and right columns of playfield."""
        # Clear columns only in playfield
        for y in range(PLAY_HEIGHT):
            display.set_pixel(0, y, 0, 0, 0)
            display.set_pixel(WIDTH - 1, y, 0, 0, 0)

        for y in range(self.left_paddle_y, self.left_paddle_y + self.paddle_height):
            if 0 <= y < PLAY_HEIGHT:
                display.set_pixel(0, y, 255, 255, 255)

        for y in range(self.right_paddle_y, self.right_paddle_y + self.paddle_height):
            if 0 <= y < PLAY_HEIGHT:
                display.set_pixel(WIDTH - 1, y, 255, 255, 255)

    def clear_ball(self):
        """Clear the ball's previous pixel from the display."""
        x, y = self.ball_position
        if 0 <= y < PLAY_HEIGHT:
            display.set_pixel(x, y, 0, 0, 0)

    def draw_ball(self):
        """Draw the ball at its current integer position."""
        x, y = self.ball_position
        if 0 <= y < PLAY_HEIGHT:
            display.set_pixel(x, y, 255, 255, 255)

    def update_paddles(self, joystick):
        """Update left paddle from input and compute AI for right paddle."""
        d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN])
        # update left paddle and record velocity
        if d == JOYSTICK_UP:
            new_y = max(self.left_paddle_y - self.paddle_speed, 0)
            self.left_paddle_v = new_y - self.left_paddle_y
            self.left_paddle_y = new_y
        elif d == JOYSTICK_DOWN:
            new_y = min(
                self.left_paddle_y + self.paddle_speed, PLAY_HEIGHT - self.paddle_height
            )
            self.left_paddle_v = new_y - self.left_paddle_y
            self.left_paddle_y = new_y
        else:
            self.left_paddle_v = 0

        # simple AI right
        # simple AI right; track velocity
        by = self.ball_position[1]
        pc = self.right_paddle_y + self.paddle_height // 2
        if by < pc:
            new_y = max(self.right_paddle_y - self.paddle_speed, 0)
            self.right_paddle_v = new_y - self.right_paddle_y
            self.right_paddle_y = new_y
        elif by > pc:
            new_y = min(
                self.right_paddle_y + self.paddle_speed,
                PLAY_HEIGHT - self.paddle_height,
            )
            self.right_paddle_v = new_y - self.right_paddle_y
            self.right_paddle_y = new_y
        else:
            self.right_paddle_v = 0

    def update_ball(self):
        """Move the ball, handle wall and paddle collisions, and scoring."""
        global game_over, global_score
        self.clear_ball()

        self.ball_position[0] += self.ball_speed[0]
        self.ball_position[1] += self.ball_speed[1]

        x, y = self.ball_position

        if y <= 0 or y >= PLAY_HEIGHT - 1:
            self.ball_speed[1] = -self.ball_speed[1]

        # left paddle hit
        if x == 1 and self.left_paddle_y <= y < self.left_paddle_y + self.paddle_height:
            self.ball_speed[0] = -self.ball_speed[0]
            self.left_score += 1
            # apply spin based on paddle vertical movement
            try:
                self.ball_speed[1] += self.left_paddle_v
            except Exception:
                pass
            # clamp vertical speed
            if self.ball_speed[1] == 0:
                self.ball_speed[1] = 1
            self.ball_speed[1] = max(-2, min(2, self.ball_speed[1]))

        # right paddle hit
        if (
            x == WIDTH - 2
            and self.right_paddle_y <= y < self.right_paddle_y + self.paddle_height
        ):
            self.ball_speed[0] = -self.ball_speed[0]
            # apply spin from right paddle
            try:
                self.ball_speed[1] += self.right_paddle_v
            except Exception:
                pass
            if self.ball_speed[1] == 0:
                self.ball_speed[1] = 1
            self.ball_speed[1] = max(-2, min(2, self.ball_speed[1]))

        # miss left
        if x <= 0:
            self.lives -= 1
            self.left_score = 0
            if self.lives <= 0:
                global_score = 0
                game_over = True
                return
            self.reset_ball()

        # miss right -> bonus
        if x >= WIDTH - 1:
            self.left_score += 10
            self.reset_ball()

        global_score = self.left_score
        self.draw_ball()

    def main_loop(self, joystick):
        """Run the Pong game loop until the player exits or loses."""
        global game_over
        game_over = False
        display.clear()
        self.reset_ball()
        display_score_and_time(0, force=True)

        while True:
            c_button, _ = joystick.nunchuck.buttons()
            if c_button:
                return
            if game_over:
                return

            self.update_paddles(joystick)
            self.update_ball()
            self.draw_paddles()
            display_score_and_time(self.left_score)

            sleep_ms(45)
            maybe_collect(150)

    async def main_loop_async(self, joystick):
        """Async/cooperative Pong loop for browsers (pygbag)."""
        global game_over
        game_over = False
        display.clear()
        self.reset_ball()
        display_score_and_time(0, force=True)

        while True:
            c_button, _ = joystick.nunchuck.buttons()
            if c_button:
                return
            if game_over:
                return

            self.update_paddles(joystick)
            self.update_ball()
            self.draw_paddles()
            display_score_and_time(self.left_score)

            await asyncio.sleep(0.045)
            maybe_collect(150)


# ---------- Breakout ----------
PADDLE_WIDTH = const(12)
PADDLE_HEIGHT = const(2)
BALL_SIZE = const(2)
BRICK_WIDTH = const(7)
BRICK_HEIGHT = const(4)
BRICK_ROWS = const(5)
BRICK_COLS = const(8)


class BreakoutGame:
    """
    Breakout-style block-breaking game with a paddle and ball.

    Handles brick layout, ball physics, and level progression.
    """

    def __init__(self):
        """Set up breakout state: paddle, ball, bricks and scoring."""
        self.paddle_x = (WIDTH - PADDLE_WIDTH) // 2
        self.paddle_y = PLAY_HEIGHT - PADDLE_HEIGHT
        self.ball_x = WIDTH // 2
        self.ball_y = PLAY_HEIGHT // 2
        self.ball_dx = 1
        self.ball_dy = -1
        self.bricks = self.create_bricks()
        self.score = 0
        self.paddle_speed = 2
        # track horizontal paddle velocity for spin
        self.paddle_v = 0

    def create_bricks(self):
        """Build the initial brick layout as a list of (x,y,w,h,color)."""
        bricks = []
        for row in range(BRICK_ROWS):
            for col in range(BRICK_COLS):
                x = col * (BRICK_WIDTH + 1) + 1
                y = row * (BRICK_HEIGHT + 1)
                bricks.append((x, y))
        return bricks

    def draw_paddle(self):
        """Render the player's paddle as a filled rectangle."""
        draw_rectangle(
            self.paddle_x,
            self.paddle_y,
            self.paddle_x + PADDLE_WIDTH - 1,
            self.paddle_y + PADDLE_HEIGHT - 1,
            255,
            255,
            255,
        )

    def clear_paddle(self):
        """Erase the paddle area by drawing a black rectangle over it."""
        draw_rectangle(
            self.paddle_x,
            self.paddle_y,
            self.paddle_x + PADDLE_WIDTH - 1,
            self.paddle_y + PADDLE_HEIGHT - 1,
            0,
            0,
            0,
        )

    def draw_ball(self):
        """Draw the ball as a filled rectangle of size BALL_SIZE."""
        draw_rectangle(
            self.ball_x, self.ball_y, self.ball_x + 1, self.ball_y + 1, 255, 255, 255
        )

    def clear_ball(self):
        """Erase the ball's previous rectangle from the display."""
        draw_rectangle(
            self.ball_x, self.ball_y, self.ball_x + 1, self.ball_y + 1, 0, 0, 0
        )

    def draw_bricks(self):
        """Draw all bricks with a color based on their row position."""
        for x, y in self.bricks:
            hue = (y * 360) // max(1, (BRICK_ROWS * BRICK_HEIGHT))
            r, g, b = hsb_to_rgb(hue, 1, 1)
            draw_rectangle(x, y, x + BRICK_WIDTH - 1, y + BRICK_HEIGHT - 1, r, g, b)

    def update_ball(self):
        """Advance the ball, handle collisions with walls, bricks and paddle."""
        global game_over, global_score
        self.clear_ball()
        self.ball_x += self.ball_dx
        self.ball_y += self.ball_dy

        # wall bounce (ball is 2x2; top-left coords)
        if self.ball_x <= 0 or self.ball_x >= WIDTH - 2:
            self.ball_dx = -self.ball_dx
        if self.ball_y <= 0:
            self.ball_dy = -self.ball_dy

        # paddle bounce (apply spin based on paddle motion)
        if self.ball_y + 1 >= self.paddle_y:
            if self.paddle_x <= self.ball_x <= self.paddle_x + PADDLE_WIDTH - 1:
                self.ball_dy = -abs(self.ball_dy)
                # modify horizontal speed by paddle velocity
                try:
                    self.ball_dx += self.paddle_v
                except Exception:
                    pass
                # clamp horizontal speed and avoid zero
                if self.ball_dx == 0:
                    # prefer direction away from paddle center
                    self.ball_dx = 1 if self.paddle_v >= 0 else -1
                self.ball_dx = max(-2, min(2, self.ball_dx))

        # below paddle -> lost
        if self.ball_y >= PLAY_HEIGHT:
            global_score = self.score
            game_over = True
            return

        self.draw_ball()

    def check_collision_with_bricks(self):
        """Detect and handle collisions between the ball and any brick."""
        global global_score
        bx = self.ball_x
        by = self.ball_y
        for brick in self.bricks:
            x, y = brick
            if x <= bx < x + BRICK_WIDTH and y <= by < y + BRICK_HEIGHT:
                self.bricks.remove(brick)
                self.ball_dy = -self.ball_dy
                self.score += 10
                global_score = self.score
                # redraw playfield (cheap at this size)
                display.clear()
                self.draw_bricks()
                break

    def update_paddle(self, joystick):
        """Move the player's paddle according to left/right input."""
        d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT])
        if d == JOYSTICK_LEFT:
            self.clear_paddle()
            new_x = max(self.paddle_x - self.paddle_speed, 0)
            self.paddle_v = new_x - self.paddle_x
            self.paddle_x = new_x
        elif d == JOYSTICK_RIGHT:
            self.clear_paddle()
            new_x = min(self.paddle_x + self.paddle_speed, WIDTH - PADDLE_WIDTH)
            self.paddle_v = new_x - self.paddle_x
            self.paddle_x = new_x
        else:
            self.paddle_v = 0
        self.draw_paddle()

    def main_loop(self, joystick):
        """Run the Breakout game loop until exit or game over."""
        global game_over, global_score
        game_over = False
        self.score = 0
        display.clear()
        self.draw_bricks()
        self.draw_paddle()
        self.draw_ball()
        display_score_and_time(0, force=True)

        while True:
            c_button, _ = joystick.nunchuck.buttons()
            if c_button:
                return
            if game_over:
                return

            self.update_ball()
            if game_over:
                return
            self.check_collision_with_bricks()
            self.update_paddle(joystick)
            display_score_and_time(self.score)

            # win
            if not self.bricks:
                global_score = self.score
                display.clear()
                draw_text(10, 10, "YOU", 255, 255, 255)
                draw_text(10, 25, "WON", 255, 255, 255)
                sleep_ms(1500)
                return

            sleep_ms(35)
            maybe_collect(150)

    async def main_loop_async(self, joystick):
        """Async/cooperative Breakout loop for browsers (pygbag)."""
        global game_over, global_score
        game_over = False
        self.score = 0
        display.clear()
        self.draw_bricks()
        self.draw_paddle()
        self.draw_ball()
        display_score_and_time(0, force=True)

        while True:
            c_button, _ = joystick.nunchuck.buttons()
            if c_button:
                return
            if game_over:
                return

            self.update_ball()
            if game_over:
                return
            self.check_collision_with_bricks()
            self.update_paddle(joystick)
            display_score_and_time(self.score)

            # win
            if not self.bricks:
                global_score = self.score
                display.clear()
                draw_text(10, 10, "YOU", 255, 255, 255)
                draw_text(10, 25, "WON", 255, 255, 255)
                await asyncio.sleep(1.5)
                return

            await asyncio.sleep(0.035)
            maybe_collect(150)


# ---------- Asteroids ----------
SHIP_COOLDOWN = const(10)
FPS = const(20)
PIXEL_WIDTH = WIDTH
PIXEL_HEIGHT = PLAY_HEIGHT


class AsteroidGame:
    """
    Asteroids-like shooter with player ship, asteroids, and projectiles.

    Includes simple physics for movement and collision handling.
    """

    """Asteroids: pilot a ship, shoot asteroids and survive."""

    class Projectile:
        def __init__(self, x, y, angle, speed):
            """Create a projectile at (x,y) moving at `angle` with `speed`."""
            self.x = x
            self.y = y
            self.angle = angle
            self.speed = speed
            self.lifetime = 12

        def update(self):
            """Advance the projectile and decrement its lifetime."""
            self.x += math.cos(math.radians(self.angle)) * self.speed
            self.y -= math.sin(math.radians(self.angle)) * self.speed
            self.x %= PIXEL_WIDTH
            self.y %= PIXEL_HEIGHT
            self.lifetime -= 1

        def is_alive(self):
            """Return True while the projectile still has lifetime left."""
            return self.lifetime > 0

        def draw_line(self, start, end, color):
            """Draw a line between two points (used for simple beam rendering)."""
            x0, y0 = int(start[0]), int(start[1])
            x1, y1 = int(end[0]), int(end[1])
            dx = abs(x1 - x0)
            dy = abs(y1 - y0)
            x, y = x0, y0
            sx = -1 if x0 > x1 else 1
            sy = -1 if y0 > y1 else 1
            sp = display.set_pixel
            if dx > dy:
                err = dx / 2.0
                while x != x1:
                    sp(x % PIXEL_WIDTH, y % PIXEL_HEIGHT, *color)
                    err -= dy
                    if err < 0:
                        y += sy
                        err += dx
                    x += sx
            else:
                err = dy / 2.0
                while y != y1:
                    sp(x % PIXEL_WIDTH, y % PIXEL_HEIGHT, *color)
                    err -= dx
                    if err < 0:
                        x += sx
                        err += dy
                    y += sy
            sp(x % PIXEL_WIDTH, y % PIXEL_HEIGHT, *color)

        def draw(self):
            """Render the projectile as a short line segment in its direction."""
            ex = self.x + math.cos(math.radians(self.angle))
            ey = self.y - math.sin(math.radians(self.angle))
            self.draw_line((self.x, self.y), (ex, ey), (255, 0, 0))

    class Asteroid:
        def __init__(self, x=None, y=None, size=None, start=False):
            """Create an asteroid optionally at (x,y) with given `size`.

            When `start` is True, ensure it spawns outside the player area.
            """
            self.x = 32 if x is None else x
            self.y = 24 if y is None else y
            if start:
                while (22 < self.x < 42) and (16 < self.y < 40):
                    self.x = random.uniform(0, PIXEL_WIDTH)
                    self.y = random.uniform(0, PIXEL_HEIGHT)
            self.angle = random.uniform(0, 360)
            self.speed = random.uniform(0.6, 1.6)
            self.size = size if size is not None else random.randint(4, 8)

        def update(self):
            """Advance asteroid position and wrap around screen edges."""
            self.x += math.cos(math.radians(self.angle)) * self.speed
            self.y -= math.sin(math.radians(self.angle)) * self.speed
            self.x %= PIXEL_WIDTH
            self.y %= PIXEL_HEIGHT

        def draw(self):
            """Render the asteroid as a ring of pixels around its center."""
            sp = display.set_pixel
            for deg in range(0, 360, 12):
                rad = math.radians(deg)
                px = int((self.x + math.cos(rad) * self.size) % PIXEL_WIDTH)
                py = int((self.y + math.sin(rad) * self.size) % PIXEL_HEIGHT)
                sp(px, py, *WHITE)

    class Ship:
        def __init__(self):
            """Create the player's ship centered on the playfield."""
            self.x = PIXEL_WIDTH / 2
            self.y = PIXEL_HEIGHT / 2
            self.angle = 0
            self.speed = 0
            self.max_speed = 2.2
            self.size = 3
            self.cooldown = 0

        def draw_line(self, start, end, color):
            """Draw a line between two fractional coordinates."""
            x0, y0 = int(start[0]), int(start[1])
            x1, y1 = int(end[0]), int(end[1])
            dx = abs(x1 - x0)
            dy = abs(y1 - y0)
            x, y = x0, y0
            sx = -1 if x0 > x1 else 1
            sy = -1 if y0 > y1 else 1
            sp = display.set_pixel
            if dx > dy:
                err = dx / 2.0
                while x != x1:
                    sp(x % PIXEL_WIDTH, y % PIXEL_HEIGHT, *color)
                    err -= dy
                    if err < 0:
                        y += sy
                        err += dx
                    x += sx
            else:
                err = dy / 2.0
                while y != y1:
                    sp(x % PIXEL_WIDTH, y % PIXEL_HEIGHT, *color)
                    err -= dx
                    if err < 0:
                        x += sx
                        err += dy
                    y += sy
            sp(x % PIXEL_WIDTH, y % PIXEL_HEIGHT, *color)

        def update(self, direction):
            """Update ship angle, speed and position based on input.

            `direction` comes from joystick helper constants.
            """
            if direction == JOYSTICK_LEFT:
                self.angle = (self.angle + 6) % 360
            elif direction == JOYSTICK_RIGHT:
                self.angle = (self.angle - 6) % 360

            if direction == JOYSTICK_UP:
                self.speed = min(self.speed + 0.12, self.max_speed)
            else:
                self.speed = max(self.speed - 0.06, 0)

            self.x += math.cos(math.radians(self.angle)) * self.speed
            self.y -= math.sin(math.radians(self.angle)) * self.speed
            self.x %= PIXEL_WIDTH
            self.y %= PIXEL_HEIGHT

            if self.cooldown > 0:
                self.cooldown -= 1

        def draw(self):
            """Render the ship as a triangular sprite oriented by `angle`."""
            a = self.angle
            s = self.size
            p0 = (
                self.x + math.cos(math.radians(a)) * s,
                self.y - math.sin(math.radians(a)) * s,
            )
            p1 = (
                self.x + math.cos(math.radians(a + 120)) * s,
                self.y - math.sin(math.radians(a + 120)) * s,
            )
            p2 = (
                self.x + math.cos(math.radians(a - 120)) * s,
                self.y - math.sin(math.radians(a - 120)) * s,
            )

            if self.speed > 0:
                self.draw_line(p1, p2, RED)
            self.draw_line(p0, p1, WHITE)
            self.draw_line(p2, p0, WHITE)

        def shoot(self):
            """Fire a projectile if cooldown allows and return it, else None."""
            if self.cooldown == 0:
                self.cooldown = SHIP_COOLDOWN
                bullet_speed = 4
                bx = self.x + math.cos(math.radians(self.angle)) * self.size
                by = self.y - math.sin(math.radians(self.angle)) * self.size
                return AsteroidGame.Projectile(bx, by, self.angle, bullet_speed)
            return None

    def __init__(self):
        """Initialize AsteroidGame state with a player ship and asteroids."""
        self.ship = self.Ship()
        self.asteroids = [self.Asteroid(start=True) for _ in range(3)]
        self.projectiles = []
        self.score = 0

    def check_collisions(self):
        """Detect and resolve collisions between projectiles, asteroids, and ship."""
        global game_over, global_score
        # projectile vs asteroid
        for p in self.projectiles[:]:
            for a in self.asteroids[:]:
                d = hypot(p.x - a.x, p.y - a.y)
                if d < a.size:
                    if p in self.projectiles:
                        self.projectiles.remove(p)
                    if a in self.asteroids:
                        self.asteroids.remove(a)
                    self.score += 10
                    if a.size > 3:
                        for _ in range(2):
                            self.asteroids.append(
                                self.Asteroid(a.x, a.y, max(2, a.size // 2))
                            )
                    break

        # ship vs asteroid
        for a in self.asteroids:
            d = hypot(self.ship.x - a.x, self.ship.y - a.y)
            if d < a.size + self.ship.size:
                game_over = True
                global_score = self.score
                return

    def main_loop(self, joystick):
        """Run the Asteroid game loop handling input, updates and rendering."""
        global game_over, global_score
        game_over = False
        global_score = 0

        self.ship = self.Ship()
        self.asteroids = [self.Asteroid(start=True) for _ in range(3)]
        self.projectiles = []
        self.score = 0

        frame_ms = 1000 // FPS
        display.clear()
        display_score_and_time(0, force=True)

        while True:
            t0 = ticks_ms()

            c_button, z_button = joystick.nunchuck.buttons()
            if c_button:
                return
            if game_over:
                return

            direction = joystick.read_direction(
                [JOYSTICK_UP, JOYSTICK_LEFT, JOYSTICK_RIGHT]
            )
            self.ship.update(direction)

            if z_button:
                pr = self.ship.shoot()
                if pr:
                    self.projectiles.append(pr)

            for a in self.asteroids:
                a.update()

            for p in self.projectiles[:]:
                p.update()
                if not p.is_alive():
                    self.projectiles.remove(p)

            self.check_collisions()
            if game_over:
                return

            # new wave
            if not self.asteroids:
                self.asteroids = [self.Asteroid(start=False) for _ in range(4)]

            display.clear()
            self.ship.draw()
            for a in self.asteroids:
                a.draw()
            for p in self.projectiles:
                p.draw()

            display_score_and_time(self.score)
            global_score = self.score

            elapsed = ticks_diff(ticks_ms(), t0)
            if elapsed < frame_ms:
                sleep_ms(frame_ms - elapsed)

            maybe_collect(140)

    async def main_loop_async(self, joystick):
        """Asynchronous cooperative version of `main_loop` for pygbag.

        Yields to the event loop between frames so the browser stays responsive.
        """
        global game_over, global_score
        game_over = False
        global_score = 0

        self.ship = self.Ship()
        self.asteroids = [self.Asteroid(start=True) for _ in range(3)]
        self.projectiles = []
        self.score = 0

        frame_ms = 1000 // FPS
        display.clear()
        display_score_and_time(0, force=True)

        while True:
            t0 = ticks_ms()

            c_button, z_button = joystick.nunchuck.buttons()
            if c_button:
                return
            if game_over:
                return

            direction = joystick.read_direction(
                [JOYSTICK_UP, JOYSTICK_LEFT, JOYSTICK_RIGHT]
            )
            self.ship.update(direction)

            if z_button:
                pr = self.ship.shoot()
                if pr:
                    self.projectiles.append(pr)

            for a in self.asteroids:
                a.update()

            for p in self.projectiles[:]:
                p.update()
                if not p.is_alive():
                    self.projectiles.remove(p)

            self.check_collisions()
            if game_over:
                return

            # new wave
            if not self.asteroids:
                self.asteroids = [self.Asteroid(start=False) for _ in range(4)]

            display.clear()
            self.ship.draw()
            for a in self.asteroids:
                a.draw()
            for p in self.projectiles:
                p.draw()

            display_score_and_time(self.score)
            global_score = self.score

            elapsed = ticks_diff(ticks_ms(), t0)
            wait_ms = frame_ms - elapsed
            if wait_ms > 0:
                await asyncio.sleep(wait_ms / 1000)
            else:
                # yield control to event loop briefly
                await asyncio.sleep(0)

            maybe_collect(140)


# ---------- Qix ----------
class QixGame:
    """
    Qix-like territory-capturing game using a nibble-packed grid.

    Players draw lines to capture areas while avoiding enemies.
    """

    """Qix-like: draw lines to claim area while avoiding opponents."""

    def __init__(self):
        """Initialize QixGame grid, player and opponent state for a level."""
        self.height = PLAY_HEIGHT
        self.width = WIDTH
        self.player_x = 0
        self.player_y = 0
        # support multiple opponents for levels
        self.opponents = []  # list of dicts: {x,y,dx,dy}
        self.level = 1
        self.num_opponents = 1
        self.occupied_percentage = 0
        self.prev_player_pos = 1

    async def main_loop_async(self, joystick):
        """Cooperative async Qix main loop for browsers.

        Mirrors `main_loop` but yields to the event loop instead of
        using blocking `sleep_ms` so the browser remains responsive.
        """
        global game_over, global_score
        game_over = False
        global_score = 0
        self.initialize_game()

        while True:
            c_button, _ = joystick.nunchuck.buttons()
            if c_button:
                return
            if game_over:
                return

            self.move_player(joystick)
            self.move_opponent()
            if game_over:
                return

            if self.occupied_percentage > 75:
                # level cleared: advance to next level with an extra opponent
                global_score = int(self.level * 100) + int(self.occupied_percentage)
                display.clear()
                draw_text(6, 18, "LEVEL", 0, 255, 0)
                draw_text(6, 33, str(self.level), 0, 255, 0)
                await asyncio.sleep(0.9)
                # advance level
                self.level += 1
                self.num_opponents += 1
                if self.num_opponents > 8:
                    self.num_opponents = 8
                self.initialize_game()
                continue

            await asyncio.sleep(0.045)
            maybe_collect(180)

    def initialize_game(self):
        """Prepare a new game: reset display, grid and place entities."""
        display.clear()
        initialize_grid()
        self.draw_frame()
        self.place_player()
        self.place_opponents(self.num_opponents)
        self.occupied_percentage = 0
        display_score_and_time(0, force=True)

    def place_opponents(self, n):
        """Place `n` opponents at random interior coordinates and mark them."""
        # place n opponents at random interior positions
        self.opponents = []
        for _ in range(n):
            ox = random.randint(1, self.width - 2)
            oy = random.randint(1, self.height - 2)
            odx = random.choice([-1, 1])
            ody = random.choice([-1, 1])
            self.opponents.append({"x": ox, "y": oy, "dx": odx, "dy": ody})
            display.set_pixel(ox, oy, 255, 0, 0)

    def draw_frame(self):
        """Draw the solid frame/border on the grid and display."""
        for x in range(self.width):
            set_grid_value(x, 0, 1)
            set_grid_value(x, self.height - 1, 1)
            display.set_pixel(x, 0, 0, 0, 255)
            display.set_pixel(x, self.height - 1, 0, 0, 255)

        for y in range(self.height):
            set_grid_value(0, y, 1)
            set_grid_value(self.width - 1, y, 1)
            display.set_pixel(0, y, 0, 0, 255)
            display.set_pixel(self.width - 1, y, 0, 0, 255)

    def place_player(self):
        """Randomly choose a border cell and place the player there."""
        edges = (
            [(x, 0) for x in range(self.width)]
            + [(x, self.height - 1) for x in range(self.width)]
            + [(0, y) for y in range(self.height)]
            + [(self.width - 1, y) for y in range(self.height)]
        )
        self.player_x, self.player_y = random.choice(edges)
        display.set_pixel(self.player_x, self.player_y, 0, 255, 0)

    def place_opponent(self):
        """Place a single opponent at a random interior location."""
        self.opponent_x = random.randint(1, self.width - 2)
        self.opponent_y = random.randint(1, self.height - 2)
        display.set_pixel(self.opponent_x, self.opponent_y, 255, 0, 0)

    def move_opponent(self):
        """Advance all opponents, bouncing off frame and ending the game on capture."""
        global game_over, global_score
        # move each opponent independently
        for op in self.opponents:
            ox = op["x"]
            oy = op["y"]
            dx = op["dx"]
            dy = op["dy"]

            nx = ox + dx
            ny = oy + dy

            # check collisions separately on x and y to allow bouncing
            v_x = get_grid_value(nx, oy)
            if v_x == 4:
                global_score = int(self.level * 100) + int(self.occupied_percentage)
                game_over = True
                return
            if v_x in (1, 2):
                dx = -dx

            v_y = get_grid_value(ox, ny)
            if v_y == 4:
                global_score = int(self.level * 100) + int(self.occupied_percentage)
                game_over = True
                return
            if v_y in (1, 2):
                dy = -dy

            # recompute target after possible bounce
            nx = ox + dx
            ny = oy + dy
            if get_grid_value(nx, ny) == 4 or (
                nx == self.player_x and ny == self.player_y
            ):
                global_score = int(self.level * 100) + int(self.occupied_percentage)
                game_over = True
                return

            # move opponent pixel
            display.set_pixel(ox, oy, 0, 0, 0)
            op["x"] = nx
            op["y"] = ny
            op["dx"] = dx
            op["dy"] = dy
            display.set_pixel(nx, ny, 255, 0, 0)

    def move_player(self, joystick):
        """Move the player according to joystick input and leave a trail."""
        d = joystick.read_direction(
            [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
        )
        if not d:
            return

        nx, ny = self.player_x, self.player_y
        if d == JOYSTICK_UP:
            ny -= 1
        elif d == JOYSTICK_DOWN:
            ny += 1
        elif d == JOYSTICK_LEFT:
            nx -= 1
        elif d == JOYSTICK_RIGHT:
            nx += 1

        if nx < 0 or nx >= self.width or ny < 0 or ny >= self.height:
            return

        v = get_grid_value(nx, ny)
        if v == 0:
            set_grid_value(nx, ny, 4)  # trail
            display.set_pixel(nx, ny, 0, 255, 0)
            self.prev_player_pos = 0
        elif v == 1:
            if self.prev_player_pos == 0:
                self.close_area(nx, ny)
            self.prev_player_pos = 1

        self.player_x, self.player_y = nx, ny
        display.set_pixel(self.player_x, self.player_y, 0, 255, 0)

    def close_area(self, x, y):
        """Convert the player's trail into a solid border and fill enclosed area."""
        # convert trail to border/filled
        set_grid_value(x, y, 1)
        display.set_pixel(x, y, 0, 0, 255)

        # pick an opponent position for flood fill (use first opponent if present)
        if self.opponents:
            ox = self.opponents[0]["x"]
            oy = self.opponents[0]["y"]
        else:
            ox = self.width // 2
            oy = self.height // 2
        flood_fill(ox, oy, accessible_mark=3)

        for i in range(self.width):
            for j in range(self.height):
                gv = get_grid_value(i, j)
                if gv == 0:
                    set_grid_value(i, j, 2)  # filled
                    display.set_pixel(i, j, 0, 0, 255)
                elif gv == 3:
                    set_grid_value(i, j, 0)  # reset accessible marks
                elif gv in (1, 4):
                    set_grid_value(i, j, 1)
                    display.set_pixel(i, j, 0, 55, 100)

        self.calculate_occupied_percentage()

    def calculate_occupied_percentage(self):
        """Recalculate and store the percentage of the grid occupied by filled area."""
        occ = count_cells_with_mark(2, self.width, self.height)
        self.occupied_percentage = (occ / (self.width * self.height)) * 100
        display_score_and_time(int(self.occupied_percentage))

    def main_loop(self, joystick):
        """Run the Qix game loop handling input, opponent movement and scoring."""
        global game_over, global_score
        game_over = False
        global_score = 0
        self.initialize_game()

        while True:
            c_button, _ = joystick.nunchuck.buttons()
            if c_button:
                return
            if game_over:
                return

            self.move_player(joystick)
            self.move_opponent()
            if game_over:
                return

            if self.occupied_percentage > 75:
                # level cleared: advance to next level with an extra opponent
                global_score = int(self.level * 100) + int(self.occupied_percentage)
                display.clear()
                draw_text(6, 18, "LEVEL", 0, 255, 0)
                draw_text(6, 33, str(self.level), 0, 255, 0)
                sleep_ms(900)
                # advance level
                self.level += 1
                self.num_opponents += 1
                # cap number of opponents to a reasonable amount
                if self.num_opponents > 8:
                    self.num_opponents = 8
                # reinit the game for next level
                self.initialize_game()
                continue

            sleep_ms(45)
            maybe_collect(180)


# ---------- Tetris ----------
class TetrisGame:
    """
    Tetris implementation with falling pieces and line clearing.

    Includes piece rotation, gravity, and scoring rules.
    """

    """Tetris: falling blocks puzzle with line clears and scoring."""

    GRID_WIDTH = const(16)
    GRID_HEIGHT = const(13)
    BLOCK_SIZE = const(4)

    COLORS = [
        (0, 255, 255),
        (255, 0, 0),
        (0, 255, 0),
        (0, 0, 255),
        (255, 255, 0),
        (255, 165, 0),
        (128, 0, 128),
    ]

    TETRIMINOS = [
        [[1, 1, 1, 1]],  # I
        [[1, 1, 1], [0, 1, 0]],  # T
        [[1, 1, 0], [0, 1, 1]],  # S
        [[0, 1, 1], [1, 1, 0]],  # Z
        [[1, 1], [1, 1]],  # O
        [[1, 1, 1], [1, 0, 0]],  # L
        [[1, 1, 1], [0, 0, 1]],  # J
    ]

    class Piece:
        def __init__(self):
            """Create a random tetromino piece at the top center of the grid."""
            self.shape = random.choice(TetrisGame.TETRIMINOS)
            self.color = random.choice(TetrisGame.COLORS)
            self.x = TetrisGame.GRID_WIDTH // 2 - len(self.shape[0]) // 2
            self.y = 0

        def rotate(self):
            """Rotate the current piece clockwise by transposing and reversing."""
            self.shape = [list(row) for row in zip(*self.shape[::-1])]

    def __init__(self):
        """Initialize Tetris board state, current piece and timing counters."""
        self.locked = {}  # (x,y)->color
        self.current = TetrisGame.Piece()
        self.score = 0
        self.last_fall = ticks_ms()
        self.last_input = ticks_ms()
        self.fall_ms = 520
        self.input_ms = 120

    async def main_loop_async(self, joystick):
        """Cooperative async version of the Tetris main loop for browsers.

        Yields to the event loop between frames to keep the UI responsive.
        """
        global game_over, global_score
        game_over = False
        global_score = 0
        display_score_and_time(0, force=True)

        while True:
            c_button, z_button = joystick.nunchuck.buttons()
            if c_button:
                return

            now = ticks_ms()

            # input handling (debounced)
            if ticks_diff(now, self.last_input) >= self.input_ms:
                d = joystick.read_direction(
                    [JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_DOWN, JOYSTICK_UP]
                )
                if d == JOYSTICK_LEFT and self.valid(self.current, dx=-1):
                    self.current.x -= 1
                elif d == JOYSTICK_RIGHT and self.valid(self.current, dx=1):
                    self.current.x += 1
                elif d == JOYSTICK_DOWN and self.valid(self.current, dy=1):
                    self.current.y += 1
                elif d == JOYSTICK_UP or z_button:
                    rot = [list(row) for row in zip(*self.current.shape[::-1])]
                    if self.valid(self.current, rotated_shape=rot):
                        self.current.shape = rot
                self.last_input = now

            # gravity / fall
            if ticks_diff(now, self.last_fall) >= self.fall_ms:
                self.last_fall = now
                if self.valid(self.current, dy=1):
                    self.current.y += 1
                else:
                    ok = self.lock_piece(self.current)
                    if not ok:
                        global_score = self.score
                        game_over = True
                        return

                    cleared = self.clear_rows()
                    if cleared:
                        self.score += cleared * 10
                        self.fall_ms = max(160, self.fall_ms - cleared * 15)
                    else:
                        self.score += 1

                    self.current = TetrisGame.Piece()
                    if not self.valid(self.current, dy=0):
                        global_score = self.score
                        game_over = True
                        return

            self.render()
            display_score_and_time(self.score)

            # cooperative frame delay
            await asyncio.sleep(0.035)
            maybe_collect(140)

    def valid(self, piece, dx=0, dy=0, rotated_shape=None):
        """Return True if `piece` at offset (dx,dy) would fit on the board."""
        shape = rotated_shape if rotated_shape is not None else piece.shape
        for y, row in enumerate(shape):
            for x, cell in enumerate(row):
                if not cell:
                    continue
                nx = piece.x + x + dx
                ny = piece.y + y + dy
                if nx < 0 or nx >= self.GRID_WIDTH:
                    return False
                if ny >= self.GRID_HEIGHT:
                    return False
                if ny >= 0 and (nx, ny) in self.locked:
                    return False
        return True

    def lock_piece(self, piece):
        """Lock `piece` into the board's locked block map; return False on overflow."""
        for y, row in enumerate(piece.shape):
            for x, cell in enumerate(row):
                if cell:
                    px = piece.x + x
                    py = piece.y + y
                    if py < 0:
                        return False
                    self.locked[(px, py)] = piece.color
        return True

    def clear_rows(self):
        """Remove any full rows, collapse above rows down, and return count."""
        full_rows = []
        for y in range(self.GRID_HEIGHT):
            ok = True
            for x in range(self.GRID_WIDTH):
                if (x, y) not in self.locked:
                    ok = False
                    break
            if ok:
                full_rows.append(y)

        if not full_rows:
            return 0

        for y in full_rows:
            for x in range(self.GRID_WIDTH):
                if (x, y) in self.locked:
                    del self.locked[(x, y)]

        full_rows.sort()
        new_locked = {}
        for (x, y), col in self.locked.items():
            shift = 0
            for ry in full_rows:
                if y < ry:
                    shift += 1
            new_locked[(x, y + shift)] = col
        self.locked = new_locked
        return len(full_rows)

    def draw_block(self, gx, gy, color):
        """Draw a single Tetris block at grid coordinates (gx,gy)."""
        x1 = gx * self.BLOCK_SIZE
        y1 = gy * self.BLOCK_SIZE
        draw_rectangle(
            x1, y1, x1 + self.BLOCK_SIZE - 1, y1 + self.BLOCK_SIZE - 1, *color
        )

    def render(self):
        """Render the entire Tetris board including locked blocks and current piece."""
        display.clear()
        # locked
        for (x, y), col in self.locked.items():
            self.draw_block(x, y, col)
        # current
        for y, row in enumerate(self.current.shape):
            for x, cell in enumerate(row):
                if cell:
                    px = self.current.x + x
                    py = self.current.y + y
                    if py >= 0:
                        self.draw_block(px, py, self.current.color)

    def main_loop(self, joystick):
        """Run the Tetris main loop processing input, gravity and rendering."""
        global game_over, global_score
        game_over = False
        global_score = 0
        display_score_and_time(0, force=True)

        while True:
            c_button, z_button = joystick.nunchuck.buttons()
            if c_button:
                return

            now = ticks_ms()

            # input
            if ticks_diff(now, self.last_input) >= self.input_ms:
                d = joystick.read_direction(
                    [JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_DOWN, JOYSTICK_UP]
                )
                if d == JOYSTICK_LEFT and self.valid(self.current, dx=-1):
                    self.current.x -= 1
                elif d == JOYSTICK_RIGHT and self.valid(self.current, dx=1):
                    self.current.x += 1
                elif d == JOYSTICK_DOWN and self.valid(self.current, dy=1):
                    self.current.y += 1
                elif d == JOYSTICK_UP or z_button:
                    # rotate
                    rot = [list(row) for row in zip(*self.current.shape[::-1])]
                    if self.valid(self.current, rotated_shape=rot):
                        self.current.shape = rot
                self.last_input = now

            # fall
            if ticks_diff(now, self.last_fall) >= self.fall_ms:
                self.last_fall = now
                if self.valid(self.current, dy=1):
                    self.current.y += 1
                else:
                    # lock
                    ok = self.lock_piece(self.current)
                    if not ok:
                        global_score = self.score
                        game_over = True
                        return

                    cleared = self.clear_rows()
                    if cleared:
                        self.score += cleared * 10
                        self.fall_ms = max(160, self.fall_ms - cleared * 15)
                    else:
                        self.score += 1

                    self.current = TetrisGame.Piece()
                    if not self.valid(self.current, dy=0):
                        global_score = self.score
                        game_over = True
                        return

            self.render()
            display_score_and_time(self.score)

            sleep_ms(35)
            maybe_collect(140)


# ---------- Maze ----------
class MazeGame:
    """
    Top-down maze game using a packed grid representation.

    Supports flood-fill, pathing, and maze-rendering helpers.
    """

    """Maze explorer: find gems, avoid enemies, with fog-of-war."""

    WALL = 0
    PATH = 1
    PLAYER = 2
    GEM = 3
    ENEMY = 4
    PROJECTILE = 5

    MazeWaySize = 3
    BORDER = 2

    def __init__(self):
        """Initialize maze state: player, enemies, gems and exploration set."""
        self.projectiles = []
        self.gems = []
        self.enemies = []
        self.score = 0

    async def main_loop_async(self, joystick):
        """Cooperative async Maze main loop for browsers."""
        global game_over, global_score
        game_over = False
        self.projectiles = []
        self.gems = []
        self.enemies = []
        self.score = 0
        self.player_direction = JOYSTICK_UP
        self.explored = set()

        # initialize and run the synchronous generate/setup parts
        display.clear()
        self.generate_maze()
        display_score_and_time(0, force=True)

        while True:
            c_button, _ = joystick.nunchuck.buttons()
            if c_button:
                return
            if game_over:
                return

            # movement input
            d = joystick.read_direction(
                [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
            )
            if d:
                self.player_direction = d

            # update world (projectiles, enemies, etc.) if methods exist
            try:
                for p in list(self.projectiles):
                    p.update()
                    if not p.is_alive():
                        self.projectiles.remove(p)
            except Exception:
                pass

            # TODO: add enemy movement and gem logic mirroring sync loop
            # keep timing reasonable for browser
            await asyncio.sleep(0.05)
            maybe_collect(120)

    def generate_maze(self):
        """Generate a randomized maze using DFS-backed carving."""
        stack = []
        visited = set()

        start_x = random.randint(self.BORDER, WIDTH - self.BORDER - 1)
        start_y = random.randint(self.BORDER, PLAY_HEIGHT - self.BORDER - 1)

        stack.append((start_x, start_y))
        visited.add((start_x, start_y))
        set_grid_value(start_x, start_y, self.PATH)

        dirs = [
            (0, self.MazeWaySize),
            (0, -self.MazeWaySize),
            (self.MazeWaySize, 0),
            (-self.MazeWaySize, 0),
        ]

        while stack:
            x, y = stack[-1]
            mixed = dirs[:]
            for i in range(len(mixed) - 1, 0, -1):
                j = random.randint(0, i)
                mixed[i], mixed[j] = mixed[j], mixed[i]

            found = False
            for dx, dy in mixed:
                nx, ny = x + dx, y + dy
                if (
                    self.BORDER <= nx < WIDTH - self.BORDER
                    and self.BORDER <= ny < PLAY_HEIGHT - self.BORDER
                    and (nx, ny) not in visited
                ):
                    # carve
                    step_x = dx // self.MazeWaySize
                    step_y = dy // self.MazeWaySize
                    for k in range(self.MazeWaySize):
                        cx = x + step_x * k
                        cy = y + step_y * k
                        set_grid_value(cx, cy, self.PATH)
                    set_grid_value(nx, ny, self.PATH)
                    stack.append((nx, ny))
                    visited.add((nx, ny))
                    found = True
                    break

            if not found:
                stack.pop()

    def place_player(self):
        """Choose a random walkable cell and place the player, mark explored."""
        while True:
            self.player_x = random.randint(self.BORDER, WIDTH - self.BORDER - 1)
            self.player_y = random.randint(self.BORDER, PLAY_HEIGHT - self.BORDER - 1)
            if get_grid_value(self.player_x, self.player_y) == self.PATH:
                set_grid_value(self.player_x, self.player_y, self.PLAYER)
                # mark initial player cell as explored
                self.explored.add((self.player_x, self.player_y))
                break

    def place_gems(self, n=10):
        """Scatter `n` gems on random path cells."""
        self.gems = []
        for _ in range(n):
            while True:
                gx = random.randint(self.BORDER, WIDTH - self.BORDER - 1)
                gy = random.randint(self.BORDER, PLAY_HEIGHT - self.BORDER - 1)
                if get_grid_value(gx, gy) == self.PATH:
                    set_grid_value(gx, gy, self.GEM)
                    self.gems.append((gx, gy))
                    break

    def place_enemies(self, n=3):
        """Place `n` enemies randomly on path cells."""
        self.enemies = []
        for _ in range(n):
            while True:
                ex = random.randint(self.BORDER, WIDTH - self.BORDER - 1)
                ey = random.randint(self.BORDER, PLAY_HEIGHT - self.BORDER - 1)
                if get_grid_value(ex, ey) == self.PATH:
                    set_grid_value(ex, ey, self.ENEMY)
                    self.enemies.append((ex, ey))
                    break

    def get_visible_cells(self):
        """Return the set of cells visible from the player's position (line-of-sight)."""
        vis = set()
        x, y = self.player_x, self.player_y
        vis.add((x, y))
        dirs = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        for dx, dy in dirs:
            nx, ny = x, y
            while True:
                nx += dx
                ny += dy
                if 0 <= nx < WIDTH and 0 <= ny < PLAY_HEIGHT:
                    v = get_grid_value(nx, ny)
                    if v == self.WALL:
                        break
                    vis.add((nx, ny))
                    if v == self.ENEMY:
                        break
                else:
                    break
        return vis

    def render(self):
        """Render the maze with fog-of-war: explored dim, visible highlighted."""
        display.clear()
        vis = self.get_visible_cells()

        # add newly seen path cells to explored set
        for x, y in vis:
            v = get_grid_value(x, y)
            if v == self.PATH or v == self.PLAYER:
                self.explored.add((x, y))

        # draw explored paths (dim)
        for x, y in self.explored:
            display.set_pixel(x, y, 40, 40, 40)

        # draw currently visible cells brighter / overlay
        for x, y in vis:
            v = get_grid_value(x, y)
            if v == self.PATH:
                display.set_pixel(x, y, 80, 80, 80)
            elif v == self.PLAYER:
                display.set_pixel(x, y, 0, 255, 0)
            elif v == self.GEM:
                display.set_pixel(x, y, 255, 215, 0)
            elif v == self.ENEMY:
                display.set_pixel(x, y, 255, 0, 0)
            elif v == self.PROJECTILE:
                display.set_pixel(x, y, 255, 255, 0)

    def move_player(self, joystick):
        """Move the player and collect gems / trigger interactions."""
        d = joystick.read_direction(
            [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
        )
        if not d:
            return

        nx, ny = self.player_x, self.player_y
        if d == JOYSTICK_UP:
            ny -= 1
        elif d == JOYSTICK_DOWN:
            ny += 1
        elif d == JOYSTICK_LEFT:
            nx -= 1
        elif d == JOYSTICK_RIGHT:
            nx += 1

        if not (0 <= nx < WIDTH and 0 <= ny < PLAY_HEIGHT):
            return

        v = get_grid_value(nx, ny)
        if v in (self.PATH, self.GEM):
            set_grid_value(self.player_x, self.player_y, self.PATH)
            self.player_x, self.player_y = nx, ny
            set_grid_value(self.player_x, self.player_y, self.PLAYER)
            self.player_direction = d
            if v == self.GEM:
                # collect
                if (nx, ny) in self.gems:
                    self.gems.remove((nx, ny))
                self.score += 10

    def move_enemies(self):
        """Advance each enemy randomly along available path tiles."""
        new_enemies = []
        for ex, ey in self.enemies:
            moves = []
            for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                nx, ny = ex + dx, ey + dy
                if (
                    0 <= nx < WIDTH
                    and 0 <= ny < PLAY_HEIGHT
                    and get_grid_value(nx, ny) == self.PATH
                ):
                    moves.append((nx, ny))
            set_grid_value(ex, ey, self.PATH)
            if moves:
                ex, ey = random.choice(moves)
            set_grid_value(ex, ey, self.ENEMY)
            new_enemies.append((ex, ey))
        self.enemies = new_enemies

    def handle_shooting(self, joystick):
        """Handle firing a projectile from the player when the button is pressed."""
        _, z_button = joystick.nunchuck.buttons()
        if not z_button:
            return

        dx, dy = 0, -1
        if self.player_direction == JOYSTICK_UP:
            dx, dy = 0, -1
        elif self.player_direction == JOYSTICK_DOWN:
            dx, dy = 0, 1
        elif self.player_direction == JOYSTICK_LEFT:
            dx, dy = -1, 0
        elif self.player_direction == JOYSTICK_RIGHT:
            dx, dy = 1, 0

        sx = self.player_x + dx
        sy = self.player_y + dy
        if not (0 <= sx < WIDTH and 0 <= sy < PLAY_HEIGHT):
            return

        v = get_grid_value(sx, sy)
        if v == self.WALL:
            return

        proj = {"x": sx, "y": sy, "dx": dx, "dy": dy, "lifetime": 12, "prev": v}
        set_grid_value(sx, sy, self.PROJECTILE)
        self.projectiles.append(proj)

    def update_projectiles(self):
        """Advance projectiles, handle collisions and remove expired ones."""
        for p in self.projectiles[:]:
            # restore previous cell
            set_grid_value(p["x"], p["y"], p["prev"])

            p["x"] += p["dx"]
            p["y"] += p["dy"]
            p["lifetime"] -= 1

            if p["lifetime"] <= 0 or not (
                0 <= p["x"] < WIDTH and 0 <= p["y"] < PLAY_HEIGHT
            ):
                self.projectiles.remove(p)
                continue

            v = get_grid_value(p["x"], p["y"])
            if v == self.WALL:
                self.projectiles.remove(p)
                continue
            if v == self.ENEMY:
                # remove enemy
                if (p["x"], p["y"]) in self.enemies:
                    self.enemies.remove((p["x"], p["y"]))
                set_grid_value(p["x"], p["y"], self.PATH)
                self.projectiles.remove(p)
                self.score += 20
                continue

            p["prev"] = v
            set_grid_value(p["x"], p["y"], self.PROJECTILE)

    def main_loop(self, joystick):
        """Run the Maze game main loop handling input, updates and rendering."""
        global game_over, global_score
        game_over = False
        global_score = 0

        initialize_grid()
        self.explored = set()
        self.score = 0
        self.projectiles = []
        self.generate_maze()
        self.place_player()
        self.place_gems(10)
        self.place_enemies(3)

        display_score_and_time(0, force=True)

        while True:
            c_button, _ = joystick.nunchuck.buttons()
            if c_button:
                return

            # lose if enemy on player
            if (self.player_x, self.player_y) in self.enemies:
                global_score = self.score
                game_over = True
                return

            self.move_player(joystick)
            self.handle_shooting(joystick)
            self.update_projectiles()
            self.move_enemies()

            self.render()
            display_score_and_time(self.score)

            if not self.enemies and not self.gems:
                global_score = self.score
                display.clear()
                draw_text(6, 18, "YOU", 0, 255, 0)
                draw_text(6, 33, "WON", 0, 255, 0)
                sleep_ms(1500)
                return

            sleep_ms(90)
            maybe_collect(140)


# ---------- FLAPPY ----------
class FlappyGame:
    """
    Flappy Bird-like one-button game where the player avoids obstacles.

    Handles gravity, pipe spawning, and score tracking.
    """

    """Flappy: navigate between pipes; flap to gain altitude."""

    def __init__(self):
        """Initialize FlappyGame and prepare first pipes and state."""
        self.reset()

    def reset(self):
        """Reset player position, velocity, pipes and score for a new run."""
        self.bx = 12
        self.by = PLAY_HEIGHT // 2
        self.vy = 0
        self.score = 0

        self.pipe_w = 7
        self.gap_h = 18
        self.speed = 1

        self.pipes = []
        # initial pipes
        for i in range(3):
            self.add_pipe(WIDTH + i * 24)

    def add_pipe(self, x):
        """Insert a vertical pipe with a gap centered at `gy` located at x."""
        min_y = self.gap_h // 2 + 2
        max_y = PLAY_HEIGHT - self.gap_h // 2 - 3
        gy = random.randint(min_y, max_y)
        self.pipes.append({"x": x, "gy": gy, "passed": False})

    def flap(self):
        """Give the bird an upward impulse (triggered by button press)."""
        # compatibility for Z button: give an upward velocity impulse
        self.vy = -4

    def collide(self):
        """Return True if the player collides with pipes or boundaries."""
        # out of bounds
        if self.by < 0 or self.by > PLAY_HEIGHT - 2:
            return True

        # pipes
        for p in self.pipes:
            px = p["x"]
            if px <= self.bx <= px + self.pipe_w - 1:
                top_end = p["gy"] - self.gap_h // 2
                bot_start = p["gy"] + self.gap_h // 2
                if self.by < top_end or self.by > bot_start:
                    return True
        return False

    def draw(self):
        """Render game frame: pipes, player and score."""
        display.clear()

        # draw pipes
        for p in self.pipes:
            x = p["x"]
            gy = p["gy"]
            top_end = gy - self.gap_h // 2
            bot_start = gy + self.gap_h // 2

            # top
            if top_end > 0:
                draw_rectangle(x, 0, x + self.pipe_w - 1, top_end, 0, 200, 0)
            # bottom
            if bot_start < PLAY_HEIGHT - 1:
                draw_rectangle(
                    x, bot_start, x + self.pipe_w - 1, PLAY_HEIGHT - 1, 0, 200, 0
                )

        # bird (2x2)
        y = int(self.by)
        draw_rectangle(self.bx, y, self.bx + 1, y + 1, 255, 255, 0)

    def main_loop(self, joystick):
        """Run the Flappy game loop managing input, physics and spawning."""
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        display_score_and_time(0, force=True)

        last_frame = ticks_ms()
        frame_ms = 35

        while True:
            c_button, z_button = joystick.nunchuck.buttons()
            if c_button:
                return

            now = ticks_ms()
            if ticks_diff(now, last_frame) < frame_ms:
                sleep_ms(5)
                continue
            last_frame = now

            # physics: flap impulse + gravity
            d = joystick.read_direction([JOYSTICK_UP])
            if z_button or d == JOYSTICK_UP:
                self.flap()

            # gravity
            self.vy += 1
            if self.vy > 5:
                self.vy = 5
            self.by += self.vy

            # clamp vertical
            if self.by < 0:
                self.by = 0
                self.vy = 0
            if self.by > PLAY_HEIGHT - 2:
                self.by = PLAY_HEIGHT - 2
                self.vy = 0

            # move pipes
            for p in self.pipes:
                p["x"] -= self.speed

                # scoring
                if (not p["passed"]) and (p["x"] + self.pipe_w) < self.bx:
                    p["passed"] = True
                    self.score += 1

            # recycle pipes
            if self.pipes and self.pipes[0]["x"] + self.pipe_w < 0:
                self.pipes.pop(0)
                self.add_pipe(WIDTH + 10)

            if self.collide():
                global_score = self.score
                game_over = True
                return

            self.draw()
            display_score_and_time(self.score)

            maybe_collect(140)

    async def main_loop_async(self, joystick):
        """Async/cooperative Flappy loop for browsers (pygbag)."""
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        display_score_and_time(0, force=True)

        last_frame = ticks_ms()
        frame_ms = 35

        while True:
            c_button, z_button = joystick.nunchuck.buttons()
            if c_button:
                return

            now = ticks_ms()
            if ticks_diff(now, last_frame) < frame_ms:
                await asyncio.sleep(0.005)
                continue
            last_frame = now

            # physics: flap impulse + gravity
            d = joystick.read_direction([JOYSTICK_UP])
            if z_button or d == JOYSTICK_UP:
                self.flap()

            # gravity
            self.vy += 1
            if self.vy > 5:
                self.vy = 5
            self.by += self.vy

            # clamp vertical
            if self.by < 0:
                self.by = 0
                self.vy = 0
            if self.by > PLAY_HEIGHT - 2:
                self.by = PLAY_HEIGHT - 2
                self.vy = 0

            # move pipes
            for p in self.pipes:
                p["x"] -= self.speed

                # scoring
                if (not p["passed"]) and (p["x"] + self.pipe_w) < self.bx:
                    p["passed"] = True
                    self.score += 1

            # recycle pipes
            if self.pipes and self.pipes[0]["x"] + self.pipe_w < 0:
                self.pipes.pop(0)
                self.add_pipe(WIDTH + 10)

            if self.collide():
                global_score = self.score
                game_over = True
                return

            self.draw()
            display_score_and_time(self.score)

            maybe_collect(140)


class RTypeGame:
    """
    Side-scrolling shooter inspired by R-Type with enemies and pickups.

    Manages player ship, enemy waves, and scrolling background.
    """

    """
    R-TYPE / Gradius-style mini endless side-scroller (shoot 'em up).

    Controls:
      - Stick: move (Up/Down/Left/Right)
      - Z: fire
      - C: back to menu / cancel
    """

    # Small sine lookup table (±4) used for simple "wobble" enemy motion
    # without calling `math.sin` to reduce CPU and avoid floating-point cost
    # on constrained MicroPython targets.
    _SIN = (0, 1, 2, 3, 4, 3, 2, 1, 0, -1, -2, -3, -4, -3, -2, -1)

    def __init__(self):
        """Initialize RTypeGame and prepare initial game state."""
        self.reset()

    async def main_loop_async(self, joystick):
        """Cooperative async R-Type main loop for browsers."""
        global game_over, global_score
        game_over = False
        self.reset()

        while True:
            c_button, z_button = joystick.nunchuck.buttons()
            if c_button:
                return

            # input
            d = joystick.read_direction(
                [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
            )
            if d == JOYSTICK_UP:
                self.py = max(self.py - 1, 0)
            elif d == JOYSTICK_DOWN:
                self.py = min(self.py + 1, PLAY_HEIGHT - self.ph)
            elif d == JOYSTICK_LEFT:
                self.px = max(self.px - 1, 0)
            elif d == JOYSTICK_RIGHT:
                self.px = min(self.px + 1, WIDTH - self.pw)

            # fire
            if z_button:
                if self.fire_cd <= 0:
                    self.bullets.append([self.px + self.pw + 1, self.py])
                    self.fire_cd = 10

            # update
            self._difficulty_update()
            if (
                ticks_diff(ticks_ms(), self.last_spawn) >= self.spawn_ms
                and len(self.enemies) < 8
            ):
                self.last_spawn = ticks_ms()
                self._spawn_enemy()

            self._update_stars()
            self._update_powerups()
            self._update_bullets()
            self._bullet_hits()
            self._update_enemies()

            global_score = self.score
            self._draw()

            await asyncio.sleep(0.035)
            maybe_collect(140)

    def reset(self):
        """Reset game state: player, bullets, enemies and timers."""
        self.score = 0

        # Player
        self.pw = 5
        self.ph = 3
        self.px = 6
        self.py = PLAY_HEIGHT // 2

        # Projectiles
        self.bullets = []  # [x,y]
        self.ebullets = []  # [x,y]
        self.fire_cd = 0
        self.power_t = 0  # frames power-up active

        # Enemies: [x, y, typ, hp, phase, cd, basey]
        self.enemies = []
        self.spawn_ms = 520
        self.last_spawn = ticks_ms()

        # Powerups: [x,y,ttl]
        self.powerups = []

        # tracking start time for time-based difficulty
        self.start_ms = ticks_ms()
        # Stars background
        self.stars = []
        for _ in range(18):
            self.stars.append(
                [
                    random.randint(0, WIDTH - 1),
                    random.randint(0, PLAY_HEIGHT - 1),
                    random.randint(1, 3),
                ]
            )

        self.frame = 0
        self.last_logic = ticks_ms()
        self.logic_ms = 35  # ~28fps

    def _rect_play(self, x, y, w, h, r, g, b):
        """Draw a rectangle clipped to the playfield using shared helper."""
        # reuse shared helper to draw playfield rectangles
        draw_play_rect(x, y, w, h, r, g, b)

    def _overlap(self, ax1, ay1, ax2, ay2, bx1, by1, bx2, by2):
        """Return True if two axis-aligned rectangles overlap."""
        if ax2 < bx1 or bx2 < ax1:
            return False
        if ay2 < by1 or by2 < ay1:
            return False
        return True

    def _spawn_enemy(self):
        """Spawn a randomized enemy with type-specific properties."""
        # typ 0: drone, typ 1: wobble, typ 2: shooter
        r = random.randint(0, 99)
        if r < 55:
            typ = 0
        elif r < 85:
            typ = 1
        else:
            typ = 2

        y = random.randint(2, PLAY_HEIGHT - 10)
        x = WIDTH + random.randint(0, 12)

        if typ == 0:
            hp = 1
        elif typ == 1:
            hp = 1
        else:
            hp = 2

        phase = random.randint(0, 15)
        cd = random.randint(10, 40)  # shooter cooldown
        self.enemies.append([x, y, typ, hp, phase, cd, y])

    def _difficulty_update(self):
        """Adjust spawn timing based on current score to increase difficulty."""
        # schnelleres Spawning mit Score
        # score steigt typischerweise in 10ern, das passt gut
        s = self.score // 10
        self.spawn_ms = 520 - s * 12
        if self.spawn_ms < 170:
            self.spawn_ms = 170

    def _update_stars(self):
        """Scroll the background starfield and respawn off-screen stars."""
        for st in self.stars:
            st[0] -= st[2]
            if st[0] < 0:
                st[0] = WIDTH - 1
                st[1] = random.randint(0, PLAY_HEIGHT - 1)
                st[2] = random.randint(1, 3)

    def _update_powerups(self):
        """Advance powerups leftwards and remove expired ones."""
        # move left, expire
        for p in self.powerups[:]:
            p[0] -= 1
            p[2] -= 1
            if p[0] < -2 or p[2] <= 0:
                self.powerups.remove(p)
                continue

            # collect
            if (
                abs(p[0] - (self.px + self.pw // 2)) <= 2
                and abs(p[1] - (self.py + 1)) <= 2
            ):
                self.powerups.remove(p)
                self.power_t = 240  # ~8 Sekunden
                # kleines Bonus
                self.score += 5

    def _update_bullets(self):
        """Advance player and enemy bullets, removing those off-screen."""
        # player bullets
        for b in self.bullets[:]:
            b[0] += 4
            if b[0] >= WIDTH:
                self.bullets.remove(b)

        # enemy bullets
        for b in self.ebullets[:]:
            b[0] -= 3
            if b[0] < 0:
                self.ebullets.remove(b)

    def _update_enemies(self):
        """Update enemy positions, behaviors and handle firing."""
        global game_over, global_score

        for e in self.enemies[:]:
            typ = e[2]

            # movement
            if typ == 0:
                e[0] -= 2
            elif typ == 1:
                e[0] -= 1
                e[4] = (e[4] + 1) & 15
                e[1] = e[6] + self._SIN[e[4]]
                if e[1] < 1:
                    e[1] = 1
                if e[1] > PLAY_HEIGHT - 6:
                    e[1] = PLAY_HEIGHT - 6
            else:
                e[0] -= 1
                e[5] -= 1
                if e[5] <= 0 and len(self.ebullets) < 3:
                    # shoot
                    self.ebullets.append([e[0], e[1] + 1])
                    e[5] = random.randint(18, 40)

            # offscreen
            if e[0] < -10:
                self.enemies.remove(e)
                continue

            # collision with player (rects)
            ex1 = e[0]
            ey1 = e[1]
            ew = 4 if typ != 2 else 5
            eh = 3 if typ != 2 else 4
            ex2 = ex1 + ew - 1
            ey2 = ey1 + eh - 1

            px1 = self.px
            py1 = self.py
            px2 = px1 + self.pw - 1
            py2 = py1 + self.ph - 1

            if self._overlap(ex1, ey1, ex2, ey2, px1, py1, px2, py2):
                global_score = self.score
                game_over = True
                return

        # enemy bullets vs player
        px1 = self.px
        py1 = self.py
        px2 = px1 + self.pw - 1
        py2 = py1 + self.ph - 1
        for b in self.ebullets[:]:
            if px1 <= b[0] <= px2 and py1 <= b[1] <= py2:
                global_score = self.score
                game_over = True
                return

    def _bullet_hits(self):
        """Process bullet collisions with enemies and apply damage/score."""
        # bullets vs enemies
        for b in self.bullets[:]:
            bx, by = b[0], b[1]
            hit = None
            for e in self.enemies:
                typ = e[2]
                ex1 = e[0]
                ey1 = e[1]
                ew = 4 if typ != 2 else 5
                eh = 3 if typ != 2 else 4
                ex2 = ex1 + ew - 1
                ey2 = ey1 + eh - 1
                if ex1 <= bx <= ex2 and ey1 <= by <= ey2:
                    hit = e
                    break

            if hit is not None:
                if b in self.bullets:
                    self.bullets.remove(b)
                hit[3] -= 1
                if hit[3] <= 0:
                    if hit in self.enemies:
                        self.enemies.remove(hit)
                    # score
                    typ = hit[2]
                    self.score += 10 + typ * 7
                    # chance for powerup
                    if random.randint(0, 99) < 12:
                        self.powerups.append([hit[0], hit[1], 400])
                else:
                    self.score += 1  # hit bonus

    def _draw(self):
        """Render the R-Type playfield: stars, powerups, player, bullets and enemies."""
        display.clear()
        sp = display.set_pixel

        # stars
        for x, y, _s in self.stars:
            if 0 <= x < WIDTH and 0 <= y < PLAY_HEIGHT:
                sp(x, y, 60, 60, 60)

        # powerups
        for p in self.powerups:
            x = int(p[0])
            y = int(p[1])
            if 0 <= x < WIDTH and 0 <= y < PLAY_HEIGHT:
                sp(x, y, 0, 255, 0)
                if x + 1 < WIDTH:
                    sp(x + 1, y, 0, 255, 0)

        # player
        self._rect_play(self.px, self.py, self.pw, self.ph, 0, 180, 255)
        # nose
        nx = self.px + self.pw
        ny = self.py + 1
        if 0 <= nx < WIDTH and 0 <= ny < PLAY_HEIGHT:
            sp(nx, ny, 0, 180, 255)

        # bullets
        for b in self.bullets:
            x, y = b
            if 0 <= x < WIDTH and 0 <= y < PLAY_HEIGHT:
                sp(x, y, 255, 255, 255)
        for b in self.ebullets:
            x, y = b
            if 0 <= x < WIDTH and 0 <= y < PLAY_HEIGHT:
                sp(x, y, 255, 60, 60)

        # enemies
        for e in self.enemies:
            x = int(e[0])
            y = int(e[1])
            typ = e[2]
            if typ == 0:
                self._rect_play(x, y, 4, 3, 255, 60, 60)
            elif typ == 1:
                self._rect_play(x, y, 4, 3, 255, 0, 255)
            else:
                self._rect_play(x, y, 5, 4, 255, 140, 0)
                # "gun"
                gx = x
                gy = y + 2
                if 0 <= gx < WIDTH and 0 <= gy < PLAY_HEIGHT:
                    sp(gx, gy, 0, 0, 0)

        # HUD
        display_score_and_time(self.score)

    def main_loop(self, joystick):
        """Run the R-Type game loop: logic tick, input handling and rendering."""
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        display_score_and_time(0, force=True)

        while True:
            c_button, z_button = joystick.nunchuck.buttons()
            if c_button:
                return
            if game_over:
                return

            now = ticks_ms()
            if ticks_diff(now, self.last_logic) < self.logic_ms:
                sleep_ms(2)
                continue
            self.last_logic = now
            self.frame += 1

            # power timer
            if self.power_t > 0:
                self.power_t -= 1

            # input
            d = joystick.read_direction(
                [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
            )
            step = 2
            if d == JOYSTICK_UP:
                self.py -= step
            elif d == JOYSTICK_DOWN:
                self.py += step
            elif d == JOYSTICK_LEFT:
                self.px -= step
            elif d == JOYSTICK_RIGHT:
                self.px += step

            # bounds
            if self.px < 0:
                self.px = 0
            if self.px > WIDTH - self.pw - 1:
                self.px = WIDTH - self.pw - 1
            if self.py < 0:
                self.py = 0
            if self.py > PLAY_HEIGHT - self.ph:
                self.py = PLAY_HEIGHT - self.ph

            # shoot
            if self.fire_cd > 0:
                self.fire_cd -= 1
            cd_min = 4 if self.power_t > 0 else 7
            if z_button and self.fire_cd == 0:
                # normal bullet
                self.bullets.append([self.px + self.pw + 1, self.py + 1])
                # powered double-shot
                if self.power_t > 0 and len(self.bullets) < 6:
                    self.bullets.append([self.px + self.pw + 1, self.py])
                self.fire_cd = cd_min

            # spawn
            self._difficulty_update()
            if (
                ticks_diff(now, self.last_spawn) >= self.spawn_ms
                and len(self.enemies) < 8
            ):
                self.last_spawn = now
                self._spawn_enemy()

            # update world
            self._update_stars()
            self._update_powerups()
            self._update_bullets()
            self._bullet_hits()
            self._update_enemies()

            global_score = self.score
            self._draw()

            if self.frame % 80 == 0:
                gc.collect()


class PacmanGame:
    """
    Simplified Pac-Man clone with pellets, ghosts, and maze navigation.

    Implements ghost AI states and pellet/fruit scoring.
    """

    """
    PACMAN-lite (Maze + Pellets + 2 Ghosts)
    Steuerung:
      - Stick: Richtung
      - C: zurück ins Menü
    """

    # W = 16
    # H = 14
    CELL = 4
    OFF_X = 0
    OFF_Y = 1

    # 16 Zeichen pro Zeile, 14 Zeilen
    MAP = [
        "################",
        "#P...#....#G...#",
        "#.##.#.##.#.##.#",
        "#o#..#....#..#o#",
        "#....###.##....#",
        "#.##........##.#",
        "#....#.##.#....#",
        "#....#.##.#....#",
        "#.##........##.#",
        "#....##.###....#",
        "#o#..#....#..#o#",
        "#.##.#..#.#.##.#",
        "#...G#....#....#",
        "################",
    ]

    # Derived map dimensions
    Width = len(MAP[0])
    Height = len(MAP)

    # dirs: 0 U, 1 D, 2 L, 3 R
    DIRS = ((0, -1), (0, 1), (-1, 0), (1, 0))
    OPP = (1, 0, 3, 2)

    def __init__(self):
        """Initialize Pacman game and prepare map, pellets, and ghosts."""
        self.reset()

    async def main_loop_async(self, joystick):
        """Cooperative async Pac-Man main loop for browsers.

        Mirrors `main_loop` but yields to the event loop instead of
        using blocking `sleep_ms` calls so the UI stays responsive.
        """
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        display_score_and_time(0, force=True)

        # initial full draw
        self._draw_background()
        self._draw()

        while True:
            c_button, _z = joystick.nunchuck.buttons()
            if c_button:
                return
            if game_over:
                return

            now = ticks_ms()

            # read input often
            d = joystick.read_direction(
                [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
            )
            if d == JOYSTICK_UP:
                self.want_dir = 0
            elif d == JOYSTICK_DOWN:
                self.want_dir = 1
            elif d == JOYSTICK_LEFT:
                self.want_dir = 2
            elif d == JOYSTICK_RIGHT:
                self.want_dir = 3

            if ticks_diff(now, self.last_logic) >= self.logic_ms:
                self.last_logic = now
                self.frame += 1

                old_px, old_py = self.px, self.py
                old_ghosts = [(g[0], g[1]) for g in self.ghosts]
                old_power = self.power_timer

                if self.power_timer > 0:
                    self.power_timer -= 1

                self._move_player()
                self._eat()
                self._move_ghosts()

                if self._check_collisions():
                    global_score = self.score
                    return

                # win?
                if self.pellet_count <= 0:
                    global_score = self.score
                    display.clear()
                    draw_text(6, 18, "YOU", 0, 255, 0)
                    draw_text(6, 33, "WON", 0, 255, 0)
                    display_score_and_time(global_score)
                    await asyncio.sleep(1.3)
                    return

                global_score = self.score

                # incremental redraw: old/new sprite cells (and current cell if pellet changed)
                dirty = set()
                dirty.add((old_px, old_py))
                dirty.add((self.px, self.py))
                for p in old_ghosts:
                    dirty.add(p)
                for g in self.ghosts:
                    dirty.add((g[0], g[1]))
                # if frightened state toggles, redraw ghosts too (same cells)
                if (old_power > 0) != (self.power_timer > 0):
                    for g in self.ghosts:
                        dirty.add((g[0], g[1]))

                self._draw_dirty_cells(dirty)

                if self.frame % 90 == 0:
                    gc.collect()

            else:
                # yield briefly instead of blocking sleep
                await asyncio.sleep(0.006)

            if self._dirty:
                self._draw()
            else:
                await asyncio.sleep(0.008)

            # give other tasks a chance
            await asyncio.sleep(0)

    def reset(self):
        """Reset board arrays, player position and ghost state for a run."""
        self.wall = bytearray(self.Width * self.Height)  # 1 if wall
        self.pel = bytearray(self.Width * self.Height)  # 0 none, 1 pellet, 2 power
        self.wall_list = []

        self.px = 1
        self.py = 1
        self.pdir = 3  # right
        self.want_dir = 3

        self.ghosts = []  # each: [x,y,dir,home_x,home_y]
        self.power_timer = 0  # ticks (logic steps)

        self.score = 0
        self.pellet_count = 0

        # parse map
        for y in range(self.Height):
            row = self.MAP[y]
            for x in range(self.Width):
                ch = row[x]
                i = y * self.Width + x
                if ch == "#":
                    self.wall[i] = 1
                    self.wall_list.append((x, y))
                else:
                    self.wall[i] = 0
                    if ch == ".":
                        self.pel[i] = 1
                        self.pellet_count += 1
                    elif ch == "o":
                        self.pel[i] = 2
                        self.pellet_count += 1
                    else:
                        self.pel[i] = 0

                    if ch == "P":
                        self.px, self.py = x, y
                    elif ch == "G":
                        # ghost start
                        self.ghosts.append([x, y, random.randint(0, 3), x, y])

        if len(self.ghosts) < 2:
            # safety
            self.ghosts.append([self.Width - 2, 1, 2, self.Width - 2, 1])

        self.last_logic = ticks_ms()
        self.logic_ms = 120
        self.ghost_tick = 0
        self._input_cd = 0
        self.frame = 0
        self._dirty = True
        self._drawn_bg = False
        self.prev_px = self.px
        self.prev_py = self.py
        self.prev_ghosts = [(g[0], g[1]) for g in self.ghosts]

    def _idx(self, x, y):
        """Return the linear buffer index for coordinates (x,y)."""
        return y * self.Width + x

    def _can_move(self, x, y):
        """Return True if the cell (x,y) is walkable (not a wall)."""
        if x < 0 or x >= self.Width or y < 0 or y >= self.Height:
            return False
        return self.wall[self._idx(x, y)] == 0

    def _eat(self):
        """Consume a pellet/power at the player's position and update score."""
        i = self._idx(self.px, self.py)
        v = self.pel[i]
        if v:
            self.pel[i] = 0
            self.pellet_count -= 1
            if v == 1:
                self.score += 1
            else:
                self.score += 10
                self.power_timer = 70  # ~8.4s bei logic_ms=120
            self._dirty = True

    def _move_player(self):
        """Move the player one step following `want_dir` or current direction."""
        # attempt desired direction first
        dx, dy = self.DIRS[self.want_dir]
        nx = self.px + dx
        ny = self.py + dy
        if self._can_move(nx, ny):
            self.pdir = self.want_dir
        else:
            # try current dir
            dx, dy = self.DIRS[self.pdir]
            nx = self.px + dx
            ny = self.py + dy
            if not self._can_move(nx, ny):
                return  # stuck

        self.px = nx
        self.py = ny
        self._dirty = True

    def _ghost_moves(self, g):
        """Return a list of possible movement directions for ghost `g`."""
        # returns list of possible dirs
        x, y, d, hx, hy = g
        moves = []
        for nd in (0, 1, 2, 3):
            dx, dy = self.DIRS[nd]
            nx = x + dx
            ny = y + dy
            if self._can_move(nx, ny):
                moves.append(nd)
        if len(moves) > 1 and self.OPP[d] in moves:
            moves.remove(self.OPP[d])
        return moves

    def _ghost_pick(self, g):
        """Pick the next movement direction for ghost `g` using heuristics."""
        x, y, d, hx, hy = g
        moves = self._ghost_moves(g)
        if not moves:
            return d
        if len(moves) == 1:
            return moves[0]

        # 25% randomness
        if random.randint(0, 99) < 25:
            return random.choice(moves)

        # greedy distance
        best = moves[0]
        bestv = None

        frightened = self.power_timer > 0
        for nd in moves:
            dx, dy = self.DIRS[nd]
            nx = x + dx
            ny = y + dy
            dist = abs(nx - self.px) + abs(ny - self.py)

            if frightened:
                # maximize distance
                if bestv is None or dist > bestv:
                    bestv = dist
                    best = nd
            else:
                # minimize distance
                if bestv is None or dist < bestv:
                    bestv = dist
                    best = nd
        return best

    def _move_ghosts(self):
        """Advance ghosts on their scheduled ticks using chosen directions."""
        # ghost speed: every 2nd logic tick
        self.ghost_tick = (self.ghost_tick + 1) & 1
        if self.ghost_tick == 1:
            return

        for g in self.ghosts:
            nd = self._ghost_pick(g)
            g[2] = nd
            dx, dy = self.DIRS[nd]
            g[0] += dx
            g[1] += dy
            self._dirty = True

    def _check_collisions(self):
        """Check for collisions between player and ghosts and handle outcomes."""
        global game_over, global_score
        for g in self.ghosts:
            if g[0] == self.px and g[1] == self.py:
                if self.power_timer > 0:
                    # eat ghost
                    self.score += 50
                    g[0], g[1] = g[3], g[4]
                    g[2] = random.randint(0, 3)
                    self._dirty = True
                else:
                    global_score = self.score
                    game_over = True
                    return True
        return False

    def _draw_cell(self, cx, cy, r, g, b):
        """Draw a mapped cell at grid coords (`cx`,`cy`) with color (r,g,b)."""
        x1 = self.OFF_X + cx * self.CELL
        y1 = self.OFF_Y + cy * self.CELL
        draw_rectangle(x1, y1, x1 + self.CELL - 1, y1 + self.CELL - 1, r, g, b)

    def _draw_bg_cell(self, x, y):
        """Draw background cell at (x,y): wall, floor and possible pellet."""
        i = self._idx(x, y)
        if self.wall[i]:
            self._draw_cell(x, y, 0, 0, 140)
            return

        # empty floor
        self._draw_cell(x, y, 0, 0, 0)

        # pellet on top of floor
        v = self.pel[i]
        if v:
            cx = self.OFF_X + x * self.CELL + 1
            cy = self.OFF_Y + y * self.CELL + 1
            if v == 1:
                display.set_pixel(cx, cy, 255, 255, 255)
            else:
                draw_rectangle(cx, cy, cx + 1, cy + 1, 255, 215, 0)

    def _draw_player(self):
        """Draw the player sprite at its current grid position.

        Calculates pixel coordinates from the player's grid position
        and draws a 2x2 rectangle representing Pac-Man.
        """
        px = self.OFF_X + self.px * self.CELL
        py = self.OFF_Y + self.py * self.CELL
        draw_rectangle(px, py, px + 2, py + 2, 255, 255, 0)

    def _draw_ghosts(self):
        """Draw all ghosts, using different colors and frightened state.

        When the player has an active power-up, ghosts are drawn in
        a frightened blue color; otherwise ghosts have distinct colors.
        """
        frightened = self.power_timer > 0
        for gi, g in enumerate(self.ghosts):
            gx = self.OFF_X + g[0] * self.CELL
            gy = self.OFF_Y + g[1] * self.CELL
            if frightened:
                col = (80, 80, 255)
            else:
                col = (255, 60, 60) if gi == 0 else (255, 0, 255)
            draw_rectangle(gx, gy, gx + 2, gy + 2, *col)

    def _draw_background(self):
        """Clear and draw the static background: walls and pellets.

        This draws the maze walls and the remaining pellets. Sets
        `_drawn_bg` to True after the background has been rendered.
        """
        display.clear()
        # walls
        for x, y in self.wall_list:
            self._draw_cell(x, y, 0, 0, 140)

        # pellets
        for y in range(self.Height):
            for x in range(self.Width):
                v = self.pel[self._idx(x, y)]
                if v:
                    cx = self.OFF_X + x * self.CELL + 1
                    cy = self.OFF_Y + y * self.CELL + 1
                    if v == 1:
                        display.set_pixel(cx, cy, 255, 255, 255)
                    else:
                        draw_rectangle(cx, cy, cx + 1, cy + 1, 255, 215, 0)
        self._drawn_bg = True

    def _draw(self):
        """Render the full game frame (background, player, ghosts).

        This method draws the background if needed and then the
        dynamic entities (player and ghosts) for the current frame.
        """
        if not self._drawn_bg:
            self._draw_background()
        self._draw_player()
        self._draw_ghosts()

        display_score_and_time(self.score)
        self._dirty = False

    def _draw_dirty_cells(self, dirty):
        """Draw only cells marked as dirty and restore their background.

        Restores the background for every coordinate in `dirty`, then
        redraws dynamic sprites and the score/time HUD on top.
        """
        if not self._drawn_bg:
            self._draw_background()

        # restore background for dirty cells first
        for x, y in dirty:
            if 0 <= x < self.Width and 0 <= y < self.Height:
                self._draw_bg_cell(x, y)

        # redraw sprites on top
        self._draw_player()
        self._draw_ghosts()
        display_score_and_time(self.score)

    def main_loop(self, joystick):
        """Main game loop: process input, update state, and render frames.

        The loop runs until `game_over` becomes True. `joystick` is the
        input provider used to read player controls each iteration.
        """
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        display_score_and_time(0, force=True)

        # initial full draw
        self._draw_background()
        self._draw()

        while True:
            c_button, _z = joystick.nunchuck.buttons()
            if c_button:
                return
            if game_over:
                return

            now = ticks_ms()

            # read input often
            d = joystick.read_direction(
                [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
            )
            if d == JOYSTICK_UP:
                self.want_dir = 0
            elif d == JOYSTICK_DOWN:
                self.want_dir = 1
            elif d == JOYSTICK_LEFT:
                self.want_dir = 2
            elif d == JOYSTICK_RIGHT:
                self.want_dir = 3

            if ticks_diff(now, self.last_logic) >= self.logic_ms:
                self.last_logic = now
                self.frame += 1

                old_px, old_py = self.px, self.py
                old_ghosts = [(g[0], g[1]) for g in self.ghosts]
                old_power = self.power_timer

                if self.power_timer > 0:
                    self.power_timer -= 1

                self._move_player()
                self._eat()
                self._move_ghosts()

                if self._check_collisions():
                    global_score = self.score
                    return

                # win?
                if self.pellet_count <= 0:
                    global_score = self.score
                    display.clear()
                    draw_text(6, 18, "YOU", 0, 255, 0)
                    draw_text(6, 33, "WON", 0, 255, 0)
                    display_score_and_time(global_score)
                    sleep_ms(1300)
                    return

                global_score = self.score

                # incremental redraw: old/new sprite cells (and current cell if pellet changed)
                dirty = set()
                dirty.add((old_px, old_py))
                dirty.add((self.px, self.py))
                for p in old_ghosts:
                    dirty.add(p)
                for g in self.ghosts:
                    dirty.add((g[0], g[1]))
                # if frightened state toggles, redraw ghosts too (same cells)
                if (old_power > 0) != (self.power_timer > 0):
                    for g in self.ghosts:
                        dirty.add((g[0], g[1]))

                self._draw_dirty_cells(dirty)

                if self.frame % 90 == 0:
                    gc.collect()

            else:
                sleep_ms(6)

            if self._dirty:
                self._draw()
            else:
                sleep_ms(8)


class CaveFlyGame:
    """
    Cave flyer where the player navigates through a tight tunnel.

    Generates procedural cave walls and collision detection.
    """

    """
    CAVE FLYER (wie Flappy in Höhle)
    Steuerung:
      - Z oder Stick UP: Schub nach oben
      - C: zurück ins Menü
    """

    def __init__(self):
        """Initialize the CaveFly game and set starting state.

        Calls `reset()` to initialize score, player position and tunnel.
        """
        self.reset()

    async def main_loop_async(self, joystick):
        """Cooperative async CaveFly main loop for browsers."""
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        display_score_and_time(0, force=True)

        # 2 second preview of cave
        self._draw()
        try:
            await asyncio.sleep(2.0)
        except Exception:
            pass

        frame_ms = 33
        last = ticks_ms()

        while True:
            c_button, z_button = joystick.nunchuck.buttons()
            if c_button:
                return

            now = ticks_ms()
            if ticks_diff(now, last) < frame_ms:
                await asyncio.sleep(0.002)
                continue
            last = now
            self.frame += 1

            # Direct control (no gravity): steer left/right
            d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT])
            step = 2
            if d == JOYSTICK_LEFT:
                self.bx = max(self.bx - step, 0)
            elif d == JOYSTICK_RIGHT:
                self.bx = min(self.bx + step, WIDTH - 2)

            # scroll cave
            self._step_scroll()

            # Scoring
            self.score += 1
            global_score = self.score

            if self._collide():
                game_over = True
                return

            self._draw()

            maybe_collect(140)

    def reset(self):
        """Reset the game variables to their initial values.

        Sets score, frame counter, player position, tunnel parameters
        and initializes the ringbuffer that stores wall positions.
        """
        self.score = 0
        self.frame = 0

        # Player (2x2) fixed Y, steer X (no gravity)
        self.by = PLAY_HEIGHT // 2
        self.bx = WIDTH // 2

        # Tunnel parameters: start wide, narrow progressively
        self.base_gap = 36  # much wider start
        self.min_gap = 8
        self.gap = self.base_gap
        self.center = WIDTH // 2  # start centered
        self.speed = 1

        # Ringbuffer for left/right tunnel boundaries per row
        self.head = 0
        self.left_wall = bytearray(PLAY_HEIGHT)
        self.right_wall = bytearray(PLAY_HEIGHT)

        # Initialize tunnel for all visible rows
        for y in range(PLAY_HEIGHT):
            self._gen_row_at((self.head + y) % PLAY_HEIGHT)

        # Ensure player starts in the middle of the opening
        mid = (
            int(self.left_wall[self._idx_row(self.by)])
            + int(self.right_wall[self._idx_row(self.by)])
        ) // 2
        self.bx = self._clamp(mid, 1, WIDTH - 3)

    def _clamp(self, v, lo, hi):
        """Clamp `v` into the inclusive range [lo, hi].

        Returns `lo` if `v` is below the range and `hi` if above.
        """
        if v < lo:
            return lo
        if v > hi:
            return hi
        return v

    def _idx_row(self, y):
        """Return the ringbuffer index for the given visible row `y`.

        Accounts for the current `head` offset in the ringbuffer.
        """
        return (self.head + y) % PLAY_HEIGHT

    def _gen_row_at(self, idx):
        """Generate tunnel wall positions for ringbuffer index `idx`.

        The function narrows the tunnel over time, applies a slight
        random drift to the center, clamps values and writes left and
        right wall positions into the ringbuffer arrays.
        """
        # tunnel tightens over time: starts wide, narrows progressively
        self.gap = self.base_gap - int(self.score / 60)
        if self.gap < self.min_gap:
            self.gap = self.min_gap

        # center drift (keep within bounds)
        self.center += random.randint(-2, 2)
        self.center = self._clamp(
            self.center, (self.gap // 2) + 3, WIDTH - (self.gap // 2) - 4
        )

        left = self.center - (self.gap // 2)
        right = self.center + (self.gap // 2)
        if left < 1:
            left = 1
        if right > WIDTH - 2:
            right = WIDTH - 2
        self.left_wall[idx] = left
        self.right_wall[idx] = right

    def _step_scroll(self):
        """Advance the tunnel by one row and generate the new bottom row.

        Moves the ringbuffer `head` and calls `_gen_row_at` for the
        newly visible bottom row.
        """
        # scroll upward: advance head so y=0 becomes previous y=1
        self.head = (self.head + 1) % PLAY_HEIGHT
        # generate new bottom row
        self._gen_row_at(self._idx_row(PLAY_HEIGHT - 1))

    def _collide(self):
        """Check collision between the 2x2 player and tunnel walls.

        Returns True when the player overlaps a wall or leaves the
        vertical bounds, False otherwise.
        """
        # bird 2x2 at (bx,by)
        x = self.bx
        for yy in (self.by, self.by + 1):
            if yy < 0 or yy >= PLAY_HEIGHT:
                return True
            ri = self._idx_row(yy)
            left = int(self.left_wall[ri])
            right = int(self.right_wall[ri])
            if x <= left:
                return True
            if (x + 1) >= right:
                return True
        return False

    def _draw(self):
        """Render the tunnel and the player for the CaveFly frame."""
        display.clear()
        sp = display.set_pixel

        # tunnel outlines per row
        for y in range(PLAY_HEIGHT):
            i = self._idx_row(y)
            left = int(self.left_wall[i])
            right = int(self.right_wall[i])
            if 0 <= left < WIDTH:
                sp(left, y, 0, 180, 255)
                if left + 1 < WIDTH:
                    sp(left + 1, y, 0, 120, 200)
            if 0 <= right < WIDTH:
                sp(right, y, 0, 180, 255)
                if right - 1 >= 0:
                    sp(right - 1, y, 0, 120, 200)

        # Bird 2x2
        draw_rectangle(self.bx, self.by, self.bx + 1, self.by + 1, 255, 255, 0)

        display_score_and_time(self.score)

    def main_loop(self, joystick):
        """Main loop for CaveFly: handle input and advance the tunnel.

        Reads joystick input, updates the player position and tunnel
        scroll, checks collisions, and updates score until the user
        cancels (C button).
        """
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        display_score_and_time(0, force=True)

        # 2 second preview of cave
        self._draw()
        sleep_ms(2000)

        frame_ms = 33
        last = ticks_ms()

        while True:
            c_button, z_button = joystick.nunchuck.buttons()
            if c_button:
                return

            now = ticks_ms()
            if ticks_diff(now, last) < frame_ms:
                sleep_ms(2)
                continue
            last = now
            self.frame += 1

            # Direct control (no gravity): steer left/right
            d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT])
            step = 2
            if d == JOYSTICK_LEFT:
                self.bx = max(self.bx - step, 0)
            elif d == JOYSTICK_RIGHT:
                self.bx = min(self.bx + step, WIDTH - 2)

            # scroll cave
            self._step_scroll()

            # scoring
            self.score += 1
            global_score = self.score

            if self._collide():
                game_over = True
                return

            self._draw()

            maybe_collect(140)


class PitfallGame:
    """
    Platformer-style runner inspired by Pitfall: avoid obstacles and collect items.

    Manages simple physics, tile-based levels, and scoring.
    """

    """
    PITFALL MINI (Endlos-Runner)
    Steuerung:
      - Links/Rechts: laufen
      - Z oder Stick UP: springen
      - C: zurück ins Menü
    """

    def __init__(self):
        """Initialize PitfallGame and reset to starting conditions."""
        self.reset()

    async def main_loop_async(self, joystick):
        """Cooperative async Pitfall main loop for browsers."""
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        self._ensure_obstacles()

        frame_ms = 33
        last_frame = ticks_ms()

        while not game_over:
            c_button, z_button = joystick.nunchuck.buttons()
            if c_button:
                return

            now = ticks_ms()
            if ticks_diff(now, last_frame) < frame_ms:
                await asyncio.sleep(0.002)
                continue
            last_frame = now
            self.frame += 1

            # difficulty
            self.speed = 1.2 + (self.distance / 800.0)
            if self.speed > 2.6:
                self.speed = 2.6

            # scroll obstacles
            for o in self.obstacles:
                o["x"] -= self.speed

            # cleanup and ensure
            self.obstacles = [
                o for o in self.obstacles if (o.get("x", 0) + o.get("w", 1)) > -2
            ]
            self._ensure_obstacles()

            # move
            d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_UP])
            if d == JOYSTICK_LEFT:
                self.px = max(0, self.px - 2)
            elif d == JOYSTICK_RIGHT:
                self.px = min(WIDTH - self.pw, self.px + 2)

            # jump handling
            if self.jump_cd > 0:
                self.jump_cd -= 1

            jump_pressed = z_button or d == JOYSTICK_UP
            if jump_pressed and self.on_ground and self.jump_cd == 0:
                if not self.jump_charging:
                    self.jump_charging = True
                    self.jump_start_frame = self.frame

            elif not jump_pressed and self.jump_charging:
                hold_frames = self.frame - self.jump_start_frame
                if hold_frames < 0:
                    hold_frames = 0
                if hold_frames > self.jump_charge_max_frames:
                    hold_frames = self.jump_charge_max_frames

                jump_power = self.jump_min_power - (hold_frames * 0.35)
                if jump_power < self.jump_max_power:
                    jump_power = self.jump_max_power

                self.vy = jump_power
                self.on_ground = False
                self.jump_cd = 10
                self.jump_charging = False

            # physics
            in_pit = self._player_in_pit()
            self.vy += 0.45
            self.py += self.vy

            if not in_pit:
                if (self.py + self.ph - 1) >= self.ground_y:
                    self.py = float(self.ground_y - self.ph + 1)
                    self.vy = 0.0
                    self.on_ground = True
                else:
                    self.on_ground = False
            else:
                self.on_ground = False

            # collect and lose checks
            self._check_treasure()
            if self._check_snake_collision() or self.py > PLAY_HEIGHT + 2:
                global_score = self.score
                game_over = True
                return

            # scoring
            self.distance += self.speed
            self.score = int(self.distance / 6) + self.bonus
            global_score = self.score

            self._render()

            if self.frame % 40 == 0:
                gc.collect()

    def reset(self):
        """Reset player physics, spawn state, and scoring variables."""
        self.ground_y = PLAY_HEIGHT - 4
        self.pw = 3
        self.ph = 5
        self.px = 10
        self.py = float(self.ground_y - self.ph + 1)
        self.vy = 0.0
        self.on_ground = True

        self.speed = 0.9
        self.distance = 0.0
        self.bonus = 0
        self.score = 0

        self.obstacles = []
        self.jump_cd = 0
        self.last_spawn_kind = None
        self.frame = 0
        self.jump_start_frame = 0
        self.jump_charging = False
        self.jump_charge_max_frames = 10
        self.jump_min_power = -3.2
        self.jump_max_power = -6.5

        # Start-of-run grace period: no snakes/holes at the very beginning.
        # We enforce this via spawn logic so it works for both desktop and RP2040.
        self._safe_distance = 20.0

    def _spawn_one(self, x_start):
        """Spawn a single obstacle or treasure at horizontal start `x_start`.

        Chooses obstacle kind probabilistically and appends a dictionary
        describing the obstacle to `self.obstacles`.
        """
        # At the start, spawn only treasures to avoid immediate frustration.
        if self.distance < self._safe_distance:
            kind = "TREASURE"
        else:
            r = random.randint(0, 99)
            kind = "PIT" if r < 45 else ("SNAKE" if r < 75 else "TREASURE")

        # nicht zu viele pits hintereinander
        if (
            kind == "PIT"
            and self.last_spawn_kind == "PIT"
            and random.randint(0, 99) < 55
        ):
            kind = "SNAKE"

        if kind == "PIT":
            w = random.randint(8, 16)
            self.obstacles.append({"kind": "PIT", "x": float(x_start), "w": w})
        elif kind == "SNAKE":
            w = random.randint(5, 8)
            self.obstacles.append({"kind": "SNAKE", "x": float(x_start), "w": w})
        else:
            ty = self.ground_y - random.choice([12, 16, 20])
            self.obstacles.append(
                {
                    "kind": "TREASURE",
                    "x": float(x_start),
                    "y": ty,
                    "w": 2,
                    "h": 2,
                    "got": False,
                }
            )

        self.last_spawn_kind = kind

    def _ensure_obstacles(self):
        """Ensure there are enough obstacles ahead of the player.

        Extends `self.obstacles` with spawned objects until a safe
        distance ahead of the player is populated.
        """
        max_right = -999
        for o in self.obstacles:
            w = o.get("w", 1)
            xr = o["x"] + w
            if xr > max_right:
                max_right = xr

        while max_right < WIDTH + 20:
            gap = random.randint(14, 28)
            spawn_x = max_right + gap
            self._spawn_one(spawn_x)
            max_right = spawn_x + self.obstacles[-1].get("w", 1)

    def _player_in_pit(self):
        """Return True if the player's horizontal foot is inside a pit."""
        foot = self.px + (self.pw // 2)
        for o in self.obstacles:
            if o["kind"] == "PIT":
                if o["x"] <= foot <= (o["x"] + o["w"] - 1):
                    return True
        return False

    def _check_snake_collision(self):
        """Detect collision with snake obstacles near ground level.

        Only counts as a hit when the player is close to ground height.
        """
        # nur gefährlich, wenn Spieler nahe am Boden ist
        player_bottom = int(self.py) + self.ph - 1
        if player_bottom < (self.ground_y - 2):
            return False

        px1 = self.px
        px2 = self.px + self.pw - 1
        py1 = int(self.py)
        py2 = py1 + self.ph - 1

        sy1 = self.ground_y - 2
        sy2 = self.ground_y - 1

        for o in self.obstacles:
            if o["kind"] != "SNAKE":
                continue
            sx1 = int(o["x"])
            sx2 = sx1 + o["w"] - 1

            if sx2 < px1 or px2 < sx1:
                continue
            if sy2 < py1 or py2 < sy1:
                continue
            return True
        return False

    def _check_treasure(self):
        """Detect and collect treasure items within the player's hitbox.

        Marks collected treasures and increases the bonus score.
        """
        px1 = self.px
        px2 = self.px + self.pw - 1
        py1 = int(self.py)
        py2 = py1 + self.ph - 1

        for o in self.obstacles:
            if o["kind"] != "TREASURE" or o.get("got"):
                continue

            tx1 = int(o["x"])
            ty1 = int(o["y"])
            tx2 = tx1 + o["w"] - 1
            ty2 = ty1 + o["h"] - 1

            if tx2 < px1 or px2 < tx1:
                continue
            if ty2 < py1 or py2 < ty1:
                continue

            o["got"] = True
            self.bonus += 25

    def _rect_play(self, x, y, w, h, r, g, b):
        """Draw a rectangle within the playfield using shared helper.

        Wrapper around `draw_play_rect` to centralize playfield drawing.
        """
        # reuse shared helper to draw playfield rectangles
        draw_play_rect(x, y, w, h, r, g, b)

    def _render(self):
        """Render the full Pitfall playfield and obstacles.

        Draws ground, pits, snakes, treasures and the player to the
        display buffer for the current frame.
        """
        display.clear()

        # Boden-Band
        self._rect_play(
            0, self.ground_y, WIDTH, PLAY_HEIGHT - self.ground_y, 40, 90, 40
        )

        # Pits (Löcher)
        for o in self.obstacles:
            if o["kind"] == "PIT":
                x = int(o["x"])
                self._rect_play(
                    x, self.ground_y, o["w"], PLAY_HEIGHT - self.ground_y, 0, 0, 0
                )

        # Schlangen
        for o in self.obstacles:
            if o["kind"] == "SNAKE":
                x = int(o["x"])
                self._rect_play(x, self.ground_y - 2, o["w"], 2, 255, 40, 40)
                ey = self.ground_y - 2
                if 0 <= ey < PLAY_HEIGHT:
                    if 0 <= x + 1 < WIDTH:
                        display.set_pixel(x + 1, ey, 0, 0, 0)
                    if 0 <= x + o["w"] - 2 < WIDTH:
                        display.set_pixel(x + o["w"] - 2, ey, 0, 0, 0)

        # Treasure
        for o in self.obstacles:
            if o["kind"] == "TREASURE" and not o.get("got"):
                tx = int(o["x"])
                ty = int(o["y"])
                self._rect_play(tx, ty, o["w"], o["h"], 255, 215, 0)

        # Spieler
        self._rect_play(self.px, int(self.py), self.pw, self.ph, 230, 230, 230)
        hx = self.px + 1
        hy = int(self.py)
        if 0 <= hx < WIDTH and 0 <= hy < PLAY_HEIGHT:
            display.set_pixel(hx, hy, 0, 0, 0)

        display_score_and_time(self.score)

    def main_loop(self, joystick):
        """Main loop for Pitfall: advance world, handle input and collisions.

        Runs until `game_over` or the player cancels. Reads joystick
        input, updates physics and obstacles, checks collisions, and
        renders each frame.
        """
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        self._ensure_obstacles()

        frame_ms = 33
        last_frame = ticks_ms()

        while not game_over:
            try:
                c_button, z_button = joystick.nunchuck.buttons()
                if c_button:
                    return

                now = ticks_ms()
                if ticks_diff(now, last_frame) < frame_ms:
                    sleep_ms(2)
                    continue
                last_frame = now
                self.frame += 1

                # difficulty
                self.speed = 1.2 + (self.distance / 800.0)
                if self.speed > 2.6:
                    self.speed = 2.6

                # scroll obstacles
                for o in self.obstacles:
                    o["x"] -= self.speed

                # cleanup
                self.obstacles = [
                    o for o in self.obstacles if (o.get("x", 0) + o.get("w", 1)) > -2
                ]
                self._ensure_obstacles()

                # move
                d = joystick.read_direction(
                    [JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_UP]
                )
                if d == JOYSTICK_LEFT:
                    self.px = max(0, self.px - 2)
                elif d == JOYSTICK_RIGHT:
                    self.px = min(WIDTH - self.pw, self.px + 2)

                # jump with variable height
                if self.jump_cd > 0:
                    self.jump_cd -= 1

                jump_pressed = z_button or d == JOYSTICK_UP
                if jump_pressed and self.on_ground and self.jump_cd == 0:
                    if not self.jump_charging:
                        self.jump_charging = True
                        self.jump_start_frame = self.frame

                elif not jump_pressed and self.jump_charging:
                    # release: jump with height based on hold duration
                    hold_frames = self.frame - self.jump_start_frame
                    if hold_frames < 0:
                        hold_frames = 0
                    if hold_frames > self.jump_charge_max_frames:
                        hold_frames = self.jump_charge_max_frames

                    jump_power = self.jump_min_power - (hold_frames * 0.35)
                    # clamp: don't exceed max power
                    if jump_power < self.jump_max_power:
                        jump_power = self.jump_max_power

                    self.vy = jump_power
                    self.on_ground = False
                    self.jump_cd = 10
                    self.jump_charging = False

                # physics
                in_pit = self._player_in_pit()
                self.vy += 0.45
                self.py += self.vy

                if not in_pit:
                    if (self.py + self.ph - 1) >= self.ground_y:
                        self.py = float(self.ground_y - self.ph + 1)
                        self.vy = 0.0
                        self.on_ground = True
                    else:
                        self.on_ground = False
                else:
                    self.on_ground = False

                # collect
                self._check_treasure()

                # lose
                if self._check_snake_collision() or self.py > PLAY_HEIGHT + 2:
                    global_score = self.score
                    game_over = True
                    return

                # score
                self.distance += self.speed
                self.score = int(self.distance / 6) + self.bonus
                global_score = self.score

                self._render()

                if self.frame % 40 == 0:
                    gc.collect()

            except RestartProgram:
                return


class MonkeyBallLiteGame:
    """
    Lightweight Monkey Ball inspired tilt-and-roll maze game.

    Uses simple physics to move a ball through obstacles to the goal.
    """

    """
    Monkey Ball Lite – Top-Down Marble Maze
    Steuerung:
      - Stick: kippen (Tilt -> Beschleunigung)
      - Z: Boost (stärkerer Tilt)
      - C: zurück ins Menü
    Ziel:
      - Sammle optional Coins (*) und erreiche das Ziel (G)
      - Falle nicht in Löcher (o)
    """

    # Fixed-point Q8.8
    FP = const(8)
    ONE = const(1 << FP)

    # MonkeyBall constants (moved from module-level)
    MB_TILE = const(4)
    MB_W = const(14)
    MB_H = const(14)

    # Tile codes (bytes)
    T_WALL = ord("#")
    T_FLOOR = ord(".")
    T_START = ord("S")
    T_GOAL = ord("G")
    T_HOLE = ord("o")
    T_COIN = ord("*")

    # Colors (tweak if you like)
    COL_WALL = (0, 0, 120)
    COL_FLOOR = (0, 0, 0)
    COL_GOAL = (0, 255, 0)
    COL_HOLE = (200, 0, 200)
    COL_COIN = (255, 220, 0)

    COL_BALL = (255, 255, 255)
    COL_SHAD = (40, 40, 40)

    # Levels: 14x14, keep borders walled.
    MB_LEVELS = [
        (
            b"##############",
            b"#S....#.......#",
            b"#.##..#..###..#",
            b"#..#.....#....#",
            b"#..#####.#.##.#",
            b"#......#.#....#",
            b"####...#.#.####",
            b"#..#...#.#....#",
            b"#..#.###.####.#",
            b"#..#.....#..*.#",
            b"#..#####.#.##.#",
            b"#......#.#..o.#",
            b"#..*....#....G#",
            b"##############",
        ),
        (
            b"##############",
            b"#S..*.....#...#",
            b"#.####.##.#.###",
            b"#......#..#...#",
            b"#.####.#.###..#",
            b"#.#..#.#...#..#",
            b"#.#..#.###.#.##",
            b"#.#......#....#",
            b"#.######.#.##.#",
            b"#......#.#..#.#",
            b"##.###.#.##.#.#",
            b"#..#...#....#.#",
            b"#..#.o...*..#G#",
            b"##############",
        ),
        (
            b"##############",
            b"#S.....#..*...#",
            b"#.###.##.###..#",
            b"#...#....#....#",
            b"###.#.####.####",
            b"#...#......#..#",
            b"#.######.#.#.##",
            b"#......#.#.#..#",
            b"####.#.#.#.##.#",
            b"#..#.#.#.#....#",
            b"#..#.#.#.######",
            b"#..#...#....oG#",
            b"#..*...#......#",
            b"##############",
        ),
    ]

    # Physics tuning (Q8.8-ish numbers)
    # acceleration = tilt * ACC
    ACC = const(10)  # base accel per tick (in FP units)
    ACC_BOOST = const(18)  # accel when Z held

    # friction v = v * FRICTION_NUM / FRICTION_DEN
    FRICTION_NUM = const(235)  # ~0.918
    FRICTION_DEN = const(256)

    # speed clamp
    VMAX = const(2 * ONE) + const(100)  # ~2.39 px/tick

    # ball size
    R = const(1)  # radius in pixels (visual is 2x2)

    def __init__(self, ctx=None):
        """Initialize the game context wrapper and bind runtime symbols.

        `ctx` may supply platform-specific functions (display, timing,
        helpers). Missing symbols are looked up in globals().
        """
        # context can provide runtime symbols (display, helpers, timing)
        if ctx is None:
            ctx = {}

        def _g(n):
            """Return symbol `n` from `ctx` or fallback to globals()."""
            return getattr(ctx, n, globals().get(n))

        self.display = _g("display")
        self.draw_text = _g("draw_text")
        self.draw_rectangle = _g("draw_rectangle")
        self.display_score_and_time = _g("display_score_and_time")
        self.ticks_ms = _g("ticks_ms")
        self.ticks_diff = _g("ticks_diff")
        self.sleep_ms = _g("sleep_ms")
        self.WIDTH = _g("WIDTH")
        self.PLAY_HEIGHT = _g("PLAY_HEIGHT")
        self.JOYSTICK_UP = _g("JOYSTICK_UP")
        self.JOYSTICK_DOWN = _g("JOYSTICK_DOWN")
        self.JOYSTICK_LEFT = _g("JOYSTICK_LEFT")
        self.JOYSTICK_RIGHT = _g("JOYSTICK_RIGHT")
        self.JOYSTICK_UP_LEFT = _g("JOYSTICK_UP_LEFT")
        self.JOYSTICK_UP_RIGHT = _g("JOYSTICK_UP_RIGHT")
        self.JOYSTICK_DOWN_LEFT = _g("JOYSTICK_DOWN_LEFT")
        self.JOYSTICK_DOWN_RIGHT = _g("JOYSTICK_DOWN_RIGHT")
        self.gc = _g("gc")

        # compute MonkeyBall offsets now that WIDTH / PLAY_HEIGHT exist
        try:
            self.MB_OFF_X = (64 - (self.MB_W * self.MB_TILE)) // 2
            self.MB_OFF_Y = (58 - (self.MB_H * self.MB_TILE)) // 2
        except Exception:
            self.MB_OFF_X = 0
            self.MB_OFF_Y = 0

        self.level_idx = 0
        self.score = 0
        self.frame = 0
        self.reset_level(reset_score=True)

    async def main_loop_async(self, joystick):
        """Cooperative async MonkeyBall main loop for browsers."""
        global game_over, global_score
        game_over = False
        global_score = 0

        # reset level synchronously
        self.reset_level(reset_score=True)

        frame_ms = 35
        last_frame = ticks_ms()
        self.frame = 0

        while True:
            c_button, z_button = joystick.nunchuck.buttons()
            if c_button:
                return
            if game_over:
                return

            now = ticks_ms()
            if ticks_diff(now, last_frame) < frame_ms:
                await asyncio.sleep(0.002)
                continue
            last_frame = now
            self.frame += 1

            # input / tilt
            d = joystick.read_direction(
                [
                    JOYSTICK_UP,
                    JOYSTICK_DOWN,
                    JOYSTICK_LEFT,
                    JOYSTICK_RIGHT,
                    JOYSTICK_UP_LEFT,
                    JOYSTICK_UP_RIGHT,
                    JOYSTICK_DOWN_LEFT,
                    JOYSTICK_DOWN_RIGHT,
                ]
            )

            tx = 0
            ty = 0
            if d in (JOYSTICK_LEFT, JOYSTICK_UP_LEFT, JOYSTICK_DOWN_LEFT):
                tx = -1
            elif d in (JOYSTICK_RIGHT, JOYSTICK_UP_RIGHT, JOYSTICK_DOWN_RIGHT):
                tx = 1

            if d in (JOYSTICK_UP, JOYSTICK_UP_LEFT, JOYSTICK_UP_RIGHT):
                ty = -1
            elif d in (JOYSTICK_DOWN, JOYSTICK_DOWN_LEFT, JOYSTICK_DOWN_RIGHT):
                ty = 1

            acc = self.ACC_BOOST if z_button else self.ACC

            # physics
            self.vx += tx * acc
            self.vy += ty * acc
            self.vx = (self.vx * self.FRICTION_NUM) // self.FRICTION_DEN
            self.vy = (self.vy * self.FRICTION_NUM) // self.FRICTION_DEN
            if self.vx > self.VMAX:
                self.vx = self.VMAX
            if self.vx < -self.VMAX:
                self.vx = -self.VMAX
            if self.vy > self.VMAX:
                self.vy = self.VMAX
            if self.vy < -self.VMAX:
                self.vy = -self.VMAX

            # move + collisions
            nx = self.x + self.vx
            ny = self.y
            if self._collides_ball_at(nx, ny):
                self.vx = -self.vx // 2
            else:
                self.x = nx

            nx = self.x
            ny = self.y + self.vy
            if self._collides_ball_at(nx, ny):
                self.vy = -self.vy // 2
            else:
                self.y = ny

            # interactions
            px = self.x >> self.FP
            py = self.y >> self.FP
            txc, tyc, tile = self._touch_hole_or_goal_or_coin(px, py)

            if tile == self.T_HOLE:
                global_score = self.score
                game_over = True
                display.clear()
                draw_text(6, 18, "FALL", 255, 0, 0)
                display_score_and_time(global_score, force=True)
                try:
                    await asyncio.sleep(0.9)
                except Exception:
                    pass
                return

            if tile == self.T_COIN:
                self._set_tile(txc, tyc, self.T_FLOOR)
                self.coins_left -= 1
                self.score += 25
                self._draw_tile(txc, tyc)

            if tile == self.T_GOAL:
                self.score += 200 + (self.level_idx * 30)
                global_score = self.score
                display.clear()
                draw_text(6, 16, "GOAL", 0, 255, 0)
                draw_text(
                    6,
                    30,
                    "LVL " + str((self.level_idx % len(self.MB_LEVELS)) + 1),
                    255,
                    255,
                    0,
                )
                display_score_and_time(global_score, force=True)
                try:
                    await asyncio.sleep(1.2)
                except Exception:
                    pass
                self.level_idx = (self.level_idx + 1) % len(self.MB_LEVELS)
                self.reset_level(reset_score=False)
                continue

            # render (dirty)
            if self.last_px is not None:
                self._repair_under_ball(self.last_px, self.last_py)
            self._draw_ball(px, py)
            self.last_px, self.last_py = px, py

            display_score_and_time(self.score)
            global_score = self.score

            if (self.frame % 90) == 0:
                try:
                    self.gc.collect()
                except Exception:
                    pass

    # -----------------
    # Level / Map
    # -----------------
    def reset_level(self, reset_score=False):
        """Reset the current level map and optionally the score."""
        if reset_score:
            self.score = 0
            self.level_idx = 0

        # Copy current level into mutable rows
        raw = self.MB_LEVELS[self.level_idx % len(self.MB_LEVELS)]
        self.map = [bytearray(row) for row in raw]

        self.coins_left = 0
        sx = sy = 1
        gx = gy = 1

        for y in range(self.MB_H):
            row = self.map[y]
            for x in range(self.MB_W):
                t = row[x]
                if t == self.T_START:
                    sx, sy = x, y
                    row[x] = self.T_FLOOR
                elif t == self.T_GOAL:
                    gx, gy = x, y
                elif t == self.T_COIN:
                    self.coins_left += 1

        self.start_tx, self.start_ty = sx, sy
        self.goal_tx, self.goal_ty = gx, gy

        # Ball state in pixel space inside map area
        self.x = (self.MB_OFF_X + sx * self.MB_TILE + (self.MB_TILE // 2)) << self.FP
        self.y = (self.MB_OFF_Y + sy * self.MB_TILE + (self.MB_TILE // 2)) << self.FP
        self.vx = 0
        self.vy = 0

        # last drawn position (for dirty repair)
        self.last_px = None
        self.last_py = None

        # Render static map once
        self.display.clear()
        self._draw_static_map()
        self.display_score_and_time(self.score, force=True)

        # tiny level label (optional)
        try:
            self.draw_text(
                2,
                2,
                "MB" + str((self.level_idx % len(self.MB_LEVELS)) + 1),
                255,
                255,
                255,
            )
        except Exception:
            pass

    def _tile_at(self, tx, ty):
        """Return the tile value at tile coordinates (tx, ty).

        Out-of-bounds coordinates are treated as walls.
        """
        if tx < 0 or tx >= self.MB_W or ty < 0 or ty >= self.MB_H:
            return self.T_WALL
        return self.map[ty][tx]

    def _set_tile(self, tx, ty, val):
        """Set the tile at (tx, ty) to `val` if within bounds."""
        if 0 <= tx < self.MB_W and 0 <= ty < self.MB_H:
            self.map[ty][tx] = val

    def _pixel_to_tile(self, px, py):
        """Convert pixel coordinates to tile coordinates within the map."""
        tx = (px - self.MB_OFF_X) // self.MB_TILE
        ty = (py - self.MB_OFF_Y) // self.MB_TILE
        return tx, ty

    def _draw_tile(self, tx, ty):
        """Draw a single map tile at tile coordinates (tx, ty)."""
        t = self._tile_at(tx, ty)
        x1 = self.MB_OFF_X + tx * self.MB_TILE
        y1 = self.MB_OFF_Y + ty * self.MB_TILE
        x2 = x1 + self.MB_TILE - 1
        y2 = y1 + self.MB_TILE - 1

        if t == self.T_WALL:
            self.draw_rectangle(x1, y1, x2, y2, *self.COL_WALL)
        else:
            # floor base
            self.draw_rectangle(x1, y1, x2, y2, *self.COL_FLOOR)
            if t == self.T_GOAL:
                # goal highlight (center)
                cx = x1 + 1
                cy = y1 + 1
                self.draw_rectangle(cx, cy, x2 - 1, y2 - 1, *self.COL_GOAL)
            elif t == self.T_HOLE:
                # hole dot
                cx = x1 + 1
                cy = y1 + 1
                self.draw_rectangle(cx, cy, x2 - 1, y2 - 1, *self.COL_HOLE)
            elif t == self.T_COIN:
                # coin pixel cluster
                cx = x1 + 1
                cy = y1 + 1
                self.draw_rectangle(cx, cy, cx + 1, cy + 1, *self.COL_COIN)

    def _draw_static_map(self):
        """Draw the static, tile-based portion of the current map."""
        for ty in range(self.MB_H):
            for tx in range(self.MB_W):
                self._draw_tile(tx, ty)

    # -----------------
    # Dirty repair under ball
    # -----------------
    def _repair_under_ball(self, px, py):
        """Restore map tiles potentially covered by the moving ball.

        Calculates the tile region possibly affected by the ball and
        redraws those tiles only.
        """
        # redraw only the tiles the ball could have overwritten (<= 4 tiles)
        # ball footprint ~ 2x2 plus shadow 1px
        minx = px - 1
        maxx = px + 2
        miny = py - 1
        maxy = py + 2

        tx0, ty0 = self._pixel_to_tile(minx, miny)
        tx1, ty1 = self._pixel_to_tile(maxx, maxy)

        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                self._draw_tile(tx, ty)

    def _draw_ball(self, px, py):
        """Draw the ball and its shadow at pixel position (px, py)."""
        sp = self.display.set_pixel

        # shadow (below-right)
        sx = px + 1
        sy = py + 2
        if 0 <= sx < self.WIDTH and 0 <= sy < self.PLAY_HEIGHT:
            sp(sx, sy, *self.COL_SHAD)

        # 2x2 ball
        for dy in (0, 1):
            yy = py + dy
            if 0 <= yy < self.PLAY_HEIGHT:
                for dx in (0, 1):
                    xx = px + dx
                    if 0 <= xx < self.WIDTH:
                        sp(xx, yy, *self.COL_BALL)

    # -----------------
    # Collision helpers
    # -----------------
    def _is_wall_pixel(self, px, py):
        """Return True when the given pixel lies on a wall tile."""
        tx, ty = self._pixel_to_tile(px, py)
        return self._tile_at(tx, ty) == self.T_WALL

    def _touch_hole_or_goal_or_coin(self, cx, cy):
        """Handle collision of the ball with holes, goal or coins.

        Returns a tuple (hole_hit, goal_reached, coin_collected).
        """
        tx, ty = self._pixel_to_tile(cx, cy)
        t = self._tile_at(tx, ty)
        return tx, ty, t

    def _collides_ball_at(self, x_fp, y_fp):
        """Return True if the ball at fixed-point coords collides with walls."""
        # check 4 corners of ball bbox in pixel coords
        px = x_fp >> self.FP
        py = y_fp >> self.FP
        r = self.R

        # corners of 2x2-ish footprint
        corners = (
            (px - r, py - r),
            (px + r + 1, py - r),
            (px - r, py + r + 1),
            (px + r + 1, py + r + 1),
        )
        for cx, cy in corners:
            if self._is_wall_pixel(cx, cy):
                return True
        return False

    # -----------------
    # Main loop
    # -----------------
    def main_loop(self, joystick):
        """Main loop for the marble/mini-bomber physics-driven level.

        Handles input tilt, ball physics, collision detection and
        level progression until the player quits or reaches the goal.
        """
        global game_over, global_score
        game_over = False
        global_score = 0

        # reset from scratch each run
        self.reset_level(reset_score=True)

        frame_ms = 35
        last_frame = ticks_ms()
        self.frame = 0

        while True:
            c_button, z_button = joystick.nunchuck.buttons()
            if c_button:
                return
            if game_over:
                return

            now = self.ticks_ms()
            if self.ticks_diff(now, last_frame) < frame_ms:
                self.sleep_ms(2)
                continue
            last_frame = now
            self.frame += 1

            # -------- input -> tilt --------
            d = joystick.read_direction(
                [
                    JOYSTICK_UP,
                    JOYSTICK_DOWN,
                    JOYSTICK_LEFT,
                    JOYSTICK_RIGHT,
                    JOYSTICK_UP_LEFT,
                    JOYSTICK_UP_RIGHT,
                    JOYSTICK_DOWN_LEFT,
                    JOYSTICK_DOWN_RIGHT,
                ]
            )

            tx = 0
            ty = 0
            if d in (JOYSTICK_LEFT, JOYSTICK_UP_LEFT, JOYSTICK_DOWN_LEFT):
                tx = -1
            elif d in (JOYSTICK_RIGHT, JOYSTICK_UP_RIGHT, JOYSTICK_DOWN_RIGHT):
                tx = 1

            if d in (JOYSTICK_UP, JOYSTICK_UP_LEFT, JOYSTICK_UP_RIGHT):
                ty = -1
            elif d in (JOYSTICK_DOWN, JOYSTICK_DOWN_LEFT, JOYSTICK_DOWN_RIGHT):
                ty = 1

            acc = self.ACC_BOOST if z_button else self.ACC

            # -------- physics (fixed-point) --------
            # vx += tilt_x * acc; vy += tilt_y * acc
            self.vx += tx * acc
            self.vy += ty * acc

            # friction
            self.vx = (self.vx * self.FRICTION_NUM) // self.FRICTION_DEN
            self.vy = (self.vy * self.FRICTION_NUM) // self.FRICTION_DEN

            # clamp speed
            if self.vx > self.VMAX:
                self.vx = self.VMAX
            if self.vx < -self.VMAX:
                self.vx = -self.VMAX
            if self.vy > self.VMAX:
                self.vy = self.VMAX
            if self.vy < -self.VMAX:
                self.vy = -self.VMAX

            # -------- move + axis-separated collision --------
            nx = self.x + self.vx
            ny = self.y

            if self._collides_ball_at(nx, ny):
                # bounce x
                self.vx = -self.vx // 2
            else:
                self.x = nx

            nx = self.x
            ny = self.y + self.vy

            if self._collides_ball_at(nx, ny):
                # bounce y
                self.vy = -self.vy // 2
            else:
                self.y = ny

            # keep inside playfield bounds (map area)
            px = self.x >> self.FP
            py = self.y >> self.FP

            # -------- interactions --------
            # center point for tile checks
            txc, tyc, tile = self._touch_hole_or_goal_or_coin(px, py)

            if tile == self.T_HOLE:
                global_score = self.score
                game_over = True
                # optional: show text
                display.clear()
                draw_text(6, 18, "FALL", 255, 0, 0)
                display_score_and_time(global_score, force=True)
                sleep_ms(900)
                return

            if tile == self.T_COIN:
                self._set_tile(txc, tyc, self.T_FLOOR)
                self.coins_left -= 1
                self.score += 25
                # redraw that tile (since it changed)
                self._draw_tile(txc, tyc)

            if tile == self.T_GOAL:
                # optional rule: require all coins
                # if self.coins_left > 0: pass
                self.score += 200 + (self.level_idx * 30)
                global_score = self.score

                display.clear()
                draw_text(6, 16, "GOAL", 0, 255, 0)
                draw_text(
                    6,
                    30,
                    "LVL " + str((self.level_idx % len(self.MB_LEVELS)) + 1),
                    255,
                    255,
                    0,
                )
                display_score_and_time(global_score, force=True)
                sleep_ms(1200)

                self.level_idx = (self.level_idx + 1) % len(self.MB_LEVELS)
                self.reset_level(reset_score=False)
                continue

            # -------- render (dirty) --------
            # repair old ball area
            if self.last_px is not None:
                self._repair_under_ball(self.last_px, self.last_py)

            # draw new ball
            self._draw_ball(px, py)
            self.last_px, self.last_py = px, py

            display_score_and_time(self.score)
            global_score = self.score

            if (self.frame % 90) == 0:
                try:
                    self.gc.collect()
                except Exception:
                    pass


# ---- 2048 ----
# 2048 constants moved into `Game2048` as class attributes to avoid
# module-level namespace collisions with other inlined games.


class Game2048:
    """
    2048 puzzle game implementation adapted for the LED matrix.

    Handles merging tiles, spawning, and win/lose detection.
    """

    # 2048 visual and timing constants (class-scoped)
    TILE_PX = const(12)
    COL_BG = (0, 0, 0)
    COL_EMPTY = (10, 10, 30)
    COL_FRAME = (0, 50, 120)
    COL_TXT = (200, 200, 200)
    COL_CURSOR = (255, 255, 0)

    COL_VAL = {
        2: (238, 228, 218),
        4: (237, 224, 200),
        8: (242, 177, 121),
        16: (245, 149, 99),
        32: (246, 124, 95),
        64: (246, 94, 59),
        128: (237, 207, 114),
        256: (237, 204, 97),
        512: (237, 200, 80),
        1024: (237, 197, 63),
        2048: (237, 194, 46),
    }

    INPUT_MS = const(120)
    A_LONG_MS = const(420)

    def __init__(self, ctx=None):
        """Initialize the 2048 game wrapper and bind runtime helpers.

        Supports `ctx` being either a dict or an object that provides
        runtime symbols (display, timing, helpers). Falls back to
        module-level globals when symbols are missing.
        """
        # bind runtime symbols into module globals for legacy code paths
        if ctx is None:
            ctx = {}

        def _g(name):
            """Return a symbol by name from `ctx` or from globals()."""
            if isinstance(ctx, dict):
                return ctx.get(name, globals().get(name))
            return getattr(ctx, name, globals().get(name))

        try:
            self.display = _g("display")
            self.draw_text = _g("draw_text")
            self.draw_rectangle = _g("draw_rectangle")
            self.display_score_and_time = _g("display_score_and_time")
            self.ticks_ms = _g("ticks_ms")
            self.ticks_diff = _g("ticks_diff")
            self.sleep_ms = _g("sleep_ms")
            self.Data = _g("Data")
        except Exception:
            # fall back to module globals if lookup fails
            self.display = globals().get("display")
            self.draw_text = globals().get("draw_text")
            self.draw_rectangle = globals().get("draw_rectangle")
            self.display_score_and_time = globals().get("display_score_and_time")
            self.ticks_ms = globals().get("ticks_ms")
            self.ticks_diff = globals().get("ticks_diff")
            self.sleep_ms = globals().get("sleep_ms")
            self.Data = globals().get("Data")

        # use fixed 4x4 grid for 2048 (avoid conflicts with global GRID_W/GIRD_H)
        self.GRID_W = 4
        self.GRID_H = 4
        self.TILE_PX = 12
        self.GRID_PX = self.GRID_W * self.TILE_PX

        self.grid = [0] * (self.GRID_W * self.GRID_H)
        self.score = 0
        self.moves = 0
        self.max_val = 0
        self.victory = False

        self._last_input = self.ticks_ms()
        self._z_down_ms = None
        self._z_armed = False

        # compute layout offsets now that WIDTH / PLAY_HEIGHT exist
        try:
            self.off_x = (WIDTH - self.GRID_PX) // 2
            self.off_y = (PLAY_HEIGHT - self.GRID_PX) // 2
        except Exception:
            self.off_x = 0
            self.off_y = 0

        self.reset()

    def _idx(self, x, y):
        """Return linear index into the GRID from tile coordinates (x, y)."""
        return y * self.GRID_W + x

    def _tile_rect(self, x, y):
        """Return pixel rectangle for tile (x, y) in grid coordinates."""
        x1 = self.off_x + x * self.TILE_PX
        y1 = self.off_y + y * self.TILE_PX
        return x1, y1, x1 + self.TILE_PX - 1, y1 + self.TILE_PX - 1

    def reset(self):
        """Reset the 2048 board and spawn the initial tiles."""
        for i in range(self.GRID_W * self.GRID_H):
            self.grid[i] = 0
        self.score = 0
        self.moves = 0
        self.max_val = 0
        self.victory = False
        self._spawn_random()
        self._spawn_random()
        if self.display:
            self.display.clear()
        self._draw_board(full=True)
        if self.display_score_and_time:
            self.display_score_and_time(self.score, force=True)

    def _spawn_random(self):
        """Spawn a new tile (2 or 4) at a random empty grid position."""
        free = [i for i, v in enumerate(self.grid) if v == 0]
        if not free:
            return
        pos = random.choice(free)
        self.grid[pos] = 4 if random.random() < 0.1 else 2

    def _compress_line(self, line):
        """Compress and merge a single row/column for a 2048 move.

        Returns the new line and the score delta from merges.
        """
        out = []
        score_delta = 0
        skip = False
        for i in range(len(line)):
            if skip:
                skip = False
                continue
            if i + 1 < len(line) and line[i] == line[i + 1]:
                merged = line[i] * 2
                score_delta += merged
                out.append(merged)
                skip = True
            else:
                out.append(line[i])
        # Ensure the returned line has exactly GRID_W elements
        if len(out) < self.GRID_W:
            out += [0] * (self.GRID_W - len(out))
        elif len(out) > self.GRID_W:
            out = out[: self.GRID_W]
        return out, score_delta

    def _move(self, dir_idx):
        """Perform a move in one of four directions (dir_idx 0-3).

        Returns a tuple (changed, score_gain) indicating whether the
        board changed and how much score was gained from merges.
        """
        changed = False
        score_gain = 0

        for idx in range(self.GRID_W):
            if dir_idx in (0, 2):
                col = [self.grid[self._idx(idx, y)] for y in range(self.GRID_H)]
                if dir_idx == 2:
                    col.reverse()
                packed = [v for v in col if v]
                new_line, gain = self._compress_line(packed)
                score_gain += gain
                if dir_idx == 2:
                    new_line.reverse()
                for y in range(self.GRID_H):
                    if self.grid[self._idx(idx, y)] != new_line[y]:
                        changed = True
                    self.grid[self._idx(idx, y)] = new_line[y]
            else:
                row = [self.grid[self._idx(x, idx)] for x in range(self.GRID_W)]
                if dir_idx == 1:
                    row.reverse()
                packed = [v for v in row if v]
                new_line, gain = self._compress_line(packed)
                score_gain += gain
                if dir_idx == 1:
                    new_line.reverse()
                for x in range(self.GRID_W):
                    if self.grid[self._idx(x, idx)] != new_line[x]:
                        changed = True
                    self.grid[self._idx(x, idx)] = new_line[x]

        if changed:
            self.score += score_gain
            self.moves += 1
            self.max_val = max(self.grid)
            if self.max_val >= 2048:
                self.victory = True
            self._spawn_random()
        return changed

    def _any_moves_possible(self):
        """Return True if any move (or spawn) is possible on the board."""
        if any(v == 0 for v in self.grid):
            return True
        for y in range(self.GRID_H):
            for x in range(self.GRID_W):
                v = self.grid[self._idx(x, y)]
                if x + 1 < self.GRID_W and self.grid[self._idx(x + 1, y)] == v:
                    return True
                if y + 1 < self.GRID_H and self.grid[self._idx(x, y + 1)] == v:
                    return True
        return False

    def _draw_tile(self, x, y):
        """Draw an individual 2048 tile at grid position (x, y)."""
        val = self.grid[self._idx(x, y)]
        x1, y1, x2, y2 = self._tile_rect(x, y)
        col = self.COL_EMPTY if val == 0 else self.COL_VAL.get(val, (255, 255, 255))
        if self.draw_rectangle:
            self.draw_rectangle(x1, y1, x2, y2, *col)
            self.draw_rectangle(x1, y1, x2, y1, *self.COL_FRAME)
            self.draw_rectangle(x1, y2, x2, y2, *self.COL_FRAME)
            self.draw_rectangle(x1, y1, x1, y2, *self.COL_FRAME)
            self.draw_rectangle(x2, y1, x2, y2, *self.COL_FRAME)
        if val:
            try:
                # Represent tile values as single-character levels:
                # 2 -> '1', 4 -> '2', 8 -> '3', ..., 1024 -> 'A', 2048 -> 'B'
                v = val
                lvl = 0
                while v > 1:
                    v >>= 1
                    lvl += 1
                if lvl <= 9:
                    txt = str(lvl)
                else:
                    txt = chr(ord("A") + (lvl - 10))
                tw = 4  # single char width
                tx = x1 + (self.TILE_PX - tw) // 2
                ty = y1 + (self.TILE_PX - 6) // 2
                if self.draw_text:
                    self.draw_text(tx, ty, txt, 0, 0, 0)
            except Exception:
                pass

    def _draw_board(self, full=False):
        """Draw the full 2048 board or only the changed tiles."""
        if full:
            for y in range(self.GRID_H):
                for x in range(self.GRID_W):
                    self._draw_tile(x, y)
        else:
            self._draw_board(full=True)

        if self.display_score_and_time:
            self.display_score_and_time(self.score)

    def main_loop(self, joystick):
        """Main loop for 2048: process input and apply moves."""
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        self.ticks_ms()

        while True:
            c_button, z_button = joystick.nunchuck.buttons()
            if c_button:
                return
            now = self.ticks_ms()

            if z_button:
                if self._z_down_ms is None:
                    self._z_down_ms = now
                    self._z_armed = True
                elif (
                    self._z_armed
                    and self.ticks_diff(now, self._z_down_ms) >= self.A_LONG_MS
                ):
                    self._z_armed = False
                    self.reset()
            else:
                if self._z_down_ms is not None:
                    self._z_down_ms = None
                    self._z_armed = False

            if self.ticks_diff(now, self._last_input) < self.INPUT_MS:
                self.sleep_ms(5)
                continue

            d = joystick.read_direction(
                [JOYSTICK_UP, JOYSTICK_RIGHT, JOYSTICK_DOWN, JOYSTICK_LEFT]
            )
            if d is not None:
                # Map JOYSTICK_* tokens to numeric directions expected by
                # _move(): 0=UP, 1=RIGHT, 2=DOWN, 3=LEFT
                dir_map = {
                    JOYSTICK_UP: 0,
                    JOYSTICK_RIGHT: 1,
                    JOYSTICK_DOWN: 2,
                    JOYSTICK_LEFT: 3,
                }
                dir_idx = dir_map.get(d, None)
                if dir_idx is not None:
                    moved = self._move(dir_idx)
                else:
                    moved = False
                if moved:
                    self._draw_board(full=False)
                    if not self._any_moves_possible():
                        if self.display:
                            self.display.clear()
                        if self.draw_text:
                            self.draw_text(6, 18, "LOSE", 255, 0, 0)
                        if self.display_score_and_time:
                            self.display_score_and_time(self.score, force=True)
                        if self.Data:
                            self.Data.add_score("2048", self.score)
                        global_score = self.score
                        self.sleep_ms(1000)
                        self.reset()
                    elif self.victory:
                        if self.display:
                            self.display.clear()
                        if self.draw_text:
                            self.draw_text(6, 18, "WIN!", 0, 255, 0)
                        if self.display_score_and_time:
                            self.display_score_and_time(self.score, force=True)
                        if self.Data:
                            self.Data.add_score("2048", self.score)
                        self.victory = False
                        self.sleep_ms(700)
                self._last_input = now

            self.sleep_ms(2)
            if (now & 0x3FF) == 0:
                gc.collect()

    async def main_loop_async(self, joystick):
        """Async/cooperative version of the 2048 main loop for browsers.

        Uses `await asyncio.sleep()` instead of blocking `sleep_ms()` so the
        event loop remains responsive in WASM/pygbag environments.
        """
        import asyncio

        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        self.ticks_ms()

        while True:
            c_button, z_button = joystick.nunchuck.buttons()
            if c_button:
                return
            now = self.ticks_ms()

            if z_button:
                if self._z_down_ms is None:
                    self._z_down_ms = now
                    self._z_armed = True
                elif (
                    self._z_armed
                    and self.ticks_diff(now, self._z_down_ms) >= self.A_LONG_MS
                ):
                    self._z_armed = False
                    self.reset()
            else:
                if self._z_down_ms is not None:
                    self._z_down_ms = None
                    self._z_armed = False

            if self.ticks_diff(now, self._last_input) < self.INPUT_MS:
                await asyncio.sleep(0.005)
                continue

            d = joystick.read_direction(
                [
                    JOYSTICK_UP,
                    JOYSTICK_RIGHT,
                    JOYSTICK_DOWN,
                    JOYSTICK_LEFT,
                ]
            )
            if d is not None:
                dir_map = {
                    JOYSTICK_UP: 0,
                    JOYSTICK_RIGHT: 1,
                    JOYSTICK_DOWN: 2,
                    JOYSTICK_LEFT: 3,
                }
                dir_idx = dir_map.get(d, None)
                if dir_idx is not None:
                    moved = self._move(dir_idx)
                else:
                    moved = False
                if moved:
                    self._draw_board(full=False)
                    if not self._any_moves_possible():
                        if self.display:
                            self.display.clear()
                        if self.draw_text:
                            self.draw_text(6, 18, "LOSE", 255, 0, 0)
                        if self.display_score_and_time:
                            self.display_score_and_time(self.score, force=True)
                        if self.Data:
                            self.Data.add_score("2048", self.score)
                        global_score = self.score
                        await asyncio.sleep(1.0)
                        self.reset()
                    elif self.victory:
                        if self.display:
                            self.display.clear()
                        if self.draw_text:
                            self.draw_text(6, 18, "WIN!", 0, 255, 0)
                        if self.display_score_and_time:
                            self.display_score_and_time(self.score, force=True)
                        if self.Data:
                            self.Data.add_score("2048", self.score)
                        self.victory = False
                        await asyncio.sleep(0.7)
                self._last_input = now

            await asyncio.sleep(0.002)
            if (now & 0x3FF) == 0:
                try:
                    gc.collect()
                except Exception:
                    pass


try:
    from micropython import const
except ImportError:

    def const(x):
        """Fallback `const` implementation for non-MicroPython builds.

        Returns the input value unchanged. Used to allow the code to
        run under CPython during development.
        """
        return x


class LocoMotionGame:
    """
    Loco-Motion style puzzle/slide game adapted for the LED matrix.

    Handles tile sliding, movement rules, and goal detection.
    """

    # LocoMotion constants
    RL_TILE = const(8)
    RL_W = const(8)
    RL_H = const(7)
    RL_PX_W = RL_W * RL_TILE
    RL_PX_H = RL_H * RL_TILE

    N = const(1)
    E = const(2)
    S = const(4)
    W = const(8)

    TFLAG_NONE = const(0x00)
    TFLAG_START = const(0x10)
    TFLAG_END = const(0x20)
    TFLAG_EMPTY = const(0x30)

    COL_BG = (0, 0, 0)
    COL_TILE_BG = (0, 0, 0)
    COL_RAIL = (180, 180, 180)
    COL_RAIL2 = (80, 80, 80)
    COL_START = (0, 255, 0)
    COL_END = (255, 200, 0)
    COL_CURSOR = (255, 255, 0)
    COL_TRAIN = (255, 60, 60)
    COL_SHADOW = (40, 40, 40)

    EDIT_INPUT_MS = const(120)
    FRAME_MS_RUN = const(35)
    Z_LONG_MS = const(420)

    SYM_BITS = {
        ord("."): 0,
        ord("-"): E | W,
        ord("|"): N | S,
        ord("L"): N | E,
        ord("J"): E | S,
        ord("7"): S | W,
        ord("F"): W | N,
        ord("+"): N | E | S | W,
        ord("T"): N | E | W,
    }

    LEVELS = [
        (
            b"SL..L..E",
            b".|..|..|",
            b".|..|..|",
            b".L--J..|",
            b"....F--J",
            b"........",
            b"........",
        ),
        (
            b"SL.L--JE",
            b".--J..|.",
            b".|....|.",
            b".|.L--J.",
            b".|.|....",
            b".L-J....",
            b"........",
        ),
        (
            b"S..T..E.",
            b"JJ.LJ.|.",
            b".|....|.",
            b".L--7.|.",
            b"....|.|.",
            b"....L-J.",
            b"........",
        ),
        (
            b"SL..L..E",
            b".|..|..|",
            b".|..|..|",
            b".L--J..|",
            b"..-.F--J",
            b"..-.....",
            b"..---...",
        ),
        (
            b"SL.L..E.",
            b"---J..|.",
            b".T..L.|.",
            b".L--JLL.",
            b"..|.--.|",
            b"..L-JJ..",
            b"........",
        ),
    ]

    def __init__(self, ctx=None):
        """Initialize LocoMotionGame and bind optional runtime symbols.

        `ctx` may be a dict or object providing platform helpers; missing
        symbols are left to module globals.
        """
        if ctx is None:
            ctx = {}

        def _g(name):
            """Return symbol `name` from `ctx` or fallback to globals()."""
            if isinstance(ctx, dict):
                return ctx.get(name, globals().get(name))
            return getattr(ctx, name, globals().get(name))

        g = globals()
        try:
            g["display"] = _g("display")
            g["draw_text"] = _g("draw_text")
            g["draw_rectangle"] = _g("draw_rectangle")
            g["display_score_and_time"] = _g("display_score_and_time")
            g["ticks_ms"] = _g("ticks_ms")
            g["ticks_diff"] = _g("ticks_diff")
            g["sleep_ms"] = _g("sleep_ms")
            g["Data"] = _g("Data")
        except Exception:
            pass

        self.level_idx = 0
        self.score = 0
        self._z_down_ms = None
        self._z_armed = False

        self.mode_run = False
        self.cur_x = 0
        self.cur_y = 0

        self.tr_cx = 0
        self.tr_cy = 0
        self.tr_dir = 1
        self.tr_prog = 0
        self.tr_speed = 2
        self.last_tr_px = None
        self.last_tr_py = None

        self.tiles = bytearray(self.RL_W * self.RL_H)

        self._last_input_ms = ticks_ms()
        # compute offsets now that PLAY_HEIGHT exists
        try:
            self.rl_off_x = 0
            self.rl_off_y = (PLAY_HEIGHT - self.RL_PX_H) // 2
        except Exception:
            self.rl_off_x = 0
            self.rl_off_y = 0

        self.load_level(self.level_idx, reset_score=True)

    def _idx(self, x, y):
        """Return linear index for loco-motion grid coordinates (x, y)."""
        return y * self.RL_W + x

    @classmethod
    def _rot_cw(cls, bits):
        """Rotate a 4-bit direction mask clockwise and return new mask."""
        oldN = bits & cls.N
        oldE = bits & cls.E
        oldS = bits & cls.S
        oldW = bits & cls.W
        nb = 0
        if oldW:
            nb |= cls.N
        if oldN:
            nb |= cls.E
        if oldE:
            nb |= cls.S
        if oldS:
            nb |= cls.W
        return nb & 0x0F

    @staticmethod
    def _opp_dir(d):
        """Return the opposite direction for a 0-3 direction index."""
        return (d + 2) & 3

    @classmethod
    def _dir_to_bit(cls, d):
        """Convert a direction index (0-3) to the corresponding bit mask."""
        return (cls.N, cls.E, cls.S, cls.W)[d & 3]

    @classmethod
    def _bit_to_dir(cls, bit):
        """Convert a direction bit mask to a 0-3 direction index."""
        if bit == cls.N:
            return 0
        if bit == cls.E:
            return 1
        if bit == cls.S:
            return 2
        return 3

    @staticmethod
    def _right_dir(d):
        """Return the direction index to the right of `d`."""
        return (d + 1) & 3

    @staticmethod
    def _left_dir(d):
        """Return the direction index to the left of `d`."""
        return (d + 3) & 3

    def _get(self, x, y):
        """Return the tile flags/value at (x, y) or empty if out of bounds."""
        if x < 0 or x >= self.RL_W or y < 0 or y >= self.RL_H:
            return self.TFLAG_EMPTY | 0
        return self.tiles[self._idx(x, y)]

    def _set(self, x, y, v):
        """Set tile flags/value at (x, y) when inside the grid."""
        if 0 <= x < self.RL_W and 0 <= y < self.RL_H:
            self.tiles[self._idx(x, y)] = v & 0x3F

    def load_level(self, level_idx, reset_score=False):
        """Load the specified level and initialize runtime flags."""
        if reset_score:
            self.score = 0
        self.level_idx = level_idx % len(self.LEVELS)
        self.mode_run = False
        self._z_down_ms = None
        self._z_armed = False

        raw = self.LEVELS[self.level_idx]
        sx = sy = 0
        ex = ey = 0

        for y in range(self.RL_H):
            row = raw[y]
            for x in range(self.RL_W):
                ch = row[x]
                bits = 0
                flag = self.TFLAG_NONE

                if ch == ord("S"):
                    flag = self.TFLAG_START
                    bits = self.E
                    sx, sy = x, y
                elif ch == ord("E"):
                    flag = self.TFLAG_END
                    bits = self.W
                    ex, ey = x, y
                elif ch == ord("."):
                    flag = self.TFLAG_EMPTY
                    bits = 0
                else:
                    flag = self.TFLAG_NONE
                    bits = self.SYM_BITS.get(ch, 0)

                self._set(x, y, flag | (bits & 0x0F))

        self.start_x, self.start_y = sx, sy
        self.end_x, self.end_y = ex, ey

        self.cur_x, self.cur_y = sx, sy

        display.clear()
        self._draw_board_full()
        self._draw_cursor()
        self._hud()
        display_score_and_time(self.score, force=True)

    def _tile_rect(self, tx, ty):
        """Return pixel rectangle for loco-motion tile (tx, ty)."""
        x1 = self.rl_off_x + tx * self.RL_TILE
        y1 = self.rl_off_y + ty * self.RL_TILE
        return x1, y1, x1 + self.RL_TILE - 1, y1 + self.RL_TILE - 1

    def _draw_tile(self, tx, ty):
        """Draw a single loco-motion tile including rails and switches."""
        v = self._get(tx, ty)
        flag = v & 0xF0
        bits = v & 0x0F

        x1, y1, x2, y2 = self._tile_rect(tx, ty)
        draw_rectangle(x1, y1, x2, y2, *self.COL_TILE_BG)

        if flag == self.TFLAG_EMPTY and bits == 0:
            sp = display.set_pixel
            sp(x1 + 4, y1 + 4, 0, 0, 10)
            return
        if flag == self.TFLAG_START:
            draw_rectangle(x1 + 1, y1 + 1, x2 - 1, y2 - 1, 0, 40, 0)
        elif flag == self.TFLAG_END:
            draw_rectangle(x1 + 1, y1 + 1, x2 - 1, y2 - 1, 40, 25, 0)

        cx = x1 + (self.RL_TILE // 2)
        cy = y1 + (self.RL_TILE // 2)
        sp = display.set_pixel

        sp(cx, cy, *self.COL_RAIL)

        def rail_to(px, py, col):
            """Draw a rail segment from the tile center to (px, py)."""
            if px == cx:
                sy = 1 if py > cy else -1
                y = cy
                while y != py:
                    sp(cx, y, *col)
                    sp(cx + 1, y, *col)
                    y += sy
                sp(cx, py, *col)
                sp(cx + 1, py, *col)
            else:
                sx = 1 if px > cx else -1
                x = cx
                while x != px:
                    sp(x, cy, *col)
                    sp(x, cy + 1, *col)
                    x += sx
                sp(px, cy, *col)
                sp(px, cy + 1, *col)

        top = y1 + 1
        bot = y2 - 1
        left = x1 + 1
        right = x2 - 1

        if bits & self.N:
            rail_to(cx, top, self.COL_RAIL)
        if bits & self.S:
            rail_to(cx, bot, self.COL_RAIL)
        if bits & self.W:
            rail_to(left, cy, self.COL_RAIL)
        if bits & self.E:
            rail_to(right, cy, self.COL_RAIL)

        if flag == self.TFLAG_START:
            sp(x1 + 1, y1 + 1, *self.COL_START)
            sp(x1 + 2, y1 + 1, *self.COL_START)
            sp(x1 + 1, y1 + 2, *self.COL_START)
        elif flag == self.TFLAG_END:
            sp(x2 - 1, y1 + 1, *self.COL_END)
            sp(x2 - 2, y1 + 1, *self.COL_END)
            sp(x2 - 1, y1 + 2, *self.COL_END)

    def _draw_board_full(self):
        """Draw the entire loco-motion board (all tiles)."""
        for y in range(self.RL_H):
            for x in range(self.RL_W):
                self._draw_tile(x, y)

    def _draw_cursor(self):
        """Draw the selection cursor around the current tile."""
        x1, y1, x2, y2 = self._tile_rect(self.cur_x, self.cur_y)
        draw_rectangle(x1, y1, x2, y1, *self.COL_CURSOR)
        draw_rectangle(x1, y2, x2, y2, *self.COL_CURSOR)
        draw_rectangle(x1, y1, x1, y2, *self.COL_CURSOR)
        draw_rectangle(x2, y1, x2, y2, *self.COL_CURSOR)

    def _repair_cursor_area(self, oldx, oldy):
        """Redraw tiles affected by moving the cursor from (oldx, oldy)."""
        self._draw_tile(oldx, oldy)
        self._draw_tile(self.cur_x, self.cur_y)

    def _hud(self):
        """Draw the HUD below the playfield with level and mode info."""
        try:
            # Draw HUD in bottom area to avoid overlaying the playfield
            by = PLAY_HEIGHT + 1
            draw_text(1, by, "RAIL", 0, 180, 255)
            draw_text(1, by + 8, "LVL " + str(self.level_idx + 1), 255, 255, 255)
            if not self.mode_run:
                draw_text(1, by + 16, "Z=ROT", 180, 180, 180)
                draw_text(1, by + 24, "ZH=RUN", 180, 180, 180)
            else:
                draw_text(1, by + 16, "RUN...", 255, 80, 80)
        except Exception:
            pass

    def _rotate_tile_at_cursor(self):
        """Rotate the tile under the cursor clockwise and update view."""
        x, y = self.cur_x, self.cur_y
        v = self._get(x, y)
        flag = v & 0xF0
        bits = v & 0x0F

        if flag == self.TFLAG_EMPTY and bits == 0:
            return

        bits = self._rot_cw(bits)
        self._set(x, y, flag | bits)
        self._draw_tile(x, y)
        self._draw_cursor()
        self._hud()

    def _find_start_direction(self):
        """Return an initial direction from the start tile's rails."""
        v = self._get(self.start_x, self.start_y)
        bits = v & 0x0F
        for d in (0, 1, 2, 3):
            if bits & self._dir_to_bit(d):
                return d
        return 1

    def _start_run(self):
        """Begin a run: set running mode and initialize train position."""
        self.mode_run = True
        self.tr_cx = self.start_x
        self.tr_cy = self.start_y
        self.tr_dir = self._find_start_direction()
        self.tr_prog = 0
        self.tr_speed = 2 + min(2, self.level_idx)

        self.last_tr_px = None
        self.last_tr_py = None

        self._draw_board_full()
        self._hud()

    def _abort_run(self):
        """Abort a running train and restore editing UI state."""
        self.mode_run = False
        self.last_tr_px = None
        self.last_tr_py = None
        self._draw_board_full()
        self._draw_cursor()
        self._hud()

    def _choose_next_dir(self, bits, incoming_dir, prev_move_dir):
        """Choose the next direction for the train given tile bits.

        Prefers continuing in `prev_move_dir` when available, otherwise
        chooses a sensible alternate using right/left preference.
        """
        inc_bit = self._dir_to_bit(incoming_dir)
        if not (bits & inc_bit):
            return None

        outs = []
        for d in (0, 1, 2, 3):
            b = self._dir_to_bit(d)
            if (bits & b) and (d != incoming_dir):
                outs.append(d)

        if not outs:
            return None

        if prev_move_dir in outs:
            return prev_move_dir

        rd = self._right_dir(prev_move_dir)
        if rd in outs:
            return rd
        ld = self._left_dir(prev_move_dir)
        if ld in outs:
            return ld

        return outs[0]

    def _train_pixel_pos(self):
        """Return the pixel position of the train given its tile and progress."""
        x1, y1, x2, y2 = self._tile_rect(self.tr_cx, self.tr_cy)
        cx = x1 + (self.RL_TILE // 2)
        cy = y1 + (self.RL_TILE // 2)

        p = self.tr_prog
        if self.tr_dir == 0:
            return cx, cy - p
        if self.tr_dir == 2:
            return cx, cy + p
        if self.tr_dir == 3:
            return cx - p, cy
        return cx + p, cy

    def _repair_under_train(self, px, py):
        """Restore the tiles that the train may have overwritten around (px,py)."""
        minx = px - 1
        miny = py - 1
        maxx = px + 2
        maxy = py + 2

        tx0 = (minx - self.rl_off_x) // self.RL_TILE
        ty0 = (miny - self.rl_off_y) // self.RL_TILE
        tx1 = (maxx - self.rl_off_x) // self.RL_TILE
        ty1 = (maxy - self.rl_off_y) // self.RL_TILE

        if tx0 < 0:
            tx0 = 0
        if ty0 < 0:
            ty0 = 0
        if tx1 >= self.RL_W:
            tx1 = self.RL_W - 1
        if ty1 >= self.RL_H:
            ty1 = self.RL_H - 1

        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                self._draw_tile(tx, ty)

    def _draw_train(self, px, py):
        """Draw the train sprite and its shadow at pixel (px, py)."""
        sp = display.set_pixel

        sx = px + 1
        sy = py + 2
        if 0 <= sx < WIDTH and 0 <= sy < PLAY_HEIGHT:
            sp(sx, sy, *self.COL_SHADOW)

        for dy in (0, 1):
            yy = py + dy
            if 0 <= yy < PLAY_HEIGHT:
                for dx in (0, 1):
                    xx = px + dx
                    if 0 <= xx < WIDTH:
                        sp(xx, yy, *self.COL_TRAIN)

    def _step_train(self):
        """Advance the train along the rails one logical step.

        Returns True while the train is still running, False when it
        reaches the end or an error occurs.
        """
        global game_over, global_score

        self.tr_prog += self.tr_speed
        if self.tr_prog < self.RL_TILE:
            return True

        self.tr_prog -= self.RL_TILE

        cur = self._get(self.tr_cx, self.tr_cy)
        cur_bits = cur & 0x0F
        out_bit = self._dir_to_bit(self.tr_dir)
        if not (cur_bits & out_bit):
            return False

        nx = self.tr_cx
        ny = self.tr_cy
        if self.tr_dir == 0:
            ny -= 1
        elif self.tr_dir == 2:
            ny += 1
        elif self.tr_dir == 3:
            nx -= 1
        else:
            nx += 1

        if nx < 0 or nx >= self.RL_W or ny < 0 or ny >= self.RL_H:
            return False

        nxt = self._get(nx, ny)
        nxt_flag = nxt & 0xF0
        nxt_bits = nxt & 0x0F

        incoming = self._opp_dir(self.tr_dir)

        if not (nxt_bits & self._dir_to_bit(incoming)):
            return False

        if nx == self.end_x and ny == self.end_y and (nxt_flag == self.TFLAG_END):
            self.score += 100 + (self.level_idx * 25)
            global_score = self.score

            display.clear()
            draw_text(10, 18, "OK!", 0, 255, 0)
            draw_text(6, 32, "LVL " + str(self.level_idx + 1), 255, 255, 0)
            display_score_and_time(global_score, force=True)
            sleep_ms(1100)

            self.load_level(self.level_idx + 1, reset_score=False)
            return None

        next_dir = self._choose_next_dir(nxt_bits, incoming, self.tr_dir)
        if next_dir is None:
            return False

        self.tr_cx = nx
        self.tr_cy = ny
        self.tr_dir = next_dir
        return True

    def _fail_derail(self):
        """Handle a derail failure: display message and abort run."""
        global game_over, global_score
        global_score = self.score

        display.clear()
        draw_text(6, 18, "DERAIL", 255, 0, 0)
        display_score_and_time(global_score, force=True)
        sleep_ms(900)

        self._abort_run()

    def main_loop(self, joystick):
        """Main loop for LocoMotion: handle editing and running modes."""
        global game_over, global_score
        game_over = False
        global_score = 0

        self.load_level(self.level_idx, reset_score=False)
        self._last_input_ms = ticks_ms()
        last_frame = ticks_ms()

        while True:
            c_button, z_button = joystick.nunchuck.buttons()
            if c_button:
                return
            if game_over:
                return

            now = ticks_ms()

            if z_button:
                if self._z_down_ms is None:
                    self._z_down_ms = now
                    self._z_armed = True
                else:
                    if (
                        self._z_armed
                        and ticks_diff(now, self._z_down_ms) >= self.Z_LONG_MS
                    ):
                        self._z_armed = False
                        if not self.mode_run:
                            self._start_run()
                        else:
                            self._abort_run()
            else:
                if self._z_down_ms is not None:
                    held = ticks_diff(now, self._z_down_ms)
                    if held < self.Z_LONG_MS and self._z_armed and (not self.mode_run):
                        self._rotate_tile_at_cursor()
                    self._z_down_ms = None
                    self._z_armed = False

            if self.mode_run:
                if ticks_diff(now, last_frame) < self.FRAME_MS_RUN:
                    sleep_ms(2)
                    continue
                last_frame = now

                if self.last_tr_px is not None:
                    self._repair_under_train(self.last_tr_px, self.last_tr_py)

                st = self._step_train()
                if st is None:
                    last_frame = ticks_ms()
                    continue
                if st is False:
                    self._fail_derail()
                    last_frame = ticks_ms()
                    continue

                px, py = self._train_pixel_pos()
                self._draw_train(px, py)
                self.last_tr_px, self.last_tr_py = px, py

                self._hud()
                display_score_and_time(self.score)
                global_score = self.score

                if (now & 0x3FF) == 0:
                    gc.collect()

                continue

            if ticks_diff(now, self._last_input_ms) < self.EDIT_INPUT_MS:
                sleep_ms(5)
                continue

            d = joystick.read_direction(
                [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
            )
            if not d:
                sleep_ms(5)
                continue

            ox, oy = self.cur_x, self.cur_y
            if d == JOYSTICK_LEFT and self.cur_x > 0:
                self.cur_x -= 1
            elif d == JOYSTICK_RIGHT and self.cur_x < self.RL_W - 1:
                self.cur_x += 1
            elif d == JOYSTICK_UP and self.cur_y > 0:
                self.cur_y -= 1
            elif d == JOYSTICK_DOWN and self.cur_y < self.RL_H - 1:
                self.cur_y += 1

            if (ox, oy) != (self.cur_x, self.cur_y):
                self._repair_cursor_area(ox, oy)
                self._draw_cursor()
                self._hud()

            self._last_input_ms = now
            maybe_collect(120)

    async def main_loop_async(self, joystick):
        """Async/cooperative version of the LocoMotion loop for browsers.

        Uses `await asyncio.sleep()` instead of blocking `sleep_ms()` so the
        event loop remains responsive in WASM/pygbag environments.
        """
        import asyncio

        global game_over, global_score
        game_over = False
        global_score = 0

        self.load_level(self.level_idx, reset_score=False)
        self._last_input_ms = ticks_ms()
        last_frame = ticks_ms()

        while True:
            c_button, z_button = joystick.nunchuck.buttons()
            if c_button:
                return
            if game_over:
                return

            now = ticks_ms()

            if z_button:
                if self._z_down_ms is None:
                    self._z_down_ms = now
                    self._z_armed = True
                else:
                    if (
                        self._z_armed
                        and ticks_diff(now, self._z_down_ms) >= self.Z_LONG_MS
                    ):
                        self._z_armed = False
                        if not self.mode_run:
                            self._start_run()
                        else:
                            self._abort_run()
            else:
                if self._z_down_ms is not None:
                    held = ticks_diff(now, self._z_down_ms)
                    if held < self.Z_LONG_MS and self._z_armed and (not self.mode_run):
                        self._rotate_tile_at_cursor()
                    self._z_down_ms = None
                    self._z_armed = False

            if self.mode_run:
                if ticks_diff(now, last_frame) < self.FRAME_MS_RUN:
                    await asyncio.sleep(0.002)
                    continue
                last_frame = now

                if self.last_tr_px is not None:
                    self._repair_under_train(self.last_tr_px, self.last_tr_py)

                st = self._step_train()
                if st is None:
                    last_frame = ticks_ms()
                    continue
                if st is False:
                    self._fail_derail()
                    last_frame = ticks_ms()
                    continue

                px, py = self._train_pixel_pos()
                self._draw_train(px, py)
                self.last_tr_px, self.last_tr_py = px, py

                self._hud()
                display_score_and_time(self.score)
                global_score = self.score

                if (now & 0x3FF) == 0:
                    try:
                        gc.collect()
                    except Exception:
                        pass

                continue

            if ticks_diff(now, self._last_input_ms) < self.EDIT_INPUT_MS:
                await asyncio.sleep(0.005)
                continue

            d = joystick.read_direction(
                [
                    JOYSTICK_UP,
                    JOYSTICK_DOWN,
                    JOYSTICK_LEFT,
                    JOYSTICK_RIGHT,
                ]
            )
            if not d:
                await asyncio.sleep(0.005)
                continue

            ox, oy = self.cur_x, self.cur_y
            if d == JOYSTICK_LEFT and self.cur_x > 0:
                self.cur_x -= 1
            elif d == JOYSTICK_RIGHT and self.cur_x < self.RL_W - 1:
                self.cur_x += 1
            elif d == JOYSTICK_UP and self.cur_y > 0:
                self.cur_y -= 1
            elif d == JOYSTICK_DOWN and self.cur_y < self.RL_H - 1:
                self.cur_y += 1

            if (ox, oy) != (self.cur_x, self.cur_y):
                self._repair_cursor_area(ox, oy)
                self._draw_cursor()
                self._hud()

            self._last_input_ms = now
            try:
                maybe_collect(120)
            except Exception:
                pass


# ---- Reversi (Othello) ----
try:
    from micropython import const
except ImportError:

    def const(x):
        """Fallback `const` for non-MicroPython environments."""
        return x

# Othello constants (moved into class as attributes)
# BOARD_OFF_* depend on runtime WIDTH/PLAY_HEIGHT; computed per-instance


class OthelloGame:
    """
    Othello/Reversi board game implementation with simple AI.

    Manages moves, flipping logic, and score calculation.
    """

    BOARD_SIZE = const(8)
    CELL_SIZE = const(6)
    BOARD_W = BOARD_SIZE * CELL_SIZE
    BOARD_H = BOARD_SIZE * CELL_SIZE
    EMPTY = const(0)
    P1 = const(1)
    P2 = const(2)

    def __init__(self, ctx=None):
        """Initialize Othello game and bind optional runtime helpers."""
        if ctx is None:
            ctx = {}

        def _g(name):
            """Return a runtime symbol from `ctx` or fallback to globals()."""
            if isinstance(ctx, dict):
                return ctx.get(name, globals().get(name))
            return getattr(ctx, name, globals().get(name))

        g = globals()
        try:
            g["display"] = _g("display")
            g["draw_text"] = _g("draw_text")
            g["draw_rectangle"] = _g("draw_rectangle")
            g["display_score_and_time"] = _g("display_score_and_time")
            g["ticks_ms"] = _g("ticks_ms")
            g["ticks_diff"] = _g("ticks_diff")
            g["sleep_ms"] = _g("sleep_ms")
            g["Data"] = _g("Data")
        except Exception:
            pass

        self.board = [[self.EMPTY] * self.BOARD_SIZE for _ in range(self.BOARD_SIZE)]
        self.cur_x = 3
        self.cur_y = 3
        self.current_player = self.P1
        self.score = 0
        self.game_finished = False
        try:
            self.board_off_x = (WIDTH - self.BOARD_W) // 2
            self.board_off_y = (PLAY_HEIGHT - self.BOARD_H) // 2
        except Exception:
            self.board_off_x = 0
            self.board_off_y = 0

    def reset(self):
        """Reset the Othello board to the starting position."""
        for y in range(self.BOARD_SIZE):
            row = self.board[y]
            for x in range(self.BOARD_SIZE):
                row[x] = self.EMPTY

        mid = self.BOARD_SIZE // 2
        self.board[mid - 1][mid - 1] = self.P2
        self.board[mid][mid] = self.P2
        self.board[mid - 1][mid] = self.P1
        self.board[mid][mid - 1] = self.P1

        self.cur_x = mid
        self.cur_y = mid
        self.current_player = self.P1
        self.game_finished = False
        self.score = 0

        display.clear()
        self.render(full=True)
        display_score_and_time(0, force=True)

    def inside(self, x, y):
        """Return True when (x, y) lies inside the board bounds."""
        return 0 <= x < self.BOARD_SIZE and 0 <= y < self.BOARD_SIZE

    def directions(self):
        """Return the eight direction vectors used for flipping logic."""
        return (
            (-1, -1),
            (0, -1),
            (1, -1),
            (-1, 0),
            (1, 0),
            (-1, 1),
            (0, 1),
            (1, 1),
        )

    def _captures_in_dir(self, x, y, dx, dy, player):
        """Return a tuple of positions captured in direction (dx,dy).

        Scans from (x+dx,y+dy) outward and returns captured enemy
        positions when terminated by a friendly piece.
        """
        enemy = self.P1 if player == self.P2 else self.P2
        cx = x + dx
        cy = y + dy
        captured = []

        if not self.inside(cx, cy):
            return ()

        if self.board[cy][cx] != enemy:
            return ()

        while True:
            captured.append((cx, cy))
            cx += dx
            cy += dy
            if not self.inside(cx, cy):
                return ()
            v = self.board[cy][cx]
            if v == self.EMPTY:
                return ()
            if v == player:
                return tuple(captured)

    def valid_moves_for(self, player):
        """Return a list of valid moves (x,y) for `player`."""
        moves = []
        for y in range(self.BOARD_SIZE):
            for x in range(self.BOARD_SIZE):
                if self.board[y][x] != self.EMPTY:
                    continue
                total_caps = 0
                for dx, dy in self.directions():
                    caps = self._captures_in_dir(x, y, dx, dy, player)
                    total_caps += len(caps)
                if total_caps > 0:
                    moves.append((x, y, total_caps))
        return moves

    def is_valid_move(self, x, y, player):
        """Return True when placing at (x,y) is a legal move for `player`."""
        if not self.inside(x, y):
            return False
        if self.board[y][x] != self.EMPTY:
            return False
        for dx, dy in self.directions():
            caps = self._captures_in_dir(x, y, dx, dy, player)
            if caps:
                return True
        return False

    def apply_move(self, x, y, player):
        """Apply a move for `player` at (x,y) and flip captured discs."""
        self.board[y][x] = player
        total_flipped = 0
        for dx, dy in self.directions():
            caps = self._captures_in_dir(x, y, dx, dy, player)
            if caps:
                for cx, cy in caps:
                    self.board[cy][cx] = player
                total_flipped += len(caps)
        return total_flipped

    def count_discs(self):
        """Count discs for both players and return (p1, p2)."""
        p1 = 0
        p2 = 0
        for y in range(self.BOARD_SIZE):
            row = self.board[y]
            for x in range(self.BOARD_SIZE):
                if row[x] == self.P1:
                    p1 += 1
                elif row[x] == self.P2:
                    p2 += 1
        return p1, p2

    def cpu_move(self):
        """Simple CPU move: pick the move with the highest immediate gain."""
        moves = self.valid_moves_for(self.P2)
        if not moves:
            return False

        best = None
        best_score = -1
        for x, y, gain in moves:
            if gain > best_score:
                best_score = gain
                best = (x, y)

        if best is None:
            return False

        bx, by = best
        self.apply_move(bx, by, self.P2)
        return True

    def _draw_cell(self, x, y):
        """Draw a single board cell (empty or player disc)."""
        v = self.board[y][x]
        x1 = self.board_off_x + x * self.CELL_SIZE
        y1 = self.board_off_y + y * self.CELL_SIZE
        x2 = x1 + self.CELL_SIZE - 1
        y2 = y1 + self.CELL_SIZE - 1

        draw_rectangle(x1, y1, x2, y2, 0, 90, 0)

        if v == self.P1:
            cx = x1 + self.CELL_SIZE // 2
            cy = y1 + self.CELL_SIZE // 2
            display.set_pixel(cx, cy, 0, 0, 0)
            display.set_pixel(cx - 1, cy, 0, 0, 0)
            display.set_pixel(cx, cy - 1, 0, 0, 0)
            display.set_pixel(cx - 1, cy - 1, 0, 0, 0)
        elif v == self.P2:
            cx = x1 + self.CELL_SIZE // 2
            cy = y1 + self.CELL_SIZE // 2
            display.set_pixel(cx, cy, 255, 255, 255)
            display.set_pixel(cx - 1, cy, 255, 255, 255)
            display.set_pixel(cx, cy - 1, 255, 255, 255)
            display.set_pixel(cx - 1, cy - 1, 255, 255, 255)

    def render(self, full=False):
        """Render the Othello board and HUD; `full` forces a full redraw."""
        if full:
            for y in range(self.BOARD_SIZE):
                for x in range(self.BOARD_SIZE):
                    self._draw_cell(x, y)
        else:
            for y in range(self.BOARD_SIZE):
                for x in range(self.BOARD_SIZE):
                    self._draw_cell(x, y)

        for x in range(self.BOARD_SIZE + 1):
            px = self.board_off_x + x * self.CELL_SIZE
            draw_rectangle(
                px, self.board_off_y, px, self.board_off_y + self.BOARD_H - 1, 0, 60, 0
            )
        for y in range(self.BOARD_SIZE + 1):
            py = self.board_off_y + y * self.CELL_SIZE
            draw_rectangle(
                self.board_off_x, py, self.board_off_x + self.BOARD_W - 1, py, 0, 60, 0
            )

        cx1 = self.board_off_x + self.cur_x * self.CELL_SIZE
        cy1 = self.board_off_y + self.cur_y * self.CELL_SIZE
        cx2 = cx1 + self.CELL_SIZE - 1
        cy2 = cy1 + self.CELL_SIZE - 1
        draw_rectangle(cx1, cy1, cx2, cy1, 255, 255, 0)
        draw_rectangle(cx1, cy2, cx2, cy2, 255, 255, 0)
        draw_rectangle(cx1, cy1, cx1, cy2, 255, 255, 0)
        draw_rectangle(cx2, cy1, cx2, cy2, 255, 255, 0)

        p1, p2 = self.count_discs()
        self.score = p1 - p2
        display_score_and_time(self.score)

    def check_game_end(self):
        """Return True when neither player has a valid move (game over)."""
        moves_p1 = self.valid_moves_for(self.P1)
        moves_p2 = self.valid_moves_for(self.P2)
        if moves_p1 or moves_p2:
            return False

        self.game_finished = True
        p1, p2 = self.count_discs()
        self.score = p1 - p2
        return True

    def main_loop(self, joystick):
        """Main loop for Othello: handle input, apply moves, and update."""
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()

        frame_ms = 80
        last_frame = ticks_ms()

        while True:
            c_button, z_button = joystick.nunchuck.buttons()
            if c_button:
                return
            if game_over:
                return

            now = ticks_ms()
            if ticks_diff(now, last_frame) < frame_ms:
                sleep_ms(5)
                continue
            last_frame = now

            if self.game_finished:
                display.clear()
                p1, p2 = self.count_discs()
                txt = "WIN" if p1 > p2 else ("LOSE" if p1 < p2 else "DRAW")
                draw_text(8, 18, txt, 255, 255, 255)
                display_score_and_time(self.score, force=True)
                global_score = self.score
                sleep_ms(1500)
                game_over = True
                return

            if self.current_player == self.P1:
                d = joystick.read_direction(
                    [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
                )

                if d == JOYSTICK_LEFT and self.cur_x > 0:
                    self.cur_x -= 1
                elif d == JOYSTICK_RIGHT and self.cur_x < self.BOARD_SIZE - 1:
                    self.cur_x += 1
                elif d == JOYSTICK_UP and self.cur_y > 0:
                    self.cur_y -= 1
                elif d == JOYSTICK_DOWN and self.cur_y < self.BOARD_SIZE - 1:
                    self.cur_y += 1

                if z_button and self.is_valid_move(self.cur_x, self.cur_y, self.P1):
                    self.apply_move(self.cur_x, self.cur_y, self.P1)
                    self.current_player = self.P2

            else:
                self.cpu_move()
                self.current_player = self.P1
                sleep_ms(120)

            if not self.valid_moves_for(self.current_player):
                if self.check_game_end():
                    continue
                self.current_player = (
                    self.P1 if self.current_player == self.P2 else self.P2
                )

            self.render(full=True)
            global_score = self.score

    async def main_loop_async(self, joystick):
        """Async/cooperative Othello loop for browsers (pygbag).

        Mirrors `main_loop` but yields with `await asyncio.sleep()` to keep
        the event loop responsive in WASM environments.
        """
        import asyncio

        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()

        frame_ms = 80
        last_frame = ticks_ms()

        while True:
            c_button, z_button = joystick.nunchuck.buttons()
            if c_button:
                return
            if game_over:
                return

            now = ticks_ms()
            if ticks_diff(now, last_frame) < frame_ms:
                await asyncio.sleep(0.005)
                continue
            last_frame = now

            if self.game_finished:
                display.clear()
                p1, p2 = self.count_discs()
                txt = "WIN" if p1 > p2 else ("LOSE" if p1 < p2 else "DRAW")
                draw_text(8, 18, txt, 255, 255, 255)
                display_score_and_time(self.score, force=True)
                global_score = self.score
                await asyncio.sleep(1.5)
                game_over = True
                return

            if self.current_player == self.P1:
                d = joystick.read_direction(
                    [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
                )

                if d == JOYSTICK_LEFT and self.cur_x > 0:
                    self.cur_x -= 1
                elif d == JOYSTICK_RIGHT and self.cur_x < self.BOARD_SIZE - 1:
                    self.cur_x += 1
                elif d == JOYSTICK_UP and self.cur_y > 0:
                    self.cur_y -= 1
                elif d == JOYSTICK_DOWN and self.cur_y < self.BOARD_SIZE - 1:
                    self.cur_y += 1

                if z_button and self.is_valid_move(self.cur_x, self.cur_y, self.P1):
                    self.apply_move(self.cur_x, self.cur_y, self.P1)
                    self.current_player = self.P2

            else:
                self.cpu_move()
                self.current_player = self.P1
                await asyncio.sleep(0.12)

            if not self.valid_moves_for(self.current_player):
                if self.check_game_end():
                    continue
                self.current_player = (
                    self.P1 if self.current_player == self.P2 else self.P2
                )

            self.render(full=True)
            global_score = self.score


# ---- Sokoban ----


class SokobanGame:
    """
    Classic Sokoban crate-pushing puzzles on a small grid.

    Tracks player position, box movement, and level completion.
    """

    # --- Sokoban constants & levels (kept as class attributes) ---
    SOK_TILE = const(4)
    SOK_W = const(16)
    SOK_H = const(14)

    # Map encoding (bytes): '#' wall, '.' floor, 'G' goal, 'B' box,
    # '*' box on goal, 'P' player, '+' player on goal
    SOK_LEVELS = [
        (
            b"################",
            b"#..............#",
            b"#....#####.....#",
            b"#....#..P#.....#",
            b"#..###.B.#.....#",
            b"#..#..BBB#.....#",
            b"#..#...GG#.....#",
            b"#..###.GG#.....#",
            b"#....#...#.....#",
            b"#....#####.....#",
            b"#..............#",
            b"#..............#",
            b"#..............#",
            b"################",
        ),
        (
            b"################",
            b"#..............#",
            b"#..#####.......#",
            b"#..#...#.......#",
            b"#..#.B.#..GG...#",
            b"#..#.BB#..GG...#",
            b"#..#..P........#",
            b"#..#####.......#",
            b"#..............#",
            b"#..............#",
            b"#..............#",
            b"#..............#",
            b"#..............#",
            b"################",
        ),
        (
            b"################",
            b"#..............#",
            b"#..######..GG..#",
            b"#..#....#..GG..#",
            b"#..#.BB.#......#",
            b"#..#..B.#..###.#",
            b"#..#..P....#...#",
            b"#..######..#...#",
            b"#..........#...#",
            b"#..#############",
            b"#..............#",
            b"#..............#",
            b"#..............#",
            b"################",
        ),
        (
            b"################",
            b"#..............#",
            b"#..............#",
            b"#....#####.....#",
            b"#..###...#..GG.#",
            b"#..#...B.#.....#",
            b"#..#..B..#.....#",
            b"#..#..P..#####.#",
            b"#..#......#....##",
            b"#..####.####...#",
            b"#..............#",
            b"#..............#",
            b"#..............#",
            b"################",
        ),
    ]

    # Colors (tweak to taste)
    COL_BG = (0, 0, 0)
    COL_WALL = (0, 0, 140)
    COL_FLOOR = (0, 0, 0)
    COL_GOAL = (0, 120, 0)
    COL_BOX = (220, 140, 0)
    COL_BOXG = (255, 220, 0)
    COL_PLYR = (255, 255, 255)
    COL_PLYRG = (180, 255, 180)
    COL_GRID = (0, 35, 0)

    def __init__(self, ctx=None):
        """Initialize SokobanGame and bind optional runtime helpers.

        `ctx` may provide platform-specific functions; missing symbols
        fall back to module globals. Initializes level state and offsets.
        """
        if ctx is None:
            ctx = {}

        def _g(name):
            """Return a runtime symbol from `ctx` or fallback to globals()."""
            if isinstance(ctx, dict):
                return ctx.get(name, globals().get(name))
            return getattr(ctx, name, globals().get(name))

        g = globals()
        try:
            g["display"] = _g("display")
            g["draw_text"] = _g("draw_text")
            g["draw_rectangle"] = _g("draw_rectangle")
            g["display_score_and_time"] = _g("display_score_and_time")
            g["ticks_ms"] = _g("ticks_ms")
            g["ticks_diff"] = _g("ticks_diff")
            g["sleep_ms"] = _g("sleep_ms")
            g["Data"] = _g("Data")
        except Exception:
            pass

        self.level_idx = 0
        self.moves = 0
        self.undo = []
        self._last_input_ms = 0
        self.input_ms = 120
        try:
            self.sok_off_x = 0
            self.sok_off_y = (PLAY_HEIGHT - (self.SOK_H * self.SOK_TILE)) // 2
        except Exception:
            self.sok_off_x = 0
            self.sok_off_y = 0
        self.reset_level(reset_all=True)

    def _idx(self, x, y):
        """Return linear index for the Sokoban level grid at (x, y)."""
        return y * self.SOK_W + x

    def _inside(self, x, y):
        """Return True when (x, y) lies within the Sokoban map bounds."""
        return 0 <= x < self.SOK_W and 0 <= y < self.SOK_H

    def reset_level(self, reset_all=False):
        """Load and initialize the current Sokoban level.

        When `reset_all` is True, resets `level_idx` to zero as well.
        Initializes walls, goals, boxes and player position arrays.
        """
        if reset_all:
            self.level_idx = 0
        self.moves = 0
        self.undo = []

        raw = self.SOK_LEVELS[self.level_idx % len(self.SOK_LEVELS)]
        self.walls = bytearray(self.SOK_W * self.SOK_H)
        self.goals = bytearray(self.SOK_W * self.SOK_H)
        self.boxes = bytearray(self.SOK_W * self.SOK_H)

        px = py = 1

        for y in range(self.SOK_H):
            row = raw[y]
            for x in range(self.SOK_W):
                ch = row[x]
                i = self._idx(x, y)
                if ch == 35:
                    self.walls[i] = 1
                elif ch == ord("G"):
                    self.goals[i] = 1
                elif ch == ord("B"):
                    self.boxes[i] = 1
                elif ch == ord("*"):
                    self.goals[i] = 1
                    self.boxes[i] = 1
                elif ch == ord("P"):
                    px, py = x, y
                elif ch == ord("+"):
                    px, py = x, y
                    self.goals[i] = 1

        self.px, self.py = px, py
        display.clear()
        self.render(full=True)
        display_score_and_time(self.moves, force=True)

    def _is_wall(self, x, y):
        """Return True when the tile at (x,y) is a wall."""
        return self.walls[self._idx(x, y)] != 0

    def _has_box(self, x, y):
        """Return True when a box occupies tile (x,y)."""
        return self.boxes[self._idx(x, y)] != 0

    def _set_box(self, x, y, v):
        """Set or clear a box at tile (x,y) depending on truthiness of `v`."""
        self.boxes[self._idx(x, y)] = 1 if v else 0

    def _is_goal(self, x, y):
        """Return True when the tile at (x,y) is a goal target."""
        return self.goals[self._idx(x, y)] != 0

    def _try_move(self, dx, dy):
        """Attempt to move the player by (dx,dy); push boxes if possible.

        Returns True on successful move (and updates state), False
        when movement is blocked by walls or immovable boxes.
        """
        x0, y0 = self.px, self.py
        x1, y1 = x0 + dx, y0 + dy
        if not self._inside(x1, y1) or self._is_wall(x1, y1):
            return False

        if self._has_box(x1, y1):
            x2, y2 = x1 + dx, y1 + dy
            if (
                not self._inside(x2, y2)
                or self._is_wall(x2, y2)
                or self._has_box(x2, y2)
            ):
                return False
            self._set_box(x1, y1, 0)
            self._set_box(x2, y2, 1)
            box_moved = 1
            rec = (x0, y0, x1, y1, box_moved, x1, y1, x2, y2)
        else:
            box_moved = 0
            rec = (x0, y0, x1, y1, box_moved, 0, 0, 0, 0)

        self.px, self.py = x1, y1
        self.moves += 1

        if len(self.undo) >= 120:
            self.undo.pop(0)
        self.undo.append(rec)
        return True

    def _undo(self):
        """Undo the last player move, restoring box positions if needed."""
        if not self.undo:
            return False
        rec = self.undo.pop()
        x0, y0, x1, y1, box_moved, bx0, by0, bx1, by1 = rec

        self.px, self.py = x0, y0

        if box_moved:
            self._set_box(bx1, by1, 0)
            self._set_box(bx0, by0, 1)

        if self.moves > 0:
            self.moves -= 1
        return True

    def _is_solved(self):
        """Return True when all boxes are on goal tiles (level solved)."""
        b = self.boxes
        g = self.goals
        for i in range(self.SOK_W * self.SOK_H):
            if b[i] and not g[i]:
                return False
        return True

    def _draw_tile(self, x, y):
        """Draw a single Sokoban tile including walls, goals and boxes."""
        i = self._idx(x, y)
        x1 = self.sok_off_x + x * self.SOK_TILE
        y1 = self.sok_off_y + y * self.SOK_TILE
        x2 = x1 + self.SOK_TILE - 1
        y2 = y1 + self.SOK_TILE - 1

        if self.walls[i]:
            draw_rectangle(x1, y1, x2, y2, *self.COL_WALL)
            return

        draw_rectangle(x1, y1, x2, y2, *self.COL_FLOOR)

        if self.goals[i]:
            draw_rectangle(x1 + 1, y1 + 1, x2 - 1, y2 - 1, *self.COL_GOAL)

        if self.boxes[i]:
            col = self.COL_BOXG if self.goals[i] else self.COL_BOX
            draw_rectangle(x1 + 1, y1 + 1, x2 - 1, y2 - 1, *col)

    def _draw_player(self):
        """Draw the player at its current tile position with goal highlight."""
        x = self.sok_off_x + self.px * self.SOK_TILE
        y = self.sok_off_y + self.py * self.SOK_TILE
        col = self.COL_PLYRG if self._is_goal(self.px, self.py) else self.COL_PLYR
        draw_rectangle(x + 1, y + 1, x + 2, y + 2, *col)

    def render(self, full=False):
        """Render Sokoban level and HUD; `full` forces full redraw."""
        for y in range(self.SOK_H):
            for x in range(self.SOK_W):
                self._draw_tile(x, y)
        self._draw_player()
        display_score_and_time(self.moves)

    def main_loop(self, joystick):
        """Main loop for Sokoban: handle input, moves, undo, and rendering."""
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset_level(reset_all=True)
        self._last_input_ms = ticks_ms()

        while True:
            c_button, z_button = joystick.nunchuck.buttons()
            if c_button:
                return
            if game_over:
                return

            now = ticks_ms()

            if z_button and ticks_diff(now, self._last_input_ms) >= self.input_ms:
                if self._undo():
                    self.render(full=True)
                self._last_input_ms = now
                maybe_collect(120)
                continue

            if ticks_diff(now, self._last_input_ms) < self.input_ms:
                sleep_ms(5)
                continue

            d = joystick.read_direction(
                [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
            )
            if not d:
                sleep_ms(5)
                continue

            dx = dy = 0
            if d == JOYSTICK_LEFT:
                dx = -1
            elif d == JOYSTICK_RIGHT:
                dx = 1
            elif d == JOYSTICK_UP:
                dy = -1
            elif d == JOYSTICK_DOWN:
                dy = 1

            moved = False
            if dx or dy:
                moved = self._try_move(dx, dy)

            if moved:
                self.render(full=True)
                self._last_input_ms = now

                if self._is_solved():
                    global_score = self.moves
                    display.clear()
                    draw_text(4, 16, "SOLVED", 0, 255, 0)
                    draw_text(
                        4,
                        30,
                        "LVL " + str((self.level_idx % len(self.SOK_LEVELS)) + 1),
                        255,
                        255,
                        0,
                    )
                    display_score_and_time(self.moves, force=True)
                    sleep_ms(1300)

                    self.level_idx = (self.level_idx + 1) % len(self.SOK_LEVELS)
                    self.reset_level(reset_all=False)

            else:
                self._last_input_ms = now - (self.input_ms // 2)

            maybe_collect(140)

    async def main_loop_async(self, joystick):
        """Async/cooperative Sokoban loop for browsers (pygbag).

        Mirrors `main_loop` but yields with `await asyncio.sleep()` instead of
        blocking `sleep_ms()` so the event loop remains responsive.
        """
        import asyncio

        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset_level(reset_all=True)
        self._last_input_ms = ticks_ms()

        while True:
            c_button, z_button = joystick.nunchuck.buttons()
            if c_button:
                return
            if game_over:
                return

            now = ticks_ms()

            if z_button and ticks_diff(now, self._last_input_ms) >= self.input_ms:
                if self._undo():
                    self.render(full=True)
                self._last_input_ms = now
                try:
                    maybe_collect(120)
                except Exception:
                    pass
                continue

            if ticks_diff(now, self._last_input_ms) < self.input_ms:
                await asyncio.sleep(0.005)
                continue

            d = joystick.read_direction(
                [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
            )
            if not d:
                await asyncio.sleep(0.005)
                continue

            dx = dy = 0
            if d == JOYSTICK_LEFT:
                dx = -1
            elif d == JOYSTICK_RIGHT:
                dx = 1
            elif d == JOYSTICK_UP:
                dy = -1
            elif d == JOYSTICK_DOWN:
                dy = 1

            moved = False
            if dx or dy:
                moved = self._try_move(dx, dy)

            if moved:
                self.render(full=True)
                self._last_input_ms = now

                if self._is_solved():
                    global_score = self.moves
                    display.clear()
                    draw_text(4, 16, "SOLVED", 0, 255, 0)
                    draw_text(
                        4,
                        30,
                        "LVL " + str((self.level_idx % len(self.SOK_LEVELS)) + 1),
                        255,
                        255,
                        0,
                    )
                    display_score_and_time(self.moves, force=True)
                    await asyncio.sleep(1.3)

                    self.level_idx = (self.level_idx + 1) % len(self.SOK_LEVELS)
                    self.reset_level(reset_all=False)

            else:
                self._last_input_ms = now - (self.input_ms // 2)

            try:
                maybe_collect(140)
            except Exception:
                pass


class DemosGame:
    """Zero-player demos: simple animations and cellular automata."""

    def __init__(self):
        """Initialize demo list, timing and reset internal demo state."""
        # TRON removed; new demos added: ANTS, FLOOD, FIRE
        self.demos = ["SNAKE", "LIFE", "ANTS", "FLOOD", "FIRE"]
        self.idx = 0
        self._init = False
        self._last_move = ticks_ms()
        self._move_delay = 180
        self._reset_demo_state()

    def _reset_demo_state(self):
        """Reset internal state used by the demos (LIFE/ANTS/FLOOD/FIRE)."""
        # shared
        self._init = False
        self._frame = 0
        self._demo_w = WIDTH
        self._demo_h = HEIGHT

        # LIFE
        self._life_w = 64
        self._life_h = 64
        self._life_cur = None
        self._life_nxt = None
        self._life_prev = None

        # ANTS (multi Langton ants)
        self._ants_w = WIDTH
        self._ants_h = HEIGHT
        self._ants_cells = None  # bytearray: 0 dead, 1 alive
        self._ants = []
        self._ants_prev = []
        self._ants_changed = []

        # FLOOD (flood fill through random maze)
        self._flood_w = WIDTH
        self._flood_h = HEIGHT
        # values: 0 empty, 1 line, 2 floodfill, 3 enemy, 4 queued, 5 line
        self._flood = None
        self._flood_vis = None
        self._flood_q = None  # bytearray queue of packed (y<<8)|x
        self._flood_q_head = 0
        self._flood_q_tail = 0
        self._flood_steps = 0
        self._flood_max_steps = 8000
        self._flood_sleep_ms = 20

        # FIRE (doom-fire)
        self._fire_w = WIDTH
        self._fire_h = HEIGHT
        self._fire = None
        self._fire_prev = None

        # SNAKE
        self._snake = [(WIDTH // 2, HEIGHT // 2)]
        self._snake_length = 3
        self._snake_dir = "UP"
        self._snake_score = 0
        self._snake_target = (WIDTH // 2, HEIGHT // 2)
        self._snake_green_targets = []  # list of (x,y,lifespan)
        self._snake_step_counter = 0
        self._snake_step_counter2 = 0

    @staticmethod
    def _shuffle_in_place(seq):
        """Shuffle a sequence in place using Fisher–Yates algorithm."""
        # Fisher-Yates; avoids relying on random.shuffle (not present on some MicroPython builds)
        n = len(seq)
        for i in range(n - 1, 0, -1):
            j = random.randint(0, i)
            seq[i], seq[j] = seq[j], seq[i]

    def _life_step(self, w, h, cur, nxt):
        """Advance one step of Conway's Game of Life on grid (w,h).

        `cur` and `nxt` are bytearrays of size w*h; this updates `nxt`.
        """
        for y in range(h):
            ym1 = (y - 1) % h
            yp1 = (y + 1) % h
            row = y * w
            rowm1 = ym1 * w
            rowp1 = yp1 * w
            for x in range(w):
                xm1 = (x - 1) % w
                xp1 = (x + 1) % w
                i = row + x
                n = (
                    cur[rowm1 + xm1]
                    + cur[rowm1 + x]
                    + cur[rowm1 + xp1]
                    + cur[row + xm1]
                    + cur[row + xp1]
                    + cur[rowp1 + xm1]
                    + cur[rowp1 + x]
                    + cur[rowp1 + xp1]
                )
                if cur[i]:
                    nxt[i] = 1 if (n == 2 or n == 3) else 0
                else:
                    nxt[i] = 1 if (n == 3) else 0

    def _life_draw_diffs(self, w, h, cur, prev):
        """Draw differences between current and previous LIFE generations."""
        # diff-draw
        for y in range(h):
            row = y * w
            for x in range(w):
                i = row + x
                v = cur[i]
                if v == prev[i]:
                    continue
                prev[i] = v
                if v:
                    r, g, b = 0, 180, 0
                else:
                    r, g, b = 0, 0, 0
                display.set_pixel(x, y, r, g, b)

    def _ants_init(self):
        """Initialize Langton-ants demo state and color palettes."""
        # Match original "game_of_ants" look:
        # - dead: black
        # - alive base: (155,155,155)
        # - alive trail: dim ant color
        # - ants: bright unique colors
        w = self._ants_w
        h = self._ants_h

        self._ants_cells = bytearray(w * h)
        for i in range(w * h):
            self._ants_cells[i] = 1 if random.randint(0, 7) == 0 else 0

        # init ants: [x,y,dir,r,g,b]
        self._ants = []
        self._ants_prev = []
        self._ants_changed = []
        n = 8
        for _ in range(n):
            ax = random.randint(0, w - 1)
            ay = random.randint(0, h - 1)
            ad = random.randint(0, 3)
            r, g, b = hsb_to_rgb(random.randint(0, 360), 1, 1)
            self._ants.append([ax, ay, ad, r, g, b])
            self._ants_prev.append((ax, ay))

        display.clear()
        # draw initial grid (alive base)
        for y in range(h):
            row = y * w
            for x in range(w):
                if self._ants_cells[row + x]:
                    display.set_pixel(x, y, 155, 155, 155)
        # draw ants
        for ant in self._ants:
            display.set_pixel(ant[0], ant[1], ant[3], ant[4], ant[5])

    def _ants_step(self):
        """Advance the Langton-ants simulation by one step."""
        w = self._ants_w
        h = self._ants_h
        cells = self._ants_cells
        ants = self._ants

        prev_positions = []
        changed = []

        # 1) update ants + grid state
        for ant in ants:
            x = ant[0]
            y = ant[1]
            d = ant[2]
            r = ant[3]
            g = ant[4]
            b = ant[5]

            prev_positions.append((x, y))
            i = y * w + x
            state = cells[i]
            if state == 0:
                if random.randint(0, 3) == 0:
                    d = random.randint(0, 3)
                else:
                    d = (d - 1) & 3
                cells[i] = 1
                changed.append((x, y, 1, r, g, b))
            else:
                d = (d + 1) & 3
                cells[i] = 0
                changed.append((x, y, 0, 0, 0, 0))

            # move
            if d == 0:
                y = (y - 1) % h
            elif d == 1:
                x = (x + 1) % w
            elif d == 2:
                y = (y + 1) % h
            else:
                x = (x - 1) % w

            ant[0], ant[1], ant[2] = x, y, d

        # 2) erase ants from previous positions (restore base cell colors)
        for x, y in prev_positions:
            if cells[y * w + x]:
                display.set_pixel(x, y, 155, 155, 155)
            else:
                display.set_pixel(x, y, 0, 0, 0)

        # 3) apply changed cells (dim colored trails)
        for x, y, st, r, g, b in changed:
            if st:
                display.set_pixel(x, y, r // 2, g // 2, b // 2)
            else:
                display.set_pixel(x, y, 0, 0, 0)

        # 4) draw ants in new positions
        for ant in ants:
            display.set_pixel(ant[0], ant[1], ant[3], ant[4], ant[5])

    def _flood_init(self):
        """Initialize flood-fill demo buffers and queues for the grid."""
        # Closely matches hub75/floodfill_maze_on_hub75_128x128.py, optimized for 64x64.
        w = self._flood_w
        h = self._flood_h

        try:
            gc.collect()
        except Exception:
            pass

        if self._flood is None or len(self._flood) != w * h:
            self._flood = bytearray(w * h)
        else:
            for i in range(w * h):
                self._flood[i] = 0

        if self._flood_vis is None or len(self._flood_vis) != w * h:
            self._flood_vis = bytearray(w * h)
        else:
            for i in range(w * h):
                self._flood_vis[i] = 0

        if self._flood_q is None or len(self._flood_q) != w * h * 2:
            self._flood_q = bytearray(w * h * 2)

        self._flood_q_head = 0
        self._flood_q_tail = 0
        self._flood_steps = 0

        g = self._flood
        visited = self._flood_vis

        border = 24  # 48 @ 128 scaled to 64
        step = 4  # 8 @ 128 scaled to 64

        # Start near center like reference
        sx = random.randint(border // 2, min(w - 2, w - border // 2))
        sy = random.randint(border // 2, min(h - 2, h - border // 2))

        # Fixed-size stack for DFS nodes (step grid is about (w/step)*(h/step)).
        max_nodes = (w // step) * (h // step)
        stack = bytearray(max_nodes * 2)
        sp = 0

        def stack_push(v):
            """Push a 16-bit value `v` onto the DFS stack (little-endian)."""
            nonlocal sp
            stack[sp] = v & 0xFF
            stack[sp + 1] = (v >> 8) & 0xFF
            sp += 2

        def stack_top():
            """Return the 16-bit value currently at the top of the stack."""
            return stack[sp - 2] | (stack[sp - 1] << 8)

        def stack_pop():
            """Pop the top 16-bit value from the DFS stack (adjust pointer)."""
            nonlocal sp
            sp -= 2

        def mark_line(px, py, v=1):
            """Set grid cell at (px,py) to `v` and draw it on the display."""
            g[py * w + px] = v
            display.set_pixel(px, py, 255, 255, 255)

        display.clear()

        stack_push((sy << 6) | sx)
        visited[sy * w + sx] = 1

        dirs = [(0, step), (0, -step), (step, 0), (-step, 0)]
        while sp:
            v = stack_top()
            x = v & 0x3F
            y = v >> 6

            mixed = dirs[:]
            self._shuffle_in_place(mixed)

            found = False
            for dx, dy in mixed:
                nx = x + dx
                ny = y + dy
                if not (0 < nx < w and 0 < ny < h):
                    continue
                ii = ny * w + nx
                if visited[ii]:
                    continue

                sx1 = dx // step
                sy1 = dy // step
                for i in range(1, step):
                    mark_line(x + sx1 * i, y + sy1 * i, 1)

                # endpoint in reference uses value 5
                mark_line(nx, ny, 5)

                visited[ii] = 1
                stack_push((ny << 6) | nx)
                found = True
                break

            if not found:
                stack_pop()

        # Choose "enemy" start in central border area on empty cell
        while True:
            ex = random.randint(border, w - border - 1)
            ey = random.randint(border, h - border - 1)
            idx = ey * w + ex
            if g[idx] == 0:
                g[idx] = 3
                break

        # enqueue start (do not overwrite enemy)
        bi = self._flood_q_tail * 2
        self._flood_q[bi] = ex & 0xFF
        self._flood_q[bi + 1] = ey & 0xFF
        self._flood_q_tail += 1

    def _flood_step(self):
        """Perform several steps of the flood-fill demo queue.

        Dequeues positions and expands the fill; throttles for
        visibility and restarts when finished or max steps exceeded.
        """
        w = self._flood_w
        h = self._flood_h
        q = self._flood_q
        head = self._flood_q_head
        tail = self._flood_q_tail
        g = self._flood
        max_steps = self._flood_max_steps

        # expand a bunch per frame
        n = 260
        while n > 0:
            # slow down for visibility
            if self._flood_steps % 50 == 0:
                sleep_ms(self._flood_sleep_ms)
            n -= 1
            if head >= tail or self._flood_steps >= max_steps:
                self._flood_init()
                return
            bi = head * 2
            # stored as bytes: x then y
            x = q[bi]
            y = q[bi + 1]
            head += 1
            i = y * w + x
            gv = g[i]
            # match reference: allow flood on empty and enemy; leave lines intact
            if gv != 0 and gv != 3 and gv != 4:
                continue
            # visit
            g[i] = 2
            if gv != 3:
                hue = (self._flood_steps * 360) // max_steps
                r, gg, b = hsb_to_rgb(hue, 1.0, 1.0)
                display.set_pixel(x, y, r, gg, b)
            self._flood_steps += 1

            # neighbors
            def q_push_xy(px, py):
                """Enqueue pixel (px,py) into the flood-fill queue if space."""
                nonlocal tail
                if tail >= w * h:
                    return
                bj = tail * 2
                q[bj] = px & 0xFF
                q[bj + 1] = py & 0xFF
                tail += 1

            if x + 1 < w and g[i + 1] == 0:
                g[i + 1] = 4
                q_push_xy(x + 1, y)
            if x - 1 >= 0 and g[i - 1] == 0:
                g[i - 1] = 4
                q_push_xy(x - 1, y)
            if y + 1 < h and g[i + w] == 0:
                g[i + w] = 4
                q_push_xy(x, y + 1)
            if y - 1 >= 0 and g[i - w] == 0:
                g[i - w] = 4
                q_push_xy(x, y - 1)

        self._flood_q_head = head
        self._flood_q_tail = tail

    def _fire_palette(self, v):
        """Return an RGB tuple for a given fire intensity `v` (0..36)."""
        # v: 0..36 -> rgb
        if v <= 0:
            return (0, 0, 0)
        if v < 10:
            return (v * 7, 0, 0)
        if v < 20:
            return (70 + (v - 10) * 10, (v - 10) * 3, 0)
        if v < 30:
            return (170 + (v - 20) * 6, 30 + (v - 20) * 8, 0)
        return (255, 120 + (v - 30) * 10 if (120 + (v - 30) * 10) < 255 else 255, 20)

    def _fire_init(self):
        """Initialize fire buffers and force initial redraw."""
        w = self._fire_w
        h = self._fire_h
        if self._fire is None or len(self._fire) != w * h:
            self._fire = bytearray(w * h)
        else:
            for i in range(w * h):
                self._fire[i] = 0
        if self._fire_prev is None or len(self._fire_prev) != w * h:
            self._fire_prev = bytearray(w * h)
        # force redraw first frame
        for i in range(w * h):
            self._fire_prev[i] = 255
        display.clear()

    def _fire_step(self):
        """Advance the fire simulation by one step and update seed row."""
        w = self._fire_w
        h = self._fire_h
        buf = self._fire

        # seed bottom row
        base = (h - 1) * w
        for x in range(w):
            buf[base + x] = 36 if random.randint(0, 99) < 60 else 0

        # propagate upwards
        for y in range(h - 1):
            row = y * w
            src_row = (y + 1) * w
            for x in range(w):
                src = src_row + x
                v = buf[src]
                if v:
                    decay = random.randint(0, 3)
                    nv = v - decay
                    if nv < 0:
                        nv = 0
                    dx = x + 1 - random.randint(0, 2)
                    if dx < 0:
                        dx = 0
                    elif dx >= w:
                        dx = w - 1
                    buf[row + dx] = nv
                else:
                    # slowly cool
                    if buf[row + x] > 0:
                        buf[row + x] -= 1

        # diff-draw
        prev = self._fire_prev
        for i in range(w * h):
            v = buf[i]
            if v == prev[i]:
                continue
            prev[i] = v
            x = i % w
            y = i // w
            r, g, b = self._fire_palette(v)
            display.set_pixel(x, y, r, g, b)

    # --- SNAKE (based on hub75/snake_on_hub75_zeroplayer.py) ---
    def _snake_restart(self):
        """Restart the snake game and reset its state and counters."""
        self._snake_score = 0
        self._snake = [(WIDTH // 2, HEIGHT // 2)]
        self._snake_length = 3
        self._snake_dir = "UP"
        self._snake_green_targets = []
        self._snake_step_counter = 0
        self._snake_step_counter2 = 0
        display.clear()
        self._snake_place_target()

    def _snake_random_target(self):
        """Return a random valid target position inside the playfield."""
        return (random.randint(1, WIDTH - 2), random.randint(1, HEIGHT - 2))

    def _snake_place_target(self):
        """Place a red target at a random free location for the snake to eat."""
        tries = 0
        while tries < 300:
            tries += 1
            x, y = self._snake_random_target()
            if (x, y) in self._snake:
                continue
            hit_green = False
            for gx, gy, _ in self._snake_green_targets:
                if (gx, gy) == (x, y):
                    hit_green = True
                    break
            if hit_green:
                continue
            self._snake_target = (x, y)
            display.set_pixel(x, y, 255, 0, 0)
            return
        self._snake_target = (WIDTH // 2, HEIGHT // 2)
        display.set_pixel(self._snake_target[0], self._snake_target[1], 255, 0, 0)

    def _snake_place_green_target(self):
        """Place a temporary green target with limited lifespan."""
        tries = 0
        while tries < 200:
            tries += 1
            x, y = random.randint(1, WIDTH - 2), random.randint(1, HEIGHT - 2)
            if (x, y) == self._snake_target:
                continue
            if (x, y) in self._snake:
                continue
            self._snake_green_targets.append((x, y, 256))
            display.set_pixel(x, y, 0, 255, 0)
            return

    def _snake_update_green_targets(self):
        """Advance lifetimes of green targets and remove expired ones."""
        new_targets = []
        for x, y, lifespan in self._snake_green_targets:
            if lifespan > 1:
                new_targets.append((x, y, lifespan - 1))
            else:
                display.set_pixel(x, y, 0, 0, 0)
        self._snake_green_targets = new_targets

    def _snake_find_nearest_target(self, head_x, head_y):
        """Return the nearest attractive target (green or red) to the snake head."""

        def md(x1, y1, x2, y2):
            """Manhattan distance helper function."""
            return abs(x1 - x2) + abs(y1 - y2)

        nearest_green = None
        min_green = 99999
        for x, y, _ in self._snake_green_targets:
            d = md(head_x, head_y, x, y)
            if d < min_green:
                min_green = d
                nearest_green = (x, y)

        tx, ty = self._snake_target
        red_d = md(head_x, head_y, tx, ty)
        if nearest_green and min_green <= red_d * 1.5:
            return nearest_green
        return (tx, ty)

    def _snake_update_direction(self):
        """Choose the snake's next direction aiming at the chosen target."""
        head_x, head_y = self._snake[0]
        target_x, target_y = self._snake_find_nearest_target(head_x, head_y)

        opposite = {"UP": "DOWN", "DOWN": "UP", "LEFT": "RIGHT", "RIGHT": "LEFT"}
        cur = self._snake_dir
        new_dir = cur

        if head_x == target_x:
            if head_y < target_y and cur != "UP":
                new_dir = "DOWN"
            elif head_y > target_y and cur != "DOWN":
                new_dir = "UP"
        elif head_y == target_y:
            if head_x < target_x and cur != "LEFT":
                new_dir = "RIGHT"
            elif head_x > target_x and cur != "RIGHT":
                new_dir = "LEFT"
        else:
            if abs(head_x - target_x) < abs(head_y - target_y):
                if head_x < target_x and cur != "LEFT":
                    new_dir = "RIGHT"
                elif head_x > target_x and cur != "RIGHT":
                    new_dir = "LEFT"
            else:
                if head_y < target_y and cur != "UP":
                    new_dir = "DOWN"
                elif head_y > target_y and cur != "DOWN":
                    new_dir = "UP"

        if new_dir == opposite.get(cur):
            new_dir = cur
        self._snake_dir = new_dir

    def _snake_check_self_collision(self):
        """Detect imminent self-collisions and try to avoid or restart."""
        head_x, head_y = self._snake[0]
        body = self._snake[1:]
        potential = {
            "UP": (head_x, (head_y - 1) % HEIGHT),
            "DOWN": (head_x, (head_y + 1) % HEIGHT),
            "LEFT": ((head_x - 1) % WIDTH, head_y),
            "RIGHT": ((head_x + 1) % WIDTH, head_y),
        }
        cur_next = potential[self._snake_dir]
        if cur_next in body:
            safe = [d for d, pos in potential.items() if pos not in body]
            if safe:
                self._snake_dir = safe[random.randint(0, len(safe) - 1)]
            else:
                self._snake_restart()

    def _snake_update_position(self):
        """Move the snake head according to direction and trim tail as needed."""
        head_x, head_y = self._snake[0]
        if self._snake_dir == "UP":
            head_y -= 1
        elif self._snake_dir == "DOWN":
            head_y += 1
        elif self._snake_dir == "LEFT":
            head_x -= 1
        else:
            head_x += 1
        head_x %= WIDTH
        head_y %= HEIGHT

        self._snake.insert(0, (head_x, head_y))
        if len(self._snake) > self._snake_length:
            tx, ty = self._snake.pop()
            display.set_pixel(tx, ty, 0, 0, 0)

    def _snake_check_target_collision(self):
        """Handle collision with the red target (grow and respawn target)."""
        if self._snake[0] == self._snake_target:
            self._snake_length += 2
            self._snake_place_target()
            self._snake_score += 1

    def _snake_check_green_target_collision(self):
        """Handle collision with green targets (reduce length)."""
        hx, hy = self._snake[0]
        for x, y, lifespan in self._snake_green_targets:
            if (hx, hy) == (x, y):
                self._snake_length = max(self._snake_length // 2, 2)
                try:
                    self._snake_green_targets.remove((x, y, lifespan))
                except Exception:
                    pass
                display.set_pixel(x, y, 0, 0, 0)
                break

    def _snake_draw(self):
        """Draw the snake using a cycling hue per segment."""
        hue = 0
        for x, y in self._snake:
            hue = (hue + 5) % 360
            r, g, b = hsb_to_rgb(hue, 1, 1)
            display.set_pixel(x, y, r, g, b)

    def _snake_init(self):
        """Initialize snake game state."""
        self._snake_restart()

    def _snake_step(self):
        """Perform one simulation step for the snake game (movement, targets)."""
        self._snake_step_counter += 1
        self._snake_step_counter2 += 1
        if (self._snake_step_counter2 & 1023) == 0:
            self._snake_place_green_target()

        self._snake_update_green_targets()
        self._snake_update_direction()
        self._snake_check_self_collision()
        self._snake_update_position()
        self._snake_check_target_collision()
        self._snake_check_green_target_collision()
        self._snake_draw()

    def main_loop(self, joystick):
        """Main demo selection and event loop; returns on exit button."""
        global game_over, global_score
        game_over = False
        global_score = 0

        frame_ms = 35
        last_frame = ticks_ms()

        while True:
            c_button, _ = joystick.nunchuck.buttons()
            if c_button:
                return

            now = ticks_ms()
            if ticks_diff(now, self._last_move) > self._move_delay:
                d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT])
                if d == JOYSTICK_LEFT:
                    self.idx = (self.idx - 1) % len(self.demos)
                    self._reset_demo_state()
                    try:
                        gc.collect()
                    except Exception:
                        pass
                    self._last_move = now
                elif d == JOYSTICK_RIGHT:
                    self.idx = (self.idx + 1) % len(self.demos)
                    self._reset_demo_state()
                    try:
                        gc.collect()
                    except Exception:
                        pass
                    self._last_move = now

            if ticks_diff(now, last_frame) < frame_ms:
                sleep_ms(1)
                continue
            last_frame = now
            self._frame += 1

            demo = self.demos[self.idx]
            if not self._init:
                display.clear()
                # No HUD in demos: use full 64x64 for visuals.
                if demo == "LIFE":
                    self._life_cur = bytearray(self._life_w * self._life_h)
                    self._life_nxt = bytearray(self._life_w * self._life_h)
                    self._life_prev = bytearray(self._life_w * self._life_h)
                    for i in range(self._life_w * self._life_h):
                        self._life_cur[i] = 1 if random.randint(0, 99) < 18 else 0
                        self._life_prev[i] = 2  # force draw
                elif demo == "ANTS":
                    self._ants_init()
                elif demo == "FLOOD":
                    self._flood_init()
                elif demo == "FIRE":
                    self._fire = bytearray(self._fire_w * self._fire_h)
                    self._fire_prev = bytearray(self._fire_w * self._fire_h)
                    self._fire_init()
                else:  # SNAKE
                    self._snake_init()
                self._init = True

            if demo == "LIFE":
                self._life_step(
                    self._life_w, self._life_h, self._life_cur, self._life_nxt
                )
                self._life_cur, self._life_nxt = self._life_nxt, self._life_cur
                self._life_draw_diffs(
                    self._life_w, self._life_h, self._life_cur, self._life_prev
                )

            elif demo == "ANTS":
                self._ants_step()

            elif demo == "FLOOD":
                self._flood_step()

            elif demo == "FIRE":
                self._fire_step()

            else:  # SNAKE
                self._snake_step()

            maybe_collect(1)

    async def _flood_step_async(self):
        """Async cooperative version of flood step for browsers.

        Processes a limited number of queue items and yields to the
        event loop periodically so the UI stays responsive.
        """
        import asyncio

        w = self._flood_w
        h = self._flood_h
        q = self._flood_q
        head = self._flood_q_head
        tail = self._flood_q_tail
        g = self._flood
        max_steps = self._flood_max_steps

        # process a limited number of items per async tick
        n = 120
        while n > 0:
            n -= 1
            if head >= tail or self._flood_steps >= max_steps:
                self._flood_init()
                self._flood_q_head = head
                self._flood_q_tail = tail
                return
            bi = head * 2
            x = q[bi]
            y = q[bi + 1]
            head += 1
            i = y * w + x
            gv = g[i]
            if gv != 0 and gv != 3 and gv != 4:
                continue
            g[i] = 2
            if gv != 3:
                hue = (self._flood_steps * 360) // max_steps
                r, gg, b = hsb_to_rgb(hue, 1.0, 1.0)
                display.set_pixel(x, y, r, gg, b)
            self._flood_steps += 1

            # enqueue neighbors
            if x + 1 < w and g[i + 1] == 0:
                g[i + 1] = 4
                bj = tail * 2
                if tail < w * h:
                    q[bj] = (x + 1) & 0xFF
                    q[bj + 1] = y & 0xFF
                    tail += 1
            if x - 1 >= 0 and g[i - 1] == 0:
                g[i - 1] = 4
                bj = tail * 2
                if tail < w * h:
                    q[bj] = (x - 1) & 0xFF
                    q[bj + 1] = y & 0xFF
                    tail += 1
            if y + 1 < h and g[i + w] == 0:
                g[i + w] = 4
                bj = tail * 2
                if tail < w * h:
                    q[bj] = x & 0xFF
                    q[bj + 1] = (y + 1) & 0xFF
                    tail += 1
            if y - 1 >= 0 and g[i - w] == 0:
                g[i - w] = 4
                bj = tail * 2
                if tail < w * h:
                    q[bj] = x & 0xFF
                    q[bj + 1] = (y - 1) & 0xFF
                    tail += 1

            # occasionally yield for visibility / responsiveness
            if (self._flood_steps & 31) == 0:
                await asyncio.sleep(self._flood_sleep_ms / 1000.0)

        self._flood_q_head = head
        self._flood_q_tail = tail

    async def main_loop_async(self, joystick):
        """Async/cooperative demo loop used by browsers (pygbag).

        Mirrors `main_loop` but yields frequently to keep the event
        loop responsive. Heavy demos are driven in small steps.
        """
        import asyncio

        global game_over, global_score
        game_over = False
        global_score = 0

        frame_ms = 35
        last_frame = ticks_ms()

        while True:
            c_button, _ = joystick.nunchuck.buttons()
            if c_button:
                return

            now = ticks_ms()
            if ticks_diff(now, self._last_move) > self._move_delay:
                d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT])
                if d == JOYSTICK_LEFT:
                    self.idx = (self.idx - 1) % len(self.demos)
                    self._reset_demo_state()
                    try:
                        gc.collect()
                    except Exception:
                        pass
                    self._last_move = now
                elif d == JOYSTICK_RIGHT:
                    self.idx = (self.idx + 1) % len(self.demos)
                    self._reset_demo_state()
                    try:
                        gc.collect()
                    except Exception:
                        pass
                    self._last_move = now

            if ticks_diff(now, last_frame) < frame_ms:
                # cooperative small sleep
                await asyncio.sleep(0.002)
                continue
            last_frame = now
            self._frame += 1

            demo = self.demos[self.idx]
            if not self._init:
                display.clear()
                if demo == "LIFE":
                    self._life_cur = bytearray(self._life_w * self._life_h)
                    self._life_nxt = bytearray(self._life_w * self._life_h)
                    self._life_prev = bytearray(self._life_w * self._life_h)
                    for i in range(self._life_w * self._life_h):
                        self._life_cur[i] = 1 if random.randint(0, 99) < 18 else 0
                        self._life_prev[i] = 2
                elif demo == "ANTS":
                    self._ants_init()
                elif demo == "FLOOD":
                    self._flood_init()
                elif demo == "FIRE":
                    self._fire = bytearray(self._fire_w * self._fire_h)
                    self._fire_prev = bytearray(self._fire_w * self._fire_h)
                    self._fire_init()
                else:
                    self._snake_init()
                self._init = True

            if demo == "LIFE":
                self._life_step(
                    self._life_w, self._life_h, self._life_cur, self._life_nxt
                )
                self._life_cur, self._life_nxt = self._life_nxt, self._life_cur
                self._life_draw_diffs(
                    self._life_w, self._life_h, self._life_cur, self._life_prev
                )

            elif demo == "ANTS":
                self._ants_step()

            elif demo == "FLOOD":
                await self._flood_step_async()

            elif demo == "FIRE":
                self._fire_step()

            else:  # SNAKE
                self._snake_step()

            # cooperative yield to allow the browser to process events
            await asyncio.sleep(0)


class LunarLanderGame:
    """
    LUNAR LANDER MINI
    Steuerung:
      - Links/Rechts: drehen
      - Z oder Stick UP: Schub
      - C: zurück ins Menü
    Ziel: weich & gerade auf dem grünen Pad landen.
    """

    _STEP = 5
    _LUT = None

    @classmethod
    def _ensure_lut(cls):
        """Ensure the lookup table for angle vectors is initialized."""
        if cls._LUT is not None:
            return
        lut = []
        step = cls._STEP
        for a in range(0, 360, step):
            lut.append(
                (
                    int(math.cos(math.radians(a)) * 256),
                    int(math.sin(math.radians(a)) * 256),
                )
            )
        cls._LUT = lut

    def __init__(self):
        """Create a new Lunar Lander instance and initialize state."""
        self.level = 1
        self.total_score = 0
        self.reset()

    async def main_loop_async(self, joystick):
        """Cooperative async Lunar Lander main loop for browsers."""
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()

        frame_ms = 45
        last_frame = ticks_ms()
        self.frame = 0

        while True:
            try:
                c_button, z_button = joystick.nunchuck.buttons()
                if c_button:
                    return

                now = ticks_ms()
                if ticks_diff(now, last_frame) < frame_ms:
                    await asyncio.sleep(0.002)
                    continue
                last_frame = now
                self.frame += 1

                # input
                d = joystick.read_direction(
                    [JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_UP]
                )
                thrust_on = z_button or d == JOYSTICK_UP
                if d == JOYSTICK_LEFT:
                    self.angle = (self.angle - 6) % 360
                elif d == JOYSTICK_RIGHT:
                    self.angle = (self.angle + 6) % 360

                # thrust
                if thrust_on and self.fuel > 0:
                    c, s = self._cos_sin(self.angle)
                    self.vx += c * 0.0015
                    self.vy -= s * 0.0015
                    self.fuel -= 1

                # physics
                self.vy += self.g
                self.x += self.vx
                self.y += self.vy

                # collisions / ground check
                if self.y >= self.terrain[int(min(max(0, int(self.x)), WIDTH - 1))]:
                    # landed or crashed
                    landed = (
                        abs(self.vx) < 0.6
                        and abs(self.vy) < 1.2
                        and abs(self.angle - 90) < 25
                    )
                    if landed:
                        self.points += 100
                        global_score = self.points
                        display.clear()
                        draw_text(2, 24, "DONE", 0, 255, 0)
                        display_score_and_time(global_score)
                        try:
                            await asyncio.sleep(1.8)
                        except Exception:
                            pass
                        self.level += 1
                        self.reset(keep_level=True)
                        display.clear()
                        self._draw_terrain()
                        draw_text(2, 4, "LVL" + str(self.level), 255, 255, 0)
                        display_score_and_time(global_score)
                        try:
                            await asyncio.sleep(1.5)
                        except Exception:
                            pass
                        last_frame = ticks_ms()
                        continue
                    else:
                        global_score = (
                            self.total_score
                            if hasattr(self, "total_score")
                            else self.points
                        )
                        game_over = True
                        return

                # render
                display.clear()
                self._draw_terrain()
                self._draw_ship(thrust_on=thrust_on)
                self._draw_fuel_bar()
                display_score_and_time(self.points)
                global_score = self.points

                if self.frame % 45 == 0:
                    gc.collect()

            except RestartProgram:
                return

    def reset(self, keep_level=False):
        """Reset the lander for a new attempt; optionally keep current level."""
        # Multi-level system: keep level on successful landing, reset on crash
        if not keep_level:
            self.level = 1
            self.total_score = 0

        self.terrain = self._make_terrain()

        # Pad gets smaller and fuel/gravity adjust per level
        self.pad_w = max(6, 10 - self.level)
        self.pad_x = random.randint(6, WIDTH - self.pad_w - 6)
        self.pad_y = self.terrain[self.pad_x]
        for x in range(self.pad_x, self.pad_x + self.pad_w):
            self.terrain[x] = self.pad_y

        self.x = float(WIDTH // 2)
        self.y = 8.0
        self.vx = 0.0
        self.vy = 0.0
        self.angle = 90

        # Fuel decreases and gravity increases per level
        self.fuel_max = max(400, 700 - (self.level - 1) * 60)
        self.fuel = self.fuel_max

        self.g = 0.10 + (self.level - 1) * 0.015
        self.thrust = 0.22

        self.points = 0
        self.last_points_ms = ticks_ms()
        self.frame = 0

    def _make_terrain(self):
        """Generate a random terrain heightmap for the playfield."""
        t = [0] * WIDTH
        y = random.randint(PLAY_HEIGHT - 18, PLAY_HEIGHT - 10)
        lo = PLAY_HEIGHT - 24
        hi = PLAY_HEIGHT - 4

        for x in range(WIDTH):
            y += random.randint(-2, 2)
            if y < lo:
                y = lo
            if y > hi:
                y = hi
            t[x] = y

        # smooth
        for _ in range(2):
            for x in range(1, WIDTH - 1):
                t[x] = (t[x - 1] + t[x] + t[x + 1]) // 3
        return t

    def _cos_sin256(self, angle_deg):
        """Return (cos*256, sin*256) for a given angle in degrees using LUT."""
        angle_deg %= 360
        self._ensure_lut()
        idx = (angle_deg // self._STEP) % (360 // self._STEP)
        return self._LUT[idx]

    def _angle_diff(self, a, b):
        """Return the smallest absolute difference between two angles (degrees)."""
        d = (a - b + 180) % 360 - 180
        return abs(d)

    def _line(self, x0, y0, x1, y1, r, g, b):
        """Draw a line using the shared `draw_line` utility."""
        draw_line(x0, y0, x1, y1, (r, g, b))

    def _draw_ship(self, thrust_on=False):
        """Draw the lander ship; optionally render thrust visuals when active."""
        size = 4
        cx, cy = self.x, self.y

        c, s = self._cos_sin256(self.angle)
        dx = (c * size) / 256.0
        dy = (-s * size) / 256.0  # y nach unten -> -sin

        nx = cx + dx
        ny = cy + dy

        c1, s1 = self._cos_sin256(self.angle + 140)
        lx = cx + (c1 * size) / 256.0
        ly = cy + (-s1 * size) / 256.0

        c2, s2 = self._cos_sin256(self.angle - 140)
        rx = cx + (c2 * size) / 256.0
        ry = cy + (-s2 * size) / 256.0

        self._line(nx, ny, lx, ly, 255, 255, 255)
        self._line(nx, ny, rx, ry, 255, 255, 255)
        self._line(lx, ly, rx, ry, 255, 255, 255)

        if thrust_on and self.fuel > 0:
            fx0 = cx - dx * 0.4
            fy0 = cy - dy * 0.4
            fx1 = cx - dx * 1.4
            fy1 = cy - dy * 1.4
            self._line(fx0, fy0, fx1, fy1, 255, 80, 0)

    def _draw_terrain(self):
        """Render the terrain and landing pad on the display."""
        sp = display.set_pixel
        for x in range(WIDTH):
            ty = self.terrain[x]
            for y in range(ty, PLAY_HEIGHT):
                sp(x, y, 0, 0, 120)

        # pad highlight
        for x in range(self.pad_x, self.pad_x + self.pad_w):
            y = self.pad_y
            if 0 <= x < WIDTH and 0 <= y < PLAY_HEIGHT:
                sp(x, y, 0, 255, 0)
                if y + 1 < PLAY_HEIGHT:
                    sp(x, y + 1, 0, 200, 0)

    def _draw_fuel_bar(self):
        """Draw the current fuel level as a horizontal bar."""
        bar_w = 22
        filled = int((self.fuel / float(self.fuel_max)) * bar_w)
        if filled < 0:
            filled = 0
        if filled > bar_w:
            filled = bar_w

        draw_rectangle(0, 0, bar_w, 1, 40, 40, 40)
        if filled > 0:
            draw_rectangle(0, 0, filled - 1, 1, 255, 255, 0)

    def main_loop(self, joystick):
        """Run the Lunar Lander game loop until exit or crash/land."""
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()

        frame_ms = 35
        last_frame = ticks_ms()

        while not game_over:
            try:
                c_button, z_button = joystick.nunchuck.buttons()
                if c_button:
                    return

                now = ticks_ms()
                if ticks_diff(now, last_frame) < frame_ms:
                    sleep_ms(2)
                    continue
                last_frame = now
                self.frame += 1

                # points over time
                if ticks_diff(now, self.last_points_ms) >= 500:
                    self.last_points_ms = now
                    self.points += 1

                # input
                d = joystick.read_direction(
                    [JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_UP]
                )
                if d == JOYSTICK_LEFT:
                    self.angle = (self.angle + 5) % 360
                elif d == JOYSTICK_RIGHT:
                    self.angle = (self.angle - 5) % 360

                thrust_on = (z_button or d == JOYSTICK_UP) and (self.fuel > 0)

                ax = 0.0
                ay = self.g
                if thrust_on:
                    c, s = self._cos_sin256(self.angle)
                    ax += (c / 256.0) * self.thrust
                    ay += (-s / 256.0) * self.thrust
                    self.fuel -= 1

                # physics
                self.vx += ax
                self.vy += ay

                # clamp velocity
                if self.vx > 2.2:
                    self.vx = 2.2
                if self.vx < -2.2:
                    self.vx = -2.2
                if self.vy > 3.0:
                    self.vy = 3.0
                if self.vy < -3.0:
                    self.vy = -3.0

                self.x += self.vx
                self.y += self.vy

                # bounds
                if self.x < 0:
                    self.x = 0
                    self.vx = 0
                elif self.x > WIDTH - 1:
                    self.x = WIDTH - 1
                    self.vx = 0

                if self.y < 0:
                    self.y = 0
                    self.vy = 0

                # landing/crash
                ix = int(self.x)
                gy = self.terrain[ix]
                if self.y >= gy - 1:
                    on_pad = self.pad_x <= ix <= (self.pad_x + self.pad_w - 1)
                    soft = abs(self.vx) < 0.65 and abs(self.vy) < 1.2
                    upright = self._angle_diff(self.angle, 90) <= 25

                    if on_pad and soft and upright:
                        # Successful landing: award points and advance level
                        level_bonus = (
                            self.points + int(self.fuel) + 200 + (self.level * 150)
                        )
                        self.total_score += level_bonus
                        global_score = self.total_score

                        display.clear()
                        draw_text(2, 12, "LVL" + str(self.level), 0, 255, 0)
                        draw_text(2, 24, "DONE", 0, 255, 0)
                        display_score_and_time(global_score)
                        sleep_ms(1800)

                        # Next level
                        self.level += 1
                        self.reset(keep_level=True)

                        # Short preview of new terrain
                        display.clear()
                        self._draw_terrain()
                        draw_text(2, 4, "LVL" + str(self.level), 255, 255, 0)
                        display_score_and_time(global_score)
                        sleep_ms(1500)

                        last_frame = ticks_ms()
                        continue
                    else:
                        global_score = (
                            self.total_score
                            if hasattr(self, "total_score")
                            else self.points
                        )
                        game_over = True
                        return

                # render
                display.clear()
                self._draw_terrain()
                self._draw_ship(thrust_on=thrust_on)
                self._draw_fuel_bar()
                display_score_and_time(self.points)
                global_score = self.points

                if self.frame % 45 == 0:
                    gc.collect()

            except RestartProgram:
                return


class UFODefenseGame:
    """
    UFO DEFENSE / Missile Command Mini
    Steuerung:
      - Stick: Fadenkreuz bewegen
      - Z: Rakete starten
      - C: zurück ins Menü
    """

    def __init__(self):
        """Create UFO Defense game instance and initialize state."""
        self.reset()

    async def main_loop_async(self, joystick):
        """Cooperative async UFO Defense main loop for browsers."""
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()

        frame_ms = 35
        last_frame = ticks_ms()

        while not game_over:
            c_button, z_button = joystick.nunchuck.buttons()
            if c_button:
                return

            now = ticks_ms()

            # crosshair move handling
            d = joystick.read_direction(
                [
                    JOYSTICK_UP,
                    JOYSTICK_DOWN,
                    JOYSTICK_LEFT,
                    JOYSTICK_RIGHT,
                    JOYSTICK_UP_LEFT,
                    JOYSTICK_UP_RIGHT,
                    JOYSTICK_DOWN_LEFT,
                    JOYSTICK_DOWN_RIGHT,
                ]
            )
            step = 1
            if d and ticks_diff(now, self._last_cross_move) >= self.cross_move_ms:
                if d in (JOYSTICK_LEFT, JOYSTICK_UP_LEFT, JOYSTICK_DOWN_LEFT):
                    self.cx = max(0, self.cx - step)
                elif d in (JOYSTICK_RIGHT, JOYSTICK_UP_RIGHT, JOYSTICK_DOWN_RIGHT):
                    self.cx = min(WIDTH - 1, self.cx + step)
                if d in (JOYSTICK_UP, JOYSTICK_UP_LEFT, JOYSTICK_UP_RIGHT):
                    self.cy = max(0, self.cy - step)
                elif d in (JOYSTICK_DOWN, JOYSTICK_DOWN_LEFT, JOYSTICK_DOWN_RIGHT):
                    self.cy = min(PLAY_HEIGHT - 8, self.cy + step)
                self._last_cross_move = now

            # shoot
            if self.shot_cd > 0:
                self.shot_cd -= 1
            if z_button and self.shot_cd == 0 and len(self.player_missiles) < 3:
                self._fire_player()
                self.shot_cd = 8

            # spawn enemies
            if ticks_diff(now, self.last_spawn) >= self.spawn_ms:
                self.last_spawn = now
                cap = self._enemy_cap(now)
                if len(self.enemy_missiles) < cap:
                    self._spawn_enemy()
                self.level += 1
                self.spawn_ms = max(self.min_spawn_ms, 850 - self.level * 10)
                self.enemy_speed = min(
                    self.max_enemy_speed, self.base_enemy_speed + self.level * 0.01
                )

            # frame pacing
            if ticks_diff(now, last_frame) < frame_ms:
                await asyncio.sleep(0.002)
                continue
            last_frame = now
            self.frame += 1

            self._update_missiles()
            if game_over:
                global_score = self.score
                return

            self._update_explosions_and_hits()
            self._draw_world()
            global_score = self.score

            if self.frame % 45 == 0:
                gc.collect()

    def reset(self):
        """Reset game state: missiles, explosions, and cities."""
        self.score = 0

        self.base_x = WIDTH // 2
        self.base_y = PLAY_HEIGHT - 2

        self.cx = WIDTH // 2
        self.cy = PLAY_HEIGHT // 3

        self.player_missiles = []
        self.enemy_missiles = []
        self.explosions = []

        self.shot_cd = 0

        xs = [6, 16, 26, 38, 48, 58]
        self.cities = [{"x": x, "alive": True} for x in xs]

        self.spawn_ms = 850
        self.min_spawn_ms = 260
        self.last_spawn = ticks_ms()
        self.base_enemy_speed = 0.4
        self.max_enemy_speed = 2.0
        self.enemy_speed = self.base_enemy_speed
        self.level = 0
        self.frame = 0
        # crosshair movement smoothing: ms between pixel moves (tweakable)
        self.cross_move_ms = 45
        self._last_cross_move = ticks_ms()

    def _line(self, x0, y0, x1, y1, col):
        """Draw a colored line between two points using shared utility.

        Args:
            x0: Start x coordinate.
            y0: Start y coordinate.
            x1: End x coordinate.
            y1: End y coordinate.
            col: Color tuple (r,g,b).
        """
        draw_line(x0, y0, x1, y1, col)

    def _cities_alive(self):
        """Return True if any city is still alive."""
        for c in self.cities:
            if c["alive"]:
                return True
        return False

    def _damage_city_at(self, x):
        """Mark a city as destroyed if an explosion hits near x."""
        for c in self.cities:
            if c["alive"] and abs(c["x"] - x) <= 3:
                c["alive"] = False
                break

    def _spawn_enemy(self):
        """Spawn a new enemy missile targeting a random alive city or base."""
        alive = [c for c in self.cities if c["alive"]]
        tgt = random.choice(alive)["x"] if alive else self.base_x

        sx = random.randint(0, WIDTH - 1)
        sy = 0
        tx = tgt
        ty = self.base_y + 1

        dx = tx - sx
        dy = ty - sy
        dist = math.sqrt(dx * dx + dy * dy) + 1e-6
        spd = self.enemy_speed
        vx = dx / dist * spd
        vy = dy / dist * spd

        self.enemy_missiles.append(
            {
                "x": float(sx),
                "y": float(sy),
                "px": float(sx),
                "py": float(sy),
                "tx": float(tx),
                "ty": float(ty),
                "vx": vx,
                "vy": vy,
            }
        )

    def _enemy_cap(self, now):
        """Return the allowed number of simultaneous enemy missiles based on time."""
        # time-based caps: 0-60s -> 2, 60-180s -> 4, 180-300s -> 6, afterwards 6
        elapsed = ticks_diff(now, getattr(self, "start_ms", now))
        if elapsed < 60_000:
            return 2
        if elapsed < 180_000:
            return 4
        return 6

    def _fire_player(self):
        """Launch a player missile towards current crosshair position."""
        sx = self.base_x
        sy = self.base_y
        tx = self.cx
        ty = self.cy

        dx = tx - sx
        dy = ty - sy
        dist = math.sqrt(dx * dx + dy * dy) + 1e-6
        spd = 2.7
        vx = dx / dist * spd
        vy = dy / dist * spd

        self.player_missiles.append(
            {
                "x": float(sx),
                "y": float(sy),
                "px": float(sx),
                "py": float(sy),
                "tx": float(tx),
                "ty": float(ty),
                "vx": vx,
                "vy": vy,
            }
        )
        # firing costs 1 point
        try:
            self.score = max(0, self.score - 1)
        except Exception:
            pass

    def _add_explosion(self, x, y, max_r, color):
        """Append a new explosion entry to be animated."""
        self.explosions.append(make_explosion(x, y, max_r, color))

    def _draw_explosion(self, ex):
        """Render a single explosion ring on the display."""
        render_explosion(ex)

    def _update_explosions_and_hits(self):
        """Advance explosion animations and remove missiles hit by them."""
        for ex in self.explosions[:]:
            ex["r"] += ex["dr"]
            if ex["r"] >= ex["max"]:
                ex["dr"] = -1
            if ex["r"] <= 0 and ex["dr"] < 0:
                self.explosions.remove(ex)
                continue

            r2 = (ex["r"] + 1) * (ex["r"] + 1)
            exx = ex["x"]
            exy = ex["y"]

            for em in self.enemy_missiles[:]:
                dx = em["x"] - exx
                dy = em["y"] - exy
                if dx * dx + dy * dy <= r2:
                    self.enemy_missiles.remove(em)
                    self.score += 10

    def _update_missiles(self):
        """Advance all missiles (player and enemy) and handle impacts."""
        global game_over, global_score

        # player
        for m in self.player_missiles[:]:
            m["px"], m["py"] = m["x"], m["y"]
            m["x"] += m["vx"]
            m["y"] += m["vy"]
            dx = m["x"] - m["tx"]
            dy = m["y"] - m["ty"]
            if dx * dx + dy * dy <= 7.0:
                self.player_missiles.remove(m)
                self._add_explosion(m["tx"], m["ty"], 6, (255, 180, 0))
            elif m["y"] < 0 or m["y"] >= PLAY_HEIGHT:
                self.player_missiles.remove(m)

        # enemy
        for m in self.enemy_missiles[:]:
            m["px"], m["py"] = m["x"], m["y"]
            m["x"] += m["vx"]
            m["y"] += m["vy"]
            if m["y"] >= m["ty"] or m["y"] >= PLAY_HEIGHT - 1:
                self.enemy_missiles.remove(m)
                ix = int(m["x"])
                iy = int(m["y"])
                self._add_explosion(ix, iy, 5, (255, 60, 60))

                if abs(ix - self.base_x) <= 3:
                    global_score = self.score
                    game_over = True
                    return

                self._damage_city_at(ix)
                if not self._cities_alive():
                    global_score = self.score
                    game_over = True
                    return

    def _draw_world(self):
        """Render the static world: cities and base, and dynamic missiles/explosions."""
        display.clear()
        sp = display.set_pixel

        # cities
        city_y = PLAY_HEIGHT - 4
        for c in self.cities:
            if c["alive"]:
                x = c["x"]
                draw_rectangle(x - 1, city_y, x + 1, city_y + 1, 0, 255, 0)

        # base
        bx = self.base_x
        by = self.base_y
        for dx in (-1, 0, 1):
            x = bx + dx
            if 0 <= x < WIDTH and 0 <= by < PLAY_HEIGHT:
                sp(x, by, 120, 120, 255)
        if 0 <= bx < WIDTH and 0 <= (by - 1) < PLAY_HEIGHT:
            sp(bx, by - 1, 120, 120, 255)

        # crosshair
        x = self.cx
        y = self.cy
        for dx in (-2, -1, 0, 1, 2):
            xx = x + dx
            if 0 <= xx < WIDTH and 0 <= y < PLAY_HEIGHT:
                sp(xx, y, 255, 255, 255)
        for dy in (-2, -1, 0, 1, 2):
            yy = y + dy
            if 0 <= x < WIDTH and 0 <= yy < PLAY_HEIGHT:
                sp(x, yy, 255, 255, 255)

        # missiles
        for m in self.player_missiles:
            self._line(m["px"], m["py"], m["x"], m["y"], (255, 255, 255))
        for m in self.enemy_missiles:
            self._line(m["px"], m["py"], m["x"], m["y"], (255, 0, 0))

        # explosions
        for ex in self.explosions:
            self._draw_explosion(ex)

        display_score_and_time(self.score)

    def main_loop(self, joystick):
        """Run UFO Defense main loop handling input, spawning, and rendering."""
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()

        frame_ms = 35
        last_frame = ticks_ms()

        while not game_over:
            try:
                c_button, z_button = joystick.nunchuck.buttons()
                if c_button:
                    return

                now = ticks_ms()

                # crosshair move: move one pixel only when enough ms passed
                d = joystick.read_direction(
                    [
                        JOYSTICK_UP,
                        JOYSTICK_DOWN,
                        JOYSTICK_LEFT,
                        JOYSTICK_RIGHT,
                        JOYSTICK_UP_LEFT,
                        JOYSTICK_UP_RIGHT,
                        JOYSTICK_DOWN_LEFT,
                        JOYSTICK_DOWN_RIGHT,
                    ]
                )
                step = 1
                if d and ticks_diff(now, self._last_cross_move) >= self.cross_move_ms:
                    if d in (JOYSTICK_LEFT, JOYSTICK_UP_LEFT, JOYSTICK_DOWN_LEFT):
                        self.cx = max(0, self.cx - step)
                    elif d in (JOYSTICK_RIGHT, JOYSTICK_UP_RIGHT, JOYSTICK_DOWN_RIGHT):
                        self.cx = min(WIDTH - 1, self.cx + step)
                    if d in (JOYSTICK_UP, JOYSTICK_UP_LEFT, JOYSTICK_UP_RIGHT):
                        self.cy = max(0, self.cy - step)
                    elif d in (JOYSTICK_DOWN, JOYSTICK_DOWN_LEFT, JOYSTICK_DOWN_RIGHT):
                        self.cy = min(PLAY_HEIGHT - 8, self.cy + step)
                    self._last_cross_move = now

                # shoot
                if self.shot_cd > 0:
                    self.shot_cd -= 1
                if z_button and self.shot_cd == 0 and len(self.player_missiles) < 3:
                    self._fire_player()
                    self.shot_cd = 8

                # spawn enemies with time-based caps
                if ticks_diff(now, self.last_spawn) >= self.spawn_ms:
                    self.last_spawn = now
                    cap = self._enemy_cap(now)
                    # only spawn if below current cap
                    if len(self.enemy_missiles) < cap:
                        self._spawn_enemy()
                    self.level += 1
                    self.spawn_ms = max(self.min_spawn_ms, 850 - self.level * 10)
                    self.enemy_speed = min(
                        self.max_enemy_speed, self.base_enemy_speed + self.level * 0.01
                    )

                # frame pacing
                if ticks_diff(now, last_frame) < frame_ms:
                    sleep_ms(2)
                    continue
                last_frame = now
                self.frame += 1

                self._update_missiles()
                if game_over:
                    global_score = self.score
                    return

                self._update_explosions_and_hits()
                self._draw_world()
                global_score = self.score

                if self.frame % 45 == 0:
                    gc.collect()

            except RestartProgram:
                return


# -----------------------------
# DOOM-LITE / RAYCASTER GAME
# -----------------------------
array: Any
try:
    from array import array  # type: ignore
except ImportError:
    array = None


class DoomLiteGame:
    """
    DOOM-LITE (extrem abgesteckt) = Wolf3D-Raycaster + Sprites

    Steuerung:
      - UP/DOWN: vor/zurück
      - LEFT/RIGHT: drehen
      - Diagonal: drehen+laufen
      - Z: schießen
      - C: zurück ins Menü

    Ziel:
      - Gegner erledigen, Wellen überleben (endlos)
    """

    # Playfield ohne Score-Leiste
    PLAY_H = HEIGHT - 6

    # Map: 16x16, '#' = Wand, '.' = frei
    MAP_W = 16
    MAP_H = 16
    MAP = (
        b"################",
        b"#..............#",
        b"#..####..####..#",
        b"#..####..####..#",
        b"#..####..####..#",
        b"#..####..####..#",
        b"#..####..####..#",
        b"#..............#",
        b"#..####..####..#",
        b"#..####..####..#",
        b"#..####..####..#",
        b"#..####..####..#",
        b"#..####..####..#",
        b"#..............#",
        b"#....######....#",
        b"################",
    )

    # Raycaster Parameter
    ANGLE_MAX = 256  # 0..255 entspricht 0..360°
    FOV = 48  # ~67.5° (48/256 * 360)
    HALF_FOV = FOV // 2
    MAX_STEPS = 36
    MAX_DIST = 32.0

    # LUT für sin/cos (256 Steps, Scale 1024) - LUT = LookUp Table
    # Lazy init to avoid large import-time allocations on MicroPython.
    _COS = None
    _SIN = None

    @classmethod
    def _ensure_trig(cls):
        """Ensure trig lookup tables are initialized (lazy init)."""
        if cls._COS is not None and cls._SIN is not None:
            return
        try:
            gc.collect()
        except Exception:
            pass

        if array:
            cos_lut = array("h")
            sin_lut = array("h")
            for i in range(256):
                ang = 2 * math.pi * i / 256
                cos_lut.append(int(math.cos(ang) * 1024))
                sin_lut.append(int(math.sin(ang) * 1024))
            cls._COS = cos_lut
            cls._SIN = sin_lut
        else:
            cos_lut = []
            sin_lut = []
            for i in range(256):
                ang = 2 * math.pi * i / 256
                cos_lut.append(int(math.cos(ang) * 1024))
                sin_lut.append(int(math.sin(ang) * 1024))
            cls._COS = cos_lut
            cls._SIN = sin_lut

    def __init__(self):
        """Initialize raycaster resources and reset game state."""
        self._ensure_trig()
        self.zbuf = [self.MAX_DIST] * WIDTH  # Wanddistanz pro Screen-Spalte
        self.reset()

    async def main_loop_async(self, joystick):
        """Cooperative async version of the DoomLite main loop for browsers.

        Mirrors `main_loop` but yields to the asyncio event loop between
        frames so the browser remains responsive during heavy rendering.
        """
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        display_score_and_time(0)

        while not game_over:
            try:
                c_button, z_button = joystick.nunchuck.buttons()
                if c_button:
                    return

                now = ticks_ms()
                if ticks_diff(now, self.last_frame) < self.frame_ms:
                    await asyncio.sleep(0.002)
                    continue
                self.last_frame = now
                self.frame += 1

                # input
                d = joystick.read_direction(
                    [
                        JOYSTICK_UP,
                        JOYSTICK_DOWN,
                        JOYSTICK_LEFT,
                        JOYSTICK_RIGHT,
                        JOYSTICK_UP_LEFT,
                        JOYSTICK_UP_RIGHT,
                        JOYSTICK_DOWN_LEFT,
                        JOYSTICK_DOWN_RIGHT,
                    ],
                    debounce=False,
                )

                # rotate
                rot = 0
                if d in (JOYSTICK_LEFT, JOYSTICK_UP_LEFT, JOYSTICK_DOWN_LEFT):
                    rot = -5
                elif d in (JOYSTICK_RIGHT, JOYSTICK_UP_RIGHT, JOYSTICK_DOWN_RIGHT):
                    rot = +5
                if rot:
                    self.ang = (self.ang + rot) & 255

                # move
                move = 0.0
                if d in (JOYSTICK_UP, JOYSTICK_UP_LEFT, JOYSTICK_UP_RIGHT):
                    move = 0.12
                elif d in (JOYSTICK_DOWN, JOYSTICK_DOWN_LEFT, JOYSTICK_DOWN_RIGHT):
                    move = -0.10

                if move != 0.0:
                    c, s = self._cos_sin(self.ang)
                    dx = c * move
                    dy = -s * move

                    nx = self.px + dx
                    ny = self.py + dy

                    # axis-separate collision
                    if not self._is_wall_pos(nx, self.py):
                        self.px = nx
                    if not self._is_wall_pos(self.px, ny):
                        self.py = ny

                # shoot
                if self.shot_cd > 0:
                    self.shot_cd -= 1
                if z_button and self.shot_cd == 0:
                    self._shoot()
                    self.shot_cd = 10

                # enemy update / collision
                self._update_enemies()
                if game_over:
                    global_score = self.score
                    return

                # next wave?
                alive = 0
                for e in self.enemies:
                    if e[2] > 0:
                        alive += 1
                if alive == 0:
                    self.score += 100
                    self.wave += 1
                    self._spawn_wave(self.wave)

                global_score = self.score
                self._render()

                if (self.frame % 80) == 0:
                    gc.collect()

                # yield to browser event loop after each rendered frame
                await asyncio.sleep(0)

            except RestartProgram:
                return
            except Exception as e:
                print("Error during DoomLiteGame.main_loop_async:", e)
                try:
                    traceback.print_exc()
                except Exception:
                    pass
                return

    def reset(self):
        """Reset player position, waves, and enemy list for a new run."""
        # Player (Map-Koordinaten, 1 Tile = 1.0)
        self.px = 2.5
        self.py = 2.5
        self.ang = 180

        self.score = 0
        self.lives = 3
        self.wave = 1

        self.shot_cd = 0

        self.enemies = []
        self._spawn_wave(self.wave)

        self.last_frame = ticks_ms()
        self.frame_ms = 35  # ~28 fps
        self.frame = 0

    # --- helpers ---
    def _is_wall_tile(self, mx, my):
        """Return True if map cell at (mx,my) is a wall or out of bounds."""
        if mx < 0 or mx >= self.MAP_W or my < 0 or my >= self.MAP_H:
            return True
        return self.MAP[my][mx] == 35  # '#'

    def _is_wall_pos(self, x, y):
        """Return True if the world position (x,y) lies inside a wall tile."""
        return self._is_wall_tile(int(x), int(y))

    def _cos_sin(self, a):
        """Return (cos,sin) from precalculated LUT scaled to 1.0."""
        a &= 255
        return self._COS[a] / 1024.0, self._SIN[a] / 1024.0

    def _angle_to_units(self, dx, dy):
        """Convert a vector (dx,dy) to 0..255 angular units suitable for LUT."""
        # dx,dy in Map-Koordinaten; Achtung y-Achse ist "nach unten"
        ang = math.atan2(-dy, dx)  # -dy -> mathematisch korrekt
        if ang < 0:
            ang += 2 * math.pi
        return int(ang * 256 / (2 * math.pi)) & 255

    def _angle_delta(self, a, b):
        """Compute the minimal signed delta between two 0..255 angle units."""
        # kleinste Differenz a-b in [-128..127]
        d = (a - b + 128) & 255
        return d - 128

    def _cast_ray(self, ray_ang):
        """
        DDA Raycast: liefert (dist, side)
        side: 0 = x-seite (vertikale Wand), 1 = y-seite (horizontale Wand)
        """
        # Ray direction (float)
        c, s = self._cos_sin(ray_ang)
        ray_dx = c
        ray_dy = -s  # y nach unten

        # avoid division by 0
        if ray_dx == 0:
            ray_dx = 1e-6
        if ray_dy == 0:
            ray_dy = 1e-6

        map_x = int(self.px)
        map_y = int(self.py)

        delta_x = abs(1.0 / ray_dx)
        delta_y = abs(1.0 / ray_dy)

        if ray_dx < 0:
            step_x = -1
            side_x = (self.px - map_x) * delta_x
        else:
            step_x = 1
            side_x = (map_x + 1.0 - self.px) * delta_x

        if ray_dy < 0:
            step_y = -1
            side_y = (self.py - map_y) * delta_y
        else:
            step_y = 1
            side_y = (map_y + 1.0 - self.py) * delta_y

        side = 0
        for _ in range(self.MAX_STEPS):
            if side_x < side_y:
                side_x += delta_x
                map_x += step_x
                side = 0
            else:
                side_y += delta_y
                map_y += step_y
                side = 1

            if self._is_wall_tile(map_x, map_y):
                if side == 0:
                    dist = side_x - delta_x
                else:
                    dist = side_y - delta_y
                if dist < 0.05:
                    dist = 0.05
                if dist > self.MAX_DIST:
                    dist = self.MAX_DIST
                return dist, side

        return self.MAX_DIST, side

    def _spawn_wave(self, wave):
        """Spawn a small wave of enemies (2..6) depending on wave number."""
        # sehr klein halten: 2..6 Gegner
        n = 2 + (wave // 2)
        if n > 6:
            n = 6
        self.enemies = []
        tries = 0
        while len(self.enemies) < n and tries < 200:
            tries += 1
            ex = random.randint(1, self.MAP_W - 2) + 0.5
            ey = random.randint(1, self.MAP_H - 2) + 0.5
            if self._is_wall_pos(ex, ey):
                continue
            # nicht direkt am Start
            if abs(ex - self.px) + abs(ey - self.py) < 4:
                continue
            hp = 1 if wave < 4 else 2
            self.enemies.append([ex, ey, hp])

    def _shoot(self):
        """Perform a simple hitscan shoot: damage nearest visible enemy in crosshair."""
        # simple hitscan: Gegner in Blickrichtung, nahe Crosshair, nicht hinter Wand
        wall_dist, _ = self._cast_ray(self.ang)

        best_i = -1
        best_d = 999.0

        for i, e in enumerate(self.enemies):
            if e[2] <= 0:
                continue
            dx = e[0] - self.px
            dy = e[1] - self.py
            dist = math.sqrt(dx * dx + dy * dy)
            if dist <= 0.1:
                continue

            if dist >= wall_dist + 0.2:
                continue

            a = self._angle_to_units(dx, dy)
            delta = self._angle_delta(a, self.ang)

            # nur wenn nahe an der Mitte (Crosshair) -> sehr "abgesteckt"
            if abs(delta) > 3:
                continue

            if dist < best_d:
                best_d = dist
                best_i = i

        if best_i >= 0:
            self.enemies[best_i][2] -= 1
            if self.enemies[best_i][2] <= 0:
                self.score += 50
            else:
                self.score += 15

    def _update_enemies(self):
        """Advance enemy AI movement and handle collisions with player."""
        global game_over, global_score

        # Enemies bewegen sich selten (Performance + Doom-Feeling)
        if (self.frame & 1) == 1:
            return

        for e in self.enemies:
            if e[2] <= 0:
                continue

            dx = self.px - e[0]
            dy = self.py - e[1]
            dist2 = dx * dx + dy * dy

            # Contact damage
            if dist2 < 0.20:
                self.lives -= 1
                if self.lives <= 0:
                    global_score = self.score
                    game_over = True
                    return
                # Respawn player (aber Score behalten)
                self.px, self.py = 2.5, 2.5
                return

            # Move toward player
            step = 0.055 + (self.wave * 0.002)
            if step > 0.09:
                step = 0.09

            # axis-priority move
            if abs(dx) > abs(dy):
                sx = step if dx > 0 else -step
                nx = e[0] + sx
                if not self._is_wall_pos(nx, e[1]):
                    e[0] = nx
                else:
                    sy = step if dy > 0 else -step
                    ny = e[1] + sy
                    if not self._is_wall_pos(e[0], ny):
                        e[1] = ny
            else:
                sy = step if dy > 0 else -step
                ny = e[1] + sy
                if not self._is_wall_pos(e[0], ny):
                    e[1] = ny
                else:
                    sx = step if dx > 0 else -step
                    nx = e[0] + sx
                    if not self._is_wall_pos(nx, e[1]):
                        e[0] = nx

    def _render(self):
        """Render the 3D view using raycasting into the map and draw sprites."""
        # background sky/floor
        # Intentionally no display.clear(): we always redraw the full playfield
        # background first. With the buffered framebuffer this means only pixels
        # that actually changed (walls/sprites/movement) are flushed.
        half = self.PLAY_H // 2
        draw_rectangle(0, 0, WIDTH - 1, half - 1, 0, 0, 25)  # sky
        draw_rectangle(0, half, WIDTH - 1, self.PLAY_H - 1, 18, 10, 0)  # floor

        # ray angles: fixedpoint, damit FOV/64 sauber läuft
        angle_step_fp = (self.FOV << 16) // WIDTH
        ang_fp = ((self.ang - self.HALF_FOV) & 255) << 16

        for x in range(WIDTH):
            ray_ang = (ang_fp >> 16) & 255
            ang_fp += angle_step_fp

            dist, side = self._cast_ray(ray_ang)
            self.zbuf[x] = dist

            line_h = int(self.PLAY_H / (dist + 1e-6))
            if line_h < 1:
                line_h = 1
            if line_h > self.PLAY_H:
                line_h = self.PLAY_H

            start = (self.PLAY_H - line_h) // 2
            end = start + line_h - 1
            if start < 0:
                start = 0
            if end >= self.PLAY_H:
                end = self.PLAY_H - 1

            # simple shading
            b = 220 - int(dist * 18)
            if b < 40:
                b = 40
            if side == 1:
                b = (b * 3) // 4

            draw_rectangle(x, start, x, end, b, b, b)

        # sprites (enemies) als billboards
        # sortiert nach Entfernung (weit -> nah)
        alive = []
        for e in self.enemies:
            if e[2] > 0:
                dx = e[0] - self.px
                dy = e[1] - self.py
                d = math.sqrt(dx * dx + dy * dy)
                alive.append((d, e))
        alive.sort(reverse=True)

        for dist, e in alive:
            dx = e[0] - self.px
            dy = e[1] - self.py
            a = self._angle_to_units(dx, dy)
            delta = self._angle_delta(a, self.ang)
            if abs(delta) > self.HALF_FOV:
                continue

            sx = int((delta + self.HALF_FOV) * WIDTH / self.FOV)
            if sx < 0 or sx >= WIDTH:
                continue

            # sprite size
            sh = int(self.PLAY_H / (dist + 1e-6))
            if sh < 2:
                sh = 2
            if sh > self.PLAY_H:
                sh = self.PLAY_H
            sw = sh // 3
            if sw < 1:
                sw = 1
            if sw > 6:
                sw = 6

            y0 = (self.PLAY_H - sh) // 2
            y1 = y0 + sh - 1

            x0 = sx - sw // 2
            x1 = x0 + sw - 1

            # draw with z-buffer test per column
            for xx in range(x0, x1 + 1):
                if 0 <= xx < WIDTH and dist < self.zbuf[xx]:
                    # hp color
                    if e[2] >= 2:
                        col = (255, 0, 255)
                    else:
                        col = (255, 60, 60)
                    draw_rectangle(xx, y0, xx, y1, col[0], col[1], col[2])

        # minimap overlay (16x16)
        draw_rectangle(0, 0, self.MAP_W + 1, self.MAP_H + 1, 0, 0, 0)
        sp = display.set_pixel
        for my in range(self.MAP_H):
            row = self.MAP[my]
            for mx in range(self.MAP_W):
                if row[mx] == 35:
                    sp(mx, my, 0, 0, 160)
        sp(int(self.px), int(self.py), 0, 255, 0)
        # direction hint
        dc, ds = self._cos_sin(self.ang)
        ax = int(self.px + dc * 0.7)
        ay = int(self.py - ds * 0.7)
        if 0 <= ax < self.MAP_W and 0 <= ay < self.MAP_H:
            sp(ax, ay, 0, 200, 0)
        for e in self.enemies:
            if e[2] > 0:
                ex = int(e[0])
                ey = int(e[1])
                if 0 <= ex < self.MAP_W and 0 <= ey < self.MAP_H:
                    sp(ex, ey, 255, 0, 0)

        # lives indicator (oben rechts)
        for i in range(self.lives):
            x = WIDTH - 2 - i * 3
            y = 1
            if 0 <= x < WIDTH and 0 <= y < self.PLAY_H:
                sp(x, y, 0, 255, 0)

        # crosshair
        cx = WIDTH // 2
        cy = self.PLAY_H // 2
        if 0 <= cx < WIDTH and 0 <= cy < self.PLAY_H:
            sp(cx, cy, 255, 255, 255)

        display_score_and_time(self.score)

    def main_loop(self, joystick):
        """Main game loop for the raycaster mini-game (handles input and rendering)."""
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        display_score_and_time(0)

        while not game_over:
            try:
                c_button, z_button = joystick.nunchuck.buttons()
                if c_button:
                    return

                now = ticks_ms()
                if ticks_diff(now, self.last_frame) < self.frame_ms:
                    sleep_ms(2)
                    continue
                self.last_frame = now
                self.frame += 1

                # input
                d = joystick.read_direction(
                    [
                        JOYSTICK_UP,
                        JOYSTICK_DOWN,
                        JOYSTICK_LEFT,
                        JOYSTICK_RIGHT,
                        JOYSTICK_UP_LEFT,
                        JOYSTICK_UP_RIGHT,
                        JOYSTICK_DOWN_LEFT,
                        JOYSTICK_DOWN_RIGHT,
                    ],
                    debounce=False,
                )

                # rotate
                rot = 0
                if d in (JOYSTICK_LEFT, JOYSTICK_UP_LEFT, JOYSTICK_DOWN_LEFT):
                    rot = -5
                elif d in (JOYSTICK_RIGHT, JOYSTICK_UP_RIGHT, JOYSTICK_DOWN_RIGHT):
                    rot = +5
                if rot:
                    self.ang = (self.ang + rot) & 255

                # move
                move = 0.0
                if d in (JOYSTICK_UP, JOYSTICK_UP_LEFT, JOYSTICK_UP_RIGHT):
                    move = 0.12
                elif d in (JOYSTICK_DOWN, JOYSTICK_DOWN_LEFT, JOYSTICK_DOWN_RIGHT):
                    move = -0.10

                if move != 0.0:
                    c, s = self._cos_sin(self.ang)
                    dx = c * move
                    dy = -s * move

                    nx = self.px + dx
                    ny = self.py + dy

                    # axis-separate collision
                    if not self._is_wall_pos(nx, self.py):
                        self.px = nx
                    if not self._is_wall_pos(self.px, ny):
                        self.py = ny

                # shoot
                if self.shot_cd > 0:
                    self.shot_cd -= 1
                if z_button and self.shot_cd == 0:
                    self._shoot()
                    self.shot_cd = 10

                # enemy update / collision
                self._update_enemies()
                if game_over:
                    global_score = self.score
                    return

                # next wave?
                alive = 0
                for e in self.enemies:
                    if e[2] > 0:
                        alive += 1
                if alive == 0:
                    self.score += 100
                    self.wave += 1
                    self._spawn_wave(self.wave)

                global_score = self.score
                self._render()

                if (self.frame % 80) == 0:
                    gc.collect()

            except RestartProgram:
                return


# ======================================================================
#                              MENUS / FLOW
# ======================================================================


class GameOverMenu:
    """Simple menu shown after losing; choose retry or return to menu."""

    def __init__(self, joystick, score, best, best_name="---"):
        """Initialize the GameOver menu with scores and joystick reference."""
        self.joystick = joystick
        self.score = score
        self.best = best
        self.best_name = best_name
        self.opts = ["RETRY", "MENU"]

    def run(self):
        """Show menu and return selected option index (0=retry,1=menu)."""
        idx = 0
        prev = -1
        last_move = ticks_ms()
        move_delay = 160

        while True:
            now = ticks_ms()

            if idx != prev:
                prev = idx
                display.clear()
                draw_text(10, 8, "LOST", 255, 20, 20)

                # score HUD line
                draw_rectangle(0, PLAY_HEIGHT, WIDTH - 1, HEIGHT - 1, 0, 0, 0)
                draw_text_small(1, PLAY_HEIGHT, str(self.score), 255, 255, 255)
                bn = self.best_name if isinstance(self.best_name, str) else "---"
                bs = "B" + str(self.best) + " " + bn
                draw_text_small(WIDTH - len(bs) * 6, 1, bs, 140, 140, 140)

                for i, o in enumerate(self.opts):
                    col = (255, 255, 255) if i == idx else (111, 111, 111)
                    draw_text(8, 28 + i * 15, o, *col)

            if ticks_diff(now, last_move) > move_delay:
                d = self.joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN])
                if d == JOYSTICK_UP and idx > 0:
                    idx -= 1
                    last_move = now
                elif d == JOYSTICK_DOWN and idx < len(self.opts) - 1:
                    idx += 1
                    last_move = now

            if self.joystick.is_pressed():
                while self.joystick.is_pressed():
                    sleep_ms(10)
                return self.opts[idx]

            sleep_ms(30)


class GameSelect:
    """Main game selector menu; choose a game to play with joystick."""

    def __init__(self):
        """Build the main game selection menu with joystick and highscore storage."""
        self.joystick = Joystick()
        self.highscores = HighScores()
        self.game_classes = {
            "2048": Game2048,  # sliding-tile puzzle
            "ASTRD": AsteroidGame,  # ship vs asteroids shooter
            "BRKOUT": BreakoutGame,  # brick-breaking arcade
            "CAVEFL": CaveFlyGame,  # cave flying runner
            "DEMOS": DemosGame,  # demo animations & automata
            "DOOMLT": DoomLiteGame,  # simple raycaster shooter
            "FLAPPY": FlappyGame,  # one-button flappy clone
            "LANDER": LunarLanderGame,  # lunar lander physics
            "LOCO": LocoMotionGame,  # locomotive puzzle
            "MAZE": MazeGame,  # maze exploration
            "MBALL": MonkeyBallLiteGame,  # rolling-ball mini-game
            "PACMAN": PacmanGame,  # classic maze & ghosts
            "PITFAL": PitfallGame,  # side-scrolling platformer
            "PONG": PongGame,  # paddle vs paddle
            "QIX": QixGame,  # territory-capturing arcade
            "REVRS": OthelloGame,  # Othello / Reversi board game
            "RTYPE": RTypeGame,  # side-scrolling shooter
            "SIMON": SimonGame,  # memory color-sequence game
            "SNAKE": SnakeGame,  # classic snake growth game
            "SOKO": SokobanGame,  # crate-pushing puzzles
            "TETRIS": TetrisGame,  # falling-block puzzle
            "UFODEF": UFODefenseGame,  # missile-defense mini-game
        }
        keys = sorted(self.game_classes.keys())
        if "DEMOS" in keys:
            keys.remove("DEMOS")
            keys.insert(0, "DEMOS")
        self.sorted_games = keys

    def run_game_selector(self):
        """Show the game list and return the selected game's class when chosen."""
        games = self.sorted_games
        selected = 0
        top = 0
        prev = -1
        view = 4
        last_move = ticks_ms()
        move_delay = 140

        while True:
            now = ticks_ms()

            if selected != prev:
                prev = selected
                display.clear()
                for i in range(view):
                    gi = top + i
                    if gi >= len(games):
                        break
                    name = games[gi]
                    col = (255, 255, 255) if gi == selected else (111, 111, 111)
                    draw_text(4, 5 + i * 15, name, *col)

                    hs = self.highscores.best(name)
                    hn = self.highscores.best_name(name)
                    hs_str = str(hs) + " " + str(hn)
                    draw_text_small(
                        WIDTH - len(hs_str) * 6, 5 + i * 15 + 8, hs_str, 120, 120, 0
                    )

            if ticks_diff(now, last_move) > move_delay:
                d = self.joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN])
                if d == JOYSTICK_UP and selected > 0:
                    selected -= 1
                    if selected < top:
                        top -= 1
                    last_move = now
                elif d == JOYSTICK_DOWN and selected < len(games) - 1:
                    selected += 1
                    if selected > top + view - 1:
                        top += 1
                    last_move = now

            if self.joystick.is_pressed():
                while self.joystick.is_pressed():
                    sleep_ms(10)
                return games[selected]

            sleep_ms(30)

    def run(self):
        """Main loop: select games, run them and handle highscores flow."""
        global game_over, global_score

        while True:
            game_name = self.run_game_selector()

            # retry loop
            while True:
                game_over = False
                global_score = 0

                game: Any = self.game_classes[game_name]()
                game.main_loop(self.joystick)

                if game_over:
                    best = self.highscores.best(game_name)
                    best_name = self.highscores.best_name(game_name)
                    if global_score > best:
                        initials = InitialsEntryMenu(
                            self.joystick, global_score, best, best_name
                        ).run()
                        if initials:
                            self.highscores.update(game_name, global_score, initials)
                    # refresh best name in case initials were saved
                    best = self.highscores.best(game_name)
                    best_name = self.highscores.best_name(game_name)
                    choice = GameOverMenu(
                        self.joystick, global_score, best, best_name
                    ).run()
                    if choice == "RETRY":
                        continue
                    else:
                        break
                else:
                    break

    async def run_game_selector_async(self):
        """Async version of `run_game_selector` for pygbag/browser.

        This yields to the browser event loop using `asyncio.sleep(0)`
        instead of blocking `sleep_ms()` so the page remains responsive.
        """
        import asyncio

        games = self.sorted_games
        selected = 0
        top = 0
        prev = -1
        view = 4
        last_move = ticks_ms()
        move_delay = 140

        while True:
            now = ticks_ms()

            if selected != prev:
                prev = selected
                display.clear()
                for i in range(view):
                    gi = top + i
                    if gi >= len(games):
                        break
                    name = games[gi]
                    col = (255, 255, 255) if gi == selected else (111, 111, 111)
                    draw_text(4, 5 + i * 15, name, *col)

                    hs = self.highscores.best(name)
                    hn = self.highscores.best_name(name)
                    hs_str = str(hs) + " " + str(hn)
                    draw_text_small(
                        WIDTH - len(hs_str) * 6, 5 + i * 15 + 8, hs_str, 120, 120, 0
                    )

            if ticks_diff(now, last_move) > move_delay:
                d = self.joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN])
                if d == JOYSTICK_UP and selected > 0:
                    selected -= 1
                    if selected < top:
                        top -= 1
                    last_move = now
                elif d == JOYSTICK_DOWN and selected < len(games) - 1:
                    selected += 1
                    if selected > top + view - 1:
                        top += 1
                    last_move = now

            if self.joystick.is_pressed():
                while self.joystick.is_pressed():
                    await asyncio.sleep(0.01)
                return games[selected]

            # cooperative yield for browser
            await asyncio.sleep(0.03)

    async def run_async(self):
        """Async wrapper around `run()` to keep browser responsive.

        Note: individual games' `main_loop` are synchronous; this wrapper
        focuses on making the menu cooperative. Games still run in their
        sync form and may block the event loop until they yield via
        `sleep_ms()`/display flushes.
        """
        import asyncio

        global game_over, global_score

        while True:
            game_name = await self.run_game_selector_async()

            # retry loop
            while True:
                game_over = False
                global_score = 0

                try:
                    game: Any = self.game_classes[game_name]()
                except Exception as e:
                    print("Error instantiating game:", e)
                    try:
                        import traceback

                        traceback.print_exc()
                    except Exception:
                        pass
                    break

                # let the browser render before entering game
                try:
                    await asyncio.sleep(0)
                except Exception:
                    pass

                # Attach a generic async wrapper to games that don't provide
                # `main_loop_async` so we can run them cooperatively via
                # `asyncio.to_thread` where supported. This avoids adding
                # per-game async methods across the codebase.
                try:
                    import types

                    if not hasattr(game, "main_loop_async"):

                        async def _auto_main_loop_async(self, joystick):
                            try:
                                await asyncio.to_thread(self.main_loop, joystick)
                            except Exception:
                                # Threading might be unsupported in WASM; fall
                                # back to synchronous call (may block).
                                try:
                                    self.main_loop(joystick)
                                except RestartProgram:
                                    raise
                                except Exception as e:
                                    print("Error during game.main_loop (fallback):", e)
                                    try:
                                        import traceback

                                        traceback.print_exc()
                                    except Exception:
                                        pass

                        # dynamic attribute assigned for runtime convenience;
                        # static analyzers may warn about attributes created
                        # outside __init__ — silence that here.
                        # pylint: disable=attribute-defined-outside-init
                        game.main_loop_async = types.MethodType(
                            _auto_main_loop_async, game
                        )
                except Exception:
                    pass

                try:
                    # If the game provides an async main loop, prefer that
                    # so the browser event loop stays responsive without
                    # relying on threads.
                    if hasattr(game, "main_loop_async"):
                        try:
                            await game.main_loop_async(self.joystick)
                        except RestartProgram:
                            raise
                        except Exception as e:
                            print("Error during game.main_loop_async:", e)
                            try:
                                import traceback

                                traceback.print_exc()
                            except Exception:
                                pass
                    else:
                        # Prefer running the blocking game loop in a thread so
                        # the asyncio event loop stays responsive in the browser.
                        # `asyncio.to_thread` will raise on platforms where threads
                        # are unsupported (WASM without pthreads); in that case we
                        # fall back to calling the blocking loop synchronously.
                        try:
                            await asyncio.to_thread(game.main_loop, self.joystick)
                        except Exception:
                            # If threading is unsupported or fails, fall back.
                            try:
                                game.main_loop(self.joystick)
                            except RestartProgram:
                                raise
                            except Exception as e:
                                print("Error during game.main_loop (sync fallback):", e)
                                try:
                                    import traceback

                                    traceback.print_exc()
                                except Exception:
                                    pass
                except RestartProgram:
                    # bubble up restart to outer async_main
                    raise
                except Exception as e:
                    print("Error running game in thread:", e)
                    try:
                        import traceback

                        traceback.print_exc()
                    except Exception:
                        pass

                if game_over:
                    best = self.highscores.best(game_name)
                    best_name = self.highscores.best_name(game_name)
                    if global_score > best:
                        try:
                            menu = InitialsEntryMenu(
                                self.joystick, global_score, best, best_name
                            )
                            try:
                                initials = await asyncio.to_thread(menu.run)
                            except Exception:
                                try:
                                    loop = asyncio.get_event_loop()
                                    initials = await loop.run_in_executor(None, menu.run)
                                except Exception:
                                    try:
                                        initials = menu.run()
                                    except Exception:
                                        initials = None
                        except Exception:
                            initials = None
                        if initials:
                            self.highscores.update(game_name, global_score, initials)
                    # refresh best name in case initials were saved
                    best = self.highscores.best(game_name)
                    best_name = self.highscores.best_name(game_name)
                    try:
                        gomenu = GameOverMenu(
                            self.joystick, global_score, best, best_name
                        )
                        try:
                            choice = await asyncio.to_thread(gomenu.run)
                        except Exception:
                            try:
                                loop = asyncio.get_event_loop()
                                choice = await loop.run_in_executor(None, gomenu.run)
                            except Exception:
                                try:
                                    choice = gomenu.run()
                                except Exception:
                                    choice = "MENU"
                    except Exception:
                        choice = "MENU"
                    if choice == "RETRY":
                        continue
                    else:
                        break
                else:
                    break


# ---------- Main ----------
def main():
    """
    Application entry point.

    Performs runtime initialization (garbage collection, display startup,
    optional buffered framebuffer initialization), clears the screen and
    shows the initial HUD. Binds commonly used runtime helpers into any
    optional game modules so they can use shared globals, then enters the
    main game-selection loop. Handles `RestartProgram` to reset to the
    top-level menu and displays a simple error marker for unexpected
    exceptions before returning to the menu.
    """
    try:
        gc.collect()
    except Exception:
        pass
    _boot_log("before display.start")
    display.start()
    _boot_log("after display.start")
    # After hub75 has allocated its internal buffers, we can try to enable
    # the optional software framebuffer diff layer.
    try:
        init_buffered_display()
    except Exception:
        pass
    display.clear()
    display_score_and_time(0, force=True)
    try:
        sleep_ms(0)
    except Exception:
        pass

    # Bind runtime symbols into optional game modules so they can use globals
    def _bind_mod(m):
        """
        Inject common runtime symbols into the provided module `m`.

        This allows optional or inlined game modules to reference the
        shared display, drawing helpers, timing functions and constants
        without importing the main application directly.
        """
        if not m:
            return
        try:
            m.display = display
            m.draw_text = draw_text
            m.draw_rectangle = draw_rectangle
            m.display_score_and_time = display_score_and_time
            m.ticks_ms = ticks_ms
            m.ticks_diff = ticks_diff
            m.sleep_ms = sleep_ms
            m.WIDTH = WIDTH
            m.PLAY_HEIGHT = PLAY_HEIGHT
            m.JOYSTICK_UP = JOYSTICK_UP
            m.JOYSTICK_DOWN = JOYSTICK_DOWN
            m.JOYSTICK_LEFT = JOYSTICK_LEFT
            m.JOYSTICK_RIGHT = JOYSTICK_RIGHT
            m.JOYSTICK_UP_LEFT = JOYSTICK_UP_LEFT
            m.JOYSTICK_UP_RIGHT = JOYSTICK_UP_RIGHT
            m.JOYSTICK_DOWN_LEFT = JOYSTICK_DOWN_LEFT
            m.JOYSTICK_DOWN_RIGHT = JOYSTICK_DOWN_RIGHT
            m.gc = gc
        except Exception:
            pass

    _bind_mod(mod_2048)

    while True:
        try:
            GameSelect().run()
        except RestartProgram:
            display.clear()
            display_score_and_time(0, force=True)
            continue
        except Exception as e:
            # Failsafe: show simple error marker and reset to menu
            print("Error:", e)
            display.clear()
            draw_text(1, 20, "ERR", 255, 0, 0)
            sleep_ms(800)
            display.clear()
            maybe_collect(1)


# Pygbag async wrapper for browser compatibility
async def async_main():
    """Async entrypoint for pygbag/web: initialize hardware and run menu."""
    import asyncio

    try:
        gc.collect()
    except Exception:
        pass
    _boot_log("before display.start")
    display.start()
    _boot_log("after display.start")
    # After hub75 has allocated its internal buffers, we can try to enable
    # the optional software framebuffer diff layer.
    try:
        init_buffered_display()
    except Exception:
        pass
    display.clear()
    display_score_and_time(0, force=True)

    # Early debug frame: show a visible marker so we can tell the app
    # reached this point in the browser before entering the main menu.
    try:
        print("DEBUG: display started, drawing INIT OK")
        # draw a simple INIT message and flush to the screen
        try:
            draw_text(10, 20, "INIT OK", 255, 200, 0)
        except Exception:
            # draw_text may not be available in some rare cases; fallback
            try:
                display.set_pixel(1, 1, 255, 255, 0)
            except Exception:
                pass
        try:
            # ensure the frame is presented and give browser a moment
            if hasattr(display, "show"):
                display.show()
        except Exception:
            pass
    except Exception:
        pass
    # yield once so the browser can render the debug frame
    try:
        await asyncio.sleep(0)
    except Exception:
        pass

    # Bind optional game modules (same as in main)
    def _bind_mod_async(m):
        """Bind shared display and helper symbols into optional modules (async)."""
        if not m:
            return
        try:
            m.display = display
            m.draw_text = draw_text
            m.draw_rectangle = draw_rectangle
            m.display_score_and_time = display_score_and_time
            m.ticks_ms = ticks_ms
            m.ticks_diff = ticks_diff
            m.sleep_ms = sleep_ms
            m.WIDTH = WIDTH
            m.PLAY_HEIGHT = PLAY_HEIGHT
            m.JOYSTICK_UP = JOYSTICK_UP
            m.JOYSTICK_DOWN = JOYSTICK_DOWN
            m.JOYSTICK_LEFT = JOYSTICK_LEFT
            m.JOYSTICK_RIGHT = JOYSTICK_RIGHT
            m.JOYSTICK_UP_LEFT = JOYSTICK_UP_LEFT
            m.JOYSTICK_UP_RIGHT = JOYSTICK_UP_RIGHT
            m.JOYSTICK_DOWN_LEFT = JOYSTICK_DOWN_LEFT
            m.JOYSTICK_DOWN_RIGHT = JOYSTICK_DOWN_RIGHT
            m.gc = gc
        except Exception:
            pass

    _bind_mod_async(mod_2048)

    while True:
        try:
            print("DEBUG: about to instantiate GameSelect and run menu")
            gs = GameSelect()
            try:
                # Prefer async run in pygbag environment so the menu yields
                if IS_PYGBAG:
                    await gs.run_async()
                else:
                    gs.run()
            except RestartProgram:
                display.clear()
                display_score_and_time(0, force=True)
                await asyncio.sleep(0)
                continue
        except Exception as e:
            # Failsafe: print and show full traceback, then reset to menu
            print("Error during GameSelect/run:", e)
            try:
                import traceback

                traceback.print_exc()
            except Exception:
                pass
            try:
                display.clear()
                draw_text(1, 20, "ERR", 255, 0, 0)
                await asyncio.sleep(0.8)
                display.clear()
            except Exception:
                pass
            maybe_collect(1)
        # Yield to browser event loop after each game loop iteration
        try:
            await asyncio.sleep(0)
        except Exception:
            pass


if __name__ == "__main__":
    if IS_PYGBAG:
        import asyncio

        asyncio.run(async_main())
    else:
        main()
