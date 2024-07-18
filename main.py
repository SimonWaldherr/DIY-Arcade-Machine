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

# Color definitions for Simon game
colors_bright = [
    (255, 0, 0),   # Red
    (0, 255, 0),   # Green
    (0, 0, 255),   # Blue
    (255, 255, 0)  # Yellow
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

# Joystick directions
JOYSTICK_UP = 'UP'
JOYSTICK_DOWN = 'DOWN'
JOYSTICK_LEFT = 'LEFT'
JOYSTICK_RIGHT = 'RIGHT'

char_dict = {
    'A': ["00110000", "01111000", "11001100", "11001100", "11111100", "11001100", "11001100", "00000000"],
    'B': ["11111100", "01100110", "01100110", "01111100", "01100110", "01100110", "11111100", "00000000"],
    'C': ["00111100", "01100110", "11000000", "11000000", "11000000", "01100110", "00111100", "00000000"],
    'D': ["11111000", "01101100", "01100110", "01100110", "01100110", "01101100", "11111000", "00000000"],
    'E': ["11111110", "01100010", "01101000", "01111000", "01101000", "01100010", "11111110", "00000000"],
    'F': ["11111110", "01100010", "01101000", "01111000", "01101000", "01100000", "11110000", "00000000"],
    'G': ["00111100", "01100110", "11000000", "11000000", "11001110", "01100110", "00111110", "00000000"],
    'H': ["11001100", "11001100", "11001100", "11111100", "11001100", "11001100", "11001100", "00000000"],
    'I': ["01111000", "00110000", "00110000", "00110000", "00110000", "00110000", "01111000", "00000000"],
    'J': ["00011110", "00001100", "00001100", "00001100", "11001100", "11001100", "01111000", "00000000"],
    'K': ["11110110", "01100110", "01101100", "01111000", "01101100", "01100110", "11110110", "00000000"],
    'L': ["11110000", "01100000", "01100000", "01100000", "01100010", "01100110", "11111110", "00000000"],
    'M': ["11000110", "11101110", "11111110", "11111110", "11010110", "11000110", "11000110", "00000000"],
    'N': ["11000110", "11100110", "11110110", "11011110", "11001110", "11000110", "11000110", "00000000"],
    'O': ["00111000", "01101100", "11000110", "11000110", "11000110", "01101100", "00111000", "00000000"],
    'P': ["11111100", "01100110", "01100110", "01111100", "01100000", "01100000", "11110000", "00000000"],
    'Q': ["01111000", "11001100", "11001100", "11001100", "11011100", "01111000", "00011100", "00000000"],
    'R': ["11111100", "01100110", "01100110", "01111100", "01101100", "01100110", "11110110", "00000000"],
    'S': ["01111000", "11001100", "11100000", "00111000", "00001100", "11001100", "01111000", "00000000"],
    'T': ["11111100", "10110100", "00110000", "00110000", "00110000", "00110000", "01111000", "00000000"],
    'U': ["11001100", "11001100", "11001100", "11001100", "11001100", "11001100", "11111100", "00000000"],
    'V': ["11001100", "11001100", "11001100", "11001100", "11001100", "01111000", "00110000", "00000000"],
    'W': ["11000110", "11000110", "11000110", "11010110", "11111110", "11101110", "11000110", "00000000"],
    'X': ["11000110", "11000110", "01101100", "00111000", "00111000", "01101100", "11000110", "00000000"],
    'Y': ["11001100", "11001100", "11001100", "01111000", "00110000", "00110000", "01111000", "00000000"],
    'Z': ["11111110", "11000110", "10001100", "00011000", "00110010", "01100110", "11111110", "00000000"],
    'a': ["00000000", "00000000", "01111000", "00001100", "01111100", "11001100", "01110110", "00000000"],
    'b': ["11100000", "01100000", "01100000", "01111100", "01100110", "01100110", "11011100", "00000000"],
    'c': ["00000000", "00000000", "01111000", "11001100", "11000000", "11001100", "01111000", "00000000"],
    'd': ["00011100", "00001100", "00001100", "01111100", "11001100", "11001100", "01110110", "00000000"],
    'e': ["00000000", "00000000", "01111000", "11001100", "11111100", "11000000", "01111000", "00000000"],
    'f': ["00111000", "01101100", "01100000", "11110000", "01100000", "01100000", "11110000", "00000000"],
    'g': ["00000000", "00000000", "01110110", "11001100", "11001100", "01111100", "00001100", "11111000"],
    'h': ["11100000", "01100000", "01101100", "01110110", "01100110", "01100110", "11100110", "00000000"],
    'i': ["00110000", "00000000", "01110000", "00110000", "00110000", "00110000", "01111000", "00000000"],
    'j': ["00001100", "00000000", "00001100", "00001100", "00001100", "11001100", "11001100", "01111000"],
    'k': ["11100000", "01100000", "01100110", "01101100", "01111000", "01101100", "11100110", "00000000"],
    'l': ["01110000", "00110000", "00110000", "00110000", "00110000", "00110000", "01111000", "00000000"],
    'm': ["00000000", "00000000", "11001100", "11111110", "11111110", "11010110", "11000110", "00000000"],
    'n': ["00000000", "00000000", "11111000", "11001100", "11001100", "11001100", "11001100", "00000000"],
    'o': ["00000000", "00000000", "01111000", "11001100", "11001100", "11001100", "01111000", "00000000"],
    'p': ["00000000", "00000000", "11011100", "01100110", "01100160", "01111100", "01100000", "11110000"],
    'q': ["00000000", "00000000", "01110110", "11001100", "11001100", "01111100", "00001100", "00011110"],
    'r': ["00000000", "00000000", "10011100", "01110110", "01100110", "01100000", "11110000", "00000000"],
    's': ["00000000", "00000000", "01111100", "11000000", "01111000", "00001100", "11111000", "00000000"],
    't': ["00010000", "00110000", "01111100", "00110000", "00110000", "00110100", "00011000", "00000000"],
    'u': ["00000000", "00000000", "11001100", "11001100", "11001100", "11001100", "01110110", "00000000"],
    'v': ["00000000", "00000000", "11001100", "11001100", "11001100", "01111000", "00110000", "00000000"],
    'w': ["00000000", "00000000", "11000110", "11000110", "11010110", "11111110", "01101100", "00000000"],
    'x': ["00000000", "00000000", "11000110", "01101100", "00111000", "01101100", "11000110", "00000000"],
    'y': ["00000000", "00000000", "11001100", "11001100", "11001100", "01111100", "00001100", "11111000"],
    'z': ["00000000", "00000000", "11111100", "10011000", "00110000", "01100100", "11111100", "00000000"],
    '0': ["01111000", "11001100", "11011100", "11111100", "11101100", "11001100", "01111100", "00000000"],
    '1': ["00110000", "01110000", "00110000", "00110000", "00110000", "00110000", "11111100", "00000000"],
    '2': ["01111000", "11001100", "00001100", "00111000", "01100000", "11001100", "11111100", "00000000"],
    '3': ["01111000", "11001100", "00001100", "00111000", "00001100", "11001100", "01111000", "00000000"],
    '4': ["00011100", "00111100", "01101100", "11001100", "11111110", "00001100", "00011110", "00000000"],
    '5': ["11111100", "11000000", "11111000", "00001100", "00001100", "11001100", "01111000", "00000000"],
    '6': ["00111000", "01100000", "11000000", "11111000", "11001100", "11001100", "01111000", "00000000"],
    '7': ["11111100", "11001100", "00001100", "00011000", "00110000", "00110000", "00110000", "00000000"],
    '8': ["01111000", "11001100", "11001100", "01111000", "11001100", "11001100", "01111000", "00000000"],
    '9': ["01111000", "11001100", "11001100", "01111100", "00001100", "00011000", "01110000", "00000000"],
    '!': ["00110000", "01111000", "01111000", "00110000", "00110000", "00000000", "00110000", "00000000"],
    '#': ["01101100", "01101100", "11111110", "01101100", "11111110", "01101100", "01101100", "00000000"],
    '$': ["00110000", "01111100", "11000000", "01111000", "00001100", "11111000", "00110000", "00000000"],
    '%': ["00000000", "11000110", "11001100", "00011000", "00110000", "01100110", "11000110", "00000000"],
    '&': ["00111000", "01101100", "00111000", "01110110", "11011100", "11001100", "01110110", "00000000"],
    '?': ["01111000", "11001100", "00001100", "00011000", "00110000", "00000000", "00110000", "00000000"],
    ' ': ["00000000", "00000000", "00000000", "00000000", "00000000", "00000000", "00000000", "00000000"],
    '.': ["00000000", "00000000", "00000000", "00000000", "00000000", "00000000", "00110000", "00000000"],
    ':': ["00000000", "00110000", "00000000", "00000000", "00000000", "00110000", "00000000", "00000000"]
}

def draw_char(x, y, char, r, g, b):
    if char in char_dict:
        matrix = char_dict[char]
        for row in range(8):
            for col in range(8):
                if matrix[row][col] == '1':
                    display.set_pixel(x + col, y + row, r, g, b)
                    
def draw_text(x, y, text, r, g, b):
    offset_x = x
    for char in text:
        draw_char(offset_x, y, char, r, g, b)
        offset_x += 9

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
    ':': ["00000", "00100", "00000", "00100", "00000"]
}

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

