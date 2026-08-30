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
            d = joystick.read_direction(
                [
                    JOYSTICK_UP,
                    JOYSTICK_RIGHT,
                    JOYSTICK_LEFT,
                    JOYSTICK_DOWN,
                    JOYSTICK_UP_LEFT,
                    JOYSTICK_UP_RIGHT,
                    JOYSTICK_DOWN_LEFT,
                    JOYSTICK_DOWN_RIGHT,
                ],
                debounce=False,
            )
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
                if self.user_input != self.sequence[: len(self.user_input)]:
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
                    d = joystick.read_direction(
                        [
                            JOYSTICK_UP,
                            JOYSTICK_RIGHT,
                            JOYSTICK_LEFT,
                            JOYSTICK_DOWN,
                            JOYSTICK_UP_LEFT,
                            JOYSTICK_UP_RIGHT,
                            JOYSTICK_DOWN_LEFT,
                            JOYSTICK_DOWN_RIGHT,
                        ],
                        debounce=False,
                    )
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
                if self.user_input != self.sequence[: len(self.user_input)]:
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
        for x, y in self.snake[: self.snake_length]:
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

        direction = joystick.read_direction(
            [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
        )
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
            self.left_paddle_y = min(
                self.left_paddle_y + self.paddle_speed, PLAY_HEIGHT - self.paddle_height
            )

        if self.players_mode == "two":
            p2 = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN], debounce=False)
            if p2 == JOYSTICK_UP:
                self.right_paddle_y = max(self.right_paddle_y - self.paddle_speed, 0)
            elif p2 == JOYSTICK_DOWN:
                self.right_paddle_y = min(
                    self.right_paddle_y + self.paddle_speed,
                    PLAY_HEIGHT - self.paddle_height,
                )
            return

        # Lightweight AI: good enough to rally, imperfect enough to beat.
        by = self.ball_position[1]
        pc = self.right_paddle_y + self.paddle_height // 2
        ai_speed = self.ai_min_speed + min(
            self.ai_max_speed - self.ai_min_speed, self.left_score // 35
        )
        if self.ball_speed[0] < 0:
            # Re-center slowly while the ball travels away.
            target = PLAY_HEIGHT // 2
            if pc < target - 2:
                self.right_paddle_y = min(
                    self.right_paddle_y + 1, PLAY_HEIGHT - self.paddle_height
                )
            elif pc > target + 2:
                self.right_paddle_y = max(self.right_paddle_y - 1, 0)
            return
        if by < pc - 1:
            self.right_paddle_y = max(self.right_paddle_y - ai_speed, 0)
        elif by > pc + 1:
            self.right_paddle_y = min(
                self.right_paddle_y + ai_speed, PLAY_HEIGHT - self.paddle_height
            )

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
        if (
            x == self.left_paddle_x + 1
            and self.left_paddle_y <= y < self.left_paddle_y + self.paddle_height
        ):
            self.ball_position[0] = self.left_paddle_x + 1
            self.ball_speed[0] = abs(self.ball_speed[0])
            self._apply_paddle_english(self.left_paddle_y)
            self.left_score += 1

        # right paddle hit
        if (
            x == self.right_paddle_x - 1
            and self.right_paddle_y <= y < self.right_paddle_y + self.paddle_height
        ):
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
                draw_text_small(
                    1,
                    PLAY_HEIGHT,
                    str(self.left_score) + "-" + str(self.right_score),
                    255,
                    255,
                    255,
                )
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


