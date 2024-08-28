import hub75
import random
import time
import machine
from machine import ADC

# Constants
HEIGHT = 64
WIDTH = 64

# Initialize the display
display = hub75.Hub75(WIDTH, HEIGHT)

# Initialize ADC for joystick
adc0 = ADC(0)
adc1 = ADC(1)
adc2 = ADC(2)

# global variables
global_score = 0
last_game = None
game_over = False

# Color definitions for Simon game
colors_bright = [
    (255, 0, 0),   # Red
    (0, 255, 0),   # Green
    (0, 0, 255),   # Blue
    (255, 255, 0)  # Yellow
]

# Farben
tetris_black = (0, 0, 0)
tetris_white = (255, 255, 255)
tetris_colors = [
    (0, 255, 255),
    (255, 0, 0),
    (0, 255, 0),
    (0, 0, 255),
    (255, 255, 0),
    (255, 165, 0),
    (128, 0, 128),
]

# Spielfeldgröße (16x13 Blöcke)
grid_width = 16
grid_height = 13
block_size = 4  # Jeder Block ist 4x4 Pixel groß

# Tetrimino-Formen
tetriminos = [
    [[1, 1, 1, 1]],
    [[1, 1, 1], [0, 1, 0]],
    [[1, 1, 0], [0, 1, 1]],
    [[0, 1, 1], [1, 1, 0]],
    [[1, 1], [1, 1]],
    [[1, 1, 1], [1, 0, 0]],
    [[1, 1, 1], [0, 0, 1]],
]

colors = [(int(r * 0.5), int(g * 0.5), int(b * 0.5)) for r, g, b in colors_bright]
inactive_colors = [(int(r * 0.2), int(g * 0.2), int(b * 0.2)) for r, g, b in colors_bright]

# Game states for Simon
simon_sequence = []
user_sequence = []

# Snake game variables
score = 0
snake = [(32, 32)]
snake_length = 3
snake_direction = 'UP'
green_targets = []
text = ""

# Breakout variables
PADDLE_WIDTH = 10
PADDLE_HEIGHT = 2
BALL_SIZE = 2
BRICK_WIDTH = 8
BRICK_HEIGHT = 4
BRICK_ROWS = 5
BRICK_COLS = 8

# Joystick directions
JOYSTICK_UP = 'UP'
JOYSTICK_DOWN = 'DOWN'
JOYSTICK_LEFT = 'LEFT'
JOYSTICK_RIGHT = 'RIGHT'
JOYSTICK_UP_LEFT = 'UP-LEFT'
JOYSTICK_UP_RIGHT = 'UP-RIGHT'
JOYSTICK_DOWN_LEFT = 'DOWN-LEFT'
JOYSTICK_DOWN_RIGHT = 'DOWN-RIGHT'

# Character dictionary
char_dict = {'A': '3078ccccfccccc00', 'B': 'fc66667c6666fc00', 'C': '3c66c0c0c0663c00', 'D': 'f86c6666666cf800', 'E': 'fe6268786862fe00', 'F': 'fe6268786860f000', 'G': '3c66c0c0ce663e00', 'H': 'ccccccfccccccc00', 'I': '7830303030307800', 'J': '1e0c0c0ccccc7800', 'K': 'f6666c786c66f600', 'L': 'f06060606266fe00', 'M': 'c6eefefed6c6c600', 'N': 'c6e6f6decec6c600', 'O': '386cc6c6c66c3800', 'P': 'fc66667c6060f000', 'Q': '78ccccccdc781c00', 'R': 'fc66667c6c66f600', 'S': '78cce0380ccc7800', 'T': 'fcb4303030307800', 'U': 'ccccccccccccfc00', 'V': 'cccccccccc783000', 'W': 'c6c6c6d6feeec600', 'X': 'c6c66c38386cc600', 'Y': 'cccccc7830307800', 'Z': 'fec68c183266fe00', 'a': '0000780c7ccc7600', 'b': 'e060607c6666dc00', 'c': '000078ccc0cc7800', 'd': '1c0c0c7ccccc7600', 'e': '000078ccfcc07800', 'f': '386c60f06060f000', 'g': '000076cccc7c0cf8', 'h': 'e0606c766666e600', 'i': '3000703030307800', 'j': '0c000c0c0ccccc78', 'k': 'e060666c786ce600', 'l': '7030303030307800', 'm': '0000ccfefed6c600', 'n': '0000f8cccccccc00', 'o': '000078cccccc7800', 'p': '0000dc667c60f0', 'q': '000076cccc7c0c1e', 'r': '00009c766660f000', 's': '00007cc0780cf800', 't': '10307c3030341800', 'u': '0000cccccccc7600', 'v': '0000cccccc783000', 'w': '0000c6c6d6fe6c00', 'x': '0000c66c386cc600', 'y': '0000cccccc7c0cf8', 'z': '0000fc983064fc00', '0': '78ccdcfceccc7c00', '1': '307030303030fc00', '2': '78cc0c3860ccfc00', '3': '78cc0c380ccc7800', '4': '1c3c6cccfe0c1e00', '5': 'fcc0f80c0ccc7800', '6': '3860c0f8cccc7800', '7': 'fccc0c1830303000', '8': '78cccc78cccc7800', '9': '78cccc7c0c187000', '!': '3078783030003000', '#': '6c6cfe6cfe6c6c00', '$': '307cc0780cf83000', '%': '00c6cc183066c600', '&': '386c3876dccc7600', '?': '78cc0c1830003000', ' ': '0000000000000000', '.': '0000000000003000', ':': '0030000000300000','(': '0c18303030180c00', ')': '6030180c18306000', '[': '78c0c0c0c0c07800', ']': 'c06060606060c000', '{': '0c18306030180c00', '}': '6030180c18306000', '<': '0c18306030180c00', '>': '6030180c18306000', '=': '0000fc0000fc0000', '+': '0000187e18180000', '-': '0000007e00000000', '*': 'c66c3810386cc600', '/': '0000060c18306000', '\\': '00006030180c0c00', '_': '00000000000000fe', '|': '1818181818181800', ';': '0000003018003000', ',': '0000000000303000', "'": '3030300000000000', '"': 'cccc000000000000', '`': '0c18300000000000', '@': '3c66dececec07e00', '^': '183c666600000000', '█': 'ffffffffffffffff'}

