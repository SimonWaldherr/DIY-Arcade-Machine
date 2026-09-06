class PolarGame(FrameLoopGame):
    """Sort charged particles by steering a switchable magnetic field."""

    FRAME_MS = 35
    PARTICLES = (
        (15, 15, 1),
        (48, 16, -1),
        (21, 28, -1),
        (44, 31, 1),
        (14, 44, -1),
        (49, 45, 1),
    )

    def __init__(self):
        self.reset()

    def reset(self):
        self.magnet_x = 32.0
        self.magnet_y = 32.0
        self.polarity = 1
        self.particles = [
            [float(x), float(y), 0.0, 0.0, charge]
            for x, y, charge in self.PARTICLES
        ]
        self.score = 0
        self.last_z = False

    def _toggle_polarity(self):
        self.polarity = -self.polarity
        return self.polarity

    def _advance_particles(self):
        index = len(self.particles) - 1
        while index >= 0:
            particle = self.particles[index]
            dx = self.magnet_x - particle[0]
            dy = self.magnet_y - particle[1]
            distance_sq = max(20.0, dx * dx + dy * dy)
            # Opposite poles attract and equal poles repel. The capped inverse
            # square force remains stable enough for the small fixed timestep.
            force = min(0.24, 38.0 / distance_sq)
            direction = 1 if particle[4] != self.polarity else -1
            particle[2] = (particle[2] + dx * force * direction) * 0.93
            particle[3] = (particle[3] + dy * force * direction) * 0.93
            particle[0] += particle[2]
            particle[1] += particle[3]

            if particle[1] < 10 or particle[1] > 53:
                particle[1] = clamp(particle[1], 10, 53)
                particle[3] *= -0.7

            correct_collector = (
                particle[0] <= 3 and particle[4] < 0
            ) or (particle[0] >= 60 and particle[4] > 0)
            if correct_collector:
                self.score += 100
                self.particles.pop(index)
            elif particle[0] < 3 or particle[0] > 60:
                particle[0] = clamp(particle[0], 3, 60)
                particle[2] *= -0.75
                self.score = max(0, self.score - 5)
            index -= 1
        return len(self.particles)

    def _draw(self):
        display.clear()
        draw_rectangle(0, 9, 2, 54, 70, 150, 255)
        draw_rectangle(61, 9, 63, 54, 255, 90, 80)
        draw_text_small(4, 10, "-", 90, 180, 255)
        draw_text_small(55, 10, "+", 255, 110, 90)
        for x, y, unused_vx, unused_vy, charge in self.particles:
            color = (255, 90, 75) if charge > 0 else (65, 165, 255)
            draw_rectangle(int(x) - 1, int(y) - 1, int(x) + 1, int(y) + 1, *color)
        magnet_color = (255, 210, 70) if self.polarity > 0 else (90, 255, 180)
        mx = int(self.magnet_x)
        my = int(self.magnet_y)
        draw_rect_outline(mx - 3, my - 3, mx + 3, my + 3, *magnet_color)
        draw_text_small(mx - 2, my - 2, "+" if self.polarity > 0 else "-", *magnet_color)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        begin_game(0)
        self.reset()

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            direction = joystick.read_direction(
                [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT],
                debounce=False,
            )
            dx, dy = direction_to_delta(direction)
            self.magnet_x = clamp(self.magnet_x + dx * 1.5, 7, 56)
            self.magnet_y = clamp(self.magnet_y + dy * 1.5, 12, 51)
            if z_button and not self.last_z:
                self._toggle_polarity()
            self.last_z = z_button
            if self._advance_particles() == 0:
                set_game_over_score(self.score, won=True)
                return False
            self._draw()
            return True

        return step


