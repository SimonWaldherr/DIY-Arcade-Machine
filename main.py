import hub75
import random
import time
import machine
import math
import gc

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
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(ms)
    else:
        time.sleep(ms / 1000)

def ticks_ms():
    return time.ticks_ms() if hasattr(time, "ticks_ms") else int(time.time() * 1000)

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
display = hub75.Hub75(WIDTH, HEIGHT)
rtc = machine.RTC()

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
    stack = [(x, y)]
    steps = 0
    while stack and steps < max_steps:
        x, y = stack.pop()
        if x < 0 or x >= GRID_W or y < 0 or y >= GRID_H:
            continue
        if get_grid_value(x, y) != 0:
            continue
        set_grid_value(x, y, accessible_mark)
        steps += 1
        stack.append((x + 1, y))
        stack.append((x - 1, y))
        stack.append((x, y + 1))
        stack.append((x, y - 1))
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
class Nunchuck:
    def __init__(self, i2c, poll=True, poll_interval=50):
        self.i2c = i2c
        self.address = 0x52
        self.buffer = bytearray(6)
        self.i2c.writeto(self.address, b"\xf0\x55")
        self.i2c.writeto(self.address, b"\xfb\x00")
        self.last_poll = ticks_ms()
        self.polling_threshold = poll_interval if poll else -1

    def update(self):
        self.i2c.writeto(self.address, b"\x00")
        self.i2c.readfrom_into(self.address, self.buffer)

    def __poll(self):
        if self.polling_threshold > 0 and ticks_diff(ticks_ms(), self.last_poll) > self.polling_threshold:
            self.update()
            self.last_poll = ticks_ms()

    def buttons(self):
        self.__poll()
        c_button = not (self.buffer[5] & 0x02)
        z_button = not (self.buffer[5] & 0x01)
        if c_button and z_button:
            raise RestartProgram()
        return c_button, z_button

    def joystick(self):
        self.__poll()
        return (self.buffer[0], self.buffer[1])

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
            return int(self.scores.get(game, 0) or 0)
        except Exception:
            return 0

    def update(self, game, score):
        score = int(score or 0)
        if score > self.best(game):
            self.scores[game] = score
            self.save()
            return True
        return False

# ======================================================================
#                                 GAMES
# ======================================================================

class SimonGame:
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
        # (Original behavior: tries to avoid immediate collision)
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

        self.snake.insert(0, (hx, hy))
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
        self.vy = -2

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

        # bird (2x2) — use integer y when drawing
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

            # flap: Z or UP
            d = joystick.read_direction([JOYSTICK_UP])
            if z_button or d == JOYSTICK_UP:
                self.flap()

            now = ticks_ms()
            if ticks_diff(now, last_frame) < frame_ms:
                sleep_ms(5)
                continue
            last_frame = now

            # physics (reduced gravity and cap)
            self.vy += 0.2
            if self.vy > 5:
                self.vy = 5
            self.by += self.vy

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

# ======================================================================
#                              MENUS / FLOW
# ======================================================================

class GameOverMenu:
    def __init__(self, joystick, score, best):
        self.joystick = joystick
        self.score = score
        self.best = best
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
                bs = "B" + str(self.best)
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
    def __init__(self):
        self.joystick = Joystick()
        self.highscores = HighScores()
        self.game_classes = {
            "ASTRD": AsteroidGame,
            "BRKOUT": BreakoutGame,
            "FLAPPY": FlappyGame,   # <- NEW
            "MAZE": MazeGame,
            "PONG": PongGame,
            "QIX": QixGame,
            "SIMON": SimonGame,
            "SNAKE": SnakeGame,
            "TETRIS": TetrisGame,
        }
        self.sorted_games = sorted(self.game_classes.keys())

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
                    hs_str = str(hs)
                    draw_text_small(WIDTH - len(hs_str) * 6, 5 + i * 15 + 8, hs_str, 120, 120, 120)

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

                # update highscore
                self.highscores.update(game_name, global_score)

                if game_over:
                    best = self.highscores.best(game_name)
                    choice = GameOverMenu(self.joystick, global_score, best).run()
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
            display.clear()
            draw_text(1, 20, "ERR", 255, 0, 0)
            sleep_ms(800)
            display.clear()
            maybe_collect(1)

if __name__ == "__main__":
    main()
