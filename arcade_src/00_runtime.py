"""
Main application module for the DIY Arcade Machine.
Contains all game engines, menu logic, and hardware abstraction layer (HAL)
for running the game console on both CPytthon (emulator) and MicroPython.

Mainly manages the frame buffer, UI updates, state transitions, and high scores.
"""

import gc
import math
import random
import sys
import time

try:
    import importlib.util as _importlib_util
except ImportError:
    _importlib_util = None
try:
    import uos as _os
except ImportError:
    import os as _os
try:
    _os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    if getattr(sys, "platform", "") == "emscripten":
        _os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
except Exception:
    pass

# ---------- Content and target configuration ----------
# Edit this block before copying the application to a target. The empty
# allowlists keep every item; put names in either blocklist to hide them from
# the game menu or demo carousel. Demo game previews use the "G:NAME" form.
#
# Examples:
#   CONFIG_DISABLED_GAMES = ("DOOMLT", "RAYRCR")
#   CONFIG_DISABLED_DEMOS = ("MANDEL", "G:DOOMLT")
#
# Low-resource defaults. Keep debug logging off unless explicitly changed here.
DEBUG_BOOT_LOG = False
CONFIG_LOW_RAM_MODE = False
CONFIG_BUFFERED_DISPLAY = False
CONFIG_ENABLE_HEAVY_GAMES = True
CONFIG_ENABLE_GAME_DEMOS = False
# Empty allowlists mean "all"; blocklists remove names after that.
CONFIG_ENABLED_GAMES = ()
CONFIG_DISABLED_GAMES = ("BTLZON","CENTI","CGOLG","CITY","DIGDUG","DODGE","JOUST","KERBAL","LIGHTS","PICROS","WORMS")  # e.g. ("DOOMLT", "RAYRCR")
CONFIG_ENABLED_DEMOS = ()
CONFIG_DISABLED_DEMOS = ()  # e.g. ("MANDEL", "G:DOOMLT")
CONFIG_FRAME_MS_DEFAULT = 35
FEATURE_TIER = 2


def _boot_log(tag):
    if not DEBUG_BOOT_LOG:
        return
    try:
        # Keep this tiny to reduce chance of further allocations.
        print("BOOT:", tag, gc.mem_free())
    except Exception:
        pass


_boot_log("imports done")


def _name_enabled(name, enabled=(), disabled=()):
    if enabled and name not in enabled:
        return False
    return name not in disabled


def _shuffle_in_place(seq):
    # Fisher-Yates avoids random.shuffle, which some MicroPython builds lack.
    n = len(seq)
    for i in range(n - 1, 0, -1):
        j = random.randint(0, i)
        seq[i], seq[j] = seq[j], seq[i]


# ---------- Runtime detection ----------
# A single module drives three distinct runtimes. Each platform flag below is
# mutually exclusive; add a new platform by extending this block and the HAL
# sections that key off these flags (display/RTC, input, sound, timing).
#   * "micropython" — RP2040/RP2350 driving a HUB75 matrix (real hardware)
#   * "web"         — pygbag / WebAssembly (Emscripten) inside a browser
#   * "desktop"     — CPython + PyGame emulator on a normal computer
try:
    IS_MICROPYTHON = sys.implementation.name == "micropython"
except Exception:
    IS_MICROPYTHON = False

IS_WEB = not IS_MICROPYTHON and getattr(sys, "platform", "") == "emscripten"
IS_DESKTOP = not IS_MICROPYTHON and not IS_WEB

if IS_MICROPYTHON:
    PLATFORM_NAME = "micropython"
elif IS_WEB:
    PLATFORM_NAME = "web"
else:
    PLATFORM_NAME = "desktop"

try:
    import asyncio
except ImportError:
    try:
        import uasyncio as asyncio  # type: ignore
    except ImportError:
        asyncio = None  # type: ignore

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
        return x


WIDTH = const(64)
HEIGHT = const(64)

HUD_HEIGHT = const(6)
PLAY_HEIGHT = const(HEIGHT - HUD_HEIGHT)  # 58

GAME_FLAG_HEAVY = const(1)
FRAMEBUFFER_MIN_FREE_RP2040 = const(110000)
FRAMEBUFFER_MIN_FREE_RP2350 = const(70000)
LOW_RAM_FREE_THRESHOLD = const(95000)


def _mem_free():
    try:
        return gc.mem_free()
    except Exception:
        return 0


def _board_name():
    try:
        return _os.uname().machine.lower()
    except Exception:
        try:
            return sys.platform.lower()
        except Exception:
            return ""


def _detect_feature_tier():
    if not IS_MICROPYTHON:
        return 2
    name = _board_name()
    if "2350" in name or "pico2" in name or "pico 2" in name:
        return 2
    free = _mem_free()
    if free and free < LOW_RAM_FREE_THRESHOLD:
        return 0
    return 1


def refresh_runtime_config():
    global \
        FEATURE_TIER, \
        CONFIG_LOW_RAM_MODE, \
        CONFIG_BUFFERED_DISPLAY, \
        CONFIG_ENABLE_HEAVY_GAMES
    FEATURE_TIER = _detect_feature_tier()
    CONFIG_LOW_RAM_MODE = bool(IS_MICROPYTHON and FEATURE_TIER == 0)
    CONFIG_ENABLE_HEAVY_GAMES = bool((not IS_MICROPYTHON) or FEATURE_TIER >= 1)
    if not IS_MICROPYTHON:
        CONFIG_BUFFERED_DISPLAY = False
        return
    free = _mem_free()
    threshold = (
        FRAMEBUFFER_MIN_FREE_RP2350
        if FEATURE_TIER >= 2
        else FRAMEBUFFER_MIN_FREE_RP2040
    )
    CONFIG_BUFFERED_DISPLAY = bool(free == 0 or free >= threshold)


refresh_runtime_config()

_boot_log("constants")


def sleep_ms(ms):
    try:
        # Try to present pending pixel updates before sleeping.
        # This keeps both HUB75 and the desktop emulator responsive.
        display_flush()
    except Exception:
        pass
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(ms)
    else:
        time.sleep(ms / 1000)


def ticks_ms():
    now = time.ticks_ms() if hasattr(time, "ticks_ms") else int(time.time() * 1000)
    # Desktop: auto-present at ~60 Hz even if the game loop doesn't sleep
    # after drawing (many legacy loops use ticks_ms/ticks_diff for pacing).
    # FrameLoopGame instances manage their own single present at the end of a
    # frame; presenting here as well would scale and flip the whole matrix
    # before the HUD has been drawn.
    if IS_DESKTOP and not _FRAME_PRESENT_MANAGED:
        try:
            last = getattr(ticks_ms, "_last_flush", 0)
            if (now - last) >= 16:
                setattr(ticks_ms, "_last_flush", now)
                display_flush()
        except Exception:
            pass
    return now


def ticks_diff(a, b):
    return time.ticks_diff(a, b) if hasattr(time, "ticks_diff") else (a - b)


def ticks_add(ticks, delta):
    """Add milliseconds while preserving MicroPython tick wraparound."""
    if hasattr(time, "ticks_add"):
        return time.ticks_add(ticks, delta)
    return ticks + delta


_gc_ctr = 0
_FRAME_PRESENT_MANAGED = False


def maybe_collect(period=90):
    global _gc_ctr
    _gc_ctr += 1
    if _gc_ctr >= period:
        _gc_ctr = 0
        gc.collect()


def draw_centered_text_lines(lines, start_y=18, line_height=12, r=255, g=255, b=255):
    for idx, line in enumerate(lines):
        x = (WIDTH - len(line) * 8) // 2
        y = start_y + idx * line_height
        draw_text(x, y, line, r, g, b)


def show_center_message(
    lines,
    start_y=18,
    line_height=12,
    r=255,
    g=255,
    b=255,
    clear=True,
    score=None,
    delay_ms=0,
):
    """Draw centered text lines with optional clear, score update and delay."""
    if clear:
        display.clear()
    draw_centered_text_lines(
        lines, start_y=start_y, line_height=line_height, r=r, g=g, b=b
    )
    if score is not None:
        display_score_and_time(score)
    try:
        display_flush()
    except Exception:
        pass
    if delay_ms > 0:
        sleep_ms(delay_ms)


async def sleep_ms_async(ms):
    """Async-friendly sleep that also presents pending display updates."""
    try:
        display_flush()
    except Exception:
        pass
    if asyncio is None:
        sleep_ms(ms)
        return
    try:
        await asyncio.sleep(ms / 1000.0)
    except Exception:
        sleep_ms(ms)


async def show_center_message_async(
    lines,
    start_y=18,
    line_height=12,
    r=255,
    g=255,
    b=255,
    clear=True,
    score=None,
    delay_ms=0,
):
    """Async version of show_center_message()."""
    if clear:
        display.clear()
    draw_centered_text_lines(
        lines, start_y=start_y, line_height=line_height, r=r, g=g, b=b
    )
    if score is not None:
        display_score_and_time(score)
    try:
        display_flush()
    except Exception:
        pass
    if delay_ms > 0:
        await sleep_ms_async(delay_ms)


