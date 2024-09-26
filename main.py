import pygame
import random
import time
import sys
import math

# Constants for display dimensions
HEIGHT = 64
WIDTH = 64
PIXEL_SIZE = 10  # Size of each pixel on the screen

# Initialize PyGame
pygame.init()

# Initialize the display
class PyGameDisplay:
    def __init__(self, width, height, pixel_size):
        self.width = width
        self.height = height
        self.pixel_size = pixel_size
        self.screen = pygame.display.set_mode(
            (self.width * self.pixel_size, self.height * self.pixel_size)
        )
        self.clock = pygame.time.Clock()
        self.pixels = [[(0, 0, 0) for _ in range(self.width)] for _ in range(self.height)]
        pygame.display.set_caption("LED Matrix Simulator")
        self.running = True

    def set_pixel(self, x, y, r, g, b):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.pixels[y][x] = (r, g, b)
            rect = pygame.Rect(
                x * self.pixel_size, y * self.pixel_size, self.pixel_size, self.pixel_size
            )
            pygame.draw.rect(self.screen, (r, g, b), rect)

    def clear(self):
        self.screen.fill((0, 0, 0))
        self.pixels = [[(0, 0, 0) for _ in range(self.width)] for _ in range(self.height)]

    def update(self):
        pygame.display.flip()
        self.clock.tick(60)  # Limit to 60 FPS

    def start(self):
        pass  # No action needed in PyGame

    def stop(self):
        self.running = False
        pygame.quit()


display = PyGameDisplay(WIDTH, HEIGHT, PIXEL_SIZE)

# Global variables for game state
global_score = 0
last_game = None
game_over = False

# Color definitions
COLORS_BRIGHT = [
    (255, 0, 0),  # Red
    (0, 255, 0),  # Green
    (0, 0, 255),  # Blue
    (255, 255, 0),  # Yellow
]

TETRIS_BLACK = (0, 0, 0)
TETRIS_WHITE = (255, 255, 255)
TETRIS_COLORS = [
    (0, 255, 255),  # Cyan
    (255, 0, 0),  # Red
    (0, 255, 0),  # Green
    (0, 0, 255),  # Blue
    (255, 255, 0),  # Yellow
    (255, 165, 0),  # Orange
    (128, 0, 128),  # Purple
]

# Game field size for Tetris (16x13 blocks)
GRID_WIDTH = 16
GRID_HEIGHT = 13
BLOCK_SIZE = 4  # Each block is 4x4 pixels

# Tetrimino shapes for Tetris
TETRIMINOS = [
    [[1, 1, 1, 1]],  # I shape
    [[1, 1, 1], [0, 1, 0]],  # T shape
    [[1, 1, 0], [0, 1, 1]],  # S shape
    [[0, 1, 1], [1, 1, 0]],  # Z shape
    [[1, 1], [1, 1]],  # O shape
    [[1, 1, 1], [1, 0, 0]],  # L shape
    [[1, 1, 1], [0, 0, 1]],  # J shape
]

# Adjusted color shades for inactive states
colors = [(int(r * 0.5), int(g * 0.5), int(b * 0.5)) for r, g, b in COLORS_BRIGHT]
inactive_colors = [
    (int(r * 0.2), int(g * 0.2), int(b * 0.2)) for r, g, b in COLORS_BRIGHT
]

# Game state variables for Simon game
simon_sequence = []
user_sequence = []

# Variables for Snake game
score = 0
snake = [(32, 32)]
snake_length = 3
snake_direction = "UP"
green_targets = []
text = ""

# Constants for Breakout game
PADDLE_WIDTH = 10
PADDLE_HEIGHT = 2
BALL_SIZE = 2
BRICK_WIDTH = 8
BRICK_HEIGHT = 4
BRICK_ROWS = 5
BRICK_COLS = 8

# Possible joystick directions
JOYSTICK_UP = "UP"
JOYSTICK_DOWN = "DOWN"
JOYSTICK_LEFT = "LEFT"
JOYSTICK_RIGHT = "RIGHT"
JOYSTICK_UP_LEFT = "UP-LEFT"
JOYSTICK_UP_RIGHT = "UP-RIGHT"
JOYSTICK_DOWN_LEFT = "DOWN-LEFT"
JOYSTICK_DOWN_RIGHT = "DOWN-RIGHT"

# Dictionary mapping characters to hex strings for display
CHAR_DICT = {
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
    "a": "0000780c7ccc7600",
    "b": "e060607c6666dc00",
    "c": "000078ccc0cc7800",
    "d": "1c0c0c7ccccc7600",
    "e": "000078ccfcc07800",
    "f": "386c60f06060f000",
    "g": "000076cccc7c0cf8",
    "h": "e0606c766666e600",
    "i": "3000703030307800",
    "j": "0c000c0c0ccccc78",
    "k": "e060666c786ce600",
    "l": "7030303030307800",
    "m": "0000ccfefed6c600",
    "n": "0000f8cccccccc00",
    "o": "000078cccccc7800",
    "p": "0000dc667c60f0",
    "q": "000076cccc7c0c1e",
    "r": "00009c766660f000",
    "s": "00007cc0780cf800",
    "t": "10307c3030341800",
    "u": "0000cccccccc7600",
    "v": "0000cccccc783000",
    "w": "0000c6c6d6fe6c00",
    "x": "0000c66c386cc600",
    "y": "0000cccccc7c0cf8",
    "z": "0000fc983064fc00",
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
    "[": "78c0c0c0c0c07800",
    "]": "c06060606060c000",
    "{": "0c18306030180c00",
    "}": "6030180c18306000",
    "<": "0c18306030180c00",
    ">": "6030180c18306000",
    "=": "0000fc0000fc0000",
    "+": "0000187e18180000",
    "-": "0000007e00000000",
    "*": "c66c3810386cc600",
    "/": "0000060c18306000",
    "\\": "00006030180c0c00",
    "_": "00000000000000fe",
    "|": "1818181818181800",
    ";": "0000003018003000",
    ",": "0000000000303000",
    "'": "3030300000000000",
    '"': "cccc000000000000",
    "`": "0c18300000000000",
    "@": "3c66dececec07e00",
    "^": "183c666600000000",
    "█": "ffffffffffffffff",
}

NUMS = {
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
    " ": ["00000", "00000", "00000", "00000", "00000"],
    ".": ["00000", "00000", "00000", "00000", "00001"],
    ":": ["00000", "00100", "00000", "00100", "00000"],
    "/": ["00001", "00010", "00100", "01000", "10000"],
    "-": ["00000", "00000", "11111", "00000", "00000"],
    "=": ["00000", "11111", "00000", "11111", "00000"],
    "+": ["00000", "00100", "01110", "00100", "00000"],
    "*": ["00000", "10101", "01110", "10101", "00000"],
    "(": ["00010", "00100", "00100", "00100", "00010"],
    ")": ["00100", "00010", "00010", "00010", "00100"],
}

def sleep_ms(ms):
    """
    Sleep for the given number of milliseconds.
    """
    end_time = time.time() + ms / 1000.0
    while time.time() < end_time:
        input_handler.process_events()
        if input_handler.quit:
            pygame.quit()
            sys.exit()
        display.update()
        time.sleep(0.01)  # Sleep a bit to prevent high CPU usage

def get_time():
    return time.time()

def ticks_ms():
    return int(time.time() * 1000)

def ticks_diff(a, b):
    return a - b

def ticks_add(a, b):
    return a + b

def ticks_us():
    return int(time.time() * 1000000)

def ticks_diff_us(a, b):
    return a - b


def draw_character(x, y, character, red, green, blue):
    """
    Draw a character at position (x, y) with the given RGB color.
    """
    if character in CHAR_DICT:
        hex_string = CHAR_DICT[character]
        for row in range(8):
            hex_value = hex_string[row * 2 : row * 2 + 2]
            bin_value = f"{int(hex_value, 16):08b}"
            for col in range(8):
                if bin_value[col] == "1":
                    display.set_pixel(x + col, y + row, red, green, blue)