nums = {
    '0': ["01110", "10001", "10001", "10001", "01110"],
    '1': ["00100", "01100", "00100", "00100", "01110"],
    '2': ["11110", "00001", "01110", "10000", "11111"],
    '3': ["11110", "00001", "00110", "00001", "11110"],
    '4': ["10000", "10010", "10010", "11111", "00010"],
    '5': ["11111", "10000", "11110", "00001", "11110"],
    '6': ["01110", "10000", "11110", "10001", "01110"],
    '7': ["11111", "00010", "00100", "01000", "10000"],
    '8': ["01110", "10001", "01110", "10001", "01110"],
    '9': ["01110", "10001", "01111", "00001", "01110"],
    ' ': ["00000", "00000", "00000", "00000", "00000"],
    '.': ["00000", "00000", "00000", "00000", "00001"],
    ':': ["00000", "00100", "00000", "00100", "00000"],
    '/': ["00001", "00010", "00100", "01000", "10000"],
    '-': ["00000", "00000", "11111", "00000", "00000"],
    '=': ["00000", "11111", "00000", "11111", "00000"],
    '+': ["00000", "00100", "01110", "00100", "00000"],
    '*': ["00000", "10101", "01110", "10101", "00000"],
    '(': ["00010", "00100", "00100", "00100", "00010"],
    ')': ["00100", "00010", "00010", "00010", "00100"]
}

# Helper functions
def draw_char(x, y, char, r, g, b):
    if char in char_dict:
        hex_string = char_dict[char]
        for row in range(8):
            hex_value = hex_string[row * 2:row * 2 + 2]
            bin_value = f"{int(hex_value, 16):08b}"
            for col in range(8):
                if bin_value[col] == '1':
                    display.set_pixel(x + col, y + row, r, g, b)

def draw_text(x, y, text, r, g, b):
    offset_x = x
    for char in text:
        draw_char(offset_x, y, char, r, g, b)
        offset_x += 9

def draw_char_small(x, y, char, r, g, b):
    if char in nums:
        matrix = nums[char]
        for row in range(5):
            for col in range(5):
                if matrix[row][col] == '1':
                    display.set_pixel(x + col, y + row, r, g, b)

def draw_text_small(x, y, text, r, g, b):
    offset_x = x
    for char in text:
        draw_char_small(offset_x, y, char, r, g, b)
        offset_x += 6

def draw_rect(x1, y1, x2, y2, r, g, b):
    for x in range(min(x1, x2), max(x1, x2) + 1):
        for y in range(min(y1, y2), max(y1, y2) + 1):
            display.set_pixel(x, y, r, g, b)

def display_score_and_time(score):
    global text, global_score
    year, month, day, wd, hour, minute, second, _ = rtc.datetime()
    time_str = "{:02}:{:02}".format(hour, minute)
    global_score = score
    score_str = str(score)
    time_x = WIDTH - (len(time_str) * 6)
    time_y = HEIGHT - 6
    score_x = 1
    score_y = HEIGHT - 6
    if text != score_str + " " + time_str:
        text = score_str + " " + time_str
        draw_rect(score_x, score_y, WIDTH, score_y + 5, 0, 0, 0)
    draw_text_small(score_x, score_y, score_str, 255, 255, 255)
    draw_text_small(time_x, time_y, time_str, 255, 255, 255)

# Global variable for the grid
grid = bytearray(WIDTH * HEIGHT)

def initialize_grid():
    global grid
    grid = bytearray(WIDTH * HEIGHT)

def get_grid_value(x, y):
    return grid[y * WIDTH + x]

def set_grid_value(x, y, value):
    grid[y * WIDTH + x] = value

def draw_line_on_grid():
    startpoint_x = random.randint(BORDER+1, WIDTH - BORDER - 1)
    startpoint_y = 0

    down_for = random.randint(1, HEIGHT - 15)
    for i in range(down_for):
        set_grid_value(startpoint_x, startpoint_y + i, 1)
        display.set_pixel(startpoint_x, startpoint_y + i, 255, 255, 255)

    left_for = random.randint(1, startpoint_x - BORDER)
    for i in range(left_for):
        set_grid_value(startpoint_x - i, startpoint_y + down_for, 1)
        display.set_pixel(startpoint_x - i, startpoint_y + down_for, 255, 255, 255)

    # Draw line down to bottom
    down_for_2 = HEIGHT - (startpoint_y + down_for)
    for i in range(down_for_2):
        set_grid_value(startpoint_x - left_for, startpoint_y + down_for + i, 1)
        display.set_pixel(startpoint_x - left_for, startpoint_y + down_for + i, 255, 255, 255)

    # Define random point x/y for enemy and check if it is on the line
    for _ in range(10):
        enemy_x = random.randint(BORDER, WIDTH - BORDER - 1)
        enemy_y = random.randint(BORDER, HEIGHT - BORDER - 1)
        if get_grid_value(enemy_x, enemy_y) == 1:
            continue
        else:
            break

    display.set_pixel(enemy_x, enemy_y, 255, 0, 0)
    return enemy_x, enemy_y

@micropython.native
def floodfill(x, y, accessible_mark, non_accessible_mark, r, g, b, max_steps=8000):
    stack = [(x, y)]
    steps = 0

    while stack and steps < max_steps:
        x, y = stack.pop(0)
        grid_value = get_grid_value(x, y)
        
        if x < 0 or x >= WIDTH or y < 0 or y >= HEIGHT:
            continue
        if grid_value != 0:
            continue

        set_grid_value(x, y, accessible_mark)
        #display.set_pixel(x, y, r, g, b)

        steps += 1

        # Add neighboring pixels to the stack
        if x + 1 < WIDTH:
            stack.append((x + 1, y))
        if x - 1 >= 0:
            stack.append((x - 1, y))
        if y + 1 < HEIGHT:
            stack.append((x, y + 1))
        if y - 1 >= 0:
            stack.append((x, y - 1))

    return len(stack) > 0  # Indicates if there's still work left


rtc = machine.RTC()

