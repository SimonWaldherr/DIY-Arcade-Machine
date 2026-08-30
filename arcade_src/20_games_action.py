class RTypeGame:
    """
    R-TYPE / GRADIUS MINI (Endlos-Side-Shooter)
    Steuerung:
      - Stick: bewegen (Up/Down/Left/Right)
      - Z: schießen
      - C: zurück ins Menü
    """

    # kleine Sinus-LUT (±4) für "wobble" Gegner ohne math.sin
    _SIN = (0, 1, 2, 3, 4, 3, 2, 1, 0, -1, -2, -3, -4, -3, -2, -1)
    MAX_BULLETS = 6
    MAX_EBULLETS = 3
    MAX_ENEMIES = 8
    MAX_POWERUPS = 3

    def __init__(self):
        self.reset()

    def reset(self):
        self.score = 0

        # Player
        self.pw = 5
        self.ph = 3
        self.px = 6
        self.py = PLAY_HEIGHT // 2

        # Projectiles
        self.bullets = []  # [x,y]
        self.ebullets = []  # [x,y]
        self.fire_cd = 0
        self.power_t = 0  # frames power-up active

        # Enemies: [x, y, typ, hp, phase, cd, basey]
        self.enemies = []
        self.spawn_ms = 520
        self.last_spawn = ticks_ms()

        # Powerups: [x,y,ttl]
        self.powerups = []

        # tracking start time for time-based difficulty
        self.start_ms = ticks_ms()
        # Stars background
        self.stars = []
        for _ in range(18):
            self.stars.append(
                [
                    random.randint(0, WIDTH - 1),
                    random.randint(0, PLAY_HEIGHT - 1),
                    random.randint(1, 3),
                ]
            )

        self.frame = 0
        self.last_logic = ticks_ms()
        self.logic_ms = 35  # ~28fps

    def _rect_play(self, x, y, w, h, r, g, b):
        # reuse shared helper to draw playfield rectangles
        draw_play_rect(x, y, w, h, r, g, b)

    def _overlap(self, ax1, ay1, ax2, ay2, bx1, by1, bx2, by2):
        if ax2 < bx1 or bx2 < ax1:
            return False
        if ay2 < by1 or by2 < ay1:
            return False
        return True

    def _spawn_enemy(self):
        # typ 0: drone, typ 1: wobble, typ 2: shooter
        r = random.randint(0, 99)
        if r < 55:
            typ = 0
        elif r < 85:
            typ = 1
        else:
            typ = 2

        y = random.randint(2, PLAY_HEIGHT - 10)
        x = WIDTH + random.randint(0, 12)

        if typ == 0:
            hp = 1
        elif typ == 1:
            hp = 1
        else:
            hp = 2

        phase = random.randint(0, 15)
        cd = random.randint(10, 40)  # shooter cooldown
        self.enemies.append([x, y, typ, hp, phase, cd, y])

    def _difficulty_update(self):
        # schnelleres Spawning mit Score
        # score steigt typischerweise in 10ern, das passt gut
        s = self.score // 10
        self.spawn_ms = 520 - s * 12
        if self.spawn_ms < 170:
            self.spawn_ms = 170

    def _update_stars(self):
        for st in self.stars:
            st[0] -= st[2]
            if st[0] < 0:
                st[0] = WIDTH - 1
                st[1] = random.randint(0, PLAY_HEIGHT - 1)
                st[2] = random.randint(1, 3)

    def _update_powerups(self):
        # move left, expire
        keep_i = 0
        for p in self.powerups:
            p[0] -= 1
            p[2] -= 1
            if p[0] < -2 or p[2] <= 0:
                continue

            # collect
            if (
                abs(p[0] - (self.px + self.pw // 2)) <= 2
                and abs(p[1] - (self.py + 1)) <= 2
            ):
                self.power_t = 240  # roughly 8 seconds at the current tick speed
                # small bonus
                self.score += 5
                continue
            self.powerups[keep_i] = p
            keep_i += 1
        del self.powerups[keep_i:]

    def _update_bullets(self):
        # player bullets
        keep_i = 0
        for b in self.bullets:
            b[0] += 4
            if b[0] >= WIDTH:
                continue
            self.bullets[keep_i] = b
            keep_i += 1
        del self.bullets[keep_i:]

        # enemy bullets
        keep_i = 0
        for b in self.ebullets:
            b[0] -= 3
            if b[0] < 0:
                continue
            self.ebullets[keep_i] = b
            keep_i += 1
        del self.ebullets[keep_i:]

    def _update_enemies(self):
        global game_over, global_score

        keep_i = 0
        for e in self.enemies:
            typ = e[2]

            # movement
            if typ == 0:
                e[0] -= 2
            elif typ == 1:
                e[0] -= 1
                e[4] = (e[4] + 1) & 15
                e[1] = e[6] + self._SIN[e[4]]
                if e[1] < 1:
                    e[1] = 1
                if e[1] > PLAY_HEIGHT - 6:
                    e[1] = PLAY_HEIGHT - 6
            else:
                e[0] -= 1
                e[5] -= 1
                if e[5] <= 0 and len(self.ebullets) < self.MAX_EBULLETS:
                    # shoot
                    self.ebullets.append([e[0], e[1] + 1])
                    e[5] = random.randint(18, 40)

            # offscreen
            if e[0] < -10:
                continue

            # collision with player (rects)
            ex1 = e[0]
            ey1 = e[1]
            ew = 4 if typ != 2 else 5
            eh = 3 if typ != 2 else 4
            ex2 = ex1 + ew - 1
            ey2 = ey1 + eh - 1

            px1 = self.px
            py1 = self.py
            px2 = px1 + self.pw - 1
            py2 = py1 + self.ph - 1

            if self._overlap(ex1, ey1, ex2, ey2, px1, py1, px2, py2):
                global_score = self.score
                game_over = True
                return
            self.enemies[keep_i] = e
            keep_i += 1
        del self.enemies[keep_i:]

        # enemy bullets vs player
        px1 = self.px
        py1 = self.py
        px2 = px1 + self.pw - 1
        py2 = py1 + self.ph - 1
        for b in self.ebullets[:]:
            if px1 <= b[0] <= px2 and py1 <= b[1] <= py2:
                global_score = self.score
                game_over = True
                return

    def _bullet_hits(self):
        # bullets vs enemies
        keep_i = 0
        for b in self.bullets:
            bx, by = b[0], b[1]
            hit = None
            for e in self.enemies:
                typ = e[2]
                ex1 = e[0]
                ey1 = e[1]
                ew = 4 if typ != 2 else 5
                eh = 3 if typ != 2 else 4
                ex2 = ex1 + ew - 1
                ey2 = ey1 + eh - 1
                if ex1 <= bx <= ex2 and ey1 <= by <= ey2:
                    hit = e
                    break

            if hit is not None:
                hit[3] -= 1
                if hit[3] <= 0:
                    self.enemies.remove(hit)
                    # score
                    typ = hit[2]
                    self.score += 10 + typ * 7
                    # chance for powerup
                    if (
                        random.randint(0, 99) < 12
                        and len(self.powerups) < self.MAX_POWERUPS
                    ):
                        self.powerups.append([hit[0], hit[1], 400])
                else:
                    self.score += 1  # hit bonus
            else:
                self.bullets[keep_i] = b
                keep_i += 1
        del self.bullets[keep_i:]

    def _draw(self):
        display.clear()
        sp = display.set_pixel

        # stars
        for x, y, _s in self.stars:
            if 0 <= x < WIDTH and 0 <= y < PLAY_HEIGHT:
                sp(x, y, 60, 60, 60)

        # powerups
        for p in self.powerups:
            x = int(p[0])
            y = int(p[1])
            if 0 <= x < WIDTH and 0 <= y < PLAY_HEIGHT:
                sp(x, y, 0, 255, 0)
                if x + 1 < WIDTH:
                    sp(x + 1, y, 0, 255, 0)

        # player
        self._rect_play(self.px, self.py, self.pw, self.ph, 0, 180, 255)
        # nose
        nx = self.px + self.pw
        ny = self.py + 1
        if 0 <= nx < WIDTH and 0 <= ny < PLAY_HEIGHT:
            sp(nx, ny, 0, 180, 255)

        # bullets
        for b in self.bullets:
            x, y = b
            if 0 <= x < WIDTH and 0 <= y < PLAY_HEIGHT:
                sp(x, y, 255, 255, 255)
        for b in self.ebullets:
            x, y = b
            if 0 <= x < WIDTH and 0 <= y < PLAY_HEIGHT:
                sp(x, y, 255, 60, 60)

        # enemies
        for e in self.enemies:
            x = int(e[0])
            y = int(e[1])
            typ = e[2]
            if typ == 0:
                self._rect_play(x, y, 4, 3, 255, 60, 60)
            elif typ == 1:
                self._rect_play(x, y, 4, 3, 255, 0, 255)
            else:
                self._rect_play(x, y, 5, 4, 255, 140, 0)
                # "gun"
                gx = x
                gy = y + 2
                if 0 <= gx < WIDTH and 0 <= gy < PLAY_HEIGHT:
                    sp(gx, gy, 0, 0, 0)

        # HUD
        display_score_and_time(self.score)

    def main_loop(self, joystick):
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        display_score_and_time(0, force=True)

        while True:
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return
            if game_over:
                return

            now = ticks_ms()
            if ticks_diff(now, self.last_logic) < self.logic_ms:
                sleep_ms(2)
                continue
            self.last_logic = now
            self.frame += 1

            # power timer
            if self.power_t > 0:
                self.power_t -= 1

            # input
            d = joystick.read_direction(
                [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
            )
            step = 2
            if d == JOYSTICK_UP:
                self.py -= step
            elif d == JOYSTICK_DOWN:
                self.py += step
            elif d == JOYSTICK_LEFT:
                self.px -= step
            elif d == JOYSTICK_RIGHT:
                self.px += step

            # bounds
            if self.px < 0:
                self.px = 0
            if self.px > WIDTH - self.pw - 1:
                self.px = WIDTH - self.pw - 1
            if self.py < 0:
                self.py = 0
            if self.py > PLAY_HEIGHT - self.ph:
                self.py = PLAY_HEIGHT - self.ph

            # shoot
            if self.fire_cd > 0:
                self.fire_cd -= 1
            cd_min = 4 if self.power_t > 0 else 7
            if z_button and self.fire_cd == 0 and len(self.bullets) < self.MAX_BULLETS:
                # normal bullet
                self.bullets.append([self.px + self.pw + 1, self.py + 1])
                # powered double-shot
                if self.power_t > 0 and len(self.bullets) < self.MAX_BULLETS:
                    self.bullets.append([self.px + self.pw + 1, self.py])
                self.fire_cd = cd_min

            # spawn
            self._difficulty_update()
            if (
                ticks_diff(now, self.last_spawn) >= self.spawn_ms
                and len(self.enemies) < self.MAX_ENEMIES
            ):
                self.last_spawn = now
                self._spawn_enemy()

            # update world
            self._update_stars()
            self._update_powerups()
            self._update_bullets()
            self._bullet_hits()
            self._update_enemies()

            global_score = self.score
            self._draw()

            if self.frame % 80 == 0:
                gc.collect()

    async def main_loop_async(self, joystick):
        """Async version for pygbag: yields with asyncio.sleep()."""
        if asyncio is None:
            return self.main_loop(joystick)

        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        display_score_and_time(0, force=True)

        def loop_iteration():
            global game_over, global_score
            c_button, z_button = joystick.read_buttons()
            if c_button or game_over:
                return False

            self.frame += 1

            # power timer
            if self.power_t > 0:
                self.power_t -= 1

            # input
            d = joystick.read_direction(
                [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
            )
            step = 2
            if d == JOYSTICK_UP:
                self.py -= step
            elif d == JOYSTICK_DOWN:
                self.py += step
            elif d == JOYSTICK_LEFT:
                self.px -= step
            elif d == JOYSTICK_RIGHT:
                self.px += step

            # bounds
            if self.px < 0:
                self.px = 0
            if self.px > WIDTH - self.pw - 1:
                self.px = WIDTH - self.pw - 1
            if self.py < 0:
                self.py = 0
            if self.py > PLAY_HEIGHT - self.ph:
                self.py = PLAY_HEIGHT - self.ph

            # shoot
            if self.fire_cd > 0:
                self.fire_cd -= 1
            cd_min = 4 if self.power_t > 0 else 7
            if z_button and self.fire_cd == 0 and len(self.bullets) < self.MAX_BULLETS:
                # normal bullet
                self.bullets.append([self.px + self.pw + 1, self.py + 1])
                # powered double-shot
                if self.power_t > 0 and len(self.bullets) < self.MAX_BULLETS:
                    self.bullets.append([self.px + self.pw + 1, self.py])
                self.fire_cd = cd_min

            # spawn
            now = ticks_ms()
            self._difficulty_update()
            if (
                ticks_diff(now, self.last_spawn) >= self.spawn_ms
                and len(self.enemies) < self.MAX_ENEMIES
            ):
                self.last_spawn = now
                self._spawn_enemy()

            # update world
            self._update_stars()
            self._update_powerups()
            self._update_bullets()
            self._bullet_hits()
            self._update_enemies()

            global_score = self.score
            self._draw()
            return True

        await _run_game_loop_async(35, loop_iteration)


class PacmanGame:
    """
    PACMAN-lite (Maze + Pellets + 2 Ghosts)
    Steuerung:
      - Stick: Richtung
      - C: zurück ins Menü
    """

    W = 16
    H = 14
    CELL = 4
    OFF_X = 0
    OFF_Y = 1

    # 16 characters per row, 15 rows. Each level must keep every pellet reachable.
    MAPS = (
        (
            "################",
            "#P.............#",
            "#.##.#.##.#.##.#",
            "#o...#....#...o#",
            "###.########.###",
            "#......##......#",
            "#.####.##.####.#",
            "#......GG......#",
            "#.####.##.####.#",
            "#......##......#",
            "###.########.###",
            "#o...#....#...o#",
            "#.##.#.##.#.##.#",
            "#..............#",
            "################",
        ),
        (
            "################",
            "#P....#........#",
            "#.##..#.####.#.#",
            "#o....#....#.#o#",
            "####.####..#.#.#",
            "#....#.....#...#",
            "#.##.#.##.###.##",
            "#....#.GG......#",
            "##.###.##.#.##.#",
            "#...#.....#....#",
            "#.#.#..####.####",
            "#o#.#....#....o#",
            "#.#.####.#..##.#",
            "#........#.....#",
            "################",
        ),
        (
            "################",
            "#P.....#.......#",
            "#.###..#.####..#",
            "#o..#.......#o.#",
            "###.#.#####.#.##",
            "#...#...#...#..#",
            "#.#####.#.###..#",
            "#.......GG.....#",
            "#..###.#.#####.#",
            "#..#...#...#...#",
            "##.#.#####.#.###",
            "#.o#.......#..o#",
            "#..####.#..###.#",
            "#.......#......#",
            "################",
        ),
    )

    # dirs: 0 U, 1 D, 2 L, 3 R
    DIRS = ((0, -1), (0, 1), (-1, 0), (1, 0))
    OPP = (1, 0, 3, 2)
    GHOST_ACTIVE = 0
    GHOST_HIDDEN = 1
    GHOST_HARMLESS = 2
    GHOST_RESPAWN_TICKS = 42  # about 5 seconds at logic_ms=120

    def __init__(self):
        self.reset()

    def reset(self):
        self.level = 0
        self.score = 0
        self._load_level()

    def _load_level(self):
        self.map = self.MAPS[self.level % len(self.MAPS)]
        self.wall = bytearray(self.W * self.H)  # 1 if wall
        self.pel = bytearray(self.W * self.H)  # 0 none, 1 pellet, 2 power
        self.wall_list = []

        self.px = 1
        self.py = 1
        self.pdir = 3  # right
        self.want_dir = 3

        self.ghosts = []  # each: [x,y,dir,home_x,home_y,state,timer]
        self.power_timer = 0  # ticks (logic steps)

        self.pellet_count = 0

        # parse map
        for y in range(self.H):
            row = self.map[y]
            for x in range(self.W):
                ch = row[x]
                i = y * self.W + x
                if ch == "#":
                    self.wall[i] = 1
                    self.wall_list.append((x, y))
                else:
                    self.wall[i] = 0
                    if ch == ".":
                        self.pel[i] = 1
                        self.pellet_count += 1
                    elif ch == "o":
                        self.pel[i] = 2
                        self.pellet_count += 1
                    else:
                        self.pel[i] = 0

                    if ch == "P":
                        self.px, self.py = x, y
                    elif ch == "G":
                        # ghost start
                        self.ghosts.append(
                            [x, y, random.randint(0, 3), x, y, self.GHOST_ACTIVE, 0]
                        )

        if len(self.ghosts) < 2:
            # safety
            self.ghosts.append([self.W - 2, 1, 2, self.W - 2, 1, self.GHOST_ACTIVE, 0])

        self.last_logic = ticks_ms()
        self.logic_ms = 120
        self.ghost_tick = 0
        self._input_cd = 0
        self.frame = 0
        self._dirty = True
        self._drawn_bg = False
        self.prev_px = self.px
        self.prev_py = self.py
        self.prev_ghosts = [(g[0], g[1]) for g in self.ghosts]

    def _idx(self, x, y):
        return y * self.W + x

    def _can_move(self, x, y):
        if x < 0 or x >= self.W or y < 0 or y >= self.H:
            return False
        return self.wall[self._idx(x, y)] == 0

    def _eat(self):
        i = self._idx(self.px, self.py)
        v = self.pel[i]
        if v:
            self.pel[i] = 0
            self.pellet_count -= 1
            if v == 1:
                self.score += 1
            else:
                self.score += 10
                self.power_timer = 70  # ~8.4s bei logic_ms=120
            self._dirty = True

    def _move_player(self):
        # attempt desired direction first
        dx, dy = self.DIRS[self.want_dir]
        nx = self.px + dx
        ny = self.py + dy
        if self._can_move(nx, ny):
            self.pdir = self.want_dir
        else:
            # try current dir
            dx, dy = self.DIRS[self.pdir]
            nx = self.px + dx
            ny = self.py + dy
            if not self._can_move(nx, ny):
                return  # stuck

        self.px = nx
        self.py = ny
        self._dirty = True

    def _ghost_moves(self, g):
        # returns list of possible dirs
        x, y, d, hx, hy = g[:5]
        moves = []
        for nd in (0, 1, 2, 3):
            dx, dy = self.DIRS[nd]
            nx = x + dx
            ny = y + dy
            if self._can_move(nx, ny):
                moves.append(nd)
        if len(moves) > 1 and self.OPP[d] in moves:
            moves.remove(self.OPP[d])
        return moves

    def _ghost_pick(self, g):
        x, y, d, hx, hy = g[:5]
        moves = self._ghost_moves(g)
        if not moves:
            return d
        if len(moves) == 1:
            return moves[0]

        # 25% randomness
        if random.randint(0, 99) < 25:
            return random.choice(moves)

        # greedy distance
        best = moves[0]
        bestv = None

        frightened = self.power_timer > 0
        for nd in moves:
            dx, dy = self.DIRS[nd]
            nx = x + dx
            ny = y + dy
            dist = abs(nx - self.px) + abs(ny - self.py)

            if frightened:
                # maximize distance
                if bestv is None or dist > bestv:
                    bestv = dist
                    best = nd
            else:
                # minimize distance
                if bestv is None or dist < bestv:
                    bestv = dist
                    best = nd
        return best

    def _update_ghost_states(self):
        for g in self.ghosts:
            if g[5] == self.GHOST_ACTIVE:
                continue
            g[6] -= 1
            if g[6] > 0:
                continue
            if g[5] == self.GHOST_HIDDEN:
                g[0], g[1] = g[3], g[4]
                g[2] = random.randint(0, 3)
                g[5] = self.GHOST_HARMLESS
                g[6] = self.GHOST_RESPAWN_TICKS
            else:
                g[5] = self.GHOST_ACTIVE
                g[6] = 0
            self._dirty = True

    def _move_ghosts(self):
        # ghost speed: every 2nd logic tick
        self.ghost_tick = (self.ghost_tick + 1) & 1
        if self.ghost_tick == 1:
            return

        for g in self.ghosts:
            if g[5] == self.GHOST_HIDDEN:
                continue
            nd = self._ghost_pick(g)
            g[2] = nd
            dx, dy = self.DIRS[nd]
            g[0] += dx
            g[1] += dy
            self._dirty = True

    def _check_collisions(self):
        global game_over, global_score
        for g in self.ghosts:
            if g[5] != self.GHOST_ACTIVE:
                continue
            if g[0] == self.px and g[1] == self.py:
                if self.power_timer > 0:
                    # eat ghost
                    self.score += 50
                    g[0], g[1] = g[3], g[4]
                    g[2] = random.randint(0, 3)
                    g[5] = self.GHOST_HIDDEN
                    g[6] = self.GHOST_RESPAWN_TICKS
                    self._dirty = True
                else:
                    global_score = self.score
                    game_over = True
                    return True
        return False

    def _draw_cell(self, cx, cy, r, g, b):
        x1 = self.OFF_X + cx * self.CELL
        y1 = self.OFF_Y + cy * self.CELL
        draw_rectangle(x1, y1, x1 + self.CELL - 1, y1 + self.CELL - 1, r, g, b)

    def _is_wall_cell(self, x, y):
        if x < 0 or x >= self.W or y < 0 or y >= self.H:
            return False
        return self.wall[self._idx(x, y)] == 1

    def _draw_wall_cell(self, x, y):
        px = self.OFF_X + x * self.CELL
        py = self.OFF_Y + y * self.CELL
        draw_rectangle(px, py, px + 3, py + 3, 0, 18, 95)
        if not self._is_wall_cell(x, y - 1):
            draw_rectangle(px, py, px + 3, py, 30, 95, 255)
        if not self._is_wall_cell(x, y + 1):
            draw_rectangle(px, py + 3, px + 3, py + 3, 0, 45, 180)
        if not self._is_wall_cell(x - 1, y):
            draw_rectangle(px, py, px, py + 3, 15, 75, 235)
        if not self._is_wall_cell(x + 1, y):
            draw_rectangle(px + 3, py, px + 3, py + 3, 0, 45, 170)

    def _draw_bg_cell(self, x, y):
        i = self._idx(x, y)
        if self.wall[i]:
            self._draw_wall_cell(x, y)
            return

        # empty floor
        self._draw_cell(x, y, 0, 0, 0)

        # pellet on top of floor
        v = self.pel[i]
        if v:
            cx = self.OFF_X + x * self.CELL + 1
            cy = self.OFF_Y + y * self.CELL + 1
            if v == 1:
                display.set_pixel(cx + 1, cy + 1, 255, 220, 150)
            else:
                draw_rectangle(cx, cy, cx + 2, cy + 2, 255, 230, 80)
                display.set_pixel(cx + 1, cy + 1, 255, 255, 255)

    def _draw_player(self):
        px = self.OFF_X + self.px * self.CELL
        py = self.OFF_Y + self.py * self.CELL
        draw_rectangle(px, py, px + 3, py + 3, 255, 220, 0)
        if self.pdir == 0:
            display.set_pixel(px + 1, py, 0, 0, 0)
            display.set_pixel(px + 2, py, 0, 0, 0)
        elif self.pdir == 1:
            display.set_pixel(px + 1, py + 3, 0, 0, 0)
            display.set_pixel(px + 2, py + 3, 0, 0, 0)
        elif self.pdir == 2:
            display.set_pixel(px, py + 1, 0, 0, 0)
            display.set_pixel(px, py + 2, 0, 0, 0)
        else:
            display.set_pixel(px + 3, py + 1, 0, 0, 0)
            display.set_pixel(px + 3, py + 2, 0, 0, 0)
        display.set_pixel(px + 1, py + 1, 255, 255, 120)

    def _draw_ghosts(self):
        frightened = self.power_timer > 0
        for gi, g in enumerate(self.ghosts):
            if g[5] == self.GHOST_HIDDEN:
                continue
            gx = self.OFF_X + g[0] * self.CELL
            gy = self.OFF_Y + g[1] * self.CELL
            if g[5] == self.GHOST_HARMLESS:
                col = (90, 55, 95) if gi == 0 else (95, 50, 90)
            elif frightened:
                col = (80, 120, 255)
            else:
                col = (255, 60, 60) if gi == 0 else (255, 80, 210)
            draw_rectangle(gx, gy + 1, gx + 3, gy + 3, *col)
            draw_rectangle(gx + 1, gy, gx + 2, gy, *col)
            eye = 140 if g[5] == self.GHOST_HARMLESS else 255
            display.set_pixel(gx + 1, gy + 1, eye, eye, eye)
            display.set_pixel(gx + 2, gy + 1, eye, eye, eye)
            eye_col = (
                (0, 0, 90) if frightened or g[5] == self.GHOST_HARMLESS else (0, 0, 0)
            )
            display.set_pixel(gx + 1, gy + 2, *eye_col)
            display.set_pixel(gx + 2, gy + 2, *eye_col)
            if not frightened and g[5] == self.GHOST_ACTIVE:
                display.set_pixel(gx, gy + 3, 0, 0, 0)
                display.set_pixel(gx + 3, gy + 3, 0, 0, 0)

    def _draw_background(self):
        display.clear()
        # walls
        for x, y in self.wall_list:
            self._draw_wall_cell(x, y)

        # pellets
        for y in range(self.H):
            for x in range(self.W):
                v = self.pel[self._idx(x, y)]
                if v:
                    cx = self.OFF_X + x * self.CELL + 1
                    cy = self.OFF_Y + y * self.CELL + 1
                    if v == 1:
                        display.set_pixel(cx + 1, cy + 1, 255, 220, 150)
                    else:
                        draw_rectangle(cx, cy, cx + 2, cy + 2, 255, 230, 80)
                        display.set_pixel(cx + 1, cy + 1, 255, 255, 255)
        self._drawn_bg = True

    def _draw(self):
        if not self._drawn_bg:
            self._draw_background()
        self._draw_player()
        self._draw_ghosts()

        draw_text_small(46, PLAY_HEIGHT, "L" + str(self.level + 1), 120, 120, 120)
        display_score_and_time(self.score)
        self._dirty = False

    def _draw_dirty_cells(self, dirty):
        if not self._drawn_bg:
            self._draw_background()

        # restore background for dirty cells first
        for x, y in dirty:
            if 0 <= x < self.W and 0 <= y < self.H:
                self._draw_bg_cell(x, y)

        # redraw sprites on top
        self._draw_player()
        self._draw_ghosts()
        draw_text_small(46, PLAY_HEIGHT, "L" + str(self.level + 1), 120, 120, 120)
        display_score_and_time(self.score)

    def main_loop(self, joystick):
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        display_score_and_time(0, force=True)

        # initial full draw
        self._draw_background()
        self._draw()

        while True:
            c_button, _z = joystick.read_buttons()
            if c_button:
                return
            if game_over:
                return

            now = ticks_ms()

            # read input often
            d = joystick.read_direction(
                [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
            )
            if d == JOYSTICK_UP:
                self.want_dir = 0
            elif d == JOYSTICK_DOWN:
                self.want_dir = 1
            elif d == JOYSTICK_LEFT:
                self.want_dir = 2
            elif d == JOYSTICK_RIGHT:
                self.want_dir = 3

            if ticks_diff(now, self.last_logic) >= self.logic_ms:
                self.last_logic = now
                self.frame += 1

                old_px, old_py = self.px, self.py
                old_ghosts = [(g[0], g[1]) for g in self.ghosts]
                old_power = self.power_timer

                if self.power_timer > 0:
                    self.power_timer -= 1

                self._move_player()
                self._eat()
                self._update_ghost_states()
                self._move_ghosts()

                if self._check_collisions():
                    global_score = self.score
                    return

                # win?
                if self.pellet_count <= 0:
                    self.score += 100 + self.level * 50
                    global_score = self.score
                    if self.level + 1 >= len(self.MAPS):
                        show_center_message(
                            ("YOU", "WON"),
                            start_y=18,
                            line_height=15,
                            r=0,
                            g=255,
                            b=0,
                            score=global_score,
                            delay_ms=1300,
                        )
                        return
                    self.level += 1
                    self._load_level()
                    self._draw_background()
                    self._draw()
                    show_center_message(
                        ("LVL", str(self.level + 1)),
                        start_y=18,
                        line_height=15,
                        r=255,
                        g=255,
                        b=0,
                        score=global_score,
                        delay_ms=700,
                    )
                    self.last_logic = ticks_ms()
                    self._drawn_bg = False
                    self._dirty = True
                    continue

                global_score = self.score

                # incremental redraw: old/new sprite cells without allocating a set
                dirty = []

                def add_dirty(cell):
                    if cell not in dirty:
                        dirty.append(cell)

                add_dirty((old_px, old_py))
                add_dirty((self.px, self.py))
                for p in old_ghosts:
                    add_dirty(p)
                for g in self.ghosts:
                    add_dirty((g[0], g[1]))
                if (old_power > 0) != (self.power_timer > 0):
                    for g in self.ghosts:
                        add_dirty((g[0], g[1]))

                self._draw_dirty_cells(dirty)

                if self.frame % 90 == 0:
                    gc.collect()

            else:
                sleep_ms(6)

            if self._dirty:
                self._draw()
            else:
                sleep_ms(8)

    async def main_loop_async(self, joystick):
        """Async version for pygbag: yields with asyncio.sleep()."""
        if asyncio is None:
            return self.main_loop(joystick)

        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        display_score_and_time(0, force=True)

        # initial full draw
        self._draw_background()
        self._draw()

        while True:
            c_button, _z = joystick.read_buttons()
            if c_button:
                return
            if game_over:
                return

            now = ticks_ms()

            # read input often
            d = joystick.read_direction(
                [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
            )
            if d == JOYSTICK_UP:
                self.want_dir = 0
            elif d == JOYSTICK_DOWN:
                self.want_dir = 1
            elif d == JOYSTICK_LEFT:
                self.want_dir = 2
            elif d == JOYSTICK_RIGHT:
                self.want_dir = 3

            if ticks_diff(now, self.last_logic) >= self.logic_ms:
                self.last_logic = now
                self.frame += 1

                old_px, old_py = self.px, self.py
                old_ghosts = [(g[0], g[1]) for g in self.ghosts]
                old_power = self.power_timer

                if self.power_timer > 0:
                    self.power_timer -= 1

                self._move_player()
                self._eat()
                self._update_ghost_states()
                self._move_ghosts()

                if self._check_collisions():
                    global_score = self.score
                    return

                # win?
                if self.pellet_count <= 0:
                    self.score += 100 + self.level * 50
                    global_score = self.score
                    if self.level + 1 >= len(self.MAPS):
                        show_center_message(
                            ("YOU", "WON"),
                            start_y=18,
                            line_height=15,
                            r=0,
                            g=255,
                            b=0,
                            score=global_score,
                        )
                        await asyncio.sleep(1.3)
                        return
                    self.level += 1
                    self._load_level()
                    self._draw_background()
                    self._draw()
                    show_center_message(
                        ("LVL", str(self.level + 1)),
                        start_y=18,
                        line_height=15,
                        r=255,
                        g=255,
                        b=0,
                        score=global_score,
                    )
                    await asyncio.sleep(0.7)
                    self.last_logic = ticks_ms()
                    self._drawn_bg = False
                    self._dirty = True
                    continue

                global_score = self.score

                # incremental redraw: old/new sprite cells without allocating a set
                dirty = []

                def add_dirty(cell):
                    if cell not in dirty:
                        dirty.append(cell)

                add_dirty((old_px, old_py))
                add_dirty((self.px, self.py))
                for p in old_ghosts:
                    add_dirty(p)
                for g in self.ghosts:
                    add_dirty((g[0], g[1]))
                if (old_power > 0) != (self.power_timer > 0):
                    for g in self.ghosts:
                        add_dirty((g[0], g[1]))

                self._draw_dirty_cells(dirty)

                if self.frame % 90 == 0:
                    try:
                        gc.collect()
                    except Exception:
                        pass

            else:
                await asyncio.sleep(0.006)

            if self._dirty:
                self._draw()
            else:
                await asyncio.sleep(0.008)


class CaveFlyGame:
    """
    CAVE FLYER
    Steuerung:
      - Links/Rechts: seitlich durch die Höhle steuern
      - C: zurück ins Menü
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.score = 0
        self.frame = 0

        # Player (2x2) fixed Y, steer X (no gravity)
        self.by = PLAY_HEIGHT // 2
        self.bx = WIDTH // 2

        # Tunnel parameters: start wide, narrow progressively
        self.base_gap = 36  # much wider start
        self.min_gap = 8
        self.gap = self.base_gap
        self.center = WIDTH // 2  # start centered
        self.speed = 1

        # Ringbuffer for left/right tunnel boundaries per row
        self.head = 0
        self.left_wall = bytearray(PLAY_HEIGHT)
        self.right_wall = bytearray(PLAY_HEIGHT)

        # Initialize tunnel for all visible rows
        for y in range(PLAY_HEIGHT):
            self._gen_row_at((self.head + y) % PLAY_HEIGHT)

        # Ensure player starts in the middle of the opening
        mid = (
            int(self.left_wall[self._idx_row(self.by)])
            + int(self.right_wall[self._idx_row(self.by)])
        ) // 2
        self.bx = self._clamp(mid, 1, WIDTH - 3)

    def _clamp(self, v, lo, hi):
        return clamp(v, lo, hi)

    def _idx_row(self, y):
        return (self.head + y) % PLAY_HEIGHT

    def _gen_row_at(self, idx):
        # tunnel tightens over time: starts wide, narrows progressively
        self.gap = self.base_gap - int(self.score / 60)
        if self.gap < self.min_gap:
            self.gap = self.min_gap

        # center drift (keep within bounds)
        self.center += random.randint(-2, 2)
        self.center = self._clamp(
            self.center, (self.gap // 2) + 3, WIDTH - (self.gap // 2) - 4
        )

        left = self.center - (self.gap // 2)
        right = self.center + (self.gap // 2)
        if left < 1:
            left = 1
        if right > WIDTH - 2:
            right = WIDTH - 2
        self.left_wall[idx] = left
        self.right_wall[idx] = right

    def _step_scroll(self):
        # scroll upward: advance head so y=0 becomes previous y=1
        self.head = (self.head + 1) % PLAY_HEIGHT
        # generate new bottom row
        self._gen_row_at(self._idx_row(PLAY_HEIGHT - 1))

    def _collide(self):
        # bird 2x2 at (bx,by)
        x = self.bx
        for yy in (self.by, self.by + 1):
            if yy < 0 or yy >= PLAY_HEIGHT:
                return True
            ri = self._idx_row(yy)
            left = int(self.left_wall[ri])
            right = int(self.right_wall[ri])
            if x <= left:
                return True
            if (x + 1) >= right:
                return True
        return False

    def _draw(self):
        display.clear()
        sp = display.set_pixel

        # tunnel outlines per row
        for y in range(PLAY_HEIGHT):
            i = self._idx_row(y)
            left = int(self.left_wall[i])
            right = int(self.right_wall[i])
            if 0 <= left < WIDTH:
                sp(left, y, 0, 180, 255)
                if left + 1 < WIDTH:
                    sp(left + 1, y, 0, 120, 200)
            if 0 <= right < WIDTH:
                sp(right, y, 0, 180, 255)
                if right - 1 >= 0:
                    sp(right - 1, y, 0, 120, 200)

        # Bird 2x2
        draw_rectangle(self.bx, self.by, self.bx + 1, self.by + 1, 255, 255, 0)

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
            self.frame += 1
            d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT])
            move_amount = 2
            if d == JOYSTICK_LEFT:
                self.bx = max(self.bx - move_amount, 0)
            elif d == JOYSTICK_RIGHT:
                self.bx = min(self.bx + move_amount, WIDTH - 2)
            self._step_scroll()
            self.score += 1
            global_score = self.score
            if self._collide():
                game_over = True
                return False
            self._draw()
            return True

        return step

    def main_loop(self, joystick):
        step = self._build_step(joystick)
        self._draw()
        start_wait = ticks_ms()
        while ticks_diff(ticks_ms(), start_wait) < 900:
            c_button, _z_button = joystick.read_buttons()
            if c_button:
                return
            sleep_ms(20)
        _run_game_loop_sync(33, step)

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        step = self._build_step(joystick)
        self._draw()
        start_wait = ticks_ms()
        while ticks_diff(ticks_ms(), start_wait) < 900:
            c_button, _z_button = joystick.read_buttons()
            if c_button:
                return
            await asyncio.sleep(0.020)
        await _run_game_loop_async(33, step)


class CentipedeGame:
    """
    CENTI
    Controls:
      - Directions: move in the bottom player zone
      - Z: fire upward
      - C: return to menu
    Atari-inspired centipede shooter with mushrooms, segmented enemies, and
    wave progression on a compact 32x29 logical grid.
    """

    FRAME_MS = 34
    CELL = 2
    GW = WIDTH // CELL
    GH = PLAY_HEIGHT // CELL
    PLAYER_MIN_Y = GH - 7

    def __init__(self):
        self.reset()

    def reset(self):
        self.score = 0
        self.wave = 1
        self.frame = 0
        self.last_z = False
        self._new_wave(reset_player=True)

    def _new_wave(self, reset_player=False):
        if reset_player:
            self.px = self.GW // 2
            self.py = self.GH - 2
        self.bullets = []
        self.flash_until = 0
        self.centipede = []
        length = min(14, 8 + self.wave)
        for i in range(length):
            self.centipede.append([i, 1, 1])
        self.mushrooms = []
        seed = self.wave * 37
        count = min(42, 20 + self.wave * 3)
        used = set()
        for i in range(count):
            x = 2 + ((seed + i * 9 + (i // 3) * 5) % (self.GW - 4))
            y = 4 + ((seed * 2 + i * 7) % (self.GH - 10))
            if (x, y) in used:
                continue
            used.add((x, y))
            self.mushrooms.append([x, y, 2])

    def _mushroom_at(self, x, y):
        for m in self.mushrooms:
            if m[0] == x and m[1] == y and m[2] > 0:
                return m
        return None

    def _move_player(self, joystick):
        d = joystick.read_direction(
            [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
        )
        dx, dy = direction_to_delta(d)
        if dx or dy:
            self.px = clamp(self.px + dx, 1, self.GW - 2)
            self.py = clamp(self.py + dy, self.PLAYER_MIN_Y, self.GH - 2)

    def _fire(self):
        if len(self.bullets) < 2:
            self.bullets.append([self.px, self.py - 1])

    def _move_bullets(self):
        keep = []
        for b in self.bullets:
            hit = False
            for _ in range(2):
                b[1] -= 1
                if b[1] < 0:
                    hit = True
                    break
                m = self._mushroom_at(b[0], b[1])
                if m:
                    m[2] -= 1
                    if m[2] <= 0:
                        self.score += 2
                    hit = True
                    break
                for seg in list(self.centipede):
                    if seg[0] == b[0] and seg[1] == b[1]:
                        self.centipede.remove(seg)
                        self.mushrooms.append([seg[0], seg[1], 2])
                        self.score += 10
                        hit = True
                        break
                if hit:
                    break
            if not hit:
                keep.append(b)
        self.bullets = keep
        self.mushrooms = [m for m in self.mushrooms if m[2] > 0]

    def _move_centipede(self):
        speed_gate = max(2, 7 - min(5, self.wave))
        if (self.frame % speed_gate) != 0:
            return
        for seg in self.centipede:
            nx = seg[0] + seg[2]
            blocked = nx <= 0 or nx >= self.GW - 1 or self._mushroom_at(nx, seg[1])
            if blocked:
                seg[2] = -seg[2]
                seg[1] += 1
                if seg[1] >= self.GH:
                    seg[1] = self.PLAYER_MIN_Y
            else:
                seg[0] = nx

    def _collides_player(self):
        for x, y, _d in self.centipede:
            if abs(x - self.px) <= 1 and abs(y - self.py) <= 1:
                return True
        return False

    def _draw_cell(self, x, y, color):
        px = x * self.CELL
        py = y * self.CELL
        draw_rectangle(px, py, px + 1, py + 1, *color)

    def _draw(self):
        display.clear()
        draw_line(
            0,
            self.PLAYER_MIN_Y * self.CELL - 1,
            WIDTH - 1,
            self.PLAYER_MIN_Y * self.CELL - 1,
            25,
            70,
            25,
        )
        for x, y, hp in self.mushrooms:
            col = (180, 80, 210) if hp > 1 else (90, 45, 120)
            self._draw_cell(x, y, col)
        for b in self.bullets:
            if 0 <= b[1] < self.GH:
                display.set_pixel(b[0] * self.CELL, b[1] * self.CELL, 255, 255, 80)
        for i, seg in enumerate(self.centipede):
            col = (255, 80, 50) if i == 0 else (255, 170, 30)
            self._draw_cell(seg[0], seg[1], col)
        draw_rectangle(
            self.px * self.CELL - 1,
            self.py * self.CELL - 1,
            self.px * self.CELL + 1,
            self.py * self.CELL + 1,
            70,
            210,
            255,
        )
        draw_text_small(1, PLAY_HEIGHT, "W" + str(self.wave), 180, 180, 180)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        self.reset()

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            self.frame += 1
            self._move_player(joystick)
            if z_button and not self.last_z:
                self._fire()
            self.last_z = z_button
            self._move_bullets()
            self._move_centipede()
            if self._collides_player():
                set_game_over_score(self.score)
                return False
            if not self.centipede:
                self.score += 75 + self.wave * 15
                self.wave += 1
                self._new_wave(reset_player=False)
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


class ArtilleryGame:
    """
    ARTILL
    Controls:
      - Up / Down: aim barrel
      - Left / Right: adjust power
      - Z: fire
      - C: return to menu
    Turn-based artillery duel with wind, terrain craters, and a CPU gunner.
    """

    FRAME_MS = 45
    GRAVITY = 0.075

    def __init__(self):
        self.reset()

    def reset(self):
        self.score = 0
        self.round = 1
        self.angle = 45
        self.power = 16
        self.last_z = False
        self.wind = 0.0
        self.shell = None
        self.cpu_wait = 0
        self.turn = "player"
        self.explosion = None
        self._new_round()

    def _new_round(self):
        self.wind = random.choice((-1, 1)) * (0.015 + random.randint(0, 4) * 0.006)
        self.terrain = []
        base = 43 + (self.round % 3)
        for x in range(WIDTH):
            y = base + int(math.sin((x + self.round * 7) * 0.23) * 4)
            y += int(math.sin((x + self.round * 11) * 0.07) * 3)
            self.terrain.append(clamp(y, 31, PLAY_HEIGHT - 2))
        self.player_x = 5
        self.enemy_x = WIDTH - 6
        self.turn = "player"
        self.shell = None
        self.cpu_wait = 18
        self.explosion = None

    def _ground_y(self, x):
        return self.terrain[clamp(int(x), 0, WIDTH - 1)]

    def _tank_pos(self, x):
        return x, self._ground_y(x) - 3

    def _fire(self, owner, angle, power):
        if self.shell:
            return
        sx = self.player_x if owner == "player" else self.enemy_x
        sy = self._ground_y(sx) - 5
        rad = math.radians(angle)
        sign = 1 if owner == "player" else -1
        speed = power * 0.12
        self.shell = [
            float(sx),
            float(sy),
            math.cos(rad) * speed * sign,
            -math.sin(rad) * speed,
            owner,
        ]

    def _crater(self, cx, cy):
        self.explosion = [int(cx), int(cy), 8]
        for x in range(max(0, int(cx) - 5), min(WIDTH, int(cx) + 6)):
            d = abs(x - int(cx))
            self.terrain[x] = clamp(
                self.terrain[x] + max(1, 4 - d // 2), 25, PLAY_HEIGHT - 1
            )

    def _hit_tank(self, x, y, tank_x):
        tx, ty = self._tank_pos(tank_x)
        return (x - tx) * (x - tx) + (y - ty) * (y - ty) <= 25

    def _advance_shell(self):
        if not self.shell:
            return True
        for _ in range(2):
            self.shell[2] += self.wind
            self.shell[3] += self.GRAVITY
            self.shell[0] += self.shell[2]
            self.shell[1] += self.shell[3]
            x, y, _vx, _vy, owner = self.shell
            if x < 0 or x >= WIDTH or y >= PLAY_HEIGHT:
                self.shell = None
                self.turn = "enemy" if owner == "player" else "player"
                self.cpu_wait = 18
                return True
            if owner == "player" and self._hit_tank(x, y, self.enemy_x):
                self.score += 100 + self.round * 10
                self.round += 1
                if self.score >= 700:
                    set_game_over_score(self.score, won=True)
                    return False
                self._new_round()
                return True
            if owner == "enemy" and self._hit_tank(x, y, self.player_x):
                set_game_over_score(self.score)
                return False
            if y >= self._ground_y(x):
                self._crater(x, y)
                self.shell = None
                self.turn = "enemy" if owner == "player" else "player"
                self.cpu_wait = 18
                return True
        return True

    def _cpu_turn(self):
        if self.turn != "enemy" or self.shell:
            return
        self.cpu_wait -= 1
        if self.cpu_wait > 0:
            return
        dx = self.enemy_x - self.player_x
        angle = clamp(38 + random.randint(-8, 12) - int(self.wind * 180), 25, 70)
        power = clamp(int(dx / 4.2) + self.round + random.randint(-4, 4), 11, 27)
        self._fire("enemy", angle, power)

    def _draw_tank(self, x, color):
        tx, ty = self._tank_pos(x)
        draw_rectangle(tx - 2, ty - 1, tx + 2, ty + 1, *color)
        draw_rectangle(tx - 1, ty - 3, tx + 1, ty - 2, *color)

    def _draw_aim(self):
        tx, ty = self._tank_pos(self.player_x)
        rad = math.radians(self.angle)
        length = 7
        ax = tx + int(math.cos(rad) * length)
        ay = ty - 2 - int(math.sin(rad) * length)
        draw_line(tx, ty - 2, ax, ay, 100, 220, 255)

    def _draw(self):
        display.clear()
        sky = (0, 12, 22)
        draw_rectangle(0, 0, WIDTH - 1, PLAY_HEIGHT - 1, *sky)
        for x, y in enumerate(self.terrain):
            draw_line(x, y, x, PLAY_HEIGHT - 1, 80, 65, 32)
            display.set_pixel(x, y, 120, 105, 55)
        self._draw_tank(self.player_x, (80, 210, 255))
        self._draw_tank(self.enemy_x, (255, 70, 55))
        if self.turn == "player" and not self.shell:
            self._draw_aim()
        if self.shell:
            display.set_pixel(int(self.shell[0]), int(self.shell[1]), 255, 255, 180)
        if self.explosion:
            x, y, t = self.explosion
            col = (255, 200, 50) if t & 1 else (255, 80, 30)
            draw_rect_outline(x - 2, y - 2, x + 2, y + 2, *col)
            self.explosion[2] -= 1
            if self.explosion[2] <= 0:
                self.explosion = None
        draw_text_small(1, PLAY_HEIGHT, "A" + str(self.angle), 210, 210, 210)
        draw_text_small(18, PLAY_HEIGHT, "P" + str(self.power), 210, 210, 210)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        self.reset()

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            if self.turn == "player" and not self.shell:
                d = joystick.read_direction(
                    [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
                )
                if d == JOYSTICK_UP:
                    self.angle = min(80, self.angle + 1)
                elif d == JOYSTICK_DOWN:
                    self.angle = max(15, self.angle - 1)
                elif d == JOYSTICK_RIGHT:
                    self.power = min(30, self.power + 1)
                elif d == JOYSTICK_LEFT:
                    self.power = max(7, self.power - 1)
                if z_button and not self.last_z:
                    self._fire("player", self.angle, self.power)
            self.last_z = z_button
            self._cpu_turn()
            if not self._advance_shell():
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


class WormsGame(FrameLoopGame):
    """
    WORMS
    Controls:
      - Left / Right: move active worm, or adjust power while holding Z
      - Up / Down: aim
      - Z: fire
      - C: return to menu
    Tiny turn-based worms/artillery game with teams and destructible terrain.
    """

    FRAME_MS = 45
    GRAVITY = 0.080

    def __init__(self, ctx=None):
        self.players_mode = get_context_setting(ctx, "players", "cpu")
        self.team_size = int(get_context_setting(ctx, "worms", 2) or 2)
        self.reset()

    def reset(self):
        self.score = 0
        self.turn_team = 0
        self.active = [0, 0]
        self.angle = 45
        self.power = 16
        self.wind = 0.0
        self.shell = None
        self.explosion = None
        self.last_fire = [False, False]
        self.cpu_wait = 26
        self.turns = 0
        self._terrain_dirty = True
        self._drawn_worms = []
        self._drawn_aim_bounds = None
        self._drawn_shell = None
        self._drawn_explosion = None
        self._new_match()

    def _new_match(self):
        self._terrain_dirty = True
        self.terrain = []
        base = 42
        for x in range(WIDTH):
            y = base + int(math.sin(x * 0.19) * 5) + int(math.sin(x * 0.055 + 1.4) * 4)
            self.terrain.append(clamp(y, 27, PLAY_HEIGHT - 2))
        self.worms = [[], []]
        left_slots = (8, 18, 28)
        right_slots = (55, 45, 35)
        for i in range(self.team_size):
            lx = left_slots[i]
            rx = right_slots[i]
            self.worms[0].append(
                {"x": float(lx), "y": float(self._ground_y(lx) - 2), "hp": 2}
            )
            self.worms[1].append(
                {"x": float(rx), "y": float(self._ground_y(rx) - 2), "hp": 2}
            )
        self._settle_all()
        self.turn_team = 0
        self.active = [0, 0]
        self._select_alive(0)
        self._select_alive(1)

    def _ground_y(self, x):
        return self.terrain[clamp(int(x), 0, WIDTH - 1)]

    def _active_worm(self):
        return self.worms[self.turn_team][self.active[self.turn_team]]

    def _select_alive(self, team):
        worms = self.worms[team]
        start = self.active[team] % len(worms)
        for off in range(len(worms)):
            idx = (start + off) % len(worms)
            if worms[idx]["hp"] > 0:
                self.active[team] = idx
                return True
        return False

    def _team_alive(self, team):
        for w in self.worms[team]:
            if w["hp"] > 0:
                return True
        return False

    def _settle_all(self):
        for team in range(2):
            for w in self.worms[team]:
                if w["hp"] <= 0:
                    continue
                ix = clamp(int(w["x"]), 0, WIDTH - 1)
                w["y"] = float(self._ground_y(ix) - 2)

    def _crater(self, cx, cy, radius=5):
        self.explosion = [int(cx), int(cy), 8]
        icx = int(cx)
        for x in range(max(0, icx - radius), min(WIDTH, icx + radius + 1)):
            d = abs(x - icx)
            cut = max(1, radius - d)
            self.terrain[x] = clamp(self.terrain[x] + cut, 22, PLAY_HEIGHT - 1)
        self._terrain_dirty = True
        self._damage_worms(cx, cy, radius + 2)
        self._settle_all()

    def _damage_worms(self, cx, cy, radius):
        r2 = radius * radius
        for team in range(2):
            for w in self.worms[team]:
                if w["hp"] <= 0:
                    continue
                dx = w["x"] - cx
                dy = w["y"] - cy
                if dx * dx + dy * dy <= r2:
                    w["hp"] -= 1
                    if team == 1:
                        self.score += 45

    def _next_turn(self):
        if not self._team_alive(0):
            set_game_over_score(self.score)
            return False
        if not self._team_alive(1):
            set_game_over_score(self.score + 250, won=True)
            return False
        self.turn_team = 1 - self.turn_team
        self.active[self.turn_team] = (self.active[self.turn_team] + 1) % len(
            self.worms[self.turn_team]
        )
        self._select_alive(self.turn_team)
        self.wind = random.choice((-1, 1)) * random.randint(0, 5) * 0.006
        self.shell = None
        self.cpu_wait = 26
        self.turns += 1
        if self.turn_team == 0:
            self.angle = 45
            self.power = 16
        return True

    def _fire(self, team, angle, power):
        if self.shell:
            return
        w = self._active_worm()
        sign = 1 if team == 0 else -1
        rad = math.radians(angle)
        speed = power * 0.12
        self.shell = [
            w["x"],
            w["y"] - 3,
            math.cos(rad) * speed * sign,
            -math.sin(rad) * speed,
            team,
        ]

    def _move_active(self, d):
        w = self._active_worm()
        if d == JOYSTICK_LEFT:
            nx = max(1.0, w["x"] - 1.0)
        elif d == JOYSTICK_RIGHT:
            nx = min(float(WIDTH - 2), w["x"] + 1.0)
        else:
            return
        gy = self._ground_y(nx)
        if abs((gy - 2) - w["y"]) <= 4:
            w["x"] = nx
            w["y"] = float(gy - 2)

    def _cpu_turn(self):
        if self.turn_team != 1 or self.shell:
            return
        self.cpu_wait -= 1
        if self.cpu_wait > 0:
            return
        enemy = self.worms[0][self.active[0]]
        me = self._active_worm()
        dx = abs(enemy["x"] - me["x"])
        angle = clamp(36 + random.randint(-5, 10) - int(self.wind * 180), 25, 72)
        power = clamp(int(dx / 4.0) + random.randint(4, 9), 9, 28)
        self._fire(1, angle, power)

    def _advance_shell(self):
        if not self.shell:
            return True
        for _ in range(2):
            self.shell[2] += self.wind
            self.shell[3] += self.GRAVITY
            self.shell[0] += self.shell[2]
            self.shell[1] += self.shell[3]
            x, y, _vx, _vy, _owner = self.shell
            if x < 0 or x >= WIDTH or y >= PLAY_HEIGHT:
                self.shell = None
                return self._next_turn()
            if y >= self._ground_y(x):
                self._crater(x, y)
                self.shell = None
                return self._next_turn()
            for team in range(2):
                for w in self.worms[team]:
                    if w["hp"] <= 0:
                        continue
                    dx = w["x"] - x
                    dy = w["y"] - y
                    if dx * dx + dy * dy <= 5:
                        self._crater(x, y)
                        self.shell = None
                        return self._next_turn()
        return True

    def _draw_worm(self, w, team, selected):
        if w["hp"] <= 0:
            return
        x = int(w["x"])
        y = int(w["y"])
        col = (80, 210, 255) if team == 0 else (255, 95, 75)
        draw_rectangle(x - 1, y - 1, x + 1, y + 1, *col)
        if selected:
            display.set_pixel(x, y - 3, 255, 255, 255)
        if w["hp"] > 1:
            display.set_pixel(x + 2, y, 255, 255, 255)

    def _draw_terrain(self):
        display.clear()
        draw_rectangle(0, 0, WIDTH - 1, PLAY_HEIGHT - 1, 0, 10, 24)
        for x, y in enumerate(self.terrain):
            draw_line(x, y, x, PLAY_HEIGHT - 1, 60, 92, 45)
            display.set_pixel(x, y, 120, 150, 70)

    def _restore_terrain_region(self, x0, y0, x1, y1):
        """Restore a dynamic sprite area from the unchanged terrain map."""
        x0 = max(0, int(x0))
        x1 = min(WIDTH - 1, int(x1))
        y0 = max(0, int(y0))
        y1 = min(PLAY_HEIGHT - 1, int(y1))
        sp = display.set_pixel
        for x in range(x0, x1 + 1):
            ground_y = self.terrain[x]
            for y in range(y0, y1 + 1):
                if y < ground_y:
                    sp(x, y, 0, 10, 24)
                elif y == ground_y:
                    sp(x, y, 120, 150, 70)
                else:
                    sp(x, y, 60, 92, 45)

    def _draw_aim(self):
        w = self._active_worm()
        sign = 1 if self.turn_team == 0 else -1
        rad = math.radians(self.angle)
        x0 = int(w["x"])
        y0 = int(w["y"] - 2)
        x1 = x0 + int(math.cos(rad) * 7 * sign)
        y1 = y0 - int(math.sin(rad) * 7)
        draw_line(x0, y0, x1, y1, 255, 255, 120)
        return min(x0, x1) - 1, min(y0, y1) - 1, max(x0, x1) + 1, max(y0, y1) + 1

    def _draw(self):
        if self._terrain_dirty:
            self._draw_terrain()
            self._terrain_dirty = False
        else:
            for x, y in self._drawn_worms:
                self._restore_terrain_region(x - 2, y - 4, x + 3, y + 2)
            if self._drawn_aim_bounds is not None:
                self._restore_terrain_region(*self._drawn_aim_bounds)
            if self._drawn_shell is not None:
                x, y = self._drawn_shell
                self._restore_terrain_region(x, y, x, y)
            if self._drawn_explosion is not None:
                self._restore_terrain_region(*self._drawn_explosion)

        drawn_worms = self._drawn_worms
        del drawn_worms[:]
        for team in range(2):
            for i, w in enumerate(self.worms[team]):
                self._draw_worm(
                    w, team, team == self.turn_team and i == self.active[team]
                )
                if w["hp"] > 0:
                    drawn_worms.append((int(w["x"]), int(w["y"])))
        aim_bounds = None
        if not self.shell and (self.turn_team == 0 or self.players_mode == "two"):
            aim_bounds = self._draw_aim()
        shell_pos = None
        if self.shell:
            shell_pos = int(self.shell[0]), int(self.shell[1])
            display.set_pixel(shell_pos[0], shell_pos[1], 255, 255, 180)
        explosion_bounds = None
        if self.explosion:
            x, y, t = self.explosion
            col = (255, 220, 40) if t & 1 else (255, 70, 30)
            draw_rect_outline(x - 2, y - 2, x + 2, y + 2, *col)
            explosion_bounds = x - 2, y - 2, x + 2, y + 2
            self.explosion[2] -= 1
            if self.explosion[2] <= 0:
                self.explosion = None
        draw_rectangle(0, PLAY_HEIGHT, WIDTH - 1, HEIGHT - 1, 0, 0, 0)
        draw_text_small(1, PLAY_HEIGHT, "A" + str(self.angle), 210, 210, 210)
        draw_text_small(19, PLAY_HEIGHT, "P" + str(self.power), 210, 210, 210)
        draw_text_small(43, PLAY_HEIGHT, "W" + str(int(self.wind * 100)), 180, 180, 180)
        self._drawn_aim_bounds = aim_bounds
        self._drawn_shell = shell_pos
        self._drawn_explosion = explosion_bounds
        display_flush()

    def _read_turn_input(self, joystick, joystick_fire):
        if self.players_mode == "two" and self.turn_team == 0:
            d, fire = read_wasd_input(
                [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT],
                debounce=True,
            )
            return d, fire
        d = joystick.read_direction(
            [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
        )
        return d, joystick_fire

    def _handle_player_turn(self, joystick, joystick_fire):
        if self.shell:
            return
        d, fire = self._read_turn_input(joystick, joystick_fire)
        if d == JOYSTICK_UP:
            self.angle = min(82, self.angle + 2)
        elif d == JOYSTICK_DOWN:
            self.angle = max(15, self.angle - 2)
        elif d in (JOYSTICK_LEFT, JOYSTICK_RIGHT):
            if fire:
                delta = 1 if d == JOYSTICK_RIGHT else -1
                self.power = clamp(self.power + delta, 6, 30)
            else:
                self._move_active(d)
        if (
            fire
            and not self.last_fire[self.turn_team]
            and d not in (JOYSTICK_LEFT, JOYSTICK_RIGHT)
        ):
            self._fire(self.turn_team, self.angle, self.power)
        self.last_fire[self.turn_team] = fire

    def _build_step(self, joystick):
        self.reset()
        begin_game(0)

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            if self.turn_team == 0 or self.players_mode == "two":
                self._handle_player_turn(joystick, z_button)
            else:
                self._cpu_turn()
                self.last_fire[1] = False
            if not self._advance_shell():
                return False
            self._draw()
            return True

        return step


class BattlezoneGame:
    """
    BTLZON
    Controls:
      - Left / Right: rotate
      - Up / Down: drive
      - Z: fire
      - C: return to menu
    Vector-style first-person tank combat with radar, shells, rocks, and waves.
    """

    FRAME_MS = 36
    FOV = 1.18

    def __init__(self, ctx=None):
        self.difficulty = get_context_setting(ctx, "difficulty", "normal")
        self.obstacles_enabled = bool(get_context_setting(ctx, "obstacles", True))
        self.reset()

    def reset(self):
        self.score = 0
        self.wave = 1
        self.lives = 4 if self.difficulty == "easy" else 3
        self.cooldown = 0
        self.flash = 0
        self.hit_flash = 0
        self.last_z = False
        self.frame = 0
        self.player_shots = []
        self.enemy_shells = []
        self.enemies = []
        self.rocks = []
        self.wave_delay = 0
        self._spawn_wave()

    def _difficulty_offset(self):
        if self.difficulty == "easy":
            return -1
        if self.difficulty == "hard":
            return 1
        return 0

    def _spawn_wave(self):
        self.player_shots = []
        self.enemy_shells = []
        self.enemies = []
        self.rocks = []
        diff = self._difficulty_offset()
        count = clamp(
            1 + (self.wave // 2) + (1 if diff > 0 and self.wave > 1 else 0), 1, 4
        )
        for i in range(count):
            side = -1 if i % 2 == 0 else 1
            bearing = side * (0.25 + random.randint(0, 52) / 100.0)
            dist = 48.0 + random.randint(0, 24) + i * 5
            strafe = side * (0.003 + random.randint(0, 5) / 1000.0)
            reload_base = 115 - self.wave * 5 - diff * 18
            reload = max(36, reload_base + random.randint(0, 36))
            kind = 1 if self.wave >= 4 and random.randint(0, 4) == 0 else 0
            self.enemies.append([bearing, dist, strafe, reload, kind, 0])
        if self.obstacles_enabled:
            rock_count = clamp(2 + self.wave // 3, 2, 5)
            for _ in range(rock_count):
                bearing = random.choice((-1, 1)) * (
                    0.18 + random.randint(0, 80) / 100.0
                )
                dist = 20.0 + random.randint(0, 52)
                size = 1 + random.randint(0, 2)
                self.rocks.append([bearing, dist, size])

    def _rotate_view(self, amount):
        for enemy in self.enemies:
            enemy[0] = clamp(enemy[0] + amount, -1.6, 1.6)
        for shell in self.enemy_shells:
            shell[0] = clamp(shell[0] + amount, -1.6, 1.6)
        for shot in self.player_shots:
            shot[0] = clamp(shot[0] + amount, -1.6, 1.6)
        for rock in self.rocks:
            rock[0] = clamp(rock[0] + amount, -1.6, 1.6)

    def _drive(self, amount):
        for enemy in self.enemies:
            enemy[1] = clamp(enemy[1] + amount, 10.0, 86.0)
        for shell in self.enemy_shells:
            shell[1] = clamp(shell[1] + amount, 1.0, 90.0)
        for rock in self.rocks:
            rock[1] = clamp(rock[1] + amount, 5.0, 90.0)
        for rock in self.rocks:
            if rock[1] < 8.0 and abs(rock[0]) < 0.15:
                self._take_hit()
                rock[1] = 46.0 + random.randint(0, 26)
                rock[0] = random.choice((-1, 1)) * (
                    0.45 + random.randint(0, 40) / 100.0
                )

    def _move_player(self, joystick):
        d = joystick.read_direction(
            [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
        )
        if d == JOYSTICK_LEFT:
            self._rotate_view(0.095)
        elif d == JOYSTICK_RIGHT:
            self._rotate_view(-0.095)
        elif d == JOYSTICK_UP:
            self._drive(-1.25)
        elif d == JOYSTICK_DOWN:
            self._drive(0.95)

    def _fire(self):
        if self.cooldown > 0:
            return
        self.cooldown = 14
        self.flash = 4
        self.player_shots.append([0.0, 4.0, 0])

    def _advance_enemy(self):
        diff = self._difficulty_offset()
        for enemy in self.enemies:
            speed = 0.06 + self.wave * 0.01 + (0.04 if enemy[4] else 0.0)
            enemy[0] += enemy[2] + math.sin(self.frame * 0.035 + enemy[1]) * 0.006
            if abs(enemy[0]) > 0.8:
                enemy[2] = -enemy[2]
            enemy[0] = clamp(enemy[0], -1.25, 1.25)
            if enemy[1] > 18:
                enemy[1] -= speed + diff * 0.015
            enemy[3] -= 1
            if enemy[5] > 0:
                enemy[5] -= 1
            if enemy[3] <= 0:
                self.enemy_shells.append([enemy[0], enemy[1], 0])
                enemy[3] = max(
                    32, 105 - self.wave * 6 - diff * 17 + random.randint(0, 30)
                )
        if self.wave_delay > 0:
            self.wave_delay -= 1
            if self.wave_delay <= 0:
                self.wave += 1
                self._spawn_wave()

    def _take_hit(self):
        if self.hit_flash > 0:
            return True
        self.lives -= 1
        self.hit_flash = 9
        if self.lives <= 0:
            set_game_over_score(self.score)
            return False
        return True

    def _hit_enemy(self, shot):
        for enemy in self.enemies:
            angular_window = 0.075 + clamp(7.0 / max(14.0, enemy[1]), 0.0, 0.22)
            if (
                abs(enemy[0] - shot[0]) <= angular_window
                and abs(enemy[1] - shot[1]) <= 4.5
            ):
                enemy[5] = 5
                self.score += 90 + self.wave * 20 + (40 if enemy[4] else 0)
                self.enemies.remove(enemy)
                return True
        return False

    def _hit_rock(self, shot):
        for rock in self.rocks:
            angular_window = 0.06 + rock[2] * 0.035
            if (
                abs(rock[0] - shot[0]) <= angular_window
                and abs(rock[1] - shot[1]) <= 4.0
            ):
                self.rocks.remove(rock)
                self.score += 8
                return True
        return False

    def _advance_shells(self):
        if self.cooldown > 0:
            self.cooldown -= 1
        if self.flash > 0:
            self.flash -= 1
        if self.hit_flash > 0:
            self.hit_flash -= 1
        kept_shots = []
        for shot in self.player_shots:
            shot[1] += 4.2
            shot[2] += 1
            if self._hit_enemy(shot) or self._hit_rock(shot):
                continue
            if shot[1] < 92 and shot[2] < 24:
                kept_shots.append(shot)
        self.player_shots = kept_shots
        kept_shells = []
        shell_speed = (
            2.0 + self.wave * 0.03 + (0.2 if self.difficulty == "hard" else 0.0)
        )
        for shell in self.enemy_shells:
            shell[1] -= shell_speed
            shell[2] += 1
            if shell[1] <= 4:
                if abs(shell[0]) < 0.16:
                    if not self._take_hit():
                        return False
                continue
            kept_shells.append(shell)
        self.enemy_shells = kept_shells
        if not self.enemies and self.wave_delay <= 0:
            self.score += 120 + self.wave * 25
            self.wave_delay = 28
        return True

    def _project(self, bearing, dist):
        if abs(bearing) > self.FOV:
            return None
        scale = clamp(96.0 / max(9.0, dist), 1.0, 9.0)
        cx = WIDTH // 2 + int(bearing * 39)
        cy = int(26 + (82.0 - dist) * 0.42)
        cy = clamp(cy, 18, PLAY_HEIGHT - 4)
        return cx, cy, scale

    def _draw_enemy(self, enemy):
        projected = self._project(enemy[0], enemy[1])
        if projected is None:
            return
        cx, cy, scale = projected
        w = int(3 + scale * 1.7)
        h = int(2 + scale * 0.75)
        col = (255, 110, 70) if enemy[4] else (70, 255, 90)
        if enemy[5] > 0:
            col = (255, 255, 180)
        draw_rect_outline(cx - w, cy - h, cx + w, cy + h, *col)
        draw_line(cx - w, cy + h, cx - w - int(2 + scale), cy + h + 2, *col)
        draw_line(cx + w, cy + h, cx + w + int(2 + scale), cy + h + 2, *col)
        draw_line(cx, cy - h, cx + int(enemy[0] * 6), cy - h - int(4 + scale), *col)
        if scale > 3:
            draw_line(cx - w, cy, cx + w, cy, *col)

    def _draw_rock(self, rock):
        projected = self._project(rock[0], rock[1])
        if projected is None:
            return
        cx, cy, scale = projected
        s = int(rock[2] + scale * 0.75)
        col = (85, 120, 85)
        draw_line(cx, cy - s, cx - s, cy + s, *col)
        draw_line(cx, cy - s, cx + s, cy + s, *col)
        draw_line(cx - s, cy + s, cx + s, cy + s, *col)

    def _draw_radar(self):
        draw_rect_outline(1, 1, 13, 13, 30, 110, 50)
        display.set_pixel(7, 7, 80, 255, 120)
        for rock in self.rocks:
            rr = clamp(rock[1] / 12, 2, 6)
            rx = 7 + int(math.sin(rock[0]) * rr)
            ry = 7 - int(math.cos(rock[0]) * rr)
            display.set_pixel(rx, ry, 70, 120, 70)
        for enemy in self.enemies:
            rr = clamp(enemy[1] / 11, 2, 6)
            ex = 7 + int(math.sin(enemy[0]) * rr)
            ey = 7 - int(math.cos(enemy[0]) * rr)
            draw_rectangle(ex - 1, ey - 1, ex + 1, ey + 1, 255, 80, 60)

    def _draw_grid(self):
        horizon = 27
        draw_line(0, horizon, WIDTH - 1, horizon, 30, 180, 70)
        for y in (33, 39, 45, 51, 56):
            fade = max(22, 100 - (y - horizon) * 2)
            draw_line(0, y, WIDTH - 1, y, 10, fade, 35)
        for x in (8, 20, 32, 44, 56):
            draw_line(WIDTH // 2, horizon, x, PLAY_HEIGHT - 1, 18, 120, 52)

    def _draw(self):
        display.clear()
        if self.hit_flash > 0 and self.hit_flash % 2:
            draw_rectangle(0, 0, WIDTH - 1, PLAY_HEIGHT - 1, 60, 0, 0)
        self._draw_grid()
        for rock in self.rocks:
            self._draw_rock(rock)
        for enemy in sorted(self.enemies, key=lambda e: e[1], reverse=True):
            self._draw_enemy(enemy)
        for shell in self.enemy_shells:
            projected = self._project(shell[0], shell[1])
            if projected:
                cx, cy, scale = projected
                r = max(1, int(scale // 2))
                draw_rectangle(cx - r, cy - r, cx + r, cy + r, 255, 220, 70)
        for shot in self.player_shots:
            projected = self._project(shot[0], shot[1])
            if projected:
                cx, cy, _scale = projected
                draw_rectangle(cx - 1, cy - 1, cx + 1, cy + 1, 255, 255, 180)
        if self.flash > 0:
            draw_line(28, PLAY_HEIGHT - 1, 32, 27, 255, 255, 160)
            draw_line(36, PLAY_HEIGHT - 1, 32, 27, 255, 255, 160)
            cross_col = (255, 255, 200)
        else:
            cross_col = (90, 255, 110)
        draw_line(28, 28, 36, 28, *cross_col)
        draw_line(32, 24, 32, 32, *cross_col)
        if self.wave_delay > 0:
            draw_text_small(21, 4, "W" + str(self.wave + 1), 255, 255, 180)
        self._draw_radar()
        draw_text_small(16, 1, "L" + str(self.lives), 220, 220, 220)
        draw_text_small(16, 7, "W" + str(self.wave), 160, 220, 160)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        self.reset()

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            self.frame += 1
            self._move_player(joystick)
            if z_button and not self.last_z:
                self._fire()
            self.last_z = z_button
            self._advance_enemy()
            if not self._advance_shells():
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


class KeenGame:
    """
    KEEN
    Controls:
      - Left / Right: run
      - Up or Z: jump
      - C: return to menu
    Compact Keen-style platformer with gems, keys, enemies, and exits.
    """

    FRAME_MS = 34
    CELL = 4
    VIEW_W = WIDTH
    PLAYER_W = 3
    PLAYER_H = 5
    MAPS = (
        (
            "########################################",
            "#......................................#",
            "#...........G..........................#",
            "#........######........................#",
            "#....................G.................#",
            "#.....####........########.......####..#",
            "#............................K.........#",
            "#..G............#####..................#",
            "#..........###..................G......#",
            "#......................######..........#",
            "#....###...............................#",
            "#P................S.............S...E..#",
            "#......................................#",
            "########################################",
        ),
        (
            "########################################",
            "#......................................#",
            "#.............................G........#",
            "#......#####.............########......#",
            "#..................G...................#",
            "#..G.........####............####......#",
            "#.................S....................#",
            "#............########..............K...#",
            "#......................................#",
            "#......S..............####.............#",
            "#....######............................#",
            "#P..................................E..#",
            "#......................................#",
            "########################################",
        ),
        (
            "########################################",
            "#......................................#",
            "#...G.....................K............#",
            "#..#####...............#########.......#",
            "#......................................#",
            "#...........G..........................#",
            "#.......########..............G........#",
            "#....................S.................#",
            "#..................######..............#",
            "#...S..................................#",
            "#..######...............####...........#",
            "#P..................................E..#",
            "#......................................#",
            "########################################",
        ),
    )

    def __init__(self):
        self.reset()

    def reset(self):
        self.level = 0
        self.score = 0
        self.last_jump = False
        self._load_level()

    def _load_level(self):
        self.map = [list(row) for row in self.MAPS[self.level % len(self.MAPS)]]
        self.map_w = len(self.map[0])
        self.map_h = len(self.map)
        self.items = []
        self.enemies = []
        self.key = False
        self.exit = (self.map_w - 2, 2)
        for y, row in enumerate(self.map):
            for x, ch in enumerate(row):
                if ch == "P":
                    self.px = float(x * self.CELL)
                    self.py = float(y * self.CELL - 1)
                    row[x] = "."
                elif ch == "G":
                    self.items.append([x * self.CELL + 1, y * self.CELL + 1, "gem"])
                    row[x] = "."
                elif ch == "K":
                    self.items.append([x * self.CELL + 1, y * self.CELL + 1, "key"])
                    row[x] = "."
                elif ch == "E":
                    self.exit = (x, y)
                    row[x] = "."
                elif ch == "S":
                    self.enemies.append(
                        [
                            float(x * self.CELL),
                            float(y * self.CELL + 4),
                            random.choice((-1, 1)),
                        ]
                    )
                    row[x] = "."
        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = False
        self.camera_x = 0

    def _solid_tile(self, tx, ty):
        if tx < 0 or tx >= self.map_w or ty < 0 or ty >= self.map_h:
            return True
        return self.map[ty][tx] == "#"

    def _rect_solid(self, x, y, w, h):
        left = int(x) // self.CELL
        right = int(x + w - 1) // self.CELL
        top = int(y) // self.CELL
        bottom = int(y + h - 1) // self.CELL
        for ty in range(top, bottom + 1):
            for tx in range(left, right + 1):
                if self._solid_tile(tx, ty):
                    return True
        return False

    def _move_axis(self, amount, axis):
        steps = int(abs(amount) + 1)
        delta = amount / steps
        for _ in range(steps):
            if axis == "x":
                nx = self.px + delta
                if self._rect_solid(nx, self.py, self.PLAYER_W, self.PLAYER_H):
                    self.vx = 0.0
                    break
                self.px = nx
            else:
                ny = self.py + delta
                if self._rect_solid(self.px, ny, self.PLAYER_W, self.PLAYER_H):
                    if delta > 0:
                        self.on_ground = True
                    self.vy = 0.0
                    break
                self.py = ny

    def _move_player(self, joystick, z_button):
        d = joystick.read_direction([JOYSTICK_UP, JOYSTICK_LEFT, JOYSTICK_RIGHT])
        if d == JOYSTICK_LEFT:
            self.vx = max(-1.55, self.vx - 0.35)
        elif d == JOYSTICK_RIGHT:
            self.vx = min(1.55, self.vx + 0.35)
        else:
            self.vx *= 0.76
        jump = z_button or d == JOYSTICK_UP
        if jump and not self.last_jump and self.on_ground:
            self.vy = -3.45
            self.on_ground = False
        self.last_jump = jump
        self.vy = min(3.0, self.vy + 0.20)
        self.on_ground = False
        self._move_axis(self.vx, "x")
        self._move_axis(self.vy, "y")
        self.px = clamp(self.px, 4.0, self.map_w * self.CELL - self.PLAYER_W - 4.0)
        self.camera_x = clamp(int(self.px) - 28, 0, self.map_w * self.CELL - WIDTH)

    def _overlap(self, ax, ay, aw, ah, bx, by, bw, bh):
        return not (ax + aw < bx or bx + bw < ax or ay + ah < by or by + bh < ay)

    def _collect_items(self):
        keep = []
        for x, y, kind in self.items:
            if self._overlap(
                self.px, self.py, self.PLAYER_W, self.PLAYER_H, x, y, 2, 2
            ):
                if kind == "key":
                    self.key = True
                    self.score += 50
                else:
                    self.score += 10
            else:
                keep.append([x, y, kind])
        self.items = keep

    def _move_enemies(self):
        keep = []
        for e in self.enemies:
            e[0] += e[2] * 0.45
            front_x = e[0] + (4 if e[2] > 0 else -1)
            foot_y = e[1] + 5
            if self._rect_solid(e[0], e[1], 4, 4) or not self._solid_tile(
                int(front_x) // self.CELL, int(foot_y) // self.CELL
            ):
                e[0] -= e[2] * 0.45
                e[2] = -e[2]
            if self._overlap(
                self.px, self.py, self.PLAYER_W, self.PLAYER_H, e[0], e[1], 4, 4
            ):
                if self.vy > 0.5 and self.py + self.PLAYER_H <= e[1] + 3:
                    self.score += 30
                    self.vy = -2.1
                    continue
                set_game_over_score(self.score)
                return False
            keep.append(e)
        self.enemies = keep
        return True

    def _check_exit(self):
        ex, ey = self.exit
        if not self.key:
            return True
        if self._overlap(
            self.px,
            self.py,
            self.PLAYER_W,
            self.PLAYER_H,
            ex * self.CELL,
            ey * self.CELL,
            4,
            7,
        ):
            self.score += 150 + self.level * 50
            self.level += 1
            if self.level >= len(self.MAPS):
                set_game_over_score(self.score, won=True)
                return False
            self._load_level()
        return True

    def _draw(self):
        display.clear()
        first_col = self.camera_x // self.CELL
        last_col = min(self.map_w, first_col + 18)
        for y, row in enumerate(self.map):
            sy = y * self.CELL
            for x in range(first_col, last_col):
                sx = x * self.CELL - self.camera_x
                if row[x] == "#":
                    draw_rectangle(sx, sy, sx + 3, sy + 3, 45, 80, 120)
        ex, ey = self.exit
        door_col = (240, 240, 255) if self.key else (95, 55, 130)
        draw_rect_outline(
            ex * self.CELL - self.camera_x,
            ey * self.CELL - 2,
            ex * self.CELL - self.camera_x + 4,
            ey * self.CELL + 6,
            *door_col,
        )
        for x, y, kind in self.items:
            sx = x - self.camera_x
            if -3 <= sx < WIDTH:
                col = (80, 230, 255) if kind == "key" else (255, 230, 70)
                draw_rectangle(int(sx), int(y), int(sx) + 1, int(y) + 1, *col)
        for x, y, _d in self.enemies:
            sx = int(x) - self.camera_x
            if -5 <= sx < WIDTH:
                draw_rectangle(sx, int(y), sx + 3, int(y) + 3, 255, 70, 70)
        px = int(self.px) - self.camera_x
        py = int(self.py)
        draw_rectangle(
            px, py, px + self.PLAYER_W - 1, py + self.PLAYER_H - 1, 240, 240, 230
        )
        display.set_pixel(px + 2, py + 1, 30, 30, 60)
        if self.key:
            draw_text_small(1, PLAY_HEIGHT, "KEY", 80, 230, 255)
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        self.reset()

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            self._move_player(joystick, z_button)
            self._collect_items()
            if not self._move_enemies():
                return False
            if not self._check_exit():
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


class PitfallGame:
    """
    PITFALL MINI (Endlos-Runner)
    Steuerung:
      - Links/Rechts: laufen
      - Z oder Stick UP: springen
      - C: zurück ins Menü
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.ground_y = PLAY_HEIGHT - 4
        self.pw = 3
        self.ph = 5
        self.px = 10
        self.py = float(self.ground_y - self.ph + 1)
        self.vy = 0.0
        self.on_ground = True

        self.speed = 0.9
        self.distance = 0.0
        self.bonus = 0
        self.score = 0

        self.obstacles = []
        self.jump_cd = 0
        self.last_spawn_kind = None
        self.frame = 0
        self.jump_start_frame = 0
        self.jump_charging = False
        self.jump_charge_max_frames = 10
        self.jump_min_power = -3.2
        self.jump_max_power = -6.5

        # Start-of-run grace period: no snakes/holes at the very beginning.
        # We enforce this via spawn logic so it works for both desktop and RP2040.
        self._safe_distance = 30.0

    def _spawn_one(self, x_start):
        # At the start, spawn only treasures to avoid immediate frustration.
        if self.distance < self._safe_distance:
            kind = "TREASURE"
        else:
            r = random.randint(0, 99)
            kind = "PIT" if r < 45 else ("SNAKE" if r < 75 else "TREASURE")

        # nicht zu viele pits hintereinander
        if (
            kind == "PIT"
            and self.last_spawn_kind == "PIT"
            and random.randint(0, 99) < 55
        ):
            kind = "SNAKE"

        if kind == "PIT":
            w = random.randint(8, 16)
            self.obstacles.append({"kind": "PIT", "x": float(x_start), "w": w})
        elif kind == "SNAKE":
            w = random.randint(5, 8)
            self.obstacles.append({"kind": "SNAKE", "x": float(x_start), "w": w})
        else:
            ty = self.ground_y - random.choice([12, 16, 20])
            self.obstacles.append(
                {
                    "kind": "TREASURE",
                    "x": float(x_start),
                    "y": ty,
                    "w": 2,
                    "h": 2,
                    "got": False,
                }
            )

        self.last_spawn_kind = kind

    def _ensure_obstacles(self):
        max_right = None
        for o in self.obstacles:
            w = o.get("w", 1)
            xr = o["x"] + w
            if max_right is None or xr > max_right:
                max_right = xr

        if max_right is None:
            max_right = WIDTH + 8

        while max_right < WIDTH + 20:
            gap = random.randint(14, 28)
            spawn_x = max_right + gap
            self._spawn_one(spawn_x)
            max_right = spawn_x + self.obstacles[-1].get("w", 1)

    def _player_in_pit(self):
        foot = self.px + (self.pw // 2)
        for o in self.obstacles:
            if o["kind"] == "PIT":
                if o["x"] <= foot <= (o["x"] + o["w"] - 1):
                    return True
        return False

    def _check_snake_collision(self):
        # nur gefährlich, wenn Spieler nahe am Boden ist
        player_bottom = int(self.py) + self.ph - 1
        if player_bottom < (self.ground_y - 2):
            return False

        px1 = self.px
        px2 = self.px + self.pw - 1
        py1 = int(self.py)
        py2 = py1 + self.ph - 1

        sy1 = self.ground_y - 2
        sy2 = self.ground_y - 1

        for o in self.obstacles:
            if o["kind"] != "SNAKE":
                continue
            sx1 = int(o["x"])
            sx2 = sx1 + o["w"] - 1

            if sx2 < px1 or px2 < sx1:
                continue
            if sy2 < py1 or py2 < sy1:
                continue
            return True
        return False

    def _check_treasure(self):
        px1 = self.px
        px2 = self.px + self.pw - 1
        py1 = int(self.py)
        py2 = py1 + self.ph - 1

        for o in self.obstacles:
            if o["kind"] != "TREASURE" or o.get("got"):
                continue

            tx1 = int(o["x"])
            ty1 = int(o["y"])
            tx2 = tx1 + o["w"] - 1
            ty2 = ty1 + o["h"] - 1

            if tx2 < px1 or px2 < tx1:
                continue
            if ty2 < py1 or py2 < ty1:
                continue

            o["got"] = True
            self.bonus += 25

    def _rect_play(self, x, y, w, h, r, g, b):
        # reuse shared helper to draw playfield rectangles
        draw_play_rect(x, y, w, h, r, g, b)

    def _render(self):
        display.clear()

        # Boden-Band
        self._rect_play(
            0, self.ground_y, WIDTH, PLAY_HEIGHT - self.ground_y, 40, 90, 40
        )

        # Pits (Löcher)
        for o in self.obstacles:
            if o["kind"] == "PIT":
                x = int(o["x"])
                self._rect_play(
                    x, self.ground_y, o["w"], PLAY_HEIGHT - self.ground_y, 0, 0, 0
                )

        # Schlangen
        for o in self.obstacles:
            if o["kind"] == "SNAKE":
                x = int(o["x"])
                self._rect_play(x, self.ground_y - 2, o["w"], 2, 255, 40, 40)
                ey = self.ground_y - 2
                if 0 <= ey < PLAY_HEIGHT:
                    if 0 <= x + 1 < WIDTH:
                        display.set_pixel(x + 1, ey, 0, 0, 0)
                    if 0 <= x + o["w"] - 2 < WIDTH:
                        display.set_pixel(x + o["w"] - 2, ey, 0, 0, 0)

        # Treasure
        for o in self.obstacles:
            if o["kind"] == "TREASURE" and not o.get("got"):
                tx = int(o["x"])
                ty = int(o["y"])
                self._rect_play(tx, ty, o["w"], o["h"], 255, 215, 0)

        # Spieler
        self._rect_play(self.px, int(self.py), self.pw, self.ph, 230, 230, 230)
        hx = self.px + 1
        hy = int(self.py)
        if 0 <= hx < WIDTH and 0 <= hy < PLAY_HEIGHT:
            display.set_pixel(hx, hy, 0, 0, 0)

        display_score_and_time(self.score)

    def main_loop(self, joystick):
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        self._ensure_obstacles()

        frame_ms = 33
        last_frame = ticks_ms()

        while not game_over:
            try:
                c_button, z_button = joystick.read_buttons()
                if c_button:
                    return

                now = ticks_ms()
                if ticks_diff(now, last_frame) < frame_ms:
                    sleep_ms(2)
                    continue
                last_frame = now
                self.frame += 1

                # difficulty
                self.speed = 1.2 + (self.distance / 800.0)
                if self.speed > 2.6:
                    self.speed = 2.6

                # scroll obstacles
                for o in self.obstacles:
                    o["x"] -= self.speed

                # cleanup
                self.obstacles = [
                    o for o in self.obstacles if (o.get("x", 0) + o.get("w", 1)) > -2
                ]
                self._ensure_obstacles()

                # move
                d = joystick.read_direction(
                    [JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_UP]
                )
                if d == JOYSTICK_LEFT:
                    self.px = max(0, self.px - 2)
                elif d == JOYSTICK_RIGHT:
                    self.px = min(WIDTH - self.pw, self.px + 2)

                # jump with variable height
                if self.jump_cd > 0:
                    self.jump_cd -= 1

                jump_pressed = z_button or d == JOYSTICK_UP
                if jump_pressed and self.on_ground and self.jump_cd == 0:
                    if not self.jump_charging:
                        self.jump_charging = True
                        self.jump_start_frame = self.frame
                    else:
                        # cap charge: auto-release after max frames
                        hold_frames = self.frame - self.jump_start_frame
                        if hold_frames >= self.jump_charge_max_frames:
                            self.vy = self.jump_max_power
                            self.on_ground = False
                            self.jump_cd = 10
                            self.jump_charging = False
                elif not jump_pressed and self.jump_charging:
                    # release: jump with height based on hold duration
                    hold_frames = self.frame - self.jump_start_frame
                    if hold_frames < 0:
                        hold_frames = 0
                    if hold_frames > self.jump_charge_max_frames:
                        hold_frames = self.jump_charge_max_frames

                    jump_power = self.jump_min_power - (hold_frames * 0.35)
                    # clamp: don't exceed max power
                    if jump_power < self.jump_max_power:
                        jump_power = self.jump_max_power

                    self.vy = jump_power
                    self.on_ground = False
                    self.jump_cd = 10
                    self.jump_charging = False

                # physics
                in_pit = self._player_in_pit()
                self.vy += 0.45
                self.py += self.vy

                if not in_pit:
                    if (self.py + self.ph - 1) >= self.ground_y:
                        self.py = float(self.ground_y - self.ph + 1)
                        self.vy = 0.0
                        self.on_ground = True
                    else:
                        self.on_ground = False
                else:
                    self.on_ground = False

                # collect
                self._check_treasure()

                # lose
                if self._check_snake_collision() or self.py > PLAY_HEIGHT + 2:
                    global_score = self.score
                    game_over = True
                    return

                # score
                self.distance += self.speed
                self.score = int(self.distance / 6) + self.bonus
                global_score = self.score

                self._render()

                if self.frame % 40 == 0:
                    gc.collect()

            except RestartProgram:
                return

    async def main_loop_async(self, joystick):
        """Async version for pygbag: yields with asyncio.sleep()."""
        if asyncio is None:
            return self.main_loop(joystick)

        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        self._ensure_obstacles()

        def loop_iteration():
            global game_over, global_score
            c_button, z_button = joystick.read_buttons()
            if c_button or game_over:
                return False

            self.frame += 1

            # difficulty
            self.speed = 1.2 + (self.distance / 800.0)
            if self.speed > 2.6:
                self.speed = 2.6

            # scroll obstacles
            for o in self.obstacles:
                o["x"] -= self.speed

            # cleanup
            self.obstacles = [
                o for o in self.obstacles if (o.get("x", 0) + o.get("w", 1)) > -2
            ]
            self._ensure_obstacles()

            # move
            d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_UP])
            if d == JOYSTICK_LEFT:
                self.px = max(0, self.px - 2)
            elif d == JOYSTICK_RIGHT:
                self.px = min(WIDTH - self.pw, self.px + 2)

            # jump with variable height
            if self.jump_cd > 0:
                self.jump_cd -= 1

            jump_pressed = z_button or d == JOYSTICK_UP
            if jump_pressed and self.on_ground and self.jump_cd == 0:
                if not self.jump_charging:
                    self.jump_charging = True
                    self.jump_start_frame = self.frame
                else:
                    hold_frames = self.frame - self.jump_start_frame
                    if hold_frames >= self.jump_charge_max_frames:
                        self.vy = self.jump_max_power
                        self.on_ground = False
                        self.jump_cd = 10
                        self.jump_charging = False
            elif not jump_pressed and self.jump_charging:
                hold_frames = self.frame - self.jump_start_frame
                if hold_frames < 0:
                    hold_frames = 0
                if hold_frames > self.jump_charge_max_frames:
                    hold_frames = self.jump_charge_max_frames

                jump_power = self.jump_min_power - (hold_frames * 0.35)
                if jump_power < self.jump_max_power:
                    jump_power = self.jump_max_power

                self.vy = jump_power
                self.on_ground = False
                self.jump_cd = 10
                self.jump_charging = False

            # physics
            in_pit = self._player_in_pit()
            self.vy += 0.45
            self.py += self.vy

            if not in_pit:
                if (self.py + self.ph - 1) >= self.ground_y:
                    self.py = float(self.ground_y - self.ph + 1)
                    self.vy = 0.0
                    self.on_ground = True
                else:
                    self.on_ground = False
            else:
                self.on_ground = False

            self._check_treasure()

            if self._check_snake_collision() or self.py > PLAY_HEIGHT + 2:
                global_score = self.score
                game_over = True
                return False

            self.distance += self.speed
            self.score = int(self.distance / 6) + self.bonus
            global_score = self.score
            self._render()
            return True

        try:
            await _run_game_loop_async(33, loop_iteration)
        except RestartProgram:
            return


class Game2048:
    """
    2048
    Controls:
      - Left / Right / Up / Down: slide tiles
      - Z (hold): reset board
      - C: return to menu
    """

    # 2048 visual and timing constants (class-scoped)
    TILE_PX = 12
    COL_BG = (0, 0, 0)
    COL_EMPTY = (10, 10, 30)
    COL_FRAME = (0, 50, 120)
    COL_TXT = (200, 200, 200)
    COL_CURSOR = (255, 255, 0)

    COL_VAL = {
        2: (238, 228, 218),
        4: (237, 224, 200),
        8: (242, 177, 121),
        16: (245, 149, 99),
        32: (246, 124, 95),
        64: (246, 94, 59),
        128: (237, 207, 114),
        256: (237, 204, 97),
        512: (237, 200, 80),
        1024: (237, 197, 63),
        2048: (237, 194, 46),
    }

    INPUT_MS = 120
    MOVE_LOCK_MS = 200
    A_LONG_MS = 420

    def __init__(self, ctx=None):
        """Initialize the 2048 game wrapper and bind runtime helpers.

        Supports `ctx` being either a dict or an object that provides
        runtime symbols (display, timing, helpers). Falls back to
        module-level globals when symbols are missing.
        """
        # bind runtime symbols into module globals for legacy code paths
        if ctx is None:
            ctx = {}

        def _g(name):
            """Return a symbol by name from `ctx` or from globals()."""
            if isinstance(ctx, dict):
                return ctx.get(name, globals().get(name))
            return getattr(ctx, name, globals().get(name))

        try:
            self.display = _g("display")
            self.draw_text = _g("draw_text")
            self.draw_rectangle = _g("draw_rectangle")
            self.display_score_and_time = _g("display_score_and_time")
            self.ticks_ms = _g("ticks_ms")
            self.ticks_diff = _g("ticks_diff")
            self.sleep_ms = _g("sleep_ms")
        except Exception:
            # fall back to module globals if lookup fails
            self.display = globals().get("display")
            self.draw_text = globals().get("draw_text")
            self.draw_rectangle = globals().get("draw_rectangle")
            self.display_score_and_time = globals().get("display_score_and_time")
            self.ticks_ms = globals().get("ticks_ms")
            self.ticks_diff = globals().get("ticks_diff")
            self.sleep_ms = globals().get("sleep_ms")

        # use fixed 4x4 grid for 2048 (avoid conflicts with global GRID_W/GIRD_H)
        self.GRID_W = 4
        self.GRID_H = 4
        self.TILE_PX = 12
        self.GRID_PX = self.GRID_W * self.TILE_PX

        self.grid = [0] * (self.GRID_W * self.GRID_H)
        self.score = 0
        self.moves = 0
        self.max_val = 0
        self.victory = False

        self._last_input = self.ticks_ms()
        self._input_locked_until = 0
        self._z_down_ms = None
        self._z_armed = False

        # compute layout offsets now that WIDTH / PLAY_HEIGHT exist
        try:
            self.off_x = (WIDTH - self.GRID_PX) // 2
            self.off_y = (PLAY_HEIGHT - self.GRID_PX) // 2
        except Exception:
            self.off_x = 0
            self.off_y = 0

        self.reset()

    def _idx(self, x, y):
        """Return linear index into the GRID from tile coordinates (x, y)."""
        return y * self.GRID_W + x

    def _tile_rect(self, x, y):
        """Return pixel rectangle for tile (x, y) in grid coordinates."""
        x1 = self.off_x + x * self.TILE_PX
        y1 = self.off_y + y * self.TILE_PX
        return x1, y1, x1 + self.TILE_PX - 1, y1 + self.TILE_PX - 1

    def reset(self):
        """Reset the 2048 board and spawn the initial tiles."""
        for i in range(self.GRID_W * self.GRID_H):
            self.grid[i] = 0
        self.score = 0
        self.moves = 0
        self.max_val = 0
        self.victory = False
        self._spawn_random()
        self._spawn_random()
        self._input_locked_until = 0
        if self.display:
            self.display.clear()
        self._draw_board(full=True)
        if self.display_score_and_time:
            self.display_score_and_time(self.score, force=True)

    def _spawn_random(self):
        """Spawn a new tile (2 or 4) at a random empty grid position."""
        free = [i for i, v in enumerate(self.grid) if v == 0]
        if not free:
            return
        pos = random.choice(free)
        self.grid[pos] = 4 if random.random() < 0.1 else 2

    def _compress_line(self, line):
        """Compress and merge a single row/column for a 2048 move.

        Returns the new line and the score delta from merges.
        """
        out = []
        score_delta = 0
        skip = False
        for i in range(len(line)):
            if skip:
                skip = False
                continue
            if i + 1 < len(line) and line[i] == line[i + 1]:
                merged = line[i] * 2
                score_delta += merged
                out.append(merged)
                skip = True
            else:
                out.append(line[i])
        # Ensure the returned line has exactly GRID_W elements
        if len(out) < self.GRID_W:
            out += [0] * (self.GRID_W - len(out))
        elif len(out) > self.GRID_W:
            out = out[: self.GRID_W]
        return out, score_delta

    def _move(self, dir_idx):
        """Perform a move in one of four directions (dir_idx 0-3).

        Returns a tuple (changed, score_gain) indicating whether the
        board changed and how much score was gained from merges.
        """
        changed = False
        score_gain = 0

        for idx in range(self.GRID_W):
            if dir_idx in (0, 2):
                col = [self.grid[self._idx(idx, y)] for y in range(self.GRID_H)]
                if dir_idx == 2:
                    col.reverse()
                packed = [v for v in col if v]
                new_line, gain = self._compress_line(packed)
                score_gain += gain
                if dir_idx == 2:
                    new_line.reverse()
                for y in range(self.GRID_H):
                    if self.grid[self._idx(idx, y)] != new_line[y]:
                        changed = True
                    self.grid[self._idx(idx, y)] = new_line[y]
            else:
                row = [self.grid[self._idx(x, idx)] for x in range(self.GRID_W)]
                if dir_idx == 1:
                    row.reverse()
                packed = [v for v in row if v]
                new_line, gain = self._compress_line(packed)
                score_gain += gain
                if dir_idx == 1:
                    new_line.reverse()
                for x in range(self.GRID_W):
                    if self.grid[self._idx(x, idx)] != new_line[x]:
                        changed = True
                    self.grid[self._idx(x, idx)] = new_line[x]

        if changed:
            self.score += score_gain
            self.moves += 1
            self.max_val = max(self.grid)
            if self.max_val >= 2048:
                self.victory = True
            self._spawn_random()
        return changed

    def _any_moves_possible(self):
        """Return True if any move (or spawn) is possible on the board."""
        if any(v == 0 for v in self.grid):
            return True
        for y in range(self.GRID_H):
            for x in range(self.GRID_W):
                v = self.grid[self._idx(x, y)]
                if x + 1 < self.GRID_W and self.grid[self._idx(x + 1, y)] == v:
                    return True
                if y + 1 < self.GRID_H and self.grid[self._idx(x, y + 1)] == v:
                    return True
        return False

    def _draw_tile(self, x, y):
        """Draw an individual 2048 tile at grid position (x, y)."""
        val = self.grid[self._idx(x, y)]
        x1, y1, x2, y2 = self._tile_rect(x, y)
        col = self.COL_EMPTY if val == 0 else self.COL_VAL.get(val, (255, 255, 255))
        if self.draw_rectangle:
            self.draw_rectangle(x1, y1, x2, y2, *col)
            draw_rect_outline(x1, y1, x2, y2, *self.COL_FRAME)
        if val:
            try:
                # Represent tile values as single-character levels:
                # 2 -> '1', 4 -> '2', 8 -> '3', ..., 1024 -> 'A', 2048 -> 'B'
                v = val
                lvl = 0
                while v > 1:
                    v >>= 1
                    lvl += 1
                if lvl <= 9:
                    txt = str(lvl)
                else:
                    txt = chr(ord("A") + (lvl - 10))
                tw = 4  # single char width
                tx = x1 + (self.TILE_PX - tw) // 2
                ty = y1 + (self.TILE_PX - 6) // 2
                if self.draw_text:
                    self.draw_text(tx, ty, txt, 0, 0, 0)
            except Exception:
                pass

    def _draw_board(self, full=False):
        """Draw the full 2048 board or only the changed tiles."""
        if full:
            for y in range(self.GRID_H):
                for x in range(self.GRID_W):
                    self._draw_tile(x, y)
        else:
            self._draw_board(full=True)

        if self.display_score_and_time:
            self.display_score_and_time(self.score)

    def main_loop(self, joystick):
        """Main loop for 2048: process input and apply moves."""
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        self.ticks_ms()

        while True:
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return
            now = self.ticks_ms()

            if z_button:
                if self._z_down_ms is None:
                    self._z_down_ms = now
                    self._z_armed = True
                elif (
                    self._z_armed
                    and self.ticks_diff(now, self._z_down_ms) >= self.A_LONG_MS
                ):
                    self._z_armed = False
                    self.reset()
            else:
                if self._z_down_ms is not None:
                    self._z_down_ms = None
                    self._z_armed = False

            if self.ticks_diff(now, self._last_input) < self.INPUT_MS:
                self.sleep_ms(5)
                continue

            if self.ticks_diff(now, self._input_locked_until) < 0:
                self.sleep_ms(5)
                continue

            d = joystick.read_direction(
                [JOYSTICK_UP, JOYSTICK_RIGHT, JOYSTICK_DOWN, JOYSTICK_LEFT]
            )
            if d is not None:
                # Map JOYSTICK_* tokens to numeric directions expected by
                # _move(): 0=UP, 1=RIGHT, 2=DOWN, 3=LEFT
                dir_map = {
                    JOYSTICK_UP: 0,
                    JOYSTICK_RIGHT: 1,
                    JOYSTICK_DOWN: 2,
                    JOYSTICK_LEFT: 3,
                }
                dir_idx = dir_map.get(d, None)
                if dir_idx is not None:
                    moved = self._move(dir_idx)
                else:
                    moved = False
                if moved:
                    self._draw_board(full=False)
                    self._input_locked_until = now + self.MOVE_LOCK_MS
                    if not self._any_moves_possible():
                        if self.display:
                            self.display.clear()
                        draw_centered_text_lines(("LOSE",), start_y=18, r=255, g=0, b=0)
                        set_game_over_score(self.score, won=False)
                        if self.display_score_and_time:
                            self.display_score_and_time(self.score, force=True)
                        self.sleep_ms(1000)
                        return
                    elif self.victory:
                        if self.display:
                            self.display.clear()
                        draw_centered_text_lines(("WIN!",), start_y=18, r=0, g=255, b=0)
                        set_game_over_score(self.score, won=True)
                        if self.display_score_and_time:
                            self.display_score_and_time(self.score, force=True)
                        self.sleep_ms(700)
                        return
                self._last_input = now

            self.sleep_ms(2)
            if (now & 0x3FF) == 0:
                gc.collect()

    async def main_loop_async(self, joystick):
        """Async/cooperative version of the 2048 main loop for browsers.

        Uses `await asyncio.sleep()` instead of blocking `sleep_ms()` so the
        event loop remains responsive in WASM/pygbag environments.
        """
        if asyncio is None:
            return self.main_loop(joystick)

        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        self.ticks_ms()

        while True:
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return
            now = self.ticks_ms()

            if z_button:
                if self._z_down_ms is None:
                    self._z_down_ms = now
                    self._z_armed = True
                elif (
                    self._z_armed
                    and self.ticks_diff(now, self._z_down_ms) >= self.A_LONG_MS
                ):
                    self._z_armed = False
                    self.reset()
            else:
                if self._z_down_ms is not None:
                    self._z_down_ms = None
                    self._z_armed = False

            if self.ticks_diff(now, self._last_input) < self.INPUT_MS:
                await asyncio.sleep(0.005)
                continue

            if self.ticks_diff(now, self._input_locked_until) < 0:
                await asyncio.sleep(0.005)
                continue

            d = joystick.read_direction(
                [
                    JOYSTICK_UP,
                    JOYSTICK_RIGHT,
                    JOYSTICK_DOWN,
                    JOYSTICK_LEFT,
                ]
            )
            if d is not None:
                dir_map = {
                    JOYSTICK_UP: 0,
                    JOYSTICK_RIGHT: 1,
                    JOYSTICK_DOWN: 2,
                    JOYSTICK_LEFT: 3,
                }
                dir_idx = dir_map.get(d, None)
                if dir_idx is not None:
                    moved = self._move(dir_idx)
                else:
                    moved = False
                if moved:
                    self._draw_board(full=False)
                    self._input_locked_until = now + self.MOVE_LOCK_MS
                    if not self._any_moves_possible():
                        if self.display:
                            self.display.clear()
                        draw_centered_text_lines(("LOSE",), start_y=18, r=255, g=0, b=0)
                        set_game_over_score(self.score, won=False)
                        if self.display_score_and_time:
                            self.display_score_and_time(self.score, force=True)
                        await asyncio.sleep(1.0)
                        return
                    elif self.victory:
                        if self.display:
                            self.display.clear()
                        draw_centered_text_lines(("WIN!",), start_y=18, r=0, g=255, b=0)
                        set_game_over_score(self.score, won=True)
                        if self.display_score_and_time:
                            self.display_score_and_time(self.score, force=True)
                        await asyncio.sleep(0.7)
                        return
                self._last_input = now

            await asyncio.sleep(0.002)
            if (now & 0x3FF) == 0:
                try:
                    gc.collect()
                except Exception:
                    pass


try:
    from micropython import const
except ImportError:

    def const(x):
        """Fallback `const` implementation for non-MicroPython builds.

        Returns the input value unchanged. Used to allow the code to
        run under CPython during development.
        """
        return x


class LocoMotionGame:
    """
    LOCO-MOTION
    Controls:
      - Left / Right / Up / Down: move cursor
      - Z (tap): rotate tile under cursor
      - Z (tap on start/end or hold): start / abort train run
      - C: return to menu
    """

    # LocoMotion constants
    RL_TILE = 8
    RL_W = 8
    RL_H = 7
    RL_PX_W = RL_W * RL_TILE
    RL_PX_H = RL_H * RL_TILE

    N = 1
    E = 2
    S = 4
    W = 8

    TFLAG_NONE = 0x00
    TFLAG_START = 0x10
    TFLAG_END = 0x20
    TFLAG_EMPTY = 0x30

    COL_BG = (0, 0, 0)
    COL_TILE_BG = (0, 0, 0)
    COL_RAIL = (180, 180, 180)
    COL_RAIL2 = (80, 80, 80)
    COL_START = (0, 255, 0)
    COL_END = (255, 200, 0)
    COL_CURSOR = (255, 255, 0)
    COL_TRAIN = (255, 60, 60)
    COL_SHADOW = (40, 40, 40)

    EDIT_INPUT_MS = 120
    FRAME_MS_RUN = 35
    Z_LONG_MS = 420

    SYM_BITS = {
        ord("."): 0,
        ord("-"): E | W,
        ord("|"): N | S,
        ord("L"): N | E,
        ord("J"): E | S,
        ord("7"): S | W,
        ord("F"): W | N,
        ord("+"): N | E | S | W,
        ord("T"): N | E | W,
    }

    LEVELS = [
        (
            b"SL..L..E",
            b".|..|..|",
            b".|..|..|",
            b".L--J..|",
            b"....F--J",
            b"........",
            b"........",
        ),
        (
            b"SL.L--JE",
            b".--J..|.",
            b".|....|.",
            b".|.L--J.",
            b".|.|....",
            b".L-J....",
            b"........",
        ),
        (
            b"S..T..E.",
            b"JJ.LJ.|.",
            b".|....|.",
            b".L--7.|.",
            b"....|.|.",
            b"....L-J.",
            b"........",
        ),
        (
            b"SL..L..E",
            b".|..|..|",
            b".|..|..|",
            b".L--J..|",
            b"..-.F--J",
            b"..-.....",
            b"..---...",
        ),
        (
            b"SL.L..E.",
            b"---J..|.",
            b".T..L.|.",
            b".L--JLL.",
            b"..|.--.|",
            b"..L-JJ..",
            b"........",
        ),
        (
            b"S----7..",
            b".....|..",
            b".....|..",
            b".....|..",
            b"E----F..",
            b"........",
            b"........",
        ),
        (
            b"S--7....",
            b"..|.F--E",
            b"..L-7...",
            b"....|...",
            b".F--J...",
            b".|......",
            b".L--T...",
        ),
    ]

    def __init__(self, ctx=None):
        """Initialize LocoMotionGame and bind optional runtime symbols.

        `ctx` may be a dict or object providing platform helpers; missing
        symbols are left to module globals.
        """
        if ctx is None:
            ctx = {}

        def _g(name):
            """Return symbol `name` from `ctx` or fallback to globals()."""
            if isinstance(ctx, dict):
                return ctx.get(name, globals().get(name))
            return getattr(ctx, name, globals().get(name))

        g = globals()
        try:
            g["display"] = _g("display")
            g["draw_text"] = _g("draw_text")
            g["draw_rectangle"] = _g("draw_rectangle")
            g["display_score_and_time"] = _g("display_score_and_time")
            g["ticks_ms"] = _g("ticks_ms")
            g["ticks_diff"] = _g("ticks_diff")
            g["sleep_ms"] = _g("sleep_ms")
        except Exception:
            pass

        self.level_idx = 0
        self.score = 0
        self._z_down_ms = None
        self._z_armed = False

        self.mode_run = False
        self.cur_x = 0
        self.cur_y = 0

        self.tr_cx = 0
        self.tr_cy = 0
        self.tr_dir = 1
        self.tr_prog = 0
        self.tr_speed = 2
        self.last_tr_px = None
        self.last_tr_py = None

        self.tiles = bytearray(self.RL_W * self.RL_H)

        self._last_input_ms = ticks_ms()
        # compute offsets now that PLAY_HEIGHT exists
        try:
            self.rl_off_x = 0
            self.rl_off_y = (PLAY_HEIGHT - self.RL_PX_H) // 2
        except Exception:
            self.rl_off_x = 0
            self.rl_off_y = 0

        self.load_level(self.level_idx, reset_score=True)

    def _idx(self, x, y):
        """Return linear index for loco-motion grid coordinates (x, y)."""
        return y * self.RL_W + x

    @classmethod
    def _rot_cw(cls, bits):
        """Rotate a 4-bit direction mask clockwise and return new mask."""
        oldN = bits & cls.N
        oldE = bits & cls.E
        oldS = bits & cls.S
        oldW = bits & cls.W
        nb = 0
        if oldW:
            nb |= cls.N
        if oldN:
            nb |= cls.E
        if oldE:
            nb |= cls.S
        if oldS:
            nb |= cls.W
        return nb & 0x0F

    @staticmethod
    def _opp_dir(d):
        """Return the opposite direction for a 0-3 direction index."""
        return (d + 2) & 3

    @classmethod
    def _dir_to_bit(cls, d):
        """Convert a direction index (0-3) to the corresponding bit mask."""
        return (cls.N, cls.E, cls.S, cls.W)[d & 3]

    @classmethod
    def _bit_to_dir(cls, bit):
        """Convert a direction bit mask to a 0-3 direction index."""
        if bit == cls.N:
            return 0
        if bit == cls.E:
            return 1
        if bit == cls.S:
            return 2
        return 3

    @staticmethod
    def _right_dir(d):
        """Return the direction index to the right of `d`."""
        return (d + 1) & 3

    @staticmethod
    def _left_dir(d):
        """Return the direction index to the left of `d`."""
        return (d + 3) & 3

    def _get(self, x, y):
        """Return the tile flags/value at (x, y) or empty if out of bounds."""
        if x < 0 or x >= self.RL_W or y < 0 or y >= self.RL_H:
            return self.TFLAG_EMPTY | 0
        return self.tiles[self._idx(x, y)]

    def _set(self, x, y, v):
        """Set tile flags/value at (x, y) when inside the grid."""
        if 0 <= x < self.RL_W and 0 <= y < self.RL_H:
            self.tiles[self._idx(x, y)] = v & 0x3F

    def load_level(self, level_idx, reset_score=False):
        """Load the specified level and initialize runtime flags."""
        if reset_score:
            self.score = 0
        self.level_idx = level_idx % len(self.LEVELS)
        self.mode_run = False
        self._z_down_ms = None
        self._z_armed = False

        raw = self.LEVELS[self.level_idx]
        sx = sy = 0
        ex = ey = 0

        for y in range(self.RL_H):
            row = raw[y]
            for x in range(self.RL_W):
                ch = row[x]
                bits = 0
                flag = self.TFLAG_NONE

                if ch == ord("S"):
                    flag = self.TFLAG_START
                    bits = self.E
                    sx, sy = x, y
                elif ch == ord("E"):
                    flag = self.TFLAG_END
                    bits = self.W
                    ex, ey = x, y
                elif ch == ord("."):
                    flag = self.TFLAG_EMPTY
                    bits = 0
                else:
                    flag = self.TFLAG_NONE
                    bits = self.SYM_BITS.get(ch, 0)

                self._set(x, y, flag | (bits & 0x0F))

        self.start_x, self.start_y = sx, sy
        self.end_x, self.end_y = ex, ey

        self.cur_x, self.cur_y = sx, sy

        display.clear()
        self._draw_board_full()
        self._draw_cursor()
        self._hud()
        display_score_and_time(self.score, force=True)

    def _tile_rect(self, tx, ty):
        """Return pixel rectangle for loco-motion tile (tx, ty)."""
        x1 = self.rl_off_x + tx * self.RL_TILE
        y1 = self.rl_off_y + ty * self.RL_TILE
        return x1, y1, x1 + self.RL_TILE - 1, y1 + self.RL_TILE - 1

    def _draw_tile(self, tx, ty):
        """Draw a single loco-motion tile including rails and switches."""
        v = self._get(tx, ty)
        flag = v & 0xF0
        bits = v & 0x0F

        x1, y1, x2, y2 = self._tile_rect(tx, ty)
        draw_rectangle(x1, y1, x2, y2, *self.COL_TILE_BG)

        if flag == self.TFLAG_EMPTY and bits == 0:
            sp = display.set_pixel
            sp(x1 + 4, y1 + 4, 0, 0, 10)
            return
        if flag == self.TFLAG_START:
            draw_rectangle(x1 + 1, y1 + 1, x2 - 1, y2 - 1, 0, 40, 0)
        elif flag == self.TFLAG_END:
            draw_rectangle(x1 + 1, y1 + 1, x2 - 1, y2 - 1, 40, 25, 0)

        cx = x1 + (self.RL_TILE // 2)
        cy = y1 + (self.RL_TILE // 2)
        sp = display.set_pixel

        sp(cx, cy, *self.COL_RAIL)

        def rail_to(px, py, col):
            """Draw a rail segment from the tile center to (px, py)."""
            if px == cx:
                sy = 1 if py > cy else -1
                y = cy
                while y != py:
                    sp(cx, y, *col)
                    sp(cx + 1, y, *col)
                    y += sy
                sp(cx, py, *col)
                sp(cx + 1, py, *col)
            else:
                sx = 1 if px > cx else -1
                x = cx
                while x != px:
                    sp(x, cy, *col)
                    sp(x, cy + 1, *col)
                    x += sx
                sp(px, cy, *col)
                sp(px, cy + 1, *col)

        top = y1 + 1
        bot = y2 - 1
        left = x1 + 1
        right = x2 - 1

        if bits & self.N:
            rail_to(cx, top, self.COL_RAIL)
        if bits & self.S:
            rail_to(cx, bot, self.COL_RAIL)
        if bits & self.W:
            rail_to(left, cy, self.COL_RAIL)
        if bits & self.E:
            rail_to(right, cy, self.COL_RAIL)

        if flag == self.TFLAG_START:
            sp(x1 + 1, y1 + 1, *self.COL_START)
            sp(x1 + 2, y1 + 1, *self.COL_START)
            sp(x1 + 1, y1 + 2, *self.COL_START)
        elif flag == self.TFLAG_END:
            sp(x2 - 1, y1 + 1, *self.COL_END)
            sp(x2 - 2, y1 + 1, *self.COL_END)
            sp(x2 - 1, y1 + 2, *self.COL_END)

    def _draw_board_full(self):
        """Draw the entire loco-motion board (all tiles)."""
        for y in range(self.RL_H):
            for x in range(self.RL_W):
                self._draw_tile(x, y)

    def _draw_cursor(self):
        """Draw the selection cursor around the current tile."""
        x1, y1, x2, y2 = self._tile_rect(self.cur_x, self.cur_y)
        draw_rectangle(x1, y1, x2, y1, *self.COL_CURSOR)
        draw_rectangle(x1, y2, x2, y2, *self.COL_CURSOR)
        draw_rectangle(x1, y1, x1, y2, *self.COL_CURSOR)
        draw_rectangle(x2, y1, x2, y2, *self.COL_CURSOR)

    def _repair_cursor_area(self, oldx, oldy):
        """Redraw tiles affected by moving the cursor from (oldx, oldy)."""
        self._draw_tile(oldx, oldy)
        self._draw_tile(self.cur_x, self.cur_y)

    def _hud(self):
        """Draw compact LocoMotion status in the 6-pixel HUD band."""
        try:
            draw_rectangle(0, PLAY_HEIGHT, WIDTH - 1, HEIGHT - 1, 0, 0, 0)
            left = ("R" if self.mode_run else "E") + str(self.level_idx + 1)
            right = "RUN" if self.mode_run else "Z ROT"
            draw_text_small(1, PLAY_HEIGHT, left, 0, 180, 255)
            draw_text_small(WIDTH - len(right) * 6, PLAY_HEIGHT, right, 180, 180, 180)
        except Exception:
            pass

    def _cursor_on_endpoint(self):
        """Return True when the cursor is on the fixed start or end tile."""
        v = self._get(self.cur_x, self.cur_y)
        flag = v & 0xF0
        return flag == self.TFLAG_START or flag == self.TFLAG_END

    def _rotate_tile_at_cursor(self):
        """Rotate the tile under the cursor clockwise and update view."""
        x, y = self.cur_x, self.cur_y
        v = self._get(x, y)
        flag = v & 0xF0
        bits = v & 0x0F

        if flag in (self.TFLAG_START, self.TFLAG_END):
            return
        if flag == self.TFLAG_EMPTY and bits == 0:
            return

        bits = self._rot_cw(bits)
        self._set(x, y, flag | bits)
        self._draw_tile(x, y)
        self._draw_cursor()
        self._hud()

    def _find_start_direction(self):
        """Return an initial direction from the start tile's rails."""
        v = self._get(self.start_x, self.start_y)
        bits = v & 0x0F
        for d in (0, 1, 2, 3):
            if bits & self._dir_to_bit(d):
                return d
        return 1

    def _start_run(self):
        """Begin a run: set running mode and initialize train position."""
        if self.mode_run:
            return
        self.mode_run = True
        self.tr_cx = self.start_x
        self.tr_cy = self.start_y
        self.tr_dir = self._find_start_direction()
        self.tr_prog = 0
        self.tr_speed = 2 + min(2, self.level_idx)

        self.last_tr_px = None
        self.last_tr_py = None

        self._draw_board_full()
        self._hud()

    def _abort_run(self):
        """Abort a running train and restore editing UI state."""
        self.mode_run = False
        self.last_tr_px = None
        self.last_tr_py = None
        self._draw_board_full()
        self._draw_cursor()
        self._hud()

    def _choose_next_dir(self, bits, incoming_dir, prev_move_dir):
        """Choose the next direction for the train given tile bits.

        Prefers continuing in `prev_move_dir` when available, otherwise
        chooses a sensible alternate using right/left preference.
        """
        inc_bit = self._dir_to_bit(incoming_dir)
        if not (bits & inc_bit):
            return None

        outs = []
        for d in (0, 1, 2, 3):
            b = self._dir_to_bit(d)
            if (bits & b) and (d != incoming_dir):
                outs.append(d)

        if not outs:
            return None

        if prev_move_dir in outs:
            return prev_move_dir

        rd = self._right_dir(prev_move_dir)
        if rd in outs:
            return rd
        ld = self._left_dir(prev_move_dir)
        if ld in outs:
            return ld

        return outs[0]

    def _train_pixel_pos(self):
        """Return the pixel position of the train given its tile and progress."""
        x1, y1, x2, y2 = self._tile_rect(self.tr_cx, self.tr_cy)
        cx = x1 + (self.RL_TILE // 2)
        cy = y1 + (self.RL_TILE // 2)

        p = self.tr_prog
        if self.tr_dir == 0:
            return cx, cy - p
        if self.tr_dir == 2:
            return cx, cy + p
        if self.tr_dir == 3:
            return cx - p, cy
        return cx + p, cy

    def _repair_under_train(self, px, py):
        """Restore the tiles that the train may have overwritten around (px,py)."""
        minx = px - 1
        miny = py - 1
        maxx = px + 2
        maxy = py + 2

        tx0 = (minx - self.rl_off_x) // self.RL_TILE
        ty0 = (miny - self.rl_off_y) // self.RL_TILE
        tx1 = (maxx - self.rl_off_x) // self.RL_TILE
        ty1 = (maxy - self.rl_off_y) // self.RL_TILE

        if tx0 < 0:
            tx0 = 0
        if ty0 < 0:
            ty0 = 0
        if tx1 >= self.RL_W:
            tx1 = self.RL_W - 1
        if ty1 >= self.RL_H:
            ty1 = self.RL_H - 1

        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                self._draw_tile(tx, ty)

    def _draw_train(self, px, py):
        """Draw the train sprite and its shadow at pixel (px, py)."""
        sp = display.set_pixel

        sx = px + 1
        sy = py + 2
        if 0 <= sx < WIDTH and 0 <= sy < PLAY_HEIGHT:
            sp(sx, sy, *self.COL_SHADOW)

        for dy in (0, 1):
            yy = py + dy
            if 0 <= yy < PLAY_HEIGHT:
                for dx in (0, 1):
                    xx = px + dx
                    if 0 <= xx < WIDTH:
                        sp(xx, yy, *self.COL_TRAIN)

    def _step_train(self):
        """Advance the train along the rails one logical step.

        Returns True while the train is still running, False when it
        reaches the end or an error occurs.
        """
        global game_over, global_score

        self.tr_prog += self.tr_speed
        if self.tr_prog < self.RL_TILE:
            return True

        self.tr_prog -= self.RL_TILE

        cur = self._get(self.tr_cx, self.tr_cy)
        cur_bits = cur & 0x0F
        out_bit = self._dir_to_bit(self.tr_dir)
        if not (cur_bits & out_bit):
            return False

        nx = self.tr_cx
        ny = self.tr_cy
        if self.tr_dir == 0:
            ny -= 1
        elif self.tr_dir == 2:
            ny += 1
        elif self.tr_dir == 3:
            nx -= 1
        else:
            nx += 1

        if nx < 0 or nx >= self.RL_W or ny < 0 or ny >= self.RL_H:
            return False

        nxt = self._get(nx, ny)
        nxt_flag = nxt & 0xF0
        nxt_bits = nxt & 0x0F

        incoming = self._opp_dir(self.tr_dir)

        if not (nxt_bits & self._dir_to_bit(incoming)):
            return False

        if nx == self.end_x and ny == self.end_y and (nxt_flag == self.TFLAG_END):
            self.score += 100 + (self.level_idx * 25)
            global_score = self.score

            display.clear()
            draw_text(10, 18, "OK!", 0, 255, 0)
            draw_text(6, 32, "LVL " + str(self.level_idx + 1), 255, 255, 0)
            display_score_and_time(global_score, force=True)
            sleep_ms(1100)

            self.load_level(self.level_idx + 1, reset_score=False)
            return None

        next_dir = self._choose_next_dir(nxt_bits, incoming, self.tr_dir)
        if next_dir is None:
            return False

        self.tr_cx = nx
        self.tr_cy = ny
        self.tr_dir = next_dir
        return True

    async def _step_train_async(self):
        """Async version of _step_train() for browser/pygbag runtimes."""
        global global_score
        self.tr_prog += self.tr_speed
        if self.tr_prog < self.RL_TILE:
            return True
        self.tr_prog -= self.RL_TILE
        cur = self._get(self.tr_cx, self.tr_cy)
        cur_bits = cur & 0x0F
        out_bit = self._dir_to_bit(self.tr_dir)
        if not (cur_bits & out_bit):
            return False
        nx = self.tr_cx
        ny = self.tr_cy
        if self.tr_dir == 0:
            ny -= 1
        elif self.tr_dir == 2:
            ny += 1
        elif self.tr_dir == 3:
            nx -= 1
        else:
            nx += 1
        if nx < 0 or nx >= self.RL_W or ny < 0 or ny >= self.RL_H:
            return False
        nxt = self._get(nx, ny)
        nxt_flag = nxt & 0xF0
        nxt_bits = nxt & 0x0F
        incoming = self._opp_dir(self.tr_dir)
        if not (nxt_bits & self._dir_to_bit(incoming)):
            return False
        if nx == self.end_x and ny == self.end_y and (nxt_flag == self.TFLAG_END):
            self.score += 100 + (self.level_idx * 25)
            global_score = self.score
            display.clear()
            draw_text(10, 18, "OK!", 0, 255, 0)
            draw_text(6, 32, "LVL " + str(self.level_idx + 1), 255, 255, 0)
            display_score_and_time(global_score, force=True)
            await sleep_ms_async(1100)
            self.load_level(self.level_idx + 1, reset_score=False)
            return None
        next_dir = self._choose_next_dir(nxt_bits, incoming, self.tr_dir)
        if next_dir is None:
            return False
        self.tr_cx = nx
        self.tr_cy = ny
        self.tr_dir = next_dir
        return True

    async def _fail_derail_async(self):
        """Async derail handler."""
        set_game_over_score(self.score, won=False)
        display.clear()
        draw_text(6, 18, "DERAIL", 255, 0, 0)
        display_score_and_time(global_score, force=True)
        await sleep_ms_async(900)
        self._abort_run()

    def _fail_derail(self):
        """Display a derail message and return to the shared game-over flow."""
        set_game_over_score(self.score, won=False)
        display.clear()
        draw_text(6, 18, "DERAIL", 255, 0, 0)
        display_score_and_time(global_score, force=True)
        sleep_ms(900)
        self._abort_run()

    def main_loop(self, joystick):
        """Main loop for LocoMotion: handle editing and running modes."""
        global game_over, global_score
        game_over = False
        global_score = 0

        self.load_level(self.level_idx, reset_score=False)
        self._last_input_ms = ticks_ms()
        last_frame = ticks_ms()

        while True:
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return
            if game_over:
                return

            now = ticks_ms()

            if z_button:
                if self._z_down_ms is None:
                    self._z_down_ms = now
                    self._z_armed = True
                else:
                    if (
                        self._z_armed
                        and ticks_diff(now, self._z_down_ms) >= self.Z_LONG_MS
                    ):
                        self._z_armed = False
                        if not self.mode_run:
                            self._start_run()
                        else:
                            self._abort_run()
            else:
                if self._z_down_ms is not None:
                    held = ticks_diff(now, self._z_down_ms)
                    if held < self.Z_LONG_MS and self._z_armed:
                        if self.mode_run:
                            self._abort_run()
                        elif self._cursor_on_endpoint():
                            self._start_run()
                        else:
                            self._rotate_tile_at_cursor()
                    self._z_down_ms = None
                    self._z_armed = False

            if self.mode_run:
                if ticks_diff(now, last_frame) < self.FRAME_MS_RUN:
                    sleep_ms(2)
                    continue
                last_frame = now

                if self.last_tr_px is not None:
                    self._repair_under_train(self.last_tr_px, self.last_tr_py)

                st = self._step_train()
                if st is None:
                    last_frame = ticks_ms()
                    continue
                if st is False:
                    self._fail_derail()
                    last_frame = ticks_ms()
                    continue

                px, py = self._train_pixel_pos()
                self._draw_train(px, py)
                self.last_tr_px, self.last_tr_py = px, py

                self._hud()
                display_score_and_time(self.score)
                global_score = self.score

                if (now & 0x3FF) == 0:
                    gc.collect()

                continue

            if ticks_diff(now, self._last_input_ms) < self.EDIT_INPUT_MS:
                sleep_ms(5)
                continue

            d = joystick.read_direction(
                [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
            )
            if not d:
                sleep_ms(5)
                continue

            ox, oy = self.cur_x, self.cur_y
            if d == JOYSTICK_LEFT and self.cur_x > 0:
                self.cur_x -= 1
            elif d == JOYSTICK_RIGHT and self.cur_x < self.RL_W - 1:
                self.cur_x += 1
            elif d == JOYSTICK_UP and self.cur_y > 0:
                self.cur_y -= 1
            elif d == JOYSTICK_DOWN and self.cur_y < self.RL_H - 1:
                self.cur_y += 1

            if (ox, oy) != (self.cur_x, self.cur_y):
                self._repair_cursor_area(ox, oy)
                self._draw_cursor()
                self._hud()

            self._last_input_ms = now
            maybe_collect(120)

    async def main_loop_async(self, joystick):
        """Async/cooperative version of the LocoMotion loop for browsers.

        Uses `await asyncio.sleep()` instead of blocking `sleep_ms()` so the
        event loop remains responsive in WASM/pygbag environments.
        """
        if asyncio is None:
            return self.main_loop(joystick)

        global game_over, global_score
        game_over = False
        global_score = 0

        self.load_level(self.level_idx, reset_score=False)
        self._last_input_ms = ticks_ms()
        last_frame = ticks_ms()

        while True:
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return
            if game_over:
                return

            now = ticks_ms()

            if z_button:
                if self._z_down_ms is None:
                    self._z_down_ms = now
                    self._z_armed = True
                else:
                    if (
                        self._z_armed
                        and ticks_diff(now, self._z_down_ms) >= self.Z_LONG_MS
                    ):
                        self._z_armed = False
                        if not self.mode_run:
                            self._start_run()
                        else:
                            self._abort_run()
            else:
                if self._z_down_ms is not None:
                    held = ticks_diff(now, self._z_down_ms)
                    if held < self.Z_LONG_MS and self._z_armed:
                        if self.mode_run:
                            self._abort_run()
                        elif self._cursor_on_endpoint():
                            self._start_run()
                        else:
                            self._rotate_tile_at_cursor()
                    self._z_down_ms = None
                    self._z_armed = False

            if self.mode_run:
                if ticks_diff(now, last_frame) < self.FRAME_MS_RUN:
                    await asyncio.sleep(0.002)
                    continue
                last_frame = now

                if self.last_tr_px is not None:
                    self._repair_under_train(self.last_tr_px, self.last_tr_py)

                st = await self._step_train_async()
                if st is None:
                    last_frame = ticks_ms()
                    continue
                if st is False:
                    await self._fail_derail_async()
                    last_frame = ticks_ms()
                    continue

                px, py = self._train_pixel_pos()
                self._draw_train(px, py)
                self.last_tr_px, self.last_tr_py = px, py

                self._hud()
                display_score_and_time(self.score)
                global_score = self.score

                if (now & 0x3FF) == 0:
                    try:
                        gc.collect()
                    except Exception:
                        pass

                continue

            if ticks_diff(now, self._last_input_ms) < self.EDIT_INPUT_MS:
                await asyncio.sleep(0.005)
                continue

            d = joystick.read_direction(
                [
                    JOYSTICK_UP,
                    JOYSTICK_DOWN,
                    JOYSTICK_LEFT,
                    JOYSTICK_RIGHT,
                ]
            )
            if not d:
                await asyncio.sleep(0.005)
                continue

            ox, oy = self.cur_x, self.cur_y
            if d == JOYSTICK_LEFT and self.cur_x > 0:
                self.cur_x -= 1
            elif d == JOYSTICK_RIGHT and self.cur_x < self.RL_W - 1:
                self.cur_x += 1
            elif d == JOYSTICK_UP and self.cur_y > 0:
                self.cur_y -= 1
            elif d == JOYSTICK_DOWN and self.cur_y < self.RL_H - 1:
                self.cur_y += 1

            if (ox, oy) != (self.cur_x, self.cur_y):
                self._repair_cursor_area(ox, oy)
                self._draw_cursor()
                self._hud()

            self._last_input_ms = now
            try:
                maybe_collect(120)
            except Exception:
                pass


class OthelloGame:
    """
    REVERSI / OTHELLO
    Controls:
      - Left / Right / Up / Down: move cursor
      - Z: place disc
      - C: return to menu
    """

    BOARD_SIZE = 8
    CELL_SIZE = 6
    BOARD_W = BOARD_SIZE * CELL_SIZE
    BOARD_H = BOARD_SIZE * CELL_SIZE
    EMPTY = 0
    P1 = 1
    P2 = 2

    def __init__(self, ctx=None):
        """Initialize Othello game and bind optional runtime helpers."""
        if ctx is None:
            ctx = {}

        def _g(name):
            """Return a runtime symbol from `ctx` or fallback to globals()."""
            if isinstance(ctx, dict):
                return ctx.get(name, globals().get(name))
            return getattr(ctx, name, globals().get(name))

        g = globals()
        try:
            g["display"] = _g("display")
            g["draw_text"] = _g("draw_text")
            g["draw_rectangle"] = _g("draw_rectangle")
            g["display_score_and_time"] = _g("display_score_and_time")
            g["ticks_ms"] = _g("ticks_ms")
            g["ticks_diff"] = _g("ticks_diff")
            g["sleep_ms"] = _g("sleep_ms")
        except Exception:
            pass

        self.board = [[self.EMPTY] * self.BOARD_SIZE for _ in range(self.BOARD_SIZE)]
        self.cur_x = 3
        self.cur_y = 3
        self.current_player = self.P1
        self.score = 0
        self.game_finished = False
        self._needs_render = True
        try:
            self.board_off_x = (WIDTH - self.BOARD_W) // 2
            self.board_off_y = (PLAY_HEIGHT - self.BOARD_H) // 2
        except Exception:
            self.board_off_x = 0
            self.board_off_y = 0

    def reset(self):
        """Reset the Othello board to the starting position."""
        for y in range(self.BOARD_SIZE):
            row = self.board[y]
            for x in range(self.BOARD_SIZE):
                row[x] = self.EMPTY

        mid = self.BOARD_SIZE // 2
        self.board[mid - 1][mid - 1] = self.P2
        self.board[mid][mid] = self.P2
        self.board[mid - 1][mid] = self.P1
        self.board[mid][mid - 1] = self.P1

        self.cur_x = mid
        self.cur_y = mid
        self.current_player = self.P1
        self.game_finished = False
        self.score = 0
        self._needs_render = True

        display.clear()
        self.render(full=True)
        display_score_and_time(0, force=True)

    def inside(self, x, y):
        """Return True when (x, y) lies inside the board bounds."""
        return 0 <= x < self.BOARD_SIZE and 0 <= y < self.BOARD_SIZE

    def directions(self):
        """Return the eight direction vectors used for flipping logic."""
        return (
            (-1, -1),
            (0, -1),
            (1, -1),
            (-1, 0),
            (1, 0),
            (-1, 1),
            (0, 1),
            (1, 1),
        )

    def _captures_in_dir(self, x, y, dx, dy, player):
        """Return a tuple of positions captured in direction (dx,dy).

        Scans from (x+dx,y+dy) outward and returns captured enemy
        positions when terminated by a friendly piece.
        """
        enemy = self.P1 if player == self.P2 else self.P2
        cx = x + dx
        cy = y + dy
        captured = []

        if not self.inside(cx, cy):
            return ()

        if self.board[cy][cx] != enemy:
            return ()

        while True:
            captured.append((cx, cy))
            cx += dx
            cy += dy
            if not self.inside(cx, cy):
                return ()
            v = self.board[cy][cx]
            if v == self.EMPTY:
                return ()
            if v == player:
                return tuple(captured)

    def valid_moves_for(self, player):
        """Return a list of valid moves (x,y) for `player`."""
        moves = []
        for y in range(self.BOARD_SIZE):
            for x in range(self.BOARD_SIZE):
                if self.board[y][x] != self.EMPTY:
                    continue
                total_caps = 0
                for dx, dy in self.directions():
                    caps = self._captures_in_dir(x, y, dx, dy, player)
                    total_caps += len(caps)
                if total_caps > 0:
                    moves.append((x, y, total_caps))
        return moves

    def is_valid_move(self, x, y, player):
        """Return True when placing at (x,y) is a legal move for `player`."""
        if not self.inside(x, y):
            return False
        if self.board[y][x] != self.EMPTY:
            return False
        for dx, dy in self.directions():
            caps = self._captures_in_dir(x, y, dx, dy, player)
            if caps:
                return True
        return False

    def apply_move(self, x, y, player):
        """Apply a move for `player` at (x,y) and flip captured discs."""
        self.board[y][x] = player
        total_flipped = 0
        for dx, dy in self.directions():
            caps = self._captures_in_dir(x, y, dx, dy, player)
            if caps:
                for cx, cy in caps:
                    self.board[cy][cx] = player
                total_flipped += len(caps)
        return total_flipped

    def count_discs(self):
        """Count discs for both players and return (p1, p2)."""
        p1 = 0
        p2 = 0
        for y in range(self.BOARD_SIZE):
            row = self.board[y]
            for x in range(self.BOARD_SIZE):
                if row[x] == self.P1:
                    p1 += 1
                elif row[x] == self.P2:
                    p2 += 1
        return p1, p2

    def cpu_move(self):
        """Simple CPU move: pick the move with the highest immediate gain."""
        moves = self.valid_moves_for(self.P2)
        if not moves:
            return False

        best = None
        best_score = -1
        for x, y, gain in moves:
            if gain > best_score:
                best_score = gain
                best = (x, y)

        if best is None:
            return False

        bx, by = best
        self.apply_move(bx, by, self.P2)
        return True

    def _draw_cell(self, x, y):
        """Draw a single board cell (empty or player disc)."""
        v = self.board[y][x]
        x1 = self.board_off_x + x * self.CELL_SIZE
        y1 = self.board_off_y + y * self.CELL_SIZE
        x2 = x1 + self.CELL_SIZE - 1
        y2 = y1 + self.CELL_SIZE - 1

        draw_rectangle(x1, y1, x2, y2, 0, 90, 0)

        if v == self.P1:
            cx = x1 + self.CELL_SIZE // 2
            cy = y1 + self.CELL_SIZE // 2
            display.set_pixel(cx, cy, 0, 0, 0)
            display.set_pixel(cx - 1, cy, 0, 0, 0)
            display.set_pixel(cx, cy - 1, 0, 0, 0)
            display.set_pixel(cx - 1, cy - 1, 0, 0, 0)
        elif v == self.P2:
            cx = x1 + self.CELL_SIZE // 2
            cy = y1 + self.CELL_SIZE // 2
            display.set_pixel(cx, cy, 255, 255, 255)
            display.set_pixel(cx - 1, cy, 255, 255, 255)
            display.set_pixel(cx, cy - 1, 255, 255, 255)
            display.set_pixel(cx - 1, cy - 1, 255, 255, 255)

    def render(self, full=False):
        """Render the Othello board and HUD; `full` forces a full redraw."""
        if full:
            for y in range(self.BOARD_SIZE):
                for x in range(self.BOARD_SIZE):
                    self._draw_cell(x, y)
        else:
            for y in range(self.BOARD_SIZE):
                for x in range(self.BOARD_SIZE):
                    self._draw_cell(x, y)

        for x in range(self.BOARD_SIZE + 1):
            px = self.board_off_x + x * self.CELL_SIZE
            draw_rectangle(
                px, self.board_off_y, px, self.board_off_y + self.BOARD_H - 1, 0, 60, 0
            )
        for y in range(self.BOARD_SIZE + 1):
            py = self.board_off_y + y * self.CELL_SIZE
            draw_rectangle(
                self.board_off_x, py, self.board_off_x + self.BOARD_W - 1, py, 0, 60, 0
            )

        cx1 = self.board_off_x + self.cur_x * self.CELL_SIZE
        cy1 = self.board_off_y + self.cur_y * self.CELL_SIZE
        cx2 = cx1 + self.CELL_SIZE - 1
        cy2 = cy1 + self.CELL_SIZE - 1
        draw_rectangle(cx1, cy1, cx2, cy1, 255, 255, 0)
        draw_rectangle(cx1, cy2, cx2, cy2, 255, 255, 0)
        draw_rectangle(cx1, cy1, cx1, cy2, 255, 255, 0)
        draw_rectangle(cx2, cy1, cx2, cy2, 255, 255, 0)

        p1, p2 = self.count_discs()
        self.score = p1 - p2
        display_score_and_time(self.score)
        self._needs_render = False

    def check_game_end(self):
        """Return True when neither player has a valid move (game over)."""
        moves_p1 = self.valid_moves_for(self.P1)
        moves_p2 = self.valid_moves_for(self.P2)
        if moves_p1 or moves_p2:
            return False

        self.game_finished = True
        p1, p2 = self.count_discs()
        self.score = p1 - p2
        return True

    def main_loop(self, joystick):
        """Main loop for Othello: handle input, apply moves, and update."""
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()

        frame_ms = 80
        last_frame = ticks_ms()

        while True:
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return
            if game_over:
                return

            now = ticks_ms()
            if ticks_diff(now, last_frame) < frame_ms:
                sleep_ms(5)
                continue
            last_frame = now

            if self.game_finished:
                display.clear()
                p1, p2 = self.count_discs()
                txt = "WIN" if p1 > p2 else ("LOSE" if p1 < p2 else "DRAW")
                draw_text(8, 18, txt, 255, 255, 255)
                display_score_and_time(self.score, force=True)
                global_score = self.score
                sleep_ms(1500)
                game_over = True
                return

            if self.current_player == self.P1:
                d = joystick.read_direction(
                    [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
                )

                if d == JOYSTICK_LEFT and self.cur_x > 0:
                    self.cur_x -= 1
                    self._needs_render = True
                elif d == JOYSTICK_RIGHT and self.cur_x < self.BOARD_SIZE - 1:
                    self.cur_x += 1
                    self._needs_render = True
                elif d == JOYSTICK_UP and self.cur_y > 0:
                    self.cur_y -= 1
                    self._needs_render = True
                elif d == JOYSTICK_DOWN and self.cur_y < self.BOARD_SIZE - 1:
                    self.cur_y += 1
                    self._needs_render = True

                if z_button and self.is_valid_move(self.cur_x, self.cur_y, self.P1):
                    self.apply_move(self.cur_x, self.cur_y, self.P1)
                    self.current_player = self.P2
                    self._needs_render = True

            else:
                if self.cpu_move():
                    self._needs_render = True
                self.current_player = self.P1
                sleep_ms(120)

            if not self.valid_moves_for(self.current_player):
                if self.check_game_end():
                    continue
                self.current_player = (
                    self.P1 if self.current_player == self.P2 else self.P2
                )

            if self._needs_render:
                self.render(full=True)
            global_score = self.score

    async def main_loop_async(self, joystick):
        """Async/cooperative Othello loop for browsers (pygbag).

        Mirrors `main_loop` but yields with `await asyncio.sleep()` to keep
        the event loop responsive in WASM environments.
        """
        if asyncio is None:
            return self.main_loop(joystick)

        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()

        frame_ms = 80
        last_frame = ticks_ms()

        while True:
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return
            if game_over:
                return

            now = ticks_ms()
            if ticks_diff(now, last_frame) < frame_ms:
                await asyncio.sleep(0.005)
                continue
            last_frame = now

            if self.game_finished:
                display.clear()
                p1, p2 = self.count_discs()
                txt = "WIN" if p1 > p2 else ("LOSE" if p1 < p2 else "DRAW")
                draw_text(8, 18, txt, 255, 255, 255)
                display_score_and_time(self.score, force=True)
                global_score = self.score
                await asyncio.sleep(1.5)
                game_over = True
                return

            if self.current_player == self.P1:
                d = joystick.read_direction(
                    [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
                )

                if d == JOYSTICK_LEFT and self.cur_x > 0:
                    self.cur_x -= 1
                    self._needs_render = True
                elif d == JOYSTICK_RIGHT and self.cur_x < self.BOARD_SIZE - 1:
                    self.cur_x += 1
                    self._needs_render = True
                elif d == JOYSTICK_UP and self.cur_y > 0:
                    self.cur_y -= 1
                    self._needs_render = True
                elif d == JOYSTICK_DOWN and self.cur_y < self.BOARD_SIZE - 1:
                    self.cur_y += 1
                    self._needs_render = True

                if z_button and self.is_valid_move(self.cur_x, self.cur_y, self.P1):
                    self.apply_move(self.cur_x, self.cur_y, self.P1)
                    self.current_player = self.P2
                    self._needs_render = True

            else:
                if self.cpu_move():
                    self._needs_render = True
                self.current_player = self.P1
                await asyncio.sleep(0.12)

            if not self.valid_moves_for(self.current_player):
                if self.check_game_end():
                    continue
                self.current_player = (
                    self.P1 if self.current_player == self.P2 else self.P2
                )

            if self._needs_render:
                self.render(full=True)
            global_score = self.score


class SokobanGame:
    """
    SOKOBAN
    Controls:
      - Left / Right / Up / Down: move player / push crate
      - Z: undo last move
      - C: return to menu
    """

    # --- Sokoban constants & levels (kept as class attributes) ---
    SOK_TILE = 4
    SOK_W = 16
    SOK_H = 14

    # Map encoding (bytes): '#' wall, '.' floor, 'G' goal, 'B' box,
    # '*' box on goal, 'P' player, '+' player on goal
    SOK_LEVELS = [
        (
            b"################",
            b"#0.............#",
            b"#....#####.....#",
            b"#....#..P#.....#",
            b"#..###.B.#.....#",
            b"#..#..BBB#.....#",
            b"#..#...GG#.....#",
            b"#..###.GG#.....#",
            b"#....#...#.....#",
            b"#....#####.....#",
            b"#.............0#",
            b"#..0...........#",
            b"#..0...........#",
            b"################",
        ),
        (
            b"################",
            b"#..............#",
            b"#..#####.......#",
            b"#..#...#.......#",
            b"#..#.B.#..GG...#",
            b"#..#.BB#..GG...#",
            b"#..#..P........#",
            b"#..#####.......#",
            b"#..............#",
            b"#..............#",
            b"#..............#",
            b"#..............#",
            b"#..............#",
            b"################",
        ),
        (
            b"################",
            b"#..............#",
            b"#..######..GG..#",
            b"#..#....#..GG..#",
            b"#..#.BB.#......#",
            b"#..#..B.#..###.#",
            b"#..#..P....#...#",
            b"#..######..#...#",
            b"#..........#...#",
            b"#..#############",
            b"#..............#",
            b"#..............#",
            b"#..............#",
            b"################",
        ),
        (
            b"################",
            b"#..............#",
            b"#..............#",
            b"#....#####.....#",
            b"#..###...#..GG.#",
            b"#..#...B.#.....#",
            b"#..#..B..#.....#",
            b"#..#..P..#####.#",
            b"#..#......#....#",
            b"#..####.####...#",
            b"#..............#",
            b"#..............#",
            b"#..............#",
            b"################",
        ),
        (
            b"################",
            b"#..............#",
            b"#..#####.......#",
            b"#..#...#.......#",
            b"#..#PBG#.......#",
            b"#..#...#.......#",
            b"#..#####.......#",
            b"#..............#",
            b"#..............#",
            b"#..............#",
            b"#..............#",
            b"#..............#",
            b"#..............#",
            b"################",
        ),
        (
            b"################",
            b"#..............#",
            b"#..########....#",
            b"#..#......#....#",
            b"#..#P.B.G.#....#",
            b"#..#..B.G.#....#",
            b"#..#......#....#",
            b"#..########....#",
            b"#..............#",
            b"#..............#",
            b"#..............#",
            b"#..............#",
            b"#..............#",
            b"################",
        ),
    ]

    # Colors (tweak to taste)
    COL_BG = (0, 0, 0)
    COL_WALL = (0, 0, 140)
    COL_FLOOR = (0, 0, 0)
    COL_GOAL = (0, 120, 0)
    COL_BOX = (220, 140, 0)
    COL_BOXG = (255, 220, 0)
    COL_PLYR = (255, 255, 255)
    COL_PLYRG = (180, 255, 180)
    COL_GRID = (0, 35, 0)

    def __init__(self, ctx=None):
        """Initialize SokobanGame and bind optional runtime helpers.

        `ctx` may provide platform-specific functions; missing symbols
        fall back to module globals. Initializes level state and offsets.
        """
        if ctx is None:
            ctx = {}

        def _g(name):
            """Return a runtime symbol from `ctx` or fallback to globals()."""
            if isinstance(ctx, dict):
                return ctx.get(name, globals().get(name))
            return getattr(ctx, name, globals().get(name))

        g = globals()
        try:
            g["display"] = _g("display")
            g["draw_text"] = _g("draw_text")
            g["draw_rectangle"] = _g("draw_rectangle")
            g["display_score_and_time"] = _g("display_score_and_time")
            g["ticks_ms"] = _g("ticks_ms")
            g["ticks_diff"] = _g("ticks_diff")
            g["sleep_ms"] = _g("sleep_ms")
        except Exception:
            pass

        self.level_idx = 0
        self.score = 0
        self.moves = 0
        self.undo = []
        self._last_input_ms = 0
        self.input_ms = 120
        try:
            self.sok_off_x = 0
            self.sok_off_y = (PLAY_HEIGHT - (self.SOK_H * self.SOK_TILE)) // 2
        except Exception:
            self.sok_off_x = 0
            self.sok_off_y = 0
        self.reset_level(reset_all=True)

    def _idx(self, x, y):
        """Return linear index for the Sokoban level grid at (x, y)."""
        return y * self.SOK_W + x

    def _inside(self, x, y):
        """Return True when (x, y) lies within the Sokoban map bounds."""
        return 0 <= x < self.SOK_W and 0 <= y < self.SOK_H

    def reset_level(self, reset_all=False):
        """Load and initialize the current Sokoban level.

        When `reset_all` is True, resets `level_idx` to zero as well.
        Initializes walls, goals, boxes and player position arrays.
        """
        if reset_all:
            self.level_idx = 0
            self.score = 0
        self.moves = 0
        self.undo = []

        raw = self.SOK_LEVELS[self.level_idx % len(self.SOK_LEVELS)]
        self.walls = bytearray(self.SOK_W * self.SOK_H)
        self.goals = bytearray(self.SOK_W * self.SOK_H)
        self.boxes = bytearray(self.SOK_W * self.SOK_H)

        px = py = 1

        for y in range(self.SOK_H):
            row = raw[y]
            for x in range(self.SOK_W):
                ch = row[x]
                i = self._idx(x, y)
                if ch == 35:
                    self.walls[i] = 1
                elif ch == ord("G"):
                    self.goals[i] = 1
                elif ch == ord("B"):
                    self.boxes[i] = 1
                elif ch == ord("*"):
                    self.goals[i] = 1
                    self.boxes[i] = 1
                elif ch == ord("P"):
                    px, py = x, y
                elif ch == ord("+"):
                    px, py = x, y
                    self.goals[i] = 1

        self.px, self.py = px, py
        display.clear()
        self.render(full=True)
        display_score_and_time(self.moves, force=True)

    def _is_wall(self, x, y):
        """Return True when the tile at (x,y) is a wall."""
        return self.walls[self._idx(x, y)] != 0

    def _has_box(self, x, y):
        """Return True when a box occupies tile (x,y)."""
        return self.boxes[self._idx(x, y)] != 0

    def _set_box(self, x, y, v):
        """Set or clear a box at tile (x,y) depending on truthiness of `v`."""
        self.boxes[self._idx(x, y)] = 1 if v else 0

    def _is_goal(self, x, y):
        """Return True when the tile at (x,y) is a goal target."""
        return self.goals[self._idx(x, y)] != 0

    def _try_move(self, dx, dy):
        """Attempt to move the player by (dx,dy); push boxes if possible.

        Returns True on successful move (and updates state), False
        when movement is blocked by walls or immovable boxes.
        """
        x0, y0 = self.px, self.py
        x1, y1 = x0 + dx, y0 + dy
        if not self._inside(x1, y1) or self._is_wall(x1, y1):
            return False

        if self._has_box(x1, y1):
            x2, y2 = x1 + dx, y1 + dy
            if (
                not self._inside(x2, y2)
                or self._is_wall(x2, y2)
                or self._has_box(x2, y2)
            ):
                return False
            self._set_box(x1, y1, 0)
            self._set_box(x2, y2, 1)
            box_moved = 1
            rec = (x0, y0, x1, y1, box_moved, x1, y1, x2, y2)
        else:
            box_moved = 0
            rec = (x0, y0, x1, y1, box_moved, 0, 0, 0, 0)

        self.px, self.py = x1, y1
        self.moves += 1

        if len(self.undo) >= 120:
            self.undo.pop(0)
        self.undo.append(rec)
        return True

    def _undo(self):
        """Undo the last player move, restoring box positions if needed."""
        if not self.undo:
            return False
        rec = self.undo.pop()
        x0, y0, x1, y1, box_moved, bx0, by0, bx1, by1 = rec

        self.px, self.py = x0, y0

        if box_moved:
            self._set_box(bx1, by1, 0)
            self._set_box(bx0, by0, 1)

        if self.moves > 0:
            self.moves -= 1
        return True

    def _is_solved(self):
        """Return True when all boxes are on goal tiles (level solved)."""
        b = self.boxes
        g = self.goals
        for i in range(self.SOK_W * self.SOK_H):
            if b[i] and not g[i]:
                return False
        return True

    def _draw_tile(self, x, y):
        """Draw a single Sokoban tile including walls, goals and boxes."""
        i = self._idx(x, y)
        x1 = self.sok_off_x + x * self.SOK_TILE
        y1 = self.sok_off_y + y * self.SOK_TILE
        x2 = x1 + self.SOK_TILE - 1
        y2 = y1 + self.SOK_TILE - 1

        if self.walls[i]:
            draw_rectangle(x1, y1, x2, y2, *self.COL_WALL)
            return

        draw_rectangle(x1, y1, x2, y2, *self.COL_FLOOR)

        if self.goals[i]:
            draw_rectangle(x1 + 1, y1 + 1, x2 - 1, y2 - 1, *self.COL_GOAL)

        if self.boxes[i]:
            col = self.COL_BOXG if self.goals[i] else self.COL_BOX
            draw_rectangle(x1 + 1, y1 + 1, x2 - 1, y2 - 1, *col)

    def _draw_player(self):
        """Draw the player at its current tile position with goal highlight."""
        x = self.sok_off_x + self.px * self.SOK_TILE
        y = self.sok_off_y + self.py * self.SOK_TILE
        col = self.COL_PLYRG if self._is_goal(self.px, self.py) else self.COL_PLYR
        draw_rectangle(x + 1, y + 1, x + 2, y + 2, *col)

    def render(self, full=False):
        """Render Sokoban level and HUD; `full` forces full redraw."""
        for y in range(self.SOK_H):
            for x in range(self.SOK_W):
                self._draw_tile(x, y)
        self._draw_player()
        display_score_and_time(self.moves)

    def main_loop(self, joystick):
        """Main loop for Sokoban: handle input, moves, undo, and rendering."""
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset_level(reset_all=True)
        self._last_input_ms = ticks_ms()

        while True:
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return
            if game_over:
                return

            now = ticks_ms()

            if z_button and ticks_diff(now, self._last_input_ms) >= self.input_ms:
                if self._undo():
                    self.render(full=True)
                self._last_input_ms = now
                maybe_collect(120)
                continue

            if ticks_diff(now, self._last_input_ms) < self.input_ms:
                sleep_ms(5)
                continue

            d = joystick.read_direction(
                [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
            )
            if not d:
                sleep_ms(5)
                continue

            dx = dy = 0
            if d == JOYSTICK_LEFT:
                dx = -1
            elif d == JOYSTICK_RIGHT:
                dx = 1
            elif d == JOYSTICK_UP:
                dy = -1
            elif d == JOYSTICK_DOWN:
                dy = 1

            moved = False
            if dx or dy:
                moved = self._try_move(dx, dy)

            if moved:
                self.render(full=True)
                self._last_input_ms = now

                if self._is_solved():
                    finish_score = max(
                        1,
                        1000
                        - self.moves
                        + ((self.level_idx % len(self.SOK_LEVELS)) + 1) * 100,
                    )
                    self.score += finish_score
                    global_score = self.score
                    display.clear()
                    draw_text(4, 16, "SOLVED", 0, 255, 0)
                    draw_text(
                        4,
                        30,
                        "LVL " + str((self.level_idx % len(self.SOK_LEVELS)) + 1),
                        255,
                        255,
                        0,
                    )
                    display_score_and_time(global_score, force=True)
                    sleep_ms(1300)
                    if self.level_idx + 1 >= len(self.SOK_LEVELS):
                        set_game_over_score(self.score, won=True)
                        return
                    self.level_idx += 1
                    self.reset_level(reset_all=False)
                    self._last_input_ms = ticks_ms()
                    continue

            else:
                self._last_input_ms = now - (self.input_ms // 2)

            maybe_collect(140)

    async def main_loop_async(self, joystick):
        """Async/cooperative Sokoban loop for browsers (pygbag).

        Mirrors `main_loop` but yields with `await asyncio.sleep()` instead of
        blocking `sleep_ms()` so the event loop remains responsive.
        """
        if asyncio is None:
            return self.main_loop(joystick)

        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset_level(reset_all=True)
        self._last_input_ms = ticks_ms()

        while True:
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return
            if game_over:
                return

            now = ticks_ms()

            if z_button and ticks_diff(now, self._last_input_ms) >= self.input_ms:
                if self._undo():
                    self.render(full=True)
                self._last_input_ms = now
                try:
                    maybe_collect(120)
                except Exception:
                    pass
                continue

            if ticks_diff(now, self._last_input_ms) < self.input_ms:
                await asyncio.sleep(0.005)
                continue

            d = joystick.read_direction(
                [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
            )
            if not d:
                await asyncio.sleep(0.005)
                continue

            dx = dy = 0
            if d == JOYSTICK_LEFT:
                dx = -1
            elif d == JOYSTICK_RIGHT:
                dx = 1
            elif d == JOYSTICK_UP:
                dy = -1
            elif d == JOYSTICK_DOWN:
                dy = 1

            moved = False
            if dx or dy:
                moved = self._try_move(dx, dy)

            if moved:
                self.render(full=True)
                self._last_input_ms = now

                if self._is_solved():
                    finish_score = max(
                        1,
                        1000
                        - self.moves
                        + ((self.level_idx % len(self.SOK_LEVELS)) + 1) * 100,
                    )
                    self.score += finish_score
                    global_score = self.score
                    display.clear()
                    draw_text(4, 16, "SOLVED", 0, 255, 0)
                    draw_text(
                        4,
                        30,
                        "LVL " + str((self.level_idx % len(self.SOK_LEVELS)) + 1),
                        255,
                        255,
                        0,
                    )
                    display_score_and_time(global_score, force=True)
                    await asyncio.sleep(1.3)
                    if self.level_idx + 1 >= len(self.SOK_LEVELS):
                        set_game_over_score(self.score, won=True)
                        return
                    self.level_idx += 1
                    self.reset_level(reset_all=False)
                    self._last_input_ms = ticks_ms()
                    continue

            else:
                self._last_input_ms = now - (self.input_ms // 2)

            try:
                maybe_collect(140)
            except Exception:
                pass


class BejeweledGame:
    """Simple Bejeweled-like match-3 puzzle.

    Controls:
      - Stick: move cursor (cell-by-cell)
      - Z: select / swap (select one tile, then another adjacent to swap)
      - C: return to menu
    """

    w = 8
    h = 8
    COLORS = [
        (220, 60, 60),
        (60, 200, 80),
        (60, 140, 220),
        (240, 200, 60),
        (200, 80, 200),
        (60, 200, 180),
    ]

    def __init__(self):
        self.reset()

    def reset(self):
        self.cols = self.w
        self.rows = self.h
        self.tile_w = max(2, WIDTH // self.cols)
        self.tile_h = max(2, PLAY_HEIGHT // self.rows)
        self.grid = [
            [random.randint(0, len(self.COLORS) - 1) for _ in range(self.cols)]
            for _ in range(self.rows)
        ]
        # remove initial matches
        while True:
            m = self._find_matches()
            if not m:
                break
            for x, y in m:
                self.grid[y][x] = random.randint(0, len(self.COLORS) - 1)

        self.cursor_x = 0
        self.cursor_y = 0
        self.sel = None
        self.score = 0
        # input smoothing for cursor (ms between moves)
        self._last_move = ticks_ms()
        self._move_delay = 160
        self._prev_cursor = None
        self._prev_sel = None
        self._last_drawn_score = -1
        self._full_redraw = True
        self._needs_redraw = True

    def _find_matches(self):
        # Identify connected components (4-connected) of the same color.
        matches = set()
        visited = set()
        for y in range(self.rows):
            for x in range(self.cols):
                if (x, y) in visited:
                    continue
                color = self.grid[y][x]
                if color is None:
                    visited.add((x, y))
                    continue

                stack = [(x, y)]
                comp = set()
                while stack:
                    cx, cy = stack.pop()
                    if (cx, cy) in comp:
                        continue
                    if not (0 <= cx < self.cols and 0 <= cy < self.rows):
                        continue
                    if self.grid[cy][cx] != color:
                        continue
                    comp.add((cx, cy))
                    visited.add((cx, cy))
                    stack.append((cx + 1, cy))
                    stack.append((cx - 1, cy))
                    stack.append((cx, cy + 1))
                    stack.append((cx, cy - 1))

                if len(comp) >= 3:
                    matches |= comp

        return matches

    def _collapse_and_refill(self):
        self._collapse_and_refill_animated(delay_ms=0)

    def _draw_tile_at_px(self, x, y_px, value):
        gx = x * self.tile_w
        if y_px > PLAY_HEIGHT - 1 or y_px + self.tile_h <= 0:
            return
        col = self.COLORS[value % len(self.COLORS)]
        y1 = max(0, y_px)
        y2 = min(PLAY_HEIGHT - 1, y_px + self.tile_h - 1)
        draw_rectangle(gx, y1, gx + self.tile_w - 1, y2, *col)
        if y1 <= y2:
            draw_rectangle(
                gx,
                y1,
                gx + self.tile_w - 1,
                y1,
                min(255, col[0] + 35),
                min(255, col[1] + 35),
                min(255, col[2] + 35),
            )

    def _draw_tile_value(self, x, y, value, empty_color=(20, 20, 20)):
        gx = x * self.tile_w
        gy = y * self.tile_h
        if value is None:
            draw_rectangle(
                gx, gy, gx + self.tile_w - 1, gy + self.tile_h - 1, *empty_color
            )
        else:
            col = self.COLORS[value % len(self.COLORS)]
            draw_rectangle(gx, gy, gx + self.tile_w - 1, gy + self.tile_h - 1, *col)

    def _draw_falling_tiles(self, movers, frame_px):
        display.clear()
        for x, start_px, end_px, value in movers:
            y_px = start_px + min(frame_px, end_px - start_px)
            self._draw_tile_at_px(x, y_px, value)
        self._draw_hud(force=True)
        display_flush()

    def _collapse_and_refill_animated(self, delay_ms=14):
        movers = []
        new_grid = [[None for _x in range(self.cols)] for _y in range(self.rows)]
        max_drop = 0

        for x in range(self.cols):
            kept = []
            for y in range(self.rows - 1, -1, -1):
                v = self.grid[y][x]
                if v is not None:
                    kept.append((y, v))

            dst_y = self.rows - 1
            for src_y, value in kept:
                new_grid[dst_y][x] = value
                start_px = src_y * self.tile_h
                end_px = dst_y * self.tile_h
                movers.append((x, start_px, end_px, value))
                max_drop = max(max_drop, end_px - start_px)
                dst_y -= 1

            spawn_row = -1
            while dst_y >= 0:
                value = random.randint(0, len(self.COLORS) - 1)
                new_grid[dst_y][x] = value
                start_px = spawn_row * self.tile_h
                end_px = dst_y * self.tile_h
                movers.append((x, start_px, end_px, value))
                max_drop = max(max_drop, end_px - start_px)
                spawn_row -= 1
                dst_y -= 1

        for frame_px in range(0, max_drop + 1):
            self._draw_falling_tiles(movers, frame_px)
            if delay_ms > 0:
                sleep_ms(delay_ms)

        self.grid = new_grid

    def _remove_matches_and_score(self, delay_ms=50):
        total_removed = 0
        while True:
            removed_coords = self._find_matches()
            if not removed_coords:
                break

            total_removed += len(removed_coords)

            # Animate removal: matched blocks dissolve into dark pixels.
            anim_frames = max(8, self.tile_w + self.tile_h)
            for f in range(anim_frames):
                display.clear()
                for ry in range(self.rows):
                    for rx in range(self.cols):
                        gx = rx * self.tile_w
                        gy = ry * self.tile_h
                        v = self.grid[ry][rx]
                        if (rx, ry) in removed_coords:
                            base = (
                                self.COLORS[v % len(self.COLORS)]
                                if v is not None
                                else (255, 255, 255)
                            )
                            for py in range(self.tile_h):
                                for px in range(self.tile_w):
                                    threshold = (
                                        px * 5 + py * 3 + rx * 7 + ry * 11
                                    ) % anim_frames
                                    if threshold <= f:
                                        display.set_pixel(gx + px, gy + py, 12, 12, 14)
                                    else:
                                        glow = 30 if f < 3 else 0
                                        display.set_pixel(
                                            gx + px,
                                            gy + py,
                                            min(255, base[0] + glow),
                                            min(255, base[1] + glow),
                                            min(255, base[2] + glow),
                                        )
                        else:
                            self._draw_tile_value(rx, ry, v, empty_color=(16, 16, 16))

                self._draw_hud(force=True)
                display_flush()
                maybe_collect(10)
                if delay_ms > 0:
                    sleep_ms(delay_ms)

            # Now actually remove and score
            for rx, ry in removed_coords:
                self.grid[ry][rx] = None
            # score: 10 per gem removed
            self.score += len(removed_coords) * 10
            # collapse and refill pixel by pixel, then loop to catch cascades
            self._collapse_and_refill_animated(
                delay_ms=delay_ms // 4 if delay_ms > 0 else 0
            )
            self._full_redraw = True

        self._needs_redraw = True

        return total_removed > 0

    def _swap_tiles(self, a, b):
        ax, ay = a
        bx, by = b
        self.grid[ay][ax], self.grid[by][bx] = self.grid[by][bx], self.grid[ay][ax]

    def _draw_board(self):
        for y in range(self.rows):
            for x in range(self.cols):
                self._draw_tile_value(x, y, self.grid[y][x])
        # selection highlight
        if self.sel is not None:
            sx, sy = self.sel
            gx = sx * self.tile_w
            gy = sy * self.tile_h
            draw_rect_outline(
                gx, gy, gx + self.tile_w - 1, gy + self.tile_h - 1, 255, 255, 255
            )

    def _draw_cell(self, x, y):
        self._draw_tile_value(x, y, self.grid[y][x])
        if self.sel == (x, y):
            gx = x * self.tile_w
            gy = y * self.tile_h
            draw_rect_outline(
                gx, gy, gx + self.tile_w - 1, gy + self.tile_h - 1, 255, 255, 255
            )

    def _draw_cursor(self):
        gx = self.cursor_x * self.tile_w
        gy = self.cursor_y * self.tile_h
        draw_rect_outline(
            gx, gy, gx + self.tile_w - 1, gy + self.tile_h - 1, 255, 245, 0
        )

    def _draw_hud(self, force=False):
        if not force and self.score == self._last_drawn_score:
            return
        draw_rectangle(0, PLAY_HEIGHT, WIDTH - 1, HEIGHT - 1, 0, 0, 0)
        draw_text_small(1, PLAY_HEIGHT, "S{}".format(self.score), 255, 255, 255)
        display_score_and_time(self.score)
        self._last_drawn_score = self.score

    def _render(self, full=False):
        if full or self._full_redraw:
            display.clear()
            self._draw_board()
            self._draw_cursor()
            self._draw_hud(force=True)
        else:
            dirty = []
            for cell in (
                self._prev_cursor,
                (self.cursor_x, self.cursor_y),
                self._prev_sel,
                self.sel,
            ):
                if cell is None:
                    continue
                if cell not in dirty:
                    dirty.append(cell)

            for x, y in dirty:
                if 0 <= x < self.cols and 0 <= y < self.rows:
                    self._draw_cell(x, y)

            self._draw_cursor()
            self._draw_hud()

        self._prev_cursor = (self.cursor_x, self.cursor_y)
        self._prev_sel = self.sel
        self._full_redraw = False
        self._needs_redraw = False
        display_flush()

    def main_loop(self, joystick):
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        display.clear()
        last_logic = ticks_ms()
        logic_ms = 90
        self._needs_redraw = True

        while True:
            c_button, z_button = joystick.read_buttons()
            if c_button:
                global_score = self.score
                game_over = True
                return

            now = ticks_ms()
            d = joystick.read_direction(
                [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
            )
            if d and ticks_diff(now, self._last_move) >= self._move_delay:
                if d == JOYSTICK_UP:
                    self.cursor_y = max(0, self.cursor_y - 1)
                elif d == JOYSTICK_DOWN:
                    self.cursor_y = min(self.rows - 1, self.cursor_y + 1)
                elif d == JOYSTICK_LEFT:
                    self.cursor_x = max(0, self.cursor_x - 1)
                elif d == JOYSTICK_RIGHT:
                    self.cursor_x = min(self.cols - 1, self.cursor_x + 1)
                self._last_move = now
                self._needs_redraw = True

            if z_button and ticks_diff(now, last_logic) >= 0:
                # select or attempt swap
                if self.sel is None:
                    self.sel = (self.cursor_x, self.cursor_y)
                    self._needs_redraw = True
                else:
                    sx, sy = self.sel
                    cx, cy = self.cursor_x, self.cursor_y
                    if abs(sx - cx) + abs(sy - cy) == 1:
                        # adjacent -> try swap
                        self._swap_tiles((sx, sy), (cx, cy))
                        if self._find_matches():
                            # consume matches
                            self._remove_matches_and_score()
                        else:
                            # revert
                            self._swap_tiles((sx, sy), (cx, cy))
                        self.sel = None
                        self._needs_redraw = True
                    else:
                        # new selection
                        self.sel = (self.cursor_x, self.cursor_y)
                        self._needs_redraw = True
                # wait until released
                while joystick.read_buttons()[1]:
                    sleep_ms(10)

            # regular match processing (in case cascades happen)
            if ticks_diff(now, last_logic) >= logic_ms:
                last_logic = now
                # ensure no leftover matches
                self._remove_matches_and_score()

            if self._needs_redraw:
                self._render()

            maybe_collect(60)
            sleep_ms(8)

    async def main_loop_async(self, joystick):
        """Async version for pygbag: yields with asyncio.sleep()."""
        if asyncio is None:
            return self.main_loop(joystick)

        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()
        display.clear()
        last_logic = ticks_ms()
        logic_ms = 90
        self._needs_redraw = True

        while True:
            c_button, z_button = joystick.read_buttons()
            if c_button:
                global_score = self.score
                game_over = True
                return

            now = ticks_ms()
            d = joystick.read_direction(
                [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT]
            )
            if d and ticks_diff(now, self._last_move) >= self._move_delay:
                if d == JOYSTICK_UP:
                    self.cursor_y = max(0, self.cursor_y - 1)
                elif d == JOYSTICK_DOWN:
                    self.cursor_y = min(self.rows - 1, self.cursor_y + 1)
                elif d == JOYSTICK_LEFT:
                    self.cursor_x = max(0, self.cursor_x - 1)
                elif d == JOYSTICK_RIGHT:
                    self.cursor_x = min(self.cols - 1, self.cursor_x + 1)
                self._last_move = now
                self._needs_redraw = True

            if z_button and ticks_diff(now, last_logic) >= 0:
                # select or attempt swap
                if self.sel is None:
                    self.sel = (self.cursor_x, self.cursor_y)
                    self._needs_redraw = True
                else:
                    sx, sy = self.sel
                    cx, cy = self.cursor_x, self.cursor_y
                    if abs(sx - cx) + abs(sy - cy) == 1:
                        # adjacent -> try swap
                        self._swap_tiles((sx, sy), (cx, cy))
                        if self._find_matches():
                            # consume matches
                            self._remove_matches_and_score(delay_ms=0)
                        else:
                            # revert
                            self._swap_tiles((sx, sy), (cx, cy))
                        self.sel = None
                        self._needs_redraw = True
                    else:
                        # new selection
                        self.sel = (self.cursor_x, self.cursor_y)
                        self._needs_redraw = True
                # wait until released
                while joystick.read_buttons()[1]:
                    await asyncio.sleep(0.01)

            # regular match processing (in case cascades happen)
            if ticks_diff(now, last_logic) >= logic_ms:
                last_logic = now
                # ensure no leftover matches
                self._remove_matches_and_score(delay_ms=0)

            if self._needs_redraw:
                self._render()

            maybe_collect(60)
            await asyncio.sleep(0.008)
