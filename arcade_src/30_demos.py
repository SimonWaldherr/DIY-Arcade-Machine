class CpuPlayerJoystick:
    """State-aware CPU controls for game attract demos."""

    def __init__(self, real_joystick, game_name, game, duration_ms=9000):
        self.real = real_joystick
        self.name = game_name
        self.game = game
        self.end_ms = ticks_ms() + duration_ms
        self._dir = None
        self._z = False
        self._last = 0
        self._pulse_until = 0
        self._script_i = 0

    def _exit_requested(self):
        c, z = self.real.read_buttons()
        if c or z or ticks_diff(ticks_ms(), self.end_ms) >= 0:
            return True
        d = self.real.read_direction(
            [JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_UP, JOYSTICK_DOWN]
        )
        return d is not None

    def _toward_x(self, x, target, dead=1):
        if x < target - dead:
            return JOYSTICK_RIGHT
        if x > target + dead:
            return JOYSTICK_LEFT
        return None

    def _toward_y(self, y, target, dead=1):
        if y < target - dead:
            return JOYSTICK_DOWN
        if y > target + dead:
            return JOYSTICK_UP
        return None

    def _pulse_z(self, ms=90):
        self._pulse_until = ticks_ms() + ms

    def _choose_2048_dir(self, g):
        dir_tokens = (JOYSTICK_UP, JOYSTICK_RIGHT, JOYSTICK_DOWN, JOYSTICK_LEFT)
        best_dir = JOYSTICK_DOWN
        best_score = -999999
        old_grid = list(g.grid)
        old_score = g.score
        old_moves = g.moves
        old_max = g.max_val
        old_victory = g.victory
        for idx, token in enumerate(dir_tokens):
            g.grid = list(old_grid)
            g.score = old_score
            g.moves = old_moves
            g.max_val = old_max
            g.victory = old_victory
            if not g._move(idx):
                continue
            empty = 0
            merge = 0
            smooth = 0
            for y in range(g.GRID_H):
                for x in range(g.GRID_W):
                    v = g.grid[g._idx(x, y)]
                    if not v:
                        empty += 1
                        continue
                    if x + 1 < g.GRID_W:
                        nv = g.grid[g._idx(x + 1, y)]
                        if nv == v:
                            merge += v
                        elif nv:
                            smooth -= abs(v - nv) // 2
                    if y + 1 < g.GRID_H:
                        nv = g.grid[g._idx(x, y + 1)]
                        if nv == v:
                            merge += v
                        elif nv:
                            smooth -= abs(v - nv) // 2
            corner = max(
                g.grid[g._idx(0, g.GRID_H - 1)],
                g.grid[g._idx(g.GRID_W - 1, g.GRID_H - 1)],
            )
            score = (
                empty * 900
                + merge * 6
                + corner * 3
                + smooth
                + (60 if token in (JOYSTICK_DOWN, JOYSTICK_LEFT) else 0)
            )
            if score > best_score:
                best_score = score
                best_dir = token
        g.grid = old_grid
        g.score = old_score
        g.moves = old_moves
        g.max_val = old_max
        g.victory = old_victory
        return best_dir

    def _choose_tetris_dir(self, g):
        piece = g.current
        best_x = piece.x
        best_rot = piece.shape
        best_score = -999999
        rotations = []
        shape = piece.shape
        for _ in range(4):
            if shape not in rotations:
                rotations.append(shape)
            shape = tuple(tuple(row) for row in zip(*shape[::-1]))
        old_shape = piece.shape
        for shape in rotations:
            width = len(shape[0])
            for x in range(0, g.GRID_WIDTH - width + 1):
                y = piece.y
                while g.valid(
                    piece, dx=x - piece.x, dy=(y + 1) - piece.y, rotated_shape=shape
                ):
                    y += 1
                landing = y
                holes = 0
                heights = [0] * g.GRID_WIDTH
                tmp = bytearray(g.locked)
                for yy, row in enumerate(shape):
                    for xx, cell in enumerate(row):
                        if cell and 0 <= landing + yy < g.GRID_HEIGHT:
                            tmp[(landing + yy) * g.GRID_WIDTH + x + xx] = 1
                for cx in range(g.GRID_WIDTH):
                    seen = False
                    for cy in range(g.GRID_HEIGHT):
                        if tmp[cy * g.GRID_WIDTH + cx]:
                            if not seen:
                                heights[cx] = g.GRID_HEIGHT - cy
                            seen = True
                        elif seen:
                            holes += 1
                bump = 0
                for i in range(g.GRID_WIDTH - 1):
                    bump += abs(heights[i] - heights[i + 1])
                score = landing * 12 - holes * 80 - bump * 5 - max(heights) * 2
                if score > best_score:
                    best_score = score
                    best_x = x
                    best_rot = shape
        if old_shape != best_rot:
            self._pulse_z(80)
            return None
        if piece.x < best_x:
            return JOYSTICK_RIGHT
        if piece.x > best_x:
            return JOYSTICK_LEFT
        return JOYSTICK_DOWN

    def _safe_frogger_dir(self, g):
        moves = (JOYSTICK_UP, JOYSTICK_LEFT, JOYSTICK_RIGHT, None)
        best = None
        best_score = -99999
        for d in moves:
            dx, dy = direction_to_delta(d) if d else (0, 0)
            px = clamp(g.player_x + dx * 4, 0, WIDTH - g.PLAYER_W)
            py = clamp(g.player_y + dy * 4, 0, PLAY_HEIGHT - g.PLAYER_H)
            risk = 0
            for lane in g.lanes:
                y = lane[0]
                for car in lane[2]:
                    cx = int(car[0] + lane[1] * 4)
                    if rects_overlap(
                        px, py, g.PLAYER_W, g.PLAYER_H, cx - 1, y, int(car[1]) + 2, 3
                    ):
                        risk += 1000
            score = (PLAY_HEIGHT - py) * 10 - risk - abs(px - WIDTH // 2)
            if score > best_score:
                best_score = score
                best = d
        return best

    def _compute(self):
        now = ticks_ms()
        if ticks_diff(now, self._last) < 55:
            self._z = ticks_diff(self._pulse_until, now) > 0
            return
        self._last = now
        g = self.game
        n = self.name
        d = None

        if hasattr(g, "ball_x") and hasattr(g, "paddle_x"):
            target = float(g.ball_x)
            if getattr(g, "ball_dy", 0) > 0:
                target = float(g.ball_x)
                vx = float(getattr(g, "ball_dx", 0))
                vy = float(getattr(g, "ball_dy", 1))
                y = float(g.ball_y)
                while y < g.paddle_y and 0 <= target <= WIDTH - 2:
                    target += vx
                    y += vy
                    if target <= 0 or target >= WIDTH - 2:
                        vx = -vx
            else:
                bricks = getattr(g, "bricks", None)
                if bricks:
                    target = (
                        min(
                            bricks,
                            key=lambda b: abs((b[0] + BRICK_WIDTH // 2) - g.ball_x),
                        )[0]
                        + BRICK_WIDTH // 2
                    )
            d = self._toward_x(g.paddle_x + PADDLE_WIDTH // 2, int(target), 1)
        elif hasattr(g, "ball_position") and hasattr(g, "left_paddle_y"):
            target = int(g.ball_position[1])
            if g.ball_speed[0] < 0:
                y = float(g.ball_position[1])
                vy = float(g.ball_speed[1])
                x = float(g.ball_position[0])
                while x > g.left_paddle_x + 1:
                    x += g.ball_speed[0]
                    y += vy
                    if y <= 0 or y >= PLAY_HEIGHT - 1:
                        vy = -vy
                        y = clamp(y, 0, PLAY_HEIGHT - 1)
                target = int(y)
            d = self._toward_y(g.left_paddle_y + g.paddle_height // 2, target, 1)
        elif n == "STACK" and hasattr(g, "bar_x"):
            target = getattr(g, "prev_x", 0)
            if abs(g.bar_x - target) <= max(1, getattr(g, "speed", 1)):
                self._pulse_z(80)
        elif n == "FLAPPY" and hasattr(g, "pipes"):
            target = PLAY_HEIGHT // 2
            for p in g.pipes:
                if p["x"] + g.pipe_w >= g.bx - 1:
                    target = p["gy"] - 2
                    break
            if g.by + max(0, g.vy) > target:
                self._pulse_z(80)
            d = JOYSTICK_UP if ticks_diff(self._pulse_until, now) > 0 else None
        elif n == "FROGGR" and hasattr(g, "lanes"):
            d = self._safe_frogger_dir(g)
        elif n == "INVADR" and hasattr(g, "aliens"):
            live = [a for a in g.aliens if a[2]]
            bottom = []
            for a in live:
                col = (a[0] - 1) // 7
                if not any(
                    o[2] and ((o[0] - 1) // 7) == col and o[1] > a[1] for o in live
                ):
                    bottom.append(a)
            target = (
                min(bottom or live, key=lambda a: abs((a[0] + 2) - g.player_x))[0] + 2
                if live
                else WIDTH // 2
            )
            for bomb in getattr(g, "bombs", []):
                if bomb[1] > PLAY_HEIGHT - 18 and abs(bomb[0] - g.player_x) < 5:
                    target = 2 if g.player_x > WIDTH // 2 else WIDTH - 3
            d = self._toward_x(g.player_x, target, 1)
            if abs(g.player_x - target) <= 2 and g.bullet is None:
                self._pulse_z(80)
        elif n == "ASTRD" and hasattr(g, "asteroids"):
            if g.asteroids:
                ship = g.ship
                a = min(
                    g.asteroids,
                    key=lambda aa: (aa.x - ship.x) ** 2 + (aa.y - ship.y) ** 2,
                )
                target = (
                    math.degrees(math.atan2(-(a.y - ship.y), a.x - ship.x)) + 360
                ) % 360
                delta = ((target - ship.angle + 180) % 360) - 180
                if abs(delta) < 18:
                    self._pulse_z(90)
                    d = JOYSTICK_UP
                elif delta > 0:
                    d = JOYSTICK_LEFT
                else:
                    d = JOYSTICK_RIGHT
        elif n == "TRON" and hasattr(g, "_clear_distance_from"):
            cur = g.direction
            left = g._LEFT_TURN[cur]
            right = g._RIGHT_TURN[cur]
            options = (
                (g._clear_distance_from(g.head_x, g.head_y, cur), None),
                (g._clear_distance_from(g.head_x, g.head_y, left), JOYSTICK_LEFT),
                (g._clear_distance_from(g.head_x, g.head_y, right), JOYSTICK_RIGHT),
            )
            d = max(options, key=lambda item: item[0])[1]
        elif n == "DOOMLT" and hasattr(g, "enemies"):
            alive = [e for e in g.enemies if e[2] > 0]
            if alive:
                e = min(alive, key=lambda ee: (ee[0] - g.px) ** 2 + (ee[1] - g.py) ** 2)
                target = g._angle_to_units(e[0] - g.px, e[1] - g.py)
                delta = g._angle_delta(target, g.ang)
                if abs(delta) <= 5:
                    self._pulse_z(90)
                    d = JOYSTICK_UP
                else:
                    d = JOYSTICK_LEFT if delta > 0 else JOYSTICK_RIGHT
            else:
                d = JOYSTICK_UP
        elif n == "RAYRCR" and hasattr(g, "objects"):
            target = 0.0
            for obj in g.objects:
                rel = obj[0] - g.pos
                if 4.0 < rel < 32.0:
                    lane = g._object_lane(obj)
                    if obj[2] == 2:
                        target = lane
                        break
                    if abs(g.lane - lane) < 0.48:
                        target = -0.78 if lane > 0 else 0.78
                        break
            if g.lane < target - 0.10:
                d = JOYSTICK_UP_RIGHT
            elif g.lane > target + 0.10:
                d = JOYSTICK_UP_LEFT
            else:
                d = JOYSTICK_UP
            self._dir = d
            self._z = bool(
                getattr(g, "energy", 0) > 28
                and getattr(g, "speed", 0) > 0.75
                and abs(g.lane) < 0.88
            )
            return
        elif n == "2048" and hasattr(g, "grid"):
            # Keep the board biased toward one corner, the standard simple 2048 CPU.
            d = self._choose_2048_dir(g)
        elif n == "TETRIS" and hasattr(g, "current"):
            d = self._choose_tetris_dir(g)
        elif hasattr(g, "cur_x") and hasattr(g, "cur_y"):
            script = (JOYSTICK_RIGHT, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_UP)
            self._script_i = (self._script_i + 1) & 31
            d = script[(self._script_i >> 3) & 3]
            if (self._script_i & 15) == 0:
                self._pulse_z(70)
        elif hasattr(g, "px") and hasattr(g, "py") and hasattr(g, "_try_move"):
            # Sokoban-like previews: walk the level and occasionally push/undo.
            script = (JOYSTICK_RIGHT, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_UP)
            self._script_i = (self._script_i + 1) & 31
            d = script[(self._script_i >> 3) & 3]
        else:
            script = (JOYSTICK_LEFT, JOYSTICK_UP, JOYSTICK_RIGHT, JOYSTICK_DOWN)
            self._script_i = (self._script_i + 1) & 31
            d = script[(self._script_i >> 3) & 3]
            if (self._script_i & 7) == 0:
                self._pulse_z(70)

        self._dir = d
        self._z = ticks_diff(self._pulse_until, now) > 0

    def read_buttons(self):
        if self._exit_requested():
            return True, False
        self._compute()
        return False, self._z

    def read_direction(self, possible_directions, debounce=True):
        if self._exit_requested():
            return None
        self._compute()
        if self._dir in possible_directions:
            return self._dir
        return None

    def is_pressed(self):
        return self.read_buttons()[1]


class DemosGame:
    """
    DEMOS
    Controls:
      - Left / Right: switch demo
      - C: return to menu
    """

    FRAME_MS = 35
    TARGET_HEAVY_FRAME_MS = 45
    HEAVY_EFFECTS = (
        "MANDEL",
        "BOIDS",
        "NBODY",
        "METAB",
        "GRAV",
        "RIPPLE",
        "FIRWRK",
        "PHYLLO",
        "LISSAJO",
        "PENDUL",
        "WINMAZE",
    )
    MAX_RADAR_BLIPS = 18
    MAX_FIREWORK_PARTICLES = 56 if CONFIG_LOW_RAM_MODE else 104
    GAME_DEMOS = (
        "2048",
        "ARENA",
        "ARTILL",
        "ASTRD",
        "BEJWL",
        "BOMBER",
        "BRKOUT",
        "BTLZON",
        "CAVEFL",
        "CENTI",
        "CGOLG",
        "CLIMB",
        "COLMNS",
        "DEFUSE",
        "DIGDUG",
        "DOOMLT",
        "FLAPPY",
        "FROGGR",
        "GALAXY",
        "GOLF",
        "INVADR",
        "JOUST",
        "KEEN",
        "LANDER",
        "LASER",
        "LOCO",
        "MAZE",
        "MINES",
        "ORBIT",
        "ORBTAL",
        "PACMAN",
        "PAIRS",
        "PINBAL",
        "PITFAL",
        "PONG",
        "QIX",
        "RAYRCR",
        "REVRS",
        "RTYPE",
        "SABOTR",
        "SIMON",
        "SNAKE",
        "SOCCER",
        "SOKO",
        "STACK",
        "TETRIS",
        "TRON",
        "TWRDEF",
        "STKARC",
        "UFODEF",
        "AIRHKY",
    )
    GAME_CLASS_NAMES = {
        "2048": "Game2048",
        "ARENA": "ArenaGame",
        "ARTILL": "ArtilleryGame",
        "ASTRD": "AsteroidGame",
        "BEJWL": "BejeweledGame",
        "BOMBER": "BomberGame",
        "BRKOUT": "BreakoutGame",
        "BTLZON": "BattlezoneGame",
        "CAVEFL": "CaveFlyGame",
        "CENTI": "CentipedeGame",
        "CGOLG": "CgolgGame",
        "CLIMB": "ClimberGame",
        "COLMNS": "ColumnsGame",
        "DEFUSE": "DefuseGame",
        "DIGDUG": "DigDugGame",
        "DOOMLT": "DoomLiteGame",
        "FLAPPY": "FlappyGame",
        "FROGGR": "FroggerGame",
        "GALAXY": "GalaxyGame",
        "GOLF": "GolfGame",
        "INVADR": "InvaderGame",
        "JOUST": "JoustGame",
        "KEEN": "KeenGame",
        "LANDER": "LunarLanderGame",
        "LASER": "LaserGame",
        "LOCO": "LocoMotionGame",
        "MAZE": "MazeGame",
        "MINES": "MinesGame",
        "ORBIT": "OrbitGame",
        "ORBTAL": "OrbitalGame",
        "PACMAN": "PacmanGame",
        "PAIRS": "PairsGame",
        "PINBAL": "PinballGame",
        "PITFAL": "PitfallGame",
        "PONG": "PongGame",
        "AIRHKY": "AirHockeyGame",
        "QIX": "QixGame",
        "RAYRCR": "RayRacerGame",
        "REVRS": "OthelloGame",
        "RTYPE": "RTypeGame",
        "SABOTR": "SabotrGame",
        "SIMON": "SimonGame",
        "SNAKE": "SnakeGame",
        "SOCCER": "SoccerGame",
        "SOKO": "SokobanGame",
        "STACK": "StackerGame",
        "STKARC": "StickArcherGame",
        "TETRIS": "TetrisGame",
        "TRON": "TronGame",
        "TWRDEF": "TowerDefenseGame",
        "UFODEF": "UFODefenseGame",
    }

    def __init__(self, ctx=None):
        self.slideshow_ms = int(get_context_setting(ctx, "slide_ms", 60000) or 60000)
        self.random_order = get_context_setting(ctx, "order", "sorted") == "random"
        self.clock_enabled = bool(get_context_setting(ctx, "clock", False))
        self.clock_source = get_context_setting(ctx, "clock_source", "rtc")
        self.clock_hour = int(get_context_setting(ctx, "clock_hour", 12) or 0) % 24
        self.clock_minute = int(get_context_setting(ctx, "clock_minute", 0) or 0) % 60
        self._clock_start_ms = ticks_ms()
        # Generated demo registry. GAME_DEMOS above contains CPU-played game
        # previews; this list contains effects implemented directly in
        # DemosGame. To add an effect: list it here, reset its state in
        # _reset_demo_state(), and dispatch init/step below. The low-RAM subset
        # avoids larger buffers and dense per-pixel math.
        effects = (
            (
                "SNAKE",
                "LIFE",
                "CUBE",
                "VORTEX",
                "COMETS",
                "SPARK",
                "RINGS",
                "GRAV",
                "SPRING",
                "CRADLE",
            )
            if CONFIG_LOW_RAM_MODE
            else (
                "SNAKE",
                "PLASMA",
                "CUBE",
                "ORBIT",
                "WARP",
                "BOUNCE",
                "VORTEX",
                "COMETS",
                "TUNNEL",
                "MYSTIFY",
                "LIFE",
                "ANTS",
                "FLOOD",
                "FIRE",
                "MATRIX",
                "STARS",
                "SPARK",
                "RINGS",
                "RADAR",
                "MANDEL",
                "BOIDS",
                "NBODY",
                "METAB",
                "GRAV",
                "RIPPLE",
                "FIRWRK",
                "SPRING",
                "CRADLE",
                "PHYLLO",
                "LISSAJO",
                "PENDUL",
                "ARCADE",
                "CRT",
                "WINMAZE",
            )
        )
        effects = tuple(
            name
            for name in effects
            if _name_enabled(name, CONFIG_ENABLED_DEMOS, CONFIG_DISABLED_DEMOS)
        )
        game_demos = tuple(
            "G:" + name
            for name in self.GAME_DEMOS
            if _name_enabled("G:" + name, CONFIG_ENABLED_DEMOS, CONFIG_DISABLED_DEMOS)
            and _name_enabled(name, CONFIG_ENABLED_GAMES, CONFIG_DISABLED_GAMES)
        )

        self.demos = game_demos + effects if CONFIG_ENABLE_GAME_DEMOS else effects
        self.idx = 0
        if self.random_order and len(self.demos) > 1:
            self.idx = random.randint(0, len(self.demos) - 1)
        self._init = False
        self._last_move = ticks_ms()
        self._slide_started_ms = self._last_move
        self._move_delay = 180
        self._game_demo_wait_ms = 850
        self._reset_demo_state()

    def _frame_ms_for_demo(self, demo):
        """Keep math-heavy effects responsive on constrained render targets."""
        if demo in self.HEAVY_EFFECTS and (CONFIG_LOW_RAM_MODE or IS_WEB):
            return self.TARGET_HEAVY_FRAME_MS
        return self.FRAME_MS

    def _demo_clock_text(self):
        if not self.clock_enabled:
            return None
        if self.clock_source == "rtc":
            try:
                year, month, day, weekday, hour, minute, second, _ = rtc.datetime()
                return "{:02}:{:02}".format(hour, minute)
            except Exception:
                pass
        elapsed_min = max(0, ticks_diff(ticks_ms(), self._clock_start_ms) // 60000)
        total = (self.clock_hour * 60 + self.clock_minute + elapsed_min) % (24 * 60)
        return "{:02}:{:02}".format(total // 60, total % 60)

    def _draw_clock_overlay(self):
        txt = self._demo_clock_text()
        if not txt:
            return
        x = WIDTH - len(txt) * 6 - 1
        draw_rectangle(x - 1, 0, WIDTH - 1, 6, 0, 0, 0)
        draw_text_small(x, 1, txt, 230, 230, 230)

    def _demo_disc(self, cx, cy, radius, color):
        r2 = radius * radius
        x0 = int(cx - radius)
        x1 = int(cx + radius)
        y0 = int(cy - radius)
        y1 = int(cy + radius)
        for yy in range(y0, y1 + 1):
            if yy < 0 or yy >= HEIGHT:
                continue
            dy = yy - cy
            for xx in range(x0, x1 + 1):
                if xx < 0 or xx >= WIDTH:
                    continue
                dx = xx - cx
                if dx * dx + dy * dy <= r2:
                    set_pixel_clipped(xx, yy, color[0], color[1], color[2])

    def _reset_demo_state(self):
        # shared
        self._init = False
        self._frame = 0
        self._demo_w = WIDTH
        self._demo_h = HEIGHT

        # LIFE (2x2 scaled)
        self._life_w = 32
        self._life_h = 32
        self._life_cur = None
        self._life_nxt = None
        self._life_prev = None

        # ANTS (multi Langton ants)
        self._ants_w = WIDTH
        self._ants_h = HEIGHT
        self._ants_cells = None  # bytearray: 0 dead, 1 alive
        self._ants = []
        self._ants_prev = []
        self._ants_changed = []

        # FLOOD (flood fill through random maze)
        self._flood_w = WIDTH
        self._flood_h = HEIGHT
        # values: 0 empty, 1 line, 2 floodfill, 3 enemy, 4 queued, 5 line
        self._flood = None
        self._flood_vis = None
        self._flood_q = None  # bytearray queue of packed (y<<8)|x
        self._flood_q_head = 0
        self._flood_q_tail = 0
        self._flood_steps = 0
        self._flood_max_steps = 4000  # scaled from 16000 @ 128x128

        # FIRE (doom-fire)
        self._fire_w = WIDTH
        self._fire_h = HEIGHT
        self._fire = None
        self._fire_prev = None

        # MATRIX (falling green rain)
        self._matrix_drops = []

        # STARS (3d starfield)
        self._stars = []

        # MYSTIFY (bouncing polygons/lines)
        self._mystify_pts = []
        self._mystify_history = []
        self._mystify_hue = 0.0

        # PLASMA effect
        self._plasma_time = 0
        self._plasma_palette = []
        self._plasma_sin = []

        # TUNNEL
        self._tunnel_phase = 0

        # ORBIT
        self._orbit_phase = 0

        # WARP
        self._warp_stars = []
        self._warp_phase = 0

        # VORTEX
        self._vortex_phase = 0

        # COMETS
        self._comets = []

        # BOUNCE
        self._bounce_x = 0
        self._bounce_y = 0
        self._bounce_dx = 1
        self._bounce_dy = 1
        self._bounce_hue = 0

        # SNAKE
        self._snake = [(WIDTH // 2, HEIGHT // 2)]
        self._snake_length = 3
        self._snake_dir = "UP"
        self._snake_score = 0
        self._snake_target = (WIDTH // 2, HEIGHT // 2)
        self._snake_green_targets = []  # list of (x,y,lifespan)
        self._snake_step_counter = 0
        self._snake_step_counter2 = 0

        # SPARK
        self._spark_particles = []

        # RINGS
        self._rings_phase = 0

        # RADAR
        self._radar_phase = 0
        self._radar_blips = []
        self._radar_rings = ()

        # MANDEL
        self._mandel_y = 0
        self._mandel_pass = 0
        self._mandel_palette = []
        self._mandel_xs = []
        self._mandel_params = None

        # BOIDS
        self._boids = []

        # NBODY
        self._nbody = []

        # METAB: moving influence points sampled on a 2x2 grid, giving a
        # liquid/metaball look without framebuffer readback or alpha blending.
        self._metab_balls = []
        self._metab_phase = 0

        # GRAV: compact particle state integrated around two moving attractors.
        self._grav_particles = []
        self._grav_phase = 0

        # SPRING: a dangling spring-mass chain with gravity and damping.
        self._spring_nodes = []
        self._spring_phase = 0
        self._spring_rest = 0.0

        # CRADLE: Newton's cradle with string constraints and elastic transfer.
        self._cradle_bobs = []
        self._cradle_phase = 0
        self._cradle_length = 0.0

        # RIPPLE: integer water height-field (two buffers) at half resolution,
        # rendered as 2x2 blocks. Raindrops perturb the field periodically.
        self._ripple_w = 32
        self._ripple_h = 32
        self._ripple_cur = None
        self._ripple_prev = None

        # FIRWRK: rising rockets that burst into gravity-bound spark showers.
        self._fw_rockets = []
        self._fw_particles = []

        # PHYLLO: golden-angle phyllotaxis spiral (sunflower seed packing).
        self._phyllo_phase = 0.0

        # LISSAJO: oscilloscope Lissajous curve with drifting frequency ratio.
        self._liss_phase = 0.0

        # PENDUL: chaotic double pendulum with a fading tip trail.
        self._pend_a1 = 0.0
        self._pend_a2 = 0.0
        self._pend_w1 = 0.0
        self._pend_w2 = 0.0
        self._pend_trail = []

        # ARCADE: self-playing Breakout attract demo.
        self._arc_bricks = None
        self._arc_ball = None
        self._arc_paddle = 0.0
        self._arc_game = None
        self._arc_cpu = None

        # CRT
        self._crt_phase = 0

        # WINMAZE
        self._winmaze = None
        self._winmaze_dir = 0
        self._winmaze_target_ang = 0
        self._winmaze_path_phase = 0

        self._game_demo_name = None
        self._game_demo_selected_ms = 0
        self._last_sound_ms = 0

    def _demo_sound(self, kind, tone=0, min_gap_ms=90):
        now = ticks_ms()
        if ticks_diff(now, self._last_sound_ms) < min_gap_ms:
            return
        self._last_sound_ms = now
        play_sound(kind, tone)

    def _life_step(self, w, h, cur, nxt):
        for y in range(h):
            ym1 = (y - 1) % h
            yp1 = (y + 1) % h
            row = y * w
            rowm1 = ym1 * w
            rowp1 = yp1 * w
            for x in range(w):
                xm1 = (x - 1) % w
                xp1 = (x + 1) % w
                i = row + x
                n = (
                    cur[rowm1 + xm1]
                    + cur[rowm1 + x]
                    + cur[rowm1 + xp1]
                    + cur[row + xm1]
                    + cur[row + xp1]
                    + cur[rowp1 + xm1]
                    + cur[rowp1 + x]
                    + cur[rowp1 + xp1]
                )
                if cur[i]:
                    nxt[i] = 1 if (n == 2 or n == 3) else 0
                else:
                    nxt[i] = 1 if (n == 3) else 0

    def _life_draw_diffs(self, w, h, cur, prev):
        # diff-draw at 2x2 scale (no full clear)
        for y in range(h):
            row = y * w
            for x in range(w):
                i = row + x
                v = cur[i]
                if v == prev[i]:
                    continue
                prev[i] = v
                px = x * 2
                py = y * 2
                if py >= HEIGHT:
                    continue
                if v:
                    r, g, b = 0, 180, 0
                else:
                    r, g, b = 0, 0, 0
                display.set_pixel(px, py, r, g, b)
                if px + 1 < WIDTH:
                    display.set_pixel(px + 1, py, r, g, b)
                if py + 1 < HEIGHT:
                    display.set_pixel(px, py + 1, r, g, b)
                    if px + 1 < WIDTH:
                        display.set_pixel(px + 1, py + 1, r, g, b)

    def _ants_init(self):
        # Match original "game_of_ants" look:
        # - dead: black
        # - alive base: (155,155,155)
        # - alive trail: dim ant color
        # - ants: bright unique colors
        w = self._ants_w
        h = self._ants_h

        self._ants_cells = bytearray(w * h)
        for i in range(w * h):
            self._ants_cells[i] = 1 if random.randint(0, 7) == 0 else 0

        # init ants: [x,y,dir,r,g,b]
        self._ants = []
        self._ants_prev = []
        self._ants_changed = []
        n = 8
        for _ in range(n):
            ax = random.randint(0, w - 1)
            ay = random.randint(0, h - 1)
            ad = random.randint(0, 3)
            r, g, b = hsb_to_rgb(random.randint(0, 360), 1, 1)
            self._ants.append([ax, ay, ad, r, g, b])
            self._ants_prev.append((ax, ay))

        display.clear()
        # draw initial grid (alive base)
        for y in range(h):
            row = y * w
            for x in range(w):
                if self._ants_cells[row + x]:
                    display.set_pixel(x, y, 155, 155, 155)
        # draw ants
        for ant in self._ants:
            display.set_pixel(ant[0], ant[1], ant[3], ant[4], ant[5])

    def _ants_step(self):
        w = self._ants_w
        h = self._ants_h
        cells = self._ants_cells
        ants = self._ants

        # These short-lived work lists are reused every frame. That is much
        # friendlier to the MicroPython allocator than rebuilding them at 28 FPS.
        prev_positions = self._ants_prev
        changed = self._ants_changed
        del prev_positions[:]
        del changed[:]

        # 1) update ants + grid state
        for ant in ants:
            x = ant[0]
            y = ant[1]
            d = ant[2]
            r = ant[3]
            g = ant[4]
            b = ant[5]

            prev_positions.append((x, y))
            i = y * w + x
            state = cells[i]
            if state == 0:
                if random.randint(0, 3) == 0:
                    d = random.randint(0, 3)
                else:
                    d = (d - 1) & 3
                cells[i] = 1
                changed.append((x, y, 1, r, g, b))
            else:
                d = (d + 1) & 3
                cells[i] = 0
                changed.append((x, y, 0, 0, 0, 0))

            # move
            if d == 0:
                y = (y - 1) % h
            elif d == 1:
                x = (x + 1) % w
            elif d == 2:
                y = (y + 1) % h
            else:
                x = (x - 1) % w

            ant[0], ant[1], ant[2] = x, y, d

        # 2) erase ants from previous positions (restore base cell colors)
        for x, y in prev_positions:
            if cells[y * w + x]:
                display.set_pixel(x, y, 155, 155, 155)
            else:
                display.set_pixel(x, y, 0, 0, 0)

        # 3) apply changed cells (dim colored trails)
        for x, y, st, r, g, b in changed:
            if st:
                display.set_pixel(x, y, r // 2, g // 2, b // 2)
            else:
                display.set_pixel(x, y, 0, 0, 0)

        # 4) draw ants in new positions
        for ant in ants:
            display.set_pixel(ant[0], ant[1], ant[3], ant[4], ant[5])

    def _flood_init(self):
        # Closely matches hub75/floodfill_maze_on_hub75_128x128.py, optimized for 64x64.
        w = self._flood_w
        h = self._flood_h

        try:
            gc.collect()
        except Exception:
            pass

        if self._flood is None or len(self._flood) != w * h:
            self._flood = bytearray(w * h)
        else:
            for i in range(w * h):
                self._flood[i] = 0

        if self._flood_vis is None or len(self._flood_vis) != w * h:
            self._flood_vis = bytearray(w * h)
        else:
            for i in range(w * h):
                self._flood_vis[i] = 0

        if self._flood_q is None or len(self._flood_q) != w * h * 2:
            self._flood_q = bytearray(w * h * 2)

        self._flood_q_head = 0
        self._flood_q_tail = 0
        self._flood_steps = 0

        g = self._flood
        visited = self._flood_vis

        border = 24  # 48 @ 128 scaled to 64
        step = 4  # 8 @ 128 scaled to 64

        # Start near center like reference
        sx = random.randint(border // 2, min(w - 2, w - border // 2))
        sy = random.randint(border // 2, min(h - 2, h - border // 2))

        # Fixed-size stack for DFS nodes (step grid is about (w/step)*(h/step)).
        max_nodes = (w // step) * (h // step)
        stack = bytearray(max_nodes * 2)
        sp = 0

        def stack_push(v):
            nonlocal sp
            stack[sp] = v & 0xFF
            stack[sp + 1] = (v >> 8) & 0xFF
            sp += 2

        def stack_top():
            return stack[sp - 2] | (stack[sp - 1] << 8)

        def stack_pop():
            nonlocal sp
            sp -= 2

        def mark_line(px, py, v=1):
            g[py * w + px] = v
            display.set_pixel(px, py, 255, 255, 255)

        display.clear()

        stack_push((sy << 6) | sx)
        visited[sy * w + sx] = 1

        dirs = [(0, step), (0, -step), (step, 0), (-step, 0)]
        while sp:
            v = stack_top()
            x = v & 0x3F
            y = v >> 6

            dir_order = [0, 1, 2, 3]
            _shuffle_in_place(dir_order)

            found = False
            for di in dir_order:
                dx, dy = dirs[di]
                nx = x + dx
                ny = y + dy
                if not (0 < nx < w and 0 < ny < h):
                    continue
                ii = ny * w + nx
                if visited[ii]:
                    continue

                sx1 = dx // step
                sy1 = dy // step
                for i in range(1, step):
                    mark_line(x + sx1 * i, y + sy1 * i, 1)

                # endpoint in reference uses value 5
                mark_line(nx, ny, 5)

                visited[ii] = 1
                stack_push((ny << 6) | nx)
                found = True
                break

            if not found:
                stack_pop()

        # Choose "enemy" start in central border area on empty cell
        while True:
            ex = random.randint(border, w - border - 1)
            ey = random.randint(border, h - border - 1)
            idx = ey * w + ex
            if g[idx] == 0:
                g[idx] = 3
                break

        # enqueue start (do not overwrite enemy)
        bi = self._flood_q_tail * 2
        self._flood_q[bi] = ex & 0xFF
        self._flood_q[bi + 1] = ey & 0xFF
        self._flood_q_tail += 1

    def _flood_step(self):
        w = self._flood_w
        h = self._flood_h
        q = self._flood_q
        head = self._flood_q_head
        tail = self._flood_q_tail
        g = self._flood
        max_steps = self._flood_max_steps

        # expand a bunch per frame
        n = 260
        while n > 0:
            n -= 1
            if head >= tail or self._flood_steps >= max_steps:
                self._flood_init()
                return
            bi = head * 2
            # stored as bytes: x then y
            x = q[bi]
            y = q[bi + 1]
            head += 1
            i = y * w + x
            gv = g[i]
            # match reference: allow flood on empty and enemy; leave lines intact
            if gv != 0 and gv != 3 and gv != 4:
                continue
            # visit
            g[i] = 2
            if gv != 3:
                hue = (self._flood_steps * 360) // max_steps
                r, gg, b = hsb_to_rgb(hue, 1.0, 1.0)
                display.set_pixel(x, y, r, gg, b)
            self._flood_steps += 1

            # neighbors
            def q_push_xy(px, py):
                nonlocal tail
                if tail >= w * h:
                    return
                bj = tail * 2
                q[bj] = px & 0xFF
                q[bj + 1] = py & 0xFF
                tail += 1

            if x + 1 < w and g[i + 1] == 0:
                g[i + 1] = 4
                q_push_xy(x + 1, y)
            if x - 1 >= 0 and g[i - 1] == 0:
                g[i - 1] = 4
                q_push_xy(x - 1, y)
            if y + 1 < h and g[i + w] == 0:
                g[i + w] = 4
                q_push_xy(x, y + 1)
            if y - 1 >= 0 and g[i - w] == 0:
                g[i - w] = 4
                q_push_xy(x, y - 1)

        self._flood_q_head = head
        self._flood_q_tail = tail

    def _fire_palette(self, v):
        # v: 0..36 -> rgb
        if v <= 0:
            return (0, 0, 0)
        if v < 10:
            return (v * 7, 0, 0)
        if v < 20:
            return (70 + (v - 10) * 10, (v - 10) * 3, 0)
        if v < 30:
            return (170 + (v - 20) * 6, 30 + (v - 20) * 8, 0)
        return (255, 120 + (v - 30) * 10 if (120 + (v - 30) * 10) < 255 else 255, 20)

    def _fire_init(self):
        w = self._fire_w
        h = self._fire_h
        if self._fire is None or len(self._fire) != w * h:
            self._fire = bytearray(w * h)
        else:
            for i in range(w * h):
                self._fire[i] = 0
        if self._fire_prev is None or len(self._fire_prev) != w * h:
            self._fire_prev = bytearray(w * h)
        # force redraw first frame
        for i in range(w * h):
            self._fire_prev[i] = 255
        display.clear()

    def _fire_step(self):
        w = self._fire_w
        h = self._fire_h
        buf = self._fire

        # seed bottom row
        base = (h - 1) * w
        for x in range(w):
            buf[base + x] = 36 if random.randint(0, 99) < 60 else 0

        # propagate upwards
        for y in range(h - 1):
            row = y * w
            src_row = (y + 1) * w
            for x in range(w):
                src = src_row + x
                v = buf[src]
                if v:
                    decay = random.randint(0, 3)
                    nv = v - decay
                    if nv < 0:
                        nv = 0
                    dx = x + 1 - random.randint(0, 2)
                    if dx < 0:
                        dx = 0
                    elif dx >= w:
                        dx = w - 1
                    buf[row + dx] = nv
                else:
                    # slowly cool
                    if buf[row + x] > 0:
                        buf[row + x] -= 1

        # diff-draw
        prev = self._fire_prev
        for i in range(w * h):
            v = buf[i]
            if v == prev[i]:
                continue
            prev[i] = v
            x = i % w
            y = i // w
            r, g, b = self._fire_palette(v)
            display.set_pixel(x, y, r, g, b)

    # --- MATRIX ---
    def _matrix_init(self):
        w = self._demo_w
        self._matrix_drops = []
        for _ in range(12):
            self._matrix_drops.append(
                {
                    "x": random.randint(0, w - 1),
                    "y": random.randint(-20, 0),
                    "speed": random.randint(1, 3),
                    "len": random.randint(4, 12),
                }
            )
        display.clear()

    def _matrix_step(self):
        w = self._demo_w
        h = self._demo_h

        # Framebuffer reads are not portable on all targets. Erasing each
        # outgoing tail produces the same effect without a no-op full-screen
        # traversal every frame.
        for drop in self._matrix_drops:
            # Erase tail
            ty = drop["y"] - drop["len"]
            if 0 <= ty < h:
                display.set_pixel(drop["x"], ty, 0, 0, 0)

            # Move
            if self._frame % drop["speed"] == 0:
                drop["y"] += 1

            # Draw head
            if 0 <= drop["y"] < h:
                # White head
                display.set_pixel(drop["x"], drop["y"], 200, 255, 200)

            # Draw body (dim green)
            by = drop["y"] - 1
            if 0 <= by < h:
                display.set_pixel(drop["x"], by, 0, 200, 0)

            by = drop["y"] - 2
            if 0 <= by < h:
                display.set_pixel(drop["x"], by, 0, 100, 0)

            by = drop["y"] - 3
            if 0 <= by < h:
                display.set_pixel(drop["x"], by, 0, 50, 0)

            # Reset
            if drop["y"] - drop["len"] > h:
                drop["x"] = random.randint(0, w - 1)
                drop["y"] = random.randint(-10, 0)
                drop["speed"] = random.randint(1, 3)
                drop["len"] = random.randint(4, 12)

    # --- STARS ---
    def _stars_init(self):
        self._stars = []
        for _ in range(40):
            # x, y, z
            self._stars.append(
                [random.uniform(-1, 1), random.uniform(-1, 1), random.uniform(0.1, 2.0)]
            )
        display.clear()

    def _stars_step(self):
        w = self._demo_w
        h = self._demo_h
        cx, cy = w // 2, h // 2

        # Erase old
        for s in self._stars:
            pz = s[2]
            if pz > 0.01:
                px = int(s[0] / pz * cx + cx)
                py = int(s[1] / pz * cy + cy)
                if 0 <= px < w and 0 <= py < h:
                    display.set_pixel(px, py, 0, 0, 0)

            # Move
            s[2] -= 0.05

            # Reset if passed screen
            if s[2] < 0.05:
                s[0] = random.uniform(-1, 1)
                s[1] = random.uniform(-1, 1)
                s[2] = 2.0

            # Draw new
            nz = s[2]
            nx = int(s[0] / nz * cx + cx)
            ny = int(s[1] / nz * cy + cy)

            if 0 <= nx < w and 0 <= ny < h:
                bright = int(255 * (1.0 - nz / 2.0))
                if bright < 0:
                    bright = 0
                if bright > 255:
                    bright = 255
                display.set_pixel(nx, ny, bright, bright, bright)

    # --- MYSTIFY ---
    def _mystify_init(self):
        self._mystify_pts = []
        for _ in range(4):  # 4 points forming our shape
            self._mystify_pts.append(
                {
                    "x": float(random.randint(0, WIDTH - 1)),
                    "y": float(random.randint(0, HEIGHT - 1)),
                    "vx": random.choice([-1.5, -1.0, 1.0, 1.5]),
                    "vy": random.choice([-1.5, -1.0, 1.0, 1.5]),
                }
            )
        self._mystify_history = []
        self._mystify_hue = random.randint(0, 360)
        display.clear()

    def _mystify_draw_poly(self, pts, r, g, b):
        for i in range(len(pts)):
            p1 = pts[i]
            p2 = pts[(i + 1) % len(pts)]
            draw_line(int(p1["x"]), int(p1["y"]), int(p2["x"]), int(p2["y"]), r, g, b)

    def _mystify_step(self):
        # Add current to history
        current_state = [{"x": p["x"], "y": p["y"]} for p in self._mystify_pts]
        self._mystify_history.append(current_state)

        # Erase oldest if history too long (max 8 trailing lines)
        if len(self._mystify_history) > 8:
            oldest = self._mystify_history.pop(0)
            self._mystify_draw_poly(oldest, 0, 0, 0)

        # Move points
        for p in self._mystify_pts:
            p["x"] += p["vx"]
            p["y"] += p["vy"]

            # Bounce
            if p["x"] <= 0:
                p["x"] = 0
                p["vx"] *= -1
            elif p["x"] >= WIDTH - 1:
                p["x"] = WIDTH - 1
                p["vx"] *= -1

            if p["y"] <= 0:
                p["y"] = 0
                p["vy"] *= -1
            elif p["y"] >= HEIGHT - 1:
                p["y"] = HEIGHT - 1
                p["vy"] *= -1

        # Draw new
        self._mystify_hue = (self._mystify_hue + 1.5) % 360
        r, g, b = hsb_to_rgb(self._mystify_hue, 1, 1)
        self._mystify_draw_poly(self._mystify_pts, r, g, b)

    # --- CUBE (3D Wireframe) ---
    def _cube_init(self):
        self._cube_angle_x = 0.0
        self._cube_angle_y = 0.0
        self._cube_angle_z = 0.0
        self._cube_pulse = 0.0
        # 8 vertices of a cube
        self._cube_vertices = [
            (-1, -1, -1),
            (1, -1, -1),
            (1, 1, -1),
            (-1, 1, -1),
            (-1, -1, 1),
            (1, -1, 1),
            (1, 1, 1),
            (-1, 1, 1),
        ]
        # 12 edges (pairs of vertex indices)
        self._cube_edges = [
            (0, 1),
            (1, 2),
            (2, 3),
            (3, 0),  # Back face
            (4, 5),
            (5, 6),
            (6, 7),
            (7, 4),  # Front face
            (0, 4),
            (1, 5),
            (2, 6),
            (3, 7),  # Connecting faces
        ]
        self._cube_hue = 0.0
        display.clear()

    def _cube_step(self):
        display.clear()

        # Increment angles
        self._cube_angle_x += 0.05
        self._cube_angle_y += 0.03
        self._cube_angle_z += 0.02
        self._cube_pulse += 0.065
        self._cube_hue = (self._cube_hue + 2) % 360
        pulse_scale = 8.5 + math.sin(self._cube_pulse) * 3.5

        # Precompute sin/cos
        sx, cx = math.sin(self._cube_angle_x), math.cos(self._cube_angle_x)
        sy, cy = math.sin(self._cube_angle_y), math.cos(self._cube_angle_y)
        sz, cz = math.sin(self._cube_angle_z), math.cos(self._cube_angle_z)

        projected = []
        for x, y, z in self._cube_vertices:
            # Rotate X
            y1 = y * cx - z * sx
            z1 = y * sx + z * cx
            # Rotate Y
            x2 = x * cy + z1 * sy
            z2 = -x * sy + z1 * cy
            # Rotate Z
            x3 = x2 * cz - y1 * sz
            y3 = x2 * sz + y1 * cz

            # Projection (scale and center)
            scale = 16 / (z2 + 3)  # Perspective divide
            px = int(WIDTH // 2 + x3 * scale * pulse_scale)
            py = int(HEIGHT // 2 + y3 * scale * pulse_scale)
            projected.append((px, py))

        # Draw edges
        r, g, b = hsb_to_rgb(self._cube_hue, 1, 1)
        for i, j in self._cube_edges:
            x1, y1 = projected[i]
            x2, y2 = projected[j]
            draw_line(x1, y1, x2, y2, r, g, b)

    # --- TUNNEL ---
    def _tunnel_init(self):
        self._tunnel_phase = 0
        display.clear()

    def _tunnel_step(self):
        display.clear()
        self._tunnel_phase = (self._tunnel_phase + 1) & 255
        phase = self._tunnel_phase
        cx = WIDTH // 2 + int(math.sin(phase * 0.07) * 7)
        cy = HEIGHT // 2 + int(math.cos(phase * 0.05) * 5)

        for i in range(9):
            depth = ((phase * 2) + i * 16) & 127
            size = 4 + depth // 2
            if size > 38:
                continue
            skew = int(math.sin((phase + i * 13) * 0.09) * 5)
            x1 = cx - size + skew
            y1 = cy - size
            x2 = cx + size - skew
            y2 = cy + size
            hue = (phase * 3 + i * 31) % 360
            r, g, b = hsb_to_rgb(hue, 1, 1)
            draw_line(x1, y1, x2, y1, r, g, b)
            draw_line(x2, y1, x2, y2, r, g, b)
            draw_line(x2, y2, x1, y2, r, g, b)
            draw_line(x1, y2, x1, y1, r, g, b)

    # --- ORBIT ---
    def _orbit_init(self):
        self._orbit_phase = 0
        display.clear()

    def _orbit_step(self):
        display.clear()
        self._orbit_phase = (self._orbit_phase + 3) % 360
        phase = self._orbit_phase
        cx = WIDTH // 2
        cy = HEIGHT // 2

        for ring in range(4):
            radius = 7 + ring * 6
            hue = (phase * 2 + ring * 70) % 360
            r, g, b = hsb_to_rgb(hue, 1, 1)
            points = 6 + ring * 2
            for i in range(points):
                a = (phase + i * (360 // points) + ring * 19) * 3.14159 / 180.0
                wobble = math.sin((phase + i * 23) * 0.07) * 2.5
                x = int(cx + math.cos(a) * (radius + wobble))
                y = int(cy + math.sin(a) * (radius - wobble))
                draw_rectangle(x - 1, y - 1, x + 1, y + 1, r, g, b)

        draw_rectangle(cx - 2, cy - 2, cx + 2, cy + 2, 255, 255, 255)

    # --- WARP ---
    def _warp_init(self):
        self._warp_phase = 0
        self._warp_stars = []
        for _ in range(28):
            angle = random.randint(0, 359) * 3.14159 / 180.0
            radius = random.randint(1, 26)
            speed = random.randint(2, 5)
            self._warp_stars.append([angle, radius, speed])
        display.clear()

    def _warp_step(self):
        display.clear()
        self._warp_phase = (self._warp_phase + 1) & 255
        cx = WIDTH // 2 + int(math.sin(self._warp_phase * 0.05) * 3)
        cy = HEIGHT // 2 + int(math.cos(self._warp_phase * 0.04) * 3)
        for star in self._warp_stars:
            a = star[0]
            old_r = star[1]
            star[1] += star[2]
            if star[1] > 46:
                star[0] = random.randint(0, 359) * 3.14159 / 180.0
                star[1] = random.randint(1, 5)
                star[2] = random.randint(2, 5)
                old_r = 1
                a = star[0]

            x0 = int(cx + math.cos(a) * old_r)
            y0 = int(cy + math.sin(a) * old_r)
            x1 = int(cx + math.cos(a) * star[1])
            y1 = int(cy + math.sin(a) * star[1])
            hue = (self._warp_phase * 4 + int(star[1]) * 6) % 360
            r, g, b = hsb_to_rgb(hue, 0.8, 1)
            draw_line(x0, y0, x1, y1, r, g, b)

    # --- VORTEX ---
    def _vortex_init(self):
        self._vortex_phase = random.randint(0, 255)
        display.clear()

    def _vortex_step(self):
        display.clear()
        self._vortex_phase = (self._vortex_phase + 3) & 255
        phase = self._vortex_phase
        cx = WIDTH // 2 + int(math.sin(phase * 0.041) * 4)
        cy = HEIGHT // 2 + int(math.cos(phase * 0.037) * 4)
        for arm in range(14):
            hue = (phase * 3 + arm * 25) % 360
            r, g, b = hsb_to_rgb(hue, 1, 1)
            for step in range(2, 31, 4):
                a = phase * 0.035 + arm * 0.58 + step * 0.09
                radius = step + math.sin(phase * 0.05 + arm) * 2.0
                x = int(cx + math.cos(a) * radius)
                y = int(cy + math.sin(a) * radius)
                px = int(cx + math.cos(a - 0.23) * (radius - 3))
                py = int(cy + math.sin(a - 0.23) * (radius - 3))
                draw_line(px, py, x, y, r, g, b)

    # --- COMETS ---
    def _comets_init(self):
        self._comets = []
        count = 9 if not CONFIG_LOW_RAM_MODE else 5
        for i in range(count):
            self._comets.append([0.0, 0.0, 0.0, 0.0, (i * 43) % 360, 0])
            self._comet_respawn(self._comets[-1], i)
        display.clear()

    def _comet_respawn(self, comet, seed=0):
        edge = random.randint(0, 3)
        if edge == 0:
            comet[0] = float(random.randint(0, WIDTH - 1))
            comet[1] = 0.0
        elif edge == 1:
            comet[0] = float(WIDTH - 1)
            comet[1] = float(random.randint(0, HEIGHT - 1))
        elif edge == 2:
            comet[0] = float(random.randint(0, WIDTH - 1))
            comet[1] = float(HEIGHT - 1)
        else:
            comet[0] = 0.0
            comet[1] = float(random.randint(0, HEIGHT - 1))
        target_x = WIDTH // 2 + random.randint(-12, 12)
        target_y = HEIGHT // 2 + random.randint(-12, 12)
        dx = target_x - comet[0]
        dy = target_y - comet[1]
        dist = math.sqrt(dx * dx + dy * dy) or 1.0
        speed = 0.75 + random.randint(0, 8) * 0.08
        comet[2] = dx / dist * speed
        comet[3] = dy / dist * speed
        comet[4] = (self._frame * 3 + seed * 41 + random.randint(0, 45)) % 360
        comet[5] = random.randint(36, 82)

    def _comets_step(self):
        display.clear()
        for i, comet in enumerate(self._comets):
            comet[0] += comet[2]
            comet[1] += comet[3]
            comet[5] -= 1
            x = int(comet[0])
            y = int(comet[1])
            if comet[5] <= 0 or x < -5 or x >= WIDTH + 5 or y < -5 or y >= HEIGHT + 5:
                self._comet_respawn(comet, i)
                self._demo_sound("ping", i, 130)
                continue
            r, g, b = hsb_to_rgb((comet[4] + self._frame * 2) % 360, 0.85, 1)
            tail_x = int(comet[0] - comet[2] * 8.0)
            tail_y = int(comet[1] - comet[3] * 8.0)
            draw_line(tail_x, tail_y, x, y, r // 3, g // 3, b // 3)
            if 0 <= x < WIDTH and 0 <= y < HEIGHT:
                display.set_pixel(x, y, r, g, b)
                if x + 1 < WIDTH:
                    display.set_pixel(x + 1, y, r // 2, g // 2, b // 2)

    # --- BOUNCE (classic screensaver) ---
    def _bounce_init(self):
        self._bounce_x = random.randint(0, WIDTH - 25)
        self._bounce_y = random.randint(0, HEIGHT - 9)
        self._bounce_dx = random.choice([-1, 1])
        self._bounce_dy = random.choice([-1, 1])
        self._bounce_hue = random.randint(0, 359)
        display.clear()

    def _bounce_step(self):
        display.clear()
        label = "ARCADE"
        w = 48
        h = 8
        self._bounce_x += self._bounce_dx
        self._bounce_y += self._bounce_dy
        bounced = False

        if self._bounce_x <= 0:
            self._bounce_x = 0
            self._bounce_dx = 1
            bounced = True
        elif self._bounce_x >= WIDTH - w:
            self._bounce_x = WIDTH - w
            self._bounce_dx = -1
            bounced = True

        if self._bounce_y <= 0:
            self._bounce_y = 0
            self._bounce_dy = 1
            bounced = True
        elif self._bounce_y >= HEIGHT - h:
            self._bounce_y = HEIGHT - h
            self._bounce_dy = -1
            bounced = True

        if bounced:
            # The original screensaver's color pop is the main visual cue.
            self._bounce_hue = (self._bounce_hue + 67) % 360
            self._demo_sound("bounce", self._bounce_hue, 70)

        r, g, b = hsb_to_rgb(self._bounce_hue, 1, 1)
        draw_text(self._bounce_x, self._bounce_y, label, r, g, b)
        draw_rectangle(
            self._bounce_x,
            self._bounce_y + 8,
            self._bounce_x + w - 1,
            self._bounce_y + 8,
            r // 3,
            g // 3,
            b // 3,
        )

    # --- PLASMA ---
    def _plasma_init(self):
        self._plasma_time = 0
        if not self._plasma_palette:
            self._plasma_palette = [
                hsb_to_rgb(i * 360 / 256.0, 1, 1) for i in range(256)
            ]
        if not self._plasma_sin:
            self._plasma_sin = [
                int((math.sin(i * 3.14159 * 2 / 255.0) + 1) * 127) for i in range(256)
            ]

    def _plasma_step(self):
        self._plasma_time = (self._plasma_time + 4) % 256
        t = self._plasma_time
        sin = self._plasma_sin
        pal = self._plasma_palette

        for y in range(0, HEIGHT, 2):
            vy = sin[(y * 4 + t) % 256]
            for x in range(0, WIDTH, 2):
                vx = sin[(x * 4 + t) % 256]
                vc = sin[(x * 2 + y * 2 + t * 2) % 256]

                dist = abs(x - (WIDTH // 2)) + abs(y - (HEIGHT // 2))
                vd = sin[(dist * 6 - t * 3) % 256]

                v = (vy + vx + vc + vd) >> 2

                r, g, b = pal[v % 256]
                draw_rectangle(x, y, x + 2, y + 2, r, g, b)

    # --- SNAKE (based on hub75/snake_on_hub75_zeroplayer.py) ---
    def _snake_restart(self):
        self._snake_score = 0
        self._snake = [(WIDTH // 2, HEIGHT // 2)]
        self._snake_length = 3
        self._snake_dir = "UP"
        self._snake_green_targets = []
        self._snake_step_counter = 0
        self._snake_step_counter2 = 0
        display.clear()
        self._snake_place_target()

    def _snake_random_target(self):
        return (random.randint(1, WIDTH - 2), random.randint(1, HEIGHT - 2))

    def _snake_place_target(self):
        tries = 0
        while tries < 300:
            tries += 1
            x, y = self._snake_random_target()
            if (x, y) in self._snake:
                continue
            hit_green = False
            for gx, gy, _ in self._snake_green_targets:
                if (gx, gy) == (x, y):
                    hit_green = True
                    break
            if hit_green:
                continue
            self._snake_target = (x, y)
            display.set_pixel(x, y, 255, 0, 0)
            return
        self._snake_target = (WIDTH // 2, HEIGHT // 2)
        display.set_pixel(self._snake_target[0], self._snake_target[1], 255, 0, 0)

    def _snake_place_green_target(self):
        tries = 0
        while tries < 200:
            tries += 1
            x, y = random.randint(1, WIDTH - 2), random.randint(1, HEIGHT - 2)
            if (x, y) == self._snake_target:
                continue
            if (x, y) in self._snake:
                continue
            self._snake_green_targets.append((x, y, 256))
            display.set_pixel(x, y, 0, 255, 0)
            return

    def _snake_update_green_targets(self):
        new_targets = []
        for x, y, lifespan in self._snake_green_targets:
            if lifespan > 1:
                new_targets.append((x, y, lifespan - 1))
            else:
                display.set_pixel(x, y, 0, 0, 0)
        self._snake_green_targets = new_targets

    def _snake_find_nearest_target(self, head_x, head_y):
        def md(x1, y1, x2, y2):
            return abs(x1 - x2) + abs(y1 - y2)

        nearest_green = None
        min_green = 99999
        for x, y, _ in self._snake_green_targets:
            d = md(head_x, head_y, x, y)
            if d < min_green:
                min_green = d
                nearest_green = (x, y)

        tx, ty = self._snake_target
        red_d = md(head_x, head_y, tx, ty)
        if nearest_green and min_green <= red_d * 1.5:
            return nearest_green
        return (tx, ty)

    def _snake_update_direction(self):
        head_x, head_y = self._snake[0]
        target_x, target_y = self._snake_find_nearest_target(head_x, head_y)

        opposite = {"UP": "DOWN", "DOWN": "UP", "LEFT": "RIGHT", "RIGHT": "LEFT"}
        cur = self._snake_dir
        new_dir = cur

        if head_x == target_x:
            if head_y < target_y and cur != "UP":
                new_dir = "DOWN"
            elif head_y > target_y and cur != "DOWN":
                new_dir = "UP"
        elif head_y == target_y:
            if head_x < target_x and cur != "LEFT":
                new_dir = "RIGHT"
            elif head_x > target_x and cur != "RIGHT":
                new_dir = "LEFT"
        else:
            if abs(head_x - target_x) < abs(head_y - target_y):
                if head_x < target_x and cur != "LEFT":
                    new_dir = "RIGHT"
                elif head_x > target_x and cur != "RIGHT":
                    new_dir = "LEFT"
            else:
                if head_y < target_y and cur != "UP":
                    new_dir = "DOWN"
                elif head_y > target_y and cur != "DOWN":
                    new_dir = "UP"

        if new_dir == opposite.get(cur):
            new_dir = cur
        self._snake_dir = new_dir

    def _snake_check_self_collision(self):
        head_x, head_y = self._snake[0]
        body = self._snake[1:]
        potential = {
            "UP": (head_x, (head_y - 1) % HEIGHT),
            "DOWN": (head_x, (head_y + 1) % HEIGHT),
            "LEFT": ((head_x - 1) % WIDTH, head_y),
            "RIGHT": ((head_x + 1) % WIDTH, head_y),
        }
        cur_next = potential[self._snake_dir]
        if cur_next in body:
            safe = [d for d, pos in potential.items() if pos not in body]
            if safe:
                self._snake_dir = safe[random.randint(0, len(safe) - 1)]
            else:
                self._snake_restart()

    def _snake_update_position(self):
        head_x, head_y = self._snake[0]
        if self._snake_dir == "UP":
            head_y -= 1
        elif self._snake_dir == "DOWN":
            head_y += 1
        elif self._snake_dir == "LEFT":
            head_x -= 1
        else:
            head_x += 1
        head_x %= WIDTH
        head_y %= HEIGHT

        self._snake.insert(0, (head_x, head_y))
        if len(self._snake) > self._snake_length:
            tx, ty = self._snake.pop()
            display.set_pixel(tx, ty, 0, 0, 0)

    def _snake_check_target_collision(self):
        if self._snake[0] == self._snake_target:
            self._snake_length += 2
            self._snake_place_target()
            self._snake_score += 1
            self._demo_sound("coin", self._snake_score, 70)

    def _snake_check_green_target_collision(self):
        hx, hy = self._snake[0]
        for x, y, lifespan in self._snake_green_targets:
            if (hx, hy) == (x, y):
                self._snake_length = max(self._snake_length // 2, 2)
                try:
                    self._snake_green_targets.remove((x, y, lifespan))
                except Exception:
                    pass
                display.set_pixel(x, y, 0, 0, 0)
                self._demo_sound("zap", self._snake_length, 90)
                break

    def _snake_draw(self):
        hue = 0
        for x, y in self._snake:
            hue = (hue + 5) % 360
            r, g, b = hsb_to_rgb(hue, 1, 1)
            display.set_pixel(x, y, r, g, b)

    def _snake_init(self):
        self._snake_restart()

    def _snake_step(self):
        self._snake_step_counter += 1
        self._snake_step_counter2 += 1
        if (self._snake_step_counter2 & 1023) == 0:
            self._snake_place_green_target()

        self._snake_update_green_targets()
        self._snake_update_direction()
        self._snake_check_self_collision()
        self._snake_update_position()
        self._snake_check_target_collision()
        self._snake_check_green_target_collision()
        self._snake_draw()

    # --- SPARK ---
    def _spark_init(self):
        self._spark_particles = []
        cx = WIDTH // 2
        cy = HEIGHT // 2
        for _ in range(30 if not CONFIG_LOW_RAM_MODE else 16):
            angle = random.randint(0, 359) * 3.14159 / 180.0
            speed = random.uniform(0.4, 1.8)
            self._spark_particles.append(
                [
                    float(cx),
                    float(cy),
                    math.cos(angle) * speed,
                    math.sin(angle) * speed,
                    random.randint(18, 70),
                    random.randint(0, 359),
                ]
            )
        display.clear()

    def _spark_respawn(self, p):
        cx = WIDTH // 2 + int(math.sin(self._frame * 0.045) * 10)
        cy = HEIGHT // 2 + int(math.cos(self._frame * 0.037) * 8)
        angle = random.randint(0, 359) * 3.14159 / 180.0
        speed = random.uniform(0.4, 1.9)
        p[0] = float(cx)
        p[1] = float(cy)
        p[2] = math.cos(angle) * speed
        p[3] = math.sin(angle) * speed
        p[4] = random.randint(18, 70)
        p[5] = random.randint(0, 359)

    def _spark_step(self):
        display.clear()
        for p in self._spark_particles:
            p[0] += p[2]
            p[1] += p[3]
            p[3] += 0.025
            p[4] -= 1
            x = int(p[0])
            y = int(p[1])
            if p[4] <= 0 or x < 0 or x >= WIDTH or y < 0 or y >= HEIGHT:
                self._spark_respawn(p)
                continue
            hue = (p[5] + self._frame * 4) % 360
            r, g, b = hsb_to_rgb(hue, 1, 1)
            display.set_pixel(x, y, r, g, b)
            tx = int(p[0] - p[2])
            ty = int(p[1] - p[3])
            if 0 <= tx < WIDTH and 0 <= ty < HEIGHT:
                display.set_pixel(tx, ty, r // 3, g // 3, b // 3)

    # --- RINGS ---
    def _rings_init(self):
        self._rings_phase = random.randint(0, 255)
        display.clear()

    def _rings_step(self):
        display.clear()
        self._rings_phase = (self._rings_phase + 3) & 255
        phase = self._rings_phase
        cx = WIDTH // 2 + int(math.sin(phase * 0.031) * 5)
        cy = HEIGHT // 2 + int(math.cos(phase * 0.027) * 5)

        for ring in range(7):
            radius = 4 + ((phase // 3 + ring * 7) % 34)
            hue = (phase * 3 + ring * 43) % 360
            r, g, b = hsb_to_rgb(hue, 1, 1)
            points = 18 + ring * 2
            for i in range(points):
                a = (i * 6.28318) / points
                wobble = math.sin((phase + i * 17 + ring * 11) * 0.055) * 2.0
                x = int(cx + math.cos(a) * (radius + wobble))
                y = int(cy + math.sin(a) * (radius - wobble))
                if 0 <= x < WIDTH and 0 <= y < HEIGHT:
                    display.set_pixel(x, y, r, g, b)
                    if ring < 4 and x + 1 < WIDTH:
                        display.set_pixel(x + 1, y, r // 2, g // 2, b // 2)

    # --- RADAR ---
    def _radar_init(self):
        self._radar_phase = random.randint(0, 255)
        self._radar_blips = []
        cx = WIDTH // 2
        cy = HEIGHT // 2
        rings = []
        for radius in (10, 18, 27):
            points = []
            for i in range(0, 64, 2):
                angle = i * 6.28318 / 64.0
                points.append(
                    (
                        int(cx + math.cos(angle) * radius),
                        int(cy + math.sin(angle) * radius),
                    )
                )
            rings.append(tuple(points))
        self._radar_rings = tuple(rings)
        display.clear()

    def _radar_step(self):
        display.clear()
        cx = WIDTH // 2
        cy = HEIGHT // 2
        self._radar_phase = (self._radar_phase + 3) & 255
        phase = self._radar_phase

        sp = display.set_pixel
        for ring in self._radar_rings:
            for x, y in ring:
                if 0 <= x < WIDTH and 0 <= y < HEIGHT:
                    sp(x, y, 0, 45, 0)
        draw_line(cx, 4, cx, HEIGHT - 5, 0, 28, 0)
        draw_line(4, cy, WIDTH - 5, cy, 0, 28, 0)

        sweep = phase * 6.28318 / 256.0
        sx = int(cx + math.cos(sweep) * 30)
        sy = int(cy + math.sin(sweep) * 30)
        draw_line(cx, cy, sx, sy, 0, 255, 80)
        for i in range(1, 5):
            a = sweep - i * 0.10
            tx = int(cx + math.cos(a) * 29)
            ty = int(cy + math.sin(a) * 29)
            draw_line(cx, cy, tx, ty, 0, 90 // i, 25 // i)

        blips = self._radar_blips
        if (
            len(blips) < self.MAX_RADAR_BLIPS
            and (self._frame & 3) == 0
            and random.randint(0, 99) < 70
        ):
            r = random.randint(7, 29)
            x = int(cx + math.cos(sweep) * r)
            y = int(cy + math.sin(sweep) * r)
            if 0 <= x < WIDTH and 0 <= y < HEIGHT:
                blips.append([x, y, 255])
                self._demo_sound("ping", r, 120)

        active_count = 0
        for blip in blips:
            x, y, bright = blip
            sp(x, y, bright // 5, bright, bright // 8)
            if bright > 170 and x + 1 < WIDTH:
                sp(x + 1, y, bright // 8, bright // 2, 0)
            bright -= 7
            if bright > 18:
                blip[2] = bright
                blips[active_count] = blip
                active_count += 1
        del blips[active_count:]

    # --- MANDELBROT ---
    def _mandel_init(self):
        self._mandel_y = 0
        self._mandel_pass = 0
        if not self._mandel_palette:
            self._mandel_palette = [hsb_to_rgb((i * 11) % 360, 1, 1) for i in range(32)]
        self._mandel_xs = []
        self._mandel_params = None
        display.clear()

    def _mandel_step(self):
        rows_per_frame = 4 if not CONFIG_LOW_RAM_MODE else 2
        pass_id = self._mandel_pass
        max_iter = 18 + (pass_id & 3) * 3
        zoom = 1.0 + (pass_id & 7) * 0.13
        cxoff = -0.58 + math.sin(pass_id * 0.23) * 0.12
        cyoff = math.cos(pass_id * 0.17) * 0.08
        pal = self._mandel_palette
        params = (max_iter, zoom, cxoff)
        if self._mandel_params != params or len(self._mandel_xs) != WIDTH:
            self._mandel_xs = [((x - 32) / 22.0) / zoom + cxoff for x in range(WIDTH)]
            self._mandel_params = params
        xs = self._mandel_xs
        sp = display.set_pixel

        for _ in range(rows_per_frame):
            y = self._mandel_y
            if y >= HEIGHT:
                self._mandel_y = 0
                self._mandel_pass = (self._mandel_pass + 1) & 255
                self._mandel_params = None
                return
            cy = ((y - 32) / 26.0) / zoom + cyoff
            for x in range(WIDTH):
                cx = xs[x]
                qx = cx - 0.25
                q = qx * qx + cy * cy
                if (
                    q * (q + qx) <= 0.25 * cy * cy
                    or (cx + 1.0) * (cx + 1.0) + cy * cy <= 0.0625
                ):
                    sp(x, y, 0, 0, 0)
                    continue
                zx = 0.0
                zy = 0.0
                it = 0
                while zx * zx + zy * zy <= 4.0 and it < max_iter:
                    zx, zy = zx * zx - zy * zy + cx, 2.0 * zx * zy + cy
                    it += 1
                if it >= max_iter:
                    sp(x, y, 0, 0, 0)
                else:
                    r, g, b = pal[(it + pass_id) & 31]
                    shade = 70 + it * 9
                    if shade > 255:
                        shade = 255
                    sp(x, y, (r * shade) // 255, (g * shade) // 255, (b * shade) // 255)
            self._mandel_y += 1

    # --- BOIDS ---
    def _boids_init(self):
        self._boids = []
        n = 18
        for i in range(n):
            a = random.randint(0, 359) * 3.14159 / 180.0
            self._boids.append(
                [
                    random.uniform(4, WIDTH - 5),
                    random.uniform(4, HEIGHT - 5),
                    math.cos(a) * 0.7,
                    math.sin(a) * 0.7,
                    (i * 360) // n,
                ]
            )
        display.clear()

    def _boids_step(self):
        display.clear()
        boids = self._boids
        n = len(boids)
        for i in range(n):
            b = boids[i]
            ax = ay = cx = cy = sx = sy = 0.0
            count = 0
            close = 0
            for j in range(n):
                if i == j:
                    continue
                o = boids[j]
                dx = o[0] - b[0]
                dy = o[1] - b[1]
                d2 = dx * dx + dy * dy
                if d2 < 170.0:
                    ax += o[2]
                    ay += o[3]
                    cx += o[0]
                    cy += o[1]
                    count += 1
                if d2 < 20.0 and d2 > 0.01:
                    sx -= dx
                    sy -= dy
                    close += 1
            if count:
                inv = 1.0 / count
                b[2] += (ax * inv - b[2]) * 0.045
                b[3] += (ay * inv - b[3]) * 0.045
                b[2] += (cx * inv - b[0]) * 0.0022
                b[3] += (cy * inv - b[1]) * 0.0022
            if close:
                b[2] += sx * 0.018
                b[3] += sy * 0.018

            if b[0] < 5:
                b[2] += 0.08
            elif b[0] > WIDTH - 6:
                b[2] -= 0.08
            if b[1] < 5:
                b[3] += 0.08
            elif b[1] > HEIGHT - 6:
                b[3] -= 0.08

            speed = math.sqrt(b[2] * b[2] + b[3] * b[3])
            if speed > 1.45:
                scale = 1.45 / speed
                b[2] *= scale
                b[3] *= scale
            elif speed < 0.35:
                b[2] *= 1.10
                b[3] *= 1.10

        for b in boids:
            b[0] = (b[0] + b[2]) % WIDTH
            b[1] = (b[1] + b[3]) % HEIGHT
            x = int(b[0])
            y = int(b[1])
            r, g, bb = hsb_to_rgb((b[4] + self._frame * 2) % 360, 0.85, 1)
            display.set_pixel(x, y, r, g, bb)
            tx = int(b[0] - b[2] * 2.0)
            ty = int(b[1] - b[3] * 2.0)
            if 0 <= tx < WIDTH and 0 <= ty < HEIGHT:
                display.set_pixel(tx, ty, r // 4, g // 4, bb // 4)

    # --- NBODY ---
    def _nbody_init(self):
        self._nbody = []
        cx = WIDTH / 2.0
        cy = HEIGHT / 2.0
        for i in range(10):
            a = i * 6.28318 / 10.0
            radius = 6.0 + (i % 4) * 3.5
            mass = 0.45 + (i % 3) * 0.22
            self._nbody.append(
                [
                    cx + math.cos(a) * radius,
                    cy + math.sin(a) * radius,
                    -math.sin(a) * (0.35 + i * 0.015),
                    math.cos(a) * (0.35 + i * 0.015),
                    mass,
                    (i * 36) % 360,
                ]
            )
        display.clear()

    def _nbody_step(self):
        display.clear()
        bodies = self._nbody
        n = len(bodies)
        for i in range(n):
            bi = bodies[i]
            ax = 0.0
            ay = 0.0
            for j in range(n):
                if i == j:
                    continue
                bj = bodies[j]
                dx = bj[0] - bi[0]
                dy = bj[1] - bi[1]
                d2 = dx * dx + dy * dy + 12.0
                inv = 0.020 * bj[4] / d2
                ax += dx * inv
                ay += dy * inv
            bi[2] = (bi[2] + ax) * 0.997
            bi[3] = (bi[3] + ay) * 0.997

        for b in bodies:
            px = int(b[0])
            py = int(b[1])
            b[0] += b[2]
            b[1] += b[3]
            if b[0] < 2 or b[0] > WIDTH - 3:
                b[2] = -b[2] * 0.92
                b[0] = 2 if b[0] < 2 else WIDTH - 3
            if b[1] < 2 or b[1] > HEIGHT - 3:
                b[3] = -b[3] * 0.92
                b[1] = 2 if b[1] < 2 else HEIGHT - 3

            x = int(b[0])
            y = int(b[1])
            r, g, bb = hsb_to_rgb((b[5] + self._frame * 3) % 360, 1, 1)
            if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                display.set_pixel(px, py, r // 5, g // 5, bb // 5)
            display.set_pixel(x, y, r, g, bb)
            if b[4] > 0.7 and x + 1 < WIDTH:
                display.set_pixel(x + 1, y, r // 2, g // 2, bb // 2)

    # --- METABALL / LIQUID FIELD ---
    def _metab_init(self):
        self._metab_phase = random.randint(0, 255)
        self._metab_balls = []
        count = 5 if not CONFIG_LOW_RAM_MODE else 3
        for i in range(count):
            angle = (i * 6.28318) / count
            self._metab_balls.append(
                [
                    WIDTH / 2.0 + math.cos(angle) * 16.0,
                    HEIGHT / 2.0 + math.sin(angle) * 12.0,
                    math.cos(angle + 1.7) * (0.34 + i * 0.025),
                    math.sin(angle + 0.9) * (0.30 + i * 0.020),
                    58.0 + i * 9.0,
                    (i * 58) % 360,
                ]
            )
        display.clear()

    def _metab_step(self):
        # Scalar field: every ball contributes inverse-distance strength.
        # Coarse 2x2 sampling keeps the liquid look affordable on 64x64.
        self._metab_phase = (self._metab_phase + 2) & 255
        balls = self._metab_balls

        for b in balls:
            b[0] += b[2]
            b[1] += b[3]
            if b[0] < 4 or b[0] > WIDTH - 5:
                b[2] = -b[2]
                b[0] = clamp(b[0], 4, WIDTH - 5)
            if b[1] < 4 or b[1] > HEIGHT - 5:
                b[3] = -b[3]
                b[1] = clamp(b[1], 4, HEIGHT - 5)

        for y in range(0, HEIGHT, 2):
            for x in range(0, WIDTH, 2):
                field = 0.0
                hue_acc = 0.0
                for b in balls:
                    dx = x - b[0]
                    dy = y - b[1]
                    d2 = dx * dx + dy * dy + 9.0
                    strength = b[4] / d2
                    field += strength
                    hue_acc += b[5] * strength
                if field > 1.75:
                    hue = (int(hue_acc / field) + self._metab_phase * 2) % 360
                    r, g, bb = hsb_to_rgb(hue, 0.9, 1)
                    # Thresholded core/edge brightness works without blending.
                    if field < 2.35:
                        r, g, bb = r // 3, g // 3, bb // 3
                    draw_rectangle(x, y, x + 1, y + 1, r, g, bb)
                else:
                    draw_rectangle(x, y, x + 1, y + 1, 0, 0, 0)

    # --- GRAVITY WELL PARTICLES ---
    def _grav_init(self):
        self._grav_phase = random.randint(0, 255)
        self._grav_particles = []
        cx = WIDTH / 2.0
        cy = HEIGHT / 2.0
        count = 28 if not CONFIG_LOW_RAM_MODE else 16
        for i in range(count):
            a = (i * 6.28318) / count
            radius = 6.0 + (i % 7) * 3.2
            self._grav_particles.append(
                [
                    cx + math.cos(a) * radius,
                    cy + math.sin(a) * radius,
                    -math.sin(a) * 0.62,
                    math.cos(a) * 0.62,
                    (i * 360) // count,
                ]
            )
        display.clear()

    def _grav_step(self):
        # Two moving attractors pull independent particles. Unlike NBODY,
        # particles do not attract each other, so cost stays predictable.
        self._grav_phase = (self._grav_phase + 3) & 255
        phase = self._grav_phase
        cx = WIDTH / 2.0
        cy = HEIGHT / 2.0
        a = phase * 6.28318 / 256.0
        wells = (
            (cx + math.cos(a) * 12.0, cy + math.sin(a * 1.25) * 10.0, 0.95),
            (
                cx + math.cos(a + 3.14159) * 14.0,
                cy + math.sin(a * 0.85 + 2.0) * 12.0,
                0.70,
            ),
        )

        display.clear()
        for wx, wy, _mass in wells:
            draw_rectangle(
                int(wx) - 1, int(wy) - 1, int(wx) + 1, int(wy) + 1, 255, 255, 255
            )

        for p in self._grav_particles:
            px = p[0]
            py = p[1]
            ax = 0.0
            ay = 0.0
            for wx, wy, mass in wells:
                dx = wx - p[0]
                dy = wy - p[1]
                d2 = dx * dx + dy * dy + 18.0
                pull = mass / d2
                ax += dx * pull
                ay += dy * pull
            p[2] = (p[2] + ax) * 0.993
            p[3] = (p[3] + ay) * 0.993
            p[0] += p[2]
            p[1] += p[3]

            # Wrap to preserve orbital energy and avoid edge clumping.
            if p[0] < 0:
                p[0] += WIDTH
                px = p[0]
            elif p[0] >= WIDTH:
                p[0] -= WIDTH
                px = p[0]
            if p[1] < 0:
                p[1] += HEIGHT
                py = p[1]
            elif p[1] >= HEIGHT:
                p[1] -= HEIGHT
                py = p[1]

            r, g, bb = hsb_to_rgb((p[4] + phase * 2) % 360, 0.85, 1)
            tx = int(px)
            ty = int(py)
            if 0 <= tx < WIDTH and 0 <= ty < HEIGHT:
                display.set_pixel(tx, ty, r // 4, g // 4, bb // 4)
            display.set_pixel(int(p[0]), int(p[1]), r, g, bb)

    # --- SPRING MASS CHAIN ---
    def _spring_init(self):
        self._spring_phase = random.randint(0, 255)
        self._spring_rest = 6.0
        self._spring_nodes = []
        count = 5 if CONFIG_LOW_RAM_MODE else 7
        cx = WIDTH / 2.0
        cy = 8.0
        for i in range(count):
            self._spring_nodes.append(
                [
                    cx + random.uniform(-0.8, 0.8),
                    cy + (i + 1) * self._spring_rest,
                    random.uniform(-0.15, 0.15),
                    random.uniform(-0.15, 0.15),
                    1.0 + i * 0.18,
                    (i * 360) // count,
                ]
            )
        display.clear()

    def _spring_pull(self, ax, ay, node, rest, k):
        dx = node[0] - ax
        dy = node[1] - ay
        d2 = dx * dx + dy * dy
        if d2 <= 0.0001:
            return
        d = math.sqrt(d2)
        nx = dx / d
        ny = dy / d
        stretch = d - rest
        fx = nx * stretch * k
        fy = ny * stretch * k
        node[2] -= fx / node[4]
        node[3] -= fy / node[4]

    def _spring_step(self):
        display.clear()
        self._spring_phase = (self._spring_phase + 2) & 255
        anchor_x = WIDTH / 2.0 + math.sin(self._spring_phase * 0.05) * 7.0
        anchor_y = 6.0
        nodes = self._spring_nodes
        if not nodes:
            self._spring_init()
            nodes = self._spring_nodes

        for node in nodes:
            node[3] += 0.12
            node[0] += node[2]
            node[1] += node[3]
            node[2] *= 0.992
            node[3] *= 0.992

        for _ in range(3):
            self._spring_pull(anchor_x, anchor_y, nodes[0], self._spring_rest, 0.12)
            for i in range(len(nodes) - 1):
                self._spring_pull(
                    nodes[i][0], nodes[i][1], nodes[i + 1], self._spring_rest, 0.09
                )

            dx = nodes[0][0] - anchor_x
            dy = nodes[0][1] - anchor_y
            d2 = dx * dx + dy * dy
            if d2 > 0.0001:
                d = math.sqrt(d2)
                nx = dx / d
                ny = dy / d
                nodes[0][0] = anchor_x + nx * self._spring_rest
                nodes[0][1] = anchor_y + ny * self._spring_rest
                rv = nodes[0][2] * nx + nodes[0][3] * ny
                nodes[0][2] -= rv * nx
                nodes[0][3] -= rv * ny

            for i in range(1, len(nodes)):
                a = nodes[i - 1]
                b = nodes[i]
                dx = b[0] - a[0]
                dy = b[1] - a[1]
                d2 = dx * dx + dy * dy
                if d2 <= 0.0001:
                    continue
                d = math.sqrt(d2)
                nx = dx / d
                ny = dy / d
                b[0] = a[0] + nx * self._spring_rest
                b[1] = a[1] + ny * self._spring_rest
                rv = (b[2] - a[2]) * nx + (b[3] - a[3]) * ny
                if rv > 0:
                    rv = 0.0
                a[2] += rv * nx * 0.5
                a[3] += rv * ny * 0.5
                b[2] -= rv * nx * 0.5
                b[3] -= rv * ny * 0.5

        for i, node in enumerate(nodes):
            radius = 2 if i < len(nodes) - 1 else 3
            if node[0] < radius + 1:
                node[0] = radius + 1
                node[2] = abs(node[2]) * 0.65
            elif node[0] > WIDTH - radius - 2:
                node[0] = WIDTH - radius - 2
                node[2] = -abs(node[2]) * 0.65
            if node[1] < 4 + radius:
                node[1] = 4 + radius
                node[3] = abs(node[3]) * 0.65
            elif node[1] > HEIGHT - radius - 2:
                node[1] = HEIGHT - radius - 2
                node[3] = -abs(node[3]) * 0.65

        draw_rectangle(
            int(anchor_x) - 2,
            int(anchor_y) - 1,
            int(anchor_x) + 2,
            int(anchor_y),
            255,
            255,
            255,
        )
        px, py = anchor_x, anchor_y
        for i, node in enumerate(nodes):
            hue = (self._frame * 3 + i * 40) % 360
            r, g, b = hsb_to_rgb(hue, 1, 1)
            draw_line(
                int(px), int(py), int(node[0]), int(node[1]), r // 2, g // 2, b // 2
            )
            self._demo_disc(
                int(node[0]), int(node[1]), 2 if i < len(nodes) - 1 else 3, (r, g, b)
            )
            px, py = node[0], node[1]

    # --- CRADLE (Newton's cradle) ---
    def _cradle_init(self):
        self._cradle_phase = 0
        self._cradle_length = 13.0
        self._cradle_bobs = []
        count = 5
        span = 7.0
        top_y = 8.0
        base_x = WIDTH / 2.0 - span * (count - 1) * 0.5
        for i in range(count):
            anchor_x = base_x + i * span
            anchor_y = top_y
            angle = -0.78 if i == 0 else 0.0
            x = anchor_x + math.sin(angle) * self._cradle_length
            y = anchor_y + math.cos(angle) * self._cradle_length
            vx = 0.9 if i == 0 else 0.0
            vy = 0.0
            self._cradle_bobs.append(
                [x, y, vx, vy, anchor_x, anchor_y, self._cradle_length, (i * 56) % 360]
            )
        display.clear()

    def _cradle_constrain(self, bob):
        dx = bob[0] - bob[4]
        dy = bob[1] - bob[5]
        d2 = dx * dx + dy * dy
        if d2 <= 0.0001:
            return
        d = math.sqrt(d2)
        nx = dx / d
        ny = dy / d
        bob[0] = bob[4] + nx * bob[6]
        bob[1] = bob[5] + ny * bob[6]
        radial = bob[2] * nx + bob[3] * ny
        bob[2] -= radial * nx
        bob[3] -= radial * ny

    def _cradle_step(self):
        display.clear()
        self._cradle_phase = (self._cradle_phase + 1) & 255
        bobs = self._cradle_bobs
        if not bobs:
            self._cradle_init()
            bobs = self._cradle_bobs

        for bob in bobs:
            bob[3] += 0.11
            bob[0] += bob[2]
            bob[1] += bob[3]
            bob[2] *= 0.994
            bob[3] *= 0.994

        for _ in range(2):
            for bob in bobs:
                self._cradle_constrain(bob)

            for i in range(len(bobs)):
                for j in range(i + 1, len(bobs)):
                    a = bobs[i]
                    b = bobs[j]
                    dx = b[0] - a[0]
                    dy = b[1] - a[1]
                    min_d = 4.4
                    d2 = dx * dx + dy * dy
                    if d2 <= 0.0001 or d2 >= min_d * min_d:
                        continue
                    d = math.sqrt(d2)
                    nx = dx / d
                    ny = dy / d
                    overlap = (min_d - d) * 0.5
                    a[0] -= nx * overlap
                    a[1] -= ny * overlap
                    b[0] += nx * overlap
                    b[1] += ny * overlap
                    rvx = b[2] - a[2]
                    rvy = b[3] - a[3]
                    vel_n = rvx * nx + rvy * ny
                    if vel_n > 0:
                        continue
                    impulse = -(1.0 + 0.98) * vel_n * 0.5
                    a[2] -= impulse * nx
                    a[3] -= impulse * ny
                    b[2] += impulse * nx
                    b[3] += impulse * ny

        for bob in bobs:
            self._cradle_constrain(bob)

        draw_rectangle(10, 6, WIDTH - 11, 6, 180, 180, 190)
        for bob in bobs:
            hue = (bob[7] + self._frame * 2) % 360
            r, g, b = hsb_to_rgb(hue, 1, 1)
            draw_line(int(bob[4]), int(bob[5]), int(bob[0]), int(bob[1]), 130, 130, 140)
            self._demo_disc(int(bob[0]), int(bob[1]), 2, (r, g, b))

    # --- CRT TEST PATTERN ---
    def _crt_init(self):
        self._crt_phase = 0
        display.clear()

    def _crt_step(self):
        self._crt_phase = (self._crt_phase + 1) & 255
        phase = self._crt_phase
        bars = (
            (255, 255, 255),
            (255, 255, 0),
            (0, 255, 255),
            (0, 255, 0),
            (255, 0, 255),
            (255, 0, 0),
            (0, 0, 255),
            (20, 20, 20),
        )
        for x in range(WIDTH):
            r, g, b = bars[(x * len(bars)) // WIDTH]
            for y in range(0, 34):
                dim = 160 if ((y + phase) & 7) == 0 else 255
                if y & 1:
                    dim = (dim * 3) // 5
                display.set_pixel(
                    x, y, (r * dim) // 255, (g * dim) // 255, (b * dim) // 255
                )
        for y in range(34, HEIGHT):
            for x in range(WIDTH):
                v = 30 + ((x * 5 + y * 3 + phase) & 31)
                display.set_pixel(x, y, v, v, v)
        for x in range(0, WIDTH, 8):
            draw_line(x, 0, x, HEIGHT - 1, 0, 0, 0)
        for y in range(0, HEIGHT, 8):
            draw_line(0, y, WIDTH - 1, y, 0, 0, 0)
        roll = phase & 63
        draw_line(0, roll, WIDTH - 1, roll, 255, 255, 255)
        draw_rectangle(23, 45, 40, 54, 0, 0, 0)
        draw_text(25, 46, "CRT", 255, 255, 255)

    # --- WIN95 MAZE / DOOM RAYCASTER REUSE ---
    def _winmaze_init(self):
        self._winmaze = DoomLiteGame()
        self._winmaze.configure_attract_maze()
        self._winmaze_path_phase = 0
        display.clear()

    def _winmaze_step(self):
        if self._winmaze is None:
            self._winmaze_init()
        self._winmaze_path_phase = (self._winmaze_path_phase + 1) & 255
        self._winmaze.step_attract_maze(self._frame)

    # --- RIPPLE (water height-field) ---
    def _ripple_init(self):
        w = self._ripple_w
        h = self._ripple_h
        self._ripple_cur = [0] * (w * h)
        self._ripple_prev = [0] * (w * h)
        # Seed a couple of drops so the surface is alive from the first frame.
        for _ in range(3):
            self._ripple_drop()
        display.clear()

    def _ripple_drop(self):
        w = self._ripple_w
        h = self._ripple_h
        x = random.randint(2, w - 3)
        y = random.randint(2, h - 3)
        self._ripple_cur[y * w + x] = 480
        self._demo_sound("ping", x + y, 150)

    def _ripple_step(self):
        w = self._ripple_w
        h = self._ripple_h
        cur = self._ripple_cur
        prev = self._ripple_prev

        # Occasional raindrops keep the pool rippling forever.
        if random.randint(0, 99) < 7:
            self._ripple_drop()

        sp = display.set_pixel
        for y in range(1, h - 1):
            row = y * w
            for x in range(1, w - 1):
                i = row + x
                # Classic damped wave equation on the integer height-field.
                v = ((cur[i - 1] + cur[i + 1] + cur[i - w] + cur[i + w]) >> 1) - prev[i]
                v -= v >> 5
                prev[i] = v

                # Shade water from deep blue troughs to bright cyan crests.
                shade = 96 + (v >> 1)
                if shade < 0:
                    shade = 0
                elif shade > 255:
                    shade = 255
                r = shade >> 2
                g = (shade * 5) >> 3
                px = x << 1
                py = y << 1
                sp(px, py, r, g, shade)
                sp(px + 1, py, r, g, shade)
                sp(px, py + 1, r, g, shade)
                sp(px + 1, py + 1, r, g, shade)

        # Swap buffers: the freshly computed field becomes current.
        self._ripple_cur, self._ripple_prev = prev, cur

    # --- FIRWRK (fireworks) ---
    def _firwrk_init(self):
        self._fw_rockets = []
        self._fw_particles = []
        display.clear()

    def _firwrk_launch(self):
        x = float(random.randint(8, WIDTH - 9))
        vy = -random.uniform(1.4, 2.0)
        apex = random.randint(8, 26)
        hue = random.randint(0, 359)
        # [x, y, vy, target_apex_y, hue]
        self._fw_rockets.append([x, float(HEIGHT - 1), vy, float(apex), hue])

    def _firwrk_burst(self, x, y, hue):
        n = 14 if CONFIG_LOW_RAM_MODE else 26
        available = self.MAX_FIREWORK_PARTICLES - len(self._fw_particles)
        if available <= 0:
            return
        n = min(n, available)
        for _ in range(n):
            a = random.randint(0, 359) * 0.0174533
            speed = random.uniform(0.4, 1.7)
            phue = (hue + random.randint(-25, 25)) % 360
            self._fw_particles.append(
                [
                    float(x),
                    float(y),
                    math.cos(a) * speed,
                    math.sin(a) * speed,
                    random.randint(20, 38),
                    phue,
                ]
            )
        self._demo_sound("bounce", hue, 80)

    def _firwrk_step(self):
        display.clear()
        max_rockets = 2 if CONFIG_LOW_RAM_MODE else 4
        if len(self._fw_rockets) < max_rockets and random.randint(0, 99) < 14:
            self._firwrk_launch()

        sp = display.set_pixel
        rockets = self._fw_rockets
        active_rockets = 0
        for rk in self._fw_rockets:
            rk[1] += rk[2]
            rk[2] += 0.03  # gravity slows the ascent
            x = int(rk[0])
            y = int(rk[1])
            # Burst at apex (rising stalls) or when the target height is reached.
            if rk[2] >= -0.2 or rk[1] <= rk[3]:
                self._firwrk_burst(rk[0], rk[1], rk[4])
                continue
            r, g, b = hsb_to_rgb(rk[4], 0.5, 1)
            if 0 <= x < WIDTH and 0 <= y < HEIGHT:
                sp(x, y, r, g, b)
                ty = y + 1
                if ty < HEIGHT:
                    sp(x, ty, r // 3, g // 3, b // 4)
            rockets[active_rockets] = rk
            active_rockets += 1
        del rockets[active_rockets:]

        particles = self._fw_particles
        active_particles = 0
        for p in self._fw_particles:
            p[0] += p[2]
            p[1] += p[3]
            p[3] += 0.045  # gravity pulls sparks down
            p[2] *= 0.985  # air drag
            p[4] -= 1
            x = int(p[0])
            y = int(p[1])
            if p[4] <= 0 or x < 0 or x >= WIDTH or y < 0 or y >= HEIGHT:
                continue
            bright = p[4] * 7
            if bright > 100:
                bright = 100
            r, g, b = hsb_to_rgb(p[5], 1, bright / 100.0)
            sp(x, y, r, g, b)
            particles[active_particles] = p
            active_particles += 1
        del particles[active_particles:]

    # --- PHYLLO (phyllotaxis sunflower spiral) ---
    def _phyllo_init(self):
        self._phyllo_phase = 0.0
        display.clear()

    def _phyllo_step(self):
        display.clear()
        cx = WIDTH * 0.5 - 0.5
        cy = HEIGHT * 0.5 - 0.5
        self._phyllo_phase += 0.05
        n = 90 if CONFIG_LOW_RAM_MODE else 150
        # Scale so the outermost seed lands near the matrix edge.
        c = 30.0 / math.sqrt(n)
        golden = 2.39996323  # 137.5 degrees, the golden angle
        base_hue = int(self._frame * 2)
        sp = display.set_pixel
        for i in range(n):
            a = i * golden + self._phyllo_phase
            r = c * math.sqrt(i)
            x = int(cx + r * math.cos(a))
            y = int(cy + r * math.sin(a))
            if 0 <= x < WIDTH and 0 <= y < HEIGHT:
                cr, cg, cb = hsb_to_rgb((i * 4 + base_hue) % 360, 1, 1)
                sp(x, y, cr, cg, cb)

    # --- LISSAJO (Lissajous oscilloscope curve) ---
    def _lissajo_init(self):
        self._liss_phase = 0.0
        display.clear()

    def _lissajo_step(self):
        display.clear()
        cx = WIDTH * 0.5
        cy = HEIGHT * 0.5
        amp = (WIDTH - 6) * 0.5
        self._liss_phase += 0.04
        delta = self._liss_phase
        # Slowly morph the frequency ratio so the figure keeps reshaping.
        a = 3.0 + math.sin(self._frame * 0.0031) * 1.5
        b = 2.0 + math.cos(self._frame * 0.0023) * 1.5
        steps = 96 if CONFIG_LOW_RAM_MODE else 170
        base_hue = int(self._frame * 2)
        two_pi = 6.2831853
        sp = display.set_pixel
        for i in range(steps):
            t = i * two_pi / steps
            x = int(cx + amp * math.sin(a * t + delta))
            y = int(cy + amp * math.sin(b * t))
            if 0 <= x < WIDTH and 0 <= y < HEIGHT:
                cr, cg, cb = hsb_to_rgb((i * 360 // steps + base_hue) % 360, 1, 1)
                sp(x, y, cr, cg, cb)
                # A dim neighbour gives the trace a soft phosphor glow.
                if x + 1 < WIDTH:
                    sp(x + 1, y, cr // 3, cg // 3, cb // 3)

    # --- PENDUL (double pendulum) ---
    _PEND_CX = WIDTH // 2
    _PEND_CY = 26
    _PEND_L1 = 13.0
    _PEND_L2 = 13.0

    def _pendul_init(self):
        # Start near the top so the system has plenty of energy to go chaotic.
        self._pend_a1 = 3.14159 * 0.62 + random.uniform(-0.2, 0.2)
        self._pend_a2 = 3.14159 * 0.55 + random.uniform(-0.2, 0.2)
        self._pend_w1 = 0.0
        self._pend_w2 = 0.0
        self._pend_trail = []
        display.clear()

    def _pendul_step(self):
        display.clear()
        g = 1.2
        m1 = 1.0
        m2 = 1.0
        l1 = self._PEND_L1
        l2 = self._PEND_L2
        a1 = self._pend_a1
        a2 = self._pend_a2
        w1 = self._pend_w1
        w2 = self._pend_w2

        # Integrate several small steps per frame for numerical stability.
        dt = 0.10
        for _ in range(3):
            sin = math.sin
            cos = math.cos
            da = a1 - a2
            den = 2 * m1 + m2 - m2 * cos(2 * a1 - 2 * a2)
            a1_acc = (
                -g * (2 * m1 + m2) * sin(a1)
                - m2 * g * sin(a1 - 2 * a2)
                - 2 * sin(da) * m2 * (w2 * w2 * l2 + w1 * w1 * l1 * cos(da))
            ) / (l1 * den)
            a2_acc = (
                2
                * sin(da)
                * (
                    w1 * w1 * l1 * (m1 + m2)
                    + g * (m1 + m2) * cos(a1)
                    + w2 * w2 * l2 * m2 * cos(da)
                )
            ) / (l2 * den)
            w1 += a1_acc * dt
            w2 += a2_acc * dt
            a1 += w1 * dt
            a2 += w2 * dt

        self._pend_a1 = a1
        self._pend_a2 = a2
        self._pend_w1 = w1
        self._pend_w2 = w2

        cx = self._PEND_CX
        cy = self._PEND_CY
        x1 = cx + l1 * math.sin(a1)
        y1 = cy + l1 * math.cos(a1)
        x2 = x1 + l2 * math.sin(a2)
        y2 = y1 + l2 * math.cos(a2)

        # Record the tip path; old points fade out.
        trail = self._pend_trail
        trail.append((x2, y2))
        if len(trail) > 48:
            del trail[:-48]
        n = len(trail)
        for i, (tx, ty) in enumerate(trail):
            ix = int(tx)
            iy = int(ty)
            if 0 <= ix < WIDTH and 0 <= iy < HEIGHT:
                tr, tg, tb = hsb_to_rgb((i * 6 + self._frame * 2) % 360, 1, (i + 1) / n)
                display.set_pixel(ix, iy, tr, tg, tb)

        ix1, iy1 = int(x1), int(y1)
        ix2, iy2 = int(x2), int(y2)
        draw_line(cx, cy, ix1, iy1, 150, 150, 160)
        draw_line(ix1, iy1, ix2, iy2, 200, 200, 210)
        # Pivot and the two bobs.
        display.set_pixel(cx, cy, 90, 90, 110)
        draw_rectangle(ix1 - 1, iy1 - 1, ix1 + 1, iy1 + 1, 80, 180, 255)
        draw_rectangle(ix2 - 1, iy2 - 1, ix2 + 1, iy2 + 1, 255, 220, 60)

    # --- ARCADE (self-playing Breakout attract demo) ---
    _ARC_COLS = 8
    _ARC_ROWS = 5
    _ARC_BRICK_W = 8
    _ARC_BRICK_H = 3
    _ARC_TOP = 7
    _ARC_PADDLE_W = 11
    _ARC_PADDLE_Y = 60

    def _arcade_init(self, joystick=None):
        self._arc_game = BreakoutGame({"settings": {"powerups": True}})
        self._arc_game.paddle_speed = 1
        self._arc_cpu = CpuPlayerJoystick(
            joystick, "BRKOUT", self._arc_game, duration_ms=24 * 60 * 60 * 1000
        )
        self._arc_game._start_round(show_hud=False)

    def _arcade_step(self, joystick=None):
        if self._arc_game is None or self._arc_cpu is None:
            self._arcade_init(joystick)
        if not self._arc_game._step_once(self._arc_cpu, show_win=False, show_hud=False):
            self._arcade_init(joystick)

    def _select_prev_next_demo(self, joystick):
        now = ticks_ms()
        if ticks_diff(now, self._last_move) <= self._move_delay:
            return

        d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT])
        if d == JOYSTICK_LEFT:
            self._advance_demo(-1, randomize=False)
        elif d == JOYSTICK_RIGHT:
            self._advance_demo(1, randomize=False)
        else:
            return

        self._demo_sound("select", self.idx, 50)
        try:
            gc.collect()
        except Exception:
            pass
        self._last_move = now

    def _advance_demo(self, step=1, randomize=None):
        if not self.demos:
            return
        if randomize is None:
            randomize = self.random_order
        if randomize and len(self.demos) > 1:
            next_idx = self.idx
            for _ in range(6):
                next_idx = random.randint(0, len(self.demos) - 1)
                if next_idx != self.idx:
                    break
            self.idx = next_idx
        else:
            self.idx = (self.idx + step) % len(self.demos)
        self._slide_started_ms = ticks_ms()
        self._reset_demo_state()

    def _maybe_auto_advance_demo(self):
        if self.slideshow_ms <= 0 or len(self.demos) <= 1:
            return False
        now = ticks_ms()
        if ticks_diff(now, self._slide_started_ms) < self.slideshow_ms:
            return False
        self._advance_demo(1, randomize=self.random_order)
        return True

    def _game_demo_class(self, name):
        cls_name = self.GAME_CLASS_NAMES.get(name)
        if not cls_name:
            return None
        return globals().get(cls_name)

    def _draw_game_demo_card(self, name):
        display.clear()
        draw_text(2, 10, name, 255, 255, 255)
        draw_text_small(2, 26, "CPU PLAYER", 120, 220, 255)
        draw_text_small(2, 36, "LR SELECT", 140, 140, 140)
        draw_text_small(2, 46, "C BACK", 140, 140, 140)
        self._draw_clock_overlay()
        display_score_and_time(0)

    def _handle_game_demo_entry(self, name, joystick):
        now = ticks_ms()
        if self._game_demo_name != name:
            self._game_demo_name = name
            self._game_demo_selected_ms = now
            self._draw_game_demo_card(name)
            return False
        if ticks_diff(now, self._game_demo_selected_ms) < self._game_demo_wait_ms:
            return False
        self._run_game_demo_sync(name, joystick)
        self._advance_demo(1, randomize=self.random_order)
        return True

    async def _handle_game_demo_entry_async(self, name, joystick):
        now = ticks_ms()
        if self._game_demo_name != name:
            self._game_demo_name = name
            self._game_demo_selected_ms = now
            self._draw_game_demo_card(name)
            try:
                display_flush()
            except Exception:
                pass
            return False
        if ticks_diff(now, self._game_demo_selected_ms) < self._game_demo_wait_ms:
            return False
        await self._run_game_demo_async(name, joystick)
        self._advance_demo(1, randomize=self.random_order)
        return True

    def _run_game_demo_sync(self, name, joystick):
        cls = self._game_demo_class(name)
        if cls is None:
            return
        game = cls()
        cpu = CpuPlayerJoystick(joystick, name, game, duration_ms=self.slideshow_ms)
        try:
            game.main_loop(cpu)
        except RestartProgram:
            raise
        except Exception:
            reset_menu_display(0)
        finally:
            self._reset_demo_state()
            display.clear()
            _wait_for_primary_release(joystick, timeout_ms=500)

    async def _run_game_demo_async(self, name, joystick):
        cls = self._game_demo_class(name)
        if cls is None:
            return
        game = cls()
        cpu = CpuPlayerJoystick(joystick, name, game, duration_ms=self.slideshow_ms)
        try:
            if hasattr(game, "main_loop_async"):
                await game.main_loop_async(cpu)
            else:
                game.main_loop(cpu)
        except RestartProgram:
            raise
        except Exception:
            reset_menu_display(0)
        finally:
            self._reset_demo_state()
            display.clear()
            await _wait_for_primary_release_async(joystick, timeout_ms=500)
            await yield_runtime(0)

    def _ensure_demo_initialized(self, demo, joystick=None):
        if self._init:
            return

        display.clear()
        # No HUD in demos: use full 64x64 for visuals.
        self._demo_sound("start", self.idx, 180)
        if demo == "LIFE":
            self._life_cur = bytearray(self._life_w * self._life_h)
            self._life_nxt = bytearray(self._life_w * self._life_h)
            self._life_prev = bytearray(self._life_w * self._life_h)
            for i in range(self._life_w * self._life_h):
                self._life_cur[i] = 1 if random.randint(0, 99) < 18 else 0
                self._life_prev[i] = 2
        elif demo == "ANTS":
            self._ants_init()
        elif demo == "FLOOD":
            self._flood_init()
        elif demo == "FIRE":
            self._fire_init()
        elif demo == "MATRIX":
            self._matrix_init()
        elif demo == "STARS":
            self._stars_init()
        elif demo == "MYSTIFY":
            self._mystify_init()
        elif demo == "CUBE":
            self._cube_init()
        elif demo == "TUNNEL":
            self._tunnel_init()
        elif demo == "ORBIT":
            self._orbit_init()
        elif demo == "WARP":
            self._warp_init()
        elif demo == "VORTEX":
            self._vortex_init()
        elif demo == "COMETS":
            self._comets_init()
        elif demo == "BOUNCE":
            self._bounce_init()
        elif demo == "PLASMA":
            self._plasma_init()
        elif demo == "SPARK":
            self._spark_init()
        elif demo == "RINGS":
            self._rings_init()
        elif demo == "RADAR":
            self._radar_init()
        elif demo == "MANDEL":
            self._mandel_init()
        elif demo == "BOIDS":
            self._boids_init()
        elif demo == "NBODY":
            self._nbody_init()
        elif demo == "METAB":
            self._metab_init()
        elif demo == "GRAV":
            self._grav_init()
        elif demo == "SPRING":
            self._spring_init()
        elif demo == "CRADLE":
            self._cradle_init()
        elif demo == "RIPPLE":
            self._ripple_init()
        elif demo == "FIRWRK":
            self._firwrk_init()
        elif demo == "PHYLLO":
            self._phyllo_init()
        elif demo == "LISSAJO":
            self._lissajo_init()
        elif demo == "PENDUL":
            self._pendul_init()
        elif demo == "ARCADE":
            self._arcade_init(joystick)
        elif demo == "CRT":
            self._crt_init()
        elif demo == "WINMAZE":
            self._winmaze_init()
        else:
            self._snake_init()
        self._init = True

    def _step_current_demo(self, joystick=None):
        demo = self.demos[self.idx]
        self._ensure_demo_initialized(demo, joystick)

        if demo == "LIFE":
            self._life_step(self._life_w, self._life_h, self._life_cur, self._life_nxt)
            self._life_cur, self._life_nxt = self._life_nxt, self._life_cur
            self._life_draw_diffs(
                self._life_w, self._life_h, self._life_cur, self._life_prev
            )
        elif demo == "ANTS":
            self._ants_step()
        elif demo == "FLOOD":
            self._flood_step()
        elif demo == "FIRE":
            self._fire_step()
        elif demo == "MATRIX":
            self._matrix_step()
        elif demo == "STARS":
            self._stars_step()
        elif demo == "MYSTIFY":
            if not getattr(self, "_mystify_pts", None):
                self._mystify_init()
            self._mystify_step()
        elif demo == "CUBE":
            if not getattr(self, "_cube_vertices", None):
                self._cube_init()
            self._cube_step()
        elif demo == "TUNNEL":
            self._tunnel_step()
        elif demo == "ORBIT":
            self._orbit_step()
        elif demo == "WARP":
            self._warp_step()
        elif demo == "VORTEX":
            self._vortex_step()
        elif demo == "COMETS":
            self._comets_step()
        elif demo == "BOUNCE":
            self._bounce_step()
        elif demo == "PLASMA":
            if not getattr(self, "_plasma_palette", None):
                self._plasma_init()
            self._plasma_step()
        elif demo == "SPARK":
            self._spark_step()
        elif demo == "RINGS":
            self._rings_step()
        elif demo == "RADAR":
            self._radar_step()
        elif demo == "MANDEL":
            self._mandel_step()
        elif demo == "BOIDS":
            self._boids_step()
        elif demo == "NBODY":
            self._nbody_step()
        elif demo == "METAB":
            self._metab_step()
        elif demo == "GRAV":
            self._grav_step()
        elif demo == "SPRING":
            self._spring_step()
        elif demo == "CRADLE":
            self._cradle_step()
        elif demo == "RIPPLE":
            if self._ripple_cur is None:
                self._ripple_init()
            self._ripple_step()
        elif demo == "FIRWRK":
            self._firwrk_step()
        elif demo == "PHYLLO":
            self._phyllo_step()
        elif demo == "LISSAJO":
            self._lissajo_step()
        elif demo == "PENDUL":
            self._pendul_step()
        elif demo == "ARCADE":
            if self._arc_game is None:
                self._arcade_init(joystick)
            self._arcade_step(joystick)
        elif demo == "CRT":
            self._crt_step()
        elif demo == "WINMAZE":
            self._winmaze_step()
        else:
            self._snake_step()

    def _prepare_demo_loop(self):
        global game_over, global_score
        game_over = False
        global_score = 0

    def main_loop(self, joystick):
        self._prepare_demo_loop()
        last_frame = ticks_ms()

        while True:
            c_button, _ = joystick.read_buttons()
            if c_button:
                return

            self._select_prev_next_demo(joystick)
            self._maybe_auto_advance_demo()
            demo = self.demos[self.idx]
            if demo.startswith("G:"):
                self._handle_game_demo_entry(demo[2:], joystick)
                last_frame = ticks_ms()
                sleep_ms(10)
                continue

            frame_ms = self._frame_ms_for_demo(demo)
            now = ticks_ms()
            if ticks_diff(now, last_frame) < frame_ms:
                sleep_ms(1)
                continue
            last_frame = now
            self._frame += 1
            self._step_current_demo(joystick)
            self._draw_clock_overlay()
            display_flush()
            maybe_collect(120)

    async def main_loop_async(self, joystick):
        """Async version for pygbag: yields with asyncio.sleep()."""
        if asyncio is None:
            return self.main_loop(joystick)

        self._prepare_demo_loop()
        last_frame = ticks_ms()

        while True:
            c_button, _ = joystick.read_buttons()
            if c_button:
                return

            self._select_prev_next_demo(joystick)
            self._maybe_auto_advance_demo()
            demo = self.demos[self.idx]
            if demo.startswith("G:"):
                await self._handle_game_demo_entry_async(demo[2:], joystick)
                last_frame = ticks_ms()
                await asyncio.sleep(0.010)
                continue

            frame_ms = self._frame_ms_for_demo(demo)
            now = ticks_ms()
            if ticks_diff(now, last_frame) < frame_ms:
                await asyncio.sleep(0.001)
                continue
            last_frame = now
            self._frame += 1
            self._step_current_demo(joystick)
            self._draw_clock_overlay()
            display_flush()
            maybe_collect(120)
            await asyncio.sleep(0)
