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
JOYSTICK_UP_LEFT = 'UP-LEFT'
JOYSTICK_UP_RIGHT = 'UP-RIGHT'
JOYSTICK_DOWN_LEFT = 'DOWN-LEFT'
JOYSTICK_DOWN_RIGHT = 'DOWN-RIGHT'

char_dict = {'A': '3078ccccfccccc00', 'B': 'fc66667c6666fc00', 'C': '3c66c0c0c0663c00', 'D': 'f86c6666666cf800', 'E': 'fe6268786862fe00', 'F': 'fe6268786860f000', 'G': '3c66c0c0ce663e00', 'H': 'ccccccfccccccc00', 'I': '7830303030307800', 'J': '1e0c0c0ccccc7800', 'K': 'f6666c786c66f600', 'L': 'f06060606266fe00', 'M': 'c6eefefed6c6c600', 'N': 'c6e6f6decec6c600', 'O': '386cc6c6c66c3800', 'P': 'fc66667c6060f000', 'Q': '78ccccccdc781c00', 'R': 'fc66667c6c66f600', 'S': '78cce0380ccc7800', 'T': 'fcb4303030307800', 'U': 'ccccccccccccfc00', 'V': 'cccccccccc783000', 'W': 'c6c6c6d6feeec600', 'X': 'c6c66c38386cc600', 'Y': 'cccccc7830307800', 'Z': 'fec68c183266fe00', 'a': '0000780c7ccc7600', 'b': 'e060607c6666dc00', 'c': '000078ccc0cc7800', 'd': '1c0c0c7ccccc7600', 'e': '000078ccfcc07800', 'f': '386c60f06060f000', 'g': '000076cccc7c0cf8', 'h': 'e0606c766666e600', 'i': '3000703030307800', 'j': '0c000c0c0ccccc78', 'k': 'e060666c786ce600', 'l': '7030303030307800', 'm': '0000ccfefed6c600', 'n': '0000f8cccccccc00', 'o': '000078cccccc7800', 'p': '0000dc667c60f0', 'q': '000076cccc7c0c1e', 'r': '00009c766660f000', 's': '00007cc0780cf800', 't': '10307c3030341800', 'u': '0000cccccccc7600', 'v': '0000cccccc783000', 'w': '0000c6c6d6fe6c00', 'x': '0000c66c386cc600', 'y': '0000cccccc7c0cf8', 'z': '0000fc983064fc00', '0': '78ccdcfceccc7c00', '1': '307030303030fc00', '2': '78cc0c3860ccfc00', '3': '78cc0c380ccc7800', '4': '1c3c6cccfe0c1e00', '5': 'fcc0f80c0ccc7800', '6': '3860c0f8cccc7800', '7': 'fccc0c1830303000', '8': '78cccc78cccc7800', '9': '78cccc7c0c187000', '!': '3078783030003000', '#': '6c6cfe6cfe6c6c00', '$': '307cc0780cf83000', '%': '00c6cc183066c600', '&': '386c3876dccc7600', '?': '78cc0c1830003000', ' ': '0000000000000000', '.': '0000000000003000', ':': '0030000000300000','(': '0c18303030180c00', ')': '6030180c18306000', '[': '78c0c0c0c0c07800', ']': 'c06060606060c000', '{': '0c18306030180c00', '}': '6030180c18306000', '<': '0c18306030180c00', '>': '6030180c18306000', '=': '0000fc0000fc0000', '+': '0000187e18180000', '-': '0000007e00000000', '*': 'c66c3810386cc600', '/': '0000060c18306000', '\\': '00006030180c0c00', '_': '00000000000000fe', '|': '1818181818181800', ';': '0000003018003000', ',': '0000000000303000', "'": '3030300000000000', '"': 'cccc000000000000', '`': '0c18300000000000', '@': '3c66dececec07e00', '^': '183c666600000000', '█': 'ffffffffffffffff'}

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

# Initialize last_called for debounce
get_joystick_direction_last_called = time.time()
last_direction = JOYSTICK_UP

