import hub75
import random
import time
import machine
import math

# Constants for display dimensions
HEIGHT = 64
WIDTH = 64

# Initialize the display
display = hub75.Hub75(WIDTH, HEIGHT)

# Global variables for game state
global_score = 0
last_game = None
game_over = False

# Color definitions for Simon game
COLORS_BRIGHT = [
    (255, 0, 0),    # Red
    (0, 255, 0),    # Green
    (0, 0, 255),    # Blue
    (255, 255, 0),  # Yellow
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
    "|": "1818181818181818",
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
    "|": ["00100", "00100", "00100", "00100", "00100"],
    "-": ["00000", "00000", "11111", "00000", "00000"],
    "=": ["00000", "11111", "00000", "11111", "00000"],
    "+": ["00000", "00100", "01110", "00100", "00000"],
    "*": ["00000", "10101", "01110", "10101", "00000"],
    "(": ["00010", "00100", "00100", "00100", "00010"],
    ")": ["00100", "00010", "00010", "00010", "00100"],
}

def hypot(x, y):
    return math.sqrt(x*x + y*y)

def sleep_ms(ms):
    """
    Sleep for the given number of milliseconds.
    """
    time.sleep(ms / 1000)

def get_time():
    return time.time()

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
    year, month, day, weekday, hour, minute, second, _ = rtc.datetime()
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