def clamp(value, lo, hi):
    """Clamp value to the inclusive [lo, hi] range."""
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def in_bounds(x, y, w=WIDTH, h=PLAY_HEIGHT):
    """Return True when (x, y) is inside 0..w-1 and 0..h-1."""
    return (0 <= x < w) and (0 <= y < h)


def point_in_rect(px, py, rx, ry, rw, rh):
    """Return True when point (px, py) is inside rectangle (rx, ry, rw, rh)."""
    return (rx <= px < (rx + rw)) and (ry <= py < (ry + rh))


def rects_overlap(ax, ay, aw, ah, bx, by, bw, bh):
    """Return True when rectangles A(ax,ay,aw,ah) and B(bx,by,bw,bh) overlap."""
    return (
        (ax < (bx + bw)) and (bx < (ax + aw)) and (ay < (by + bh)) and (by < (ay + ah))
    )


def draw_rect_outline(x1, y1, x2, y2, r, g, b):
    """Draw a one-pixel rectangle outline."""
    draw_rectangle(x1, y1, x2, y1, r, g, b)
    draw_rectangle(x1, y2, x2, y2, r, g, b)
    draw_rectangle(x1, y1, x1, y2, r, g, b)
    draw_rectangle(x2, y1, x2, y2, r, g, b)


def begin_game(score=0):
    """Reset shared game-over state at the start of a playable game."""
    global game_over, global_score, game_result
    game_over = False
    game_result = "LOST"
    global_score = int(score or 0)
    display_score_and_time(global_score, force=True)


def set_game_over_score(score, won=False):
    """Record the final score before returning to the shared game-over flow."""
    global game_over, global_score, game_result
    global_score = int(score or 0)
    game_result = "WON" if won else "LOST"
    game_over = True


def get_context_setting(ctx, key, default=None):
    """Read a per-game setting from the optional game context."""
    if ctx is None:
        return default
    try:
        if isinstance(ctx, dict):
            settings = ctx.get("settings", None)
        else:
            settings = getattr(ctx, "settings", None)
        if isinstance(settings, dict):
            return settings.get(key, default)
    except Exception:
        pass
    return default


async def yield_runtime(delay=0):
    """Yield cooperatively on web/desktop async runtimes; no-op on sync-only builds."""
    if asyncio is None:
        return
    try:
        await asyncio.sleep(delay)
    except Exception:
        pass


def _run_game_loop_sync(frame_ms, loop_fn):
    """Small sync counterpart to _run_game_loop_async for games with frame callbacks."""
    global _FRAME_PRESENT_MANAGED
    last_frame = ticks_ms()
    while True:
        now = ticks_ms()
        if ticks_diff(now, last_frame) < frame_ms:
            # Pacing must not present a static framebuffer every 4 ms.  A
            # frame will be flushed below after the game has actually drawn.
            if hasattr(time, "sleep_ms"):
                time.sleep_ms(4)
            else:
                time.sleep(0.004)
            continue
        last_frame = now
        _FRAME_PRESENT_MANAGED = True
        try:
            keep_running = loop_fn()
            try:
                display_flush()
            except Exception:
                pass
        finally:
            _FRAME_PRESENT_MANAGED = False
        if not keep_running:
            return
        maybe_collect(150)


def reset_menu_display(score=0):
    """Return the matrix to the common menu/HUD baseline after errors or restarts."""
    display.clear()
    display_score_and_time(score, force=True)
    try:
        display_flush()
    except Exception:
        pass


async def _run_game_loop_async(frame_ms, loop_fn):
    """
    Generic async game loop runner with frame pacing for pygbag compatibility.

    Eliminates code duplication across all game main_loop_async() methods by
    centralizing frame pacing, asyncio.sleep() handling, and GC collection logic.
    Provides cooperative multitasking via asyncio.sleep() and frame pacing via
    ticks_ms/ticks_diff. Automatically falls back to sync when asyncio unavailable.

    Usage Example:
    ==========================================
    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)

        # Setup game state
        display.clear()
        self.init_game()
        display_score_and_time(0, force=True)

        # Define one frame of game logic
        def loop_iteration():
            # Handle input
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False  # Exit loop

            # Update and render game
            self.update(joystick)
            self.draw()
            display_score_and_time(self.score)

            return True  # Continue loop

        # Run game with frame pacing (45ms per frame)
        await _run_game_loop_async(45, loop_iteration)
    ==========================================

    Args:
        frame_ms (int): Target frame time in milliseconds (e.g., 45, 35, 60)
        loop_fn (callable): Function to run each frame.
                           Return False to exit loop, True to continue.
                           Should not be async.
    """
    if asyncio is None:
        # Fallback: sync mode (MicroPython on hardware)
        while loop_fn():
            pass
        return

    # Async mode: frame pacing with asyncio.sleep()
    global _FRAME_PRESENT_MANAGED
    last_frame = ticks_ms()
    while True:
        now = ticks_ms()
        if ticks_diff(now, last_frame) < frame_ms:
            await asyncio.sleep(0.005)
            continue
        last_frame = now

        _FRAME_PRESENT_MANAGED = True
        try:
            keep_running = loop_fn()
            try:
                display_flush()
            except Exception:
                pass
            if not keep_running:
                return
        finally:
            _FRAME_PRESENT_MANAGED = False

        try:
            maybe_collect(150)
        except Exception:
            pass


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
    # Desktop (CPython) runtime: emulate HUB75 via PyGame.
    class _DesktopRTC:
        def datetime(self):
            # machine.RTC().datetime():
            # year, month, day, weekday, hour, minute, second, subseconds.
            lt = time.localtime()
            # weekday: MicroPython usually uses 0=Mon..6=Sun
            return (lt[0], lt[1], lt[2], lt[6], lt[3], lt[4], lt[5], 0)

    class _PyGameDisplay:
        def __init__(self, w, h, scale=10):
            self.w = int(w)
            self.h = int(h)
            self.scale = int(scale)
            self._pg = None
            self._screen = None
            self._surface = None
            self._scaled_surface = None
            # pygame.SCALED asks SDL for a renderer. That fails in some
            # pygbag browser runtimes, so web uses the software-scaling path.
            self._use_pygame_scaled = False
            self._inited = False

        def start(self):
            if self._inited:
                return
            try:
                import pygame  # type: ignore
            except Exception as e:
                raise RuntimeError(
                    "PyGame not installed. Install with: pip install pygame-ce"
                ) from e
            self._pg = pygame
            pygame.init()
            try:
                if (
                    _importlib_util is not None
                    and _importlib_util.find_spec("pygame.mixer") is not None
                ):
                    pygame.mixer.quit()
            except Exception:
                pass
            pygame.display.set_caption("DIY Arcade Machine")
            flags = 0
            target = (self.w * self.scale, self.h * self.scale)
            if self._use_pygame_scaled:
                flags = getattr(pygame, "SCALED", 0)
                target = (self.w, self.h)
            # Reuse an existing display surface of the same size so that a
            # loading screen set up by the bootstrap (main.py) is not destroyed
            # by a second pygame.display.set_mode() call (breaks pygbag canvas).
            existing = pygame.display.get_surface()
            if existing is not None and existing.get_size() == target:
                self._screen = existing
            else:
                self._screen = pygame.display.set_mode(target, flags)
            try:
                self._screen.set_colorkey(None)
            except Exception:
                pass
            if self._use_pygame_scaled:
                self._surface = self._screen
                self._scaled_surface = None
            else:
                self._surface = pygame.Surface((self.w, self.h))
                self._scaled_surface = pygame.Surface(target)
            self.clear()
            self.show()
            self._inited = True

        def set_pixel(self, x, y, r, g, b):
            if not self._surface:
                return
            if 0 <= x < self.w and 0 <= y < self.h:
                self._surface.set_at(
                    (int(x), int(y)), (int(r) & 255, int(g) & 255, int(b) & 255)
                )

        def clear(self):
            if self._surface:
                self._surface.fill((0, 0, 0))

        def fill_rect(self, x1, y1, x2, y2, r, g, b):
            if not self._surface or not self._pg:
                return
            self._surface.fill(
                (int(r) & 255, int(g) & 255, int(b) & 255),
                self._pg.Rect(int(x1), int(y1), int(x2 - x1 + 1), int(y2 - y1 + 1)),
            )

        def blit_image(self, image):
            if not self._surface or not self._pg:
                return False
            scaled = self._pg.transform.scale(image, (self.w, self.h))
            self._surface.blit(scaled, (0, 0))
            return True

        def show(self):
            if not self._pg or not self._screen or not self._surface:
                return
            # keep window responsive
            self._pg.event.pump()
            if self._use_pygame_scaled:
                self._pg.display.flip()
                return
            if self._scaled_surface is not None:
                self._pg.transform.scale(
                    self._surface,
                    (self.w * self.scale, self.h * self.scale),
                    self._scaled_surface,
                )
                self._screen.blit(self._scaled_surface, (0, 0))
            else:
                scaled = self._pg.transform.scale(
                    self._surface, (self.w * self.scale, self.h * self.scale)
                )
                self._screen.blit(scaled, (0, 0))
            self._pg.display.flip()

    display = _PyGameDisplay(WIDTH, HEIGHT, scale=10)
    rtc = _DesktopRTC()

