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
    CELL = 7
    ORIGIN_X = 4
    ORIGIN_Y = 7

    def __init__(self):
        self.reset()

    def reset(self):
        self.start = (1, 1)
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
        return (1, 3) in occupied and (6, 5) in occupied

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