def draw_text(x, y, text, red, green, blue):
    """
    Draw text starting from position (x, y) with the given RGB color.
    """
    offset_x = x
    for character in text:
        draw_character(offset_x, y, character, red, green, blue)
        offset_x += 9  # Move to the next character position

def draw_character_small(x, y, character, red, green, blue):
    """
    Draw a small character at position (x, y) with the given RGB color.
    """
    if character in NUMS:
        matrix = NUMS[character]
        for row in range(5):
            for col in range(5):
                if matrix[row][col] == "1":
                    display.set_pixel(x + col, y + row, red, green, blue)

def draw_text_small(x, y, text, red, green, blue):
    """
    Draw small text starting from position (x, y) with the given RGB color.
    """
    offset_x = x
    for character in text:
        draw_character_small(offset_x, y, character, red, green, blue)
        offset_x += 6  # Move to the next character position

def draw_rectangle(x1, y1, x2, y2, red, green, blue):
    """
    Draw a rectangle between (x1, y1) and (x2, y2) with the given RGB color.
    """
    for x in range(min(x1, x2), max(x1, x2) + 1):
        for y in range(min(y1, y2), max(y1, y2) + 1):
            display.set_pixel(x, y, red, green, blue)

def display_score_and_time(score):
    """
    Display the current score and time at the bottom of the display.
    """
    global text, global_score
    now = time.localtime()
    hour = now.tm_hour
    minute = now.tm_min
    time_str = "{:02}:{:02}".format(hour, minute)
    global_score = score
    score_str = str(score)
    time_x = WIDTH - (len(time_str) * 6)
    time_y = HEIGHT - 6
    score_x = 1
    score_y = HEIGHT - 6
    if text != score_str + " " + time_str:
        text = score_str + " " + time_str
        draw_rectangle(score_x, score_y, WIDTH, score_y + 5, 0, 0, 0)
    draw_text_small(score_x, score_y, score_str, 255, 255, 255)
    draw_text_small(time_x, time_y, time_str, 255, 255, 255)

# Global variable for the grid
grid = bytearray(WIDTH * HEIGHT)

def initialize_grid():
    """
    Initialize the grid to be empty.
    """
    global grid
    grid = bytearray(WIDTH * HEIGHT)

def get_grid_value(x, y):
    """
    Get the value at position (x, y) in the grid.
    """
    return grid[y * WIDTH + x]

def set_grid_value(x, y, value):
    """
    Set the value at position (x, y) in the grid.
    """
    grid[y * WIDTH + x] = value

def flood_fill(
    x, y, accessible_mark, non_accessible_mark, red, green, blue, max_steps=8000
):
    """
    Perform flood fill starting from (x, y).
    """
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
        steps += 1

        if x + 1 < WIDTH:
            stack.append((x + 1, y))
        if x - 1 >= 0:
            stack.append((x - 1, y))
        if y + 1 < HEIGHT:
            stack.append((x, y + 1))
        if y - 1 >= 0:
            stack.append((x, y - 1))

    return len(stack) > 0  # Indicates if there's still work left

def hsb_to_rgb(hue, saturation, brightness):
    """
    Convert HSB (Hue, Saturation, Brightness) color space to RGB.

    Args:
        hue (float): Hue angle in degrees (0-360).
        saturation (float): Saturation (0-1).
        brightness (float): Brightness (0-1).

    Returns:
        tuple: Corresponding RGB values as integers (0-255).
    """
    hue_normalized = (hue % 360) / 60
    hue_index = int(hue_normalized)
    hue_fraction = hue_normalized - hue_index

    value1 = brightness * (1 - saturation)
    value2 = brightness * (1 - saturation * hue_fraction)
    value3 = brightness * (1 - saturation * (1 - hue_fraction))

    if hue_index == 0:
        red, green, blue = brightness, value3, value1
    elif hue_index == 1:
        red, green, blue = value2, brightness, value1
    elif hue_index == 2:
        red, green, blue = value1, brightness, value3
    elif hue_index == 3:
        red, green, blue = value1, value2, brightness
    elif hue_index == 4:
        red, green, blue = value3, value1, brightness
    elif hue_index == 5:
        red, green, blue = brightness, value1, value2
    else:
        red, green, blue = 0, 0, 0

    return int(red * 255), int(green * 255), int(blue * 255)

# Input Handler for keyboard events
class InputHandler:
    def __init__(self):
        self.keys_pressed = set()
        self.quit = False

    def process_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.quit = True
            elif event.type == pygame.KEYDOWN:
                self.keys_pressed.add(event.key)
            elif event.type == pygame.KEYUP:
                if event.key in self.keys_pressed:
                    self.keys_pressed.remove(event.key)

input_handler = InputHandler()

# Joystick and Nunchuk classes adapted for keyboard input
class Nunchuck:
    def __init__(self):
        pass

    def buttons(self):
        """
        Simulate buttons C and Z.
        Return tuple of booleans (C_button, Z_button)
        """
        keys = input_handler.keys_pressed
        c_button = pygame.K_x in keys  # Map 'X' key to C button
        z_button = pygame.K_y in keys  # Map 'Y' key to Z button
        return c_button, z_button

class Joystick:
    """
    Class to handle joystick inputs via keyboard.
    """

    def __init__(self):
        self.nunchuck = Nunchuck()

    def read_direction(self, possible_directions, debounce=True):
        """
        Read the joystick direction based on possible directions.
        """
        direction = None
        keys = input_handler.keys_pressed
        if (
            pygame.K_LEFT in keys
            and pygame.K_UP in keys
            and JOYSTICK_UP_LEFT in possible_directions
        ):
            direction = JOYSTICK_UP_LEFT
        elif (
            pygame.K_RIGHT in keys
            and pygame.K_UP in keys
            and JOYSTICK_UP_RIGHT in possible_directions
        ):
            direction = JOYSTICK_UP_RIGHT
        elif (
            pygame.K_LEFT in keys
            and pygame.K_DOWN in keys
            and JOYSTICK_DOWN_LEFT in possible_directions
        ):
            direction = JOYSTICK_DOWN_LEFT
        elif (
            pygame.K_RIGHT in keys
            and pygame.K_DOWN in keys
            and JOYSTICK_DOWN_RIGHT in possible_directions
        ):
            direction = JOYSTICK_DOWN_RIGHT
        elif pygame.K_LEFT in keys and JOYSTICK_LEFT in possible_directions:
            direction = JOYSTICK_LEFT
        elif pygame.K_RIGHT in keys and JOYSTICK_RIGHT in possible_directions:
            direction = JOYSTICK_RIGHT
        elif pygame.K_UP in keys and JOYSTICK_UP in possible_directions:
            direction = JOYSTICK_UP
        elif pygame.K_DOWN in keys and JOYSTICK_DOWN in possible_directions:
            direction = JOYSTICK_DOWN

        return direction

    def is_pressed(self):
        """
        Check if the joystick button is pressed.
        """
        keys = input_handler.keys_pressed
        return pygame.K_x in keys or pygame.K_y in keys

