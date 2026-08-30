"""Compact adaptations of arcade classics for the 64x64 matrix."""


class DonkeyGame(FrameLoopGame):
    """Climb girders, use ladders, and jump over rolling barrels."""

    FRAME_MS = 35
    LEVEL_Y = (50, 38, 26, 14)
    LADDERS = (50, 14, 47)

    def __init__(self):
        self.reset()

    def reset(self):
        self.player_x = 5
        self.level = 0
        self.barrels = []
        self.frame = 0
        self.jump = 0
        self.score = 0
        self.last_z = False

    def _climb(self):
        if self.level >= len(self.LADDERS):
            return False
        if abs(self.player_x - self.LADDERS[self.level]) > 4:
            return False
        self.level += 1
        self.player_x = self.LADDERS[self.level - 1]
        self.score += 25
        return True

    def _advance_barrels(self):
        kept = []
        for barrel in self.barrels:
            barrel[0] += barrel[2] * 2
            if barrel[0] < 2 or barrel[0] > 61:
                if barrel[1] == 0:
                    continue
                barrel[1] -= 1
                barrel[2] = -barrel[2]
                barrel[0] = clamp(barrel[0], 2, 61)
            if barrel[1] == self.level and abs(barrel[0] - self.player_x) < 4:
                if not self.jump:
                    return False
                self.score += 10
            kept.append(barrel)
        self.barrels = kept
        return True

    def _draw(self):
        display.clear()
        for index, y in enumerate(self.LEVEL_Y):
            draw_line(1, y, 62, y, 180, 55 + index * 25, 55)
            if index < len(self.LADDERS):
                x = self.LADDERS[index]
                draw_line(x - 2, y - 11, x - 2, y, 230, 180, 70)
                draw_line(x + 2, y - 11, x + 2, y, 230, 180, 70)
        py = self.LEVEL_Y[self.level] - 4 - (3 if self.jump else 0)
        draw_rectangle(self.player_x - 2, py, self.player_x + 2, py + 3, 80, 210, 255)
        for x, level, _direction in self.barrels:
            y = self.LEVEL_Y[level] - 3
            draw_rectangle(x - 2, y, x + 2, y + 2, 255, 145, 40)
        draw_rectangle(54, 7, 61, 13, 190, 70, 210)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        begin_game(0)
        self.reset()

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            direction = joystick.read_direction(
                [JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_UP], debounce=False
            )
            if direction == JOYSTICK_LEFT:
                self.player_x = max(2, self.player_x - 1)
            elif direction == JOYSTICK_RIGHT:
                self.player_x = min(61, self.player_x + 1)
            elif direction == JOYSTICK_UP:
                self._climb()
            if z_button and not self.last_z:
                self.jump = 9
            self.last_z = z_button
            self.jump = max(0, self.jump - 1)
            self.frame += 1
            if self.frame % 55 == 1:
                self.barrels.append([58, 3, -1])
            if self.frame % 3 == 0 and not self._advance_barrels():
                set_game_over_score(self.score)
                return False
            if self.level == 3 and self.player_x >= 54:
                set_game_over_score(self.score + 500, won=True)
                return False
            self._draw()
            return True

        return step


