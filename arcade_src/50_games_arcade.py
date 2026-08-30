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
        draw_rectangle(
            self.bar_x,
            self.bar_y,
            self.bar_x + self.bar_w - 1,
            self.bar_y + self.LAYER_H - 1,
            r,
            g,
            b,
        )
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
        if (
            right - ox < self.bar_w
            and (self.bar_w - (right - ox)) <= self.OVERLAP_GRACE
        ):
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
            show_center_message(
                ("YOU", "WON"),
                start_y=18,
                line_height=15,
                r=0,
                g=255,
                b=0,
                score=global_score,
                delay_ms=900,
            )

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))
        if self.won:
            await show_center_message_async(
                ("YOU", "WON"),
                start_y=18,
                line_height=15,
                r=0,
                g=255,
                b=0,
                score=global_score,
                delay_ms=900,
            )


class FroggerGame(FrameLoopGame):
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
        d = joystick.read_direction(
            [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
        )
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
        draw_rectangle(
            self.player_x,
            self.player_y,
            self.player_x + self.PLAYER_W - 1,
            self.player_y + self.PLAYER_H - 1,
            0,
            255,
            80,
        )
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
class CatchGame(FrameLoopGame):
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
            caught = (
                y >= by - 1 and self.basket_x <= x <= self.basket_x + self.basket_w - 1
            )
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
        draw_rectangle(
            self.basket_x,
            PLAY_HEIGHT - 2,
            self.basket_x + self.basket_w - 1,
            PLAY_HEIGHT - 1,
            0,
            180,
            255,
        )
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


class MinesGame(GridCursorGame):
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
        self.revealed = [
            [False for _x in range(self.GRID_W)] for _y in range(self.GRID_H)
        ]
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
                if (
                    0 <= xx < self.GRID_W
                    and 0 <= yy < self.GRID_H
                    and self.mines[yy][xx]
                ):
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
                    if (
                        0 <= xx < self.GRID_W
                        and 0 <= yy < self.GRID_H
                        and not self.revealed[yy][xx]
                    ):
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
                            draw_text_small(
                                px + 1, py, str(n), 40 + n * 25, 220, 255 - n * 18
                            )
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


class ClimberGame(FrameLoopGame):
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
            self.platforms.append(
                [random.randint(2, WIDTH - 16), PLAY_HEIGHT - i * 8, 14]
            )

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
            if (
                py + 3 >= p[1]
                and py + 3 <= p[1] + 2
                and px + 3 >= p[0]
                and px <= p[0] + p[2]
            ):
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
            self.platforms.append(
                [random.randint(1, WIDTH - w - 1), top - random.randint(7, 10), w]
            )

    def _draw(self):
        display.clear()
        for p in self.platforms:
            hue = (120 + p[1] * 3) % 360
            r, g, b = hsb_to_rgb(hue, 1, 1)
            draw_rectangle(p[0], int(p[1]), p[0] + p[2], int(p[1]) + 1, r, g, b)
        draw_rectangle(
            int(self.x), int(self.y), int(self.x) + 3, int(self.y) + 3, 255, 255, 255
        )
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


class ArenaGame(FrameLoopGame):
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
        self.sparks = []  # [x, y, dx, dy, ttl]
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
        d = joystick.read_direction(
            [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
        )
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
        draw_rect_outline(
            0, 0, WIDTH - 1, PLAY_HEIGHT - 1, border_r, border_g, border_b
        )
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


class DefuseGame(FrameLoopGame):
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
    WIRE_COLORS = (
        (255, 0, 0),
        (0, 180, 255),
        (255, 230, 0),
        (0, 255, 70),
        (255, 0, 210),
    )

    def __init__(self):
        self.reset()

    def reset(self):
        self.cursor = 0
        self.score = 0
        self.round = 1
        self.last_move = ticks_ms()
        self.last_z = False
        self.wrong_flash_until = 0
        self.wrong_strikes = 0  # strikes per bomb; 2nd wrong = game over
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
            self.score += max(
                1, (self.limit_ms - ticks_diff(ticks_ms(), self.started)) // 200
            )
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
            draw_rectangle(
                8 + i * 10,
                7,
                13 + i * 10,
                10,
                r // 3 if dim else r,
                g // 3 if dim else g,
                b // 3 if dim else b,
            )
            if i == self.cut_index:
                draw_rect_outline(7 + i * 10, 6, 14 + i * 10, 11, 255, 255, 255)
        wrong_flash = ticks_diff(now, self.wrong_flash_until) < 0
        for i, x in enumerate(self.WIRE_X):
            r, g, b = self.WIRE_COLORS[i]
            if self.cut[i]:
                draw_rectangle(x - 2, 18, x + 2, 46, 30, 30, 30)
                draw_line(x - 3, 31, x + 3, 26, 255, 255, 255)
            else:
                is_next = (
                    self.cut_index < len(self.sequence)
                    and self.sequence[self.cut_index] == i
                )
                if is_next and (now // 200) % 2 == 0:
                    draw_rectangle(
                        x - 1,
                        16,
                        x + 1,
                        49,
                        min(255, r + 80),
                        min(255, g + 80),
                        min(255, b + 80),
                    )
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


class BilliardsGame(FrameLoopGame):
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
        self.balls.append(
            self._ball(16, (self.TOP + self.BOTTOM) // 2, (245, 245, 245), 0)
        )
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
            (self.LEFT, self.TOP),
            (mid_x, self.TOP),
            (self.RIGHT, self.TOP),
            (self.LEFT, self.BOTTOM),
            (mid_x, self.BOTTOM),
            (self.RIGHT, self.BOTTOM),
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
        d = joystick.read_direction(
            [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT], debounce=False
        )
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
        draw_rect_outline(
            self.LEFT - 1, self.TOP - 1, self.RIGHT + 1, self.BOTTOM + 1, 130, 78, 32
        )
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


class GolfGame(FrameLoopGame):
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
        self.angle = -45  # degrees, full 360° allowed
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
            self.obstacles.append(
                [28, gap_y + 8, 2, max(4, PLAY_HEIGHT - gap_y - 13), 2]
            )
        else:
            gap_x = 20 + (seed % 22)
            self.obstacles.append([10, 27, max(4, gap_x - 10), 2, 2])
            self.obstacles.append([gap_x + 9, 27, max(4, WIDTH - gap_x - 15), 2, 2])
        n = min(6, 2 + self.hole // 2)
        for i in range(n):
            ox = 14 + i * 7 + ((seed + i * 13) % 5)
            oy = 4 + ((seed * (i + 1) * 7) % 42)
            kind = i % 3
            if kind == 0:  # tree: small square
                self.obstacles.append([ox, oy, 4, 4, 0])
            elif kind == 1:  # bunker: wide, short
                self.obstacles.append([ox - 1, oy, 6, 3, 1])
            else:  # wall: narrow, tall
                self.obstacles.append([ox, oy, 2, 8, 2])

    def _aim(self, joystick):
        d = joystick.read_direction(
            [JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_UP, JOYSTICK_DOWN]
        )
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
        return (
            abs(self.ball_x - self.hole_x) <= 2
            and abs(self.ball_y - self.hole_y) <= 2
            and self._ball_speed() < 0.6
        )

    def _draw(self):
        display.clear()
        # Fairway — solid green background
        draw_rectangle(1, 1, WIDTH - 2, PLAY_HEIGHT - 2, 18, 90, 28)
        # Border rough (darker)
        draw_rect_outline(0, 0, WIDTH - 1, PLAY_HEIGHT - 1, 10, 55, 16)
        # Obstacles
        for o in self.obstacles:
            if o[4] == 0:  # tree: dark green with brown centre
                draw_rectangle(o[0], o[1], o[0] + o[2] - 1, o[1] + o[3] - 1, 10, 65, 10)
                display.set_pixel(o[0] + 1, o[1] + 1, 100, 60, 20)
            elif o[4] == 1:  # bunker: sandy
                draw_rectangle(
                    o[0], o[1], o[0] + o[2] - 1, o[1] + o[3] - 1, 210, 185, 110
                )
            else:  # wall: grey
                draw_rectangle(
                    o[0], o[1], o[0] + o[2] - 1, o[1] + o[3] - 1, 110, 110, 110
                )
        # Hole: dark cup with yellow flag dot
        draw_rectangle(
            self.hole_x - 2, self.hole_y - 2, self.hole_x + 2, self.hole_y + 2, 0, 0, 0
        )
        display.set_pixel(self.hole_x + 2, self.hole_y - 3, 255, 220, 0)
        # Aim indicator when stationary
        if not self._moving():
            rad = self.angle * math.pi / 180.0
            ax = int(self.ball_x + math.cos(rad) * (self.power + 3))
            ay = int(self.ball_y + math.sin(rad) * (self.power + 3))
            draw_line(int(self.ball_x) + 1, int(self.ball_y) + 1, ax, ay, 255, 255, 0)
            draw_rectangle(1, 1, self.power * 4, 2, 255, 180, 0)
        # Ball
        draw_rectangle(
            int(self.ball_x),
            int(self.ball_y),
            int(self.ball_x) + 1,
            int(self.ball_y) + 1,
            255,
            255,
            255,
        )
        draw_text_small(
            1, 52, "H" + str(self.hole) + " P" + str(self.par), 200, 200, 200
        )
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
                self.score += (
                    max(1, 26 - self.strokes * 3 + self.par * 2) + self.hole * 2
                )
                self.hole += 1
                self._new_hole()
            if self.strokes >= self.par + 6:
                set_game_over_score(self.score)
                return False
            self._draw()
            return True

        return step


class LaserGame(FrameLoopGame):
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
            # Mirror 2 (\) redirects rightward beams down; mirror 1 (/) redirects up.
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
        self.solution_mirrors = solution_mirrors  # [(x, y, correct_kind), ...]
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
        d = joystick.read_direction(
            [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
        )
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
                self._draw_mirror(
                    px, py, self.grid[y][x], (x, y) in path_set, self.beam_phase
                )
        beam_complete = self._draw_beam(path, solved)
        sy = oy + self.start_y * self.CELL + 2
        ty = oy + self.target_y * self.CELL + 2
        start_pulse = 30 if ((self.beam_phase // 5) & 1) else 0
        draw_rectangle(0, sy - 1, 3, sy + 2, 255, 60 + start_pulse, 0)
        if solved:
            draw_rectangle(WIDTH - 5, ty - 2, WIDTH - 1, ty + 3, 80, 255, 120)
            draw_rectangle(WIDTH - 3, ty - 1, WIDTH - 1, ty + 2, 220, 255, 220)
        else:
            draw_rectangle(
                WIDTH - 4, ty - 1, WIDTH - 1, ty + 2, 0, 170 + start_pulse, 80
            )
        cx = ox + self.cursor_x * self.CELL
        cy = oy + self.cursor_y * self.CELL
        pulse_active = ticks_diff(now, self.beam_pulse_until) < 0
        cr, cg, cb = (255, 220, 80) if pulse_active else (255, 255, 255)
        draw_rect_outline(cx - 1, cy - 1, cx + 6, cy + 6, cr, cg, cb)
        wrong_count = sum(
            1 for mx, my, ck in self.solution_mirrors if self.grid[my][mx] != ck
        )
        draw_text_small(
            1, 52, "L" + str(self.level) + " M" + str(wrong_count), 160, 160, 160
        )
        display_score_and_time(self.score)
        return beam_complete

    def _start_level_complete(self, now):
        time_bonus = max(
            0, (self.time_limit_ms - ticks_diff(now, self.level_start)) // 400
        )
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
            if (
                not self.level_complete_pending
                and ticks_diff(now, self.level_start) > self.time_limit_ms
            ):
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


class PairsGame(FrameLoopGame):
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
        d = joystick.read_direction(
            [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
        )
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


class BomberGame(FrameLoopGame):
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
        self.blocks = [
            [False for _x in range(self.GRID_W)] for _y in range(self.GRID_H)
        ]
        for y in range(self.GRID_H):
            for x in range(self.GRID_W):
                fixed = x % 2 == 1 and y % 2 == 1
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
                self.enemies.append(
                    [
                        x,
                        y,
                        random.choice(
                            (JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT)
                        ),
                    ]
                )

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
        d = joystick.read_direction(
            [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
        )
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
                e[2] = random.choice(
                    (JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT)
                )
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
                    fixed = x % 2 == 1 and y % 2 == 1
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
        draw_rectangle(
            ox + self.px * self.CELL + 1,
            oy + self.py * self.CELL + 1,
            ox + self.px * self.CELL + 4,
            oy + self.py * self.CELL + 4,
            0,
            220,
            255,
        )
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


class SkyWarGame(FrameLoopGame):
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
        d = joystick.read_direction(
            [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
        )
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
            self.enemies.append(
                ["drone", WIDTH + 2, random.randint(4, PLAY_HEIGHT - 22), spd]
            )
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
        self.shots = [
            s for s in self.shots if 0 <= s[1] < WIDTH and 0 <= s[2] < PLAY_HEIGHT
        ]
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
        self.enemy_shots = [
            s for s in self.enemy_shots if s[0] >= 0 and 0 <= s[1] < PLAY_HEIGHT
        ]
        survivors = []
        for e in self.enemies:
            hit = False
            ew = 6 if e[0] == "drone" else 8
            eh = 4 if e[0] == "drone" else 5
            for s in self.shots:
                if rects_overlap(
                    int(s[1]), int(s[2]), 2, 4, int(e[1]), int(e[2]), ew, eh
                ):
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
                draw_rectangle(
                    int(s[1]), int(s[2]), int(s[1]) + 1, int(s[2]) + 3, 255, 255, 0
                )
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


class WingsGame(FrameLoopGame):
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
    DECK_Y = PLAY_HEIGHT - 13  # carrier deck screen y
    SEA_Y = PLAY_HEIGHT - 5  # sea surface screen y
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
        self.py = float(self.DECK_Y)  # player screen y
        self.vx = 0.0
        self.vy = 0.0
        self.state = self.LANDED
        self.fuel = 1600
        self.ammo = 20
        self.score = 0
        self.shots = []  # [type, world_x, screen_y, vx, vy]
        self.hit_flashes = []  # [world_x, screen_y, ttl_frames]
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
        d = joystick.read_direction(
            [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
        )
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
                self.shots.append(
                    ["bomb", self.px + 4, float(self.py + 5), self.vx * 0.5, 0.4]
                )
            else:
                # low altitude → strafing gun in direction of flight
                gx = self.px + (9 if flying_right else 0)
                self.shots.append(
                    ["gun", gx, float(self.py + 2), 5.0 if flying_right else -5.0, 0.0]
                )
            self.last_fire = now

    def _advance(self):
        self.frame += 1
        self.wave_t = (self.wave_t + 1) % 16

        if self.state == self.LANDED:
            self.fuel = min(1600, self.fuel + 10)  # refuel while on deck
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
            s[1] += s[3]  # world x
            s[2] += s[4]  # screen y
            if s[0] == "bomb":
                s[4] = min(s[4] + 0.14, 5.0)  # bomb gravity
        # remove shots that went off-screen or hit sea
        self.shots = [
            s
            for s in self.shots
            if 0 <= s[2] < self.SEA_Y and abs(s[1] - self.px) < WIDTH + 80
        ]

        # advance hit flashes
        self.hit_flashes = [
            [f[0], f[1], f[2] - 1] for f in self.hit_flashes if f[2] > 1
        ]

        # shot-target hit detection
        target_sy = self.SEA_Y - 10  # ground level for island targets (screen y)
        for s in self.shots:
            for island in self.islands:
                for t in island[2]:
                    if t[2]:
                        continue
                    if abs(s[1] - t[1]) < 9 and abs(s[2] - target_sy) < 9:
                        t[2] = True
                        s[2] = float(self.SEA_Y)  # mark shot for removal
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
            draw_line(
                (wxi + wo) % WIDTH,
                self.SEA_Y,
                (wxi + wo + 3) % WIDTH,
                self.SEA_Y - 1,
                0,
                60,
                145,
            )

        # carrier
        c_sx = self._to_screen_x(0)
        if c_sx + self.CARRIER_W >= 0 and c_sx < WIDTH:
            on_approach = (
                self.state == self.FLYING
                and self._on_carrier()
                and abs(self.py - self.DECK_Y) < 8
                and abs(self.vx) < 2.3
            )
            deck_r = 0 if on_approach else 80
            deck_g = 220 if on_approach else 85
            draw_rectangle(
                c_sx,
                self.DECK_Y,
                c_sx + self.CARRIER_W,
                self.DECK_Y + 4,
                deck_r,
                deck_g,
                95,
            )
            draw_rectangle(
                c_sx + 6, self.DECK_Y - 4, c_sx + 16, self.DECK_Y, 70, 70, 80
            )  # bridge
            # landing stripe
            draw_line(
                c_sx + 2,
                self.DECK_Y,
                c_sx + self.CARRIER_W - 2,
                self.DECK_Y,
                255,
                240,
                80,
            )
            # hull below waterline
            draw_rectangle(
                c_sx, self.DECK_Y + 4, c_sx + self.CARRIER_W, self.SEA_Y - 1, 55, 55, 65
            )

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
            draw_rectangle(
                i_sx, self.SEA_Y - 4, i_sx + iw, self.SEA_Y - 1, 200, 175, 100
            )
            # green interior
            draw_rectangle(
                i_sx + 3, self.SEA_Y - 9, i_sx + iw - 3, self.SEA_Y - 4, 45, 100, 30
            )
            # small hill
            draw_rectangle(
                i_sx + iw // 3,
                self.SEA_Y - 12,
                i_sx + 2 * iw // 3,
                self.SEA_Y - 9,
                30,
                75,
                20,
            )
            # targets on the island
            for t in island[2]:
                t_sx = self._to_screen_x(t[1])
                t_sy = self.SEA_Y - 10
                if t[2]:  # destroyed — show rubble
                    draw_rectangle(t_sx, t_sy + 1, t_sx + 5, t_sy + 4, 90, 55, 15)
                elif t[0] == "depot":
                    draw_rectangle(t_sx, t_sy, t_sx + 7, t_sy + 5, 140, 90, 25)
                    draw_rectangle(t_sx + 2, t_sy - 3, t_sx + 5, t_sy, 160, 100, 30)
                else:  # gun emplacement
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
                draw_line(psx + 1, psy, psx + 5, psy - 1, 180, 220, 255)  # top wing
                draw_line(psx - 1, psy + 2, psx - 3, psy, 120, 170, 210)  # tail
            else:
                draw_line(psx + 1, psy, psx + 5, psy - 1, 180, 220, 255)  # top wing
                draw_line(psx + 7, psy + 2, psx + 9, psy, 120, 170, 210)  # tail
        else:  # landed on deck
            draw_rectangle(psx, psy, psx + 6, psy + 2, 0, 180, 230)

        # HUD
        fuel_w = max(0, min(22, self.fuel // 73))
        low_fuel = fuel_w <= 5
        draw_rectangle(
            1, 1, fuel_w, 2, 255 if low_fuel else 0, 50 if low_fuel else 200, 0
        )
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