class TimeLoopGame(FrameLoopGame):
    """Record movement loops whose ghosts hold switches for the next run."""

    FRAME_MS = 40
    MOVE_DELAY_MS = 105
    MAP = (
        "########",
        "#P..#E.#",
        "#.#.#..#",
        "#A.....#",
        "###.##.#",
        "#....B.#",
        "########",
    )
    MAPS = (MAP,
        ('########', '#P..#E.#', '#......#', '#A#.#..#', '#.#.##.#', '#....B.#', '########'),
        ('########', '#P...E.#', '#.##.#.#', '#A.....#', '#.#.##.#', '#....B.#', '########'),
    )
    CELL = 7
    ORIGIN_X = 4
    ORIGIN_Y = 7

    def __init__(self, ctx=None):
        self.map_index = int(get_context_setting(ctx, "map", 0) or 0) % len(self.MAPS)
        self.MAP = self.MAPS[self.map_index]
        self.reset()

    def reset(self):
        self.start = next((x, y) for y, row in enumerate(self.MAP) for x, cell in enumerate(row) if cell == "P")
        self.pads = tuple((x, y) for y, row in enumerate(self.MAP) for x, cell in enumerate(row) if cell in ("A", "B"))
        self.player_x, self.player_y = self.start
        self.path = [self.start]
        self.ghost_paths = []
        self.step_index = 0
        self.moves = 0
        self.won = False
        self.last_move = ticks_ms()
        self.last_z = False

    def _cell(self, x, y):
        if y < 0 or y >= len(self.MAP) or x < 0 or x >= len(self.MAP[0]):
            return "#"
        return self.MAP[y][x]

    def _ghost_positions(self):
        positions = []
        for path in self.ghost_paths:
            positions.append(path[min(self.step_index, len(path) - 1)])
        return positions

    def _pads_active(self):
        occupied = self._ghost_positions()
        occupied.append((self.player_x, self.player_y))
        return all(pad in occupied for pad in self.pads)

    def _move(self, dx, dy):
        nx = self.player_x + dx
        ny = self.player_y + dy
        if self._cell(nx, ny) == "#":
            return False
        self.player_x = nx
        self.player_y = ny
        self.path.append((nx, ny))
        self.step_index += 1
        self.moves += 1
        if self._cell(nx, ny) == "E" and self._pads_active():
            self.won = True
        return True

    def _close_loop(self):
        if len(self.path) <= 1:
            return False
        self.ghost_paths.append(tuple(self.path))
        if len(self.ghost_paths) > 2:
            self.ghost_paths.pop(0)
        self.player_x, self.player_y = self.start
        self.path = [self.start]
        self.step_index = 0
        return True

    def _draw_cell(self, x, y, color, inset=1):
        px = self.ORIGIN_X + x * self.CELL
        py = self.ORIGIN_Y + y * self.CELL
        draw_rectangle(
            px + inset,
            py + inset,
            px + self.CELL - 1 - inset,
            py + self.CELL - 1 - inset,
            *color
        )

    def _draw(self):
        display.clear()
        active = self._pads_active()
        for y, row in enumerate(self.MAP):
            for x, cell in enumerate(row):
                if cell == "#":
                    self._draw_cell(x, y, (35, 48, 72), 0)
                elif cell in ("A", "B"):
                    self._draw_cell(x, y, (80, 225, 110) if active else (180, 120, 35), 2)
                elif cell == "E":
                    self._draw_cell(x, y, (70, 255, 120) if active else (170, 50, 60), 1)
        ghost_colors = ((70, 180, 255), (200, 95, 255))
        for index, (x, y) in enumerate(self._ghost_positions()):
            self._draw_cell(x, y, ghost_colors[index % len(ghost_colors)], 2)
        self._draw_cell(self.player_x, self.player_y, (255, 235, 80), 1)
        display_score_and_time(max(0, 1000 - self.moves * 5 - len(self.ghost_paths) * 50))

    def _build_step(self, joystick):
        begin_game(0)
        self.reset()

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            now = ticks_ms()
            if ticks_diff(now, self.last_move) >= self.MOVE_DELAY_MS:
                direction = joystick.read_direction(
                    [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
                )
                dx, dy = direction_to_delta(direction)
                if (dx or dy) and self._move(dx, dy):
                    self.last_move = now
            if z_button and not self.last_z:
                self._close_loop()
            self.last_z = z_button
            if self.won:
                score = max(100, 1000 - self.moves * 5 - len(self.ghost_paths) * 50)
                set_game_over_score(score, won=True)
                return False
            self._draw()
            return True

        return step


class SlideGame(FrameLoopGame):
    """Eight-tile puzzle shuffled exclusively through legal moves."""

    FRAME_MS = 40
    MOVE_DELAY_MS = 140
    SOLVED = (1, 2, 3, 4, 5, 6, 7, 8, 0)
    DIRECTIONS = ((-1, 0), (1, 0), (0, -1), (0, 1))

    def __init__(self):
        self.reset()

    def reset(self):
        self.tiles = bytearray(self.SOLVED)
        self.blank = 8
        self.moves = 0
        previous = -1
        for unused in range(100):
            dx, dy = self.DIRECTIONS[random.randint(0, 3)]
            target = self.blank + dx + dy * 3
            if target != previous:
                old_blank = self.blank
                if self._move(dx, dy):
                    previous = old_blank
        if self._is_solved():
            self._move(-1, 0)
        self.moves = 0
        self.last_move = ticks_ms()
        self.dirty = True

    def _move(self, dx, dy):
        if abs(dx) + abs(dy) != 1:
            return False
        x, y = self.blank % 3 + dx, self.blank // 3 + dy
        if not (0 <= x < 3 and 0 <= y < 3):
            return False
        target = y * 3 + x
        self.tiles[self.blank] = self.tiles[target]
        self.tiles[target] = 0
        self.blank = target
        self.moves += 1
        self.dirty = True
        return True

    def _is_solved(self):
        return all(self.tiles[i] == self.SOLVED[i] for i in range(9))

    def _draw(self):
        # The board only changes on a move; idle frames update just the HUD.
        if self.dirty:
            display.clear()
            for index, value in enumerate(self.tiles):
                x, y = 9 + index % 3 * 16, 3 + index // 3 * 17
                if value:
                    color = (35, 125, 80) if value == index + 1 else (35, 65, 135)
                    draw_rectangle(x, y, x + 13, y + 14, *color)
                    draw_text_small(x + 5, y + 5, str(value), 255, 255, 230)
                else:
                    draw_rect_outline(x, y, x + 13, y + 14, 255, 210, 70)
            self.dirty = False
        display_score_and_time(self.moves)

    def _build_step(self, joystick):
        begin_game(0)
        self.reset()

        def step():
            c_button, unused_z = joystick.read_buttons()
            if c_button:
                return False
            now = ticks_ms()
            if ticks_diff(now, self.last_move) >= self.MOVE_DELAY_MS:
                direction = joystick.read_direction(
                    [JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_UP, JOYSTICK_DOWN]
                )
                dx, dy = direction_to_delta(direction)
                if self._move(dx, dy):
                    self.last_move = now
            self._draw()
            if self._is_solved():
                set_game_over_score(max(100, 2000 - self.moves * 10), won=True)
                return False
            return True

        return step


class CatchGame(FrameLoopGame):
    """Catch green gems and avoid red bombs across five lanes."""

    FRAME_MS = 35
    MAX_DROPS = 8
    CATCH_Y = 49

    def __init__(self):
        self.reset()

    def reset(self):
        self.lane = 2
        self.drops = []
        self.score = 0
        self.lives = 3
        self.frame = 0
        self.last_move = ticks_ms()

    def _advance(self):
        self.frame += 1
        interval = max(16, 38 - self.score // 50)
        if self.frame % interval == 0 and len(self.drops) < self.MAX_DROPS:
            self.drops.append([random.randint(0, 4), 5.0, random.randint(0, 3) == 0])
        speed = min(1.6, 0.65 + self.score / 700.0)
        # Remove in reverse order without allocating a replacement list.
        for index in range(len(self.drops) - 1, -1, -1):
            drop = self.drops[index]
            drop[1] += speed
            if drop[1] >= self.CATCH_Y:
                caught = drop[0] == self.lane
                if caught and not drop[2]:
                    self.score += 10
                elif (caught and drop[2]) or (not caught and not drop[2]):
                    self.lives = max(0, self.lives - 1)
                self.drops.pop(index)
                if not self.lives:
                    return False
        return True

    def _draw(self):
        display.clear()
        for lane in range(5):
            x = 7 + lane * 12
            draw_rectangle(x, 8, x, 46, 12, 18, 28)
        for lane, y, bomb in self.drops:
            x = 7 + lane * 12
            color = (255, 65, 60) if bomb else (70, 245, 130)
            draw_rectangle(x - 2, int(y) - 2, x + 2, int(y) + 2, *color)
            if bomb:
                display.set_pixel(x, int(y) - 3, 255, 200, 60)
        x = 7 + self.lane * 12
        draw_rectangle(x - 4, 50, x + 4, 52, 80, 180, 255)
        display.set_pixel(x - 4, 49, 80, 180, 255)
        display.set_pixel(x + 4, 49, 80, 180, 255)
        for life in range(self.lives):
            draw_rectangle(2 + life * 5, 1, 4 + life * 5, 3, 255, 90, 110)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        begin_game(0)
        self.reset()

        def step():
            c_button, unused_z = joystick.read_buttons()
            if c_button:
                return False
            now = ticks_ms()
            if ticks_diff(now, self.last_move) >= 100:
                direction = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT])
                dx, unused_dy = direction_to_delta(direction)
                if dx:
                    self.lane = clamp(self.lane + dx, 0, 4)
                    self.last_move = now
            alive = self._advance()
            self._draw()
            if not alive:
                set_game_over_score(self.score)
                return False
            return True

        return step