class SimonGame:
    """
    Class representing the Simon Says game.
    """

    def __init__(self):
        """
        Initialize the Simon game with empty sequences.
        """
        self.sequence = []
        self.user_input = []

    def draw_quad_screen(self):
        """
        Draw the four quadrants of the screen with inactive colors.
        """
        half_width = WIDTH // 2
        half_height = (HEIGHT - 6) // 2  # Adjust for score display area
        draw_rectangle(0, 0, half_width - 1, half_height - 1, *inactive_colors[0])
        draw_rectangle(half_width, 0, WIDTH - 1, half_height - 1, *inactive_colors[1])
        draw_rectangle(0, half_height, half_width - 1, HEIGHT - 7, *inactive_colors[2])
        draw_rectangle(
            half_width, half_height, WIDTH - 1, HEIGHT - 7, *inactive_colors[3]
        )

    def flash_color(self, index, duration=0.5):
        """
        Flash a specific color on the screen.

        Args:
            index (int): Index of the color to flash.
            duration (float): Duration to display the color.
        """
        x = index % 2
        y = index // 2
        half_width = WIDTH // 2
        half_height = (HEIGHT - 6) // 2
        draw_rectangle(
            x * half_width,
            y * half_height,
            (x + 1) * half_width - 1,
            (y + 1) * half_height - 1,
            *colors[index],
        )

        sleep_ms(duration * 1000)

        draw_rectangle(
            x * half_width,
            y * half_height,
            (x + 1) * half_width - 1,
            (y + 1) * half_height - 1,
            *inactive_colors[index],
        )

    def play_sequence(self):
        """
        Play the current sequence by flashing the colors.
        """
        for color_index in self.sequence:
            self.flash_color(color_index)

            sleep_ms(500)

    def get_user_input(self, joystick):
        """
        Get the user's input via the joystick.

        Args:
            joystick (Joystick): The joystick object.

        Returns:
            str: The direction selected by the user.
        """
        while True:
            direction = joystick.read_direction(
                [
                    JOYSTICK_UP_LEFT,
                    JOYSTICK_UP_RIGHT,
                    JOYSTICK_DOWN_LEFT,
                    JOYSTICK_DOWN_RIGHT,
                ]
            )
            if direction:
                return direction

            sleep_ms(100)

    def translate_joystick_to_color(self, direction):
        """
        Translate joystick direction to a color index.

        Args:
            direction (str): Direction from the joystick.

        Returns:
            int: Corresponding color index.
        """
        mapping = {
            JOYSTICK_UP_LEFT: 0,
            JOYSTICK_UP_RIGHT: 1,
            JOYSTICK_DOWN_LEFT: 2,
            JOYSTICK_DOWN_RIGHT: 3,
        }
        return mapping.get(direction, None)

    def check_user_sequence(self):
        """
        Check if the user's input matches the game sequence.

        Returns:
            bool: True if sequences match, False otherwise.
        """
        return self.user_input == self.sequence[: len(self.user_input)]

    def start_game(self):
        """
        Start a new game by resetting sequences and drawing the initial screen.
        """
        self.sequence = []
        self.user_input = []
        self.draw_quad_screen()

    def main_loop(self, joystick):
        """
        Main game loop for the Simon game.

        Args:
            joystick (Joystick): The joystick object.
        """
        global global_score, game_over
        game_over = False

        self.start_game()
        while not game_over:
            c_button, _ = joystick.nunchuck.buttons()
            if c_button:  # C-button ends the game
                game_over = True

            self.sequence.append(random.randint(0, 3))
            display_score_and_time(len(self.sequence) - 1)
            self.play_sequence()
            self.user_input = []

            for _ in range(len(self.sequence)):
                direction = self.get_user_input(joystick)
                selected_color = self.translate_joystick_to_color(direction)
                if selected_color is not None:
                    self.flash_color(selected_color, duration=0.2)
                    self.user_input.append(selected_color)
                    if not self.check_user_sequence():
                        global_score = len(self.sequence) - 1
                        game_over = True
                        return
                else:
                    print("Invalid input")
                    break

            sleep_ms(1000)