# Optimized Grid Management
grid = bytearray(WIDTH * HEIGHT // 2)  # Reduced grid size to save memory

def initialize_grid():
    """
    Initialize the grid to be empty.
    """
    global grid
    grid = bytearray(WIDTH * HEIGHT // 2)

def get_grid_value(x, y):
    """
    Get the value at position (x, y) in the grid.
    """
    index = y * WIDTH + x
    return (grid[index // 2] >> ((index % 2) * 4)) & 0x0F

def set_grid_value(x, y, value):
    """
    Set the value at position (x, y) in the grid.
    """
    index = y * WIDTH + x
    half_index = index // 2
    shift = (index % 2) * 4
    grid[half_index] = (grid[half_index] & ~(0x0F << shift)) | ((value & 0x0F) << shift)

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

rtc = machine.RTC()

# Exception to restart the program / go back to the main menu
class RestartProgram(Exception):
    pass

class Nunchuck:
    """
    Class to handle Wii Nunchuk inputs over I2C.
    """

    def __init__(self, i2c, poll=True, poll_interval=50):
        self.i2c = i2c
        self.address = 0x52
        self.buffer = bytearray(6)  # Buffer to store sensor data

        # Initialization sequence for the Nunchuk
        self.i2c.writeto(self.address, b"\xf0\x55")
        self.i2c.writeto(self.address, b"\xfb\x00")

        # Timestamp of the last polling update
        self.last_poll = time.ticks_ms()

        # Polling interval in milliseconds
        self.polling_threshold = poll_interval if poll else -1

    def update(self):
        """
        Update the buffer with new data from the Nunchuk.
        """
        self.i2c.writeto(self.address, b"\x00")
        self.i2c.readfrom_into(self.address, self.buffer)

    def __poll(self):
        """
        Internal method to handle polling based on the threshold.
        """
        if (
            self.polling_threshold > 0
            and time.ticks_diff(time.ticks_ms(), self.last_poll)
            > self.polling_threshold
        ):
            self.update()
            self.last_poll = time.ticks_ms()

    def accelerator(self):
        """
        Get accelerometer data.
        """
        self.__poll()
        return (
            (self.buffer[2] << 2) + ((self.buffer[5] & 0x0C) >> 2),
            (self.buffer[3] << 2) + ((self.buffer[5] & 0x30) >> 4),
            (self.buffer[4] << 2) + ((self.buffer[5] & 0xC0) >> 6),
        )

    def buttons(self):
        """
        Get button states (C and Z buttons).
        """
        self.__poll()

        c_button = not (self.buffer[5] & 0x02)
        z_button = not (self.buffer[5] & 0x01)

        if c_button and z_button:
            #machine.reset()
            raise RestartProgram()

        return c_button, z_button

    def joystick(self):
        """
        Get joystick positions.
        """
        self.__poll()
        return (self.buffer[0], self.buffer[1])

    def joystick_left(self):
        """
        Check if joystick is tilted to the left.
        """
        self.__poll()
        return self.buffer[0] < 55

    def joystick_right(self):
        """
        Check if joystick is tilted to the right.
        """
        self.__poll()
        return self.buffer[0] > 200

    def joystick_up(self):
        """
        Check if joystick is tilted up.
        """
        self.__poll()
        return self.buffer[1] > 200

    def joystick_down(self):
        """
        Check if joystick is tilted down.
        """
        self.__poll()
        return self.buffer[1] < 55

    def joystick_center(self):
        """
        Check if joystick is in the center position.
        """
        self.__poll()
        return 100 < self.buffer[0] < 155 and 100 < self.buffer[1] < 155

    def joystick_x(self):
        """
        Get X-axis value of the joystick.
        """
        self.__poll()
        return (self.buffer[0] >> 2) - 34

    def joystick_y(self):
        """
        Get Y-axis value of the joystick.
        """
        self.__poll()
        return (self.buffer[1] >> 2) - 34

    def is_shaking(self):
        """
        Detect shaking motion using accelerometer data.
        """
        x, y, z = self.accelerator()
        return max(x, y, z) > 800  # Threshold for detection

class Joystick:
    """
    Class to handle joystick inputs, either via analog inputs or I2C (Nunchuk).
    """

    def __init__(self):
        self.joystick_mode = "i2c"

        if self.joystick_mode == "i2c":
            self.i2c = machine.I2C(0, scl=machine.Pin(21), sda=machine.Pin(20))
            self.nunchuck = Nunchuck(self.i2c)

    def read_direction(self, possible_directions, debounce=True):
        """
        Read the joystick direction based on possible directions.
        """
        if self.joystick_mode == "i2c":
            x, y = self.nunchuck.joystick()
            # Map joystick positions to directions
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
        return None

    def is_pressed(self):
        """
        Check if the joystick button is pressed.
        """
        if self.joystick_mode == "i2c":
            _, z = self.nunchuck.buttons()
            return z
        return False

def hsb_to_rgb(hue, saturation, brightness):
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

# Game Classes

class SimonGame:
    """
    Class representing the Simon Says game.
    """

    # Class-level attributes for memory efficiency
    WIDTH = 64
    HEIGHT = 64
    HALF_WIDTH = WIDTH // 2
    HALF_HEIGHT = (HEIGHT - 6) // 2  # Adjust for score display area

    # Static colors for inactive and active states
    COLORS_BRIGHT = [
        (255, 0, 0),    # Red
        (0, 255, 0),    # Green
        (0, 0, 255),    # Blue
        (255, 255, 0),  # Yellow
    ]
    INACTIVE_COLORS = [
        (128, 0, 0),    # Dim Red
        (0, 128, 0),    # Dim Green
        (0, 0, 128),    # Dim Blue
        (128, 128, 0),  # Dim Yellow
    ]

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
        # Pre-calculate quadrant boundaries
        quadrants = [
            (0, 0, self.HALF_WIDTH, self.HALF_HEIGHT),
            (self.HALF_WIDTH, 0, self.WIDTH, self.HALF_HEIGHT),
            (0, self.HALF_HEIGHT, self.HALF_WIDTH, self.HEIGHT - 7),
            (self.HALF_WIDTH, self.HALF_HEIGHT, self.WIDTH, self.HEIGHT - 7)
        ]
        
        # Draw all quadrants with inactive colors
        for i, (x1, y1, x2, y2) in enumerate(quadrants):
            draw_rectangle(x1, y1, x2 - 1, y2 - 1, *self.INACTIVE_COLORS[i])

    def flash_color(self, index, duration=500):
        """
        Flash a specific color on the screen.

        Args:
            index (int): Index of the color to flash.
            duration (int): Duration to display the color in milliseconds.
        """
        # Calculate quadrant boundaries based on the index
        x_offset = (index % 2) * self.HALF_WIDTH
        y_offset = (index // 2) * self.HALF_HEIGHT

        # Draw the active color in the specified quadrant
        draw_rectangle(x_offset, y_offset, x_offset + self.HALF_WIDTH - 1,
                       y_offset + self.HALF_HEIGHT - 1, *self.COLORS_BRIGHT[index])

        sleep_ms(duration)

        # Restore the inactive color
        draw_rectangle(x_offset, y_offset, x_offset + self.HALF_WIDTH - 1,
                       y_offset + self.HALF_HEIGHT - 1, *self.INACTIVE_COLORS[index])

    def play_sequence(self):
        """
        Play the current sequence by flashing the colors.
        """
        for color_index in self.sequence:
            self.flash_color(color_index)
            sleep_ms(200)  # Shorter sleep for smoother transitions

    def get_user_input(self, joystick):
        """
        Get the user's input via the joystick.

        Args:
            joystick (Joystick): The joystick object.

        Returns:
            int: The direction selected by the user mapped to the color index.
        """
        direction_map = {
            JOYSTICK_UP_LEFT: 0,
            JOYSTICK_UP_RIGHT: 1,
            JOYSTICK_DOWN_LEFT: 2,
            JOYSTICK_DOWN_RIGHT: 3
        }

        while True:
            direction = joystick.read_direction(direction_map.keys())
            if direction in direction_map:
                return direction_map[direction]
            sleep_ms(50)  # Reduced sleep to lower response time

    def check_user_sequence(self):
        """
        Check if the user's input matches the game sequence.

        Returns:
            bool: True if sequences match, False otherwise.
        """
        return self.user_input == self.sequence[:len(self.user_input)]

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
            try:
                # Check for exit condition
                c_button, _ = joystick.nunchuck.buttons()
                if c_button:  # C-button ends the game
                    game_over = True
                    return

                # Add a random color to the sequence
                self.sequence.append(random.randint(0, 3))
                display_score_and_time(len(self.sequence) - 1)

                # Play the sequence
                self.play_sequence()
                self.user_input = []

                # Get user input and validate
                for _ in range(len(self.sequence)):
                    selected_color = self.get_user_input(joystick)
                    if selected_color is not None:
                        self.flash_color(selected_color, duration=200)
                        self.user_input.append(selected_color)
                        if not self.check_user_sequence():
                            global_score = len(self.sequence) - 1
                            game_over = True
                            return
                    else:
                        break

                sleep_ms(500)  # Small delay between sequences
                gc.collect()  # Manually trigger garbage collection for efficiency
            except RestartProgram:
                game_over = True
                return


class SnakeGame:
    """
    Class representing the Snake game.
    """

    # Class-level attributes for memory efficiency
    WIDTH = 64
    HEIGHT = 64
    INITIAL_LENGTH = 3
    INITIAL_POSITION = (32, 32)
    MAX_GREEN_TARGETS = 5

    # Static colors
    SNAKE_COLOR = (0, 255, 0)
    TARGET_COLOR = (255, 0, 0)
    GREEN_TARGET_COLOR = (0, 255, 0)
    CLEAR_COLOR = (0, 0, 0)

    def __init__(self):
        """
        Initialize the Snake game variables.
        """
        self.snake = [self.INITIAL_POSITION]  # Only store head initially
        self.snake_length = self.INITIAL_LENGTH
        self.snake_direction = "UP"
        self.score = 0
        self.green_targets = []
        self.target = self.random_target()
        self.running = True

    def random_target(self):
        """
        Generate a random position for the target.
        """
        return (random.randint(1, self.WIDTH - 2), random.randint(1, self.HEIGHT - 8))

    def restart_game(self):
        """
        Restart the game by resetting variables and clearing the display.
        """
        self.snake = [self.INITIAL_POSITION]
        self.snake_length = self.INITIAL_LENGTH
        self.snake_direction = "UP"
        self.score = 0
        self.green_targets.clear()
        display.clear()
        self.place_target()

    def place_target(self):
        """
        Place the target on the display.
        """
        self.target = self.random_target()
        display.set_pixel(self.target[0], self.target[1], *self.TARGET_COLOR)

    def place_green_target(self):
        """
        Place a green target on the display.
        """
        if len(self.green_targets) < self.MAX_GREEN_TARGETS:
            x, y = self.random_target()
            self.green_targets.append((x, y, 256))
            display.set_pixel(x, y, *self.GREEN_TARGET_COLOR)

    def update_green_targets(self):
        """
        Update the lifespan of green targets and remove them if necessary.
        """
        updated_targets = []
        for x, y, lifespan in self.green_targets:
            if lifespan > 1:
                updated_targets.append((x, y, lifespan - 1))
            else:
                display.set_pixel(x, y, *self.CLEAR_COLOR)
        self.green_targets = updated_targets

    def check_self_collision(self):
        """
        Check for collision of the snake with itself.
        """
        global game_over
        head = self.snake[0]
        if head in self.snake[1:]:
            game_over = True

    def update_snake_position(self):
        """
        Update the position of the snake based on its current direction.
        """
        head_x, head_y = self.snake[0]
        new_head = {
            "UP": (head_x, (head_y - 1) % self.HEIGHT),
            "DOWN": (head_x, (head_y + 1) % self.HEIGHT),
            "LEFT": ((head_x - 1) % self.WIDTH, head_y),
            "RIGHT": ((head_x + 1) % self.WIDTH, head_y),
        }[self.snake_direction]

        # Add new head to the snake
        self.snake.insert(0, new_head)

        # Remove tail if the snake hasn't grown
        if len(self.snake) > self.snake_length:
            tail = self.snake.pop()
            display.set_pixel(tail[0], tail[1], *self.CLEAR_COLOR)

    def check_target_collision(self):
        """
        Check if the snake has collided with the target.
        """
        head = self.snake[0]
        if head == self.target:
            self.snake_length += 2
            self.place_target()
            self.score += 1

    def check_green_target_collision(self):
        """
        Check if the snake has collided with a green target.
        """
        head = self.snake[0]
        for target in self.green_targets:
            if (head[0], head[1]) == (target[0], target[1]):
                self.snake_length = max(self.snake_length // 2, 2)
                self.green_targets.remove(target)
                display.set_pixel(target[0], target[1], *self.CLEAR_COLOR)

    def draw_snake(self):
        """
        Draw the snake on the display.
        """
        for i, (x, y) in enumerate(self.snake):
            # Dim the color for the body based on its position
            brightness = 1 - (i / len(self.snake)) * 0.5
            red, green, blue = (int(c * brightness) for c in self.SNAKE_COLOR)
            display.set_pixel(x, y, red, green, blue)

    def main_loop(self, joystick):
        """
        Main game loop for the Snake game.

        Args:
            joystick (Joystick): The joystick object.
        """
        global game_over
        game_over = False
        self.restart_game()
        while not game_over:
            try:
                c_button, _ = joystick.nunchuck.buttons()
                if c_button:  # C-button ends the game
                    game_over = True

                direction = joystick.read_direction(
                    [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
                )
                if direction:
                    self.snake_direction = direction

                self.update_snake_position()
                self.check_self_collision()
                self.check_target_collision()
                self.check_green_target_collision()
                self.draw_snake()
                self.update_green_targets()
                display_score_and_time(self.score)

                sleep_ms(max(30, 90 - max(10, self.snake_length // 3)))
                gc.collect()
            except RestartProgram:
                game_over = True
                return



class PongGame:
    """
    Class representing the Pong game.
    """

    # Class-level attributes for memory efficiency
    WIDTH = 64
    HEIGHT = 64
    PADDLE_HEIGHT = 8
    PADDLE_SPEED = 2
    BALL_INITIAL_SPEED = [1, 1]
    LIVES = 3

    # Static colors
    BALL_COLOR = (255, 255, 255)
    PADDLE_COLOR = (255, 255, 255)
    CLEAR_COLOR = (0, 0, 0)

    def __init__(self):
        """
        Initialize the Pong game variables.
        """
        self.ball_speed = self.BALL_INITIAL_SPEED[:]
        self.ball_position = [self.WIDTH // 2, self.HEIGHT // 2]
        self.left_paddle_y = self.HEIGHT // 2 - self.PADDLE_HEIGHT // 2
        self.right_paddle_y = self.HEIGHT // 2 - self.PADDLE_HEIGHT // 2
        self.score = 0
        self.lives = self.LIVES

    def draw_paddle(self, x, paddle_y):
        """
        Draw the paddle on the display.
        """
        for y in range(paddle_y, paddle_y + self.PADDLE_HEIGHT):
            display.set_pixel(x, y, *self.PADDLE_COLOR)

    def clear_paddle(self, x, paddle_y):
        """
        Clear the paddle from its current position.
        """
        for y in range(paddle_y, paddle_y + self.PADDLE_HEIGHT):
            display.set_pixel(x, y, *self.CLEAR_COLOR)

    def draw_ball(self):
        """
        Draw the ball on the display.
        """
        x, y = self.ball_position
        display.set_pixel(x, y, *self.BALL_COLOR)

    def clear_ball(self):
        """
        Clear the ball from its current position.
        """
        x, y = self.ball_position
        display.set_pixel(x, y, *self.CLEAR_COLOR)

    def update_ball(self):
        """
        Update the ball's position and handle collisions.
        """
        global game_over
        self.clear_ball()
        self.ball_position[0] += self.ball_speed[0]
        self.ball_position[1] += self.ball_speed[1]

        x, y = self.ball_position

        # Handle collision with top and bottom walls
        if y <= 0 or y >= self.HEIGHT - 1:
            self.ball_speed[1] = -self.ball_speed[1]

        # Handle collision with left paddle
        if x == 1 and self.left_paddle_y <= y < self.left_paddle_y + self.PADDLE_HEIGHT:
            self.ball_speed[0] = -self.ball_speed[0]
            self.score += 1

        # Handle collision with right paddle
        elif x == self.WIDTH - 2 and self.right_paddle_y <= y < self.right_paddle_y + self.PADDLE_HEIGHT:
            self.ball_speed[0] = -self.ball_speed[0]

        # Ball misses the left paddle
        if x <= 0:
            self.lives -= 1
            if self.lives == 0:
                game_over = True
                return
            self.reset_ball()

        # Ball misses the right paddle
        elif x >= self.WIDTH - 1:
            self.score += 10
            self.reset_ball()

        self.draw_ball()

    def reset_ball(self):
        """
        Reset the ball to the center of the display with a random direction.
        """
        self.ball_position = [self.WIDTH // 2, self.HEIGHT // 2]
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
            self.clear_paddle(0, self.left_paddle_y)
            self.left_paddle_y = max(self.left_paddle_y - self.PADDLE_SPEED, 0)
        elif direction == JOYSTICK_DOWN:
            self.clear_paddle(0, self.left_paddle_y)
            self.left_paddle_y = min(
                self.left_paddle_y + self.PADDLE_SPEED, self.HEIGHT - self.PADDLE_HEIGHT
            )

        # Simple AI for right paddle
        ball_y = self.ball_position[1]
        paddle_center = self.right_paddle_y + self.PADDLE_HEIGHT // 2
        if ball_y < paddle_center:
            self.clear_paddle(self.WIDTH - 1, self.right_paddle_y)
            self.right_paddle_y = max(self.right_paddle_y - self.PADDLE_SPEED, 0)
        elif ball_y > paddle_center:
            self.clear_paddle(self.WIDTH - 1, self.right_paddle_y)
            self.right_paddle_y = min(
                self.right_paddle_y + self.PADDLE_SPEED, self.HEIGHT - self.PADDLE_HEIGHT
            )

        # Draw paddles after updates
        self.draw_paddle(0, self.left_paddle_y)
        self.draw_paddle(self.WIDTH - 1, self.right_paddle_y)

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
            try:
                c_button, _ = joystick.nunchuck.buttons()
                if c_button:  # C-button ends the game
                    game_over = True

                self.update_paddles(joystick)
                self.update_ball()
                display_score_and_time(self.score)

                sleep_ms(50)
                gc.collect()
            except RestartProgram:
                game_over = True
                return


class BreakoutGame:
    """
    Class representing the Breakout game.
    """

    # Class-level attributes for memory efficiency
    WIDTH = 64
    HEIGHT = 64
    PADDLE_WIDTH = 10
    PADDLE_HEIGHT = 2
    BALL_SIZE = 2
    BRICK_WIDTH = 8
    BRICK_HEIGHT = 4
    BRICK_ROWS = 5
    BRICK_COLS = 8

    # Static colors
    PADDLE_COLOR = (255, 255, 255)
    BALL_COLOR = (255, 255, 255)
    CLEAR_COLOR = (0, 0, 0)

    def __init__(self):
        """
        Initialize the Breakout game variables.
        """
        self.paddle_x = (self.WIDTH - self.PADDLE_WIDTH) // 2
        self.paddle_y = self.HEIGHT - self.PADDLE_HEIGHT
        self.ball_x = self.WIDTH // 2
        self.ball_y = self.HEIGHT // 2
        self.ball_dx = 1
        self.ball_dy = -1
        self.bricks = self.create_bricks()
        self.score = 0
        self.lives = 3

    def create_bricks(self):
        """
        Create the initial set of bricks.

        Returns:
            list: List of brick positions.
        """
        bricks = []
        for row in range(self.BRICK_ROWS):
            for col in range(self.BRICK_COLS):
                x = col * (self.BRICK_WIDTH + 1) + 1
                y = row * (self.BRICK_HEIGHT + 1)
                bricks.append((x, y))
        return bricks

    def draw_paddle(self):
        """
        Draw the paddle on the display.
        """
        for x in range(self.paddle_x, self.paddle_x + self.PADDLE_WIDTH):
            for y in range(self.paddle_y, self.paddle_y + self.PADDLE_HEIGHT):
                display.set_pixel(x, y, *self.PADDLE_COLOR)

    def clear_paddle(self):
        """
        Clear the paddle from its current position.
        """
        for x in range(self.paddle_x, self.paddle_x + self.PADDLE_WIDTH):
            for y in range(self.paddle_y, self.paddle_y + self.PADDLE_HEIGHT):
                display.set_pixel(x, y, *self.CLEAR_COLOR)

    def draw_ball(self):
        """
        Draw the ball on the display.
        """
        for dx in range(self.BALL_SIZE):
            for dy in range(self.BALL_SIZE):
                display.set_pixel(self.ball_x + dx, self.ball_y + dy, *self.BALL_COLOR)

    def clear_ball(self):
        """
        Clear the ball from its current position.
        """
        for dx in range(self.BALL_SIZE):
            for dy in range(self.BALL_SIZE):
                display.set_pixel(self.ball_x + dx, self.ball_y + dy, *self.CLEAR_COLOR)

    def draw_bricks(self):
        """
        Draw all the bricks on the display.
        """
        for x, y in self.bricks:
            hue = (y * 360) // (self.BRICK_ROWS * self.BRICK_COLS)
            red, green, blue = hsb_to_rgb(hue, 1, 1)
            for dx in range(self.BRICK_WIDTH):
                for dy in range(self.BRICK_HEIGHT):
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
        if self.ball_x <= 0 or self.ball_x >= self.WIDTH - self.BALL_SIZE:
            self.ball_dx = -self.ball_dx
        if self.ball_y <= 1:
            self.ball_dy = -self.ball_dy

        # Handle collision with paddle
        if self.ball_y >= self.HEIGHT - self.PADDLE_HEIGHT - self.BALL_SIZE:
            if self.paddle_x <= self.ball_x <= self.paddle_x + self.PADDLE_WIDTH:
                self.ball_dy = -self.ball_dy

        # Ball falls below paddle
        if self.ball_y >= self.HEIGHT:
            self.lives -= 1
            if self.lives == 0:
                game_over = True
                return
            self.reset_ball()

        self.draw_ball()

    def check_collision_with_bricks(self):
        """
        Check for collision between the ball and bricks.
        """
        global global_score
        for brick in self.bricks[:]:
            bx, by = brick
            if (
                bx <= self.ball_x < bx + self.BRICK_WIDTH
                and by <= self.ball_y < by + self.BRICK_HEIGHT
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
            self.paddle_x = max(self.paddle_x - 2, 0)
        elif direction == JOYSTICK_RIGHT:
            self.clear_paddle()
            self.paddle_x = min(self.paddle_x + 2, self.WIDTH - self.PADDLE_WIDTH)
        self.draw_paddle()

    def reset_ball(self):
        """
        Reset the ball to the center of the display with a random direction.
        """
        self.ball_x = self.WIDTH // 2
        self.ball_y = self.HEIGHT // 2
        self.ball_dx = random.choice([-1, 1])
        self.ball_dy = random.choice([-1, 1])

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
            try:
                c_button, _ = joystick.nunchuck.buttons()
                if c_button:  # C-button ends the game
                    game_over = True

                self.update_ball()
                self.check_collision_with_bricks()
                self.update_paddle(joystick)
                display_score_and_time(self.score)

                if self.score == self.BRICK_ROWS * self.BRICK_COLS * 10:
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
                gc.collect()
            except RestartProgram:
                game_over = True
                return


class AsteroidGame:
    """
    Class representing the Asteroid game.
    """

    # Class-level constants for memory efficiency
    WIDTH = 64
    HEIGHT = 64
    SHIP_COOLDOWN = 10  # Frames between shots
    MAX_PROJECTILE_LIFETIME = 10
    FPS = 20
    MAX_ASTEROIDS = 3
    WHITE = (255, 255, 255)
    RED = (255, 0, 0)
    CLEAR_COLOR = (0, 0, 0)

    def __init__(self):
        """
        Initialize the game variables.
        """
        self.ship = self.Ship()
        self.asteroids = [self.Asteroid(start=True) for _ in range(self.MAX_ASTEROIDS)]
        self.projectiles = []
        self.score = 0
        self.running = True

    class Projectile:
        def __init__(self, x, y, angle, speed):
            self.x = x
            self.y = y
            self.angle = angle
            self.speed = speed
            self.lifetime = AsteroidGame.MAX_PROJECTILE_LIFETIME

        def update(self):
            self.x += math.cos(math.radians(self.angle)) * self.speed
            self.y -= math.sin(math.radians(self.angle)) * self.speed
            self.x %= AsteroidGame.WIDTH
            self.y %= AsteroidGame.HEIGHT
            self.lifetime -= 1

        def is_alive(self):
            return self.lifetime > 0
        
        def draw(self):
            display.set_pixel(int(self.x) % AsteroidGame.WIDTH, int(self.y) % AsteroidGame.HEIGHT, *AsteroidGame.RED)

    class Asteroid:
        def __init__(self, x=None, y=None, size=None, start=False):
            self.x = random.uniform(0, AsteroidGame.WIDTH) if x is None else x
            self.y = random.uniform(0, AsteroidGame.HEIGHT) if y is None else y
            if start:
                while 22 < self.x < 42 or 22 < self.y < 42:
                    self.x = random.uniform(0, AsteroidGame.WIDTH)
                    self.y = random.uniform(0, AsteroidGame.HEIGHT)
            self.angle = random.uniform(0, 360)
            self.speed = random.uniform(0.5, 1.5)
            self.size = size if size is not None else random.randint(4, 8)

        def update(self):
            self.x += math.cos(math.radians(self.angle)) * self.speed
            self.y -= math.sin(math.radians(self.angle)) * self.speed
            self.x %= AsteroidGame.WIDTH
            self.y %= AsteroidGame.HEIGHT

        def draw(self):
            for degree in range(0, 360, 10):
                rad = math.radians(degree)
                px = int((self.x + math.cos(rad) * self.size) % AsteroidGame.WIDTH)
                py = int((self.y + math.sin(rad) * self.size) % AsteroidGame.HEIGHT)
                display.set_pixel(px, py, *AsteroidGame.WHITE)

    class Ship:
        def __init__(self):
            self.x = AsteroidGame.WIDTH / 2
            self.y = AsteroidGame.HEIGHT / 2
            self.angle = 0
            self.speed = 0
            self.max_speed = 2
            self.size = 3
            self.cooldown = 0

        def update(self, direction):
            if direction == JOYSTICK_LEFT:
                self.angle = (self.angle + 5) % 360
            elif direction == JOYSTICK_RIGHT:
                self.angle = (self.angle - 5) % 360

            if direction == JOYSTICK_UP:
                self.speed = min(self.speed + 0.1, self.max_speed)
            else:
                self.speed = max(self.speed - 0.05, 0)

            self.x += math.cos(math.radians(self.angle)) * self.speed
            self.y -= math.sin(math.radians(self.angle)) * self.speed
            self.x %= AsteroidGame.WIDTH
            self.y %= AsteroidGame.HEIGHT

            if self.cooldown > 0:
                self.cooldown -= 1

        def draw(self):
            points = [
                (self.x + math.cos(math.radians(self.angle)) * self.size,
                 self.y - math.sin(math.radians(self.angle)) * self.size),
                (self.x + math.cos(math.radians(self.angle + 120)) * self.size,
                 self.y - math.sin(math.radians(self.angle + 120)) * self.size),
                (self.x + math.cos(math.radians(self.angle - 120)) * self.size,
                 self.y - math.sin(math.radians(self.angle - 120)) * self.size),
            ]

            self.draw_line(points[1], points[2], AsteroidGame.RED if self.speed > 0 else AsteroidGame.WHITE)
            self.draw_line(points[0], points[1], AsteroidGame.WHITE)
            self.draw_line(points[2], points[0], AsteroidGame.WHITE)

        def draw_line(self, start, end, color):
            x0, y0 = int(start[0]), int(start[1])
            x1, y1 = int(end[0]), int(end[1])
            dx = abs(x1 - x0)
            dy = abs(y1 - y0)
            sx = -1 if x0 > x1 else 1
            sy = -1 if y0 > y1 else 1
            if dx > dy:
                err = dx / 2.0
                while x0 != x1:
                    display.set_pixel(x0 % AsteroidGame.WIDTH, y0 % AsteroidGame.HEIGHT, *color)
                    err -= dy
                    if err < 0:
                        y0 += sy
                        err += dx
                    x0 += sx
            else:
                err = dy / 2.0
                while y0 != y1:
                    display.set_pixel(x0 % AsteroidGame.WIDTH, y0 % AsteroidGame.HEIGHT, *color)
                    err -= dx
                    if err < 0:
                        x0 += sx
                        err += dy
                    y0 += sy
            display.set_pixel(x0 % AsteroidGame.WIDTH, y0 % AsteroidGame.HEIGHT, *color)

        def shoot(self):
            if self.cooldown == 0:
                self.cooldown = AsteroidGame.SHIP_COOLDOWN
                bullet_speed = 4
                bullet_x = self.x + math.cos(math.radians(self.angle)) * self.size
                bullet_y = self.y - math.sin(math.radians(self.angle)) * self.size
                return AsteroidGame.Projectile(bullet_x, bullet_y, self.angle, bullet_speed)
            return None

    def check_collisions(self):
        for projectile in self.projectiles[:]:
            for asteroid in self.asteroids[:]:
                if hypot(projectile.x - asteroid.x, projectile.y - asteroid.y) < asteroid.size:
                    self.projectiles.remove(projectile)
                    self.asteroids.remove(asteroid)
                    self.score += 10
                    if asteroid.size > 3:
                        for _ in range(2):
                            new_size = asteroid.size // 2
                            self.asteroids.append(self.Asteroid(asteroid.x, asteroid.y, new_size))
                    break

        for asteroid in self.asteroids:
            if hypot(self.ship.x - asteroid.x, self.ship.y - asteroid.y) < asteroid.size + self.ship.size:
                self.running = False
                break

    def main_loop(self, joystick):
        self.running = True
        while self.running:
            start_time = time.ticks_ms()

            c_button, z_button = joystick.nunchuck.buttons()
            if c_button:
                self.running = False

            direction = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT])
            self.ship.update(direction)

            if z_button:
                projectile = self.ship.shoot()
                if projectile:
                    self.projectiles.append(projectile)

            for asteroid in self.asteroids:
                asteroid.update()

            for projectile in self.projectiles[:]:
                projectile.update()
                if not projectile.is_alive():
                    self.projectiles.remove(projectile)

            self.check_collisions()

            display.clear()

            self.ship.draw()
            for asteroid in self.asteroids:
                asteroid.draw()
            for projectile in self.projectiles:
                projectile.draw()

            display_score_and_time(self.score)

            elapsed = time.ticks_diff(time.ticks_ms(), start_time)
            frame_duration = 1000 // self.FPS
            if frame_duration - elapsed > 0:
                sleep_ms(frame_duration - elapsed)



class QixGame:
    """
    Class representing the Qix game.
    """

    # Class-level constants for memory efficiency
    WIDTH = 64
    HEIGHT = 64
    BORDER_COLOR = (0, 0, 255)
    PLAYER_COLOR = (0, 255, 0)
    OPPONENT_COLOR = (255, 0, 0)
    TRAIL_COLOR = (0, 255, 0)
    FILL_COLOR = (0, 0, 255)

    # Grid values
    WALL = 1
    FILLED = 2
    OPPONENT = 3
    TRAIL = 4

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
        self.prev_player_pos = self.WALL
        self.grid = bytearray(self.WIDTH * self.HEIGHT // 2)  # Reduced memory usage

    def initialize_game(self):
        """
        Set up the initial state of the game.
        """
        display.clear()
        self.initialize_grid()
        self.draw_frame()
        self.place_player()
        self.place_opponent()

    def initialize_grid(self):
        """
        Initialize the grid to be empty.
        """
        self.grid = bytearray(self.WIDTH * self.HEIGHT // 2)

    def get_grid_value(self, x, y):
        """
        Get the value at position (x, y) in the grid.
        """
        index = y * self.WIDTH + x
        return (self.grid[index // 2] >> ((index % 2) * 4)) & 0x0F

    def set_grid_value(self, x, y, value):
        """
        Set the value at position (x, y) in the grid.
        """
        index = y * self.WIDTH + x
        half_index = index // 2
        shift = (index % 2) * 4
        self.grid[half_index] = (self.grid[half_index] & ~(0x0F << shift)) | ((value & 0x0F) << shift)

    def draw_frame(self):
        """
        Draw a frame around the play area.
        """
        for x in range(self.WIDTH):
            self.set_grid_value(x, 0, self.WALL)
            self.set_grid_value(x, self.HEIGHT - 1, self.WALL)
            display.set_pixel(x, 0, *self.BORDER_COLOR)
            display.set_pixel(x, self.HEIGHT - 1, *self.BORDER_COLOR)

        for y in range(self.HEIGHT):
            self.set_grid_value(0, y, self.WALL)
            self.set_grid_value(self.WIDTH - 1, y, self.WALL)
            display.set_pixel(0, y, *self.BORDER_COLOR)
            display.set_pixel(self.WIDTH - 1, y, *self.BORDER_COLOR)

    def place_player(self):
        """
        Place the player at a random position on the edge.
        """
        edge_positions = (
            [(x, 0) for x in range(self.WIDTH)] +
            [(x, self.HEIGHT - 1) for x in range(self.WIDTH)] +
            [(0, y) for y in range(self.HEIGHT)] +
            [(self.WIDTH - 1, y) for y in range(self.HEIGHT)]
        )
        self.player_x, self.player_y = random.choice(edge_positions)
        display.set_pixel(self.player_x, self.player_y, *self.PLAYER_COLOR)

    def place_opponent(self):
        """
        Place the opponent at a random position inside the playfield.
        """
        self.opponent_x = random.randint(1, self.WIDTH - 2)
        self.opponent_y = random.randint(1, self.HEIGHT - 2)
        self.set_grid_value(self.opponent_x, self.opponent_y, self.OPPONENT)
        display.set_pixel(self.opponent_x, self.opponent_y, *self.OPPONENT_COLOR)

    def move_opponent(self):
        """
        Move the opponent and handle collisions with boundaries and trails.
        """
        global game_over
        next_x = self.opponent_x + self.opponent_dx
        next_y = self.opponent_y + self.opponent_dy

        if self.get_grid_value(next_x, self.opponent_y) in (self.WALL, self.TRAIL):
            self.opponent_dx = -self.opponent_dx

        if self.get_grid_value(self.opponent_x, next_y) in (self.WALL, self.TRAIL):
            self.opponent_dy = -self.opponent_dy

        if self.get_grid_value(next_x, next_y) == self.TRAIL or (next_x == self.player_x and next_y == self.player_y):
            game_over = True
            return

        self.set_grid_value(self.opponent_x, self.opponent_y, 0)
        display.set_pixel(self.opponent_x, self.opponent_y, *self.CLEAR_COLOR)

        self.opponent_x += self.opponent_dx
        self.opponent_y += self.opponent_dy
        display.set_pixel(self.opponent_x, self.opponent_y, *self.OPPONENT_COLOR)

    def move_player(self, joystick):
        """
        Move the player based on joystick input.
        """
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

            if 0 <= new_x < self.WIDTH and 0 <= new_y < self.HEIGHT:
                grid_value = self.get_grid_value(new_x, new_y)
                if grid_value == 0:
                    self.set_grid_value(new_x, new_y, self.TRAIL)
                    display.set_pixel(new_x, new_y, *self.TRAIL_COLOR)
                    self.prev_player_pos = 0
                elif grid_value == self.WALL:
                    if self.prev_player_pos == 0:
                        self.close_area(new_x, new_y)
                    self.prev_player_pos = self.WALL

                self.player_x, self.player_y = new_x, new_y
                display.set_pixel(self.player_x, self.player_y, *self.PLAYER_COLOR)

    def close_area(self, x, y):
        """
        Close an area when the player reconnects with a border or trail.
        """
        self.set_grid_value(x, y, self.WALL)
        display.set_pixel(x, y, *self.BORDER_COLOR)
        self.flood_fill(self.opponent_x, self.opponent_y)

        for i in range(self.WIDTH):
            for j in range(self.HEIGHT):
                grid_value = self.get_grid_value(i, j)
                if grid_value == 0:
                    self.set_grid_value(i, j, self.FILLED)
                    display.set_pixel(i, j, *self.FILL_COLOR)
                elif grid_value == self.OPPONENT:
                    self.set_grid_value(i, j, 0)

        self.calculate_occupied_percentage()

    def flood_fill(self, x, y):
        """
        Perform flood fill from the opponent's position.
        """
        flood_fill(x, y, accessible_mark=self.OPPONENT, non_accessible_mark=self.FILLED, 
                   red=self.OPPONENT_COLOR[0], green=self.OPPONENT_COLOR[1], blue=self.OPPONENT_COLOR[2])

    def calculate_occupied_percentage(self):
        """
        Calculate the percentage of the playfield occupied by the player.
        """
        occupied_pixels = sum(1 for value in self.grid if value == self.FILLED)
        self.occupied_percentage = (occupied_pixels / (self.WIDTH * self.HEIGHT)) * 100
        display_score_and_time(int(self.occupied_percentage))

    def check_win_condition(self):
        """
        Check if the player has won the game.
        """
        return self.occupied_percentage > 75

    def main_loop(self, joystick):
        """
        Main game loop for the Qix game.
        """
        global game_over
        game_over = False
        self.initialize_game()

        while not game_over:
            c_button, _ = joystick.nunchuck.buttons()
            if c_button:
                game_over = True

            self.move_player(joystick)
            self.move_opponent()
            if self.check_win_condition():
                draw_text(self.WIDTH // 2 - 20, self.HEIGHT // 2 - 10, "YOU WIN", *self.PLAYER_COLOR)
                sleep_ms(2000)
                break

            sleep_ms(50)


class TetrisGame:
    """
    Class representing the Tetris game.
    """

    # Class-level constants
    GRID_WIDTH = 10
    GRID_HEIGHT = 20
    BLOCK_SIZE = 4  # Each block occupies 4x4 pixels
    TETRIS_BLACK = (0, 0, 0)
    TETRIS_COLORS = [
        (0, 255, 255),    # Cyan
        (255, 0, 0),      # Red
        (0, 255, 0),      # Green
        (0, 0, 255),      # Blue
        (255, 255, 0),    # Yellow
        (255, 165, 0),    # Orange
        (128, 0, 128),    # Purple
    ]

    # Tetrimino shapes
    TETRIMINOS = [
        [[1, 1, 1, 1]],                    # I shape
        [[1, 1, 1], [0, 1, 0]],            # T shape
        [[1, 1, 0], [0, 1, 1]],            # S shape
        [[0, 1, 1], [1, 1, 0]],            # Z shape
        [[1, 1], [1, 1]],                  # O shape
        [[1, 1, 1], [1, 0, 0]],            # L shape
        [[1, 1, 1], [0, 0, 1]],            # J shape
    ]

    def __init__(self):
        """
        Initialize the Tetris game variables.
        """
        self.locked_positions = {}
        self.grid = self.create_grid()
        self.current_piece = self.create_new_piece()
        self.fall_time = 0
        self.score = 0
        self.change_piece = False

    def create_grid(self):
        """
        Create the game grid with locked positions.

        Returns:
            list: The game grid.
        """
        grid = [[self.TETRIS_BLACK for _ in range(self.GRID_WIDTH)] for _ in range(self.GRID_HEIGHT)]
        for (x, y), color in self.locked_positions.items():
            grid[y][x] = color
        return grid

    def create_new_piece(self):
        """
        Create a new random Tetrimino.

        Returns:
            dict: A dictionary containing the shape, color, and position of the Tetrimino.
        """
        shape = random.choice(self.TETRIMINOS)
        color = random.choice(self.TETRIS_COLORS)
        x = self.GRID_WIDTH // 2 - len(shape[0]) // 2
        y = 0
        return {"shape": shape, "color": color, "x": x, "y": y}

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
                        new_x < 0 or
                        new_x >= self.GRID_WIDTH or
                        new_y >= self.GRID_HEIGHT or
                        (new_y >= 0 and grid[new_y][new_x] != self.TETRIS_BLACK)
                    ):
                        return False
        return True

    def clear_rows(self):
        """
        Clear completed rows from the grid.

        Returns:
            int: Number of rows cleared.
        """
        rows_to_clear = [y for y, row in enumerate(self.grid) if self.TETRIS_BLACK not in row]
        for y in rows_to_clear:
            del self.grid[y]
            self.grid.insert(0, [self.TETRIS_BLACK] * self.GRID_WIDTH)
            self.locked_positions = {(x, y): self.locked_positions.get((x, y - 1), self.TETRIS_BLACK) for x in range(self.GRID_WIDTH) for y in range(self.GRID_HEIGHT)}
        return len(rows_to_clear)

    def draw_grid(self):
        """
        Draw the grid with locked positions.
        """
        for y in range(self.GRID_HEIGHT):
            for x in range(self.GRID_WIDTH):
                color = self.grid[y][x]
                draw_rectangle(
                    x * self.BLOCK_SIZE,
                    y * self.BLOCK_SIZE,
                    (x + 1) * self.BLOCK_SIZE - 1,
                    (y + 1) * self.BLOCK_SIZE - 1,
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
                    x * self.BLOCK_SIZE,
                    y * self.BLOCK_SIZE,
                    (x + 1) * self.BLOCK_SIZE - 1,
                    (y + 1) * self.BLOCK_SIZE - 1,
                    *self.TETRIS_BLACK,
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
                    x * self.BLOCK_SIZE,
                    y * self.BLOCK_SIZE,
                    (x + 1) * self.BLOCK_SIZE - 1,
                    (y + 1) * self.BLOCK_SIZE - 1,
                    *color,
                )

    def rotate_piece(self, shape):
        """
        Rotate the Tetrimino shape clockwise.

        Args:
            shape (list): The shape of the Tetrimino.

        Returns:
            list: The rotated shape.
        """
        return [list(row) for row in zip(*shape[::-1])]

    def handle_input(self, joystick):
        """
        Handle joystick input.

        Args:
            joystick (Joystick): The joystick object.

        Returns:
            str: Direction input from the joystick.
        """
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
        clock = time.time()
        fall_speed = 500  # Fall speed in milliseconds

        while not game_over:
            elapsed_time = time.time() - clock
            if elapsed_time >= fall_speed / 1000:
                self.fall_time = 0
                self.move_piece_down()
                clock = time.time()

            direction = self.handle_input(joystick)
            self.move_piece(direction)

            if self.change_piece:
                self.lock_piece()
                self.score += self.clear_rows() * 100
                self.current_piece = self.create_new_piece()
                self.change_piece = False

            self.draw_grid()
            display_score_and_time(self.score)

            if self.check_game_over():
                game_over = True
                break

    def move_piece_down(self):
        """
        Move the current piece down by one row.
        """
        self.erase_piece(self.get_piece_positions())
        self.current_piece["y"] += 1
        if not self.valid_move(
            self.current_piece["shape"],
            self.grid,
            (self.current_piece["x"], self.current_piece["y"]),
        ):
            self.current_piece["y"] -= 1
            self.change_piece = True
        self.draw_piece(self.get_piece_positions(), self.current_piece["color"])

    def move_piece(self, direction):
        """
        Move the current piece based on the direction input.
        """
        if direction in [JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_DOWN, JOYSTICK_UP]:
            self.erase_piece(self.get_piece_positions())

        if direction == JOYSTICK_LEFT:
            self.current_piece["x"] -= 1
        elif direction == JOYSTICK_RIGHT:
            self.current_piece["x"] += 1
        elif direction == JOYSTICK_DOWN:
            self.current_piece["y"] += 1
        elif direction == JOYSTICK_UP:
            rotated_shape = self.rotate_piece(self.current_piece["shape"])
            if self.valid_move(rotated_shape, self.grid, (self.current_piece["x"], self.current_piece["y"])):
                self.current_piece["shape"] = rotated_shape

        if not self.valid_move(self.current_piece["shape"], self.grid, (self.current_piece["x"], self.current_piece["y"])):
            if direction == JOYSTICK_LEFT:
                self.current_piece["x"] += 1
            elif direction == JOYSTICK_RIGHT:
                self.current_piece["x"] -= 1
            elif direction == JOYSTICK_DOWN:
                self.current_piece["y"] -= 1
            elif direction == JOYSTICK_UP:
                for _ in range(3):  # Rotate back
                    self.current_piece["shape"] = self.rotate_piece(self.current_piece["shape"])

        self.draw_piece(self.get_piece_positions(), self.current_piece["color"])

    def lock_piece(self):
        """
        Lock the current piece in place on the grid.
        """
        for x, y in self.get_piece_positions():
            self.locked_positions[(x, y)] = self.current_piece["color"]

    def get_piece_positions(self):
        """
        Get the positions occupied by the current piece.

        Returns:
            list: List of (x, y) positions.
        """
        return [
            (self.current_piece["x"] + x, self.current_piece["y"] + y)
            for y, row in enumerate(self.current_piece["shape"])
            for x, cell in enumerate(row) if cell
        ]

    def check_game_over(self):
        """
        Check if the game is over.

        Returns:
            bool: True if game over, False otherwise.
        """
        return any(y < 0 for x, y in self.locked_positions)


class MazeGame:
    """
    Class representing the Maze game where the player moves in a maze,
    collects gems, and shoots enemies.
    """

    # Class-level constants for memory efficiency
    WIDTH = 64
    HEIGHT = 64
    WALL = 0
    PATH = 1
    PLAYER = 2
    GEM = 3
    ENEMY = 4
    PROJECTILE = 5
    PLAYER_COLOR = (0, 255, 0)
    GEM_COLOR = (255, 215, 0)
    ENEMY_COLOR = (255, 0, 0)
    PROJECTILE_COLOR = (255, 255, 0)
    PATH_COLOR = (255, 255, 255)

    def __init__(self):
        """
        Initialize the Maze game variables.
        """
        self.grid = bytearray(self.WIDTH * self.HEIGHT // 2)
        self.player_x = 0
        self.player_y = 0
        self.player_direction = None
        self.gems = []
        self.enemies = []
        self.projectiles = []
        self.score = 0

    def initialize_game(self):
        """
        Set up the game environment by generating the maze, placing the player, gems, and enemies.
        """
        display.clear()
        self.initialize_grid()
        self.generate_maze()
        self.place_player()
        self.place_gems()
        self.place_enemies()

    def initialize_grid(self):
        """
        Initialize the grid to be empty.
        """
        self.grid = bytearray(self.WIDTH * self.HEIGHT // 2)

    def get_grid_value(self, x, y):
        """
        Get the value at position (x, y) in the grid.
        """
        index = y * self.WIDTH + x
        return (self.grid[index // 2] >> ((index % 2) * 4)) & 0x0F

    def set_grid_value(self, x, y, value):
        """
        Set the value at position (x, y) in the grid.
        """
        index = y * self.WIDTH + x
        half_index = index // 2
        shift = (index % 2) * 4
        self.grid[half_index] = (self.grid[half_index] & ~(0x0F << shift)) | ((value & 0x0F) << shift)

    def generate_maze(self):
        """
        Generate a random maze using depth-first search algorithm.
        """
        stack = []
        visited = set()

        start_x = random.randint(1, self.WIDTH - 2)
        start_y = random.randint(1, self.HEIGHT - 2)
        stack.append((start_x, start_y))
        visited.add((start_x, start_y))

        directions = [(0, 2), (0, -2), (2, 0), (-2, 0)]

        while stack:
            x, y = stack[-1]

            # Mischen der Richtungen
            mixed_directions = directions[:]  # Kopie der Richtungen
            for i in range(len(mixed_directions) - 1, 0, -1):
                j = random.randint(0, i)
                mixed_directions[i], mixed_directions[j] = mixed_directions[j], mixed_directions[i]
                
            found_unvisited = False

            for dx, dy in directions:
                nx, ny = x + dx, y + dy
                if 0 < nx < self.WIDTH and 0 < ny < self.HEIGHT and (nx, ny) not in visited:
                    self.set_grid_value(x + dx // 2, y + dy // 2, self.PATH)
                    self.set_grid_value(nx, ny, self.PATH)
                    stack.append((nx, ny))
                    visited.add((nx, ny))
                    found_unvisited = True
                    break

            if not found_unvisited:
                stack.pop()

    def place_player(self):
        """
        Place the player at a random position in the maze.
        """
        while True:
            self.player_x = random.randint(1, self.WIDTH - 2)
            self.player_y = random.randint(1, self.HEIGHT - 2)
            if self.get_grid_value(self.player_x, self.player_y) == self.PATH:
                self.set_grid_value(self.player_x, self.player_y, self.PLAYER)
                break

    def place_gems(self):
        """
        Place gems randomly in the maze.
        """
        self.gems = []
        for _ in range(10):
            while True:
                gem_x = random.randint(1, self.WIDTH - 2)
                gem_y = random.randint(1, self.HEIGHT - 2)
                if self.get_grid_value(gem_x, gem_y) == self.PATH:
                    self.set_grid_value(gem_x, gem_y, self.GEM)
                    self.gems.append((gem_x, gem_y))
                    break

    def place_enemies(self):
        """
        Place enemies randomly in the maze.
        """
        self.enemies = []
        for _ in range(3):
            while True:
                enemy_x = random.randint(1, self.WIDTH - 2)
                enemy_y = random.randint(1, self.HEIGHT - 2)
                if self.get_grid_value(enemy_x, enemy_y) == self.PATH:
                    self.set_grid_value(enemy_x, enemy_y, self.ENEMY)
                    self.enemies.append((enemy_x, enemy_y))
                    break

    def get_visible_cells(self):
        """
        Compute the cells visible to the player along the corridors.
        """
        visible_cells = set()
        x, y = self.player_x, self.player_y
        visible_cells.add((x, y))

        directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        for dx, dy in directions:
            nx, ny = x, y
            while True:
                nx += dx
                ny += dy
                if 0 <= nx < self.WIDTH and 0 <= ny < self.HEIGHT:
                    cell_value = self.get_grid_value(nx, ny)
                    if cell_value == self.WALL:
                        break
                    visible_cells.add((nx, ny))
                    if cell_value == self.ENEMY:
                        break
                else:
                    break
        return visible_cells

    def render(self):
        """
        Render the visible part of the maze.
        """
        display.clear()
        visible_cells = self.get_visible_cells()
        for x, y in visible_cells:
            cell_value = self.get_grid_value(x, y)
            color = {
                self.PATH: self.PATH_COLOR,
                self.PLAYER: self.PLAYER_COLOR,
                self.GEM: self.GEM_COLOR,
                self.ENEMY: self.ENEMY_COLOR,
                self.PROJECTILE: self.PROJECTILE_COLOR
            }.get(cell_value, self.PATH_COLOR)
            display.set_pixel(x, y, *color)

    def move_player(self, joystick):
        """
        Handle player movement based on joystick input.
        """
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

            if 0 <= new_x < self.WIDTH and 0 <= new_y < self.HEIGHT and self.get_grid_value(new_x, new_y) in [self.PATH, self.GEM]:
                self.set_grid_value(self.player_x, self.player_y, self.PATH)  # Clear old position
                self.player_x, self.player_y = new_x, new_y
                self.set_grid_value(self.player_x, self.player_y, self.PLAYER)
                self.player_direction = direction
                if self.get_grid_value(new_x, new_y) == self.GEM:
                    self.collect_gem(new_x, new_y)

    def collect_gem(self, x, y):
        """
        Handle the collection of a gem.
        """
        self.set_grid_value(x, y, self.PLAYER)
        self.gems.remove((x, y))
        self.score += 10

    def move_enemies(self):
        """
        Move enemies in the maze.
        """
        for enemy in self.enemies:
            possible_moves = []
            directions = [(0, -1), (0, 1), (-1, 0), (1, 0)]
            for dx, dy in directions:
                nx, ny = enemy[0] + dx, enemy[1] + dy
                if 0 <= nx < self.WIDTH and 0 <= ny < self.HEIGHT and self.get_grid_value(nx, ny) == self.PATH:
                    possible_moves.append((nx, ny))

            if possible_moves:
                new_position = random.choice(possible_moves)
                self.set_grid_value(enemy[0], enemy[1], self.PATH)  # Clear old position
                self.enemies.remove(enemy)
                self.enemies.append(new_position)
                self.set_grid_value(new_position[0], new_position[1], self.ENEMY)

    def handle_shooting(self, joystick):
        """
        Handle shooting when player presses the fire button.
        """
        _, z_button = joystick.nunchuck.buttons()
        if z_button:
            dx, dy = {"UP": (0, -1), "DOWN": (0, 1), "LEFT": (-1, 0), "RIGHT": (1, 0)}.get(self.player_direction, (0, -1))
            projectile = {"x": self.player_x, "y": self.player_y, "dx": dx, "dy": dy, "lifetime": 10}
            self.set_grid_value(projectile["x"], projectile["y"], self.PROJECTILE)
            self.projectiles.append(projectile)

    def update_projectiles(self):
        """
        Update the positions of projectiles and handle collisions.
        """
        for projectile in self.projectiles[:]:
            self.set_grid_value(projectile["x"], projectile["y"], self.PATH)  # Clear old position
            projectile["x"] += projectile["dx"]
            projectile["y"] += projectile["dy"]

            if 0 <= projectile["x"] < self.WIDTH and 0 <= projectile["y"] < self.HEIGHT:
                cell_value = self.get_grid_value(projectile["x"], projectile["y"])
                if cell_value == self.WALL:
                    self.projectiles.remove(projectile)
                elif cell_value == self.ENEMY:
                    self.enemies = [e for e in self.enemies if e != (projectile["x"], projectile["y"])]
                    self.set_grid_value(projectile["x"], projectile["y"], self.PATH)
                    self.projectiles.remove(projectile)
                    self.score += 20
                else:
                    projectile["lifetime"] -= 1
                    if projectile["lifetime"] > 0:
                        self.set_grid_value(projectile["x"], projectile["y"], self.PROJECTILE)
                    else:
                        self.projectiles.remove(projectile)
            else:
                self.projectiles.remove(projectile)

    def main_loop(self, joystick):
        """
        Main game loop for the Maze game.
        """
        global game_over
        game_over = False
        self.initialize_game()

        while not game_over:
            c_button, _ = joystick.nunchuck.buttons()
            if c_button:
                game_over = True

            self.move_player(joystick)
            self.handle_shooting(joystick)
            self.update_projectiles()
            self.move_enemies()

            self.render()
            display_score_and_time(self.score)

            if not self.enemies and not self.gems:
                display.clear()
                draw_text(10, 10, "YOU WIN", 0, 255, 0)
                sleep_ms(2000)
                break

            sleep_ms(100)



class GameSelect:
    """
    Class for selecting and running games.
    """

    def __init__(self):
        """
        Initialize the game selector with available games.
        """
        self.joystick = None  # Joystick will be initialized only when needed
        self.game_instances = {}  # Dictionary to store game instances temporarily
        self.game_classes = {
            "SNAKE": SnakeGame,
            "SIMON": SimonGame,
            "BRKOUT": BreakoutGame,
            "ASTRD": AsteroidGame,
            "MAZE": MazeGame,
            "PONG": PongGame,
            "QIX": QixGame,
            "TETRIS": TetrisGame,
        }
        self.sorted_games = sorted(self.game_classes.keys())
        self.selected_game = None

    def initialize_joystick(self):
        """
        Initialize the joystick if it hasn't been initialized yet.
        """
        if not self.joystick:
            self.joystick = Joystick()

    def run(self):
        """
        Main loop to run the game selector and handle game execution.
        """
        # Ensure joystick is initialized before starting the main loop
        self.initialize_joystick()
        
        while True:
            if self.selected_game is None:
                self.run_game_selector()
            else:
                self.run_selected_game()
                # Run the game over menu after the game finishes
                GameOverMenu().run_game_over_menu()

    def run_selected_game(self):
        """
        Run the selected game based on user choice.
        """
        game_name = self.selected_game
        self.selected_game = None  # Reset selection

        if game_name == "EXIT":
            return
        elif game_name == "MENU":
            return
        else:
            # Create and run the game instance
            game_instance = self.create_game_instance(game_name)
            game_instance.main_loop(self.joystick)
            # Clean up the game instance after it's finished
            self.delete_game_instance(game_name)

    def create_game_instance(self, game_name):
        """
        Create a new game instance if it doesn't exist in the dictionary.

        Args:
            game_name (str): The name of the game to create an instance for.

        Returns:
            object: The initialized game instance.
        """
        if game_name not in self.game_instances:
            self.game_instances[game_name] = self.game_classes[game_name]()
        return self.game_instances[game_name]

    def delete_game_instance(self, game_name):
        """
        Delete the game instance to free up memory.

        Args:
            game_name (str): The name of the game to delete the instance for.
        """
        if game_name in self.game_instances:
            del self.game_instances[game_name]

    def run_game_selector(self):
        """
        Display the game selection menu and handle user input.
        """
        selected_index = 0
        top_index = 0
        display_size = 4  # Number of games to display at once
        previous_selected = None
        last_move_time = time.time()
        debounce_delay = 0.05

        while True:
            current_time = time.time()

            if selected_index != previous_selected:
                previous_selected = selected_index
                self.display_game_options(top_index, selected_index, display_size)

            if current_time - last_move_time > debounce_delay:
                direction = self.joystick.read_direction(
                    [JOYSTICK_UP, JOYSTICK_DOWN], debounce=False
                )
                selected_index, top_index = self.update_selection(direction, selected_index, top_index, display_size)
                last_move_time = current_time

            # Ensure joystick is initialized before checking if it's pressed
            if self.joystick and self.joystick.is_pressed():
                self.selected_game = self.sorted_games[selected_index]
                break

            sleep_ms(40)

    def display_game_options(self, top_index, selected_index, display_size):
        """
        Display the list of game options on the screen.

        Args:
            top_index (int): The index of the first game to display.
            selected_index (int): The currently selected game index.
            display_size (int): The number of games to display at once.
        """
        display.clear()
        for i in range(display_size):
            game_idx = top_index + i
            if game_idx < len(self.sorted_games):
                color = (255, 255, 255) if game_idx == selected_index else (111, 111, 111)
                draw_text(8, 5 + i * 15, self.sorted_games[game_idx], *color)

    def update_selection(self, direction, selected_index, top_index, display_size):
        """
        Update the selected game index based on joystick input.

        Args:
            direction (str): The direction read from the joystick.
            selected_index (int): The current selected index.
            top_index (int): The top index of the displayed list.
            display_size (int): The number of games displayed.

        Returns:
            tuple: Updated (selected_index, top_index).
        """
        if direction == JOYSTICK_UP and selected_index > 0:
            selected_index -= 1
            if selected_index < top_index:
                top_index -= 1
        elif direction == JOYSTICK_DOWN and selected_index < len(self.sorted_games) - 1:
            selected_index += 1
            if selected_index > top_index + display_size - 1:
                top_index += 1

        return selected_index, top_index


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
        debounce_delay = 0.05
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

            sleep_ms(40)

def main():
    try:
        while True:
            # Start the game selection
            game_state = GameSelect()

            # Run the main game loop
            game_state.run()
    except RestartProgram:
        # reset the game state and buttons
        game_state = None
        game_over = False
        main()  # Starte main() erneut

if __name__ == "__main__":
    # Initialize the I2C bus for Nunchuk
    i2c = machine.I2C(0, scl=machine.Pin(21), sda=machine.Pin(20), freq=100000)

    # Create the Nunchuk object
    nunchuk = Nunchuck(i2c, poll=True, poll_interval=100)

    # Start the display
    display.start()
    
    main()