class GalagaGame(FrameLoopGame):
    """Fight a formation whose ships peel off into diving attacks."""

    FRAME_MS = 32

    def __init__(self):
        self.reset()

    def reset(self):
        self.ship_x = 32
        self.enemies = [[8 + col * 9, 7 + row * 7, 0] for row in range(3) for col in range(6)]
        self.bullets = []
        self.enemy_bullets = []
        self.frame = 0
        self.score = 0
        self.last_z = False

    def _shoot(self):
        if len(self.bullets) < 3:
            self.bullets.append([self.ship_x, 50])

    def _advance(self):
        for bullet in self.bullets:
            bullet[1] -= 3
        for bullet in self.enemy_bullets:
            bullet[1] += 2
        for enemy in self.enemies:
            if enemy[2]:
                enemy[1] += 2
                enemy[0] += -1 if enemy[0] > self.ship_x else 1
        hit_bullets = []
        hit_enemies = []
        for bullet in self.bullets:
            for enemy in self.enemies:
                if abs(bullet[0] - enemy[0]) <= 3 and abs(bullet[1] - enemy[1]) <= 3:
                    hit_bullets.append(bullet)
                    hit_enemies.append(enemy)
                    self.score += 50 if enemy[2] else 25
                    break
        self.bullets = [b for b in self.bullets if b[1] > 0 and b not in hit_bullets]
        self.enemies = [e for e in self.enemies if e not in hit_enemies and e[1] < 55]
        for bullet in self.enemy_bullets:
            if bullet[1] >= 51 and abs(bullet[0] - self.ship_x) <= 3:
                return False
        for enemy in self.enemies:
            if enemy[1] >= 49 and abs(enemy[0] - self.ship_x) <= 5:
                return False
        self.enemy_bullets = [b for b in self.enemy_bullets if b[1] < 56]
        return True

    def _draw(self):
        display.clear()
        for x, y, diving in self.enemies:
            color = (255, 80, 100) if diving else (100, 210, 255)
            draw_rectangle(x - 2, y, x + 2, y + 2, *color)
        for x, y in self.bullets:
            draw_line(x, y, x, y + 2, 255, 240, 120)
        for x, y in self.enemy_bullets:
            display.set_pixel(x, y, 255, 70, 70)
        draw_line(self.ship_x, 50, self.ship_x - 3, 54, 100, 255, 150)
        draw_line(self.ship_x, 50, self.ship_x + 3, 54, 100, 255, 150)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        begin_game(0)
        self.reset()

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            direction = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT], debounce=False)
            if direction == JOYSTICK_LEFT:
                self.ship_x = max(4, self.ship_x - 2)
            elif direction == JOYSTICK_RIGHT:
                self.ship_x = min(59, self.ship_x + 2)
            if z_button and not self.last_z:
                self._shoot()
            self.last_z = z_button
            self.frame += 1
            if self.enemies and self.frame % 45 == 0:
                self.enemies[self.frame // 45 % len(self.enemies)][2] = 1
            if self.enemies and self.frame % 31 == 0:
                enemy = self.enemies[self.frame // 31 % len(self.enemies)]
                self.enemy_bullets.append([enemy[0], enemy[1] + 2])
            if not self._advance():
                set_game_over_score(self.score)
                return False
            if not self.enemies:
                set_game_over_score(self.score + 500, won=True)
                return False
            self._draw()
            return True

        return step


class TempestGame(FrameLoopGame):
    """Circle a wireframe tunnel and shoot enemies before they reach its rim."""

    FRAME_MS = 35
    RIM = ((32, 3), (46, 7), (58, 17), (61, 31), (58, 45), (46, 55), (32, 57), (18, 55), (6, 45), (3, 31), (6, 17), (18, 7))

    def __init__(self):
        self.reset()

    def reset(self):
        self.lane = 0
        self.enemies = []
        self.shots = []
        self.frame = 0
        self.score = 0
        self.last_move = ticks_ms()
        self.last_z = False

    def _advance(self):
        for enemy in self.enemies:
            enemy[1] += 1
        for shot in self.shots:
            shot[1] -= 2
        removed_enemies = []
        removed_shots = []
        for shot in self.shots:
            for enemy in self.enemies:
                if shot[0] == enemy[0] and abs(shot[1] - enemy[1]) <= 2:
                    removed_enemies.append(enemy)
                    removed_shots.append(shot)
                    self.score += 40
                    break
        self.enemies = [e for e in self.enemies if e not in removed_enemies]
        self.shots = [s for s in self.shots if s[1] > 0 and s not in removed_shots]
        return not any(e[1] >= 10 and e[0] == self.lane for e in self.enemies)

    def _point(self, lane, depth):
        x, y = self.RIM[lane]
        return 32 + (x - 32) * depth // 10, 30 + (y - 30) * depth // 10

    def _draw(self):
        display.clear()
        for x, y in self.RIM:
            draw_line(32, 30, x, y, 35, 70, 105)
        for lane, depth in self.enemies:
            x, y = self._point(lane, depth)
            draw_rectangle(x - 1, y - 1, x + 1, y + 1, 255, 75, 125)
        for lane, depth in self.shots:
            x, y = self._point(lane, depth)
            display.set_pixel(x, y, 255, 240, 100)
        x, y = self.RIM[self.lane]
        draw_rectangle(x - 2, y - 2, x + 2, y + 2, 80, 240, 255)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        begin_game(0)
        self.reset()

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            now = ticks_ms()
            direction = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT], debounce=False)
            if ticks_diff(now, self.last_move) >= 90:
                if direction == JOYSTICK_LEFT:
                    self.lane = (self.lane - 1) % len(self.RIM)
                    self.last_move = now
                elif direction == JOYSTICK_RIGHT:
                    self.lane = (self.lane + 1) % len(self.RIM)
                    self.last_move = now
            if z_button and not self.last_z:
                self.shots.append([self.lane, 9])
            self.last_z = z_button
            self.frame += 1
            if self.frame % max(20, 42 - self.score // 120) == 1:
                self.enemies.append([(self.frame // 7) % len(self.RIM), 1])
            if self.frame % 7 == 0 and not self._advance():
                set_game_over_score(self.score)
                return False
            self._draw()
            return True

        return step


class DefenderGame(FrameLoopGame):
    """Patrol a wrapping planet, destroy raiders, and rescue abducted settlers."""

    FRAME_MS = 35

    def __init__(self):
        self.reset()

    def reset(self):
        self.ship_y = 28
        self.direction = 1
        self.raiders = [[52, 12, 0], [38, 35, 1], [60, 22, 2]]
        self.settlers = [[12, 50, 0], [31, 50, 0], [51, 50, 0]]
        self.bullets = []
        self.frame = 0
        self.score = 0
        self.last_z = False

    def _shoot(self):
        self.bullets.append([32 + self.direction * 4, self.ship_y, self.direction])

    def _advance(self):
        for bullet in self.bullets:
            bullet[0] += bullet[2] * 4
        for raider in self.raiders:
            target = self.settlers[raider[2] % len(self.settlers)]
            if self.frame % 3 == 0:
                raider[0] += -1 if raider[0] > target[0] else 1
                raider[1] += 1 if raider[1] < target[1] else -1
            if abs(raider[0] - 32) < 4 and abs(raider[1] - self.ship_y) < 4:
                return False
        hit_bullets = []
        hit_raiders = []
        for bullet in self.bullets:
            for raider in self.raiders:
                if abs(bullet[0] - raider[0]) < 4 and abs(bullet[1] - raider[1]) < 4:
                    hit_bullets.append(bullet)
                    hit_raiders.append(raider)
                    self.score += 50
                    break
        self.bullets = [b for b in self.bullets if 0 <= b[0] < WIDTH and b not in hit_bullets]
        self.raiders = [r for r in self.raiders if r not in hit_raiders]
        for raider in self.raiders:
            target = self.settlers[raider[2] % len(self.settlers)]
            if abs(raider[0] - target[0]) < 3 and abs(raider[1] - target[1]) < 3:
                target[2] = 1
        return sum(s[2] for s in self.settlers) < len(self.settlers)

    def _draw(self):
        display.clear()
        draw_line(0, 53, 63, 53, 50, 145, 65)
        for x, y, lost in self.settlers:
            if not lost:
                draw_line(x, y - 3, x, y, 110, 255, 155)
        for x, y, _target in self.raiders:
            draw_rectangle(x - 2, y - 1, x + 2, y + 1, 255, 80, 150)
        for x, y, _direction in self.bullets:
            draw_line(x - 2, y, x + 2, y, 255, 245, 100)
        draw_line(28, self.ship_y, 36, self.ship_y, 90, 220, 255)
        draw_line(32, self.ship_y, 32 - self.direction * 4, self.ship_y + 3, 90, 220, 255)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        begin_game(0)
        self.reset()

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            direction = joystick.read_direction(
                [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT], debounce=False
            )
            if direction == JOYSTICK_UP:
                self.ship_y = max(5, self.ship_y - 2)
            elif direction == JOYSTICK_DOWN:
                self.ship_y = min(49, self.ship_y + 2)
            elif direction == JOYSTICK_LEFT:
                self.direction = -1
            elif direction == JOYSTICK_RIGHT:
                self.direction = 1
            if z_button and not self.last_z:
                self._shoot()
            self.last_z = z_button
            self.frame += 1
            if self.frame % 2 == 0 and not self._advance():
                set_game_over_score(self.score)
                return False
            if not self.raiders:
                set_game_over_score(self.score + 300, won=True)
                return False
            self._draw()
            return True

        return step


class MoonPatrolGame(FrameLoopGame):
    """Drive an armed lunar rover, jump craters, and shoot airborne hazards."""

    FRAME_MS = 32

    def __init__(self):
        self.reset()

    def reset(self):
        self.rover_y = 46
        self.velocity_y = 0
        self.obstacles = [[72, 0], [105, 1], [138, 0]]
        self.bullets = []
        self.frame = 0
        self.distance = 0
        self.last_z = False

    def _jump(self):
        if self.rover_y >= 46:
            self.velocity_y = -5
            return True
        return False

    def _advance(self):
        self.velocity_y += 1
        self.rover_y = min(46, self.rover_y + self.velocity_y)
        if self.rover_y == 46:
            self.velocity_y = 0
        for obstacle in self.obstacles:
            obstacle[0] -= 1
            if obstacle[0] < -5:
                obstacle[0] += 105
                obstacle[1] = 1 - obstacle[1]
                self.distance += 25
        for bullet in self.bullets:
            bullet[1] -= 3
        used_bullets = []
        for bullet in self.bullets:
            for obstacle in self.obstacles:
                if obstacle[1] == 1 and abs(bullet[0] - obstacle[0]) < 4 and abs(bullet[1] - 24) < 4:
                    obstacle[0] += 105
                    used_bullets.append(bullet)
                    self.distance += 40
                    break
        self.bullets = [b for b in self.bullets if b[1] > 1 and b not in used_bullets]
        for obstacle in self.obstacles:
            if obstacle[1] == 0 and 8 <= obstacle[0] <= 19 and self.rover_y > 39:
                return False
            if obstacle[1] == 1 and 8 <= obstacle[0] <= 19 and self.rover_y < 37:
                return False
        return True

    def _draw(self):
        display.clear()
        draw_line(0, 52, 63, 52, 120, 105, 90)
        draw_rectangle(9, self.rover_y, 19, self.rover_y + 4, 235, 210, 95)
        display.set_pixel(11, self.rover_y + 5, 120, 190, 255)
        display.set_pixel(17, self.rover_y + 5, 120, 190, 255)
        for x, kind in self.obstacles:
            if 0 <= x < 64:
                if kind == 0:
                    draw_rectangle(x, 49, x + 5, 52, 20, 20, 35)
                else:
                    draw_rectangle(x, 23, x + 5, 26, 255, 85, 85)
        for x, y in self.bullets:
            draw_line(x, y, x + 2, y, 255, 240, 100)
        display_score_and_time(self.distance)

    def _build_step(self, joystick):
        begin_game(0)
        self.reset()

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            direction = joystick.read_direction([JOYSTICK_UP], debounce=False)
            if z_button and not self.last_z:
                self._jump()
            if direction == JOYSTICK_UP and self.frame % 8 == 0:
                self.bullets.append([15, self.rover_y])
            self.last_z = z_button
            self.frame += 1
            if not self._advance():
                set_game_over_score(self.distance)
                return False
            self._draw()
            return True

        return step


class ZaxxonGame(FrameLoopGame):
    """Fly through an isometric fortress and align with moving energy gates."""

    FRAME_MS = 35

    def __init__(self):
        self.reset()

    def reset(self):
        self.ship_y = 30
        self.altitude = 2
        self.gates = [[72, 18, 16], [104, 31, 13], [136, 10, 18]]
        self.score = 0
        self.frame = 0

    def _advance(self):
        for gate in self.gates:
            gate[0] -= 1
            if gate[0] < -5:
                gate[0] += 102
                gate[1] = 8 + (gate[1] * 3 + 7) % 34
                self.score += 50
            if 8 <= gate[0] <= 16 and not gate[1] <= self.ship_y <= gate[1] + gate[2]:
                return False
        return True

    def _draw(self):
        display.clear()
        for offset in range(0, 64, 12):
            draw_line(offset, 55, offset + 24, 5, 25, 70, 95)
        for x, gap, size in self.gates:
            if 0 <= x < 64:
                draw_line(x, 4, x, gap, 255, 90, 80)
                draw_line(x, gap + size, x, 54, 255, 90, 80)
                draw_line(x, 4, min(63, x + 6), 9, 90, 170, 210)
        color = (100 + self.altitude * 35, 230, 255)
        draw_line(7, self.ship_y, 16, self.ship_y, *color)
        draw_line(11, self.ship_y, 8, self.ship_y + 5, *color)
        draw_text_small(1, 1, "A" + str(self.altitude), 180, 230, 255)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        begin_game(0)
        self.reset()

        def step():
            c_button, _z_button = joystick.read_buttons()
            if c_button:
                return False
            direction = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN], debounce=False)
            if direction == JOYSTICK_UP:
                self.ship_y = max(6, self.ship_y - 2)
                self.altitude = min(4, self.altitude + 1)
            elif direction == JOYSTICK_DOWN:
                self.ship_y = min(52, self.ship_y + 2)
                self.altitude = max(0, self.altitude - 1)
            self.frame += 1
            if not self._advance():
                set_game_over_score(self.score)
                return False
            self._draw()
            return True

        return step


class PaperboyGame(FrameLoopGame):
    """Cycle down a hazardous street and throw papers into marked mailboxes."""

    FRAME_MS = 35

    def __init__(self):
        self.reset()

    def reset(self):
        self.bike_y = 31
        self.targets = [[75, 10], [105, 47], [135, 16]]
        self.hazards = [[90, 30], [128, 39]]
        self.papers = []
        self.score = 0
        self.missed = 0
        self.last_z = False

    def _throw(self):
        if len(self.papers) < 2:
            self.papers.append([15, self.bike_y, 2 if self.bike_y < 29 else -2])

    def _advance(self):
        for item in self.targets + self.hazards:
            item[0] -= 1
            if item[0] < -5:
                item[0] += 95
                if item in self.targets:
                    self.missed += 1
        for paper in self.papers:
            paper[0] += 3
            paper[1] += paper[2]
        hit_papers = []
        for paper in self.papers:
            for target in self.targets:
                if abs(paper[0] - target[0]) < 4 and abs(paper[1] - target[1]) < 5:
                    hit_papers.append(paper)
                    target[0] += 95
                    self.score += 100
                    break
        self.papers = [p for p in self.papers if p[0] < 64 and 0 < p[1] < 56 and p not in hit_papers]
        return not any(8 <= x <= 17 and abs(y - self.bike_y) < 5 for x, y in self.hazards)

    def _draw(self):
        display.clear()
        draw_rectangle(0, 19, 63, 43, 40, 42, 48)
        draw_line(0, 30, 63, 30, 210, 190, 90)
        draw_rectangle(8, self.bike_y - 2, 15, self.bike_y + 2, 70, 200, 255)
        for x, y in self.targets:
            if 0 <= x < 64:
                draw_rectangle(x, y, x + 3, y + 6, 100, 240, 135)
        for x, y in self.hazards:
            if 0 <= x < 64:
                draw_rectangle(x, y - 2, x + 4, y + 2, 255, 90, 70)
        for x, y, _dy in self.papers:
            draw_rectangle(x, y, x + 2, y + 1, 245, 245, 230)
        draw_text_small(1, 1, "M" + str(self.missed), 255, 150, 90)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        begin_game(0)
        self.reset()

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            direction = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN], debounce=False)
            if direction == JOYSTICK_UP:
                self.bike_y = max(22, self.bike_y - 2)
            elif direction == JOYSTICK_DOWN:
                self.bike_y = min(40, self.bike_y + 2)
            if z_button and not self.last_z:
                self._throw()
            self.last_z = z_button
            if not self._advance() or self.missed >= 5:
                set_game_over_score(self.score)
                return False
            self._draw()
            return True

        return step