# Use the software framebuffer diff layer only on MicroPython/HUB75.
# IMPORTANT: delay allocations until after display.start(), otherwise the
# hub75 driver may fail to allocate its own internal buffers on boot.
USE_BUFFERED_DISPLAY_DESIRED = CONFIG_BUFFERED_DISPLAY
USE_BUFFERED_DISPLAY = False

_boot_log("buffer flags")

# ---------- Framebuffer diff / buffered drawing ----------
# keep a software framebuffer and only push changed pixels to the hardware
_fb_w = WIDTH
_fb_h = HEIGHT
_fb_size = _fb_w * _fb_h * 3
_fb_current = None
_fb_prev = None
_dirty_mask = None
_fb_zero_row = bytes(_fb_w * 3)
_dirty_zero_row = bytes(_fb_w)
_dirty_count = 0
_force_full_flush = False

_boot_log("framebuffer vars")

# keep originals to actually write to the hardware
_display_set_pixel_orig = display.set_pixel
_display_clear_orig = getattr(display, "clear", None)

_boot_log("display refs")


def init_buffered_display():
    """Allocate software framebuffer + hooks after hub75 display is started."""
    global \
        USE_BUFFERED_DISPLAY, \
        USE_BUFFERED_DISPLAY_DESIRED, \
        _fb_current, \
        _fb_prev, \
        _dirty_mask, \
        _dirty_count, \
        _force_full_flush
    refresh_runtime_config()
    USE_BUFFERED_DISPLAY_DESIRED = CONFIG_BUFFERED_DISPLAY
    if USE_BUFFERED_DISPLAY:
        return
    if not USE_BUFFERED_DISPLAY_DESIRED:
        return

    try:
        gc.collect()
    except Exception:
        pass

    free = _mem_free()
    if IS_MICROPYTHON and free:
        threshold = (
            FRAMEBUFFER_MIN_FREE_RP2350
            if FEATURE_TIER >= 2
            else FRAMEBUFFER_MIN_FREE_RP2040
        )
        if free < threshold:
            USE_BUFFERED_DISPLAY = False
            return

    try:
        if _fb_current is None or len(_fb_current) != _fb_size:
            _fb_current = bytearray(_fb_size)
        if _fb_prev is None or len(_fb_prev) != _fb_size:
            _fb_prev = bytearray(_fb_size)
        if _dirty_mask is None or len(_dirty_mask) != (_fb_w * _fb_h):
            _dirty_mask = bytearray(_fb_w * _fb_h)
        _dirty_count = 0
        _force_full_flush = True
    except MemoryError:
        # Not enough contiguous heap for buffering. Keep unbuffered drawing.
        USE_BUFFERED_DISPLAY = False
        return

    # Apply our buffered hooks if the hardware object exposes the expected methods.
    try:
        display.set_pixel = _set_pixel_buf
        display.clear = _clear_buf
        USE_BUFFERED_DISPLAY = True
    except Exception:
        USE_BUFFERED_DISPLAY = False


def _mark_dirty_pixel(px):
    # legacy stub (kept to avoid touching other call-sites)
    global _dirty_count
    if _dirty_mask is not None:
        if _dirty_mask[px] == 0:
            _dirty_count += 1
        _dirty_mask[px] = 1


def _set_pixel_buf(x, y, r, g, b):
    global _dirty_count
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
            if _dirty_mask[pix] == 0:
                _dirty_count += 1
            _dirty_mask[pix] = 1


def _zero_framebuffer(buffer):
    """Clear an RGB framebuffer a row at a time without per-call allocations."""
    if buffer is None:
        return
    row_size = _fb_w * 3
    for offset in range(0, _fb_size, row_size):
        buffer[offset : offset + row_size] = _fb_zero_row


def _clear_buf():
    # Keep software and hardware black baselines synchronized. Games can then
    # redraw only their visible pixels instead of forcing a 4096-pixel scan.
    global _dirty_count, _force_full_flush
    _zero_framebuffer(_fb_current)
    if _dirty_mask is not None:
        for offset in range(0, _fb_w * _fb_h, _fb_w):
            _dirty_mask[offset : offset + _fb_w] = _dirty_zero_row
    _dirty_count = 0
    hardware_cleared = False
    if _display_clear_orig:
        try:
            _display_clear_orig()
            hardware_cleared = True
        except Exception:
            pass
    if hardware_cleared:
        # The physical matrix is black now, so its comparison buffer must be
        # black too. Subsequent drawing marks precisely the pixels to restore.
        _zero_framebuffer(_fb_prev)
        _force_full_flush = False
    else:
        # Without a hardware clear, compare the entire old and new frames so
        # pixels that disappeared are explicitly written as black.
        _force_full_flush = True


def display_flush():
    if not USE_BUFFERED_DISPLAY:
        try:
            if hasattr(display, "show"):
                display.show()
        except Exception:
            pass
        return
    # push changed pixels to the hardware and update prev buffer
    if _fb_current is None or _fb_prev is None or _dirty_mask is None:
        return
    sp = _display_set_pixel_orig
    global _dirty_count, _force_full_flush
    if _force_full_flush:
        pix = 0
        idx = 0
        for y in range(_fb_h):
            for x in range(_fb_w):
                r = _fb_current[idx]
                g = _fb_current[idx + 1]
                b = _fb_current[idx + 2]
                if (
                    _fb_prev[idx] != r
                    or _fb_prev[idx + 1] != g
                    or _fb_prev[idx + 2] != b
                ):
                    try:
                        sp(x, y, r, g, b)
                    except Exception:
                        pass
                    _fb_prev[idx] = r
                    _fb_prev[idx + 1] = g
                    _fb_prev[idx + 2] = b
                _dirty_mask[pix] = 0
                pix += 1
                idx += 3
        _dirty_count = 0
        _force_full_flush = False
    elif _dirty_count:
        pix = 0
        idx = 0
        for y in range(_fb_h):
            for x in range(_fb_w):
                if _dirty_mask[pix]:
                    _dirty_mask[pix] = 0
                    r = _fb_current[idx]
                    g = _fb_current[idx + 1]
                    b = _fb_current[idx + 2]
                    if (
                        _fb_prev[idx] != r
                        or _fb_prev[idx + 1] != g
                        or _fb_prev[idx + 2] != b
                    ):
                        try:
                            sp(x, y, r, g, b)
                        except Exception:
                            pass
                        _fb_prev[idx] = r
                        _fb_prev[idx + 1] = g
                        _fb_prev[idx + 2] = b
                pix += 1
                idx += 3
        _dirty_count = 0
    # Desktop display needs an explicit present; HUB75 hardware does not.
    try:
        if hasattr(display, "show"):
            display.show()
    except Exception:
        pass


# Note: hooks are installed by init_buffered_display() after display.start().


# Helper for games: use this to push changed pixels to the hardware.
def push_frame():
    try:
        display_flush()
    except Exception:
        pass


# Shared helper for playfield-aware rectangles
def draw_play_rect(x, y, w, h, r, g, b):
    # clamp to play area (avoid drawing into HUD)
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


def draw_line(x0, y0, x1, y1, r, g, b):
    """Bresenham line from (x0,y0) to (x1,y1), clipped to the full display."""
    x0 = int(x0)
    y0 = int(y0)
    x1 = int(x1)
    y1 = int(y1)
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    sp = display.set_pixel
    while True:
        if 0 <= x0 < WIDTH and 0 <= y0 < HEIGHT:
            sp(x0, y0, r, g, b)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def _draw_line_wrapped(start, end, color):
    """Bresenham line with toroidal (modulo) wrapping — used by AsteroidGame."""
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
            sp(x % WIDTH, y % PLAY_HEIGHT, *color)
            err -= dy
            if err < 0:
                y += sy
                err += dx
            x += sx
    else:
        err = dy / 2.0
        while y != y1:
            sp(x % WIDTH, y % PLAY_HEIGHT, *color)
            err -= dx
            if err < 0:
                x += sx
                err += dy
            y += sy
    sp(x % WIDTH, y % PLAY_HEIGHT, *color)


# ---------- Global state ----------
global_score = 0
game_over = False
game_result = "LOST"