def rect(x1, y1, x2, y2, r, g, b):
    for x in range(min(x1, x2), max(x1, x2) + 1):
        for y in range(min(y1, y2), max(y1, y2) + 1):
            display.set_pixel(x, y, r, g, b)

def get_joystick_direction():
    read0 = adc0.read_u16()
    read1 = adc1.read_u16()
    valueX = read0 - 32768  # Adjusted to be centered at 0
    valueY = read1 - 32768  # Adjusted to be centered at 0

    if abs(valueX) > abs(valueY):
        if valueX > 10000:
            return JOYSTICK_RIGHT
        elif valueX < -10000:
            return JOYSTICK_LEFT
    else:
        if valueY > 10000:
            return JOYSTICK_DOWN
        elif valueY < -10000:
            return JOYSTICK_UP
    return None

rtc = machine.RTC()

# Simon Game
def simon_game():
    def draw_quad_screen():
        rect(0, 0, WIDTH // 2 - 1, (HEIGHT-6) // 2 - 1, *inactive_colors[0])
        rect(WIDTH // 2, 0, WIDTH - 1, (HEIGHT-6) // 2 - 1, *inactive_colors[1])
        rect(0, (HEIGHT-6) // 2, WIDTH // 2 - 1, (HEIGHT-6) - 1, *inactive_colors[2])
        rect(WIDTH // 2, (HEIGHT-6) // 2, WIDTH - 1, (HEIGHT-6) - 1, *inactive_colors[3])
        
    def flash_color(index, duration=0.5):
        x, y = index % 2, index // 2
        rect(x * WIDTH // 2, y * (HEIGHT-6) // 2, (x + 1) * WIDTH // 2 - 1, (y + 1) * (HEIGHT-6) // 2 - 1, *colors[index])
        time.sleep(duration)
        rect(x * WIDTH // 2, y * (HEIGHT-6) // 2, (x + 1) * WIDTH // 2 - 1, (y + 1) * (HEIGHT-6) // 2 - 1, *inactive_colors[index])
        
    def play_sequence():
        for color in simon_sequence:
            flash_color(color)
            time.sleep(0.5)
            
    def get_joystick_direction():
        read0 = adc0.read_u16()
        read1 = adc1.read_u16()
        read2 = adc2.read_u16()
        
        valueX = read0 - 32768  # Adjusted to be centered at 0
        valueY = read1 - 32768  # Adjusted to be centered at 0

        if valueY < -10000 and valueX < -10000:
                return 'UP-LEFT'
        elif valueY < -10000 and valueX > 10000:
            return 'UP-RIGHT'
        elif valueY > 10000 and valueX < -10000:
            return 'DOWN-LEFT'
        elif valueY > 10000 and valueX > 10000:
            return 'DOWN-RIGHT'
            
        return None
    
    def get_user_input():
        while True:
            joystick_dir = get_joystick_direction()
            if joystick_dir:
                return joystick_dir
            time.sleep(0.1)
            
    def translate_joystick_to_color(joystick_dir):
        if joystick_dir == 'UP-LEFT':
            return 0
        elif joystick_dir == 'UP-RIGHT':
            return 1
        elif joystick_dir == 'DOWN-LEFT':
            return 2
        elif joystick_dir == 'DOWN-RIGHT':
            return 3
        return None
    
    def check_user_sequence():
        for i in range(len(user_sequence)):
            if user_sequence[i] != simon_sequence[i]:
                return False
        return True
    
    def start_game():
        global simon_sequence, user_sequence
        simon_sequence = []
        user_sequence = []
        draw_quad_screen()
        
    def display_score_and_time(score):
        global text
        year, month, day, wd, hour, minute, second, _ = rtc.datetime()
        time_str = "{:02}:{:02}".format(hour, minute)
        score_str = str(score)
        time_x = WIDTH - (len(time_str) * 6)
        time_y = HEIGHT - 6
        score_x = 1
        score_y = HEIGHT - 6
        if text != score_str + " " + time_str:
            text = score_str + " " + time_str
            rect(score_x, score_y, WIDTH, score_y + 5, 0, 0, 0)
        draw_text_small(score_x, score_y, score_str, 255, 255, 255)
        draw_text_small(time_x, time_y, time_str, 255, 255, 255)
        
    def main_simon_game_loop():
        global simon_sequence, user_sequence
        
        start_game()
        while True:
            simon_sequence.append(random.randint(0, 3))
            display_score_and_time(len(simon_sequence) - 1)
            play_sequence()
            user_sequence = []
            
            for _ in range(len(simon_sequence)):
                joystick_dir = get_user_input()
                selected_color = translate_joystick_to_color(joystick_dir)
                if selected_color is not None:
                    flash_color(selected_color, 0.2)
                    user_sequence.append(selected_color)
                    if not check_user_sequence():
                        # Game over - red flash and restart
                        rect(0, 0, WIDTH - 1, (HEIGHT-6) - 1, *inactive_colors[0])
                        display_score_and_time(0)
                        start_game()

                else:
                    print("Invalid input")
                    break
                
            time.sleep(1)

    main_simon_game_loop()

# Snake Game
def snake_game():
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

    def restart_game():
        global snake, snake_length, snake_direction, score, green_targets
        score = 0
        snake = [(32, 32)]
        snake_length = 3
        snake_direction = 'UP'
        target = random_target()
        green_targets = []
        display.clear()
        place_target()

    def random_target():
        return (random.randint(1, WIDTH - 2), random.randint(1, HEIGHT - 8))

    def place_target():
        global target
        target = random_target()
        display.set_pixel(target[0], target[1], 255, 0, 0)  # Red target

    def place_green_target():
        x, y = random.randint(1, WIDTH - 2), random.randint(1, HEIGHT - 8)
        green_targets.append((x, y, 256))
        display.set_pixel(x, y, 0, 255, 0)  # Green target

    def update_green_targets():
        global green_targets
        new_green_targets = []
        for x, y, lifespan in green_targets:
            if lifespan > 1:
                new_green_targets.append((x, y, lifespan - 1))
            else:
                display.set_pixel(x, y, 0, 0, 0)  # Clear green target from display
        green_targets = new_green_targets

    def find_nearest_target(head_x, head_y, green_targets, red_target):
        def manhattan_distance(x1, y1, x2, y2):
            return abs(x1 - x2) + abs(y1 - y2)

        min_distance_green = float('inf')
        nearest_green_target = None

        for x, y, _ in green_targets:
            distance = manhattan_distance(head_x, head_y, x, y)
            if distance < min_distance_green:
                min_distance_green = distance
                nearest_green_target = (x, y)

        distance_red = manhattan_distance(head_x, head_y, red_target[0], red_target[1])

        if nearest_green_target and min_distance_green <= distance_red * 1.5:
            return nearest_green_target
        else:
            return red_target

    def update_direction(snake, snake_direction, green_targets, target, joystick_dir):
        head_x, head_y = snake[0]
        target_x, target_y = find_nearest_target(head_x, head_y, green_targets, target)

        opposite_directions = {'UP': 'DOWN', 'DOWN': 'UP', 'LEFT': 'RIGHT', 'RIGHT': 'LEFT'}

        new_direction = snake_direction  # Default to current direction

        if joystick_dir:
            new_direction = joystick_dir
        else:
            if head_x == target_x:
                if head_y < target_y and snake_direction != 'UP':
                    new_direction = 'DOWN'
                elif head_y > target_y and snake_direction != 'DOWN':
                    new_direction = 'UP'
            elif head_y == target_y:
                if head_x < target_x and snake_direction != 'LEFT':
                    new_direction = 'RIGHT'
                elif head_x > target_x and snake_direction != 'RIGHT':
                    new_direction = 'LEFT'
            else:
                if abs(head_x - target_x) < abs(head_y - target_y):
                    if head_x < target_x and snake_direction != 'LEFT':
                        new_direction = 'RIGHT'
                    elif head_x > target_x and snake_direction != 'RIGHT':
                        new_direction = 'LEFT'
                else:
                    if head_y < target_y and snake_direction != 'UP':
                        new_direction = 'DOWN'
                    elif head_y > target_y and snake_direction != 'DOWN':
                        new_direction = 'UP'

        if new_direction == opposite_directions[snake_direction]:
            new_direction = snake_direction

        return new_direction

    def check_self_collision():
        global snake, snake_direction
        head_x, head_y = snake[0]
        body = snake[1:]
        potential_moves = {
            'UP': (head_x, head_y - 1),
            'DOWN': (head_x, head_y + 1),
            'LEFT': (head_x - 1, head_y),
            'RIGHT': (head_x + 1, head_y)
        }
        safe_moves = {dir: pos for dir, pos in potential_moves.items() if pos not in body}
        if potential_moves[snake_direction] not in safe_moves.values():
            if safe_moves:
                snake_direction = random.choice(list(safe_moves.keys()))
            else:
                restart_game()

    def update_snake_position():
        global snake, snake_length, snake_direction
        head_x, head_y = snake[0]
        if snake_direction == 'UP':
            head_y -= 1
        elif snake_direction == 'DOWN':
            head_y += 1
        elif snake_direction == 'LEFT':
            head_x -= 1
        elif snake_direction == 'RIGHT':
            head_x += 1

        head_x %= WIDTH
        head_y %= HEIGHT

        snake.insert(0, (head_x, head_y))
        if len(snake) > snake_length:
            tail = snake.pop()
            display.set_pixel(tail[0], tail[1], 0, 0, 0)

    def check_target_collision():
        global snake, snake_length, target, score
        head_x, head_y = snake[0]
        if (head_x, head_y) == target:
            snake_length += 2
            place_target()
            score += 1

    def check_green_target_collision():
        global snake, snake_length, green_targets
        head_x, head_y = snake[0]
        for x, y, lifespan in green_targets:
            if (head_x, head_y) == (x, y):
                snake_length = max(snake_length // 2, 2)
                green_targets.remove((x, y, lifespan))
                display.set_pixel(x, y, 0, 0, 0)

    def draw_snake():
        hue = 0
        for idx, (x, y) in enumerate(snake[:snake_length]):
            hue = (hue + 5) % 360
            r, g, b = hsb_to_rgb(hue, 1, 1)
            display.set_pixel(x, y, r, g, b)
        for idx in range(snake_length, len(snake)):
            x, y = snake[idx]
            display.set_pixel(x, y, 0, 0, 0)

    def display_score_and_time(score):
        global text
        year, month, day, wd, hour, minute, second, _ = rtc.datetime()
        time_str = "{:02}:{:02}".format(hour, minute)
        score_str = str(score)
        time_x = WIDTH - (len(time_str) * 6)
        time_y = HEIGHT - 6
        score_x = 1
        score_y = HEIGHT - 6
        if text != score_str + " " + time_str:
            text = score_str + " " + time_str
            rect(score_x, score_y, WIDTH, score_y + 5, 0, 0, 0)
        draw_text_small(score_x, score_y, score_str, 255, 255, 255)
        draw_text_small(time_x, time_y, time_str, 255, 255, 255)

    def main_snake_game_loop():
        global snake_direction
        step_counter = 0

        while True:
            step_counter += 1

            if step_counter % 1024 == 0:
                place_green_target()
            update_green_targets()

            joystick_dir = get_joystick_direction()

            if joystick_dir is not None:
                snake_direction = joystick_dir

            check_self_collision()
            update_snake_position()
            check_target_collision()
            check_green_target_collision()
            draw_snake()
            display_score_and_time(score)

            time.sleep(max(0.03, (0.09 - max(0.01, snake_length / 300))))

    restart_game()
    main_snake_game_loop()

# Pong Game
def pong_game():
    # Pong game variables
    paddle_height = 8
    paddle_speed = 2
    ball_speed = [1, 1]
    ball_position = [WIDTH // 2, HEIGHT // 2]
    left_paddle = HEIGHT // 2 - paddle_height // 2
    right_paddle = HEIGHT // 2 - paddle_height // 2
    prev_left_score = 0
    prev_right_score = 0
    left_score = 0
    right_score = 0

    def draw_paddles():
        # Clear paddles
        for y in range(HEIGHT):
            display.set_pixel(0, y, 0, 0, 0)
            display.set_pixel(WIDTH - 1, y, 0, 0, 0)

        # Draw new paddles
        for y in range(left_paddle, left_paddle + paddle_height):
            display.set_pixel(0, y, 255, 255, 255)
        for y in range(right_paddle, right_paddle + paddle_height):
            display.set_pixel(WIDTH - 1, y, 255, 255, 255)

    def draw_ball():
        display.set_pixel(ball_position[0], ball_position[1], 255, 255, 255)

    def clear_ball():
        display.set_pixel(ball_position[0], ball_position[1], 0, 0, 0)

    def update_ball():
        nonlocal ball_position, ball_speed, left_score, right_score
        clear_ball()

        ball_position[0] += ball_speed[0]
        ball_position[1] += ball_speed[1]

        # Ball collision with top and bottom walls
        if ball_position[1] <= 0 or ball_position[1] >= HEIGHT - 1:
            ball_speed[1] = -ball_speed[1]

        # Ball collision with paddles
        if ball_position[0] == 1 and left_paddle <= ball_position[1] < left_paddle + paddle_height:
            ball_speed[0] = -ball_speed[0]
        elif ball_position[0] == WIDTH - 2 and right_paddle <= ball_position[1] < right_paddle + paddle_height:
            ball_speed[0] = -ball_speed[0]

        # Ball out of bounds
        if ball_position[0] <= 0:
            right_score += 1
            reset_ball()
        elif ball_position[0] >= WIDTH - 1:
            left_score += 1
            reset_ball()

        draw_ball()

    def reset_ball():
        nonlocal ball_position, ball_speed
        ball_position = [WIDTH // 2, HEIGHT // 2]
        ball_speed = [random.choice([-1, 1]), random.choice([-1, 1])]

    def update_paddles():
        nonlocal left_paddle, right_paddle

        joystick_dir = get_joystick_direction()
        if joystick_dir == JOYSTICK_UP:
            left_paddle = max(left_paddle - paddle_speed, 0)
        elif joystick_dir == JOYSTICK_DOWN:
            left_paddle = min(left_paddle + paddle_speed, HEIGHT - paddle_height)

        # Simple AI for right paddle
        if ball_position[1] < right_paddle + paddle_height // 2:
            right_paddle = max(right_paddle - paddle_speed, 0)
        elif ball_position[1] > right_paddle + paddle_height // 2:
            right_paddle = min(right_paddle + paddle_speed, HEIGHT - paddle_height)

    def display_score():
        # Clear score
        rect(0, HEIGHT - 6, WIDTH, HEIGHT - 1, 0, 0, 0)

        # Draw new score
        draw_text_small(3, HEIGHT - 6, str(left_score), 255, 255, 255)
        draw_text_small(WIDTH - 9, HEIGHT - 6, str(right_score), 255, 255, 255)

    def main_pong_game_loop():
        nonlocal prev_left_score, prev_right_score, left_score, right_score
        rect(0, 0, WIDTH, HEIGHT, 0, 0, 0)
        while True:
            update_paddles()
            update_ball()
            draw_paddles()
            if left_score != prev_left_score or right_score != prev_right_score:
                display_score()
                prev_left_score = left_score
                prev_right_score = right_score
            time.sleep(0.05)

    reset_ball()
    main_pong_game_loop()


def game_selector():
    display.start()
    draw_text(10,  5, "SIMON", 222, 222, 222)
    draw_text(10, 20, "SNAKE", 222, 222, 222)
    draw_text(10, 35, "PONG", 222, 222, 222)
    selected = 0
    current_time = time.time()
    last_selection_time = current_time

    while True:

        joystick_dir = get_joystick_direction()
        current_time = time.time()

        # Add a debounce delay of 0.2 seconds
        if current_time - last_selection_time > 0.2:
            if joystick_dir == JOYSTICK_UP:
                if selected > 0:
                    selected -= 1
                    last_selection_time = current_time
            elif joystick_dir == JOYSTICK_DOWN:
                if selected < 2:
                    selected += 1
                    last_selection_time = current_time
        
        if selected == 0:
            draw_text(10,  5, "SIMON", 255, 255, 255)
            draw_text(10, 20, "SNAKE", 111, 111, 111)
            draw_text(10, 35, "PONG", 111, 111, 111)
        elif selected == 1:
            draw_text(10,  5, "SIMON", 111, 111, 111)
            draw_text(10, 20, "SNAKE", 255, 255, 255)
            draw_text(10, 35, "PONG", 111, 111, 111)
        elif selected == 2:
            draw_text(10,  5, "SIMON", 111, 111, 111)
            draw_text(10, 20, "SNAKE", 111, 111, 111)
            draw_text(10, 35, "PONG", 255, 255, 255)

        button = adc2.read_u16()
        if button < 10:
            if selected == 0:
                simon_game()
            elif selected == 1:
                snake_game()
            elif selected == 2:
                pong_game()

# Main
if __name__ == '__main__':
    game_selector()