class TapperGame(FrameLoopGame):
    """Serve four bar lanes quickly and catch every returning mug."""

    FRAME_MS = 35
    LANES = (10, 22, 34, 46)

    def __init__(self):
        self.reset()

    def reset(self):
        self.lane = 0
        self.customers = [[0, 60], [1, 50], [2, 57], [3, 45]]
        self.mugs = []
        self.score = 0
        self.frame = 0
        self.last_move = ticks_ms()
        self.last_z = False

    def _serve(self):
        if not any(mug[0] == self.lane and mug[2] > 0 for mug in self.mugs):
            self.mugs.append([self.lane, 7, 2])

    def _advance(self):
        if self.frame % 3 == 0:
            for customer in self.customers:
                customer[1] -= 1
        for mug in self.mugs:
            mug[1] += mug[2]
        served = []
        for mug in self.mugs:
            if mug[2] <= 0:
                continue
            for customer in self.customers:
                if customer[0] == mug[0] and abs(customer[1] - mug[1]) < 3:
                    customer[1] = 62
                    mug[2] = -2
                    served.append(customer)
                    self.score += 50
                    break
        for mug in self.mugs:
            if mug[2] < 0 and mug[1] <= 6:
                if mug[0] != self.lane:
                    return False
                mug[1] = -10
                self.score += 10
        self.mugs = [m for m in self.mugs if m[1] >= 0]
        return not any(customer[1] <= 5 for customer in self.customers)

    def _draw(self):
        display.clear()
        for index, y in enumerate(self.LANES):
            draw_line(4, y + 4, 63, y + 4, 125, 75, 35)
            if index == self.lane:
                draw_rectangle(1, y, 5, y + 5, 80, 220, 255)
        for lane, x in self.customers:
            y = self.LANES[lane]
            draw_rectangle(x - 2, y, x + 2, y + 4, 255, 120, 90)
        for lane, x, _speed in self.mugs:
            if x >= 0:
                y = self.LANES[lane]
                draw_rectangle(x, y + 1, x + 2, y + 3, 245, 230, 150)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        begin_game(0)
        self.reset()

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            now = ticks_ms()
            direction = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN], debounce=False)
            if ticks_diff(now, self.last_move) >= 100:
                if direction == JOYSTICK_UP:
                    self.lane = max(0, self.lane - 1)
                    self.last_move = now
                elif direction == JOYSTICK_DOWN:
                    self.lane = min(3, self.lane + 1)
                    self.last_move = now
            if z_button and not self.last_z:
                self._serve()
            self.last_z = z_button
            self.frame += 1
            if not self._advance():
                set_game_over_score(self.score)
                return False
            self._draw()
            return True

        return step