class SnakeGame:
    """
    Class representing the Snake game.
    """

    def __init__(self):
        """
        Initialize the Snake game variables.
        """
        self.snake = [(32, 32)]
        self.snake_length = 3
        self.snake_direction = "UP"
        self.score = 0
        self.green_targets = []
        self.target = self.random_target()

    def restart_game(self):
        """
        Restart the game by resetting variables and clearing the display.
        """
        self.snake = [(32, 32)]
        self.snake_length = 3
        self.snake_direction = "UP"
        self.score = 0
        self.green_targets = []
        display.clear()
        self.place_target()

    def random_target(self):
        """
        Generate a random position for the target.

        Returns:
            tuple: Coordinates of the target.
        """
        return (random.randint(1, WIDTH - 2), random.randint(1, HEIGHT - 8))

    def place_target(self):
        """
        Place the target on the display.
        """
        self.target = self.random_target()
        display.set_pixel(self.target[0], self.target[1], 255, 0, 0)

    def place_green_target(self):
        """
        Place a green target on the display.
        """
        x, y = random.randint(1, WIDTH - 2), random.randint(1, HEIGHT - 8)
        self.green_targets.append((x, y, 256))
        display.set_pixel(x, y, 0, 255, 0)

    def update_green_targets(self):
        """
        Update the lifespan of green targets and remove them if necessary.
        """
        new_green_targets = []
        for x, y, lifespan in self.green_targets:
            if lifespan > 1:
                new_green_targets.append((x, y, lifespan - 1))
            else:
                display.set_pixel(x, y, 0, 0, 0)
        self.green_targets = new_green_targets

    def check_self_collision(self):
        """
        Check for collision of the snake with itself.

        If collision is detected, the game ends.
        """
        global global_score, game_over
        head_x, head_y = self.snake[0]
        body = self.snake[1:]
        potential_moves = {
            "UP": (head_x, head_y - 1),
            "DOWN": (head_x, head_y + 1),
            "LEFT": (head_x - 1, head_y),
            "RIGHT": (head_x + 1, head_y),
        }
        safe_moves = {
            direction: pos
            for direction, pos in potential_moves.items()
            if pos not in body
        }
        if potential_moves[self.snake_direction] not in safe_moves.values():
            if safe_moves:
                self.snake_direction = random.choice(list(safe_moves.keys()))
            else:
                global_score = self.score
                game_over = True
                return

    def update_snake_position(self):
        """
        Update the position of the snake based on its current direction.
        """
        head_x, head_y = self.snake[0]
        if self.snake_direction == "UP":
            head_y -= 1
        elif self.snake_direction == "DOWN":
            head_y += 1
        elif self.snake_direction == "LEFT":
            head_x -= 1
        elif self.snake_direction == "RIGHT":
            head_x += 1

        head_x %= WIDTH
        head_y %= HEIGHT

        self.snake.insert(0, (head_x, head_y))
        if len(self.snake) > self.snake_length:
            tail = self.snake.pop()
            display.set_pixel(tail[0], tail[1], 0, 0, 0)

    def check_target_collision(self):
        """
        Check if the snake has collided with the target.

        If so, increase the snake length and score, and place a new target.
        """
        head_x, head_y = self.snake[0]
        if (head_x, head_y) == self.target:
            self.snake_length += 2
            self.place_target()
            self.score += 1

    def check_green_target_collision(self):
        """
        Check if the snake has collided with a green target.

        If so, reduce the snake length.
        """
        head_x, head_y = self.snake[0]
        for x, y, lifespan in self.green_targets:
            if (head_x, head_y) == (x, y):
                self.snake_length = max(self.snake_length // 2, 2)
                self.green_targets.remove((x, y, lifespan))
                display.set_pixel(x, y, 0, 0, 0)

    def draw_snake(self):
        """
        Draw the snake on the display with a color gradient.
        """
        hue = 0
        for idx, (x, y) in enumerate(self.snake[: self.snake_length]):
            hue = (hue + 5) % 360
            red, green, blue = hsb_to_rgb(hue, 1, 1)
            display.set_pixel(x, y, red, green, blue)
        for idx in range(self.snake_length, len(self.snake)):
            x, y = self.snake[idx]
            display.set_pixel(x, y, 0, 0, 0)

    def main_loop(self, joystick):
        """
        Main game loop for the Snake game.

        Args:
            joystick (Joystick): The joystick object.
        """
        global game_over
        game_over = False
        self.restart_game()
        step_counter = 0

        while not game_over:
            c_button, _ = joystick.nunchuck.buttons()
            if c_button:  # C-button ends the game
                game_over = True

            step_counter += 1

            if step_counter % 1024 == 0:
                self.place_green_target()
            self.update_green_targets()

            direction = joystick.read_direction(
                [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
            )
            if direction:
                self.snake_direction = direction

            self.check_self_collision()
            self.update_snake_position()
            self.check_target_collision()
            self.check_green_target_collision()
            self.draw_snake()
            display_score_and_time(self.score)

            sleep_ms(max(0.03, (0.09 - max(0.01, self.snake_length / 300))) * 1000)


class PongGame:
    """
    Class representing the Pong game.
    """

    def __init__(self):
        """
        Initialize the Pong game variables.
        """
        self.paddle_height = 8
        self.paddle_speed = 2
        self.ball_speed = [1, 1]
        self.ball_position = [WIDTH // 2, HEIGHT // 2]
        self.left_paddle_y = HEIGHT // 2 - self.paddle_height // 2
        self.right_paddle_y = HEIGHT // 2 - self.paddle_height // 2
        self.previous_left_score = 0
        self.left_score = 0
        self.lives = 3

    def draw_paddles(self):
        """
        Draw the paddles on the display.
        """
        # Clear previous paddle positions
        for y in range(HEIGHT):
            display.set_pixel(0, y, 0, 0, 0)
            display.set_pixel(WIDTH - 1, y, 0, 0, 0)

        # Draw left paddle
        for y in range(self.left_paddle_y, self.left_paddle_y + self.paddle_height):
            display.set_pixel(0, y, 255, 255, 255)

        # Draw right paddle
        for y in range(self.right_paddle_y, self.right_paddle_y + self.paddle_height):
            display.set_pixel(WIDTH - 1, y, 255, 255, 255)

    def draw_ball(self):
        """
        Draw the ball on the display.
        """
        x, y = self.ball_position
        display.set_pixel(x, y, 255, 255, 255)

    def clear_ball(self):
        """
        Clear the ball from its current position.
        """
        x, y = self.ball_position
        display.set_pixel(x, y, 0, 0, 0)

    def update_ball(self):
        """
        Update the ball's position and handle collisions.
        """
        global global_score, game_over
        self.clear_ball()
        self.ball_position[0] += self.ball_speed[0]
        self.ball_position[1] += self.ball_speed[1]

        x, y = self.ball_position

        # Handle collision with top and bottom walls
        if y <= 0 or y >= HEIGHT - 1:
            self.ball_speed[1] = -self.ball_speed[1]

        # Handle collision with left paddle
        if x == 1 and self.left_paddle_y <= y < self.left_paddle_y + self.paddle_height:
            self.ball_speed[0] = -self.ball_speed[0]
            self.left_score += 1

        # Handle collision with right paddle
        elif (
            x == WIDTH - 2
            and self.right_paddle_y <= y < self.right_paddle_y + self.paddle_height
        ):
            self.ball_speed[0] = -self.ball_speed[0]

        # Ball misses the left paddle
        if x <= 0:
            self.left_score = 0
            self.lives -= 1
            if self.lives == 0:
                game_over = True
                return
            self.reset_ball()

        # Ball misses the right paddle
        elif x >= WIDTH - 1:
            self.left_score += 10
            self.reset_ball()

        global_score = self.left_score
        self.draw_ball()

    def reset_ball(self):
        """
        Reset the ball to the center of the display with a random direction.
        """
        self.ball_position = [WIDTH // 2, HEIGHT // 2]
        self.ball_speed = [random.choice([-1, 1]), random.choice([-1, 1])]

    def update_paddles(self, joystick):
        """
        Update the positions of the paddles based on input and AI.

        Args:
            joystick (Joystick): The joystick object.
        """
        # Update left paddle based on joystick input
        direction = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN])
        if direction == JOYSTICK_UP:
            self.left_paddle_y = max(self.left_paddle_y - self.paddle_speed, 0)
        elif direction == JOYSTICK_DOWN:
            self.left_paddle_y = min(
                self.left_paddle_y + self.paddle_speed, HEIGHT - self.paddle_height
            )

        # Simple AI for right paddle
        ball_y = self.ball_position[1]
        paddle_center = self.right_paddle_y + self.paddle_height // 2
        if ball_y < paddle_center:
            self.right_paddle_y = max(self.right_paddle_y - self.paddle_speed, 0)
        elif ball_y > paddle_center:
            self.right_paddle_y = min(
                self.right_paddle_y + self.paddle_speed, HEIGHT - self.paddle_height
            )

    def main_loop(self, joystick):
        """
        Main game loop for the Pong game.

        Args:
            joystick (Joystick): The joystick object.
        """
        global game_over
        game_over = False
        self.reset_ball()
        display.clear()
        while not game_over:
            c_button, _ = joystick.nunchuck.buttons()
            if c_button:  # C-button ends the game
                game_over = True

            self.update_paddles(joystick)
            self.update_ball()
            self.draw_paddles()
            if self.left_score != self.previous_left_score:
                display_score_and_time(self.left_score)
                self.previous_left_score = self.left_score

            sleep_ms(50)


class BreakoutGame:
    """
    Class representing the Breakout game.
    """

    def __init__(self):
        """
        Initialize the Breakout game variables.
        """
        self.paddle_x = (WIDTH - PADDLE_WIDTH) // 2
        self.paddle_y = HEIGHT - PADDLE_HEIGHT
        self.ball_x = WIDTH // 2
        self.ball_y = HEIGHT // 2

        # Ball direction
        self.ball_dx = 1
        self.ball_dy = -1

        # Create bricks
        self.bricks = self.create_bricks()

        # Game variables
        self.score = 0
        self.paddle_speed = 2

        display.clear()

    def create_bricks(self):
        """
        Create the initial set of bricks.

        Returns:
            list: List of brick positions.
        """
        bricks = []
        for row in range(BRICK_ROWS):
            for col in range(BRICK_COLS):
                x = col * (BRICK_WIDTH + 1) + 1
                y = row * (BRICK_HEIGHT + 1)
                bricks.append((x, y))
        return bricks

    def draw_paddle(self):
        """
        Draw the paddle on the display.
        """
        for x in range(self.paddle_x, self.paddle_x + PADDLE_WIDTH):
            for y in range(self.paddle_y, self.paddle_y + PADDLE_HEIGHT):
                display.set_pixel(x, y, 255, 255, 255)

    def clear_paddle(self):
        """
        Clear the paddle from its current position.
        """
        for x in range(self.paddle_x, self.paddle_x + PADDLE_WIDTH):
            for y in range(self.paddle_y, self.paddle_y + PADDLE_HEIGHT):
                display.set_pixel(x, y, 0, 0, 0)

    def draw_ball(self):
        """
        Draw the ball on the display.
        """
        # Draw a 2x2 ball
        display.set_pixel(self.ball_x, self.ball_y, 255, 255, 255)
        display.set_pixel(self.ball_x + 1, self.ball_y, 255, 255, 255)
        display.set_pixel(self.ball_x, self.ball_y + 1, 255, 255, 255)
        display.set_pixel(self.ball_x + 1, self.ball_y + 1, 255, 255, 255)

    def clear_ball(self):
        """
        Clear the ball from its current position.
        """
        # Clear a 2x2 ball
        display.set_pixel(self.ball_x, self.ball_y, 0, 0, 0)
        display.set_pixel(self.ball_x + 1, self.ball_y, 0, 0, 0)
        display.set_pixel(self.ball_x, self.ball_y + 1, 0, 0, 0)
        display.set_pixel(self.ball_x + 1, self.ball_y + 1, 0, 0, 0)

    def draw_bricks(self):
        """
        Draw all the bricks on the display.
        """
        for x, y in self.bricks:
            hue = (y) * 360 // (BRICK_ROWS * BRICK_COLS)
            red, green, blue = hsb_to_rgb(hue, 1, 1)
            for dx in range(BRICK_WIDTH):
                for dy in range(BRICK_HEIGHT):
                    display.set_pixel(x + dx, y + dy, red, green, blue)

    def clear_bricks(self):
        """
        Clear all the bricks from the display.
        """
        display.clear()

    def update_ball(self):
        """
        Update the ball's position and handle collisions.
        """
        global game_over
        self.clear_ball()
        self.ball_x += self.ball_dx
        self.ball_y += self.ball_dy

        # Handle collision with walls
        if self.ball_x <= 0 or self.ball_x >= WIDTH - 1:
            self.ball_dx = -self.ball_dx
        if self.ball_y <= 1:
            self.ball_dy = -self.ball_dy

        # Handle collision with paddle
        if self.ball_y >= HEIGHT - PADDLE_HEIGHT - 2:
            if self.paddle_x <= self.ball_x <= self.paddle_x + PADDLE_WIDTH:
                self.ball_dy = -self.ball_dy

        # Ball falls below paddle
        if self.ball_y >= HEIGHT:
            game_over = True
            return

        self.draw_ball()

    def check_collision_with_bricks(self):
        """
        Check for collision between the ball and bricks.
        """
        global global_score
        for brick in self.bricks:
            bx, by = brick
            if (
                bx <= self.ball_x < bx + BRICK_WIDTH
                and by <= self.ball_y < by + BRICK_HEIGHT
            ):
                self.clear_ball()
                self.ball_dy = -self.ball_dy
                self.bricks.remove(brick)
                self.score += 10
                global_score = self.score
                self.clear_bricks()
                self.draw_bricks()
                break

    def update_paddle(self, joystick):
        """
        Update the paddle's position based on joystick input.

        Args:
            joystick (Joystick): The joystick object.
        """
        direction = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT])
        if direction == JOYSTICK_LEFT:
            self.clear_paddle()
            self.paddle_x = max(self.paddle_x - self.paddle_speed, 0)
        elif direction == JOYSTICK_RIGHT:
            self.clear_paddle()
            self.paddle_x = min(self.paddle_x + self.paddle_speed, WIDTH - PADDLE_WIDTH)
        self.draw_paddle()

    def main_loop(self, joystick):
        """
        Main game loop for the Breakout game.

        Args:
            joystick (Joystick): The joystick object.
        """
        global game_over
        game_over = False
        display.clear()
        self.draw_bricks()
        while not game_over:
            c_button, _ = joystick.nunchuck.buttons()
            if c_button:  # C-button ends the game
                game_over = True

            self.update_ball()
            self.check_collision_with_bricks()
            self.update_paddle(joystick)
            display_score_and_time(self.score)
            if self.score == BRICK_ROWS * BRICK_COLS * 10:
                display.clear()
                draw_text(10, 5, "YOU", 255, 255, 255)
                draw_text(10, 20, "WON", 255, 255, 255)
                sleep_ms(3000)
                break
            elif self.score < 60:
                sleep_ms(50)
            elif self.score < 120:
                sleep_ms(30)
            else:
                sleep_ms(10)


