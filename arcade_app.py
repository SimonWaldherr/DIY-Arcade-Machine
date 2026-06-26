"""
Main application module for the DIY Arcade Machine.
Contains all game engines, menu logic, and hardware abstraction layer (HAL)
for running the game console on both CPytthon (emulator) and MicroPython.

Mainly manages the frame buffer, UI updates, state transitions, and high scores.
"""
import random
import time
import math
import gc
import sys
import importlib.util
try:
    import uos as _os
except ImportError:
    import os as _os
try:
    _os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    _os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
except Exception:
    pass

# Low-resource defaults. Keep debug logging off unless explicitly changed here.
DEBUG_BOOT_LOG = False
CONFIG_LOW_RAM_MODE = False
CONFIG_BUFFERED_DISPLAY = False
CONFIG_ENABLE_HEAVY_GAMES = True
CONFIG_ENABLE_GAME_DEMOS = False
# Empty allowlists mean "all"; blocklists remove names after that.
# Game demo names in CONFIG_*_DEMOS use the "G:NAME" form, e.g. "G:SNAKE".
CONFIG_ENABLED_GAMES = ()
CONFIG_DISABLED_GAMES = ()
CONFIG_ENABLED_DEMOS = ()
CONFIG_DISABLED_DEMOS = ()
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
    # Fisher-Yates; avoids relying on random.shuffle (not present on some MicroPython builds)
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
    IS_MICROPYTHON = (sys.implementation.name == "micropython")
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
    def const(x): return x

WIDTH  = const(64)
HEIGHT = const(64)

HUD_HEIGHT  = const(6)
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
    global FEATURE_TIER, CONFIG_LOW_RAM_MODE, CONFIG_BUFFERED_DISPLAY, CONFIG_ENABLE_HEAVY_GAMES
    FEATURE_TIER = _detect_feature_tier()
    CONFIG_LOW_RAM_MODE = bool(IS_MICROPYTHON and FEATURE_TIER == 0)
    CONFIG_ENABLE_HEAVY_GAMES = bool((not IS_MICROPYTHON) or FEATURE_TIER >= 1)
    if not IS_MICROPYTHON:
        CONFIG_BUFFERED_DISPLAY = False
        return
    free = _mem_free()
    threshold = FRAMEBUFFER_MIN_FREE_RP2350 if FEATURE_TIER >= 2 else FRAMEBUFFER_MIN_FREE_RP2040
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
    # after drawing (many loops use ticks_ms/ticks_diff for pacing).
    if IS_DESKTOP:
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

def show_center_message(lines, start_y=18, line_height=12,
                        r=255, g=255, b=255, clear=True,
                        score=None, delay_ms=0):
    """Draw centered text lines with optional clear, score update and delay."""
    if clear:
        display.clear()
    draw_centered_text_lines(lines, start_y=start_y, line_height=line_height, r=r, g=g, b=b)
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

async def show_center_message_async(lines, start_y=18, line_height=12,
                                    r=255, g=255, b=255, clear=True,
                                    score=None, delay_ms=0):
    """Async version of show_center_message()."""
    if clear:
        display.clear()
    draw_centered_text_lines(lines, start_y=start_y, line_height=line_height, r=r, g=g, b=b)
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
    return (ax < (bx + bw)) and (bx < (ax + aw)) and (ay < (by + bh)) and (by < (ay + ah))

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
    last_frame = ticks_ms()
    while True:
        now = ticks_ms()
        if ticks_diff(now, last_frame) < frame_ms:
            sleep_ms(4)
            continue
        last_frame = now
        if not loop_fn():
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
            if not loop_fn():
                return
            try:
                display_flush()
            except Exception:
                pass
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
            # machine.RTC().datetime() layout: (year, month, day, weekday, hour, minute, second, subseconds)
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
                raise RuntimeError("PyGame not installed. Install with: pip install pygame") from e
            self._pg = pygame
            pygame.init()
            try:
                if importlib.util.find_spec("pygame.mixer") is not None:
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
                self._surface.set_at((int(x), int(y)), (int(r) & 255, int(g) & 255, int(b) & 255))

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
                self._pg.transform.scale(self._surface, (self.w * self.scale, self.h * self.scale), self._scaled_surface)
                self._screen.blit(self._scaled_surface, (0, 0))
            else:
                scaled = self._pg.transform.scale(self._surface, (self.w * self.scale, self.h * self.scale))
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
_force_full_flush = False

_boot_log("framebuffer vars")

# keep originals to actually write to the hardware
_display_set_pixel_orig = display.set_pixel
_display_clear_orig = getattr(display, "clear", None)

_boot_log("display refs")

def init_buffered_display():
    """Allocate software framebuffer + hooks after hub75 display is started."""
    global USE_BUFFERED_DISPLAY, USE_BUFFERED_DISPLAY_DESIRED, _fb_current, _fb_prev, _dirty_mask, _force_full_flush
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
        threshold = FRAMEBUFFER_MIN_FREE_RP2350 if FEATURE_TIER >= 2 else FRAMEBUFFER_MIN_FREE_RP2040
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
    if _dirty_mask is not None:
        _dirty_mask[px] = 1

def _set_pixel_buf(x, y, r, g, b):
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
    # clear current framebuffer and mark all pixels dirty
    w = _fb_w * _fb_h
    global _force_full_flush
    if _fb_current is not None:
        # Zero unconditionally — cheaper than branching on every byte
        for i in range(w * 3):
            _fb_current[i] = 0
    # Avoid building a huge list of dirty pixel indices.
    _force_full_flush = True
    if _dirty_mask is not None:
        for i in range(w):
            _dirty_mask[i] = 0
    # also clear hardware quickly if supported
    if _display_clear_orig:
        try:
            _display_clear_orig()
        except Exception:
            pass

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
    x0 = int(x0); y0 = int(y0); x1 = int(x1); y1 = int(y1)
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
    (255, 0, 0),    # Red
    (0, 255, 0),    # Green
    (0, 0, 255),    # Blue
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
RED   = (255, 0, 0)
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

_WEB_TOUCH_KEYS = ("up", "down", "left", "right", "x", "space")

def _js_prop(obj, name, default=None):
    try:
        return obj[name]
    except Exception:
        try:
            return getattr(obj, name)
        except Exception:
            return default

def _read_web_touch_input():
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
    result = {}
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

def direction_to_delta(direction, default_dx=0, default_dy=0):
    """Map 4-way joystick direction constants to (dx, dy), else return provided defaults."""
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
    """Map 8-way joystick direction constants to (dx, dy), else return provided defaults."""
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
        "A": "3078ccccfccccc00","B": "fc66667c6666fc00","C": "3c66c0c0c0663c00","D": "f86c6666666cf800",
        "E": "fe6268786862fe00","F": "fe6268786860f000","G": "3c66c0c0ce663e00","H": "ccccccfccccccc00",
        "I": "7830303030307800","J": "1e0c0c0ccccc7800","K": "f6666c786c66f600","L": "f06060606266fe00",
        "M": "c6eefefed6c6c600","N": "c6e6f6decec6c600","O": "386cc6c6c66c3800","P": "fc66667c6060f000",
        "Q": "78ccccccdc781c00","R": "fc66667c6c66f600","S": "78cce0380ccc7800","T": "fcb4303030307800",
        "U": "ccccccccccccfc00","V": "cccccccccc783000","W": "c6c6c6d6feeec600","X": "c6c66c38386cc600",
        "Y": "cccccc7830307800","Z": "fec68c183266fe00",
        "0": "386cc6c6c66c3800","1": "307030303030fc00","2": "78cc0c3860ccfc00","3": "78cc0c380ccc7800",
        "4": "1c3c6cccfe0c1e00","5": "fcc0f80c0ccc7800","6": "3860c0f8cccc7800","7": "fccc0c1830303000",
        "8": "78cccc78cccc7800","9": "78cccc7c0c187000",
        "!": "3078783030003000","#": "6c6cfe6cfe6c6c00","$": "307cc0780cf83000","%": "00c6cc183066c600",
        "&": "386c3876dccc7600","?": "78cc0c1830003000"," ": "0000000000000000",".": "0000000000003000",
        ":": "0030000000300000","(": "0c18303030180c00",")": "6030180c18306000","-": "000000fc00000000",
    }

def _get_nums_dict():
    return {
        "0": ["01110","10001","10001","10001","01110"],
        "1": ["00100","01100","00100","00100","01110"],
        "2": ["11110","00001","01110","10000","11111"],
        "3": ["11110","00001","00110","00001","11110"],
        "4": ["10000","10010","10010","11111","00010"],
        "5": ["11111","10000","11110","00001","11110"],
        "6": ["01110","10000","11110","10001","01110"],
        "7": ["11111","00010","00100","01000","10000"],
        "8": ["01110","10001","01110","10001","01110"],
        "9": ["01110","10001","01111","00001","01110"],
        "A": ["01110","10001","11111","10001","10001"],
        "B": ["11110","10001","11110","10001","11110"],
        "C": ["01111","10000","10000","10000","01111"],
        "D": ["11110","10001","10001","10001","11110"],
        "E": ["11111","10000","11110","10000","11111"],
        "F": ["11111","10000","11110","10000","10000"],
        "G": ["01111","10000","10111","10001","01110"],
        "H": ["10001","10001","11111","10001","10001"],
        "I": ["11111","00100","00100","00100","11111"],
        "J": ["00111","00010","00010","10010","01100"],
        "K": ["10001","10010","11100","10010","10001"],
        "L": ["10000","10000","10000","10000","11111"],
        "M": ["10001","11011","10101","10001","10001"],
        "N": ["10001","11001","10101","10011","10001"],
        "O": ["01110","10001","10001","10001","01110"],
        "P": ["11110","10001","11110","10000","10000"],
        "Q": ["01110","10001","10101","10010","01101"],
        "R": ["11110","10001","11110","10010","10001"],
        "S": ["01111","10000","01110","00001","11110"],
        "T": ["11111","00100","00100","00100","00100"],
        "U": ["10001","10001","10001","10001","01110"],
        "V": ["10001","10001","10001","01010","00100"],
        "W": ["10001","10001","10101","11011","10001"],
        "X": ["10001","01010","00100","01010","10001"],
        "Y": ["10001","01010","00100","00100","00100"],
        "Z": ["11111","00010","00100","01000","11111"],
        " ": ["00000","00000","00000","00000","00000"],
        ".": ["00000","00000","00000","00000","00001"],
        ":": ["00000","00100","00000","00100","00000"],
        "/": ["00001","00010","00100","01000","10000"],
        "|": ["00100","00100","00100","00100","00100"],
        "-": ["00000","00000","11111","00000","00000"],
        "=": ["00000","11111","00000","11111","00000"],
        "+": ["00000","00100","01110","00100","00000"],
        "*": ["00000","10101","01110","10101","00000"],
        "(": ["00010","00100","00100","00100","00010"],
        ")": ["00100","00010","00010","00010","00100"],
    }

def _hex_to_bytes(hex_str):
    try:
        return bytes.fromhex(hex_str)
    except AttributeError:
        out = bytearray(len(hex_str) // 2)
        oi = 0
        for i in range(0, len(hex_str), 2):
            out[oi] = int(hex_str[i:i+2], 16)
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
    if x1 > x2: x1, x2 = x2, x1
    if y1 > y2: y1, y2 = y2, y1
    if x2 < 0 or y2 < 0 or x1 >= WIDTH or y1 >= HEIGHT:
        return
    if x1 < 0: x1 = 0
    if y1 < 0: y1 = 0
    if x2 >= WIDTH: x2 = WIDTH - 1
    if y2 >= HEIGHT: y2 = HEIGHT - 1
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
    # flush buffered drawing to hardware (only changed pixels)
    if not (IS_WEB and _FRAME_PRESENT_MANAGED):
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
NEW_CONTROLLER_SIGNATURE = b"\xA0\x20\x10\x00\xFF\xFF\x00\x00"

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
    if x < AXIS_LOW and y < AXIS_LOW and JOYSTICK_DOWN_LEFT in possible_directions:
        return JOYSTICK_DOWN_LEFT
    if x > AXIS_HIGH and y < AXIS_LOW and JOYSTICK_DOWN_RIGHT in possible_directions:
        return JOYSTICK_DOWN_RIGHT
    if x < AXIS_LOW and y > AXIS_HIGH and JOYSTICK_UP_LEFT in possible_directions:
        return JOYSTICK_UP_LEFT
    if x > AXIS_HIGH and y > AXIS_HIGH and JOYSTICK_UP_RIGHT in possible_directions:
        return JOYSTICK_UP_RIGHT
    if x < AXIS_LOW and JOYSTICK_LEFT in possible_directions:
        return JOYSTICK_LEFT
    if x > AXIS_HIGH and JOYSTICK_RIGHT in possible_directions:
        return JOYSTICK_RIGHT
    if y < AXIS_LOW and JOYSTICK_DOWN in possible_directions:
        return JOYSTICK_DOWN
    if y > AXIS_HIGH and JOYSTICK_UP in possible_directions:
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
        if d == self._last_dir and ticks_diff(now, self._last_dir_ms) < self._debounce_ms:
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

        def _new_decode(self):
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
            if self.polling_threshold > 0 and ticks_diff(ticks_ms(), self.last_poll) > self.polling_threshold:
                self.update()
                self.last_poll = ticks_ms()

        def buttons(self):
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
            self.__poll()
            if not self.is_new_controller:
                return (self.buffer[0], self.buffer[1])

            # New controller does not provide analog joystick in the same way.
            # Synthesize analog-like values from the D-pad so the existing
            # read_direction() threshold logic keeps working.
            up, down, left, right, a_btn, b_btn, start, select = self._new_decode()
            return dpad_to_analog(up, down, left, right)

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

        def _poll(self):
            try:
                import pygame  # type: ignore
            except Exception:
                return
            now = ticks_ms()
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
            left = bool(keys[pygame.K_LEFT] or ticks_diff(self._left_until, now) > 0 or (touch and touch.get("left")))
            right = bool(keys[pygame.K_RIGHT] or ticks_diff(self._right_until, now) > 0 or (touch and touch.get("right")))
            up = bool(keys[pygame.K_UP] or ticks_diff(self._up_until, now) > 0 or (touch and touch.get("up")))
            down = bool(keys[pygame.K_DOWN] or ticks_diff(self._down_until, now) > 0 or (touch and touch.get("down")))

            # Z button: z/space/enter
            self._held_z = bool(keys[pygame.K_z] or keys[pygame.K_SPACE] or keys[pygame.K_RETURN] or (touch and touch.get("space")))
            self._z = bool(self._held_z or ticks_diff(self._z_until, now) > 0)
            # C button: x/escape
            self._held_c = bool(keys[pygame.K_x] or keys[pygame.K_ESCAPE] or (touch and touch.get("x")))
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


def read_wasd_direction(possible_directions, debounce=False):
    """Read WASD as a digital direction source for desktop/web multiplayer."""
    if IS_MICROPYTHON:
        return None
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
        if not debounce:
            return d
        now = ticks_ms()
        last_dir = getattr(read_wasd_direction, "_last_dir", None)
        last_ms = getattr(read_wasd_direction, "_last_ms", 0)
        if d is None:
            setattr(read_wasd_direction, "_last_dir", None)
            return None
        if d == last_dir and ticks_diff(now, last_ms) < _JoystickBase._debounce_ms:
            return None
        setattr(read_wasd_direction, "_last_dir", d)
        setattr(read_wasd_direction, "_last_ms", now)
        return d
    except Exception:
        return None


def read_wasd_buttons():
    """Return (back, action) for the WASD-side player on desktop/web."""
    if IS_MICROPYTHON:
        return False, False
    try:
        import pygame  # type: ignore
        pygame.event.pump()
        keys = pygame.key.get_pressed()
        return False, bool(keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT])
    except Exception:
        return False, False


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
    return math.sqrt(x*x + y*y)

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
        return entries[:self.MAX_ENTRIES]

    def _set_entries(self, game, entries):
        clean = []
        for entry in entries:
            item = self._entry_from_value(entry)
            if item:
                clean.append(item)
        clean.sort(key=lambda item: int(item.get("score", 0) or 0), reverse=True)
        self.scores[game] = clean[:self.MAX_ENTRIES]

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
                out.append((game, int(entry.get("score", 0) or 0),
                            self._clean_name(entry.get("name", "---"))))
        else:
            for game_name in self.scores:
                for entry in self._entries_from_value(self.scores.get(game_name, [])):
                    out.append((game_name, int(entry.get("score", 0) or 0),
                                self._clean_name(entry.get("name", "---"))))
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
    #   game_id: ((key, short_label, ((stored_value, menu_label), ...), default_index), ...)
    # The selector uses this declarative data to draw settings screens; games read
    # the stored values from the context passed by GameSelect._make_game_instance().
    DEFINITIONS = {
        "DEMOS": (
            ("slide_ms", "SLIDE", ((30000, "30S"), (60000, "60S"), (90000, "90S"), (120000, "120S")), 1),
            ("order", "ORDER", (("sorted", "SORT"), ("random", "RAND")), 0),
            ("clock", "CLOCK", ((False, "OFF"), (True, "ON")), 0),
            ("clock_source", "TIME", (("rtc", "RTC"), ("manual", "SET")), 0),
            ("clock_hour", "HOUR", tuple((i, "{:02}".format(i)) for i in range(24)), 12),
            ("clock_minute", "MIN", tuple((i, "{:02}".format(i)) for i in range(60)), 0),
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
        "BRKOUT": (
            ("powerups", "POWER", ((False, "OFF"), (True, "ON")), 0),
        ),
        "BTLZON": (
            ("difficulty", "DIFF", (("easy", "EASY"), ("normal", "NORM"), ("hard", "HARD")), 1),
            ("obstacles", "ROCKS", ((False, "OFF"), (True, "ON")), 1),
        ),
        "CITY": (
            ("jobs", "JOBS", ((3, "3"), (5, "5")), 0),
            ("traffic", "TRAF", ((True, "ON"), (False, "OFF")), 0),
        ),
        "LANDER": (
            ("mode", "MODE", (("classic", "V1"), ("scroll", "V2")), 0),
        ),
        "KERBAL": (
            ("mission", "MISN", (("orbit", "ORB"), ("return", "RET")), 0),
            ("assist", "ASST", ((True, "ON"), (False, "OFF")), 0),
        ),
        "PONG": (
            ("players", "PLAYR", (("cpu", "1P"), ("two", "2P")), 0),
        ),
        "TRON": (
            ("players", "PLAYR", (("cpu", "CPU"), ("two", "2P")), 0),
        ),
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
            x0 = 10
            y0 = 28
            for i in range(3):
                col = (255, 255, 255) if i == self.idx else (120, 120, 120)
                draw_text(10 + i * 18, y0, self.letters[i], *col)
                if i == self.idx:
                    draw_rectangle(8 + i * 18, y0 + 13, 20 + i * 18, y0 + 14, 255, 255, 255)

            draw_text_small(2, 50, "A=OK B=BACK", 120, 120, 120)

            now = ticks_ms()
            if ticks_diff(now, last_move) > move_delay:
                d = self.joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
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
                d = self.joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
                if d == JOYSTICK_LEFT and self.idx > 0:
                    self.idx -= 1; last_move = now
                elif d == JOYSTICK_RIGHT and self.idx < 2:
                    self.idx += 1; last_move = now
                elif d == JOYSTICK_UP:
                    c = ord(self.letters[self.idx])
                    self.letters[self.idx] = chr(65 if c >= 90 else c + 1); last_move = now
                elif d == JOYSTICK_DOWN:
                    c = ord(self.letters[self.idx])
                    self.letters[self.idx] = chr(90 if c <= 65 else c - 1); last_move = now
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

class SimonGame:
    """
    SIMON
    Controls:
      - Directions: move white selector frame
      - Z: confirm selected color
      - C: return to menu
    """
    INPUT_BAR_Y = PLAY_HEIGHT - 6

    def __init__(self):
        self.sequence = []
        self.user_input = []
        self.cursor = 0

    def _quad_rect(self, idx):
        hw = WIDTH // 2
        hh = self.INPUT_BAR_Y // 2
        x = idx % 2
        y = idx // 2
        x1 = x * hw
        y1 = y * hh
        x2 = (x + 1) * hw - 1
        y2 = (y + 1) * hh - 1
        if y2 >= self.INPUT_BAR_Y:
            y2 = self.INPUT_BAR_Y - 1
        return x1, y1, x2, y2

    def draw_quad_screen(self):
        hw = WIDTH // 2
        hh = self.INPUT_BAR_Y // 2
        draw_rectangle(0, 0, hw - 1, hh - 1, *inactive_colors[0])
        draw_rectangle(hw, 0, WIDTH - 1, hh - 1, *inactive_colors[1])
        draw_rectangle(0, hh, hw - 1, self.INPUT_BAR_Y - 1, *inactive_colors[2])
        draw_rectangle(hw, hh, WIDTH - 1, self.INPUT_BAR_Y - 1, *inactive_colors[3])
        self.draw_input_bar()

    def draw_selector_frame(self):
        x1, y1, x2, y2 = self._quad_rect(self.cursor)
        draw_rect_outline(x1, y1, x2, y2, 255, 255, 255)
        draw_rect_outline(x1 + 1, y1 + 1, x2 - 1, y2 - 1, 255, 255, 255)

    def redraw_input_view(self):
        self.draw_quad_screen()
        self.draw_selector_frame()
        display_score_and_time(len(self.sequence) - 1)

    def draw_input_bar(self):
        y = self.INPUT_BAR_Y
        draw_rectangle(0, y, WIDTH - 1, PLAY_HEIGHT - 1, 0, 0, 0)
        start = max(0, len(self.user_input) - 12)
        x = 1
        for idx in self.user_input[start:]:
            draw_rectangle(x, y + 1, x + 3, y + 4, *colors[idx])
            x += 5

    def flash_color(self, idx, duration_ms=250):
        x1, y1, x2, y2 = self._quad_rect(idx)

        draw_rectangle(x1, y1, x2, y2, *colors[idx])
        sleep_ms(duration_ms)
        draw_rectangle(x1, y1, x2, y2, *inactive_colors[idx])
        if self.user_input:
            self.draw_input_bar()
        if idx == self.cursor:
            self.draw_selector_frame()
        display_flush()

    def play_sequence(self):
        for c in self.sequence:
            self.flash_color(c, 300)
            sleep_ms(200)

    def get_user_input(self, joystick):
        self.redraw_input_view()
        last_move = ticks_ms()
        last_z = False
        while True:
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return None
            if z_button and not last_z:
                return self.cursor
            last_z = z_button
            now = ticks_ms()
            d = joystick.read_direction([
                JOYSTICK_UP, JOYSTICK_RIGHT, JOYSTICK_LEFT, JOYSTICK_DOWN,
                JOYSTICK_UP_LEFT, JOYSTICK_UP_RIGHT,
                JOYSTICK_DOWN_LEFT, JOYSTICK_DOWN_RIGHT,
            ], debounce=False)
            if d:
                dx, dy = direction_to_delta_8way(d)
                col = self.cursor % 2
                row = self.cursor // 2
                if ticks_diff(now, last_move) >= 130:
                    if dx < 0:
                        col = 0
                    elif dx > 0:
                        col = 1
                    if dy < 0:
                        row = 0
                    elif dy > 0:
                        row = 1
                    new_cursor = row * 2 + col
                    if new_cursor != self.cursor:
                        self.cursor = new_cursor
                        self.redraw_input_view()
                    last_move = now
            sleep_ms(30)

    def translate(self, direction):
        return direction if direction in (0, 1, 2, 3) else None

    def main_loop(self, joystick):
        global game_over, global_score
        game_over = False
        self.sequence = []
        self.user_input = []
        display.clear()
        self.draw_quad_screen()
        display_score_and_time(0, force=True)

        while True:
            c_button, _ = joystick.read_buttons()
            if c_button:
                return

            self.sequence.append(random.randint(0, 3))
            display_score_and_time(len(self.sequence) - 1)
            self.play_sequence()
            self.user_input = []

            for _ in range(len(self.sequence)):
                direction = self.get_user_input(joystick)
                if direction is None:
                    return
                sel = self.translate(direction)
                if sel is None:
                    continue
                self.flash_color(sel, 120)
                self.user_input.append(sel)
                self.redraw_input_view()
                # check prefix
                if self.user_input != self.sequence[:len(self.user_input)]:
                    global_score = len(self.sequence) - 1
                    game_over = True
                    return

            sleep_ms(300)
            maybe_collect(120)

    async def main_loop_async(self, joystick):
        """Async version for pygbag: yields with asyncio.sleep()."""
        if asyncio is None:
            return self.main_loop(joystick)

        global game_over, global_score
        game_over = False
        self.sequence = []
        self.user_input = []
        display.clear()
        self.draw_quad_screen()
        display_score_and_time(0, force=True)

        while True:
            c_button, _ = joystick.read_buttons()
            if c_button:
                return

            self.sequence.append(random.randint(0, 3))
            display_score_and_time(len(self.sequence) - 1)

            # play sequence (async flashes)
            for c in self.sequence:
                x1, y1, x2, y2 = self._quad_rect(c)
                draw_rectangle(x1, y1, x2, y2, *colors[c])
                display_flush()
                await asyncio.sleep(0.3)
                draw_rectangle(x1, y1, x2, y2, *inactive_colors[c])
                display_flush()
                await asyncio.sleep(0.2)

            self.user_input = []

            for _ in range(len(self.sequence)):
                self.redraw_input_view()
                sel = None
                last_move = ticks_ms()
                last_z = False
                while sel is None:
                    c_button, z_button = joystick.read_buttons()
                    if c_button:
                        return
                    if z_button and not last_z:
                        sel = self.cursor
                        break
                    last_z = z_button
                    now = ticks_ms()
                    d = joystick.read_direction([
                        JOYSTICK_UP, JOYSTICK_RIGHT,
                        JOYSTICK_LEFT, JOYSTICK_DOWN,
                        JOYSTICK_UP_LEFT, JOYSTICK_UP_RIGHT,
                        JOYSTICK_DOWN_LEFT, JOYSTICK_DOWN_RIGHT,
                    ], debounce=False)
                    if d:
                        dx, dy = direction_to_delta_8way(d)
                        col = self.cursor % 2
                        row = self.cursor // 2
                        if ticks_diff(now, last_move) >= 130:
                            if dx < 0:
                                col = 0
                            elif dx > 0:
                                col = 1
                            if dy < 0:
                                row = 0
                            elif dy > 0:
                                row = 1
                            new_cursor = row * 2 + col
                            if new_cursor != self.cursor:
                                self.cursor = new_cursor
                                self.redraw_input_view()
                            last_move = now
                    await asyncio.sleep(0.030)

                # flash selected quadrant
                x1, y1, x2, y2 = self._quad_rect(sel)
                draw_rectangle(x1, y1, x2, y2, *colors[sel])
                display_flush()
                await asyncio.sleep(0.12)
                draw_rectangle(x1, y1, x2, y2, *inactive_colors[sel])
                display_flush()

                self.user_input.append(sel)
                self.redraw_input_view()
                if self.user_input != self.sequence[:len(self.user_input)]:
                    global_score = len(self.sequence) - 1
                    game_over = True
                    return

            await asyncio.sleep(0.3)
            maybe_collect(120)


class SnakeGame:
    """
    SNAKE
    Controls:
      - Left / Right / Up / Down: steer snake
      - C: return to menu
    """
    def __init__(self):
        self.restart_game()

    def restart_game(self):
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
        return (random.randint(1, WIDTH - 2), random.randint(1, PLAY_HEIGHT - 2))

    def place_target(self):
        for _ in range(300):
            t = self.random_target()
            if t in self.snake:
                continue

            blocked = False
            for gx, gy, _life in self.green_targets:
                if t == (gx, gy):
                    blocked = True
                    break
            if blocked:
                continue

            self.target = t
            display.set_pixel(t[0], t[1], 255, 0, 0)
            return

        self.target = (WIDTH // 2, PLAY_HEIGHT // 2)
        display.set_pixel(self.target[0], self.target[1], 255, 0, 0)

    def place_green_target(self):
        for _ in range(200):
            x = random.randint(1, WIDTH - 2)
            y = random.randint(1, PLAY_HEIGHT - 2)
            if (x, y) == self.target:
                continue
            if (x, y) in self.snake:
                continue
            self.green_targets.append((x, y, 256))
            display.set_pixel(x, y, 0, 255, 0)
            return

    def update_green_targets(self):
        new_list = []
        for x, y, life in self.green_targets:
            if life > 1:
                new_list.append((x, y, life - 1))
            else:
                display.set_pixel(x, y, 0, 0, 0)
        self.green_targets = new_list

    def check_self_collision(self):
        global game_over, global_score
        hx, hy = self.snake[0]
        body = self.snake[1:]
        if len(body) > 12:
            body_positions = set(body)
        else:
            body_positions = body
        moves = {
            JOYSTICK_UP: (hx, hy - 1),
            JOYSTICK_DOWN: (hx, hy + 1),
            JOYSTICK_LEFT: (hx - 1, hy),
            JOYSTICK_RIGHT: (hx + 1, hy),
        }
        
        safe_dirs = [d for d, p in moves.items() if p not in body_positions]
        if moves[self.snake_direction] in body_positions:
            if safe_dirs:
                self.snake_direction = random.choice(safe_dirs)
            else:
                global_score = self.score
                game_over = True

    def update_snake_position(self):
        hx, hy = self.snake[0]
        dx, dy = direction_to_delta(self.snake_direction)
        hx += dx
        hy += dy

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
        hx, hy = self.snake[0]
        if (hx, hy) == self.target:
            self.snake_length += 2
            self.score += 1
            self.place_target()

    def check_green_target_collision(self):
        hx, hy = self.snake[0]
        for x, y, life in self.green_targets:
            if (hx, hy) == (x, y):
                self.snake_length = max(self.snake_length // 2, 2)
                self.green_targets.remove((x, y, life))
                display.set_pixel(x, y, 0, 0, 0)
                break

    def draw_snake(self):
        hue = 0
        for (x, y) in self.snake[:self.snake_length]:
            hue = (hue + 7) % 360
            r, g, b = hsb_to_rgb(hue, 1, 1)
            display.set_pixel(x, y, r, g, b)

    def _step(self, joystick):
        global game_over
        c_button, _ = joystick.read_buttons()
        if c_button or game_over:
            return False

        self.step_counter += 1
        if self.step_counter % 1024 == 0:
            self.place_green_target()
        self.update_green_targets()

        direction = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
        if direction:
            self.snake_direction = direction

        self.check_self_collision()
        if game_over:
            return False

        self.update_snake_position()
        self.check_target_collision()
        self.check_green_target_collision()
        self.draw_snake()

        display_score_and_time(self.score)
        return True

    def main_loop(self, joystick):
        global game_over
        game_over = False
        self.restart_game()

        while True:
            if not self._step(joystick):
                return

            delay = 112 - max(10, self.snake_length // 3)
            if delay < 30:
                delay = 30
            sleep_ms(delay)
            maybe_collect(120)

    async def main_loop_async(self, joystick):
        """Async version for pygbag: yields with asyncio.sleep()."""
        if asyncio is None:
            return self.main_loop(joystick)
        
        global game_over
        game_over = False
        self.restart_game()

        def loop_iteration():
            return self._step(joystick)

        await _run_game_loop_async(56, loop_iteration)

class PongGame:
    """
    PONG
    Controls:
      - Up / Down: move paddle
      - C: return to menu
    """
    def __init__(self, ctx=None):
        self.players_mode = get_context_setting(ctx, "players", "cpu")
        self.paddle_height = 10
        self.paddle_speed = 3
        self.ai_min_speed = 1
        self.ai_max_speed = 3
        self.left_paddle_x = 1
        self.right_paddle_x = WIDTH - 2
        self.left_paddle_y = PLAY_HEIGHT // 2 - self.paddle_height // 2
        self.right_paddle_y = PLAY_HEIGHT // 2 - self.paddle_height // 2
        self._prev_left_paddle_y = self.left_paddle_y
        self._prev_right_paddle_y = self.right_paddle_y
        self.ball_speed = [1, 1]
        self.ball_position = [WIDTH // 2, PLAY_HEIGHT // 2]
        self.left_score = 0
        self.right_score = 0
        self.lives = 3

    def reset_ball(self):
        self.ball_position = [WIDTH // 2, PLAY_HEIGHT // 2]
        self.ball_speed = [random.choice([-1, 1]), random.choice([-2, -1, 1, 2])]

    def reset_match(self):
        self.left_paddle_y = PLAY_HEIGHT // 2 - self.paddle_height // 2
        self.right_paddle_y = PLAY_HEIGHT // 2 - self.paddle_height // 2
        self._prev_left_paddle_y = self.left_paddle_y
        self._prev_right_paddle_y = self.right_paddle_y
        self.left_score = 0
        self.right_score = 0
        self.lives = 3
        self.reset_ball()

    def _draw_paddle(self, x, y, color):
        for py in range(y, y + self.paddle_height):
            if 0 <= py < PLAY_HEIGHT:
                display.set_pixel(x, py, color[0], color[1], color[2])

    def draw_paddles(self):
        if self._prev_left_paddle_y != self.left_paddle_y:
            self._draw_paddle(self.left_paddle_x, self._prev_left_paddle_y, (0, 0, 0))
        if self._prev_right_paddle_y != self.right_paddle_y:
            self._draw_paddle(self.right_paddle_x, self._prev_right_paddle_y, (0, 0, 0))

        self._draw_paddle(self.left_paddle_x, self.left_paddle_y, (255, 255, 255))
        self._draw_paddle(self.right_paddle_x, self.right_paddle_y, (255, 255, 255))
        self._prev_left_paddle_y = self.left_paddle_y
        self._prev_right_paddle_y = self.right_paddle_y

    def _apply_paddle_english(self, paddle_y):
        hit_offset = self.ball_position[1] - paddle_y
        segment = (hit_offset * 5) // self.paddle_height
        if segment <= 0:
            self.ball_speed[1] = -2
        elif segment == 1:
            self.ball_speed[1] = -1
        elif segment == 2:
            self.ball_speed[1] = 0
        elif segment == 3:
            self.ball_speed[1] = 1
        else:
            self.ball_speed[1] = 2

    def clear_ball(self):
        x, y = self.ball_position
        if 0 <= y < PLAY_HEIGHT:
            display.set_pixel(x, y, 0, 0, 0)

    def draw_ball(self):
        x, y = self.ball_position
        if 0 <= y < PLAY_HEIGHT:
            display.set_pixel(x, y, 255, 255, 255)

    def update_paddles(self, joystick):
        if self.players_mode == "two":
            d = read_wasd_direction([JOYSTICK_UP, JOYSTICK_DOWN], debounce=False)
        else:
            d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN])
        if d == JOYSTICK_UP:
            self.left_paddle_y = max(self.left_paddle_y - self.paddle_speed, 0)
        elif d == JOYSTICK_DOWN:
            self.left_paddle_y = min(self.left_paddle_y + self.paddle_speed, PLAY_HEIGHT - self.paddle_height)

        if self.players_mode == "two":
            p2 = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN], debounce=False)
            if p2 == JOYSTICK_UP:
                self.right_paddle_y = max(self.right_paddle_y - self.paddle_speed, 0)
            elif p2 == JOYSTICK_DOWN:
                self.right_paddle_y = min(self.right_paddle_y + self.paddle_speed, PLAY_HEIGHT - self.paddle_height)
            return

        # Lightweight AI: good enough to rally, imperfect enough to beat.
        by = self.ball_position[1]
        pc = self.right_paddle_y + self.paddle_height // 2
        ai_speed = self.ai_min_speed + min(self.ai_max_speed - self.ai_min_speed, self.left_score // 35)
        if self.ball_speed[0] < 0:
            # Re-center slowly while the ball travels away.
            target = PLAY_HEIGHT // 2
            if pc < target - 2:
                self.right_paddle_y = min(self.right_paddle_y + 1, PLAY_HEIGHT - self.paddle_height)
            elif pc > target + 2:
                self.right_paddle_y = max(self.right_paddle_y - 1, 0)
            return
        if by < pc - 1:
            self.right_paddle_y = max(self.right_paddle_y - ai_speed, 0)
        elif by > pc + 1:
            self.right_paddle_y = min(self.right_paddle_y + ai_speed, PLAY_HEIGHT - self.paddle_height)

    def update_ball(self):
        global game_over, global_score
        self.clear_ball()

        self.ball_position[0] += self.ball_speed[0]
        self.ball_position[1] += self.ball_speed[1]

        x, y = self.ball_position

        if y <= 0 or y >= PLAY_HEIGHT - 1:
            self.ball_position[1] = max(0, min(PLAY_HEIGHT - 1, y))
            self.ball_speed[1] = -self.ball_speed[1]
            y = self.ball_position[1]

        # left paddle hit
        if x == self.left_paddle_x + 1 and self.left_paddle_y <= y < self.left_paddle_y + self.paddle_height:
            self.ball_position[0] = self.left_paddle_x + 1
            self.ball_speed[0] = abs(self.ball_speed[0])
            self._apply_paddle_english(self.left_paddle_y)
            self.left_score += 1

        # right paddle hit
        if x == self.right_paddle_x - 1 and self.right_paddle_y <= y < self.right_paddle_y + self.paddle_height:
            self.ball_position[0] = self.right_paddle_x - 1
            self.ball_speed[0] = -abs(self.ball_speed[0])
            self._apply_paddle_english(self.right_paddle_y)

        # miss left
        if x <= 0:
            if self.players_mode == "two":
                self.right_score += 1
                if self.right_score >= 5:
                    set_game_over_score(self.left_score, won=False)
                    return
                self.reset_ball()
                return
            self.lives -= 1
            if self.lives <= 0:
                set_game_over_score(self.left_score, won=False)
                return
            # nur leichte Strafe, keine komplette Score-Nullung
            if self.left_score > 0:
                self.left_score = max(0, self.left_score - 5)
            self.reset_ball()
            return

        # miss right -> bonus
        if x >= WIDTH - 1:
            if self.players_mode == "two":
                self.left_score += 1
                if self.left_score >= 5:
                    set_game_over_score(self.left_score, won=True)
                    return
                self.reset_ball()
                return
            self.left_score += 10
            self.reset_ball()

        global_score = self.left_score
        self.draw_ball()

    def _build_step(self, joystick):
        global game_over
        game_over = False
        display.clear()
        self.reset_match()
        display_score_and_time(0, force=True)
        def step():
            c_button, _ = joystick.read_buttons()
            if c_button or game_over:
                return False
            self.update_paddles(joystick)
            self.update_ball()
            self.draw_paddles()
            if self.players_mode == "two":
                draw_rectangle(0, PLAY_HEIGHT, WIDTH - 1, HEIGHT - 1, 0, 0, 0)
                draw_text_small(1, PLAY_HEIGHT, str(self.left_score) + "-" + str(self.right_score), 255, 255, 255)
            else:
                display_score_and_time(self.left_score)
            return True
        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(45, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(45, self._build_step(joystick))


class AirHockeyGame:
    """
    AIRHKY
    Controls:
      - Left / Right / Up / Down: move mallet
      - C: return to menu
    Fast puck-and-mallet air hockey with CPU or local 2-player support.
    """
    FRAME_MS = 30
    RINK_LEFT = 3
    RINK_RIGHT = WIDTH - 4
    RINK_TOP = 3
    RINK_BOTTOM = PLAY_HEIGHT - 3
    GOAL_HALF = 7
    PUCK_R = 1.1
    MALLET_R = 3.3
    MALLET_SPEED = 1.55
    CPU_SPEED = 1.35
    PUCK_MAX_SPEED = 4.3

    def __init__(self, ctx=None):
        self.players_mode = get_context_setting(ctx, "players", "cpu")
        self.target_goals = int(get_context_setting(ctx, "goals", 5) or 5)
        self.reset()

    def reset(self):
        self.left_score = 0
        self.right_score = 0
        self.frame = 0
        self.flash = 0
        self.last_z = False
        self.left_x = 12.0
        self.left_y = PLAY_HEIGHT / 2
        self.right_x = WIDTH - 13.0
        self.right_y = PLAY_HEIGHT / 2
        self.prev_left_x = self.left_x
        self.prev_left_y = self.left_y
        self.prev_right_x = self.right_x
        self.prev_right_y = self.right_y
        self.puck_x = WIDTH / 2
        self.puck_y = PLAY_HEIGHT / 2
        self.puck_vx = 1.65
        self.puck_vy = random.choice((-0.9, -0.45, 0.45, 0.9))

    def _puck_speed(self):
        return math.sqrt(self.puck_vx * self.puck_vx + self.puck_vy * self.puck_vy)

    def _serve(self, direction=1):
        self.puck_x = WIDTH / 2
        self.puck_y = PLAY_HEIGHT / 2
        self.puck_vx = direction * (1.25 + random.random() * 0.55)
        self.puck_vy = random.choice((-0.95, -0.55, 0.55, 0.95))
        self.flash = 8

    def _keep_left(self, x, y):
        return clamp(x, self.RINK_LEFT + 4, WIDTH / 2 - 6), clamp(y, self.RINK_TOP + 4, self.RINK_BOTTOM - 4)

    def _keep_right(self, x, y):
        return clamp(x, WIDTH / 2 + 6, self.RINK_RIGHT - 4), clamp(y, self.RINK_TOP + 4, self.RINK_BOTTOM - 4)

    def _move_left(self, direction):
        if direction is None:
            self.prev_left_x = self.left_x
            self.prev_left_y = self.left_y
            return
        dx, dy = direction_to_delta_8way(direction)
        self.prev_left_x = self.left_x
        self.prev_left_y = self.left_y
        self.left_x, self.left_y = self._keep_left(self.left_x + dx * self.MALLET_SPEED, self.left_y + dy * self.MALLET_SPEED)

    def _move_right(self, direction):
        if direction is None:
            self.prev_right_x = self.right_x
            self.prev_right_y = self.right_y
            return
        dx, dy = direction_to_delta_8way(direction)
        self.prev_right_x = self.right_x
        self.prev_right_y = self.right_y
        self.right_x, self.right_y = self._keep_right(self.right_x + dx * self.MALLET_SPEED, self.right_y + dy * self.MALLET_SPEED)

    def _predict_puck_y(self, target_x):
        x = self.puck_x
        y = self.puck_y
        vx = self.puck_vx
        vy = self.puck_vy
        if abs(vx) < 0.08:
            return y
        for _ in range(96):
            if vx > 0 and x >= target_x:
                break
            if vx < 0 and x <= target_x:
                break
            x += vx
            y += vy
            vx *= 0.995
            vy *= 0.995
            if y <= self.RINK_TOP + self.PUCK_R:
                y = self.RINK_TOP + self.PUCK_R
                vy = abs(vy)
            elif y >= self.RINK_BOTTOM - self.PUCK_R:
                y = self.RINK_BOTTOM - self.PUCK_R
                vy = -abs(vy)
        return clamp(y, self.RINK_TOP + 3, self.RINK_BOTTOM - 3)

    def _cpu_direction(self):
        defend = self.puck_vx > 0.04 or self.puck_x > WIDTH * 0.58
        if defend:
            target_x = self.RINK_RIGHT - 8.0
            target_y = self._predict_puck_y(target_x)
            target_y += clamp(self.puck_vy * 2.4, -2.2, 2.2)
            if self.puck_x > WIDTH * 0.78:
                target_y += clamp((self.puck_y - PLAY_HEIGHT / 2) * 0.16, -1.5, 1.5)
        else:
            target_x = WIDTH - 13.0
            target_y = PLAY_HEIGHT / 2 + clamp((self.puck_y - PLAY_HEIGHT / 2) * 0.28, -3.5, 3.5)
        dx = target_x - self.right_x
        dy = target_y - self.right_y
        if abs(dx) < 0.8 and abs(dy) < 0.8:
            return None
        dirs = []
        if dy < -1:
            dirs.append(JOYSTICK_UP)
        elif dy > 1:
            dirs.append(JOYSTICK_DOWN)
        if dx < -1:
            dirs.append(JOYSTICK_LEFT)
        elif dx > 1:
            dirs.append(JOYSTICK_RIGHT)
        if len(dirs) == 2:
            pair = tuple(sorted(dirs))
            if pair == (JOYSTICK_LEFT, JOYSTICK_UP):
                return JOYSTICK_UP_LEFT
            if pair == (JOYSTICK_RIGHT, JOYSTICK_UP):
                return JOYSTICK_UP_RIGHT
            if pair == (JOYSTICK_LEFT, JOYSTICK_DOWN):
                return JOYSTICK_DOWN_LEFT
            if pair == (JOYSTICK_DOWN, JOYSTICK_RIGHT):
                return JOYSTICK_DOWN_RIGHT
        return dirs[0] if dirs else None

    def _bounce_puck_off_mallet(self, mx, my, prev_mx, prev_my):
        dx = self.puck_x - mx
        dy = self.puck_y - my
        min_d = self.MALLET_R + self.PUCK_R
        d2 = dx * dx + dy * dy
        if d2 <= 0.0001 or d2 >= min_d * min_d:
            return False
        dist = math.sqrt(d2)
        nx = dx / dist
        ny = dy / dist
        overlap = min_d - dist
        self.puck_x += nx * overlap
        self.puck_y += ny * overlap
        rel_vx = self.puck_vx - (mx - prev_mx) * 0.6
        rel_vy = self.puck_vy - (my - prev_my) * 0.6
        vel_n = rel_vx * nx + rel_vy * ny
        if vel_n > 0:
            vel_n = -vel_n * 0.5
        self.puck_vx -= 1.9 * vel_n * nx
        self.puck_vy -= 1.9 * vel_n * ny
        self.puck_vx += (mx - prev_mx) * 0.45
        self.puck_vy += (my - prev_my) * 0.45
        speed = self._puck_speed()
        if speed > self.PUCK_MAX_SPEED:
            scale = self.PUCK_MAX_SPEED / speed
            self.puck_vx *= scale
            self.puck_vy *= scale
        self.flash = 4
        return True

    def _goal(self, left_side):
        if left_side:
            self.right_score += 1
            self._serve(1)
        else:
            self.left_score += 1
            self._serve(-1)
        global global_score
        global_score = max(self.left_score, self.right_score)
        if self.left_score >= self.target_goals or self.right_score >= self.target_goals:
            won = self.left_score > self.right_score
            if self.players_mode == "two":
                won = self.left_score > self.right_score
            set_game_over_score(max(self.left_score, self.right_score), won=won)
            return True
        return False

    def _advance_puck(self):
        self.puck_x += self.puck_vx
        self.puck_y += self.puck_vy
        self.puck_vx *= 0.995
        self.puck_vy *= 0.995
        if self._puck_speed() < 0.03:
            self.puck_vx = 0.0
            self.puck_vy = 0.0

        if self.puck_y <= self.RINK_TOP + self.PUCK_R:
            self.puck_y = self.RINK_TOP + self.PUCK_R
            self.puck_vy = abs(self.puck_vy)
        elif self.puck_y >= self.RINK_BOTTOM - self.PUCK_R:
            self.puck_y = self.RINK_BOTTOM - self.PUCK_R
            self.puck_vy = -abs(self.puck_vy)

        goal_y = PLAY_HEIGHT / 2
        if self.puck_x <= self.RINK_LEFT + self.PUCK_R:
            if abs(self.puck_y - goal_y) <= self.GOAL_HALF:
                if self._goal(left_side=True):
                    return False
                return True
            self.puck_x = self.RINK_LEFT + self.PUCK_R
            self.puck_vx = abs(self.puck_vx)
        elif self.puck_x >= self.RINK_RIGHT - self.PUCK_R:
            if abs(self.puck_y - goal_y) <= self.GOAL_HALF:
                if self._goal(left_side=False):
                    return False
                return True
            self.puck_x = self.RINK_RIGHT - self.PUCK_R
            self.puck_vx = -abs(self.puck_vx)

        self._bounce_puck_off_mallet(self.left_x, self.left_y, self.prev_left_x, self.prev_left_y)
        self._bounce_puck_off_mallet(self.right_x, self.right_y, self.prev_right_x, self.prev_right_y)
        return True

    def _draw_rink(self):
        display.clear()
        draw_rectangle(0, 0, WIDTH - 1, PLAY_HEIGHT - 1, 14, 90, 70)
        draw_rectangle(self.RINK_LEFT, self.RINK_TOP, self.RINK_RIGHT, self.RINK_BOTTOM, 8, 120, 92)
        draw_rect_outline(self.RINK_LEFT, self.RINK_TOP, self.RINK_RIGHT, self.RINK_BOTTOM, 220, 220, 220)
        draw_line(WIDTH // 2, self.RINK_TOP + 1, WIDTH // 2, self.RINK_BOTTOM - 1, 220, 220, 220)
        for y in range(self.RINK_TOP + 4, self.RINK_BOTTOM - 3, 8):
            draw_line(WIDTH // 2 - 1, y, WIDTH // 2 + 1, y + 1, 220, 220, 220)
        goal_y1 = int(PLAY_HEIGHT / 2 - self.GOAL_HALF)
        goal_y2 = int(PLAY_HEIGHT / 2 + self.GOAL_HALF)
        draw_rectangle(self.RINK_LEFT, goal_y1, self.RINK_LEFT + 1, goal_y2, 0, 0, 0)
        draw_rectangle(self.RINK_RIGHT - 1, goal_y1, self.RINK_RIGHT, goal_y2, 0, 0, 0)

    def _draw_player(self, x, y, color):
        draw_rectangle(int(x) - 2, int(y) - 2, int(x) + 2, int(y) + 2, *color)
        draw_rect_outline(int(x) - 2, int(y) - 2, int(x) + 2, int(y) + 2, 255, 255, 255)

    def _draw_hud(self):
        draw_rectangle(0, PLAY_HEIGHT, WIDTH - 1, HEIGHT - 1, 0, 0, 0)
        draw_text_small(1, PLAY_HEIGHT, str(self.left_score), 70, 170, 255)
        draw_text_small(11, PLAY_HEIGHT, "-", 255, 255, 255)
        draw_text_small(18, PLAY_HEIGHT, str(self.right_score), 255, 90, 90)
        draw_text_small(31, PLAY_HEIGHT, "T" + str(self.target_goals), 200, 200, 200)
        mode = "2P" if self.players_mode == "two" else "CPU"
        draw_text_small(44, PLAY_HEIGHT, mode, 160, 160, 160)

    def _draw(self):
        self._draw_rink()
        self._draw_player(self.left_x, self.left_y, (70, 170, 255))
        self._draw_player(self.right_x, self.right_y, (255, 90, 90))
        if self.flash:
            self.flash -= 1
        draw_rectangle(int(self.puck_x) - 1, int(self.puck_y) - 1, int(self.puck_x) + 1, int(self.puck_y) + 1, 255, 255, 255)
        self._draw_hud()
        global global_score
        global_score = max(self.left_score, self.right_score)
        display_flush()

    def _build_step(self, joystick):
        self.reset()
        begin_game(0)

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            self.frame += 1
            if self.players_mode == "two":
                left_dir = read_wasd_direction(
                    [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT,
                     JOYSTICK_UP_LEFT, JOYSTICK_UP_RIGHT, JOYSTICK_DOWN_LEFT, JOYSTICK_DOWN_RIGHT],
                    debounce=True
                )
                right_dir = joystick.read_direction(
                    [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT,
                     JOYSTICK_UP_LEFT, JOYSTICK_UP_RIGHT, JOYSTICK_DOWN_LEFT, JOYSTICK_DOWN_RIGHT],
                    debounce=True
                )
            else:
                left_dir = joystick.read_direction(
                    [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT,
                     JOYSTICK_UP_LEFT, JOYSTICK_UP_RIGHT, JOYSTICK_DOWN_LEFT, JOYSTICK_DOWN_RIGHT],
                    debounce=True
                )
                right_dir = self._cpu_direction()
            self._move_left(left_dir)
            self._move_right(right_dir)
            if not self._advance_puck():
                self._draw()
                return False
            self._draw()
            return True
        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


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
    BREAKOUT
    Controls:
      - Left / Right: move paddle
      - C: return to menu
    """
    def __init__(self, ctx=None):
        self.powerups_enabled = bool(get_context_setting(ctx, "powerups", False))
        self.paddle_x = (WIDTH - PADDLE_WIDTH) // 2
        self.paddle_y = PLAY_HEIGHT - PADDLE_HEIGHT
        self.paddle_w = PADDLE_WIDTH
        self.wide_timer = 0
        self.ball_x = WIDTH // 2
        self.ball_y = PLAY_HEIGHT // 2
        self.ball_dx = 1
        self.ball_dy = -1
        self.bricks = self.create_bricks()
        self.score = 0
        self.paddle_speed = 2
        self.powerups = []

    def create_bricks(self):
        bricks = []
        for row in range(BRICK_ROWS):
            for col in range(BRICK_COLS):
                x = col * (BRICK_WIDTH + 1) + 1
                y = row * (BRICK_HEIGHT + 1)
                bricks.append((x, y))
        return bricks

    def draw_paddle(self):
        draw_rectangle(self.paddle_x, self.paddle_y, self.paddle_x + self.paddle_w - 1, self.paddle_y + PADDLE_HEIGHT - 1, 255, 255, 255)

    def clear_paddle(self):
        draw_rectangle(self.paddle_x, self.paddle_y, self.paddle_x + self.paddle_w - 1, self.paddle_y + PADDLE_HEIGHT - 1, 0, 0, 0)

    def draw_ball(self):
        bx, by = int(self.ball_x), int(self.ball_y)
        draw_rectangle(bx, by, bx + 1, by + 1, 255, 255, 255)

    def clear_ball(self):
        bx, by = int(self.ball_x), int(self.ball_y)
        draw_rectangle(bx, by, bx + 1, by + 1, 0, 0, 0)

    def draw_bricks(self):
        for x, y in self.bricks:
            hue = (y * 300) // max(1, (BRICK_ROWS * (BRICK_HEIGHT + 1)))
            r, g, b = hsb_to_rgb(hue, 1, 1)
            draw_rectangle(x, y, x + BRICK_WIDTH - 1, y + BRICK_HEIGHT - 1, r, g, b)

    def update_ball(self):
        global game_over, global_score
        self.clear_ball()
        self.ball_x += self.ball_dx
        self.ball_y += self.ball_dy

        # wall bounce (ball is 2x2; top-left coords)
        if self.ball_x <= 0:
            self.ball_x = 0
            self.ball_dx = abs(self.ball_dx)
        elif self.ball_x >= WIDTH - 2:
            self.ball_x = WIDTH - 2
            self.ball_dx = -abs(self.ball_dx)
            
        if self.ball_y <= 0:
            self.ball_dy = -self.ball_dy

        # paddle bounce
        if self.ball_y + 1 >= self.paddle_y:
            if self.paddle_x <= self.ball_x + 1 and self.ball_x <= self.paddle_x + self.paddle_w - 1:
                self.ball_dy = -abs(self.ball_dy)
                self.ball_y = self.paddle_y - 2
                
                # apply spin based on paddle movement
                last_move = getattr(self, "last_paddle_move", None)
                if last_move == JOYSTICK_LEFT:
                    self.ball_dx -= 0.5
                elif last_move == JOYSTICK_RIGHT:
                    self.ball_dx += 0.5
                # clamp max x speed
                self.ball_dx = max(-1.8, min(1.8, self.ball_dx))

        # below paddle -> lost
        if self.ball_y >= PLAY_HEIGHT:
            global_score = self.score
            game_over = True
            return

        self.draw_ball()

    def check_collision_with_bricks(self):
        global global_score
        bx = int(self.ball_x)
        by = int(self.ball_y)
        for brick in self.bricks:
            x, y = brick
            if point_in_rect(bx, by, x, y, BRICK_WIDTH, BRICK_HEIGHT):
                self.bricks.remove(brick)
                self.ball_dy = -self.ball_dy
                self.score += 10
                global_score = self.score
                draw_rectangle(x, y, x + BRICK_WIDTH - 1, y + BRICK_HEIGHT - 1, 0, 0, 0)
                if self.powerups_enabled and random.randint(0, 99) < 18 and len(self.powerups) < 3:
                    self.powerups.append([x + BRICK_WIDTH // 2, y + BRICK_HEIGHT, 0])
                break

    def update_paddle(self, joystick):
        d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT])
        self.last_paddle_move = d
        if d == JOYSTICK_LEFT:
            self.clear_paddle()
            self.paddle_x = max(self.paddle_x - self.paddle_speed, 0)
        elif d == JOYSTICK_RIGHT:
            self.clear_paddle()
            self.paddle_x = min(self.paddle_x + self.paddle_speed, WIDTH - self.paddle_w)
        self.draw_paddle()

    def update_powerups(self):
        if not self.powerups_enabled:
            return
        keep = []
        for p in self.powerups:
            draw_rectangle(int(p[0]) - 1, int(p[1]) - 1, int(p[0]) + 1, int(p[1]) + 1, 0, 0, 0)
            p[1] += 0.65
            if p[1] >= self.paddle_y - 1:
                if self.paddle_x - 1 <= p[0] <= self.paddle_x + self.paddle_w:
                    self.wide_timer = 360
                    self.clear_paddle()
                    self.paddle_w = min(20, PADDLE_WIDTH + 6)
                    self.paddle_x = min(self.paddle_x, WIDTH - self.paddle_w)
                    play_web_sound("coin", 4)
                    continue
            if p[1] < PLAY_HEIGHT:
                keep.append(p)
                draw_rectangle(int(p[0]) - 1, int(p[1]) - 1, int(p[0]) + 1, int(p[1]) + 1, 80, 220, 255)
        self.powerups = keep
        if self.wide_timer > 0:
            self.wide_timer -= 1
            if self.wide_timer == 0:
                self.clear_paddle()
                center = self.paddle_x + self.paddle_w // 2
                self.paddle_w = PADDLE_WIDTH
                self.paddle_x = clamp(center - self.paddle_w // 2, 0, WIDTH - self.paddle_w)

    def _start_round(self, show_hud=True):
        global game_over, global_score
        game_over = False
        global_score = 0
        self.score = 0
        self.paddle_x = (WIDTH - PADDLE_WIDTH) // 2
        self.paddle_y = PLAY_HEIGHT - PADDLE_HEIGHT
        self.paddle_w = PADDLE_WIDTH
        self.wide_timer = 0
        self.ball_x = WIDTH // 2
        self.ball_y = PLAY_HEIGHT // 2
        self.ball_dx = 1
        self.ball_dy = -1
        self.bricks = self.create_bricks()
        self.powerups = []
        display.clear()
        self.draw_bricks()
        self.draw_paddle()
        self.draw_ball()
        if show_hud:
            display_score_and_time(0, force=True)
        else:
            draw_rectangle(0, PLAY_HEIGHT, WIDTH - 1, HEIGHT - 1, 0, 0, 0)

    def _step_once(self, joystick, show_win=True, show_hud=True):
        global game_over
        c_button, _ = joystick.read_buttons()
        if c_button or game_over:
            return False

        self.update_ball()
        if game_over:
            return False
        self.check_collision_with_bricks()
        self.update_powerups()
        self.update_paddle(joystick)
        if show_hud:
            display_score_and_time(self.score)
        else:
            draw_rectangle(0, PLAY_HEIGHT, WIDTH - 1, HEIGHT - 1, 0, 0, 0)

        if not self.bricks:
            set_game_over_score(self.score, won=True)
            if show_win:
                show_center_message(("YOU", "WON"), start_y=10, line_height=15, delay_ms=1500)
            return False
        return True

    def main_loop(self, joystick):
        self._start_round()

        while True:
            if not self._step_once(joystick):
                return

            sleep_ms(35)
            maybe_collect(150)

    async def main_loop_async(self, joystick):
        """Async version for pygbag: yields with asyncio.sleep()."""
        if asyncio is None:
            return self.main_loop(joystick)
        
        self._start_round()
        
        def loop_iteration():
            return self._step_once(joystick, show_win=False)
        
        await _run_game_loop_async(35, loop_iteration)

# ---------- Asteroids ----------
SHIP_COOLDOWN = const(10)
FPS = const(20)
PIXEL_WIDTH = WIDTH
PIXEL_HEIGHT = PLAY_HEIGHT

class AsteroidGame:
    """
    ASTEROIDS
    Controls:
      - Left / Right: rotate ship
      - Up: thrust
      - Z: shoot
      - C: return to menu
    """
    _SHAPE_CACHE = None

    @classmethod
    def _shape_offsets(cls, size):
        if cls._SHAPE_CACHE is None:
            cls._SHAPE_CACHE = {}
        if size not in cls._SHAPE_CACHE:
            pts = []
            for deg in range(0, 360, 12):
                rad = math.radians(deg)
                pts.append((int(math.cos(rad) * size), int(math.sin(rad) * size)))
            cls._SHAPE_CACHE[size] = pts
        return cls._SHAPE_CACHE[size]

    class Projectile:
        def __init__(self, x, y, angle, speed):
            self.x = x
            self.y = y
            self.angle = angle
            self.speed = speed
            rad = math.radians(angle)
            self.vx = math.cos(rad) * speed
            self.vy = -math.sin(rad) * speed
            self.tip_dx = math.cos(rad)
            self.tip_dy = -math.sin(rad)
            self.lifetime = 12

        def update(self):
            self.x += self.vx
            self.y += self.vy
            self.x %= PIXEL_WIDTH
            self.y %= PIXEL_HEIGHT
            self.lifetime -= 1

        def is_alive(self):
            return self.lifetime > 0

        def draw_line(self, start, end, color):
            # Delegate to module-level helper to avoid code duplication with Ship
            _draw_line_wrapped(start, end, color)

        def draw(self):
            ex = self.x + self.tip_dx
            ey = self.y + self.tip_dy
            self.draw_line((self.x, self.y), (ex, ey), (255, 0, 0))

    class Asteroid:
        def __init__(self, x=None, y=None, size=None, start=False, speed_boost=0.0):
            self.x = 32 if x is None else x
            self.y = 24 if y is None else y
            if start:
                while (22 < self.x < 42) and (16 < self.y < 40):
                    self.x = random.uniform(0, PIXEL_WIDTH)
                    self.y = random.uniform(0, PIXEL_HEIGHT)
            self.angle = random.uniform(0, 360)
            self.speed = random.uniform(0.3 + speed_boost, 0.8 + speed_boost)
            rad = math.radians(self.angle)
            self.vx = math.cos(rad) * self.speed
            self.vy = -math.sin(rad) * self.speed
            self.size = size if size is not None else random.randint(4, 8)
            self.shape = AsteroidGame._shape_offsets(self.size)

        def update(self):
            self.x += self.vx
            self.y += self.vy
            self.x %= PIXEL_WIDTH
            self.y %= PIXEL_HEIGHT

        def draw(self):
            sp = display.set_pixel
            sx = int(self.x)
            sy = int(self.y)
            for ox, oy in self.shape:
                px = (sx + ox) % PIXEL_WIDTH
                py = (sy + oy) % PIXEL_HEIGHT
                sp(px, py, *WHITE)

    class Ship:
        def __init__(self):
            self.x = PIXEL_WIDTH / 2
            self.y = PIXEL_HEIGHT / 2
            self.angle = 0
            self.speed = 0
            self.max_speed = 3.0
            self.size = 3
            self.cooldown = 0
            self.thrusting = False
            self.flame_phase = 0

        def draw_line(self, start, end, color):
            # Delegate to module-level helper shared with Projectile
            _draw_line_wrapped(start, end, color)

        def update(self, direction):
            turn_step = 9 if self.speed <= 0.05 else 7
            if direction == JOYSTICK_LEFT:
                self.angle = (self.angle + turn_step) % 360
            elif direction == JOYSTICK_RIGHT:
                self.angle = (self.angle - turn_step) % 360

            if direction == JOYSTICK_UP:
                self.speed = min(self.speed + 0.20, self.max_speed)
                self.thrusting = True
            else:
                self.speed = max(self.speed - 0.08, 0)
                self.thrusting = False

            rad = math.radians(self.angle)
            ca = math.cos(rad)
            sa = math.sin(rad)
            self.x += ca * self.speed
            self.y -= sa * self.speed
            self.x %= PIXEL_WIDTH
            self.y %= PIXEL_HEIGHT

            if self.cooldown > 0:
                self.cooldown -= 1
            self.flame_phase = (self.flame_phase + 1) & 7

        def _fill_triangle(self, points, color):
            pts = [(int(round(x)), int(round(y))) for x, y in points]
            min_y = max(0, min(p[1] for p in pts))
            max_y = min(PIXEL_HEIGHT - 1, max(p[1] for p in pts))
            sp = display.set_pixel
            for y in range(min_y, max_y + 1):
                xs = []
                for i in range(3):
                    x1, y1 = pts[i]
                    x2, y2 = pts[(i + 1) % 3]
                    if y1 == y2:
                        continue
                    if min(y1, y2) <= y <= max(y1, y2):
                        t = (y - y1) / float(y2 - y1)
                        xs.append(x1 + (x2 - x1) * t)
                if len(xs) >= 2:
                    xs.sort()
                    x0 = max(0, int(math.ceil(xs[0])))
                    x1 = min(PIXEL_WIDTH - 1, int(math.floor(xs[-1])))
                    for x in range(x0, x1 + 1):
                        sp(x, y, *color)

        def _draw_flame(self, p1, p2, rad):
            if not self.thrusting:
                return
            bx = (p1[0] + p2[0]) * 0.5
            by = (p1[1] + p2[1]) * 0.5
            length = 4 + (self.flame_phase & 1)
            tail = (bx - math.cos(rad) * length, by + math.sin(rad) * length)
            wide = 1.0 + (self.flame_phase % 3) * 0.25
            self.draw_line(p1, tail, (255, 60, 0))
            self.draw_line(p2, tail, (255, 120, 0))
            self.draw_line((bx - math.sin(rad) * wide, by - math.cos(rad) * wide),
                           tail, (255, 220, 40))

        def draw(self):
            a = self.angle
            s = self.size
            rad0 = math.radians(a)
            rad1 = math.radians(a + 120)
            rad2 = math.radians(a - 120)
            p0 = (self.x + math.cos(rad0) * s,
                  self.y - math.sin(rad0) * s)
            p1 = (self.x + math.cos(rad1) * s,
                  self.y - math.sin(rad1) * s)
            p2 = (self.x + math.cos(rad2) * s,
                  self.y - math.sin(rad2) * s)

            self._draw_flame(p1, p2, rad0)
            self._fill_triangle((p0, p1, p2), WHITE)
            self.draw_line(p1, p2, (170, 210, 255))
            self.draw_line(p0, p1, WHITE)
            self.draw_line(p2, p0, WHITE)

        def shoot(self):
            if self.cooldown == 0:
                self.cooldown = SHIP_COOLDOWN
                bullet_speed = 4
                rad = math.radians(self.angle)
                bx = self.x + math.cos(rad) * self.size
                by = self.y - math.sin(rad) * self.size
                return AsteroidGame.Projectile(bx, by, self.angle, bullet_speed)
            return None

    def __init__(self):
        self.ship = self.Ship()
        self.asteroids = [self.Asteroid(start=True) for _ in range(3)]
        self.projectiles = []
        self.max_projectiles = 4 if CONFIG_LOW_RAM_MODE else 6
        self.max_asteroids = 8 if CONFIG_LOW_RAM_MODE else 12
        self.score = 0

    def check_collisions(self):
        global game_over, global_score
        speed_boost = min(self.score / 600.0, 1.5)
        # projectile vs asteroid
        hit_asteroids = bytearray(len(self.asteroids))
        hit_count = 0
        keep_i = 0
        spawned = []
        for p in self.projectiles:
            hit_ai = -1
            hit_a = None
            for ai, a in enumerate(self.asteroids):
                if hit_asteroids[ai]:
                    continue
                dx = p.x - a.x
                dy = p.y - a.y
                if dx * dx + dy * dy < a.size * a.size:
                    hit_ai = ai
                    hit_a = a
                    break
            if hit_ai >= 0:
                hit_asteroids[hit_ai] = 1
                hit_count += 1
                self.score += 10
                if hit_a.size > 3:
                    half = max(2, hit_a.size // 2)
                    if len(self.asteroids) + len(spawned) < self.max_asteroids:
                        spawned.append(self.Asteroid(hit_a.x, hit_a.y, half, speed_boost=speed_boost))
                    if len(self.asteroids) + len(spawned) < self.max_asteroids:
                        spawned.append(self.Asteroid(hit_a.x, hit_a.y, half, speed_boost=speed_boost))
            else:
                self.projectiles[keep_i] = p
                keep_i += 1
        del self.projectiles[keep_i:]
        if hit_count:
            keep_a = 0
            for i, a in enumerate(self.asteroids):
                if not hit_asteroids[i]:
                    self.asteroids[keep_a] = a
                    keep_a += 1
            del self.asteroids[keep_a:]
            if spawned:
                self.asteroids.extend(spawned)

        # ship vs asteroid
        for a in self.asteroids:
            dx = self.ship.x - a.x
            dy = self.ship.y - a.y
            limit = a.size + self.ship.size
            if dx * dx + dy * dy < limit * limit:
                game_over = True
                global_score = self.score
                return

    def _build_step(self, joystick):
        global game_over, global_score
        game_over = False
        global_score = 0
        self.ship = self.Ship()
        self.asteroids = [self.Asteroid(start=True) for _ in range(3)]
        self.projectiles = []
        self.max_projectiles = 4 if CONFIG_LOW_RAM_MODE else 6
        self.max_asteroids = 8 if CONFIG_LOW_RAM_MODE else 12
        self.score = 0
        display.clear()
        display_score_and_time(0, force=True)
        def step():
            global game_over, global_score
            c_button, z_button = joystick.read_buttons()
            if c_button or game_over:
                return False
            direction = joystick.read_direction([JOYSTICK_UP, JOYSTICK_LEFT, JOYSTICK_RIGHT])
            self.ship.update(direction)
            if z_button:
                pr = self.ship.shoot()
                if pr and len(self.projectiles) < self.max_projectiles:
                    self.projectiles.append(pr)
            for a in self.asteroids:
                a.update()
            keep_i = 0
            for p in self.projectiles:
                p.update()
                if p.is_alive():
                    self.projectiles[keep_i] = p
                    keep_i += 1
            del self.projectiles[keep_i:]
            self.check_collisions()
            if game_over:
                return False
            if not self.asteroids:
                speed_boost = min(self.score / 600.0, 1.5)
                self.asteroids = [self.Asteroid(start=True, speed_boost=speed_boost) for _ in range(3 if CONFIG_LOW_RAM_MODE else 4)]
            display.clear()
            self.ship.draw()
            for a in self.asteroids:
                a.draw()
            for p in self.projectiles:
                p.draw()
            display_score_and_time(self.score)
            global_score = self.score
            return True
        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(50, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(50, self._build_step(joystick))

# ---------- Qix ----------
class QixGame:
    """
    QIX
    Controls:
      - Left / Right / Up / Down: move and draw boundary
      - C: return to menu
    """
    def __init__(self):
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

    def initialize_game(self):
        display.clear()
        initialize_grid()
        self.draw_frame()
        self.place_player()
        self.place_opponents(self.num_opponents)
        self.occupied_percentage = 0
        self.prev_player_pos = 1
        display_score_and_time(0, force=True)

    def place_opponents(self, n):
        # place n opponents at random interior positions
        self.opponents = []
        for _ in range(n):
            ox = random.randint(1, self.width - 2)
            oy = random.randint(1, self.height - 2)
            odx = random.choice([-1, 1])
            ody = random.choice([-1, 1])
            self.opponents.append([ox, oy, odx, ody])
            display.set_pixel(ox, oy, 255, 0, 0)

    def draw_frame(self):
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
        edges = ([(x, 0) for x in range(self.width)] +
                 [(x, self.height - 1) for x in range(self.width)] +
                 [(0, y) for y in range(self.height)] +
                 [(self.width - 1, y) for y in range(self.height)])
        self.player_x, self.player_y = random.choice(edges)
        display.set_pixel(self.player_x, self.player_y, 0, 255, 0)

    def move_opponent(self):
        global game_over, global_score
        # move each opponent independently
        for op in self.opponents:
            ox = op[0]
            oy = op[1]
            dx = op[2]
            dy = op[3]

            nx = ox + dx
            ny = oy + dy

            # check collisions separately on x and y to allow bouncing
            v_x = get_grid_value(nx, oy)
            if v_x == 4:
                global_score = int(self.occupied_percentage)
                game_over = True
                return
            if v_x in (1, 2):
                dx = -dx

            v_y = get_grid_value(ox, ny)
            if v_y == 4:
                global_score = int(self.occupied_percentage)
                game_over = True
                return
            if v_y in (1, 2):
                dy = -dy

            # recompute target after possible bounce
            nx = ox + dx
            ny = oy + dy
            if get_grid_value(nx, ny) == 4 or (nx == self.player_x and ny == self.player_y):
                global_score = int(self.occupied_percentage)
                game_over = True
                return

            # move opponent pixel
            display.set_pixel(ox, oy, 0, 0, 0)
            op[0] = nx
            op[1] = ny
            op[2] = dx
            op[3] = dy
            display.set_pixel(nx, ny, 255, 0, 0)

    def move_player(self, joystick):
        d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
        if not d:
            return

        nx, ny = self.player_x, self.player_y
        if d == JOYSTICK_UP: ny -= 1
        elif d == JOYSTICK_DOWN: ny += 1
        elif d == JOYSTICK_LEFT: nx -= 1
        elif d == JOYSTICK_RIGHT: nx += 1

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
        # convert trail to border/filled
        set_grid_value(x, y, 1)
        display.set_pixel(x, y, 0, 0, 255)

        # Flood-fill all regions reachable by opponents. With multiple opponents,
        # using only the first one can incorrectly claim an area containing another.
        if self.opponents:
            for op in self.opponents:
                flood_fill(op[0], op[1], accessible_mark=3)
        else:
            flood_fill(self.width // 2, self.height // 2, accessible_mark=3)

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
        occ = count_cells_with_mark(2, self.width, self.height)
        self.occupied_percentage = (occ / (self.width * self.height)) * 100
        display_score_and_time(int(self.occupied_percentage))

    def _build_step(self, joystick):
        global game_over, global_score
        game_over = False
        global_score = 0
        self.initialize_game()
        def step():
            global game_over, global_score
            c_button, _ = joystick.read_buttons()
            if c_button or game_over:
                return False
            self.move_player(joystick)
            self.move_opponent()
            if game_over:
                return False
            if self.occupied_percentage > 75:
                global_score = int(self.occupied_percentage)
                display.clear()
                draw_text(6, 18, "LEVEL", 0, 255, 0)
                draw_text(6, 33, str(self.level), 0, 255, 0)
                sleep_ms(900)
                self.level += 1
                self.num_opponents += 1
                if self.num_opponents > 8:
                    self.num_opponents = 8
                self.initialize_game()
            return True
        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(35, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(35, self._build_step(joystick))

# ---------- Tetris ----------
class TetrisGame:
    """
    TETRIS
    Controls:
      - Left / Right: move piece
      - Down: soft drop
      - Up / Z: rotate piece
      - C: return to menu
    """
    GRID_WIDTH = 16
    GRID_HEIGHT = 13
    BLOCK_SIZE = 4

    COLORS = (
        (0, 255, 255), (255, 0, 0), (0, 255, 0), (0, 0, 255),
        (255, 255, 0), (255, 165, 0), (128, 0, 128),
    )

    TETRIMINOS = (
        ((1,1,1,1),),                # I
        ((1,1,1),(0,1,0)),          # T
        ((1,1,0),(0,1,1)),          # S
        ((0,1,1),(1,1,0)),          # Z
        ((1,1),(1,1)),              # O
        ((1,1,1),(1,0,0)),          # L
        ((1,1,1),(0,0,1)),          # J
    )

    class Piece:
        def __init__(self):
            idx = random.randint(0, len(TetrisGame.TETRIMINOS) - 1)
            self.shape = TetrisGame.TETRIMINOS[idx]
            self.color = random.randint(1, len(TetrisGame.COLORS))
            self.x = TetrisGame.GRID_WIDTH // 2 - len(self.shape[0]) // 2
            self.y = 0

    def __init__(self):
        self.locked = bytearray(self.GRID_WIDTH * self.GRID_HEIGHT)
        self.current = TetrisGame.Piece()
        self.score = 0
        self.last_fall = ticks_ms()
        self.last_input = ticks_ms()
        self.fall_ms = 520
        self.input_ms = 120

    def valid(self, piece, dx=0, dy=0, rotated_shape=None):
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
                if ny >= 0 and self.locked[ny * self.GRID_WIDTH + nx]:
                    return False
        return True

    def lock_piece(self, piece):
        for y, row in enumerate(piece.shape):
            for x, cell in enumerate(row):
                if cell:
                    px = piece.x + x
                    py = piece.y + y
                    if py < 0:
                        return False
                    self.locked[py * self.GRID_WIDTH + px] = piece.color
        return True

    def clear_rows(self):
        w = self.GRID_WIDTH
        h = self.GRID_HEIGHT
        cleared = 0
        dst_y = h - 1
        for src_y in range(h - 1, -1, -1):
            full = True
            base = src_y * w
            for x in range(w):
                if self.locked[base + x] == 0:
                    full = False
                    break
            if full:
                cleared += 1
                continue
            if dst_y != src_y:
                dst = dst_y * w
                for x in range(w):
                    self.locked[dst + x] = self.locked[base + x]
            dst_y -= 1
        while dst_y >= 0:
            base = dst_y * w
            for x in range(w):
                self.locked[base + x] = 0
            dst_y -= 1
        return cleared

    def draw_block(self, gx, gy, color):
        x1 = gx * self.BLOCK_SIZE
        y1 = gy * self.BLOCK_SIZE
        if isinstance(color, int):
            color = self.COLORS[(color - 1) % len(self.COLORS)]
        draw_rectangle(x1, y1, x1 + self.BLOCK_SIZE - 1, y1 + self.BLOCK_SIZE - 1, *color)

    def render(self):
        display.clear()
        # locked
        w = self.GRID_WIDTH
        for y in range(self.GRID_HEIGHT):
            base = y * w
            for x in range(w):
                col = self.locked[base + x]
                if col:
                    self.draw_block(x, y, col)
        # current
        for y, row in enumerate(self.current.shape):
            for x, cell in enumerate(row):
                if cell:
                    px = self.current.x + x
                    py = self.current.y + y
                    if py >= 0:
                        self.draw_block(px, py, self.current.color)

    def _build_step(self, joystick):
        global game_over, global_score
        game_over = False
        global_score = 0
        self.locked = bytearray(self.GRID_WIDTH * self.GRID_HEIGHT)
        self.current = TetrisGame.Piece()
        self.score = 0
        self.last_fall = ticks_ms()
        self.last_input = ticks_ms()
        self.fall_ms = 520
        display_score_and_time(0, force=True)
        def step():
            global game_over, global_score
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            now = ticks_ms()
            if ticks_diff(now, self.last_input) >= self.input_ms:
                d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_DOWN, JOYSTICK_UP])
                if d == JOYSTICK_LEFT and self.valid(self.current, dx=-1):
                    self.current.x -= 1
                elif d == JOYSTICK_RIGHT and self.valid(self.current, dx=1):
                    self.current.x += 1
                elif d == JOYSTICK_DOWN and self.valid(self.current, dy=1):
                    self.current.y += 1
                elif d == JOYSTICK_UP or z_button:
                    rot = tuple(tuple(row) for row in zip(*self.current.shape[::-1]))
                    if self.valid(self.current, rotated_shape=rot):
                        self.current.shape = rot
                self.last_input = now
            if ticks_diff(now, self.last_fall) >= self.fall_ms:
                self.last_fall = now
                if self.valid(self.current, dy=1):
                    self.current.y += 1
                else:
                    ok = self.lock_piece(self.current)
                    if not ok:
                        global_score = self.score
                        game_over = True
                        return False
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
                        return False
            self.render()
            display_score_and_time(self.score)
            return True
        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(35, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(35, self._build_step(joystick))

# ---------- Maze ----------
class MazeGame:
    """
    MAZE
    Controls:
      - Left / Right / Up / Down: move player
      - Z: shoot
      - C: return to menu
    """
    WALL = 0
    PATH = 1
    PLAYER = 2
    GEM = 3
    ENEMY = 4
    PROJECTILE = 5

    MazeWaySize = 3
    BORDER = 2

    def __init__(self):
        self.projectiles = []
        self.gems = []
        self.enemies = []
        self.score = 0
        self.player_direction = JOYSTICK_UP
        self.explored = bytearray(WIDTH * PLAY_HEIGHT)

    def _idx(self, x, y):
        return y * WIDTH + x

    def _mark_explored(self, x, y):
        if 0 <= x < WIDTH and 0 <= y < PLAY_HEIGHT:
            self.explored[self._idx(x, y)] = 1

    def generate_maze(self):
        stack = []
        visited = bytearray(WIDTH * PLAY_HEIGHT)

        start_x = random.randint(self.BORDER, WIDTH - self.BORDER - 1)
        start_y = random.randint(self.BORDER, PLAY_HEIGHT - self.BORDER - 1)

        # WIDTH/PLAY_HEIGHT are <256, so y<<8|x safely packs one cell.
        stack.append((start_y << 8) | start_x)
        visited[self._idx(start_x, start_y)] = 1
        set_grid_value(start_x, start_y, self.PATH)

        dirs = ((0, self.MazeWaySize), (0, -self.MazeWaySize), (self.MazeWaySize, 0), (-self.MazeWaySize, 0))
        dir_order = [0, 1, 2, 3]

        while stack:
            pack = stack[-1]
            x = pack & 0xFF
            y = pack >> 8
            dir_order[0], dir_order[1], dir_order[2], dir_order[3] = 0, 1, 2, 3
            _shuffle_in_place(dir_order)

            found = False
            for di in dir_order:
                dx, dy = dirs[di]
                nx, ny = x + dx, y + dy
                if self.BORDER <= nx < WIDTH - self.BORDER and self.BORDER <= ny < PLAY_HEIGHT - self.BORDER and not visited[self._idx(nx, ny)]:
                    step_x = dx // self.MazeWaySize
                    step_y = dy // self.MazeWaySize
                    for k in range(self.MazeWaySize):
                        cx = x + step_x * k
                        cy = y + step_y * k
                        set_grid_value(cx, cy, self.PATH)
                    set_grid_value(nx, ny, self.PATH)
                    stack.append((ny << 8) | nx)
                    visited[self._idx(nx, ny)] = 1
                    found = True
                    break

            if not found:
                stack.pop()

        self._add_extra_connections()

    def _add_extra_connections(self):
        dirs = ((0, self.MazeWaySize), (0, -self.MazeWaySize), (self.MazeWaySize, 0), (-self.MazeWaySize, 0))
        added = 0
        attempts = 0
        target = 20 if not CONFIG_LOW_RAM_MODE else 12
        while added < target and attempts < target * 18:
            attempts += 1
            x = random.randint(self.BORDER, WIDTH - self.BORDER - 1)
            y = random.randint(self.BORDER, PLAY_HEIGHT - self.BORDER - 1)
            if get_grid_value(x, y) != self.PATH:
                continue
            dx, dy = dirs[random.randint(0, len(dirs) - 1)]
            nx, ny = x + dx, y + dy
            if not (self.BORDER <= nx < WIDTH - self.BORDER and self.BORDER <= ny < PLAY_HEIGHT - self.BORDER):
                continue
            if get_grid_value(nx, ny) != self.PATH:
                continue
            step_x = dx // self.MazeWaySize
            step_y = dy // self.MazeWaySize
            blocked = False
            for k in range(1, self.MazeWaySize):
                if get_grid_value(x + step_x * k, y + step_y * k) != self.WALL:
                    blocked = True
                    break
            if blocked:
                continue
            for k in range(1, self.MazeWaySize):
                set_grid_value(x + step_x * k, y + step_y * k, self.PATH)
            added += 1

    def place_player(self):
        while True:
            self.player_x = random.randint(self.BORDER, WIDTH - self.BORDER - 1)
            self.player_y = random.randint(self.BORDER, PLAY_HEIGHT - self.BORDER - 1)
            if get_grid_value(self.player_x, self.player_y) == self.PATH:
                set_grid_value(self.player_x, self.player_y, self.PLAYER)
                self._mark_explored(self.player_x, self.player_y)
                break

    def place_gems(self, n=10):
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
        vis = []
        seen = set()
        def add_vis(px, py):
            cell = (px, py)
            if cell not in seen:
                seen.add(cell)
                vis.append(cell)
        def add_side_peek(px, py, dx, dy):
            if abs(px - x) + abs(py - y) > 5:
                return
            for sx, sy in ((-dy, dx), (dy, -dx)):
                bx, by = px, py
                for _i in range(3):
                    bx += sx
                    by += sy
                    if not (0 <= bx < WIDTH and 0 <= by < PLAY_HEIGHT):
                        break
                    v = get_grid_value(bx, by)
                    if v == self.WALL:
                        break
                    add_vis(bx, by)
                    if v == self.ENEMY:
                        break
        x, y = self.player_x, self.player_y
        add_vis(x, y)
        dirs = ((-1,0), (1,0), (0,-1), (0,1))
        for dx, dy in dirs:
            nx, ny = x, y
            while True:
                nx += dx
                ny += dy
                if 0 <= nx < WIDTH and 0 <= ny < PLAY_HEIGHT:
                    v = get_grid_value(nx, ny)
                    if v == self.WALL:
                        break
                    add_vis(nx, ny)
                    add_side_peek(nx, ny, dx, dy)
                    if v == self.ENEMY:
                        break
                else:
                    break
        return vis

    def render(self):
        display.clear()
        vis = self.get_visible_cells()

        for x, y in vis:
            v = get_grid_value(x, y)
            if v == self.PATH or v == self.PLAYER:
                self._mark_explored(x, y)

        sp = display.set_pixel
        for y in range(PLAY_HEIGHT):
            base = y * WIDTH
            for x in range(WIDTH):
                if self.explored[base + x]:
                    sp(x, y, 40, 40, 40)

        for x, y in vis:
            v = get_grid_value(x, y)
            if v == self.PATH:
                sp(x, y, 80, 80, 80)
            elif v == self.PLAYER:
                sp(x, y, 0, 255, 0)
            elif v == self.GEM:
                sp(x, y, 255, 215, 0)
            elif v == self.ENEMY:
                sp(x, y, 255, 0, 0)
            elif v == self.PROJECTILE:
                sp(x, y, 255, 255, 0)

    def move_player(self, joystick):
        d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
        if not d:
            return

        dx, dy = direction_to_delta(d)
        nx = self.player_x + dx
        ny = self.player_y + dy

        if not in_bounds(nx, ny):
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
        new_enemies = []
        for (ex, ey) in self.enemies:
            moves = []
            for dx, dy in [(0,-1),(0,1),(-1,0),(1,0)]:
                nx, ny = ex + dx, ey + dy
                if in_bounds(nx, ny) and get_grid_value(nx, ny) == self.PATH:
                    moves.append((nx, ny))
            set_grid_value(ex, ey, self.PATH)
            if moves:
                ex, ey = random.choice(moves)
            set_grid_value(ex, ey, self.ENEMY)
            new_enemies.append((ex, ey))
        self.enemies = new_enemies

    def handle_shooting(self, joystick):
        _, z_button = joystick.read_buttons()
        if not z_button:
            return

        # Compute delta from last movement direction (UP fallback).
        dx, dy = direction_to_delta(self.player_direction, 0, -1)

        sx = self.player_x + dx
        sy = self.player_y + dy
        if not in_bounds(sx, sy):
            return

        v = get_grid_value(sx, sy)
        if v == self.WALL:
            return

        if len(self.projectiles) >= 3:
            return
        self.projectiles.append([sx, sy, dx, dy, 12, v])
        set_grid_value(sx, sy, self.PROJECTILE)

    def update_projectiles(self):
        keep_i = 0
        for p in self.projectiles:
            set_grid_value(p[0], p[1], p[5])

            p[0] += p[2]
            p[1] += p[3]
            p[4] -= 1

            if p[4] <= 0 or not in_bounds(p[0], p[1]):
                continue

            v = get_grid_value(p[0], p[1])
            if v == self.WALL:
                continue
            if v == self.ENEMY:
                pos = (p[0], p[1])
                if pos in self.enemies:
                    self.enemies.remove(pos)
                set_grid_value(p[0], p[1], self.PATH)
                self.score += 20
                continue

            p[5] = v
            set_grid_value(p[0], p[1], self.PROJECTILE)
            self.projectiles[keep_i] = p
            keep_i += 1
        del self.projectiles[keep_i:]

    def _build_step(self, joystick, win_delay_ms=1500):
        global game_over, global_score
        game_over = False
        global_score = 0

        initialize_grid()
        self.explored = bytearray(WIDTH * PLAY_HEIGHT)
        self.score = 0
        self.projectiles = []
        self.generate_maze()
        self.place_player()
        self.place_gems(10)
        self.place_enemies(3)

        display_score_and_time(0, force=True)

        def loop_iteration():
            global game_over, global_score
            c_button, _ = joystick.read_buttons()
            if c_button:
                return False
            if (self.player_x, self.player_y) in self.enemies:
                global_score = self.score
                game_over = True
                return False
            self.move_player(joystick)
            self.handle_shooting(joystick)
            self.update_projectiles()
            self.move_enemies()
            self.render()
            display_score_and_time(self.score)
            if not self.enemies and not self.gems:
                set_game_over_score(self.score, won=True)
                loop_iteration.won = True
                show_center_message(("YOU", "WON"), start_y=18, line_height=15,
                                    r=0, g=255, b=0, delay_ms=win_delay_ms)
                return False
            return True

        loop_iteration.won = False
        return loop_iteration

    def main_loop(self, joystick):
        _run_game_loop_sync(90, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        step = self._build_step(joystick, win_delay_ms=0)
        await _run_game_loop_async(90, step)
        if getattr(step, "won", False):
            await sleep_ms_async(1500)

# ---------- FLAPPY ----------
class FlappyGame:
    """
    FLAPPY
    Controls:
      - Z / Up: flap
      - C: return to menu
    """
    def __init__(self):
        self.reset()

    def reset(self):
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
        min_y = self.gap_h // 2 + 2
        max_y = PLAY_HEIGHT - self.gap_h // 2 - 3
        gy = random.randint(min_y, max_y)
        self.pipes.append({"x": x, "gy": gy, "passed": False})

    def flap(self):
        # compatibility for Z button: give an upward velocity impulse
        self.vy = -3

    def collide(self):
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
                draw_rectangle(x, bot_start, x + self.pipe_w - 1, PLAY_HEIGHT - 1, 0, 200, 0)

        # bird (2x2)
        y = int(self.by)
        draw_rectangle(self.bx, y, self.bx + 1, y + 1, 255, 255, 0)

    def _build_step(self, joystick):
        global game_over, global_score
        game_over = False
        global_score = 0
        self.reset()
        display_score_and_time(0, force=True)
        def step():
            global game_over, global_score
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            d = joystick.read_direction([JOYSTICK_UP])
            if z_button or d == JOYSTICK_UP:
                self.flap()
            self.vy += 1
            if self.vy > 5:
                self.vy = 5
            self.by += self.vy
            if self.by < 0:
                self.by = 0
                self.vy = 0
            if self.by > PLAY_HEIGHT - 2:
                self.by = PLAY_HEIGHT - 2
                self.vy = 0
            for p in self.pipes:
                p["x"] -= self.speed
                if (not p["passed"]) and (p["x"] + self.pipe_w) < self.bx:
                    p["passed"] = True
                    self.score += 1
            if self.pipes and self.pipes[0]["x"] + self.pipe_w < 0:
                self.pipes.pop(0)
                self.add_pipe(WIDTH + 10)
            if self.collide():
                global_score = self.score
                game_over = True
                return False
            self.draw()
            display_score_and_time(self.score)
            return True
        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(35, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(35, self._build_step(joystick))


class DodgeGame:
    """
    DODGE (Ausweichspiel)
    Steuerung:
      - Links/Rechts: bewegen
      - Z: kurzer Dash in die letzte Richtung
      - C: zurück ins Menü
    """
    MAX_OBSTACLES = 12
    START_SPAWN_MS = 520
    FRAME_MS = 38
    MIN_SPAWN_MS = 160
    DIFFICULTY_SCORE_INTERVAL = 6
    SPAWN_MS_DECREMENT = 12

    def __init__(self):
        self.reset()

    def reset(self):
        self.player_x = float(WIDTH) / 2.0
        self.player_y = float(PLAY_HEIGHT) - 4.0
        self.obstacles = []      # [x, y, w, h, vx, vy, color_hue]
        self.score = 0
        self.last_dir = None
        self.last_spawn = ticks_ms()
        self.spawn_ms = self.START_SPAWN_MS      # wird mit steigender Punktzahl schneller
        self.frame_ms = self.FRAME_MS

    def _spawn_obstacle(self):
        if len(self.obstacles) >= self.MAX_OBSTACLES:
            return
        w = random.randint(2, 6)
        h = random.randint(2, 6)
        ox = random.randint(0, WIDTH - w)
        vx = random.uniform(-0.5, 0.5)
        vy = random.uniform(0.6, 1.8)
        hue = random.randint(0, 360)
        self.obstacles.append([float(ox), 0.0, w, h, vx, vy, hue])

    def _move_player(self, joystick, z_button):
        d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT])
        if d:
            self.last_dir = d

        step = 1.0
        if z_button and self.last_dir:
            # Dash beschleunigt die letzte Richtung ohne neue Allokation.
            step = 2.5

        if self.last_dir == JOYSTICK_LEFT and (d == JOYSTICK_LEFT or z_button):
            self.player_x = max(0.0, self.player_x - step)
        elif self.last_dir == JOYSTICK_RIGHT and (d == JOYSTICK_RIGHT or z_button):
            self.player_x = min(WIDTH - 3.0, self.player_x + step)

    def _advance_obstacles(self):
        new_obs = []
        for o in self.obstacles:
            o[0] += o[4] # x += vx
            o[1] += o[5] # y += vy
            # bounce off walls
            if o[0] < 0:
                o[0] = 0
                o[4] *= -1
            elif o[0] + o[2] > WIDTH:
                o[0] = float(WIDTH - o[2])
                o[4] *= -1

            if o[1] >= PLAY_HEIGHT:
                self.score += 1
                continue
            new_obs.append(o)
        self.obstacles = new_obs

    def _collides(self):
        # Spieler 3x3 Block 
        px = int(self.player_x)
        py = int(self.player_y)
        px2 = px + 2
        py2 = py + 2
        for o in self.obstacles:
            ox = int(o[0])
            oy = int(o[1])
            ox2 = ox + o[2] - 1
            oy2 = oy + o[3] - 1
            if px <= ox2 and px2 >= ox and py <= oy2 and py2 >= oy:
                return True
        return False

    def _draw(self):
        display.clear()
        # Hindernisse
        for o in self.obstacles:
            ox = int(o[0])
            oy = int(o[1])
            r, g, b = hsb_to_rgb(o[6], 1, 1)
            draw_rectangle(ox, oy, ox + o[2] - 1, oy + o[3] - 1, r, g, b)
            
        # Spieler
        px = int(self.player_x)
        py = int(self.player_y)
        draw_rectangle(px, py, px + 2, py + 2, 0, 220, 255)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        global game_over, global_score
        game_over = False
        global_score = 0
        self.reset()
        display_score_and_time(0, force=True)
        def step():
            global game_over, global_score
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            now = ticks_ms()
            if ticks_diff(now, self.last_spawn) >= self.spawn_ms:
                self._spawn_obstacle()
                self.last_spawn = now
                if self.spawn_ms > self.MIN_SPAWN_MS and (self.score % self.DIFFICULTY_SCORE_INTERVAL) == 0:
                    self.spawn_ms -= self.SPAWN_MS_DECREMENT
            self._move_player(joystick, z_button)
            self._advance_obstacles()
            if self._collides():
                global_score = self.score
                game_over = True
                return False
            global_score = self.score
            self._draw()
            return True
        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class InvaderGame:
    """
    INVADR
    Controls:
      - Left/Right: move ship
      - Z: fire
      - C: return to menu
    """
    FRAME_MS = 38
    ALIEN_COLS = 8
    ALIEN_ROWS = 5
    SHIELD_W = 9
    SHIELD_H = 5

    def __init__(self):
        self.reset()

    def reset(self):
        self.player_x = WIDTH // 2
        self.player_y = PLAY_HEIGHT - 4
        self.bullet = None
        self.bombs = []
        self.aliens = []
        self.shields = []
        self.ufo = None
        self.alien_dir = 1
        self.alien_drop = 0
        self.score = 0
        self.wave = 1
        self.last_alien_step = ticks_ms()
        self.alien_step_ms = 560
        self.last_bomb = ticks_ms()
        self.last_ufo = ticks_ms()
        self.last_z = False
        self._spawn_wave(speed_up=False)
        self._build_shields()

    def _spawn_wave(self, speed_up=True):
        self.aliens = []
        start_x = 1
        start_y = 6
        # Keep the formation dense enough to read like Space Invaders on 64 px.
        for row in range(self.ALIEN_ROWS):
            for col in range(self.ALIEN_COLS):
                self.aliens.append([start_x + col * 7, start_y + row * 5, 1, row])
        self.alien_dir = 1
        self.alien_drop = 0
        if speed_up:
            self.wave += 1
            if self.alien_step_ms > 170:
                self.alien_step_ms -= 35

    def _build_shields(self):
        self.shields = []
        y = PLAY_HEIGHT - 15
        for sx in (7, 28, 49):
            # Store shield pixels as a byte mask so impacts can erode them cheaply.
            cells = bytearray(self.SHIELD_W * self.SHIELD_H)
            for yy in range(self.SHIELD_H):
                for xx in range(self.SHIELD_W):
                    solid = True
                    if yy == self.SHIELD_H - 1 and 3 <= xx <= 5:
                        solid = False
                    if yy == 0 and (xx == 0 or xx == self.SHIELD_W - 1):
                        solid = False
                    cells[yy * self.SHIELD_W + xx] = 1 if solid else 0
            self.shields.append([sx, y, cells])

    def _move_player(self, joystick):
        d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT])
        if d == JOYSTICK_LEFT:
            self.player_x = max(2, self.player_x - 2)
        elif d == JOYSTICK_RIGHT:
            self.player_x = min(WIDTH - 3, self.player_x + 2)

    def _fire(self):
        if self.bullet is None:
            self.bullet = [self.player_x, self.player_y - 2]

    def _hit_shield(self, x, y):
        for shield in self.shields:
            sx = shield[0]
            sy = shield[1]
            if x < sx or y < sy or x >= sx + self.SHIELD_W or y >= sy + self.SHIELD_H:
                continue
            lx = x - sx
            ly = y - sy
            cells = shield[2]
            idx = ly * self.SHIELD_W + lx
            if not cells[idx]:
                return False
            # Classic shield damage: one hit eats a small chunk, not just one pixel.
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    nx = lx + dx
                    ny = ly + dy
                    if 0 <= nx < self.SHIELD_W and 0 <= ny < self.SHIELD_H:
                        cells[ny * self.SHIELD_W + nx] = 0
            return True
        return False

    def _step_bullet(self):
        if self.bullet is None:
            return
        self.bullet[1] -= 3
        bx = self.bullet[0]
        by = self.bullet[1]
        if by < 0:
            self.bullet = None
            return
        if self._hit_shield(bx, by):
            self.bullet = None
            return
        for alien in self.aliens:
            if not alien[2]:
                continue
            ax = alien[0]
            ay = alien[1]
            if ax <= bx <= ax + 4 and ay <= by <= ay + 3:
                alien[2] = 0
                self.bullet = None
                self.score += 10
                break
        if self.bullet is not None and self.ufo is not None:
            ux = self.ufo[0]
            uy = self.ufo[1]
            if ux <= bx <= ux + 7 and uy <= by <= uy + 2:
                self.ufo = None
                self.bullet = None
                self.score += 150

    def _step_aliens(self):
        now = ticks_ms()
        if ticks_diff(now, self.last_alien_step) < self.alien_step_ms:
            return False
        self.last_alien_step = now

        hit_edge = False
        for alien in self.aliens:
            if not alien[2]:
                continue
            nx = alien[0] + self.alien_dir * 2
            if nx < 1 or nx > WIDTH - 6:
                hit_edge = True
                break

        if hit_edge:
            self.alien_dir *= -1
            self.alien_drop += 1
            for alien in self.aliens:
                if alien[2]:
                    alien[1] += 3
        else:
            for alien in self.aliens:
                if alien[2]:
                    alien[0] += self.alien_dir * 2
        return True

    def _drop_bomb(self):
        if not self.aliens:
            return
        now = ticks_ms()
        live_count = self._live_count()
        interval = max(230, 900 - self.wave * 55 - (self.ALIEN_ROWS * self.ALIEN_COLS - live_count) * 8)
        if ticks_diff(now, self.last_bomb) < interval:
            return
        self.last_bomb = now
        if len(self.bombs) >= 5:
            return

        bottom = []
        for alien in self.aliens:
            if not alien[2]:
                continue
            col = (alien[0] - 1) // 7
            # Bombs should come from the visible bottom alien in each column.
            is_bottom = True
            for other in self.aliens:
                if other[2] and ((other[0] - 1) // 7) == col and other[1] > alien[1]:
                    is_bottom = False
                    break
            if is_bottom:
                bottom.append(alien)
        if not bottom:
            return
        alien = bottom[random.randint(0, len(bottom) - 1)]
        self.bombs.append([alien[0] + 2, alien[1] + 4])

    def _step_bombs(self):
        new_bombs = []
        px1 = self.player_x - 2
        px2 = self.player_x + 2
        py1 = self.player_y - 1
        py2 = self.player_y + 1
        hit = False
        for bomb in self.bombs:
            bomb[1] += 2
            bx = bomb[0]
            by = bomb[1]
            if self._hit_shield(bx, by):
                continue
            elif px1 <= bx <= px2 and py1 <= by <= py2:
                hit = True
            elif by < PLAY_HEIGHT:
                new_bombs.append(bomb)
        self.bombs = new_bombs
        return hit

    def _step_ufo(self):
        now = ticks_ms()
        if self.ufo is None:
            # Long irregular delay keeps the saucer as an occasional bonus target.
            if ticks_diff(now, self.last_ufo) > 9000 + random.randint(0, 4500):
                direction = random.choice([-1, 1])
                x = -8 if direction > 0 else WIDTH
                self.ufo = [x, 2, direction]
                self.last_ufo = now
            return

        self.ufo[0] += self.ufo[2]
        if self.ufo[0] < -9 or self.ufo[0] > WIDTH + 1:
            self.ufo = None
            self.last_ufo = now

    def _aliens_reached_player(self):
        for alien in self.aliens:
            if alien[2] and alien[1] + 4 >= self.player_y - 1:
                return True
        return False

    def _all_clear(self):
        for alien in self.aliens:
            if alien[2]:
                return False
        return True

    def _live_count(self):
        count = 0
        for alien in self.aliens:
            if alien[2]:
                count += 1
        return count

    def _draw_alien(self, x, y, typ):
        # Three tiny sprite silhouettes preserve the original row hierarchy.
        if typ == 0:
            pts = ((2, 0), (1, 1), (2, 1), (3, 1), (0, 2), (1, 2), (3, 2), (4, 2), (0, 3), (4, 3))
            color = (200, 120, 255)
        elif typ < 3:
            pts = ((1, 0), (3, 0), (0, 1), (1, 1), (2, 1), (3, 1), (4, 1), (0, 2), (2, 2), (4, 2), (1, 3), (3, 3))
            color = (0, 220, 80)
        else:
            pts = ((0, 0), (4, 0), (1, 1), (2, 1), (3, 1), (0, 2), (1, 2), (3, 2), (4, 2), (1, 3), (3, 3))
            color = (0, 180, 255)
        for px, py in pts:
            display.set_pixel(x + px, y + py, color[0], color[1], color[2])

    def _draw_shields(self):
        for shield in self.shields:
            sx = shield[0]
            sy = shield[1]
            cells = shield[2]
            for yy in range(self.SHIELD_H):
                for xx in range(self.SHIELD_W):
                    if cells[yy * self.SHIELD_W + xx]:
                        display.set_pixel(sx + xx, sy + yy, 40, 220, 80)

    def _draw(self):
        display.clear()
        for alien in self.aliens:
            if not alien[2]:
                continue
            ax = alien[0]
            ay = alien[1]
            self._draw_alien(ax, ay, alien[3])

        self._draw_shields()

        if self.bullet is not None:
            display.set_pixel(self.bullet[0], self.bullet[1], 255, 255, 80)
            if self.bullet[1] + 1 < PLAY_HEIGHT:
                display.set_pixel(self.bullet[0], self.bullet[1] + 1, 255, 180, 30)

        for bomb in self.bombs:
            display.set_pixel(bomb[0], bomb[1], 255, 60, 60)

        if self.ufo is not None:
            ux = self.ufo[0]
            uy = self.ufo[1]
            draw_rectangle(ux + 1, uy, ux + 6, uy, 255, 60, 60)
            draw_rectangle(ux, uy + 1, ux + 7, uy + 1, 255, 120, 120)
            set_pixel_clipped(ux + 2, uy + 2, 255, 220, 80)
            set_pixel_clipped(ux + 5, uy + 2, 255, 220, 80)

        px = self.player_x
        py = self.player_y
        draw_rectangle(px - 2, py, px + 2, py + 1, 80, 180, 255)
        display.set_pixel(px, py - 1, 255, 255, 255)
        display_score_and_time(self.score)

    def _step(self, joystick, z_button):
        global game_over, global_score
        self._move_player(joystick)
        if z_button and not self.last_z:
            self._fire()
        self.last_z = z_button
        self._step_bullet()
        self._step_aliens()
        self._drop_bomb()
        self._step_ufo()

        if self._step_bombs() or self._aliens_reached_player():
            set_game_over_score(self.score)
            return False

        if self._all_clear():
            self.score += 100
            global_score = self.score
            self._spawn_wave()

        global_score = self.score
        self._draw()
        maybe_collect(100)
        return True

    def _build_step(self, joystick):
        self.reset()
        begin_game(0)
        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            return self._step(joystick, z_button)
        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class TronGame:
    """
    TRON LIGHT CYCLE (Endless)
    Controls:
      - Left/Right: 90° turn
      - Z: Turbo (double step)
      - C: Back to menu
    """
    FRAME_MS = 62
    TURBO_STEP = 2
    HUE_STEP = 7
    PALETTE_SIZE = 128
    COLLECT_INTERVAL = 120
    RESPAWN_MIN_CLEAR = 5
    RESPAWN_TRIES = 48

    _PALETTE = None

    @classmethod
    def _palette(cls):
        if cls._PALETTE is None:
            cls._PALETTE = tuple(
                hsb_to_rgb((i * cls.HUE_STEP) % 360, 1, 1)
                for i in range(cls.PALETTE_SIZE)
            )
        return cls._PALETTE

    # Direction ids: 0=up, 1=down, 2=left, 3=right.
    _LEFT_TURN = (2, 3, 1, 0)
    _RIGHT_TURN = (3, 2, 0, 1)
    _DIR_VECS = ((0, -1), (0, 1), (-1, 0), (1, 0))
    DIR_UP = 0
    DIR_DOWN = 1
    DIR_LEFT = 2
    DIR_RIGHT = 3

    def __init__(self, ctx=None):
        self.players_mode = get_context_setting(ctx, "players", "cpu")
        self.reset()

    def reset(self):
        self.trail = bytearray(WIDTH * PLAY_HEIGHT)
        self.head_x = WIDTH // 4
        self.head_y = PLAY_HEIGHT // 2
        self.direction = self.DIR_RIGHT
        
        self.enemy_x = WIDTH - (WIDTH // 4)
        self.enemy_y = PLAY_HEIGHT // 2
        self.enemy_dir = self.DIR_LEFT
        self.enemy_alive = True
        self.enemy_score = 0
        
        self.score = 0
        self._palette = TronGame._palette()

        display.clear()
        self._occupy(self.head_x, self.head_y)
        self._occupy(self.enemy_x, self.enemy_y)
        self._draw_head(force=True)
        self._draw_enemy(force=True)
        display_score_and_time(0, force=True)

    def _idx(self, x, y):
        return y * WIDTH + x

    def _occupy(self, x, y):
        self.trail[self._idx(x, y)] = 1

    def _blocked(self, x, y):
        if x < 0 or x >= WIDTH or y < 0 or y >= PLAY_HEIGHT:
            return True
        return self.trail[self._idx(x, y)] != 0

    def _turn(self, d):
        if d == JOYSTICK_LEFT:
            self.direction = self._LEFT_TURN[self.direction]
        elif d == JOYSTICK_RIGHT:
            self.direction = self._RIGHT_TURN[self.direction]

    def _turn_enemy(self, d):
        if d == JOYSTICK_LEFT:
            self.enemy_dir = self._LEFT_TURN[self.enemy_dir]
        elif d == JOYSTICK_RIGHT:
            self.enemy_dir = self._RIGHT_TURN[self.enemy_dir]

    def _enemy_lookahead(self, e_dir):
        # How many clear tiles in direction e_dir?
        dx, dy = self._DIR_VECS[e_dir]
        nx, ny = self.enemy_x, self.enemy_y
        dist = 0
        while True:
            nx += dx
            ny += dy
            if self._blocked(nx, ny):
                break
            dist += 1
            if dist > 8: # don't need to look too far
                break
        return dist

    def _clear_distance_from(self, x, y, e_dir, limit=12):
        dx, dy = self._DIR_VECS[e_dir]
        dist = 0
        while dist < limit:
            x += dx
            y += dy
            if self._blocked(x, y):
                break
            dist += 1
        return dist

    def _best_enemy_dir_from(self, x, y):
        best_dir = self.DIR_LEFT
        best_dist = -1
        for e_dir in range(4):
            dist = self._clear_distance_from(x, y, e_dir)
            if dist > best_dist:
                best_dist = dist
                best_dir = e_dir
        return best_dir, best_dist

    def _try_respawn_enemy(self):
        for _ in range(self.RESPAWN_TRIES):
            rx = random.randint(4, WIDTH - 5)
            ry = random.randint(4, PLAY_HEIGHT - 5)
            if self._blocked(rx, ry):
                continue
            # Keep the respawn readable and avoid spawning directly on top of the player.
            if abs(rx - self.head_x) + abs(ry - self.head_y) < 14:
                continue
            e_dir, clear = self._best_enemy_dir_from(rx, ry)
            if clear < self.RESPAWN_MIN_CLEAR:
                continue
            self.enemy_x = rx
            self.enemy_y = ry
            self.enemy_dir = e_dir
            self.enemy_alive = True
            self.enemy_score = 0
            self._occupy(rx, ry)
            self._draw_enemy()
            return True
        return False

    def _step(self, turbo):
        # AI step
        if self.enemy_alive:
            if self.players_mode != "two":
                # Check survival ahead
                fwd_dist = self._enemy_lookahead(self.enemy_dir)
                if fwd_dist < 4:
                    # Need to turn! Check left and right distances
                    l_dir = self._LEFT_TURN[self.enemy_dir]
                    r_dir = self._RIGHT_TURN[self.enemy_dir]
                    l_dist = self._enemy_lookahead(l_dir)
                    r_dist = self._enemy_lookahead(r_dir)

                    if max(fwd_dist, l_dist, r_dist) == 0:
                        # Trapped! Just crash next tick.
                        pass
                    elif l_dist >= r_dist and l_dist > fwd_dist:
                        self.enemy_dir = l_dir
                    elif r_dist >= l_dist and r_dist > fwd_dist:
                        self.enemy_dir = r_dir
            
            # Enemy moves 1 step per frame normally
            edx, edy = self._DIR_VECS[self.enemy_dir]
            enx, eny = self.enemy_x + edx, self.enemy_y + edy
            if self._blocked(enx, eny):
                self.enemy_alive = False
                # Optionally add big score for killing enemy
                self.score += 150
                draw_rectangle(self.enemy_x - 2, self.enemy_y - 2, self.enemy_x + 2, self.enemy_y + 2, 255, 100, 0)
            else:
                self.enemy_x = enx
                self.enemy_y = eny
                self.enemy_score += 1
                self._occupy(enx, eny)
                self._draw_enemy()

        # Player step
        dx, dy = self._DIR_VECS[self.direction]
        steps = self.TURBO_STEP if turbo else 1
        for _ in range(steps):
            nx = self.head_x + dx
            ny = self.head_y + dy
            if self._blocked(nx, ny):
                return False
            self.head_x = nx
            self.head_y = ny
            self.score += 1
            self._occupy(nx, ny)
            self._draw_head()
        return True

    def _draw_head(self, force=False):
        color = self._palette[self.score % len(self._palette)]
        r, g, b = color
        display.set_pixel(self.head_x, self.head_y, r, g, b)
        if force:
            display_flush()

    def _draw_enemy(self, force=False):
        # Enemy is fixed red-ish to contrast with player palette
        display.set_pixel(self.enemy_x, self.enemy_y, 255, 50, 50)
        if force:
            display_flush()

    def _build_step(self, joystick):
        global game_over, global_score
        game_over = False
        global_score = 0
        self.reset()
        def step():
            global game_over, global_score
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            if self.players_mode == "two":
                _p1_back, p1_action = read_wasd_buttons()
                turn = read_wasd_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT], debounce=True)
                z_button = p1_action
            else:
                turn = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT])
            if turn:
                self._turn(turn)
            if self.players_mode == "two":
                p2_turn = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT])
                if p2_turn:
                    self._turn_enemy(p2_turn)
            alive = self._step(turbo=z_button)
            global_score = self.score
            display_score_and_time(self.score)
            if not alive:
                game_over = True
                return False
            if not self.enemy_alive and random.randint(0, 15) == 0:
                self._try_respawn_enemy()
            return True
        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class RTypeGame:
    """
    R-TYPE / GRADIUS MINI (Endlos-Side-Shooter)
    Steuerung:
      - Stick: bewegen (Up/Down/Left/Right)
      - Z: schießen
      - C: zurück ins Menü
    """
    # kleine Sinus-LUT (±4) für "wobble" Gegner ohne math.sin
    _SIN = (0, 1, 2, 3, 4, 3, 2, 1, 0, -1, -2, -3, -4, -3, -2, -1)
    MAX_BULLETS = 6
    MAX_EBULLETS = 3
    MAX_ENEMIES = 8
    MAX_POWERUPS = 3

    def __init__(self):
        self.reset()

    def reset(self):
        self.score = 0

        # Player
        self.pw = 5
        self.ph = 3
        self.px = 6
        self.py = PLAY_HEIGHT // 2

        # Projectiles
        self.bullets = []     # [x,y]
        self.ebullets = []    # [x,y]
        self.fire_cd = 0
        self.power_t = 0      # frames power-up active

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
            self.stars.append([random.randint(0, WIDTH - 1),
                               random.randint(0, PLAY_HEIGHT - 1),
                               random.randint(1, 3)])

        self.frame = 0
        self.last_logic = ticks_ms()
        self.logic_ms = 35  # ~28fps

    def _rect_play(self, x, y, w, h, r, g, b):
        # reuse shared helper to draw playfield rectangles
        draw_play_rect(x, y, w, h, r, g, b)

    def _overlap(self, ax1, ay1, ax2, ay2, bx1, by1, bx2, by2):
        if ax2 < bx1 or bx2 < ax1:
            return False
        if ay2 < by1 or by2 < ay1:
            return False
        return True

    def _spawn_enemy(self):
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
        # schnelleres Spawning mit Score
        # score steigt typischerweise in 10ern, das passt gut
        s = self.score // 10
        self.spawn_ms = 520 - s * 12
        if self.spawn_ms < 170:
            self.spawn_ms = 170

    def _update_stars(self):
        for st in self.stars:
            st[0] -= st[2]
            if st[0] < 0:
                st[0] = WIDTH - 1
                st[1] = random.randint(0, PLAY_HEIGHT - 1)
                st[2] = random.randint(1, 3)

    def _update_powerups(self):
        # move left, expire
        keep_i = 0
        for p in self.powerups:
            p[0] -= 1
            p[2] -= 1
            if p[0] < -2 or p[2] <= 0:
                continue

            # collect
            if abs(p[0] - (self.px + self.pw // 2)) <= 2 and abs(p[1] - (self.py + 1)) <= 2:
                self.power_t = 240  # roughly 8 seconds at the current tick speed
                # small bonus
                self.score += 5
                continue
            self.powerups[keep_i] = p
            keep_i += 1
        del self.powerups[keep_i:]

    def _update_bullets(self):
        # player bullets
        keep_i = 0
        for b in self.bullets:
            b[0] += 4
            if b[0] >= WIDTH:
                continue
            self.bullets[keep_i] = b
            keep_i += 1
        del self.bullets[keep_i:]

        # enemy bullets
        keep_i = 0
        for b in self.ebullets:
            b[0] -= 3
            if b[0] < 0:
                continue
            self.ebullets[keep_i] = b
            keep_i += 1
        del self.ebullets[keep_i:]

    def _update_enemies(self):
        global game_over, global_score

        keep_i = 0
        for e in self.enemies:
            typ = e[2]

            # movement
            if typ == 0:
                e[0] -= 2
            elif typ == 1:
                e[0] -= 1
                e[4] = (e[4] + 1) & 15
                e[1] = e[6] + self._SIN[e[4]]
                if e[1] < 1: e[1] = 1
                if e[1] > PLAY_HEIGHT - 6: e[1] = PLAY_HEIGHT - 6
            else:
                e[0] -= 1
                e[5] -= 1
                if e[5] <= 0 and len(self.ebullets) < self.MAX_EBULLETS:
                    # shoot
                    self.ebullets.append([e[0], e[1] + 1])
                    e[5] = random.randint(18, 40)

            # offscreen
            if e[0] < -10:
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
            self.enemies[keep_i] = e
            keep_i += 1
        del self.enemies[keep_i:]

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
        # bullets vs enemies
        keep_i = 0
        for b in self.bullets:
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
                hit[3] -= 1
                if hit[3] <= 0:
                    self.enemies.remove(hit)
                    # score
                    typ = hit[2]
                    self.score += (10 + typ * 7)
                    # chance for powerup
                    if random.randint(0, 99) < 12 and len(self.powerups) < self.MAX_POWERUPS:
                        self.powerups.append([hit[0], hit[1], 400])
                else:
                    self.score += 1  # hit bonus
            else:
                self.bullets[keep_i] = b
                keep_i += 1
        del self.bullets[keep_i:]

    def _draw(self):
        display.clear()
        sp = display.set_pixel

        # stars
        for x, y, _s in self.stars:
            if 0 <= x < WIDTH and 0 <= y < PLAY_HEIGHT:
                sp(x, y, 60, 60, 60)

        # powerups
        for p in self.powerups:
            x = int(p[0]); y = int(p[1])
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
            x = int(e[0]); y = int(e[1]); typ = e[2]
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
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        display_score_and_time(0, force=True)

        while True:
            c_button, z_button = joystick.read_buttons()
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
            d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
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
            if self.px < 0: self.px = 0
            if self.px > WIDTH - self.pw - 1: self.px = WIDTH - self.pw - 1
            if self.py < 0: self.py = 0
            if self.py > PLAY_HEIGHT - self.ph: self.py = PLAY_HEIGHT - self.ph

            # shoot
            if self.fire_cd > 0:
                self.fire_cd -= 1
            cd_min = 4 if self.power_t > 0 else 7
            if z_button and self.fire_cd == 0 and len(self.bullets) < self.MAX_BULLETS:
                # normal bullet
                self.bullets.append([self.px + self.pw + 1, self.py + 1])
                # powered double-shot
                if self.power_t > 0 and len(self.bullets) < self.MAX_BULLETS:
                    self.bullets.append([self.px + self.pw + 1, self.py])
                self.fire_cd = cd_min

            # spawn
            self._difficulty_update()
            if ticks_diff(now, self.last_spawn) >= self.spawn_ms and len(self.enemies) < self.MAX_ENEMIES:
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

    async def main_loop_async(self, joystick):
        """Async version for pygbag: yields with asyncio.sleep()."""
        if asyncio is None:
            return self.main_loop(joystick)

        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        display_score_and_time(0, force=True)

        def loop_iteration():
            global game_over, global_score
            c_button, z_button = joystick.read_buttons()
            if c_button or game_over:
                return False

            self.frame += 1

            # power timer
            if self.power_t > 0:
                self.power_t -= 1

            # input
            d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
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
            if self.px < 0: self.px = 0
            if self.px > WIDTH - self.pw - 1: self.px = WIDTH - self.pw - 1
            if self.py < 0: self.py = 0
            if self.py > PLAY_HEIGHT - self.ph: self.py = PLAY_HEIGHT - self.ph

            # shoot
            if self.fire_cd > 0:
                self.fire_cd -= 1
            cd_min = 4 if self.power_t > 0 else 7
            if z_button and self.fire_cd == 0 and len(self.bullets) < self.MAX_BULLETS:
                # normal bullet
                self.bullets.append([self.px + self.pw + 1, self.py + 1])
                # powered double-shot
                if self.power_t > 0 and len(self.bullets) < self.MAX_BULLETS:
                    self.bullets.append([self.px + self.pw + 1, self.py])
                self.fire_cd = cd_min

            # spawn
            now = ticks_ms()
            self._difficulty_update()
            if ticks_diff(now, self.last_spawn) >= self.spawn_ms and len(self.enemies) < self.MAX_ENEMIES:
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
            return True

        await _run_game_loop_async(35, loop_iteration)


class PacmanGame:
    """
    PACMAN-lite (Maze + Pellets + 2 Ghosts)
    Steuerung:
      - Stick: Richtung
      - C: zurück ins Menü
    """
    W = 16
    H = 14
    CELL = 4
    OFF_X = 0
    OFF_Y = 1

    # 16 characters per row, 15 rows. Each level must keep every pellet reachable.
    MAPS = (
        (
            "################",
            "#P.............#",
            "#.##.#.##.#.##.#",
            "#o...#....#...o#",
            "###.########.###",
            "#......##......#",
            "#.####.##.####.#",
            "#......GG......#",
            "#.####.##.####.#",
            "#......##......#",
            "###.########.###",
            "#o...#....#...o#",
            "#.##.#.##.#.##.#",
            "#..............#",
            "################",
        ),
        (
            "################",
            "#P....#........#",
            "#.##..#.####.#.#",
            "#o....#....#.#o#",
            "####.####..#.#.#",
            "#....#.....#...#",
            "#.##.#.##.###.##",
            "#....#.GG......#",
            "##.###.##.#.##.#",
            "#...#.....#....#",
            "#.#.#..####.####",
            "#o#.#....#....o#",
            "#.#.####.#..##.#",
            "#........#.....#",
            "################",
        ),
        (
            "################",
            "#P.....#.......#",
            "#.###..#.####..#",
            "#o..#.......#o.#",
            "###.#.#####.#.##",
            "#...#...#...#..#",
            "#.#####.#.###..#",
            "#.......GG.....#",
            "#..###.#.#####.#",
            "#..#...#...#...#",
            "##.#.#####.#.###",
            "#.o#.......#..o#",
            "#..####.#..###.#",
            "#.......#......#",
            "################",
        ),
    )

    # dirs: 0 U, 1 D, 2 L, 3 R
    DIRS = ((0, -1), (0, 1), (-1, 0), (1, 0))
    OPP  = (1, 0, 3, 2)
    GHOST_ACTIVE = 0
    GHOST_HIDDEN = 1
    GHOST_HARMLESS = 2
    GHOST_RESPAWN_TICKS = 42  # about 5 seconds at logic_ms=120

    def __init__(self):
        self.reset()

    def reset(self):
        self.level = 0
        self.score = 0
        self._load_level()

    def _load_level(self):
        self.map = self.MAPS[self.level % len(self.MAPS)]
        self.wall = bytearray(self.W * self.H)      # 1 if wall
        self.pel = bytearray(self.W * self.H)       # 0 none, 1 pellet, 2 power
        self.wall_list = []

        self.px = 1
        self.py = 1
        self.pdir = 3  # right
        self.want_dir = 3

        self.ghosts = []  # each: [x,y,dir,home_x,home_y,state,timer]
        self.power_timer = 0  # ticks (logic steps)

        self.pellet_count = 0

        # parse map
        for y in range(self.H):
            row = self.map[y]
            for x in range(self.W):
                ch = row[x]
                i = y * self.W + x
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
                        self.ghosts.append([x, y, random.randint(0, 3), x, y, self.GHOST_ACTIVE, 0])

        if len(self.ghosts) < 2:
            # safety
            self.ghosts.append([self.W - 2, 1, 2, self.W - 2, 1, self.GHOST_ACTIVE, 0])

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
        return y * self.W + x

    def _can_move(self, x, y):
        if x < 0 or x >= self.W or y < 0 or y >= self.H:
            return False
        return self.wall[self._idx(x, y)] == 0

    def _eat(self):
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
        # returns list of possible dirs
        x, y, d, hx, hy = g[:5]
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
        x, y, d, hx, hy = g[:5]
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

        frightened = (self.power_timer > 0)
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

    def _update_ghost_states(self):
        for g in self.ghosts:
            if g[5] == self.GHOST_ACTIVE:
                continue
            g[6] -= 1
            if g[6] > 0:
                continue
            if g[5] == self.GHOST_HIDDEN:
                g[0], g[1] = g[3], g[4]
                g[2] = random.randint(0, 3)
                g[5] = self.GHOST_HARMLESS
                g[6] = self.GHOST_RESPAWN_TICKS
            else:
                g[5] = self.GHOST_ACTIVE
                g[6] = 0
            self._dirty = True

    def _move_ghosts(self):
        # ghost speed: every 2nd logic tick
        self.ghost_tick = (self.ghost_tick + 1) & 1
        if self.ghost_tick == 1:
            return

        for g in self.ghosts:
            if g[5] == self.GHOST_HIDDEN:
                continue
            nd = self._ghost_pick(g)
            g[2] = nd
            dx, dy = self.DIRS[nd]
            g[0] += dx
            g[1] += dy
            self._dirty = True

    def _check_collisions(self):
        global game_over, global_score
        for g in self.ghosts:
            if g[5] != self.GHOST_ACTIVE:
                continue
            if g[0] == self.px and g[1] == self.py:
                if self.power_timer > 0:
                    # eat ghost
                    self.score += 50
                    g[0], g[1] = g[3], g[4]
                    g[2] = random.randint(0, 3)
                    g[5] = self.GHOST_HIDDEN
                    g[6] = self.GHOST_RESPAWN_TICKS
                    self._dirty = True
                else:
                    global_score = self.score
                    game_over = True
                    return True
        return False

    def _draw_cell(self, cx, cy, r, g, b):
        x1 = self.OFF_X + cx * self.CELL
        y1 = self.OFF_Y + cy * self.CELL
        draw_rectangle(x1, y1, x1 + self.CELL - 1, y1 + self.CELL - 1, r, g, b)

    def _is_wall_cell(self, x, y):
        if x < 0 or x >= self.W or y < 0 or y >= self.H:
            return False
        return self.wall[self._idx(x, y)] == 1

    def _draw_wall_cell(self, x, y):
        px = self.OFF_X + x * self.CELL
        py = self.OFF_Y + y * self.CELL
        draw_rectangle(px, py, px + 3, py + 3, 0, 18, 95)
        if not self._is_wall_cell(x, y - 1):
            draw_rectangle(px, py, px + 3, py, 30, 95, 255)
        if not self._is_wall_cell(x, y + 1):
            draw_rectangle(px, py + 3, px + 3, py + 3, 0, 45, 180)
        if not self._is_wall_cell(x - 1, y):
            draw_rectangle(px, py, px, py + 3, 15, 75, 235)
        if not self._is_wall_cell(x + 1, y):
            draw_rectangle(px + 3, py, px + 3, py + 3, 0, 45, 170)

    def _draw_bg_cell(self, x, y):
        i = self._idx(x, y)
        if self.wall[i]:
            self._draw_wall_cell(x, y)
            return

        # empty floor
        self._draw_cell(x, y, 0, 0, 0)

        # pellet on top of floor
        v = self.pel[i]
        if v:
            cx = self.OFF_X + x * self.CELL + 1
            cy = self.OFF_Y + y * self.CELL + 1
            if v == 1:
                display.set_pixel(cx + 1, cy + 1, 255, 220, 150)
            else:
                draw_rectangle(cx, cy, cx + 2, cy + 2, 255, 230, 80)
                display.set_pixel(cx + 1, cy + 1, 255, 255, 255)

    def _draw_player(self):
        px = self.OFF_X + self.px * self.CELL
        py = self.OFF_Y + self.py * self.CELL
        draw_rectangle(px, py, px + 3, py + 3, 255, 220, 0)
        if self.pdir == 0:
            display.set_pixel(px + 1, py, 0, 0, 0)
            display.set_pixel(px + 2, py, 0, 0, 0)
        elif self.pdir == 1:
            display.set_pixel(px + 1, py + 3, 0, 0, 0)
            display.set_pixel(px + 2, py + 3, 0, 0, 0)
        elif self.pdir == 2:
            display.set_pixel(px, py + 1, 0, 0, 0)
            display.set_pixel(px, py + 2, 0, 0, 0)
        else:
            display.set_pixel(px + 3, py + 1, 0, 0, 0)
            display.set_pixel(px + 3, py + 2, 0, 0, 0)
        display.set_pixel(px + 1, py + 1, 255, 255, 120)

    def _draw_ghosts(self):
        frightened = (self.power_timer > 0)
        for gi, g in enumerate(self.ghosts):
            if g[5] == self.GHOST_HIDDEN:
                continue
            gx = self.OFF_X + g[0] * self.CELL
            gy = self.OFF_Y + g[1] * self.CELL
            if g[5] == self.GHOST_HARMLESS:
                col = (90, 55, 95) if gi == 0 else (95, 50, 90)
            elif frightened:
                col = (80, 120, 255)
            else:
                col = (255, 60, 60) if gi == 0 else (255, 80, 210)
            draw_rectangle(gx, gy + 1, gx + 3, gy + 3, *col)
            draw_rectangle(gx + 1, gy, gx + 2, gy, *col)
            eye = 140 if g[5] == self.GHOST_HARMLESS else 255
            display.set_pixel(gx + 1, gy + 1, eye, eye, eye)
            display.set_pixel(gx + 2, gy + 1, eye, eye, eye)
            eye_col = (0, 0, 90) if frightened or g[5] == self.GHOST_HARMLESS else (0, 0, 0)
            display.set_pixel(gx + 1, gy + 2, *eye_col)
            display.set_pixel(gx + 2, gy + 2, *eye_col)
            if not frightened and g[5] == self.GHOST_ACTIVE:
                display.set_pixel(gx, gy + 3, 0, 0, 0)
                display.set_pixel(gx + 3, gy + 3, 0, 0, 0)

    def _draw_background(self):
        display.clear()
        # walls
        for (x, y) in self.wall_list:
            self._draw_wall_cell(x, y)

        # pellets
        for y in range(self.H):
            for x in range(self.W):
                v = self.pel[self._idx(x, y)]
                if v:
                    cx = self.OFF_X + x * self.CELL + 1
                    cy = self.OFF_Y + y * self.CELL + 1
                    if v == 1:
                        display.set_pixel(cx + 1, cy + 1, 255, 220, 150)
                    else:
                        draw_rectangle(cx, cy, cx + 2, cy + 2, 255, 230, 80)
                        display.set_pixel(cx + 1, cy + 1, 255, 255, 255)
        self._drawn_bg = True

    def _draw(self):
        if not self._drawn_bg:
            self._draw_background()
        self._draw_player()
        self._draw_ghosts()

        draw_text_small(46, PLAY_HEIGHT, "L" + str(self.level + 1), 120, 120, 120)
        display_score_and_time(self.score)
        self._dirty = False

    def _draw_dirty_cells(self, dirty):
        if not self._drawn_bg:
            self._draw_background()

        # restore background for dirty cells first
        for (x, y) in dirty:
            if 0 <= x < self.W and 0 <= y < self.H:
                self._draw_bg_cell(x, y)

        # redraw sprites on top
        self._draw_player()
        self._draw_ghosts()
        draw_text_small(46, PLAY_HEIGHT, "L" + str(self.level + 1), 120, 120, 120)
        display_score_and_time(self.score)

    def main_loop(self, joystick):
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        display_score_and_time(0, force=True)

        # initial full draw
        self._draw_background()
        self._draw()

        while True:
            c_button, _z = joystick.read_buttons()
            if c_button:
                return
            if game_over:
                return

            now = ticks_ms()

            # read input often
            d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
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
                self._update_ghost_states()
                self._move_ghosts()

                if self._check_collisions():
                    global_score = self.score
                    return

                # win?
                if self.pellet_count <= 0:
                    self.score += 100 + self.level * 50
                    global_score = self.score
                    if self.level + 1 >= len(self.MAPS):
                        show_center_message(("YOU", "WON"), start_y=18, line_height=15, r=0, g=255, b=0, score=global_score, delay_ms=1300)
                        return
                    self.level += 1
                    self._load_level()
                    self._draw_background()
                    self._draw()
                    show_center_message(("LVL", str(self.level + 1)), start_y=18, line_height=15, r=255, g=255, b=0, score=global_score, delay_ms=700)
                    self.last_logic = ticks_ms()
                    self._drawn_bg = False
                    self._dirty = True
                    continue

                global_score = self.score

                # incremental redraw: old/new sprite cells without allocating a set
                dirty = []
                def add_dirty(cell):
                    if cell not in dirty:
                        dirty.append(cell)
                add_dirty((old_px, old_py))
                add_dirty((self.px, self.py))
                for p in old_ghosts:
                    add_dirty(p)
                for g in self.ghosts:
                    add_dirty((g[0], g[1]))
                if (old_power > 0) != (self.power_timer > 0):
                    for g in self.ghosts:
                        add_dirty((g[0], g[1]))

                self._draw_dirty_cells(dirty)

                if self.frame % 90 == 0:
                    gc.collect()

            else:
                sleep_ms(6)

            if self._dirty:
                self._draw()
            else:
                sleep_ms(8)

    async def main_loop_async(self, joystick):
        """Async version for pygbag: yields with asyncio.sleep()."""
        if asyncio is None:
            return self.main_loop(joystick)

        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        display_score_and_time(0, force=True)

        # initial full draw
        self._draw_background()
        self._draw()

        while True:
            c_button, _z = joystick.read_buttons()
            if c_button:
                return
            if game_over:
                return

            now = ticks_ms()

            # read input often
            d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
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
                self._update_ghost_states()
                self._move_ghosts()

                if self._check_collisions():
                    global_score = self.score
                    return

                # win?
                if self.pellet_count <= 0:
                    self.score += 100 + self.level * 50
                    global_score = self.score
                    if self.level + 1 >= len(self.MAPS):
                        show_center_message(("YOU", "WON"), start_y=18, line_height=15, r=0, g=255, b=0, score=global_score)
                        await asyncio.sleep(1.3)
                        return
                    self.level += 1
                    self._load_level()
                    self._draw_background()
                    self._draw()
                    show_center_message(("LVL", str(self.level + 1)), start_y=18, line_height=15, r=255, g=255, b=0, score=global_score)
                    await asyncio.sleep(0.7)
                    self.last_logic = ticks_ms()
                    self._drawn_bg = False
                    self._dirty = True
                    continue

                global_score = self.score

                # incremental redraw: old/new sprite cells without allocating a set
                dirty = []
                def add_dirty(cell):
                    if cell not in dirty:
                        dirty.append(cell)
                add_dirty((old_px, old_py))
                add_dirty((self.px, self.py))
                for p in old_ghosts:
                    add_dirty(p)
                for g in self.ghosts:
                    add_dirty((g[0], g[1]))
                if (old_power > 0) != (self.power_timer > 0):
                    for g in self.ghosts:
                        add_dirty((g[0], g[1]))

                self._draw_dirty_cells(dirty)

                if self.frame % 90 == 0:
                    try:
                        gc.collect()
                    except Exception:
                        pass

            else:
                await asyncio.sleep(0.006)

            if self._dirty:
                self._draw()
            else:
                await asyncio.sleep(0.008)


class CaveFlyGame:
    """
    CAVE FLYER
    Steuerung:
      - Links/Rechts: seitlich durch die Höhle steuern
      - C: zurück ins Menü
    """
    def __init__(self):
        self.reset()

    def reset(self):
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
        mid = (int(self.left_wall[self._idx_row(self.by)]) + int(self.right_wall[self._idx_row(self.by)])) // 2
        self.bx = self._clamp(mid, 1, WIDTH - 3)

    def _clamp(self, v, lo, hi):
        return clamp(v, lo, hi)

    def _idx_row(self, y):
        return (self.head + y) % PLAY_HEIGHT

    def _gen_row_at(self, idx):
        # tunnel tightens over time: starts wide, narrows progressively
        self.gap = self.base_gap - int(self.score / 60)
        if self.gap < self.min_gap:
            self.gap = self.min_gap

        # center drift (keep within bounds)
        self.center += random.randint(-2, 2)
        self.center = self._clamp(self.center, (self.gap // 2) + 3, WIDTH - (self.gap // 2) - 4)

        left = self.center - (self.gap // 2)
        right = self.center + (self.gap // 2)
        if left < 1:
            left = 1
        if right > WIDTH - 2:
            right = WIDTH - 2
        self.left_wall[idx] = left
        self.right_wall[idx] = right

    def _step_scroll(self):
        # scroll upward: advance head so y=0 becomes previous y=1
        self.head = (self.head + 1) % PLAY_HEIGHT
        # generate new bottom row
        self._gen_row_at(self._idx_row(PLAY_HEIGHT - 1))

    def _collide(self):
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

    def _build_step(self, joystick):
        global game_over, global_score
        game_over = False
        global_score = 0
        self.reset()
        display_score_and_time(0, force=True)
        def step():
            global game_over, global_score
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            self.frame += 1
            d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT])
            move_amount = 2
            if d == JOYSTICK_LEFT:
                self.bx = max(self.bx - move_amount, 0)
            elif d == JOYSTICK_RIGHT:
                self.bx = min(self.bx + move_amount, WIDTH - 2)
            self._step_scroll()
            self.score += 1
            global_score = self.score
            if self._collide():
                game_over = True
                return False
            self._draw()
            return True
        return step

    def main_loop(self, joystick):
        step = self._build_step(joystick)
        self._draw()
        start_wait = ticks_ms()
        while ticks_diff(ticks_ms(), start_wait) < 900:
            c_button, _z_button = joystick.read_buttons()
            if c_button:
                return
            sleep_ms(20)
        _run_game_loop_sync(33, step)

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        step = self._build_step(joystick)
        self._draw()
        start_wait = ticks_ms()
        while ticks_diff(ticks_ms(), start_wait) < 900:
            c_button, _z_button = joystick.read_buttons()
            if c_button:
                return
            await asyncio.sleep(0.020)
        await _run_game_loop_async(33, step)


class CentipedeGame:
    """
    CENTI
    Controls:
      - Directions: move in the bottom player zone
      - Z: fire upward
      - C: return to menu
    Atari-inspired centipede shooter with mushrooms, segmented enemies, and
    wave progression on a compact 32x29 logical grid.
    """
    FRAME_MS = 34
    CELL = 2
    GW = WIDTH // CELL
    GH = PLAY_HEIGHT // CELL
    PLAYER_MIN_Y = GH - 7

    def __init__(self):
        self.reset()

    def reset(self):
        self.score = 0
        self.wave = 1
        self.frame = 0
        self.last_z = False
        self._new_wave(reset_player=True)

    def _new_wave(self, reset_player=False):
        if reset_player:
            self.px = self.GW // 2
            self.py = self.GH - 2
        self.bullets = []
        self.flash_until = 0
        self.centipede = []
        length = min(14, 8 + self.wave)
        for i in range(length):
            self.centipede.append([i, 1, 1])
        self.mushrooms = []
        seed = self.wave * 37
        count = min(42, 20 + self.wave * 3)
        used = set()
        for i in range(count):
            x = 2 + ((seed + i * 9 + (i // 3) * 5) % (self.GW - 4))
            y = 4 + ((seed * 2 + i * 7) % (self.GH - 10))
            if (x, y) in used:
                continue
            used.add((x, y))
            self.mushrooms.append([x, y, 2])

    def _mushroom_at(self, x, y):
        for m in self.mushrooms:
            if m[0] == x and m[1] == y and m[2] > 0:
                return m
        return None

    def _move_player(self, joystick):
        d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
        dx, dy = direction_to_delta(d)
        if dx or dy:
            self.px = clamp(self.px + dx, 1, self.GW - 2)
            self.py = clamp(self.py + dy, self.PLAYER_MIN_Y, self.GH - 2)

    def _fire(self):
        if len(self.bullets) < 2:
            self.bullets.append([self.px, self.py - 1])

    def _move_bullets(self):
        keep = []
        for b in self.bullets:
            hit = False
            for _ in range(2):
                b[1] -= 1
                if b[1] < 0:
                    hit = True
                    break
                m = self._mushroom_at(b[0], b[1])
                if m:
                    m[2] -= 1
                    if m[2] <= 0:
                        self.score += 2
                    hit = True
                    break
                for seg in list(self.centipede):
                    if seg[0] == b[0] and seg[1] == b[1]:
                        self.centipede.remove(seg)
                        self.mushrooms.append([seg[0], seg[1], 2])
                        self.score += 10
                        hit = True
                        break
                if hit:
                    break
            if not hit:
                keep.append(b)
        self.bullets = keep
        self.mushrooms = [m for m in self.mushrooms if m[2] > 0]

    def _move_centipede(self):
        speed_gate = max(2, 7 - min(5, self.wave))
        if (self.frame % speed_gate) != 0:
            return
        for seg in self.centipede:
            nx = seg[0] + seg[2]
            blocked = nx <= 0 or nx >= self.GW - 1 or self._mushroom_at(nx, seg[1])
            if blocked:
                seg[2] = -seg[2]
                seg[1] += 1
                if seg[1] >= self.GH:
                    seg[1] = self.PLAYER_MIN_Y
            else:
                seg[0] = nx

    def _collides_player(self):
        for x, y, _d in self.centipede:
            if abs(x - self.px) <= 1 and abs(y - self.py) <= 1:
                return True
        return False

    def _draw_cell(self, x, y, color):
        px = x * self.CELL
        py = y * self.CELL
        draw_rectangle(px, py, px + 1, py + 1, *color)

    def _draw(self):
        display.clear()
        draw_line(0, self.PLAYER_MIN_Y * self.CELL - 1, WIDTH - 1, self.PLAYER_MIN_Y * self.CELL - 1, 25, 70, 25)
        for x, y, hp in self.mushrooms:
            col = (180, 80, 210) if hp > 1 else (90, 45, 120)
            self._draw_cell(x, y, col)
        for b in self.bullets:
            if 0 <= b[1] < self.GH:
                display.set_pixel(b[0] * self.CELL, b[1] * self.CELL, 255, 255, 80)
        for i, seg in enumerate(self.centipede):
            col = (255, 80, 50) if i == 0 else (255, 170, 30)
            self._draw_cell(seg[0], seg[1], col)
        draw_rectangle(self.px * self.CELL - 1, self.py * self.CELL - 1, self.px * self.CELL + 1, self.py * self.CELL + 1, 70, 210, 255)
        draw_text_small(1, PLAY_HEIGHT, "W" + str(self.wave), 180, 180, 180)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        self.reset()

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            self.frame += 1
            self._move_player(joystick)
            if z_button and not self.last_z:
                self._fire()
            self.last_z = z_button
            self._move_bullets()
            self._move_centipede()
            if self._collides_player():
                set_game_over_score(self.score)
                return False
            if not self.centipede:
                self.score += 75 + self.wave * 15
                self.wave += 1
                self._new_wave(reset_player=False)
            self._draw()
            return True
        return step

    def main_loop(self, joystick):
        begin_game(0)
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        begin_game(0)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class ArtilleryGame:
    """
    ARTILL
    Controls:
      - Up / Down: aim barrel
      - Left / Right: adjust power
      - Z: fire
      - C: return to menu
    Turn-based artillery duel with wind, terrain craters, and a CPU gunner.
    """
    FRAME_MS = 45
    GRAVITY = 0.075

    def __init__(self):
        self.reset()

    def reset(self):
        self.score = 0
        self.round = 1
        self.angle = 45
        self.power = 16
        self.last_z = False
        self.wind = 0.0
        self.shell = None
        self.cpu_wait = 0
        self.turn = "player"
        self.explosion = None
        self._new_round()

    def _new_round(self):
        self.wind = random.choice((-1, 1)) * (0.015 + random.randint(0, 4) * 0.006)
        self.terrain = []
        base = 43 + (self.round % 3)
        for x in range(WIDTH):
            y = base + int(math.sin((x + self.round * 7) * 0.23) * 4)
            y += int(math.sin((x + self.round * 11) * 0.07) * 3)
            self.terrain.append(clamp(y, 31, PLAY_HEIGHT - 2))
        self.player_x = 5
        self.enemy_x = WIDTH - 6
        self.turn = "player"
        self.shell = None
        self.cpu_wait = 18
        self.explosion = None

    def _ground_y(self, x):
        return self.terrain[clamp(int(x), 0, WIDTH - 1)]

    def _tank_pos(self, x):
        return x, self._ground_y(x) - 3

    def _fire(self, owner, angle, power):
        if self.shell:
            return
        sx = self.player_x if owner == "player" else self.enemy_x
        sy = self._ground_y(sx) - 5
        rad = math.radians(angle)
        sign = 1 if owner == "player" else -1
        speed = power * 0.12
        self.shell = [float(sx), float(sy), math.cos(rad) * speed * sign, -math.sin(rad) * speed, owner]

    def _crater(self, cx, cy):
        self.explosion = [int(cx), int(cy), 8]
        for x in range(max(0, int(cx) - 5), min(WIDTH, int(cx) + 6)):
            d = abs(x - int(cx))
            self.terrain[x] = clamp(self.terrain[x] + max(1, 4 - d // 2), 25, PLAY_HEIGHT - 1)

    def _hit_tank(self, x, y, tank_x):
        tx, ty = self._tank_pos(tank_x)
        return (x - tx) * (x - tx) + (y - ty) * (y - ty) <= 25

    def _advance_shell(self):
        if not self.shell:
            return True
        for _ in range(2):
            self.shell[2] += self.wind
            self.shell[3] += self.GRAVITY
            self.shell[0] += self.shell[2]
            self.shell[1] += self.shell[3]
            x, y, _vx, _vy, owner = self.shell
            if x < 0 or x >= WIDTH or y >= PLAY_HEIGHT:
                self.shell = None
                self.turn = "enemy" if owner == "player" else "player"
                self.cpu_wait = 18
                return True
            if owner == "player" and self._hit_tank(x, y, self.enemy_x):
                self.score += 100 + self.round * 10
                self.round += 1
                if self.score >= 700:
                    set_game_over_score(self.score, won=True)
                    return False
                self._new_round()
                return True
            if owner == "enemy" and self._hit_tank(x, y, self.player_x):
                set_game_over_score(self.score)
                return False
            if y >= self._ground_y(x):
                self._crater(x, y)
                self.shell = None
                self.turn = "enemy" if owner == "player" else "player"
                self.cpu_wait = 18
                return True
        return True

    def _cpu_turn(self):
        if self.turn != "enemy" or self.shell:
            return
        self.cpu_wait -= 1
        if self.cpu_wait > 0:
            return
        dx = self.enemy_x - self.player_x
        angle = clamp(38 + random.randint(-8, 12) - int(self.wind * 180), 25, 70)
        power = clamp(int(dx / 4.2) + self.round + random.randint(-4, 4), 11, 27)
        self._fire("enemy", angle, power)

    def _draw_tank(self, x, color):
        tx, ty = self._tank_pos(x)
        draw_rectangle(tx - 2, ty - 1, tx + 2, ty + 1, *color)
        draw_rectangle(tx - 1, ty - 3, tx + 1, ty - 2, *color)

    def _draw_aim(self):
        tx, ty = self._tank_pos(self.player_x)
        rad = math.radians(self.angle)
        length = 7
        ax = tx + int(math.cos(rad) * length)
        ay = ty - 2 - int(math.sin(rad) * length)
        draw_line(tx, ty - 2, ax, ay, 100, 220, 255)

    def _draw(self):
        display.clear()
        sky = (0, 12, 22)
        draw_rectangle(0, 0, WIDTH - 1, PLAY_HEIGHT - 1, *sky)
        for x, y in enumerate(self.terrain):
            draw_line(x, y, x, PLAY_HEIGHT - 1, 80, 65, 32)
            display.set_pixel(x, y, 120, 105, 55)
        self._draw_tank(self.player_x, (80, 210, 255))
        self._draw_tank(self.enemy_x, (255, 70, 55))
        if self.turn == "player" and not self.shell:
            self._draw_aim()
        if self.shell:
            display.set_pixel(int(self.shell[0]), int(self.shell[1]), 255, 255, 180)
        if self.explosion:
            x, y, t = self.explosion
            col = (255, 200, 50) if t & 1 else (255, 80, 30)
            draw_rect_outline(x - 2, y - 2, x + 2, y + 2, *col)
            self.explosion[2] -= 1
            if self.explosion[2] <= 0:
                self.explosion = None
        draw_text_small(1, PLAY_HEIGHT, "A" + str(self.angle), 210, 210, 210)
        draw_text_small(18, PLAY_HEIGHT, "P" + str(self.power), 210, 210, 210)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        self.reset()

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            if self.turn == "player" and not self.shell:
                d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
                if d == JOYSTICK_UP:
                    self.angle = min(80, self.angle + 1)
                elif d == JOYSTICK_DOWN:
                    self.angle = max(15, self.angle - 1)
                elif d == JOYSTICK_RIGHT:
                    self.power = min(30, self.power + 1)
                elif d == JOYSTICK_LEFT:
                    self.power = max(7, self.power - 1)
                if z_button and not self.last_z:
                    self._fire("player", self.angle, self.power)
            self.last_z = z_button
            self._cpu_turn()
            if not self._advance_shell():
                return False
            self._draw()
            return True
        return step

    def main_loop(self, joystick):
        begin_game(0)
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        begin_game(0)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class WormsGame:
    """
    WORMS
    Controls:
      - Left / Right: move active worm, or adjust power while holding Z
      - Up / Down: aim
      - Z: fire
      - C: return to menu
    Tiny turn-based worms/artillery game with teams and destructible terrain.
    """
    FRAME_MS = 45
    GRAVITY = 0.080

    def __init__(self, ctx=None):
        self.players_mode = get_context_setting(ctx, "players", "cpu")
        self.team_size = int(get_context_setting(ctx, "worms", 2) or 2)
        self.reset()

    def reset(self):
        self.score = 0
        self.turn_team = 0
        self.active = [0, 0]
        self.angle = 45
        self.power = 16
        self.wind = 0.0
        self.shell = None
        self.explosion = None
        self.last_fire = [False, False]
        self.cpu_wait = 26
        self.turns = 0
        self._new_match()

    def _new_match(self):
        self.terrain = []
        base = 42
        for x in range(WIDTH):
            y = base + int(math.sin(x * 0.19) * 5) + int(math.sin(x * 0.055 + 1.4) * 4)
            self.terrain.append(clamp(y, 27, PLAY_HEIGHT - 2))
        self.worms = [[], []]
        left_slots = (8, 18, 28)
        right_slots = (55, 45, 35)
        for i in range(self.team_size):
            lx = left_slots[i]
            rx = right_slots[i]
            self.worms[0].append({"x": float(lx), "y": float(self._ground_y(lx) - 2), "hp": 2})
            self.worms[1].append({"x": float(rx), "y": float(self._ground_y(rx) - 2), "hp": 2})
        self._settle_all()
        self.turn_team = 0
        self.active = [0, 0]
        self._select_alive(0)
        self._select_alive(1)

    def _ground_y(self, x):
        return self.terrain[clamp(int(x), 0, WIDTH - 1)]

    def _active_worm(self):
        return self.worms[self.turn_team][self.active[self.turn_team]]

    def _select_alive(self, team):
        worms = self.worms[team]
        start = self.active[team] % len(worms)
        for off in range(len(worms)):
            idx = (start + off) % len(worms)
            if worms[idx]["hp"] > 0:
                self.active[team] = idx
                return True
        return False

    def _team_alive(self, team):
        for w in self.worms[team]:
            if w["hp"] > 0:
                return True
        return False

    def _settle_all(self):
        for team in range(2):
            for w in self.worms[team]:
                if w["hp"] <= 0:
                    continue
                ix = clamp(int(w["x"]), 0, WIDTH - 1)
                w["y"] = float(self._ground_y(ix) - 2)

    def _crater(self, cx, cy, radius=5):
        self.explosion = [int(cx), int(cy), 8]
        icx = int(cx)
        for x in range(max(0, icx - radius), min(WIDTH, icx + radius + 1)):
            d = abs(x - icx)
            cut = max(1, radius - d)
            self.terrain[x] = clamp(self.terrain[x] + cut, 22, PLAY_HEIGHT - 1)
        self._damage_worms(cx, cy, radius + 2)
        self._settle_all()

    def _damage_worms(self, cx, cy, radius):
        r2 = radius * radius
        for team in range(2):
            for w in self.worms[team]:
                if w["hp"] <= 0:
                    continue
                dx = w["x"] - cx
                dy = w["y"] - cy
                if dx * dx + dy * dy <= r2:
                    w["hp"] -= 1
                    if team == 1:
                        self.score += 45

    def _next_turn(self):
        if not self._team_alive(0):
            set_game_over_score(self.score)
            return False
        if not self._team_alive(1):
            set_game_over_score(self.score + 250, won=True)
            return False
        self.turn_team = 1 - self.turn_team
        self.active[self.turn_team] = (self.active[self.turn_team] + 1) % len(self.worms[self.turn_team])
        self._select_alive(self.turn_team)
        self.wind = random.choice((-1, 1)) * random.randint(0, 5) * 0.006
        self.shell = None
        self.cpu_wait = 26
        self.turns += 1
        if self.turn_team == 0:
            self.angle = 45
            self.power = 16
        return True

    def _fire(self, team, angle, power):
        if self.shell:
            return
        w = self._active_worm()
        sign = 1 if team == 0 else -1
        rad = math.radians(angle)
        speed = power * 0.12
        self.shell = [w["x"], w["y"] - 3, math.cos(rad) * speed * sign, -math.sin(rad) * speed, team]

    def _move_active(self, d):
        w = self._active_worm()
        if d == JOYSTICK_LEFT:
            nx = max(1.0, w["x"] - 1.0)
        elif d == JOYSTICK_RIGHT:
            nx = min(float(WIDTH - 2), w["x"] + 1.0)
        else:
            return
        gy = self._ground_y(nx)
        if abs((gy - 2) - w["y"]) <= 4:
            w["x"] = nx
            w["y"] = float(gy - 2)

    def _cpu_turn(self):
        if self.turn_team != 1 or self.shell:
            return
        self.cpu_wait -= 1
        if self.cpu_wait > 0:
            return
        enemy = self.worms[0][self.active[0]]
        me = self._active_worm()
        dx = abs(enemy["x"] - me["x"])
        angle = clamp(36 + random.randint(-5, 10) - int(self.wind * 180), 25, 72)
        power = clamp(int(dx / 4.0) + random.randint(4, 9), 9, 28)
        self._fire(1, angle, power)

    def _advance_shell(self):
        if not self.shell:
            return True
        for _ in range(2):
            self.shell[2] += self.wind
            self.shell[3] += self.GRAVITY
            self.shell[0] += self.shell[2]
            self.shell[1] += self.shell[3]
            x, y, _vx, _vy, _owner = self.shell
            if x < 0 or x >= WIDTH or y >= PLAY_HEIGHT:
                self.shell = None
                return self._next_turn()
            if y >= self._ground_y(x):
                self._crater(x, y)
                self.shell = None
                return self._next_turn()
            for team in range(2):
                for w in self.worms[team]:
                    if w["hp"] <= 0:
                        continue
                    dx = w["x"] - x
                    dy = w["y"] - y
                    if dx * dx + dy * dy <= 5:
                        self._crater(x, y)
                        self.shell = None
                        return self._next_turn()
        return True

    def _draw_worm(self, w, team, selected):
        if w["hp"] <= 0:
            return
        x = int(w["x"])
        y = int(w["y"])
        col = (80, 210, 255) if team == 0 else (255, 95, 75)
        draw_rectangle(x - 1, y - 1, x + 1, y + 1, *col)
        if selected:
            display.set_pixel(x, y - 3, 255, 255, 255)
        if w["hp"] > 1:
            display.set_pixel(x + 2, y, 255, 255, 255)

    def _draw_aim(self):
        w = self._active_worm()
        sign = 1 if self.turn_team == 0 else -1
        rad = math.radians(self.angle)
        x0 = int(w["x"])
        y0 = int(w["y"] - 2)
        x1 = x0 + int(math.cos(rad) * 7 * sign)
        y1 = y0 - int(math.sin(rad) * 7)
        draw_line(x0, y0, x1, y1, 255, 255, 120)

    def _draw(self):
        display.clear()
        draw_rectangle(0, 0, WIDTH - 1, PLAY_HEIGHT - 1, 0, 10, 24)
        for x, y in enumerate(self.terrain):
            draw_line(x, y, x, PLAY_HEIGHT - 1, 60, 92, 45)
            display.set_pixel(x, y, 120, 150, 70)
        for team in range(2):
            for i, w in enumerate(self.worms[team]):
                self._draw_worm(w, team, team == self.turn_team and i == self.active[team])
        if not self.shell and (self.turn_team == 0 or self.players_mode == "two"):
            self._draw_aim()
        if self.shell:
            display.set_pixel(int(self.shell[0]), int(self.shell[1]), 255, 255, 180)
        if self.explosion:
            x, y, t = self.explosion
            col = (255, 220, 40) if t & 1 else (255, 70, 30)
            draw_rect_outline(x - 2, y - 2, x + 2, y + 2, *col)
            self.explosion[2] -= 1
            if self.explosion[2] <= 0:
                self.explosion = None
        draw_rectangle(0, PLAY_HEIGHT, WIDTH - 1, HEIGHT - 1, 0, 0, 0)
        draw_text_small(1, PLAY_HEIGHT, "A" + str(self.angle), 210, 210, 210)
        draw_text_small(19, PLAY_HEIGHT, "P" + str(self.power), 210, 210, 210)
        draw_text_small(43, PLAY_HEIGHT, "W" + str(int(self.wind * 100)), 180, 180, 180)
        display_flush()

    def _read_turn_input(self, joystick, joystick_fire):
        if self.players_mode == "two" and self.turn_team == 0:
            d = read_wasd_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT], debounce=True)
            _back, fire = read_wasd_buttons()
            return d, fire
        d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
        return d, joystick_fire

    def _handle_player_turn(self, joystick, joystick_fire):
        if self.shell:
            return
        d, fire = self._read_turn_input(joystick, joystick_fire)
        if d == JOYSTICK_UP:
            self.angle = min(82, self.angle + 2)
        elif d == JOYSTICK_DOWN:
            self.angle = max(15, self.angle - 2)
        elif d in (JOYSTICK_LEFT, JOYSTICK_RIGHT):
            if fire:
                delta = 1 if d == JOYSTICK_RIGHT else -1
                self.power = clamp(self.power + delta, 6, 30)
            else:
                self._move_active(d)
        if fire and not self.last_fire[self.turn_team] and d not in (JOYSTICK_LEFT, JOYSTICK_RIGHT):
            self._fire(self.turn_team, self.angle, self.power)
        self.last_fire[self.turn_team] = fire

    def _build_step(self, joystick):
        self.reset()
        begin_game(0)

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            if self.turn_team == 0 or self.players_mode == "two":
                self._handle_player_turn(joystick, z_button)
            else:
                self._cpu_turn()
                self.last_fire[1] = False
            if not self._advance_shell():
                return False
            self._draw()
            return True
        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class BattlezoneGame:
    """
    BTLZON
    Controls:
      - Left / Right: rotate
      - Up / Down: drive
      - Z: fire
      - C: return to menu
    Vector-style first-person tank combat with radar, shells, rocks, and waves.
    """
    FRAME_MS = 36
    FOV = 1.18

    def __init__(self, ctx=None):
        self.difficulty = get_context_setting(ctx, "difficulty", "normal")
        self.obstacles_enabled = bool(get_context_setting(ctx, "obstacles", True))
        self.reset()

    def reset(self):
        self.score = 0
        self.wave = 1
        self.lives = 4 if self.difficulty == "easy" else 3
        self.cooldown = 0
        self.flash = 0
        self.hit_flash = 0
        self.last_z = False
        self.frame = 0
        self.player_shots = []
        self.enemy_shells = []
        self.enemies = []
        self.rocks = []
        self.wave_delay = 0
        self._spawn_wave()

    def _difficulty_offset(self):
        if self.difficulty == "easy":
            return -1
        if self.difficulty == "hard":
            return 1
        return 0

    def _spawn_wave(self):
        self.player_shots = []
        self.enemy_shells = []
        self.enemies = []
        self.rocks = []
        diff = self._difficulty_offset()
        count = clamp(1 + (self.wave // 2) + (1 if diff > 0 and self.wave > 1 else 0), 1, 4)
        for i in range(count):
            side = -1 if i % 2 == 0 else 1
            bearing = side * (0.25 + random.randint(0, 52) / 100.0)
            dist = 48.0 + random.randint(0, 24) + i * 5
            strafe = side * (0.003 + random.randint(0, 5) / 1000.0)
            reload_base = 115 - self.wave * 5 - diff * 18
            reload = max(36, reload_base + random.randint(0, 36))
            kind = 1 if self.wave >= 4 and random.randint(0, 4) == 0 else 0
            self.enemies.append([bearing, dist, strafe, reload, kind, 0])
        if self.obstacles_enabled:
            rock_count = clamp(2 + self.wave // 3, 2, 5)
            for _ in range(rock_count):
                bearing = random.choice((-1, 1)) * (0.18 + random.randint(0, 80) / 100.0)
                dist = 20.0 + random.randint(0, 52)
                size = 1 + random.randint(0, 2)
                self.rocks.append([bearing, dist, size])

    def _rotate_view(self, amount):
        for enemy in self.enemies:
            enemy[0] = clamp(enemy[0] + amount, -1.6, 1.6)
        for shell in self.enemy_shells:
            shell[0] = clamp(shell[0] + amount, -1.6, 1.6)
        for shot in self.player_shots:
            shot[0] = clamp(shot[0] + amount, -1.6, 1.6)
        for rock in self.rocks:
            rock[0] = clamp(rock[0] + amount, -1.6, 1.6)

    def _drive(self, amount):
        for enemy in self.enemies:
            enemy[1] = clamp(enemy[1] + amount, 10.0, 86.0)
        for shell in self.enemy_shells:
            shell[1] = clamp(shell[1] + amount, 1.0, 90.0)
        for rock in self.rocks:
            rock[1] = clamp(rock[1] + amount, 5.0, 90.0)
        for rock in self.rocks:
            if rock[1] < 8.0 and abs(rock[0]) < 0.15:
                self._take_hit()
                rock[1] = 46.0 + random.randint(0, 26)
                rock[0] = random.choice((-1, 1)) * (0.45 + random.randint(0, 40) / 100.0)

    def _move_player(self, joystick):
        d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
        if d == JOYSTICK_LEFT:
            self._rotate_view(0.095)
        elif d == JOYSTICK_RIGHT:
            self._rotate_view(-0.095)
        elif d == JOYSTICK_UP:
            self._drive(-1.25)
        elif d == JOYSTICK_DOWN:
            self._drive(0.95)

    def _fire(self):
        if self.cooldown > 0:
            return
        self.cooldown = 14
        self.flash = 4
        self.player_shots.append([0.0, 4.0, 0])

    def _advance_enemy(self):
        diff = self._difficulty_offset()
        for enemy in self.enemies:
            speed = 0.06 + self.wave * 0.01 + (0.04 if enemy[4] else 0.0)
            enemy[0] += enemy[2] + math.sin(self.frame * 0.035 + enemy[1]) * 0.006
            if abs(enemy[0]) > 0.8:
                enemy[2] = -enemy[2]
            enemy[0] = clamp(enemy[0], -1.25, 1.25)
            if enemy[1] > 18:
                enemy[1] -= speed + diff * 0.015
            enemy[3] -= 1
            if enemy[5] > 0:
                enemy[5] -= 1
            if enemy[3] <= 0:
                self.enemy_shells.append([enemy[0], enemy[1], 0])
                enemy[3] = max(32, 105 - self.wave * 6 - diff * 17 + random.randint(0, 30))
        if self.wave_delay > 0:
            self.wave_delay -= 1
            if self.wave_delay <= 0:
                self.wave += 1
                self._spawn_wave()

    def _take_hit(self):
        if self.hit_flash > 0:
            return True
        self.lives -= 1
        self.hit_flash = 9
        if self.lives <= 0:
            set_game_over_score(self.score)
            return False
        return True

    def _hit_enemy(self, shot):
        for enemy in self.enemies:
            angular_window = 0.075 + clamp(7.0 / max(14.0, enemy[1]), 0.0, 0.22)
            if abs(enemy[0] - shot[0]) <= angular_window and abs(enemy[1] - shot[1]) <= 4.5:
                enemy[5] = 5
                self.score += 90 + self.wave * 20 + (40 if enemy[4] else 0)
                self.enemies.remove(enemy)
                return True
        return False

    def _hit_rock(self, shot):
        for rock in self.rocks:
            angular_window = 0.06 + rock[2] * 0.035
            if abs(rock[0] - shot[0]) <= angular_window and abs(rock[1] - shot[1]) <= 4.0:
                self.rocks.remove(rock)
                self.score += 8
                return True
        return False

    def _advance_shells(self):
        if self.cooldown > 0:
            self.cooldown -= 1
        if self.flash > 0:
            self.flash -= 1
        if self.hit_flash > 0:
            self.hit_flash -= 1
        kept_shots = []
        for shot in self.player_shots:
            shot[1] += 4.2
            shot[2] += 1
            if self._hit_enemy(shot) or self._hit_rock(shot):
                continue
            if shot[1] < 92 and shot[2] < 24:
                kept_shots.append(shot)
        self.player_shots = kept_shots
        kept_shells = []
        shell_speed = 2.0 + self.wave * 0.03 + (0.2 if self.difficulty == "hard" else 0.0)
        for shell in self.enemy_shells:
            shell[1] -= shell_speed
            shell[2] += 1
            if shell[1] <= 4:
                if abs(shell[0]) < 0.16:
                    if not self._take_hit():
                        return False
                continue
            kept_shells.append(shell)
        self.enemy_shells = kept_shells
        if not self.enemies and self.wave_delay <= 0:
            self.score += 120 + self.wave * 25
            self.wave_delay = 28
        return True

    def _project(self, bearing, dist):
        if abs(bearing) > self.FOV:
            return None
        scale = clamp(96.0 / max(9.0, dist), 1.0, 9.0)
        cx = WIDTH // 2 + int(bearing * 39)
        cy = int(26 + (82.0 - dist) * 0.42)
        cy = clamp(cy, 18, PLAY_HEIGHT - 4)
        return cx, cy, scale

    def _draw_enemy(self, enemy):
        projected = self._project(enemy[0], enemy[1])
        if projected is None:
            return
        cx, cy, scale = projected
        w = int(3 + scale * 1.7)
        h = int(2 + scale * 0.75)
        col = (255, 110, 70) if enemy[4] else (70, 255, 90)
        if enemy[5] > 0:
            col = (255, 255, 180)
        draw_rect_outline(cx - w, cy - h, cx + w, cy + h, *col)
        draw_line(cx - w, cy + h, cx - w - int(2 + scale), cy + h + 2, *col)
        draw_line(cx + w, cy + h, cx + w + int(2 + scale), cy + h + 2, *col)
        draw_line(cx, cy - h, cx + int(enemy[0] * 6), cy - h - int(4 + scale), *col)
        if scale > 3:
            draw_line(cx - w, cy, cx + w, cy, *col)

    def _draw_rock(self, rock):
        projected = self._project(rock[0], rock[1])
        if projected is None:
            return
        cx, cy, scale = projected
        s = int(rock[2] + scale * 0.75)
        col = (85, 120, 85)
        draw_line(cx, cy - s, cx - s, cy + s, *col)
        draw_line(cx, cy - s, cx + s, cy + s, *col)
        draw_line(cx - s, cy + s, cx + s, cy + s, *col)

    def _draw_radar(self):
        draw_rect_outline(1, 1, 13, 13, 30, 110, 50)
        display.set_pixel(7, 7, 80, 255, 120)
        for rock in self.rocks:
            rr = clamp(rock[1] / 12, 2, 6)
            rx = 7 + int(math.sin(rock[0]) * rr)
            ry = 7 - int(math.cos(rock[0]) * rr)
            display.set_pixel(rx, ry, 70, 120, 70)
        for enemy in self.enemies:
            rr = clamp(enemy[1] / 11, 2, 6)
            ex = 7 + int(math.sin(enemy[0]) * rr)
            ey = 7 - int(math.cos(enemy[0]) * rr)
            draw_rectangle(ex - 1, ey - 1, ex + 1, ey + 1, 255, 80, 60)

    def _draw_grid(self):
        horizon = 27
        draw_line(0, horizon, WIDTH - 1, horizon, 30, 180, 70)
        for y in (33, 39, 45, 51, 56):
            fade = max(22, 100 - (y - horizon) * 2)
            draw_line(0, y, WIDTH - 1, y, 10, fade, 35)
        for x in (8, 20, 32, 44, 56):
            draw_line(WIDTH // 2, horizon, x, PLAY_HEIGHT - 1, 18, 120, 52)

    def _draw(self):
        display.clear()
        if self.hit_flash > 0 and self.hit_flash % 2:
            draw_rectangle(0, 0, WIDTH - 1, PLAY_HEIGHT - 1, 60, 0, 0)
        self._draw_grid()
        for rock in self.rocks:
            self._draw_rock(rock)
        for enemy in sorted(self.enemies, key=lambda e: e[1], reverse=True):
            self._draw_enemy(enemy)
        for shell in self.enemy_shells:
            projected = self._project(shell[0], shell[1])
            if projected:
                cx, cy, scale = projected
                r = max(1, int(scale // 2))
                draw_rectangle(cx - r, cy - r, cx + r, cy + r, 255, 220, 70)
        for shot in self.player_shots:
            projected = self._project(shot[0], shot[1])
            if projected:
                cx, cy, _scale = projected
                draw_rectangle(cx - 1, cy - 1, cx + 1, cy + 1, 255, 255, 180)
        if self.flash > 0:
            draw_line(28, PLAY_HEIGHT - 1, 32, 27, 255, 255, 160)
            draw_line(36, PLAY_HEIGHT - 1, 32, 27, 255, 255, 160)
            cross_col = (255, 255, 200)
        else:
            cross_col = (90, 255, 110)
        draw_line(28, 28, 36, 28, *cross_col)
        draw_line(32, 24, 32, 32, *cross_col)
        if self.wave_delay > 0:
            draw_text_small(21, 4, "W" + str(self.wave + 1), 255, 255, 180)
        self._draw_radar()
        draw_text_small(16, 1, "L" + str(self.lives), 220, 220, 220)
        draw_text_small(16, 7, "W" + str(self.wave), 160, 220, 160)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        self.reset()

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            self.frame += 1
            self._move_player(joystick)
            if z_button and not self.last_z:
                self._fire()
            self.last_z = z_button
            self._advance_enemy()
            if not self._advance_shells():
                return False
            self._draw()
            return True
        return step

    def main_loop(self, joystick):
        begin_game(0)
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        begin_game(0)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class KeenGame:
    """
    KEEN
    Controls:
      - Left / Right: run
      - Up or Z: jump
      - C: return to menu
    Compact Keen-style platformer with gems, keys, enemies, and exits.
    """
    FRAME_MS = 34
    CELL = 4
    VIEW_W = WIDTH
    PLAYER_W = 3
    PLAYER_H = 5
    MAPS = (
        (
            "########################################",
            "#......................................#",
            "#...........G..........................#",
            "#........######........................#",
            "#....................G.................#",
            "#.....####........########.......####..#",
            "#............................K.........#",
            "#..G............#####..................#",
            "#..........###..................G......#",
            "#......................######..........#",
            "#....###...............................#",
            "#P................S.............S...E..#",
            "#......................................#",
            "########################################",
        ),
        (
            "########################################",
            "#......................................#",
            "#.............................G........#",
            "#......#####.............########......#",
            "#..................G...................#",
            "#..G.........####............####......#",
            "#.................S....................#",
            "#............########..............K...#",
            "#......................................#",
            "#......S..............####.............#",
            "#....######............................#",
            "#P..................................E..#",
            "#......................................#",
            "########################################",
        ),
        (
            "########################################",
            "#......................................#",
            "#...G.....................K............#",
            "#..#####...............#########.......#",
            "#......................................#",
            "#...........G..........................#",
            "#.......########..............G........#",
            "#....................S.................#",
            "#..................######..............#",
            "#...S..................................#",
            "#..######...............####...........#",
            "#P..................................E..#",
            "#......................................#",
            "########################################",
        ),
    )

    def __init__(self):
        self.reset()

    def reset(self):
        self.level = 0
        self.score = 0
        self.last_jump = False
        self._load_level()

    def _load_level(self):
        self.map = [list(row) for row in self.MAPS[self.level % len(self.MAPS)]]
        self.map_w = len(self.map[0])
        self.map_h = len(self.map)
        self.items = []
        self.enemies = []
        self.key = False
        self.exit = (self.map_w - 2, 2)
        for y, row in enumerate(self.map):
            for x, ch in enumerate(row):
                if ch == "P":
                    self.px = float(x * self.CELL)
                    self.py = float(y * self.CELL - 1)
                    row[x] = "."
                elif ch == "G":
                    self.items.append([x * self.CELL + 1, y * self.CELL + 1, "gem"])
                    row[x] = "."
                elif ch == "K":
                    self.items.append([x * self.CELL + 1, y * self.CELL + 1, "key"])
                    row[x] = "."
                elif ch == "E":
                    self.exit = (x, y)
                    row[x] = "."
                elif ch == "S":
                    self.enemies.append([float(x * self.CELL), float(y * self.CELL + 4), random.choice((-1, 1))])
                    row[x] = "."
        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = False
        self.camera_x = 0

    def _solid_tile(self, tx, ty):
        if tx < 0 or tx >= self.map_w or ty < 0 or ty >= self.map_h:
            return True
        return self.map[ty][tx] == "#"

    def _rect_solid(self, x, y, w, h):
        left = int(x) // self.CELL
        right = int(x + w - 1) // self.CELL
        top = int(y) // self.CELL
        bottom = int(y + h - 1) // self.CELL
        for ty in range(top, bottom + 1):
            for tx in range(left, right + 1):
                if self._solid_tile(tx, ty):
                    return True
        return False

    def _move_axis(self, amount, axis):
        steps = int(abs(amount) + 1)
        delta = amount / steps
        for _ in range(steps):
            if axis == "x":
                nx = self.px + delta
                if self._rect_solid(nx, self.py, self.PLAYER_W, self.PLAYER_H):
                    self.vx = 0.0
                    break
                self.px = nx
            else:
                ny = self.py + delta
                if self._rect_solid(self.px, ny, self.PLAYER_W, self.PLAYER_H):
                    if delta > 0:
                        self.on_ground = True
                    self.vy = 0.0
                    break
                self.py = ny

    def _move_player(self, joystick, z_button):
        d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_LEFT, JOYSTICK_RIGHT])
        if d == JOYSTICK_LEFT:
            self.vx = max(-1.55, self.vx - 0.35)
        elif d == JOYSTICK_RIGHT:
            self.vx = min(1.55, self.vx + 0.35)
        else:
            self.vx *= 0.76
        jump = z_button or d == JOYSTICK_UP
        if jump and not self.last_jump and self.on_ground:
            self.vy = -3.45
            self.on_ground = False
        self.last_jump = jump
        self.vy = min(3.0, self.vy + 0.20)
        self.on_ground = False
        self._move_axis(self.vx, "x")
        self._move_axis(self.vy, "y")
        self.px = clamp(self.px, 4.0, self.map_w * self.CELL - self.PLAYER_W - 4.0)
        self.camera_x = clamp(int(self.px) - 28, 0, self.map_w * self.CELL - WIDTH)

    def _overlap(self, ax, ay, aw, ah, bx, by, bw, bh):
        return not (ax + aw < bx or bx + bw < ax or ay + ah < by or by + bh < ay)

    def _collect_items(self):
        keep = []
        for x, y, kind in self.items:
            if self._overlap(self.px, self.py, self.PLAYER_W, self.PLAYER_H, x, y, 2, 2):
                if kind == "key":
                    self.key = True
                    self.score += 50
                else:
                    self.score += 10
            else:
                keep.append([x, y, kind])
        self.items = keep

    def _move_enemies(self):
        keep = []
        for e in self.enemies:
            e[0] += e[2] * 0.45
            front_x = e[0] + (4 if e[2] > 0 else -1)
            foot_y = e[1] + 5
            if self._rect_solid(e[0], e[1], 4, 4) or not self._solid_tile(int(front_x) // self.CELL, int(foot_y) // self.CELL):
                e[0] -= e[2] * 0.45
                e[2] = -e[2]
            if self._overlap(self.px, self.py, self.PLAYER_W, self.PLAYER_H, e[0], e[1], 4, 4):
                if self.vy > 0.5 and self.py + self.PLAYER_H <= e[1] + 3:
                    self.score += 30
                    self.vy = -2.1
                    continue
                set_game_over_score(self.score)
                return False
            keep.append(e)
        self.enemies = keep
        return True

    def _check_exit(self):
        ex, ey = self.exit
        if not self.key:
            return True
        if self._overlap(self.px, self.py, self.PLAYER_W, self.PLAYER_H, ex * self.CELL, ey * self.CELL, 4, 7):
            self.score += 150 + self.level * 50
            self.level += 1
            if self.level >= len(self.MAPS):
                set_game_over_score(self.score, won=True)
                return False
            self._load_level()
        return True

    def _draw(self):
        display.clear()
        first_col = self.camera_x // self.CELL
        last_col = min(self.map_w, first_col + 18)
        for y, row in enumerate(self.map):
            sy = y * self.CELL
            for x in range(first_col, last_col):
                sx = x * self.CELL - self.camera_x
                if row[x] == "#":
                    draw_rectangle(sx, sy, sx + 3, sy + 3, 45, 80, 120)
        ex, ey = self.exit
        door_col = (240, 240, 255) if self.key else (95, 55, 130)
        draw_rect_outline(ex * self.CELL - self.camera_x, ey * self.CELL - 2, ex * self.CELL - self.camera_x + 4, ey * self.CELL + 6, *door_col)
        for x, y, kind in self.items:
            sx = x - self.camera_x
            if -3 <= sx < WIDTH:
                col = (80, 230, 255) if kind == "key" else (255, 230, 70)
                draw_rectangle(int(sx), int(y), int(sx) + 1, int(y) + 1, *col)
        for x, y, _d in self.enemies:
            sx = int(x) - self.camera_x
            if -5 <= sx < WIDTH:
                draw_rectangle(sx, int(y), sx + 3, int(y) + 3, 255, 70, 70)
        px = int(self.px) - self.camera_x
        py = int(self.py)
        draw_rectangle(px, py, px + self.PLAYER_W - 1, py + self.PLAYER_H - 1, 240, 240, 230)
        display.set_pixel(px + 2, py + 1, 30, 30, 60)
        if self.key:
            draw_text_small(1, PLAY_HEIGHT, "KEY", 80, 230, 255)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        self.reset()

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            self._move_player(joystick, z_button)
            self._collect_items()
            if not self._move_enemies():
                return False
            if not self._check_exit():
                return False
            self._draw()
            return True
        return step

    def main_loop(self, joystick):
        begin_game(0)
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        begin_game(0)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class PitfallGame:
    """
    PITFALL MINI (Endlos-Runner)
    Steuerung:
      - Links/Rechts: laufen
      - Z oder Stick UP: springen
      - C: zurück ins Menü
    """
    def __init__(self):
        self.reset()

    def reset(self):
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
        self._safe_distance = 30.0

    def _spawn_one(self, x_start):

        # At the start, spawn only treasures to avoid immediate frustration.
        if self.distance < self._safe_distance:
            kind = "TREASURE"
        else:
            r = random.randint(0, 99)
            kind = "PIT" if r < 45 else ("SNAKE" if r < 75 else "TREASURE")

        # nicht zu viele pits hintereinander
        if kind == "PIT" and self.last_spawn_kind == "PIT" and random.randint(0, 99) < 55:
            kind = "SNAKE"

        if kind == "PIT":
            w = random.randint(8, 16)
            self.obstacles.append({"kind": "PIT", "x": float(x_start), "w": w})
        elif kind == "SNAKE":
            w = random.randint(5, 8)
            self.obstacles.append({"kind": "SNAKE", "x": float(x_start), "w": w})
        else:
            ty = self.ground_y - random.choice([12, 16, 20])
            self.obstacles.append({"kind": "TREASURE", "x": float(x_start), "y": ty, "w": 2, "h": 2, "got": False})

        self.last_spawn_kind = kind

    def _ensure_obstacles(self):
        max_right = None
        for o in self.obstacles:
            w = o.get("w", 1)
            xr = o["x"] + w
            if max_right is None or xr > max_right:
                max_right = xr

        if max_right is None:
            max_right = WIDTH + 8

        while max_right < WIDTH + 20:
            gap = random.randint(14, 28)
            spawn_x = max_right + gap
            self._spawn_one(spawn_x)
            max_right = spawn_x + self.obstacles[-1].get("w", 1)

    def _player_in_pit(self):
        foot = self.px + (self.pw // 2)
        for o in self.obstacles:
            if o["kind"] == "PIT":
                if o["x"] <= foot <= (o["x"] + o["w"] - 1):
                    return True
        return False

    def _check_snake_collision(self):
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
        # reuse shared helper to draw playfield rectangles
        draw_play_rect(x, y, w, h, r, g, b)

    def _render(self):
        display.clear()

        # Boden-Band
        self._rect_play(0, self.ground_y, WIDTH, PLAY_HEIGHT - self.ground_y, 40, 90, 40)

        # Pits (Löcher)
        for o in self.obstacles:
            if o["kind"] == "PIT":
                x = int(o["x"])
                self._rect_play(x, self.ground_y, o["w"], PLAY_HEIGHT - self.ground_y, 0, 0, 0)

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
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        self._ensure_obstacles()

        frame_ms = 33
        last_frame = ticks_ms()

        while not game_over:
            try:
                c_button, z_button = joystick.read_buttons()
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
                self.obstacles = [o for o in self.obstacles if (o.get("x", 0) + o.get("w", 1)) > -2]
                self._ensure_obstacles()

                # move
                d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_UP])
                if d == JOYSTICK_LEFT:
                    self.px = max(0, self.px - 2)
                elif d == JOYSTICK_RIGHT:
                    self.px = min(WIDTH - self.pw, self.px + 2)

                # jump with variable height
                if self.jump_cd > 0:
                    self.jump_cd -= 1
                
                jump_pressed = (z_button or d == JOYSTICK_UP)
                if jump_pressed and self.on_ground and self.jump_cd == 0:
                    if not self.jump_charging:
                        self.jump_charging = True
                        self.jump_start_frame = self.frame
                    else:
                        # cap charge: auto-release after max frames
                        hold_frames = self.frame - self.jump_start_frame
                        if hold_frames >= self.jump_charge_max_frames:
                            self.vy = self.jump_max_power
                            self.on_ground = False
                            self.jump_cd = 10
                            self.jump_charging = False
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

    async def main_loop_async(self, joystick):
        """Async version for pygbag: yields with asyncio.sleep()."""
        if asyncio is None:
            return self.main_loop(joystick)

        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        self._ensure_obstacles()
        def loop_iteration():
            global game_over, global_score
            c_button, z_button = joystick.read_buttons()
            if c_button or game_over:
                return False

            self.frame += 1

            # difficulty
            self.speed = 1.2 + (self.distance / 800.0)
            if self.speed > 2.6:
                self.speed = 2.6

            # scroll obstacles
            for o in self.obstacles:
                o["x"] -= self.speed

            # cleanup
            self.obstacles = [o for o in self.obstacles if (o.get("x", 0) + o.get("w", 1)) > -2]
            self._ensure_obstacles()

            # move
            d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_UP])
            if d == JOYSTICK_LEFT:
                self.px = max(0, self.px - 2)
            elif d == JOYSTICK_RIGHT:
                self.px = min(WIDTH - self.pw, self.px + 2)

            # jump with variable height
            if self.jump_cd > 0:
                self.jump_cd -= 1

            jump_pressed = (z_button or d == JOYSTICK_UP)
            if jump_pressed and self.on_ground and self.jump_cd == 0:
                if not self.jump_charging:
                    self.jump_charging = True
                    self.jump_start_frame = self.frame
                else:
                    hold_frames = self.frame - self.jump_start_frame
                    if hold_frames >= self.jump_charge_max_frames:
                        self.vy = self.jump_max_power
                        self.on_ground = False
                        self.jump_cd = 10
                        self.jump_charging = False
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

            self._check_treasure()

            if self._check_snake_collision() or self.py > PLAY_HEIGHT + 2:
                global_score = self.score
                game_over = True
                return False

            self.distance += self.speed
            self.score = int(self.distance / 6) + self.bonus
            global_score = self.score
            self._render()
            return True

        try:
            await _run_game_loop_async(33, loop_iteration)
        except RestartProgram:
            return

class Game2048:
    """
    2048
    Controls:
      - Left / Right / Up / Down: slide tiles
      - Z (hold): reset board
      - C: return to menu
    """

    # 2048 visual and timing constants (class-scoped)
    TILE_PX = 12
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

    INPUT_MS = 120
    MOVE_LOCK_MS = 200
    A_LONG_MS = 420

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
        except Exception:
            # fall back to module globals if lookup fails
            self.display = globals().get("display")
            self.draw_text = globals().get("draw_text")
            self.draw_rectangle = globals().get("draw_rectangle")
            self.display_score_and_time = globals().get("display_score_and_time")
            self.ticks_ms = globals().get("ticks_ms")
            self.ticks_diff = globals().get("ticks_diff")
            self.sleep_ms = globals().get("sleep_ms")

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
        self._input_locked_until = 0
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
        self._input_locked_until = 0
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
            draw_rect_outline(x1, y1, x2, y2, *self.COL_FRAME)
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
            c_button, z_button = joystick.read_buttons()
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

            if self.ticks_diff(now, self._input_locked_until) < 0:
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
                    self._input_locked_until = now + self.MOVE_LOCK_MS
                    if not self._any_moves_possible():
                        if self.display:
                            self.display.clear()
                        draw_centered_text_lines(("LOSE",), start_y=18, r=255, g=0, b=0)
                        set_game_over_score(self.score, won=False)
                        if self.display_score_and_time:
                            self.display_score_and_time(self.score, force=True)
                        self.sleep_ms(1000)
                        return
                    elif self.victory:
                        if self.display:
                            self.display.clear()
                        draw_centered_text_lines(("WIN!",), start_y=18, r=0, g=255, b=0)
                        set_game_over_score(self.score, won=True)
                        if self.display_score_and_time:
                            self.display_score_and_time(self.score, force=True)
                        self.sleep_ms(700)
                        return
                self._last_input = now

            self.sleep_ms(2)
            if (now & 0x3FF) == 0:
                gc.collect()

    async def main_loop_async(self, joystick):
        """Async/cooperative version of the 2048 main loop for browsers.

        Uses `await asyncio.sleep()` instead of blocking `sleep_ms()` so the
        event loop remains responsive in WASM/pygbag environments.
        """
        if asyncio is None:
            return self.main_loop(joystick)

        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        self.ticks_ms()

        while True:
            c_button, z_button = joystick.read_buttons()
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

            if self.ticks_diff(now, self._input_locked_until) < 0:
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
                    self._input_locked_until = now + self.MOVE_LOCK_MS
                    if not self._any_moves_possible():
                        if self.display:
                            self.display.clear()
                        draw_centered_text_lines(("LOSE",), start_y=18, r=255, g=0, b=0)
                        set_game_over_score(self.score, won=False)
                        if self.display_score_and_time:
                            self.display_score_and_time(self.score, force=True)
                        await asyncio.sleep(1.0)
                        return
                    elif self.victory:
                        if self.display:
                            self.display.clear()
                        draw_centered_text_lines(("WIN!",), start_y=18, r=0, g=255, b=0)
                        set_game_over_score(self.score, won=True)
                        if self.display_score_and_time:
                            self.display_score_and_time(self.score, force=True)
                        await asyncio.sleep(0.7)
                        return
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
    LOCO-MOTION
    Controls:
      - Left / Right / Up / Down: move cursor
      - Z (tap): rotate tile under cursor
      - Z (tap on start/end or hold): start / abort train run
      - C: return to menu
    """

    # LocoMotion constants
    RL_TILE = 8
    RL_W = 8
    RL_H = 7
    RL_PX_W = RL_W * RL_TILE
    RL_PX_H = RL_H * RL_TILE

    N = 1
    E = 2
    S = 4
    W = 8

    TFLAG_NONE = 0x00
    TFLAG_START = 0x10
    TFLAG_END = 0x20
    TFLAG_EMPTY = 0x30

    COL_BG = (0, 0, 0)
    COL_TILE_BG = (0, 0, 0)
    COL_RAIL = (180, 180, 180)
    COL_RAIL2 = (80, 80, 80)
    COL_START = (0, 255, 0)
    COL_END = (255, 200, 0)
    COL_CURSOR = (255, 255, 0)
    COL_TRAIN = (255, 60, 60)
    COL_SHADOW = (40, 40, 40)

    EDIT_INPUT_MS = 120
    FRAME_MS_RUN = 35
    Z_LONG_MS = 420

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
        (
            b"S----7..",
            b".....|..",
            b".....|..",
            b".....|..",
            b"E----F..",
            b"........",
            b"........",
        ),
        (
            b"S--7....",
            b"..|.F--E",
            b"..L-7...",
            b"....|...",
            b".F--J...",
            b".|......",
            b".L--T...",
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
        """Draw compact LocoMotion status in the 6-pixel HUD band."""
        try:
            draw_rectangle(0, PLAY_HEIGHT, WIDTH - 1, HEIGHT - 1, 0, 0, 0)
            left = ("R" if self.mode_run else "E") + str(self.level_idx + 1)
            right = "RUN" if self.mode_run else "Z ROT"
            draw_text_small(1, PLAY_HEIGHT, left, 0, 180, 255)
            draw_text_small(WIDTH - len(right) * 6, PLAY_HEIGHT, right, 180, 180, 180)
        except Exception:
            pass

    def _cursor_on_endpoint(self):
        """Return True when the cursor is on the fixed start or end tile."""
        v = self._get(self.cur_x, self.cur_y)
        flag = v & 0xF0
        return flag == self.TFLAG_START or flag == self.TFLAG_END

    def _rotate_tile_at_cursor(self):
        """Rotate the tile under the cursor clockwise and update view."""
        x, y = self.cur_x, self.cur_y
        v = self._get(x, y)
        flag = v & 0xF0
        bits = v & 0x0F

        if flag in (self.TFLAG_START, self.TFLAG_END):
            return
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
        if self.mode_run:
            return
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

    async def _step_train_async(self):
        """Async version of _step_train() for browser/pygbag runtimes."""
        global global_score
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
            await sleep_ms_async(1100)
            self.load_level(self.level_idx + 1, reset_score=False)
            return None
        next_dir = self._choose_next_dir(nxt_bits, incoming, self.tr_dir)
        if next_dir is None:
            return False
        self.tr_cx = nx
        self.tr_cy = ny
        self.tr_dir = next_dir
        return True

    async def _fail_derail_async(self):
        """Async derail handler."""
        set_game_over_score(self.score, won=False)
        display.clear()
        draw_text(6, 18, "DERAIL", 255, 0, 0)
        display_score_and_time(global_score, force=True)
        await sleep_ms_async(900)
        self._abort_run()

    def _fail_derail(self):
        """Handle a derail failure: display message and return to shared game-over flow."""
        set_game_over_score(self.score, won=False)
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
            c_button, z_button = joystick.read_buttons()
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
                    if held < self.Z_LONG_MS and self._z_armed:
                        if self.mode_run:
                            self._abort_run()
                        elif self._cursor_on_endpoint():
                            self._start_run()
                        else:
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
        if asyncio is None:
            return self.main_loop(joystick)

        global game_over, global_score
        game_over = False
        global_score = 0

        self.load_level(self.level_idx, reset_score=False)
        self._last_input_ms = ticks_ms()
        last_frame = ticks_ms()

        while True:
            c_button, z_button = joystick.read_buttons()
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
                    if held < self.Z_LONG_MS and self._z_armed:
                        if self.mode_run:
                            self._abort_run()
                        elif self._cursor_on_endpoint():
                            self._start_run()
                        else:
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

                st = await self._step_train_async()
                if st is None:
                    last_frame = ticks_ms()
                    continue
                if st is False:
                    await self._fail_derail_async()
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


class OthelloGame:
    """
    REVERSI / OTHELLO
    Controls:
      - Left / Right / Up / Down: move cursor
      - Z: place disc
      - C: return to menu
    """

    BOARD_SIZE = 8
    CELL_SIZE = 6
    BOARD_W = BOARD_SIZE * CELL_SIZE
    BOARD_H = BOARD_SIZE * CELL_SIZE
    EMPTY = 0
    P1 = 1
    P2 = 2

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
        except Exception:
            pass

        self.board = [[self.EMPTY] * self.BOARD_SIZE for _ in range(self.BOARD_SIZE)]
        self.cur_x = 3
        self.cur_y = 3
        self.current_player = self.P1
        self.score = 0
        self.game_finished = False
        self._needs_render = True
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
        self._needs_render = True

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
        self._needs_render = False

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
            c_button, z_button = joystick.read_buttons()
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
                    self._needs_render = True
                elif d == JOYSTICK_RIGHT and self.cur_x < self.BOARD_SIZE - 1:
                    self.cur_x += 1
                    self._needs_render = True
                elif d == JOYSTICK_UP and self.cur_y > 0:
                    self.cur_y -= 1
                    self._needs_render = True
                elif d == JOYSTICK_DOWN and self.cur_y < self.BOARD_SIZE - 1:
                    self.cur_y += 1
                    self._needs_render = True

                if z_button and self.is_valid_move(self.cur_x, self.cur_y, self.P1):
                    self.apply_move(self.cur_x, self.cur_y, self.P1)
                    self.current_player = self.P2
                    self._needs_render = True

            else:
                if self.cpu_move():
                    self._needs_render = True
                self.current_player = self.P1
                sleep_ms(120)

            if not self.valid_moves_for(self.current_player):
                if self.check_game_end():
                    continue
                self.current_player = (
                    self.P1 if self.current_player == self.P2 else self.P2
                )

            if self._needs_render:
                self.render(full=True)
            global_score = self.score

    async def main_loop_async(self, joystick):
        """Async/cooperative Othello loop for browsers (pygbag).

        Mirrors `main_loop` but yields with `await asyncio.sleep()` to keep
        the event loop responsive in WASM environments.
        """
        if asyncio is None:
            return self.main_loop(joystick)

        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()

        frame_ms = 80
        last_frame = ticks_ms()

        while True:
            c_button, z_button = joystick.read_buttons()
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
                    self._needs_render = True
                elif d == JOYSTICK_RIGHT and self.cur_x < self.BOARD_SIZE - 1:
                    self.cur_x += 1
                    self._needs_render = True
                elif d == JOYSTICK_UP and self.cur_y > 0:
                    self.cur_y -= 1
                    self._needs_render = True
                elif d == JOYSTICK_DOWN and self.cur_y < self.BOARD_SIZE - 1:
                    self.cur_y += 1
                    self._needs_render = True

                if z_button and self.is_valid_move(self.cur_x, self.cur_y, self.P1):
                    self.apply_move(self.cur_x, self.cur_y, self.P1)
                    self.current_player = self.P2
                    self._needs_render = True

            else:
                if self.cpu_move():
                    self._needs_render = True
                self.current_player = self.P1
                await asyncio.sleep(0.12)

            if not self.valid_moves_for(self.current_player):
                if self.check_game_end():
                    continue
                self.current_player = (
                    self.P1 if self.current_player == self.P2 else self.P2
                )

            if self._needs_render:
                self.render(full=True)
            global_score = self.score


class SokobanGame:
    """
    SOKOBAN
    Controls:
      - Left / Right / Up / Down: move player / push crate
      - Z: undo last move
      - C: return to menu
    """

    # --- Sokoban constants & levels (kept as class attributes) ---
    SOK_TILE = 4
    SOK_W = 16
    SOK_H = 14

    # Map encoding (bytes): '#' wall, '.' floor, 'G' goal, 'B' box,
    # '*' box on goal, 'P' player, '+' player on goal
    SOK_LEVELS = [
        (
            b"################",
            b"#0.............#",
            b"#....#####.....#",
            b"#....#..P#.....#",
            b"#..###.B.#.....#",
            b"#..#..BBB#.....#",
            b"#..#...GG#.....#",
            b"#..###.GG#.....#",
            b"#....#...#.....#",
            b"#....#####.....#",
            b"#.............0#",
            b"#..0...........#",
            b"#..0...........#",
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
            b"#..#......#....#",
            b"#..####.####...#",
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
            b"#..#PBG#.......#",
            b"#..#...#.......#",
            b"#..#####.......#",
            b"#..............#",
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
            b"#..########....#",
            b"#..#......#....#",
            b"#..#P.B.G.#....#",
            b"#..#..B.G.#....#",
            b"#..#......#....#",
            b"#..########....#",
            b"#..............#",
            b"#..............#",
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
        except Exception:
            pass

        self.level_idx = 0
        self.score = 0
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
            self.score = 0
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
            c_button, z_button = joystick.read_buttons()
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
                    finish_score = max(1, 1000 - self.moves + ((self.level_idx % len(self.SOK_LEVELS)) + 1) * 100)
                    self.score += finish_score
                    global_score = self.score
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
                    display_score_and_time(global_score, force=True)
                    sleep_ms(1300)
                    if self.level_idx + 1 >= len(self.SOK_LEVELS):
                        set_game_over_score(self.score, won=True)
                        return
                    self.level_idx += 1
                    self.reset_level(reset_all=False)
                    self._last_input_ms = ticks_ms()
                    continue

            else:
                self._last_input_ms = now - (self.input_ms // 2)

            maybe_collect(140)

    async def main_loop_async(self, joystick):
        """Async/cooperative Sokoban loop for browsers (pygbag).

        Mirrors `main_loop` but yields with `await asyncio.sleep()` instead of
        blocking `sleep_ms()` so the event loop remains responsive.
        """
        if asyncio is None:
            return self.main_loop(joystick)

        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset_level(reset_all=True)
        self._last_input_ms = ticks_ms()

        while True:
            c_button, z_button = joystick.read_buttons()
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
                    finish_score = max(1, 1000 - self.moves + ((self.level_idx % len(self.SOK_LEVELS)) + 1) * 100)
                    self.score += finish_score
                    global_score = self.score
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
                    display_score_and_time(global_score, force=True)
                    await asyncio.sleep(1.3)
                    if self.level_idx + 1 >= len(self.SOK_LEVELS):
                        set_game_over_score(self.score, won=True)
                        return
                    self.level_idx += 1
                    self.reset_level(reset_all=False)
                    self._last_input_ms = ticks_ms()
                    continue

            else:
                self._last_input_ms = now - (self.input_ms // 2)

            try:
                maybe_collect(140)
            except Exception:
                pass


class BejeweledGame:
    """Simple Bejeweled-like match-3 puzzle.

    Controls:
      - Stick: move cursor (cell-by-cell)
      - Z: select / swap (select one tile, then another adjacent to swap)
      - C: return to menu
    """

    w = 8
    h = 8
    COLORS = [
        (220, 60, 60),
        (60, 200, 80),
        (60, 140, 220),
        (240, 200, 60),
        (200, 80, 200),
        (60, 200, 180),
    ]

    def __init__(self):
        self.reset()

    def reset(self):
        self.cols = self.w
        self.rows = self.h
        self.tile_w = max(2, WIDTH // self.cols)
        self.tile_h = max(2, PLAY_HEIGHT // self.rows)
        self.grid = [
            [random.randint(0, len(self.COLORS) - 1) for _ in range(self.cols)]
            for _ in range(self.rows)
        ]
        # remove initial matches
        while True:
            m = self._find_matches()
            if not m:
                break
            for x, y in m:
                self.grid[y][x] = random.randint(0, len(self.COLORS) - 1)

        self.cursor_x = 0
        self.cursor_y = 0
        self.sel = None
        self.score = 0
        # input smoothing for cursor (ms between moves)
        self._last_move = ticks_ms()
        self._move_delay = 160
        self._prev_cursor = None
        self._prev_sel = None
        self._last_drawn_score = -1
        self._full_redraw = True
        self._needs_redraw = True

    def _find_matches(self):
        # Identify connected components (4-connected) of the same color.
        matches = set()
        visited = set()
        for y in range(self.rows):
            for x in range(self.cols):
                if (x, y) in visited:
                    continue
                color = self.grid[y][x]
                if color is None:
                    visited.add((x, y))
                    continue

                stack = [(x, y)]
                comp = set()
                while stack:
                    cx, cy = stack.pop()
                    if (cx, cy) in comp:
                        continue
                    if not (0 <= cx < self.cols and 0 <= cy < self.rows):
                        continue
                    if self.grid[cy][cx] != color:
                        continue
                    comp.add((cx, cy))
                    visited.add((cx, cy))
                    stack.append((cx + 1, cy))
                    stack.append((cx - 1, cy))
                    stack.append((cx, cy + 1))
                    stack.append((cx, cy - 1))

                if len(comp) >= 3:
                    matches |= comp

        return matches

    def _collapse_and_refill(self):
        self._collapse_and_refill_animated(delay_ms=0)

    def _draw_tile_at_px(self, x, y_px, value):
        gx = x * self.tile_w
        if y_px > PLAY_HEIGHT - 1 or y_px + self.tile_h <= 0:
            return
        col = self.COLORS[value % len(self.COLORS)]
        y1 = max(0, y_px)
        y2 = min(PLAY_HEIGHT - 1, y_px + self.tile_h - 1)
        draw_rectangle(gx, y1, gx + self.tile_w - 1, y2, *col)
        if y1 <= y2:
            draw_rectangle(gx, y1, gx + self.tile_w - 1, y1, min(255, col[0] + 35), min(255, col[1] + 35), min(255, col[2] + 35))

    def _draw_tile_value(self, x, y, value, empty_color=(20, 20, 20)):
        gx = x * self.tile_w
        gy = y * self.tile_h
        if value is None:
            draw_rectangle(gx, gy, gx + self.tile_w - 1, gy + self.tile_h - 1, *empty_color)
        else:
            col = self.COLORS[value % len(self.COLORS)]
            draw_rectangle(gx, gy, gx + self.tile_w - 1, gy + self.tile_h - 1, *col)

    def _draw_falling_tiles(self, movers, frame_px):
        display.clear()
        for x, start_px, end_px, value in movers:
            y_px = start_px + min(frame_px, end_px - start_px)
            self._draw_tile_at_px(x, y_px, value)
        self._draw_hud(force=True)
        display_flush()

    def _collapse_and_refill_animated(self, delay_ms=14):
        movers = []
        new_grid = [[None for _x in range(self.cols)] for _y in range(self.rows)]
        max_drop = 0

        for x in range(self.cols):
            kept = []
            for y in range(self.rows - 1, -1, -1):
                v = self.grid[y][x]
                if v is not None:
                    kept.append((y, v))

            dst_y = self.rows - 1
            for src_y, value in kept:
                new_grid[dst_y][x] = value
                start_px = src_y * self.tile_h
                end_px = dst_y * self.tile_h
                movers.append((x, start_px, end_px, value))
                max_drop = max(max_drop, end_px - start_px)
                dst_y -= 1

            spawn_row = -1
            while dst_y >= 0:
                value = random.randint(0, len(self.COLORS) - 1)
                new_grid[dst_y][x] = value
                start_px = spawn_row * self.tile_h
                end_px = dst_y * self.tile_h
                movers.append((x, start_px, end_px, value))
                max_drop = max(max_drop, end_px - start_px)
                spawn_row -= 1
                dst_y -= 1

        for frame_px in range(0, max_drop + 1):
            self._draw_falling_tiles(movers, frame_px)
            if delay_ms > 0:
                sleep_ms(delay_ms)

        self.grid = new_grid

    def _remove_matches_and_score(self, delay_ms=50):
        total_removed = 0
        while True:
            removed_coords = self._find_matches()
            if not removed_coords:
                break

            total_removed += len(removed_coords)

            # Animate removal: matched blocks dissolve into dark pixels.
            anim_frames = max(8, self.tile_w + self.tile_h)
            for f in range(anim_frames):
                display.clear()
                for ry in range(self.rows):
                    for rx in range(self.cols):
                        gx = rx * self.tile_w
                        gy = ry * self.tile_h
                        v = self.grid[ry][rx]
                        if (rx, ry) in removed_coords:
                            base = self.COLORS[v % len(self.COLORS)] if v is not None else (255, 255, 255)
                            for py in range(self.tile_h):
                                for px in range(self.tile_w):
                                    threshold = ((px * 5 + py * 3 + rx * 7 + ry * 11) % anim_frames)
                                    if threshold <= f:
                                        display.set_pixel(gx + px, gy + py, 12, 12, 14)
                                    else:
                                        glow = 30 if f < 3 else 0
                                        display.set_pixel(gx + px, gy + py,
                                                          min(255, base[0] + glow),
                                                          min(255, base[1] + glow),
                                                          min(255, base[2] + glow))
                        else:
                            self._draw_tile_value(rx, ry, v, empty_color=(16, 16, 16))

                self._draw_hud(force=True)
                display_flush()
                maybe_collect(10)
                if delay_ms > 0:
                    sleep_ms(delay_ms)

            # Now actually remove and score
            for rx, ry in removed_coords:
                self.grid[ry][rx] = None
            # score: 10 per gem removed
            self.score += len(removed_coords) * 10
            # collapse and refill pixel by pixel, then loop to catch cascades
            self._collapse_and_refill_animated(delay_ms=delay_ms // 4 if delay_ms > 0 else 0)
            self._full_redraw = True

        self._needs_redraw = True

        return total_removed > 0

    def _swap_tiles(self, a, b):
        ax, ay = a
        bx, by = b
        self.grid[ay][ax], self.grid[by][bx] = self.grid[by][bx], self.grid[ay][ax]

    def _draw_board(self):
        for y in range(self.rows):
            for x in range(self.cols):
                self._draw_tile_value(x, y, self.grid[y][x])
        # selection highlight
        if self.sel is not None:
            sx, sy = self.sel
            gx = sx * self.tile_w
            gy = sy * self.tile_h
            draw_rect_outline(gx, gy, gx + self.tile_w - 1, gy + self.tile_h - 1, 255, 255, 255)

    def _draw_cell(self, x, y):
        self._draw_tile_value(x, y, self.grid[y][x])
        if self.sel == (x, y):
            gx = x * self.tile_w
            gy = y * self.tile_h
            draw_rect_outline(gx, gy, gx + self.tile_w - 1, gy + self.tile_h - 1, 255, 255, 255)

    def _draw_cursor(self):
        gx = self.cursor_x * self.tile_w
        gy = self.cursor_y * self.tile_h
        draw_rect_outline(gx, gy, gx + self.tile_w - 1, gy + self.tile_h - 1, 255, 245, 0)

    def _draw_hud(self, force=False):
        if not force and self.score == self._last_drawn_score:
            return
        draw_rectangle(0, PLAY_HEIGHT, WIDTH - 1, HEIGHT - 1, 0, 0, 0)
        draw_text_small(1, PLAY_HEIGHT, "S{}".format(self.score), 255, 255, 255)
        display_score_and_time(self.score)
        self._last_drawn_score = self.score

    def _render(self, full=False):
        if full or self._full_redraw:
            display.clear()
            self._draw_board()
            self._draw_cursor()
            self._draw_hud(force=True)
        else:
            dirty = []
            for cell in (self._prev_cursor, (self.cursor_x, self.cursor_y), self._prev_sel, self.sel):
                if cell is None:
                    continue
                if cell not in dirty:
                    dirty.append(cell)

            for x, y in dirty:
                if 0 <= x < self.cols and 0 <= y < self.rows:
                    self._draw_cell(x, y)

            self._draw_cursor()
            self._draw_hud()

        self._prev_cursor = (self.cursor_x, self.cursor_y)
        self._prev_sel = self.sel
        self._full_redraw = False
        self._needs_redraw = False
        display_flush()

    def main_loop(self, joystick):
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        display.clear()
        last_logic = ticks_ms()
        logic_ms = 90
        self._needs_redraw = True

        while True:
            c_button, z_button = joystick.read_buttons()
            if c_button:
                global_score = self.score
                game_over = True
                return

            now = ticks_ms()
            d = joystick.read_direction(
                [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
            )
            if d and ticks_diff(now, self._last_move) >= self._move_delay:
                if d == JOYSTICK_UP:
                    self.cursor_y = max(0, self.cursor_y - 1)
                elif d == JOYSTICK_DOWN:
                    self.cursor_y = min(self.rows - 1, self.cursor_y + 1)
                elif d == JOYSTICK_LEFT:
                    self.cursor_x = max(0, self.cursor_x - 1)
                elif d == JOYSTICK_RIGHT:
                    self.cursor_x = min(self.cols - 1, self.cursor_x + 1)
                self._last_move = now
                self._needs_redraw = True

            if z_button and ticks_diff(now, last_logic) >= 0:
                # select or attempt swap
                if self.sel is None:
                    self.sel = (self.cursor_x, self.cursor_y)
                    self._needs_redraw = True
                else:
                    sx, sy = self.sel
                    cx, cy = self.cursor_x, self.cursor_y
                    if abs(sx - cx) + abs(sy - cy) == 1:
                        # adjacent -> try swap
                        self._swap_tiles((sx, sy), (cx, cy))
                        if self._find_matches():
                            # consume matches
                            self._remove_matches_and_score()
                        else:
                            # revert
                            self._swap_tiles((sx, sy), (cx, cy))
                        self.sel = None
                        self._needs_redraw = True
                    else:
                        # new selection
                        self.sel = (self.cursor_x, self.cursor_y)
                        self._needs_redraw = True
                # wait until released
                while joystick.read_buttons()[1]:
                    sleep_ms(10)

            # regular match processing (in case cascades happen)
            if ticks_diff(now, last_logic) >= logic_ms:
                last_logic = now
                # ensure no leftover matches
                self._remove_matches_and_score()

            if self._needs_redraw:
                self._render()

            maybe_collect(60)
            sleep_ms(8)

    async def main_loop_async(self, joystick):
        """Async version for pygbag: yields with asyncio.sleep()."""
        if asyncio is None:
            return self.main_loop(joystick)

        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        display.clear()
        last_logic = ticks_ms()
        logic_ms = 90
        self._needs_redraw = True

        while True:
            c_button, z_button = joystick.read_buttons()
            if c_button:
                global_score = self.score
                game_over = True
                return

            now = ticks_ms()
            d = joystick.read_direction(
                [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
            )
            if d and ticks_diff(now, self._last_move) >= self._move_delay:
                if d == JOYSTICK_UP:
                    self.cursor_y = max(0, self.cursor_y - 1)
                elif d == JOYSTICK_DOWN:
                    self.cursor_y = min(self.rows - 1, self.cursor_y + 1)
                elif d == JOYSTICK_LEFT:
                    self.cursor_x = max(0, self.cursor_x - 1)
                elif d == JOYSTICK_RIGHT:
                    self.cursor_x = min(self.cols - 1, self.cursor_x + 1)
                self._last_move = now
                self._needs_redraw = True

            if z_button and ticks_diff(now, last_logic) >= 0:
                # select or attempt swap
                if self.sel is None:
                    self.sel = (self.cursor_x, self.cursor_y)
                    self._needs_redraw = True
                else:
                    sx, sy = self.sel
                    cx, cy = self.cursor_x, self.cursor_y
                    if abs(sx - cx) + abs(sy - cy) == 1:
                        # adjacent -> try swap
                        self._swap_tiles((sx, sy), (cx, cy))
                        if self._find_matches():
                            # consume matches
                            self._remove_matches_and_score(delay_ms=0)
                        else:
                            # revert
                            self._swap_tiles((sx, sy), (cx, cy))
                        self.sel = None
                        self._needs_redraw = True
                    else:
                        # new selection
                        self.sel = (self.cursor_x, self.cursor_y)
                        self._needs_redraw = True
                # wait until released
                while joystick.read_buttons()[1]:
                    await asyncio.sleep(0.01)

            # regular match processing (in case cascades happen)
            if ticks_diff(now, last_logic) >= logic_ms:
                last_logic = now
                # ensure no leftover matches
                self._remove_matches_and_score(delay_ms=0)

            if self._needs_redraw:
                self._render()

            maybe_collect(60)
            await asyncio.sleep(0.008)


class CpuPlayerJoystick:
    """State-aware CPU controls for game attract demos."""
    def __init__(self, real_joystick, game_name, game, duration_ms=9000):
        self.real = real_joystick
        self.name = game_name
        self.game = game
        self.end_ms = ticks_ms() + duration_ms
        self._dir = None
        self._z = False
        self._last = 0
        self._pulse_until = 0
        self._script_i = 0

    def _exit_requested(self):
        c, z = self.real.read_buttons()
        if c or z or ticks_diff(ticks_ms(), self.end_ms) >= 0:
            return True
        d = self.real.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_UP, JOYSTICK_DOWN])
        return d is not None

    def _toward_x(self, x, target, dead=1):
        if x < target - dead:
            return JOYSTICK_RIGHT
        if x > target + dead:
            return JOYSTICK_LEFT
        return None

    def _toward_y(self, y, target, dead=1):
        if y < target - dead:
            return JOYSTICK_DOWN
        if y > target + dead:
            return JOYSTICK_UP
        return None

    def _pulse_z(self, ms=90):
        self._pulse_until = ticks_ms() + ms

    def _choose_2048_dir(self, g):
        dir_tokens = (JOYSTICK_UP, JOYSTICK_RIGHT, JOYSTICK_DOWN, JOYSTICK_LEFT)
        best_dir = JOYSTICK_DOWN
        best_score = -999999
        old_grid = list(g.grid)
        old_score = g.score
        old_moves = g.moves
        old_max = g.max_val
        old_victory = g.victory
        for idx, token in enumerate(dir_tokens):
            g.grid = list(old_grid)
            g.score = old_score
            g.moves = old_moves
            g.max_val = old_max
            g.victory = old_victory
            if not g._move(idx):
                continue
            empty = 0
            merge = 0
            smooth = 0
            for y in range(g.GRID_H):
                for x in range(g.GRID_W):
                    v = g.grid[g._idx(x, y)]
                    if not v:
                        empty += 1
                        continue
                    if x + 1 < g.GRID_W:
                        nv = g.grid[g._idx(x + 1, y)]
                        if nv == v:
                            merge += v
                        elif nv:
                            smooth -= abs(v - nv) // 2
                    if y + 1 < g.GRID_H:
                        nv = g.grid[g._idx(x, y + 1)]
                        if nv == v:
                            merge += v
                        elif nv:
                            smooth -= abs(v - nv) // 2
            corner = max(g.grid[g._idx(0, g.GRID_H - 1)], g.grid[g._idx(g.GRID_W - 1, g.GRID_H - 1)])
            score = empty * 900 + merge * 6 + corner * 3 + smooth + (60 if token in (JOYSTICK_DOWN, JOYSTICK_LEFT) else 0)
            if score > best_score:
                best_score = score
                best_dir = token
        g.grid = old_grid
        g.score = old_score
        g.moves = old_moves
        g.max_val = old_max
        g.victory = old_victory
        return best_dir

    def _choose_tetris_dir(self, g):
        piece = g.current
        best_x = piece.x
        best_rot = piece.shape
        best_score = -999999
        rotations = []
        shape = piece.shape
        for _ in range(4):
            if shape not in rotations:
                rotations.append(shape)
            shape = tuple(tuple(row) for row in zip(*shape[::-1]))
        old_shape = piece.shape
        for shape in rotations:
            width = len(shape[0])
            for x in range(0, g.GRID_WIDTH - width + 1):
                y = piece.y
                while g.valid(piece, dx=x - piece.x, dy=(y + 1) - piece.y, rotated_shape=shape):
                    y += 1
                landing = y
                holes = 0
                heights = [0] * g.GRID_WIDTH
                tmp = bytearray(g.locked)
                for yy, row in enumerate(shape):
                    for xx, cell in enumerate(row):
                        if cell and 0 <= landing + yy < g.GRID_HEIGHT:
                            tmp[(landing + yy) * g.GRID_WIDTH + x + xx] = 1
                for cx in range(g.GRID_WIDTH):
                    seen = False
                    for cy in range(g.GRID_HEIGHT):
                        if tmp[cy * g.GRID_WIDTH + cx]:
                            if not seen:
                                heights[cx] = g.GRID_HEIGHT - cy
                            seen = True
                        elif seen:
                            holes += 1
                bump = 0
                for i in range(g.GRID_WIDTH - 1):
                    bump += abs(heights[i] - heights[i + 1])
                score = landing * 12 - holes * 80 - bump * 5 - max(heights) * 2
                if score > best_score:
                    best_score = score
                    best_x = x
                    best_rot = shape
        if old_shape != best_rot:
            self._pulse_z(80)
            return None
        if piece.x < best_x:
            return JOYSTICK_RIGHT
        if piece.x > best_x:
            return JOYSTICK_LEFT
        return JOYSTICK_DOWN

    def _safe_frogger_dir(self, g):
        moves = (JOYSTICK_UP, JOYSTICK_LEFT, JOYSTICK_RIGHT, None)
        best = None
        best_score = -99999
        for d in moves:
            dx, dy = direction_to_delta(d) if d else (0, 0)
            px = clamp(g.player_x + dx * 4, 0, WIDTH - g.PLAYER_W)
            py = clamp(g.player_y + dy * 4, 0, PLAY_HEIGHT - g.PLAYER_H)
            risk = 0
            for lane in g.lanes:
                y = lane[0]
                for car in lane[2]:
                    cx = int(car[0] + lane[1] * 4)
                    if rects_overlap(px, py, g.PLAYER_W, g.PLAYER_H, cx - 1, y, int(car[1]) + 2, 3):
                        risk += 1000
            score = (PLAY_HEIGHT - py) * 10 - risk - abs(px - WIDTH // 2)
            if score > best_score:
                best_score = score
                best = d
        return best

    def _compute(self):
        now = ticks_ms()
        if ticks_diff(now, self._last) < 55:
            self._z = ticks_diff(self._pulse_until, now) > 0
            return
        self._last = now
        g = self.game
        n = self.name
        d = None

        if hasattr(g, "ball_x") and hasattr(g, "paddle_x"):
            target = float(g.ball_x)
            if getattr(g, "ball_dy", 0) > 0:
                target = float(g.ball_x)
                vx = float(getattr(g, "ball_dx", 0))
                vy = float(getattr(g, "ball_dy", 1))
                y = float(g.ball_y)
                while y < g.paddle_y and 0 <= target <= WIDTH - 2:
                    target += vx
                    y += vy
                    if target <= 0 or target >= WIDTH - 2:
                        vx = -vx
            else:
                bricks = getattr(g, "bricks", None)
                if bricks:
                    target = min(bricks, key=lambda b: abs((b[0] + BRICK_WIDTH // 2) - g.ball_x))[0] + BRICK_WIDTH // 2
            d = self._toward_x(g.paddle_x + PADDLE_WIDTH // 2, int(target), 1)
        elif hasattr(g, "ball_position") and hasattr(g, "left_paddle_y"):
            target = int(g.ball_position[1])
            if g.ball_speed[0] < 0:
                y = float(g.ball_position[1])
                vy = float(g.ball_speed[1])
                x = float(g.ball_position[0])
                while x > g.left_paddle_x + 1:
                    x += g.ball_speed[0]
                    y += vy
                    if y <= 0 or y >= PLAY_HEIGHT - 1:
                        vy = -vy
                        y = clamp(y, 0, PLAY_HEIGHT - 1)
                target = int(y)
            d = self._toward_y(g.left_paddle_y + g.paddle_height // 2, target, 1)
        elif n == "STACK" and hasattr(g, "bar_x"):
            target = getattr(g, "prev_x", 0)
            if abs(g.bar_x - target) <= max(1, getattr(g, "speed", 1)):
                self._pulse_z(80)
        elif n == "FLAPPY" and hasattr(g, "pipes"):
            target = PLAY_HEIGHT // 2
            for p in g.pipes:
                if p["x"] + g.pipe_w >= g.bx - 1:
                    target = p["gy"] - 2
                    break
            if g.by + max(0, g.vy) > target:
                self._pulse_z(80)
            d = JOYSTICK_UP if ticks_diff(self._pulse_until, now) > 0 else None
        elif n == "FROGGR" and hasattr(g, "lanes"):
            d = self._safe_frogger_dir(g)
        elif n == "INVADR" and hasattr(g, "aliens"):
            live = [a for a in g.aliens if a[2]]
            bottom = []
            for a in live:
                col = (a[0] - 1) // 7
                if not any(o[2] and ((o[0] - 1) // 7) == col and o[1] > a[1] for o in live):
                    bottom.append(a)
            target = min(bottom or live, key=lambda a: abs((a[0] + 2) - g.player_x))[0] + 2 if live else WIDTH // 2
            for bomb in getattr(g, "bombs", []):
                if bomb[1] > PLAY_HEIGHT - 18 and abs(bomb[0] - g.player_x) < 5:
                    target = 2 if g.player_x > WIDTH // 2 else WIDTH - 3
            d = self._toward_x(g.player_x, target, 1)
            if abs(g.player_x - target) <= 2 and g.bullet is None:
                self._pulse_z(80)
        elif n == "ASTRD" and hasattr(g, "asteroids"):
            if g.asteroids:
                ship = g.ship
                a = min(g.asteroids, key=lambda aa: (aa.x - ship.x) ** 2 + (aa.y - ship.y) ** 2)
                target = (math.degrees(math.atan2(-(a.y - ship.y), a.x - ship.x)) + 360) % 360
                delta = ((target - ship.angle + 180) % 360) - 180
                if abs(delta) < 18:
                    self._pulse_z(90)
                    d = JOYSTICK_UP
                elif delta > 0:
                    d = JOYSTICK_LEFT
                else:
                    d = JOYSTICK_RIGHT
        elif n == "TRON" and hasattr(g, "_clear_distance_from"):
            cur = g.direction
            left = g._LEFT_TURN[cur]
            right = g._RIGHT_TURN[cur]
            options = ((g._clear_distance_from(g.head_x, g.head_y, cur), None),
                       (g._clear_distance_from(g.head_x, g.head_y, left), JOYSTICK_LEFT),
                       (g._clear_distance_from(g.head_x, g.head_y, right), JOYSTICK_RIGHT))
            d = max(options, key=lambda item: item[0])[1]
        elif n == "DOOMLT" and hasattr(g, "enemies"):
            alive = [e for e in g.enemies if e[2] > 0]
            if alive:
                e = min(alive, key=lambda ee: (ee[0] - g.px) ** 2 + (ee[1] - g.py) ** 2)
                target = g._angle_to_units(e[0] - g.px, e[1] - g.py)
                delta = g._angle_delta(target, g.ang)
                if abs(delta) <= 5:
                    self._pulse_z(90)
                    d = JOYSTICK_UP
                else:
                    d = JOYSTICK_LEFT if delta > 0 else JOYSTICK_RIGHT
            else:
                d = JOYSTICK_UP
        elif n == "RAYRCR" and hasattr(g, "objects"):
            target = 0.0
            for obj in g.objects:
                rel = obj[0] - g.pos
                if 4.0 < rel < 32.0:
                    lane = g._object_lane(obj)
                    if obj[2] == 2:
                        target = lane
                        break
                    if abs(g.lane - lane) < 0.48:
                        target = -0.78 if lane > 0 else 0.78
                        break
            if g.lane < target - 0.10:
                d = JOYSTICK_UP_RIGHT
            elif g.lane > target + 0.10:
                d = JOYSTICK_UP_LEFT
            else:
                d = JOYSTICK_UP
            self._dir = d
            self._z = bool(getattr(g, "energy", 0) > 28 and getattr(g, "speed", 0) > 0.75 and abs(g.lane) < 0.88)
            return
        elif n == "2048" and hasattr(g, "grid"):
            # Keep the board biased toward one corner, the standard simple 2048 CPU.
            d = self._choose_2048_dir(g)
        elif n == "TETRIS" and hasattr(g, "current"):
            d = self._choose_tetris_dir(g)
        elif hasattr(g, "cur_x") and hasattr(g, "cur_y"):
            script = (JOYSTICK_RIGHT, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_UP)
            self._script_i = (self._script_i + 1) & 31
            d = script[(self._script_i >> 3) & 3]
            if (self._script_i & 15) == 0:
                self._pulse_z(70)
        elif hasattr(g, "px") and hasattr(g, "py") and hasattr(g, "_try_move"):
            # Sokoban-like previews: walk the level and occasionally push/undo.
            script = (JOYSTICK_RIGHT, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_UP)
            self._script_i = (self._script_i + 1) & 31
            d = script[(self._script_i >> 3) & 3]
        else:
            script = (JOYSTICK_LEFT, JOYSTICK_UP, JOYSTICK_RIGHT, JOYSTICK_DOWN)
            self._script_i = (self._script_i + 1) & 31
            d = script[(self._script_i >> 3) & 3]
            if (self._script_i & 7) == 0:
                self._pulse_z(70)

        self._dir = d
        self._z = ticks_diff(self._pulse_until, now) > 0

    def read_buttons(self):
        if self._exit_requested():
            return True, False
        self._compute()
        return False, self._z

    def read_direction(self, possible_directions, debounce=True):
        if self._exit_requested():
            return None
        self._compute()
        if self._dir in possible_directions:
            return self._dir
        return None

    def is_pressed(self):
        return self.read_buttons()[1]


class DemosGame:
    """
    DEMOS
    Controls:
      - Left / Right: switch demo
      - C: return to menu
    """
    FRAME_MS = 35
    GAME_DEMOS = (
        "2048", "ARENA", "ARTILL", "ASTRD", "BEJWL", "BOMBER", "BRKOUT", "BTLZON",
        "CAVEFL", "CENTI", "CGOLG", "CLIMB", "COLMNS", "DEFUSE",
        "DOOMLT", "FLAPPY", "FROGGR", "GALAXY", "GOLF", "INVADR",
        "KEEN", "LANDER", "LASER", "LOCO", "MAZE", "MINES", "ORBIT", "ORBTAL", "PACMAN",
        "PAIRS", "PINBAL", "PITFAL", "PONG", "QIX", "RAYRCR", "REVRS", "RTYPE",
        "SABOTR", "SIMON", "SNAKE", "SOCCER", "SOKO", "STACK", "TETRIS", "TRON", "TWRDEF",
        "STKARC", "UFODEF", "AIRHKY",
    )
    GAME_CLASS_NAMES = {
        "2048": "Game2048",
        "ARENA": "ArenaGame",
        "ARTILL": "ArtilleryGame",
        "ASTRD": "AsteroidGame",
        "BEJWL": "BejeweledGame",
        "BOMBER": "BomberGame",
        "BRKOUT": "BreakoutGame",
        "BTLZON": "BattlezoneGame",
        "CAVEFL": "CaveFlyGame",
        "CENTI": "CentipedeGame",
        "CGOLG": "CgolgGame",
        "CLIMB": "ClimberGame",
        "COLMNS": "ColumnsGame",
        "DEFUSE": "DefuseGame",
        "DOOMLT": "DoomLiteGame",
        "FLAPPY": "FlappyGame",
        "FROGGR": "FroggerGame",
        "GALAXY": "GalaxyGame",
        "GOLF": "GolfGame",
        "INVADR": "InvaderGame",
        "KEEN": "KeenGame",
        "LANDER": "LunarLanderGame",
        "LASER": "LaserGame",
        "LOCO": "LocoMotionGame",
        "MAZE": "MazeGame",
        "MINES": "MinesGame",
        "ORBIT": "OrbitGame",
        "ORBTAL": "OrbitalGame",
        "PACMAN": "PacmanGame",
        "PAIRS": "PairsGame",
        "PINBAL": "PinballGame",
        "PITFAL": "PitfallGame",
        "PONG": "PongGame",
        "AIRHKY": "AirHockeyGame",
        "QIX": "QixGame",
        "RAYRCR": "RayRacerGame",
        "REVRS": "OthelloGame",
        "RTYPE": "RTypeGame",
        "SABOTR": "SabotrGame",
        "SIMON": "SimonGame",
        "SNAKE": "SnakeGame",
        "SOCCER": "SoccerGame",
        "SOKO": "SokobanGame",
        "STACK": "StackerGame",
        "STKARC": "StickArcherGame",
        "TETRIS": "TetrisGame",
        "TRON": "TronGame",
        "TWRDEF": "TowerDefenseGame",
        "UFODEF": "UFODefenseGame",
    }

    def __init__(self, ctx=None):
        self.slideshow_ms = int(get_context_setting(ctx, "slide_ms", 60000) or 60000)
        self.random_order = get_context_setting(ctx, "order", "sorted") == "random"
        self.clock_enabled = bool(get_context_setting(ctx, "clock", False))
        self.clock_source = get_context_setting(ctx, "clock_source", "rtc")
        self.clock_hour = int(get_context_setting(ctx, "clock_hour", 12) or 0) % 24
        self.clock_minute = int(get_context_setting(ctx, "clock_minute", 0) or 0) % 60
        self._clock_start_ms = ticks_ms()
        # Generated demo registry. GAME_DEMOS above contains CPU-played game
        # previews; this list contains effects implemented directly in
        # DemosGame. To add an effect: list it here, reset its state in
        # _reset_demo_state(), and dispatch init/step below. The low-RAM subset
        # avoids larger buffers and dense per-pixel math.
        effects = (
            ("SNAKE", "LIFE", "CUBE", "VORTEX", "COMETS", "SPARK", "RINGS", "GRAV", "SPRING", "CRADLE")
            if CONFIG_LOW_RAM_MODE
            else ("SNAKE", "PLASMA", "CUBE", "ORBIT", "WARP", "BOUNCE",
                  "VORTEX", "COMETS",
                  "TUNNEL", "MYSTIFY", "LIFE", "ANTS", "FLOOD", "FIRE",
                  "MATRIX", "STARS", "SPARK", "RINGS", "RADAR", "MANDEL",
                  "BOIDS", "NBODY", "METAB", "GRAV", "RIPPLE", "FIRWRK",
                  "SPRING", "CRADLE",
                  "PHYLLO", "LISSAJO", "PENDUL", "ARCADE", "CRT", "WINMAZE")
        )
        effects = tuple(
            name for name in effects
            if _name_enabled(name, CONFIG_ENABLED_DEMOS, CONFIG_DISABLED_DEMOS)
        )
        game_demos = tuple(
            "G:" + name for name in self.GAME_DEMOS
            if _name_enabled("G:" + name, CONFIG_ENABLED_DEMOS, CONFIG_DISABLED_DEMOS)
            and _name_enabled(name, CONFIG_ENABLED_GAMES, CONFIG_DISABLED_GAMES)
        )

        self.demos = (
            game_demos + effects
            if CONFIG_ENABLE_GAME_DEMOS
            else effects
        )
        self.idx = 0
        if self.random_order and len(self.demos) > 1:
            self.idx = random.randint(0, len(self.demos) - 1)
        self._init = False
        self._last_move = ticks_ms()
        self._slide_started_ms = self._last_move
        self._move_delay = 180
        self._game_demo_wait_ms = 850
        self._reset_demo_state()

    def _demo_clock_text(self):
        if not self.clock_enabled:
            return None
        if self.clock_source == "rtc":
            try:
                year, month, day, weekday, hour, minute, second, _ = rtc.datetime()
                return "{:02}:{:02}".format(hour, minute)
            except Exception:
                pass
        elapsed_min = max(0, ticks_diff(ticks_ms(), self._clock_start_ms) // 60000)
        total = (self.clock_hour * 60 + self.clock_minute + elapsed_min) % (24 * 60)
        return "{:02}:{:02}".format(total // 60, total % 60)

    def _draw_clock_overlay(self):
        txt = self._demo_clock_text()
        if not txt:
            return
        x = WIDTH - len(txt) * 6 - 1
        draw_rectangle(x - 1, 0, WIDTH - 1, 6, 0, 0, 0)
        draw_text_small(x, 1, txt, 230, 230, 230)

    def _demo_disc(self, cx, cy, radius, color):
        r2 = radius * radius
        x0 = int(cx - radius)
        x1 = int(cx + radius)
        y0 = int(cy - radius)
        y1 = int(cy + radius)
        for yy in range(y0, y1 + 1):
            if yy < 0 or yy >= HEIGHT:
                continue
            dy = yy - cy
            for xx in range(x0, x1 + 1):
                if xx < 0 or xx >= WIDTH:
                    continue
                dx = xx - cx
                if dx * dx + dy * dy <= r2:
                    set_pixel_clipped(xx, yy, color[0], color[1], color[2])

    def _reset_demo_state(self):
        # shared
        self._init = False
        self._frame = 0
        self._demo_w = WIDTH
        self._demo_h = HEIGHT

        # LIFE (2x2 scaled)
        self._life_w = 32
        self._life_h = 32
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
        self._flood_max_steps = 4000  # scaled from 16000 @ 128x128

        # FIRE (doom-fire)
        self._fire_w = WIDTH
        self._fire_h = HEIGHT
        self._fire = None
        self._fire_prev = None

        # MATRIX (falling green rain)
        self._matrix_drops = []
        
        # STARS (3d starfield)
        self._stars = []
        
        # MYSTIFY (bouncing polygons/lines)
        self._mystify_pts = []
        self._mystify_history = []
        self._mystify_hue = 0.0
        
        # PLASMA effect
        self._plasma_time = 0
        self._plasma_palette = []
        self._plasma_sin = []

        # TUNNEL
        self._tunnel_phase = 0

        # ORBIT
        self._orbit_phase = 0

        # WARP
        self._warp_stars = []
        self._warp_phase = 0

        # VORTEX
        self._vortex_phase = 0

        # COMETS
        self._comets = []

        # BOUNCE
        self._bounce_x = 0
        self._bounce_y = 0
        self._bounce_dx = 1
        self._bounce_dy = 1
        self._bounce_hue = 0

        # SNAKE
        self._snake = [(WIDTH // 2, HEIGHT // 2)]
        self._snake_length = 3
        self._snake_dir = 'UP'
        self._snake_score = 0
        self._snake_target = (WIDTH // 2, HEIGHT // 2)
        self._snake_green_targets = []  # list of (x,y,lifespan)
        self._snake_step_counter = 0
        self._snake_step_counter2 = 0

        # SPARK
        self._spark_particles = []

        # RINGS
        self._rings_phase = 0

        # RADAR
        self._radar_phase = 0
        self._radar_blips = []

        # MANDEL
        self._mandel_y = 0
        self._mandel_pass = 0
        self._mandel_palette = []
        self._mandel_xs = []
        self._mandel_params = None

        # BOIDS
        self._boids = []

        # NBODY
        self._nbody = []

        # METAB: moving influence points sampled on a 2x2 grid, giving a
        # liquid/metaball look without framebuffer readback or alpha blending.
        self._metab_balls = []
        self._metab_phase = 0

        # GRAV: compact particle state integrated around two moving attractors.
        self._grav_particles = []
        self._grav_phase = 0

        # SPRING: a dangling spring-mass chain with gravity and damping.
        self._spring_nodes = []
        self._spring_phase = 0
        self._spring_rest = 0.0

        # CRADLE: Newton's cradle with string constraints and elastic transfer.
        self._cradle_bobs = []
        self._cradle_phase = 0
        self._cradle_length = 0.0

        # RIPPLE: integer water height-field (two buffers) at half resolution,
        # rendered as 2x2 blocks. Raindrops perturb the field periodically.
        self._ripple_w = 32
        self._ripple_h = 32
        self._ripple_cur = None
        self._ripple_prev = None

        # FIRWRK: rising rockets that burst into gravity-bound spark showers.
        self._fw_rockets = []
        self._fw_particles = []

        # PHYLLO: golden-angle phyllotaxis spiral (sunflower seed packing).
        self._phyllo_phase = 0.0

        # LISSAJO: oscilloscope Lissajous curve with drifting frequency ratio.
        self._liss_phase = 0.0

        # PENDUL: chaotic double pendulum with a fading tip trail.
        self._pend_a1 = 0.0
        self._pend_a2 = 0.0
        self._pend_w1 = 0.0
        self._pend_w2 = 0.0
        self._pend_trail = []

        # ARCADE: self-playing Breakout attract demo.
        self._arc_bricks = None
        self._arc_ball = None
        self._arc_paddle = 0.0
        self._arc_game = None
        self._arc_cpu = None

        # CRT
        self._crt_phase = 0

        # WINMAZE
        self._winmaze = None
        self._winmaze_dir = 0
        self._winmaze_target_ang = 0
        self._winmaze_path_phase = 0

        self._game_demo_name = None
        self._game_demo_selected_ms = 0
        self._last_sound_ms = 0

    def _demo_sound(self, kind, tone=0, min_gap_ms=90):
        now = ticks_ms()
        if ticks_diff(now, self._last_sound_ms) < min_gap_ms:
            return
        self._last_sound_ms = now
        play_web_sound(kind, tone)

    def _life_step(self, w, h, cur, nxt):
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
                    cur[rowm1 + xm1] + cur[rowm1 + x] + cur[rowm1 + xp1] +
                    cur[row + xm1] + cur[row + xp1] +
                    cur[rowp1 + xm1] + cur[rowp1 + x] + cur[rowp1 + xp1]
                )
                if cur[i]:
                    nxt[i] = 1 if (n == 2 or n == 3) else 0
                else:
                    nxt[i] = 1 if (n == 3) else 0

    def _life_draw_diffs(self, w, h, cur, prev):
        # diff-draw at 2x2 scale (no full clear)
        for y in range(h):
            row = y * w
            for x in range(w):
                i = row + x
                v = cur[i]
                if v == prev[i]:
                    continue
                prev[i] = v
                px = x * 2
                py = y * 2
                if py >= HEIGHT:
                    continue
                if v:
                    r, g, b = 0, 180, 0
                else:
                    r, g, b = 0, 0, 0
                display.set_pixel(px, py, r, g, b)
                if px + 1 < WIDTH:
                    display.set_pixel(px + 1, py, r, g, b)
                if py + 1 < HEIGHT:
                    display.set_pixel(px, py + 1, r, g, b)
                    if px + 1 < WIDTH:
                        display.set_pixel(px + 1, py + 1, r, g, b)

    def _ants_init(self):
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
        step = 4      # 8 @ 128 scaled to 64

        # Start near center like reference
        sx = random.randint(border // 2, min(w - 2, w - border // 2))
        sy = random.randint(border // 2, min(h - 2, h - border // 2))

        # Fixed-size stack for DFS nodes (step grid is about (w/step)*(h/step)).
        max_nodes = (w // step) * (h // step)
        stack = bytearray(max_nodes * 2)
        sp = 0

        def stack_push(v):
            nonlocal sp
            stack[sp] = v & 0xFF
            stack[sp + 1] = (v >> 8) & 0xFF
            sp += 2

        def stack_top():
            return stack[sp - 2] | (stack[sp - 1] << 8)

        def stack_pop():
            nonlocal sp
            sp -= 2

        def mark_line(px, py, v=1):
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

            dir_order = [0, 1, 2, 3]
            _shuffle_in_place(dir_order)

            found = False
            for di in dir_order:
                dx, dy = dirs[di]
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

    # --- MATRIX ---
    def _matrix_init(self):
        w = self._demo_w
        self._matrix_drops = []
        for _ in range(12):
            self._matrix_drops.append({
                'x': random.randint(0, w - 1),
                'y': random.randint(-20, 0),
                'speed': random.randint(1, 3),
                'len': random.randint(4, 12)
            })
        display.clear()

    def _matrix_step(self):
        w = self._demo_w
        h = self._demo_h
        
        # darken screen
        for y in range(h):
            for x in range(w):
                # We can't directly read pixels from software buffer easily in all configs.
                # Just draw black with alpha effect conceptually.
                pass
                
        # Better matrix approach without reading buffer:
        # Just clear screen occasionally or redraw tails in black
        for drop in self._matrix_drops:
            # Erase tail
            ty = drop['y'] - drop['len']
            if 0 <= ty < h:
                display.set_pixel(drop['x'], ty, 0, 0, 0)
                
            # Move
            if self._frame % drop['speed'] == 0:
                drop['y'] += 1
                
            # Draw head
            if 0 <= drop['y'] < h:
                # White head
                display.set_pixel(drop['x'], drop['y'], 200, 255, 200)
                
            # Draw body (dim green)
            by = drop['y'] - 1
            if 0 <= by < h:
                display.set_pixel(drop['x'], by, 0, 200, 0)
                
            by = drop['y'] - 2
            if 0 <= by < h:
                display.set_pixel(drop['x'], by, 0, 100, 0)
                
            by = drop['y'] - 3
            if 0 <= by < h:
                display.set_pixel(drop['x'], by, 0, 50, 0)
                
            # Reset
            if drop['y'] - drop['len'] > h:
                drop['x'] = random.randint(0, w - 1)
                drop['y'] = random.randint(-10, 0)
                drop['speed'] = random.randint(1, 3)
                drop['len'] = random.randint(4, 12)

    # --- STARS ---
    def _stars_init(self):
        w = self._demo_w
        h = self._demo_h
        self._stars = []
        for _ in range(40):
            # x, y, z
            self._stars.append([
                random.uniform(-1, 1),
                random.uniform(-1, 1),
                random.uniform(0.1, 2.0)
            ])
        display.clear()

    def _stars_step(self):
        w = self._demo_w
        h = self._demo_h
        cx, cy = w // 2, h // 2
        
        # Erase old
        for s in self._stars:
            pz = s[2]
            if pz > 0.01:
                px = int(s[0] / pz * cx + cx)
                py = int(s[1] / pz * cy + cy)
                if 0 <= px < w and 0 <= py < h:
                    display.set_pixel(px, py, 0, 0, 0)
                    
            # Move
            s[2] -= 0.05
            
            # Reset if passed screen
            if s[2] < 0.05:
                s[0] = random.uniform(-1, 1)
                s[1] = random.uniform(-1, 1)
                s[2] = 2.0
                
            # Draw new
            nz = s[2]
            nx = int(s[0] / nz * cx + cx)
            ny = int(s[1] / nz * cy + cy)
            
            if 0 <= nx < w and 0 <= ny < h:
                bright = int(255 * (1.0 - nz/2.0))
                if bright < 0: bright = 0
                if bright > 255: bright = 255
                display.set_pixel(nx, ny, bright, bright, bright)
                
    # --- MYSTIFY ---
    def _mystify_init(self):
        self._mystify_pts = []
        for _ in range(4): # 4 points forming our shape
            self._mystify_pts.append({
                'x': float(random.randint(0, WIDTH-1)),
                'y': float(random.randint(0, HEIGHT-1)),
                'vx': random.choice([-1.5, -1.0, 1.0, 1.5]),
                'vy': random.choice([-1.5, -1.0, 1.0, 1.5])
            })
        self._mystify_history = []
        self._mystify_hue = random.randint(0, 360)
        display.clear()

    def _mystify_draw_poly(self, pts, r, g, b):
        for i in range(len(pts)):
            p1 = pts[i]
            p2 = pts[(i + 1) % len(pts)]
            draw_line(int(p1['x']), int(p1['y']), int(p2['x']), int(p2['y']), r, g, b)

    def _mystify_step(self):
        # Add current to history
        current_state = [{'x': p['x'], 'y': p['y']} for p in self._mystify_pts]
        self._mystify_history.append(current_state)
        
        # Erase oldest if history too long (max 8 trailing lines)
        if len(self._mystify_history) > 8:
            oldest = self._mystify_history.pop(0)
            self._mystify_draw_poly(oldest, 0, 0, 0)
            
        # Move points
        for p in self._mystify_pts:
            p['x'] += p['vx']
            p['y'] += p['vy']
            
            # Bounce
            if p['x'] <= 0:
                p['x'] = 0
                p['vx'] *= -1
            elif p['x'] >= WIDTH - 1:
                p['x'] = WIDTH - 1
                p['vx'] *= -1
                
            if p['y'] <= 0:
                p['y'] = 0
                p['vy'] *= -1
            elif p['y'] >= HEIGHT - 1:
                p['y'] = HEIGHT - 1
                p['vy'] *= -1
                
        # Draw new
        self._mystify_hue = (self._mystify_hue + 1.5) % 360
        r, g, b = hsb_to_rgb(self._mystify_hue, 1, 1)
        self._mystify_draw_poly(self._mystify_pts, r, g, b)

    # --- CUBE (3D Wireframe) ---
    def _cube_init(self):
        self._cube_angle_x = 0.0
        self._cube_angle_y = 0.0
        self._cube_angle_z = 0.0
        self._cube_pulse = 0.0
        # 8 vertices of a cube
        self._cube_vertices = [
            (-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
            (-1, -1, 1),  (1, -1, 1),  (1, 1, 1),  (-1, 1, 1)
        ]
        # 12 edges (pairs of vertex indices)
        self._cube_edges = [
            (0, 1), (1, 2), (2, 3), (3, 0), # Back face
            (4, 5), (5, 6), (6, 7), (7, 4), # Front face
            (0, 4), (1, 5), (2, 6), (3, 7)  # Connecting faces
        ]
        self._cube_hue = 0.0
        display.clear()

    def _cube_step(self):
        display.clear()
        
        # Increment angles
        self._cube_angle_x += 0.05
        self._cube_angle_y += 0.03
        self._cube_angle_z += 0.02
        self._cube_pulse += 0.065
        self._cube_hue = (self._cube_hue + 2) % 360
        pulse_scale = 8.5 + math.sin(self._cube_pulse) * 3.5
        
        # Precompute sin/cos
        sx, cx = math.sin(self._cube_angle_x), math.cos(self._cube_angle_x)
        sy, cy = math.sin(self._cube_angle_y), math.cos(self._cube_angle_y)
        sz, cz = math.sin(self._cube_angle_z), math.cos(self._cube_angle_z)
        
        projected = []
        for x, y, z in self._cube_vertices:
            # Rotate X
            y1 = y * cx - z * sx
            z1 = y * sx + z * cx
            # Rotate Y
            x2 = x * cy + z1 * sy
            z2 = -x * sy + z1 * cy
            # Rotate Z
            x3 = x2 * cz - y1 * sz
            y3 = x2 * sz + y1 * cz
            
            # Projection (scale and center)
            scale = 16 / (z2 + 3) # Perspective divide
            px = int(WIDTH // 2 + x3 * scale * pulse_scale)
            py = int(HEIGHT // 2 + y3 * scale * pulse_scale)
            projected.append((px, py))
            
        # Draw edges
        r, g, b = hsb_to_rgb(self._cube_hue, 1, 1)
        for i, j in self._cube_edges:
            x1, y1 = projected[i]
            x2, y2 = projected[j]
            draw_line(x1, y1, x2, y2, r, g, b)

    # --- TUNNEL ---
    def _tunnel_init(self):
        self._tunnel_phase = 0
        display.clear()

    def _tunnel_step(self):
        display.clear()
        self._tunnel_phase = (self._tunnel_phase + 1) & 255
        phase = self._tunnel_phase
        cx = WIDTH // 2 + int(math.sin(phase * 0.07) * 7)
        cy = HEIGHT // 2 + int(math.cos(phase * 0.05) * 5)

        for i in range(9):
            depth = ((phase * 2) + i * 16) & 127
            size = 4 + depth // 2
            if size > 38:
                continue
            skew = int(math.sin((phase + i * 13) * 0.09) * 5)
            x1 = cx - size + skew
            y1 = cy - size
            x2 = cx + size - skew
            y2 = cy + size
            hue = (phase * 3 + i * 31) % 360
            r, g, b = hsb_to_rgb(hue, 1, 1)
            draw_line(x1, y1, x2, y1, r, g, b)
            draw_line(x2, y1, x2, y2, r, g, b)
            draw_line(x2, y2, x1, y2, r, g, b)
            draw_line(x1, y2, x1, y1, r, g, b)

    # --- ORBIT ---
    def _orbit_init(self):
        self._orbit_phase = 0
        display.clear()

    def _orbit_step(self):
        display.clear()
        self._orbit_phase = (self._orbit_phase + 3) % 360
        phase = self._orbit_phase
        cx = WIDTH // 2
        cy = HEIGHT // 2

        for ring in range(4):
            radius = 7 + ring * 6
            hue = (phase * 2 + ring * 70) % 360
            r, g, b = hsb_to_rgb(hue, 1, 1)
            points = 6 + ring * 2
            for i in range(points):
                a = (phase + i * (360 // points) + ring * 19) * 3.14159 / 180.0
                wobble = math.sin((phase + i * 23) * 0.07) * 2.5
                x = int(cx + math.cos(a) * (radius + wobble))
                y = int(cy + math.sin(a) * (radius - wobble))
                draw_rectangle(x - 1, y - 1, x + 1, y + 1, r, g, b)

        draw_rectangle(cx - 2, cy - 2, cx + 2, cy + 2, 255, 255, 255)

    # --- WARP ---
    def _warp_init(self):
        self._warp_phase = 0
        self._warp_stars = []
        for _ in range(28):
            angle = random.randint(0, 359) * 3.14159 / 180.0
            radius = random.randint(1, 26)
            speed = random.randint(2, 5)
            self._warp_stars.append([angle, radius, speed])
        display.clear()

    def _warp_step(self):
        display.clear()
        self._warp_phase = (self._warp_phase + 1) & 255
        cx = WIDTH // 2 + int(math.sin(self._warp_phase * 0.05) * 3)
        cy = HEIGHT // 2 + int(math.cos(self._warp_phase * 0.04) * 3)
        for star in self._warp_stars:
            a = star[0]
            old_r = star[1]
            star[1] += star[2]
            if star[1] > 46:
                star[0] = random.randint(0, 359) * 3.14159 / 180.0
                star[1] = random.randint(1, 5)
                star[2] = random.randint(2, 5)
                old_r = 1
                a = star[0]

            x0 = int(cx + math.cos(a) * old_r)
            y0 = int(cy + math.sin(a) * old_r)
            x1 = int(cx + math.cos(a) * star[1])
            y1 = int(cy + math.sin(a) * star[1])
            hue = (self._warp_phase * 4 + int(star[1]) * 6) % 360
            r, g, b = hsb_to_rgb(hue, 0.8, 1)
            draw_line(x0, y0, x1, y1, r, g, b)

    # --- VORTEX ---
    def _vortex_init(self):
        self._vortex_phase = random.randint(0, 255)
        display.clear()

    def _vortex_step(self):
        display.clear()
        self._vortex_phase = (self._vortex_phase + 3) & 255
        phase = self._vortex_phase
        cx = WIDTH // 2 + int(math.sin(phase * 0.041) * 4)
        cy = HEIGHT // 2 + int(math.cos(phase * 0.037) * 4)
        for arm in range(14):
            hue = (phase * 3 + arm * 25) % 360
            r, g, b = hsb_to_rgb(hue, 1, 1)
            for step in range(2, 31, 4):
                a = phase * 0.035 + arm * 0.58 + step * 0.09
                radius = step + math.sin(phase * 0.05 + arm) * 2.0
                x = int(cx + math.cos(a) * radius)
                y = int(cy + math.sin(a) * radius)
                px = int(cx + math.cos(a - 0.23) * (radius - 3))
                py = int(cy + math.sin(a - 0.23) * (radius - 3))
                draw_line(px, py, x, y, r, g, b)

    # --- COMETS ---
    def _comets_init(self):
        self._comets = []
        count = 9 if not CONFIG_LOW_RAM_MODE else 5
        for i in range(count):
            self._comets.append([0.0, 0.0, 0.0, 0.0, (i * 43) % 360, 0])
            self._comet_respawn(self._comets[-1], i)
        display.clear()

    def _comet_respawn(self, comet, seed=0):
        edge = random.randint(0, 3)
        if edge == 0:
            comet[0] = float(random.randint(0, WIDTH - 1))
            comet[1] = 0.0
        elif edge == 1:
            comet[0] = float(WIDTH - 1)
            comet[1] = float(random.randint(0, HEIGHT - 1))
        elif edge == 2:
            comet[0] = float(random.randint(0, WIDTH - 1))
            comet[1] = float(HEIGHT - 1)
        else:
            comet[0] = 0.0
            comet[1] = float(random.randint(0, HEIGHT - 1))
        target_x = WIDTH // 2 + random.randint(-12, 12)
        target_y = HEIGHT // 2 + random.randint(-12, 12)
        dx = target_x - comet[0]
        dy = target_y - comet[1]
        dist = math.sqrt(dx * dx + dy * dy) or 1.0
        speed = 0.75 + random.randint(0, 8) * 0.08
        comet[2] = dx / dist * speed
        comet[3] = dy / dist * speed
        comet[4] = (self._frame * 3 + seed * 41 + random.randint(0, 45)) % 360
        comet[5] = random.randint(36, 82)

    def _comets_step(self):
        display.clear()
        for i, comet in enumerate(self._comets):
            comet[0] += comet[2]
            comet[1] += comet[3]
            comet[5] -= 1
            x = int(comet[0])
            y = int(comet[1])
            if comet[5] <= 0 or x < -5 or x >= WIDTH + 5 or y < -5 or y >= HEIGHT + 5:
                self._comet_respawn(comet, i)
                self._demo_sound("ping", i, 130)
                continue
            r, g, b = hsb_to_rgb((comet[4] + self._frame * 2) % 360, 0.85, 1)
            tail_x = int(comet[0] - comet[2] * 8.0)
            tail_y = int(comet[1] - comet[3] * 8.0)
            draw_line(tail_x, tail_y, x, y, r // 3, g // 3, b // 3)
            if 0 <= x < WIDTH and 0 <= y < HEIGHT:
                display.set_pixel(x, y, r, g, b)
                if x + 1 < WIDTH:
                    display.set_pixel(x + 1, y, r // 2, g // 2, b // 2)

    # --- BOUNCE (classic screensaver) ---
    def _bounce_init(self):
        self._bounce_x = random.randint(0, WIDTH - 25)
        self._bounce_y = random.randint(0, HEIGHT - 9)
        self._bounce_dx = random.choice([-1, 1])
        self._bounce_dy = random.choice([-1, 1])
        self._bounce_hue = random.randint(0, 359)
        display.clear()

    def _bounce_step(self):
        display.clear()
        label = "ARCADE"
        w = 48
        h = 8
        self._bounce_x += self._bounce_dx
        self._bounce_y += self._bounce_dy
        bounced = False

        if self._bounce_x <= 0:
            self._bounce_x = 0
            self._bounce_dx = 1
            bounced = True
        elif self._bounce_x >= WIDTH - w:
            self._bounce_x = WIDTH - w
            self._bounce_dx = -1
            bounced = True

        if self._bounce_y <= 0:
            self._bounce_y = 0
            self._bounce_dy = 1
            bounced = True
        elif self._bounce_y >= HEIGHT - h:
            self._bounce_y = HEIGHT - h
            self._bounce_dy = -1
            bounced = True

        if bounced:
            # The original screensaver's color pop is the main visual cue.
            self._bounce_hue = (self._bounce_hue + 67) % 360
            self._demo_sound("bounce", self._bounce_hue, 70)

        r, g, b = hsb_to_rgb(self._bounce_hue, 1, 1)
        draw_text(self._bounce_x, self._bounce_y, label, r, g, b)
        draw_rectangle(self._bounce_x, self._bounce_y + 8, self._bounce_x + w - 1, self._bounce_y + 8, r // 3, g // 3, b // 3)

    # --- PLASMA ---
    def _plasma_init(self):
        self._plasma_time = 0
        if not self._plasma_palette:
            self._plasma_palette = [hsb_to_rgb(i * 360 / 256.0, 1, 1) for i in range(256)]
        if not self._plasma_sin:
            self._plasma_sin = [int((math.sin(i * 3.14159 * 2 / 255.0) + 1) * 127) for i in range(256)]

    def _plasma_step(self):
        self._plasma_time = (self._plasma_time + 4) % 256
        t = self._plasma_time
        sin = self._plasma_sin
        pal = self._plasma_palette
        
        for y in range(0, HEIGHT, 2):
            vy = sin[(y*4 + t) % 256]
            for x in range(0, WIDTH, 2):
                vx = sin[(x*4 + t) % 256]
                vc = sin[(x*2 + y*2 + t*2) % 256]
                
                dist = abs(x - (WIDTH//2)) + abs(y - (HEIGHT//2))
                vd = sin[(dist*6 - t*3) % 256]
                
                v = (vy + vx + vc + vd) >> 2
                
                r, g, b = pal[v % 256]
                draw_rectangle(x, y, x+2, y+2, r, g, b)
        
    # --- SNAKE (based on hub75/snake_on_hub75_zeroplayer.py) ---
    def _snake_restart(self):
        self._snake_score = 0
        self._snake = [(WIDTH // 2, HEIGHT // 2)]
        self._snake_length = 3
        self._snake_dir = 'UP'
        self._snake_green_targets = []
        self._snake_step_counter = 0
        self._snake_step_counter2 = 0
        display.clear()
        self._snake_place_target()

    def _snake_random_target(self):
        return (random.randint(1, WIDTH - 2), random.randint(1, HEIGHT - 2))

    def _snake_place_target(self):
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
        new_targets = []
        for x, y, lifespan in self._snake_green_targets:
            if lifespan > 1:
                new_targets.append((x, y, lifespan - 1))
            else:
                display.set_pixel(x, y, 0, 0, 0)
        self._snake_green_targets = new_targets

    def _snake_find_nearest_target(self, head_x, head_y):
        def md(x1, y1, x2, y2):
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
        head_x, head_y = self._snake[0]
        target_x, target_y = self._snake_find_nearest_target(head_x, head_y)

        opposite = {'UP': 'DOWN', 'DOWN': 'UP', 'LEFT': 'RIGHT', 'RIGHT': 'LEFT'}
        cur = self._snake_dir
        new_dir = cur

        if head_x == target_x:
            if head_y < target_y and cur != 'UP':
                new_dir = 'DOWN'
            elif head_y > target_y and cur != 'DOWN':
                new_dir = 'UP'
        elif head_y == target_y:
            if head_x < target_x and cur != 'LEFT':
                new_dir = 'RIGHT'
            elif head_x > target_x and cur != 'RIGHT':
                new_dir = 'LEFT'
        else:
            if abs(head_x - target_x) < abs(head_y - target_y):
                if head_x < target_x and cur != 'LEFT':
                    new_dir = 'RIGHT'
                elif head_x > target_x and cur != 'RIGHT':
                    new_dir = 'LEFT'
            else:
                if head_y < target_y and cur != 'UP':
                    new_dir = 'DOWN'
                elif head_y > target_y and cur != 'DOWN':
                    new_dir = 'UP'

        if new_dir == opposite.get(cur):
            new_dir = cur
        self._snake_dir = new_dir

    def _snake_check_self_collision(self):
        head_x, head_y = self._snake[0]
        body = self._snake[1:]
        potential = {
            'UP': (head_x, (head_y - 1) % HEIGHT),
            'DOWN': (head_x, (head_y + 1) % HEIGHT),
            'LEFT': ((head_x - 1) % WIDTH, head_y),
            'RIGHT': ((head_x + 1) % WIDTH, head_y)
        }
        cur_next = potential[self._snake_dir]
        if cur_next in body:
            safe = [d for d, pos in potential.items() if pos not in body]
            if safe:
                self._snake_dir = safe[random.randint(0, len(safe) - 1)]
            else:
                self._snake_restart()

    def _snake_update_position(self):
        head_x, head_y = self._snake[0]
        if self._snake_dir == 'UP':
            head_y -= 1
        elif self._snake_dir == 'DOWN':
            head_y += 1
        elif self._snake_dir == 'LEFT':
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
        if self._snake[0] == self._snake_target:
            self._snake_length += 2
            self._snake_place_target()
            self._snake_score += 1
            self._demo_sound("coin", self._snake_score, 70)

    def _snake_check_green_target_collision(self):
        hx, hy = self._snake[0]
        for x, y, lifespan in self._snake_green_targets:
            if (hx, hy) == (x, y):
                self._snake_length = max(self._snake_length // 2, 2)
                try:
                    self._snake_green_targets.remove((x, y, lifespan))
                except Exception:
                    pass
                display.set_pixel(x, y, 0, 0, 0)
                self._demo_sound("zap", self._snake_length, 90)
                break

    def _snake_draw(self):
        hue = 0
        for x, y in self._snake:
            hue = (hue + 5) % 360
            r, g, b = hsb_to_rgb(hue, 1, 1)
            display.set_pixel(x, y, r, g, b)

    def _snake_init(self):
        self._snake_restart()

    def _snake_step(self):
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

    # --- SPARK ---
    def _spark_init(self):
        self._spark_particles = []
        cx = WIDTH // 2
        cy = HEIGHT // 2
        for _ in range(30 if not CONFIG_LOW_RAM_MODE else 16):
            angle = random.randint(0, 359) * 3.14159 / 180.0
            speed = random.uniform(0.4, 1.8)
            self._spark_particles.append([
                float(cx), float(cy),
                math.cos(angle) * speed,
                math.sin(angle) * speed,
                random.randint(18, 70),
                random.randint(0, 359),
            ])
        display.clear()

    def _spark_respawn(self, p):
        cx = WIDTH // 2 + int(math.sin(self._frame * 0.045) * 10)
        cy = HEIGHT // 2 + int(math.cos(self._frame * 0.037) * 8)
        angle = random.randint(0, 359) * 3.14159 / 180.0
        speed = random.uniform(0.4, 1.9)
        p[0] = float(cx)
        p[1] = float(cy)
        p[2] = math.cos(angle) * speed
        p[3] = math.sin(angle) * speed
        p[4] = random.randint(18, 70)
        p[5] = random.randint(0, 359)

    def _spark_step(self):
        display.clear()
        for p in self._spark_particles:
            p[0] += p[2]
            p[1] += p[3]
            p[3] += 0.025
            p[4] -= 1
            x = int(p[0])
            y = int(p[1])
            if p[4] <= 0 or x < 0 or x >= WIDTH or y < 0 or y >= HEIGHT:
                self._spark_respawn(p)
                continue
            hue = (p[5] + self._frame * 4) % 360
            r, g, b = hsb_to_rgb(hue, 1, 1)
            display.set_pixel(x, y, r, g, b)
            tx = int(p[0] - p[2])
            ty = int(p[1] - p[3])
            if 0 <= tx < WIDTH and 0 <= ty < HEIGHT:
                display.set_pixel(tx, ty, r // 3, g // 3, b // 3)

    # --- RINGS ---
    def _rings_init(self):
        self._rings_phase = random.randint(0, 255)
        display.clear()

    def _rings_step(self):
        display.clear()
        self._rings_phase = (self._rings_phase + 3) & 255
        phase = self._rings_phase
        cx = WIDTH // 2 + int(math.sin(phase * 0.031) * 5)
        cy = HEIGHT // 2 + int(math.cos(phase * 0.027) * 5)

        for ring in range(7):
            radius = 4 + ((phase // 3 + ring * 7) % 34)
            hue = (phase * 3 + ring * 43) % 360
            r, g, b = hsb_to_rgb(hue, 1, 1)
            points = 18 + ring * 2
            for i in range(points):
                a = (i * 6.28318) / points
                wobble = math.sin((phase + i * 17 + ring * 11) * 0.055) * 2.0
                x = int(cx + math.cos(a) * (radius + wobble))
                y = int(cy + math.sin(a) * (radius - wobble))
                if 0 <= x < WIDTH and 0 <= y < HEIGHT:
                    display.set_pixel(x, y, r, g, b)
                    if ring < 4 and x + 1 < WIDTH:
                        display.set_pixel(x + 1, y, r // 2, g // 2, b // 2)

    # --- RADAR ---
    def _radar_init(self):
        self._radar_phase = random.randint(0, 255)
        self._radar_blips = []
        display.clear()

    def _radar_step(self):
        display.clear()
        cx = WIDTH // 2
        cy = HEIGHT // 2
        self._radar_phase = (self._radar_phase + 3) & 255
        phase = self._radar_phase

        for radius in (10, 18, 27):
            for i in range(0, 64, 2):
                a = i * 6.28318 / 64.0
                x = int(cx + math.cos(a) * radius)
                y = int(cy + math.sin(a) * radius)
                if 0 <= x < WIDTH and 0 <= y < HEIGHT:
                    display.set_pixel(x, y, 0, 45, 0)
        draw_line(cx, 4, cx, HEIGHT - 5, 0, 28, 0)
        draw_line(4, cy, WIDTH - 5, cy, 0, 28, 0)

        sweep = phase * 6.28318 / 256.0
        sx = int(cx + math.cos(sweep) * 30)
        sy = int(cy + math.sin(sweep) * 30)
        draw_line(cx, cy, sx, sy, 0, 255, 80)
        for i in range(1, 5):
            a = sweep - i * 0.10
            tx = int(cx + math.cos(a) * 29)
            ty = int(cy + math.sin(a) * 29)
            draw_line(cx, cy, tx, ty, 0, 90 // i, 25 // i)

        if (self._frame & 3) == 0 and random.randint(0, 99) < 70:
            r = random.randint(7, 29)
            x = int(cx + math.cos(sweep) * r)
            y = int(cy + math.sin(sweep) * r)
            if 0 <= x < WIDTH and 0 <= y < HEIGHT:
                self._radar_blips.append([x, y, 255])
                self._demo_sound("ping", r, 120)

        active = []
        for blip in self._radar_blips:
            x, y, bright = blip
            display.set_pixel(x, y, bright // 5, bright, bright // 8)
            if bright > 170 and x + 1 < WIDTH:
                display.set_pixel(x + 1, y, bright // 8, bright // 2, 0)
            bright -= 7
            if bright > 18:
                blip[2] = bright
                active.append(blip)
        if len(active) > 18:
            active = active[-18:]
        self._radar_blips = active

    # --- MANDELBROT ---
    def _mandel_init(self):
        self._mandel_y = 0
        self._mandel_pass = 0
        if not self._mandel_palette:
            self._mandel_palette = [hsb_to_rgb((i * 11) % 360, 1, 1) for i in range(32)]
        self._mandel_xs = []
        self._mandel_params = None
        display.clear()

    def _mandel_step(self):
        rows_per_frame = 4 if not CONFIG_LOW_RAM_MODE else 2
        pass_id = self._mandel_pass
        max_iter = 18 + (pass_id & 3) * 3
        zoom = 1.0 + (pass_id & 7) * 0.13
        cxoff = -0.58 + math.sin(pass_id * 0.23) * 0.12
        cyoff = math.cos(pass_id * 0.17) * 0.08
        pal = self._mandel_palette
        params = (max_iter, zoom, cxoff)
        if self._mandel_params != params or len(self._mandel_xs) != WIDTH:
            self._mandel_xs = [((x - 32) / 22.0) / zoom + cxoff for x in range(WIDTH)]
            self._mandel_params = params
        xs = self._mandel_xs
        sp = display.set_pixel

        for _ in range(rows_per_frame):
            y = self._mandel_y
            if y >= HEIGHT:
                self._mandel_y = 0
                self._mandel_pass = (self._mandel_pass + 1) & 255
                self._mandel_params = None
                return
            cy = ((y - 32) / 26.0) / zoom + cyoff
            for x in range(WIDTH):
                cx = xs[x]
                qx = cx - 0.25
                q = qx * qx + cy * cy
                if q * (q + qx) <= 0.25 * cy * cy or (cx + 1.0) * (cx + 1.0) + cy * cy <= 0.0625:
                    sp(x, y, 0, 0, 0)
                    continue
                zx = 0.0
                zy = 0.0
                it = 0
                while zx * zx + zy * zy <= 4.0 and it < max_iter:
                    zx, zy = zx * zx - zy * zy + cx, 2.0 * zx * zy + cy
                    it += 1
                if it >= max_iter:
                    sp(x, y, 0, 0, 0)
                else:
                    r, g, b = pal[(it + pass_id) & 31]
                    shade = 70 + it * 9
                    if shade > 255:
                        shade = 255
                    sp(x, y, (r * shade) // 255, (g * shade) // 255, (b * shade) // 255)
            self._mandel_y += 1

    # --- BOIDS ---
    def _boids_init(self):
        self._boids = []
        n = 18
        for i in range(n):
            a = random.randint(0, 359) * 3.14159 / 180.0
            self._boids.append([
                random.uniform(4, WIDTH - 5),
                random.uniform(4, HEIGHT - 5),
                math.cos(a) * 0.7,
                math.sin(a) * 0.7,
                (i * 360) // n,
            ])
        display.clear()

    def _boids_step(self):
        display.clear()
        boids = self._boids
        n = len(boids)
        for i in range(n):
            b = boids[i]
            ax = ay = cx = cy = sx = sy = 0.0
            count = 0
            close = 0
            for j in range(n):
                if i == j:
                    continue
                o = boids[j]
                dx = o[0] - b[0]
                dy = o[1] - b[1]
                d2 = dx * dx + dy * dy
                if d2 < 170.0:
                    ax += o[2]
                    ay += o[3]
                    cx += o[0]
                    cy += o[1]
                    count += 1
                if d2 < 20.0 and d2 > 0.01:
                    sx -= dx
                    sy -= dy
                    close += 1
            if count:
                inv = 1.0 / count
                b[2] += (ax * inv - b[2]) * 0.045
                b[3] += (ay * inv - b[3]) * 0.045
                b[2] += (cx * inv - b[0]) * 0.0022
                b[3] += (cy * inv - b[1]) * 0.0022
            if close:
                b[2] += sx * 0.018
                b[3] += sy * 0.018

            if b[0] < 5:
                b[2] += 0.08
            elif b[0] > WIDTH - 6:
                b[2] -= 0.08
            if b[1] < 5:
                b[3] += 0.08
            elif b[1] > HEIGHT - 6:
                b[3] -= 0.08

            speed = math.sqrt(b[2] * b[2] + b[3] * b[3])
            if speed > 1.45:
                scale = 1.45 / speed
                b[2] *= scale
                b[3] *= scale
            elif speed < 0.35:
                b[2] *= 1.10
                b[3] *= 1.10

        for b in boids:
            b[0] = (b[0] + b[2]) % WIDTH
            b[1] = (b[1] + b[3]) % HEIGHT
            x = int(b[0])
            y = int(b[1])
            r, g, bb = hsb_to_rgb((b[4] + self._frame * 2) % 360, 0.85, 1)
            display.set_pixel(x, y, r, g, bb)
            tx = int(b[0] - b[2] * 2.0)
            ty = int(b[1] - b[3] * 2.0)
            if 0 <= tx < WIDTH and 0 <= ty < HEIGHT:
                display.set_pixel(tx, ty, r // 4, g // 4, bb // 4)

    # --- NBODY ---
    def _nbody_init(self):
        self._nbody = []
        cx = WIDTH / 2.0
        cy = HEIGHT / 2.0
        for i in range(10):
            a = i * 6.28318 / 10.0
            radius = 6.0 + (i % 4) * 3.5
            mass = 0.45 + (i % 3) * 0.22
            self._nbody.append([
                cx + math.cos(a) * radius,
                cy + math.sin(a) * radius,
                -math.sin(a) * (0.35 + i * 0.015),
                math.cos(a) * (0.35 + i * 0.015),
                mass,
                (i * 36) % 360,
            ])
        display.clear()

    def _nbody_step(self):
        display.clear()
        bodies = self._nbody
        n = len(bodies)
        for i in range(n):
            bi = bodies[i]
            ax = 0.0
            ay = 0.0
            for j in range(n):
                if i == j:
                    continue
                bj = bodies[j]
                dx = bj[0] - bi[0]
                dy = bj[1] - bi[1]
                d2 = dx * dx + dy * dy + 12.0
                inv = 0.020 * bj[4] / d2
                ax += dx * inv
                ay += dy * inv
            bi[2] = (bi[2] + ax) * 0.997
            bi[3] = (bi[3] + ay) * 0.997

        for b in bodies:
            px = int(b[0])
            py = int(b[1])
            b[0] += b[2]
            b[1] += b[3]
            if b[0] < 2 or b[0] > WIDTH - 3:
                b[2] = -b[2] * 0.92
                b[0] = 2 if b[0] < 2 else WIDTH - 3
            if b[1] < 2 or b[1] > HEIGHT - 3:
                b[3] = -b[3] * 0.92
                b[1] = 2 if b[1] < 2 else HEIGHT - 3

            x = int(b[0])
            y = int(b[1])
            r, g, bb = hsb_to_rgb((b[5] + self._frame * 3) % 360, 1, 1)
            if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                display.set_pixel(px, py, r // 5, g // 5, bb // 5)
            display.set_pixel(x, y, r, g, bb)
            if b[4] > 0.7 and x + 1 < WIDTH:
                display.set_pixel(x + 1, y, r // 2, g // 2, bb // 2)

    # --- METABALL / LIQUID FIELD ---
    def _metab_init(self):
        self._metab_phase = random.randint(0, 255)
        self._metab_balls = []
        count = 5 if not CONFIG_LOW_RAM_MODE else 3
        for i in range(count):
            angle = (i * 6.28318) / count
            self._metab_balls.append([
                WIDTH / 2.0 + math.cos(angle) * 16.0,
                HEIGHT / 2.0 + math.sin(angle) * 12.0,
                math.cos(angle + 1.7) * (0.34 + i * 0.025),
                math.sin(angle + 0.9) * (0.30 + i * 0.020),
                58.0 + i * 9.0,
                (i * 58) % 360,
            ])
        display.clear()

    def _metab_step(self):
        # Scalar field: every ball contributes inverse-distance strength.
        # Coarse 2x2 sampling keeps the liquid look affordable on 64x64.
        self._metab_phase = (self._metab_phase + 2) & 255
        balls = self._metab_balls

        for b in balls:
            b[0] += b[2]
            b[1] += b[3]
            if b[0] < 4 or b[0] > WIDTH - 5:
                b[2] = -b[2]
                b[0] = clamp(b[0], 4, WIDTH - 5)
            if b[1] < 4 or b[1] > HEIGHT - 5:
                b[3] = -b[3]
                b[1] = clamp(b[1], 4, HEIGHT - 5)

        for y in range(0, HEIGHT, 2):
            for x in range(0, WIDTH, 2):
                field = 0.0
                hue_acc = 0.0
                for b in balls:
                    dx = x - b[0]
                    dy = y - b[1]
                    d2 = dx * dx + dy * dy + 9.0
                    strength = b[4] / d2
                    field += strength
                    hue_acc += b[5] * strength
                if field > 1.75:
                    hue = (int(hue_acc / field) + self._metab_phase * 2) % 360
                    r, g, bb = hsb_to_rgb(hue, 0.9, 1)
                    # Thresholded core/edge brightness works without blending.
                    if field < 2.35:
                        r, g, bb = r // 3, g // 3, bb // 3
                    draw_rectangle(x, y, x + 1, y + 1, r, g, bb)
                else:
                    draw_rectangle(x, y, x + 1, y + 1, 0, 0, 0)

    # --- GRAVITY WELL PARTICLES ---
    def _grav_init(self):
        self._grav_phase = random.randint(0, 255)
        self._grav_particles = []
        cx = WIDTH / 2.0
        cy = HEIGHT / 2.0
        count = 28 if not CONFIG_LOW_RAM_MODE else 16
        for i in range(count):
            a = (i * 6.28318) / count
            radius = 6.0 + (i % 7) * 3.2
            self._grav_particles.append([
                cx + math.cos(a) * radius,
                cy + math.sin(a) * radius,
                -math.sin(a) * 0.62,
                math.cos(a) * 0.62,
                (i * 360) // count,
            ])
        display.clear()

    def _grav_step(self):
        # Two moving attractors pull independent particles. Unlike NBODY,
        # particles do not attract each other, so cost stays predictable.
        self._grav_phase = (self._grav_phase + 3) & 255
        phase = self._grav_phase
        cx = WIDTH / 2.0
        cy = HEIGHT / 2.0
        a = phase * 6.28318 / 256.0
        wells = (
            (cx + math.cos(a) * 12.0, cy + math.sin(a * 1.25) * 10.0, 0.95),
            (cx + math.cos(a + 3.14159) * 14.0, cy + math.sin(a * 0.85 + 2.0) * 12.0, 0.70),
        )

        display.clear()
        for wx, wy, _mass in wells:
            draw_rectangle(int(wx) - 1, int(wy) - 1, int(wx) + 1, int(wy) + 1, 255, 255, 255)

        for p in self._grav_particles:
            px = p[0]
            py = p[1]
            ax = 0.0
            ay = 0.0
            for wx, wy, mass in wells:
                dx = wx - p[0]
                dy = wy - p[1]
                d2 = dx * dx + dy * dy + 18.0
                pull = mass / d2
                ax += dx * pull
                ay += dy * pull
            p[2] = (p[2] + ax) * 0.993
            p[3] = (p[3] + ay) * 0.993
            p[0] += p[2]
            p[1] += p[3]

            # Wrap to preserve orbital energy and avoid edge clumping.
            if p[0] < 0:
                p[0] += WIDTH
                px = p[0]
            elif p[0] >= WIDTH:
                p[0] -= WIDTH
                px = p[0]
            if p[1] < 0:
                p[1] += HEIGHT
                py = p[1]
            elif p[1] >= HEIGHT:
                p[1] -= HEIGHT
                py = p[1]

            r, g, bb = hsb_to_rgb((p[4] + phase * 2) % 360, 0.85, 1)
            tx = int(px)
            ty = int(py)
            if 0 <= tx < WIDTH and 0 <= ty < HEIGHT:
                display.set_pixel(tx, ty, r // 4, g // 4, bb // 4)
            display.set_pixel(int(p[0]), int(p[1]), r, g, bb)

    # --- SPRING MASS CHAIN ---
    def _spring_init(self):
        self._spring_phase = random.randint(0, 255)
        self._spring_rest = 6.0
        self._spring_nodes = []
        count = 5 if CONFIG_LOW_RAM_MODE else 7
        cx = WIDTH / 2.0
        cy = 8.0
        for i in range(count):
            self._spring_nodes.append([
                cx + random.uniform(-0.8, 0.8),
                cy + (i + 1) * self._spring_rest,
                random.uniform(-0.15, 0.15),
                random.uniform(-0.15, 0.15),
                1.0 + i * 0.18,
                (i * 360) // count,
            ])
        display.clear()

    def _spring_pull(self, ax, ay, node, rest, k):
        dx = node[0] - ax
        dy = node[1] - ay
        d2 = dx * dx + dy * dy
        if d2 <= 0.0001:
            return
        d = math.sqrt(d2)
        nx = dx / d
        ny = dy / d
        stretch = d - rest
        fx = nx * stretch * k
        fy = ny * stretch * k
        node[2] -= fx / node[4]
        node[3] -= fy / node[4]

    def _spring_step(self):
        display.clear()
        self._spring_phase = (self._spring_phase + 2) & 255
        anchor_x = WIDTH / 2.0 + math.sin(self._spring_phase * 0.05) * 7.0
        anchor_y = 6.0
        nodes = self._spring_nodes
        if not nodes:
            self._spring_init()
            nodes = self._spring_nodes

        for node in nodes:
            node[3] += 0.12
            node[0] += node[2]
            node[1] += node[3]
            node[2] *= 0.992
            node[3] *= 0.992

        for _ in range(3):
            self._spring_pull(anchor_x, anchor_y, nodes[0], self._spring_rest, 0.12)
            for i in range(len(nodes) - 1):
                self._spring_pull(nodes[i][0], nodes[i][1], nodes[i + 1], self._spring_rest, 0.09)

            dx = nodes[0][0] - anchor_x
            dy = nodes[0][1] - anchor_y
            d2 = dx * dx + dy * dy
            if d2 > 0.0001:
                d = math.sqrt(d2)
                nx = dx / d
                ny = dy / d
                nodes[0][0] = anchor_x + nx * self._spring_rest
                nodes[0][1] = anchor_y + ny * self._spring_rest
                rv = nodes[0][2] * nx + nodes[0][3] * ny
                nodes[0][2] -= rv * nx
                nodes[0][3] -= rv * ny

            for i in range(1, len(nodes)):
                a = nodes[i - 1]
                b = nodes[i]
                dx = b[0] - a[0]
                dy = b[1] - a[1]
                d2 = dx * dx + dy * dy
                if d2 <= 0.0001:
                    continue
                d = math.sqrt(d2)
                nx = dx / d
                ny = dy / d
                b[0] = a[0] + nx * self._spring_rest
                b[1] = a[1] + ny * self._spring_rest
                rv = (b[2] - a[2]) * nx + (b[3] - a[3]) * ny
                if rv > 0:
                    rv = 0.0
                a[2] += rv * nx * 0.5
                a[3] += rv * ny * 0.5
                b[2] -= rv * nx * 0.5
                b[3] -= rv * ny * 0.5

        for i, node in enumerate(nodes):
            radius = 2 if i < len(nodes) - 1 else 3
            if node[0] < radius + 1:
                node[0] = radius + 1
                node[2] = abs(node[2]) * 0.65
            elif node[0] > WIDTH - radius - 2:
                node[0] = WIDTH - radius - 2
                node[2] = -abs(node[2]) * 0.65
            if node[1] < 4 + radius:
                node[1] = 4 + radius
                node[3] = abs(node[3]) * 0.65
            elif node[1] > HEIGHT - radius - 2:
                node[1] = HEIGHT - radius - 2
                node[3] = -abs(node[3]) * 0.65

        draw_rectangle(int(anchor_x) - 2, int(anchor_y) - 1, int(anchor_x) + 2, int(anchor_y), 255, 255, 255)
        px, py = anchor_x, anchor_y
        for i, node in enumerate(nodes):
            hue = (self._frame * 3 + i * 40) % 360
            r, g, b = hsb_to_rgb(hue, 1, 1)
            draw_line(int(px), int(py), int(node[0]), int(node[1]), r // 2, g // 2, b // 2)
            self._demo_disc(int(node[0]), int(node[1]), 2 if i < len(nodes) - 1 else 3, (r, g, b))
            px, py = node[0], node[1]

    # --- CRADLE (Newton's cradle) ---
    def _cradle_init(self):
        self._cradle_phase = 0
        self._cradle_length = 13.0
        self._cradle_bobs = []
        count = 5
        span = 7.0
        top_y = 8.0
        base_x = WIDTH / 2.0 - span * (count - 1) * 0.5
        for i in range(count):
            anchor_x = base_x + i * span
            anchor_y = top_y
            angle = -0.78 if i == 0 else 0.0
            x = anchor_x + math.sin(angle) * self._cradle_length
            y = anchor_y + math.cos(angle) * self._cradle_length
            vx = 0.9 if i == 0 else 0.0
            vy = 0.0
            self._cradle_bobs.append([x, y, vx, vy, anchor_x, anchor_y, self._cradle_length, (i * 56) % 360])
        display.clear()

    def _cradle_constrain(self, bob):
        dx = bob[0] - bob[4]
        dy = bob[1] - bob[5]
        d2 = dx * dx + dy * dy
        if d2 <= 0.0001:
            return
        d = math.sqrt(d2)
        nx = dx / d
        ny = dy / d
        bob[0] = bob[4] + nx * bob[6]
        bob[1] = bob[5] + ny * bob[6]
        radial = bob[2] * nx + bob[3] * ny
        bob[2] -= radial * nx
        bob[3] -= radial * ny

    def _cradle_step(self):
        display.clear()
        self._cradle_phase = (self._cradle_phase + 1) & 255
        bobs = self._cradle_bobs
        if not bobs:
            self._cradle_init()
            bobs = self._cradle_bobs

        for bob in bobs:
            bob[3] += 0.11
            bob[0] += bob[2]
            bob[1] += bob[3]
            bob[2] *= 0.994
            bob[3] *= 0.994

        for _ in range(2):
            for bob in bobs:
                self._cradle_constrain(bob)

            for i in range(len(bobs)):
                for j in range(i + 1, len(bobs)):
                    a = bobs[i]
                    b = bobs[j]
                    dx = b[0] - a[0]
                    dy = b[1] - a[1]
                    min_d = 4.4
                    d2 = dx * dx + dy * dy
                    if d2 <= 0.0001 or d2 >= min_d * min_d:
                        continue
                    d = math.sqrt(d2)
                    nx = dx / d
                    ny = dy / d
                    overlap = (min_d - d) * 0.5
                    a[0] -= nx * overlap
                    a[1] -= ny * overlap
                    b[0] += nx * overlap
                    b[1] += ny * overlap
                    rvx = b[2] - a[2]
                    rvy = b[3] - a[3]
                    vel_n = rvx * nx + rvy * ny
                    if vel_n > 0:
                        continue
                    impulse = -(1.0 + 0.98) * vel_n * 0.5
                    a[2] -= impulse * nx
                    a[3] -= impulse * ny
                    b[2] += impulse * nx
                    b[3] += impulse * ny

        for bob in bobs:
            self._cradle_constrain(bob)

        draw_rectangle(10, 6, WIDTH - 11, 6, 180, 180, 190)
        for bob in bobs:
            hue = (bob[7] + self._frame * 2) % 360
            r, g, b = hsb_to_rgb(hue, 1, 1)
            draw_line(int(bob[4]), int(bob[5]), int(bob[0]), int(bob[1]), 130, 130, 140)
            self._demo_disc(int(bob[0]), int(bob[1]), 2, (r, g, b))

    # --- CRT TEST PATTERN ---
    def _crt_init(self):
        self._crt_phase = 0
        display.clear()

    def _crt_step(self):
        self._crt_phase = (self._crt_phase + 1) & 255
        phase = self._crt_phase
        bars = (
            (255, 255, 255), (255, 255, 0), (0, 255, 255), (0, 255, 0),
            (255, 0, 255), (255, 0, 0), (0, 0, 255), (20, 20, 20)
        )
        for x in range(WIDTH):
            r, g, b = bars[(x * len(bars)) // WIDTH]
            for y in range(0, 34):
                dim = 160 if ((y + phase) & 7) == 0 else 255
                if y & 1:
                    dim = (dim * 3) // 5
                display.set_pixel(x, y, (r * dim) // 255, (g * dim) // 255, (b * dim) // 255)
        for y in range(34, HEIGHT):
            for x in range(WIDTH):
                v = 30 + ((x * 5 + y * 3 + phase) & 31)
                display.set_pixel(x, y, v, v, v)
        for x in range(0, WIDTH, 8):
            draw_line(x, 0, x, HEIGHT - 1, 0, 0, 0)
        for y in range(0, HEIGHT, 8):
            draw_line(0, y, WIDTH - 1, y, 0, 0, 0)
        roll = phase & 63
        draw_line(0, roll, WIDTH - 1, roll, 255, 255, 255)
        draw_rectangle(23, 45, 40, 54, 0, 0, 0)
        draw_text(25, 46, "CRT", 255, 255, 255)

    # --- WIN95 MAZE / DOOM RAYCASTER REUSE ---
    def _winmaze_init(self):
        self._winmaze = DoomLiteGame()
        self._winmaze.configure_attract_maze()
        self._winmaze_path_phase = 0
        display.clear()

    def _winmaze_step(self):
        if self._winmaze is None:
            self._winmaze_init()
        self._winmaze_path_phase = (self._winmaze_path_phase + 1) & 255
        self._winmaze.step_attract_maze(self._frame)

    # --- RIPPLE (water height-field) ---
    def _ripple_init(self):
        w = self._ripple_w
        h = self._ripple_h
        self._ripple_cur = [0] * (w * h)
        self._ripple_prev = [0] * (w * h)
        # Seed a couple of drops so the surface is alive from the first frame.
        for _ in range(3):
            self._ripple_drop()
        display.clear()

    def _ripple_drop(self):
        w = self._ripple_w
        h = self._ripple_h
        x = random.randint(2, w - 3)
        y = random.randint(2, h - 3)
        self._ripple_cur[y * w + x] = 480
        self._demo_sound("ping", x + y, 150)

    def _ripple_step(self):
        w = self._ripple_w
        h = self._ripple_h
        cur = self._ripple_cur
        prev = self._ripple_prev

        # Occasional raindrops keep the pool rippling forever.
        if random.randint(0, 99) < 7:
            self._ripple_drop()

        sp = display.set_pixel
        for y in range(1, h - 1):
            row = y * w
            for x in range(1, w - 1):
                i = row + x
                # Classic damped wave equation on the integer height-field.
                v = ((cur[i - 1] + cur[i + 1] + cur[i - w] + cur[i + w]) >> 1) - prev[i]
                v -= v >> 5
                prev[i] = v

                # Shade water from deep blue troughs to bright cyan crests.
                shade = 96 + (v >> 1)
                if shade < 0:
                    shade = 0
                elif shade > 255:
                    shade = 255
                r = shade >> 2
                g = (shade * 5) >> 3
                px = x << 1
                py = y << 1
                sp(px, py, r, g, shade)
                sp(px + 1, py, r, g, shade)
                sp(px, py + 1, r, g, shade)
                sp(px + 1, py + 1, r, g, shade)

        # Swap buffers: the freshly computed field becomes current.
        self._ripple_cur, self._ripple_prev = prev, cur

    # --- FIRWRK (fireworks) ---
    def _firwrk_init(self):
        self._fw_rockets = []
        self._fw_particles = []
        display.clear()

    def _firwrk_launch(self):
        x = float(random.randint(8, WIDTH - 9))
        vy = -random.uniform(1.4, 2.0)
        apex = random.randint(8, 26)
        hue = random.randint(0, 359)
        # [x, y, vy, target_apex_y, hue]
        self._fw_rockets.append([x, float(HEIGHT - 1), vy, float(apex), hue])

    def _firwrk_burst(self, x, y, hue):
        n = 14 if CONFIG_LOW_RAM_MODE else 26
        for _ in range(n):
            a = random.randint(0, 359) * 0.0174533
            speed = random.uniform(0.4, 1.7)
            phue = (hue + random.randint(-25, 25)) % 360
            self._fw_particles.append([
                float(x), float(y),
                math.cos(a) * speed, math.sin(a) * speed,
                random.randint(20, 38), phue,
            ])
        self._demo_sound("bounce", hue, 80)

    def _firwrk_step(self):
        display.clear()
        max_rockets = 2 if CONFIG_LOW_RAM_MODE else 4
        if len(self._fw_rockets) < max_rockets and random.randint(0, 99) < 14:
            self._firwrk_launch()

        sp = display.set_pixel
        rockets = []
        for rk in self._fw_rockets:
            rk[1] += rk[2]
            rk[2] += 0.03  # gravity slows the ascent
            x = int(rk[0])
            y = int(rk[1])
            # Burst at apex (rising stalls) or when the target height is reached.
            if rk[2] >= -0.2 or rk[1] <= rk[3]:
                self._firwrk_burst(rk[0], rk[1], rk[4])
                continue
            r, g, b = hsb_to_rgb(rk[4], 0.5, 1)
            if 0 <= x < WIDTH and 0 <= y < HEIGHT:
                sp(x, y, r, g, b)
                ty = y + 1
                if ty < HEIGHT:
                    sp(x, ty, r // 3, g // 3, b // 4)
            rockets.append(rk)
        self._fw_rockets = rockets

        alive = []
        for p in self._fw_particles:
            p[0] += p[2]
            p[1] += p[3]
            p[3] += 0.045  # gravity pulls sparks down
            p[2] *= 0.985   # air drag
            p[4] -= 1
            x = int(p[0])
            y = int(p[1])
            if p[4] <= 0 or x < 0 or x >= WIDTH or y < 0 or y >= HEIGHT:
                continue
            bright = p[4] * 7
            if bright > 100:
                bright = 100
            r, g, b = hsb_to_rgb(p[5], 1, bright / 100.0)
            sp(x, y, r, g, b)
            alive.append(p)
        self._fw_particles = alive

    # --- PHYLLO (phyllotaxis sunflower spiral) ---
    def _phyllo_init(self):
        self._phyllo_phase = 0.0
        display.clear()

    def _phyllo_step(self):
        display.clear()
        cx = WIDTH * 0.5 - 0.5
        cy = HEIGHT * 0.5 - 0.5
        self._phyllo_phase += 0.05
        n = 90 if CONFIG_LOW_RAM_MODE else 150
        # Scale so the outermost seed lands near the matrix edge.
        c = 30.0 / math.sqrt(n)
        golden = 2.39996323  # 137.5 degrees, the golden angle
        base_hue = int(self._frame * 2)
        sp = display.set_pixel
        for i in range(n):
            a = i * golden + self._phyllo_phase
            r = c * math.sqrt(i)
            x = int(cx + r * math.cos(a))
            y = int(cy + r * math.sin(a))
            if 0 <= x < WIDTH and 0 <= y < HEIGHT:
                cr, cg, cb = hsb_to_rgb((i * 4 + base_hue) % 360, 1, 1)
                sp(x, y, cr, cg, cb)

    # --- LISSAJO (Lissajous oscilloscope curve) ---
    def _lissajo_init(self):
        self._liss_phase = 0.0
        display.clear()

    def _lissajo_step(self):
        display.clear()
        cx = WIDTH * 0.5
        cy = HEIGHT * 0.5
        amp = (WIDTH - 6) * 0.5
        self._liss_phase += 0.04
        delta = self._liss_phase
        # Slowly morph the frequency ratio so the figure keeps reshaping.
        a = 3.0 + math.sin(self._frame * 0.0031) * 1.5
        b = 2.0 + math.cos(self._frame * 0.0023) * 1.5
        steps = 96 if CONFIG_LOW_RAM_MODE else 170
        base_hue = int(self._frame * 2)
        two_pi = 6.2831853
        sp = display.set_pixel
        for i in range(steps):
            t = i * two_pi / steps
            x = int(cx + amp * math.sin(a * t + delta))
            y = int(cy + amp * math.sin(b * t))
            if 0 <= x < WIDTH and 0 <= y < HEIGHT:
                cr, cg, cb = hsb_to_rgb((i * 360 // steps + base_hue) % 360, 1, 1)
                sp(x, y, cr, cg, cb)
                # A dim neighbour gives the trace a soft phosphor glow.
                if x + 1 < WIDTH:
                    sp(x + 1, y, cr // 3, cg // 3, cb // 3)

    # --- PENDUL (double pendulum) ---
    _PEND_CX = WIDTH // 2
    _PEND_CY = 26
    _PEND_L1 = 13.0
    _PEND_L2 = 13.0

    def _pendul_init(self):
        # Start near the top so the system has plenty of energy to go chaotic.
        self._pend_a1 = 3.14159 * 0.62 + random.uniform(-0.2, 0.2)
        self._pend_a2 = 3.14159 * 0.55 + random.uniform(-0.2, 0.2)
        self._pend_w1 = 0.0
        self._pend_w2 = 0.0
        self._pend_trail = []
        display.clear()

    def _pendul_step(self):
        display.clear()
        g = 1.2
        m1 = 1.0
        m2 = 1.0
        l1 = self._PEND_L1
        l2 = self._PEND_L2
        a1 = self._pend_a1
        a2 = self._pend_a2
        w1 = self._pend_w1
        w2 = self._pend_w2

        # Integrate several small steps per frame for numerical stability.
        dt = 0.10
        for _ in range(3):
            sin = math.sin
            cos = math.cos
            da = a1 - a2
            den = 2 * m1 + m2 - m2 * cos(2 * a1 - 2 * a2)
            a1_acc = (
                -g * (2 * m1 + m2) * sin(a1)
                - m2 * g * sin(a1 - 2 * a2)
                - 2 * sin(da) * m2 * (w2 * w2 * l2 + w1 * w1 * l1 * cos(da))
            ) / (l1 * den)
            a2_acc = (
                2 * sin(da) * (
                    w1 * w1 * l1 * (m1 + m2)
                    + g * (m1 + m2) * cos(a1)
                    + w2 * w2 * l2 * m2 * cos(da)
                )
            ) / (l2 * den)
            w1 += a1_acc * dt
            w2 += a2_acc * dt
            a1 += w1 * dt
            a2 += w2 * dt

        self._pend_a1 = a1
        self._pend_a2 = a2
        self._pend_w1 = w1
        self._pend_w2 = w2

        cx = self._PEND_CX
        cy = self._PEND_CY
        x1 = cx + l1 * math.sin(a1)
        y1 = cy + l1 * math.cos(a1)
        x2 = x1 + l2 * math.sin(a2)
        y2 = y1 + l2 * math.cos(a2)

        # Record the tip path; old points fade out.
        self._pend_trail.append((x2, y2))
        if len(self._pend_trail) > 48:
            self._pend_trail = self._pend_trail[-48:]
        n = len(self._pend_trail)
        for i, (tx, ty) in enumerate(self._pend_trail):
            ix = int(tx)
            iy = int(ty)
            if 0 <= ix < WIDTH and 0 <= iy < HEIGHT:
                tr, tg, tb = hsb_to_rgb((i * 6 + self._frame * 2) % 360, 1, (i + 1) / n)
                display.set_pixel(ix, iy, tr, tg, tb)

        ix1, iy1 = int(x1), int(y1)
        ix2, iy2 = int(x2), int(y2)
        draw_line(cx, cy, ix1, iy1, 150, 150, 160)
        draw_line(ix1, iy1, ix2, iy2, 200, 200, 210)
        # Pivot and the two bobs.
        display.set_pixel(cx, cy, 90, 90, 110)
        draw_rectangle(ix1 - 1, iy1 - 1, ix1 + 1, iy1 + 1, 80, 180, 255)
        draw_rectangle(ix2 - 1, iy2 - 1, ix2 + 1, iy2 + 1, 255, 220, 60)

    # --- ARCADE (self-playing Breakout attract demo) ---
    _ARC_COLS = 8
    _ARC_ROWS = 5
    _ARC_BRICK_W = 8
    _ARC_BRICK_H = 3
    _ARC_TOP = 7
    _ARC_PADDLE_W = 11
    _ARC_PADDLE_Y = 60

    def _arcade_init(self, joystick=None):
        self._arc_game = BreakoutGame({"settings": {"powerups": True}})
        self._arc_game.paddle_speed = 1
        self._arc_cpu = CpuPlayerJoystick(joystick, "BRKOUT", self._arc_game, duration_ms=24 * 60 * 60 * 1000)
        self._arc_game._start_round(show_hud=False)

    def _arcade_step(self, joystick=None):
        if self._arc_game is None or self._arc_cpu is None:
            self._arcade_init(joystick)
        if not self._arc_game._step_once(self._arc_cpu, show_win=False, show_hud=False):
            self._arcade_init(joystick)

    def _select_prev_next_demo(self, joystick):
        now = ticks_ms()
        if ticks_diff(now, self._last_move) <= self._move_delay:
            return

        d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT])
        if d == JOYSTICK_LEFT:
            self._advance_demo(-1, randomize=False)
        elif d == JOYSTICK_RIGHT:
            self._advance_demo(1, randomize=False)
        else:
            return

        self._demo_sound("select", self.idx, 50)
        try:
            gc.collect()
        except Exception:
            pass
        self._last_move = now

    def _advance_demo(self, step=1, randomize=None):
        if not self.demos:
            return
        if randomize is None:
            randomize = self.random_order
        if randomize and len(self.demos) > 1:
            next_idx = self.idx
            for _ in range(6):
                next_idx = random.randint(0, len(self.demos) - 1)
                if next_idx != self.idx:
                    break
            self.idx = next_idx
        else:
            self.idx = (self.idx + step) % len(self.demos)
        self._slide_started_ms = ticks_ms()
        self._reset_demo_state()

    def _maybe_auto_advance_demo(self):
        if self.slideshow_ms <= 0 or len(self.demos) <= 1:
            return False
        now = ticks_ms()
        if ticks_diff(now, self._slide_started_ms) < self.slideshow_ms:
            return False
        self._advance_demo(1, randomize=self.random_order)
        return True

    def _game_demo_class(self, name):
        cls_name = self.GAME_CLASS_NAMES.get(name)
        if not cls_name:
            return None
        return globals().get(cls_name)

    def _draw_game_demo_card(self, name):
        display.clear()
        draw_text(2, 10, name, 255, 255, 255)
        draw_text_small(2, 26, "CPU PLAYER", 120, 220, 255)
        draw_text_small(2, 36, "LR SELECT", 140, 140, 140)
        draw_text_small(2, 46, "C BACK", 140, 140, 140)
        self._draw_clock_overlay()
        display_score_and_time(0)

    def _handle_game_demo_entry(self, name, joystick):
        now = ticks_ms()
        if self._game_demo_name != name:
            self._game_demo_name = name
            self._game_demo_selected_ms = now
            self._draw_game_demo_card(name)
            return False
        if ticks_diff(now, self._game_demo_selected_ms) < self._game_demo_wait_ms:
            return False
        self._run_game_demo_sync(name, joystick)
        self._advance_demo(1, randomize=self.random_order)
        return True

    async def _handle_game_demo_entry_async(self, name, joystick):
        now = ticks_ms()
        if self._game_demo_name != name:
            self._game_demo_name = name
            self._game_demo_selected_ms = now
            self._draw_game_demo_card(name)
            try:
                display_flush()
            except Exception:
                pass
            return False
        if ticks_diff(now, self._game_demo_selected_ms) < self._game_demo_wait_ms:
            return False
        await self._run_game_demo_async(name, joystick)
        self._advance_demo(1, randomize=self.random_order)
        return True

    def _run_game_demo_sync(self, name, joystick):
        cls = self._game_demo_class(name)
        if cls is None:
            return
        game = cls()
        cpu = CpuPlayerJoystick(joystick, name, game, duration_ms=self.slideshow_ms)
        try:
            game.main_loop(cpu)
        except RestartProgram:
            raise
        except Exception:
            reset_menu_display(0)
        finally:
            self._reset_demo_state()
            display.clear()
            _wait_for_primary_release(joystick, timeout_ms=500)

    async def _run_game_demo_async(self, name, joystick):
        cls = self._game_demo_class(name)
        if cls is None:
            return
        game = cls()
        cpu = CpuPlayerJoystick(joystick, name, game, duration_ms=self.slideshow_ms)
        try:
            if hasattr(game, "main_loop_async"):
                await game.main_loop_async(cpu)
            else:
                game.main_loop(cpu)
        except RestartProgram:
            raise
        except Exception:
            reset_menu_display(0)
        finally:
            self._reset_demo_state()
            display.clear()
            await _wait_for_primary_release_async(joystick, timeout_ms=500)
            await yield_runtime(0)

    def _ensure_demo_initialized(self, demo, joystick=None):
        if self._init:
            return

        display.clear()
        # No HUD in demos: use full 64x64 for visuals.
        self._demo_sound("start", self.idx, 180)
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
            self._fire_init()
        elif demo == "MATRIX":
            self._matrix_init()
        elif demo == "STARS":
            self._stars_init()
        elif demo == "MYSTIFY":
            self._mystify_init()
        elif demo == "CUBE":
            self._cube_init()
        elif demo == "TUNNEL":
            self._tunnel_init()
        elif demo == "ORBIT":
            self._orbit_init()
        elif demo == "WARP":
            self._warp_init()
        elif demo == "VORTEX":
            self._vortex_init()
        elif demo == "COMETS":
            self._comets_init()
        elif demo == "BOUNCE":
            self._bounce_init()
        elif demo == "PLASMA":
            self._plasma_init()
        elif demo == "SPARK":
            self._spark_init()
        elif demo == "RINGS":
            self._rings_init()
        elif demo == "RADAR":
            self._radar_init()
        elif demo == "MANDEL":
            self._mandel_init()
        elif demo == "BOIDS":
            self._boids_init()
        elif demo == "NBODY":
            self._nbody_init()
        elif demo == "METAB":
            self._metab_init()
        elif demo == "GRAV":
            self._grav_init()
        elif demo == "SPRING":
            self._spring_init()
        elif demo == "CRADLE":
            self._cradle_init()
        elif demo == "RIPPLE":
            self._ripple_init()
        elif demo == "FIRWRK":
            self._firwrk_init()
        elif demo == "PHYLLO":
            self._phyllo_init()
        elif demo == "LISSAJO":
            self._lissajo_init()
        elif demo == "PENDUL":
            self._pendul_init()
        elif demo == "ARCADE":
            self._arcade_init(joystick)
        elif demo == "CRT":
            self._crt_init()
        elif demo == "WINMAZE":
            self._winmaze_init()
        else:
            self._snake_init()
        self._init = True

    def _step_current_demo(self, joystick=None):
        demo = self.demos[self.idx]
        self._ensure_demo_initialized(demo, joystick)

        if demo == "LIFE":
            self._life_step(self._life_w, self._life_h, self._life_cur, self._life_nxt)
            self._life_cur, self._life_nxt = self._life_nxt, self._life_cur
            self._life_draw_diffs(self._life_w, self._life_h, self._life_cur, self._life_prev)
        elif demo == "ANTS":
            self._ants_step()
        elif demo == "FLOOD":
            self._flood_step()
        elif demo == "FIRE":
            self._fire_step()
        elif demo == "MATRIX":
            self._matrix_step()
        elif demo == "STARS":
            self._stars_step()
        elif demo == "MYSTIFY":
            if not getattr(self, "_mystify_pts", None):
                self._mystify_init()
            self._mystify_step()
        elif demo == "CUBE":
            if not getattr(self, "_cube_vertices", None):
                self._cube_init()
            self._cube_step()
        elif demo == "TUNNEL":
            self._tunnel_step()
        elif demo == "ORBIT":
            self._orbit_step()
        elif demo == "WARP":
            self._warp_step()
        elif demo == "VORTEX":
            self._vortex_step()
        elif demo == "COMETS":
            self._comets_step()
        elif demo == "BOUNCE":
            self._bounce_step()
        elif demo == "PLASMA":
            if not getattr(self, "_plasma_palette", None):
                self._plasma_init()
            self._plasma_step()
        elif demo == "SPARK":
            self._spark_step()
        elif demo == "RINGS":
            self._rings_step()
        elif demo == "RADAR":
            self._radar_step()
        elif demo == "MANDEL":
            self._mandel_step()
        elif demo == "BOIDS":
            self._boids_step()
        elif demo == "NBODY":
            self._nbody_step()
        elif demo == "METAB":
            self._metab_step()
        elif demo == "GRAV":
            self._grav_step()
        elif demo == "SPRING":
            self._spring_step()
        elif demo == "CRADLE":
            self._cradle_step()
        elif demo == "RIPPLE":
            if self._ripple_cur is None:
                self._ripple_init()
            self._ripple_step()
        elif demo == "FIRWRK":
            self._firwrk_step()
        elif demo == "PHYLLO":
            self._phyllo_step()
        elif demo == "LISSAJO":
            self._lissajo_step()
        elif demo == "PENDUL":
            self._pendul_step()
        elif demo == "ARCADE":
            if self._arc_game is None:
                self._arcade_init(joystick)
            self._arcade_step(joystick)
        elif demo == "CRT":
            self._crt_step()
        elif demo == "WINMAZE":
            self._winmaze_step()
        else:
            self._snake_step()

    def _prepare_demo_loop(self):
        global game_over, global_score
        game_over = False
        global_score = 0

    def main_loop(self, joystick):
        self._prepare_demo_loop()
        frame_ms = self.FRAME_MS
        last_frame = ticks_ms()

        while True:
            c_button, _ = joystick.read_buttons()
            if c_button:
                return

            self._select_prev_next_demo(joystick)
            self._maybe_auto_advance_demo()
            demo = self.demos[self.idx]
            if demo.startswith("G:"):
                self._handle_game_demo_entry(demo[2:], joystick)
                last_frame = ticks_ms()
                sleep_ms(10)
                continue

            now = ticks_ms()
            if ticks_diff(now, last_frame) < frame_ms:
                sleep_ms(1)
                continue
            last_frame = now
            self._frame += 1
            self._step_current_demo(joystick)
            self._draw_clock_overlay()
            display_flush()
            maybe_collect(120)

    async def main_loop_async(self, joystick):
        """Async version for pygbag: yields with asyncio.sleep()."""
        if asyncio is None:
            return self.main_loop(joystick)

        self._prepare_demo_loop()
        frame_ms = self.FRAME_MS
        last_frame = ticks_ms()

        while True:
            c_button, _ = joystick.read_buttons()
            if c_button:
                return

            self._select_prev_next_demo(joystick)
            self._maybe_auto_advance_demo()
            demo = self.demos[self.idx]
            if demo.startswith("G:"):
                await self._handle_game_demo_entry_async(demo[2:], joystick)
                last_frame = ticks_ms()
                await asyncio.sleep(0.010)
                continue

            now = ticks_ms()
            if ticks_diff(now, last_frame) < frame_ms:
                await asyncio.sleep(0.001)
                continue
            last_frame = now
            self._frame += 1
            self._step_current_demo(joystick)
            self._draw_clock_overlay()
            display_flush()
            maybe_collect(120)
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
    # pad_x, pad_w, pad_y, terrain control points, fuel, gravity, thrust.
    # Profiles are deliberately fixed so each level can be checked for a clear,
    # reachable landing pad instead of relying on random terrain.
    LEVELS = (
        (25, 10, 48, (48, 46, 49, 47, 50), 760, 0.10, 0.30),
        (9, 10, 44, (42, 45, 43, 48, 46), 720, 0.105, 0.30),
        (45, 9, 42, (50, 47, 45, 43, 41), 700, 0.112, 0.31),
        (18, 9, 39, (46, 43, 40, 44, 48), 680, 0.118, 0.31),
        (36, 8, 36, (52, 47, 42, 38, 44), 650, 0.124, 0.32),
        (7, 8, 35, (39, 42, 45, 40, 37), 630, 0.130, 0.32),
        (49, 7, 33, (50, 45, 39, 35, 34), 610, 0.136, 0.33),
        (27, 7, 31, (44, 40, 36, 32, 38), 590, 0.142, 0.33),
    )

    @classmethod
    def _ensure_lut(cls):
        if cls._LUT is not None:
            return
        lut = []
        step = cls._STEP
        for a in range(0, 360, step):
            lut.append((int(math.cos(math.radians(a)) * 256), int(math.sin(math.radians(a)) * 256)))
        cls._LUT = lut

    def __init__(self, ctx=None):
        self.mode = get_context_setting(ctx, "mode", "classic")
        self.level = 1
        self.total_score = 0
        self.reset()

    def reset(self, keep_level=False):
        # Multi-level system: keep level on successful landing, reset on crash
        if not keep_level:
            self.level = 1
            self.total_score = 0
        
        profile = self.LEVELS[(self.level - 1) % len(self.LEVELS)]
        cycle = (self.level - 1) // len(self.LEVELS)
        self.terrain = self._make_terrain(profile, cycle)

        # Pad/fuel/gravity come from fixed profiles, with a small cap for
        # repeat cycles after the handcrafted set.
        self.pad_x = profile[0]
        self.pad_w = max(6, profile[1] - min(2, cycle))
        self.pad_y = profile[2]
        for x in range(self.pad_x, self.pad_x + self.pad_w):
            self.terrain[x] = self.pad_y

        self.x = float(WIDTH // 2)
        self.y = 8.0
        self.vx = 0.0
        self.vy = 0.0
        self.angle = 90

        self.fuel_max = max(470, int(profile[4] - cycle * 30))
        self.fuel = self.fuel_max

        self.g = profile[5] + cycle * 0.006
        self.thrust = profile[6]

        self.points = 300
        self.last_points_ms = ticks_ms()
        self.frame = 0

    def _make_terrain(self, profile, cycle=0):
        control = profile[3]
        span = WIDTH - 1
        t = [0] * WIDTH
        lo = PLAY_HEIGHT - 24
        hi = PLAY_HEIGHT - 4
        for x in range(WIDTH):
            pos = x * (len(control) - 1) / span
            i = int(pos)
            if i >= len(control) - 1:
                y = control[-1]
            else:
                frac = pos - i
                y = int(control[i] * (1.0 - frac) + control[i + 1] * frac)
            ripple = ((x * 7 + self.level * 5) % 5) - 2
            t[x] = clamp(y + ripple + min(2, cycle), lo, hi)

        # smooth
        for _ in range(2):
            for x in range(1, WIDTH - 1):
                t[x] = (t[x - 1] + t[x] + t[x + 1]) // 3
        return t

    def _cos_sin256(self, angle_deg):
        angle_deg %= 360
        self._ensure_lut()
        idx = (angle_deg // self._STEP) % (360 // self._STEP)
        return self._LUT[idx]

    def _angle_diff(self, a, b):
        d = (a - b + 180) % 360 - 180
        return abs(d)

    def _line(self, x0, y0, x1, y1, r, g, b):
        # Delegate to module-level Bresenham helper (shared with UFODefenseGame)
        draw_line(x0, y0, x1, y1, r, g, b)

    def _draw_ship(self, thrust_on=False):
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
        bar_w = 22
        filled = int((self.fuel / float(self.fuel_max)) * bar_w)
        if filled < 0:
            filled = 0
        if filled > bar_w:
            filled = bar_w

        draw_rectangle(0, 0, bar_w, 1, 40, 40, 40)
        if filled > 0:
            draw_rectangle(0, 0, filled - 1, 1, 255, 255, 0)

    def _reset_v2(self):
        self.level = 1
        self.total_score = 0
        self.world_w = 320
        self.v2_pads = []
        self.v2_powerups = []
        self.v2_target = 0
        self.v2_camera_x = 0
        self.v2_docked = False
        self.v2_docked_pad = -1
        self.v2_terrain = self._make_v2_terrain()
        self.x = 22.0
        self.y = 12.0
        self.vx = 0.0
        self.vy = 0.0
        self.angle = 90
        self.fuel_max = 900
        self.fuel = self.fuel_max
        self.g = 0.092
        self.thrust = 0.44
        self.points = 500
        self.last_points_ms = ticks_ms()
        self.frame = 0

    def _make_v2_terrain(self):
        t = [PLAY_HEIGHT - 8] * self.world_w
        pad_specs = ((18, 11, 47), (82, 10, 43), (145, 9, 39), (214, 9, 44), (284, 8, 36))
        for x in range(self.world_w):
            base = PLAY_HEIGHT - 10
            wave = int(math.sin(x * 0.075) * 7 + math.sin(x * 0.021 + 1.7) * 5)
            t[x] = clamp(base + wave, PLAY_HEIGHT - 25, PLAY_HEIGHT - 4)
        for _ in range(2):
            for x in range(1, self.world_w - 1):
                t[x] = (t[x - 1] + t[x] + t[x + 1]) // 3
        self.v2_pads = []
        for px, pw, py in pad_specs:
            self.v2_pads.append({"x": px, "w": pw, "y": py, "done": False})
            for x in range(px, min(self.world_w, px + pw)):
                t[x] = py
        self.v2_powerups = [
            {"x": 55, "y": 28, "kind": "FUEL", "on": True},
            {"x": 124, "y": 24, "kind": "FUEL", "on": True},
            {"x": 190, "y": 22, "kind": "FUEL", "on": True},
            {"x": 252, "y": 26, "kind": "FUEL", "on": True},
        ]
        return t

    def _v2_screen_x(self, world_x):
        return int(world_x - self.v2_camera_x)

    def _update_v2_camera(self):
        target = int(self.x) - WIDTH // 2
        self.v2_camera_x = clamp(target, 0, max(0, self.world_w - WIDTH))

    def _draw_terrain_v2(self):
        start = int(self.v2_camera_x)
        sp = display.set_pixel
        for sx in range(WIDTH):
            wx = start + sx
            if wx < 0 or wx >= self.world_w:
                continue
            ty = self.v2_terrain[wx]
            col = (0, 80, 145)
            for pad_i, pad in enumerate(self.v2_pads):
                if pad["x"] <= wx < pad["x"] + pad["w"] and ty == pad["y"]:
                    if pad_i == self.v2_target:
                        col = (0, 255, 0)
                    elif pad.get("done"):
                        col = (60, 130, 80)
                    else:
                        col = (100, 100, 100)
                    break
            for y in range(ty, PLAY_HEIGHT):
                sp(sx, y, col[0] // 2, col[1] // 2, col[2] // 2)
            sp(sx, ty, *col)

    def _draw_powerups_v2(self):
        phase = (self.frame // 4) & 1
        for p in self.v2_powerups:
            if not p["on"]:
                continue
            sx = self._v2_screen_x(p["x"])
            sy = int(p["y"])
            if -2 <= sx < WIDTH + 2:
                col = (255, 230, 40) if phase else (255, 120, 20)
                draw_rectangle(sx - 1, sy - 1, sx + 1, sy + 1, *col)

    def _draw_ship_v2(self, thrust_on=False):
        old_x = self.x
        self.x = self._v2_screen_x(old_x)
        self._draw_ship(thrust_on)
        self.x = old_x

    def _collect_powerups_v2(self):
        for p in self.v2_powerups:
            if not p["on"]:
                continue
            if abs(self.x - p["x"]) <= 3 and abs(self.y - p["y"]) <= 3:
                p["on"] = False
                self.fuel = min(self.fuel_max, self.fuel + 260)
                self.total_score += 75

    def _dock_v2(self, pad_i):
        pad = self.v2_pads[pad_i]
        self.v2_docked = True
        self.v2_docked_pad = pad_i
        self.x = float(pad["x"] + pad["w"] // 2)
        self.y = float(pad["y"] - 5)
        self.vx = 0.0
        self.vy = 0.0
        self.angle = 90

    def _v2_landing_result(self):
        ix = clamp(int(self.x), 0, self.world_w - 1)
        gy = self.v2_terrain[ix]
        if self.y < gy - 1:
            return None
        soft = abs(self.vx) < 0.70 and abs(self.vy) < 1.25
        upright = self._angle_diff(self.angle, 90) <= 25
        landed_pad_i = -1
        for i, pad in enumerate(self.v2_pads):
            if pad["x"] <= ix < pad["x"] + pad["w"] and gy == pad["y"]:
                landed_pad_i = i
                break
        if landed_pad_i >= 0 and soft and upright:
            pad = self.v2_pads[landed_pad_i]
            if landed_pad_i != self.v2_target:
                if pad.get("done"):
                    self._dock_v2(landed_pad_i)
                    self.fuel = min(self.fuel_max, self.fuel + 80)
                    return "docked"
                return "crash"
            pad["done"] = True
            self.total_score += self.points + int(self.fuel) + 250
            self.v2_target += 1
            if self.v2_target >= len(self.v2_pads):
                return "won"
            self.points = 500 + self.v2_target * 80
            self.fuel = min(self.fuel_max, self.fuel + 180)
            self._dock_v2(landed_pad_i)
            return "landed"
        return "crash"

    def _draw_v2_scene(self, thrust_on=False):
        self._update_v2_camera()
        display.clear()
        self._draw_terrain_v2()
        self._draw_powerups_v2()
        self._draw_ship_v2(thrust_on)
        self._draw_fuel_bar()
        target = self.v2_pads[min(self.v2_target, len(self.v2_pads) - 1)]
        tx = self._v2_screen_x(target["x"] + target["w"] // 2)
        if 0 <= tx < WIDTH:
            draw_text_small(clamp(tx - 3, 0, WIDTH - 12), 3, "V", 0, 255, 0)
        display_score_and_time(global_score)

    def _run_v2_frame(self, joystick):
        global game_over, global_score
        c_button, z_button = joystick.read_buttons()
        if c_button:
            return False
        now = ticks_ms()
        self.frame += 1
        if ticks_diff(now, self.last_points_ms) >= 500:
            self.last_points_ms = now
            if self.points > 0:
                self.points -= 1
        d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_UP])
        if d == JOYSTICK_LEFT:
            self.angle = (self.angle + 5) % 360
        elif d == JOYSTICK_RIGHT:
            self.angle = (self.angle - 5) % 360
        thrust_on = (z_button or d == JOYSTICK_UP) and self.fuel > 0
        if self.v2_docked:
            global_score = self.total_score + self.points
            if thrust_on:
                self.v2_docked = False
                self.v2_docked_pad = -1
                self.vy = -1.25
                self.y -= 2.0
            else:
                self._draw_v2_scene(False)
                return True
        ax = 0.0
        ay = self.g
        if thrust_on:
            c, s = self._cos_sin256(self.angle)
            ax += (c / 256.0) * self.thrust
            ay += (-s / 256.0) * self.thrust
            self.fuel -= 1
        self.vx = clamp(self.vx + ax, -2.8, 2.8)
        self.vy = clamp(self.vy + ay, -3.4, 3.0)
        self.x = clamp(self.x + self.vx, 1.0, self.world_w - 2.0)
        self.y = max(0.0, self.y + self.vy)
        self._collect_powerups_v2()
        result = self._v2_landing_result()
        if result == "crash":
            set_game_over_score(self.total_score)
            return False
        if result == "won":
            set_game_over_score(self.total_score, won=True)
            return False
        global_score = self.total_score + self.points
        self._draw_v2_scene(thrust_on)
        return True

    def _main_loop_v2(self, joystick):
        global game_over, global_score
        game_over = False
        global_score = 0
        self._reset_v2()
        frame_ms = 35
        last_frame = ticks_ms()
        while not game_over:
            if ticks_diff(ticks_ms(), last_frame) < frame_ms:
                sleep_ms(2)
                continue
            last_frame = ticks_ms()
            if not self._run_v2_frame(joystick):
                return

    async def _main_loop_v2_async(self, joystick):
        if asyncio is None:
            return self._main_loop_v2(joystick)
        global game_over, global_score
        game_over = False
        global_score = 0
        self._reset_v2()
        frame_ms = 35
        last_frame = ticks_ms()
        while not game_over:
            if ticks_diff(ticks_ms(), last_frame) < frame_ms:
                await asyncio.sleep(0.002)
                continue
            last_frame = ticks_ms()
            if not self._run_v2_frame(joystick):
                return

    def main_loop(self, joystick):
        if self.mode == "scroll":
            return self._main_loop_v2(joystick)
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()

        frame_ms = 35
        last_frame = ticks_ms()

        while not game_over:
            try:
                c_button, z_button = joystick.read_buttons()
                if c_button:
                    return

                now = ticks_ms()
                if ticks_diff(now, last_frame) < frame_ms:
                    sleep_ms(2)
                    continue
                last_frame = now
                self.frame += 1

                # time bonus counts down (faster landing = more points)
                if ticks_diff(now, self.last_points_ms) >= 500:
                    self.last_points_ms = now
                    if self.points > 0:
                        self.points -= 1

                # input
                d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_UP])
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
                if self.vx > 2.2: self.vx = 2.2
                if self.vx < -2.2: self.vx = -2.2
                if self.vy > 3.0: self.vy = 3.0
                if self.vy < -3.0: self.vy = -3.0

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
                    on_pad = (self.pad_x <= ix <= (self.pad_x + self.pad_w - 1))
                    soft = (abs(self.vx) < 0.65 and abs(self.vy) < 1.2)
                    upright = (self._angle_diff(self.angle, 90) <= 25)

                    if on_pad and soft and upright:
                        # Successful landing: award points and advance level
                        level_bonus = self.points + int(self.fuel) + 200 + (self.level * 150)
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
                        global_score = self.total_score if hasattr(self, 'total_score') else self.points
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

    async def main_loop_async(self, joystick):
        """Async version for pygbag: yields with asyncio.sleep()."""
        if asyncio is None:
            return self.main_loop(joystick)
        if self.mode == "scroll":
            return await self._main_loop_v2_async(joystick)

        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()

        frame_ms = 35
        last_frame = ticks_ms()

        while not game_over:
            try:
                c_button, z_button = joystick.read_buttons()
                if c_button:
                    return

                now = ticks_ms()
                if ticks_diff(now, last_frame) < frame_ms:
                    await asyncio.sleep(0.002)
                    continue
                last_frame = now
                self.frame += 1

                # time bonus counts down (faster landing = more points)
                if ticks_diff(now, self.last_points_ms) >= 500:
                    self.last_points_ms = now
                    if self.points > 0:
                        self.points -= 1

                # input
                d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_UP])
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
                if self.vx > 2.2: self.vx = 2.2
                if self.vx < -2.2: self.vx = -2.2
                if self.vy > 3.0: self.vy = 3.0
                if self.vy < -3.0: self.vy = -3.0

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
                    on_pad = (self.pad_x <= ix <= (self.pad_x + self.pad_w - 1))
                    soft = (abs(self.vx) < 0.65 and abs(self.vy) < 1.2)
                    upright = (self._angle_diff(self.angle, 90) <= 25)

                    if on_pad and soft and upright:
                        # Successful landing: award points and advance level
                        level_bonus = self.points + int(self.fuel) + 200 + (self.level * 150)
                        self.total_score += level_bonus
                        global_score = self.total_score
                        
                        display.clear()
                        draw_text(2, 12, "LVL" + str(self.level), 0, 255, 0)
                        draw_text(2, 24, "DONE", 0, 255, 0)
                        display_score_and_time(global_score)
                        await asyncio.sleep(1.8)
                        
                        # Next level
                        self.level += 1
                        self.reset(keep_level=True)
                        
                        # Short preview of new terrain
                        display.clear()
                        self._draw_terrain()
                        draw_text(2, 4, "LVL" + str(self.level), 255, 255, 0)
                        display_score_and_time(global_score)
                        await asyncio.sleep(1.5)
                        
                        last_frame = ticks_ms()
                        continue
                    else:
                        global_score = self.total_score if hasattr(self, 'total_score') else self.points
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
                    try:
                        gc.collect()
                    except Exception:
                        pass

            except RestartProgram:
                return


class KerbalGame:
    """
    KERBAL
    Controls:
      - Left / Right: rotate rocket
      - Z or Up: thrust
      - C: return to menu
    Arcade orbital flight: launch, circularize, optionally return and land.
    """
    FRAME_MS = 35
    PLANET_R = 18.0
    MU = 34.0
    SCALE = 1.28

    def __init__(self, ctx=None):
        self.mission = get_context_setting(ctx, "mission", "orbit")
        self.assist = bool(get_context_setting(ctx, "assist", True))
        self.reset()

    def reset(self):
        self.cx = 0.0
        self.cy = 0.0
        self.x = 0.0
        self.y = -self.PLANET_R - 2.0
        self.vx = 0.0
        self.vy = 0.0
        self.angle = 90
        self.fuel_max = 860
        self.fuel = self.fuel_max
        self.thrust = 0.090
        self.score = 0
        self.orbit_hold = 0
        self.return_ready = False
        self.landed = False
        self.frame = 0
        self.prelaunch = True
        self.launch_grace = 0
        self.trail = []
        self.max_trail = 54
        self.last_score_ms = ticks_ms()

    def _cos_sin(self, angle_deg):
        a = math.radians(angle_deg % 360)
        return math.cos(a), math.sin(a)

    def _radius(self):
        return math.sqrt(self.x * self.x + self.y * self.y) + 1e-6

    def _surface_alt(self):
        return self._radius() - self.PLANET_R

    def _radial_tangent_speed(self):
        r = self._radius()
        ux = self.x / r
        uy = self.y / r
        radial = self.vx * ux + self.vy * uy
        tangent = self.vx * (-uy) + self.vy * ux
        return radial, tangent

    def _orbit_quality(self):
        alt = self._surface_alt()
        radial, tangent = self._radial_tangent_speed()
        target = math.sqrt(self.MU / max(8.0, self._radius()))
        alt_ok = 8.0 <= alt <= 24.0
        speed_ok = abs(abs(tangent) - target) < (0.20 if self.assist else 0.14)
        radial_ok = abs(radial) < (0.18 if self.assist else 0.10)
        return alt_ok and speed_ok and radial_ok, alt, target, radial, tangent

    def _screen(self, wx, wy):
        return int(WIDTH // 2 + wx * self.SCALE), int(PLAY_HEIGHT // 2 + wy * self.SCALE)

    def _draw_planet(self):
        px, py = self._screen(0, 0)
        r = int(self.PLANET_R * self.SCALE)
        for deg in range(0, 360, 10):
            a = math.radians(deg)
            x = px + int(math.cos(a) * r)
            y = py + int(math.sin(a) * r)
            if 0 <= x < WIDTH and 0 <= y < PLAY_HEIGHT:
                display.set_pixel(x, y, 40, 120, 255)
        for deg in range(0, 360, 30):
            a = math.radians(deg)
            x = px + int(math.cos(a) * (r - 2))
            y = py + int(math.sin(a) * (r - 2))
            if 0 <= x < WIDTH and 0 <= y < PLAY_HEIGHT:
                display.set_pixel(x, y, 20, 80, 160)

    def _draw_orbit_band(self):
        px, py = self._screen(0, 0)
        for rr, col in ((int((self.PLANET_R + 8.0) * self.SCALE), (25, 70, 25)),
                        (int((self.PLANET_R + 24.0) * self.SCALE), (25, 70, 25))):
            for deg in range(0, 360, 18):
                a = math.radians(deg)
                x = px + int(math.cos(a) * rr)
                y = py + int(math.sin(a) * rr)
                if 0 <= x < WIDTH and 0 <= y < PLAY_HEIGHT:
                    display.set_pixel(x, y, *col)

    def _record_trail(self):
        if (self.frame & 1) != 0:
            return
        self.trail.append((self.x, self.y))
        if len(self.trail) > self.max_trail:
            self.trail.pop(0)

    def _draw_trail(self):
        n = len(self.trail)
        if n < 2:
            return
        for i, (tx, ty) in enumerate(self.trail):
            sx, sy = self._screen(tx, ty)
            if 0 <= sx < WIDTH and 0 <= sy < PLAY_HEIGHT:
                level = 45 + int(130 * (i + 1) / n)
                display.set_pixel(sx, sy, 20, level, 170)

    def _draw_flight_cues(self):
        sx, sy = self._screen(self.x, self.y)
        speed = math.sqrt(self.vx * self.vx + self.vy * self.vy)
        if speed > 0.08:
            vx = self.vx / speed
            vy = self.vy / speed
            px = sx + int(vx * 6)
            py = sy + int(vy * 6)
            set_pixel_clipped(px, py, 80, 255, 255)
            if self.return_ready:
                rx = sx - int(vx * 6)
                ry = sy - int(vy * 6)
                set_pixel_clipped(rx, ry, 255, 130, 40)
        if self.assist:
            c, s = self._cos_sin(self.angle)
            ax = sx + int(c * 7)
            ay = sy - int(s * 7)
            set_pixel_clipped(ax, ay, 255, 255, 70)

    def _draw_ship(self, thrust_on):
        sx, sy = self._screen(self.x, self.y)
        c, s = self._cos_sin(self.angle)
        nose = (sx + int(c * 4), sy - int(s * 4))
        left = (sx + int(math.cos(math.radians(self.angle + 140)) * 3),
                sy - int(math.sin(math.radians(self.angle + 140)) * 3))
        right = (sx + int(math.cos(math.radians(self.angle - 140)) * 3),
                 sy - int(math.sin(math.radians(self.angle - 140)) * 3))
        draw_line(nose[0], nose[1], left[0], left[1], 255, 255, 255)
        draw_line(nose[0], nose[1], right[0], right[1], 255, 255, 255)
        draw_line(left[0], left[1], right[0], right[1], 255, 255, 255)
        if thrust_on:
            fx = sx - int(c * 5)
            fy = sy + int(s * 5)
            draw_line(sx, sy, fx, fy, 255, 100, 0)

    def _draw_hud(self, alt, target_speed, radial, tangent):
        draw_rectangle(0, PLAY_HEIGHT, WIDTH - 1, HEIGHT - 1, 0, 0, 0)
        fuel_w = int(20 * max(0, self.fuel) / self.fuel_max)
        draw_rectangle(1, PLAY_HEIGHT + 1, 20, PLAY_HEIGHT + 2, 45, 45, 45)
        if fuel_w > 0:
            draw_rectangle(1, PLAY_HEIGHT + 1, fuel_w, PLAY_HEIGHT + 2, 255, 210, 30)
        draw_text_small(24, PLAY_HEIGHT, "A" + str(max(0, int(alt))), 180, 220, 255)
        if self.prelaunch:
            draw_text_small(43, PLAY_HEIGHT, "GO", 255, 255, 90)
        elif self.return_ready:
            label = "LND" if alt < 7 else "RET"
            draw_text_small(43, PLAY_HEIGHT, label, 120, 255, 120)
        else:
            diff = int(abs(abs(tangent) - target_speed) * 10)
            draw_text_small(46, PLAY_HEIGHT, "D" + str(min(9, diff)), 180, 180, 180)
            hold_w = int(17 * min(110, self.orbit_hold) / 110)
            draw_rectangle(25, PLAY_HEIGHT + 4, 42, PLAY_HEIGHT + 4, 28, 28, 28)
            if hold_w > 0:
                draw_rectangle(25, PLAY_HEIGHT + 4, 24 + hold_w, PLAY_HEIGHT + 4, 80, 255, 120)

    def _draw(self, thrust_on, alt, target_speed, radial, tangent):
        display.clear()
        self._draw_orbit_band()
        self._draw_trail()
        self._draw_planet()
        self._draw_flight_cues()
        self._draw_ship(thrust_on)
        ok, _alt, _target, _radial, _tangent = self._orbit_quality()
        if ok:
            draw_text_small(25, 2, "ORB", 80, 255, 120)
        self._draw_hud(alt, target_speed, radial, tangent)
        display_flush()

    def _step(self, joystick):
        global game_over, global_score
        c_button, z_button = joystick.read_buttons()
        if c_button:
            return False
        d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_UP], debounce=False)
        if d == JOYSTICK_LEFT:
            self.angle = (self.angle + 4) % 360
        elif d == JOYSTICK_RIGHT:
            self.angle = (self.angle - 4) % 360
        thrust_on = (z_button or d == JOYSTICK_UP) and self.fuel > 0

        if self.prelaunch:
            if thrust_on:
                self.prelaunch = False
                self.launch_grace = 80
                self.vx = 0.08
                self.vy = -0.10
                self.trail = []
            else:
                ok, alt, target_speed, radial, tangent = self._orbit_quality()
                global_score = 0
                self._draw(False, alt, target_speed, radial, tangent)
                return True

        r = self._radius()
        gx = -self.MU * self.x / (r * r * r)
        gy = -self.MU * self.y / (r * r * r)
        ax = gx
        ay = gy
        if thrust_on:
            c, s = self._cos_sin(self.angle)
            ax += c * self.thrust
            ay += -s * self.thrust
            self.fuel -= 1
        if self.assist and self._surface_alt() < 5 and self.vy > 0:
            self.vy *= 0.995
        if self.assist and self.launch_grace > 0 and self._surface_alt() < 7:
            self.vy *= 0.970

        self.vx = clamp(self.vx + ax, -1.55, 1.55)
        self.vy = clamp(self.vy + ay, -1.55, 1.55)
        if self.assist and not self.return_ready:
            alt_now = self._surface_alt()
            if self.launch_grace > 0 or alt_now < 28:
                r = self._radius()
                ux = self.x / r
                uy = self.y / r
                radial = self.vx * ux + self.vy * uy
                cap = 0.72 if self.launch_grace > 0 else 0.95
                if radial > cap:
                    excess = radial - cap
                    self.vx -= excess * ux
                    self.vy -= excess * uy
        self.x += self.vx
        self.y += self.vy
        self.frame += 1
        if self.launch_grace > 0:
            self.launch_grace -= 1
        self._record_trail()

        ok, alt, target_speed, radial, tangent = self._orbit_quality()
        if ok:
            self.orbit_hold += 1
            self.score += 2
        else:
            self.orbit_hold = max(0, self.orbit_hold - 2)

        if self.orbit_hold >= 110:
            if self.mission == "orbit":
                set_game_over_score(self.score + int(self.fuel), won=True)
                return False
            self.return_ready = True

        if self._radius() <= self.PLANET_R + 1.0:
            speed = math.sqrt(self.vx * self.vx + self.vy * self.vy)
            upright = abs(((self.angle - 90 + 180) % 360) - 180) < 32
            if self.return_ready and speed < 0.75 and upright:
                set_game_over_score(self.score + int(self.fuel) + 500, won=True)
            elif self.launch_grace > 0:
                r = self._radius()
                ux = self.x / r
                uy = self.y / r
                self.x = ux * (self.PLANET_R + 1.4)
                self.y = uy * (self.PLANET_R + 1.4)
                inward = self.vx * ux + self.vy * uy
                if inward < 0:
                    self.vx -= inward * ux
                    self.vy -= inward * uy
                self.vx *= 0.72
                self.vy *= 0.72
                global_score = self.score
                self._draw(thrust_on, alt, target_speed, radial, tangent)
                return True
            else:
                set_game_over_score(self.score)
            return False

        if self._radius() > 58 or self.fuel <= 0 and self._surface_alt() > 32 and not ok:
            set_game_over_score(self.score)
            return False

        global_score = self.score + int(max(0, alt))
        self._draw(thrust_on, alt, target_speed, radial, tangent)
        return True

    def _build_step(self, joystick):
        self.reset()
        begin_game(0)
        def step():
            return self._step(joystick)
        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class UFODefenseGame:
    """
    UFO DEFENSE / Missile Command Mini
    Steuerung:
      - Stick: Fadenkreuz bewegen
      - Z: Rakete starten
      - C: zurück ins Menü
    """
    FRAME_MS = 35
    TURRETS = (4, 32, 59)
    DIRS_8 = (
        JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT,
        JOYSTICK_UP_LEFT, JOYSTICK_UP_RIGHT, JOYSTICK_DOWN_LEFT, JOYSTICK_DOWN_RIGHT,
    )

    def __init__(self, ctx=None):
        self.launcher_mode = get_context_setting(ctx, "launcher", "turrets")
        self.spawn_mode = get_context_setting(ctx, "spawns", "wave")
        self.blast_style = get_context_setting(ctx, "blast", "filled")
        self.chain_reactions = bool(get_context_setting(ctx, "chain", True))
        self.reset()

    def reset(self):
        self.score = 0

        self.base_x = WIDTH // 2
        self.base_y = PLAY_HEIGHT - 1

        self.cx = WIDTH // 2
        self.cy = PLAY_HEIGHT // 3

        self.player_missiles = []
        self.enemy_missiles = []
        self.explosions = []

        self.shot_cd = 0

        xs = [12, 19, 26, 38, 45, 52]
        self.cities = [{"x": x, "alive": True} for x in xs]

        self.spawn_ms = 850
        self.wave_spawn_ms = 950
        self.min_spawn_ms = 260
        self.last_spawn = ticks_ms()
        self.base_enemy_speed = 0.4
        self.max_enemy_speed = 2.0
        self.enemy_speed = self.base_enemy_speed
        self.level = 1
        self.to_spawn = 6
        self.frame = 0
        self.start_ms = ticks_ms()
        # crosshair movement smoothing: ms between pixel moves (tweakable)
        self.cross_move_ms = 28
        self._last_cross_move = ticks_ms()

    def _line(self, x0, y0, x1, y1, col):
        # Delegate to module-level Bresenham helper (shared with LunarLanderGame)
        r, g, b = col
        draw_line(x0, y0, x1, y1, r, g, b)

    def _cities_alive(self):
        for c in self.cities:
            if c["alive"]:
                return True
        return False

    def _damage_city_at(self, x):
        for c in self.cities:
            if c["alive"] and abs(c["x"] - x) <= 3:
                c["alive"] = False
                break

    def _enemy_targets(self):
        targets = [c["x"] for c in self.cities if c["alive"]]
        if self.launcher_mode == "base":
            targets.append(self.base_x)
        if not targets:
            targets = [self.base_x] if self.launcher_mode == "base" else list(self.TURRETS)
        return targets

    def _spawn_enemy(self):
        targets = self._enemy_targets()
        tgt = targets[random.randint(0, len(targets) - 1)]

        sx = random.randint(0, WIDTH - 1)
        sy = 0
        tx = tgt
        ty = self.base_y + 1

        dx = tx - sx
        dy = ty - sy
        if self.spawn_mode == "wave":
            spd = min(1.15, 0.30 + 0.09 * self.level)
            steps = max(1.0, self.base_y / spd)
            vx = dx / steps
            vy = spd
        else:
            dist = math.sqrt(dx * dx + dy * dy) + 1e-6
            spd = self.enemy_speed
            vx = dx / dist * spd
            vy = dy / dist * spd

        self.enemy_missiles.append({
            "x": float(sx), "y": float(sy),
            "px": float(sx), "py": float(sy),
            "tx": float(tx), "ty": float(ty),
            "vx": vx, "vy": vy
        })

    def _enemy_cap(self, now):
        # time-based caps: 0-60s -> 2, 60-180s -> 4, 180-300s -> 6, afterwards 6
        elapsed = ticks_diff(now, getattr(self, 'start_ms', now))
        if elapsed < 60_000:
            return 2
        if elapsed < 180_000:
            return 4
        return 6

    def _launcher_x(self):
        if self.launcher_mode != "turrets":
            return self.base_x
        bx = self.TURRETS[0]
        for t in self.TURRETS:
            if abs(t - self.cx) < abs(bx - self.cx):
                bx = t
        return bx

    def _fire_player(self):
        sx = self._launcher_x()
        sy = self.base_y
        tx = self.cx
        ty = self.cy

        dx = tx - sx
        dy = ty - sy
        dist = math.sqrt(dx * dx + dy * dy) + 1e-6
        spd = 3.2 if self.launcher_mode == "turrets" else 2.9
        vx = dx / dist * spd
        vy = dy / dist * spd

        self.player_missiles.append({
            "x": float(sx), "y": float(sy),
            "px": float(sx), "py": float(sy),
            "tx": float(tx), "ty": float(ty),
            "vx": vx, "vy": vy
        })

    def _add_explosion(self, x, y, max_r, color):
        self.explosions.append({"x": float(x), "y": float(y), "r": 0, "dr": 1, "max": max_r, "col": color})

    def _draw_explosion(self, ex):
        r = ex["r"]
        if r <= 0:
            return
        x0 = ex["x"]; y0 = ex["y"]
        col = ex["col"]
        sp = display.set_pixel
        if self.blast_style == "filled":
            ir = int(r)
            r2 = r * r
            icx = int(x0)
            icy = int(y0)
            for dy in range(-ir, ir + 1):
                yy = icy + dy
                if yy < 0 or yy >= PLAY_HEIGHT:
                    continue
                for dx in range(-ir, ir + 1):
                    if dx * dx + dy * dy <= r2:
                        xx = icx + dx
                        if 0 <= xx < WIDTH:
                            sp(xx, yy, col[0], col[1], col[2])
            return

        for deg in range(0, 360, 18):
            a = math.radians(deg)
            x = int(x0 + math.cos(a) * r)
            y = int(y0 + math.sin(a) * r)
            if 0 <= x < WIDTH and 0 <= y < PLAY_HEIGHT:
                sp(x, y, col[0], col[1], col[2])

    def _update_explosions_and_hits(self):
        active_explosions = []
        chain_explosions = []
        for ex in self.explosions:
            ex["r"] += ex["dr"]
            if ex["r"] >= ex["max"]:
                ex["dr"] = -1
            if ex["r"] <= 0 and ex["dr"] < 0:
                continue

            r2 = (ex["r"] + 1) * (ex["r"] + 1)
            exx = ex["x"]; exy = ex["y"]

            keep_enemy = []
            for em in self.enemy_missiles:
                dx = em["x"] - exx
                dy = em["y"] - exy
                if dx * dx + dy * dy <= r2:
                    self.score += 10
                    if self.chain_reactions:
                        chain_explosions.append({
                            "x": float(em["x"]), "y": float(em["y"]),
                            "r": 0, "dr": 1, "max": 5,
                            "col": (255, 110, 30),
                        })
                    continue
                keep_enemy.append(em)
            self.enemy_missiles = keep_enemy
            active_explosions.append(ex)
        self.explosions = active_explosions + chain_explosions

    def _update_missiles(self):
        global game_over, global_score

        # player
        keep_player = []
        for m in self.player_missiles:
            m["px"], m["py"] = m["x"], m["y"]
            m["x"] += m["vx"]
            m["y"] += m["vy"]
            dx = m["x"] - m["tx"]
            dy = m["y"] - m["ty"]
            if dx * dx + dy * dy <= 7.0:
                self._add_explosion(m["tx"], m["ty"], 7 if self.blast_style == "filled" else 6, (255, 180, 0))
                continue
            elif m["y"] < 0 or m["y"] >= PLAY_HEIGHT:
                continue
            keep_player.append(m)
        self.player_missiles = keep_player

        # enemy
        keep_enemy = []
        for m in self.enemy_missiles:
            m["px"], m["py"] = m["x"], m["y"]
            m["x"] += m["vx"]
            m["y"] += m["vy"]
            if m["y"] >= m["ty"] or m["y"] >= PLAY_HEIGHT - 1:
                ix = int(m["x"])
                iy = int(m["y"])
                self._add_explosion(ix, iy, 5, (255, 60, 60))

                if self.launcher_mode == "base" and abs(ix - self.base_x) <= 3:
                    global_score = self.score
                    game_over = True
                    return

                self._damage_city_at(ix)
                if not self._cities_alive():
                    global_score = self.score
                    game_over = True
                    return
            else:
                keep_enemy.append(m)
        self.enemy_missiles = keep_enemy

    def _advance_spawning(self, now):
        if self.spawn_mode == "wave":
            if self.to_spawn > 0 and ticks_diff(now, self.last_spawn) >= self.wave_spawn_ms:
                self._spawn_enemy()
                self.to_spawn -= 1
                self.last_spawn = now
            elif self.to_spawn == 0 and not self.enemy_missiles:
                self.score += 35 * self.level
                self.level += 1
                self.to_spawn = 6 + self.level
                if self.wave_spawn_ms > 360:
                    self.wave_spawn_ms -= 60
            return

        if ticks_diff(now, self.last_spawn) >= self.spawn_ms:
            self.last_spawn = now
            cap = self._enemy_cap(now)
            if len(self.enemy_missiles) < cap:
                self._spawn_enemy()
            self.level += 1
            self.spawn_ms = max(self.min_spawn_ms, 850 - self.level * 10)
            self.enemy_speed = min(self.max_enemy_speed, self.base_enemy_speed + self.level * 0.01)

    def _move_crosshair(self, joystick, now):
        d = joystick.read_direction(self.DIRS_8, debounce=False)
        if not d or ticks_diff(now, self._last_cross_move) < self.cross_move_ms:
            return
        dx, dy = direction_to_delta_8way(d)
        if dx or dy:
            self.cx = clamp(self.cx + dx * 2, 1, WIDTH - 2)
            self.cy = clamp(self.cy + dy * 2, 2, PLAY_HEIGHT - 8)
            self._last_cross_move = now

    def _draw_world(self):
        display.clear()
        sp = display.set_pixel
        draw_rectangle(0, self.base_y, WIDTH - 1, self.base_y, 60, 40, 20)

        # cities
        city_y = PLAY_HEIGHT - 4
        for c in self.cities:
            if c["alive"]:
                x = c["x"]
                draw_rectangle(x - 1, city_y, x + 1, city_y + 1, 0, 255, 0)

        # base / turrets
        by = self.base_y
        if self.launcher_mode == "turrets":
            for t in self.TURRETS:
                draw_rectangle(t - 1, by - 1, t + 1, by, 120, 120, 140)
                if 0 <= t < WIDTH and 0 <= by - 2 < PLAY_HEIGHT:
                    sp(t, by - 2, 180, 180, 200)
        else:
            bx = self.base_x
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

        draw_text_small(1, 1, "W" + str(self.level), 170, 170, 170)

        display_score_and_time(self.score)

    def main_loop(self, joystick):
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()

        frame_ms = 35
        last_frame = ticks_ms()

        while not game_over:
            try:
                c_button, z_button = joystick.read_buttons()
                if c_button:
                    return

                now = ticks_ms()

                self._move_crosshair(joystick, now)

                # shoot
                if self.shot_cd > 0:
                    self.shot_cd -= 1
                if z_button and self.shot_cd == 0 and len(self.player_missiles) < 4:
                    self._fire_player()
                    self.shot_cd = 8

                self._advance_spawning(now)

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

    async def main_loop_async(self, joystick):
        """Async version for pygbag/browser runtimes."""
        if asyncio is None:
            return self.main_loop(joystick)
        global game_over, global_score
        game_over = False
        global_score = 0
        self.reset()
        frame_ms = 35
        last_frame = ticks_ms()
        while not game_over:
            try:
                c_button, z_button = joystick.read_buttons()
                if c_button:
                    return
                now = ticks_ms()
                self._move_crosshair(joystick, now)
                if self.shot_cd > 0:
                    self.shot_cd -= 1
                if z_button and self.shot_cd == 0 and len(self.player_missiles) < 4:
                    self._fire_player()
                    self.shot_cd = 8
                self._advance_spawning(now)
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
                    try:
                        gc.collect()
                    except Exception:
                        pass
            except RestartProgram:
                return

# -----------------------------
# DOOM-LITE / RAYCASTER GAME
# -----------------------------
try:
    from array import array
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

    # Maps: 16x16, '#' = Wand, '.' = frei
    MAP_W = 16
    MAP_H = 16
    MAPS = ((
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
    ), (
        b"################",
        b"#.....#........#",
        b"#.###.#.######.#",
        b"#.#...#......#.#",
        b"#.#.####.###.#.#",
        b"#.#......#...#.#",
        b"#.######.#.###.#",
        b"#........#.....#",
        b"#.####.#####.#.#",
        b"#....#.....#.#.#",
        b"####.#####.#.#.#",
        b"#....#.....#...#",
        b"#.##.#.#######.#",
        b"#....#.........#",
        b"#.###########..#",
        b"################",
    ), (
        b"################",
        b"#........#.....#",
        b"#.######.#.###.#",
        b"#.#......#...#.#",
        b"#.#.########.#.#",
        b"#.#..........#.#",
        b"#.####.#######.#",
        b"#......#.......#",
        b"#.######.#####.#",
        b"#.#......#.....#",
        b"#.#.####.#.###.#",
        b"#.#....#.#...#.#",
        b"#.####.#.###.#.#",
        b"#......#.....#.#",
        b"#..#########...#",
        b"################",
    ), (
        b"################",
        b"#..............#",
        b"#.####.##.####.#",
        b"#.#....##....#.#",
        b"#.#.##.##.##.#.#",
        b"#...##....##...#",
        b"###.########.###",
        b"#..............#",
        b"#.####....####.#",
        b"#....#.##.#....#",
        b"####.#.##.#.####",
        b"#....#....#....#",
        b"#.##.######.##.#",
        b"#..............#",
        b"#..##########..#",
        b"################",
    ), (
        b"################",
        b"#..............#",
        b"#.##.######.##.#",
        b"#.#..........#.#",
        b"#.#.###..###.#.#",
        b"#...#......#...#",
        b"###.#.####.#.###",
        b"#.....#..#.....#",
        b"#.###.#..#.###.#",
        b"#...#......#...#",
        b"#.#.########.#.#",
        b"#.#..........#.#",
        b"#.##.######.##.#",
        b"#..............#",
        b"#..##########..#",
        b"################",
    ), (
        b"################",
        b"#..............#",
        b"#.####....####.#",
        b"#....#.##.#....#",
        b"####.#.##.#.####",
        b"#....#....#....#",
        b"#.##.######.##.#",
        b"#.#..........#.#",
        b"#.#.###..###.#.#",
        b"#...#......#...#",
        b"###.#.####.#.###",
        b"#.....#..#.....#",
        b"#.###.#..#.###.#",
        b"#..............#",
        b"#..##########..#",
        b"################",
    ))
    STARTS = ((2.5, 2.5), (1.5, 1.5), (2.5, 13.5), (1.5, 7.5), (1.5, 1.5), (1.5, 13.5))

    # Raycaster Parameter
    ANGLE_MAX = 256               # 0..255 entspricht 0..360°
    FOV = 48                      # ~67.5° (48/256 * 360)
    HALF_FOV = FOV // 2
    MAX_STEPS = 36
    MAX_DIST = 32.0

    # LUT für sin/cos (256 Steps, Scale 1024)
    # Lazy init to avoid large import-time allocations on MicroPython.
    _COS = None
    _SIN = None

    @classmethod
    def _ensure_trig(cls):
        if cls._COS is not None and cls._SIN is not None:
            return
        try:
            gc.collect()
        except Exception:
            pass

        if CONFIG_LOW_RAM_MODE and array:
            cos_lut = array('h')
            sin_lut = array('h')
            for i in range(256):
                ang = 2 * math.pi * i / 256
                cos_lut.append(int(math.cos(ang) * 1024))
                sin_lut.append(int(math.sin(ang) * 1024))
            cls._COS = cos_lut
            cls._SIN = sin_lut
        elif array:
            cos_lut = array('f')
            sin_lut = array('f')
            for i in range(256):
                ang = 2 * math.pi * i / 256
                cos_lut.append(math.cos(ang))
                sin_lut.append(math.sin(ang))
            cls._COS = cos_lut
            cls._SIN = sin_lut
        else:
            cos_lut = []
            sin_lut = []
            for i in range(256):
                ang = 2 * math.pi * i / 256
                if CONFIG_LOW_RAM_MODE:
                    cos_lut.append(int(math.cos(ang) * 1024))
                    sin_lut.append(int(math.sin(ang) * 1024))
                else:
                    cos_lut.append(math.cos(ang))
                    sin_lut.append(math.sin(ang))
            cls._COS = cos_lut
            cls._SIN = sin_lut

    def __init__(self):
        self._ensure_trig()
        self.zbuf = [self.MAX_DIST] * WIDTH  # Wanddistanz pro Screen-Spalte
        self.MAP = self.MAPS[0]
        self.level = 1
        self._minimap_walls = []
        self._minimap_initialized = False
        self._minimap_prev_player = None
        self._minimap_prev_aim = None
        self._minimap_prev_enemies = []
        self.render_hud = True
        self.render_minimap = True
        self.render_crosshair = True
        self.render_enemies = True
        self._attract_dir = 0
        self._attract_target_ang = 0
        self.reset()

    def reset(self):
        self.level = 1
        self._set_level(self.level)
        # Player (Map-Koordinaten, 1 Tile = 1.0)
        self.px, self.py = self.STARTS[0]
        self.ang = 0  # 0 = nach rechts

        self.score = 0
        self.lives = 3
        self.wave = 1

        self.shot_cd = 0
        self.wave_announce = 0  # frames left to show wave banner
        self.hit_flash = 0      # frames left to flash crosshair on hit
        self.dmg_flash = 0      # frames left to flash screen red when damaged

        self.enemies = []
        self._spawn_wave(self.wave)

        self.last_frame = ticks_ms()
        self.frame_ms = 45 if CONFIG_LOW_RAM_MODE else CONFIG_FRAME_MS_DEFAULT  # ~22-28 fps
        self.frame = 0

    # --- helpers ---
    def _set_level(self, level):
        self.level = level
        idx = (level - 1) % len(self.MAPS)
        self.MAP = self.MAPS[idx]
        self._minimap_walls = [
            (mx, my)
            for my in range(self.MAP_H)
            for mx in range(self.MAP_W)
            if self.MAP[my][mx] == 35
        ]
        self._minimap_initialized = False
        self._minimap_prev_player = None
        self._minimap_prev_aim = None
        self._minimap_prev_enemies = []

    def _restore_minimap_cell(self, mx, my):
        if 0 <= mx < self.MAP_W and 0 <= my < self.MAP_H:
            if self.MAP[my][mx] == 35:
                display.set_pixel(mx, my, 0, 0, 160)
            else:
                display.set_pixel(mx, my, 0, 0, 0)

    def _player_start_for_level(self):
        return self.STARTS[(self.level - 1) % len(self.STARTS)]

    def _is_wall_tile(self, mx, my):
        if mx < 0 or mx >= self.MAP_W or my < 0 or my >= self.MAP_H:
            return True
        return self.MAP[my][mx] == 35  # '#'

    def _is_wall_pos(self, x, y):
        return self._is_wall_tile(int(x), int(y))

    def configure_attract_maze(self):
        self.enemies = []
        self.lives = 0
        self.score = 0
        self.wave_announce = 0
        self.hit_flash = 0
        self.dmg_flash = 0
        self.render_hud = False
        self.render_minimap = False
        self.render_crosshair = False
        self.render_enemies = False
        self.level = random.randint(1, len(self.MAPS))
        self._set_level(self.level)
        self.px, self.py = self._player_start_for_level()
        self._attract_dir = random.randint(0, 3)
        self._attract_target_ang = (self._attract_dir * 64) & 255
        self.ang = self._attract_target_ang

    def _attract_open_dir(self, d):
        dir_dx = (1, 0, -1, 0)
        dir_dy = (0, -1, 0, 1)
        mx = int(self.px) + dir_dx[d]
        my = int(self.py) + dir_dy[d]
        return not self._is_wall_tile(mx, my)

    def _choose_attract_dir(self):
        cur = self._attract_dir
        left = (cur + 1) & 3
        right = (cur - 1) & 3
        back = (cur + 2) & 3
        side_choices = []
        if self._attract_open_dir(left):
            side_choices.append(left)
        if self._attract_open_dir(right):
            side_choices.append(right)
        if not self._attract_open_dir(cur):
            if side_choices:
                return side_choices[random.randint(0, len(side_choices) - 1)]
            if self._attract_open_dir(back):
                return back
            return cur
        if side_choices and random.randint(0, 99) < 28:
            return side_choices[random.randint(0, len(side_choices) - 1)]
        return cur

    def step_attract_maze(self, frame=0):
        dir_dx = (1, 0, -1, 0)
        dir_dy = (0, -1, 0, 1)
        centered = (
            abs(self.px - (int(self.px) + 0.5)) < 0.045 and
            abs(self.py - (int(self.py) + 0.5)) < 0.045
        )
        if centered:
            self.px = int(self.px) + 0.5
            self.py = int(self.py) + 0.5
            self._attract_dir = self._choose_attract_dir()
            self._attract_target_ang = (self._attract_dir * 64) & 255

        delta = ((self._attract_target_ang - self.ang + 128) & 255) - 128
        if delta:
            step_ang = 8
            if abs(delta) <= step_ang:
                self.ang = self._attract_target_ang
            elif delta > 0:
                self.ang = (self.ang + step_ang) & 255
            else:
                self.ang = (self.ang - step_ang) & 255
        else:
            step = 0.080
            nx = self.px + dir_dx[self._attract_dir] * step
            ny = self.py + dir_dy[self._attract_dir] * step
            if self._is_wall_pos(nx, ny):
                self.px = int(self.px) + 0.5
                self.py = int(self.py) + 0.5
                self._attract_dir = self._choose_attract_dir()
                self._attract_target_ang = (self._attract_dir * 64) & 255
            else:
                self.px = nx
                self.py = ny

        if (frame & 511) == 0:
            self.level = (self.level % len(self.MAPS)) + 1
            self._set_level(self.level)
            self.px, self.py = self._player_start_for_level()
            self._attract_dir = random.randint(0, 3)
            self._attract_target_ang = (self._attract_dir * 64) & 255
            self.ang = self._attract_target_ang
        self._render()

    def _is_enemy_clear_pos(self, x, y):
        # Keep enemies visually away from walls so sprites do not scrape along
        # columns and corners. The margin is small enough for one-tile corridors.
        if self._is_wall_pos(x, y):
            return False
        margin = 0.20
        return (
            not self._is_wall_pos(x - margin, y) and
            not self._is_wall_pos(x + margin, y) and
            not self._is_wall_pos(x, y - margin) and
            not self._is_wall_pos(x, y + margin)
        )

    def _cos_sin(self, a):
        a &= 255
        c = self._COS[a]
        s = self._SIN[a]
        if CONFIG_LOW_RAM_MODE:
            return c / 1024.0, s / 1024.0
        return c, s

    def _angle_to_units(self, dx, dy):
        # dx,dy in Map-Koordinaten; Achtung y-Achse ist "nach unten"
        ang = math.atan2(-dy, dx)  # -dy -> mathematisch korrekt
        if ang < 0:
            ang += 2 * math.pi
        return int(ang * 256 / (2 * math.pi)) & 255

    def _angle_delta(self, a, b):
        # kleinste Differenz a-b in [-128..127]
        d = (a - b + 128) & 255
        return d - 128

    def _cast_ray(self, ray_ang):
        """
        DDA Raycast: liefert (dist, side)
        side: 0 = x-seite (vertikale Wand), 1 = y-seite (horizontale Wand)
        """
        # Hoist to locals – attribute lookups are expensive in MicroPython.
        COS = self._COS
        SIN = self._SIN
        MAP = self.MAP
        MAP_W = self.MAP_W
        MAP_H = self.MAP_H
        MAX_DIST = self.MAX_DIST
        px = self.px
        py = self.py

        # Inline trig lookup. Low-RAM mode stores int16 values scaled by 1024.
        a = ray_ang & 255
        ray_dx = COS[a]
        ray_dy = -SIN[a]  # y nach unten
        if CONFIG_LOW_RAM_MODE:
            ray_dx = ray_dx / 1024.0
            ray_dy = ray_dy / 1024.0

        # avoid division by 0
        if ray_dx == 0:
            ray_dx = 1e-6
        if ray_dy == 0:
            ray_dy = 1e-6

        map_x = int(px)
        map_y = int(py)

        delta_x = abs(1.0 / ray_dx)
        delta_y = abs(1.0 / ray_dy)

        if ray_dx < 0:
            step_x = -1
            side_x = (px - map_x) * delta_x
        else:
            step_x = 1
            side_x = (map_x + 1.0 - px) * delta_x

        if ray_dy < 0:
            step_y = -1
            side_y = (py - map_y) * delta_y
        else:
            step_y = 1
            side_y = (map_y + 1.0 - py) * delta_y

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

            # Inline _is_wall_tile to avoid per-step method call overhead.
            if map_x < 0 or map_x >= MAP_W or map_y < 0 or map_y >= MAP_H or MAP[map_y][map_x] == 35:
                if side == 0:
                    dist = side_x - delta_x
                else:
                    dist = side_y - delta_y
                if dist < 0.05:
                    dist = 0.05
                if dist > MAX_DIST:
                    dist = MAX_DIST
                return dist, side

        return MAX_DIST, side

    def _spawn_wave(self, wave):
        self._set_level(wave)
        # sehr klein halten: 2..6 Gegner
        n = 2 + (wave // 2)
        if n > 7:
            n = 7
        self.enemies = []
        
        # Precompute all valid spawn points
        valid_spawns = []
        sx, sy = self._player_start_for_level()
        for x in range(1, self.MAP_W - 1):
            for y in range(1, self.MAP_H - 1):
                if not self._is_wall_tile(x, y):
                    # nicht direkt am Start
                    if abs(x + 0.5 - sx) + abs(y + 0.5 - sy) >= 4 and self._is_enemy_clear_pos(x + 0.5, y + 0.5):
                        valid_spawns.append((x + 0.5, y + 0.5))

        # Shuffle or random choice valid spawns
        for _ in range(n):
            if not valid_spawns:
                break
            spawn = random.choice(valid_spawns)
            valid_spawns.remove(spawn)
            
            if wave >= 7 and random.randint(0, 99) < 25:
                typ = 2
            elif wave >= 3 and random.randint(0, 99) < 45:
                typ = 1
            else:
                typ = 0

            hp = 1 + typ
            if wave >= 8 and typ > 0:
                hp += 1
            # x, y, hp, cooldown, type, animation phase
            self.enemies.append([spawn[0], spawn[1], hp, random.randint(20, 90), typ, random.randint(0, 31)])
            
        self.wave_announce = 60  # show wave banner for ~2 s

    def _shoot(self):
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

            # nur wenn nahe an der Mitte (Crosshair) -> leicht großzügiger für Arcade-Stick
            if abs(delta) > 4:
                continue

            if dist < best_d:
                best_d = dist
                best_i = i

        if best_i >= 0:
            self.enemies[best_i][2] -= 1
            self.hit_flash = 8  # flash crosshair on hit
            if self.enemies[best_i][2] <= 0:
                typ = self.enemies[best_i][4] if len(self.enemies[best_i]) > 4 else 0
                self.score += 50 + typ * 25
            else:
                self.score += 15

    def _update_enemies(self):
        global game_over, global_score

        # Enemies bewegen sich selten (Performance + Doom-Feeling)
        if (self.frame & 1) == 1:
            return

        for e in self.enemies:
            if len(e) < 4:
                e.append(0)  # upgrade legacy states to support cooldowns
            while len(e) < 6:
                e.append(0)
                
            if e[2] <= 0:
                continue

            dx = self.px - e[0]
            dy = self.py - e[1]
            dist2 = dx * dx + dy * dy
            dist = math.sqrt(dist2)

            # Contact damage
            if dist2 < 0.20:
                self.lives -= 1
                self.dmg_flash = 12
                if self.lives <= 0:
                    global_score = self.score
                    game_over = True
                    return
                # Respawn player
                self.px, self.py = self._player_start_for_level()
                return

            typ = e[4]
            e[5] = (e[5] + 1) & 31

            # Enemies might shoot back occasionally if wave > 2
            if self.wave > 2 and e[3] <= 0:
                # Basic LOS check (can see player directly?)
                shoot_range = 7.0 + typ * 1.2
                if dist > 0.5 and dist < shoot_range:
                    a = self._angle_to_units(dx, dy)
                    ray_dist, _ = self._cast_ray(a)
                    if ray_dist > dist - 0.2:
                        # Player visible! Bam.
                        self.lives -= 1
                        self.hit_flash = 10
                        self.dmg_flash = 12
                        if self.lives <= 0:
                            global_score = self.score
                            game_over = True
                            return
                        self.px, self.py = self._player_start_for_level()
                        # Reload enemy weapon
                        e[3] = random.randint(90, 210) - typ * 15
                        if e[3] < 55:
                            e[3] = 55
                        return
                    else:
                        e[3] = 30 # retry sooner if blocked
            elif e[3] > 0:
                e[3] -= 1

            # Move toward player
            step = 0.05 + (self.wave * 0.002) + typ * 0.006
            if step > 0.09:
                step = 0.09

            # axis-priority move
            if abs(dx) > abs(dy):
                sx = step if dx > 0 else -step
                nx = e[0] + sx
                if self._is_enemy_clear_pos(nx, e[1]):
                    e[0] = nx
                else:
                    sy = step if dy > 0 else -step
                    ny = e[1] + sy
                    if self._is_enemy_clear_pos(e[0], ny):
                        e[1] = ny
            else:
                sy = step if dy > 0 else -step
                ny = e[1] + sy
                if self._is_enemy_clear_pos(e[0], ny):
                    e[1] = ny
                else:
                    sx = step if dx > 0 else -step
                    nx = e[0] + sx
                    if self._is_enemy_clear_pos(nx, e[1]):
                        e[0] = nx

    def _enemy_palette(self, typ, hp):
        if typ == 2:
            return (150, 35, 255, 255, 140, 40)
        if typ == 1:
            return (255, 120, 20, 255, 220, 40)
        if hp > 1:
            return (255, 45, 180, 255, 220, 40)
        return (230, 35, 35, 255, 230, 40)

    def _draw_enemy_sprite(self, sp, x0, x1, y0, y1, dist, zbuf, typ, hp, anim):
        body_r, body_g, body_b, eye_r, eye_g, eye_b = self._enemy_palette(typ, hp)
        h = y1 - y0 + 1
        w = x1 - x0 + 1
        if h <= 0 or w <= 0:
            return

        for xx in range(x0, x1 + 1):
            if xx < 0 or xx >= WIDTH or dist >= zbuf[xx]:
                continue
            rel_x = xx - x0
            center = (w - 1) // 2
            for yy in range(y0, y1 + 1):
                if yy < 0 or yy >= self.PLAY_H:
                    continue
                rel_y = yy - y0

                # Width profile: small horn/head, wider torso, separated legs.
                if rel_y < h // 7:
                    half = 0 if typ == 0 else 1
                    horn = typ > 0 and (rel_x == center - 1 or rel_x == center + 1)
                    if not horn and abs(rel_x - center) > half:
                        continue
                    rr, gg, bb = body_r // 2, body_g // 2, body_b // 2
                elif rel_y < h // 3:
                    half = max(1, w // 4)
                    if abs(rel_x - center) > half:
                        continue
                    eye_row = y0 + h // 4
                    eye_col = abs(rel_x - center) == 1 or w <= 2
                    if yy == eye_row and eye_col:
                        rr, gg, bb = eye_r, eye_g, eye_b
                    else:
                        rr, gg, bb = body_r, body_g // 2, body_b // 2
                elif rel_y < (h * 3) // 4:
                    half = max(1, w // 2 - 1)
                    if abs(rel_x - center) > half:
                        continue
                    edge = abs(rel_x - center) == half
                    if edge:
                        rr, gg, bb = body_r // 3, body_g // 3, body_b // 3
                    else:
                        rr, gg, bb = body_r, body_g, body_b
                else:
                    stride = (anim >> 3) & 1
                    leg_left = center - 1 - stride
                    leg_right = center + 1 + stride
                    if rel_x != leg_left and rel_x != leg_right:
                        continue
                    rr, gg, bb = body_r // 2, body_g // 2, body_b // 2

                sp(xx, yy, rr, gg, bb)

    def _render(self):
        # Hoist frequently-accessed attributes to locals once.
        # On MicroPython each 'self.X' lookup costs a dictionary probe;
        # reading a local is a single LOAD_FAST bytecode.
        sp = display.set_pixel
        PLAY_H = self.PLAY_H
        zbuf = self.zbuf

        # We combine sky, wall, and floor rendering in one pass per column
        # to prevent overwriting pixels multiple times. This dramatically
        # reduces the dirty-pixel mask modifications and saves CPU time.
        minimap_w = self.MAP_W + 2 if self.render_minimap else 0
        minimap_h = self.MAP_H + 2 if self.render_minimap else 0
        
        # ray angles: fixedpoint, damit FOV/64 sauber läuft
        col_step = 2
        angle_step_fp = (self.FOV << 16) // WIDTH
        # Positive angle points upward in map coordinates, so screen-left is
        # ang + HALF_FOV and screen-right is ang - HALF_FOV.
        ang_fp = ((self.ang + self.HALF_FOV) & 255) << 16

        for x in range(0, WIDTH, col_step):
            ray_ang = (ang_fp >> 16) & 255
            ang_fp -= angle_step_fp * col_step

            dist, side = self._cast_ray(ray_ang)
            zbuf[x] = dist
            if col_step == 2 and x + 1 < WIDTH:
                zbuf[x + 1] = dist

            line_h = int(PLAY_H / (dist + 1e-6))
            if line_h < 1:
                line_h = 1
            if line_h > PLAY_H:
                line_h = PLAY_H

            start = (PLAY_H - line_h) // 2
            end = start + line_h - 1
            if start < 0: start = 0
            if end >= PLAY_H: end = PLAY_H - 1

            # Level color variation based on wave
            theme = (self.wave - 1) % 4
            b = 220 - int(dist * 18)
            if b < 40:
                b = 40
            
            wr = b if side == 0 else (b * 3) // 4
            
            # Apply theme color to wall
            if theme == 0:   # Brown
                wg = wr * 3 // 5
                wb = wr // 4
            elif theme == 1: # Blue
                wb = wr
                wg = wr * 3 // 5
                wr = wr // 4
            elif theme == 2: # Greenish
                wg = wr
                wb = wr // 3
                wr = wr // 3
            else:            # Purple
                wb = wr
                wg = wr // 4
                
            # Base sky and floor colors depending on theme
            if theme == 0:
                sky_r, sky_g, sky_b = 0, 0, 25
                fl_r, fl_g, fl_b = 18, 10, 0
            elif theme == 1:
                sky_r, sky_g, sky_b = 20, 0, 0
                fl_r, fl_g, fl_b = 0, 10, 18
            elif theme == 2:
                sky_r, sky_g, sky_b = 25, 10, 0
                fl_r, fl_g, fl_b = 0, 18, 0
            else:
                sky_r, sky_g, sky_b = 0, 20, 10
                fl_r, fl_g, fl_b = 18, 0, 18

            # apply damage flash overeverything in this column
            if self.dmg_flash > 0:
                flash_r = 150 + self.dmg_flash * 6
                if flash_r > 255: flash_r = 255
                sky_r, sky_g, sky_b = flash_r, 0, 0
                wr, wg, wb = flash_r, 0, 0
                fl_r, fl_g, fl_b = flash_r, 0, 0

            # Inline single-column draw (avoids draw_rectangle call overhead).
            # Draw sky, wall, and floor in order!
            for y in range(0, start):
                if x < minimap_w and y < minimap_h:
                    continue
                sp(x, y, sky_r, sky_g, sky_b)
                if col_step == 2 and x + 1 < WIDTH:
                    if x + 1 < minimap_w and y < minimap_h:
                        continue
                    sp(x + 1, y, sky_r, sky_g, sky_b)
            
            for y in range(start, end + 1):
                if x < minimap_w and y < minimap_h:
                    continue
                sp(x, y, wr, wg, wb)
                if col_step == 2 and x + 1 < WIDTH:
                    if x + 1 < minimap_w and y < minimap_h:
                        continue
                    sp(x + 1, y, wr, wg, wb)
                    
            for y in range(end + 1, PLAY_H):
                if x < minimap_w and y < minimap_h:
                    continue
                sp(x, y, fl_r, fl_g, fl_b)
                if col_step == 2 and x + 1 < WIDTH:
                    if x + 1 < minimap_w and y < minimap_h:
                        continue
                    sp(x + 1, y, fl_r, fl_g, fl_b)

        # sprites (enemies) als billboards
        # sortiert nach Entfernung (weit -> nah)
        # dx/dy stored alongside dist so we don't recalculate below.
        px = self.px
        py = self.py
        ang = self.ang
        if self.render_enemies:
            alive = []
            for e in self.enemies:
                if e[2] > 0:
                    dx = e[0] - px
                    dy = e[1] - py
                    d = math.sqrt(dx * dx + dy * dy)
                    alive.append((d, e, dx, dy))
            alive.sort(reverse=True)

            HALF_FOV = self.HALF_FOV
            FOV = self.FOV
            for dist, e, dx, dy in alive:
                a = self._angle_to_units(dx, dy)
                delta = self._angle_delta(a, ang)
                if abs(delta) > HALF_FOV:
                    continue

                sx = int((HALF_FOV - delta) * WIDTH / FOV)
                if sx < 0 or sx >= WIDTH:
                    continue

                # sprite size
                sh = int(PLAY_H / (dist + 1e-6))
                if sh < 2:
                    sh = 2
                if sh > PLAY_H:
                    sh = PLAY_H
                sw = sh // 3
                if sw < 1:
                    sw = 1
                if sw > 8:
                    sw = 8

                y0 = (PLAY_H - sh) // 2
                y1 = y0 + sh - 1

                x0 = sx - sw // 2
                x1 = x0 + sw - 1

                typ = e[4] if len(e) > 4 else 0
                anim = e[5] if len(e) > 5 else 0
                self._draw_enemy_sprite(sp, x0, x1, y0, y1, dist, zbuf, typ, e[2], anim)

        if self.render_minimap:
            # minimap overlay: keep the background static and only refresh markers.
            if not self._minimap_initialized:
                draw_rectangle(0, 0, self.MAP_W + 1, self.MAP_H + 1, 0, 0, 0)
                for mx, my in self._minimap_walls:
                    sp(mx, my, 0, 0, 160)
                self._minimap_initialized = True
            else:
                if self._minimap_prev_player is not None:
                    self._restore_minimap_cell(self._minimap_prev_player[0], self._minimap_prev_player[1])
                if self._minimap_prev_aim is not None:
                    self._restore_minimap_cell(self._minimap_prev_aim[0], self._minimap_prev_aim[1])
                for ex, ey in self._minimap_prev_enemies:
                    self._restore_minimap_cell(ex, ey)

            player_cell = (int(px), int(py))
            sp(player_cell[0], player_cell[1], 0, 255, 0)
            # direction hint
            dc, ds = self._cos_sin(ang)
            ax = int(px + dc * 0.7)
            ay = int(py - ds * 0.7)
            aim_cell = None
            if 0 <= ax < self.MAP_W and 0 <= ay < self.MAP_H:
                sp(ax, ay, 0, 200, 0)
                aim_cell = (ax, ay)
            current_enemy_cells = []
            for e in self.enemies:
                if e[2] > 0:
                    ex = int(e[0])
                    ey = int(e[1])
                    if 0 <= ex < self.MAP_W and 0 <= ey < self.MAP_H:
                        current_enemy_cells.append((ex, ey))
                        typ = e[4] if len(e) > 4 else 0
                        if typ == 2:
                            sp(ex, ey, 180, 60, 255)
                        elif typ == 1:
                            sp(ex, ey, 255, 130, 0)
                        else:
                            sp(ex, ey, 255, 0, 0)
            self._minimap_prev_player = player_cell
            self._minimap_prev_aim = aim_cell
            self._minimap_prev_enemies = current_enemy_cells

        if self.render_hud:
            # lives indicator - 2x2 red blocks (oben rechts)
            for i in range(self.lives):
                lx = WIDTH - 3 - i * 4
                ly = 1
                draw_rectangle(lx, ly, lx + 1, ly + 1, 220, 30, 30)

        # wave announcement banner
        if self.wave_announce > 0:
            wlabel = "L" + str(self.level)
            wx = WIDTH // 2 - len(wlabel) * 3
            wy = PLAY_H // 2 - 3
            draw_rectangle(wx - 1, wy - 1, wx + len(wlabel) * 6, wy + 5, 0, 0, 0)
            draw_text_small(wx, wy, wlabel, 255, 220, 0)

        if self.render_crosshair:
            # crosshair (+ shape, flashes yellow on hit)
            cx = WIDTH // 2
            cy = PLAY_H // 2
            if self.hit_flash > 0:
                cr, cg, cb = 255, 255, 0
            else:
                cr, cg, cb = 200, 200, 200
            for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                xx = cx + dx
                yy = cy + dy
                if 0 <= xx < WIDTH and 0 <= yy < PLAY_H:
                    sp(xx, yy, cr, cg, cb)

        if self.render_hud:
            display_score_and_time(self.score)

    def main_loop(self, joystick):
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        display_score_and_time(0)

        while not game_over:
            try:
                c_button, z_button = joystick.read_buttons()
                if c_button:
                    return

                now = ticks_ms()
                if ticks_diff(now, self.last_frame) < self.frame_ms:
                    sleep_ms(2)
                    continue
                self.last_frame = now
                self.frame += 1
                if self.wave_announce > 0:
                    self.wave_announce -= 1
                if self.hit_flash > 0:
                    self.hit_flash -= 1
                if self.dmg_flash > 0:
                    self.dmg_flash -= 1

                # input
                d = joystick.read_direction([
                    JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT,
                    JOYSTICK_UP_LEFT, JOYSTICK_UP_RIGHT, JOYSTICK_DOWN_LEFT, JOYSTICK_DOWN_RIGHT
                ], debounce=False)

                # rotate
                tx, ty = direction_to_delta_8way(d)
                rot = 0
                if tx < 0:
                    rot = 5
                elif tx > 0:
                    rot = -5
                if rot:
                    self.ang = (self.ang + rot) & 255

                # move
                move = 0.0
                if ty < 0:
                    move = 0.12
                elif ty > 0:
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
                    self.px, self.py = self._player_start_for_level()
                    self.ang = 0

                global_score = self.score
                self._render()

                if (self.frame % 80) == 0:
                    gc.collect()

            except RestartProgram:
                return

    async def main_loop_async(self, joystick):
        """Async version for pygbag: yields with asyncio.sleep()."""
        if asyncio is None:
            return self.main_loop(joystick)

        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        display_score_and_time(0)

        while not game_over:
            try:
                c_button, z_button = joystick.read_buttons()
                if c_button:
                    return

                now = ticks_ms()
                if ticks_diff(now, self.last_frame) < self.frame_ms:
                    await asyncio.sleep(0.002)
                    continue
                self.last_frame = now
                self.frame += 1
                if self.wave_announce > 0:
                    self.wave_announce -= 1
                if self.hit_flash > 0:
                    self.hit_flash -= 1
                if self.dmg_flash > 0:
                    self.dmg_flash -= 1

                # input
                d = joystick.read_direction([
                    JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT,
                    JOYSTICK_UP_LEFT, JOYSTICK_UP_RIGHT, JOYSTICK_DOWN_LEFT, JOYSTICK_DOWN_RIGHT
                ], debounce=False)

                # rotate
                tx, ty = direction_to_delta_8way(d)
                rot = 0
                if tx < 0:
                    rot = 5
                elif tx > 0:
                    rot = -5
                if rot:
                    self.ang = (self.ang + rot) & 255

                # move
                move = 0.0
                if ty < 0:
                    move = 0.12
                elif ty > 0:
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
                    self.px, self.py = self._player_start_for_level()
                    self.ang = 0

                global_score = self.score
                self._render()

                if (self.frame % 80) == 0:
                    gc.collect()

            except RestartProgram:
                return


class CityChaseGame:
    """
    CITY
    Controls:
      - Up / Down: accelerate / brake
      - Left / Right: steer
      - Z: boost
      - C: return to menu
    Top-down city chase inspired by early overhead open-world crime games.
    """
    FRAME_MS = 38
    WORLD = 256
    BLOCK = 32
    ROAD_W = 10
    MAX_SPEED = 2.45

    def __init__(self, ctx=None):
        self.target_jobs = int(get_context_setting(ctx, "jobs", 3) or 3)
        self.traffic_enabled = bool(get_context_setting(ctx, "traffic", True))
        self.reset()

    def reset(self):
        self.x = 128.0
        self.y = 128.0
        self.angle = -90.0
        self.speed = 0.0
        self.condition = 100.0
        self.heat = 0.0
        self.energy = 100.0
        self.score = 0
        self.frame = 0
        self.jobs_done = 0
        self.phase = "pickup"
        self.bump_flash = 0
        self.boost_flash = 0
        self.hit_cooldown = 0
        self.entities = []
        self.pickup = self._random_road_point(46)
        self.dropoff = self._random_road_point(76)
        self._spawn_traffic(8 if self.traffic_enabled else 0)

    def _road_axis(self, value):
        m = int(value) % self.BLOCK
        return m < self.ROAD_W or m >= self.BLOCK - self.ROAD_W

    def _is_road(self, x, y):
        x = x % self.WORLD
        y = y % self.WORLD
        return self._road_axis(x) or self._road_axis(y)

    def _is_intersection(self, x, y):
        return self._road_axis(x) and self._road_axis(y)

    def _wrap_dist(self, a, b):
        d = abs(a - b)
        return min(d, self.WORLD - d)

    def _dist2_to_player(self, x, y):
        dx = self._wrap_dist(x, self.x)
        dy = self._wrap_dist(y, self.y)
        return dx * dx + dy * dy

    def _wrapped_delta_to_player(self, x, y):
        dx = (x - self.x + self.WORLD / 2) % self.WORLD - self.WORLD / 2
        dy = (y - self.y + self.WORLD / 2) % self.WORLD - self.WORLD / 2
        return dx, dy

    def _target_distance(self):
        tx, ty = self._target()
        dx, dy = self._wrapped_delta_to_player(tx, ty)
        return math.sqrt(dx * dx + dy * dy)

    def _random_road_point(self, min_dist=32):
        for _ in range(90):
            gx = random.randint(0, self.WORLD - 1)
            gy = random.randint(0, self.WORLD - 1)
            if not self._is_road(gx, gy):
                continue
            if self._dist2_to_player(gx, gy) >= min_dist * min_dist:
                return [float(gx), float(gy)]
        return [float((int(self.x) + min_dist) % self.WORLD), float(self.y)]

    def _dir_vec(self, d):
        if d == 0:
            return 1, 0
        if d == 1:
            return 0, 1
        if d == 2:
            return -1, 0
        return 0, -1

    def _valid_dirs(self, x, y):
        out = []
        for d in range(4):
            dx, dy = self._dir_vec(d)
            if self._is_road(x + dx * 5, y + dy * 5):
                out.append(d)
        return out or [0]

    def _spawn_traffic(self, count):
        for _ in range(count):
            px, py = self._random_road_point(28)
            dirs = self._valid_dirs(px, py)
            self.entities.append([px, py, random.choice(dirs), 0, random.randint(0, 30)])

    def _spawn_police(self):
        target = 0
        if self.heat > 18:
            target = 1 + min(3, int(self.heat // 35))
        current = 0
        for e in self.entities:
            if e[3] == 1:
                current += 1
        while current < target:
            px, py = self._random_road_point(62)
            dirs = self._valid_dirs(px, py)
            self.entities.append([px, py, random.choice(dirs), 1, random.randint(0, 15)])
            current += 1

    def _choose_police_dir(self, e):
        best = e[2]
        best_score = 999999.0
        for d in self._valid_dirs(e[0], e[1]):
            dx, dy = self._dir_vec(d)
            nx = (e[0] + dx * 8) % self.WORLD
            ny = (e[1] + dy * 8) % self.WORLD
            score = self._dist2_to_player(nx, ny)
            if score < best_score:
                best = d
                best_score = score
        return best

    def _update_entities(self):
        kept = []
        for e in self.entities:
            e[4] += 1
            if e[3] == 1 and self.heat <= 2 and self._dist2_to_player(e[0], e[1]) > 70 * 70:
                continue
            if self._is_intersection(e[0], e[1]) and e[4] > 12:
                if e[3] == 1:
                    e[2] = self._choose_police_dir(e)
                elif random.randint(0, 99) < 34:
                    e[2] = random.choice(self._valid_dirs(e[0], e[1]))
                e[4] = 0
            dx, dy = self._dir_vec(e[2])
            step = 1.22 if e[3] == 1 else 0.78
            if e[3] == 1:
                step += min(0.44, self.heat * 0.006)
            nx = (e[0] + dx * step) % self.WORLD
            ny = (e[1] + dy * step) % self.WORLD
            if self._is_road(nx, ny):
                e[0] = nx
                e[1] = ny
            else:
                e[2] = random.choice(self._valid_dirs(e[0], e[1]))
            if self._dist2_to_player(e[0], e[1]) < (7 * 7):
                if self.hit_cooldown <= 0:
                    if e[3] == 1:
                        self.condition -= 9.0
                        self.heat += 2.0
                    else:
                        self.condition -= 4.0
                        self.heat += 0.8
                    self.speed *= 0.48
                    self.bump_flash = 10
                    self.hit_cooldown = 14
            kept.append(e)
        self.entities = kept

    def _target(self):
        return self.pickup if self.phase == "pickup" else self.dropoff

    def _advance_job(self):
        tx, ty = self._target()
        if self._wrap_dist(self.x, tx) > 5 or self._wrap_dist(self.y, ty) > 5:
            return True
        if self.phase == "pickup":
            self.phase = "drop"
            self.score += 120
            self.heat = min(100.0, self.heat + 12.0)
            self.dropoff = self._random_road_point(70)
            return True
        self.jobs_done += 1
        self.score += 520 + int(self.condition)
        self.heat = min(100.0, self.heat + 18.0)
        if self.jobs_done >= self.target_jobs:
            set_game_over_score(self.score + int(self.condition * 8), won=True)
            return False
        self.phase = "pickup"
        self.pickup = self._random_road_point(55)
        self.dropoff = self._random_road_point(76)
        return True

    def _update(self, direction, boost):
        self.frame += 1
        if self.bump_flash > 0:
            self.bump_flash -= 1
        if self.boost_flash > 0:
            self.boost_flash -= 1
        if self.hit_cooldown > 0:
            self.hit_cooldown -= 1
        dx, dy = direction_to_delta_8way(direction)
        if dx < 0:
            self.angle -= 5.0 + min(3.0, abs(self.speed) * 1.2)
        elif dx > 0:
            self.angle += 5.0 + min(3.0, abs(self.speed) * 1.2)
        if dy < 0:
            self.speed += 0.105
        elif dy > 0:
            self.speed -= 0.130
        else:
            self.speed *= 0.982
        max_speed = self.MAX_SPEED
        if boost and self.energy > 1.5 and self.speed > 0.3:
            self.speed += 0.090
            self.energy -= 1.15
            self.heat = min(100.0, self.heat + 0.06)
            self.boost_flash = 4
            max_speed = self.MAX_SPEED + 0.82
        else:
            self.energy = min(100.0, self.energy + 0.08)
        self.speed = clamp(self.speed, -0.86, max_speed)

        rad = math.radians(self.angle)
        vx = math.cos(rad) * self.speed
        vy = math.sin(rad) * self.speed
        nx = (self.x + vx) % self.WORLD
        ny = (self.y + vy) % self.WORLD
        if self._is_road(nx, self.y):
            self.x = nx
        else:
            self.speed *= -0.26
            self.condition -= 1.2
            self.bump_flash = 6
        if self._is_road(self.x, ny):
            self.y = ny
        else:
            self.speed *= -0.26
            self.condition -= 1.2
            self.bump_flash = 6

        self.heat = clamp(self.heat - 0.018, 0.0, 100.0)
        self._spawn_police()
        self._update_entities()
        self.score += int(max(0.0, self.speed) * 0.8)
        if self.condition <= 0:
            set_game_over_score(self.score, won=False)
            return False
        return self._advance_job()

    def _screen_pos(self, wx, wy):
        dx, dy = self._wrapped_delta_to_player(wx, wy)
        sx = int(WIDTH // 2 + dx)
        sy = int(PLAY_HEIGHT // 2 + dy)
        return sx, sy

    def _draw_city(self):
        ox = self.x - WIDTH // 2
        oy = self.y - PLAY_HEIGHT // 2
        for sy in range(PLAY_HEIGHT):
            wy = (oy + sy) % self.WORLD
            yroad = self._road_axis(wy)
            for sx in range(WIDTH):
                wx = (ox + sx) % self.WORLD
                xroad = self._road_axis(wx)
                if xroad or yroad:
                    shade = 34 + ((int(wx) + int(wy)) & 3) * 5
                    if xroad and yroad:
                        display.set_pixel(sx, sy, shade + 14, shade + 14, shade + 16)
                    elif ((int(wx if yroad else wy) // 7) & 3) == 0:
                        display.set_pixel(sx, sy, 210, 205, 160)
                    else:
                        display.set_pixel(sx, sy, shade, shade, shade + 4)
                else:
                    bx = int(wx) // self.BLOCK
                    by = int(wy) // self.BLOCK
                    c = 24 + ((bx * 17 + by * 11) % 34)
                    display.set_pixel(sx, sy, c // 2, c, c + 12)

    def _draw_marker(self, point, color):
        sx, sy = self._screen_pos(point[0], point[1])
        if -5 <= sx < WIDTH + 5 and -5 <= sy < PLAY_HEIGHT + 5:
            draw_rect_outline(sx - 4, sy - 4, sx + 4, sy + 4, *color)
            set_pixel_clipped(sx, sy, 255, 255, 255)
            return True
        return False

    def _draw_target_pointer(self, point, color):
        dx, dy = self._wrapped_delta_to_player(point[0], point[1])
        if abs(dx) < 1 and abs(dy) < 1:
            return
        limit_x = WIDTH // 2 - 5
        limit_y = PLAY_HEIGHT // 2 - 8
        scale_x = limit_x / abs(dx) if abs(dx) > 0.1 else 999.0
        scale_y = limit_y / abs(dy) if abs(dy) > 0.1 else 999.0
        scale = min(scale_x, scale_y, 1.0)
        px = int(WIDTH // 2 + dx * scale)
        py = int(PLAY_HEIGHT // 2 + dy * scale)
        px = clamp(px, 3, WIDTH - 4)
        py = clamp(py, 8, PLAY_HEIGHT - 8)
        draw_line(WIDTH // 2, PLAY_HEIGHT // 2, px, py, color[0] // 2, color[1] // 2, color[2] // 2)
        draw_rect_outline(px - 2, py - 2, px + 2, py + 2, *color)
        set_pixel_clipped(px, py, 255, 255, 255)

    def _draw_car(self, sx, sy, angle, body, trim):
        rad = math.radians(angle)
        fx = int(math.cos(rad) * 3)
        fy = int(math.sin(rad) * 3)
        rx = int(math.cos(rad + math.pi / 2) * 2)
        ry = int(math.sin(rad + math.pi / 2) * 2)
        draw_line(sx - fx - rx, sy - fy - ry, sx + fx, sy + fy, *body)
        draw_line(sx - fx + rx, sy - fy + ry, sx + fx, sy + fy, *body)
        draw_line(sx - rx, sy - ry, sx + rx, sy + ry, *trim)
        set_pixel_clipped(sx + fx, sy + fy, 255, 255, 255)

    def _draw_hud(self):
        draw_rectangle(0, 0, WIDTH - 1, 6, 0, 0, 0)
        draw_text_small(1, 1, "J" + str(self.jobs_done) + "/" + str(self.target_jobs), 255, 255, 255)
        heat_w = int(self.heat * 17 / 100)
        cond_w = int(self.condition * 17 / 100)
        draw_rectangle(25, 1, 42, 2, 25, 25, 25)
        draw_rectangle(45, 1, 62, 2, 25, 25, 25)
        if heat_w > 0:
            draw_rectangle(25, 1, 24 + heat_w, 2, 255, 45, 45)
        if cond_w > 0:
            draw_rectangle(45, 1, 44 + cond_w, 2, 45, 220, 90)
        label = "P" if self.phase == "pickup" else "D"
        draw_text_small(1, PLAY_HEIGHT - 6, label, 255, 240, 90)
        dist = min(99, int(self._target_distance()))
        draw_text_small(8, PLAY_HEIGHT - 6, str(dist), 180, 220, 255)

    def _draw(self):
        display.clear()
        self._draw_city()
        if self.phase == "pickup":
            if not self._draw_marker(self.pickup, (60, 255, 110)):
                self._draw_target_pointer(self.pickup, (60, 255, 110))
        else:
            if not self._draw_marker(self.dropoff, (255, 220, 60)):
                self._draw_target_pointer(self.dropoff, (255, 220, 60))
        for e in self.entities:
            sx, sy = self._screen_pos(e[0], e[1])
            if -6 <= sx < WIDTH + 6 and -6 <= sy < PLAY_HEIGHT + 6:
                if e[3] == 1:
                    self._draw_car(sx, sy, e[2] * 90, (255, 40, 40), (40, 90, 255))
                else:
                    self._draw_car(sx, sy, e[2] * 90, (70, 170, 255), (255, 230, 70))
        if self.bump_flash:
            body = (255, 70, 35)
        elif self.boost_flash:
            body = (255, 255, 255)
        else:
            body = (245, 245, 245)
        self._draw_car(WIDTH // 2, PLAY_HEIGHT // 2, self.angle, body, (255, 40, 210))
        self._draw_hud()
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        self.reset()
        begin_game(0)

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            d = joystick.read_direction([
                JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT,
                JOYSTICK_UP_LEFT, JOYSTICK_UP_RIGHT, JOYSTICK_DOWN_LEFT, JOYSTICK_DOWN_RIGHT
            ], debounce=False)
            if not self._update(d, z_button):
                return False
            self._draw()
            return True
        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class TopDownRacerGame:
    """
    RACING
    Controls:
      - Up / Down: accelerate / brake
      - Left / Right: steer
      - Z: boost
      - C: return to menu
    Top-down circuit racer with scrolling road, traffic, boost, and lap finish.
    """
    FRAME_MS = 34
    CAR_Y = PLAY_HEIGHT - 14
    ROAD_HALF = 17
    LAP_LEN = 760.0

    def __init__(self, ctx=None):
        self.target_laps = int(get_context_setting(ctx, "laps", 3) or 3)
        self.traffic_enabled = bool(get_context_setting(ctx, "traffic", True))
        self.reset()

    def reset(self):
        self.world_y = 0.0
        self.speed = 0.0
        self.player_x = WIDTH // 2
        self.energy = 100.0
        self.score = 0
        self.lap = 1
        self.frame = 0
        self.bump_flash = 0
        self.boost_flash = 0
        self.rivals = []
        self.next_spawn_y = 46.0
        self.passed = 0
        self._spawn_until(self.world_y + 190.0)

    def _track_center(self, z):
        return (
            WIDTH // 2
            + math.sin(z * 0.028) * 12.0
            + math.sin(z * 0.010 + 1.8) * 7.0
        )

    def _sample_world_for_row(self, row):
        return self.world_y + (self.CAR_Y - row) * 2.15

    def _lane_x(self, z, lane):
        return self._track_center(z) + lane * (self.ROAD_HALF - 6)

    def _spawn_until(self, limit_y):
        if not self.traffic_enabled:
            return
        while self.next_spawn_y < limit_y:
            gap = random.randint(36, 68)
            self.next_spawn_y += gap
            lane = random.choice((-0.72, -0.25, 0.25, 0.72))
            kind = random.randint(0, 1)
            drift = random.randint(0, 80)
            self.rivals.append([self.next_spawn_y, lane, kind, drift])

    def _rival_x(self, rival):
        lane = rival[1]
        if rival[2] == 1:
            lane += math.sin((self.frame + rival[3]) * 0.035) * 0.12
        lane = clamp(lane, -0.9, 0.9)
        return self._lane_x(rival[0], lane)

    def _update(self, direction, boost):
        self.frame += 1
        if self.bump_flash > 0:
            self.bump_flash -= 1
        if self.boost_flash > 0:
            self.boost_flash -= 1

        dx, dy = direction_to_delta_8way(direction)
        if dy < 0:
            self.speed += 0.085
        elif dy > 0:
            self.speed -= 0.125
        else:
            self.speed *= 0.988

        max_speed = 3.05
        if boost and self.energy > 2.0 and self.speed > 0.8:
            self.speed += 0.105
            self.energy -= 1.05
            self.boost_flash = 4
            max_speed = 3.95
        else:
            self.energy = min(100.0, self.energy + 0.075)

        self.speed = clamp(self.speed, 0.0, max_speed)

        if dx:
            steer = 0.72 + self.speed * 0.23
            self.player_x += dx * steer
        self.player_x = clamp(self.player_x, 2.0, WIDTH - 3.0)

        center = self._track_center(self.world_y)
        margin = self.ROAD_HALF - 3
        if abs(self.player_x - center) > margin:
            self.speed *= 0.935
            self.energy -= 0.42 + self.speed * 0.20
            self.bump_flash = max(self.bump_flash, 2)

        self.world_y += self.speed
        self.lap = int(self.world_y // self.LAP_LEN) + 1
        self.score = int(self.world_y) + self.passed * 55 + int(self.energy * 2)

        kept = []
        for rival in self.rivals:
            rel = rival[0] - self.world_y
            sx = self._rival_x(rival)
            sy = self.CAR_Y - rel / 2.15
            if -12.0 <= rel <= 9.0 and abs(sy - self.CAR_Y) <= 6.0 and abs(sx - self.player_x) <= 5.0:
                self.energy -= 18.0 if rival[2] == 0 else 24.0
                self.speed *= 0.43
                self.bump_flash = 12
                continue
            if rel < -20.0:
                self.passed += 1
                continue
            kept.append(rival)
        self.rivals = kept
        self._spawn_until(self.world_y + 190.0)

        if self.energy <= 0.0:
            set_game_over_score(self.score, won=False)
            return False
        if self.world_y >= self.LAP_LEN * self.target_laps:
            self.score += int(self.energy * 15) + self.passed * 20 + 1000
            set_game_over_score(self.score, won=True)
            return False
        return True

    def _draw_car(self, x, y, body, trim, player=False):
        x = int(x)
        y = int(y)
        draw_rectangle(x - 2, y - 3, x + 2, y + 3, *body)
        draw_rectangle(x - 1, y - 4, x + 1, y - 3, *trim)
        set_pixel_clipped(x - 3, y - 2, 20, 20, 20)
        set_pixel_clipped(x + 3, y - 2, 20, 20, 20)
        set_pixel_clipped(x - 3, y + 2, 20, 20, 20)
        set_pixel_clipped(x + 3, y + 2, 20, 20, 20)
        if player:
            set_pixel_clipped(x, y - 5, 255, 255, 255)

    def _draw_road_row(self, row):
        z = self._sample_world_for_row(row)
        center = int(self._track_center(z))
        left = center - self.ROAD_HALF
        right = center + self.ROAD_HALF
        dash = int(z / 12) & 1
        finish = int(z) % int(self.LAP_LEN)
        for x in range(WIDTH):
            if left <= x <= right:
                if finish < 9 and ((x + row) & 3) < 2:
                    display.set_pixel(x, row, 245, 245, 245)
                elif x in (left, left + 1, right - 1, right):
                    if self.boost_flash:
                        display.set_pixel(x, row, 255, 80, 210)
                    else:
                        display.set_pixel(x, row, 255, 230, 50)
                elif abs(x - center) <= 1 and dash:
                    display.set_pixel(x, row, 220, 220, 220)
                else:
                    shade = 38 + ((row + int(self.world_y)) & 3) * 4
                    if self.bump_flash:
                        display.set_pixel(x, row, 90, 30, 32)
                    else:
                        display.set_pixel(x, row, shade, shade, shade + 8)
            else:
                grass = 20 + ((x * 3 + row + int(self.world_y)) & 7)
                display.set_pixel(x, row, 4, grass, 12)

    def _draw_hud(self):
        draw_rectangle(0, 0, WIDTH - 1, 6, 0, 0, 0)
        draw_text_small(1, 1, "L" + str(min(self.lap, self.target_laps)) + "/" + str(self.target_laps), 255, 255, 255)
        bar_w = int(22 * self.energy / 100.0)
        draw_rectangle(WIDTH - 25, 1, WIDTH - 3, 3, 25, 25, 25)
        if bar_w > 0:
            col = (50, 235, 90) if self.energy > 30 else (255, 70, 30)
            draw_rectangle(WIDTH - 25, 1, WIDTH - 26 + bar_w, 3, *col)

    def _draw(self):
        display.clear()
        for row in range(PLAY_HEIGHT):
            self._draw_road_row(row)

        for rival in self.rivals:
            rel = rival[0] - self.world_y
            y = self.CAR_Y - rel / 2.15
            if -8 <= y < PLAY_HEIGHT + 8:
                x = self._rival_x(rival)
                if rival[2] == 0:
                    self._draw_car(x, y, (255, 70, 45), (255, 230, 70))
                else:
                    self._draw_car(x, y, (45, 160, 255), (255, 255, 255))

        if self.bump_flash:
            body = (255, 60, 35)
        elif self.boost_flash:
            body = (255, 255, 255)
        else:
            body = (235, 235, 245)
        self._draw_car(self.player_x, self.CAR_Y, body, (255, 40, 210), player=True)
        if self.boost_flash:
            draw_rectangle(int(self.player_x) - 1, self.CAR_Y + 4, int(self.player_x) + 1, self.CAR_Y + 6, 40, 170, 255)
        self._draw_hud()
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        self.reset()
        begin_game(0)

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            d = joystick.read_direction([
                JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT,
                JOYSTICK_UP_LEFT, JOYSTICK_UP_RIGHT, JOYSTICK_DOWN_LEFT, JOYSTICK_DOWN_RIGHT
            ], debounce=False)
            if not self._update(d, z_button):
                return False
            self._draw()
            return True
        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class RayRacerGame:
    """
    RAY RACER
    Raycaster-style anti-grav racer for the 64x64 matrix.

    Controls:
      - UP/DOWN: accelerate/brake
      - LEFT/RIGHT: steer
      - Z: boost
      - C: return to menu
    """

    PLAY_H = HEIGHT - 6
    HORIZON = 14
    TRACK_LEN = 900.0
    RACE_LAPS = 3
    FRAME_MS = 34
    NORMAL_MAX_SPEED = 2.25
    BOOST_MAX_SPEED = 3.10
    CRUISE_SPEED = NORMAL_MAX_SPEED * 0.5

    def __init__(self):
        self.row_depth = [0.0] * self.PLAY_H
        self.row_center = [WIDTH // 2] * self.PLAY_H
        self.row_half = [0] * self.PLAY_H
        self.reset()

    def reset(self):
        self.pos = 0.0
        self.speed = self.CRUISE_SPEED
        self.lane = 0.0
        self.energy = 100.0
        self.score = 0
        self.passed = 0
        self.lap = 1
        self.frame = 0
        self.bump_flash = 0
        self.boost_flash = 0
        self.objects = []
        self._spawn_until(self.pos + 145.0)
        self._prepare_depth_table()

    def _prepare_depth_table(self):
        span = self.PLAY_H - self.HORIZON
        for y in range(self.PLAY_H):
            if y < self.HORIZON:
                self.row_depth[y] = 0.0
                continue
            p = (y - self.HORIZON + 1) / span
            depth = 1.8 / (p * p)
            if depth > 72.0:
                depth = 72.0
            self.row_depth[y] = depth

    def _track_curve(self, z):
        # Three broad waves create readable F-Zero-like sweepers without maps.
        return (
            math.sin(z * 0.013) * 18.0 +
            math.sin(z * 0.027 + 1.7) * 7.0 +
            math.sin(z * 0.006) * 24.0
        )

    def _object_lane(self, obj):
        lane = obj[1]
        if obj[2] == 0:
            lane += math.sin((self.frame + obj[3]) * 0.055) * 0.13
        elif obj[2] == 1:
            lane += math.sin((self.frame + obj[3]) * 0.035) * 0.08
        if lane < -0.95:
            lane = -0.95
        elif lane > 0.95:
            lane = 0.95
        return lane

    def _spawn_until(self, z_limit):
        far = self.pos + 18.0
        for obj in self.objects:
            if obj[0] > far:
                far = obj[0]
        while far < z_limit:
            far += random.randint(16, 38)
            lane = random.choice((-0.72, -0.28, 0.28, 0.72))
            roll = random.randint(0, 99)
            if roll < 17:
                kind = 2      # energy gate
            elif roll < 42:
                kind = 1      # heavy rival
            else:
                kind = 0      # fast rival
            self.objects.append([far, lane, kind, random.randint(0, 127)])

    def _update(self, direction, boost):
        global game_over
        self.frame += 1
        if self.bump_flash > 0:
            self.bump_flash -= 1
        if self.boost_flash > 0:
            self.boost_flash -= 1

        sx, sy = direction_to_delta_8way(direction)

        if sy < 0:
            self.speed += 0.070
        elif sy > 0:
            self.speed -= 0.110
        else:
            if self.speed < self.CRUISE_SPEED:
                self.speed += 0.034
                if self.speed > self.CRUISE_SPEED:
                    self.speed = self.CRUISE_SPEED
            elif self.speed > self.CRUISE_SPEED:
                self.speed -= 0.022
                if self.speed < self.CRUISE_SPEED:
                    self.speed = self.CRUISE_SPEED

        max_speed = self.NORMAL_MAX_SPEED
        if boost and self.energy > 2.0 and self.speed > 0.35:
            self.speed += 0.085
            self.energy -= 1.15
            self.boost_flash = 4
            max_speed = self.BOOST_MAX_SPEED
        else:
            self.energy += 0.085
            if self.energy > 100.0:
                self.energy = 100.0

        if self.speed < 0.0:
            self.speed = 0.0
        elif self.speed > max_speed:
            self.speed = max_speed

        if sx:
            steer = 0.045 + self.speed * 0.022
            self.lane += sx * steer
        else:
            self.lane *= 0.992

        if self.lane < -1.38:
            self.lane = -1.38
        elif self.lane > 1.38:
            self.lane = 1.38

        if abs(self.lane) > 1.05:
            self.speed *= 0.935
            self.energy -= 0.55 + self.speed * 0.18
            self.bump_flash = 2

        self.pos += self.speed
        self.lap = int(self.pos // self.TRACK_LEN) + 1
        self.score = int(self.pos * 2) + self.passed * 65 + int(self.energy)

        kept = []
        for obj in self.objects:
            rel = obj[0] - self.pos
            lane = self._object_lane(obj)
            if rel < 1.25:
                if obj[2] == 2:
                    if abs(self.lane - lane) < 0.38:
                        self.energy += 22.0
                        if self.energy > 100.0:
                            self.energy = 100.0
                        self.score += 120
                elif abs(self.lane - lane) < (0.34 if obj[2] == 0 else 0.42):
                    self.energy -= 17.0 if obj[2] == 0 else 25.0
                    self.speed *= 0.42
                    self.bump_flash = 12
                else:
                    self.passed += 1
                continue
            kept.append(obj)
        self.objects = kept
        self._spawn_until(self.pos + 145.0)

        if self.energy <= 0.0:
            set_game_over_score(self.score, won=False)
            return
        if self.pos >= self.TRACK_LEN * self.RACE_LAPS:
            self.score += int(self.energy * 20) + 1500
            set_game_over_score(self.score, won=True)
            return
        game_over = False

    def _project_y(self, rel):
        if rel <= 1.8:
            return self.PLAY_H - 1
        if rel > 72.0:
            return -1
        span = self.PLAY_H - self.HORIZON
        p = math.sqrt(1.8 / rel)
        y = self.HORIZON + int(p * span)
        if y < self.HORIZON:
            y = self.HORIZON
        elif y >= self.PLAY_H:
            y = self.PLAY_H - 1
        return y

    def _draw_hovercar(self, sp, sx, sy, size, kind):
        if size < 2:
            size = 2
        half = size // 2
        if kind == 1:
            body = (255, 90, 30)
            glow = (255, 220, 40)
        else:
            body = (35, 210, 255)
            glow = (255, 35, 200)
        y0 = sy - size
        y1 = sy
        for y in range(y0, y1 + 1):
            if y < 0 or y >= self.PLAY_H:
                continue
            rel_y = y - y0
            row_half = max(1, half - abs(rel_y - size // 2) // 2)
            for x in range(sx - row_half, sx + row_half + 1):
                if 0 <= x < WIDTH:
                    if abs(x - sx) == row_half:
                        sp(x, y, glow[0], glow[1], glow[2])
                    else:
                        sp(x, y, body[0], body[1], body[2])
        for x in (sx - half - 1, sx + half + 1):
            if 0 <= x < WIDTH and 0 <= sy < self.PLAY_H:
                sp(x, sy, 255, 255, 255)

    def _draw_energy_gate(self, sp, sx, sy, size):
        half = max(2, size // 2)
        top = sy - size - 1
        for x in range(sx - half, sx + half + 1):
            if 0 <= x < WIDTH and 0 <= top < self.PLAY_H:
                sp(x, top, 60, 255, 110)
        for y in range(top, sy + 1):
            if 0 <= y < self.PLAY_H:
                for x in (sx - half, sx + half):
                    if 0 <= x < WIDTH:
                        sp(x, y, 30, 220, 120)
        if 0 <= sx < WIDTH and 0 <= sy - half < self.PLAY_H:
            sp(sx, sy - half, 255, 255, 160)

    def _render(self):
        sp = display.set_pixel
        base_curve = self._track_curve(self.pos)
        shake = self.bump_flash if self.bump_flash > 0 else 0
        if shake:
            shake = (shake & 1) * 2 - 1

        # Sky and distant skyline.
        for y in range(self.HORIZON):
            r = 5 + y * 2
            g = 5 + y
            b = 24 + y * 3
            if self.boost_flash:
                b += 28
            for x in range(WIDTH):
                sp(x, y, r, g, b if b < 255 else 255)
        for x in range(0, WIDTH, 7):
            h = 2 + ((x * 5 + int(self.pos)) % 6)
            for y in range(self.HORIZON - h, self.HORIZON):
                if 0 <= y < self.PLAY_H:
                    sp(x, y, 22, 22, 42)
                    if x + 1 < WIDTH:
                        sp(x + 1, y, 22, 22, 42)

        for y in range(self.HORIZON, self.PLAY_H):
            depth = self.row_depth[y]
            p = (y - self.HORIZON + 1) / (self.PLAY_H - self.HORIZON)
            curve = self._track_curve(self.pos + depth)
            center = WIDTH // 2 + int((curve - base_curve) * 0.72) - int(self.lane * p * 28.0) + shake
            half = 3 + int(p * p * 34.0)
            self.row_center[y] = center
            self.row_half[y] = half
            left = center - half
            right = center + half
            stripe = int((self.pos + depth) * 0.23) & 1
            for x in range(WIDTH):
                if left <= x <= right:
                    edge = (x == left or x == right or x == left + 1 or x == right - 1)
                    lane_mark = abs(x - center) <= 1 and (int((self.pos + depth) * 0.45) & 3) < 2
                    side_mark = (abs(x - (center - half // 2)) <= 1 or abs(x - (center + half // 2)) <= 1) and stripe
                    if edge:
                        if self.boost_flash:
                            sp(x, y, 255, 80, 255)
                        else:
                            sp(x, y, 35, 230, 255)
                    elif lane_mark:
                        sp(x, y, 255, 245, 160)
                    elif side_mark:
                        sp(x, y, 110, 120, 150)
                    else:
                        shade = 26 + int(p * 58)
                        if stripe:
                            shade += 12
                        if self.bump_flash:
                            sp(x, y, 120, 22, 24)
                        else:
                            sp(x, y, shade, shade + 6, shade + 18)
                else:
                    dist_edge = left - x if x < left else x - right
                    glow = 70 - dist_edge * 5
                    if glow > 0:
                        sp(x, y, glow // 3, glow, glow)
                    else:
                        ground = 8 + int(p * 16)
                        sp(x, y, ground, 7, 18 + int(p * 10))

        visible = []
        for obj in self.objects:
            rel = obj[0] - self.pos
            if 1.2 < rel < 72.0:
                visible.append((rel, obj))
        visible.sort(reverse=True)
        for rel, obj in visible:
            y = self._project_y(rel)
            if y < self.HORIZON:
                continue
            center = self.row_center[y]
            half = self.row_half[y]
            lane = self._object_lane(obj)
            sx = center + int(lane * half)
            size = int(36 / rel) + 2
            if size > 13:
                size = 13
            if obj[2] == 2:
                self._draw_energy_gate(sp, sx, y, size + 3)
            else:
                self._draw_hovercar(sp, sx, y, size, obj[2])

        # Player hovercraft and cockpit line.
        car_y = self.PLAY_H - 4
        car_x = WIDTH // 2
        if self.bump_flash:
            car_col = (255, 50, 35)
        elif self.boost_flash:
            car_col = (255, 255, 255)
        else:
            car_col = (245, 245, 255)
        for dy, w in ((0, 2), (1, 4), (2, 6), (3, 4)):
            yy = car_y + dy
            for x in range(car_x - w, car_x + w + 1):
                if 0 <= x < WIDTH and 0 <= yy < self.PLAY_H:
                    if abs(x - car_x) == w:
                        sp(x, yy, 255, 45, 210)
                    else:
                        sp(x, yy, car_col[0], car_col[1], car_col[2])
        if self.boost_flash:
            for x in range(car_x - 2, car_x + 3):
                sp(x, self.PLAY_H - 1, 80, 180, 255)

        # Top playfield status: lap and energy.
        draw_rectangle(0, 0, WIDTH - 1, 0, 0, 0, 0)
        draw_text_small(1, 1, "L" + str(self.lap), 255, 255, 255)
        bar = int(self.energy * 24 / 100)
        draw_rectangle(WIDTH - 27, 1, WIDTH - 3, 3, 20, 20, 20)
        if bar > 0:
            br, bg, bb = (40, 230, 100) if self.energy > 30 else (255, 80, 30)
            draw_rectangle(WIDTH - 27, 1, WIDTH - 28 + bar, 3, br, bg, bb)

        display_score_and_time(self.score)

    def _build_step(self, joystick):
        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            d = joystick.read_direction([
                JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT,
                JOYSTICK_UP_LEFT, JOYSTICK_UP_RIGHT, JOYSTICK_DOWN_LEFT, JOYSTICK_DOWN_RIGHT
            ], debounce=False)
            self._update(d, z_button)
            if game_over:
                return False
            self._render()
            if (self.frame % 90) == 0:
                gc.collect()
            return True
        return step

    def main_loop(self, joystick):
        begin_game(0)
        self.reset()
        display.clear()
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        begin_game(0)
        self.reset()
        display.clear()
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))



class StackerGame:
    """
    STACKER
    Controls:
      - Z: lock the moving block
      - C: return to menu
    Stack each moving layer on top of the previous one. Missing overlap ends the run.
    """
    FRAME_MS = 45
    LAYER_H = 3
    OVERLAP_GRACE = 2

    def __init__(self):
        self.reset()

    def reset(self):
        self.locked = []  # (x, y, w, hue_index)
        self.score = 0
        self.bar_w = 34
        self.bar_x = 0
        self.bar_y = PLAY_HEIGHT - self.LAYER_H
        self.dir = 1
        self.speed = 1
        self.prev_x = 0
        self.prev_w = WIDTH
        self.last_z = False
        self.won = False
        display.clear()
        display_score_and_time(0, force=True)

    def _color(self, n):
        return hsb_to_rgb((n * 31) % 360, 1, 1)

    def _draw(self):
        display.clear()
        for x, y, w, n in self.locked:
            r, g, b = self._color(n)
            draw_rectangle(x, y, x + w - 1, y + self.LAYER_H - 1, r, g, b)
        r, g, b = self._color(self.score + 3)
        draw_rectangle(self.bar_x, self.bar_y,
                       self.bar_x + self.bar_w - 1,
                       self.bar_y + self.LAYER_H - 1,
                       r, g, b)
        display_score_and_time(self.score)

    def _drop(self):
        ox = max(self.bar_x, self.prev_x)
        right = min(self.bar_x + self.bar_w, self.prev_x + self.prev_w)
        if right <= ox and abs(right - ox) <= self.OVERLAP_GRACE:
            if self.bar_x < self.prev_x:
                ox = self.prev_x
                right = min(self.prev_x + 2, self.prev_x + self.prev_w)
            else:
                right = self.prev_x + self.prev_w
                ox = max(self.prev_x, right - 2)
        if right <= ox:
            set_game_over_score(self.score, won=False)
            return False
        if right - ox < self.bar_w and (self.bar_w - (right - ox)) <= self.OVERLAP_GRACE:
            ox = max(0, ox - 1)
            right = min(WIDTH, right + 1)
        self.bar_x = ox
        self.bar_w = right - ox
        self.locked.append((self.bar_x, self.bar_y, self.bar_w, self.score))
        self.prev_x = self.bar_x
        self.prev_w = self.bar_w
        self.score += 1
        if self.bar_y <= 0:
            self.won = True
            set_game_over_score(self.score + 50, won=True)
            return False
        self.bar_y -= self.LAYER_H
        self.speed = 1 + min(3, self.score // 6)
        if random.randint(0, 1):
            self.bar_x = 0
            self.dir = 1
        else:
            self.bar_x = WIDTH - self.bar_w
            self.dir = -1
        return True

    def _build_step(self, joystick):
        global game_over, global_score
        game_over = False
        global_score = 0
        self.reset()

        def step():
            global global_score
            c_button, z_button = joystick.read_buttons()
            if c_button or game_over:
                return False
            self.bar_x += self.dir * self.speed
            if self.bar_x <= 0:
                self.bar_x = 0
                self.dir = 1
            elif self.bar_x + self.bar_w >= WIDTH:
                self.bar_x = WIDTH - self.bar_w
                self.dir = -1
            if z_button and not self.last_z:
                if not self._drop():
                    return False
            self.last_z = z_button
            global_score = self.score
            self._draw()
            return True

        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))
        if self.won:
            show_center_message(("YOU", "WON"), start_y=18, line_height=15,
                                r=0, g=255, b=0, score=global_score, delay_ms=900)

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))
        if self.won:
            await show_center_message_async(("YOU", "WON"), start_y=18, line_height=15,
                                            r=0, g=255, b=0, score=global_score,
                                            delay_ms=900)


class FroggerGame:
    """
    FROGGR
    Controls:
      - Left / Right / Up / Down: hop
      - C: return to menu
    Cross traffic lanes. Each successful crossing makes the next level harder.
    """
    FRAME_MS = 48
    PLAYER_W = 3
    PLAYER_H = 3

    def __init__(self):
        self.reset()

    def reset(self):
        self.score = 0
        self.level = 1
        self.player_x = WIDTH // 2
        self.player_y = PLAY_HEIGHT - self.PLAYER_H
        self.last_move = ticks_ms()
        self.lanes = []
        self._build_lanes()

    def _build_lanes(self):
        self.lanes = []
        lane_count = min(5, 3 + ((self.level - 1) // 3))
        spacing = PLAY_HEIGHT // (lane_count + 1)
        self.move_ms = max(130, 175 - self.level * 5)
        for i in range(lane_count):
            y = PLAY_HEIGHT - ((i + 1) * spacing) - 1
            if y < 8:
                y = 8
            direction = -1 if i % 2 else 1
            speed_mag = 1 + min(3, (self.level + i - 1) // 3)
            speed = direction * speed_mag
            w = min(12, 6 + (i % 2) * 2 + ((self.level - 1) // 4))
            gap = max(20, 36 - self.level * 2 - i)
            cars = []
            for x in range((i * 13) % gap, WIDTH + gap, gap):
                cars.append([float(x), w])
            hue = (i * 70 + self.level * 11 + 8) % 360
            self.lanes.append([y, speed, cars, hue, gap])

    def _reset_player(self):
        self.player_x = WIDTH // 2
        self.player_y = PLAY_HEIGHT - self.PLAYER_H

    def _move_player(self, joystick):
        now = ticks_ms()
        if ticks_diff(now, self.last_move) < self.move_ms:
            return
        d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
        if not d:
            return
        dx, dy = direction_to_delta(d)
        self.player_x = clamp(self.player_x + dx * 4, 0, WIDTH - self.PLAYER_W)
        self.player_y = clamp(self.player_y + dy * 4, 0, PLAY_HEIGHT - self.PLAYER_H)
        self.last_move = now

    def _move_cars(self):
        for lane in self.lanes:
            speed = lane[1]
            cars = lane[2]
            gap = lane[4]
            for car in cars:
                car[0] += speed
                if speed > 0 and car[0] > WIDTH + car[1]:
                    car[0] = -float(car[1] + gap // 2)
                elif speed < 0 and car[0] < -car[1] - 8:
                    car[0] = float(WIDTH + gap // 2)

    def _hit_car(self):
        px = int(self.player_x)
        py = int(self.player_y)
        for lane in self.lanes:
            y = lane[0]
            for car in lane[2]:
                cx = int(car[0])
                cw = int(car[1])
                if rects_overlap(px, py, self.PLAYER_W, self.PLAYER_H, cx, y, cw, 3):
                    return True
        return False

    def _draw(self):
        display.clear()
        draw_rectangle(0, 0, WIDTH - 1, 1, 0, 120, 0)
        draw_rectangle(0, PLAY_HEIGHT - 2, WIDTH - 1, PLAY_HEIGHT - 1, 0, 60, 0)
        for lane in self.lanes:
            y = lane[0]
            r, g, b = hsb_to_rgb(lane[3], 1, 1)
            for car in lane[2]:
                x = int(car[0])
                w = int(car[1])
                draw_rectangle(x, y, x + w - 1, y + 2, r, g, b)
        draw_rectangle(self.player_x, self.player_y,
                       self.player_x + self.PLAYER_W - 1,
                       self.player_y + self.PLAYER_H - 1,
                       0, 255, 80)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        global game_over, global_score
        game_over = False
        global_score = 0
        self.reset()
        display_score_and_time(0, force=True)

        def step():
            global game_over, global_score
            c_button, _z_button = joystick.read_buttons()
            if c_button:
                return False
            self._move_player(joystick)
            self._move_cars()
            if self._hit_car():
                global_score = self.score
                game_over = True
                return False
            if self.player_y <= 1:
                self.score += 10 * self.level
                self.level += 1
                self._build_lanes()
                self._reset_player()
            global_score = self.score
            self._draw()
            return True

        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class CatchGame:
    """
    CATCH
    Controls:
      - Left / Right: move basket
      - Z: quick slide
      - C: return to menu
    Catch stars, avoid bombs, and do not miss too many stars.
    """
    FRAME_MS = 36
    MAX_DROPS = 9

    def __init__(self):
        self.reset()

    def reset(self):
        self.basket_x = WIDTH // 2 - 4
        self.basket_w = 9
        self.score = 0
        self.missed = 0
        self.drops = []
        self.last_spawn = ticks_ms()
        self.spawn_ms = 520

    def _spawn_drop(self):
        if len(self.drops) >= self.MAX_DROPS:
            return
        is_bomb = random.randint(0, 5) == 0
        x = random.randint(1, WIDTH - 3)
        speed = 1 + min(3, self.score // 10)
        hue = 0 if is_bomb else (45 + random.randint(0, 45))
        self.drops.append([x, 0, speed, is_bomb, hue])

    def _move_basket(self, joystick, z_button):
        d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT])
        step = 4 if z_button else 2
        if d == JOYSTICK_LEFT:
            self.basket_x = max(0, self.basket_x - step)
        elif d == JOYSTICK_RIGHT:
            self.basket_x = min(WIDTH - self.basket_w, self.basket_x + step)

    def _advance_drops(self):
        global game_over, global_score
        keep = []
        by = PLAY_HEIGHT - 2
        for drop in self.drops:
            drop[1] += drop[2]
            x = drop[0]
            y = drop[1]
            is_bomb = drop[3]
            caught = (y >= by - 1 and self.basket_x <= x <= self.basket_x + self.basket_w - 1)
            if caught:
                if is_bomb:
                    global_score = self.score
                    game_over = True
                    return
                self.score += 1
                if self.spawn_ms > 190 and self.score % 5 == 0:
                    self.spawn_ms -= 25
                continue
            if y >= PLAY_HEIGHT:
                if not is_bomb:
                    self.missed += 1
                    if self.missed >= 5:
                        global_score = self.score
                        game_over = True
                        return
                continue
            keep.append(drop)
        self.drops = keep

    def _draw(self):
        display.clear()
        for drop in self.drops:
            x = int(drop[0])
            y = int(drop[1])
            if drop[3]:
                draw_rectangle(x - 1, y, x + 1, y + 1, 255, 0, 0)
            else:
                r, g, b = hsb_to_rgb(drop[4], 1, 1)
                display.set_pixel(x, y, r, g, b)
                if y > 0:
                    display.set_pixel(x, y - 1, r // 3, g // 3, b // 3)
        draw_rectangle(self.basket_x, PLAY_HEIGHT - 2,
                       self.basket_x + self.basket_w - 1, PLAY_HEIGHT - 1,
                       0, 180, 255)
        for i in range(self.missed):
            display.set_pixel(WIDTH - 1 - i, 0, 255, 40, 0)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        global game_over, global_score
        game_over = False
        global_score = 0
        self.reset()
        display_score_and_time(0, force=True)

        def step():
            global game_over, global_score
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            now = ticks_ms()
            if ticks_diff(now, self.last_spawn) >= self.spawn_ms:
                self._spawn_drop()
                self.last_spawn = now
            self._move_basket(joystick, z_button)
            self._advance_drops()
            if game_over:
                return False
            global_score = self.score
            self._draw()
            return True

        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))

class MinesGame:
    """
    MINES
    Controls:
      - Directions: move cursor
      - Z: reveal field
      - C: return to menu
    Reveal every safe field without stepping on a mine.
    """
    FRAME_MS = 45
    GRID_W = 8
    GRID_H = 7
    CELL = 7
    MINES = 9

    def __init__(self):
        self.reset()

    def reset(self):
        self.cursor_x = 0
        self.cursor_y = 0
        self.score = 0
        self.last_move = ticks_ms()
        self.last_z = False
        self.revealed = [[False for _x in range(self.GRID_W)] for _y in range(self.GRID_H)]
        self.mines = [[False for _x in range(self.GRID_W)] for _y in range(self.GRID_H)]
        placed = 0
        while placed < self.MINES:
            x = random.randint(0, self.GRID_W - 1)
            y = random.randint(0, self.GRID_H - 1)
            if (x > 1 or y > 1) and not self.mines[y][x]:
                self.mines[y][x] = True
                placed += 1

    def _count(self, x, y):
        n = 0
        for yy in range(y - 1, y + 2):
            for xx in range(x - 1, x + 2):
                if 0 <= xx < self.GRID_W and 0 <= yy < self.GRID_H and self.mines[yy][xx]:
                    n += 1
        return n

    def _reveal(self, x, y):
        if self.revealed[y][x]:
            return True
        self.revealed[y][x] = True
        self.score += 1
        if self.mines[y][x]:
            return False
        if self._count(x, y) == 0:
            for yy in range(y - 1, y + 2):
                for xx in range(x - 1, x + 2):
                    if 0 <= xx < self.GRID_W and 0 <= yy < self.GRID_H and not self.revealed[yy][xx]:
                        if not self.mines[yy][xx]:
                            self._reveal(xx, yy)
        return True

    def _safe_revealed(self):
        total = 0
        for y in range(self.GRID_H):
            for x in range(self.GRID_W):
                if self.revealed[y][x] and not self.mines[y][x]:
                    total += 1
        return total

    def _move_cursor(self, joystick):
        now = ticks_ms()
        if ticks_diff(now, self.last_move) < 135:
            return
        d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
        dx, dy = direction_to_delta(d)
        if dx or dy:
            self.cursor_x = clamp(self.cursor_x + dx, 0, self.GRID_W - 1)
            self.cursor_y = clamp(self.cursor_y + dy, 0, self.GRID_H - 1)
            self.last_move = now

    def _draw(self):
        display.clear()
        ox = 4
        oy = 4
        for y in range(self.GRID_H):
            for x in range(self.GRID_W):
                px = ox + x * self.CELL
                py = oy + y * self.CELL
                if self.revealed[y][x]:
                    if self.mines[y][x]:
                        draw_rectangle(px + 2, py + 2, px + 4, py + 4, 255, 0, 0)
                    else:
                        draw_rectangle(px, py, px + 5, py + 5, 18, 30, 38)
                        n = self._count(x, y)
                        if n:
                            draw_text_small(px + 1, py, str(n), 40 + n * 25, 220, 255 - n * 18)
                else:
                    draw_rectangle(px, py, px + 5, py + 5, 24, 58, 78)
            display.set_pixel(0, 0, 0, 0, 0)
        cx = ox + self.cursor_x * self.CELL
        cy = oy + self.cursor_y * self.CELL
        draw_rect_outline(cx - 1, cy - 1, cx + 6, cy + 6, 255, 255, 255)
        display_score_and_time(self._safe_revealed())

    def _build_step(self, joystick):
        global game_over, global_score
        game_over = False
        global_score = 0
        self.reset()
        display_score_and_time(0, force=True)

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            self._move_cursor(joystick)
            if z_button and not self.last_z:
                if not self._reveal(self.cursor_x, self.cursor_y):
                    set_game_over_score(self._safe_revealed())
                    return False
                safe = self.GRID_W * self.GRID_H - self.MINES
                if self._safe_revealed() >= safe:
                    set_game_over_score(safe + 50, won=True)
                    return False
            self.last_z = z_button
            self._draw()
            return True

        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class ClimberGame:
    """
    CLIMB
    Controls:
      - Left / Right: drift
      - Z: short jet jump
      - C: return to menu
    Jump from platform to platform while the tower scrolls down.
    """
    FRAME_MS = 35

    def __init__(self):
        self.reset()

    def reset(self):
        self.x = WIDTH // 2
        self.y = PLAY_HEIGHT - 12
        self.vy = -2.2
        self.score = 0
        self.platforms = []
        for i in range(8):
            self.platforms.append([random.randint(2, WIDTH - 16), PLAY_HEIGHT - i * 8, 14])

    def _move(self, joystick, z_button):
        d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT])
        if d == JOYSTICK_LEFT:
            self.x -= 2
        elif d == JOYSTICK_RIGHT:
            self.x += 2
        if self.x < -3:
            self.x = WIDTH - 1
        elif self.x >= WIDTH:
            self.x = -2
        self.vy += 0.18
        if z_button and self.vy > -1.5:
            self.vy -= 0.34
        self.y += self.vy

    def _collide_platforms(self):
        if self.vy <= 0:
            return
        px = int(self.x)
        py = int(self.y)
        for p in self.platforms:
            if py + 3 >= p[1] and py + 3 <= p[1] + 2 and px + 3 >= p[0] and px <= p[0] + p[2]:
                self.vy = -3.4
                self.score += 1
                break

    def _scroll(self):
        if self.y < 22:
            dy = 22 - self.y
            self.y = 22
            self.score += int(dy)
            for p in self.platforms:
                p[1] += dy
        keep = []
        for p in self.platforms:
            if p[1] < PLAY_HEIGHT:
                keep.append(p)
        self.platforms = keep
        while len(self.platforms) < 8:
            top = PLAY_HEIGHT
            for p in self.platforms:
                if p[1] < top:
                    top = p[1]
            w = max(7, 14 - self.score // 80)
            self.platforms.append([random.randint(1, WIDTH - w - 1), top - random.randint(7, 10), w])

    def _draw(self):
        display.clear()
        for p in self.platforms:
            hue = (120 + p[1] * 3) % 360
            r, g, b = hsb_to_rgb(hue, 1, 1)
            draw_rectangle(p[0], int(p[1]), p[0] + p[2], int(p[1]) + 1, r, g, b)
        draw_rectangle(int(self.x), int(self.y), int(self.x) + 3, int(self.y) + 3, 255, 255, 255)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        game_over = False
        self.reset()
        display_score_and_time(0, force=True)

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            self._move(joystick, z_button)
            self._collide_platforms()
            self._scroll()
            if self.y > PLAY_HEIGHT + 5:
                set_game_over_score(self.score)
                return False
            self._draw()
            return not game_over

        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class ArenaGame:
    """
    ARENA
    Controls:
      - Directions: move
      - Z: fire
      - C: return to menu
    Survive enemy waves in a small arena.
    """
    FRAME_MS = 38
    INVINCIBLE_MS = 1200

    def __init__(self):
        self.reset()

    def reset(self):
        self.x = WIDTH // 2
        self.y = PLAY_HEIGHT // 2
        self.dir = JOYSTICK_UP
        self.score = 0
        self.wave = 1
        self.lives = 3
        self.frame = 0
        self.enemies = []
        self.shots = []
        self.sparks = []   # [x, y, dx, dy, ttl]
        self.last_shot = 0
        self.invincible_until = 0
        self.flash_until = 0
        self._spawn_wave()

    def _spawn_wave(self):
        self.enemies = []
        count = min(10, 3 + (self.wave + 1) // 2)
        fast_count = min(count // 2, max(0, (self.wave - 3) // 3))
        for i in range(count):
            edge = random.randint(0, 3)
            if edge == 0:
                x, y = random.randint(0, WIDTH - 3), 0
            elif edge == 1:
                x, y = random.randint(0, WIDTH - 3), PLAY_HEIGHT - 3
            elif edge == 2:
                x, y = 0, random.randint(0, PLAY_HEIGHT - 3)
            else:
                x, y = WIDTH - 3, random.randint(0, PLAY_HEIGHT - 3)
            speed = 2 if i < fast_count else 1
            self.enemies.append([x, y, speed])

    def _move_player(self, joystick):
        d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
        dx, dy = direction_to_delta(d)
        if dx or dy:
            self.dir = d
            self.x = clamp(self.x + dx * 2, 1, WIDTH - 4)
            self.y = clamp(self.y + dy * 2, 1, PLAY_HEIGHT - 4)

    def _fire(self):
        now = ticks_ms()
        if ticks_diff(now, self.last_shot) < 160:
            return
        dx, dy = direction_to_delta(self.dir, 0, -1)
        self.shots.append([float(self.x + 1), float(self.y + 1), dx * 4.0, dy * 4.0])
        self.last_shot = now

    def _advance(self):
        self.frame += 1
        keep = []
        for s in self.shots:
            s[0] += s[2]
            s[1] += s[3]
            if 0 <= s[0] < WIDTH and 0 <= s[1] < PLAY_HEIGHT:
                keep.append(s)
        self.shots = keep
        step_delay = max(3, 6 - self.wave // 3)
        if self.frame % step_delay == 0:
            for e in self.enemies:
                spd = e[2]
                if e[0] < self.x:
                    e[0] = min(e[0] + spd, self.x)
                elif e[0] > self.x:
                    e[0] = max(e[0] - spd, self.x)
                if e[1] < self.y:
                    e[1] = min(e[1] + spd, self.y)
                elif e[1] > self.y:
                    e[1] = max(e[1] - spd, self.y)
        # advance sparks
        keep_sparks = []
        for sp in self.sparks:
            sp[0] += sp[2]
            sp[1] += sp[3]
            sp[4] -= 1
            if sp[4] > 0 and 0 <= sp[0] < WIDTH and 0 <= sp[1] < PLAY_HEIGHT:
                keep_sparks.append(sp)
        self.sparks = keep_sparks
        survivors = []
        for e in self.enemies:
            hit = False
            for s in self.shots:
                if rects_overlap(int(s[0]), int(s[1]), 2, 2, e[0], e[1], 3, 3):
                    hit = True
                    s[0] = -99
                    self.score += 5 + self.wave
                    self.flash_until = ticks_ms() + 80
                    # spawn explosion sparks
                    ex, ey = e[0] + 1, e[1] + 1
                    for _ in range(5):
                        sdx = random.randint(-2, 2)
                        sdy = random.randint(-2, 2)
                        self.sparks.append([float(ex), float(ey), sdx, sdy, 5])
                    break
            if not hit:
                survivors.append(e)
        self.enemies = survivors
        if not self.enemies:
            self.wave += 1
            self.score += 15 + self.wave * 5
            self._spawn_wave()

    def _hit_player(self):
        now = ticks_ms()
        if ticks_diff(now, self.invincible_until) < 0:
            return -1
        for i, e in enumerate(self.enemies):
            if rects_overlap(self.x, self.y, 3, 3, e[0], e[1], 3, 3):
                return i
        return -1

    def _draw(self):
        display.clear()
        now = ticks_ms()
        flashing = ticks_diff(now, self.flash_until) < 0
        border_r = 255 if flashing else 28
        border_g = 255 if flashing else 28
        border_b = 42
        draw_rect_outline(0, 0, WIDTH - 1, PLAY_HEIGHT - 1, border_r, border_g, border_b)
        for sp in self.sparks:
            display.set_pixel(int(sp[0]), int(sp[1]), 255, 160, 0)
        for s in self.shots:
            display.set_pixel(int(s[0]), int(s[1]), 255, 255, 0)
        for e in self.enemies:
            g = 50 if e[2] == 1 else 160
            draw_rectangle(e[0], e[1], e[0] + 2, e[1] + 2, 255, g, 0)
        invincible = ticks_diff(now, self.invincible_until) < 0
        if not invincible or (self.frame // 3) % 2 == 0:
            draw_rectangle(self.x, self.y, self.x + 2, self.y + 2, 0, 220, 255)
        draw_text_small(1, 1, "W" + str(self.wave), 200, 200, 200)
        for i in range(self.lives):
            draw_rectangle(WIDTH - 5 - i * 4, 1, WIDTH - 3 - i * 4, 2, 255, 60, 60)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        self.reset()
        display_score_and_time(0, force=True)

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            self._move_player(joystick)
            if z_button:
                self._fire()
            self._advance()
            hit_i = self._hit_player()
            if hit_i >= 0:
                del self.enemies[hit_i]
                self.lives -= 1
                self.invincible_until = ticks_ms() + self.INVINCIBLE_MS
                if self.lives <= 0:
                    set_game_over_score(self.score)
                    return False
            self._draw()
            return True

        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class DefuseGame:
    """
    DEFUSE
    Controls:
      - Left / Right: choose wire
      - Z: cut wire
      - C: return to menu
    Memorize and cut wire colors in the requested order before the timer expires.
    """
    FRAME_MS = 45
    WIRE_X = (6, 19, 32, 45, 58)
    WIRE_COLORS = ((255, 0, 0), (0, 180, 255), (255, 230, 0), (0, 255, 70), (255, 0, 210))

    def __init__(self):
        self.reset()

    def reset(self):
        self.cursor = 0
        self.score = 0
        self.round = 1
        self.last_move = ticks_ms()
        self.last_z = False
        self.wrong_flash_until = 0
        self.wrong_strikes = 0   # strikes per bomb; 2nd wrong = game over
        self._new_bomb()

    def _new_bomb(self):
        length = min(5, 2 + self.round // 2)
        self.sequence = []
        while len(self.sequence) < length:
            v = random.randint(0, 4)
            if v not in self.sequence:
                self.sequence.append(v)
        self.cut_index = 0
        self.cut = [False, False, False, False, False]
        self.started = ticks_ms()
        self.limit_ms = max(4000, 10000 - self.round * 400)
        self.wrong_strikes = 0

    def _move_cursor(self, joystick):
        now = ticks_ms()
        if ticks_diff(now, self.last_move) < 130:
            return
        d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT])
        if d == JOYSTICK_LEFT:
            self.cursor = max(0, self.cursor - 1)
            self.last_move = now
        elif d == JOYSTICK_RIGHT:
            self.cursor = min(4, self.cursor + 1)
            self.last_move = now

    def _cut_wire(self):
        """Returns True = continue, False = game over."""
        if self.cut[self.cursor]:
            return True
        if self.sequence[self.cut_index] != self.cursor:
            self.wrong_flash_until = ticks_ms() + 500
            self.wrong_strikes += 1
            # First strike: burn 2.5 s off the clock and continue
            if self.wrong_strikes < 2:
                self.started -= 2500
                return True
            # Second strike: detonate
            return False
        self.cut[self.cursor] = True
        self.cut_index += 1
        self.score += 5
        if self.cut_index >= len(self.sequence):
            self.score += max(1, (self.limit_ms - ticks_diff(ticks_ms(), self.started)) // 200)
            self.round += 1
            self._new_bomb()
        return True

    def _draw(self):
        display.clear()
        now = ticks_ms()
        elapsed = ticks_diff(now, self.started)
        left = max(0, self.limit_ms - elapsed)
        bar = int((WIDTH - 2) * left / self.limit_ms)
        urgent = left < 2500
        draw_rectangle(1, 1, bar, 3, 255, 40 if urgent else 220, 0)
        for i, idx in enumerate(self.sequence):
            r, g, b = self.WIRE_COLORS[idx]
            dim = i < self.cut_index
            draw_rectangle(8 + i * 10, 7, 13 + i * 10, 10, r // 3 if dim else r, g // 3 if dim else g, b // 3 if dim else b)
            if i == self.cut_index:
                draw_rect_outline(7 + i * 10, 6, 14 + i * 10, 11, 255, 255, 255)
        wrong_flash = ticks_diff(now, self.wrong_flash_until) < 0
        for i, x in enumerate(self.WIRE_X):
            r, g, b = self.WIRE_COLORS[i]
            if self.cut[i]:
                draw_rectangle(x - 2, 18, x + 2, 46, 30, 30, 30)
                draw_line(x - 3, 31, x + 3, 26, 255, 255, 255)
            else:
                is_next = (self.cut_index < len(self.sequence) and self.sequence[self.cut_index] == i)
                if is_next and (now // 200) % 2 == 0:
                    draw_rectangle(x - 1, 16, x + 1, 49, min(255, r + 80), min(255, g + 80), min(255, b + 80))
                else:
                    draw_rectangle(x - 1, 16, x + 1, 49, r, g, b)
        x = self.WIRE_X[self.cursor]
        cx_r, cx_g, cx_b = (255, 0, 0) if wrong_flash else (255, 255, 255)
        draw_rect_outline(x - 5, 14, x + 5, 51, cx_r, cx_g, cx_b)
        draw_text_small(1, 52, "R" + str(self.round), 160, 160, 160)
        if self.wrong_strikes > 0:
            draw_rectangle(WIDTH - 6, 52, WIDTH - 2, 56, 255, 0, 0)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        self.reset()
        display_score_and_time(0, force=True)

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            if ticks_diff(ticks_ms(), self.started) > self.limit_ms:
                set_game_over_score(self.score)
                return False
            self._move_cursor(joystick)
            if z_button and not self.last_z:
                if not self._cut_wire():
                    set_game_over_score(self.score)
                    return False
            self.last_z = z_button
            # wrong-strike visual: show strike count
            self._draw()
            return True

        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class BilliardsGame:
    """
    BILLI
    Controls:
      - Left / Right: aim
      - Up / Down: set power
      - Z: strike cue ball
      - C: return to menu
    Compact billiards with Pool/Snooker setups, pockets, rails, and ball physics.
    """
    FRAME_MS = 34
    LEFT = 4
    RIGHT = WIDTH - 5
    TOP = 4
    BOTTOM = PLAY_HEIGHT - 4
    BALL_R = 1.45
    FRICTION = 0.982
    RESTITUTION = 0.92

    def __init__(self, ctx=None):
        self.rules = get_context_setting(ctx, "rules", "pool")
        self.long_aim = get_context_setting(ctx, "aim", "short") == "long"
        self.reset()

    def reset(self):
        self.score = 0
        self.strokes = 0
        self.angle = 0
        self.power = 5
        self.last_z = False
        self.aim_hold_dir = None
        self.aim_hold_count = 0
        self.power_hold_dir = None
        self.power_hold_count = 0
        self.foul_flash = 0
        self.win_pending = False
        self._rack()

    def _ball(self, x, y, color, value, active=True):
        return [float(x), float(y), 0.0, 0.0, color, int(value), bool(active)]

    def _rack(self):
        self.balls = []
        self.balls.append(self._ball(16, (self.TOP + self.BOTTOM) // 2, (245, 245, 245), 0))
        if self.rules == "snooker":
            reds = ((43, 25), (46, 23), (46, 27), (49, 21), (49, 25), (49, 29))
            for x, y in reds:
                self.balls.append(self._ball(x, y, (220, 35, 35), 1))
            colors = (
                (39, 18, (255, 230, 40), 2),
                (39, 36, (60, 220, 80), 3),
                (51, 25, (40, 80, 255), 5),
                (53, 20, (255, 80, 220), 6),
                (53, 31, (20, 20, 20), 7),
            )
            for x, y, col, val in colors:
                self.balls.append(self._ball(x, y, col, val))
        else:
            rack = (
                (43, 29, (255, 210, 35), 1),
                (46, 27, (35, 80, 255), 2),
                (46, 31, (255, 50, 50), 3),
                (49, 25, (150, 70, 255), 4),
                (49, 29, (255, 135, 35), 5),
                (49, 33, (40, 210, 90), 6),
                (52, 29, (20, 20, 20), 8),
            )
            for x, y, col, val in rack:
                self.balls.append(self._ball(x, y, col, val))

    def _pockets(self):
        mid_x = WIDTH // 2
        return (
            (self.LEFT, self.TOP), (mid_x, self.TOP), (self.RIGHT, self.TOP),
            (self.LEFT, self.BOTTOM), (mid_x, self.BOTTOM), (self.RIGHT, self.BOTTOM),
        )

    def _moving(self):
        for b in self.balls:
            if b[6] and (abs(b[2]) > 0.035 or abs(b[3]) > 0.035):
                return True
        return False

    def _draw_disc(self, cx, cy, radius, color):
        r2 = radius * radius
        for yy in range(int(cy - radius), int(cy + radius) + 1):
            for xx in range(int(cx - radius), int(cx + radius) + 1):
                dx = xx - cx
                dy = yy - cy
                if dx * dx + dy * dy <= r2:
                    set_pixel_clipped(xx, yy, color[0], color[1], color[2])

    def _reset_cue(self):
        cue = self.balls[0]
        cue[0] = 16.0
        cue[1] = float((self.TOP + self.BOTTOM) // 2)
        cue[2] = 0.0
        cue[3] = 0.0
        cue[6] = True
        for _ in range(16):
            ok = True
            for b in self.balls[1:]:
                if not b[6]:
                    continue
                dx = b[0] - cue[0]
                dy = b[1] - cue[1]
                if dx * dx + dy * dy < 18:
                    ok = False
                    break
            if ok:
                return
            cue[1] += 2.0
            if cue[1] > self.BOTTOM - 5:
                cue[1] = self.TOP + 5

    def _object_balls_left(self):
        for b in self.balls[1:]:
            if b[6]:
                return True
        return False

    def _strike(self):
        cue = self.balls[0]
        if not cue[6] or self._moving():
            return
        rad = math.radians(self.angle)
        cue[2] = math.cos(rad) * self.power * 0.47
        cue[3] = math.sin(rad) * self.power * 0.47
        self.strokes += 1

    def _aim_step_for_hold(self):
        if self.aim_hold_count <= 5:
            return 1
        return 4

    def _power_step_for_hold(self):
        if self.power_hold_count <= 4:
            return 1
        return 2

    def _handle_input(self, joystick, z_button):
        if self._moving():
            self.last_z = z_button
            self.aim_hold_dir = None
            self.aim_hold_count = 0
            self.power_hold_dir = None
            self.power_hold_count = 0
            return
        # Aim needs raw per-frame hold detection. The default debounce would
        # drop repeated held directions and prevent the fast-step mode from
        # ever kicking in reliably.
        d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT], debounce=False)
        if d == JOYSTICK_LEFT:
            if self.aim_hold_dir == d:
                self.aim_hold_count += 1
            else:
                self.aim_hold_dir = d
                self.aim_hold_count = 1
            step = self._aim_step_for_hold()
            self.angle = (self.angle - step) % 360
            self.power_hold_dir = None
            self.power_hold_count = 0
        elif d == JOYSTICK_RIGHT:
            if self.aim_hold_dir == d:
                self.aim_hold_count += 1
            else:
                self.aim_hold_dir = d
                self.aim_hold_count = 1
            step = self._aim_step_for_hold()
            self.angle = (self.angle + step) % 360
            self.power_hold_dir = None
            self.power_hold_count = 0
        elif d == JOYSTICK_UP:
            self.aim_hold_dir = None
            self.aim_hold_count = 0
            if self.power_hold_dir == d:
                self.power_hold_count += 1
            else:
                self.power_hold_dir = d
                self.power_hold_count = 1
            self.power = min(10, self.power + self._power_step_for_hold())
        elif d == JOYSTICK_DOWN:
            self.aim_hold_dir = None
            self.aim_hold_count = 0
            if self.power_hold_dir == d:
                self.power_hold_count += 1
            else:
                self.power_hold_dir = d
                self.power_hold_count = 1
            self.power = max(1, self.power - self._power_step_for_hold())
        else:
            self.aim_hold_dir = None
            self.aim_hold_count = 0
            self.power_hold_dir = None
            self.power_hold_count = 0
        if z_button and not self.last_z:
            self._strike()
        self.last_z = z_button

    def _pocket_ball(self, idx):
        ball = self.balls[idx]
        ball[2] = 0.0
        ball[3] = 0.0
        ball[6] = False
        if idx == 0:
            self.score = max(0, self.score - 20)
            self.foul_flash = 18
            return
        mult = 18 if self.rules == "snooker" else 30
        self.score += ball[5] * mult

    def _wall_bounce(self, b):
        if b[0] <= self.LEFT + self.BALL_R:
            b[0] = self.LEFT + self.BALL_R
            b[2] = abs(b[2]) * self.RESTITUTION
        elif b[0] >= self.RIGHT - self.BALL_R:
            b[0] = self.RIGHT - self.BALL_R
            b[2] = -abs(b[2]) * self.RESTITUTION
        if b[1] <= self.TOP + self.BALL_R:
            b[1] = self.TOP + self.BALL_R
            b[3] = abs(b[3]) * self.RESTITUTION
        elif b[1] >= self.BOTTOM - self.BALL_R:
            b[1] = self.BOTTOM - self.BALL_R
            b[3] = -abs(b[3]) * self.RESTITUTION

    def _collide_pair(self, a, b):
        if not a[6] or not b[6]:
            return
        dx = b[0] - a[0]
        dy = b[1] - a[1]
        min_d = self.BALL_R * 2.0
        d2 = dx * dx + dy * dy
        if d2 <= 0.0001 or d2 >= min_d * min_d:
            return
        dist = math.sqrt(d2)
        nx = dx / dist
        ny = dy / dist
        overlap = (min_d - dist) * 0.5
        a[0] -= nx * overlap
        a[1] -= ny * overlap
        b[0] += nx * overlap
        b[1] += ny * overlap
        rvx = b[2] - a[2]
        rvy = b[3] - a[3]
        vel_n = rvx * nx + rvy * ny
        if vel_n > 0:
            return
        impulse = -(1.0 + self.RESTITUTION) * vel_n * 0.5
        ix = impulse * nx
        iy = impulse * ny
        a[2] -= ix
        a[3] -= iy
        b[2] += ix
        b[3] += iy

    def _advance(self):
        if self.foul_flash > 0:
            self.foul_flash -= 1
        for _ in range(2):
            for idx, b in enumerate(self.balls):
                if not b[6]:
                    continue
                b[0] += b[2] * 0.5
                b[1] += b[3] * 0.5
                for px, py in self._pockets():
                    dx = b[0] - px
                    dy = b[1] - py
                    if dx * dx + dy * dy <= 10.5:
                        self._pocket_ball(idx)
                        break
                if not b[6]:
                    continue
                self._wall_bounce(b)
            for i in range(len(self.balls)):
                for j in range(i + 1, len(self.balls)):
                    self._collide_pair(self.balls[i], self.balls[j])
            for b in self.balls:
                if not b[6]:
                    continue
                b[2] *= self.FRICTION
                b[3] *= self.FRICTION
                if abs(b[2]) < 0.025:
                    b[2] = 0.0
                if abs(b[3]) < 0.025:
                    b[3] = 0.0
        if not self._moving() and not self.balls[0][6]:
            self._reset_cue()
        if not self._object_balls_left():
            bonus = max(0, 260 - self.strokes * 8)
            set_game_over_score(self.score + bonus, won=True)
            return False
        return True

    def _draw_table(self):
        display.clear()
        draw_rectangle(0, 0, WIDTH - 1, PLAY_HEIGHT - 1, 44, 24, 10)
        draw_rectangle(self.LEFT, self.TOP, self.RIGHT, self.BOTTOM, 8, 95, 36)
        draw_rect_outline(self.LEFT, self.TOP, self.RIGHT, self.BOTTOM, 95, 58, 24)
        draw_rect_outline(self.LEFT - 1, self.TOP - 1, self.RIGHT + 1, self.BOTTOM + 1, 130, 78, 32)
        for px, py in self._pockets():
            self._draw_disc(px, py, 3.0, (0, 0, 0))

    def _draw_aim(self):
        if self._moving() or not self.balls[0][6]:
            return
        cue = self.balls[0]
        rad = math.radians(self.angle)
        length = 26 if self.long_aim else 14
        x0 = int(cue[0])
        y0 = int(cue[1])
        x1 = int(cue[0] + math.cos(rad) * length)
        y1 = int(cue[1] + math.sin(rad) * length)
        draw_line(x0, y0, x1, y1, 255, 255, 160)
        bx = int(cue[0] - math.cos(rad) * 5)
        by = int(cue[1] - math.sin(rad) * 5)
        draw_line(bx, by, x0, y0, 170, 105, 45)

    def _draw_balls(self):
        for idx, b in enumerate(self.balls):
            if not b[6]:
                continue
            self._draw_disc(b[0], b[1], self.BALL_R + 0.5, (0, 0, 0))
            self._draw_disc(b[0], b[1], self.BALL_R, b[4])
            if idx != 0 and b[5] >= 8:
                set_pixel_clipped(int(b[0]), int(b[1]), 255, 255, 255)

    def _draw_hud(self):
        label = "SNO" if self.rules == "snooker" else "POOL"
        draw_text_small(1, 1, label, 230, 230, 230)
        if not self._moving():
            draw_text_small(21, 1, "A" + str(int(self.angle) % 360), 210, 210, 210)
            draw_rectangle(WIDTH - 13, 1, WIDTH - 3, 3, 35, 35, 35)
            draw_rectangle(WIDTH - 13, 1, WIDTH - 14 + self.power, 3, 255, 220, 50)
        if self.foul_flash:
            draw_text_small(21, 1, "FOUL", 255, 70, 45)

    def _draw(self):
        self._draw_table()
        self._draw_aim()
        self._draw_balls()
        self._draw_hud()
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        self.reset()
        begin_game(0)

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            self._handle_input(joystick, z_button)
            if not self._advance():
                return False
            self._draw()
            return True
        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class GolfGame:
    """
    GOLF
    Controls:
      - Left / Right: aim
      - Up / Down: set power
      - Z: shoot
      - C: return to menu
    Put the ball into the hole across compact obstacle courses.
    """
    FRAME_MS = 36

    def __init__(self):
        self.reset()

    def reset(self):
        self.hole = 1
        self.score = 0
        self._new_hole()

    def _new_hole(self):
        # Ball starts near bottom-left tee, hole at randomised position
        seed = self.hole * 31
        self.ball_x = float(5 + (seed % 4))
        self.ball_y = float(PLAY_HEIGHT - 8 - (seed % 6))
        self.vx = 0.0
        self.vy = 0.0
        self.angle = -45   # degrees, full 360° allowed
        self.power = 4
        self.strokes = 0
        self.par = 3 + min(2, self.hole // 4)
        self.hole_x = WIDTH - 7 - ((seed * 3) % 8)
        self.hole_y = 6 + (seed % 40)
        # Obstacles: [x, y, w, h, kind] where kind 0=tree 1=bunker 2=wall
        self.obstacles = []
        if self.hole % 2:
            gap_y = 16 + (seed % 22)
            self.obstacles.append([28, 5, 2, max(4, gap_y - 6), 2])
            self.obstacles.append([28, gap_y + 8, 2, max(4, PLAY_HEIGHT - gap_y - 13), 2])
        else:
            gap_x = 20 + (seed % 22)
            self.obstacles.append([10, 27, max(4, gap_x - 10), 2, 2])
            self.obstacles.append([gap_x + 9, 27, max(4, WIDTH - gap_x - 15), 2, 2])
        n = min(6, 2 + self.hole // 2)
        for i in range(n):
            ox = 14 + i * 7 + ((seed + i * 13) % 5)
            oy = 4 + ((seed * (i + 1) * 7) % 42)
            kind = i % 3
            if kind == 0:   # tree: small square
                self.obstacles.append([ox, oy, 4, 4, 0])
            elif kind == 1: # bunker: wide, short
                self.obstacles.append([ox - 1, oy, 6, 3, 1])
            else:           # wall: narrow, tall
                self.obstacles.append([ox, oy, 2, 8, 2])

    def _aim(self, joystick):
        d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_UP, JOYSTICK_DOWN])
        if d == JOYSTICK_LEFT:
            self.angle -= 5
        elif d == JOYSTICK_RIGHT:
            self.angle += 5
        elif d == JOYSTICK_UP:
            self.power = min(8, self.power + 1)
        elif d == JOYSTICK_DOWN:
            self.power = max(1, self.power - 1)
        # full 360° wrap
        if self.angle > 180:
            self.angle -= 360
        elif self.angle <= -180:
            self.angle += 360

    def _shoot(self):
        rad = self.angle * math.pi / 180.0
        self.vx = math.cos(rad) * self.power * 0.85
        self.vy = math.sin(rad) * self.power * 0.85
        self.strokes += 1

    def _moving(self):
        return abs(self.vx) > 0.05 or abs(self.vy) > 0.05

    def _ball_speed(self):
        return abs(self.vx) + abs(self.vy)

    def _advance_ball(self):
        self.ball_x += self.vx
        self.ball_y += self.vy
        # Wall bounces — uniform energy loss on all four walls (top-down, no gravity)
        if self.ball_x <= 1:
            self.vx = abs(self.vx) * 0.70
            self.ball_x = 1.0
        elif self.ball_x >= WIDTH - 2:
            self.vx = -abs(self.vx) * 0.70
            self.ball_x = float(WIDTH - 2)
        if self.ball_y <= 1:
            self.vy = abs(self.vy) * 0.70
            self.ball_y = 1.0
        elif self.ball_y >= PLAY_HEIGHT - 2:
            self.vy = -abs(self.vy) * 0.70
            self.ball_y = float(PLAY_HEIGHT - 2)
        # Obstacle bounce — detect dominant axis and reflect accordingly
        for o in self.obstacles:
            ox, oy, ow, oh = o[0], o[1], o[2], o[3]
            if rects_overlap(int(self.ball_x), int(self.ball_y), 2, 2, ox, oy, ow, oh):
                if o[4] == 1:
                    self.vx *= 0.72
                    self.vy *= 0.72
                    continue
                bxc = self.ball_x + 1.0
                byc = self.ball_y + 1.0
                ocx = ox + ow * 0.5
                ocy = oy + oh * 0.5
                loss = 0.65
                if abs(bxc - ocx) / ow > abs(byc - ocy) / oh:
                    self.vx = -self.vx * loss
                    self.ball_x += self.vx * 2
                else:
                    self.vy = -self.vy * loss
                    self.ball_y += self.vy * 2
        # Uniform rolling friction (grass, same in all directions — top-down)
        self.vx *= 0.96
        self.vy *= 0.96
        if abs(self.ball_x - self.hole_x) <= 4 and abs(self.ball_y - self.hole_y) <= 4:
            if self._ball_speed() < 1.35:
                self.ball_x += (self.hole_x - self.ball_x) * 0.35
                self.ball_y += (self.hole_y - self.ball_y) * 0.35
                self.vx *= 0.78
                self.vy *= 0.78
        if not self._moving():
            self.vx = 0.0
            self.vy = 0.0

    def _in_hole(self):
        return abs(self.ball_x - self.hole_x) <= 2 and abs(self.ball_y - self.hole_y) <= 2 and self._ball_speed() < 0.6

    def _draw(self):
        display.clear()
        # Fairway — solid green background
        draw_rectangle(1, 1, WIDTH - 2, PLAY_HEIGHT - 2, 18, 90, 28)
        # Border rough (darker)
        draw_rect_outline(0, 0, WIDTH - 1, PLAY_HEIGHT - 1, 10, 55, 16)
        # Obstacles
        for o in self.obstacles:
            if o[4] == 0:   # tree: dark green with brown centre
                draw_rectangle(o[0], o[1], o[0] + o[2] - 1, o[1] + o[3] - 1, 10, 65, 10)
                display.set_pixel(o[0] + 1, o[1] + 1, 100, 60, 20)
            elif o[4] == 1: # bunker: sandy
                draw_rectangle(o[0], o[1], o[0] + o[2] - 1, o[1] + o[3] - 1, 210, 185, 110)
            else:           # wall: grey
                draw_rectangle(o[0], o[1], o[0] + o[2] - 1, o[1] + o[3] - 1, 110, 110, 110)
        # Hole: dark cup with yellow flag dot
        draw_rectangle(self.hole_x - 2, self.hole_y - 2, self.hole_x + 2, self.hole_y + 2, 0, 0, 0)
        display.set_pixel(self.hole_x + 2, self.hole_y - 3, 255, 220, 0)
        # Aim indicator when stationary
        if not self._moving():
            rad = self.angle * math.pi / 180.0
            ax = int(self.ball_x + math.cos(rad) * (self.power + 3))
            ay = int(self.ball_y + math.sin(rad) * (self.power + 3))
            draw_line(int(self.ball_x) + 1, int(self.ball_y) + 1, ax, ay, 255, 255, 0)
            draw_rectangle(1, 1, self.power * 4, 2, 255, 180, 0)
        # Ball
        draw_rectangle(int(self.ball_x), int(self.ball_y), int(self.ball_x) + 1, int(self.ball_y) + 1, 255, 255, 255)
        draw_text_small(1, 52, "H" + str(self.hole) + " P" + str(self.par), 200, 200, 200)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        self.reset()
        display_score_and_time(0, force=True)
        last_z = False

        def step():
            nonlocal last_z
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            if self._moving():
                self._advance_ball()
            else:
                self._aim(joystick)
                if z_button and not last_z:
                    self._shoot()
            last_z = z_button
            if self._in_hole():
                self.score += max(1, 26 - self.strokes * 3 + self.par * 2) + self.hole * 2
                self.hole += 1
                self._new_hole()
            if self.strokes >= self.par + 6:
                set_game_over_score(self.score)
                return False
            self._draw()
            return True

        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))

class LaserGame:
    """
    LASER
    Controls:
      - Directions: move cursor
      - Z: rotate mirror
      - C: return to menu
    Rotate mirrors until the beam reaches the target.
    """
    FRAME_MS = 40
    GRID_W = 8
    GRID_H = 7
    CELL = 7

    def __init__(self):
        self.reset()

    def reset(self):
        self.score = 0
        self.level = 1
        self.cursor_x = 1
        self.cursor_y = 0
        self.last_move = ticks_ms()
        self.last_z = False
        self.beam_phase = 0
        self.beam_pulse_until = 0
        self.level_complete_pending = False
        self.level_complete_score = 0
        self._new_level()

    def _new_level(self):
        # Number of zigzag kinks: each kink adds 2 path mirrors (one pair per turn).
        # Level N guarantees exactly N required rotations by scrambling N path mirrors.
        n_kinks = min(3, (self.level + 1) // 2)
        self.grid = [[0 for _x in range(self.GRID_W)] for _y in range(self.GRID_H)]
        path_cells = set()
        solution_mirrors = []

        # X positions for the kink column; spread evenly across the grid interior
        step = (self.GRID_W - 2) // (n_kinks + 1)
        kink_xs = [min(1 + (i + 1) * step, self.GRID_W - 2) for i in range(n_kinks)]

        cur_y = random.randint(0, self.GRID_H - 1)
        self.start_y = cur_y
        prev_x = 0

        for kx in kink_xs:
            # horizontal run into this kink column
            for px in range(prev_x, kx + 1):
                path_cells.add((px, cur_y))
            # pick a different target row for this kink
            next_y = cur_y
            while next_y == cur_y:
                next_y = random.randint(0, self.GRID_H - 1)
            # mirror 2 (\) deflects rightward beam downward; mirror 1 (/) deflects upward
            going_down = next_y > cur_y
            kind = 2 if going_down else 1
            # first turn mirror — deflects horizontal beam to vertical
            self.grid[cur_y][kx] = kind
            solution_mirrors.append((kx, cur_y, kind))
            # vertical segment between the two turns
            lo, hi = (cur_y, next_y) if cur_y <= next_y else (next_y, cur_y)
            for py in range(lo, hi + 1):
                path_cells.add((kx, py))
            # second turn mirror — same kind deflects vertical beam back to rightward
            # (\) maps (0,+1)->(+1,0)  and  (/) maps (0,-1)->(+1,0)
            self.grid[next_y][kx] = kind
            solution_mirrors.append((kx, next_y, kind))
            prev_x = kx
            cur_y = next_y

        # final horizontal run to right edge
        for px in range(prev_x, self.GRID_W):
            path_cells.add((px, cur_y))
        self.target_y = cur_y

        # boundary cells must stay empty
        self.grid[self.start_y][0] = 0
        self.grid[self.target_y][self.GRID_W - 1] = 0

        # fill off-path cells with noise mirrors
        noise_count = min(14, 4 + self.level)
        placed = 0
        attempts = 0
        while placed < noise_count and attempts < 120:
            attempts += 1
            nx = random.randint(1, self.GRID_W - 2)
            ny = random.randint(0, self.GRID_H - 1)
            if (nx, ny) in path_cells or self.grid[ny][nx] != 0:
                continue
            self.grid[ny][nx] = 1 if random.randint(0, 1) == 0 else 2
            placed += 1

        # Scramble exactly `level` solution mirrors to wrong orientation —
        # this guarantees the player must make exactly level rotations to solve.
        _shuffle_in_place(solution_mirrors)
        n_scramble = min(self.level, len(solution_mirrors))
        for i in range(n_scramble):
            mx, my, correct_kind = solution_mirrors[i]
            self.grid[my][mx] = 3 - correct_kind  # flip: 1<->2

        # Store solution for hint display (how many mirrors still wrong)
        self.solution_mirrors = solution_mirrors   # [(x, y, correct_kind), ...]
        self.moves = 0
        self.cursor_x = 1
        self.cursor_y = self.start_y
        self.level_start = ticks_ms()
        self.time_limit_ms = max(15000, 50000 - self.level * 2500)
        self.beam_phase = 0
        self.level_complete_pending = False
        self.level_complete_score = 0

    def _trace(self):
        x = 0
        y = self.start_y
        dx = 1
        dy = 0
        path = []
        seen = set()
        for _i in range(80):
            if not (0 <= x < self.GRID_W and 0 <= y < self.GRID_H):
                return path, False
            path.append((x, y))
            if x == self.GRID_W - 1 and y == self.target_y:
                return path, True
            state = (x, y, dx, dy)
            if state in seen:
                return path, False
            seen.add(state)
            mirror = self.grid[y][x]
            if mirror == 1:
                dx, dy = -dy, -dx
            elif mirror == 2:
                dx, dy = dy, dx
            x += dx
            y += dy
        return path, False

    def _move_cursor(self, joystick):
        now = ticks_ms()
        if ticks_diff(now, self.last_move) < 140:
            return
        d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
        dx, dy = direction_to_delta(d)
        if dx or dy:
            self.cursor_x = clamp(self.cursor_x + dx, 0, self.GRID_W - 1)
            self.cursor_y = clamp(self.cursor_y + dy, 0, self.GRID_H - 1)
            self.last_move = now

    def _rotate(self):
        v = self.grid[self.cursor_y][self.cursor_x]
        self.grid[self.cursor_y][self.cursor_x] = 2 if v == 1 else 1
        self.moves += 1
        self.beam_phase = 0
        self.beam_pulse_until = ticks_ms() + 120

    def _draw_mirror(self, px, py, kind, lit=False, phase=0):
        if not kind:
            return
        if lit:
            pulse = 35 if ((phase // 4) & 1) else 0
            r, g, b = 80 + pulse, 220 + pulse // 2, 255
            draw_rectangle(px + 2, py + 2, px + 4, py + 4, 18, 60, 85)
        else:
            r, g, b = 0, 110, 145
        if kind == 1:
            draw_line(px + 1, py + 5, px + 5, py + 1, r, g, b)
        elif kind == 2:
            draw_line(px + 1, py + 1, px + 5, py + 5, r, g, b)

    def _draw_beam_cell(self, x, y, r, g, b, size=1):
        px = 4 + x * self.CELL + 3
        py = 4 + y * self.CELL + 3
        draw_rectangle(px - size, py - size, px + size, py + size, r, g, b)

    def _draw_beam(self, path, solved):
        if not path:
            return False
        self.beam_phase = (self.beam_phase + 1) & 255
        if solved and self.level_complete_pending:
            head = min(len(path) - 1, self.beam_phase // 2)
        else:
            head = (self.beam_phase // 2) % max(1, len(path))
        complete = solved and self.level_complete_pending and head >= len(path) - 1
        base = (45, 255, 95) if solved else (255, 70, 0)
        dim = (0, 95, 38) if solved else (100, 18, 0)

        for i in range(len(path) - 1):
            x1, y1 = path[i]
            x2, y2 = path[i + 1]
            cx1 = 4 + x1 * self.CELL + 3
            cy1 = 4 + y1 * self.CELL + 3
            cx2 = 4 + x2 * self.CELL + 3
            cy2 = 4 + y2 * self.CELL + 3
            draw_line(cx1, cy1, cx2, cy2, dim[0], dim[1], dim[2])

        for offset in range(5):
            idx = head - offset
            if idx < 0:
                continue
            x, y = path[idx]
            fade = max(0, 5 - offset)
            r = min(255, base[0] + fade * 14)
            g = min(255, base[1] + fade * 16)
            b = min(255, base[2] + fade * 8)
            self._draw_beam_cell(x, y, r, g, b, 1 if offset else 2)

        x, y = path[head]
        self._draw_beam_cell(x, y, 255, 245, 130 if not solved else 255, 1)
        return complete

    def _draw(self):
        display.clear()
        ox = 4
        oy = 4
        now = ticks_ms()
        elapsed = ticks_diff(now, self.level_start)
        left = max(0, self.time_limit_ms - elapsed)
        bar = int((WIDTH - 2) * left / self.time_limit_ms)
        urgent = left < 5000
        draw_rectangle(1, 1, bar, 2, 255, 40 if urgent else 180, 0)
        path, solved = self._trace()
        path_set = set(path)
        for y in range(self.GRID_H):
            for x in range(self.GRID_W):
                px = ox + x * self.CELL
                py = oy + y * self.CELL
                tone = 28 if (x, y) in path_set else 18
                draw_rect_outline(px, py, px + 5, py + 5, tone, tone + 6, tone + 12)
                self._draw_mirror(px, py, self.grid[y][x], (x, y) in path_set, self.beam_phase)
        beam_complete = self._draw_beam(path, solved)
        sy = oy + self.start_y * self.CELL + 2
        ty = oy + self.target_y * self.CELL + 2
        start_pulse = 30 if ((self.beam_phase // 5) & 1) else 0
        draw_rectangle(0, sy - 1, 3, sy + 2, 255, 60 + start_pulse, 0)
        if solved:
            draw_rectangle(WIDTH - 5, ty - 2, WIDTH - 1, ty + 3, 80, 255, 120)
            draw_rectangle(WIDTH - 3, ty - 1, WIDTH - 1, ty + 2, 220, 255, 220)
        else:
            draw_rectangle(WIDTH - 4, ty - 1, WIDTH - 1, ty + 2, 0, 170 + start_pulse, 80)
        cx = ox + self.cursor_x * self.CELL
        cy = oy + self.cursor_y * self.CELL
        pulse_active = ticks_diff(now, self.beam_pulse_until) < 0
        cr, cg, cb = (255, 220, 80) if pulse_active else (255, 255, 255)
        draw_rect_outline(cx - 1, cy - 1, cx + 6, cy + 6, cr, cg, cb)
        wrong_count = sum(1 for mx, my, ck in self.solution_mirrors
                          if self.grid[my][mx] != ck)
        draw_text_small(1, 52, "L" + str(self.level) + " M" + str(wrong_count), 160, 160, 160)
        display_score_and_time(self.score)
        return beam_complete

    def _start_level_complete(self, now):
        time_bonus = max(0, (self.time_limit_ms - ticks_diff(now, self.level_start)) // 400)
        self.level_complete_score = max(5, 40 - self.moves) + self.level + time_bonus
        self.level_complete_pending = True
        self.beam_phase = 0
        self.beam_pulse_until = now + 220

    def _finish_level_complete(self):
        self.score += self.level_complete_score
        self.level += 1
        self._new_level()

    def _build_step(self, joystick):
        self.reset()
        display_score_and_time(0, force=True)

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            now = ticks_ms()
            if not self.level_complete_pending and ticks_diff(now, self.level_start) > self.time_limit_ms:
                set_game_over_score(self.score)
                return False
            if not self.level_complete_pending:
                self._move_cursor(joystick)
                if z_button and not self.last_z:
                    self._rotate()
                    _path, solved = self._trace()
                    if solved:
                        self._start_level_complete(now)
            self.last_z = z_button
            if self._draw() and self.level_complete_pending:
                self._finish_level_complete()
            return True

        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class PairsGame:
    """
    PAIRS
    Controls:
      - Directions: move cursor
      - Z: flip card
      - C: return to menu
    Match all hidden pairs with as few attempts as possible.
    """
    FRAME_MS = 50
    GRID = 4
    CELL = 13

    def __init__(self):
        self.reset()

    def reset(self):
        self.cursor_x = 0
        self.cursor_y = 0
        self.score = 0
        self.level = 1
        self.last_move = ticks_ms()
        self.last_z = False
        self.open_cards = []
        self.pause_until = 0
        self._new_board()

    def _new_board(self):
        values = []
        for i in range(8):
            values.append(i)
            values.append(i)
        _shuffle_in_place(values)
        self.cards = []
        k = 0
        for _y in range(self.GRID):
            row = []
            for _x in range(self.GRID):
                row.append(values[k])
                k += 1
            self.cards.append(row)
        self.matched = [[False for _x in range(self.GRID)] for _y in range(self.GRID)]
        self.open_cards = []
        self.tries = 0

    def _move_cursor(self, joystick):
        now = ticks_ms()
        if ticks_diff(now, self.last_move) < 135:
            return
        d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
        dx, dy = direction_to_delta(d)
        if dx or dy:
            self.cursor_x = clamp(self.cursor_x + dx, 0, self.GRID - 1)
            self.cursor_y = clamp(self.cursor_y + dy, 0, self.GRID - 1)
            self.last_move = now

    def _flip(self):
        pos = (self.cursor_x, self.cursor_y)
        if self.matched[self.cursor_y][self.cursor_x] or pos in self.open_cards:
            return
        if len(self.open_cards) >= 2:
            return
        self.open_cards.append(pos)
        if len(self.open_cards) == 2:
            self.tries += 1
            a = self.open_cards[0]
            b = self.open_cards[1]
            va = self.cards[a[1]][a[0]]
            vb = self.cards[b[1]][b[0]]
            if va == vb:
                self.matched[a[1]][a[0]] = True
                self.matched[b[1]][b[0]] = True
                self.open_cards = []
                self.score += max(1, 10 - self.tries // 2)
                if self._complete():
                    self.score += 25 + self.level * 5
                    self.level += 1
                    self._new_board()
            else:
                self.pause_until = ticks_ms() + 650

    def _complete(self):
        for row in self.matched:
            for v in row:
                if not v:
                    return False
        return True

    def _card_visible(self, x, y):
        return self.matched[y][x] or (x, y) in self.open_cards

    def _draw(self):
        display.clear()
        now = ticks_ms()
        if self.pause_until and ticks_diff(now, self.pause_until) >= 0:
            self.open_cards = []
            self.pause_until = 0
        ox = 6
        oy = 3
        for y in range(self.GRID):
            for x in range(self.GRID):
                px = ox + x * self.CELL
                py = oy + y * self.CELL
                if self._card_visible(x, y):
                    val = self.cards[y][x]
                    r, g, b = hsb_to_rgb(val * 42, 1, 1)
                    draw_rectangle(px, py, px + 9, py + 9, r, g, b)
                    draw_text_small(px + 2, py + 2, str(val + 1), 0, 0, 0)
                else:
                    draw_rectangle(px, py, px + 9, py + 9, 30, 55, 90)
                if self.matched[y][x]:
                    draw_rect_outline(px, py, px + 9, py + 9, 0, 255, 70)
        cx = ox + self.cursor_x * self.CELL
        cy = oy + self.cursor_y * self.CELL
        draw_rect_outline(cx - 1, cy - 1, cx + 10, cy + 10, 255, 255, 255)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        global game_over, global_score
        game_over = False
        global_score = 0
        self.reset()
        display_score_and_time(0, force=True)

        def step():
            global game_over, global_score
            c_button, z_button = joystick.read_buttons()
            if c_button:
                global_score = self.score
                game_over = True
                return False
            if not self.pause_until:
                self._move_cursor(joystick)
                if z_button and not self.last_z:
                    self._flip()
            self.last_z = z_button
            self._draw()
            return True

        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))
class BomberGame:
    """
    BOMBER
    Controls:
      - Directions: move
      - Z: place bomb
      - C: return to menu
    Clear enemies with timed bombs in a compact block maze.
    """
    FRAME_MS = 55
    GRID_W = 9
    GRID_H = 8
    CELL = 7

    def __init__(self):
        self.reset()

    def reset(self):
        self.level = 1
        self.score = 0
        self.last_move = ticks_ms()
        self.last_z = False
        self._new_level()

    def _new_level(self):
        self.px = 0
        self.py = 0
        self.bombs = []
        self.blasts = []
        self.blocks = [[False for _x in range(self.GRID_W)] for _y in range(self.GRID_H)]
        for y in range(self.GRID_H):
            for x in range(self.GRID_W):
                fixed = (x % 2 == 1 and y % 2 == 1)
                loose = (x > 1 or y > 1) and random.randint(0, 4) == 0
                self.blocks[y][x] = fixed or loose
        self.blocks[0][0] = False
        self.blocks[0][1] = False
        self.blocks[1][0] = False
        self.enemies = []
        count = min(7, 2 + self.level)
        while len(self.enemies) < count:
            x = random.randint(2, self.GRID_W - 1)
            y = random.randint(2, self.GRID_H - 1)
            if not self.blocks[y][x]:
                self.enemies.append([x, y, random.choice((JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT))])

    def _blocked(self, x, y):
        if x < 0 or y < 0 or x >= self.GRID_W or y >= self.GRID_H:
            return True
        if self.blocks[y][x]:
            return True
        for b in self.bombs:
            if b[0] == x and b[1] == y:
                return True
        return False

    def _move_player(self, joystick):
        now = ticks_ms()
        if ticks_diff(now, self.last_move) < 135:
            return
        d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
        dx, dy = direction_to_delta(d)
        if dx or dy:
            nx = self.px + dx
            ny = self.py + dy
            if not self._blocked(nx, ny):
                self.px = nx
                self.py = ny
            self.last_move = now

    def _place_bomb(self):
        for b in self.bombs:
            if b[0] == self.px and b[1] == self.py:
                return
        if len(self.bombs) < 2:
            self.bombs.append([self.px, self.py, ticks_ms() + 1250])

    def _blast_cells(self, bx, by):
        cells = [(bx, by)]
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            for dist in (1, 2):
                x = bx + dx * dist
                y = by + dy * dist
                if x < 0 or y < 0 or x >= self.GRID_W or y >= self.GRID_H:
                    break
                cells.append((x, y))
                if self.blocks[y][x]:
                    break
        return cells

    def _explode(self, bx, by):
        cells = self._blast_cells(bx, by)
        until = ticks_ms() + 360
        for x, y in cells:
            self.blasts.append([x, y, until])
            if self.blocks[y][x] and not (x % 2 == 1 and y % 2 == 1):
                self.blocks[y][x] = False
                self.score += 1
        survivors = []
        for e in self.enemies:
            if (e[0], e[1]) in cells:
                self.score += 10
            else:
                survivors.append(e)
        self.enemies = survivors
        if (self.px, self.py) in cells:
            return False
        return True

    def _advance_bombs(self):
        keep = []
        now = ticks_ms()
        for b in self.bombs:
            if ticks_diff(now, b[2]) >= 0:
                if not self._explode(b[0], b[1]):
                    return False
            else:
                keep.append(b)
        self.bombs = keep
        self.blasts = [b for b in self.blasts if ticks_diff(now, b[2]) < 0]
        return True

    def _move_enemies(self):
        if random.randint(0, 1):
            return
        for e in self.enemies:
            dx, dy = direction_to_delta(e[2])
            nx = e[0] + dx
            ny = e[1] + dy
            if self._blocked(nx, ny) or random.randint(0, 4) == 0:
                e[2] = random.choice((JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT))
            else:
                e[0] = nx
                e[1] = ny

    def _hit_player(self):
        for e in self.enemies:
            if e[0] == self.px and e[1] == self.py:
                return True
        for x, y, _until in self.blasts:
            if x == self.px and y == self.py:
                return True
        return False

    def _draw(self):
        display.clear()
        ox = 1
        oy = 1
        for y in range(self.GRID_H):
            for x in range(self.GRID_W):
                px = ox + x * self.CELL
                py = oy + y * self.CELL
                if self.blocks[y][x]:
                    fixed = (x % 2 == 1 and y % 2 == 1)
                    col = (70, 70, 90) if fixed else (110, 70, 20)
                    draw_rectangle(px, py, px + 5, py + 5, *col)
        for x, y, _until in self.blasts:
            px = ox + x * self.CELL
            py = oy + y * self.CELL
            draw_rectangle(px, py + 2, px + 5, py + 3, 255, 160, 0)
            draw_rectangle(px + 2, py, px + 3, py + 5, 255, 160, 0)
        for x, y, _until in self.bombs:
            px = ox + x * self.CELL
            py = oy + y * self.CELL
            draw_rectangle(px + 1, py + 1, px + 4, py + 4, 20, 20, 20)
            display.set_pixel(px + 4, py, 255, 80, 0)
        for e in self.enemies:
            px = ox + e[0] * self.CELL
            py = oy + e[1] * self.CELL
            draw_rectangle(px + 1, py + 1, px + 4, py + 4, 255, 0, 60)
        draw_rectangle(ox + self.px * self.CELL + 1, oy + self.py * self.CELL + 1,
                       ox + self.px * self.CELL + 4, oy + self.py * self.CELL + 4,
                       0, 220, 255)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        self.reset()
        display_score_and_time(0, force=True)

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            self._move_player(joystick)
            if z_button and not self.last_z:
                self._place_bomb()
            self.last_z = z_button
            if not self._advance_bombs():
                set_game_over_score(self.score)
                return False
            self._move_enemies()
            if self._hit_player():
                set_game_over_score(self.score)
                return False
            if not self.enemies:
                self.score += 20 + self.level * 5
                self.level += 1
                self._new_level()
            self._draw()
            return True

        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))

class SkyWarGame:
    """
    SKYWAR
    Controls:
      - Directions: fly
      - Z: fire cannon
      - C: return to menu
    Helicopter battlefield shooter with air and ground targets.
    """
    FRAME_MS = 35

    def __init__(self):
        self.reset()

    def reset(self):
        self.x = 8
        self.y = PLAY_HEIGHT // 2
        self.score = 0
        self.lives = 3
        self.shots = []
        self.enemies = []
        self.enemy_shots = []
        self.last_shot = 0
        self.last_spawn = ticks_ms()
        self.spawn_ms = 400
        self.scroll = 0
        self.invincible_until = 0
        self.frame = 0

    def _input(self, joystick, z_button):
        d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
        dx, dy = direction_to_delta(d)
        self.x = clamp(self.x + dx * 2, 2, WIDTH // 2)
        self.y = clamp(self.y + dy * 2, 2, PLAY_HEIGHT - 14)
        now = ticks_ms()
        if z_button and ticks_diff(now, self.last_shot) > 140:
            self.shots.append(["gun", self.x + 7, self.y + 2, 4, 0])
            self.last_shot = now

    def _spawn_enemy(self):
        kind = random.randint(0, 2)
        spd = -2 if self.score < 400 else -3
        if kind == 0:
            self.enemies.append(["drone", WIDTH + 2, random.randint(4, PLAY_HEIGHT - 22), spd])
        elif kind == 1:
            self.enemies.append(["tank", WIDTH + 2, PLAY_HEIGHT - 12, spd + 1])
        else:
            self.enemies.append(["turret", WIDTH + 2, PLAY_HEIGHT - 13, spd + 1])

    def _advance(self):
        self.frame += 1
        self.scroll = (self.scroll + 1) % 8
        for shot in self.shots:
            shot[1] += shot[3]
            shot[2] += shot[4]
        self.shots = [s for s in self.shots if 0 <= s[1] < WIDTH and 0 <= s[2] < PLAY_HEIGHT]
        keep = []
        for e in self.enemies:
            e[1] += e[3]
            if e[0] == "drone":
                if self.frame % 2 == 0:
                    e[2] += random.randint(-1, 1)
                    if e[2] < self.y:
                        e[2] += 1
                    elif e[2] > self.y:
                        e[2] -= 1
                e[2] = clamp(e[2], 4, PLAY_HEIGHT - 18)
                if random.randint(0, 22) == 0:
                    self.enemy_shots.append([e[1] - 1, e[2] + 2, -4, 0])
            if e[0] == "turret" and random.randint(0, 18) == 0:
                self.enemy_shots.append([e[1] - 1, e[2] + 2, -3, 0])
            if e[0] == "tank" and random.randint(0, 25) == 0:
                self.enemy_shots.append([e[1] - 1, e[2] - 1, -3, -1])
            if e[1] > -12:
                keep.append(e)
        self.enemies = keep
        for s in self.enemy_shots:
            s[0] += s[2]
            s[1] += s[3]
        self.enemy_shots = [s for s in self.enemy_shots if s[0] >= 0 and 0 <= s[1] < PLAY_HEIGHT]
        survivors = []
        for e in self.enemies:
            hit = False
            ew = 6 if e[0] == "drone" else 8
            eh = 4 if e[0] == "drone" else 5
            for s in self.shots:
                if rects_overlap(int(s[1]), int(s[2]), 2, 4, int(e[1]), int(e[2]), ew, eh):
                    s[1] = WIDTH + 99
                    hit = True
                    pts = 8 if e[0] == "drone" else (10 if e[0] == "tank" else 14)
                    self.score += pts
                    break
            if not hit:
                survivors.append(e)
        self.enemies = survivors
        self.score += 1
        if self.spawn_ms > 180 and self.score % 120 < 2:
            self.spawn_ms = max(180, self.spawn_ms - 20)

    def _collided(self):
        now = ticks_ms()
        if ticks_diff(now, self.invincible_until) < 0:
            return False
        for e in self.enemies:
            ew = 6 if e[0] == "drone" else 8
            if rects_overlap(self.x, self.y, 7, 5, int(e[1]), int(e[2]), ew, 5):
                return True
        for s in self.enemy_shots:
            if rects_overlap(self.x, self.y, 7, 5, int(s[0]), int(s[1]), 3, 2):
                return True
        return False

    def _hurt(self):
        self.lives -= 1
        self.x = 8
        self.y = PLAY_HEIGHT // 2
        self.enemy_shots = []
        self.invincible_until = ticks_ms() + 1500
        if self.lives <= 0:
            set_game_over_score(self.score)
            return False
        return True

    def _draw(self):
        display.clear()
        now = ticks_ms()
        ground = PLAY_HEIGHT - 6
        draw_rectangle(0, ground, WIDTH - 1, PLAY_HEIGHT - 1, 60, 42, 18)
        sx = -self.scroll
        while sx < WIDTH:
            draw_rectangle(sx, ground - 2, sx + 4, ground - 1, 28, 100, 28)
            sx += 8
        for s in self.shots:
            if s[0] == "gun":
                draw_rectangle(int(s[1]), int(s[2]), int(s[1]) + 1, int(s[2]) + 3, 255, 255, 0)
        for s in self.enemy_shots:
            display.set_pixel(int(s[0]), int(s[1]), 255, 60, 0)
        for e in self.enemies:
            ex = int(e[1])
            ey = int(e[2])
            if e[0] == "drone":
                draw_rectangle(ex, ey + 1, ex + 5, ey + 3, 255, 40, 0)
                draw_line(ex - 1, ey, ex + 6, ey, 255, 120, 0)
            elif e[0] == "tank":
                draw_rectangle(ex, ey + 2, ex + 7, ey + 4, 100, 160, 60)
                draw_rectangle(ex + 1, ey, ex + 5, ey + 1, 100, 160, 60)
                draw_rectangle(ex + 5, ey - 1, ex + 8, ey, 100, 160, 60)
            else:
                draw_rectangle(ex, ey + 2, ex + 5, ey + 5, 180, 60, 200)
                draw_line(ex + 2, ey + 2, ex - 2, ey - 1, 200, 80, 220)
        invincible = ticks_diff(now, self.invincible_until) < 0
        if not invincible or (self.frame // 3) % 2 == 0:
            draw_rectangle(self.x, self.y + 1, self.x + 6, self.y + 4, 0, 220, 255)
            draw_line(self.x - 2, self.y, self.x + 8, self.y, 255, 255, 255)
        for i in range(self.lives):
            draw_rectangle(i * 3, 0, i * 3 + 1, 1, 0, 255, 80)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        self.reset()
        display_score_and_time(0, force=True)

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            now = ticks_ms()
            if ticks_diff(now, self.last_spawn) >= self.spawn_ms:
                self._spawn_enemy()
                self.last_spawn = now
            self._input(joystick, z_button)
            self._advance()
            if self._collided() and not self._hurt():
                return False
            self._draw()
            return True

        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class WingsGame:
    """
    WINGS
    Controls:
      - Up / Down: altitude
      - Left / Right: accelerate / decelerate (can reverse)
      - Z: fire (gun when low, bomb when high)
      - C: return to menu
    Carrier-based strike: take off, bomb island targets, return and land.
    """
    FRAME_MS = 38
    # Player is always drawn at this fixed screen x; world scrolls around it.
    SCREEN_PX = 12
    # Carrier occupies world x [0, CARRIER_W)
    CARRIER_W = 32
    DECK_Y = PLAY_HEIGHT - 13   # carrier deck screen y
    SEA_Y = PLAY_HEIGHT - 5     # sea surface screen y
    LANDED = 0
    FLYING = 1

    def __init__(self):
        self.reset()

    def _make_islands(self):
        # 4 islands at increasing world distances, each with more targets
        islands = []
        for i in range(4):
            wx = 260 + i * 380
            iw = 70 + i * 15
            targets = []
            for j in range(2 + i):
                kind = "gun" if j % 2 == 0 else "depot"
                targets.append([kind, wx + 10 + j * 18, False])
            islands.append([wx, iw, targets])  # [world_x, width, targets]
        return islands

    def reset(self):
        self.px = float(self.CARRIER_W // 2)  # player world x, starts on deck
        self.py = float(self.DECK_Y)           # player screen y
        self.vx = 0.0
        self.vy = 0.0
        self.state = self.LANDED
        self.fuel = 1600
        self.ammo = 20
        self.score = 0
        self.shots = []         # [type, world_x, screen_y, vx, vy]
        self.hit_flashes = []   # [world_x, screen_y, ttl_frames]
        self.last_fire = 0
        self.wave_t = 0
        self.frame = 0
        self.landed_flash = 0
        self.islands = self._make_islands()

    def _to_screen_x(self, wx):
        return int(wx - self.px + self.SCREEN_PX)

    def _on_carrier(self):
        return 2.0 <= self.px <= float(self.CARRIER_W - 2)

    def _input(self, joystick, z_button):
        if self.state == self.LANDED:
            if z_button:
                # catapult launch: always fire to the right
                self.state = self.FLYING
                self.vx = 3.0
                self.vy = -1.5
            return
        d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
        if d == JOYSTICK_UP:
            self.vy = max(-3.5, self.vy - 0.22)
        elif d == JOYSTICK_DOWN:
            self.vy = min(2.5, self.vy + 0.15)
        elif d == JOYSTICK_LEFT:
            self.vx = max(-3.0, self.vx - 0.18)
        elif d == JOYSTICK_RIGHT:
            self.vx = min(3.5, self.vx + 0.18)
        now = ticks_ms()
        if z_button and self.ammo > 0 and ticks_diff(now, self.last_fire) > 190:
            self.ammo -= 1
            flying_right = self.vx >= 0
            if self.py < self.SEA_Y - 14:
                # high altitude → drop bomb with gravity
                self.shots.append(["bomb", self.px + 4, float(self.py + 5), self.vx * 0.5, 0.4])
            else:
                # low altitude → strafing gun in direction of flight
                gx = self.px + (9 if flying_right else 0)
                self.shots.append(["gun", gx, float(self.py + 2), 5.0 if flying_right else -5.0, 0.0])
            self.last_fire = now

    def _advance(self):
        self.frame += 1
        self.wave_t = (self.wave_t + 1) % 16

        if self.state == self.LANDED:
            self.fuel = min(1600, self.fuel + 10)   # refuel while on deck
            return

        # gravity
        self.vy = min(4.0, self.vy + 0.05)
        # air friction
        self.vx *= 0.984
        self.vy *= 0.96
        # move player — hard left wall at carrier bow (world x = 0)
        self.px = max(0.0, self.px + self.vx)
        self.py = clamp(self.py + self.vy, 2.0, float(self.SEA_Y))
        self.fuel -= max(1, int(abs(self.vx) * 0.5 + 1))

        # move shots
        for s in self.shots:
            s[1] += s[3]    # world x
            s[2] += s[4]    # screen y
            if s[0] == "bomb":
                s[4] = min(s[4] + 0.14, 5.0)   # bomb gravity
        # remove shots that went off-screen or hit sea
        self.shots = [s for s in self.shots
                      if 0 <= s[2] < self.SEA_Y and abs(s[1] - self.px) < WIDTH + 80]

        # advance hit flashes
        self.hit_flashes = [[f[0], f[1], f[2] - 1] for f in self.hit_flashes if f[2] > 1]

        # shot-target hit detection
        target_sy = self.SEA_Y - 10   # ground level for island targets (screen y)
        for s in self.shots:
            for island in self.islands:
                for t in island[2]:
                    if t[2]:
                        continue
                    if abs(s[1] - t[1]) < 9 and abs(s[2] - target_sy) < 9:
                        t[2] = True
                        s[2] = float(self.SEA_Y)   # mark shot for removal
                        self.score += 20 if t[0] == "depot" else 15
                        self.hit_flashes.append([t[1], target_sy, 8])

        # landing check: player over carrier deck at right altitude and low speed
        if self._on_carrier():
            near_deck = abs(self.py - self.DECK_Y) < 7
            slow_enough = abs(self.vx) < 2.3 and self.vy < 2.5
            if near_deck and slow_enough:
                self.state = self.LANDED
                self.py = float(self.DECK_Y)
                self.vx = 0.0
                self.vy = 0.0
                self.ammo = 20
                self.score += 30
                self.landed_flash = ticks_ms() + 500

        self.score += 1

    def _crashed(self):
        if self.fuel <= 0:
            return True
        if self.state == self.FLYING and self.py >= float(self.SEA_Y):
            return True
        # Flying into an island at low altitude = crash
        if self.state == self.FLYING and self.py > self.SEA_Y - 12:
            for island in self.islands:
                if island[0] <= self.px <= island[0] + island[1]:
                    return True
        return False

    def _draw(self):
        display.clear()
        now = ticks_ms()

        # sea
        draw_rectangle(0, self.SEA_Y, WIDTH - 1, PLAY_HEIGHT - 1, 0, 25, 80)
        wo = self.wave_t
        for wxi in range(0, WIDTH, 8):
            draw_line((wxi + wo) % WIDTH, self.SEA_Y,
                      (wxi + wo + 3) % WIDTH, self.SEA_Y - 1, 0, 60, 145)

        # carrier
        c_sx = self._to_screen_x(0)
        if c_sx + self.CARRIER_W >= 0 and c_sx < WIDTH:
            on_approach = (self.state == self.FLYING and self._on_carrier()
                           and abs(self.py - self.DECK_Y) < 8 and abs(self.vx) < 2.3)
            deck_r = 0 if on_approach else 80
            deck_g = 220 if on_approach else 85
            draw_rectangle(c_sx, self.DECK_Y, c_sx + self.CARRIER_W, self.DECK_Y + 4, deck_r, deck_g, 95)
            draw_rectangle(c_sx + 6, self.DECK_Y - 4, c_sx + 16, self.DECK_Y, 70, 70, 80)   # bridge
            # landing stripe
            draw_line(c_sx + 2, self.DECK_Y, c_sx + self.CARRIER_W - 2, self.DECK_Y, 255, 240, 80)
            # hull below waterline
            draw_rectangle(c_sx, self.DECK_Y + 4, c_sx + self.CARRIER_W, self.SEA_Y - 1, 55, 55, 65)

        if ticks_diff(now, self.landed_flash) < 0:
            draw_rect_outline(0, 0, WIDTH - 1, PLAY_HEIGHT - 1, 0, 255, 100)

        # islands
        for island in self.islands:
            iw_x = island[0]
            iw = island[1]
            i_sx = self._to_screen_x(iw_x)
            if i_sx + iw < -5 or i_sx > WIDTH + 5:
                continue
            # beach / sand edge
            draw_rectangle(i_sx, self.SEA_Y - 4, i_sx + iw, self.SEA_Y - 1, 200, 175, 100)
            # green interior
            draw_rectangle(i_sx + 3, self.SEA_Y - 9, i_sx + iw - 3, self.SEA_Y - 4, 45, 100, 30)
            # small hill
            draw_rectangle(i_sx + iw // 3, self.SEA_Y - 12, i_sx + 2 * iw // 3, self.SEA_Y - 9, 30, 75, 20)
            # targets on the island
            for t in island[2]:
                t_sx = self._to_screen_x(t[1])
                t_sy = self.SEA_Y - 10
                if t[2]:    # destroyed — show rubble
                    draw_rectangle(t_sx, t_sy + 1, t_sx + 5, t_sy + 4, 90, 55, 15)
                elif t[0] == "depot":
                    draw_rectangle(t_sx, t_sy, t_sx + 7, t_sy + 5, 140, 90, 25)
                    draw_rectangle(t_sx + 2, t_sy - 3, t_sx + 5, t_sy, 160, 100, 30)
                else:   # gun emplacement
                    draw_rectangle(t_sx, t_sy + 3, t_sx + 4, t_sy + 5, 180, 40, 40)
                    draw_line(t_sx + 1, t_sy + 3, t_sx - 1, t_sy, 200, 60, 60)

        # hit flashes (explosion markers)
        for f in self.hit_flashes:
            fx = self._to_screen_x(f[0])
            fy = int(f[1])
            if 0 <= fx < WIDTH:
                draw_rectangle(fx - 2, fy - 2, fx + 4, fy + 2, 255, 180, 0)

        # shots
        for s in self.shots:
            s_sx = self._to_screen_x(s[1])
            s_sy = int(s[2])
            if 0 <= s_sx < WIDTH and 0 <= s_sy < PLAY_HEIGHT:
                if s[0] == "gun":
                    draw_rectangle(s_sx, s_sy, s_sx + 2, s_sy + 1, 255, 220, 0)
                else:
                    draw_rectangle(s_sx, s_sy, s_sx + 1, s_sy + 1, 255, 100, 0)

        # player aircraft
        psx = self.SCREEN_PX
        psy = int(self.py)
        going_right = self.vx >= 0
        if self.state == self.FLYING:
            draw_rectangle(psx, psy + 1, psx + 6, psy + 3, 0, 200, 255)
            if going_right:
                draw_line(psx + 1, psy, psx + 5, psy - 1, 180, 220, 255)   # top wing
                draw_line(psx - 1, psy + 2, psx - 3, psy, 120, 170, 210)   # tail
            else:
                draw_line(psx + 1, psy, psx + 5, psy - 1, 180, 220, 255)   # top wing
                draw_line(psx + 7, psy + 2, psx + 9, psy, 120, 170, 210)   # tail
        else:   # landed on deck
            draw_rectangle(psx, psy, psx + 6, psy + 2, 0, 180, 230)

        # HUD
        fuel_w = max(0, min(22, self.fuel // 73))
        low_fuel = fuel_w <= 5
        draw_rectangle(1, 1, fuel_w, 2, 255 if low_fuel else 0, 50 if low_fuel else 200, 0)
        draw_text_small(44, 0, str(self.ammo), 255, 255, 0)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        self.reset()
        display_score_and_time(0, force=True)

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            self._input(joystick, z_button)
            self._advance()
            if self._crashed():
                set_game_over_score(self.score)
                return False
            self._draw()
            return True

        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class CgolgGame:
    """
    CGOLG
    Controls:
      - Left / Right: select Conway creature
      - Up / Down: move spawn lane in the blue quarter
      - Z: spawn selected creature
      - C: return to menu
    Conway's Game of Life Game. Blue and red cells mix color through neighbor
    ancestry while both sides seed directed movers into opposite quarters.
    """
    FRAME_MS = 34
    GEN_MS = 135
    LEFT_W = WIDTH // 4
    RIGHT_X = WIDTH - LEFT_W
    BASE_HP = 72
    PLAYER_MAX_ENERGY = 16
    ENEMY_MAX_ENERGY = 18
    PLAYER_REGEN_MS = 850
    ENEMY_REGEN_MS = 560
    PLAYER_COLOR = (0, 70, 255)
    ENEMY_COLOR = (255, 35, 0)
    PATTERNS = (
        ("GDR", 3, ((0, 1), (1, 2), (2, 0), (2, 1), (2, 2))),
        ("GUR", 3, ((0, 1), (1, 0), (2, 0), (2, 1), (2, 2))),
        ("LWSS", 6, ((0, 0), (0, 2), (1, 3), (2, 3), (3, 0), (3, 3), (4, 1), (4, 2), (4, 3))),
        ("LWS2", 7, ((0, 1), (0, 2), (1, 1), (1, 2), (1, 3), (2, 0), (2, 2), (2, 3), (3, 0), (3, 1), (3, 2), (4, 1))),
        ("LWS3", 7, ((0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (2, 0), (2, 1), (2, 3), (3, 1), (3, 2), (3, 3), (4, 2))),
    )

    def __init__(self):
        self.size = WIDTH * PLAY_HEIGHT
        self.alive = bytearray(self.size)
        self.red = bytearray(self.size)
        self.blue = bytearray(self.size)
        self.next_alive = bytearray(self.size)
        self.next_red = bytearray(self.size)
        self.next_blue = bytearray(self.size)
        self.reset()

    def reset(self):
        for buf in (self.alive, self.red, self.blue, self.next_alive, self.next_red, self.next_blue):
            for i in range(len(buf)):
                buf[i] = 0
        self.score = 0
        self.frame = 0
        self.last_gen = ticks_ms()
        self.last_move = ticks_ms()
        self.last_z = False
        self.cursor_y = PLAY_HEIGHT // 2
        self.pattern_idx = 0
        self.player_energy = 9
        self.enemy_energy = 9
        self.player_hp = self.BASE_HP
        self.enemy_hp = self.BASE_HP
        self.last_player_regen = ticks_ms()
        self.last_enemy_regen = ticks_ms()
        self.last_enemy_spawn = ticks_ms() + 400
        self.enemy_spawn_ms = 620
        self.flash_until = 0
        self.blue_hit_until = 0
        self.red_hit_until = 0
        self._seed_opening()

    def _idx(self, x, y):
        return y * WIDTH + x

    def _set_cell(self, x, y, r, b):
        if 0 <= x < WIDTH and 0 <= y < PLAY_HEIGHT:
            i = self._idx(x, y)
            self.alive[i] = 1
            self.red[i] = r
            self.blue[i] = b

    def _pattern(self):
        return self.PATTERNS[self.pattern_idx]

    def _pattern_points(self, base_x, base_y, cells, is_player):
        for px, py in cells:
            x = base_x + px if is_player else base_x - px
            yield x, base_y + py

    def _seed_opening(self):
        self._spawn_pattern(4, 13, 0, True, free=True)
        self._spawn_pattern(4, 38, 2, True, free=True)
        self._spawn_pattern(WIDTH - 6, 18, 0, False, free=True)
        self._spawn_pattern(WIDTH - 6, 43, 2, False, free=True)

    def _spawn_pattern(self, base_x, base_y, pattern_idx, is_player, free=False):
        name, cost, cells = self.PATTERNS[pattern_idx]
        if is_player:
            if not free and self.player_energy < cost:
                return False
            r, b = self.PLAYER_COLOR[0], self.PLAYER_COLOR[2]
            max_x = self.LEFT_W - 2
        else:
            if not free and self.enemy_energy < cost:
                return False
            r, b = self.ENEMY_COLOR[0], self.ENEMY_COLOR[2]
            max_x = WIDTH - 1

        placed = False
        for x, y in self._pattern_points(base_x, base_y, cells, is_player):
            if is_player and x >= self.LEFT_W:
                continue
            if (not is_player) and x < self.RIGHT_X:
                continue
            if 0 <= x <= max_x and 0 <= y < PLAY_HEIGHT:
                self._set_cell(x, y, r, b)
                placed = True

        if placed and not free:
            if is_player:
                self.player_energy -= cost
                self.score += cost
            else:
                self.enemy_energy -= cost
        return placed

    def _handle_input(self, joystick, z_button):
        now = ticks_ms()
        if ticks_diff(now, self.last_move) >= 125:
            d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_UP, JOYSTICK_DOWN])
            if d == JOYSTICK_LEFT:
                self.pattern_idx = (self.pattern_idx - 1) % len(self.PATTERNS)
                self.last_move = now
            elif d == JOYSTICK_RIGHT:
                self.pattern_idx = (self.pattern_idx + 1) % len(self.PATTERNS)
                self.last_move = now
            elif d == JOYSTICK_UP:
                self.cursor_y = max(1, self.cursor_y - 3)
                self.last_move = now
            elif d == JOYSTICK_DOWN:
                self.cursor_y = min(PLAY_HEIGHT - 6, self.cursor_y + 3)
                self.last_move = now

        if z_button and not self.last_z:
            if self._spawn_pattern(4, self.cursor_y, self.pattern_idx, True):
                self.flash_until = now + 90
        self.last_z = z_button

    def _regen(self):
        now = ticks_ms()
        if ticks_diff(now, self.last_player_regen) >= self.PLAYER_REGEN_MS:
            self.player_energy = min(self.PLAYER_MAX_ENERGY, self.player_energy + 1)
            self.last_player_regen = now
        if ticks_diff(now, self.last_enemy_regen) >= self.ENEMY_REGEN_MS:
            self.enemy_energy = min(self.ENEMY_MAX_ENERGY, self.enemy_energy + 1)
            self.last_enemy_regen = now

    def _enemy_choose_y(self):
        best_y = random.randint(3, PLAY_HEIGHT - 8)
        best_count = -1
        for band in range(0, PLAY_HEIGHT, 8):
            count = 0
            y2 = min(PLAY_HEIGHT, band + 8)
            for y in range(band, y2):
                row = y * WIDTH
                for x in range(WIDTH // 2 - 4, self.RIGHT_X):
                    i = row + x
                    if self.alive[i] and self.blue[i] > self.red[i]:
                        count += 1
            if count > best_count:
                best_count = count
                best_y = min(PLAY_HEIGHT - 6, band + 2)
        return best_y

    def _choose_enemy_pattern(self, choices):
        pressure = self.BASE_HP - self.enemy_hp + self.score // 60
        if pressure > 18 and 4 in choices and random.randint(0, 1) == 0:
            return 4
        if pressure > 8 and 3 in choices and random.randint(0, 2) != 0:
            return 3
        if 2 in choices and random.randint(0, 1) == 0:
            return 2
        return choices[random.randint(0, len(choices) - 1)]

    def _enemy_bonus_spawn(self, y):
        if self.enemy_energy < 3 or random.randint(0, 3) != 0:
            return
        lane = clamp(y + random.choice((-7, 7)), 2, PLAY_HEIGHT - 8)
        self._spawn_pattern(WIDTH - 6, lane, random.randint(0, 1), False)

    def _enemy_spawn(self):
        now = ticks_ms()
        if ticks_diff(now, self.last_enemy_spawn) < self.enemy_spawn_ms:
            return
        choices = []
        for i, (_name, cost, _cells) in enumerate(self.PATTERNS):
            if cost <= self.enemy_energy:
                choices.append(i)
        if not choices:
            return
        idx = self._choose_enemy_pattern(choices)
        y = self._enemy_choose_y()
        if random.randint(0, 3) == 0:
            y = random.randint(2, PLAY_HEIGHT - 8)
        if self._spawn_pattern(WIDTH - 6, y, idx, False):
            self.last_enemy_spawn = now
            self.enemy_spawn_ms = max(430, self.enemy_spawn_ms - 5)
            self._enemy_bonus_spawn(y)

    def _generation(self):
        alive = self.alive
        red = self.red
        blue = self.blue
        na = self.next_alive
        nr = self.next_red
        nb = self.next_blue
        for i in range(self.size):
            na[i] = 0
            nr[i] = 0
            nb[i] = 0

        for y in range(PLAY_HEIGHT):
            ym = y - 1
            yp = y + 1
            row = y * WIDTH
            for x in range(WIDTH):
                count = 0
                sr = 0
                sb = 0
                for yy in (ym, y, yp):
                    if yy < 0 or yy >= PLAY_HEIGHT:
                        continue
                    base = yy * WIDTH
                    for xx in (x - 1, x, x + 1):
                        if xx < 0 or xx >= WIDTH or (xx == x and yy == y):
                            continue
                        ni = base + xx
                        if alive[ni]:
                            count += 1
                            sr += red[ni]
                            sb += blue[ni]
                i = row + x
                if alive[i]:
                    if count == 2 or count == 3:
                        na[i] = 1
                        if count:
                            nr[i] = min(255, (red[i] * 3 + sr // count) // 4)
                            nb[i] = min(255, (blue[i] * 3 + sb // count) // 4)
                        else:
                            nr[i] = red[i]
                            nb[i] = blue[i]
                elif count == 3:
                    na[i] = 1
                    nr[i] = min(255, sr // 3)
                    nb[i] = min(255, sb // 3)

        self.alive, self.next_alive = self.next_alive, self.alive
        self.red, self.next_red = self.next_red, self.red
        self.blue, self.next_blue = self.next_blue, self.blue
        self._score_and_damage()

    def _score_and_damage(self):
        blue_right = 0
        red_left = 0
        blue_total = 0
        red_total = 0
        for y in range(PLAY_HEIGHT):
            row = y * WIDTH
            for x in range(WIDTH):
                i = row + x
                if not self.alive[i]:
                    continue
                if self.blue[i] >= self.red[i]:
                    blue_total += 1
                    if x >= self.RIGHT_X:
                        blue_right += 1
                else:
                    red_total += 1
                    if x < self.LEFT_W:
                        red_left += 1
        if blue_right:
            dmg = min(3, 1 + blue_right // 14)
            self.enemy_hp = max(0, self.enemy_hp - dmg)
            self.score += dmg * 10 + blue_right // 2
            self.blue_hit_until = ticks_ms() + 140
        if red_left:
            dmg = min(3, 1 + red_left // 14)
            self.player_hp = max(0, self.player_hp - dmg)
            self.red_hit_until = ticks_ms() + 140
        self.score += max(0, blue_total - red_total) // 12
        if self.enemy_hp <= 0:
            set_game_over_score(self.score + 200, won=True)
        elif self.player_hp <= 0:
            set_game_over_score(self.score, won=False)

    def _draw_hud_top(self):
        draw_rectangle(0, 0, WIDTH - 1, 4, 0, 0, 0)
        pbar = (self.player_hp * (self.LEFT_W - 2)) // self.BASE_HP
        ebar = (self.enemy_hp * (self.LEFT_W - 2)) // self.BASE_HP
        if pbar > 0:
            draw_rectangle(1, 1, pbar, 2, 0, 80, 255)
        if ebar > 0:
            draw_rectangle(WIDTH - 1 - ebar, 1, WIDTH - 2, 2, 255, 40, 0)
        name, cost, _cells = self._pattern()
        txt = name + str(cost)
        draw_text_small((WIDTH - len(txt) * 6) // 2, 0, txt, 190, 190, 190)
        if self.player_energy > 0:
            draw_rectangle(1, 4, min(self.LEFT_W - 2, self.player_energy), 4, 0, 180, 255)
        if self.enemy_energy > 0:
            draw_rectangle(max(self.RIGHT_X + 1, WIDTH - 1 - self.enemy_energy), 4, WIDTH - 2, 4, 255, 60, 0)

    def _draw_bases(self):
        now = ticks_ms()
        left_col = (70, 190, 255) if ticks_diff(now, self.red_hit_until) >= 0 else (255, 255, 255)
        right_col = (255, 90, 45) if ticks_diff(now, self.blue_hit_until) >= 0 else (255, 255, 255)
        draw_rect_outline(0, 8, self.LEFT_W - 1, PLAY_HEIGHT - 2, 0, 42, 110)
        draw_rect_outline(self.RIGHT_X, 8, WIDTH - 1, PLAY_HEIGHT - 2, 110, 25, 0)
        draw_rectangle(2, PLAY_HEIGHT // 2 - 3, 5, PLAY_HEIGHT // 2 + 3, left_col[0], left_col[1], left_col[2])
        draw_rectangle(3, PLAY_HEIGHT // 2 - 1, 6, PLAY_HEIGHT // 2 + 1, 0, 45, 110)
        cx = WIDTH - 4
        cy = PLAY_HEIGHT // 2
        draw_rect_outline(cx - 3, cy - 3, cx + 2, cy + 3, right_col[0], right_col[1], right_col[2])
        draw_line(cx - 4, cy, cx + 3, cy, right_col[0], right_col[1], right_col[2])
        draw_line(cx, cy - 4, cx, cy + 4, right_col[0], right_col[1], right_col[2])

    def _draw_goal_hint(self):
        if self.frame > 170:
            return
        y = 10 + ((self.frame // 18) % 3) * 8
        x1 = self.LEFT_W + 3
        x2 = self.RIGHT_X - 4
        draw_line(x1, y, x2, y, 0, 110, 255)
        draw_line(x2 - 3, y - 2, x2, y, 0, 170, 255)
        draw_line(x2 - 3, y + 2, x2, y, 0, 170, 255)

    def _draw_pattern_preview(self, base_x, base_y, pattern_idx, is_player):
        _name, _cost, cells = self.PATTERNS[pattern_idx]
        if is_player:
            color = (80, 210, 255)
        else:
            color = (255, 90, 55)
        for x, y in self._pattern_points(base_x, base_y, cells, is_player):
            if 0 <= x < WIDTH and 0 <= y < PLAY_HEIGHT:
                draw_rectangle(x, y, x, y, color[0], color[1], color[2])

    def _draw_direction_arrow(self, y, is_player):
        y = clamp(y, 2, PLAY_HEIGHT - 3)
        if is_player:
            draw_line(2, y, self.LEFT_W - 3, y, 0, 95, 180)
            draw_line(self.LEFT_W - 5, y - 2, self.LEFT_W - 2, y, 0, 150, 255)
            draw_line(self.LEFT_W - 5, y + 2, self.LEFT_W - 2, y, 0, 150, 255)
        else:
            draw_line(WIDTH - 3, y, self.RIGHT_X + 2, y, 180, 45, 0)
            draw_line(self.RIGHT_X + 4, y - 2, self.RIGHT_X + 1, y, 255, 80, 25)
            draw_line(self.RIGHT_X + 4, y + 2, self.RIGHT_X + 1, y, 255, 80, 25)

    def _draw(self):
        display.clear()
        draw_line(self.LEFT_W, 0, self.LEFT_W, PLAY_HEIGHT - 1, 0, 30, 80)
        draw_line(self.RIGHT_X - 1, 0, self.RIGHT_X - 1, PLAY_HEIGHT - 1, 80, 20, 0)
        self._draw_goal_hint()
        sp = display.set_pixel
        for y in range(PLAY_HEIGHT):
            row = y * WIDTH
            for x in range(WIDTH):
                i = row + x
                if not self.alive[i]:
                    continue
                r = self.red[i]
                b = self.blue[i]
                g = min(70, min(r, b) // 3)
                if r > b:
                    r = max(r, 90)
                else:
                    b = max(b, 100)
                sp(x, y, r, g, b)
        self._draw_bases()

        cy = self.cursor_y
        col = (255, 255, 255) if ticks_diff(ticks_ms(), self.flash_until) < 0 else (0, 180, 255)
        enemy_preview_y = clamp(PLAY_HEIGHT - cy - 5, 1, PLAY_HEIGHT - 7)
        self._draw_direction_arrow(cy + 2, True)
        self._draw_direction_arrow(enemy_preview_y + 2, False)
        self._draw_pattern_preview(4, cy, self.pattern_idx, True)
        self._draw_pattern_preview(WIDTH - 6, enemy_preview_y, self.pattern_idx, False)
        draw_rect_outline(1, cy - 1, self.LEFT_W - 2, min(PLAY_HEIGHT - 1, cy + 5), col[0], col[1], col[2])
        self._draw_hud_top()
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button or game_over:
                return False
            self.frame += 1
            self._handle_input(joystick, z_button)
            self._regen()
            self._enemy_spawn()
            now = ticks_ms()
            if ticks_diff(now, self.last_gen) >= self.GEN_MS:
                self.last_gen = now
                self._generation()
            self._draw()
            if (self.frame % 80) == 0:
                gc.collect()
            return True
        return step

    def main_loop(self, joystick):
        begin_game(0)
        self.reset()
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        begin_game(0)
        self.reset()
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class PinballGame:
    """
    PINBAL
    Controls:
      - Hold Z at launch: charge plunger
      - Left / Right: flippers
      - C: return to menu
    Compact Video Pinball-inspired table with rollover lanes, spinner, drop
    targets, bumpers, flippers, plunger strength, bonus, and multipliers.
    """
    FRAME_MS = 30
    BALL_R = 1.45
    LANE_X = 55.0
    LANE_GATE_Y = 10.0
    LANE_BOTTOM_Y = 52.0
    POSTS = ((7, 47), (52, 47), (31, 51), (33, 51))

    def __init__(self):
        self.reset()

    def reset(self):
        self.score = 0
        self.balls = 3
        self.mult = 1
        self.bonus = 0
        self.charge = 0
        self.last_z = False
        self.frame = 0
        self.hit_cooldown = 0
        self.stuck = 0
        self.spinner_phase = 0
        self.bumpers = ((18, 17, 5), (43, 17, 5), (31, 31, 5))
        self.lanes = [[15, 7, 0], [28, 7, 0], [41, 7, 0]]
        self.targets = [[8, 20, 0], [8, 27, 0], [8, 34, 0], [51, 23, 0], [51, 31, 0]]
        self._new_ball()

    def _new_ball(self):
        self.ball_x = 58.0
        self.ball_y = 50.0
        self.vx = 0.0
        self.vy = 0.0
        self.in_plunger = True
        self.charge = 0

    def _launch(self):
        strength = 2.2 + self.charge * 0.10
        self.vx = -0.45
        self.vy = -strength
        self.in_plunger = False
        self.charge = 0

    def _flipper_input(self, joystick):
        d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT])
        return d == JOYSTICK_LEFT, d == JOYSTICK_RIGHT

    def _reflect_on_normal(self, nx, ny, boost=1.0):
        dot = self.vx * nx + self.vy * ny
        if dot < 0:
            self.vx = (self.vx - 2 * dot * nx) * boost
            self.vy = (self.vy - 2 * dot * ny) * boost

    def _bounce_circle(self, cx, cy, radius, score):
        dx = self.ball_x - cx
        dy = self.ball_y - cy
        min_d = radius + self.BALL_R
        d2 = dx * dx + dy * dy
        if d2 > min_d * min_d:
            return False
        dist = math.sqrt(d2) or 1.0
        nx = dx / dist
        ny = dy / dist
        self.ball_x = cx + nx * min_d
        self.ball_y = cy + ny * min_d
        self._reflect_on_normal(nx, ny, 1.08)
        if score > 0 and self.hit_cooldown <= 0:
            self.score += score * self.mult
            self.hit_cooldown = 5
        return True

    def _bounce_segment(self, x1, y1, x2, y2, active=False, side=0):
        vx = x2 - x1
        vy = y2 - y1
        seg_len2 = vx * vx + vy * vy
        if seg_len2 <= 0:
            return False
        t = ((self.ball_x - x1) * vx + (self.ball_y - y1) * vy) / seg_len2
        t = clamp(t, 0.0, 1.0)
        cx = x1 + vx * t
        cy = y1 + vy * t
        dx = self.ball_x - cx
        dy = self.ball_y - cy
        min_d = self.BALL_R + 0.55
        d2 = dx * dx + dy * dy
        if d2 > min_d * min_d:
            return False
        dist = math.sqrt(d2) or 1.0
        nx = dx / dist
        ny = dy / dist
        self.ball_x = cx + nx * min_d
        self.ball_y = cy + ny * min_d
        self._reflect_on_normal(nx, ny, 0.92)
        if active and self.ball_y >= 43:
            self.vx += side * 0.85
            self.vy = min(self.vy, -3.8)
            self.score += 1
        return True

    def _apply_flippers(self, left_on, right_on):
        left_tip_y = 46 if left_on else 55
        right_tip_y = 46 if right_on else 55
        self._bounce_segment(11, 52, 29, left_tip_y, left_on, 1)
        self._bounce_segment(53, 52, 35, right_tip_y, right_on, -1)

    def _hit_bumpers(self):
        for bx, by, radius in self.bumpers:
            self._bounce_circle(bx, by, radius, 15)

    def _hit_targets(self):
        for t in self.targets:
            tx, ty, lit = t
            if abs(self.ball_x - tx) <= 2 + self.BALL_R and abs(self.ball_y - ty) <= 4 + self.BALL_R:
                if not lit:
                    t[2] = 1
                    self.bonus = min(99, self.bonus + 2)
                    self.score += 25 * self.mult
                    if all(tt[2] for tt in self.targets):
                        self.mult = min(5, self.mult + 1)
                        self.bonus = min(99, self.bonus + 10)
                        for tt in self.targets:
                            tt[2] = 0
                if abs(self.ball_x - tx) > abs(self.ball_y - ty) * 0.45:
                    self.vx = -self.vx * 0.9
                    self.ball_x = tx + (3.6 if self.ball_x >= tx else -3.6)
                else:
                    self.vy = -self.vy * 0.85
                    self.ball_y = ty + (5.4 if self.ball_y >= ty else -5.4)

    def _hit_lanes(self):
        if not (4 <= self.ball_y <= 11):
            return
        for lane in self.lanes:
            lx, _ly, lit = lane
            if abs(self.ball_x - lx) <= 3:
                if not lit:
                    lane[2] = 1
                    self.bonus = min(99, self.bonus + 3)
                    self.score += 15 * self.mult
                    if all(ll[2] for ll in self.lanes):
                        self.mult = min(5, self.mult + 1)
                        for ll in self.lanes:
                            ll[2] = 0
                self.vy = abs(self.vy) * 0.7
                return

    def _hit_spinner(self):
        if 27 <= self.ball_x <= 36 and 21 <= self.ball_y <= 28:
            if self.hit_cooldown <= 0:
                self.score += 5 * self.mult
                self.bonus = min(99, self.bonus + 1)
                self.hit_cooldown = 3
            self.spinner_phase = (self.spinner_phase + 1) & 3
            self.vx += 0.18 if self.ball_x < 32 else -0.18
            self.vy *= 0.96

    def _collect_bonus(self):
        if self.bonus:
            self.score += self.bonus * self.mult
            self.bonus = 0

    def _hit_posts(self):
        for x, y in self.POSTS:
            self._bounce_circle(x, y, 1.6, 0)

    def _wall_collisions(self):
        if self.ball_x <= 3 + self.BALL_R:
            self.ball_x = 3 + self.BALL_R
            self.vx = abs(self.vx) * 0.84
        elif self.ball_x >= WIDTH - 4 - self.BALL_R:
            self.ball_x = WIDTH - 4 - self.BALL_R
            self.vx = -abs(self.vx) * 0.84

        if self.ball_y <= 2 + self.BALL_R:
            self.ball_y = 2 + self.BALL_R
            self.vy = abs(self.vy) * 0.78
            if self.ball_x > self.LANE_X:
                self.vx = min(self.vx - 0.75, -0.85)

        if self.LANE_GATE_Y < self.ball_y < self.LANE_BOTTOM_Y:
            if self.ball_x > self.LANE_X and self.ball_x < self.LANE_X + self.BALL_R:
                self.ball_x = self.LANE_X + self.BALL_R
                self.vx = abs(self.vx) * 0.65
            elif self.ball_x <= self.LANE_X and self.ball_x > self.LANE_X - self.BALL_R:
                self.ball_x = self.LANE_X - self.BALL_R
                self.vx = -abs(self.vx) * 0.65
        elif self.ball_y <= self.LANE_GATE_Y and self.ball_x > self.LANE_X:
            self.vx = min(self.vx, -0.8)

        if self.ball_y >= PLAY_HEIGHT - 3 - self.BALL_R:
            if self.ball_x < 26:
                self.ball_y = PLAY_HEIGHT - 3 - self.BALL_R
                self.vx = max(self.vx, 0.8)
                self.vy = -abs(self.vy) * 0.7
            elif self.ball_x > 38:
                self.ball_y = PLAY_HEIGHT - 3 - self.BALL_R
                self.vx = min(self.vx, -0.8)
                self.vy = -abs(self.vy) * 0.7

    def _advance_ball(self, left_on, right_on):
        if self.in_plunger:
            return True
        if self.hit_cooldown > 0:
            self.hit_cooldown -= 1
        steps = max(1, int(max(abs(self.vx), abs(self.vy))) + 1)
        gravity = 0.10 / steps
        for _ in range(steps):
            self.vy += gravity
            self.ball_x += self.vx / steps
            self.ball_y += self.vy / steps
            self._wall_collisions()
            self._hit_bumpers()
            self._hit_posts()
            self._hit_targets()
            self._hit_lanes()
            self._hit_spinner()
            self._apply_flippers(left_on, right_on)

        self.vx *= 0.992
        self.vy *= 0.995
        # Anti-softlock: a real table can never trap the ball, but discrete
        # physics occasionally parks it between elements with almost no speed.
        # If that happens away from a held flipper (so deliberate cradling is
        # left alone), give it a small upward kick after ~1s.
        if (not left_on and not right_on
                and self.ball_y < PLAY_HEIGHT - 8
                and self.vx * self.vx + self.vy * self.vy < 0.05):
            self.stuck += 1
            if self.stuck > 33:
                self.vy -= 1.7
                self.vx += random.choice((-0.7, 0.7))
                self.stuck = 0
        else:
            self.stuck = 0
        if self.ball_y > PLAY_HEIGHT + 4:
            self._collect_bonus()
            self.balls -= 1
            if self.balls <= 0:
                set_game_over_score(self.score)
                return False
            self._new_ball()
        return True

    def _draw(self, left_on=False, right_on=False):
        display.clear()
        draw_rect_outline(2, 1, WIDTH - 3, PLAY_HEIGHT - 1, 40, 80, 120)
        draw_line(55, 8, 55, PLAY_HEIGHT - 3, 70, 70, 90)
        draw_line(55, 8, 60, 3, 70, 70, 90)
        for lx, ly, lit in self.lanes:
            col = (255, 230, 80) if lit else (50, 100, 150)
            draw_rect_outline(lx - 4, ly - 3, lx + 4, ly + 3, *col)
        draw_rectangle(56, 49 - self.charge // 3, 60, 55, 255, 120, 20)
        for bx, by, radius in self.bumpers:
            draw_rect_outline(bx - radius, by - radius, bx + radius, by + radius, 0, 120, 255)
            draw_rectangle(bx - 1, by - 1, bx + 1, by + 1, 255, 80, 180)
        if self.spinner_phase & 1:
            draw_line(29, 24, 35, 24, 255, 255, 255)
        else:
            draw_line(32, 21, 32, 28, 255, 255, 255)
        for x, y in self.POSTS:
            draw_rectangle(x - 1, y - 1, x + 1, y + 1, 200, 210, 230)
        for tx, ty, lit in self.targets:
            col = (255, 240, 80) if lit else (150, 80, 30)
            if lit:
                draw_rectangle(tx - 1, ty + 2, tx + 1, ty + 3, *col)
            else:
                draw_rectangle(tx - 1, ty - 3, tx + 1, ty + 3, *col)
        if left_on:
            draw_line(11, 52, 28, 46, 255, 255, 255)
        else:
            draw_line(11, 52, 28, 55, 180, 180, 180)
        if right_on:
            draw_line(53, 52, 36, 46, 255, 255, 255)
        else:
            draw_line(53, 52, 36, 55, 180, 180, 180)
        draw_rectangle(int(self.ball_x) - 1, int(self.ball_y) - 1, int(self.ball_x) + 1, int(self.ball_y) + 1, 255, 255, 255)
        draw_text_small(1, PLAY_HEIGHT, "L" + str(self.balls), 255, 255, 255)
        draw_text_small(13, PLAY_HEIGHT, "B" + str(self.bonus), 255, 220, 60)
        draw_text_small(31, PLAY_HEIGHT, "X" + str(self.mult), 255, 220, 60)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        self.reset()

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            left_on, right_on = self._flipper_input(joystick)
            if self.in_plunger:
                if z_button:
                    self.charge = min(28, self.charge + 1)
                elif self.last_z:
                    self._launch()
            if not self._advance_ball(left_on, right_on):
                return False
            self.last_z = z_button
            self._draw(left_on, right_on)
            return True
        return step

    def main_loop(self, joystick):
        begin_game(0)
        self.reset()
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        begin_game(0)
        self.reset()
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class SabotrGame:
    """
    SABOTR
    Controls:
      - Directions: move
      - Hold Z: sneak; Z next to a guard from behind: takedown
      - C: return to menu
    Stealth puzzle: avoid enemy sight windows, hide bodies from patrols, and
    reach the target.
    """
    FRAME_MS = 80
    W = 16
    H = 14
    CELL = 4
    MAPS = (
        (
            "################",
            "#P.....#......T#",
            "#.###..#..###..#",
            "#...#.....#....#",
            "###.#.###.#.####",
            "#.....#...#....#",
            "#.#####.###.##.#",
            "#......G.......#",
            "#.##.###.#####.#",
            "#....#...#.....#",
            "####.#.###.#.###",
            "#....#.....#...#",
            "#..G....#......#",
            "################",
        ),
        (
            "################",
            "#P.............#",
            "#....G.........#",
            "#..............#",
            "#......####....#",
            "#......#..#....#",
            "#......#..#....#",
            "#......####....#",
            "#..............#",
            "#..........G...#",
            "#..............#",
            "#.....####.....#",
            "#............T.#",
            "################",
        ),
        (
            "################",
            "#P....#.......T#",
            "#.##..#..####..#",
            "#..#.....#.....#",
            "#..#######.###.#",
            "#........G#...##",
            "####.######.#.##",
            "#....#......#.##",
            "#.##.#.######.##",
            "#.#..#....G...##",
            "#.#.#######.####",
            "#.#...........##",
            "#....####.....##",
            "################",
        ),
        (
            "################",
            "#P.............#",
            "#..######..G...#",
            "#..#....#......#",
            "#..#....####...#",
            "#..#...........#",
            "#..#######.#####",
            "#........#.....#",
            "#####.####.###.#",
            "#.....#....#...#",
            "#.#####.####.#.#",
            "#.......G....#T#",
            "#.............##",
            "################",
        ),
    )
    DIRS = {JOYSTICK_UP: (0, -1), JOYSTICK_DOWN: (0, 1), JOYSTICK_LEFT: (-1, 0), JOYSTICK_RIGHT: (1, 0)}

    def __init__(self):
        self.reset()

    def reset(self):
        self.level = 0
        self.score = 0
        self.last_move = ticks_ms()
        self.last_z = False
        self.frame = 0
        self._load_map()

    def _load_map(self):
        self.map = self.MAPS[self.level % len(self.MAPS)]
        self.walls = bytearray(self.W * self.H)
        self.guards = []
        self.bodies = []
        self.player_dir = JOYSTICK_RIGHT
        for y, row in enumerate(self.map):
            for x, ch in enumerate(row):
                self.walls[y * self.W + x] = 1 if ch == "#" else 0
                if ch == "P":
                    self.px, self.py = x, y
                elif ch == "T":
                    self.tx, self.ty = x, y
                elif ch == "G":
                    self.guards.append([x, y, random.choice((JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_UP, JOYSTICK_DOWN)), 0])

    def _blocked(self, x, y):
        return x < 0 or x >= self.W or y < 0 or y >= self.H or self.walls[y * self.W + x]

    def _guard_cells(self):
        return set((g[0], g[1]) for g in self.guards)

    def _behind_guard(self, g):
        dx, dy = self.DIRS.get(g[2], (1, 0))
        return g[0] - dx, g[1] - dy

    def _try_takedown(self):
        for g in list(self.guards):
            if (self.px, self.py) == self._behind_guard(g) or abs(self.px - g[0]) + abs(self.py - g[1]) == 1:
                self.guards.remove(g)
                self.bodies.append((g[0], g[1]))
                self.score += 25
                return True
        return False

    def _move_player(self, joystick, sneaking):
        now = ticks_ms()
        delay = 210 if sneaking else 120
        if ticks_diff(now, self.last_move) < delay:
            return
        d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
        if d not in self.DIRS:
            return
        dx, dy = self.DIRS[d]
        nx, ny = self.px + dx, self.py + dy
        if not self._blocked(nx, ny) and (nx, ny) not in self._guard_cells():
            self.px, self.py = nx, ny
            self.player_dir = d
            self.last_move = now

    def _guard_fov(self, g):
        dx, dy = self.DIRS.get(g[2], (1, 0))
        cells = []
        for step in range(1, 6):
            cx = g[0] + dx * step
            cy = g[1] + dy * step
            if self._blocked(cx, cy):
                break
            cells.append((cx, cy))
            if step >= 3:
                for sx, sy in ((-dy, dx), (dy, -dx)):
                    px, py = cx + sx, cy + sy
                    if not self._blocked(px, py):
                        cells.append((px, py))
        return cells

    def _move_guards(self):
        if (self.frame & 3) != 0:
            return
        for g in self.guards:
            dx, dy = self.DIRS.get(g[2], (1, 0))
            nx, ny = g[0] + dx, g[1] + dy
            if self._blocked(nx, ny) or (nx, ny) in self._guard_cells():
                options = []
                for d, (odx, ody) in self.DIRS.items():
                    tx, ty = g[0] + odx, g[1] + ody
                    if not self._blocked(tx, ty):
                        options.append(d)
                if options:
                    g[2] = random.choice(options)
            else:
                g[0], g[1] = nx, ny

    def _caught(self):
        for g in self.guards:
            fov = self._guard_fov(g)
            if (self.px, self.py) in fov:
                return True
            for body in self.bodies:
                if body in fov:
                    return True
        return False

    def _draw_cell(self, x, y, color):
        px = x * self.CELL
        py = y * self.CELL + 1
        draw_rectangle(px, py, px + 3, py + 3, *color)

    def _draw(self):
        display.clear()
        for y in range(self.H):
            for x in range(self.W):
                if self.walls[y * self.W + x]:
                    self._draw_cell(x, y, (45, 55, 60))
                else:
                    self._draw_cell(x, y, (5, 18, 16))
        for g in self.guards:
            for x, y in self._guard_fov(g):
                self._draw_cell(x, y, (45, 35, 8))
        self._draw_cell(self.tx, self.ty, (0, 200, 80))
        for x, y in self.bodies:
            self._draw_cell(x, y, (110, 30, 30))
        for g in self.guards:
            self._draw_cell(g[0], g[1], (255, 120, 20))
        self._draw_cell(self.px, self.py, (60, 190, 255))
        draw_text_small(1, PLAY_HEIGHT, "L" + str(self.level + 1), 180, 180, 180)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        self.reset()

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            self.frame += 1
            if z_button and not self.last_z:
                self._try_takedown()
            self._move_player(joystick, z_button)
            self._move_guards()
            self.last_z = z_button
            if self._caught():
                set_game_over_score(self.score)
                return False
            if self.px == self.tx and self.py == self.ty:
                self.score += 100
                self.level += 1
                if self.level >= len(self.MAPS):
                    set_game_over_score(self.score, won=True)
                    return False
                self._load_map()
            self._draw()
            return True
        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class SoccerGame:
    """
    SOCCER
    Controls:
      - Directions: move blue formation / goalkeeper with ball
      - Z: kick when in possession
      - C: return to menu
    Atari-style 4-player-per-side soccer: striker, two defenders, goalkeeper,
    formation motion, two halves, and timed scoring.
    """
    FRAME_MS = 38
    HALF_TICKS = 1450

    def __init__(self):
        self.reset()

    def reset(self):
        self.blue_goals = 0
        self.red_goals = 0
        self.half = 1
        self.ticks_left = self.HALF_TICKS
        self.frame = 0
        self.anchor_x = 20
        self.anchor_y = PLAY_HEIGHT // 2
        self.red_anchor_x = 43
        self.red_anchor_y = PLAY_HEIGHT // 2
        self.blue_goalie_x = 5
        self.blue_goalie_y = PLAY_HEIGHT // 2
        self.red_goalie_x = 58
        self.red_goalie_y = PLAY_HEIGHT // 2
        self.input_dx = 0
        self.input_dy = 0
        self.ball_owner = None
        self._kickoff()

    def _formation(self, blue=True):
        if blue:
            ax = self.anchor_x
            ay = self.anchor_y
            return [[ax + 18, ay, "S"], [ax, ay - 9, "D"], [ax, ay + 9, "D"], [self.blue_goalie_x, self.blue_goalie_y, "G"]]
        ax = self.red_anchor_x
        ay = self.red_anchor_y
        return [[ax - 18, ay, "S"], [ax, ay - 9, "D"], [ax, ay + 9, "D"], [self.red_goalie_x, self.red_goalie_y, "G"]]

    def _kickoff(self):
        self.ball_x = WIDTH / 2
        self.ball_y = PLAY_HEIGHT / 2
        self.vx = random.choice((-1.2, 1.2))
        self.vy = random.choice((-0.45, 0.45))
        self.ball_owner = None

    def _move_blue(self, joystick):
        d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
        dx, dy = direction_to_delta(d)
        if dx or dy:
            self.input_dx = dx
            self.input_dy = dy
        goalie_owned = self.ball_owner and self.ball_owner[0] == "B" and self.ball_owner[1] == 3
        if goalie_owned:
            if dx:
                self.blue_goalie_x = clamp(self.blue_goalie_x + dx, 3, 12)
            if dy:
                self.blue_goalie_y = clamp(self.blue_goalie_y + dy * 2, PLAY_HEIGHT // 2 - 10, PLAY_HEIGHT // 2 + 10)
            return
        if dx:
            self.anchor_x = clamp(self.anchor_x + dx, 10, 31)
        if dy:
            self.anchor_y = clamp(self.anchor_y + dy * 2, 12, PLAY_HEIGHT - 12)

    def _move_red_ai(self):
        target = self.ball_y
        if self.red_anchor_y < target - 2:
            self.red_anchor_y += 1
        elif self.red_anchor_y > target + 2:
            self.red_anchor_y -= 1
        if self.ball_x > WIDTH // 2 + 3:
            self.red_anchor_x = min(48, self.red_anchor_x + 1)
        elif self.ball_x < WIDTH // 2 - 8:
            self.red_anchor_x = max(35, self.red_anchor_x - 1)
        self.red_anchor_y = clamp(self.red_anchor_y, 12, PLAY_HEIGHT - 12)
        if not (self.ball_owner and self.ball_owner[0] == "B" and self.ball_owner[1] == 3):
            if self.blue_goalie_x > 5:
                self.blue_goalie_x -= 1
            elif self.blue_goalie_x < 5:
                self.blue_goalie_x += 1
            if self.blue_goalie_y < self.ball_y - 1:
                self.blue_goalie_y += 1
            elif self.blue_goalie_y > self.ball_y + 1:
                self.blue_goalie_y -= 1
        if self.red_goalie_x < 58:
            self.red_goalie_x += 1
        elif self.red_goalie_x > 58:
            self.red_goalie_x -= 1
        if (self.frame & 1) == 0:
            goalie_target = self.ball_y if self.ball_x > WIDTH // 2 else PLAY_HEIGHT // 2
            if self.red_goalie_y < goalie_target - 1:
                self.red_goalie_y += 1
            elif self.red_goalie_y > goalie_target + 1:
                self.red_goalie_y -= 1
        self.blue_goalie_x = clamp(self.blue_goalie_x, 3, 12)
        self.blue_goalie_y = clamp(self.blue_goalie_y, PLAY_HEIGHT // 2 - 10, PLAY_HEIGHT // 2 + 10)
        self.red_goalie_x = clamp(self.red_goalie_x, 51, 60)
        self.red_goalie_y = clamp(self.red_goalie_y, PLAY_HEIGHT // 2 - 10, PLAY_HEIGHT // 2 + 10)

    def _nearest_player(self, blue=True):
        team = self._formation(blue)
        best = 0
        best_d = 9999
        for i, p in enumerate(team):
            dx = self.ball_x - p[0]
            dy = self.ball_y - p[1]
            d = dx * dx + dy * dy
            if d < best_d:
                best = i
                best_d = d
        return best, best_d

    def _capture_ball(self):
        if self.ball_owner:
            return
        speed2 = self.vx * self.vx + self.vy * self.vy
        bi, bd = self._nearest_player(True)
        ri, rd = self._nearest_player(False)
        b_role = self._formation(True)[bi][2]
        r_role = self._formation(False)[ri][2]
        blue_limit = 10 if speed2 < 3.2 else 5
        red_limit = 9 if speed2 < 3.0 else 4
        if b_role == "G" and self.ball_x < 10 and abs(self.ball_y - self.blue_goalie_y) <= 4:
            blue_limit = 18
        if r_role == "G" and self.ball_x > WIDTH - 10 and abs(self.ball_y - self.red_goalie_y) <= 3:
            red_limit = 14
        if bd < blue_limit:
            self.ball_owner = ("B", bi)
        elif rd < red_limit:
            self.ball_owner = ("R", ri)

    def _owner_pos(self):
        side, idx = self.ball_owner
        team = self._formation(side == "B")
        return team[idx][0], team[idx][1], team[idx][2]

    def _kick(self, blue=True):
        if blue:
            if self.input_dx < 0:
                self.vx = -1.85
                self.vy = self.input_dy * 1.20
            elif self.input_dx > 0:
                self.vx = 3.20
                self.vy = self.input_dy * 1.15
            elif self.input_dy:
                self.vx = 2.35
                self.vy = self.input_dy * 1.45
            else:
                target_y = PLAY_HEIGHT // 2 + (8 if self.red_goalie_y <= PLAY_HEIGHT // 2 else -8)
                target_y = clamp(target_y, PLAY_HEIGHT // 2 - 9, PLAY_HEIGHT // 2 + 9)
                self.vx = 3.10
                self.vy = (target_y - self.ball_y) * 0.105
        else:
            target_y = PLAY_HEIGHT // 2 + (7 if self.blue_goalie_y <= PLAY_HEIGHT // 2 else -7)
            self.vx = -2.35
            self.vy = (target_y - self.ball_y) * 0.075
        self.ball_owner = None

    def _advance_ball(self):
        if self.ball_owner:
            x, y, role = self._owner_pos()
            self.ball_x = x + (3 if self.ball_owner[0] == "B" else -3)
            self.ball_y = y
            return
        self.ball_x += self.vx
        self.ball_y += self.vy
        self.vx *= 0.992
        self.vy *= 0.992
        if self.ball_y <= 2:
            self.ball_y = 2
            self.vy = abs(self.vy)
        elif self.ball_y >= PLAY_HEIGHT - 3:
            self.ball_y = PLAY_HEIGHT - 3
            self.vy = -abs(self.vy)
        goal_y = PLAY_HEIGHT // 2
        if self.ball_x <= 1:
            if abs(self.ball_y - goal_y) <= 8:
                self.red_goals += 1
                self._kickoff()
            else:
                self.ball_x = 1
                self.vx = abs(self.vx)
        elif self.ball_x >= WIDTH - 2:
            if abs(self.ball_y - goal_y) <= 8:
                self.blue_goals += 1
                self._kickoff()
            else:
                self.ball_x = WIDTH - 2
                self.vx = -abs(self.vx)

    def _red_action(self):
        if self.ball_owner and self.ball_owner[0] == "R" and (self.frame % 18) == 0:
            self._kick(False)

    def _draw_team(self, team, color):
        for x, y, role in team:
            if role == "G":
                draw_rectangle(int(x) - 1, int(y) - 3, int(x) + 1, int(y) + 3, *color)
            elif role == "S":
                draw_rectangle(int(x) - 2, int(y) - 2, int(x) + 2, int(y) + 2, *color)
            else:
                draw_rectangle(int(x) - 1, int(y) - 2, int(x) + 1, int(y) + 2, *color)

    def _draw(self):
        display.clear()
        draw_rectangle(0, 0, WIDTH - 1, PLAY_HEIGHT - 1, 5, 58, 22)
        draw_line(WIDTH // 2, 1, WIDTH // 2, PLAY_HEIGHT - 2, 220, 220, 220)
        draw_rect_outline(0, PLAY_HEIGHT // 2 - 10, 3, PLAY_HEIGHT // 2 + 10, 255, 255, 255)
        draw_rect_outline(WIDTH - 4, PLAY_HEIGHT // 2 - 10, WIDTH - 1, PLAY_HEIGHT // 2 + 10, 255, 255, 255)
        self._draw_team(self._formation(True), (45, 165, 255))
        self._draw_team(self._formation(False), (255, 55, 45))
        draw_rectangle(int(self.ball_x) - 1, int(self.ball_y) - 1, int(self.ball_x) + 1, int(self.ball_y) + 1, 255, 255, 255)
        draw_text_small(1, PLAY_HEIGHT, str(self.blue_goals) + "-" + str(self.red_goals), 255, 255, 255)
        draw_text_small(27, PLAY_HEIGHT, "H" + str(self.half), 180, 180, 180)
        draw_text_small(45, PLAY_HEIGHT, str(max(0, self.ticks_left // 25)), 255, 220, 60)

    def _build_step(self, joystick):
        self.reset()

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            self.frame += 1
            self.ticks_left -= 1
            self._move_blue(joystick)
            self._move_red_ai()
            advanced_loose_ball = False
            if not self.ball_owner:
                self._advance_ball()
                advanced_loose_ball = True
                self._capture_ball()
            if z_button and self.ball_owner and self.ball_owner[0] == "B":
                self._kick(True)
                advanced_loose_ball = False
            self._red_action()
            if not advanced_loose_ball:
                self._advance_ball()
            if not self.ball_owner:
                self._capture_ball()
            if self.blue_goals >= 3 or self.red_goals >= 3:
                score = self.blue_goals * 100 + self.red_goals
                set_game_over_score(score, won=self.blue_goals > self.red_goals)
                return False
            if self.ticks_left <= 0:
                if self.half == 1:
                    self.half = 2
                    self.ticks_left = self.HALF_TICKS
                    self._kickoff()
                else:
                    score = self.blue_goals * 100 + self.red_goals
                    set_game_over_score(score, won=self.blue_goals > self.red_goals)
                    return False
            self._draw()
            return True
        return step

    def main_loop(self, joystick):
        begin_game(0)
        self.reset()
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        begin_game(0)
        self.reset()
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class TowerDefenseGame:
    """
    TWRDEF
    Controls:
      - Directions: move build cursor
      - Z: build tower / upgrade tower
      - C: return to menu
    Stop enemy waves before they reach the base. Towers automatically target
    enemies; repeated builds upgrade range, damage, slow, and splash.
    """
    FRAME_MS = 38
    CELL = 8
    GRID_W = WIDTH // CELL
    GRID_H = PLAY_HEIGHT // CELL
    OPEN_START = (0, 3)
    OPEN_BASE = (7, 3)
    LEVELS = (
        ("PATH", ((0, 1), (2, 1), (2, 3), (6, 3), (6, 1), (7, 1), (7, 5), (2, 5), (2, 6), (7, 6))),
        ("OPEN", None),
        ("PATH", ((0, 5), (3, 5), (3, 2), (5, 2), (5, 4), (7, 4), (7, 0))),
        ("OPEN", None),
        ("PATH", ((0, 3), (1, 3), (1, 1), (4, 1), (4, 5), (6, 5), (6, 2), (7, 2))),
        ("PATH", ((0, 6), (3, 6), (3, 4), (1, 4), (1, 2), (5, 2), (5, 0), (7, 0))),
        ("OPEN", None),
    )
    TOWER_COST = (0, 12, 18, 28, 42)
    TOWER_RANGE = (0, 18, 22, 26, 30)
    TOWER_DAMAGE = (0, 5, 9, 12, 18)
    TOWER_COOLDOWN = (0, 18, 16, 14, 12)

    def __init__(self):
        self.reset()

    def reset(self):
        self.cursor_x = 3
        self.cursor_y = 2
        self.last_move = ticks_ms()
        self.last_z = False
        self.wave = 0
        self.score = 0
        self.money = 32
        self.lives = 12
        self.frame = 0
        self.level = 1
        self.layout_id = -1
        self.open_level = False
        self.path_cells = set()
        self.route_cells = []
        self.start_cell = self.OPEN_START
        self.base_cell = self.OPEN_BASE
        self.towers = []
        self.enemies = []
        self.shots = []
        self.spawn_queue = 0
        self.spawn_gap = 34
        self.spawn_tick = 0
        self.next_wave_tick = 20
        self.flash_until = 0
        self._load_layout(0, clear_towers=False)

    def _cells_between(self, a, b):
        ax, ay = a
        bx, by = b
        dx = 1 if bx > ax else -1 if bx < ax else 0
        dy = 1 if by > ay else -1 if by < ay else 0
        cells = []
        x, y = ax, ay
        cells.append((x, y))
        while (x, y) != (bx, by):
            x += dx
            y += dy
            cells.append((x, y))
        return cells

    def _build_route_from_waypoints(self, points):
        route = []
        for i in range(len(points) - 1):
            segment = self._cells_between(points[i], points[i + 1])
            if route:
                segment = segment[1:]
            route.extend(segment)
        return route

    def _load_layout(self, layout_id, clear_towers):
        if clear_towers and self.towers:
            self.money += min(36, len(self.towers) * 7)
            self.towers = []
        self.enemies = []
        self.shots = []
        self.layout_id = layout_id
        self.level = layout_id + 1
        kind, points = self.LEVELS[layout_id]
        self.open_level = kind == "OPEN"
        if self.open_level:
            self.start_cell = self.OPEN_START
            self.base_cell = self.OPEN_BASE
            self.path_cells = set()
            self.route_cells = []
        else:
            self.route_cells = self._build_route_from_waypoints(points)
            self.path_cells = set(self.route_cells)
            self.start_cell = self.route_cells[0]
            self.base_cell = self.route_cells[-1]

    def _near_path(self, px, py, pad=5.8):
        return self._point_to_cell(px, py) in self.path_cells

    def _cell_center(self, gx, gy):
        return gx * self.CELL + self.CELL // 2, gy * self.CELL + self.CELL // 2

    def _point_to_cell(self, px, py):
        return (clamp(int(px) // self.CELL, 0, self.GRID_W - 1),
                clamp(int(py) // self.CELL, 0, self.GRID_H - 1))

    def _tower_at(self, gx, gy):
        for t in self.towers:
            if t[0] == gx and t[1] == gy:
                return t
        return None

    def _can_build(self, gx, gy):
        if not (0 <= gx < self.GRID_W and 0 <= gy < self.GRID_H):
            return False
        if (gx, gy) == self.start_cell or (gx, gy) == self.base_cell:
            return False
        if self._tower_at(gx, gy):
            return False
        if self.path_cells and (gx, gy) in self.path_cells:
            return False
        if self.open_level:
            for e in self.enemies:
                if self._point_to_cell(e[0], e[1]) == (gx, gy):
                    return False
            if not self._find_route(self.start_cell, blocked_extra=(gx, gy)):
                return False
            for e in self.enemies:
                if not self._find_route(self._point_to_cell(e[0], e[1]), blocked_extra=(gx, gy)):
                    return False
            return True
        return True

    def _try_build_or_upgrade(self):
        tower = self._tower_at(self.cursor_x, self.cursor_y)
        if tower:
            level = tower[2]
            if level >= 4:
                self.flash_until = ticks_ms() + 140
                return
            cost = self.TOWER_COST[level + 1]
            if self.money >= cost:
                self.money -= cost
                tower[2] += 1
                tower[3] = 0
            else:
                self.flash_until = ticks_ms() + 140
            return

        if not self._can_build(self.cursor_x, self.cursor_y):
            self.flash_until = ticks_ms() + 140
            return
        cost = self.TOWER_COST[1]
        if self.money >= cost:
            self.money -= cost
            self.towers.append([self.cursor_x, self.cursor_y, 1, 0])
            if self.open_level:
                self._reroute_open_enemies()
        else:
            self.flash_until = ticks_ms() + 140

    def _move_cursor(self, joystick):
        now = ticks_ms()
        if ticks_diff(now, self.last_move) < 125:
            return
        d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
        dx, dy = direction_to_delta(d)
        if dx or dy:
            self.cursor_x = clamp(self.cursor_x + dx, 0, self.GRID_W - 1)
            self.cursor_y = clamp(self.cursor_y + dy, 0, self.GRID_H - 1)
            self.last_move = now

    def _start_wave(self):
        next_wave = self.wave + 1
        layout_id = ((next_wave - 1) // 3) % len(self.LEVELS)
        if layout_id != self.layout_id:
            self._load_layout(layout_id, clear_towers=self.wave > 0)
        self.wave = next_wave
        self.spawn_queue = 7 + self.wave * 2
        self.spawn_gap = max(12, 34 - self.wave)
        self.spawn_tick = 0
        if self.wave % 5 == 0:
            self.spawn_queue += 1

    def _tower_cells(self):
        return set((t[0], t[1]) for t in self.towers)

    def _find_route(self, start, blocked_extra=None):
        blocked = self._tower_cells()
        if blocked_extra is not None:
            blocked.add(blocked_extra)
        blocked.discard(start)
        blocked.discard(self.base_cell)
        queue = [start]
        prev = {start: None}
        qi = 0
        while qi < len(queue):
            cell = queue[qi]
            qi += 1
            if cell == self.base_cell:
                route = []
                while cell is not None:
                    route.append(cell)
                    cell = prev[cell]
                route.reverse()
                return route
            x, y = cell
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                n = (nx, ny)
                if not (0 <= nx < self.GRID_W and 0 <= ny < self.GRID_H):
                    continue
                if n in blocked or n in prev:
                    continue
                prev[n] = cell
                queue.append(n)
        return []

    def _route_for_enemy(self, start_cell=None):
        if self.open_level:
            return self._find_route(start_cell or self.start_cell)
        return self.route_cells

    def _reroute_open_enemies(self):
        for e in self.enemies:
            cell = self._point_to_cell(e[0], e[1])
            route = self._find_route(cell)
            if len(route) >= 2:
                e[9] = route
                e[2] = 1

    def _spawn_enemy(self):
        boss = self.wave % 5 == 0 and self.spawn_queue == 1
        runner = (self.wave >= 4 and self.spawn_queue % 5 == 0)
        hp = 14 + self.wave * 4
        speed = 0.48 + min(0.30, self.wave * 0.018)
        reward = 3 + self.wave // 2
        kind = 0
        if runner:
            hp = max(8, hp - 6)
            speed += 0.25
            reward += 1
            kind = 1
        if boss:
            hp = hp * 4
            speed *= 0.62
            reward += 12
            kind = 2
        route = self._route_for_enemy()
        if len(route) < 2:
            return
        x, y = self._cell_center(route[0][0], route[0][1])
        self.enemies.append([float(x), float(y), 1, float(hp), float(hp), speed, 0, kind, reward, route])

    def _advance_waves(self):
        if self.spawn_queue > 0:
            self.spawn_tick += 1
            if self.spawn_tick >= self.spawn_gap:
                self.spawn_tick = 0
                self._spawn_enemy()
                self.spawn_queue -= 1
            return
        if not self.enemies:
            self.next_wave_tick -= 1
            if self.next_wave_tick <= 0:
                self.next_wave_tick = 55
                self._start_wave()

    def _advance_enemies(self):
        keep = []
        for e in self.enemies:
            if e[6] > 0:
                e[6] -= 1
            target_i = int(e[2])
            route = e[9]
            if target_i >= len(route):
                target_i = len(route) - 1
            tx, ty = self._cell_center(route[target_i][0], route[target_i][1])
            dx = tx - e[0]
            dy = ty - e[1]
            dist = math.sqrt(dx * dx + dy * dy) or 1.0
            speed = e[5] * (0.52 if e[6] > 0 else 1.0)
            if dist <= speed:
                e[0] = float(tx)
                e[1] = float(ty)
                e[2] += 1
                if e[2] >= len(route):
                    self.lives -= 2 if e[7] == 2 else 1
                    self.flash_until = ticks_ms() + 180
                    continue
            else:
                e[0] += dx / dist * speed
                e[1] += dy / dist * speed
            keep.append(e)
        self.enemies = keep

    def _enemy_progress(self, e):
        return int(e[2]) * 1000 + int(e[0]) + int(e[1])

    def _tower_target(self, tx, ty, rng):
        best = None
        best_p = -1
        r2 = rng * rng
        for e in self.enemies:
            dx = e[0] - tx
            dy = e[1] - ty
            if dx * dx + dy * dy <= r2:
                p = self._enemy_progress(e)
                if p > best_p:
                    best = e
                    best_p = p
        return best

    def _damage_enemy(self, enemy, damage, slow=False, splash=0):
        enemy[3] -= damage
        if slow:
            enemy[6] = max(enemy[6], 36)
        if splash:
            ex, ey = enemy[0], enemy[1]
            for e in self.enemies:
                if e is enemy:
                    continue
                dx = e[0] - ex
                dy = e[1] - ey
                if dx * dx + dy * dy <= splash * splash:
                    e[3] -= damage * 0.45
                    e[6] = max(e[6], 18)

    def _fire_towers(self):
        for t in self.towers:
            if t[3] > 0:
                t[3] -= 1
                continue
            cx, cy = self._cell_center(t[0], t[1])
            level = t[2]
            target = self._tower_target(cx, cy, self.TOWER_RANGE[level])
            if not target:
                continue
            self._damage_enemy(target, self.TOWER_DAMAGE[level], slow=level >= 2, splash=4 if level >= 3 else 0)
            t[3] = self.TOWER_COOLDOWN[level]
            color = (0, 220, 255) if level >= 2 else (255, 240, 60)
            if level >= 3:
                color = (210, 90, 255)
            self.shots.append([cx, cy, int(target[0]), int(target[1]), 4, color])

    def _collect_dead(self):
        keep = []
        for e in self.enemies:
            if e[3] <= 0:
                self.money += e[8]
                self.score += e[8] * 3 + self.wave
            else:
                keep.append(e)
        self.enemies = keep

    def _advance_shots(self):
        keep = []
        for s in self.shots:
            s[4] -= 1
            if s[4] > 0:
                keep.append(s)
        self.shots = keep

    def _draw_path(self):
        if self.path_cells:
            for gx, gy in self.path_cells:
                x = gx * self.CELL
                y = gy * self.CELL
                x2 = x + self.CELL - 1
                y2 = min(PLAY_HEIGHT - 1, y + self.CELL - 1)
                draw_rectangle(x, y, x2, y2, 98, 68, 34)
                edge = (62, 44, 24)
                if (gx, gy - 1) not in self.path_cells and not ((gx, gy) == self.base_cell and gy == 0):
                    draw_line(x, y, x2, y, *edge)
                if (gx + 1, gy) not in self.path_cells and not ((gx, gy) == self.base_cell and gx == self.GRID_W - 1):
                    draw_line(x2, y, x2, y2, *edge)
                if (gx, gy + 1) not in self.path_cells and not ((gx, gy) == self.base_cell and gy == self.GRID_H - 1):
                    draw_line(x, y2, x2, y2, *edge)
                if (gx - 1, gy) not in self.path_cells and not ((gx, gy) == self.start_cell and gx == 0):
                    draw_line(x, y, x, y2, *edge)
        else:
            for x in range(0, WIDTH, self.CELL):
                draw_line(x, 0, x, PLAY_HEIGHT - 1, 12, 34, 28)
            for y in range(0, PLAY_HEIGHT, self.CELL):
                draw_line(0, y, WIDTH - 1, y, 12, 34, 28)
        sx, sy = self._cell_center(self.start_cell[0], self.start_cell[1])
        ex, ey = self._cell_center(self.base_cell[0], self.base_cell[1])
        draw_rectangle(sx - 3, sy - 3, sx + 3, sy + 3, 255, 95, 0)
        draw_rectangle(ex - 4, ey - 4, ex + 4, ey + 4, 0, 160, 255)

    def _draw_towers(self):
        colors = ((0, 0, 0), (60, 220, 90), (60, 185, 255), (205, 85, 255), (255, 230, 90))
        for gx, gy, level, cooldown in self.towers:
            cx, cy = self._cell_center(gx, gy)
            r, g, b = colors[level]
            draw_rectangle(cx - 2, cy - 2, cx + 2, cy + 2, r, g, b)
            if level >= 2:
                draw_rectangle(cx - 1, cy - 4, cx + 1, cy - 3, r, g, b)
            if level >= 3:
                draw_rect_outline(cx - 3, cy - 3, cx + 3, cy + 3, r, g, b)

    def _draw_enemies(self):
        for e in self.enemies:
            x = int(e[0])
            y = int(e[1])
            if e[7] == 2:
                col = (255, 55, 220)
                size = 2
            elif e[7] == 1:
                col = (255, 120, 20)
                size = 1
            else:
                col = (255, 35, 35)
                size = 1
            if e[6] > 0:
                col = (80, 190, 255)
            draw_rectangle(x - size, y - size, x + size, y + size, col[0], col[1], col[2])
            hp_w = max(1, int((e[3] * 5) / max(1, e[4])))
            draw_rectangle(x - 2, y - size - 3, x - 3 + hp_w, y - size - 3, 0, 255, 80)

    def _draw_shots(self):
        for x1, y1, x2, y2, ttl, col in self.shots:
            draw_line(x1, y1, x2, y2, col[0], col[1], col[2])

    def _draw_cursor(self):
        cx = self.cursor_x * self.CELL
        cy = self.cursor_y * self.CELL
        blocked = not self._can_build(self.cursor_x, self.cursor_y)
        tower = self._tower_at(self.cursor_x, self.cursor_y)
        if tower:
            col = (255, 255, 255)
        elif blocked or ticks_diff(ticks_ms(), self.flash_until) < 0:
            col = (255, 50, 40)
        else:
            col = (255, 240, 60)
        draw_rect_outline(cx, cy, cx + self.CELL - 1, cy + self.CELL - 1, col[0], col[1], col[2])
        if tower:
            tx, ty = self._cell_center(self.cursor_x, self.cursor_y)
            rng = self.TOWER_RANGE[tower[2]]
            draw_rect_outline(max(0, tx - rng), max(0, ty - rng),
                              min(WIDTH - 1, tx + rng), min(PLAY_HEIGHT - 1, ty + rng),
                              35, 70, 95)

    def _draw_hud(self):
        draw_rectangle(0, PLAY_HEIGHT, WIDTH - 1, HEIGHT - 1, 0, 0, 0)
        draw_text_small(1, PLAY_HEIGHT, "W" + str(self.wave), 180, 180, 180)
        draw_text_small(19, PLAY_HEIGHT, "$" + str(min(99, self.money)), 255, 220, 40)
        draw_text_small(43, PLAY_HEIGHT, "B" + str(max(0, self.lives)), 80, 190, 255)
        if self.open_level:
            draw_rectangle(WIDTH - 2, PLAY_HEIGHT + 1, WIDTH - 1, PLAY_HEIGHT + 2, 80, 255, 140)

    def _draw(self):
        display.clear()
        draw_rectangle(0, 0, WIDTH - 1, PLAY_HEIGHT - 1, 8, 24, 20)
        self._draw_path()
        self._draw_towers()
        self._draw_enemies()
        self._draw_shots()
        self._draw_cursor()
        self._draw_hud()

    def _build_step(self, joystick):
        self.reset()

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            self.frame += 1
            self._move_cursor(joystick)
            if z_button and not self.last_z:
                self._try_build_or_upgrade()
            self.last_z = z_button
            self._advance_waves()
            self._advance_enemies()
            self._fire_towers()
            self._collect_dead()
            self._advance_shots()
            if self.lives <= 0:
                set_game_over_score(self.score)
                return False
            self._draw()
            if (self.frame % 90) == 0:
                gc.collect()
            return True
        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class DigDugGame:
    """
    DIGDUG
    Controls:
      - Directions: dig/move
      - Z: pump the enemy in the facing direction
      - C: return to menu
    Dig tunnels, collect gems, and clear burrowing enemies.
    """
    FRAME_MS = 70
    GRID_W = 8
    GRID_H = 7
    CELL = 8

    def __init__(self):
        self.reset()

    def reset(self):
        self.level = 1
        self.score = 0
        self.lives = 3
        self.last_move = ticks_ms()
        self.last_z = False
        self.dir = JOYSTICK_RIGHT
        self._new_level()

    def _new_level(self):
        self.px = self.GRID_W // 2
        self.py = self.GRID_H - 1
        self.dir = JOYSTICK_RIGHT
        self.dirt = [[True for _x in range(self.GRID_W)] for _y in range(self.GRID_H)]
        self.dirt[self.py][self.px] = False
        for x in range(1, self.GRID_W - 1):
            if x % 2 == 0:
                self.dirt[self.py][x] = False
        self.gems = []
        while len(self.gems) < min(7, 3 + self.level):
            x = random.randint(0, self.GRID_W - 1)
            y = random.randint(1, self.GRID_H - 2)
            if (x, y) != (self.px, self.py) and (x, y) not in self.gems:
                self.gems.append((x, y))
        self.enemies = []
        count = min(6, 2 + self.level)
        tries = 0
        while len(self.enemies) < count and tries < 80:
            tries += 1
            x = random.randint(0, self.GRID_W - 1)
            y = random.randint(0, self.GRID_H - 3)
            if abs(x - self.px) + abs(y - self.py) > 5:
                self.enemies.append([x, y, 0, random.choice((JOYSTICK_LEFT, JOYSTICK_RIGHT)), 0])
                self.dirt[y][x] = False

    def _move_player(self, joystick):
        now = ticks_ms()
        if ticks_diff(now, self.last_move) < 130:
            return
        d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
        if not d:
            return
        dx, dy = direction_to_delta(d)
        nx = self.px + dx
        ny = self.py + dy
        if 0 <= nx < self.GRID_W and 0 <= ny < self.GRID_H:
            self.dir = d
            self.px = nx
            self.py = ny
            if self.dirt[ny][nx]:
                self.dirt[ny][nx] = False
                self.score += 1
            if (nx, ny) in self.gems:
                self.gems.remove((nx, ny))
                self.score += 25
            self.last_move = now

    def _pump(self):
        dx, dy = direction_to_delta(self.dir, 1, 0)
        for e in self.enemies:
            dist = abs(e[0] - self.px) + abs(e[1] - self.py)
            aligned = (dx and e[1] == self.py and (e[0] - self.px) * dx > 0 and dist <= 2)
            aligned = aligned or (dy and e[0] == self.px and (e[1] - self.py) * dy > 0 and dist <= 2)
            if aligned:
                e[2] += 1
                e[4] = 10
                self.score += 3
                if e[2] >= 3:
                    self.score += 60
                    self.enemies.remove(e)
                return

    def _enemy_step(self, e):
        if e[4] > 0:
            e[4] -= 1
            return
        choices = []
        for d in (JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT):
            dx, dy = direction_to_delta(d)
            nx = e[0] + dx
            ny = e[1] + dy
            if 0 <= nx < self.GRID_W and 0 <= ny < self.GRID_H:
                cost = abs(nx - self.px) + abs(ny - self.py)
                if not self.dirt[ny][nx]:
                    choices.append((cost, nx, ny, False))
                elif random.randint(0, 7) == 0:
                    choices.append((cost + 3, nx, ny, True))
        if not choices:
            return
        best = choices[0]
        for c in choices[1:]:
            if c[0] < best[0]:
                best = c
        e[0] = best[1]
        e[1] = best[2]
        if best[3]:
            self.dirt[e[1]][e[0]] = False

    def _advance_enemies(self):
        if random.randint(0, max(1, 4 - self.level // 2)) != 0:
            return
        for e in self.enemies:
            self._enemy_step(e)

    def _hit_player(self):
        for e in self.enemies:
            if e[0] == self.px and e[1] == self.py:
                return True
        return False

    def _hurt(self):
        self.lives -= 1
        if self.lives <= 0:
            set_game_over_score(self.score)
            return False
        self.px = self.GRID_W // 2
        self.py = self.GRID_H - 1
        self.dirt[self.py][self.px] = False
        return True

    def _draw_cell(self, gx, gy, col):
        x = gx * self.CELL
        y = gy * self.CELL + 1
        draw_rectangle(x + 1, y + 1, x + self.CELL - 2, y + self.CELL - 2, col[0], col[1], col[2])

    def _draw(self):
        display.clear()
        for y in range(self.GRID_H):
            for x in range(self.GRID_W):
                if self.dirt[y][x]:
                    shade = 34 + min(60, y * 8)
                    self._draw_cell(x, y, (shade, 22 + y * 5, 8))
                else:
                    draw_rect_outline(x * self.CELL + 2, y * self.CELL + 3,
                                      x * self.CELL + self.CELL - 3,
                                      y * self.CELL + self.CELL, 18, 15, 22)
        for x, y in self.gems:
            self._draw_cell(x, y, (40, 180, 255))
            display.set_pixel(x * self.CELL + 4, y * self.CELL + 4, 255, 255, 255)
        for e in self.enemies:
            col = (255, 70, 50) if e[2] == 0 else (255, 170, 220)
            self._draw_cell(e[0], e[1], col)
        self._draw_cell(self.px, self.py, (255, 230, 70))
        dx, dy = direction_to_delta(self.dir, 1, 0)
        hx = self.px * self.CELL + 4 + dx * 4
        hy = self.py * self.CELL + 5 + dy * 4
        display.set_pixel(hx, hy, 255, 255, 255)
        for i in range(self.lives):
            draw_rectangle(WIDTH - 4 - i * 4, 0, WIDTH - 2 - i * 4, 1, 255, 80, 80)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        self.reset()
        display_score_and_time(0, force=True)

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            self._move_player(joystick)
            if z_button and not self.last_z:
                self._pump()
            self.last_z = z_button
            self._advance_enemies()
            if self._hit_player() and not self._hurt():
                return False
            if not self.enemies:
                self.score += 100 + self.level * 25 + len(self.gems) * 5
                self.level += 1
                self._new_level()
            self._draw()
            return True

        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class JoustGame:
    """
    JOUST
    Controls:
      - Left / Right: fly
      - Z: flap
      - C: return to menu
    Defeat riders by colliding from above.
    """
    FRAME_MS = 35

    def __init__(self):
        self.reset()

    def reset(self):
        self.score = 0
        self.level = 1
        self.lives = 3
        self.x = WIDTH // 2
        self.y = PLAY_HEIGHT - 12
        self.vx = 0.0
        self.vy = 0.0
        self.frame = 0
        self.invincible_until = 0
        self._new_wave()

    def _new_wave(self):
        self.enemies = []
        count = min(7, 2 + self.level)
        for i in range(count):
            side = -8 if i % 2 else WIDTH + 2
            self.enemies.append([float(side), float(10 + (i * 11) % 38),
                                 -1.1 if side > WIDTH else 1.1, 0.0])

    def _platform_at(self, x, y):
        platforms = ((3, PLAY_HEIGHT - 5, 58), (6, 37, 20), (38, 37, 20), (18, 22, 28))
        for px, py, pw in platforms:
            if px <= x <= px + pw and py - 2 <= y <= py + 2:
                return py
        return None

    def _input(self, joystick, z_button):
        d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT], debounce=False)
        if d == JOYSTICK_LEFT:
            self.vx -= 0.18
        elif d == JOYSTICK_RIGHT:
            self.vx += 0.18
        else:
            self.vx *= 0.93
        self.vx = clamp(self.vx, -2.2, 2.2)
        if z_button:
            self.vy -= 0.55
        self.vy += 0.24
        self.vy = clamp(self.vy, -3.0, 3.0)
        self.x += self.vx
        self.y += self.vy
        if self.x < -5:
            self.x = WIDTH + 2
        elif self.x > WIDTH + 5:
            self.x = -2
        plat = self._platform_at(int(self.x), int(self.y) + 4)
        if plat is not None and self.vy >= 0:
            self.y = plat - 5
            self.vy = 0
        self.y = clamp(self.y, 2, PLAY_HEIGHT - 7)

    def _advance_enemies(self):
        for e in self.enemies:
            if random.randint(0, 5) == 0:
                if e[0] < self.x:
                    e[2] += 0.16
                else:
                    e[2] -= 0.16
            if random.randint(0, 9) == 0:
                e[3] -= 0.55
            e[3] += 0.18
            e[2] = clamp(e[2], -1.8 - self.level * 0.08, 1.8 + self.level * 0.08)
            e[3] = clamp(e[3], -2.4, 2.8)
            e[0] += e[2]
            e[1] += e[3]
            if e[0] < -7:
                e[0] = WIDTH + 4
            elif e[0] > WIDTH + 7:
                e[0] = -4
            plat = self._platform_at(int(e[0]), int(e[1]) + 4)
            if plat is not None and e[3] >= 0:
                e[1] = plat - 5
                e[3] = -0.6
            e[1] = clamp(e[1], 2, PLAY_HEIGHT - 7)

    def _collisions(self):
        now = ticks_ms()
        survivors = []
        for e in self.enemies:
            if rects_overlap(int(self.x), int(self.y), 5, 5, int(e[0]), int(e[1]), 5, 5):
                if self.y + 1 < e[1]:
                    self.score += 80 + self.level * 10
                    self.vy = -1.4
                    continue
                if ticks_diff(now, self.invincible_until) >= 0:
                    self.lives -= 1
                    self.invincible_until = now + 1600
                    self.x = WIDTH // 2
                    self.y = PLAY_HEIGHT - 12
                    self.vx = 0.0
                    self.vy = -1.0
                    if self.lives <= 0:
                        set_game_over_score(self.score)
                        return False
            survivors.append(e)
        self.enemies = survivors
        if not self.enemies:
            self.score += 150 + self.level * 25
            self.level += 1
            self._new_wave()
        return True

    def _draw_rider(self, x, y, col):
        ix = int(x)
        iy = int(y)
        draw_rectangle(ix, iy + 2, ix + 4, iy + 4, col[0], col[1], col[2])
        draw_line(ix - 2, iy + 3, ix + 6, iy + 1, 255, 255, 255)
        display.set_pixel(ix + 2, iy, 255, 230, 90)

    def _draw(self):
        display.clear()
        for px, py, pw in ((3, PLAY_HEIGHT - 5, 58), (6, 37, 20), (38, 37, 20), (18, 22, 28)):
            draw_rectangle(px, py, px + pw, py + 1, 60, 160, 90)
        for e in self.enemies:
            self._draw_rider(e[0], e[1], (255, 80, 40))
        inv = ticks_diff(ticks_ms(), self.invincible_until) < 0
        if not inv or (self.frame // 4) % 2 == 0:
            self._draw_rider(self.x, self.y, (0, 210, 255))
        for i in range(self.lives):
            draw_rectangle(i * 4, 0, i * 4 + 2, 1, 255, 80, 80)
        draw_text_small(WIDTH - 14, 0, "W" + str(self.level), 180, 180, 180)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        self.reset()
        display_score_and_time(0, force=True)

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            self.frame += 1
            self._input(joystick, z_button)
            self._advance_enemies()
            if not self._collisions():
                return False
            self._draw()
            return True

        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class BurgerTimeGame:
    """
    BURGER
    Controls:
      - Directions: run platforms and ladders
      - Z: pepper nearby enemies
      - C: return to menu
    Walk over burger layers to drop every ingredient.
    """
    FRAME_MS = 58
    GRID_W = 8
    GRID_H = 7
    CELL = 8
    PLAT_ROWS = (0, 2, 4, 6)
    LADDERS = (1, 4, 6)

    def __init__(self):
        self.reset()

    def reset(self):
        self.score = 0
        self.level = 1
        self.lives = 3
        self.pepper = 3
        self.last_move = ticks_ms()
        self.last_z = False
        self._new_level()

    def _new_level(self):
        self.px = 0
        self.py = 6
        self.ingredients = []
        cols = (0, 3, 5)
        for bi, x0 in enumerate(cols):
            for ri, y in enumerate(self.PLAT_ROWS):
                width = 3 if x0 <= 4 else 2
                self.ingredients.append([x0, y, width, 0, y + 1 + bi * 5 + ri])
        self.enemies = []
        count = min(5, 2 + self.level)
        for i in range(count):
            self.enemies.append([7 - (i % 3), self.PLAT_ROWS[i % len(self.PLAT_ROWS)], 0, 0])

    def _on_ladder(self, x):
        return x in self.LADDERS

    def _legal_cell(self, x, y):
        if x < 0 or x >= self.GRID_W or y < 0 or y >= self.GRID_H:
            return False
        return y in self.PLAT_ROWS or self._on_ladder(x)

    def _move_player(self, joystick):
        now = ticks_ms()
        if ticks_diff(now, self.last_move) < 125:
            return
        d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
        if not d:
            return
        dx, dy = direction_to_delta(d)
        nx = self.px + dx
        ny = self.py + dy
        if dy and not self._on_ladder(self.px):
            return
        if self._legal_cell(nx, ny):
            self.px = nx
            self.py = ny
            self._step_ingredients()
            self.last_move = now

    def _step_ingredients(self):
        for item in self.ingredients:
            x0, y, width, mask, _drop = item
            if self.py == y and x0 <= self.px < x0 + width:
                bit = 1 << (self.px - x0)
                if not (mask & bit):
                    item[3] = mask | bit
                    self.score += 5

    def _drop_ready(self, item):
        return item[3] == ((1 << item[2]) - 1)

    def _advance_drops(self):
        for item in self.ingredients:
            if self._drop_ready(item) and item[1] < self.GRID_H:
                item[1] += 0.25
                for e in self.enemies:
                    if int(item[1]) == e[1] and item[0] <= e[0] < item[0] + item[2]:
                        e[0] = random.randint(0, self.GRID_W - 1)
                        e[1] = 0
                        e[3] = 10
                        self.score += 30

    def _pepper(self):
        if self.pepper <= 0:
            return
        used = False
        for e in self.enemies:
            if abs(e[0] - self.px) + abs(e[1] - self.py) <= 2:
                e[3] = 18
                used = True
        if used:
            self.pepper -= 1
            self.score += 8

    def _enemy_move_options(self, e):
        opts = []
        for d in (JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_UP, JOYSTICK_DOWN):
            dx, dy = direction_to_delta(d)
            nx = e[0] + dx
            ny = e[1] + dy
            if dy and not self._on_ladder(e[0]):
                continue
            if self._legal_cell(nx, ny):
                opts.append((abs(nx - self.px) + abs(ny - self.py), nx, ny))
        return opts

    def _move_enemies(self):
        if random.randint(0, 1):
            return
        for e in self.enemies:
            if e[3] > 0:
                e[3] -= 1
                continue
            opts = self._enemy_move_options(e)
            if not opts:
                continue
            best = opts[random.randint(0, len(opts) - 1)]
            for opt in opts:
                if opt[0] < best[0] or random.randint(0, 5) == 0:
                    best = opt
            e[0] = best[1]
            e[1] = best[2]

    def _hit_player(self):
        for e in self.enemies:
            if e[3] <= 0 and e[0] == self.px and e[1] == self.py:
                return True
        return False

    def _hurt(self):
        self.lives -= 1
        if self.lives <= 0:
            set_game_over_score(self.score)
            return False
        self.px = 0
        self.py = 6
        for e in self.enemies:
            e[3] = 8
        return True

    def _complete(self):
        for item in self.ingredients:
            if int(item[1]) < self.GRID_H:
                return False
        return True

    def _draw_grid(self):
        for y in self.PLAT_ROWS:
            draw_rectangle(0, y * self.CELL + 6, WIDTH - 1, y * self.CELL + 7, 80, 95, 150)
        for x in self.LADDERS:
            draw_line(x * self.CELL + 3, 0, x * self.CELL + 3, PLAY_HEIGHT - 2, 70, 150, 210)
            draw_line(x * self.CELL + 5, 0, x * self.CELL + 5, PLAY_HEIGHT - 2, 70, 150, 210)

    def _draw(self):
        display.clear()
        self._draw_grid()
        for item in self.ingredients:
            x0, y, width, mask, hue = item
            iy = int(y)
            if iy >= self.GRID_H:
                continue
            r, g, b = hsb_to_rgb(hue * 23, 0.85, 1)
            for i in range(width):
                x = (x0 + i) * self.CELL + 1
                py = iy * self.CELL + 2
                dim = bool(mask & (1 << i))
                draw_rectangle(x, py, x + 6, py + 2,
                               r if dim else r // 2,
                               g if dim else g // 2,
                               b if dim else b // 2)
        for e in self.enemies:
            col = (180, 180, 180) if e[3] > 0 else (255, 60, 60)
            draw_rectangle(e[0] * self.CELL + 2, e[1] * self.CELL + 2,
                           e[0] * self.CELL + 5, e[1] * self.CELL + 5,
                           col[0], col[1], col[2])
        draw_rectangle(self.px * self.CELL + 2, self.py * self.CELL + 1,
                       self.px * self.CELL + 5, self.py * self.CELL + 5,
                       255, 230, 90)
        for i in range(self.lives):
            draw_rectangle(i * 4, 0, i * 4 + 2, 1, 255, 80, 80)
        draw_text_small(WIDTH - 16, 0, "P" + str(self.pepper), 210, 210, 210)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        self.reset()
        display_score_and_time(0, force=True)

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            self._move_player(joystick)
            if z_button and not self.last_z:
                self._pepper()
            self.last_z = z_button
            self._advance_drops()
            self._move_enemies()
            if self._hit_player() and not self._hurt():
                return False
            if self._complete():
                self.score += 120 + self.level * 30 + self.pepper * 10
                self.level += 1
                self.pepper = min(5, self.pepper + 1)
                self._new_level()
            self._draw()
            return True

        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class StickArcherGame:
    """
    STKARC
    Controls:
      - Up / Down: aim bow
      - Left / Right: sidestep
      - Hold Z: draw bow, release Z: fire
      - C: return to menu
    Stickman archery duel with simple arrow physics and ragdoll knockouts.
    """
    FRAME_MS = 35
    GROUND_Y = PLAY_HEIGHT - 5
    MAX_CHARGE = 30

    def __init__(self):
        self.reset()

    def reset(self):
        self.score = 0
        self.wave = 1
        self.player_hp = 5
        self.enemy_hp = 3
        self.px = 9
        self.ex = WIDTH - 10
        self.aim = 38
        self.charge = 0
        self.last_z = False
        self.last_move = ticks_ms()
        self.arrows = []
        self.parts = []
        self.hit_flash = 0
        self.wind = random.randint(-8, 8) / 100.0
        self.enemy_next_shot = ticks_ms() + 1100
        self.enemy_fall_until = 0
        self.player_fall_until = 0

    def _move_player(self, joystick):
        now = ticks_ms()
        if ticks_diff(now, self.last_move) < 70:
            return
        d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
        if d == JOYSTICK_UP:
            self.aim = min(78, self.aim + 3)
            self.last_move = now
        elif d == JOYSTICK_DOWN:
            self.aim = max(12, self.aim - 3)
            self.last_move = now
        elif d == JOYSTICK_LEFT:
            self.px = max(4, self.px - 1)
            self.last_move = now
        elif d == JOYSTICK_RIGHT:
            self.px = min(WIDTH // 2 - 5, self.px + 1)
            self.last_move = now

    def _fire_player(self):
        rad = math.radians(self.aim)
        speed = 2.3 + self.charge * 0.12
        sx = self.px + 4
        sy = self.GROUND_Y - 14
        self.arrows.append([float(sx), float(sy), math.cos(rad) * speed,
                            -math.sin(rad) * speed, 0, sx, sy])
        self.charge = 0

    def _fire_enemy(self):
        dx = max(10, self.ex - self.px)
        base = 24 + min(28, dx // 2)
        angle = clamp(base + random.randint(-9, 9) - self.wave, 14, 72)
        rad = math.radians(angle)
        speed = 2.6 + min(1.3, self.wave * 0.14)
        sx = self.ex - 4
        sy = self.GROUND_Y - 14
        self.arrows.append([float(sx), float(sy), -math.cos(rad) * speed,
                            -math.sin(rad) * speed, 1, sx, sy])
        self.enemy_next_shot = ticks_ms() + max(650, 1700 - self.wave * 80 + random.randint(-160, 180))

    def _handle_bow(self, z_button):
        if z_button:
            self.charge = min(self.MAX_CHARGE, self.charge + 1)
        elif self.last_z and self.charge > 2:
            self._fire_player()
        elif not z_button and self.charge:
            self.charge = 0
        self.last_z = z_button

    def _target_hit(self, arrow, tx, hp):
        ax = int(arrow[0])
        ay = int(arrow[1])
        body_x = int(tx) - 3
        body_y = self.GROUND_Y - 18
        if rects_overlap(ax, ay, 2, 2, body_x, body_y, 7, 16):
            headshot = ay <= body_y + 4
            dmg = 2 if headshot else 1
            return max(0, hp - dmg), True, headshot
        return hp, False, False

    def _spawn_parts(self, x, friendly=False):
        col = (80, 210, 255) if friendly else (255, 80, 60)
        for i in range(7):
            vx = random.randint(-14, 14) / 10.0
            vy = -random.randint(4, 18) / 10.0
            self.parts.append([float(x), float(self.GROUND_Y - 14 + i % 4),
                               vx, vy, 28 + random.randint(0, 18), col])

    def _advance_arrows(self):
        keep = []
        for a in self.arrows:
            a[5] = a[0]
            a[6] = a[1]
            a[0] += a[2]
            a[1] += a[3]
            a[2] += self.wind
            a[3] += 0.16
            if a[4] == 0:
                self.enemy_hp, hit, head = self._target_hit(a, self.ex, self.enemy_hp)
                if hit:
                    self.score += 18 if head else 10
                    self.hit_flash = ticks_ms() + 120
                    if self.enemy_hp <= 0:
                        self.score += 80 + self.wave * 15
                        self.enemy_fall_until = ticks_ms() + 850
                        self._spawn_parts(self.ex, False)
                    continue
            else:
                self.player_hp, hit, _head = self._target_hit(a, self.px, self.player_hp)
                if hit:
                    self.hit_flash = ticks_ms() + 120
                    if self.player_hp <= 0:
                        self.player_fall_until = ticks_ms() + 850
                        self._spawn_parts(self.px, True)
                    continue
            if -4 <= a[0] <= WIDTH + 4 and a[1] < self.GROUND_Y:
                keep.append(a)
        self.arrows = keep

    def _advance_parts(self):
        keep = []
        for p in self.parts:
            p[0] += p[2]
            p[1] += p[3]
            p[3] += 0.18
            if p[1] > self.GROUND_Y - 1:
                p[1] = self.GROUND_Y - 1
                p[3] *= -0.25
                p[2] *= 0.75
            p[4] -= 1
            if p[4] > 0:
                keep.append(p)
        self.parts = keep

    def _advance_rounds(self):
        now = ticks_ms()
        if self.enemy_hp <= 0 and ticks_diff(now, self.enemy_fall_until) >= 0:
            self.wave += 1
            self.enemy_hp = 2 + min(5, self.wave)
            self.ex = WIDTH - 10 - random.randint(0, 5)
            self.wind = random.randint(-10, 10) / 100.0
            self.enemy_next_shot = now + 900
            self.arrows = [a for a in self.arrows if a[4] != 0]
        if self.player_hp <= 0 and ticks_diff(now, self.player_fall_until) >= 0:
            set_game_over_score(self.score)
            return False
        return True

    def _draw_stickman(self, x, hp, friendly=True, falling=False):
        col = (80, 210, 255) if friendly else (255, 80, 60)
        ix = int(x)
        foot = self.GROUND_Y
        lean = 5 if falling else 0
        head_y = foot - 18 + lean
        body_y = foot - 13 + lean
        draw_rectangle(ix - 2, head_y, ix + 2, head_y + 3, col[0], col[1], col[2])
        draw_line(ix, head_y + 4, ix + lean, body_y + 7, col[0], col[1], col[2])
        draw_line(ix + lean, body_y, ix - 4, body_y + 4, col[0], col[1], col[2])
        draw_line(ix + lean, body_y, ix + 4, body_y + 4, col[0], col[1], col[2])
        draw_line(ix + lean, body_y + 7, ix - 3, foot, col[0], col[1], col[2])
        draw_line(ix + lean, body_y + 7, ix + 4, foot, col[0], col[1], col[2])
        if not falling:
            bow_x = ix + 6 if friendly else ix - 6
            draw_line(ix + (3 if friendly else -3), body_y + 2, bow_x, body_y - 4, 210, 170, 80)
            draw_line(ix + (3 if friendly else -3), body_y + 2, bow_x, body_y + 8, 210, 170, 80)
        for i in range(hp):
            px = ix - 5 + i * 2
            display.set_pixel(px, max(0, head_y - 3), 0, 255, 80)

    def _draw_aim(self):
        rad = math.radians(self.aim)
        sx = self.px + 4
        sy = self.GROUND_Y - 14
        ex = sx + int(math.cos(rad) * (8 + self.charge // 3))
        ey = sy - int(math.sin(rad) * (8 + self.charge // 3))
        draw_line(sx, sy, ex, ey, 255, 230, 80)
        if self.charge:
            bar = int(20 * self.charge / self.MAX_CHARGE)
            draw_rectangle(1, 2, 1 + bar, 3, 255, 220, 40)

    def _draw(self):
        display.clear()
        sky_flash = ticks_diff(ticks_ms(), self.hit_flash) < 0
        if sky_flash:
            draw_rectangle(0, 0, WIDTH - 1, PLAY_HEIGHT - 1, 28, 10, 10)
        draw_rectangle(0, self.GROUND_Y, WIDTH - 1, PLAY_HEIGHT - 1, 45, 80, 45)
        for x in range(0, WIDTH, 6):
            draw_rectangle(x, self.GROUND_Y - 1, x + 2, self.GROUND_Y - 1, 90, 140, 60)
        falling_player = self.player_hp <= 0
        falling_enemy = self.enemy_hp <= 0
        self._draw_stickman(self.px, max(0, self.player_hp), True, falling_player)
        self._draw_stickman(self.ex, max(0, self.enemy_hp), False, falling_enemy)
        if not falling_player:
            self._draw_aim()
        for a in self.arrows:
            col = (255, 240, 120) if a[4] == 0 else (255, 110, 80)
            draw_line(int(a[5]), int(a[6]), int(a[0]), int(a[1]), col[0], col[1], col[2])
            display.set_pixel(int(a[0]), int(a[1]), 255, 255, 255)
        for p in self.parts:
            col = p[5]
            draw_rectangle(int(p[0]), int(p[1]), int(p[0]) + 1, int(p[1]) + 1, col[0], col[1], col[2])
        wx = WIDTH - 11
        draw_text_small(wx, 2, "W" + str(self.wave), 170, 170, 170)
        wind_x = WIDTH // 2
        if self.wind < -0.01:
            draw_line(wind_x + 3, 2, wind_x - 3, 2, 170, 220, 255)
            display.set_pixel(wind_x - 4, 2, 170, 220, 255)
        elif self.wind > 0.01:
            draw_line(wind_x - 3, 2, wind_x + 3, 2, 170, 220, 255)
            display.set_pixel(wind_x + 4, 2, 170, 220, 255)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        self.reset()
        display_score_and_time(0, force=True)

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            now = ticks_ms()
            if self.player_hp > 0:
                self._move_player(joystick)
                self._handle_bow(z_button)
            if self.enemy_hp > 0 and ticks_diff(now, self.enemy_next_shot) >= 0:
                self._fire_enemy()
            self._advance_arrows()
            self._advance_parts()
            if not self._advance_rounds():
                return False
            self._draw()
            return True

        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class OrbitGame:
    """
    ORBIT
    Controls:
      - Directions: aim thrust
      - Z: eject mass and accelerate
      - C: return to menu
    Absorb smaller blobs, avoid larger ones, and use gravity wells carefully.
    """
    FRAME_MS = 40

    def __init__(self):
        self.reset()

    def reset(self):
        self.level = 1
        self.score = 0
        self.aim = 0.0
        self.last_thrust = 0
        self._new_level()

    def _new_level(self):
        self.x = WIDTH * 0.32
        self.y = PLAY_HEIGHT * 0.52
        self.vx = 0.0
        self.vy = 0.0
        self.r = 4.2
        self.target_r = min(12.0, 7.2 + self.level * 0.45)
        self.blobs = []
        count = min(18, 8 + self.level * 2)
        tries = 0
        while len(self.blobs) < count and tries < 120:
            tries += 1
            x = random.randint(5, WIDTH - 6)
            y = random.randint(6, PLAY_HEIGHT - 7)
            if abs(x - self.x) + abs(y - self.y) < 18:
                continue
            small = random.randint(0, 9) < 7
            br = random.randint(16, 38) / 10.0 if small else random.randint(44, 76) / 10.0
            vx = random.randint(-10, 10) / 35.0
            vy = random.randint(-10, 10) / 35.0
            self.blobs.append([float(x), float(y), vx, vy, br])
        self.wells = []
        if self.level >= 2:
            self.wells.append([WIDTH // 2, PLAY_HEIGHT // 2, 0.018 + self.level * 0.002])
        if self.level >= 5:
            self.wells.append([random.randint(14, 50), random.randint(12, 44), -0.012])

    def _draw_circle(self, cx, cy, radius, col):
        # Fill by horizontal spans: one sqrt per row gives the exact half-width,
        # so we only touch disk pixels instead of testing the whole bounding box.
        icx = int(cx)
        icy = int(cy)
        r = int(radius)
        cr, cg, cb = col
        sp = set_pixel_clipped
        for dy in range(-r, r + 1):
            hw = int(math.sqrt(r * r - dy * dy))
            yy = icy + dy
            for xx in range(icx - hw, icx + hw + 1):
                sp(xx, yy, cr, cg, cb)

    def _aim_from_joystick(self, joystick):
        x, y = joystick.read_xy()
        dx = x - 128
        dy = y - 128
        # Dead zone: ignore tiny movements
        if dx * dx + dy * dy < 400:  # ~20 units radius
            return
        # y is inverted: high y = up = negative screen y
        self.aim = math.atan2(-dy, dx)

    def _thrust(self):
        now = ticks_ms()
        if ticks_diff(now, self.last_thrust) < 120 or self.r <= 2.8:
            return
        ax = math.cos(self.aim)
        ay = math.sin(self.aim)
        self.vx += ax * 0.34
        self.vy += ay * 0.34
        self.r = max(2.8, self.r - 0.18)
        bx = self.x - ax * (self.r + 2)
        by = self.y - ay * (self.r + 2)
        self.blobs.append([bx, by, -ax * 1.1 + self.vx * 0.25, -ay * 1.1 + self.vy * 0.25, 1.5])
        self.last_thrust = now

    def _apply_wells(self, obj):
        for wx, wy, strength in self.wells:
            dx = wx - obj[0]
            dy = wy - obj[1]
            d2 = max(36.0, dx * dx + dy * dy)
            force = strength / d2
            obj[2] += dx * force
            obj[3] += dy * force

    def _move_object(self, obj, radius):
        obj[0] += obj[2]
        obj[1] += obj[3]
        obj[2] *= 0.994
        obj[3] *= 0.994
        if obj[0] < radius:
            obj[0] = radius
            obj[2] = abs(obj[2]) * 0.75
        elif obj[0] > WIDTH - 1 - radius:
            obj[0] = WIDTH - 1 - radius
            obj[2] = -abs(obj[2]) * 0.75
        if obj[1] < radius:
            obj[1] = radius
            obj[3] = abs(obj[3]) * 0.75
        elif obj[1] > PLAY_HEIGHT - 1 - radius:
            obj[1] = PLAY_HEIGHT - 1 - radius
            obj[3] = -abs(obj[3]) * 0.75

    def _advance(self):
        player_obj = [self.x, self.y, self.vx, self.vy]
        self._apply_wells(player_obj)
        self._move_object(player_obj, self.r)
        self.x, self.y, self.vx, self.vy = player_obj
        for b in self.blobs:
            self._apply_wells(b)
            self._move_object(b, b[4])
        # Blob-blob absorption: larger blobs eat smaller ones
        alive = list(range(len(self.blobs)))
        eaten = set()
        for i in range(len(self.blobs)):
            if i in eaten:
                continue
            for j in range(i + 1, len(self.blobs)):
                if j in eaten:
                    continue
                bi = self.blobs[i]
                bj = self.blobs[j]
                dx = bi[0] - bj[0]
                dy = bi[1] - bj[1]
                if dx * dx + dy * dy <= (bi[4] + bj[4]) * (bi[4] + bj[4]):
                    if bi[4] >= bj[4] * 1.04:
                        bi[4] = math.sqrt(bi[4] * bi[4] + bj[4] * bj[4] * 0.55)
                        bi[2] = (bi[2] * 3 + bj[2]) / 4
                        bi[3] = (bi[3] * 3 + bj[3]) / 4
                        eaten.add(j)
                    elif bj[4] >= bi[4] * 1.04:
                        bj[4] = math.sqrt(bj[4] * bj[4] + bi[4] * bi[4] * 0.55)
                        bj[2] = (bj[2] * 3 + bi[2]) / 4
                        bj[3] = (bj[3] * 3 + bi[3]) / 4
                        eaten.add(i)
                        break
        self.blobs = [b for i, b in enumerate(self.blobs) if i not in eaten]
        # Player-blob collisions
        keep = []
        for b in self.blobs:
            dx = b[0] - self.x
            dy = b[1] - self.y
            touch = dx * dx + dy * dy <= (self.r + b[4]) * (self.r + b[4])
            if touch:
                if self.r >= b[4] * 1.04:
                    self.r = math.sqrt(self.r * self.r + b[4] * b[4] * 0.55)
                    self.score += max(1, int(b[4] * 4))
                    self.vx = (self.vx * 4 + b[2]) / 5
                    self.vy = (self.vy * 4 + b[3]) / 5
                    continue
                set_game_over_score(self.score)
                return False
            keep.append(b)
        self.blobs = keep
        if self.r >= self.target_r:
            self.score += 100 + self.level * 25
            self.level += 1
            self._new_level()
        return True

    def _draw(self):
        display.clear()
        for wx, wy, strength in self.wells:
            col = (130, 80, 255) if strength > 0 else (80, 220, 255)
            draw_rect_outline(wx - 4, wy - 4, wx + 4, wy + 4, col[0], col[1], col[2])
        for b in self.blobs:
            if b[4] < self.r:
                col = (70, 220, 160)
            else:
                col = (255, 80, 80)
            self._draw_circle(b[0], b[1], b[4], col)
        self._draw_circle(self.x, self.y, self.r, (80, 170, 255))
        ax = int(self.x + math.cos(self.aim) * (self.r + 5))
        ay = int(self.y + math.sin(self.aim) * (self.r + 5))
        draw_line(int(self.x), int(self.y), ax, ay, 255, 255, 255)
        need = max(1, int(self.target_r * 2))
        have = min(need, int(self.r * 2))
        draw_rectangle(1, 1, need, 2, 45, 45, 65)
        draw_rectangle(1, 1, have, 2, 80, 230, 255)
        draw_text_small(WIDTH - 14, 1, "L" + str(self.level), 170, 170, 170)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        self.reset()
        display_score_and_time(0, force=True)

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            self._aim_from_joystick(joystick)
            if z_button:
                self._thrust()
            if not self._advance():
                return False
            self._draw()
            return True

        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class GalaxyGame:
    """
    GALAXY
    Controls:
      - Directions: move cursor
      - Z: select own planet / send fleet
      - C: return to menu
    Capture planets by sending fleets across the star map.
    """
    FRAME_MS = 70

    def __init__(self):
        self.reset()

    def reset(self):
        self.score = 0
        self.level = 1
        self.cursor = 0
        self.selected = -1
        self.last_move = ticks_ms()
        self.last_z = False
        self.ai_next = ticks_ms() + 1300
        self.growth_tick = ticks_ms()
        self._new_map()

    def _new_map(self):
        self.planets = [
            [8, PLAY_HEIGHT // 2, 4, 0, 22, 2],
            [WIDTH - 9, PLAY_HEIGHT // 2, 4, 1, 20 + self.level * 2, 2],
        ]
        count = min(8, 3 + self.level)
        tries = 0
        while len(self.planets) < count + 2 and tries < 120:
            tries += 1
            x = random.randint(14, WIDTH - 15)
            y = random.randint(8, PLAY_HEIGHT - 9)
            ok = True
            for p in self.planets:
                if (p[0] - x) * (p[0] - x) + (p[1] - y) * (p[1] - y) < 120:
                    ok = False
                    break
            if ok:
                r = random.randint(2, 4)
                ships = random.randint(6, 18)
                grow = 1 if r < 4 else 2
                self.planets.append([x, y, r, -1, ships, grow])
        self.fleets = []
        self.cursor = 0
        self.selected = -1

    def _owner_color(self, owner):
        if owner == 0:
            return (80, 210, 255)
        if owner == 1:
            return (255, 80, 80)
        return (170, 170, 120)

    def _draw_circle(self, cx, cy, radius, col):
        # Fill by horizontal spans: one sqrt per row gives the exact half-width,
        # so we only touch disk pixels instead of testing the whole bounding box.
        icx = int(cx)
        icy = int(cy)
        r = int(radius)
        cr, cg, cb = col
        sp = set_pixel_clipped
        for dy in range(-r, r + 1):
            hw = int(math.sqrt(r * r - dy * dy))
            yy = icy + dy
            for xx in range(icx - hw, icx + hw + 1):
                sp(xx, yy, cr, cg, cb)

    def _move_cursor(self, joystick):
        now = ticks_ms()
        if ticks_diff(now, self.last_move) < 180:
            return
        x, y = joystick.read_xy()
        dx = x - 128
        dy = y - 128
        if dx * dx + dy * dy < 576:  # dead zone ~24 units
            return
        # Find nearest planet in the pushed direction (dot product scores)
        cur = self.planets[self.cursor]
        best_i = -1
        best_score = -1.0
        norm = math.sqrt(dx * dx + dy * dy)
        jx = dx / norm
        jy = -dy / norm  # screen y is inverted
        for i, p in enumerate(self.planets):
            if i == self.cursor:
                continue
            px = p[0] - cur[0]
            py = p[1] - cur[1]
            dist = math.sqrt(px * px + py * py)
            if dist < 1.0:
                continue
            dot = (px / dist) * jx + (py / dist) * jy
            # Weight: strong directional alignment beats proximity
            score = dot - dist * 0.012
            if dot > 0.35 and score > best_score:
                best_score = score
                best_i = i
        if best_i >= 0:
            self.cursor = best_i
            self.last_move = now

    def _send_fleet(self, src_i, dst_i, owner):
        if src_i == dst_i:
            return
        src = self.planets[src_i]
        dst = self.planets[dst_i]
        if src[3] != owner or src[4] < 4:
            return
        ships = max(2, src[4] // 2)
        src[4] -= ships
        dx = dst[0] - src[0]
        dy = dst[1] - src[1]
        dist = max(1.0, math.sqrt(dx * dx + dy * dy))
        speed = 1.45 if owner == 0 else 1.25 + self.level * 0.03
        self.fleets.append([float(src[0]), float(src[1]), dst_i, owner, ships, dx / dist * speed, dy / dist * speed])

    def _player_action(self):
        p = self.planets[self.cursor]
        if self.selected < 0:
            if p[3] == 0:
                self.selected = self.cursor
            return
        self._send_fleet(self.selected, self.cursor, 0)
        self.selected = -1

    def _ai_action(self):
        own = []
        targets = []
        for i, p in enumerate(self.planets):
            if p[3] == 1:
                own.append(i)
            else:
                targets.append(i)
        if not own or not targets:
            return
        src_i = own[0]
        for i in own:
            if self.planets[i][4] > self.planets[src_i][4]:
                src_i = i
        dst_i = targets[0]
        for i in targets:
            p = self.planets[i]
            d0 = abs(p[0] - self.planets[src_i][0]) + abs(p[1] - self.planets[src_i][1]) + p[4] * 2
            d1 = abs(self.planets[dst_i][0] - self.planets[src_i][0]) + abs(self.planets[dst_i][1] - self.planets[src_i][1]) + self.planets[dst_i][4] * 2
            if d0 < d1:
                dst_i = i
        self._send_fleet(src_i, dst_i, 1)

    def _grow_planets(self):
        now = ticks_ms()
        if ticks_diff(now, self.growth_tick) < 720:
            return
        self.growth_tick = now
        for p in self.planets:
            if p[3] >= 0:
                p[4] = min(99, p[4] + p[5])

    def _arrive(self, fleet):
        p = self.planets[fleet[2]]
        ships = int(fleet[4])
        if p[3] == fleet[3]:
            p[4] = min(99, p[4] + ships)
            return
        p[4] -= ships
        if p[4] < 0:
            p[3] = fleet[3]
            p[4] = min(99, -p[4])
            if fleet[3] == 0:
                self.score += 35 + p[2] * 5

    def _advance_fleets(self):
        keep = []
        for f in self.fleets:
            dst = self.planets[f[2]]
            f[0] += f[5]
            f[1] += f[6]
            dx = dst[0] - f[0]
            dy = dst[1] - f[1]
            if dx * dx + dy * dy <= (dst[2] + 1) * (dst[2] + 1):
                self._arrive(f)
            else:
                keep.append(f)
        self.fleets = keep

    def _owned_or_fleet(self, owner):
        for p in self.planets:
            if p[3] == owner:
                return True
        for f in self.fleets:
            if f[3] == owner:
                return True
        return False

    def _check_end(self):
        if not self._owned_or_fleet(1):
            self.score += 150 + self.level * 40
            self.level += 1
            self._new_map()
            return True
        if not self._owned_or_fleet(0):
            set_game_over_score(self.score)
            return False
        return True

    def _draw(self):
        display.clear()
        for f in self.fleets:
            col = self._owner_color(f[3])
            display.set_pixel(int(f[0]), int(f[1]), col[0], col[1], col[2])
            if f[4] >= 10:
                display.set_pixel(int(f[0]) - 1, int(f[1]), col[0], col[1], col[2])
        for i, p in enumerate(self.planets):
            col = self._owner_color(p[3])
            self._draw_circle(p[0], p[1], p[2], col)
            if i == self.selected:
                draw_rect_outline(p[0] - p[2] - 2, p[1] - p[2] - 2,
                                  p[0] + p[2] + 2, p[1] + p[2] + 2, 255, 255, 255)
            if i == self.cursor:
                draw_rect_outline(p[0] - p[2] - 4, p[1] - p[2] - 4,
                                  p[0] + p[2] + 4, p[1] + p[2] + 4, 255, 230, 70)
            txt = str(min(99, p[4]))
            draw_text_small(p[0] - len(txt) * 3, p[1] + p[2] + 1, txt, 230, 230, 230)
        draw_text_small(1, 1, "L" + str(self.level), 170, 170, 170)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        self.reset()
        display_score_and_time(0, force=True)

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            self._move_cursor(joystick)
            if z_button and not self.last_z:
                self._player_action()
            self.last_z = z_button
            now = ticks_ms()
            if ticks_diff(now, self.ai_next) >= 0:
                self._ai_action()
                self.ai_next = now + max(650, 1700 - self.level * 85)
            self._grow_planets()
            self._advance_fleets()
            if not self._check_end():
                return False
            self._draw()
            return True

        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class OrbitalGame:
    """
    ORBTAL
    Controls:
      - Left / Right: aim launcher
      - Z: fire; MULTI option allows several active shots
      - C: return to menu
    Bounce shots through numbered circles. Every circle starts at 3, counts down
    on each touch, and bursts at 0.
    """
    FRAME_MS = 35
    CANNON_X = WIDTH // 2
    CANNON_Y = PLAY_HEIGHT - 2
    MAX_MULTI_SHOTS = 4

    def __init__(self, ctx=None):
        self.gravity_enabled = bool(get_context_setting(ctx, "gravity", False))
        self.multi_shot_enabled = bool(get_context_setting(ctx, "multi_shot", False))
        self.reset()

    def reset(self):
        self.score = 0
        self.level = 1
        self.aim = 90
        self.last_move = ticks_ms()
        self.last_z = False
        self.shot = None
        self.shots = []
        self.circles = []
        self.bursts = []
        self.safe_until = 0
        self._seed_level()

    def _seed_level(self):
        self.circles = []
        count = min(8, 2 + self.level)
        tries = 0
        while len(self.circles) < count and tries < 120:
            tries += 1
            r = random.randint(4, 7)
            x = random.randint(r + 1, WIDTH - r - 2)
            y = random.randint(r + 4, PLAY_HEIGHT - 18)
            if abs(x - self.CANNON_X) < 10 and y > PLAY_HEIGHT - 26:
                continue
            ok = True
            for c in self.circles:
                dx = c[0] - x
                dy = c[1] - y
                if dx * dx + dy * dy < (c[2] + r + 4) * (c[2] + r + 4):
                    ok = False
                    break
            if ok:
                self.circles.append([float(x), float(y), float(r), 3, 0])

    def _draw_circle_outline(self, cx, cy, radius, col):
        # Midpoint circle: traces only the ~8r boundary pixels instead of
        # scanning the full (2r+1)^2 bounding box, a big win with up to 8
        # circles redrawn every frame on the LED matrix.
        icx = int(cx)
        icy = int(cy)
        r = int(radius)
        cr, cg, cb = col
        sp = set_pixel_clipped
        if r < 1:
            sp(icx, icy, cr, cg, cb)
            return
        x = r
        y = 0
        err = 1 - r
        while x >= y:
            sp(icx + x, icy + y, cr, cg, cb)
            sp(icx - x, icy + y, cr, cg, cb)
            sp(icx + x, icy - y, cr, cg, cb)
            sp(icx - x, icy - y, cr, cg, cb)
            sp(icx + y, icy + x, cr, cg, cb)
            sp(icx - y, icy + x, cr, cg, cb)
            sp(icx + y, icy - x, cr, cg, cb)
            sp(icx - y, icy - x, cr, cg, cb)
            y += 1
            if err < 0:
                err += 2 * y + 1
            else:
                x -= 1
                err += 2 * (y - x) + 1

    def _move_aim(self, joystick):
        now = ticks_ms()
        if ticks_diff(now, self.last_move) < 55:
            return
        d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT], debounce=False)
        if d == JOYSTICK_LEFT:
            self.aim = min(165, self.aim + 3)
            self.last_move = now
        elif d == JOYSTICK_RIGHT:
            self.aim = max(15, self.aim - 3)
            self.last_move = now

    def _fire(self):
        if self.shots and not self.multi_shot_enabled:
            return
        if len(self.shots) >= self.MAX_MULTI_SHOTS:
            return
        rad = math.radians(self.aim)
        speed = 3.0
        # shot: [x, y, vx, vy, age, last_circle, grow_r]
        shot = [
            float(self.CANNON_X),
            float(self.CANNON_Y - 2),
            math.cos(rad) * speed,
            -math.sin(rad) * speed,
            0,
            -1,
            0.0,
        ]
        self.shots.append(shot)
        self.shot = shot

    def _burst(self, x, y, col):
        for _ in range(8):
            self.bursts.append([float(x), float(y),
                                random.randint(-12, 12) / 10.0,
                                random.randint(-12, 12) / 10.0,
                                14 + random.randint(0, 10), col])

    def _bounce_circle(self, circle):
        sx, sy, vx, vy, age, _last = self.shot[:6]
        dx = sx - circle[0]
        dy = sy - circle[1]
        dist = max(0.1, math.sqrt(dx * dx + dy * dy))
        nx = dx / dist
        ny = dy / dist
        dot = vx * nx + vy * ny
        vx = vx - 2 * dot * nx
        vy = vy - 2 * dot * ny
        self.shot[0] = circle[0] + nx * (circle[2] + 2.0)
        self.shot[1] = circle[1] + ny * (circle[2] + 2.0)
        self.shot[2] = vx * 0.985
        self.shot[3] = vy * 0.985

    def _max_grow_radius(self, x, y):
        # Largest radius whose outline still clears the side/top walls, the
        # cannon line, and every existing circle (with a small gap so rings
        # never visually touch). Bounded so a settled circle stays sensible.
        # Keep clear of the cannon line so a freshly settled circle never
        # immediately trips the crowding check below it.
        m = min(x - 1.0, (WIDTH - 2.0) - x, y - 1.0, self.CANNON_Y - y - 3.0)
        for c in self.circles:
            dx = x - c[0]
            dy = y - c[1]
            gap = math.sqrt(dx * dx + dy * dy) - c[2] - 1.0
            if gap < m:
                m = gap
        return clamp(m, 2.0, 12.0)

    def _settle_shot(self, radius=None):
        if self.shot is None:
            return
        if radius is None:
            radius = self._max_grow_radius(self.shot[0], self.shot[1])
        r = max(2.0, float(radius))
        self.circles.append([self.shot[0], self.shot[1], r, 3, 18])
        try:
            self.shots.remove(self.shot)
        except ValueError:
            pass
        self.shot = self.shots[0] if self.shots else None
        self.safe_until = ticks_ms() + 300

    def _apply_shot_gravity(self, shot):
        if not self.gravity_enabled:
            return
        sx = shot[0]
        sy = shot[1]
        for c in self.circles:
            dx = c[0] - sx
            dy = c[1] - sy
            dist2 = dx * dx + dy * dy
            if dist2 < 9.0:
                continue
            dist = math.sqrt(dist2)
            pull = (c[2] * 0.45) / dist2
            if pull > 0.055:
                pull = 0.055
            shot[2] += (dx / dist) * pull
            shot[3] += (dy / dist) * pull

    def _advance_one_shot(self):
        if self.shot is None:
            return True
        self.shot[4] += 1
        # Check: if shot crosses below CANNON_Y line → game over
        if self.shot[1] >= self.CANNON_Y:
            set_game_over_score(self.score)
            return False
        speed2 = self.shot[2] * self.shot[2] + self.shot[3] * self.shot[3]
        # Growing phase: shot has slowed to near-stop, expand to fill the gap.
        if self.shot[6] > 0 or speed2 < 0.15:
            max_r = self._max_grow_radius(self.shot[0], self.shot[1])
            if self.shot[6] <= 0:
                self.shot[6] = 0.5
            # Grow as large as possible without touching a wall or another
            # circle, then lock that radius in.
            self.shot[6] = min(self.shot[6] + 0.3, max_r)
            if self.shot[6] >= max_r - 0.05:
                self._settle_shot(max_r)
            return True
        # Normal movement with deceleration (stronger friction than before)
        self._apply_shot_gravity(self.shot)
        self.shot[0] += self.shot[2]
        self.shot[1] += self.shot[3]
        self.shot[2] *= 0.964
        self.shot[3] *= 0.964
        if self.shot[0] <= 1:
            self.shot[0] = 1
            self.shot[2] = abs(self.shot[2])
        elif self.shot[0] >= WIDTH - 2:
            self.shot[0] = WIDTH - 2
            self.shot[2] = -abs(self.shot[2])
        if self.shot[1] <= 1:
            self.shot[1] = 1
            self.shot[3] = abs(self.shot[3])
        for i, c in enumerate(list(self.circles)):
            if self.shot is None:
                return True
            if self.shot[5] == i and c[4] > 0:
                continue
            dx = self.shot[0] - c[0]
            dy = self.shot[1] - c[1]
            if dx * dx + dy * dy <= (c[2] + 1.5) * (c[2] + 1.5):
                c[3] -= 1
                c[4] = 7
                self.shot[5] = i
                self.score += 7
                self._bounce_circle(c)
                if c[3] <= 0:
                    self.score += 30 + int(c[2]) * 4
                    self._burst(c[0], c[1], (255, 220, 70))
                    try:
                        self.circles.remove(c)
                    except ValueError:
                        pass
                break
        return True

    def _advance_shot(self):
        if not self.shots:
            self.shot = None
            return True
        for shot in list(self.shots):
            self.shot = shot
            if not self._advance_one_shot():
                return False
        self.shot = self.shots[0] if self.shots else None
        return True

    def _advance_cooldowns(self):
        for c in self.circles:
            if c[4] > 0:
                c[4] -= 1
        keep = []
        for b in self.bursts:
            b[0] += b[2]
            b[1] += b[3]
            b[3] += 0.08
            b[4] -= 1
            if b[4] > 0:
                keep.append(b)
        self.bursts = keep

    def _check_pressure(self):
        now = ticks_ms()
        if ticks_diff(now, self.safe_until) < 0:
            return True
        for c in self.circles:
            if c[1] + c[2] >= self.CANNON_Y - 2 and abs(c[0] - self.CANNON_X) < c[2] + 5:
                set_game_over_score(self.score)
                return False
        if not self.circles and not self.shots:
            self.score += 100 + self.level * 20
            self.level += 1
            self._seed_level()
        return True

    def _draw(self):
        display.clear()
        draw_rectangle(0, self.CANNON_Y + 1, WIDTH - 1, PLAY_HEIGHT - 1, 24, 24, 32)
        for c in self.circles:
            col = (255, 90, 90) if c[3] == 1 else ((255, 190, 70) if c[3] == 2 else (80, 190, 255))
            self._draw_circle_outline(c[0], c[1], c[2], col)
            draw_text_small(int(c[0]) - 2, int(c[1]) - 3, str(c[3]), 255, 255, 255)
        for b in self.bursts:
            col = b[5]
            display.set_pixel(int(b[0]), int(b[1]), col[0], col[1], col[2])
        for shot in self.shots:
            if shot[6] > 0:
                # Growing phase: draw as expanding circle outline
                self._draw_circle_outline(shot[0], shot[1], shot[6], (180, 255, 180))
            else:
                draw_rectangle(int(shot[0]) - 1, int(shot[1]) - 1,
                               int(shot[0]) + 1, int(shot[1]) + 1,
                               255, 255, 255)
        rad = math.radians(self.aim)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        ax = self.CANNON_X + int(cos_a * 9)
        ay = self.CANNON_Y - int(sin_a * 9)
        draw_line(self.CANNON_X, self.CANNON_Y, ax, ay, 255, 255, 120)
        # When idle, extend a dotted guide so the launch direction is readable.
        if self.multi_shot_enabled or not self.shots:
            for dist in (13, 17, 21, 25):
                gx = self.CANNON_X + int(cos_a * dist)
                gy = self.CANNON_Y - int(sin_a * dist)
                set_pixel_clipped(gx, gy, 120, 120, 60)
        draw_rectangle(self.CANNON_X - 2, self.CANNON_Y - 1,
                       self.CANNON_X + 2, self.CANNON_Y + 1, 150, 150, 170)
        draw_text_small(1, 1, "L" + str(self.level), 170, 170, 170)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        self.reset()
        display_score_and_time(0, force=True)

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            self._move_aim(joystick)
            if z_button and not self.last_z:
                self._fire()
            self.last_z = z_button
            if not self._advance_shot():
                return False
            self._advance_cooldowns()
            if not self._check_pressure():
                return False
            self._draw()
            return True

        return step

    def main_loop(self, joystick):
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class ColumnsGame:
    """
    COLMNS
    Controls:
      - Left / Right: move the falling column
      - Up: cycle the three colors
      - Down: soft drop; Z: hard drop
      - C: return to menu
    Sega-style Columns: a vertical triple of colored gems falls into a well.
    Line up three or more of one color in any direction (including diagonals)
    to clear them; cleared gems feed chains for bonus points. The run ends when
    the stack reaches the top.
    """
    FRAME_MS = 33
    COLS = 7
    ROWS = 13
    CELL = 4
    NCOLORS = 5
    OX = (WIDTH - COLS * CELL) // 2
    OY = 4
    PALETTE = (
        (0, 0, 0),
        (230, 60, 60),
        (60, 200, 90),
        (70, 120, 255),
        (235, 205, 55),
        (210, 80, 220),
    )

    def __init__(self):
        self.reset()

    def reset(self):
        self.grid = [0] * (self.COLS * self.ROWS)
        self.score = 0
        self.level = 1
        self.cleared = 0
        self.col = self.COLS // 2
        self.y = 0
        self.colors = self._rand_colors()
        self.fall_interval = 520
        self.last_fall = ticks_ms()
        self.last_move = ticks_ms()
        self.last_cycle = ticks_ms()
        self.last_z = False
        self._spawn()

    def _rand_colors(self):
        return [random.randint(1, self.NCOLORS) for _ in range(3)]

    def _idx(self, x, y):
        return y * self.COLS + x

    def _spawn(self):
        self.col = self.COLS // 2
        self.y = 0
        self.colors = self._rand_colors()
        # No room for the new column means the stack reached the top.
        for dy in range(3):
            if self.grid[self._idx(self.col, dy)]:
                set_game_over_score(self.score)
                return False
        return True

    def _cells_free(self, col, top_y):
        for dy in range(3):
            yy = top_y + dy
            if yy < 0:
                continue
            if yy >= self.ROWS or self.grid[self._idx(col, yy)]:
                return False
        return True

    def _move(self, dx):
        nc = self.col + dx
        if 0 <= nc < self.COLS and self._cells_free(nc, self.y):
            self.col = nc

    def _cycle(self):
        # Rotate so the bottom gem wraps to the top (classic Columns shuffle).
        self.colors = [self.colors[2], self.colors[0], self.colors[1]]

    def _can_fall(self):
        bottom = self.y + 2
        return bottom + 1 < self.ROWS and not self.grid[self._idx(self.col, bottom + 1)]

    def _fall_step(self):
        if self._can_fall():
            self.y += 1
        else:
            self._lock()

    def _hard_drop(self):
        while self._can_fall():
            self.y += 1
        self._lock()

    def _lock(self):
        for dy in range(3):
            self.grid[self._idx(self.col, self.y + dy)] = self.colors[dy]
        self._resolve()
        self._spawn()
        self.last_fall = ticks_ms()

    def _find_matches(self):
        marks = set()
        g = self.grid
        for y in range(self.ROWS):
            for x in range(self.COLS):
                c = g[self._idx(x, y)]
                if not c:
                    continue
                for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
                    # Only start a run when the previous cell breaks it, so each
                    # line is counted once.
                    px, py = x - dx, y - dy
                    if 0 <= px < self.COLS and 0 <= py < self.ROWS and g[self._idx(px, py)] == c:
                        continue
                    run = [(x, y)]
                    nx, ny = x + dx, y + dy
                    while 0 <= nx < self.COLS and 0 <= ny < self.ROWS and g[self._idx(nx, ny)] == c:
                        run.append((nx, ny))
                        nx += dx
                        ny += dy
                    if len(run) >= 3:
                        marks.update(run)
        return marks

    def _apply_gravity(self):
        for x in range(self.COLS):
            stack = [self.grid[self._idx(x, y)] for y in range(self.ROWS) if self.grid[self._idx(x, y)]]
            pad = self.ROWS - len(stack)
            for y in range(self.ROWS):
                self.grid[self._idx(x, y)] = 0 if y < pad else stack[y - pad]

    def _resolve(self):
        chain = 0
        while True:
            marks = self._find_matches()
            if not marks:
                break
            chain += 1
            for x, y in marks:
                self.grid[self._idx(x, y)] = 0
            self.score += len(marks) * 10 * chain
            self.cleared += len(marks)
            self._apply_gravity()
        # Speed up roughly every 25 cleared gems.
        new_level = 1 + self.cleared // 25
        if new_level != self.level:
            self.level = new_level
            self.fall_interval = max(140, 520 - (self.level - 1) * 45)

    def _draw_cell(self, x, y, color):
        px = self.OX + x * self.CELL
        py = self.OY + y * self.CELL
        r, g, b = self.PALETTE[color]
        draw_rectangle(px, py, px + self.CELL - 2, py + self.CELL - 2, r, g, b)

    def _draw(self):
        display.clear()
        draw_rect_outline(self.OX - 1, self.OY - 1,
                          self.OX + self.COLS * self.CELL,
                          self.OY + self.ROWS * self.CELL, 60, 60, 90)
        for y in range(self.ROWS):
            for x in range(self.COLS):
                c = self.grid[self._idx(x, y)]
                if c:
                    self._draw_cell(x, y, c)
        for dy in range(3):
            self._draw_cell(self.col, self.y + dy, self.colors[dy])
        draw_text_small(1, 1, "L" + str(self.level), 170, 170, 170)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        self.reset()
        display_score_and_time(0, force=True)

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            if game_over:
                return False
            now = ticks_ms()
            d = joystick.read_direction(
                [JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_UP, JOYSTICK_DOWN], debounce=False)
            if d in (JOYSTICK_LEFT, JOYSTICK_RIGHT) and ticks_diff(now, self.last_move) >= 110:
                self._move(-1 if d == JOYSTICK_LEFT else 1)
                self.last_move = now
            elif d == JOYSTICK_UP and ticks_diff(now, self.last_cycle) >= 150:
                self._cycle()
                self.last_cycle = now
            if z_button and not self.last_z:
                self._hard_drop()
            self.last_z = z_button
            if game_over:
                return False
            interval = self.fall_interval // 5 if d == JOYSTICK_DOWN else self.fall_interval
            if ticks_diff(now, self.last_fall) >= interval:
                self._fall_step()
                self.last_fall = now
            if game_over:
                return False
            self._draw()
            return True

        return step

    def main_loop(self, joystick):
        begin_game(0)
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        begin_game(0)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))


class GameOverMenu:
    """Unified end-of-run menu with retry, highscore view, and menu return."""
    def __init__(self, joystick, score, best, best_name="---", title="LOST",
                 highscores=None, game_name=None):
        self.joystick = joystick
        self.score = int(score or 0)
        self.best = int(best or 0)
        self.best_name = best_name if isinstance(best_name, str) else "---"
        self.title = title
        self.highscores = highscores
        self.game_name = game_name
        self.opts = ("RETRY", "HISCR", "MENU")
        self.hs_top = 0

    def _title_color(self):
        if self.title == "WON":
            return (50, 255, 80)
        return (255, 55, 45)

    def _draw_button(self, x, y, label, selected):
        col = (255, 255, 255) if selected else (95, 95, 95)
        bg = (28, 70, 34) if selected and self.title == "WON" else (70, 28, 28) if selected else (0, 0, 0)
        w = len(label) * 6 + 5
        draw_rectangle(x - 2, y - 2, x + w - 1, y + 7, *bg)
        draw_rect_outline(x - 2, y - 2, x + w - 1, y + 7, *col)
        draw_text_small(x, y, label, *col)

    def _draw_menu(self, idx):
        display.clear()
        tr, tg, tb = self._title_color()
        draw_text((WIDTH - len(self.title) * 9) // 2, 2, self.title, tr, tg, tb)
        draw_text_small(2, 16, "SCORE", 170, 170, 170)
        draw_text_small(39, 16, str(self.score)[:4], 255, 255, 255)
        draw_text_small(2, 24, "BEST", 170, 170, 170)
        best_txt = (str(self.best) + " " + self.best_name)[:8]
        draw_text_small(32, 24, best_txt, 255, 220, 80)
        self._draw_button(14, 31, "RETRY", idx == 0)
        self._draw_button(14, 40, "HISCR", idx == 1)
        self._draw_button(17, 49, "MENU", idx == 2)
        draw_rectangle(0, PLAY_HEIGHT, WIDTH - 1, HEIGHT - 1, 0, 0, 0)
        draw_text_small(1, PLAY_HEIGHT, "Z OK", 120, 120, 120)
        draw_text_small(WIDTH - 36, PLAY_HEIGHT, "C MENU", 120, 120, 120)
        display_flush()

    def _highscore_entries(self):
        if self.highscores is None:
            if self.game_name:
                return [(self.game_name, self.best, self.best_name)] if self.best > 0 else []
            return []
        return self.highscores.entries(self.game_name)

    def _draw_highscores(self, top=0):
        display.clear()
        rows = self._highscore_entries()
        title = ("HISCR " + str(self.game_name or ""))[:10]
        draw_text_small(2, 1, title, 255, 220, 80)
        if not rows:
            draw_text_small(8, 25, "NO SCORE", 140, 140, 140)
        max_top = max(0, len(rows) - 5)
        top = clamp(top, 0, max_top)
        for i, row in enumerate(rows[top:top + 5]):
            game, score, name = row
            y = 11 + i * 9
            rank = str(top + i + 1)
            col = (255, 255, 255)
            draw_text_small(1, y, rank, *col)
            name_x = 8 if len(rank) == 1 else 14
            draw_text_small(name_x, y, str(name or "---")[:3], 120, 180, 255)
            score_txt = str(score)[-6:]
            draw_text_small(WIDTH - len(score_txt) * 6 - 1, y, score_txt, *col)
        draw_menu_scrollbar(top, 5, len(rows))
        draw_rectangle(0, PLAY_HEIGHT, WIDTH - 1, HEIGHT - 1, 0, 0, 0)
        draw_text_small(1, PLAY_HEIGHT, "Z BACK", 120, 120, 120)
        draw_text_small(WIDTH - 36, PLAY_HEIGHT, "C MENU", 120, 120, 120)
        display_flush()

    def run(self):
        _wait_for_primary_release(self.joystick, timeout_ms=2000)
        idx = 0
        prev = -1
        last_move = ticks_ms()
        move_delay = 130

        while True:
            now = ticks_ms()
            if idx != prev:
                prev = idx
                self._draw_menu(idx)

            if ticks_diff(now, last_move) > move_delay:
                d = self.joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT], debounce=True)
                if d in (JOYSTICK_UP, JOYSTICK_LEFT):
                    idx = (idx - 1) % len(self.opts)
                    last_move = now
                elif d in (JOYSTICK_DOWN, JOYSTICK_RIGHT):
                    idx = (idx + 1) % len(self.opts)
                    last_move = now

            c_button, z_button = self.joystick.read_buttons()
            if c_button:
                _wait_for_primary_release(self.joystick)
                return "MENU"
            if z_button:
                _wait_for_primary_release(self.joystick)
                selected = self.opts[idx]
                if selected == "HISCR":
                    result = self._show_highscores_sync()
                    if result == "MENU":
                        return "MENU"
                    prev = -1
                else:
                    return selected

            sleep_ms(16)

    def _show_highscores_sync(self):
        self.hs_top = 0
        prev_top = -1
        last_move = ticks_ms()
        move_delay = 130
        while True:
            if self.hs_top != prev_top:
                prev_top = self.hs_top
                self._draw_highscores(self.hs_top)
            now = ticks_ms()
            if ticks_diff(now, last_move) > move_delay:
                d = self.joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN], debounce=True)
                rows = self._highscore_entries()
                max_top = max(0, len(rows) - 5)
                if d == JOYSTICK_UP and self.hs_top > 0:
                    self.hs_top -= 1
                    last_move = now
                elif d == JOYSTICK_DOWN and self.hs_top < max_top:
                    self.hs_top += 1
                    last_move = now
            c_button, z_button = self.joystick.read_buttons()
            if c_button:
                _wait_for_primary_release(self.joystick)
                return "MENU"
            if z_button:
                _wait_for_primary_release(self.joystick)
                return "BACK"
            sleep_ms(16)

    async def run_async(self):
        """Async version of run() for use in pygbag/browser environments."""
        if asyncio is None:
            return self.run()
        await _wait_for_primary_release_async(self.joystick, timeout_ms=2000)
        idx = 0
        prev = -1
        last_move = ticks_ms()
        move_delay = 130
        while True:
            now = ticks_ms()
            if idx != prev:
                prev = idx
                self._draw_menu(idx)

            if ticks_diff(now, last_move) > move_delay:
                d = self.joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT], debounce=True)
                if d in (JOYSTICK_UP, JOYSTICK_LEFT):
                    idx = (idx - 1) % len(self.opts)
                    last_move = now
                elif d in (JOYSTICK_DOWN, JOYSTICK_RIGHT):
                    idx = (idx + 1) % len(self.opts)
                    last_move = now

            c_button, z_button = self.joystick.read_buttons()
            if c_button:
                await _wait_for_primary_release_async(self.joystick)
                return "MENU"
            if z_button:
                await _wait_for_primary_release_async(self.joystick)
                selected = self.opts[idx]
                if selected == "HISCR":
                    result = await self._show_highscores_async()
                    if result == "MENU":
                        return "MENU"
                    prev = -1
                else:
                    return selected

            await asyncio.sleep(0.016)

    async def _show_highscores_async(self):
        self.hs_top = 0
        prev_top = -1
        last_move = ticks_ms()
        move_delay = 130
        while True:
            if self.hs_top != prev_top:
                prev_top = self.hs_top
                self._draw_highscores(self.hs_top)
            now = ticks_ms()
            if ticks_diff(now, last_move) > move_delay:
                d = self.joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN], debounce=True)
                rows = self._highscore_entries()
                max_top = max(0, len(rows) - 5)
                if d == JOYSTICK_UP and self.hs_top > 0:
                    self.hs_top -= 1
                    last_move = now
                elif d == JOYSTICK_DOWN and self.hs_top < max_top:
                    self.hs_top += 1
                    last_move = now
            c_button, z_button = self.joystick.read_buttons()
            if c_button:
                await _wait_for_primary_release_async(self.joystick)
                return "MENU"
            if z_button:
                await _wait_for_primary_release_async(self.joystick)
                return "BACK"
            await asyncio.sleep(0.016)


def draw_menu_scrollbar(top, view, total):
    """Draw the shared vertical scrollbar used by game and settings lists."""
    if total <= 0:
        return
    track_x = WIDTH - 1
    track_y = 2
    track_h = PLAY_HEIGHT - 4
    draw_line(track_x, track_y, track_x, track_y + track_h - 1, 35, 35, 35)
    if total <= view:
        draw_rectangle(track_x - 1, track_y, track_x, track_y + track_h - 1, 160, 160, 160)
        return
    thumb_h = max(4, int(track_h * view / total))
    thumb_h = min(track_h, thumb_h)
    max_top = max(1, total - view)
    thumb_y = track_y + int((track_h - thumb_h) * top / max_top)
    draw_rectangle(track_x - 1, thumb_y, track_x, thumb_y + thumb_h - 1, 220, 220, 220)


class GameSettingsMenu:
    """Small shared option editor for games that declare GameSettings entries."""

    def __init__(self, joystick, game_name, settings):
        self.joystick = joystick
        self.game_name = game_name
        self.settings = settings

    def _draw(self, idx):
        opts = self.settings.definitions_for(self.game_name)
        display.clear()
        draw_text(1, 1, self.game_name[:6], 120, 180, 255)
        # Keep the bottom HUD band free for button hints; option rows stay above it.
        view = 4
        top = 0
        if len(opts) > view:
            top = idx - view + 1
            if top < 0:
                top = 0
            max_top = len(opts) - view
            if top > max_top:
                top = max_top
        for row in range(view):
            opt_i = top + row
            if opt_i >= len(opts):
                break
            opt = opts[opt_i]
            y = 15 + row * 10
            col = (255, 255, 255) if opt_i == idx else (110, 110, 110)
            label = opt[1]
            choice_i = self.settings.choice_index(self.game_name, opt_i)
            choice_label = str(opt[2][choice_i][1])
            draw_text_small(2, y, label[:5], *col)
            val_x = max(31, WIDTH - len(choice_label) * 6 - 2)
            draw_text_small(val_x, y, choice_label, *col)
        draw_menu_scrollbar(top, view, len(opts))
        draw_text_small(1, PLAY_HEIGHT, "Z+", 120, 120, 120)
        draw_text_small(WIDTH - 36, PLAY_HEIGHT, "C BACK", 120, 120, 120)
        display_flush()

    async def run_async(self):
        opts = self.settings.definitions_for(self.game_name)
        if not opts:
            return
        idx = 0
        prev_idx = -1
        prev_values = None
        last_move = ticks_ms()
        move_delay = 135

        while True:
            values = tuple(self.settings.choice_index(self.game_name, i) for i in range(len(opts)))
            if idx != prev_idx or values != prev_values:
                prev_idx = idx
                prev_values = values
                self._draw(idx)

            now = ticks_ms()
            if ticks_diff(now, last_move) > move_delay:
                d = self.joystick.read_direction(
                    [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT],
                    debounce=True
                )
                if d == JOYSTICK_UP and idx > 0:
                    idx -= 1
                    last_move = now
                elif d == JOYSTICK_DOWN and idx < len(opts) - 1:
                    idx += 1
                    last_move = now
                elif d == JOYSTICK_LEFT:
                    self.settings.cycle(self.game_name, idx, -1)
                    last_move = now
                elif d == JOYSTICK_RIGHT:
                    self.settings.cycle(self.game_name, idx, 1)
                    last_move = now

            c_button, z_button = self.joystick.read_buttons()
            if c_button:
                await _wait_for_primary_release_async(self.joystick)
                return
            if z_button:
                self.settings.cycle(self.game_name, idx, 1)
                await _wait_for_primary_release_async(self.joystick)

            await yield_runtime(0.016)
            if asyncio is None:
                sleep_ms(16)

class GameSelect:
    """Main game selector menu; choose a game to play with joystick."""
    # Tuple shape: (menu_id, game_class, flags). GAME_FLAG_HEAVY entries can be
    # hidden by runtime configuration for constrained targets.
    GAME_REGISTRY = (
        ("DEMOS", DemosGame, 0),
        ("2048", Game2048, GAME_FLAG_HEAVY),
        ("AIRHKY", AirHockeyGame, 0),
        ("ARENA", ArenaGame, 0),
        ("ARTILL", ArtilleryGame, 0),
        ("ASTRD", AsteroidGame, GAME_FLAG_HEAVY),
        ("BEJWL", BejeweledGame, GAME_FLAG_HEAVY),
        ("BILLI", BilliardsGame, 0),
        ("BOMBER", BomberGame, 0),
        ("BRKOUT", BreakoutGame, 0),
        ("BTLZON", BattlezoneGame, 0),
        ("CAVEFL", CaveFlyGame, 0),
        ("CENTI", CentipedeGame, 0),
        ("CGOLG", CgolgGame, 0),
        ("CITY", CityChaseGame, 0),
        ("CLIMB", ClimberGame, 0),
        ("COLMNS", ColumnsGame, 0),
        ("DEFUSE", DefuseGame, 0),
        ("DODGE", DodgeGame, 0),
        ("DOOMLT", DoomLiteGame, GAME_FLAG_HEAVY),
        ("FLAPPY", FlappyGame, 0),
        ("FROGGR", FroggerGame, 0),
        ("GALAXY", GalaxyGame, 0),
        ("GOLF", GolfGame, 0),
        ("INVADR", InvaderGame, 0),
        ("KEEN", KeenGame, 0),
        ("KERBAL", KerbalGame, GAME_FLAG_HEAVY),
        ("LANDER", LunarLanderGame, GAME_FLAG_HEAVY),
        ("LASER", LaserGame, 0),
        ("LOCO", LocoMotionGame, GAME_FLAG_HEAVY),
        ("MAZE", MazeGame, GAME_FLAG_HEAVY),
        ("MINES", MinesGame, 0),
        ("ORBIT", OrbitGame, 0),
        ("ORBTAL", OrbitalGame, 0),
        ("PACMAN", PacmanGame, 0),
        ("PAIRS", PairsGame, 0),
        ("PINBAL", PinballGame, 0),
        ("PITFAL", PitfallGame, 0),
        ("PONG", PongGame, 0),
        ("QIX", QixGame, GAME_FLAG_HEAVY),
        ("RACING", TopDownRacerGame, 0),
        ("RAYRCR", RayRacerGame, GAME_FLAG_HEAVY),
        ("REVRS", OthelloGame, GAME_FLAG_HEAVY),
        ("RTYPE", RTypeGame, GAME_FLAG_HEAVY),
        ("SABOTR", SabotrGame, 0),
        ("SIMON", SimonGame, 0),
        ("SNAKE", SnakeGame, 0),
        ("SOCCER", SoccerGame, 0),
        ("SOKO", SokobanGame, GAME_FLAG_HEAVY),
        ("STACK", StackerGame, 0),
        ("STKARC", StickArcherGame, 0),
        ("TETRIS", TetrisGame, GAME_FLAG_HEAVY),
        ("TRON", TronGame, 0),
        ("TWRDEF", TowerDefenseGame, 0),
        ("UFODEF", UFODefenseGame, GAME_FLAG_HEAVY),
        ("WORMS", WormsGame, 0),
    )

    def __init__(self):
        refresh_runtime_config()
        self.joystick = Joystick()
        self.highscores = HighScores()
        self.settings = GameSettings()
        self.game_registry = tuple(
            g for g in self.GAME_REGISTRY
            if (CONFIG_ENABLE_HEAVY_GAMES or not (g[2] & GAME_FLAG_HEAVY))
            and _name_enabled(g[0], CONFIG_ENABLED_GAMES, CONFIG_DISABLED_GAMES)
        )
        self.sorted_games = tuple(g[0] for g in self.game_registry)
        self.selected = 0
        self.top = 0

    def _game_class(self, name):
        for game_name, cls, _flags in self.game_registry:
            if game_name == name:
                return cls
        return None

    def _make_game_instance(self, game_name, game_cls):
        ctx = {"game_name": game_name, "settings": self.settings.snapshot(game_name)}
        init_code = getattr(getattr(game_cls, "__init__", None), "__code__", None)
        # Older games still have __init__(self). Newer games accept ctx so they can
        # use the shared settings system without forcing every class to change.
        if init_code is not None and getattr(init_code, "co_argcount", 1) >= 2:
            return game_cls(ctx)
        return game_cls()

    def _draw_scrollbar(self, top, view, total):
        draw_menu_scrollbar(top, view, total)

    def _move_selection(self, delta, view, total):
        if total <= 0:
            return
        # Wrap around both ends so Up at the first entry lands on the last game.
        self.selected = (self.selected + delta) % total
        max_top = max(0, total - view)
        if self.selected < self.top:
            self.top = self.selected
        elif self.selected > self.top + view - 1:
            self.top = clamp(self.selected - view + 1, 0, max_top)

    async def _run_game_instance(self, game):
        # Prefer async loops when available so pygbag/browser frames keep rendering.
        if asyncio is not None and hasattr(game, "main_loop_async"):
            await game.main_loop_async(self.joystick)
        else:
            game.main_loop(self.joystick)
        await yield_runtime(0)

    async def _handle_game_over(self, game_name):
        # Highscore prompts live here so every game can just set global_score.
        best = self.highscores.best(game_name)
        best_name = self.highscores.best_name(game_name)
        if self.highscores.qualifies(game_name, global_score):
            entry_title = "NEW HS" if global_score > best else "SAVE"
            if asyncio is not None:
                initials = await InitialsEntryMenu(self.joystick, global_score, best, best_name, entry_title).run_async()
            else:
                initials = InitialsEntryMenu(self.joystick, global_score, best, best_name, entry_title).run()
            if initials:
                self.highscores.update(game_name, global_score, initials)

        best = self.highscores.best(game_name)
        best_name = self.highscores.best_name(game_name)
        title = globals().get("game_result", "LOST")
        if asyncio is not None:
            return await GameOverMenu(self.joystick, global_score, best, best_name, title,
                                      self.highscores, game_name).run_async()
        return GameOverMenu(self.joystick, global_score, best, best_name, title,
                            self.highscores, game_name).run()

    async def run_game_selector(self):
        # wait for lingering button presses to prevent instant re-entry
        await _wait_for_primary_release_async(self.joystick, timeout_ms=2000)
        games = self.sorted_games
        prev_selected = -1
        prev_top = -1
        view = 4
        row_y = (3, 16, 29, 42)
        last_move = ticks_ms()
        move_delay = 140

        while True:
            now = ticks_ms()

            if self.selected != prev_selected or self.top != prev_top:
                prev_selected = self.selected
                prev_top = self.top
                display.clear()
                for i in range(view):
                    gi = self.top + i
                    if gi >= len(games):
                        break
                    name = games[gi]
                    is_sel = gi == self.selected
                    col = (255, 255, 255) if is_sel else (111, 111, 111)
                    y = row_y[i]
                    draw_text(6, y, name, *col)

                    hs = self.highscores.best(name)
                    hn = self.highscores.best_name(name)
                    hs_str = str(hs) + " " + str(hn)
                    hs_x = max(0, WIDTH - len(hs_str) * 6 - 3)
                    draw_text_small(hs_x, y + 8, hs_str, 120, 120, 0)

                self._draw_scrollbar(self.top, view, len(games))
                draw_text_small(1, PLAY_HEIGHT, "Z GO", 120, 120, 120)
                if self.settings.has_options(games[self.selected]):
                    draw_text_small(WIDTH - 30, PLAY_HEIGHT, "C OPT", 80, 180, 255)

                display_flush()

            if ticks_diff(now, last_move) > move_delay:
                d = self.joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN])
                if d == JOYSTICK_UP:
                    self._move_selection(-1, view, len(games))
                    last_move = now
                elif d == JOYSTICK_DOWN:
                    self._move_selection(1, view, len(games))
                    last_move = now

            c_button, z_button = self.joystick.read_buttons()
            if z_button:
                await _wait_for_primary_release_async(self.joystick)
                return games[self.selected]
            if c_button:
                game_name = games[self.selected]
                await _wait_for_primary_release_async(self.joystick)
                if self.settings.has_options(game_name):
                    await GameSettingsMenu(self.joystick, game_name, self.settings).run_async()
                    prev_selected = -1
                    prev_top = -1
                else:
                    return game_name

            await yield_runtime(0.030)
            if asyncio is not None:
                continue
            sleep_ms(30)

    async def run(self):
        global game_over, global_score, game_result

        while True:
            game_name = await self.run_game_selector()

            # retry loop
            while True:
                game_over = False
                game_result = "LOST"
                global_score = 0

                game_cls = self._game_class(game_name)
                if game_cls is None:
                    break
                game = self._make_game_instance(game_name, game_cls)
                await self._run_game_instance(game)

                if game_over:
                    if await self._handle_game_over(game_name) == "RETRY":
                        continue
                break

# ---------- Intro ----------
async def _show_intro():
    """Show logo.png on desktop/web or a colour-fade animation on MicroPython."""

    async def _yield():
        await yield_runtime(0)

    def _intro_key_pressed():
        if IS_MICROPYTHON:
            return False
        try:
            import pygame  # type: ignore
            pygame.event.pump()
            for event in pygame.event.get():
                if event.type == pygame.KEYDOWN:
                    return True
                if event.type == pygame.QUIT:
                    raise RestartProgram()
            keys = pygame.key.get_pressed()
            for key in (
                pygame.K_SPACE, pygame.K_RETURN, pygame.K_ESCAPE,
                pygame.K_z, pygame.K_x,
                pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT,
            ):
                if keys[key]:
                    return True
        except RestartProgram:
            raise
        except Exception:
            pass
        return False

    def _intro_skip_requested(joystick=None):
        if _intro_key_pressed():
            return True
        if joystick is not None:
            try:
                c_btn, z_btn = joystick.read_buttons()
                if c_btn or z_btn:
                    return True
            except RestartProgram:
                raise
            except Exception:
                pass
        return False

    def _draw_png_logo(path):
        try:
            import struct
            import zlib
            with open(path, "rb") as fh:
                data = fh.read()
            if data[:8] != b"\x89PNG\r\n\x1a\n":
                return False
            pos = 8
            width = height = color_type = None
            compressed = []
            while pos + 8 <= len(data):
                length = struct.unpack(">I", data[pos:pos + 4])[0]
                kind = data[pos + 4:pos + 8]
                chunk = data[pos + 8:pos + 8 + length]
                pos += 12 + length
                if kind == b"IHDR":
                    width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(">IIBBBBB", chunk)
                    if bit_depth != 8 or compression != 0 or filter_method != 0 or interlace != 0 or color_type not in (2, 6):
                        return False
                elif kind == b"IDAT":
                    compressed.append(chunk)
                elif kind == b"IEND":
                    break
            if not width or not height or not compressed:
                return False
            channels = 4 if color_type == 6 else 3
            row_len = width * channels
            raw = zlib.decompress(b"".join(compressed))
            rows = []
            i = 0
            prev = [0] * row_len
            for _ in range(height):
                filt = raw[i]
                i += 1
                row = list(raw[i:i + row_len])
                i += row_len
                for x in range(row_len):
                    left = row[x - channels] if x >= channels else 0
                    up = prev[x]
                    up_left = prev[x - channels] if x >= channels else 0
                    if filt == 1:
                        row[x] = (row[x] + left) & 255
                    elif filt == 2:
                        row[x] = (row[x] + up) & 255
                    elif filt == 3:
                        row[x] = (row[x] + ((left + up) >> 1)) & 255
                    elif filt == 4:
                        p = left + up - up_left
                        pa = abs(p - left)
                        pb = abs(p - up)
                        pc = abs(p - up_left)
                        row[x] = (row[x] + (left if pa <= pb and pa <= pc else up if pb <= pc else up_left)) & 255
                rows.append(row)
                prev = row
            for y in range(HEIGHT):
                sy = (y * height) // HEIGHT
                row = rows[sy]
                for x in range(WIDTH):
                    sx = ((x * width) // WIDTH) * channels
                    r = row[sx]
                    g = row[sx + 1]
                    b = row[sx + 2]
                    if channels == 4:
                        a = row[sx + 3]
                        r = (r * a) // 255
                        g = (g * a) // 255
                        b = (b * a) // 255
                    display.set_pixel(x, y, r, g, b)
            return True
        except Exception:
            return False

    display.clear()
    shown = False
    joystick = None if IS_MICROPYTHON else Joystick()
    if not IS_MICROPYTHON:
        try:
            import pygame  # type: ignore
            import os as _os_intro
            _candidates = []
            for _base in (
                _os_intro.getcwd(),
                _os_intro.path.dirname(_os_intro.path.abspath(__file__)),
                _os_intro.path.dirname(_os_intro.path.abspath(sys.argv[0])) if getattr(sys, "argv", None) else "",
            ):
                if _base:
                    _lp = _os_intro.path.join(_base, "logo.png")
                    if _lp not in _candidates:
                        _candidates.append(_lp)
            for _lp in _candidates:
                if _draw_png_logo(_lp):
                    display_flush()
                    await _yield()
                    if _intro_skip_requested(joystick):
                        display.clear()
                        display_flush()
                        await _yield()
                        return
                    shown = True
                    break
            img = None
            if not shown:
                for _lp in _candidates:
                    try:
                        img = pygame.image.load(_lp)
                        break
                    except Exception:
                        pass
            if not shown and img is not None:
                blit_image = getattr(display, "blit_image", None)
                if blit_image is None or not blit_image(img):
                    img = pygame.transform.scale(img, (WIDTH, HEIGHT))
                    for y in range(HEIGHT):
                        for x in range(WIDTH):
                            c = img.get_at((x, y))
                            display.set_pixel(x, y, c[0], c[1], c[2])
                display_flush()
                await _yield()
                if _intro_skip_requested(joystick):
                    display.clear()
                    display_flush()
                    await _yield()
                    return
                shown = True
        except Exception:
            pass

    if not shown:
        colours = [(255, 60, 0), (255, 200, 0), (0, 180, 255), (0, 220, 80)]
        strip_h = HEIGHT // len(colours)
        if IS_MICROPYTHON:
            # RP2040 startup should reach the menu quickly; avoid full-screen fades.
            for ci, col in enumerate(colours):
                y0 = ci * strip_h
                y1 = y0 + strip_h if ci < len(colours) - 1 else HEIGHT
                for y in range(y0, y1):
                    for x in range(WIDTH):
                        display.set_pixel(x, y, col[0], col[1], col[2])
            display_flush()
            await _yield()
        else:
            # Desktop/web keeps the smoother fade.
            for step in range(32):
                t = (step + 1) / 32.0
                for ci, col in enumerate(colours):
                    y0 = ci * strip_h
                    y1 = y0 + strip_h if ci < len(colours) - 1 else HEIGHT
                    for y in range(y0, y1):
                        for x in range(WIDTH):
                            display.set_pixel(x, y, int(col[0] * t), int(col[1] * t), int(col[2] * t))
                display_flush()
                await _yield()
                await sleep_ms_async(30)
                if _intro_skip_requested(joystick):
                    display.clear()
                    display_flush()
                    await _yield()
                    return
                try:
                    maybe_collect(120)
                except Exception:
                    pass
        draw_centered_text_lines(("DIY", "ARCADE"), start_y=18, line_height=12)
        display_flush()
        await _yield()

        if IS_MICROPYTHON:
            await sleep_ms_async(900)
            display.clear()
            display_flush()
            await _yield()
            return

    # On hardware, never poll buttons during intro startup.
    if IS_MICROPYTHON:
        display.clear()
        display_flush()
        await _yield()
        return

    # Keep desktop/web startup interruptible.
    deadline = ticks_ms() + (250 if IS_MICROPYTHON else 3000)
    while ticks_diff(deadline, ticks_ms()) > 0:
        if _intro_skip_requested(joystick):
            if joystick is not None:
                _wait_for_primary_release(joystick, timeout_ms=500)
            break
        await _yield()
        await sleep_ms_async(10 if IS_MICROPYTHON else 15)

    display.clear()
    display_flush()
    await _yield()

async def _start_display_runtime():
    """Bring up the display and optional framebuffer before intro/menu code runs."""
    try:
        gc.collect()
    except Exception:
        pass
    _boot_log("before display.start")
    display.start()
    _boot_log("after display.start")
    try:
        refresh_runtime_config()
        init_buffered_display()
    except Exception:
        pass
    _boot_log("buffered on" if USE_BUFFERED_DISPLAY else "buffered off")
    reset_menu_display(0)
    await yield_runtime(0)

async def _recover_to_menu(delay_ms=800):
    """Show a brief error marker and restore enough state for the selector to continue."""
    display.clear()
    draw_text(1, 20, "ERR", 255, 0, 0)
    await sleep_ms_async(delay_ms)
    reset_menu_display(0)
    maybe_collect(1)
    await yield_runtime(0)


# ---------- Main ----------
async def main():
    await _start_display_runtime()

    try:
        await _show_intro()
    except RestartProgram:
        reset_menu_display(0)
        await yield_runtime(0)

    selector = GameSelect()
    while True:
        await yield_runtime(0)
        try:
            await selector.run()
        except RestartProgram:
            reset_menu_display(0)
            continue
        except Exception as e:
            # Failsafe: show simple error marker and reset to menu
            print("Error:", e)
            await _recover_to_menu()

if __name__ == "__main__":
    if asyncio is not None:
        asyncio.run(main())
    else:
        import sys as _sys
        print("asyncio unavailable", file=_sys.stderr)