class BubbleBobbleGame(FrameLoopGame):
    """Trap bouncing enemies in bubbles, then touch the bubbles to pop them."""

    FRAME_MS = 35

    def __init__(self):
        self.reset()

    def reset(self):
        self.player_x = 10
        self.player_y = 49
        self.velocity_y = 0
        self.enemies = [[45, 47, -1, 0], [28, 34, 1, 0], [52, 20, -1, 0]]
        self.bubbles = []
        self.score = 0
        self.frame = 0
        self.last_z = False

    def _advance(self):
        self.velocity_y += 1
        self.player_y = min(49, self.player_y + self.velocity_y)
        if self.player_y == 49:
            self.velocity_y = 0
        for bubble in self.bubbles:
            bubble[0] += bubble[2] * 2
            bubble[1] -= 1
        for enemy in self.enemies:
            if enemy[3]:
                enemy[1] -= 1
            elif self.frame % 2 == 0:
                enemy[0] += enemy[2]
                if enemy[0] < 4 or enemy[0] > 59:
                    enemy[2] = -enemy[2]
        used = []
        for bubble in self.bubbles:
            for enemy in self.enemies:
                if not enemy[3] and abs(bubble[0] - enemy[0]) < 4 and abs(bubble[1] - enemy[1]) < 4:
                    enemy[3] = 1
                    used.append(bubble)
                    break
        self.bubbles = [b for b in self.bubbles if 0 < b[0] < 64 and b[1] > 1 and b not in used]
        popped = []
        for enemy in self.enemies:
            if enemy[3] and abs(enemy[0] - self.player_x) < 5 and abs(enemy[1] - self.player_y) < 6:
                popped.append(enemy)
                self.score += 100
            elif not enemy[3] and abs(enemy[0] - self.player_x) < 4 and abs(enemy[1] - self.player_y) < 5:
                return False
        self.enemies = [e for e in self.enemies if e not in popped and e[1] > 1]
        return True

    def _draw(self):
        display.clear()
        for y in (53, 38, 24):
            draw_line(2, y, 61, y, 70, 105, 170)
        draw_rectangle(self.player_x - 2, self.player_y, self.player_x + 2, self.player_y + 4, 80, 240, 150)
        for x, y, _direction in self.bubbles:
            draw_rect_outline(x - 2, y - 2, x + 2, y + 2, 120, 220, 255)
        for x, y, _direction, trapped in self.enemies:
            color = (120, 200, 255) if trapped else (255, 90, 150)
            draw_rectangle(x - 2, y, x + 2, y + 3, *color)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        begin_game(0)
        self.reset()

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            direction = joystick.read_direction(
                [JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_UP], debounce=False
            )
            if direction == JOYSTICK_LEFT:
                self.player_x = max(3, self.player_x - 2)
            elif direction == JOYSTICK_RIGHT:
                self.player_x = min(60, self.player_x + 2)
            elif direction == JOYSTICK_UP and self.player_y >= 49:
                self.velocity_y = -5
            if z_button and not self.last_z:
                self.bubbles.append([self.player_x + 3, self.player_y, 1])
            self.last_z = z_button
            self.frame += 1
            if not self._advance():
                set_game_over_score(self.score)
                return False
            if not self.enemies:
                set_game_over_score(self.score + 300, won=True)
                return False
            self._draw()
            return True

        return step


