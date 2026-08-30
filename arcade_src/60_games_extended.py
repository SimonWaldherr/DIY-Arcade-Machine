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
        (
            "LWSS",
            6,
            ((0, 0), (0, 2), (1, 3), (2, 3), (3, 0), (3, 3), (4, 1), (4, 2), (4, 3)),
        ),
        (
            "LWS2",
            7,
            (
                (0, 1),
                (0, 2),
                (1, 1),
                (1, 2),
                (1, 3),
                (2, 0),
                (2, 2),
                (2, 3),
                (3, 0),
                (3, 1),
                (3, 2),
                (4, 1),
            ),
        ),
        (
            "LWS3",
            7,
            (
                (0, 1),
                (0, 2),
                (1, 0),
                (1, 1),
                (1, 2),
                (2, 0),
                (2, 1),
                (2, 3),
                (3, 1),
                (3, 2),
                (3, 3),
                (4, 2),
            ),
        ),
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
        for buf in (
            self.alive,
            self.red,
            self.blue,
            self.next_alive,
            self.next_red,
            self.next_blue,
        ):
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
            d = joystick.read_direction(
                [JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_UP, JOYSTICK_DOWN]
            )
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
            draw_rectangle(
                1, 4, min(self.LEFT_W - 2, self.player_energy), 4, 0, 180, 255
            )
        if self.enemy_energy > 0:
            draw_rectangle(
                max(self.RIGHT_X + 1, WIDTH - 1 - self.enemy_energy),
                4,
                WIDTH - 2,
                4,
                255,
                60,
                0,
            )

    def _draw_bases(self):
        now = ticks_ms()
        left_col = (
            (70, 190, 255)
            if ticks_diff(now, self.red_hit_until) >= 0
            else (255, 255, 255)
        )
        right_col = (
            (255, 90, 45)
            if ticks_diff(now, self.blue_hit_until) >= 0
            else (255, 255, 255)
        )
        draw_rect_outline(0, 8, self.LEFT_W - 1, PLAY_HEIGHT - 2, 0, 42, 110)
        draw_rect_outline(self.RIGHT_X, 8, WIDTH - 1, PLAY_HEIGHT - 2, 110, 25, 0)
        draw_rectangle(
            2,
            PLAY_HEIGHT // 2 - 3,
            5,
            PLAY_HEIGHT // 2 + 3,
            left_col[0],
            left_col[1],
            left_col[2],
        )
        draw_rectangle(3, PLAY_HEIGHT // 2 - 1, 6, PLAY_HEIGHT // 2 + 1, 0, 45, 110)
        cx = WIDTH - 4
        cy = PLAY_HEIGHT // 2
        draw_rect_outline(
            cx - 3, cy - 3, cx + 2, cy + 3, right_col[0], right_col[1], right_col[2]
        )
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
        col = (
            (255, 255, 255)
            if ticks_diff(ticks_ms(), self.flash_until) < 0
            else (0, 180, 255)
        )
        enemy_preview_y = clamp(PLAY_HEIGHT - cy - 5, 1, PLAY_HEIGHT - 7)
        self._draw_direction_arrow(cy + 2, True)
        self._draw_direction_arrow(enemy_preview_y + 2, False)
        self._draw_pattern_preview(4, cy, self.pattern_idx, True)
        self._draw_pattern_preview(WIDTH - 6, enemy_preview_y, self.pattern_idx, False)
        draw_rect_outline(
            1,
            cy - 1,
            self.LEFT_W - 2,
            min(PLAY_HEIGHT - 1, cy + 5),
            col[0],
            col[1],
            col[2],
        )
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
            if (
                abs(self.ball_x - tx) <= 2 + self.BALL_R
                and abs(self.ball_y - ty) <= 4 + self.BALL_R
            ):
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
        if (
            not left_on
            and not right_on
            and self.ball_y < PLAY_HEIGHT - 8
            and self.vx * self.vx + self.vy * self.vy < 0.05
        ):
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
            draw_rect_outline(
                bx - radius, by - radius, bx + radius, by + radius, 0, 120, 255
            )
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
        draw_rectangle(
            int(self.ball_x) - 1,
            int(self.ball_y) - 1,
            int(self.ball_x) + 1,
            int(self.ball_y) + 1,
            255,
            255,
            255,
        )
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


class SabotrGame(FrameLoopGame):
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
    DIRS = {
        JOYSTICK_UP: (0, -1),
        JOYSTICK_DOWN: (0, 1),
        JOYSTICK_LEFT: (-1, 0),
        JOYSTICK_RIGHT: (1, 0),
    }

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
                    self.guards.append(
                        [
                            x,
                            y,
                            random.choice(
                                (
                                    JOYSTICK_LEFT,
                                    JOYSTICK_RIGHT,
                                    JOYSTICK_UP,
                                    JOYSTICK_DOWN,
                                )
                            ),
                            0,
                        ]
                    )

    def _blocked(self, x, y):
        return (
            x < 0 or x >= self.W or y < 0 or y >= self.H or self.walls[y * self.W + x]
        )

    def _guard_cells(self):
        return set((g[0], g[1]) for g in self.guards)

    def _behind_guard(self, g):
        dx, dy = self.DIRS.get(g[2], (1, 0))
        return g[0] - dx, g[1] - dy

    def _try_takedown(self):
        for g in list(self.guards):
            if (self.px, self.py) == self._behind_guard(g) or abs(self.px - g[0]) + abs(
                self.py - g[1]
            ) == 1:
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
        d = joystick.read_direction(
            [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
        )
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
            return [
                [ax + 18, ay, "S"],
                [ax, ay - 9, "D"],
                [ax, ay + 9, "D"],
                [self.blue_goalie_x, self.blue_goalie_y, "G"],
            ]
        ax = self.red_anchor_x
        ay = self.red_anchor_y
        return [
            [ax - 18, ay, "S"],
            [ax, ay - 9, "D"],
            [ax, ay + 9, "D"],
            [self.red_goalie_x, self.red_goalie_y, "G"],
        ]

    def _kickoff(self):
        self.ball_x = WIDTH / 2
        self.ball_y = PLAY_HEIGHT / 2
        self.vx = random.choice((-1.2, 1.2))
        self.vy = random.choice((-0.45, 0.45))
        self.ball_owner = None

    def _move_blue(self, joystick):
        d = joystick.read_direction(
            [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
        )
        dx, dy = direction_to_delta(d)
        if dx or dy:
            self.input_dx = dx
            self.input_dy = dy
        goalie_owned = (
            self.ball_owner and self.ball_owner[0] == "B" and self.ball_owner[1] == 3
        )
        if goalie_owned:
            if dx:
                self.blue_goalie_x = clamp(self.blue_goalie_x + dx, 3, 12)
            if dy:
                self.blue_goalie_y = clamp(
                    self.blue_goalie_y + dy * 2,
                    PLAY_HEIGHT // 2 - 10,
                    PLAY_HEIGHT // 2 + 10,
                )
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
        if not (
            self.ball_owner and self.ball_owner[0] == "B" and self.ball_owner[1] == 3
        ):
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
            goalie_target = (
                self.ball_y if self.ball_x > WIDTH // 2 else PLAY_HEIGHT // 2
            )
            if self.red_goalie_y < goalie_target - 1:
                self.red_goalie_y += 1
            elif self.red_goalie_y > goalie_target + 1:
                self.red_goalie_y -= 1
        self.blue_goalie_x = clamp(self.blue_goalie_x, 3, 12)
        self.blue_goalie_y = clamp(
            self.blue_goalie_y, PLAY_HEIGHT // 2 - 10, PLAY_HEIGHT // 2 + 10
        )
        self.red_goalie_x = clamp(self.red_goalie_x, 51, 60)
        self.red_goalie_y = clamp(
            self.red_goalie_y, PLAY_HEIGHT // 2 - 10, PLAY_HEIGHT // 2 + 10
        )

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
        if (
            b_role == "G"
            and self.ball_x < 10
            and abs(self.ball_y - self.blue_goalie_y) <= 4
        ):
            blue_limit = 18
        if (
            r_role == "G"
            and self.ball_x > WIDTH - 10
            and abs(self.ball_y - self.red_goalie_y) <= 3
        ):
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
                target_y = PLAY_HEIGHT // 2 + (
                    8 if self.red_goalie_y <= PLAY_HEIGHT // 2 else -8
                )
                target_y = clamp(target_y, PLAY_HEIGHT // 2 - 9, PLAY_HEIGHT // 2 + 9)
                self.vx = 3.10
                self.vy = (target_y - self.ball_y) * 0.105
        else:
            target_y = PLAY_HEIGHT // 2 + (
                7 if self.blue_goalie_y <= PLAY_HEIGHT // 2 else -7
            )
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
        draw_rect_outline(
            0, PLAY_HEIGHT // 2 - 10, 3, PLAY_HEIGHT // 2 + 10, 255, 255, 255
        )
        draw_rect_outline(
            WIDTH - 4,
            PLAY_HEIGHT // 2 - 10,
            WIDTH - 1,
            PLAY_HEIGHT // 2 + 10,
            255,
            255,
            255,
        )
        self._draw_team(self._formation(True), (45, 165, 255))
        self._draw_team(self._formation(False), (255, 55, 45))
        draw_rectangle(
            int(self.ball_x) - 1,
            int(self.ball_y) - 1,
            int(self.ball_x) + 1,
            int(self.ball_y) + 1,
            255,
            255,
            255,
        )
        draw_text_small(
            1,
            PLAY_HEIGHT,
            str(self.blue_goals) + "-" + str(self.red_goals),
            255,
            255,
            255,
        )
        draw_text_small(27, PLAY_HEIGHT, "H" + str(self.half), 180, 180, 180)
        draw_text_small(
            45, PLAY_HEIGHT, str(max(0, self.ticks_left // 25)), 255, 220, 60
        )

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


class TowerDefenseGame(FrameLoopGame):
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
        (
            "PATH",
            (
                (0, 1),
                (2, 1),
                (2, 3),
                (6, 3),
                (6, 1),
                (7, 1),
                (7, 5),
                (2, 5),
                (2, 6),
                (7, 6),
            ),
        ),
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
        return (
            clamp(int(px) // self.CELL, 0, self.GRID_W - 1),
            clamp(int(py) // self.CELL, 0, self.GRID_H - 1),
        )

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
                if not self._find_route(
                    self._point_to_cell(e[0], e[1]), blocked_extra=(gx, gy)
                ):
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
        d = joystick.read_direction(
            [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
        )
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
        runner = self.wave >= 4 and self.spawn_queue % 5 == 0
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
        self.enemies.append(
            [float(x), float(y), 1, float(hp), float(hp), speed, 0, kind, reward, route]
        )

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
            self._damage_enemy(
                target,
                self.TOWER_DAMAGE[level],
                slow=level >= 2,
                splash=4 if level >= 3 else 0,
            )
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
                if (gx, gy - 1) not in self.path_cells and not (
                    (gx, gy) == self.base_cell and gy == 0
                ):
                    draw_line(x, y, x2, y, *edge)
                if (gx + 1, gy) not in self.path_cells and not (
                    (gx, gy) == self.base_cell and gx == self.GRID_W - 1
                ):
                    draw_line(x2, y, x2, y2, *edge)
                if (gx, gy + 1) not in self.path_cells and not (
                    (gx, gy) == self.base_cell and gy == self.GRID_H - 1
                ):
                    draw_line(x, y2, x2, y2, *edge)
                if (gx - 1, gy) not in self.path_cells and not (
                    (gx, gy) == self.start_cell and gx == 0
                ):
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
        colors = (
            (0, 0, 0),
            (60, 220, 90),
            (60, 185, 255),
            (205, 85, 255),
            (255, 230, 90),
        )
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
            draw_rectangle(
                x - size, y - size, x + size, y + size, col[0], col[1], col[2]
            )
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
        draw_rect_outline(
            cx, cy, cx + self.CELL - 1, cy + self.CELL - 1, col[0], col[1], col[2]
        )
        if tower:
            tx, ty = self._cell_center(self.cursor_x, self.cursor_y)
            rng = self.TOWER_RANGE[tower[2]]
            draw_rect_outline(
                max(0, tx - rng),
                max(0, ty - rng),
                min(WIDTH - 1, tx + rng),
                min(PLAY_HEIGHT - 1, ty + rng),
                35,
                70,
                95,
            )

    def _draw_hud(self):
        draw_rectangle(0, PLAY_HEIGHT, WIDTH - 1, HEIGHT - 1, 0, 0, 0)
        draw_text_small(1, PLAY_HEIGHT, "W" + str(self.wave), 180, 180, 180)
        draw_text_small(19, PLAY_HEIGHT, "$" + str(min(99, self.money)), 255, 220, 40)
        draw_text_small(43, PLAY_HEIGHT, "B" + str(max(0, self.lives)), 80, 190, 255)
        if self.open_level:
            draw_rectangle(
                WIDTH - 2, PLAY_HEIGHT + 1, WIDTH - 1, PLAY_HEIGHT + 2, 80, 255, 140
            )

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


class DigDugGame(FrameLoopGame):
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
                self.enemies.append(
                    [x, y, 0, random.choice((JOYSTICK_LEFT, JOYSTICK_RIGHT)), 0]
                )
                self.dirt[y][x] = False

    def _move_player(self, joystick):
        now = ticks_ms()
        if ticks_diff(now, self.last_move) < 130:
            return
        d = joystick.read_direction(
            [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
        )
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
            aligned = dx and e[1] == self.py and (e[0] - self.px) * dx > 0 and dist <= 2
            aligned = aligned or (
                dy and e[0] == self.px and (e[1] - self.py) * dy > 0 and dist <= 2
            )
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
        draw_rectangle(
            x + 1, y + 1, x + self.CELL - 2, y + self.CELL - 2, col[0], col[1], col[2]
        )

    def _draw(self):
        display.clear()
        for y in range(self.GRID_H):
            for x in range(self.GRID_W):
                if self.dirt[y][x]:
                    shade = 34 + min(60, y * 8)
                    self._draw_cell(x, y, (shade, 22 + y * 5, 8))
                else:
                    draw_rect_outline(
                        x * self.CELL + 2,
                        y * self.CELL + 3,
                        x * self.CELL + self.CELL - 3,
                        y * self.CELL + self.CELL,
                        18,
                        15,
                        22,
                    )
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


class JoustGame(FrameLoopGame):
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
            self.enemies.append(
                [
                    float(side),
                    float(10 + (i * 11) % 38),
                    -1.1 if side > WIDTH else 1.1,
                    0.0,
                ]
            )

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
            if rects_overlap(
                int(self.x), int(self.y), 5, 5, int(e[0]), int(e[1]), 5, 5
            ):
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
        for px, py, pw in (
            (3, PLAY_HEIGHT - 5, 58),
            (6, 37, 20),
            (38, 37, 20),
            (18, 22, 28),
        ):
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


class BurgerTimeGame(FrameLoopGame):
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
            self.enemies.append(
                [7 - (i % 3), self.PLAT_ROWS[i % len(self.PLAT_ROWS)], 0, 0]
            )

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
        d = joystick.read_direction(
            [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
        )
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
            draw_rectangle(
                0, y * self.CELL + 6, WIDTH - 1, y * self.CELL + 7, 80, 95, 150
            )
        for x in self.LADDERS:
            draw_line(
                x * self.CELL + 3, 0, x * self.CELL + 3, PLAY_HEIGHT - 2, 70, 150, 210
            )
            draw_line(
                x * self.CELL + 5, 0, x * self.CELL + 5, PLAY_HEIGHT - 2, 70, 150, 210
            )

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
                draw_rectangle(
                    x,
                    py,
                    x + 6,
                    py + 2,
                    r if dim else r // 2,
                    g if dim else g // 2,
                    b if dim else b // 2,
                )
        for e in self.enemies:
            col = (180, 180, 180) if e[3] > 0 else (255, 60, 60)
            draw_rectangle(
                e[0] * self.CELL + 2,
                e[1] * self.CELL + 2,
                e[0] * self.CELL + 5,
                e[1] * self.CELL + 5,
                col[0],
                col[1],
                col[2],
            )
        draw_rectangle(
            self.px * self.CELL + 2,
            self.py * self.CELL + 1,
            self.px * self.CELL + 5,
            self.py * self.CELL + 5,
            255,
            230,
            90,
        )
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


class StickArcherGame(FrameLoopGame):
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
        d = joystick.read_direction(
            [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
        )
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
        self.arrows.append(
            [
                float(sx),
                float(sy),
                math.cos(rad) * speed,
                -math.sin(rad) * speed,
                0,
                sx,
                sy,
            ]
        )
        self.charge = 0

    def _fire_enemy(self):
        dx = max(10, self.ex - self.px)
        base = 24 + min(28, dx // 2)
        angle = clamp(base + random.randint(-9, 9) - self.wave, 14, 72)
        rad = math.radians(angle)
        speed = 2.6 + min(1.3, self.wave * 0.14)
        sx = self.ex - 4
        sy = self.GROUND_Y - 14
        self.arrows.append(
            [
                float(sx),
                float(sy),
                -math.cos(rad) * speed,
                -math.sin(rad) * speed,
                1,
                sx,
                sy,
            ]
        )
        self.enemy_next_shot = ticks_ms() + max(
            650, 1700 - self.wave * 80 + random.randint(-160, 180)
        )

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
            self.parts.append(
                [
                    float(x),
                    float(self.GROUND_Y - 14 + i % 4),
                    vx,
                    vy,
                    28 + random.randint(0, 18),
                    col,
                ]
            )

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
                self.player_hp, hit, _head = self._target_hit(
                    a, self.px, self.player_hp
                )
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
            draw_line(
                ix + (3 if friendly else -3),
                body_y + 2,
                bow_x,
                body_y - 4,
                210,
                170,
                80,
            )
            draw_line(
                ix + (3 if friendly else -3),
                body_y + 2,
                bow_x,
                body_y + 8,
                210,
                170,
                80,
            )
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
            draw_line(
                int(a[5]), int(a[6]), int(a[0]), int(a[1]), col[0], col[1], col[2]
            )
            display.set_pixel(int(a[0]), int(a[1]), 255, 255, 255)
        for p in self.parts:
            col = p[5]
            draw_rectangle(
                int(p[0]),
                int(p[1]),
                int(p[0]) + 1,
                int(p[1]) + 1,
                col[0],
                col[1],
                col[2],
            )
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


class OrbitGame(FrameLoopGame):
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
            br = (
                random.randint(16, 38) / 10.0
                if small
                else random.randint(44, 76) / 10.0
            )
            vx = random.randint(-10, 10) / 35.0
            vy = random.randint(-10, 10) / 35.0
            self.blobs.append([float(x), float(y), vx, vy, br])
        self.wells = []
        if self.level >= 2:
            self.wells.append(
                [WIDTH // 2, PLAY_HEIGHT // 2, 0.018 + self.level * 0.002]
            )
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
        self.blobs.append(
            [bx, by, -ax * 1.1 + self.vx * 0.25, -ay * 1.1 + self.vy * 0.25, 1.5]
        )
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


class GalaxyGame(FrameLoopGame):
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
        self.fleets.append(
            [
                float(src[0]),
                float(src[1]),
                dst_i,
                owner,
                ships,
                dx / dist * speed,
                dy / dist * speed,
            ]
        )

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
            d0 = (
                abs(p[0] - self.planets[src_i][0])
                + abs(p[1] - self.planets[src_i][1])
                + p[4] * 2
            )
            d1 = (
                abs(self.planets[dst_i][0] - self.planets[src_i][0])
                + abs(self.planets[dst_i][1] - self.planets[src_i][1])
                + self.planets[dst_i][4] * 2
            )
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
                draw_rect_outline(
                    p[0] - p[2] - 2,
                    p[1] - p[2] - 2,
                    p[0] + p[2] + 2,
                    p[1] + p[2] + 2,
                    255,
                    255,
                    255,
                )
            if i == self.cursor:
                draw_rect_outline(
                    p[0] - p[2] - 4,
                    p[1] - p[2] - 4,
                    p[0] + p[2] + 4,
                    p[1] + p[2] + 4,
                    255,
                    230,
                    70,
                )
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


class OrbitalGame(FrameLoopGame):
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
            self.bursts.append(
                [
                    float(x),
                    float(y),
                    random.randint(-12, 12) / 10.0,
                    random.randint(-12, 12) / 10.0,
                    14 + random.randint(0, 10),
                    col,
                ]
            )

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
            if (
                c[1] + c[2] >= self.CANNON_Y - 2
                and abs(c[0] - self.CANNON_X) < c[2] + 5
            ):
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
            col = (
                (255, 90, 90)
                if c[3] == 1
                else ((255, 190, 70) if c[3] == 2 else (80, 190, 255))
            )
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
                draw_rectangle(
                    int(shot[0]) - 1,
                    int(shot[1]) - 1,
                    int(shot[0]) + 1,
                    int(shot[1]) + 1,
                    255,
                    255,
                    255,
                )
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
        draw_rectangle(
            self.CANNON_X - 2,
            self.CANNON_Y - 1,
            self.CANNON_X + 2,
            self.CANNON_Y + 1,
            150,
            150,
            170,
        )
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
                    if (
                        0 <= px < self.COLS
                        and 0 <= py < self.ROWS
                        and g[self._idx(px, py)] == c
                    ):
                        continue
                    run = [(x, y)]
                    nx, ny = x + dx, y + dy
                    while (
                        0 <= nx < self.COLS
                        and 0 <= ny < self.ROWS
                        and g[self._idx(nx, ny)] == c
                    ):
                        run.append((nx, ny))
                        nx += dx
                        ny += dy
                    if len(run) >= 3:
                        marks.update(run)
        return marks

    def _apply_gravity(self):
        for x in range(self.COLS):
            stack = [
                self.grid[self._idx(x, y)]
                for y in range(self.ROWS)
                if self.grid[self._idx(x, y)]
            ]
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
        draw_rect_outline(
            self.OX - 1,
            self.OY - 1,
            self.OX + self.COLS * self.CELL,
            self.OY + self.ROWS * self.CELL,
            60,
            60,
            90,
        )
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
                [JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_UP, JOYSTICK_DOWN],
                debounce=False,
            )
            if (
                d in (JOYSTICK_LEFT, JOYSTICK_RIGHT)
                and ticks_diff(now, self.last_move) >= 110
            ):
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
            interval = (
                self.fall_interval // 5 if d == JOYSTICK_DOWN else self.fall_interval
            )
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


class LightsOutGame(GridCursorGame):
    """Turn off a five-by-five light grid by toggling adjacent cells."""

    FRAME_MS = 40
    GRID_W = 5
    GRID_H = 5
    CELL = 10
    ORIGIN_X = 7
    ORIGIN_Y = 4
    SCRAMBLE_STEPS_MIN = 12
    SCRAMBLE_STEPS_MAX = 16

    def __init__(self):
        self.reset()

    def reset(self):
        self.cursor_x = self.GRID_W // 2
        self.cursor_y = self.GRID_H // 2
        self.last_move = ticks_ms()
        self.last_z = False
        self.moves = 0
        self.grid = [0] * (self.GRID_W * self.GRID_H)
        used_positions = []
        scramble_steps = random.randint(
            self.SCRAMBLE_STEPS_MIN,
            self.SCRAMBLE_STEPS_MAX,
        )
        while len(used_positions) < scramble_steps:
            index = random.randint(0, self.GRID_W * self.GRID_H - 1)
            if index in used_positions:
                continue
            used_positions.append(index)
            self._flip_pattern(index % self.GRID_W, index // self.GRID_W)
        if self._is_solved():
            self._flip_pattern(self.cursor_x, self.cursor_y)
        self.needs_redraw = True

    def _index(self, x, y):
        return y * self.GRID_W + x

    def _flip_pattern(self, x, y):
        for dx, dy in ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)):
            nx = x + dx
            ny = y + dy
            if 0 <= nx < self.GRID_W and 0 <= ny < self.GRID_H:
                index = self._index(nx, ny)
                self.grid[index] = 1 - self.grid[index]

    def _is_solved(self):
        return not any(self.grid)

    def _draw(self):
        display.clear()
        for y in range(self.GRID_H):
            for x in range(self.GRID_W):
                px = self.ORIGIN_X + x * self.CELL
                py = self.ORIGIN_Y + y * self.CELL
                if self.grid[self._index(x, y)]:
                    color = (255, 210, 30)
                else:
                    color = (18, 28, 42)
                draw_rectangle(px, py, px + 7, py + 7, *color)
        px = self.ORIGIN_X + self.cursor_x * self.CELL
        py = self.ORIGIN_Y + self.cursor_y * self.CELL
        draw_rect_outline(px - 1, py - 1, px + 8, py + 8, 255, 255, 255)
        display_score_and_time(self.moves)

    def _build_step(self, joystick):
        begin_game(0)
        self.reset()
        self._draw()
        self.needs_redraw = False

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            if self._move_cursor(joystick):
                self.needs_redraw = True
            if z_button and not self.last_z:
                self._flip_pattern(self.cursor_x, self.cursor_y)
                self.moves += 1
                self.needs_redraw = True
                if self._is_solved():
                    score = max(10, 1000 - self.moves * 20)
                    set_game_over_score(score, won=True)
                    return False
            self.last_z = z_button
            if self.needs_redraw:
                self._draw()
                self.needs_redraw = False
            return True

        return step


class ReactionGridGame(GridCursorGame):
    """Hit lit pads quickly, but leave red decoy pads alone."""

    FRAME_MS = 35
    GRID_W = 4
    GRID_H = 4
    CELL = 12
    ORIGIN_X = 8
    ORIGIN_Y = 4
    MAX_STRIKES = 3
    TARGET_COUNT = GRID_W * GRID_H

    def __init__(self):
        self.reset()

    def reset(self):
        self.cursor_x = 0
        self.cursor_y = 0
        self.last_move = ticks_ms()
        self.last_z = False
        self.score = 0
        self.strikes = 0
        self.target = -1
        self.target_is_decoy = False
        self.deadline = ticks_ms()
        self._spawn_target()
        self.needs_redraw = True

    def _spawn_target(self):
        old_target = self.target
        if old_target < 0:
            self.target = random.randint(0, self.TARGET_COUNT - 1)
        else:
            target = random.randint(0, self.TARGET_COUNT - 2)
            self.target = target + (target >= old_target)
        self.target_is_decoy = self.score >= 3 and random.randint(0, 5) == 0
        timeout = max(400, 1150 - self.score * 28)
        self.deadline = ticks_add(ticks_ms(), timeout)

    def _selected_index(self):
        return self.cursor_y * self.GRID_W + self.cursor_x

    def _add_strike(self):
        self.strikes += 1
        if self.strikes >= self.MAX_STRIKES:
            set_game_over_score(self.score)
            return False
        return True

    def _draw(self):
        display.clear()
        for index in range(self.GRID_W * self.GRID_H):
            x = index % self.GRID_W
            y = index // self.GRID_W
            px = self.ORIGIN_X + x * self.CELL
            py = self.ORIGIN_Y + y * self.CELL
            color = (22, 34, 50)
            if index == self.target:
                if self.target_is_decoy:
                    color = (255, 35, 25)
                else:
                    color = (30, 240, 100)
            draw_rectangle(px, py, px + 9, py + 9, *color)
        px = self.ORIGIN_X + self.cursor_x * self.CELL
        py = self.ORIGIN_Y + self.cursor_y * self.CELL
        draw_rect_outline(px - 1, py - 1, px + 10, py + 10, 255, 255, 255)
        for strike in range(self.strikes):
            display.set_pixel(WIDTH - strike * 3 - 2, 1, 255, 0, 0)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        begin_game(0)
        self.reset()
        self._draw()
        self.needs_redraw = False

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            if self._move_cursor(joystick):
                self.needs_redraw = True
            if z_button and not self.last_z:
                hit_target = self._selected_index() == self.target
                if hit_target and not self.target_is_decoy:
                    self.score += 1
                    self._spawn_target()
                    self.needs_redraw = True
                elif not self._add_strike():
                    return False
                else:
                    self.needs_redraw = True
            self.last_z = z_button
            if ticks_diff(ticks_ms(), self.deadline) >= 0:
                if not self.target_is_decoy and not self._add_strike():
                    return False
                self._spawn_target()
                self.needs_redraw = True
            if self.needs_redraw:
                self._draw()
                self.needs_redraw = False
            return True

        return step


class PicrossGame(GridCursorGame):
    """Solve compact nonograms from row and column run clues."""

    FRAME_MS = 40
    GRID_W = 5
    GRID_H = 5
    CELL = 8
    ORIGIN_X = 22
    ORIGIN_Y = 16
    PUZZLES = (
        (
            ("01110", "10001", "10101", "10001", "01110"),
            ("3", "11", "111", "11", "3"),
            ("3", "11", "111", "11", "3"),
        ),
        (
            ("00100", "01110", "11111", "01110", "00100"),
            ("1", "3", "5", "3", "1"),
            ("1", "3", "5", "3", "1"),
        ),
        (
            ("10001", "01010", "00100", "01010", "10001"),
            ("11", "11", "1", "11", "11"),
            ("11", "11", "1", "11", "11"),
        ),
        (
            ("11011", "11011", "00000", "10001", "01110"),
            ("22", "22", "0", "11", "3"),
            ("21", "21", "1", "21", "21"),
        ),
        (
            ("10101", "11111", "01110", "00100", "00100"),
            ("111", "5", "3", "1", "1"),
            ("2", "2", "5", "2", "2"),
        ),
    )

    def __init__(self):
        self.reset()

    def reset(self):
        self.pattern, self.row_clues, self.column_clues = random.choice(self.PUZZLES)
        self.grid = [0] * (self.GRID_W * self.GRID_H)
        self.cursor_x = 0
        self.cursor_y = 0
        self.last_move = ticks_ms()
        self.last_z = False
        self.moves = 0
        self.needs_redraw = True

    def _index(self, x, y):
        return y * self.GRID_W + x

    def _matches_pattern(self):
        for y in range(self.GRID_H):
            for x in range(self.GRID_W):
                filled = self.grid[self._index(x, y)] == 1
                if filled != (self.pattern[y][x] == "1"):
                    return False
        return True

    def _draw_clues(self):
        for y, clue in enumerate(self.row_clues):
            x = self.ORIGIN_X - len(clue) * 6 - 2
            py = self.ORIGIN_Y + y * self.CELL + 1
            draw_text_small(x, py, clue, 120, 180, 220)
        for x, clue in enumerate(self.column_clues):
            px = self.ORIGIN_X + x * self.CELL + 1
            py = self.ORIGIN_Y - len(clue) * 5
            for digit in clue:
                draw_text_small(px, py, digit, 120, 180, 220)
                py += 5

    def _draw(self):
        display.clear()
        self._draw_clues()
        for y in range(self.GRID_H):
            for x in range(self.GRID_W):
                px = self.ORIGIN_X + x * self.CELL
                py = self.ORIGIN_Y + y * self.CELL
                state = self.grid[self._index(x, y)]
                color = (18, 30, 42)
                if state == 1:
                    color = (40, 210, 255)
                draw_rectangle(px, py, px + 6, py + 6, *color)
                if state == 2:
                    display.set_pixel(px + 3, py + 3, 100, 120, 135)
        px = self.ORIGIN_X + self.cursor_x * self.CELL
        py = self.ORIGIN_Y + self.cursor_y * self.CELL
        draw_rect_outline(px - 1, py - 1, px + 7, py + 7, 255, 255, 255)
        display_score_and_time(self.moves)

    def _build_step(self, joystick):
        begin_game(0)
        self.reset()
        self._draw()
        self.needs_redraw = False

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            if self._move_cursor(joystick):
                self.needs_redraw = True
            if z_button and not self.last_z:
                index = self._index(self.cursor_x, self.cursor_y)
                self.grid[index] = (self.grid[index] + 1) % 3
                self.moves += 1
                self.needs_redraw = True
                if self._matches_pattern():
                    score = max(10, 1200 - self.moves * 15)
                    set_game_over_score(score, won=True)
                    return False
            self.last_z = z_button
            if self.needs_redraw:
                self._draw()
                self.needs_redraw = False
            return True

        return step


class SlalomGame(FrameLoopGame):
    """Carve through downhill gates; hold Z to tuck and accelerate."""

    FRAME_MS = 35
    PLAYER_Y = 47
    PLAYER_HALF_WIDTH = 2
    MAX_GATES = 5
    MAX_SNOW = 24
    MAX_GATE_SHIFT = 14

    def __init__(self):
        self.reset()

    def reset(self):
        self.x = WIDTH / 2.0
        self.velocity_x = 0.0
        self.score = 0
        self.gates = []
        self.snow = []
        for _unused in range(self.MAX_SNOW):
            self.snow.append(
                [
                    random.randint(0, WIDTH - 1),
                    random.randint(0, PLAY_HEIGHT - 1),
                    random.randint(1, 3),
                ]
            )
        self._spawn_gate(-5.0)

    def _gate_gap(self):
        return max(10, 20 - self.score // 4)

    def _spawn_gate(self, y):
        gap = self._gate_gap()
        margin = gap // 2 + 5
        min_center = margin
        max_center = WIDTH - margin - 1
        if self.gates:
            previous_center = self.gates[-1][1]
            min_center = max(min_center, previous_center - self.MAX_GATE_SHIFT)
            max_center = min(max_center, previous_center + self.MAX_GATE_SHIFT)
        center = random.randint(min_center, max_center)
        self.gates.append([float(y), center, gap, False])

    def _inside_gate(self, gate):
        center = gate[1]
        half_gap = gate[2] // 2
        safe_left = center - half_gap + 1
        safe_right = center + half_gap - 1
        return (
            self.x - self.PLAYER_HALF_WIDTH >= safe_left
            and self.x + self.PLAYER_HALF_WIDTH <= safe_right
        )

    def _steer(self, joystick, tucked):
        direction = joystick.read_direction(
            [JOYSTICK_LEFT, JOYSTICK_RIGHT],
            debounce=False,
        )
        acceleration = 0.28 if tucked else 0.52
        if direction == JOYSTICK_LEFT:
            self.velocity_x -= acceleration
        elif direction == JOYSTICK_RIGHT:
            self.velocity_x += acceleration
        else:
            self.velocity_x *= 0.82
        self.velocity_x = clamp(self.velocity_x, -3.2, 3.2)
        self.x += self.velocity_x
        if self.x < self.PLAYER_HALF_WIDTH:
            self.x = float(self.PLAYER_HALF_WIDTH)
            self.velocity_x = 0.0
        elif self.x > WIDTH - self.PLAYER_HALF_WIDTH - 1:
            self.x = float(WIDTH - self.PLAYER_HALF_WIDTH - 1)
            self.velocity_x = 0.0

    def _advance_snow(self, speed):
        for flake in self.snow:
            flake[1] += speed * flake[2] * 0.55
            if flake[1] >= PLAY_HEIGHT:
                flake[0] = random.randint(0, WIDTH - 1)
                flake[1] -= PLAY_HEIGHT

    def _advance_gates(self, tucked):
        speed = 1.05 + min(1.45, self.score * 0.05)
        if tucked:
            speed += 0.75
        self._advance_snow(speed)

        keep_index = 0
        for gate in self.gates:
            previous_y = gate[0]
            gate[0] += speed
            if not gate[3] and previous_y < self.PLAYER_Y <= gate[0]:
                if not self._inside_gate(gate):
                    set_game_over_score(self.score)
                    return False
                gate[3] = True
                self.score += 2 if tucked else 1
            if gate[0] < PLAY_HEIGHT + 6:
                self.gates[keep_index] = gate
                keep_index += 1
        del self.gates[keep_index:]
        if len(self.gates) < self.MAX_GATES and (
            not self.gates or self.gates[-1][0] >= 12
        ):
            self._spawn_gate(-5.0)
        return True

    def _draw(self, tucked):
        display.clear()
        for x, y, _flake_speed in self.snow:
            display.set_pixel(int(x), int(y), 65, 80, 100)
        for y, center, gap, _passed in self.gates:
            pole_y = int(y)
            left = center - gap // 2
            right = center + gap // 2
            draw_play_rect(left, pole_y, 2, 6, 40, 120, 255)
            draw_play_rect(right - 1, pole_y, 2, 6, 255, 55, 45)
            draw_play_rect(left + 2, pole_y, 3, 2, 40, 120, 255)
            draw_play_rect(right - 4, pole_y, 3, 2, 255, 55, 45)

        player_x = int(self.x)
        color = (255, 210, 30) if not tucked else (255, 90, 25)
        draw_play_rect(player_x - 1, self.PLAYER_Y, 3, 4, *color)
        draw_line(
            player_x - 3, self.PLAYER_Y + 4, player_x, self.PLAYER_Y + 3, 220, 240, 255
        )
        draw_line(
            player_x, self.PLAYER_Y + 3, player_x + 3, self.PLAYER_Y + 4, 220, 240, 255
        )
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        begin_game(0)
        self.reset()
        self._draw(False)

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            self._steer(joystick, z_button)
            if not self._advance_gates(z_button):
                return False
            self._draw(z_button)
            return True

        return step


class ConnectGame(FrameLoopGame):
    """Drop four counters in a row before the compact CPU opponent does."""

    FRAME_MS = 35
    COLS = 7
    ROWS = 6
    CELL = 8
    ORIGIN_X = 4
    ORIGIN_Y = 4
    PLAYER = 1
    CPU = 2

    def __init__(self):
        self.reset()

    def reset(self):
        self.grid = [0] * (self.COLS * self.ROWS)
        self.cursor = self.COLS // 2
        self.last_move = ticks_ms()
        self.last_z = False
        self.moves = 0

    def _index(self, x, y):
        return y * self.COLS + x

    def _drop(self, col, player):
        """Drop one counter and return its row, or ``None`` for a full column."""
        for y in range(self.ROWS - 1, -1, -1):
            index = self._index(col, y)
            if not self.grid[index]:
                self.grid[index] = player
                return y
        return None

    def _winner_from(self, x, y):
        player = self.grid[self._index(x, y)]
        if not player:
            return 0
        for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
            count = 1
            for sign in (-1, 1):
                nx, ny = x + sign * dx, y + sign * dy
                while (
                    0 <= nx < self.COLS
                    and 0 <= ny < self.ROWS
                    and self.grid[self._index(nx, ny)] == player
                ):
                    count += 1
                    nx += sign * dx
                    ny += sign * dy
            if count >= 4:
                return player
        return 0

    def _would_win(self, col, player):
        row = self._drop(col, player)
        if row is None:
            return False
        won = self._winner_from(col, row) == player
        self.grid[self._index(col, row)] = 0
        return won

    def _cpu_column(self):
        legal = [col for col in range(self.COLS) if not self.grid[self._index(col, 0)]]
        for player in (self.CPU, self.PLAYER):
            for col in legal:
                if self._would_win(col, player):
                    return col
        # Favor the center but keep the CPU's play varied.
        ordered = sorted(legal, key=lambda col: abs(col - self.COLS // 2))
        return ordered[random.randint(0, min(2, len(ordered) - 1))]

    def _draw(self):
        display.clear()
        draw_rectangle(2, 2, WIDTH - 3, PLAY_HEIGHT - 1, 20, 60, 150)
        for y in range(self.ROWS):
            for x in range(self.COLS):
                px = self.ORIGIN_X + x * self.CELL
                py = self.ORIGIN_Y + y * self.CELL
                piece = self.grid[self._index(x, y)]
                color = (8, 14, 35)
                if piece == self.PLAYER:
                    color = (255, 215, 35)
                elif piece == self.CPU:
                    color = (245, 60, 55)
                draw_rectangle(px, py, px + 5, py + 5, *color)
        px = self.ORIGIN_X + self.cursor * self.CELL
        draw_rect_outline(px - 1, self.ORIGIN_Y - 2, px + 6, PLAY_HEIGHT - 2, 255, 255, 255)
        display_score_and_time(self.moves)

    def _build_step(self, joystick):
        begin_game(0)
        self.reset()
        self._draw()

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            now = ticks_ms()
            direction = joystick.read_direction(
                [JOYSTICK_LEFT, JOYSTICK_RIGHT], debounce=False
            )
            if direction == JOYSTICK_LEFT and ticks_diff(now, self.last_move) >= 130:
                self.cursor = max(0, self.cursor - 1)
                self.last_move = now
            elif direction == JOYSTICK_RIGHT and ticks_diff(now, self.last_move) >= 130:
                self.cursor = min(self.COLS - 1, self.cursor + 1)
                self.last_move = now
            if z_button and not self.last_z:
                row = self._drop(self.cursor, self.PLAYER)
                if row is not None:
                    self.moves += 1
                    if self._winner_from(self.cursor, row) == self.PLAYER:
                        set_game_over_score(100 + max(0, 42 - self.moves), won=True)
                        return False
                    cpu_col = self._cpu_column()
                    cpu_row = self._drop(cpu_col, self.CPU)
                    if self._winner_from(cpu_col, cpu_row) == self.CPU:
                        set_game_over_score(0)
                        return False
                    if all(self.grid[self._index(col, 0)] for col in range(self.COLS)):
                        set_game_over_score(25, won=True)
                        return False
            self.last_z = z_button
            self._draw()
            return True

        return step


class FloodGame(FrameLoopGame):
    """Flood the seven-by-seven colour board in as few moves as possible."""

    FRAME_MS = 35
    GRID_W = 7
    GRID_H = 7
    CELL = 7
    ORIGIN_X = 8
    ORIGIN_Y = 2
    PALETTE = (
        (245, 65, 60),
        (55, 210, 105),
        (55, 130, 255),
        (250, 215, 45),
        (215, 75, 225),
    )

    def __init__(self):
        self.reset()

    def reset(self):
        self.grid = [random.randint(0, len(self.PALETTE) - 1) for _ in range(self.GRID_W * self.GRID_H)]
        while all(color == self.grid[0] for color in self.grid):
            self.grid = [random.randint(0, len(self.PALETTE) - 1) for _ in range(self.GRID_W * self.GRID_H)]
        self.selected_color = (self.grid[0] + 1) % len(self.PALETTE)
        self.moves = 0
        self.last_move = ticks_ms()
        self.last_z = False

    def _index(self, x, y):
        return y * self.GRID_W + x

    def _flood(self, color):
        old_color = self.grid[0]
        if color == old_color:
            return 0
        pending = [0]
        changed = 0
        self.grid[0] = color
        while pending:
            index = pending.pop()
            changed += 1
            x, y = index % self.GRID_W, index // self.GRID_W
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < self.GRID_W and 0 <= ny < self.GRID_H:
                    neighbor = self._index(nx, ny)
                    if self.grid[neighbor] == old_color:
                        self.grid[neighbor] = color
                        pending.append(neighbor)
        return changed

    def _is_solved(self):
        return all(color == self.grid[0] for color in self.grid)

    def _draw(self):
        display.clear()
        for y in range(self.GRID_H):
            for x in range(self.GRID_W):
                px = self.ORIGIN_X + x * self.CELL
                py = self.ORIGIN_Y + y * self.CELL
                draw_rectangle(px, py, px + 6, py + 6, *self.PALETTE[self.grid[self._index(x, y)]])
        palette_y = PLAY_HEIGHT - 5
        for index, color in enumerate(self.PALETTE):
            px = 2 + index * 12
            draw_rectangle(px, palette_y, px + 7, palette_y + 3, *color)
            if index == self.selected_color:
                draw_rect_outline(px - 1, palette_y - 1, px + 8, palette_y + 4, 255, 255, 255)
        display_score_and_time(self.moves)

    def _build_step(self, joystick):
        begin_game(0)
        self.reset()
        self._draw()

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            now = ticks_ms()
            direction = joystick.read_direction(
                [JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_UP, JOYSTICK_DOWN],
                debounce=False,
            )
            if ticks_diff(now, self.last_move) >= 130:
                if direction in (JOYSTICK_LEFT, JOYSTICK_UP):
                    self.selected_color = (self.selected_color - 1) % len(self.PALETTE)
                    self.last_move = now
                elif direction in (JOYSTICK_RIGHT, JOYSTICK_DOWN):
                    self.selected_color = (self.selected_color + 1) % len(self.PALETTE)
                    self.last_move = now
            if z_button and not self.last_z and self._flood(self.selected_color):
                self.moves += 1
                if self._is_solved():
                    set_game_over_score(max(10, 800 - self.moves * 30), won=True)
                    return False
            self.last_z = z_button
            self._draw()
            return True

        return step


class WiresGame(GridCursorGame):
    """Rotate cable tiles until every tile belongs to one connected circuit."""

    FRAME_MS = 40
    GRID_W = 5
    GRID_H = 5
    CELL = 10
    ORIGIN_X = 7
    ORIGIN_Y = 4
    UP = 1
    RIGHT = 2
    DOWN = 4
    LEFT = 8

    # A snake-shaped spanning tree.  Rotating its tiles creates a compact,
    # always-solvable circuit puzzle without storing a full level in RAM.
    SOLUTION = (
        RIGHT,
        LEFT | RIGHT,
        LEFT | RIGHT,
        LEFT | RIGHT,
        LEFT | DOWN,
        RIGHT | DOWN,
        LEFT | RIGHT,
        LEFT | RIGHT,
        LEFT | RIGHT,
        UP | LEFT,
        UP | RIGHT,
        LEFT | RIGHT,
        LEFT | RIGHT,
        LEFT | RIGHT,
        LEFT | DOWN,
        RIGHT | DOWN,
        LEFT | RIGHT,
        LEFT | RIGHT,
        LEFT | RIGHT,
        UP | LEFT,
        UP | RIGHT,
        LEFT | RIGHT,
        LEFT | RIGHT,
        LEFT | RIGHT,
        LEFT,
    )

    def __init__(self):
        self.reset()

    def reset(self):
        self.grid = list(self.SOLUTION)
        for index in range(len(self.grid)):
            turns = random.randint(1, 3)
            for _unused in range(turns):
                self.grid[index] = self._rotate(self.grid[index])
        self.cursor_x = self.GRID_W // 2
        self.cursor_y = self.GRID_H // 2
        self.last_move = ticks_ms()
        self.last_z = False
        self.moves = 0
        self.needs_redraw = True
        if self._is_solved():
            self.grid[0] = self._rotate(self.grid[0])

    @classmethod
    def _rotate(cls, tile):
        """Turn a tile clockwise, keeping straight sections compact."""
        turned = 0
        if tile & cls.UP:
            turned |= cls.RIGHT
        if tile & cls.RIGHT:
            turned |= cls.DOWN
        if tile & cls.DOWN:
            turned |= cls.LEFT
        if tile & cls.LEFT:
            turned |= cls.UP
        return turned

    def _index(self, x, y):
        return y * self.GRID_W + x

    def _is_solved(self):
        """Check that cable ends match and every tile is reachable from tile 0."""
        directions = (
            (self.UP, 0, -1, self.DOWN),
            (self.RIGHT, 1, 0, self.LEFT),
            (self.DOWN, 0, 1, self.UP),
            (self.LEFT, -1, 0, self.RIGHT),
        )
        for y in range(self.GRID_H):
            for x in range(self.GRID_W):
                tile = self.grid[self._index(x, y)]
                for bit, dx, dy, opposite in directions:
                    if not (tile & bit):
                        continue
                    nx, ny = x + dx, y + dy
                    if not (0 <= nx < self.GRID_W and 0 <= ny < self.GRID_H):
                        return False
                    if not (self.grid[self._index(nx, ny)] & opposite):
                        return False
        seen = [False] * len(self.grid)
        pending = [0]
        seen[0] = True
        while pending:
            index = pending.pop()
            x, y = index % self.GRID_W, index // self.GRID_W
            tile = self.grid[index]
            for bit, dx, dy, opposite in directions:
                nx, ny = x + dx, y + dy
                if (
                    tile & bit
                    and 0 <= nx < self.GRID_W
                    and 0 <= ny < self.GRID_H
                    and self.grid[self._index(nx, ny)] & opposite
                ):
                    neighbor = self._index(nx, ny)
                    if not seen[neighbor]:
                        seen[neighbor] = True
                        pending.append(neighbor)
        return all(seen)

    def _draw_tile(self, x, y, tile, lit):
        px = self.ORIGIN_X + x * self.CELL
        py = self.ORIGIN_Y + y * self.CELL
        draw_rectangle(px, py, px + 7, py + 7, 12, 22, 42)
        color = (60, 235, 150) if lit else (70, 125, 180)
        cx, cy = px + 3, py + 3
        display.set_pixel(cx, cy, *color)
        if tile & self.UP:
            draw_line(cx, cy, cx, py, *color)
        if tile & self.RIGHT:
            draw_line(cx, cy, px + 7, cy, *color)
        if tile & self.DOWN:
            draw_line(cx, cy, cx, py + 7, *color)
        if tile & self.LEFT:
            draw_line(cx, cy, px, cy, *color)

    def _draw(self):
        display.clear()
        solved = self._is_solved()
        for y in range(self.GRID_H):
            for x in range(self.GRID_W):
                self._draw_tile(x, y, self.grid[self._index(x, y)], solved)
        px = self.ORIGIN_X + self.cursor_x * self.CELL
        py = self.ORIGIN_Y + self.cursor_y * self.CELL
        draw_rect_outline(px - 1, py - 1, px + 8, py + 8, 255, 255, 255)
        display_score_and_time(self.moves)

    def _build_step(self, joystick):
        begin_game(0)
        self.reset()
        self._draw()
        self.needs_redraw = False

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            if self._move_cursor(joystick):
                self.needs_redraw = True
            if z_button and not self.last_z:
                index = self._index(self.cursor_x, self.cursor_y)
                self.grid[index] = self._rotate(self.grid[index])
                self.moves += 1
                self.needs_redraw = True
                if self._is_solved():
                    set_game_over_score(max(10, 1000 - self.moves * 12), won=True)
                    return False
            self.last_z = z_button
            if self.needs_redraw:
                self._draw()
                self.needs_redraw = False
            return True

        return step


class TiltGame(GridCursorGame):
    """Slide across an ice board and collect every crystal in a single run."""

    FRAME_MS = 40
    GRID_W = 7
    GRID_H = 7
    CELL = 7
    ORIGIN_X = 8
    ORIGIN_Y = 2
    WALL = "#"
    ICE = "."
    PLAYER = "P"
    CRYSTAL = "*"
    LEVEL = (
        "#######",
        "#P.*..#",
        "#.###.#",
        "#...#*#",
        "#.###.#",
        "#*....#",
        "#######",
    )

    def __init__(self):
        self.reset()

    def reset(self):
        self.board = []
        self.player_x = 1
        self.player_y = 1
        self.crystals = 0
        for y, row in enumerate(self.LEVEL):
            cells = []
            for x, cell in enumerate(row):
                if cell == self.PLAYER:
                    self.player_x, self.player_y = x, y
                    cells.append(self.ICE)
                else:
                    cells.append(cell)
                    if cell == self.CRYSTAL:
                        self.crystals += 1
            self.board.append(cells)
        self.moves = 0
        self.last_move = ticks_ms()
        self.last_z = False
        self.needs_redraw = True

    def _slide(self, dx, dy):
        """Move until a wall, collecting every crystal passed on the way."""
        x, y = self.player_x, self.player_y
        moved = False
        while self.board[y + dy][x + dx] != self.WALL:
            x += dx
            y += dy
            moved = True
            if self.board[y][x] == self.CRYSTAL:
                self.board[y][x] = self.ICE
                self.crystals -= 1
        if moved:
            self.player_x, self.player_y = x, y
            self.moves += 1
        return moved

    def _move_on_ice(self, joystick):
        now = ticks_ms()
        if ticks_diff(now, self.last_move) < self.MOVE_DELAY_MS:
            return False
        direction = joystick.read_direction(
            [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
        )
        dx, dy = direction_to_delta(direction)
        if not (dx or dy):
            return False
        self.last_move = now
        return self._slide(dx, dy)

    def _draw(self):
        display.clear()
        for y in range(self.GRID_H):
            for x in range(self.GRID_W):
                px = self.ORIGIN_X + x * self.CELL
                py = self.ORIGIN_Y + y * self.CELL
                cell = self.board[y][x]
                color = (25, 42, 90) if cell == self.WALL else (32, 110, 175)
                draw_rectangle(px, py, px + 5, py + 5, *color)
                if cell == self.CRYSTAL:
                    display.set_pixel(px + 2, py + 1, 100, 255, 245)
                    display.set_pixel(px + 1, py + 3, 100, 255, 245)
                    display.set_pixel(px + 3, py + 3, 100, 255, 245)
                    display.set_pixel(px + 2, py + 5, 100, 255, 245)
        px = self.ORIGIN_X + self.player_x * self.CELL
        py = self.ORIGIN_Y + self.player_y * self.CELL
        draw_rectangle(px + 1, py + 1, px + 4, py + 4, 255, 245, 110)
        draw_text_small(1, 1, "G" + str(self.crystals), 210, 245, 255)
        display_score_and_time(self.moves)

    def _build_step(self, joystick):
        begin_game(0)
        self.reset()
        self._draw()
        self.needs_redraw = False

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            if z_button and not self.last_z:
                self.reset()
                self.needs_redraw = True
            elif self._move_on_ice(joystick):
                self.needs_redraw = True
                if not self.crystals:
                    set_game_over_score(max(10, 700 - self.moves * 25), won=True)
                    return False
            self.last_z = z_button
            if self.needs_redraw:
                self._draw()
                self.needs_redraw = False
            return True

        return step


class BeatGame(FrameLoopGame):
    """Rhythm game: tap the matching direction as notes cross the beat line."""

    FRAME_MS = 30
    HIT_Y = 47
    HIT_WINDOW = 4
    DIRECTIONS = (
        JOYSTICK_LEFT,
        JOYSTICK_DOWN,
        JOYSTICK_UP,
        JOYSTICK_RIGHT,
    )
    PATTERN = (0, 2, 1, 3, 0, 1, 2, 3, 3, 1, 0, 2, 0, 3, 2, 1)
    LANE_X = (8, 23, 38, 53)

    def __init__(self):
        self.reset()

    def reset(self):
        self.notes = []
        self.frame = 0
        self.next_note = 0
        self.spawned = 0
        self.score = 0
        self.streak = 0
        self.misses = 0
        self.last_direction = None

    def _spawn_note(self):
        lane = self.PATTERN[self.next_note % len(self.PATTERN)]
        self.next_note += 1
        self.spawned += 1
        self.notes.append([lane, 2])

    def _judge(self, direction):
        """Consume the closest matching note inside the hit window."""
        if direction not in self.DIRECTIONS:
            return False
        lane = self.DIRECTIONS.index(direction)
        best_index = -1
        best_distance = self.HIT_WINDOW + 1
        for index, note in enumerate(self.notes):
            distance = abs(note[1] - self.HIT_Y)
            if note[0] == lane and distance < best_distance:
                best_index = index
                best_distance = distance
        if best_index < 0 or best_distance > self.HIT_WINDOW:
            self.streak = 0
            return False
        self.notes.pop(best_index)
        self.streak += 1
        self.score += max(10, 50 - best_distance * 8) + min(50, self.streak * 2)
        play_sound("score", 2)
        return True

    def _advance_notes(self):
        """Move notes and count any that passed the judgement line."""
        if self.frame % 2:
            return
        kept = []
        for note in self.notes:
            note[1] += 2
            if note[1] <= self.HIT_Y + self.HIT_WINDOW:
                kept.append(note)
            else:
                self.misses += 1
                self.streak = 0
        self.notes = kept

    def _draw(self):
        display.clear()
        for lane, x in enumerate(self.LANE_X):
            color = ((80, 130, 255), (255, 90, 160), (80, 220, 130), (255, 190, 55))[lane]
            draw_line(x, 1, x, self.HIT_Y + 4, 30, 40, 65)
            draw_rect_outline(x - 4, self.HIT_Y - 3, x + 4, self.HIT_Y + 3, *color)
        for lane, y in self.notes:
            x = self.LANE_X[lane]
            color = ((80, 130, 255), (255, 90, 160), (80, 220, 130), (255, 190, 55))[lane]
            draw_rectangle(x - 3, y - 1, x + 3, y + 1, *color)
        draw_text_small(1, 1, "X" + str(self.streak), 220, 220, 255)
        draw_text_small(45, 1, str(self.misses), 255, 100, 100)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        begin_game(0)
        self.reset()

        def step():
            c_button, _z_button = joystick.read_buttons()
            if c_button:
                return False
            direction = joystick.read_direction(self.DIRECTIONS, debounce=False)
            if direction is not None and direction != self.last_direction:
                self._judge(direction)
            self.last_direction = direction
            self.frame += 1
            if self.spawned < 24 and self.frame % 18 == 1:
                self._spawn_note()
            self._advance_notes()
            if self.misses >= 6:
                set_game_over_score(self.score)
                return False
            if self.spawned >= 24 and not self.notes:
                set_game_over_score(self.score + self.streak * 10, won=True)
                return False
            self._draw()
            return True

        return step


class SonarGame(FrameLoopGame):
    """Explore a dark ruin with short sonar pulses and recover its beacons."""

    FRAME_MS = 40
    CELL = 6
    ORIGIN_X = 5
    ORIGIN_Y = 3
    LEVEL = (
        "#########",
        "#P..#..C#",
        "#.#...#.#",
        "#..C#...#",
        "###...#.#",
        "#C....#E#",
        "#########",
    )

    def __init__(self):
        self.reset()

    def reset(self):
        self.player_x = 1
        self.player_y = 1
        self.exit_x = 7
        self.exit_y = 5
        self.beacons = []
        for y, row in enumerate(self.LEVEL):
            for x, cell in enumerate(row):
                if cell == "P":
                    self.player_x, self.player_y = x, y
                elif cell == "C":
                    self.beacons.append([x, y])
                elif cell == "E":
                    self.exit_x, self.exit_y = x, y
        self.visited = [False] * (len(self.LEVEL) * len(self.LEVEL[0]))
        self._visit(self.player_x, self.player_y)
        self.energy = 8
        self.pulse = 5
        self.moves = 0
        self.last_move = ticks_ms()
        self.last_z = False

    def _index(self, x, y):
        return y * len(self.LEVEL[0]) + x

    def _visit(self, x, y):
        self.visited[self._index(x, y)] = True

    def _move(self, dx, dy):
        nx, ny = self.player_x + dx, self.player_y + dy
        if self.LEVEL[ny][nx] == "#":
            return False
        self.player_x, self.player_y = nx, ny
        self._visit(nx, ny)
        self.moves += 1
        self.pulse = max(0, self.pulse - 1)
        for beacon in self.beacons:
            if beacon[0] == nx and beacon[1] == ny:
                self.beacons.remove(beacon)
                play_sound("score", 3)
                break
        return True

    def _emit_pulse(self):
        if self.energy <= 0:
            return False
        self.energy -= 1
        self.pulse = 6
        play_sound("select", 1)
        return True

    def _visible(self, x, y):
        distance = abs(x - self.player_x) + abs(y - self.player_y)
        return distance <= self.pulse or self.visited[self._index(x, y)]

    def _draw(self):
        display.clear()
        for y, row in enumerate(self.LEVEL):
            for x, cell in enumerate(row):
                if not self._visible(x, y):
                    continue
                px = self.ORIGIN_X + x * self.CELL
                py = self.ORIGIN_Y + y * self.CELL
                if cell == "#":
                    color = (25, 75, 105) if self.pulse else (12, 25, 38)
                    draw_rectangle(px, py, px + 4, py + 4, *color)
                else:
                    display.set_pixel(px + 2, py + 2, 30, 75, 85)
        for x, y in self.beacons:
            if self._visible(x, y):
                px = self.ORIGIN_X + x * self.CELL
                py = self.ORIGIN_Y + y * self.CELL
                draw_rectangle(px + 1, py + 1, px + 3, py + 3, 80, 255, 230)
        if not self.beacons and self._visible(self.exit_x, self.exit_y):
            px = self.ORIGIN_X + self.exit_x * self.CELL
            py = self.ORIGIN_Y + self.exit_y * self.CELL
            draw_rect_outline(px, py, px + 4, py + 4, 255, 210, 70)
        px = self.ORIGIN_X + self.player_x * self.CELL
        py = self.ORIGIN_Y + self.player_y * self.CELL
        draw_rectangle(px + 1, py + 1, px + 3, py + 3, 255, 245, 150)
        draw_text_small(1, 1, "E" + str(self.energy), 120, 220, 255)
        display_score_and_time(self.moves)

    def _build_step(self, joystick):
        begin_game(0)
        self.reset()

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            now = ticks_ms()
            direction = joystick.read_direction(
                [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT],
                debounce=False,
            )
            if ticks_diff(now, self.last_move) >= 140:
                dx, dy = direction_to_delta(direction)
                if dx or dy:
                    self._move(dx, dy)
                    self.last_move = now
            if z_button and not self.last_z:
                self._emit_pulse()
            self.last_z = z_button
            if (
                not self.beacons
                and self.player_x == self.exit_x
                and self.player_y == self.exit_y
            ):
                set_game_over_score(max(20, 900 - self.moves * 15 + self.energy * 25), won=True)
                return False
            self._draw()
            return True

        return step


class SignalGame(FrameLoopGame):
    """Operate a busy intersection: switch the lights before traffic collides."""

    FRAME_MS = 35
    NS_GREEN = 0
    EW_GREEN = 1
    STOP_LINE = 20
    INTERSECTION_START = 23
    INTERSECTION_END = 35
    EXIT_AT = 44

    def __init__(self):
        self.reset()

    def reset(self):
        self.phase = self.NS_GREEN
        self.vehicles = []
        self.frame = 0
        self.spawn_index = 0
        self.score = 0
        self.crashed = False
        self.last_z = False

    def _is_green(self, side):
        return (side % 2 == 0) == (self.phase == self.NS_GREEN)

    def _spawn_vehicle(self, side=None):
        if side is None:
            side = (0, 1, 2, 3, 1, 0, 3, 2)[self.spawn_index % 8]
            self.spawn_index += 1
        if any(vehicle[0] == side and vehicle[1] < 8 for vehicle in self.vehicles):
            return False
        self.vehicles.append([side, 0])
        return True

    def _advance_traffic(self):
        for vehicle in self.vehicles:
            if vehicle[1] == self.STOP_LINE and not self._is_green(vehicle[0]):
                continue
            vehicle[1] += 1
        horizontal = False
        vertical = False
        kept = []
        for side, progress in self.vehicles:
            if progress > self.EXIT_AT:
                self.score += 1
                continue
            kept.append([side, progress])
            if self.INTERSECTION_START <= progress <= self.INTERSECTION_END:
                if side % 2:
                    horizontal = True
                else:
                    vertical = True
        self.vehicles = kept
        self.crashed = horizontal and vertical
        return not self.crashed

    def _vehicle_position(self, side, progress):
        if side == 0:
            return 27, progress - 4
        if side == 1:
            return 67 - progress, 32
        if side == 2:
            return 34, 62 - progress
        return progress - 4, 25

    def _draw(self):
        display.clear()
        draw_rectangle(24, 0, 39, PLAY_HEIGHT - 1, 35, 38, 45)
        draw_rectangle(0, 21, WIDTH - 1, 37, 35, 38, 45)
        draw_line(31, 0, 31, 20, 220, 190, 70)
        draw_line(31, 38, 31, PLAY_HEIGHT - 1, 220, 190, 70)
        draw_line(0, 29, 23, 29, 220, 190, 70)
        draw_line(40, 29, WIDTH - 1, 29, 220, 190, 70)
        ns_color = (60, 240, 110) if self.phase == self.NS_GREEN else (245, 65, 55)
        ew_color = (60, 240, 110) if self.phase == self.EW_GREEN else (245, 65, 55)
        draw_rectangle(21, 17, 23, 19, *ns_color)
        draw_rectangle(40, 38, 42, 40, *ns_color)
        draw_rectangle(42, 18, 44, 20, *ew_color)
        draw_rectangle(19, 38, 21, 40, *ew_color)
        for side, progress in self.vehicles:
            x, y = self._vehicle_position(side, progress)
            color = ((80, 180, 255), (255, 100, 80), (100, 230, 135), (240, 190, 65))[side]
            draw_rectangle(x - 1, y - 1, x + 2, y + 2, *color)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        begin_game(0)
        self.reset()

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            if z_button and not self.last_z:
                self.phase = self.EW_GREEN if self.phase == self.NS_GREEN else self.NS_GREEN
                play_sound("select", self.phase)
            self.last_z = z_button
            self.frame += 1
            if self.frame % max(18, 42 - self.score) == 1:
                self._spawn_vehicle()
            if self.frame % 2 == 0 and not self._advance_traffic():
                set_game_over_score(self.score * 25)
                return False
            self._draw()
            return True

        return step
