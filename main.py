import random
import time
import math
import gc
import sys

def _shuffle_in_place(seq):
    # Fisher-Yates; avoids relying on random.shuffle (not present on some MicroPython builds)
    n = len(seq)
    for i in range(n - 1, 0, -1):
        j = random.randint(0, i)
        seq[i], seq[j] = seq[j], seq[i]

# ---------- Runtime detection ----------
try:
    IS_MICROPYTHON = (sys.implementation.name == "micropython")
except Exception:
    IS_MICROPYTHON = False

if IS_MICROPYTHON:
    import hub75
    import machine
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
    if not IS_MICROPYTHON:
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
def maybe_collect(period=90):
    global _gc_ctr
    _gc_ctr += 1
    if _gc_ctr >= period:
        _gc_ctr = 0
        gc.collect()

# ---------- Display ----------
if IS_MICROPYTHON:
    display = hub75.Hub75(WIDTH, HEIGHT)
    rtc = machine.RTC()
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
            pygame.display.set_caption("DIY Arcade Machine (Desktop)")
            self._screen = pygame.display.set_mode((self.w * self.scale, self.h * self.scale))
            self._surface = pygame.Surface((self.w, self.h))
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

        def show(self):
            if not self._pg or not self._screen or not self._surface:
                return
            # keep window responsive
            self._pg.event.pump()
            scaled = self._pg.transform.scale(self._surface, (self.w * self.scale, self.h * self.scale))
            self._screen.blit(scaled, (0, 0))
            self._pg.display.flip()

    display = _PyGameDisplay(WIDTH, HEIGHT, scale=10)
    rtc = _DesktopRTC()

# Use the software framebuffer diff layer only on MicroPython/HUB75.
# On desktop, drawing directly to the PyGame surface is simpler and avoids
# subtle corruption when the menu redraws rapidly.
USE_BUFFERED_DISPLAY = IS_MICROPYTHON

# ---------- Framebuffer diff / buffered drawing ----------
# keep a software framebuffer and only push changed pixels to the hardware
_fb_w = WIDTH
_fb_h = HEIGHT
_fb_size = _fb_w * _fb_h * 3
_fb_current = bytearray(_fb_size)
_fb_prev = bytearray(_fb_size)

# dirty tracking: list of changed pixel indices and mask to avoid duplicates
_dirty_pixels = []
_dirty_mask = bytearray(_fb_w * _fb_h)

# keep originals to actually write to the hardware
_display_set_pixel_orig = display.set_pixel
_display_clear_orig = getattr(display, "clear", None)

def _mark_dirty_pixel(px):
    if _dirty_mask[px] == 0:
        _dirty_mask[px] = 1
        _dirty_pixels.append(px)

def _set_pixel_buf(x, y, r, g, b):
    if x < 0 or x >= _fb_w or y < 0 or y >= _fb_h:
        return
    pix = y * _fb_w + x
    idx = pix * 3
    if _fb_current[idx] != r or _fb_current[idx + 1] != g or _fb_current[idx + 2] != b:
        _fb_current[idx] = r
        _fb_current[idx + 1] = g
        _fb_current[idx + 2] = b
        _mark_dirty_pixel(pix)