class AirHockeyGame(FrameLoopGame):
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
    GOAL_TOP = PLAY_HEIGHT // 2 - GOAL_HALF
    GOAL_BOTTOM = PLAY_HEIGHT // 2 + GOAL_HALF
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
        self._draw_left_x = self.left_x
        self._draw_left_y = self.left_y
        self._draw_right_x = self.right_x
        self._draw_right_y = self.right_y
        self._draw_puck_x = self.puck_x
        self._draw_puck_y = self.puck_y
        self._rink_ready = False

    def _puck_speed(self):
        return math.sqrt(self.puck_vx * self.puck_vx + self.puck_vy * self.puck_vy)

    def _serve(self, direction=1):
        self.puck_x = WIDTH / 2
        self.puck_y = PLAY_HEIGHT / 2
        self.puck_vx = direction * (1.25 + random.random() * 0.55)
        self.puck_vy = random.choice((-0.95, -0.55, 0.55, 0.95))
        self.flash = 8

    def _keep_left(self, x, y):
        return clamp(x, self.RINK_LEFT + 4, WIDTH / 2 - 6), clamp(
            y, self.RINK_TOP + 4, self.RINK_BOTTOM - 4
        )

    def _keep_right(self, x, y):
        return clamp(x, WIDTH / 2 + 6, self.RINK_RIGHT - 4), clamp(
            y, self.RINK_TOP + 4, self.RINK_BOTTOM - 4
        )

    def _move_left(self, direction):
        if direction is None:
            self.prev_left_x = self.left_x
            self.prev_left_y = self.left_y
            return
        dx, dy = direction_to_delta_8way(direction)
        self.prev_left_x = self.left_x
        self.prev_left_y = self.left_y
        self.left_x, self.left_y = self._keep_left(
            self.left_x + dx * self.MALLET_SPEED, self.left_y + dy * self.MALLET_SPEED
        )

    def _move_right(self, direction):
        if direction is None:
            self.prev_right_x = self.right_x
            self.prev_right_y = self.right_y
            return
        dx, dy = direction_to_delta_8way(direction)
        self.prev_right_x = self.right_x
        self.prev_right_y = self.right_y
        self.right_x, self.right_y = self._keep_right(
            self.right_x + dx * self.MALLET_SPEED, self.right_y + dy * self.MALLET_SPEED
        )

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
            target_y = PLAY_HEIGHT / 2 + clamp(
                (self.puck_y - PLAY_HEIGHT / 2) * 0.28, -3.5, 3.5
            )
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
        if (
            self.left_score >= self.target_goals
            or self.right_score >= self.target_goals
        ):
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

        self._bounce_puck_off_mallet(
            self.left_x, self.left_y, self.prev_left_x, self.prev_left_y
        )
        self._bounce_puck_off_mallet(
            self.right_x, self.right_y, self.prev_right_x, self.prev_right_y
        )
        return True

    def _draw_rink(self):
        display.clear()
        draw_rectangle(0, 0, WIDTH - 1, PLAY_HEIGHT - 1, 14, 90, 70)
        draw_rectangle(
            self.RINK_LEFT, self.RINK_TOP, self.RINK_RIGHT, self.RINK_BOTTOM, 8, 120, 92
        )
        draw_rect_outline(
            self.RINK_LEFT,
            self.RINK_TOP,
            self.RINK_RIGHT,
            self.RINK_BOTTOM,
            220,
            220,
            220,
        )
        draw_line(
            WIDTH // 2,
            self.RINK_TOP + 1,
            WIDTH // 2,
            self.RINK_BOTTOM - 1,
            220,
            220,
            220,
        )
        for y in range(self.RINK_TOP + 4, self.RINK_BOTTOM - 3, 8):
            draw_line(WIDTH // 2 - 1, y, WIDTH // 2 + 1, y + 1, 220, 220, 220)
        draw_rectangle(
            self.RINK_LEFT, self.GOAL_TOP, self.RINK_LEFT + 1, self.GOAL_BOTTOM, 0, 0, 0
        )
        draw_rectangle(
            self.RINK_RIGHT - 1,
            self.GOAL_TOP,
            self.RINK_RIGHT,
            self.GOAL_BOTTOM,
            0,
            0,
            0,
        )

    def _rink_pixel_color(self, x, y):
        """Return the static rink color below a moving puck or mallet."""
        if (
            self.RINK_LEFT <= x <= self.RINK_RIGHT
            and self.RINK_TOP <= y <= self.RINK_BOTTOM
        ):
            color = (8, 120, 92)
        else:
            color = (14, 90, 70)

        if (
            x == self.RINK_LEFT
            or x == self.RINK_RIGHT
            or y == self.RINK_TOP
            or y == self.RINK_BOTTOM
        ):
            color = (220, 220, 220)
        elif x == WIDTH // 2 and self.RINK_TOP < y < self.RINK_BOTTOM:
            color = (220, 220, 220)
        elif (
            WIDTH // 2 - 1 <= x <= WIDTH // 2 + 1
            and self.RINK_TOP + 4 <= y < self.RINK_BOTTOM - 3
            and (y - (self.RINK_TOP + 4)) % 8 < 2
        ):
            color = (220, 220, 220)

        if self.GOAL_TOP <= y <= self.GOAL_BOTTOM and (
            self.RINK_LEFT <= x <= self.RINK_LEFT + 1
            or self.RINK_RIGHT - 1 <= x <= self.RINK_RIGHT
        ):
            return 0, 0, 0
        return color

    def _restore_rink_region(self, cx, cy, radius):
        """Restore one small dynamic region without repainting the whole rink."""
        x0 = max(0, int(cx) - radius)
        x1 = min(WIDTH - 1, int(cx) + radius)
        y0 = max(0, int(cy) - radius)
        y1 = min(PLAY_HEIGHT - 1, int(cy) + radius)
        sp = display.set_pixel
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                r, g, b = self._rink_pixel_color(x, y)
                sp(x, y, r, g, b)

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
        if not self._rink_ready:
            self._draw_rink()
            self._rink_ready = True
        else:
            self._restore_rink_region(self._draw_left_x, self._draw_left_y, 2)
            self._restore_rink_region(self._draw_right_x, self._draw_right_y, 2)
            self._restore_rink_region(self._draw_puck_x, self._draw_puck_y, 1)
        self._draw_player(self.left_x, self.left_y, (70, 170, 255))
        self._draw_player(self.right_x, self.right_y, (255, 90, 90))
        if self.flash:
            self.flash -= 1
        draw_rectangle(
            int(self.puck_x) - 1,
            int(self.puck_y) - 1,
            int(self.puck_x) + 1,
            int(self.puck_y) + 1,
            255,
            255,
            255,
        )
        self._draw_hud()
        self._draw_left_x = self.left_x
        self._draw_left_y = self.left_y
        self._draw_right_x = self.right_x
        self._draw_right_y = self.right_y
        self._draw_puck_x = self.puck_x
        self._draw_puck_y = self.puck_y
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
                    debounce=True,
                )
                right_dir = joystick.read_direction(
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
                    debounce=True,
                )
            else:
                left_dir = joystick.read_direction(
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
                    debounce=True,
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
        draw_rectangle(
            self.paddle_x,
            self.paddle_y,
            self.paddle_x + self.paddle_w - 1,
            self.paddle_y + PADDLE_HEIGHT - 1,
            255,
            255,
            255,
        )

    def clear_paddle(self):
        draw_rectangle(
            self.paddle_x,
            self.paddle_y,
            self.paddle_x + self.paddle_w - 1,
            self.paddle_y + PADDLE_HEIGHT - 1,
            0,
            0,
            0,
        )

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
            if (
                self.paddle_x <= self.ball_x + 1
                and self.ball_x <= self.paddle_x + self.paddle_w - 1
            ):
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
                if (
                    self.powerups_enabled
                    and random.randint(0, 99) < 18
                    and len(self.powerups) < 3
                ):
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
            self.paddle_x = min(
                self.paddle_x + self.paddle_speed, WIDTH - self.paddle_w
            )
        self.draw_paddle()

    def update_powerups(self):
        if not self.powerups_enabled:
            return
        keep = []
        for p in self.powerups:
            draw_rectangle(
                int(p[0]) - 1, int(p[1]) - 1, int(p[0]) + 1, int(p[1]) + 1, 0, 0, 0
            )
            p[1] += 0.65
            if p[1] >= self.paddle_y - 1:
                if self.paddle_x - 1 <= p[0] <= self.paddle_x + self.paddle_w:
                    self.wide_timer = 360
                    self.clear_paddle()
                    self.paddle_w = min(20, PADDLE_WIDTH + 6)
                    self.paddle_x = min(self.paddle_x, WIDTH - self.paddle_w)
                    play_sound("coin", 4)
                    continue
            if p[1] < PLAY_HEIGHT:
                keep.append(p)
                draw_rectangle(
                    int(p[0]) - 1,
                    int(p[1]) - 1,
                    int(p[0]) + 1,
                    int(p[1]) + 1,
                    80,
                    220,
                    255,
                )
        self.powerups = keep
        if self.wide_timer > 0:
            self.wide_timer -= 1
            if self.wide_timer == 0:
                self.clear_paddle()
                center = self.paddle_x + self.paddle_w // 2
                self.paddle_w = PADDLE_WIDTH
                self.paddle_x = clamp(
                    center - self.paddle_w // 2, 0, WIDTH - self.paddle_w
                )

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
                show_center_message(
                    ("YOU", "WON"), start_y=10, line_height=15, delay_ms=1500
                )
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
            self.draw_line(
                (bx - math.sin(rad) * wide, by - math.cos(rad) * wide),
                tail,
                (255, 220, 40),
            )

        def draw(self):
            a = self.angle
            s = self.size
            rad0 = math.radians(a)
            rad1 = math.radians(a + 120)
            rad2 = math.radians(a - 120)
            p0 = (self.x + math.cos(rad0) * s, self.y - math.sin(rad0) * s)
            p1 = (self.x + math.cos(rad1) * s, self.y - math.sin(rad1) * s)
            p2 = (self.x + math.cos(rad2) * s, self.y - math.sin(rad2) * s)

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
                        spawned.append(
                            self.Asteroid(
                                hit_a.x, hit_a.y, half, speed_boost=speed_boost
                            )
                        )
                    if len(self.asteroids) + len(spawned) < self.max_asteroids:
                        spawned.append(
                            self.Asteroid(
                                hit_a.x, hit_a.y, half, speed_boost=speed_boost
                            )
                        )
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
            direction = joystick.read_direction(
                [JOYSTICK_UP, JOYSTICK_LEFT, JOYSTICK_RIGHT]
            )
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
                self.asteroids = [
                    self.Asteroid(start=True, speed_boost=speed_boost)
                    for _ in range(3 if CONFIG_LOW_RAM_MODE else 4)
                ]
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
        edges = (
            [(x, 0) for x in range(self.width)]
            + [(x, self.height - 1) for x in range(self.width)]
            + [(0, y) for y in range(self.height)]
            + [(self.width - 1, y) for y in range(self.height)]
        )
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
            if get_grid_value(nx, ny) == 4 or (
                nx == self.player_x and ny == self.player_y
            ):
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
        (0, 255, 255),
        (255, 0, 0),
        (0, 255, 0),
        (0, 0, 255),
        (255, 255, 0),
        (255, 165, 0),
        (128, 0, 128),
    )

    TETRIMINOS = (
        ((1, 1, 1, 1),),  # I
        ((1, 1, 1), (0, 1, 0)),  # T
        ((1, 1, 0), (0, 1, 1)),  # S
        ((0, 1, 1), (1, 1, 0)),  # Z
        ((1, 1), (1, 1)),  # O
        ((1, 1, 1), (1, 0, 0)),  # L
        ((1, 1, 1), (0, 0, 1)),  # J
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
        draw_rectangle(
            x1, y1, x1 + self.BLOCK_SIZE - 1, y1 + self.BLOCK_SIZE - 1, *color
        )

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

        dirs = (
            (0, self.MazeWaySize),
            (0, -self.MazeWaySize),
            (self.MazeWaySize, 0),
            (-self.MazeWaySize, 0),
        )
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
                if (
                    self.BORDER <= nx < WIDTH - self.BORDER
                    and self.BORDER <= ny < PLAY_HEIGHT - self.BORDER
                    and not visited[self._idx(nx, ny)]
                ):
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
        dirs = (
            (0, self.MazeWaySize),
            (0, -self.MazeWaySize),
            (self.MazeWaySize, 0),
            (-self.MazeWaySize, 0),
        )
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
            if not (
                self.BORDER <= nx < WIDTH - self.BORDER
                and self.BORDER <= ny < PLAY_HEIGHT - self.BORDER
            ):
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
        dirs = ((-1, 0), (1, 0), (0, -1), (0, 1))
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
        d = joystick.read_direction(
            [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
        )
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
        for ex, ey in self.enemies:
            moves = []
            for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
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
                show_center_message(
                    ("YOU", "WON"),
                    start_y=18,
                    line_height=15,
                    r=0,
                    g=255,
                    b=0,
                    delay_ms=win_delay_ms,
                )
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
                draw_rectangle(
                    x, bot_start, x + self.pipe_w - 1, PLAY_HEIGHT - 1, 0, 200, 0
                )

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


class DodgeGame(FrameLoopGame):
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
        self.obstacles = []  # [x, y, w, h, vx, vy, color_hue]
        self.score = 0
        self.last_dir = None
        self.last_spawn = ticks_ms()
        self.spawn_ms = self.START_SPAWN_MS  # wird mit steigender Punktzahl schneller
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
            o[0] += o[4]  # x += vx
            o[1] += o[5]  # y += vy
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
                if (
                    self.spawn_ms > self.MIN_SPAWN_MS
                    and (self.score % self.DIFFICULTY_SCORE_INTERVAL) == 0
                ):
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


class InvaderGame(FrameLoopGame):
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
        interval = max(
            230,
            900 - self.wave * 55 - (self.ALIEN_ROWS * self.ALIEN_COLS - live_count) * 8,
        )
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
            pts = (
                (2, 0),
                (1, 1),
                (2, 1),
                (3, 1),
                (0, 2),
                (1, 2),
                (3, 2),
                (4, 2),
                (0, 3),
                (4, 3),
            )
            color = (200, 120, 255)
        elif typ < 3:
            pts = (
                (1, 0),
                (3, 0),
                (0, 1),
                (1, 1),
                (2, 1),
                (3, 1),
                (4, 1),
                (0, 2),
                (2, 2),
                (4, 2),
                (1, 3),
                (3, 3),
            )
            color = (0, 220, 80)
        else:
            pts = (
                (0, 0),
                (4, 0),
                (1, 1),
                (2, 1),
                (3, 1),
                (0, 2),
                (1, 2),
                (3, 2),
                (4, 2),
                (1, 3),
                (3, 3),
            )
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


class TronGame(FrameLoopGame):
    """
    TRON LIGHT CYCLE (Endless)
    Controls:
      - Left/Right: 90° turn
      - P1: WASD + Shift turbo in 2P mode
      - P2: Arrow keys + Z turbo in 2P mode
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
            if dist > 8:  # don't need to look too far
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
            # Keep respawns readable and away from the player's current position.
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
                draw_rectangle(
                    self.enemy_x - 2,
                    self.enemy_y - 2,
                    self.enemy_x + 2,
                    self.enemy_y + 2,
                    255,
                    100,
                    0,
                )
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

    def _step_two_player(self, p1_turbo, p2_turbo):
        """Advance both cycles from the same board state for fair collisions."""
        p1_steps = self.TURBO_STEP if p1_turbo else 1
        p2_steps = self.TURBO_STEP if p2_turbo else 1
        for phase in range(max(p1_steps, p2_steps)):
            p1_moves = phase < p1_steps
            p2_moves = phase < p2_steps
            p1_next = None
            p2_next = None
            p1_alive = True
            p2_alive = True

            if p1_moves:
                dx, dy = self._DIR_VECS[self.direction]
                p1_next = self.head_x + dx, self.head_y + dy
                p1_alive = not self._blocked(p1_next[0], p1_next[1])
            if p2_moves:
                dx, dy = self._DIR_VECS[self.enemy_dir]
                p2_next = self.enemy_x + dx, self.enemy_y + dy
                p2_alive = not self._blocked(p2_next[0], p2_next[1])

            # Reaching one free cell at the same time is a draw, regardless of
            # whether player one or player two happens to be processed first.
            if p1_moves and p2_moves and p1_next == p2_next:
                return False, False
            if not p1_alive or not p2_alive:
                return p1_alive, p2_alive

            if p1_moves:
                self.head_x, self.head_y = p1_next
                self.score += 1
                self._occupy(self.head_x, self.head_y)
                self._draw_head()
            if p2_moves:
                self.enemy_x, self.enemy_y = p2_next
                self.enemy_score += 1
                self._occupy(self.enemy_x, self.enemy_y)
                self._draw_enemy()
        return True, True

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

    def _draw_match_score(self):
        if self.players_mode != "two":
            display_score_and_time(self.score)
            return
        draw_rectangle(0, PLAY_HEIGHT, WIDTH - 1, HEIGHT - 1, 0, 0, 0)
        draw_text_small(1, PLAY_HEIGHT, "1" + str(self.score), 80, 210, 255)
        draw_text_small(23, PLAY_HEIGHT, "-", 255, 255, 255)
        draw_text_small(30, PLAY_HEIGHT, "2" + str(self.enemy_score), 255, 90, 75)
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
                turn, p1_action = read_wasd_input(
                    [JOYSTICK_LEFT, JOYSTICK_RIGHT], debounce=True
                )
                p2_turbo = z_button
            else:
                turn = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT])
                p2_turbo = False
            if turn:
                self._turn(turn)
            if self.players_mode == "two":
                p2_turn = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT])
                if p2_turn:
                    self._turn_enemy(p2_turn)
                p1_alive, p2_alive = self._step_two_player(p1_action, p2_turbo)
                if not p1_alive or not p2_alive:
                    if p1_alive:
                        self.score += 150
                    elif p2_alive:
                        self.enemy_score += 150
                    set_game_over_score(self.score, won=p1_alive and not p2_alive)
                    return False
            else:
                if not self._step(turbo=z_button):
                    game_over = True
                    return False
            global_score = self.score
            self._draw_match_score()
            if (
                self.players_mode != "two"
                and not self.enemy_alive
                and random.randint(0, 15) == 0
            ):
                self._try_respawn_enemy()
            return True

        return step