# Nunchuck class
class Nunchuck:
    def __init__(self, i2c, poll=True, poll_interval=50):
        self.i2c = i2c
        self.address = 0x52
        self.buffer = bytearray(6)  # Puffer zur Speicherung der Sensordaten

        # Initialisierungssequenz für den Nunchuk
        self.i2c.writeto(self.address, b'\xf0\x55')
        self.i2c.writeto(self.address, b'\xfb\x00')

        # Zeitstempel der letzten Polling-Aktualisierung
        self.last_poll = time.ticks_ms()
        
        # Polling-Intervall in Millisekunden
        self.polling_threshold = poll_interval if poll else -1

    def update(self):
        self.i2c.writeto(self.address, b'\x00')
        self.i2c.readfrom_into(self.address, self.buffer)

    def __poll(self):
        if self.polling_threshold > 0 and time.ticks_diff(time.ticks_ms(), self.last_poll) > self.polling_threshold:
            self.update()
            self.last_poll = time.ticks_ms()

    def accelerator(self):
        self.__poll()
        return (
            (self.buffer[2] << 2) + ((self.buffer[5] & 0x0C) >> 2),
            (self.buffer[3] << 2) + ((self.buffer[5] & 0x30) >> 4),
            (self.buffer[4] << 2) + ((self.buffer[5] & 0xC0) >> 6)
        )

    def buttons(self):
        self.__poll()
        return (
            not (self.buffer[5] & 0x02),  # C-Taste
            not (self.buffer[5] & 0x01)   # Z-Taste
        )

    def joystick(self):
        self.__poll()
        return (self.buffer[0], self.buffer[1])

    def joystick_left(self):
        self.__poll()
        return self.buffer[0] < 55

    def joystick_right(self):
        self.__poll()
        return self.buffer[0] > 200

    def joystick_up(self):
        self.__poll()
        return self.buffer[1] > 200

    def joystick_down(self):
        self.__poll()
        return self.buffer[1] < 55

    def joystick_center(self):
        self.__poll()
        return 100 < self.buffer[0] < 155 and 100 < self.buffer[1] < 155

    def joystick_x(self):
        self.__poll()
        return (self.buffer[0] >> 2) - 34

    def joystick_y(self):
        self.__poll()
        return (self.buffer[1] >> 2) - 34

    def is_shaking(self):
        x, y, z = self.accelerator()
        return max(x, y, z) > 800  # Schwellenwert für Erkennung

# Joystick class
class Joystick:
    def __init__(self, adc_x, adc_y, adc_button):
        self.joystick_mode = "analog"
        self.joystick_mode = "i2c"
        # comment out the mode you don't want to use


        if self.joystick_mode == "i2c":
            self.i2c = machine.I2C(0, scl=machine.Pin(21), sda=machine.Pin(20))
            self.nunchuck = Nunchuck(i2c)
        elif self.joystick_mode == "analog":
            self.adc_x = adc_x
            self.adc_y = adc_y
            self.adc_button = adc_button
            self.last_direction = None
            self.last_read_time = 0
            self.debounce_interval = 150


    def read_direction(self, possible_directions, debounce=True):
        if self.joystick_mode == "i2c":
            x, y = self.nunchuck.joystick()
            if x < 100 and y < 100 and JOYSTICK_DOWN_LEFT in possible_directions:
                return JOYSTICK_DOWN_LEFT
            elif x > 150 and y < 100 and JOYSTICK_DOWN_RIGHT in possible_directions:
                return JOYSTICK_DOWN_RIGHT
            elif x < 100 and y > 150 and JOYSTICK_UP_LEFT in possible_directions:
                return JOYSTICK_UP_LEFT
            elif x > 150 and y > 150 and JOYSTICK_UP_RIGHT in possible_directions:
                return JOYSTICK_UP_RIGHT
            elif x < 100 and JOYSTICK_LEFT in possible_directions:
                return JOYSTICK_LEFT
            elif x > 150 and JOYSTICK_RIGHT in possible_directions:
                return JOYSTICK_RIGHT
            elif y < 100 and JOYSTICK_DOWN in possible_directions:
                return JOYSTICK_DOWN
            elif y > 150 and JOYSTICK_UP in possible_directions:
                return JOYSTICK_UP
            else:
                return None
            

        current_time = time.ticks_ms()

        if debounce and current_time - self.last_read_time < self.debounce_interval:
            return self.last_direction

        value_x = self.adc_x.read_u16() - 30039
        value_y = self.adc_y.read_u16() - 28919

        #print(value_x, value_y)

        threshold = 15000  # Threshold for detecting direction

        direction = None
        if value_y < -threshold and value_x < -threshold and JOYSTICK_DOWN_LEFT in possible_directions:
            direction = JOYSTICK_DOWN_LEFT #JOYSTICK_UP_LEFT
        elif value_y < -threshold and value_x > threshold and JOYSTICK_UP_LEFT in possible_directions:
            direction = JOYSTICK_UP_LEFT #JOYSTICK_UP_RIGHT
        elif value_y > threshold and value_x < -threshold and JOYSTICK_DOWN_RIGHT in possible_directions:
            direction = JOYSTICK_DOWN_RIGHT #JOYSTICK_DOWN_LEFT
        elif value_y > threshold and value_x > threshold and JOYSTICK_UP_RIGHT in possible_directions:
            direction = JOYSTICK_UP_RIGHT #JOYSTICK_DOWN_RIGHT
        elif value_y < -threshold and JOYSTICK_LEFT in possible_directions:
            direction = JOYSTICK_LEFT #JOYSTICK_UP
        elif value_y > threshold and JOYSTICK_RIGHT in possible_directions:
            direction = JOYSTICK_RIGHT #JOYSTICK_DOWN
        elif value_x < -threshold and JOYSTICK_DOWN in possible_directions:
            direction = JOYSTICK_DOWN #JOYSTICK_LEFT
        elif value_x > threshold and JOYSTICK_UP in possible_directions:
            direction = JOYSTICK_UP #JOYSTICK_RIGHT

        if debounce:
            self.last_read_time = current_time

        return direction

    def is_pressed(self):
        if self.joystick_mode == "i2c":
            _, z = self.nunchuck.buttons()
            return z
        return self.adc_button.read_u16() < 100


# Color conversion function
def hsb_to_rgb(hue, saturation, brightness):
    hue_normalized = (hue % 360) / 60
    hue_index = int(hue_normalized)
    hue_fraction = hue_normalized - hue_index

    value1 = brightness * (1 - saturation)
    value2 = brightness * (1 - saturation * hue_fraction)
    value3 = brightness * (1 - saturation * (1 - hue_fraction))

    red, green, blue = [
        (brightness, value3, value1),
        (value2, brightness, value1),
        (value1, brightness, value3),
        (value1, value2, brightness),
        (value3, value1, brightness),
        (brightness, value1, value2)
    ][hue_index]

    return int(red * 255), int(green * 255), int(blue * 255)