def _clear_buf():
    # clear current framebuffer and mark all pixels dirty
    w = _fb_w * _fb_h
    for i in range(w * 3):
        if _fb_current[i] != 0:
            _fb_current[i] = 0
    # mark all pixels dirty so they will be pushed
    # reset mask and append indices
    del _dirty_pixels[:]
    for i in range(w):
        _dirty_mask[i] = 1
        _dirty_pixels.append(i)
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
    # push only dirty pixels to the hardware and update prev buffer
    if not _dirty_pixels:
        return
    sp = _display_set_pixel_orig
    for pix in _dirty_pixels:
        idx = pix * 3
        r = _fb_current[idx]
        g = _fb_current[idx + 1]
        b = _fb_current[idx + 2]
        # compare with previous
        if _fb_prev[idx] != r or _fb_prev[idx + 1] != g or _fb_prev[idx + 2] != b:
            try:
                sp(pix % _fb_w, pix // _fb_w, r, g, b)
            except Exception:
                pass
            _fb_prev[idx] = r
            _fb_prev[idx + 1] = g
            _fb_prev[idx + 2] = b
        _dirty_mask[pix] = 0
    del _dirty_pixels[:]
    # Desktop display needs an explicit present; HUB75 hardware does not.
    try:
        if hasattr(display, "show"):
            display.show()
    except Exception:
        pass

# override display methods to write into our buffer (MicroPython/HUB75 only)
if USE_BUFFERED_DISPLAY:
    # Apply our buffered hooks if the hardware object exposes the expected methods.
    # Some hub75 wrappers may not expose the exact same API; guard against that.
    try:
        display.set_pixel = _set_pixel_buf
        display.clear = _clear_buf
    except Exception:
        # fallback: keep originals
        pass

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


# ---------- Global state ----------
global_score = 0
game_over = False

# ---------- Colors ----------
COLORS_BRIGHT = [
    (255, 0, 0),    # Red
    (0, 255, 0),    # Green
    (0, 0, 255),    # Blue
    (255, 255, 0),  # Yellow
]
colors = [(int(r * 0.5), int(g * 0.5), int(b * 0.5)) for r, g, b in COLORS_BRIGHT]
inactive_colors = [(int(r * 0.2), int(g * 0.2), int(b * 0.2)) for r, g, b in COLORS_BRIGHT]

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

# ---------- Fonts ----------
CHAR_DICT = {
    "A": "3078ccccfccccc00","B": "fc66667c6666fc00","C": "3c66c0c0c0663c00","D": "f86c6666666cf800",
    "E": "fe6268786862fe00","F": "fe6268786860f000","G": "3c66c0c0ce663e00","H": "ccccccfccccccc00",
    "I": "7830303030307800","J": "1e0c0c0ccccc7800","K": "f6666c786c66f600","L": "f06060606266fe00",
    "M": "c6eefefed6c6c600","N": "c6e6f6decec6c600","O": "386cc6c6c66c3800","P": "fc66667c6060f000",
    "Q": "78ccccccdc781c00","R": "fc66667c6c66f600","S": "78cce0380ccc7800","T": "fcb4303030307800",
    "U": "ccccccccccccfc00","V": "cccccccccc783000","W": "c6c6c6d6feeec600","X": "c6c66c38386cc600",
    "Y": "cccccc7830307800","Z": "fec68c183266fe00",
    "0": "78ccdcfceccc7c00","1": "307030303030fc00","2": "78cc0c3860ccfc00","3": "78cc0c380ccc7800",
    "4": "1c3c6cccfe0c1e00","5": "fcc0f80c0ccc7800","6": "3860c0f8cccc7800","7": "fccc0c1830303000",
    "8": "78cccc78cccc7800","9": "78cccc7c0c187000",
    "!": "3078783030003000","#": "6c6cfe6cfe6c6c00","$": "307cc0780cf83000","%": "00c6cc183066c600",
    "&": "386c3876dccc7600","?": "78cc0c1830003000"," ": "0000000000000000",".": "0000000000003000",
    ":": "0030000000300000","(": "0c18303030180c00",")": "6030180c18306000","-": "000000fc00000000",
}

NUMS = {
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

FONT8 = {ch: _hex_to_bytes(hs) for ch, hs in CHAR_DICT.items()}  # 8 bytes per char
FONT5 = {ch: bytes(int(row, 2) for row in rows) for ch, rows in NUMS.items()}  # 5 rows
del CHAR_DICT
del NUMS
gc.collect()

# ---------- Drawing ----------
def draw_rectangle(x1, y1, x2, y2, r, g, b):
    if x1 > x2: x1, x2 = x2, x1
    if y1 > y2: y1, y2 = y2, y1
    if x2 < 0 or y2 < 0 or x1 >= WIDTH or y1 >= HEIGHT:
        return
    if x1 < 0: x1 = 0
    if y1 < 0: y1 = 0
    if x2 >= WIDTH: x2 = WIDTH - 1
    if y2 >= HEIGHT: y2 = HEIGHT - 1
    sp = display.set_pixel
    for y in range(y1, y2 + 1):
        for x in range(x1, x2 + 1):
            sp(x, y, r, g, b)

def draw_character(x, y, ch, r, g, b):
    rows = FONT8.get(ch)
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
    rows = FONT5.get(ch)
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
    try:
        display_flush()
    except Exception:
        pass

# ---------- Grid (nibble-packed) for Maze/Qix ----------
GRID_W = WIDTH
GRID_H = PLAY_HEIGHT
grid = bytearray((GRID_W * GRID_H + 1) // 2)

def initialize_grid():
    global grid
    grid = bytearray((GRID_W * GRID_H + 1) // 2)

def get_grid_value(x, y):
    if x < 0 or x >= GRID_W or y < 0 or y >= GRID_H:
        return 1  # treat out-of-bounds as wall/border
    idx = y * GRID_W + x
    b = grid[idx >> 1]
    if idx & 1:
        return (b >> 4) & 0x0F
    return b & 0x0F

def set_grid_value(x, y, value):
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

if IS_MICROPYTHON:
    class Nunchuck:
        def __init__(self, i2c, poll=True, poll_interval=50):
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

    class Joystick:
        def __init__(self):
            self.i2c = machine.I2C(0, scl=machine.Pin(21), sda=machine.Pin(20))
            self.nunchuck = Nunchuck(self.i2c, poll=True, poll_interval=50)

        def read_direction(self, possible_directions, debounce=True):
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
            _, z = self.nunchuck.buttons()
            return z
else:
    class Nunchuck:
        # Desktop keyboard input emulating the nunchuck API.
        def __init__(self):
            self._z = False
            self._c = False
            self._x = 128
            self._y = 128

        def _poll(self):
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
            self._z = bool(keys[pygame.K_z] or keys[pygame.K_SPACE] or keys[pygame.K_RETURN])
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
            self._poll()
            if self._c and self._z:
                raise RestartProgram()
            return self._c, self._z

        def joystick(self):
            self._poll()
            return (self._x, self._y)

    class Joystick:
        def __init__(self):
            self.nunchuck = Nunchuck()

        def read_direction(self, possible_directions, debounce=True):
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
            _, z = self.nunchuck.buttons()
            return z

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

    def __init__(self):
        self.scores = {}
        self.load()

    def load(self):
        try:
            with open(self.FILE, "r") as f:
                self.scores = json.load(f)
        except Exception:
            self.scores = {}

    def save(self):
        try:
            with open(self.FILE, "w") as f:
                json.dump(self.scores, f)
        except Exception:
            pass

    def best(self, game):
        try:
            v = self.scores.get(game, 0)
            if isinstance(v, dict):
                return int(v.get("score", 0) or 0)
            return int(v or 0)
        except Exception:
            return 0

    def best_name(self, game):
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
    """Simon: memory game — repeat the color sequence shown."""
    def __init__(self):
        self.sequence = []
        self.user_input = []

    def draw_quad_screen(self):
        hw = WIDTH // 2
        hh = PLAY_HEIGHT // 2
        draw_rectangle(0, 0, hw - 1, hh - 1, *inactive_colors[0])
        draw_rectangle(hw, 0, WIDTH - 1, hh - 1, *inactive_colors[1])
        draw_rectangle(0, hh, hw - 1, PLAY_HEIGHT - 1, *inactive_colors[2])
        draw_rectangle(hw, hh, WIDTH - 1, PLAY_HEIGHT - 1, *inactive_colors[3])

    def flash_color(self, idx, duration_ms=250):
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
        for c in self.sequence:
            self.flash_color(c, 300)
            sleep_ms(200)

    def get_user_input(self, joystick):
        while True:
            d = joystick.read_direction([JOYSTICK_UP_LEFT, JOYSTICK_UP_RIGHT, JOYSTICK_DOWN_LEFT, JOYSTICK_DOWN_RIGHT])
            if d:
                return d
            sleep_ms(30)

    def translate(self, direction):
        m = {JOYSTICK_UP_LEFT: 0, JOYSTICK_UP_RIGHT: 1, JOYSTICK_DOWN_LEFT: 2, JOYSTICK_DOWN_RIGHT: 3}
        return m.get(direction, None)

    def main_loop(self, joystick):
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
                if self.user_input != self.sequence[:len(self.user_input)]:
                    global_score = len(self.sequence) - 1
                    game_over = True
                    return

            sleep_ms(300)
            maybe_collect(120)

class SnakeGame:
    """Snake: classic snake game, collect targets and grow."""
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
        self.target = self.random_target()
        display.set_pixel(self.target[0], self.target[1], 255, 0, 0)

    def place_green_target(self):
        x, y = random.randint(1, WIDTH - 2), random.randint(1, PLAY_HEIGHT - 2)
        self.green_targets.append((x, y, 256))
        display.set_pixel(x, y, 0, 255, 0)

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

    def main_loop(self, joystick, mode="single"):
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

            direction = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
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
    """Pong: two-player paddle game (AI-controlled opponent)."""
    def __init__(self):
        self.paddle_height = 10
        self.paddle_speed = 2
        self.left_paddle_y = PLAY_HEIGHT // 2 - self.paddle_height // 2
        self.right_paddle_y = PLAY_HEIGHT // 2 - self.paddle_height // 2
        self.ball_speed = [1, 1]
        self.ball_position = [WIDTH // 2, PLAY_HEIGHT // 2]
        self.left_score = 0
        self.lives = 3

    def reset_ball(self):
        self.ball_position = [WIDTH // 2, PLAY_HEIGHT // 2]
        self.ball_speed = [random.choice([-1, 1]), random.choice([-1, 1])]

    def draw_paddles(self):
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
        x, y = self.ball_position
        if 0 <= y < PLAY_HEIGHT:
            display.set_pixel(x, y, 0, 0, 0)

    def draw_ball(self):
        x, y = self.ball_position
        if 0 <= y < PLAY_HEIGHT:
            display.set_pixel(x, y, 255, 255, 255)

    def update_paddles(self, joystick):
        d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN])
        if d == JOYSTICK_UP:
            self.left_paddle_y = max(self.left_paddle_y - self.paddle_speed, 0)
        elif d == JOYSTICK_DOWN:
            self.left_paddle_y = min(self.left_paddle_y + self.paddle_speed, PLAY_HEIGHT - self.paddle_height)

        # simple AI right
        by = self.ball_position[1]
        pc = self.right_paddle_y + self.paddle_height // 2
        if by < pc:
            self.right_paddle_y = max(self.right_paddle_y - self.paddle_speed, 0)
        elif by > pc:
            self.right_paddle_y = min(self.right_paddle_y + self.paddle_speed, PLAY_HEIGHT - self.paddle_height)

    def update_ball(self):
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

        # right paddle hit
        if x == WIDTH - 2 and self.right_paddle_y <= y < self.right_paddle_y + self.paddle_height:
            self.ball_speed[0] = -self.ball_speed[0]

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

# ---------- Breakout ----------
PADDLE_WIDTH = const(12)
PADDLE_HEIGHT = const(2)
BALL_SIZE = const(2)
BRICK_WIDTH = const(7)
BRICK_HEIGHT = const(4)
BRICK_ROWS = const(5)
BRICK_COLS = const(8)

class BreakoutGame:
    """Breakout: destroy bricks with a bouncing ball and paddle."""
    def __init__(self):
        self.paddle_x = (WIDTH - PADDLE_WIDTH) // 2
        self.paddle_y = PLAY_HEIGHT - PADDLE_HEIGHT
        self.ball_x = WIDTH // 2
        self.ball_y = PLAY_HEIGHT // 2
        self.ball_dx = 1
        self.ball_dy = -1
        self.bricks = self.create_bricks()
        self.score = 0
        self.paddle_speed = 2

    def create_bricks(self):
        bricks = []
        for row in range(BRICK_ROWS):
            for col in range(BRICK_COLS):
                x = col * (BRICK_WIDTH + 1) + 1
                y = row * (BRICK_HEIGHT + 1)
                bricks.append((x, y))
        return bricks

    def draw_paddle(self):
        draw_rectangle(self.paddle_x, self.paddle_y, self.paddle_x + PADDLE_WIDTH - 1, self.paddle_y + PADDLE_HEIGHT - 1, 255, 255, 255)

    def clear_paddle(self):
        draw_rectangle(self.paddle_x, self.paddle_y, self.paddle_x + PADDLE_WIDTH - 1, self.paddle_y + PADDLE_HEIGHT - 1, 0, 0, 0)

    def draw_ball(self):
        draw_rectangle(self.ball_x, self.ball_y, self.ball_x + 1, self.ball_y + 1, 255, 255, 255)

    def clear_ball(self):
        draw_rectangle(self.ball_x, self.ball_y, self.ball_x + 1, self.ball_y + 1, 0, 0, 0)

    def draw_bricks(self):
        for x, y in self.bricks:
            hue = (y * 360) // max(1, (BRICK_ROWS * BRICK_HEIGHT))
            r, g, b = hsb_to_rgb(hue, 1, 1)
            draw_rectangle(x, y, x + BRICK_WIDTH - 1, y + BRICK_HEIGHT - 1, r, g, b)

    def update_ball(self):
        global game_over, global_score
        self.clear_ball()
        self.ball_x += self.ball_dx
        self.ball_y += self.ball_dy

        # wall bounce (ball is 2x2; top-left coords)
        if self.ball_x <= 0 or self.ball_x >= WIDTH - 2:
            self.ball_dx = -self.ball_dx
        if self.ball_y <= 0:
            self.ball_dy = -self.ball_dy

        # paddle bounce
        if self.ball_y + 1 >= self.paddle_y:
            if self.paddle_x <= self.ball_x <= self.paddle_x + PADDLE_WIDTH - 1:
                self.ball_dy = -abs(self.ball_dy)

        # below paddle -> lost
        if self.ball_y >= PLAY_HEIGHT:
            global_score = self.score
            game_over = True
            return

        self.draw_ball()

    def check_collision_with_bricks(self):
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
        d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT])
        if d == JOYSTICK_LEFT:
            self.clear_paddle()
            self.paddle_x = max(self.paddle_x - self.paddle_speed, 0)
        elif d == JOYSTICK_RIGHT:
            self.clear_paddle()
            self.paddle_x = min(self.paddle_x + self.paddle_speed, WIDTH - PADDLE_WIDTH)
        self.draw_paddle()

    def main_loop(self, joystick):
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

# ---------- Asteroids ----------
SHIP_COOLDOWN = const(10)
FPS = const(20)
PIXEL_WIDTH = WIDTH
PIXEL_HEIGHT = PLAY_HEIGHT

class AsteroidGame:
    """Asteroids: pilot a ship, shoot asteroids and survive."""
    class Projectile:
        def __init__(self, x, y, angle, speed):
            self.x = x
            self.y = y
            self.angle = angle
            self.speed = speed
            self.lifetime = 12

        def update(self):
            self.x += math.cos(math.radians(self.angle)) * self.speed
            self.y -= math.sin(math.radians(self.angle)) * self.speed
            self.x %= PIXEL_WIDTH
            self.y %= PIXEL_HEIGHT
            self.lifetime -= 1

        def is_alive(self):
            return self.lifetime > 0

        def draw_line(self, start, end, color):
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
            ex = self.x + math.cos(math.radians(self.angle))
            ey = self.y - math.sin(math.radians(self.angle))
            self.draw_line((self.x, self.y), (ex, ey), (255, 0, 0))

    class Asteroid:
        def __init__(self, x=None, y=None, size=None, start=False):
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
            self.x += math.cos(math.radians(self.angle)) * self.speed
            self.y -= math.sin(math.radians(self.angle)) * self.speed
            self.x %= PIXEL_WIDTH
            self.y %= PIXEL_HEIGHT

        def draw(self):
            sp = display.set_pixel
            for deg in range(0, 360, 12):
                rad = math.radians(deg)
                px = int((self.x + math.cos(rad) * self.size) % PIXEL_WIDTH)
                py = int((self.y + math.sin(rad) * self.size) % PIXEL_HEIGHT)
                sp(px, py, *WHITE)

    class Ship:
        def __init__(self):
            self.x = PIXEL_WIDTH / 2
            self.y = PIXEL_HEIGHT / 2
            self.angle = 0
            self.speed = 0
            self.max_speed = 2.2
            self.size = 3
            self.cooldown = 0

        def draw_line(self, start, end, color):
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
            a = self.angle
            s = self.size
            p0 = (self.x + math.cos(math.radians(a)) * s,
                  self.y - math.sin(math.radians(a)) * s)
            p1 = (self.x + math.cos(math.radians(a + 120)) * s,
                  self.y - math.sin(math.radians(a + 120)) * s)
            p2 = (self.x + math.cos(math.radians(a - 120)) * s,
                  self.y - math.sin(math.radians(a - 120)) * s)

            if self.speed > 0:
                self.draw_line(p1, p2, RED)
            self.draw_line(p0, p1, WHITE)
            self.draw_line(p2, p0, WHITE)

        def shoot(self):
            if self.cooldown == 0:
                self.cooldown = SHIP_COOLDOWN
                bullet_speed = 4
                bx = self.x + math.cos(math.radians(self.angle)) * self.size
                by = self.y - math.sin(math.radians(self.angle)) * self.size
                return AsteroidGame.Projectile(bx, by, self.angle, bullet_speed)
            return None

    def __init__(self):
        self.ship = self.Ship()
        self.asteroids = [self.Asteroid(start=True) for _ in range(3)]
        self.projectiles = []
        self.score = 0

    def check_collisions(self):
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
                            self.asteroids.append(self.Asteroid(a.x, a.y, max(2, a.size // 2)))
                    break

        # ship vs asteroid
        for a in self.asteroids:
            d = hypot(self.ship.x - a.x, self.ship.y - a.y)
            if d < a.size + self.ship.size:
                game_over = True
                global_score = self.score
                return

    def main_loop(self, joystick):
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

            direction = joystick.read_direction([JOYSTICK_UP, JOYSTICK_LEFT, JOYSTICK_RIGHT])
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

# ---------- Qix ----------
class QixGame:
    """Qix-like: draw lines to claim area while avoiding opponents."""
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
        display_score_and_time(0, force=True)

    def place_opponents(self, n):
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

    def place_opponent(self):
        self.opponent_x = random.randint(1, self.width - 2)
        self.opponent_y = random.randint(1, self.height - 2)
        display.set_pixel(self.opponent_x, self.opponent_y, 255, 0, 0)

    def move_opponent(self):
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
            op["x"] = nx
            op["y"] = ny
            op["dx"] = dx
            op["dy"] = dy
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
        occ = count_cells_with_mark(2, self.width, self.height)
        self.occupied_percentage = (occ / (self.width * self.height)) * 100
        display_score_and_time(int(self.occupied_percentage))

    def main_loop(self, joystick):
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
                global_score = int(self.occupied_percentage)
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
    """Tetris: falling blocks puzzle with line clears and scoring."""
    GRID_WIDTH = const(16)
    GRID_HEIGHT = const(13)
    BLOCK_SIZE = const(4)

    COLORS = [
        (0, 255, 255),(255, 0, 0),(0, 255, 0),(0, 0, 255),
        (255, 255, 0),(255, 165, 0),(128, 0, 128),
    ]

    TETRIMINOS = [
        [[1,1,1,1]],                 # I
        [[1,1,1],[0,1,0]],           # T
        [[1,1,0],[0,1,1]],           # S
        [[0,1,1],[1,1,0]],           # Z
        [[1,1],[1,1]],               # O
        [[1,1,1],[1,0,0]],           # L
        [[1,1,1],[0,0,1]],           # J
    ]

    class Piece:
        def __init__(self):
            self.shape = random.choice(TetrisGame.TETRIMINOS)
            self.color = random.choice(TetrisGame.COLORS)
            self.x = TetrisGame.GRID_WIDTH // 2 - len(self.shape[0]) // 2
            self.y = 0

        def rotate(self):
            self.shape = [list(row) for row in zip(*self.shape[::-1])]

    def __init__(self):
        self.locked = {}  # (x,y)->color
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
                if ny >= 0 and (nx, ny) in self.locked:
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
                    self.locked[(px, py)] = piece.color
        return True

    def clear_rows(self):
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
        x1 = gx * self.BLOCK_SIZE
        y1 = gy * self.BLOCK_SIZE
        draw_rectangle(x1, y1, x1 + self.BLOCK_SIZE - 1, y1 + self.BLOCK_SIZE - 1, *color)

    def render(self):
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
                d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_DOWN, JOYSTICK_UP])
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
        self.projectiles = []
        self.gems = []
        self.enemies = []
        self.score = 0
        self.player_direction = JOYSTICK_UP
        self.explored = set()

    def generate_maze(self):
        stack = []
        visited = set()

        start_x = random.randint(self.BORDER, WIDTH - self.BORDER - 1)
        start_y = random.randint(self.BORDER, PLAY_HEIGHT - self.BORDER - 1)

        stack.append((start_x, start_y))
        visited.add((start_x, start_y))
        set_grid_value(start_x, start_y, self.PATH)

        dirs = [(0, self.MazeWaySize), (0, -self.MazeWaySize), (self.MazeWaySize, 0), (-self.MazeWaySize, 0)]

        while stack:
            x, y = stack[-1]
            mixed = dirs[:]
            for i in range(len(mixed)-1, 0, -1):
                j = random.randint(0, i)
                mixed[i], mixed[j] = mixed[j], mixed[i]

            found = False
            for dx, dy in mixed:
                nx, ny = x + dx, y + dy
                if self.BORDER <= nx < WIDTH - self.BORDER and self.BORDER <= ny < PLAY_HEIGHT - self.BORDER and (nx, ny) not in visited:
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
        while True:
            self.player_x = random.randint(self.BORDER, WIDTH - self.BORDER - 1)
            self.player_y = random.randint(self.BORDER, PLAY_HEIGHT - self.BORDER - 1)
            if get_grid_value(self.player_x, self.player_y) == self.PATH:
                set_grid_value(self.player_x, self.player_y, self.PLAYER)
                # mark initial player cell as explored
                self.explored.add((self.player_x, self.player_y))
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
        vis = set()
        x, y = self.player_x, self.player_y
        vis.add((x, y))
        dirs = [(-1,0),(1,0),(0,-1),(0,1)]
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
        d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
        if not d:
            return

        nx, ny = self.player_x, self.player_y
        if d == JOYSTICK_UP: ny -= 1
        elif d == JOYSTICK_DOWN: ny += 1
        elif d == JOYSTICK_LEFT: nx -= 1
        elif d == JOYSTICK_RIGHT: nx += 1

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
        new_enemies = []
        for (ex, ey) in self.enemies:
            moves = []
            for dx, dy in [(0,-1),(0,1),(-1,0),(1,0)]:
                nx, ny = ex + dx, ey + dy
                if 0 <= nx < WIDTH and 0 <= ny < PLAY_HEIGHT and get_grid_value(nx, ny) == self.PATH:
                    moves.append((nx, ny))
            set_grid_value(ex, ey, self.PATH)
            if moves:
                ex, ey = random.choice(moves)
            set_grid_value(ex, ey, self.ENEMY)
            new_enemies.append((ex, ey))
        self.enemies = new_enemies

    def handle_shooting(self, joystick):
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
        for p in self.projectiles[:]:
            # restore previous cell
            set_grid_value(p["x"], p["y"], p["prev"])

            p["x"] += p["dx"]
            p["y"] += p["dy"]
            p["lifetime"] -= 1

            if p["lifetime"] <= 0 or not (0 <= p["x"] < WIDTH and 0 <= p["y"] < PLAY_HEIGHT):
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
    """Flappy: navigate between pipes; flap to gain altitude."""
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
        self.vy = -4

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

    def main_loop(self, joystick):
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
        for p in self.powerups[:]:
            p[0] -= 1
            p[2] -= 1
            if p[0] < -2 or p[2] <= 0:
                self.powerups.remove(p)
                continue

            # collect
            if abs(p[0] - (self.px + self.pw // 2)) <= 2 and abs(p[1] - (self.py + 1)) <= 2:
                self.powerups.remove(p)
                self.power_t = 240  # ~8 Sekunden
                # kleines Bonus
                self.score += 5

    def _update_bullets(self):
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
                if e[1] < 1: e[1] = 1
                if e[1] > PLAY_HEIGHT - 6: e[1] = PLAY_HEIGHT - 6
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
                    self.score += (10 + typ * 7)
                    # chance for powerup
                    if random.randint(0, 99) < 12:
                        self.powerups.append([hit[0], hit[1], 400])
                else:
                    self.score += 1  # hit bonus

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
            if z_button and self.fire_cd == 0:
                # normal bullet
                self.bullets.append([self.px + self.pw + 1, self.py + 1])
                # powered double-shot
                if self.power_t > 0 and len(self.bullets) < 6:
                    self.bullets.append([self.px + self.pw + 1, self.py])
                self.fire_cd = cd_min

            # spawn
            self._difficulty_update()
            if ticks_diff(now, self.last_spawn) >= self.spawn_ms and len(self.enemies) < 8:
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

    # 16 Zeichen pro Zeile, 14 Zeilen
    MAP = [
        "################",
        "#P....#....G...#",
        "#.##.#.##.#.##.#",
        "#o#..#....#..#o#",
        "#....###.###...#",
        "#.##........##.#",
        "#....#.##.#....#",
        "#....#.##.#....#",
        "#.##........##.#",
        "#...###.###....#",
        "#o#..#....#..#o#",
        "#.##.#.##.#.##.#",
        "#...G#....#....#",
        "################",
    ]

    # dirs: 0 U, 1 D, 2 L, 3 R
    DIRS = ((0, -1), (0, 1), (-1, 0), (1, 0))
    OPP  = (1, 0, 3, 2)

    def __init__(self):
        self.reset()

    def reset(self):
        self.wall = bytearray(self.W * self.H)      # 1 if wall
        self.pel = bytearray(self.W * self.H)       # 0 none, 1 pellet, 2 power
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
        for y in range(self.H):
            row = self.MAP[y]
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
                        self.ghosts.append([x, y, random.randint(0, 3), x, y])

        if len(self.ghosts) < 2:
            # safety
            self.ghosts.append([self.W - 2, 1, 2, self.W - 2, 1])

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

    def _move_ghosts(self):
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
        x1 = self.OFF_X + cx * self.CELL
        y1 = self.OFF_Y + cy * self.CELL
        draw_rectangle(x1, y1, x1 + self.CELL - 1, y1 + self.CELL - 1, r, g, b)

    def _draw_bg_cell(self, x, y):
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
        px = self.OFF_X + self.px * self.CELL
        py = self.OFF_Y + self.py * self.CELL
        draw_rectangle(px, py, px + 2, py + 2, 255, 255, 0)

    def _draw_ghosts(self):
        frightened = (self.power_timer > 0)
        for gi, g in enumerate(self.ghosts):
            gx = self.OFF_X + g[0] * self.CELL
            gy = self.OFF_Y + g[1] * self.CELL
            if frightened:
                col = (80, 80, 255)
            else:
                col = (255, 60, 60) if gi == 0 else (255, 0, 255)
            draw_rectangle(gx, gy, gx + 2, gy + 2, *col)

    def _draw_background(self):
        display.clear()
        # walls
        for (x, y) in self.wall_list:
            self._draw_cell(x, y, 0, 0, 140)

        # pellets
        for y in range(self.H):
            for x in range(self.W):
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
        if not self._drawn_bg:
            self._draw_background()
        self._draw_player()
        self._draw_ghosts()

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
            c_button, _z = joystick.nunchuck.buttons()
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
    CAVE FLYER (wie Flappy in Höhle)
    Steuerung:
      - Z oder Stick UP: Schub nach oben
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

        # Tunnel parameters
        self.base_gap = 22
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
        if v < lo: return lo
        if v > hi: return hi
        return v

    def _idx_row(self, y):
        return (self.head + y) % PLAY_HEIGHT

    def _gen_row_at(self, idx):
        # tunnel tightens over time
        self.gap = self.base_gap - int(self.score / 80)
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

    def main_loop(self, joystick):
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

    def _spawn_one(self, x_start):
        
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


class DemosGame:
    """Zero-player demos: simple animations and cellular automata."""
    def __init__(self):
        self.demos = ["SNAKE", "TRON", "LIFE", "ANT"]
        self.idx = 0
        self._init = False
        self._last_move = ticks_ms()
        self._move_delay = 180
        self._reset_demo_state()

    def _reset_demo_state(self):
        # shared
        self._init = False
        self._frame = 0

        # LIFE (2x2 scaled)
        self._life_w = 32
        self._life_h = 24
        self._life_cur = bytearray(self._life_w * self._life_h)
        self._life_nxt = bytearray(self._life_w * self._life_h)
        self._life_prev = bytearray(self._life_w * self._life_h)

        # ANT
        self._ant_w = WIDTH
        self._ant_h = PLAY_HEIGHT
        self._ant_cells = bytearray(self._ant_w * self._ant_h)
        self._ant = [self._ant_w // 2, self._ant_h // 2, 0]
        self._ant_prev = [self._ant[0], self._ant[1]]

        # TRON
        self._tron_w = WIDTH
        self._tron_h = PLAY_HEIGHT
        self._tron_occ = bytearray(self._tron_w * self._tron_h)
        self._tron_p1 = [self._tron_w // 3, self._tron_h // 2, 1, 0]
        self._tron_p2 = [2 * self._tron_w // 3, self._tron_h // 2, -1, 0]
        self._tron_prev1 = [self._tron_p1[0], self._tron_p1[1]]
        self._tron_prev2 = [self._tron_p2[0], self._tron_p2[1]]

        # SNAKE
        self._snake = [(WIDTH // 2, PLAY_HEIGHT // 2)]
        self._snake_len = 8
        self._snake_dir = 0  # 0U 1D 2L 3R
        self._snake_target = (random.randint(1, WIDTH - 2), random.randint(1, PLAY_HEIGHT - 2))
        self._snake_occ = bytearray(WIDTH * PLAY_HEIGHT)

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
                if py >= PLAY_HEIGHT:
                    continue
                if v:
                    r, g, b = 0, 180, 0
                else:
                    r, g, b = 0, 0, 0
                display.set_pixel(px, py, r, g, b)
                if px + 1 < WIDTH:
                    display.set_pixel(px + 1, py, r, g, b)
                if py + 1 < PLAY_HEIGHT:
                    display.set_pixel(px, py + 1, r, g, b)
                    if px + 1 < WIDTH:
                        display.set_pixel(px + 1, py + 1, r, g, b)

    def _langton_step(self, w, h, cells, ant):
        x, y, d = ant
        i = y * w + x
        if cells[i]:
            # black: turn left
            d = (d - 1) & 3
            cells[i] = 0
        else:
            # white: turn right
            d = (d + 1) & 3
            cells[i] = 1
        if d == 0:
            y = (y - 1) % h
        elif d == 1:
            x = (x + 1) % w
        elif d == 2:
            y = (y + 1) % h
        else:
            x = (x - 1) % w
        ant[0], ant[1], ant[2] = x, y, d

    def _langton_draw(self, w, h, cells, ant):
        # kept for compatibility (not used in incremental mode)
        display.clear()
        for y in range(h):
            for x in range(w):
                if cells[y * w + x] == 1 and y < PLAY_HEIGHT:
                    display.set_pixel(x, y, 50, 50, 255)
        ax, ay, _ = ant
        if ay < PLAY_HEIGHT:
            display.set_pixel(ax, ay, 255, 255, 0)

    def _tron_step(self, w, h, occ, p):
        # p: [x,y,dx,dy]
        x, y, dx, dy = p
        nx = x + dx
        ny = y + dy
        if nx <= 0 or nx >= w - 1 or ny <= 0 or ny >= h - 1 or occ[ny * w + nx]:
            # turn randomly
            if random.randint(0, 1) == 0:
                dx, dy = -dy, dx
            else:
                dx, dy = dy, -dx
            nx = x + dx
            ny = y + dy
        if nx <= 0 or nx >= w - 1 or ny <= 0 or ny >= h - 1 or occ[ny * w + nx]:
            return False
        p[0], p[1], p[2], p[3] = nx, ny, dx, dy
        occ[ny * w + nx] = 1
        return True

    def _tron_draw(self, w, h, occ, p1, p2):
        # kept for compatibility (not used in incremental mode)
        display.clear()
        for y in range(h):
            for x in range(w):
                if occ[y * w + x] and y < PLAY_HEIGHT:
                    display.set_pixel(x, y, 0, 200, 200)
        if p1[1] < PLAY_HEIGHT:
            display.set_pixel(p1[0], p1[1], 255, 0, 0)
        if p2[1] < PLAY_HEIGHT:
            display.set_pixel(p2[0], p2[1], 0, 255, 0)

    def _snake_place_target(self):
        tries = 0
        while tries < 200:
            x = random.randint(1, WIDTH - 2)
            y = random.randint(1, PLAY_HEIGHT - 2)
            if self._snake_occ[y * WIDTH + x] == 0:
                self._snake_target = (x, y)
                return
            tries += 1
        self._snake_target = (WIDTH // 2, PLAY_HEIGHT // 2)

    def _snake_init(self):
        self._snake_occ = bytearray(WIDTH * PLAY_HEIGHT)
        self._snake = [(WIDTH // 2, PLAY_HEIGHT // 2)]
        self._snake_len = 10
        self._snake_dir = random.randint(0, 3)
        self._snake_occ[self._snake[0][1] * WIDTH + self._snake[0][0]] = 1
        self._snake_place_target()
        display.clear()
        tx, ty = self._snake_target
        display.set_pixel(tx, ty, 255, 0, 0)
        hx, hy = self._snake[0]
        display.set_pixel(hx, hy, 0, 255, 0)

    def _snake_step(self):
        # simple greedy AI to target avoiding self
        head_x, head_y = self._snake[0]
        tx, ty = self._snake_target

        def cand_dirs():
            # prioritize moving closer (Manhattan)
            opts = [0, 1, 2, 3]
            _shuffle_in_place(opts)
            opts.sort(key=lambda d: abs((head_x + (d == 3) - (d == 2)) - tx) + abs((head_y + (d == 1) - (d == 0)) - ty))
            return opts

        nd = self._snake_dir
        for d in cand_dirs():
            nx = head_x + (1 if d == 3 else (-1 if d == 2 else 0))
            ny = head_y + (1 if d == 1 else (-1 if d == 0 else 0))
            if nx <= 0 or nx >= WIDTH - 1 or ny <= 0 or ny >= PLAY_HEIGHT - 1:
                continue
            if self._snake_occ[ny * WIDTH + nx]:
                continue
            nd = d
            break

        self._snake_dir = nd
        nx = head_x + (1 if nd == 3 else (-1 if nd == 2 else 0))
        ny = head_y + (1 if nd == 1 else (-1 if nd == 0 else 0))

        # if blocked, restart demo
        if nx <= 0 or nx >= WIDTH - 1 or ny <= 0 or ny >= PLAY_HEIGHT - 1 or self._snake_occ[ny * WIDTH + nx]:
            self._snake_init()
            return

        self._snake.insert(0, (nx, ny))
        self._snake_occ[ny * WIDTH + nx] = 1
        display.set_pixel(nx, ny, 0, 255, 0)

        if (nx, ny) == self._snake_target:
            self._snake_len += 2
            self._snake_place_target()
            tx, ty = self._snake_target
            display.set_pixel(tx, ty, 255, 0, 0)

        if len(self._snake) > self._snake_len:
            tx, ty = self._snake.pop()
            self._snake_occ[ty * WIDTH + tx] = 0
            display.set_pixel(tx, ty, 0, 0, 0)

    def main_loop(self, joystick):
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
                    self._last_move = now
                elif d == JOYSTICK_RIGHT:
                    self.idx = (self.idx + 1) % len(self.demos)
                    self._reset_demo_state()
                    self._last_move = now

            if ticks_diff(now, last_frame) < frame_ms:
                sleep_ms(1)
                continue
            last_frame = now
            self._frame += 1

            demo = self.demos[self.idx]
            if not self._init:
                display.clear()
                draw_text_small(1, PLAY_HEIGHT, demo, 120, 120, 120)
                if demo == "LIFE":
                    for i in range(self._life_w * self._life_h):
                        self._life_cur[i] = 1 if random.randint(0, 99) < 18 else 0
                        self._life_prev[i] = 2  # force draw
                elif demo == "ANT":
                    # start with empty field
                    self._ant_cells = bytearray(self._ant_w * self._ant_h)
                    self._ant = [self._ant_w // 2, self._ant_h // 2, 0]
                    self._ant_prev = [self._ant[0], self._ant[1]]
                elif demo == "TRON":
                    self._tron_occ = bytearray(self._tron_w * self._tron_h)
                    self._tron_p1 = [self._tron_w // 3, self._tron_h // 2, 1, 0]
                    self._tron_p2 = [2 * self._tron_w // 3, self._tron_h // 2, -1, 0]
                    self._tron_prev1 = [self._tron_p1[0], self._tron_p1[1]]
                    self._tron_prev2 = [self._tron_p2[0], self._tron_p2[1]]
                    self._tron_occ[self._tron_p1[1] * self._tron_w + self._tron_p1[0]] = 1
                    self._tron_occ[self._tron_p2[1] * self._tron_w + self._tron_p2[0]] = 1
                    display.set_pixel(self._tron_p1[0], self._tron_p1[1], 255, 0, 0)
                    display.set_pixel(self._tron_p2[0], self._tron_p2[1], 0, 255, 0)
                else:  # SNAKE
                    self._snake_init()
                self._init = True

            if demo == "LIFE":
                self._life_step(self._life_w, self._life_h, self._life_cur, self._life_nxt)
                self._life_cur, self._life_nxt = self._life_nxt, self._life_cur
                self._life_draw_diffs(self._life_w, self._life_h, self._life_cur, self._life_prev)

            elif demo == "ANT":
                # do multiple steps per frame, draw only changed cell + ant
                for _ in range(10):
                    ax0, ay0 = self._ant[0], self._ant[1]
                    self._langton_step(self._ant_w, self._ant_h, self._ant_cells, self._ant)
                    # redraw flipped cell
                    i = ay0 * self._ant_w + ax0
                    if self._ant_cells[i]:
                        display.set_pixel(ax0, ay0, 50, 50, 255)
                    else:
                        display.set_pixel(ax0, ay0, 0, 0, 0)

                # erase previous ant marker (restore cell color)
                px, py = self._ant_prev
                i = py * self._ant_w + px
                if self._ant_cells[i]:
                    display.set_pixel(px, py, 50, 50, 255)
                else:
                    display.set_pixel(px, py, 0, 0, 0)
                # draw ant
                ax, ay, _d = self._ant
                if ay < PLAY_HEIGHT:
                    display.set_pixel(ax, ay, 255, 255, 0)
                self._ant_prev[0], self._ant_prev[1] = ax, ay

            elif demo == "TRON":
                # step a few times per frame
                for _ in range(2):
                    ok1 = self._tron_step(self._tron_w, self._tron_h, self._tron_occ, self._tron_p1)
                    ok2 = self._tron_step(self._tron_w, self._tron_h, self._tron_occ, self._tron_p2)
                    if not ok1 or not ok2:
                        # restart this demo
                        self._reset_demo_state()
                        break

                # convert old heads to trail
                display.set_pixel(self._tron_prev1[0], self._tron_prev1[1], 0, 90, 90)
                display.set_pixel(self._tron_prev2[0], self._tron_prev2[1], 0, 90, 90)

                # draw new heads
                display.set_pixel(self._tron_p1[0], self._tron_p1[1], 255, 0, 0)
                display.set_pixel(self._tron_p2[0], self._tron_p2[1], 0, 255, 0)
                self._tron_prev1[0], self._tron_prev1[1] = self._tron_p1[0], self._tron_p1[1]
                self._tron_prev2[0], self._tron_prev2[1] = self._tron_p2[0], self._tron_p2[1]

            else:  # SNAKE
                self._snake_step()

            maybe_collect(1)


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
    _LUT = [(int(math.cos(math.radians(a)) * 256), int(math.sin(math.radians(a)) * 256))
            for a in range(0, 360, _STEP)]

    def __init__(self):
        self.reset()

    def reset(self):
        self.terrain = self._make_terrain()

        self.pad_w = 10
        self.pad_x = random.randint(6, WIDTH - self.pad_w - 6)
        self.pad_y = self.terrain[self.pad_x]
        for x in range(self.pad_x, self.pad_x + self.pad_w):
            self.terrain[x] = self.pad_y

        self.x = float(WIDTH // 2)
        self.y = 8.0
        self.vx = 0.0
        self.vy = 0.0
        self.angle = 90

        self.fuel_max = 700
        self.fuel = self.fuel_max

        self.g = 0.10
        self.thrust = 0.22

        self.points = 0
        self.last_points_ms = ticks_ms()
        self.frame = 0

    def _make_terrain(self):
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
        angle_deg %= 360
        idx = (angle_deg // self._STEP) % (360 // self._STEP)
        return self._LUT[idx]

    def _angle_diff(self, a, b):
        d = (a - b + 180) % 360 - 180
        return abs(d)

    def _line(self, x0, y0, x1, y1, r, g, b):
        x0 = int(x0); y0 = int(y0); x1 = int(x1); y1 = int(y1)
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        sp = display.set_pixel

        while True:
            if 0 <= x0 < WIDTH and 0 <= y0 < PLAY_HEIGHT:
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

    def main_loop(self, joystick):
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
                        final = self.points + int(self.fuel) + 200
                        global_score = final
                        display.clear()
                        draw_text(4, 18, "LANDED", 0, 255, 0)
                        display_score_and_time(global_score)
                        sleep_ms(1500)
                        return
                    else:
                        global_score = self.points
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
        self.reset()

    def reset(self):
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
        x0 = int(x0); y0 = int(y0); x1 = int(x1); y1 = int(y1)
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        sp = display.set_pixel
        r, g, b = col

        while True:
            if 0 <= x0 < WIDTH and 0 <= y0 < PLAY_HEIGHT:
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

    def _spawn_enemy(self):
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

    def _fire_player(self):
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

        for deg in range(0, 360, 18):
            a = math.radians(deg)
            x = int(x0 + math.cos(a) * r)
            y = int(y0 + math.sin(a) * r)
            if 0 <= x < WIDTH and 0 <= y < PLAY_HEIGHT:
                sp(x, y, col[0], col[1], col[2])

    def _update_explosions_and_hits(self):
        for ex in self.explosions[:]:
            ex["r"] += ex["dr"]
            if ex["r"] >= ex["max"]:
                ex["dr"] = -1
            if ex["r"] <= 0 and ex["dr"] < 0:
                self.explosions.remove(ex)
                continue

            r2 = (ex["r"] + 1) * (ex["r"] + 1)
            exx = ex["x"]; exy = ex["y"]

            for em in self.enemy_missiles[:]:
                dx = em["x"] - exx
                dy = em["y"] - exy
                if dx * dx + dy * dy <= r2:
                    self.enemy_missiles.remove(em)
                    self.score += 10

    def _update_missiles(self):
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
                d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
                step = 1
                if d and ticks_diff(now, self._last_cross_move) >= self.cross_move_ms:
                    if d == JOYSTICK_LEFT:
                        self.cx = max(0, self.cx - step)
                    elif d == JOYSTICK_RIGHT:
                        self.cx = min(WIDTH - 1, self.cx + step)
                    elif d == JOYSTICK_UP:
                        self.cy = max(0, self.cy - step)
                    elif d == JOYSTICK_DOWN:
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
                    self.enemy_speed = min(self.max_enemy_speed, self.base_enemy_speed + self.level * 0.01)

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

# ======================================================================
#                              MENUS / FLOW
# ======================================================================

class GameOverMenu:
    """Simple menu shown after losing; choose retry or return to menu."""
    def __init__(self, joystick, score, best, best_name="---"):
        self.joystick = joystick
        self.score = score
        self.best = best
        self.best_name = best_name
        self.opts = ["RETRY", "MENU"]

    def run(self):
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
        self.joystick = Joystick()
        self.highscores = HighScores()
        self.game_classes = {
            "ASTRD": AsteroidGame,
            "BRKOUT": BreakoutGame,
            "FLAPPY": FlappyGame,
            "MAZE": MazeGame,
            "PONG": PongGame,
            "QIX": QixGame,
            "SIMON": SimonGame,
            "SNAKE": SnakeGame,
            "TETRIS": TetrisGame,
            "RTYPE": RTypeGame,
            "PACMAN": PacmanGame,
            "CAVEFL": CaveFlyGame,
            "PITFAL": PitfallGame,
            "LANDER": LunarLanderGame,
            "UFODEF": UFODefenseGame,
            "DEMOS": DemosGame,
        }
        keys = sorted(self.game_classes.keys())
        if "DEMOS" in keys:
            keys.remove("DEMOS")
            keys.insert(0, "DEMOS")
        self.sorted_games = keys

    def run_game_selector(self):
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
                    draw_text(8, 5 + i * 15, name, *col)

                    hs = self.highscores.best(name)
                    hn = self.highscores.best_name(name)
                    hs_str = str(hs) + " " + str(hn)
                    draw_text_small(WIDTH - len(hs_str) * 6, 5 + i * 15 + 8, hs_str, 120, 120, 0)

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
        global game_over, global_score

        while True:
            game_name = self.run_game_selector()

            # retry loop
            while True:
                game_over = False
                global_score = 0

                game = self.game_classes[game_name]()
                game.main_loop(self.joystick)

                if game_over:
                    best = self.highscores.best(game_name)
                    best_name = self.highscores.best_name(game_name)
                    if global_score > best:
                        initials = InitialsEntryMenu(self.joystick, global_score, best, best_name).run()
                        if initials:
                            self.highscores.update(game_name, global_score, initials)
                    # refresh best name in case initials were saved
                    best = self.highscores.best(game_name)
                    best_name = self.highscores.best_name(game_name)
                    choice = GameOverMenu(self.joystick, global_score, best, best_name).run()
                    if choice == "RETRY":
                        continue
                    else:
                        break
                else:
                    break

# ---------- Main ----------
def main():
    display.start()
    display.clear()
    display_score_and_time(0, force=True)

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

if __name__ == "__main__":
    main()