class MarbleGame(FrameLoopGame):
    """Accelerate a marble through walls, holes, and a narrow finish gate."""

    FRAME_MS = 35
    WALLS = ((18, 8, 22, 42), (39, 18, 43, 52), (24, 47, 38, 51))
    HOLES = ((31, 20), (51, 39))

    def __init__(self):
        self.reset()

    def reset(self):
        self.x = 7.0
        self.y = 50.0
        self.vx = 0.0
        self.vy = 0.0
        self.frames = 0

    def _physics(self, dx, dy):
        self.vx = clamp(self.vx + dx * 0.22, -2.2, 2.2) * 0.94
        self.vy = clamp(self.vy + dy * 0.22, -2.2, 2.2) * 0.94
        old_x, old_y = self.x, self.y
        self.x = clamp(self.x + self.vx, 2, 61)
        self.y = clamp(self.y + self.vy, 2, 55)
        for x1, y1, x2, y2 in self.WALLS:
            if x1 - 2 <= self.x <= x2 + 2 and y1 - 2 <= self.y <= y2 + 2:
                self.x, self.y = old_x, old_y
                self.vx *= -0.45
                self.vy *= -0.45
        return not any((self.x - hx) ** 2 + (self.y - hy) ** 2 < 9 for hx, hy in self.HOLES)

    def _draw(self):
        display.clear()
        for wall in self.WALLS:
            draw_rectangle(*wall, 65, 105, 165)
        for x, y in self.HOLES:
            draw_rectangle(x - 2, y - 2, x + 2, y + 2, 5, 5, 12)
        draw_rect_outline(54, 2, 62, 8, 100, 255, 130)
        draw_rectangle(int(self.x) - 2, int(self.y) - 2, int(self.x) + 2, int(self.y) + 2, 245, 230, 160)
        display_score_and_time(max(0, 999 - self.frames // 3))

    def _build_step(self, joystick):
        begin_game(0)
        self.reset()

        def step():
            c_button, _z_button = joystick.read_buttons()
            if c_button:
                return False
            direction = joystick.read_direction(
                [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT], debounce=False
            )
            dx, dy = direction_to_delta(direction)
            self.frames += 1
            if not self._physics(dx, dy):
                set_game_over_score(0)
                return False
            if self.x >= 54 and self.y <= 8:
                set_game_over_score(max(50, 1000 - self.frames // 2), won=True)
                return False
            self._draw()
            return True

        return step


class BlobbyVolleyGame(FrameLoopGame):
    """One-button beach volleyball against a compact CPU blob."""

    FRAME_MS = 30

    def __init__(self):
        self.reset()

    def reset(self):
        self.player_x = 14.0
        self.cpu_x = 50.0
        self.player_vy = 0.0
        self.cpu_vy = 0.0
        self.player_y = 48.0
        self.cpu_y = 48.0
        self.ball_x = 20.0
        self.ball_y = 15.0
        self.ball_vx = 1.2
        self.ball_vy = 0.0
        self.player_score = 0
        self.cpu_score = 0
        self.last_z = False

    def _round_reset(self, toward_player):
        self.ball_x = 32.0
        self.ball_y = 13.0
        self.ball_vx = -1.1 if toward_player else 1.1
        self.ball_vy = 0.0

    def _advance(self):
        self.player_vy += 0.45
        self.cpu_vy += 0.45
        self.player_y = min(48.0, self.player_y + self.player_vy)
        self.cpu_y = min(48.0, self.cpu_y + self.cpu_vy)
        if self.player_y >= 48:
            self.player_vy = 0
        if self.cpu_y >= 48:
            self.cpu_vy = 0
        self.cpu_x += clamp(self.ball_x - self.cpu_x, -1.1, 1.1)
        if self.ball_y < 34 and abs(self.cpu_x - self.ball_x) < 5 and self.cpu_y >= 47:
            self.cpu_vy = -5
        self.ball_vy += 0.25
        self.ball_x += self.ball_vx
        self.ball_y += self.ball_vy
        if self.ball_x < 2 or self.ball_x > 61:
            self.ball_vx = -self.ball_vx
            self.ball_x = clamp(self.ball_x, 2, 61)
        if self.ball_y < 2:
            self.ball_vy = abs(self.ball_vy)
        if 29 <= self.ball_x <= 35 and self.ball_y >= 31:
            self.ball_vx = -self.ball_vx
            self.ball_x = 28 if self.ball_x < 32 else 36
        for x, y, side in ((self.player_x, self.player_y, 1), (self.cpu_x, self.cpu_y, -1)):
            if abs(self.ball_x - x) < 6 and abs(self.ball_y - y) < 7:
                self.ball_vx = side * (1.4 + abs(self.ball_x - x) * 0.1)
                self.ball_vy = -4.2
        if self.ball_y > 54:
            if self.ball_x < 32:
                self.cpu_score += 1
                self._round_reset(True)
            else:
                self.player_score += 1
                self._round_reset(False)

    def _draw(self):
        display.clear()
        draw_line(0, 54, 63, 54, 230, 205, 120)
        draw_line(32, 30, 32, 54, 235, 235, 240)
        draw_rectangle(int(self.player_x) - 4, int(self.player_y), int(self.player_x) + 4, 53, 70, 200, 255)
        draw_rectangle(int(self.cpu_x) - 4, int(self.cpu_y), int(self.cpu_x) + 4, 53, 255, 100, 150)
        draw_rectangle(int(self.ball_x) - 2, int(self.ball_y) - 2, int(self.ball_x) + 2, int(self.ball_y) + 2, 255, 245, 110)
        draw_text_small(1, 1, str(self.player_score) + "-" + str(self.cpu_score), 255, 255, 255)
        display_score_and_time(self.player_score)

    def _build_step(self, joystick):
        begin_game(0)
        self.reset()

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            direction = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT], debounce=False)
            if direction == JOYSTICK_LEFT:
                self.player_x = max(5, self.player_x - 1.5)
            elif direction == JOYSTICK_RIGHT:
                self.player_x = min(27, self.player_x + 1.5)
            if z_button and not self.last_z and self.player_y >= 48:
                self.player_vy = -5
            self.last_z = z_button
            self._advance()
            if self.player_score >= 5 or self.cpu_score >= 5:
                set_game_over_score(self.player_score * 100, won=self.player_score >= 5)
                return False
            self._draw()
            return True

        return step


class PeggleGame(FrameLoopGame):
    """Aim a bouncing ball, clear orange pegs, and conserve limited shots."""

    FRAME_MS = 30
    PEG_LAYOUT = (
        (11, 16, 0), (23, 13, 1), (35, 16, 0), (47, 13, 1),
        (17, 27, 1), (29, 25, 0), (41, 27, 0), (53, 25, 1),
        (10, 38, 0), (24, 40, 1), (38, 38, 0), (52, 40, 0),
    )

    def __init__(self):
        self.reset()

    def reset(self):
        self.pegs = [[x, y, orange, 1] for x, y, orange in self.PEG_LAYOUT]
        self.aim = 0
        self.ball = None
        self.shots = 8
        self.score = 0
        self.bucket_x = 24
        self.bucket_direction = 1
        self.last_move = ticks_ms()
        self.last_z = False

    def _launch(self):
        if self.ball is not None or self.shots <= 0:
            return False
        angle = (-1.1, -0.75, -0.4, 0.0, 0.4, 0.75, 1.1)[self.aim]
        self.ball = [32.0, 5.0, angle, 1.2]
        self.shots -= 1
        return True

    def _advance_ball(self):
        self.bucket_x += self.bucket_direction
        if self.bucket_x <= 4 or self.bucket_x >= 44:
            self.bucket_direction = -self.bucket_direction
        if self.ball is None:
            return
        ball = self.ball
        ball[3] += 0.13
        ball[0] += ball[2]
        ball[1] += ball[3]
        if ball[0] < 2 or ball[0] > 61:
            ball[2] = -ball[2]
            ball[0] = clamp(ball[0], 2, 61)
        for peg in self.pegs:
            if peg[3] and (ball[0] - peg[0]) ** 2 + (ball[1] - peg[1]) ** 2 < 18:
                peg[3] = 0
                ball[3] = -abs(ball[3]) * 0.8
                ball[2] += (ball[0] - peg[0]) * 0.12
                self.score += 100 if peg[2] else 25
                break
        if ball[1] > 54:
            if self.bucket_x <= ball[0] <= self.bucket_x + 16:
                self.shots += 1
                self.score += 50
            self.ball = None

    def _orange_left(self):
        return sum(1 for peg in self.pegs if peg[2] and peg[3])

    def _draw(self):
        display.clear()
        for x, y, orange, active in self.pegs:
            if active:
                color = (255, 145, 45) if orange else (80, 170, 255)
                draw_rectangle(x - 2, y - 2, x + 2, y + 2, *color)
        aim_x = 32 + (-18, -12, -6, 0, 6, 12, 18)[self.aim]
        draw_line(32, 4, aim_x, 13, 180, 180, 210)
        if self.ball is not None:
            draw_rectangle(int(self.ball[0]) - 2, int(self.ball[1]) - 2, int(self.ball[0]) + 2, int(self.ball[1]) + 2, 255, 245, 170)
        draw_line(self.bucket_x, 55, self.bucket_x + 16, 55, 100, 240, 160)
        draw_text_small(1, 1, "B" + str(self.shots), 220, 230, 255)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        begin_game(0)
        self.reset()

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            now = ticks_ms()
            direction = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT], debounce=False)
            if self.ball is None and ticks_diff(now, self.last_move) >= 100:
                if direction == JOYSTICK_LEFT:
                    self.aim = max(0, self.aim - 1)
                    self.last_move = now
                elif direction == JOYSTICK_RIGHT:
                    self.aim = min(6, self.aim + 1)
                    self.last_move = now
            if z_button and not self.last_z:
                self._launch()
            self.last_z = z_button
            self._advance_ball()
            if not self._orange_left():
                set_game_over_score(self.score + self.shots * 100, won=True)
                return False
            if self.shots <= 0 and self.ball is None:
                set_game_over_score(self.score)
                return False
            self._draw()
            return True

        return step