def get_joystick_direction(possible_directions, debounce=False):
    global get_joystick_direction_last_called, last_direction
    read0 = adc0.read_u16()
    read1 = adc1.read_u16()
    valueX = read0 - 32768  # Adjusted to be centered at 0
    valueY = read1 - 32768  # Adjusted to be centered at 0

    direction = None
    if valueY < -10000 and valueX < -10000:
        direction = JOYSTICK_UP_LEFT
    elif valueY < -10000 and valueX > 10000:
        direction = JOYSTICK_UP_RIGHT
    elif valueY > 10000 and valueX < -10000:
        direction = JOYSTICK_DOWN_LEFT
    elif valueY > 10000 and valueX > 10000:
        direction = JOYSTICK_DOWN_RIGHT
    elif abs(valueX) > abs(valueY):
        if valueX > 10000:
            direction = JOYSTICK_RIGHT
        elif valueX < -10000:
            direction = JOYSTICK_LEFT
    else:
        if valueY > 10000:
            direction = JOYSTICK_DOWN
        elif valueY < -10000:
            direction = JOYSTICK_UP

    if direction not in possible_directions:
        direction = None

    if debounce:
        current_time = time.time()
        if direction and direction != last_direction:
            last_direction = direction
            get_joystick_direction_last_called = current_time
            return direction
        elif direction == last_direction and current_time - get_joystick_direction_last_called > 0.25:
            get_joystick_direction_last_called = current_time
            return direction
        return None

    return direction

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
            
    
    def get_user_input():
        while True:
            joystick_dir = get_joystick_direction([JOYSTICK_UP_LEFT, JOYSTICK_UP_RIGHT, JOYSTICK_DOWN_LEFT, JOYSTICK_DOWN_RIGHT], debounce=False)
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
        global snake, snake_length, snake_direction, score, green_targets, target
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

    def main_snake_game_loop():
        global snake_direction
        step_counter = 0

        while True:
            step_counter += 1

            if step_counter % 1024 == 0:
                place_green_target()
            update_green_targets()

            joystick_dir = get_joystick_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT], debounce=False)

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
        nonlocal ball_position, ball_speed, left_score
        clear_ball()

        ball_position[0] += ball_speed[0]
        ball_position[1] += ball_speed[1]

        # Ball collision with top and bottom walls
        if ball_position[1] <= 0 or ball_position[1] >= HEIGHT - 1:
            ball_speed[1] = -ball_speed[1]

        # Ball collision with paddles
        if ball_position[0] == 1 and left_paddle <= ball_position[1] < left_paddle + paddle_height:
            ball_speed[0] = -ball_speed[0]
            left_score += 1
        elif ball_position[0] == WIDTH - 2 and right_paddle <= ball_position[1] < right_paddle + paddle_height:
            ball_speed[0] = -ball_speed[0]

        # Ball out of bounds
        if ball_position[0] <= 0:
            left_score = 0
            reset_ball()
        elif ball_position[0] >= WIDTH - 1:
            left_score += 10
            reset_ball()

        draw_ball()

    def reset_ball():
        nonlocal ball_position, ball_speed
        ball_position = [WIDTH // 2, HEIGHT // 2]
        ball_speed = [random.choice([-1, 1]), random.choice([-1, 1])]

    def update_paddles():
        nonlocal left_paddle, right_paddle

        joystick_dir = get_joystick_direction([JOYSTICK_UP, JOYSTICK_DOWN], debounce=False)
        if joystick_dir == JOYSTICK_UP:
            left_paddle = max(left_paddle - paddle_speed, 0)
        elif joystick_dir == JOYSTICK_DOWN:
            left_paddle = min(left_paddle + paddle_speed, HEIGHT - paddle_height)

        # Simple logic for automatic right paddle
        if ball_position[1] < right_paddle + paddle_height // 2:
            right_paddle = max(right_paddle - paddle_speed, 0)
        elif ball_position[1] > right_paddle + paddle_height // 2:
            right_paddle = min(right_paddle + paddle_speed, HEIGHT - paddle_height)

    def main_pong_game_loop():
        nonlocal prev_left_score, prev_right_score, left_score
        rect(0, 0, WIDTH, HEIGHT, 0, 0, 0)
        while True:
            update_paddles()
            update_ball()
            draw_paddles()
            if left_score != prev_left_score:
                display_score_and_time(left_score)
                prev_left_score = left_score
            time.sleep(0.05)

    reset_ball()
    main_pong_game_loop()

def qix_game():
    # Qix game variables
    player_position = [0, 0]  # Start at the edge of the playfield
    prev_player_position = player_position.copy()
    captured_area = [[False for _ in range(WIDTH)] for _ in range(HEIGHT)]
    player_trail = []
    player_direction = None
    qix_speed = 1
    qix_count = 1
    qix_positions = [(random.randint(1, WIDTH - 2), random.randint(1, HEIGHT - 8)) for _ in range(qix_count)]
    qix_direction = [(random.choice([-1, 1]), random.choice([-1, 1])) for _ in range(qix_count)]
    type_of_pixel = 0
    prev_type_of_pixel = 0

    # capture border
    for x in range(WIDTH):
        captured_area[0][x] = True
        captured_area[HEIGHT - 1][x] = True
        display.set_pixel(0, x, 0, 0, 255)
        display.set_pixel(HEIGHT - 1, x, 0, 0, 255)
    for y in range(HEIGHT):
        captured_area[y][0] = True
        captured_area[y][WIDTH - 1] = True
        display.set_pixel(y, 0, 0, 0, 255)
        display.set_pixel(y, WIDTH - 1, 0, 0, 255)

    def draw_qix():
        for x, y in qix_positions:
            display.set_pixel(x, y, 255, 0, 0)

    def clear_qix():
        for x, y in qix_positions:
            display.set_pixel(x, y, 0, 0, 0)

    def update_qix():
        nonlocal qix_positions, qix_direction
        clear_qix()
        for i in range(len(qix_positions)):
            qix_positions[i] = ((qix_positions[i][0] + qix_direction[i][0] * qix_speed) % WIDTH,
                                (qix_positions[i][1] + qix_direction[i][1] * qix_speed) % HEIGHT)

            # Bounce on walls or captured areas
            if qix_positions[i][0] <= 0 or qix_positions[i][0] >= WIDTH - 1 or captured_area[qix_positions[i][1]][qix_positions[i][0]]:
                qix_direction[i] = (-qix_direction[i][0], qix_direction[i][1])
            if qix_positions[i][1] <= 0 or qix_positions[i][1] >= HEIGHT - 1 or captured_area[qix_positions[i][1]][qix_positions[i][0]]:
                qix_direction[i] = (qix_direction[i][0], -qix_direction[i][1])
        draw_qix()

    def draw_player():
        display.set_pixel(player_position[0], player_position[1], 0, 255, 0)

    def clear_player():
        display.set_pixel(player_position[0], player_position[1], 0, 150, 0)

    def move_player():
        nonlocal player_position, player_direction, player_trail, prev_type_of_pixel, type_of_pixel, prev_player_position
        clear_player()

        prev_player_position = player_position.copy()



        if player_direction == JOYSTICK_UP and player_position[1] > 0:
            player_position[1] -= 1
        elif player_direction == JOYSTICK_DOWN and player_position[1] < HEIGHT - 1:
            player_position[1] += 1
        elif player_direction == JOYSTICK_LEFT and player_position[0] > 0:
            player_position[0] -= 1
        elif player_direction == JOYSTICK_RIGHT and player_position[0] < WIDTH - 1:
            player_position[0] += 1

        prev_type_of_pixel = type_of_pixel
        
        # check type of pixel on new position (border, qix, captured area, player trail, empty)
        type_of_pixel = 0
        if player_position[0] == 0 or player_position[0] == WIDTH - 1 or player_position[1] == 0 or player_position[1] == HEIGHT - 1:
            type_of_pixel = 1 # border
        elif player_position in qix_positions:
            type_of_pixel = 2 # qix
        elif captured_area[player_position[1]][player_position[0]]:
            type_of_pixel = 3 # captured area
        elif player_position in player_trail:
            type_of_pixel = 4 # player trail
        else:
            type_of_pixel = 5 # empty

        #print(type_of_pixel)

        if type_of_pixel == 3 and prev_type_of_pixel != 3:
            if len(player_trail) > 2:
                capture_area()
                #player_trail = []
                # set player trail to captured area
                #player_trail = [(x, y) for x in range(WIDTH) for y in range(HEIGHT) if captured_area[y][x]]
                player_trail = []

        # Update player trail
        if player_position not in player_trail:
            player_trail.append(player_position.copy())
            #print(player_trail)

        draw_player()

    def coords_to_matrix(coords, size=64):
        matrix = [[0] * size for _ in range(size)]
        for x, y in coords:
            matrix[x][y] = 1
        return matrix

    def add_border_coords(size=64):
        border_coords = []
        for i in range(size):
            border_coords.append((0, i))  # Top row
            border_coords.append((size - 1, i))  # Bottom row
            border_coords.append((i, 0))  # Left column
            border_coords.append((i, size - 1))  # Right column
        return border_coords

    def flood_fill(matrix, start, fill_char):
        rows, cols = len(matrix), len(matrix[0])
        queue = [start]
        filled = set()
        while queue:
            r, c = queue.pop(0)
            if (r < 0 or r >= rows or c < 0 or c >= cols or
                matrix[r][c] != ' ' or (r, c) in filled):
                continue
            matrix[r][c] = fill_char
            filled.add((r, c))
            queue.extend([(r-1, c), (r+1, c), (r, c-1), (r, c+1)])
        return filled


    def find_enclosed_areas(matrix):
        size = len(matrix)

        # Mark border-connected areas with -1
        for i in range(size):
            for j in range(size):
                if matrix[i][j] == 0 and (i == 0 or i == size - 1 or j == 0 or j == size - 1):
                    flood_fill(matrix, i, j, 0, -1)

        # Identify and collect enclosed areas
        enclosed_areas = []
        for i in range(size):
            for j in range(size):
                if matrix[i][j] == 0:
                    enclosed_areas.append(flood_fill(matrix, i, j, 0, 2))

        # Determine which areas to fill
        if enclosed_areas:
            smallest_area = min(enclosed_areas, key=len)
            for area in enclosed_areas:
                for x, y in area:
                    matrix[x][y] = 0  # Reset to empty
            for x, y in smallest_area:
                matrix[x][y] = 2  # Fill with blue

        # Restore original green coordinates
        for i in range(size):
            for j in range(size):
                if matrix[i][j] == 1:
                    matrix[i][j] = 'G'

        return matrix




    # Check if the player has enclosed an area
    def check_enclosure():
        nonlocal player_trail
        if player_trail:
            start_x, start_y = player_trail[0]
            end_x, end_y = player_trail[-1]
            if start_x == end_x or start_y == end_y:
                for x, y in player_trail:
                    captured_area[y][x] = True
                flood_fill2(start_x, start_y)

    # Capture the enclosed area
    def capture_area():
        matrix = coords_to_matrix(player_trail)
        enclosed_areas, filled_matrix = find_enclosed_areas(matrix)

        for area in enclosed_areas:
            for x, y in area:
                if filled_matrix[y][x] == 2:  # Fixed to reflect y,x
                    captured_area[y][x] = True
                    display.set_pixel(x, y, 0, 110, 255)
                if filled_matrix[y][x] == 1:  # Fixed to reflect y,x
                    display.set_pixel(x, y, 255, 255, 155)

    def flood_fill2(x, y):
        stack = [(x, y)]
        while stack:
            cx, cy = stack.pop()
            if 0 <= cx < WIDTH and 0 <= cy < HEIGHT and not captured_area[cy][cx]:
                captured_area[cy][cx] = True
                display.set_pixel(cx, cy, 0, 0, 255)
                stack.extend([(cx+1, cy), (cx-1, cy), (cx, cy+1), (cx, cy-1)])

    def main_qix_game_loop():
        nonlocal player_direction, player_trail
        while True:
            joystick_dir = get_joystick_direction([JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT], debounce=False)
            if joystick_dir is not None:
                player_direction = joystick_dir

            move_player()
            if not captured_area[player_position[1]][player_position[0]]:
                player_trail.append((player_position[0], player_position[1]))
                display.set_pixel(player_position[0], player_position[1], 255, 255, 255)

            check_enclosure()
            update_qix()

            # Count the number of pixels in captured areas
            captured_pixels = sum(sum(row) for row in captured_area)

            display_score_and_time(captured_pixels)

            # Check for collision with Qix or Player Trail
            for x, y in qix_positions:
                if (player_position[0], player_position[1]) == (x, y):
                    rect(0, 0, WIDTH, HEIGHT, 0, 0, 0)
                    display_score_and_time(0)
                    qix_game()
                if (x, y) in player_trail and not captured_area[y][x]:
                    rect(0, 0, WIDTH, HEIGHT, 0, 0, 0)
                    display_score_and_time(0)
                    qix_game()

            time.sleep(0.1)

    main_qix_game_loop()


def game_selector():
    games = ["SIMON", "SNAKE", "PONG", "QIX"]
    display.start()
    
    selected = 0
    previous_selected = None
    top_index = 0
    display_size = 4

    while True:
        # Draw the list of games, scrollable
        if selected != previous_selected:
            display.clear()
            previous_selected = selected
            for i in range(display_size):
                game_index = top_index + i
                if game_index < len(games):
                    if game_index == selected:
                        draw_text(10, 5 + i * 15, games[game_index], 255, 255, 255)
                    else:
                        draw_text(10, 5 + i * 15, games[game_index], 111, 111, 111)
        
        joystick_dir = get_joystick_direction([JOYSTICK_UP, JOYSTICK_DOWN], debounce=True)

        if joystick_dir is None:
            button = adc2.read_u16()
            if button < 10:
                button = adc2.read_u16()

            if button < 5 and selected < len(games):
                display.clear()

                if selected == 0:
                    simon_game()
                elif selected == 1:
                    snake_game()
                elif selected == 2:
                    pong_game()
                elif selected == 3:
                    qix_game()
            continue
        else:
            display.clear()
            previous_selected = None


        if joystick_dir == JOYSTICK_UP:
            if selected > 0:
                selected -= 1
            if selected < top_index:
                top_index -= 1
        elif joystick_dir == JOYSTICK_DOWN:
            if selected < len(games) - 1:
                selected += 1
            if selected > top_index + display_size - 1:
                top_index += 1

if __name__ == '__main__':
    game_selector()