class BubbleShooterGame(FrameLoopGame):
    """Hex-grid color matching with wall shots and unsupported bubble drops."""

    FRAME_MS = 30
    COLORS = ((255, 75, 95), (70, 180, 255), (255, 205, 45), (100, 240, 120))
    ROWS = 9

    def __init__(self):
        self.reset()

    def reset(self):
        self.board = {}
        for row in range(4):
            for col in range(10 - row % 2):
                self.board[(row, col)] = random.randrange(len(self.COLORS))
        self.ceiling = 0
        self.aim = 6
        self.ball = None
        self.score = 0
        self.misses = 0
        self.lost = False
        self.current = self._pick_color()
        self.next_color = self._pick_color()
        self.last_z = False
        self.last_move = ticks_ms()

    def _pick_color(self):
        colors = sorted(set(self.board.values()))
        return colors[random.randrange(len(colors))] if colors else 0

    def _center(self, cell):
        row, col = cell
        return 4 + col * 6 + (row % 2) * 3, 7 + row * 5 + self.ceiling

    def _neighbors(self, cell):
        row, col = cell
        shift = 1 if row % 2 else -1
        cells = ((row, col - 1), (row, col + 1),
                 (row - 1, col), (row - 1, col + shift),
                 (row + 1, col), (row + 1, col + shift))
        return [p for p in cells if 0 <= p[0] < self.ROWS and 0 <= p[1] < 10 - p[0] % 2]

    def _connected(self, seeds, color=None):
        found = set(seeds)
        pending = list(seeds)
        while pending:
            for cell in self._neighbors(pending.pop()):
                if cell in self.board and cell not in found and (color is None or self.board[cell] == color):
                    found.add(cell)
                    pending.append(cell)
        return found

    def _resolve(self, cell):
        group = self._connected([cell], self.board[cell])
        if len(group) >= 3:
            for p in group:
                del self.board[p]
            self.score += len(group) * 10
            anchored = self._connected([p for p in self.board if p[0] == 0])
            falling = [p for p in self.board if p not in anchored]
            for p in falling:
                del self.board[p]
            self.score += len(falling) * 20
        else:
            self.misses += 1
            if self.misses == 5:
                self.misses = 0
                self.ceiling += 5
        self.lost = any(self._center(p)[1] >= 47 for p in self.board)
        # Do not offer colors that were eliminated by this shot.
        self.current = self.next_color if self.next_color in self.board.values() else self._pick_color()
        self.next_color = self._pick_color()

    def _launch(self):
        if self.ball is not None or self.lost or not self.board:
            return False
        angle = (self.aim - 6) * 0.17
        self.ball = [32.0, 52.0, math.sin(angle) * 3, -math.cos(angle) * 3, self.current]
        return True

    def _move_projectile(self, ball):
        ball[0] += ball[2] / 4
        ball[1] += ball[3] / 4
        if ball[0] < 3:
            ball[0] = 6 - ball[0]
            ball[2] = abs(ball[2])
        elif ball[0] > 60:
            ball[0] = 120 - ball[0]
            ball[2] = -abs(ball[2])

    def _contact(self, ball):
        for cell in self.board:
            x, y = self._center(cell)
            if (x - ball[0]) ** 2 + (y - ball[1]) ** 2 <= 34:
                return cell
        return None

    def _attach(self, hit):
        ball = self.ball
        candidates = self._neighbors(hit) if hit is not None else [(0, col) for col in range(10)]
        candidates = [p for p in candidates if p not in self.board]
        if not candidates:
            self.lost = True
        else:
            cell = min(candidates, key=lambda p: (self._center(p)[0] - ball[0]) ** 2 + (self._center(p)[1] - ball[1]) ** 2)
            self.board[cell] = ball[4]
            self._resolve(cell)
        self.ball = None

    def _advance(self):
        if self.ball is None:
            return
        for _ in range(4):
            self._move_projectile(self.ball)
            hit = self._contact(self.ball)
            if hit is not None or self.ball[1] <= 7 + self.ceiling:
                self._attach(hit)
                return

    def _draw_bubble(self, x, y, color):
        rgb = self.COLORS[color]
        draw_rectangle(x - 1, y - 2, x + 1, y + 2, *rgb)
        draw_line(x - 2, y - 1, x - 2, y + 1, *rgb)
        draw_line(x + 2, y - 1, x + 2, y + 1, *rgb)
        display.set_pixel(x - 1, y - 1, 255, 255, 255)

    def _draw(self):
        display.clear()
        draw_line(0, 4 + self.ceiling, 63, 4 + self.ceiling, 70, 80, 105)
        for x in range(1, 64, 4):
            display.set_pixel(x, 47, 115, 45, 55)
        for cell in self.board:
            self._draw_bubble(*self._center(cell), self.board[cell])
        if self.ball is None:
            angle = (self.aim - 6) * 0.17
            preview = [32.0, 52.0, math.sin(angle) * 3, -math.cos(angle) * 3]
            for frame in range(32):
                stopped = False
                for _ in range(4):
                    self._move_projectile(preview)
                    if self._contact(preview) is not None or preview[1] <= 7 + self.ceiling:
                        stopped = True
                        break
                if stopped:
                    break
                if frame % 2 == 0:
                    display.set_pixel(int(preview[0]), int(preview[1]), 100, 110, 130)
            self._draw_bubble(32, 52, self.current)
        else:
            self._draw_bubble(int(self.ball[0]), int(self.ball[1]), self.ball[4])
        self._draw_bubble(57, 52, self.next_color)
        for i in range(5 - self.misses):
            display.set_pixel(3 + i * 3, 53, 210, 210, 230)
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
            if self.ball is None and ticks_diff(now, self.last_move) >= 90:
                if direction == JOYSTICK_LEFT:
                    self.aim = max(0, self.aim - 1)
                    self.last_move = now
                elif direction == JOYSTICK_RIGHT:
                    self.aim = min(12, self.aim + 1)
                    self.last_move = now
            if z_button and not self.last_z:
                self._launch()
            self.last_z = z_button
            self._advance()
            if self.lost or not self.board:
                set_game_over_score(self.score, won=not self.lost)
                return False
            self._draw()
            return True

        return step