class QixGame:
    """
    Class representing the Qix game.
    """

    def __init__(self):
        """
        Initialize the Qix game variables.
        """
        self.player_x = 0
        self.player_y = 0
        self.opponent_x = 0
        self.opponent_y = 0
        self.opponent_dx = 1
        self.opponent_dy = 1
        self.occupied_percentage = 0
        self.height = HEIGHT - 7  # Adjust for score display area
        self.width = WIDTH

        # Previous player position type (grid value)
        self.prev_player_pos = 1

    def initialize_game(self):
        """
        Initialize the game by setting up the grid and placing the player and opponent.
        """
        display.clear()
        initialize_grid()
        self.draw_frame()
        self.place_player()
        self.place_opponent()

    def draw_frame(self):
        """
        Draw a frame around the play area.
        """
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
        """
        Place the player at a random position on the edge.
        """
        edge_positions = (
            [(x, 0) for x in range(self.width)]
            + [(x, self.height - 1) for x in range(self.width)]
            + [(0, y) for y in range(self.height)]
            + [(self.width - 1, y) for y in range(self.height)]
        )
        self.player_x, self.player_y = random.choice(edge_positions)
        display.set_pixel(self.player_x, self.player_y, 0, 255, 0)

    def place_opponent(self):
        """
        Place the opponent at a random position inside the playfield.
        """
        self.opponent_x = random.randint(1, self.width - 2)
        self.opponent_y = random.randint(1, self.height - 2)
        set_grid_value(self.opponent_x, self.opponent_y, 3)
        display.set_pixel(self.opponent_x, self.opponent_y, 255, 0, 0)

    def move_opponent(self):
        """
        Move the opponent and handle collisions with boundaries and trails.
        """
        global game_over
        next_x = self.opponent_x + self.opponent_dx
        next_y = self.opponent_y + self.opponent_dy

        # Check for collision in the x direction
        if get_grid_value(next_x, self.opponent_y) in (1, 2):
            self.opponent_dx = -self.opponent_dx

        # Check for collision in the y direction
        if get_grid_value(self.opponent_x, next_y) in (1, 2):
            self.opponent_dy = -self.opponent_dy

        # Check for collision with player or trail
        if get_grid_value(next_x, next_y) == 4 or (
            next_x == self.player_x and next_y == self.player_y
        ):
            game_over = True
            return

        # Clear current position
        set_grid_value(self.opponent_x, self.opponent_y, 0)
        display.set_pixel(self.opponent_x, self.opponent_y, 0, 0, 0)

        # Update position
        self.opponent_x += self.opponent_dx
        self.opponent_y += self.opponent_dy
        display.set_pixel(self.opponent_x, self.opponent_y, 255, 0, 0)

    def move_player(self, joystick):
        """
        Move the player based on joystick input.

        Args:
            joystick (Joystick): The joystick object.
        """
        direction = joystick.read_direction(
            [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
        )
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
        """
        Close an area when the player reconnects with a border or trail.

        Args:
            x (int): X-coordinate of the connection point.
            y (int): Y-coordinate of the connection point.
        """
        # Finalize the trail
        set_grid_value(x, y, 1)
        display.set_pixel(x, y, 0, 0, 255)

        # Flood fill from the opponent's position
        self.flood_fill(self.opponent_x, self.opponent_y)

        # Fill the non-accessible area
        for i in range(self.width):
            for j in range(self.height):
                grid_value = get_grid_value(i, j)
                if grid_value == 0:
                    set_grid_value(i, j, 2)  # Mark as player's area
                    display.set_pixel(i, j, 0, 0, 255)
                elif grid_value == 3:
                    set_grid_value(i, j, 0)
                elif grid_value in (1, 4):
                    set_grid_value(i, j, 1)
                    display.set_pixel(i, j, 0, 55, 100)

        # Recalculate occupied percentage
        self.calculate_occupied_percentage()

    def flood_fill(self, x, y):
        """
        Perform flood fill from the opponent's position.

        Args:
            x (int): X-coordinate to start flood fill.
            y (int): Y-coordinate to start flood fill.
        """
        flood_fill(
            x, y, accessible_mark=3, non_accessible_mark=2, red=255, green=0, blue=0
        )

    def calculate_occupied_percentage(self):
        """
        Calculate the percentage of the playfield occupied by the player.
        """
        occupied_pixels = sum(1 for value in grid if value == 2)
        self.occupied_percentage = (occupied_pixels / (self.width * self.height)) * 100
        display_score_and_time(int(self.occupied_percentage))

    def check_win_condition(self):
        """
        Check if the player has won the game.

        Returns:
            bool: True if the player has won, False otherwise.
        """
        return self.occupied_percentage > 75

    def main_loop(self, joystick):
        """
        Main game loop for the Qix game.

        Args:
            joystick (Joystick): The joystick object.
        """
        global game_over
        game_over = False
        self.initialize_game()

        while not game_over:
            c_button, _ = joystick.nunchuck.buttons()
            if c_button:  # C-button ends the game
                game_over = True

            self.move_player(joystick)
            self.move_opponent()
            if self.check_win_condition():
                draw_text(
                    self.width // 2 - 20, self.height // 2 - 10, "YOU WIN", 0, 255, 0
                )
                sleep_ms(2000)
                break

            sleep_ms(50)


class Tetrimino:
    """
    Class representing a Tetrimino piece in Tetris.
    """

    def __init__(self):
        """
        Initialize a new Tetrimino with random shape and color.
        """
        self.shape = random.choice(TETRIMINOS)
        self.color = random.choice(TETRIS_COLORS)
        self.x = GRID_WIDTH // 2 - len(self.shape[0]) // 2
        self.y = 0

    def rotate(self):
        """
        Rotate the Tetrimino shape clockwise.
        """
        self.shape = [list(row) for row in zip(*self.shape[::-1])]


class TetrisGame:
    """
    Class representing the Tetris game.
    """

    def __init__(self):
        """
        Initialize the Tetris game variables.
        """
        self.locked_positions = {}
        self.grid = self.create_grid(self.locked_positions)
        self.change_piece = False
        self.current_piece = Tetrimino()
        self.fall_time = 0
        self.text = ""
        self.last_input_time = 0
        self.input_cooldown = 60

    def create_grid(self, locked_positions=None):
        """
        Create the game grid with locked positions.

        Args:
            locked_positions (dict): Dictionary of locked positions.

        Returns:
            list: The game grid.
        """
        if locked_positions is None:
            locked_positions = {}
        grid = [[TETRIS_BLACK for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)]
        for y in range(GRID_HEIGHT):
            for x in range(GRID_WIDTH):
                if (x, y) in locked_positions:
                    color = locked_positions[(x, y)]
                    grid[y][x] = color
        return grid

    def valid_move(self, shape, grid, offset):
        """
        Check if a move is valid.

        Args:
            shape (list): The shape of the Tetrimino.
            grid (list): The game grid.
            offset (tuple): The offset position.

        Returns:
            bool: True if the move is valid, False otherwise.
        """
        off_x, off_y = offset
        for y, row in enumerate(shape):
            for x, cell in enumerate(row):
                if cell:
                    new_x = x + off_x
                    new_y = y + off_y
                    if (
                        new_x < 0
                        or new_x >= GRID_WIDTH
                        or new_y >= GRID_HEIGHT
                        or grid[new_y][new_x] != TETRIS_BLACK
                    ):
                        return False
        return True

    def clear_rows(self, grid, locked_positions):
        """
        Clear completed rows from the grid.

        Args:
            grid (list): The game grid.
            locked_positions (dict): Dictionary of locked positions.

        Returns:
            int: Number of rows cleared.
        """
        cleared_rows = 0
        for y in range(GRID_HEIGHT - 1, -1, -1):
            row = grid[y]
            if TETRIS_BLACK not in row:
                cleared_rows += 1
                for x in range(GRID_WIDTH):
                    del locked_positions[(x, y)]
                for k in range(y, 0, -1):
                    for x in range(GRID_WIDTH):
                        locked_positions[(x, k)] = locked_positions.get(
                            (x, k - 1), TETRIS_BLACK
                        )
        return cleared_rows

    def draw_grid(self):
        """
        Draw the grid with locked positions.
        """
        for y in range(GRID_HEIGHT):
            for x in range(GRID_WIDTH):
                color = self.grid[y][x]
                if color != TETRIS_BLACK:
                    draw_rectangle(
                        x * BLOCK_SIZE,
                        y * BLOCK_SIZE,
                        (x + 1) * BLOCK_SIZE - 1,
                        (y + 1) * BLOCK_SIZE - 1,
                        *color,
                    )

    def erase_piece(self, piece_positions):
        """
        Erase a Tetrimino from the display.

        Args:
            piece_positions (list): List of positions occupied by the piece.
        """
        for x, y in piece_positions:
            if y >= 0:
                draw_rectangle(
                    x * BLOCK_SIZE,
                    y * BLOCK_SIZE,
                    (x + 1) * BLOCK_SIZE - 1,
                    (y + 1) * BLOCK_SIZE - 1,
                    *TETRIS_BLACK,
                )

    def draw_piece(self, piece_positions, color):
        """
        Draw a Tetrimino on the display.

        Args:
            piece_positions (list): List of positions occupied by the piece.
            color (tuple): Color of the piece.
        """
        for x, y in piece_positions:
            if y >= 0:
                draw_rectangle(
                    x * BLOCK_SIZE,
                    y * BLOCK_SIZE,
                    (x + 1) * BLOCK_SIZE - 1,
                    (y + 1) * BLOCK_SIZE - 1,
                    *color,
                )

    def handle_input(self, joystick):
        """
        Handle joystick input with cooldown.

        Args:
            joystick (Joystick): The joystick object.

        Returns:
            str: Direction input from the joystick.
        """
        current_time = ticks_ms()
        if current_time - self.last_input_time < self.input_cooldown:
            return None
        self.last_input_time = current_time
        return joystick.read_direction(
            [JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_DOWN, JOYSTICK_UP], debounce=False
        )

    def main_loop(self, joystick):
        """
        Main game loop for the Tetris game.

        Args:
            joystick (Joystick): The joystick object.
        """
        global game_over
        game_over = False
        display.clear()
        clock = ticks_ms()
        while not game_over:
            c_button, _ = joystick.nunchuck.buttons()
            if c_button:  # C-button ends the game
                game_over = True

            self.grid = self.create_grid(self.locked_positions)
            fall_speed = 500  # in milliseconds
            current_time = ticks_ms()
            self.fall_time += ticks_diff(current_time, clock)
            clock = current_time

            redraw_needed = False

            if self.fall_time >= fall_speed:
                self.fall_time = 0
                old_piece_positions = [
                    (self.current_piece.x + x, self.current_piece.y + y)
                    for y, row in enumerate(self.current_piece.shape)
                    for x, cell in enumerate(row)
                    if cell
                ]
                self.erase_piece(old_piece_positions)

                self.current_piece.y += 1
                if not self.valid_move(
                    self.current_piece.shape,
                    self.grid,
                    (self.current_piece.x, self.current_piece.y),
                ):
                    self.current_piece.y -= 1
                    self.change_piece = True

                redraw_needed = True

            direction = self.handle_input(joystick)
            if direction == JOYSTICK_LEFT:
                self.erase_piece(
                    [
                        (self.current_piece.x + x, self.current_piece.y + y)
                        for y, row in enumerate(self.current_piece.shape)
                        for x, cell in enumerate(row)
                        if cell
                    ]
                )
                self.current_piece.x -= 1
                if not self.valid_move(
                    self.current_piece.shape,
                    self.grid,
                    (self.current_piece.x, self.current_piece.y),
                ):
                    self.current_piece.x += 1
                else:
                    redraw_needed = True
            elif direction == JOYSTICK_RIGHT:
                self.erase_piece(
                    [
                        (self.current_piece.x + x, self.current_piece.y + y)
                        for y, row in enumerate(self.current_piece.shape)
                        for x, cell in enumerate(row)
                        if cell
                    ]
                )
                self.current_piece.x += 1
                if not self.valid_move(
                    self.current_piece.shape,
                    self.grid,
                    (self.current_piece.x, self.current_piece.y),
                ):
                    self.current_piece.x -= 1
                else:
                    redraw_needed = True
            elif direction == JOYSTICK_DOWN:
                self.erase_piece(
                    [
                        (self.current_piece.x + x, self.current_piece.y + y)
                        for y, row in enumerate(self.current_piece.shape)
                        for x, cell in enumerate(row)
                        if cell
                    ]
                )
                self.current_piece.y += 1
                if not self.valid_move(
                    self.current_piece.shape,
                    self.grid,
                    (self.current_piece.x, self.current_piece.y),
                ):
                    self.current_piece.y -= 1
                else:
                    redraw_needed = True
            elif direction == JOYSTICK_UP:
                self.erase_piece(
                    [
                        (self.current_piece.x + x, self.current_piece.y + y)
                        for y, row in enumerate(self.current_piece.shape)
                        for x, cell in enumerate(row)
                        if cell
                    ]
                )
                self.current_piece.rotate()
                if not self.valid_move(
                    self.current_piece.shape,
                    self.grid,
                    (self.current_piece.x, self.current_piece.y),
                ):
                    # Rotate back if move is invalid
                    for _ in range(3):
                        self.current_piece.rotate()
                else:
                    redraw_needed = True

            if redraw_needed:
                new_piece_positions = [
                    (self.current_piece.x + x, self.current_piece.y + y)
                    for y, row in enumerate(self.current_piece.shape)
                    for x, cell in enumerate(row)
                    if cell
                ]
                self.draw_piece(new_piece_positions, self.current_piece.color)

            if self.change_piece:
                for pos in new_piece_positions:
                    self.locked_positions[(pos[0], pos[1])] = self.current_piece.color

                cleared_rows = self.clear_rows(self.grid, self.locked_positions)

                if cleared_rows > 0:
                    display.clear()
                    self.grid = self.create_grid(self.locked_positions)
                    self.draw_grid()
                else:
                    self.draw_piece(new_piece_positions, self.current_piece.color)

                self.current_piece = Tetrimino()
                self.change_piece = False

            display_score_and_time(len(self.locked_positions))

            # Check for game over condition
            if any(y < 1 for x, y in self.locked_positions):
                game_over = True
                self.__init__()  # Reset the game
                break

        display.clear()
        return


class Projectile:
    def __init__(self, x, y, angle, speed):
        self.x = x
        self.y = y
        self.angle = angle
        self.speed = speed
        self.lifetime = 10  # Frames

    def update(self):
        self.x += math.cos(math.radians(self.angle)) * self.speed
        self.y -= math.sin(math.radians(self.angle)) * self.speed
        self.x %= PIXEL_WIDTH
        self.y %= PIXEL_HEIGHT
        self.lifetime -= 1

    def is_alive(self):
        return self.lifetime > 0
    
    def draw(self):
        # Zeichne das Projektil als einzelner Pixel
        px = int(self.x) % PIXEL_WIDTH
        py = int(self.y) % PIXEL_HEIGHT
        self.draw_line((self.x, self.y), (self.x + math.cos(math.radians(self.angle)), self.y - math.sin(math.radians(self.angle))), RED)

    def draw_line(self, start, end, color):
        # Bresenham's Linie-Algorithmus
        x0, y0 = int(start[0]), int(start[1])
        x1, y1 = int(end[0]), int(end[1])
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        x, y = x0, y0
        sx = -1 if x0 > x1 else 1
        sy = -1 if y0 > y1 else 1
        if dx > dy:
            err = dx / 2.0
            while x != x1:
                display.set_pixel(x % PIXEL_WIDTH, y % PIXEL_HEIGHT, *color)
                err -= dy
                if err < 0:
                    y += sy
                    err += dx
                x += sx
        else:
            err = dy / 2.0
            while y != y1:
                display.set_pixel(x % PIXEL_WIDTH, y % PIXEL_HEIGHT, *color)
                err -= dx
                if err < 0:
                    x += sx
                    err += dy
                y += sy
        display.set_pixel(x % PIXEL_WIDTH, y % PIXEL_HEIGHT, *color)


class Asteroid:
    def __init__(self, x=None, y=None, size=None, start=False):
        self.x, self.y = 32, 32

        # use values from parameter if they are not None
        if x is not None:
            self.x = x
        if y is not None:
            self.y = y
            
        while (start == True and (self.x > 22 and self.x < 42) or (self.y > 22 and self.y < 42)):
            self.x = random.uniform(0, PIXEL_WIDTH)
            self.y = random.uniform(0, PIXEL_HEIGHT)

        self.angle = random.uniform(0, 360)
        self.speed = random.uniform(0.5, 1.5)
        self.size = size if size is not None else random.randint(4, 8)

    def update(self):
        self.x += math.cos(math.radians(self.angle)) * self.speed
        self.y -= math.sin(math.radians(self.angle)) * self.speed
        self.x %= PIXEL_WIDTH
        self.y %= PIXEL_HEIGHT

    def draw(self):
        # Zeichne Kreis durch Setzen mehrerer Pixel
        for degree in range(0, 360, 10):
            rad = math.radians(degree)
            px = int((self.x + math.cos(rad) * self.size) % PIXEL_WIDTH)
            py = int((self.y + math.sin(rad) * self.size) % PIXEL_HEIGHT)
            display.set_pixel(px, py, *WHITE)

class Ship:
    def __init__(self):
        self.x = PIXEL_WIDTH / 2
        self.y = PIXEL_HEIGHT / 2
        self.angle = 0
        self.speed = 0
        self.max_speed = 2
        self.size = 3
        self.cooldown = 0

    def update(self, direction):
        # Drehung des Raumschiffs basierend auf Richtungseingaben
        if direction == "LEFT":
            self.angle = (self.angle + 5) % 360
        elif direction == "RIGHT":
            self.angle = (self.angle - 5) % 360

        # Vorwärtsbewegung
        if direction == "UP":
            self.speed = min(self.speed + 0.1, self.max_speed)
        else:
            self.speed = max(self.speed - 0.05, 0)

        # Position aktualisieren
        self.x += math.cos(math.radians(self.angle)) * self.speed
        self.y -= math.sin(math.radians(self.angle)) * self.speed

        # Bildschirmrand überprüfen (Wrap-Around)
        self.x %= PIXEL_WIDTH
        self.y %= PIXEL_HEIGHT

        # Cooldown für Schüsse
        if self.cooldown > 0:
            self.cooldown -= 1

    def draw(self):
        # Dreieck als Raumschiff
        points = [
            (self.x + math.cos(math.radians(self.angle)) * self.size,
             self.y - math.sin(math.radians(self.angle)) * self.size),
            (self.x + math.cos(math.radians(self.angle + 120)) * self.size,
             self.y - math.sin(math.radians(self.angle + 120)) * self.size),
            (self.x + math.cos(math.radians(self.angle - 120)) * self.size,
             self.y - math.sin(math.radians(self.angle - 120)) * self.size),
        ]
        # Linien zwischen den Punkten zeichnen
        if self.speed > 0:
            self.draw_line(points[1], points[2], RED) # hinten - rot wenn das Raumschiff sich bewegt
            
        self.draw_line(points[0], points[1], WHITE) # links - Backbord
        self.draw_line(points[2], points[0], WHITE) # rechts - Steuerbord

    def draw_line(self, start, end, color):
        # Bresenham's Linie-Algorithmus
        x0, y0 = int(start[0]), int(start[1])
        x1, y1 = int(end[0]), int(end[1])
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        x, y = x0, y0
        sx = -1 if x0 > x1 else 1
        sy = -1 if y0 > y1 else 1
        if dx > dy:
            err = dx / 2.0
            while x != x1:
                display.set_pixel(x % PIXEL_WIDTH, y % PIXEL_HEIGHT, *color)
                err -= dy
                if err < 0:
                    y += sy
                    err += dx
                x += sx
        else:
            err = dy / 2.0
            while y != y1:
                display.set_pixel(x % PIXEL_WIDTH, y % PIXEL_HEIGHT, *color)
                err -= dx
                if err < 0:
                    x += sx
                    err += dy
                y += sy
        display.set_pixel(x % PIXEL_WIDTH, y % PIXEL_HEIGHT, *color)

    def shoot(self):
        if self.cooldown == 0:
            self.cooldown = SHIP_COOLDOWN
            bullet_speed = 4
            bullet_x = self.x + math.cos(math.radians(self.angle)) * self.size
            bullet_y = self.y - math.sin(math.radians(self.angle)) * self.size
            return Projectile(bullet_x, bullet_y, self.angle, bullet_speed)
        return None

PIXEL_WIDTH, PIXEL_HEIGHT = 64, 64
SHIP_COOLDOWN = 10  # Frames zwischen Schüssen
FPS = 20
WHITE = (255, 255, 255)
RED = (255, 0, 0)
BLACK = (0, 0, 0)

def hypot(x, y):
    return math.sqrt(x*x + y*y)

class AsteroidGame:
    def __init__(self):
        self.display = display
        self.ship = Ship()
        self.asteroids = [Asteroid(start=True) for _ in range(3)]
        self.projectiles = []
        self.running = True
        self.score = 0

    def check_collisions(self):
        # Kollisionen zwischen Projektilen und Asteroiden
        for projectile in self.projectiles[:]:
            for asteroid in self.asteroids[:]:
                distance = hypot(projectile.x - asteroid.x, projectile.y - asteroid.y)
                if distance < asteroid.size:
                    self.projectiles.remove(projectile)
                    self.asteroids.remove(asteroid)
                    self.score += 10
                    # Zerlege den Asteroiden, wenn er groß genug ist
                    if asteroid.size > 3:
                        for _ in range(2):
                            new_size = asteroid.size // 2
                            self.asteroids.append(Asteroid(asteroid.x, asteroid.y, new_size))
                    break

        # Kollisionen zwischen Schiff und Asteroiden
        for asteroid in self.asteroids:
            distance = hypot(self.ship.x - asteroid.x, self.ship.y - asteroid.y)
            if distance < asteroid.size + self.ship.size:
                self.running = False
                self.score = max(self.score, self.score)  # Optional: Halte den höchsten Score
                break

    def main_loop(self, joystick):
        """
        Hauptspiel-Schleife für das Asteroid-Spiel.

        Args:
            joystick: Das Joystick-Objekt zur Steuerung.
        """
        self.running = True
        self.score = 0
        while self.running:
            start_time = ticks_ms()

            c_button, z_button = joystick.nunchuck.buttons()
            if c_button:  # C-Taste beendet das Spiel
                self.running = False

            direction = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
            if direction:
                self.ship.update(direction)
            else:
                self.ship.update(None)

            if z_button:
                projectile = self.ship.shoot()
                if projectile:
                    self.projectiles.append(projectile)

            self.ship.update(direction)

            for asteroid in self.asteroids:
                asteroid.update()

            for projectile in self.projectiles[:]:
                projectile.update()
                if not projectile.is_alive():
                    self.projectiles.remove(projectile)

            self.check_collisions()

            self.display.clear()

            # Zeichnen aller Objekte
            self.ship.draw()
            for asteroid in self.asteroids:
                asteroid.draw()
            for projectile in self.projectiles:
                projectile.draw()

            # Spielstand anzeigen
            display_score_and_time(self.score)

            # Framerate kontrollieren
            elapsed = ticks_diff(ticks_ms(), start_time)
            frame_duration = 10 // FPS
            sleep_time = frame_duration - elapsed
            if sleep_time > 0:
                sleep_ms(sleep_time)

class GameSelect:
    """
    Class for selecting and running games.
    """

    def __init__(self):
        """
        Initialize the game selector with available games.
        """

        self.joystick = Joystick()


        self.games = {
            "SNAKE": SnakeGame(),
            "SIMON": SimonGame(),
            "BRKOUT": BreakoutGame(),
            "ASTRD": AsteroidGame(),
            "PONG": PongGame(),
            "QIX": QixGame(),
            "TETRIS": TetrisGame(),
        }
        self.selected_game = None

    def run_game(self, game_name):
        """
        Run the selected game.

        Args:
            game_name (str): Name of the game to run.
        """
        global game_over
        game_over = False
        self.games[game_name].main_loop(self.joystick)

    def run_game_selector(self):
        """
        Display the game selection menu and handle user input.
        """
        games_list = list(self.games.keys())
        selected_index = 0
        previous_selected = None
        top_index = 0
        display_size = 4
        last_move_time = time.time()
        debounce_delay = 0.1

        while True:
            current_time = time.time()

            if selected_index != previous_selected:
                previous_selected = selected_index
                display.clear()
                for i in range(display_size):
                    game_idx = top_index + i
                    if game_idx < len(games_list):
                        color = (
                            (255, 255, 255)
                            if game_idx == selected_index
                            else (111, 111, 111)
                        )
                        draw_text(8, 5 + i * 15, games_list[game_idx], *color)

            if current_time - last_move_time > debounce_delay:
                direction = self.joystick.read_direction(
                    [JOYSTICK_UP, JOYSTICK_DOWN], debounce=False
                )
                if direction == JOYSTICK_UP and selected_index > 0:
                    selected_index -= 1
                    if selected_index < top_index:
                        top_index -= 1
                    last_move_time = current_time
                elif (
                    direction == JOYSTICK_DOWN and selected_index < len(games_list) - 1
                ):
                    selected_index += 1
                    if selected_index > top_index + display_size - 1:
                        top_index += 1
                    last_move_time = current_time

            if self.joystick.is_pressed():
                self.selected_game = games_list[selected_index]
                break

            sleep_ms(50)

    def run(self):
        """
        Main loop to run the game selector and handle game execution.
        """
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
                except Exception as error:
                    print(f"Error: {error}")
                    self.selected_game = None


class GameOverMenu:
    """
    Class for displaying the game over menu.
    """

    def __init__(self):
        """
        Initialize the game over menu with options.
        """
        self.joystick = Joystick()
        self.menu_options = ["RETRY", "MENU"]
        self.selected_option = None

    def run_game_over_menu(self):
        """
        Display the game over menu and handle user input.
        """
        global last_game, global_score, game_over
        selected_index = 0
        previous_selected = None
        last_move_time = time.time()
        debounce_delay = 0.1
        game_over = False
        display.clear()

        while True:
            current_time = time.time()

            # Display "Game Over" message
            draw_text(10, 10, "LOST", 255, 20, 20)
            display_score_and_time(global_score)

            # Display menu options
            if selected_index != previous_selected:
                previous_selected = selected_index
                display.clear()
                for i, option in enumerate(self.menu_options):
                    color = (255, 255, 255) if i == selected_index else (111, 111, 111)
                    draw_text(8, 30 + i * 15, option, *color)

            if current_time - last_move_time > debounce_delay:
                direction = self.joystick.read_direction(
                    [JOYSTICK_UP, JOYSTICK_DOWN], debounce=False
                )
                if direction == JOYSTICK_UP and selected_index > 0:
                    selected_index -= 1
                    last_move_time = current_time
                elif (
                    direction == JOYSTICK_DOWN
                    and selected_index < len(self.menu_options) - 1
                ):
                    selected_index += 1
                    last_move_time = current_time

            if self.joystick.is_pressed():
                if self.menu_options[selected_index] == "RETRY":
                    global_score = 0
                    GameSelect().run_game(last_game)
                elif self.menu_options[selected_index] == "MENU":
                    return

            sleep_ms(50)

if __name__ == "__main__":
    # Initialize PyGame
    pygame.init()
    input_handler = InputHandler()

    # Start the game selection
    game_state = GameSelect()

    # Start the display
    display.start()

    # Run the main game loop
    game_state.run()