# ---------- Colors ----------
COLORS_BRIGHT = [
    (255, 0, 0),  # Red
    (0, 255, 0),  # Green
    (0, 0, 255),  # Blue
    (255, 255, 0),  # Yellow
]
# Pre-computed to avoid list comprehension allocations during import
colors = (
    (255, 0, 0),
    (0, 255, 0),
    (0, 80, 255),
    (255, 235, 0),
)
inactive_colors = (
    (82, 0, 0),
    (0, 82, 0),
    (0, 24, 92),
    (82, 76, 0),
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

# Reuse these immutable direction sets in shared menus and game helpers. This
# avoids rebuilding the same short lists in every input frame.
JOYSTICK_DIRECTIONS_4 = (
    JOYSTICK_UP,
    JOYSTICK_DOWN,
    JOYSTICK_LEFT,
    JOYSTICK_RIGHT,
)
JOYSTICK_DIRECTIONS_8 = JOYSTICK_DIRECTIONS_4 + (
    JOYSTICK_UP_LEFT,
    JOYSTICK_UP_RIGHT,
    JOYSTICK_DOWN_LEFT,
    JOYSTICK_DOWN_RIGHT,
)
JOYSTICK_DIRECTIONS_HORIZONTAL = (JOYSTICK_LEFT, JOYSTICK_RIGHT)
JOYSTICK_DIRECTIONS_VERTICAL = (JOYSTICK_UP, JOYSTICK_DOWN)

_WEB_TOUCH_KEYS = ("up", "down", "left", "right", "x", "space")
_WEB_TOUCH_STATE = None


def _js_prop(obj, name, default=None):
    try:
        return obj[name]
    except Exception:
        try:
            return getattr(obj, name)
        except Exception:
            return default


def _read_web_touch_input():
    global _WEB_TOUCH_STATE
    if not IS_WEB:
        return None
    try:
        import platform  # type: ignore

        state = getattr(platform.window, "DIYArcadeTouchInput", None)
    except Exception:
        return None
    if state is None:
        return None

    presses = _js_prop(state, "presses", None)
    # JS bridge values are copied into one reusable mapping. Allocating twelve
    # dictionary entries every input frame caused avoidable browser GC churn.
    result = _WEB_TOUCH_STATE
    if result is None:
        result = {}
        _WEB_TOUCH_STATE = result
    for key in _WEB_TOUCH_KEYS:
        result[key] = bool(_js_prop(state, key, False))
        try:
            result[key + "_presses"] = int(_js_prop(presses, key, 0) or 0)
        except Exception:
            result[key + "_presses"] = 0
    return result


def play_web_sound(kind, tone=0):
    """Fire a tiny browser-side WebAudio cue when running under pygbag."""
    if not IS_WEB:
        return
    try:
        import platform  # type: ignore

        fn = getattr(platform.window, "DIYArcadeSound", None)
        if fn:
            fn(kind, int(tone or 0))
    except Exception:
        pass


_PYGAME_SOUND_CACHE = {}
_PYGAME_SOUND_FAILED = False
_DESKTOP_SOUND_CACHE = {}
_DESKTOP_SOUND_FAILED = False


def _pygame_sound_bytes(kind, tone, sample_rate=22050):
    """Generate a small chiptune-style PCM cue; no asset file required."""
    if kind == "coin":
        duration = 0.095
    elif kind == "start":
        duration = 0.105
    elif kind == "zap":
        duration = 0.070
    else:
        duration = 0.055

    count = int(sample_rate * duration)
    data = bytearray(count * 2)
    tone = int(tone or 0)
    base = 180 + (tone % 11) * 18
    seed = (tone * 1103515245 + len(str(kind)) * 97) & 0x7FFFFFFF

    # The mixer buffer is signed 16-bit for broad PyGame compatibility, but the
    # waveform is deliberately quantized and square/noise based for an 8-bit feel.
    for i in range(count):
        t = i / sample_rate
        env = 1.0 - (i / count)
        if kind == "coin":
            freq = 660 if i < count // 2 else 940
            wave = 1.0 if math.sin(2.0 * math.pi * freq * t) >= 0 else -1.0
        elif kind == "start":
            step = (i * 3) // count
            freq = 220 + (tone % 4) * 35 + step * 110
            wave = 1.0 if math.sin(2.0 * math.pi * freq * t) >= 0 else -1.0
        elif kind == "bounce":
            freq = 260 + (tone % 5) * 44
            wave = 1.0 if math.sin(2.0 * math.pi * freq * t) >= 0 else -1.0
        elif kind == "ping":
            freq = base + 520
            tri = 2.0 * abs(2.0 * ((freq * t) - int(freq * t + 0.5))) - 1.0
            wave = tri
        elif kind == "zap":
            freq = 220.0 - 120.0 * (i / count)
            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
            noise = ((seed >> 16) & 255) / 127.5 - 1.0
            pulse = 1.0 if math.sin(2.0 * math.pi * freq * t) >= 0 else -1.0
            wave = pulse * 0.65 + noise * 0.35
        else:
            freq = 360
            wave = 1.0 if math.sin(2.0 * math.pi * freq * t) >= 0 else -1.0

        quantized = int(max(-1.0, min(1.0, wave * env)) * 7) / 7.0
        sample = int(quantized * 9500)
        if sample < 0:
            sample += 65536
        j = i * 2
        data[j] = sample & 255
        data[j + 1] = (sample >> 8) & 255
    return bytes(data)


def _pygame_mixer_module():
    """Return pygame.mixer only when the optional mixer module exists."""
    try:
        if _importlib_util is None or _importlib_util.find_spec("pygame.mixer") is None:
            return None
        import pygame  # type: ignore

        return getattr(pygame, "mixer", None)
    except Exception:
        return None


def play_pygame_sound(kind, tone=0):
    """Play a procedurally generated cue on desktop PyGame."""
    global _PYGAME_SOUND_FAILED
    if not IS_DESKTOP or _PYGAME_SOUND_FAILED:
        return False
    try:
        mixer = _pygame_mixer_module()
        if mixer is None:
            _PYGAME_SOUND_FAILED = True
            return False
        if not mixer.get_init():
            mixer.init(frequency=22050, size=-16, channels=1, buffer=256)
        key = (str(kind), int(tone or 0))
        snd = _PYGAME_SOUND_CACHE.get(key)
        if snd is None:
            snd = mixer.Sound(buffer=_pygame_sound_bytes(key[0], key[1]))
            _PYGAME_SOUND_CACHE[key] = snd
        snd.play()
        return True
    except Exception:
        _PYGAME_SOUND_FAILED = True
        return False


def _desktop_sound_wav_path(kind, tone):
    """Create/cache a temporary WAV for native desktop fallback players."""
    key = (str(kind), int(tone or 0))
    path = _DESKTOP_SOUND_CACHE.get(key)
    if path:
        return path
    try:
        import tempfile
        import wave

        base = _os.path.join(tempfile.gettempdir(), "diy_arcade_sfx")
        try:
            _os.makedirs(base)
        except Exception:
            pass
        path = _os.path.join(base, "sfx_%s_%d.wav" % (key[0], key[1]))
        if not _os.path.exists(path):
            with wave.open(path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(22050)
                wf.writeframes(_pygame_sound_bytes(key[0], key[1]))
        _DESKTOP_SOUND_CACHE[key] = path
        return path
    except Exception:
        return None


def play_native_desktop_sound(kind, tone=0):
    """Fallback when pygame.mixer is unavailable; stores temp WAVs outside repo."""
    global _DESKTOP_SOUND_FAILED
    if not IS_DESKTOP or _DESKTOP_SOUND_FAILED:
        return False
    try:
        import shutil
        import subprocess

        path = _desktop_sound_wav_path(kind, tone)
        if not path:
            _DESKTOP_SOUND_FAILED = True
            return False
        if sys.platform == "darwin":
            cmd = ["afplay", path]
        elif sys.platform.startswith("linux"):
            player = shutil.which("paplay") or shutil.which("aplay")
            if not player:
                _DESKTOP_SOUND_FAILED = True
                return False
            cmd = [player, path]
        elif sys.platform.startswith("win"):
            import winsound

            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            return True
        else:
            _DESKTOP_SOUND_FAILED = True
            return False
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        _DESKTOP_SOUND_FAILED = True
        return False


def play_sound(kind, tone=0):
    """Cross-runtime sound hook: WebAudio in pygbag, procedural PyGame on desktop."""
    play_web_sound(kind, tone)
    if IS_DESKTOP and not play_pygame_sound(kind, tone):
        play_native_desktop_sound(kind, tone)


def direction_to_delta(direction, default_dx=0, default_dy=0):
    """Map a four-way joystick direction to ``(dx, dy)`` or the defaults."""
    if direction == JOYSTICK_UP:
        return 0, -1
    if direction == JOYSTICK_DOWN:
        return 0, 1
    if direction == JOYSTICK_LEFT:
        return -1, 0
    if direction == JOYSTICK_RIGHT:
        return 1, 0
    return default_dx, default_dy


def direction_to_delta_8way(direction, default_dx=0, default_dy=0):
    """Map an eight-way joystick direction to ``(dx, dy)`` or the defaults."""
    if direction == JOYSTICK_UP:
        return 0, -1
    if direction == JOYSTICK_DOWN:
        return 0, 1
    if direction == JOYSTICK_LEFT:
        return -1, 0
    if direction == JOYSTICK_RIGHT:
        return 1, 0
    if direction == JOYSTICK_UP_LEFT:
        return -1, -1
    if direction == JOYSTICK_UP_RIGHT:
        return 1, -1
    if direction == JOYSTICK_DOWN_LEFT:
        return -1, 1
    if direction == JOYSTICK_DOWN_RIGHT:
        return 1, 1
    return default_dx, default_dy


# Neutral analog reading for an idle nunchuck/joystick axis. The threshold
# logic in _read_direction_from_xy() treats this midpoint as "no input".
ANALOG_CENTER = const(128)
ANALOG_MIN = const(0)
ANALOG_MAX = const(255)


def dpad_to_analog(up, down, left, right):
    """Synthesize an analog (x, y) pair from four boolean D-pad inputs.

    Every input backend that lacks a real analog stick (the digital "new"
    nunchuck on hardware, and keyboard/touch on desktop/web) funnels through
    this single helper so the axis encoding stays identical across platforms:
      * x: LEFT -> ANALOG_MIN, RIGHT -> ANALOG_MAX, else centered
      * y: UP   -> ANALOG_MAX, DOWN  -> ANALOG_MIN, else centered (y is
           inverted because the threshold logic expects "up" to be the high end)
    Opposing presses cancel out and leave the axis centered.
    """
    x = ANALOG_CENTER
    y = ANALOG_CENTER
    if left and not right:
        x = ANALOG_MIN
    elif right and not left:
        x = ANALOG_MAX
    if up and not down:
        y = ANALOG_MAX
    elif down and not up:
        y = ANALOG_MIN
    return x, y


# ---------- Fonts ----------
# NOTE: On MicroPython, even defining large dicts at module level can trigger
# MemoryError during import. We define them inside functions (lazy) to avoid
# any allocation until first use.


def _get_char_dict():
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
        "0": "386cc6c6c66c3800",
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
        "A": ["01110", "10001", "11111", "10001", "10001"],
        "B": ["11110", "10001", "11110", "10001", "11110"],
        "C": ["01111", "10000", "10000", "10000", "01111"],
        "D": ["11110", "10001", "10001", "10001", "11110"],
        "E": ["11111", "10000", "11110", "10000", "11111"],
        "F": ["11111", "10000", "11110", "10000", "10000"],
        "G": ["01111", "10000", "10111", "10001", "01110"],
        "H": ["10001", "10001", "11111", "10001", "10001"],
        "I": ["11111", "00100", "00100", "00100", "11111"],
        "J": ["00111", "00010", "00010", "10010", "01100"],
        "K": ["10001", "10010", "11100", "10010", "10001"],
        "L": ["10000", "10000", "10000", "10000", "11111"],
        "M": ["10001", "11011", "10101", "10001", "10001"],
        "N": ["10001", "11001", "10101", "10011", "10001"],
        "O": ["01110", "10001", "10001", "10001", "01110"],
        "P": ["11110", "10001", "11110", "10000", "10000"],
        "Q": ["01110", "10001", "10101", "10010", "01101"],
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
def set_pixel_clipped(x, y, r, g, b):
    if 0 <= x < WIDTH and 0 <= y < HEIGHT:
        display.set_pixel(x, y, r, g, b)


def draw_rectangle(x1, y1, x2, y2, r, g, b):
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
    fill_rect = getattr(display, "fill_rect", None)
    if fill_rect is not None and not USE_BUFFERED_DISPLAY:
        try:
            fill_rect(x1, y1, x2, y2, r, g, b)
            return
        except Exception:
            pass
    sp = display.set_pixel
    for y in range(y1, y2 + 1):
        for x in range(x1, x2 + 1):
            sp(x, y, r, g, b)


def draw_character(x, y, ch, r, g, b):
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
    ox = x
    for ch in text:
        draw_character(ox, y, ch, r, g, b)
        ox += 9


def draw_character_small(x, y, ch, r, g, b):
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
    ox = x
    for ch in text:
        draw_character_small(ox, y, ch, r, g, b)
        ox += 6


# ---------- HUD ----------
_hud_last_ms = 0
_hud_time_str = "00:00"
_hud_last_text = None


def display_score_and_time(score, force=False):
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
    # FrameLoopGame presents exactly once after its complete render pass.
    # Menus and legacy games still flush immediately as before.
    if not _FRAME_PRESENT_MANAGED:
        try:
            display_flush()
        except Exception:
            pass


# ---------- Grid (nibble-packed) for Maze/Qix ----------
GRID_W = WIDTH
GRID_H = PLAY_HEIGHT
grid = None  # lazy-allocated to reduce import-time RAM usage on MicroPython


def initialize_grid():
    global grid
    size = (GRID_W * GRID_H + 1) // 2
    if grid is None or len(grid) != size:
        grid = bytearray(size)
    else:
        for i in range(size):
            grid[i] = 0


def _ensure_grid():
    # Small helper to avoid allocating at import-time.
    global grid
    if grid is None:
        grid = bytearray((GRID_W * GRID_H + 1) // 2)


def get_grid_value(x, y):
    _ensure_grid()
    if x < 0 or x >= GRID_W or y < 0 or y >= GRID_H:
        return 1  # treat out-of-bounds as wall/border
    idx = y * GRID_W + x
    b = grid[idx >> 1]
    if idx & 1:
        return (b >> 4) & 0x0F
    return b & 0x0F


def set_grid_value(x, y, value):
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
    pass


# ---------- Nunchuk / Joystick ----------
NEW_CONTROLLER_SIGNATURE = b"\xa0\x20\x10\x00\xff\xff\x00\x00"

# Axis thresholds for treating a 0-255 analog reading as a directional press.
# A reading below LOW means "low end" (LEFT / DOWN); above HIGH means "high end"
# (RIGHT / UP). The dead zone between LOW and HIGH around ANALOG_CENTER prevents
# jitter from registering as input. Kept as named constants so every axis test
# shares one tuning point instead of scattering magic numbers.
AXIS_LOW = const(100)
AXIS_HIGH = const(150)


def _read_direction_from_xy(x, y, possible_directions):
    """Convert raw joystick axis values (0-255) to a direction constant.

    Diagonals are checked first so that a corner press is never misread as a
    cardinal direction.  Returns None when no threshold is exceeded, or when
    the detected direction is not listed in *possible_directions*.
    """
    x_low = x < AXIS_LOW
    x_high = x > AXIS_HIGH
    y_low = y < AXIS_LOW
    y_high = y > AXIS_HIGH
    if x_low and y_low and JOYSTICK_DOWN_LEFT in possible_directions:
        return JOYSTICK_DOWN_LEFT
    if x_high and y_low and JOYSTICK_DOWN_RIGHT in possible_directions:
        return JOYSTICK_DOWN_RIGHT
    if x_low and y_high and JOYSTICK_UP_LEFT in possible_directions:
        return JOYSTICK_UP_LEFT
    if x_high and y_high and JOYSTICK_UP_RIGHT in possible_directions:
        return JOYSTICK_UP_RIGHT
    if x_low and JOYSTICK_LEFT in possible_directions:
        return JOYSTICK_LEFT
    if x_high and JOYSTICK_RIGHT in possible_directions:
        return JOYSTICK_RIGHT
    if y_low and JOYSTICK_DOWN in possible_directions:
        return JOYSTICK_DOWN
    if y_high and JOYSTICK_UP in possible_directions:
        return JOYSTICK_UP
    return None


def _primary_release_done(joystick, t0, timeout_ms):
    """Shared stop condition for the sync/async release-wait loops below.

    Returns True once every button is released, or once *timeout_ms* has
    elapsed since *t0*. Keeping this in one place means the sync and async
    waiters can never drift apart in behaviour — only their idle/yield call
    differs (blocking sleep on hardware vs. cooperative await in the browser).
    """
    c, z = joystick.read_buttons()
    if not z and not c:
        return True
    return ticks_diff(ticks_ms(), t0) >= timeout_ms


def _wait_for_primary_release(joystick, timeout_ms=1200):
    """Block until all buttons are released or the timeout expires (sync)."""
    t0 = ticks_ms()
    while not _primary_release_done(joystick, t0, timeout_ms):
        sleep_ms(10)


async def _wait_for_primary_release_async(joystick, timeout_ms=1200):
    """Async version: yields to the browser event loop on every iteration."""
    if asyncio is None:
        # No event loop available (bare MicroPython) — fall back to blocking.
        _wait_for_primary_release(joystick, timeout_ms)
        return
    t0 = ticks_ms()
    while not _primary_release_done(joystick, t0, timeout_ms):
        await asyncio.sleep(0.010)


class _JoystickBase:
    """Platform-independent joystick facade.

    Direction debouncing and the public ``read_*`` API live here so every
    platform shares one implementation. Concrete subclasses only provide the
    two raw hooks below; this is the single seam to extend when adding a new
    input backend.

        _read_xy_raw()      -> (x, y) analog pair (0-255), or None if unavailable
        _read_buttons_raw() -> (c_button, z_button); may raise RestartProgram
    """

    _debounce_ms = 70

    def __init__(self):
        self._last_dir = None
        self._last_dir_ms = 0

    def _read_xy_raw(self):
        raise NotImplementedError

    def _read_buttons_raw(self):
        raise NotImplementedError

    def read_direction(self, possible_directions, debounce=True):
        xy = self._read_xy_raw()
        if xy is None:
            return None
        d = _read_direction_from_xy(xy[0], xy[1], possible_directions)
        if not debounce:
            return d
        now = ticks_ms()
        if d is None:
            self._last_dir = None
            return None
        if (
            d == self._last_dir
            and ticks_diff(now, self._last_dir_ms) < self._debounce_ms
        ):
            return None
        self._last_dir = d
        self._last_dir_ms = now
        return d

    def read_buttons(self):
        try:
            return self._read_buttons_raw()
        except RestartProgram:
            raise
        except Exception:
            return False, False

    def read_xy(self):
        xy = self._read_xy_raw()
        return xy if xy is not None else (ANALOG_CENTER, ANALOG_CENTER)

    def is_pressed(self):
        _, z = self.read_buttons()
        return z


# Each platform supplies its own raw input source behind the _JoystickBase API:
#   * MicroPython: real Wii Nunchuk over I2C (analog stick or digital "new" pad)
#   * Desktop/Web: keyboard events plus optional browser touch buttons
# Only the two _read_*_raw hooks differ; all higher-level behaviour is shared.
if IS_MICROPYTHON:

    class Nunchuck:
        def __init__(self, i2c, poll=True, poll_interval=25):
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
            self.i2c.writeto(self.address, b"\x00")
            self.i2c.readfrom_into(self.address, self.buffer)

        def __poll(self):
            now = ticks_ms()
            if self.polling_threshold > 0 and ticks_diff(
                now, self.last_poll
            ) >= self.polling_threshold:
                self.update()
                self.last_poll = now

        def buttons(self):
            self.__poll()
            if not self.is_new_controller:
                c_button = not (self.buffer[5] & 0x02)
                z_button = not (self.buffer[5] & 0x01)
                if c_button and z_button:
                    raise RestartProgram()
                return c_button, z_button

            # Decode only the button bits needed by this API call. The old
            # eight-value tuple was rebuilt again when direction was read.
            b4 = self.buffer[4]
            b5 = self.buffer[5]
            # Map to existing API:
            # - z_button: primary action (A)
            # - c_button: secondary/back (B)
            c_button = not (b5 & 0x40)
            z_button = not (b5 & 0x10)
            # Restart combo on new controller: START + SELECT
            if not (b4 & 0x04) and not (b4 & 0x10):
                raise RestartProgram()
            return c_button, z_button

        def joystick(self):
            self.__poll()
            if not self.is_new_controller:
                return (self.buffer[0], self.buffer[1])

            # New controller does not provide analog joystick in the same way.
            # Synthesize analog-like values from the D-pad so the existing
            # read_direction() threshold logic keeps working.
            b4 = self.buffer[4]
            b5 = self.buffer[5]
            return dpad_to_analog(
                not (b5 & 0x01),
                not (b4 & 0x40),
                not (b5 & 0x02),
                not (b4 & 0x80),
            )

    class Joystick(_JoystickBase):
        def __init__(self):
            super().__init__()
            self.i2c = machine.I2C(0, scl=machine.Pin(21), sda=machine.Pin(20))
            self.nunchuck = None
            self._last_reinit = 0
            self._reinit_nunchuck()

        def _reinit_nunchuck(self):
            self._last_reinit = ticks_ms()
            try:
                self.nunchuck = Nunchuck(self.i2c, poll=True, poll_interval=25)
            except Exception:
                self.nunchuck = None

        def _ensure_nunchuck(self):
            if self.nunchuck is not None:
                return True
            if ticks_diff(ticks_ms(), self._last_reinit) >= 250:
                self._reinit_nunchuck()
            return self.nunchuck is not None

        def _read_xy_raw(self):
            if not self._ensure_nunchuck():
                return None
            try:
                return self.nunchuck.joystick()
            except Exception:
                self.nunchuck = None
                self._ensure_nunchuck()
                return None

        def _read_buttons_raw(self):
            if not self._ensure_nunchuck():
                return False, False
            try:
                return self.nunchuck.buttons()
            except RestartProgram:
                raise
            except Exception:
                self.nunchuck = None
                self._ensure_nunchuck()
                return False, False
else:
    _KEY_LATCH_MS = 90
    _INPUT_POLL_MS = 4

    class Nunchuck:
        # Desktop keyboard input emulating the nunchuck API.
        def __init__(self):
            self._z = False
            self._c = False
            self._held_z = False
            self._held_c = False
            self._x = 128
            self._y = 128
            self._z_until = 0
            self._c_until = 0
            self._left_until = 0
            self._right_until = 0
            self._up_until = 0
            self._down_until = 0
            self._touch_press_counts = {}
            self._last_poll_ms = -1

        def _poll(self):
            try:
                import pygame  # type: ignore
            except Exception:
                return
            now = ticks_ms()
            if (
                self._last_poll_ms >= 0
                and ticks_diff(now, self._last_poll_ms) < _INPUT_POLL_MS
            ):
                return
            self._last_poll_ms = now
            try:
                events = pygame.event.get([pygame.KEYDOWN])
            except Exception:
                events = ()
                try:
                    pygame.event.pump()
                except Exception:
                    pass
            for event in events:
                key = getattr(event, "key", None)
                if key in (pygame.K_z, pygame.K_SPACE, pygame.K_RETURN):
                    self._z_until = now + _KEY_LATCH_MS
                elif key in (pygame.K_x, pygame.K_ESCAPE):
                    self._c_until = now + _KEY_LATCH_MS
                elif key == pygame.K_LEFT:
                    self._left_until = now + _KEY_LATCH_MS
                elif key == pygame.K_RIGHT:
                    self._right_until = now + _KEY_LATCH_MS
                elif key == pygame.K_UP:
                    self._up_until = now + _KEY_LATCH_MS
                elif key == pygame.K_DOWN:
                    self._down_until = now + _KEY_LATCH_MS

            touch = _read_web_touch_input()
            if touch:
                for touch_key, until_attr in (
                    ("left", "_left_until"),
                    ("right", "_right_until"),
                    ("up", "_up_until"),
                    ("down", "_down_until"),
                    ("x", "_c_until"),
                    ("space", "_z_until"),
                ):
                    press_count = touch.get(touch_key + "_presses", 0)
                    if press_count != self._touch_press_counts.get(touch_key, 0):
                        setattr(self, until_attr, now + _KEY_LATCH_MS)
                        self._touch_press_counts[touch_key] = press_count

            keys = pygame.key.get_pressed()
            left = bool(
                keys[pygame.K_LEFT]
                or ticks_diff(self._left_until, now) > 0
                or (touch and touch.get("left"))
            )
            right = bool(
                keys[pygame.K_RIGHT]
                or ticks_diff(self._right_until, now) > 0
                or (touch and touch.get("right"))
            )
            up = bool(
                keys[pygame.K_UP]
                or ticks_diff(self._up_until, now) > 0
                or (touch and touch.get("up"))
            )
            down = bool(
                keys[pygame.K_DOWN]
                or ticks_diff(self._down_until, now) > 0
                or (touch and touch.get("down"))
            )

            # Z button: z/space/enter
            self._held_z = bool(
                keys[pygame.K_z]
                or keys[pygame.K_SPACE]
                or keys[pygame.K_RETURN]
                or (touch and touch.get("space"))
            )
            self._z = bool(self._held_z or ticks_diff(self._z_until, now) > 0)
            # C button: x/escape
            self._held_c = bool(
                keys[pygame.K_x] or keys[pygame.K_ESCAPE] or (touch and touch.get("x"))
            )
            self._c = bool(self._held_c or ticks_diff(self._c_until, now) > 0)

            # Keyboard/touch only give us digital direction state; funnel it
            # through the shared D-pad encoder so desktop matches hardware.
            self._x, self._y = dpad_to_analog(up, down, left, right)

        def buttons(self):
            self._poll()
            if self._held_c and self._held_z:
                raise RestartProgram()
            return self._c, self._z

        def joystick(self):
            self._poll()
            return (self._x, self._y)

    class Joystick(_JoystickBase):
        def __init__(self):
            super().__init__()
            self.nunchuck = Nunchuck()

        def _read_xy_raw(self):
            return self.nunchuck.joystick()

        def _read_buttons_raw(self):
            return self.nunchuck.buttons()


_wasd_last_dir = None
_wasd_last_ms = 0


def read_wasd_input(possible_directions, debounce=False):
    """Return the WASD player's direction and action from one keyboard poll."""
    global _wasd_last_dir, _wasd_last_ms
    if IS_MICROPYTHON:
        return None, False
    try:
        import pygame  # type: ignore

        pygame.event.pump()
        keys = pygame.key.get_pressed()
        up = bool(keys[pygame.K_w])
        down = bool(keys[pygame.K_s])
        left = bool(keys[pygame.K_a])
        right = bool(keys[pygame.K_d])
        x, y = dpad_to_analog(up, down, left, right)
        d = _read_direction_from_xy(x, y, possible_directions)
        action = bool(keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT])
        if not debounce:
            return d, action
        now = ticks_ms()
        if d is None:
            _wasd_last_dir = None
            return None, action
        if d == _wasd_last_dir and ticks_diff(
            now, _wasd_last_ms
        ) < _JoystickBase._debounce_ms:
            return None, action
        _wasd_last_dir = d
        _wasd_last_ms = now
        return d, action
    except Exception:
        return None, False


def read_wasd_direction(possible_directions, debounce=False):
    """Read WASD as a digital direction source for desktop/web multiplayer."""
    direction, _action = read_wasd_input(possible_directions, debounce)
    return direction


def read_wasd_buttons():
    """Return (back, action) for the WASD-side player on desktop/web."""
    _direction, action = read_wasd_input((), debounce=False)
    return False, action


def read_player2_direction(possible_directions, debounce=False):
    """Compatibility alias: player 2 now uses the normal joystick/arrow path."""
    return None


def read_player2_buttons():
    """Compatibility stub; player 2 uses the normal joystick/arrow buttons."""
    return False, False


# ---------- Color helper ----------
def hsb_to_rgb(hue, saturation, brightness):
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
    return math.sqrt(x * x + y * y)


# ---------- Highscores ----------
try:
    import ujson as json
except ImportError:
    import json


class HighScores:
    FILE = "highscores.json"
    MAX_ENTRIES = 10

    def __init__(self):
        self.scores = {}
        self.load()

    def _clean_name(self, name):
        if isinstance(name, str) and name:
            return name[:3].upper()
        return "---"

    def _entry_from_value(self, value):
        try:
            if isinstance(value, dict):
                score = int(value.get("score", 0) or 0)
                name = self._clean_name(value.get("name", "---"))
            elif isinstance(value, (list, tuple)) and len(value) >= 2:
                score = int(value[0] or 0)
                name = self._clean_name(value[1])
            else:
                score = int(value or 0)
                name = "---"
            if score > 0:
                return {"score": score, "name": name}
        except Exception:
            pass
        return None

    def _entries_from_value(self, value):
        if isinstance(value, list):
            entries = []
            for item in value:
                entry = self._entry_from_value(item)
                if entry:
                    entries.append(entry)
        else:
            entry = self._entry_from_value(value)
            entries = [entry] if entry else []
        entries.sort(key=lambda item: int(item.get("score", 0) or 0), reverse=True)
        return entries[: self.MAX_ENTRIES]

    def _set_entries(self, game, entries):
        clean = []
        for entry in entries:
            item = self._entry_from_value(entry)
            if item:
                clean.append(item)
        clean.sort(key=lambda item: int(item.get("score", 0) or 0), reverse=True)
        self.scores[game] = clean[: self.MAX_ENTRIES]

    def _normalize_scores(self):
        for game in list(self.scores.keys()):
            entries = self._entries_from_value(self.scores.get(game))
            if entries:
                self.scores[game] = entries
            else:
                try:
                    del self.scores[game]
                except Exception:
                    pass

    def _load_compact(self):
        out = {}
        with open(self.FILE, "r") as f:
            for line in f:
                parts = line.strip().split(":")
                if len(parts) < 2:
                    continue
                game = parts[0]
                score = int(parts[1] or 0)
                if score <= 0:
                    continue
                name = parts[2][:3].upper() if len(parts) > 2 and parts[2] else "---"
                entries = out.get(game)
                if not isinstance(entries, list):
                    entries = []
                    out[game] = entries
                entries.append({"score": score, "name": name})
        self.scores = out
        self._normalize_scores()

    def load(self):
        try:
            with open(self.FILE, "r") as f:
                self.scores = json.load(f)
            if not isinstance(self.scores, dict):
                self.scores = {}
            self._normalize_scores()
        except Exception:
            try:
                self._load_compact()
            except Exception:
                self.scores = {}

    def _write_scores(self, f):
        self._normalize_scores()
        if IS_MICROPYTHON:
            for game, entries in self.scores.items():
                for entry in self._entries_from_value(entries):
                    try:
                        score = int(entry.get("score", 0) or 0)
                        name = self._clean_name(entry.get("name", "---"))
                        if score > 0:
                            f.write(game + ":" + str(score) + ":" + name + "\n")
                    except Exception:
                        pass
        else:
            json.dump(self.scores, f)

    def save(self):
        tmp_file = self.FILE + ".tmp"
        try:
            with open(tmp_file, "w") as f:
                self._write_scores(f)
            try:
                _os.remove(self.FILE)
            except Exception:
                pass
            _os.rename(tmp_file, self.FILE)
        except Exception:
            try:
                _os.remove(tmp_file)
            except Exception:
                pass
            try:
                with open(self.FILE, "w") as f:
                    self._write_scores(f)
            except Exception:
                pass

    def best(self, game):
        entries = self._entries_from_value(self.scores.get(game, []))
        if entries:
            return int(entries[0].get("score", 0) or 0)
        return 0

    def best_name(self, game):
        entries = self._entries_from_value(self.scores.get(game, []))
        if entries:
            return self._clean_name(entries[0].get("name", "---"))
        return "---"

    def entries(self, game=None, limit=None):
        if isinstance(game, int) and limit is None:
            limit = game
            game = None
        out = []
        if game is not None:
            for entry in self._entries_from_value(self.scores.get(game, [])):
                out.append(
                    (
                        game,
                        int(entry.get("score", 0) or 0),
                        self._clean_name(entry.get("name", "---")),
                    )
                )
        else:
            for game_name in self.scores:
                for entry in self._entries_from_value(self.scores.get(game_name, [])):
                    out.append(
                        (
                            game_name,
                            int(entry.get("score", 0) or 0),
                            self._clean_name(entry.get("name", "---")),
                        )
                    )
            out.sort(key=lambda item: item[1], reverse=True)
        if limit is not None:
            return out[:limit]
        return out

    def qualifies(self, game, score, limit=None):
        score = int(score or 0)
        if score <= 0:
            return False
        if limit is None:
            limit = self.MAX_ENTRIES
        entries = self._entries_from_value(self.scores.get(game, []))
        return len(entries) < limit or score > int(entries[-1].get("score", 0) or 0)

    def update(self, game, score, name=None):
        score = int(score or 0)
        if score <= 0:
            return False
        entries = self._entries_from_value(self.scores.get(game, []))
        entries.append({"score": score, "name": self._clean_name(name)})
        self._set_entries(game, entries)
        self.save()
        return True


class GameSettings:
    """Shared per-game option state for selector menus and game instances."""

    FILE = "settings.json"
    # Definition shape:
    #   game_id: ((key, short_label, ((stored_value, menu_label), ...),
    #             default_index), ...)
    # The selector uses this declarative data to draw settings screens; games read
    # the stored values from the context passed by GameSelect._make_game_instance().
    DEFINITIONS = {
        "DEMOS": (
            (
                "slide_ms",
                "SLIDE",
                ((30000, "30S"), (60000, "60S"), (90000, "90S"), (120000, "120S")),
                1,
            ),
            ("order", "ORDER", (("sorted", "SORT"), ("random", "RAND")), 0),
            ("clock", "CLOCK", ((False, "OFF"), (True, "ON")), 0),
            ("clock_source", "TIME", (("rtc", "RTC"), ("manual", "SET")), 0),
            (
                "clock_hour",
                "HOUR",
                tuple((i, "{:02}".format(i)) for i in range(24)),
                12,
            ),
            (
                "clock_minute",
                "MIN",
                tuple((i, "{:02}".format(i)) for i in range(60)),
                0,
            ),
        ),
        "ORBTAL": (
            ("gravity", "GRAV", ((False, "OFF"), (True, "ON")), 0),
            ("multi_shot", "MULTI", ((False, "OFF"), (True, "ON")), 0),
        ),
        "RACING": (
            ("laps", "LAPS", ((2, "2"), (3, "3"), (5, "5")), 1),
            ("traffic", "TRAF", ((True, "ON"), (False, "OFF")), 0),
        ),
        "BILLI": (
            ("rules", "RULE", (("pool", "POOL"), ("snooker", "SNOOK")), 0),
            ("aim", "AIM", (("short", "SHORT"), ("long", "LONG")), 0),
        ),
        "AIRHKY": (
            ("players", "PLAYR", (("cpu", "1P"), ("two", "2P")), 0),
            ("goals", "GOALS", ((3, "3"), (5, "5"), (7, "7")), 1),
        ),
        "BRKOUT": (("powerups", "POWER", ((False, "OFF"), (True, "ON")), 0),),
        "BTLZON": (
            (
                "difficulty",
                "DIFF",
                (("easy", "EASY"), ("normal", "NORM"), ("hard", "HARD")),
                1,
            ),
            ("obstacles", "ROCKS", ((False, "OFF"), (True, "ON")), 1),
        ),
        "CITY": (
            ("jobs", "JOBS", ((3, "3"), (5, "5")), 0),
            ("traffic", "TRAF", ((True, "ON"), (False, "OFF")), 0),
        ),
        "LANDER": (("mode", "MODE", (("classic", "V1"), ("scroll", "V2")), 0),),
        "KERBAL": (
            ("mission", "MISN", (("orbit", "ORB"), ("return", "RET")), 0),
            ("assist", "ASST", ((True, "ON"), (False, "OFF")), 0),
        ),
        "PONG": (("players", "PLAYR", (("cpu", "1P"), ("two", "2P")), 0),),
        "TRON": (("players", "PLAYR", (("cpu", "CPU"), ("two", "2P")), 0),),
        "WORMS": (
            ("players", "PLAYR", (("cpu", "CPU"), ("two", "2P")), 0),
            ("worms", "TEAM", ((2, "2"), (3, "3")), 0),
        ),
        "UFODEF": (
            ("launcher", "GUNS", (("base", "BASE"), ("turrets", "3GUN")), 1),
            ("spawns", "SPAWN", (("wave", "WAVE"), ("time", "TIME")), 0),
            ("blast", "BLAST", (("filled", "FILL"), ("ring", "RING")), 0),
            ("chain", "CHAIN", ((False, "OFF"), (True, "ON")), 1),
        ),
    }

    def __init__(self):
        self.values = {}
        self.load()

    def load(self):
        try:
            with open(self.FILE, "r") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                self.values = raw
        except Exception:
            self.values = {}

    def save(self):
        tmp_file = self.FILE + ".tmp"
        try:
            # Write-and-rename keeps settings resilient if power is lost while saving.
            with open(tmp_file, "w") as f:
                json.dump(self.values, f)
            try:
                _os.remove(self.FILE)
            except Exception:
                pass
            _os.rename(tmp_file, self.FILE)
        except Exception:
            try:
                _os.remove(tmp_file)
            except Exception:
                pass

    def definitions_for(self, game_name):
        return self.DEFINITIONS.get(game_name, ())

    def has_options(self, game_name):
        return bool(self.definitions_for(game_name))

    def _default_value(self, opt):
        choices = opt[2]
        idx = opt[3] if len(opt) > 3 else 0
        if idx < 0 or idx >= len(choices):
            idx = 0
        return choices[idx][0]

    def _stored_value(self, game_name, key, default):
        game_values = self.values.get(game_name)
        if isinstance(game_values, dict) and key in game_values:
            return game_values.get(key)
        return default

    def value(self, game_name, key, default=None):
        for opt in self.definitions_for(game_name):
            if opt[0] == key:
                return self._stored_value(game_name, key, self._default_value(opt))
        return default

    def snapshot(self, game_name):
        out = {}
        for opt in self.definitions_for(game_name):
            out[opt[0]] = self.value(game_name, opt[0])
        return out

    def choice_index(self, game_name, opt_index):
        opts = self.definitions_for(game_name)
        if opt_index < 0 or opt_index >= len(opts):
            return 0
        opt = opts[opt_index]
        value = self.value(game_name, opt[0])
        for i, choice in enumerate(opt[2]):
            if choice[0] == value:
                return i
        return opt[3] if len(opt) > 3 else 0

    def cycle(self, game_name, opt_index, delta):
        opts = self.definitions_for(game_name)
        if opt_index < 0 or opt_index >= len(opts):
            return
        opt = opts[opt_index]
        choices = opt[2]
        if not choices:
            return
        idx = (self.choice_index(game_name, opt_index) + delta) % len(choices)
        game_values = self.values.get(game_name)
        if not isinstance(game_values, dict):
            game_values = {}
            self.values[game_name] = game_values
        game_values[opt[0]] = choices[idx][0]
        self.save()


class InitialsEntryMenu:
    """3-letter initials entry for highscores."""

    def __init__(self, joystick, score, best, best_name="---", title="NEW HS"):
        self.joystick = joystick
        self.score = score
        self.best = best
        self.best_name = best_name
        self.title = title
        self.letters = ["A", "A", "A"]
        self.idx = 0

    def run(self):
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
                    JOYSTICK_DIRECTIONS_4
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

            c_button, z_button = self.joystick.read_buttons()
            if c_button:
                # cancel
                while True:
                    c_pressed, _z_pressed = self.joystick.read_buttons()
                    if not c_pressed:
                        break
                    sleep_ms(10)
                return None

            if z_button:
                while True:
                    _c_pressed, z_pressed = self.joystick.read_buttons()
                    if not z_pressed:
                        break
                    sleep_ms(10)
                return "".join(self.letters)

            sleep_ms(20)

    async def run_async(self):
        """Async version of run() for use in pygbag/browser environments."""
        if asyncio is None:
            return self.run()
        last_move = ticks_ms()
        move_delay = 140
        while True:
            display.clear()
            draw_text(2, 6, self.title, 0, 220, 0)
            draw_rectangle(0, PLAY_HEIGHT, WIDTH - 1, HEIGHT - 1, 0, 0, 0)
            draw_text_small(1, PLAY_HEIGHT, str(self.score), 255, 255, 255)
            bn = self.best_name if isinstance(self.best_name, str) else "---"
            bs = "B" + str(self.best) + " " + bn
            draw_text_small(WIDTH - len(bs) * 6, 1, bs, 140, 140, 140)
            for i in range(3):
                col = (255, 255, 255) if i == self.idx else (120, 120, 120)
                draw_text(10 + i * 18, 28, self.letters[i], *col)
                if i == self.idx:
                    draw_rectangle(8 + i * 18, 41, 20 + i * 18, 42, 255, 255, 255)
            draw_text_small(2, 50, "A=OK B=BACK", 120, 120, 120)
            display_flush()
            now = ticks_ms()
            if ticks_diff(now, last_move) > move_delay:
                d = self.joystick.read_direction(
                    JOYSTICK_DIRECTIONS_4
                )
                if d == JOYSTICK_LEFT and self.idx > 0:
                    self.idx -= 1
                    last_move = now
                elif d == JOYSTICK_RIGHT and self.idx < 2:
                    self.idx += 1
                    last_move = now
                elif d == JOYSTICK_UP:
                    c = ord(self.letters[self.idx])
                    self.letters[self.idx] = chr(65 if c >= 90 else c + 1)
                    last_move = now
                elif d == JOYSTICK_DOWN:
                    c = ord(self.letters[self.idx])
                    self.letters[self.idx] = chr(90 if c <= 65 else c - 1)
                    last_move = now
            c_button, z_button = self.joystick.read_buttons()
            if c_button:
                await _wait_for_primary_release_async(self.joystick)
                return None
            if z_button:
                await _wait_for_primary_release_async(self.joystick)
                return "".join(self.letters)
            await asyncio.sleep(0.020)


# ======================================================================
#                                 GAMES
# ======================================================================


class FrameLoopGame:
    """Run callback-based games consistently on every supported runtime.

    Subclasses provide ``FRAME_MS`` and ``_build_step(joystick)``.  Keeping
    the sync/async dispatch here prevents each small game from maintaining a
    subtly different browser fallback or frame-pacing implementation.
    """

    FRAME_MS = CONFIG_FRAME_MS_DEFAULT

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(
            self.FRAME_MS,
            self._build_step(joystick),
        )


class GridCursorGame(FrameLoopGame):
    """Shared, debounced four-way cursor movement for grid games."""

    MOVE_DELAY_MS = 135

    def _move_cursor(self, joystick):
        now = ticks_ms()
        if ticks_diff(now, self.last_move) < self.MOVE_DELAY_MS:
            return False
        direction = joystick.read_direction(
            JOYSTICK_DIRECTIONS_4
        )
        dx, dy = direction_to_delta(direction)
        if not (dx or dy):
            return False
        self.cursor_x = clamp(self.cursor_x + dx, 0, self.GRID_W - 1)
        self.cursor_y = clamp(self.cursor_y + dy, 0, self.GRID_H - 1)
        self.last_move = now
        return True