class StreetFightersGame(FrameLoopGame):
    """One-on-one footwork and timing duel against an aggressive CPU fighter."""

    FRAME_MS = 35

    def __init__(self):
        self.reset()

    def reset(self):
        self.player_x = 12
        self.cpu_x = 51
        self.player_hp = 12
        self.cpu_hp = 12
        self.player_attack = 0
        self.cpu_attack = 0
        self.player_jump = 0
        self.frame = 0
        self.score = 0
        self.last_z = False

    def _punch(self):
        if self.player_attack:
            return False
        self.player_attack = 5
        if abs(self.cpu_x - self.player_x) <= 10:
            self.cpu_hp -= 2
            self.score += 50
            self.cpu_x = min(58, self.cpu_x + 3)
            return True
        return False

    def _advance_cpu(self):
        distance = self.cpu_x - self.player_x
        if distance > 8:
            self.cpu_x -= 1
        elif self.cpu_attack == 0 and self.frame % 18 == 0:
            self.cpu_attack = 5
            if not self.player_jump:
                self.player_hp -= 1
                self.player_x = max(4, self.player_x - 2)
        self.player_attack = max(0, self.player_attack - 1)
        self.cpu_attack = max(0, self.cpu_attack - 1)
        self.player_jump = max(0, self.player_jump - 1)

    def _draw_fighter(self, x, color, attack, jump):
        y = 40 - (5 if jump else 0)
        draw_rectangle(x - 2, y, x + 2, y + 5, *color)
        draw_line(x, y + 5, x - 3, y + 10, *color)
        draw_line(x, y + 5, x + 3, y + 10, *color)
        arm_x = x + (7 if attack else 4)
        draw_line(x, y + 2, arm_x, y + 2, *color)

    def _draw(self):
        display.clear()
        draw_line(0, 52, 63, 52, 145, 95, 60)
        self._draw_fighter(self.player_x, (80, 190, 255), self.player_attack, self.player_jump)
        self._draw_fighter(self.cpu_x, (255, 85, 100), -self.cpu_attack, 0)
        draw_rectangle(2, 3, 2 + self.player_hp * 2, 5, 80, 210, 255)
        draw_rectangle(61 - self.cpu_hp * 2, 3, 61, 5, 255, 80, 90)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        begin_game(0)
        self.reset()

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            direction = joystick.read_direction(
                [JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_UP], debounce=False
            )
            if direction == JOYSTICK_LEFT:
                self.player_x = max(4, self.player_x - 1)
            elif direction == JOYSTICK_RIGHT:
                self.player_x = min(self.cpu_x - 4, self.player_x + 1)
            elif direction == JOYSTICK_UP and not self.player_jump:
                self.player_jump = 12
            if z_button and not self.last_z:
                self._punch()
            self.last_z = z_button
            self.frame += 1
            self._advance_cpu()
            if self.cpu_hp <= 0:
                set_game_over_score(self.score + self.player_hp * 25, won=True)
                return False
            if self.player_hp <= 0:
                set_game_over_score(self.score)
                return False
            self._draw()
            return True

        return step