# Game classes
class SimonGame:
    def __init__(self):
        self.sequence = []
        self.user_input = []

    def draw_quad_screen(self):
        draw_rect(0, 0, WIDTH // 2 - 1, (HEIGHT-6) // 2 - 1, *inactive_colors[0])
        draw_rect(WIDTH // 2, 0, WIDTH - 1, (HEIGHT-6) // 2 - 1, *inactive_colors[1])
        draw_rect(0, (HEIGHT-6) // 2, WIDTH // 2 - 1, (HEIGHT-6) - 1, *inactive_colors[2])
        draw_rect(WIDTH // 2, (HEIGHT-6) // 2, WIDTH - 1, (HEIGHT-6) - 1, *inactive_colors[3])

    def flash_color(self, index, duration=0.5):
        x, y = index % 2, index // 2
        draw_rect(x * WIDTH // 2, y * (HEIGHT-6) // 2, (x + 1) * WIDTH // 2 - 1, (y + 1) * (HEIGHT-6) // 2 - 1, *colors[index])
        time.sleep(duration)
        draw_rect(x * WIDTH // 2, y * (HEIGHT-6) // 2, (x + 1) * WIDTH // 2 - 1, (y + 1) * (HEIGHT-6) // 2 - 1, *inactive_colors[index])

    def play_sequence(self):
        for color in self.sequence:
            self.flash_color(color)
            time.sleep(0.5)

    def get_user_input(self, joystick):
        while True:
            direction = joystick.read_direction([JOYSTICK_UP_LEFT, JOYSTICK_UP_RIGHT, JOYSTICK_DOWN_LEFT, JOYSTICK_DOWN_RIGHT])
            if direction:
                return direction
            time.sleep(0.1)

    def translate_joystick_to_color(self, direction):
        if direction == JOYSTICK_UP_LEFT:
            return 0
        elif direction == JOYSTICK_UP_RIGHT:
            return 1
        elif direction == JOYSTICK_DOWN_LEFT:
            return 2
        elif direction == JOYSTICK_DOWN_RIGHT:
            return 3
        return None

    def check_user_sequence(self):
        return self.user_input == self.sequence[:len(self.user_input)]

    def start_game(self):
        self.sequence = []
        self.user_input = []
        self.draw_quad_screen()

    def main_loop(self, joystick):
        global global_score, game_over
        game_over = False

        self.start_game()
        while not game_over:
            c_button, _ = joystick.nunchuck.buttons()
            if c_button:  # C-Button beendet das Spiel
                game_over = True
            
            self.sequence.append(random.randint(0, 3))
            display_score_and_time(len(self.sequence) - 1)
            self.play_sequence()
            self.user_input = []

            for _ in range(len(self.sequence)):
                direction = self.get_user_input(joystick)
                selected_color = self.translate_joystick_to_color(direction)
                if selected_color is not None:
                    self.flash_color(selected_color, 0.2)
                    self.user_input.append(selected_color)
                    if not self.check_user_sequence():
                        global_score = len(self.sequence) - 1
                        game_over = True
                        #GameOverMenu().run_game_over_menu()
                        return
                else:
                    print("Invalid input")
                    break

            time.sleep(1)

class SnakeGame:
    def __init__(self):
        self.snake = [(32, 32)]
        self.snake_length = 3
        self.snake_direction = 'UP'
        self.score = 0
        self.green_targets = []
        self.target = self.random_target()

    def restart_game(self):
        self.snake = [(32, 32)]
        self.snake_length = 3
        self.snake_direction = 'UP'
        self.score = 0
        self.green_targets = []
        display.clear()
        self.place_target()

    def random_target(self):
        return (random.randint(1, WIDTH - 2), random.randint(1, HEIGHT - 8))

    def place_target(self):
        self.target = self.random_target()
        display.set_pixel(self.target[0], self.target[1], 255, 0, 0)

    def place_green_target(self):
        x, y = random.randint(1, WIDTH - 2), random.randint(1, HEIGHT - 8)
        self.green_targets.append((x, y, 256))
        display.set_pixel(x, y, 0, 255, 0)

    def update_green_targets(self):
        new_green_targets = []
        for x, y, lifespan in self.green_targets:
            if lifespan > 1:
                new_green_targets.append((x, y, lifespan - 1))
            else:
                display.set_pixel(x, y, 0, 0, 0)
        self.green_targets = new_green_targets

    def check_self_collision(self):
        global global_score, game_over
        head_x, head_y = self.snake[0]
        body = self.snake[1:]
        potential_moves = {
            'UP': (head_x, head_y - 1),
            'DOWN': (head_x, head_y + 1),
            'LEFT': (head_x - 1, head_y),
            'RIGHT': (head_x + 1, head_y)
        }
        safe_moves = {dir: pos for dir, pos in potential_moves.items() if pos not in body}
        if potential_moves[self.snake_direction] not in safe_moves.values():
            if safe_moves:
                self.snake_direction = random.choice(list(safe_moves.keys()))
            else:
                global_score = self.score
                game_over = True
                #GameOverMenu().run_game_over_menu()
                return

    def update_snake_position(self):
        head_x, head_y = self.snake[0]
        if self.snake_direction == 'UP':
            head_y -= 1
        elif self.snake_direction == 'DOWN':
            head_y += 1
        elif self.snake_direction == 'LEFT':
            head_x -= 1
        elif self.snake_direction == 'RIGHT':
            head_x += 1

        head_x %= WIDTH
        head_y %= HEIGHT

        self.snake.insert(0, (head_x, head_y))
        if len(self.snake) > self.snake_length:
            tail = self.snake.pop()
            display.set_pixel(tail[0], tail[1], 0, 0, 0)

    def check_target_collision(self):
        head_x, head_y = self.snake[0]
        if (head_x, head_y) == self.target:
            self.snake_length += 2
            self.place_target()
            self.score += 1

    def check_green_target_collision(self):
        head_x, head_y = self.snake[0]
        for x, y, lifespan in self.green_targets:
            if (head_x, head_y) == (x, y):
                self.snake_length = max(self.snake_length // 2, 2)
                self.green_targets.remove((x, y, lifespan))
                display.set_pixel(x, y, 0, 0, 0)

    def draw_snake(self):
        hue = 0
        for idx, (x, y) in enumerate(self.snake[:self.snake_length]):
            hue = (hue + 5) % 360
            r, g, b = hsb_to_rgb(hue, 1, 1)
            display.set_pixel(x, y, r, g, b)
        for idx in range(self.snake_length, len(self.snake)):
            x, y = self.snake[idx]
            display.set_pixel(x, y, 0, 0, 0)

    def main_loop(self, joystick):
        global game_over
        game_over = False
        self.restart_game()
        step_counter = 0

        while not game_over:
            c_button, _ = joystick.nunchuck.buttons()
            if c_button:  # C-Button beendet das Spiel
                game_over = True

            step_counter += 1

            if step_counter % 1024 == 0:
                self.place_green_target()
            self.update_green_targets()

            direction = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
            if direction:
                self.snake_direction = direction

            self.check_self_collision()
            self.update_snake_position()
            self.check_target_collision()
            self.check_green_target_collision()
            self.draw_snake()
            display_score_and_time(self.score)

            time.sleep(max(0.03, (0.09 - max(0.01, self.snake_length / 300))))

class PongGame:
    def __init__(self):
        self.paddle_height = 8
        self.paddle_speed = 2
        self.ball_speed = [1, 1]
        self.ball_position = [WIDTH // 2, HEIGHT // 2]
        self.left_paddle = HEIGHT // 2 - self.paddle_height // 2
        self.right_paddle = HEIGHT // 2 - self.paddle_height // 2
        self.prev_left_score = 0
        self.left_score = 0
        self.lives = 3

    def draw_paddles(self):
        for y in range(HEIGHT):
            display.set_pixel(0, y, 0, 0, 0)
            display.set_pixel(WIDTH - 1, y, 0, 0, 0)

        for y in range(self.left_paddle, self.left_paddle + self.paddle_height):
            display.set_pixel(0, y, 255, 255, 255)
        for y in range(self.right_paddle, self.right_paddle + self.paddle_height):
            display.set_pixel(WIDTH - 1, y, 255, 255, 255)

    def draw_ball(self):
        display.set_pixel(self.ball_position[0], self.ball_position[1], 255, 255, 255)

    def clear_ball(self):
        display.set_pixel(self.ball_position[0], self.ball_position[1], 0, 0, 0)

    def update_ball(self):
        global global_score, game_over
        self.clear_ball()
        self.ball_position[0] += self.ball_speed[0]
        self.ball_position[1] += self.ball_speed[1]

        if self.ball_position[1] <= 0 or self.ball_position[1] >= HEIGHT - 1:
            self.ball_speed[1] = -self.ball_speed[1]

        if self.ball_position[0] == 1 and self.left_paddle <= self.ball_position[1] < self.left_paddle + self.paddle_height:
            self.ball_speed[0] = -self.ball_speed[0]
            self.left_score += 1
        elif self.ball_position[0] == WIDTH - 2 and self.right_paddle <= self.ball_position[1] < self.right_paddle + self.paddle_height:
            self.ball_speed[0] = -self.ball_speed[0]

        if self.ball_position[0] <= 0:
            self.left_score = 0
            self.lives -= 1
            if self.lives == 0:
                game_over = True
                #GameOverMenu().run_game_over_menu()
                return
            self.reset_ball()
        elif self.ball_position[0] >= WIDTH - 1:
            self.left_score += 10
            self.reset_ball()

        global_score = self.left_score
        self.draw_ball()

    def reset_ball(self):
        self.ball_position = [WIDTH // 2, HEIGHT // 2]
        self.ball_speed = [random.choice([-1, 1]), random.choice([-1, 1])]

    def update_paddles(self, joystick):
        direction = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN])
        if direction == JOYSTICK_UP:
            self.left_paddle = max(self.left_paddle - self.paddle_speed, 0)
        elif direction == JOYSTICK_DOWN:
            self.left_paddle = min(self.left_paddle + self.paddle_speed, HEIGHT - self.paddle_height)

        if self.ball_position[1] < self.right_paddle + self.paddle_height // 2:
            self.right_paddle = max(self.right_paddle - self.paddle_speed, 0)
        elif self.ball_position[1] > self.right_paddle + self.paddle_height // 2:
            self.right_paddle = min(self.right_paddle + self.paddle_speed, HEIGHT - self.paddle_height)

    def main_loop(self, joystick):
        global game_over
        game_over = False
        self.reset_ball()
        draw_rect(0, 0, WIDTH, HEIGHT, 0, 0, 0)
        while not game_over:
            c_button, _ = joystick.nunchuck.buttons()
            if c_button:  # C-Button beendet das Spiel
                game_over = True

            self.update_paddles(joystick)
            self.update_ball()
            self.draw_paddles()
            if self.left_score != self.prev_left_score:
                display_score_and_time(self.left_score)
                self.prev_left_score = self.left_score
            time.sleep(0.05)


# Breakout game class
class BreakoutGame:
    def __init__(self):
        # Paddle and ball positions
        self.paddle_x = (WIDTH - PADDLE_WIDTH) // 2
        self.paddle_y = HEIGHT - PADDLE_HEIGHT
        self.ball_x = WIDTH // 2
        self.ball_y = HEIGHT // 2

        # Ball direction
        self.ball_dx = 1
        self.ball_dy = -1

        # Bricks
        self.bricks = self.create_bricks()

        # Game variables
        self.score = 0
        self.paddle_speed = 2

        display.clear()

    def create_bricks(self):
        bricks = []
        for row in range(BRICK_ROWS):
            for col in range(BRICK_COLS):
                bricks.append((col * (BRICK_WIDTH + 1) + 1, row * (BRICK_HEIGHT + 1)))
        return bricks

    def draw_paddle(self):
        for x in range(self.paddle_x, self.paddle_x + PADDLE_WIDTH):
            for y in range(self.paddle_y, self.paddle_y + PADDLE_HEIGHT):
                display.set_pixel(x, y, 255, 255, 255)

    def clear_paddle(self):
        for x in range(self.paddle_x, self.paddle_x + PADDLE_WIDTH):
            for y in range(self.paddle_y, self.paddle_y + PADDLE_HEIGHT):
                display.set_pixel(x, y, 0, 0, 0)

    def draw_ball(self):
        #display.set_pixel(self.ball_x, self.ball_y, 255, 255, 255)
        # 2x2 ball
        display.set_pixel(self.ball_x, self.ball_y, 255, 255, 255)
        display.set_pixel(self.ball_x + 1, self.ball_y, 255, 255, 255)
        display.set_pixel(self.ball_x, self.ball_y + 1, 255, 255, 255)
        display.set_pixel(self.ball_x + 1, self.ball_y + 1, 255, 255, 255)

    def clear_ball(self):
        #display.set_pixel(self.ball_x, self.ball_y, 0, 0, 0)
        # 2x2 ball
        display.set_pixel(self.ball_x, self.ball_y, 0, 0, 0)
        display.set_pixel(self.ball_x + 1, self.ball_y, 0, 0, 0)
        display.set_pixel(self.ball_x, self.ball_y + 1, 0, 0, 0)
        display.set_pixel(self.ball_x + 1, self.ball_y + 1, 0, 0, 0)

    def draw_bricks(self):
        for x, y in self.bricks:
            hue = (y) * 360 // (BRICK_ROWS * BRICK_COLS)
            r, g, b = hsb_to_rgb(hue, 1, 1)

            for dx in range(BRICK_WIDTH):
                for dy in range(BRICK_HEIGHT):
                    display.set_pixel(x + dx, y + dy, r, g, b)

    def clear_bricks(self):
        display.clear()

    def update_ball(self):
        global game_over
        self.clear_ball()
        self.ball_x += self.ball_dx
        self.ball_y += self.ball_dy

        # Check collision with walls
        if self.ball_x <= 0 or self.ball_x >= WIDTH - 1:
            self.ball_dx = -self.ball_dx

        # Check collision with paddle
        if self.ball_y <= 1:
            self.ball_dy = -self.ball_dy

        # Check collision with paddle
        if self.ball_y >= HEIGHT - PADDLE_HEIGHT -2:
            if self.paddle_x <= self.ball_x <= self.paddle_x + PADDLE_WIDTH:
                self.ball_dy = -self.ball_dy

        if self.ball_y >= HEIGHT:
            game_over = True
            #GameOverMenu().run_game_over_menu()
            return

        self.draw_ball()

    def check_collision_with_bricks(self):
        global global_score
        for brick in self.bricks:
            bx, by = brick
            if bx <= self.ball_x < bx + BRICK_WIDTH and by <= self.ball_y < by + BRICK_HEIGHT:
                self.clear_ball()
                self.ball_dy = -self.ball_dy
                self.bricks.remove(brick)
                self.score += 10
                global_score = self.score
                self.clear_bricks()
                self.draw_bricks()
                break

    def update_paddle(self, joystick):
        direction = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT])
        if direction == JOYSTICK_LEFT:
            self.clear_paddle()
            self.paddle_x = max(self.paddle_x - self.paddle_speed, 0)
        elif direction == JOYSTICK_RIGHT:
            self.clear_paddle()
            self.paddle_x = min(self.paddle_x + self.paddle_speed, WIDTH - PADDLE_WIDTH)
        self.draw_paddle()

    def main_loop(self, joystick):
        global game_over
        game_over = False
        display.clear()
        self.draw_bricks()
        while not game_over:
            c_button, _ = joystick.nunchuck.buttons()
            if c_button:  # C-Button beendet das Spiel
                game_over = True

            self.update_ball()
            self.check_collision_with_bricks()
            self.update_paddle(joystick)
            display_score_and_time(self.score)
            if self.score == BRICK_ROWS * BRICK_COLS * 10:
                display.clear()
                draw_text(10, 5, "YOU", 255, 255, 255)
                draw_text(10, 20, "WON", 255, 255, 255)
                time.sleep(3)
                break
            elif self.score < 60:
                time.sleep(0.05)
            elif self.score < 120:
                time.sleep(0.03)
            else:
                time.sleep(0.01)

class QixGame:
    def __init__(self):
        self.player_x = 0
        self.player_y = 0
        self.opponent_x = 0
        self.opponent_y = 0
        self.opponent_dx = 1
        self.opponent_dy = 1
        self.occupied_percentage = 0
        self.height = HEIGHT - 7
        self.width = WIDTH
        
        # prev player position type (grid value)
        self.prev_player_pos = 1

        # grid values:
        # 0 = empty
        # 1 = line
        # 2 = floodfill
        # 3 = enemy
        # 4 = temp line

    def initialize_game(self):
        display.clear()
        initialize_grid()
        self.draw_frame()
        self.place_player()
        self.place_opponent()

    def draw_frame(self):
        # Draw a frame around the play area
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
        # Place the player at a random position on the edge
        edge_positions = [(x, 0) for x in range(self.width)] + \
                         [(x, self.height - 1) for x in range(self.width)] + \
                         [(0, y) for y in range(self.height)] + \
                         [(self.width - 1, y) for y in range(self.height)]
        self.player_x, self.player_y = random.choice(edge_positions)
        display.set_pixel(self.player_x, self.player_y, 0, 255, 0)

    def place_opponent(self):
        # Place the opponent at a random position inside the playfield
        self.opponent_x, self.opponent_y = random.randint(1, self.width - 2), random.randint(1, self.height - 2)
        set_grid_value(self.opponent_x, self.opponent_y, 3)
        display.set_pixel(self.opponent_x, self.opponent_y, 255, 0, 0)

    def move_opponent(self):
        global game_over
        # Move the opponent and bounce off the boundaries
        next_x = self.opponent_x + self.opponent_dx
        next_y = self.opponent_y + self.opponent_dy

        # Check for collision in the x direction
        if get_grid_value(next_x, self.opponent_y) == 1 or get_grid_value(next_x, self.opponent_y) == 2:
            self.opponent_dx = -self.opponent_dx

        # Check for collision in the y direction
        if get_grid_value(self.opponent_x, next_y) == 1 or get_grid_value(self.opponent_x, next_y) == 2:
            self.opponent_dy = -self.opponent_dy

        # check for collision with player or line and exit
        if get_grid_value(next_x, next_y) == 4 or (next_x == self.player_x and next_y == self.player_y):
            game_over = True
            #GameOverMenu().run_game_over_menu()
            return

        # Clear current position
        set_grid_value(self.opponent_x, self.opponent_y, 0)
        display.set_pixel(self.opponent_x, self.opponent_y, 0, 0, 0)

        # Update position
        self.opponent_x += self.opponent_dx
        self.opponent_y += self.opponent_dy
        display.set_pixel(self.opponent_x, self.opponent_y, 255, 0, 0)


    def move_player(self, joystick):
        # Handle player movement based on joystick input
        direction = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
        if direction:
            new_x, new_y = self.player_x, self.player_y
            if direction == JOYSTICK_UP:
                new_y -= 1
            elif direction == JOYSTICK_DOWN:
                new_y += 1
            elif direction == JOYSTICK_LEFT:
                new_x -= 1
            elif direction == JOYSTICK_RIGHT:
                new_x += 1

            if 0 <= new_x < self.width and 0 <= new_y < self.height:
                if get_grid_value(new_x, new_y) == 0:
                    set_grid_value(new_x, new_y, 4)
                    display.set_pixel(new_x, new_y, 0, 255, 0)
                    self.prev_player_pos = 0
                elif get_grid_value(new_x, new_y) == 1:
                    if self.prev_player_pos == 0:
                        self.close_area(new_x, new_y)
                    self.prev_player_pos = 1

                self.player_x, self.player_y = new_x, new_y
                display.set_pixel(self.player_x, self.player_y, 0, 255, 0)


    def close_area(self, x, y):
        # When the player closes an area by reconnecting with a border or trail
        set_grid_value(x, y, 1)
        display.set_pixel(x, y, 0, 0, 255)

        # Flood fill from the opponent's position
        self.flood_fill(self.opponent_x, self.opponent_y)

        # Fill the non-accessible area
        for i in range(WIDTH):
            for j in range(self.height):
                if get_grid_value(i, j) == 0:
                    set_grid_value(i, j, 2)  # Mark non-accessible area as player's
                    display.set_pixel(i, j, 0, 0, 255)
                elif get_grid_value(i, j) == 3:
                    set_grid_value(i, j, 0)
                elif get_grid_value(i, j) == 1 or get_grid_value(i, j) == 4:
                    set_grid_value(i, j, 1)
                    display.set_pixel(i, j, 0, 55, 100)

        # Calculate occupied percentage after filling
        self.calculate_occupied_percentage()

    def flood_fill(self, x, y):
        # Apply flood fill from the opponent's position to determine the area it controls
        floodfill(x, y, accessible_mark=3, non_accessible_mark=2, r=255, g=0, b=0)

    def calculate_occupied_percentage(self):
        # Calculate how much of the playfield has been occupied
        occupied_pixels = sum(1 for i in range(len(grid)) if grid[i] == 2)
        self.occupied_percentage = (occupied_pixels / (self.width * self.height) * 100)
        display_score_and_time(int(self.occupied_percentage))

    def check_win_condition(self):
        return self.occupied_percentage > 75

    def main_loop(self, joystick):
        global game_over
        game_over = False
        self.initialize_game()

        while not game_over:
            c_button, _ = joystick.nunchuck.buttons()
            if c_button:  # C-Button beendet das Spiel
                game_over = True

            self.move_player(joystick)
            self.move_opponent()
            if self.check_win_condition():
                draw_text(self.width // 2 - 20, self.height // 2 - 10, "YOU WIN", 0, 255, 0)
                time.sleep(2)
                break

            time.sleep(0.05)

class Tetrimino:
    def __init__(self):
        self.shape = random.choice(tetriminos)
        self.color = random.choice(tetris_colors)
        self.x = grid_width // 2 - len(self.shape[0]) // 2
        self.y = 0

    def rotate(self):
        self.shape = [list(row) for row in zip(*self.shape[::-1])]

class TetrisGame:
    def __init__(self):
        self.locked_positions = {}
        self.grid = self.create_grid(self.locked_positions)
        self.change_piece = False
        self.current_piece = Tetrimino()
        self.fall_time = 0
        self.text = ""
        self.old_piece_pos = []
        self.last_input_time = 0
        self.input_cooldown = 60

    def create_grid(self, locked_positions={}):
        grid = [[tetris_black for _ in range(grid_width)] for _ in range(grid_height)]
        for y in range(grid_height):
            for x in range(grid_width):
                if (x, y) in locked_positions:
                    color = locked_positions[(x, y)]
                    grid[y][x] = color
        return grid

    def valid_move(self, shape, grid, offset):
        off_x, off_y = offset
        for y, row in enumerate(shape):
            for x, cell in enumerate(row):
                if cell:
                    if (x + off_x < 0 or x + off_x >= grid_width or y + off_y >= grid_height or grid[y + off_y][x + off_x] != tetris_black):
                        return False
        return True

    def clear_rows(self, grid, locked):
        cleared_rows = 0
        for y in range(grid_height - 1, -1, -1):
            row = grid[y]
            if tetris_black not in row:
                cleared_rows += 1
                for x in range(grid_width):
                    del locked[(x, y)]
                for k in range(y, 0, -1):
                    for x in range(grid_width):
                        locked[(x, k)] = locked.get((x, k - 1), tetris_black)
        return cleared_rows

    def draw_grid(self):
        for y in range(grid_height):
            for x in range(grid_width):
                color = self.grid[y][x]
                if color != tetris_black:
                    draw_rect(x * block_size, y * block_size, (x + 1) * block_size - 1, (y + 1) * block_size - 1, *color)

    def erase_piece(self, piece_pos):
        for x, y in piece_pos:
            if y >= 0:
                draw_rect(x * block_size, y * block_size, (x + 1) * block_size - 1, (y + 1) * block_size - 1, *tetris_black)

    def draw_piece(self, piece_pos, color):
        for x, y in piece_pos:
            if y >= 0:
                draw_rect(x * block_size, y * block_size, (x + 1) * block_size - 1, (y + 1) * block_size - 1, *color)

    def handle_input(self, joystick):
        current_time = time.ticks_ms()
        if current_time - self.last_input_time < self.input_cooldown:
            return None
        self.last_input_time = current_time
        return joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_DOWN, JOYSTICK_UP], debounce=False)

    def main_loop(self, joystick):
        global game_over
        game_over = False
        display.clear()
        clock = time.ticks_ms()
        while not game_over:
            c_button, _ = joystick.nunchuck.buttons()
            if c_button:  # C-Button beendet das Spiel
                game_over = True

            self.grid = self.create_grid(self.locked_positions)
            fall_speed = 500  # in milliseconds
            current_time = time.ticks_ms()
            self.fall_time += time.ticks_diff(current_time, clock)
            clock = current_time

            redraw_needed = False

            if self.fall_time >= fall_speed:
                self.fall_time = 0
                old_piece_pos = [(self.current_piece.x + x, self.current_piece.y + y) for y, row in enumerate(self.current_piece.shape) for x, cell in enumerate(row) if cell]
                self.erase_piece(old_piece_pos)  # Lösche das alte Tetrimino

                self.current_piece.y += 1
                if not self.valid_move(self.current_piece.shape, self.grid, (self.current_piece.x, self.current_piece.y)):
                    self.current_piece.y -= 1
                    self.change_piece = True

                redraw_needed = True

            direction = self.handle_input(joystick)  # Verwende die handle_input-Methode
            if direction == JOYSTICK_LEFT:
                self.erase_piece([(self.current_piece.x + x, self.current_piece.y + y) for y, row in enumerate(self.current_piece.shape) for x, cell in enumerate(row) if cell])
                self.current_piece.x -= 1
                if not self.valid_move(self.current_piece.shape, self.grid, (self.current_piece.x, self.current_piece.y)):
                    self.current_piece.x += 1
                else:
                    redraw_needed = True
            elif direction == JOYSTICK_RIGHT:
                self.erase_piece([(self.current_piece.x + x, self.current_piece.y + y) for y, row in enumerate(self.current_piece.shape) for x, cell in enumerate(row) if cell])
                self.current_piece.x += 1
                if not self.valid_move(self.current_piece.shape, self.grid, (self.current_piece.x, self.current_piece.y)):
                    self.current_piece.x -= 1
                else:
                    redraw_needed = True
            elif direction == JOYSTICK_DOWN:
                self.erase_piece([(self.current_piece.x + x, self.current_piece.y + y) for y, row in enumerate(self.current_piece.shape) for x, cell in enumerate(row) if cell])
                self.current_piece.y += 1
                if not self.valid_move(self.current_piece.shape, self.grid, (self.current_piece.x, self.current_piece.y)):
                    self.current_piece.y -= 1
                else:
                    redraw_needed = True
            elif direction == JOYSTICK_UP:
                self.erase_piece([(self.current_piece.x + x, self.current_piece.y + y) for y, row in enumerate(self.current_piece.shape) for x, cell in enumerate(row) if cell])
                self.current_piece.rotate()
                if not self.valid_move(self.current_piece.shape, self.grid, (self.current_piece.x, self.current_piece.y)):
                    self.current_piece.rotate()
                    self.current_piece.rotate()
                    self.current_piece.rotate()
                else:
                    redraw_needed = True

            if redraw_needed:
                new_piece_pos = [(self.current_piece.x + x, self.current_piece.y + y) for y, row in enumerate(self.current_piece.shape) for x, cell in enumerate(row) if cell]
                self.draw_piece(new_piece_pos, self.current_piece.color)  # Zeichne das neue Tetrimino

            if self.change_piece:
                for pos in new_piece_pos:
                    self.locked_positions[(pos[0], pos[1])] = self.current_piece.color

                cleared_rows = self.clear_rows(self.grid, self.locked_positions)

                if cleared_rows > 0:
                    display.clear()
                    self.grid = self.create_grid(self.locked_positions)  # Erneut das Grid erstellen
                    self.draw_grid()  # Grid neu zeichnen
                else:
                    self.draw_piece(new_piece_pos, self.current_piece.color)  # Zeichne das aktuelle Tetrimino

                self.current_piece = Tetrimino()
                self.change_piece = False

            display_score_and_time(len(self.locked_positions))

            if any(y < 1 for x, y in self.locked_positions):
                game_over = True
                # reset the grid
                self.grid = self.create_grid()
                x, y, w, h = 0, 0, WIDTH, HEIGHT
                self.__init__()

                break


        display.clear()
        #game_over = False
        #GameOverMenu().run_game_over_menu()
        return



# Game Selector class
class GameSelect:
    def __init__(self):
        self.joystick = Joystick(adc0, adc1, adc2)
        self.games = {
            "SNAKE": SnakeGame(),
            "SIMON": SimonGame(),
            "BRKOUT": BreakoutGame(),
            "PONG": PongGame(),
            "QIX": QixGame(),
            "TETRIS": TetrisGame()
        }
        self.selected_game = None

    # make a method to run the selected game (from outside the class)
    def run_game(self, game):
        global game_over
        game_over = False
        self.games[game].main_loop(self.joystick)

    def run_game_selector(self):
        games = list(self.games.keys())
        selected = 0
        previous_selected = None
        top_index = 0
        display_size = 4
        last_move_time = time.time()
        debounce_delay = 0.1

        while True:
            current_time = time.time()
            
            # Update display only when selection changes
            if selected != previous_selected:
                previous_selected = selected
                display.clear()
                for i in range(display_size):
                    game_index = top_index + i
                    if game_index < len(games):
                        color = (255, 255, 255) if game_index == selected else (111, 111, 111)
                        draw_text(8, 5 + i * 15, games[game_index], *color)

            # Check joystick direction with debounce logic
            if current_time - last_move_time > debounce_delay:
                direction = self.joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN], debounce=False)
                if direction == JOYSTICK_UP and selected > 0:
                    selected -= 1
                    if selected < top_index:
                        top_index -= 1
                    last_move_time = current_time
                elif direction == JOYSTICK_DOWN and selected < len(games) - 1:
                    selected += 1
                    if selected > top_index + display_size - 1:
                        top_index += 1
                    last_move_time = current_time

            # Check if joystick button is pressed
            if self.joystick.is_pressed():
                self.selected_game = games[selected]
                break

            # Maintain a consistent frame rate
            time.sleep(0.05)

    def run(self):
        global last_game
        while True:
            if self.selected_game is None:
                self.run_game_selector()
            else:
                last_game = self.selected_game
                try:
                    selected_game = self.selected_game
                    self.selected_game = None

                    self.games[selected_game].main_loop(self.joystick)
                    GameOverMenu().run_game_over_menu()
                except Exception as e:
                    print(f"Error: {e}")
                    self.selected_game = None


# similar to the GameSelect class, but with "back to menu" and "restart" options when a game ends
class GameOverMenu:
    def __init__(self):
        self.joystick = Joystick(adc0, adc1, adc2)
        self.menu = ["RETRY", "MENU"]
        self.selected_option = None

    def run_game_over_menu(self):
        global last_game, global_score, game_over
        selected = 0
        previous_selected = None
        last_move_time = time.time()
        debounce_delay = 0.1
        game_over = False
        display.clear()

        while True:
            current_time = time.time()
            
            # display "Game Over" message
            draw_text(10, 10, "LOST", 255, 20, 20)

            # display score and time
            display_score_and_time(global_score)

            # display menu options
            if selected != previous_selected:
                previous_selected = selected
                display.clear()
                for i, option in enumerate(self.menu):
                    color = (255, 255, 255) if i == selected else (111, 111, 111)
                    draw_text(8, 30 + i * 15, option, *color)

            if current_time - last_move_time > debounce_delay:
                direction = self.joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN], debounce=False)
                if direction == JOYSTICK_UP and selected > 0:
                    selected -= 1
                    last_move_time = current_time
                elif direction == JOYSTICK_DOWN and selected < len(self.menu) - 1:
                    selected += 1
                    last_move_time = current_time

            if self.joystick.is_pressed():
                if self.menu[selected] == "RETRY":
                    global_score = 0
                    GameSelect().run_game(last_game)
                elif self.menu[selected] == "MENU":
                    return

            time.sleep(0.05)



# Main program
if __name__ == '__main__':
    # Initialisierung des I2C-Busses
    i2c = machine.I2C(0, scl=machine.Pin(21), sda=machine.Pin(20), freq=100000)
    
    # Erstellen des Nunchuck-Objekts
    nunchuk = Nunchuck(i2c, poll=True, poll_interval=100)

    # Game selection
    game_state = GameSelect()

    # Start the display
    display.start()

    # Main game loop
    game_state.run()
