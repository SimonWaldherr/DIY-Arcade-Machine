class LunarLanderGame:
    """
    LUNAR LANDER MINI
    Steuerung:
      - Links/Rechts: drehen
      - Z oder Stick UP: Schub
      - C: zurück ins Menü
    Ziel: weich & gerade auf dem grünen Pad landen.
    """

    _STEP = 5
    _LUT = None
    # pad_x, pad_w, pad_y, terrain control points, fuel, gravity, thrust.
    # Profiles are deliberately fixed so each level can be checked for a clear,
    # reachable landing pad instead of relying on random terrain.
    LEVELS = (
        (25, 10, 48, (48, 46, 49, 47, 50), 760, 0.10, 0.30),
        (9, 10, 44, (42, 45, 43, 48, 46), 720, 0.105, 0.30),
        (45, 9, 42, (50, 47, 45, 43, 41), 700, 0.112, 0.31),
        (18, 9, 39, (46, 43, 40, 44, 48), 680, 0.118, 0.31),
        (36, 8, 36, (52, 47, 42, 38, 44), 650, 0.124, 0.32),
        (7, 8, 35, (39, 42, 45, 40, 37), 630, 0.130, 0.32),
        (49, 7, 33, (50, 45, 39, 35, 34), 610, 0.136, 0.33),
        (27, 7, 31, (44, 40, 36, 32, 38), 590, 0.142, 0.33),
    )

    @classmethod
    def _ensure_lut(cls):
        if cls._LUT is not None:
            return
        lut = []
        step = cls._STEP
        for a in range(0, 360, step):
            lut.append(
                (
                    int(math.cos(math.radians(a)) * 256),
                    int(math.sin(math.radians(a)) * 256),
                )
            )
        cls._LUT = lut

    def __init__(self, ctx=None):
        self.mode = get_context_setting(ctx, "mode", "classic")
        self.level = 1
        self.total_score = 0
        self.reset()

    def reset(self, keep_level=False):
        # Multi-level system: keep level on successful landing, reset on crash
        if not keep_level:
            self.level = 1
            self.total_score = 0

        profile = self.LEVELS[(self.level - 1) % len(self.LEVELS)]
        cycle = (self.level - 1) // len(self.LEVELS)
        self.terrain = self._make_terrain(profile, cycle)

        # Pad/fuel/gravity come from fixed profiles, with a small cap for
        # repeat cycles after the handcrafted set.
        self.pad_x = profile[0]
        self.pad_w = max(6, profile[1] - min(2, cycle))
        self.pad_y = profile[2]
        for x in range(self.pad_x, self.pad_x + self.pad_w):
            self.terrain[x] = self.pad_y

        self.x = float(WIDTH // 2)
        self.y = 8.0
        self.vx = 0.0
        self.vy = 0.0
        self.angle = 90

        self.fuel_max = max(470, int(profile[4] - cycle * 30))
        self.fuel = self.fuel_max

        self.g = profile[5] + cycle * 0.006
        self.thrust = profile[6]

        self.points = 300
        self.last_points_ms = ticks_ms()
        self.frame = 0

    def _make_terrain(self, profile, cycle=0):
        control = profile[3]
        span = WIDTH - 1
        t = [0] * WIDTH
        lo = PLAY_HEIGHT - 24
        hi = PLAY_HEIGHT - 4
        for x in range(WIDTH):
            pos = x * (len(control) - 1) / span
            i = int(pos)
            if i >= len(control) - 1:
                y = control[-1]
            else:
                frac = pos - i
                y = int(control[i] * (1.0 - frac) + control[i + 1] * frac)
            ripple = ((x * 7 + self.level * 5) % 5) - 2
            t[x] = clamp(y + ripple + min(2, cycle), lo, hi)

        # smooth
        for _ in range(2):
            for x in range(1, WIDTH - 1):
                t[x] = (t[x - 1] + t[x] + t[x + 1]) // 3
        return t

    def _cos_sin256(self, angle_deg):
        angle_deg %= 360
        self._ensure_lut()
        idx = (angle_deg // self._STEP) % (360 // self._STEP)
        return self._LUT[idx]

    def _angle_diff(self, a, b):
        d = (a - b + 180) % 360 - 180
        return abs(d)

    def _line(self, x0, y0, x1, y1, r, g, b):
        # Delegate to module-level Bresenham helper (shared with UFODefenseGame)
        draw_line(x0, y0, x1, y1, r, g, b)

    def _draw_ship(self, thrust_on=False):
        size = 4
        cx, cy = self.x, self.y

        c, s = self._cos_sin256(self.angle)
        dx = (c * size) / 256.0
        dy = (-s * size) / 256.0  # y nach unten -> -sin

        nx = cx + dx
        ny = cy + dy

        c1, s1 = self._cos_sin256(self.angle + 140)
        lx = cx + (c1 * size) / 256.0
        ly = cy + (-s1 * size) / 256.0

        c2, s2 = self._cos_sin256(self.angle - 140)
        rx = cx + (c2 * size) / 256.0
        ry = cy + (-s2 * size) / 256.0

        self._line(nx, ny, lx, ly, 255, 255, 255)
        self._line(nx, ny, rx, ry, 255, 255, 255)
        self._line(lx, ly, rx, ry, 255, 255, 255)

        if thrust_on and self.fuel > 0:
            fx0 = cx - dx * 0.4
            fy0 = cy - dy * 0.4
            fx1 = cx - dx * 1.4
            fy1 = cy - dy * 1.4
            self._line(fx0, fy0, fx1, fy1, 255, 80, 0)

    def _draw_terrain(self):
        sp = display.set_pixel
        for x in range(WIDTH):
            ty = self.terrain[x]
            for y in range(ty, PLAY_HEIGHT):
                sp(x, y, 0, 0, 120)

        # pad highlight
        for x in range(self.pad_x, self.pad_x + self.pad_w):
            y = self.pad_y
            if 0 <= x < WIDTH and 0 <= y < PLAY_HEIGHT:
                sp(x, y, 0, 255, 0)
                if y + 1 < PLAY_HEIGHT:
                    sp(x, y + 1, 0, 200, 0)

    def _draw_fuel_bar(self):
        bar_w = 22
        filled = int((self.fuel / float(self.fuel_max)) * bar_w)
        if filled < 0:
            filled = 0
        if filled > bar_w:
            filled = bar_w

        draw_rectangle(0, 0, bar_w, 1, 40, 40, 40)
        if filled > 0:
            draw_rectangle(0, 0, filled - 1, 1, 255, 255, 0)

    def _reset_v2(self):
        self.level = 1
        self.total_score = 0
        self.world_w = 320
        self.v2_pads = []
        self.v2_powerups = []
        self.v2_target = 0
        self.v2_camera_x = 0
        self.v2_docked = False
        self.v2_docked_pad = -1
        self.v2_terrain = self._make_v2_terrain()
        self.x = 22.0
        self.y = 12.0
        self.vx = 0.0
        self.vy = 0.0
        self.angle = 90
        self.fuel_max = 900
        self.fuel = self.fuel_max
        self.g = 0.092
        self.thrust = 0.44
        self.points = 500
        self.last_points_ms = ticks_ms()
        self.frame = 0

    def _make_v2_terrain(self):
        t = [PLAY_HEIGHT - 8] * self.world_w
        pad_specs = (
            (18, 11, 47),
            (82, 10, 43),
            (145, 9, 39),
            (214, 9, 44),
            (284, 8, 36),
        )
        for x in range(self.world_w):
            base = PLAY_HEIGHT - 10
            wave = int(math.sin(x * 0.075) * 7 + math.sin(x * 0.021 + 1.7) * 5)
            t[x] = clamp(base + wave, PLAY_HEIGHT - 25, PLAY_HEIGHT - 4)
        for _ in range(2):
            for x in range(1, self.world_w - 1):
                t[x] = (t[x - 1] + t[x] + t[x + 1]) // 3
        self.v2_pads = []
        for px, pw, py in pad_specs:
            self.v2_pads.append({"x": px, "w": pw, "y": py, "done": False})
            for x in range(px, min(self.world_w, px + pw)):
                t[x] = py
        self.v2_powerups = [
            {"x": 55, "y": 28, "kind": "FUEL", "on": True},
            {"x": 124, "y": 24, "kind": "FUEL", "on": True},
            {"x": 190, "y": 22, "kind": "FUEL", "on": True},
            {"x": 252, "y": 26, "kind": "FUEL", "on": True},
        ]
        return t

    def _v2_screen_x(self, world_x):
        return int(world_x - self.v2_camera_x)

    def _update_v2_camera(self):
        target = int(self.x) - WIDTH // 2
        self.v2_camera_x = clamp(target, 0, max(0, self.world_w - WIDTH))

    def _draw_terrain_v2(self):
        start = int(self.v2_camera_x)
        sp = display.set_pixel
        for sx in range(WIDTH):
            wx = start + sx
            if wx < 0 or wx >= self.world_w:
                continue
            ty = self.v2_terrain[wx]
            col = (0, 80, 145)
            for pad_i, pad in enumerate(self.v2_pads):
                if pad["x"] <= wx < pad["x"] + pad["w"] and ty == pad["y"]:
                    if pad_i == self.v2_target:
                        col = (0, 255, 0)
                    elif pad.get("done"):
                        col = (60, 130, 80)
                    else:
                        col = (100, 100, 100)
                    break
            for y in range(ty, PLAY_HEIGHT):
                sp(sx, y, col[0] // 2, col[1] // 2, col[2] // 2)
            sp(sx, ty, *col)

    def _draw_powerups_v2(self):
        phase = (self.frame // 4) & 1
        for p in self.v2_powerups:
            if not p["on"]:
                continue
            sx = self._v2_screen_x(p["x"])
            sy = int(p["y"])
            if -2 <= sx < WIDTH + 2:
                col = (255, 230, 40) if phase else (255, 120, 20)
                draw_rectangle(sx - 1, sy - 1, sx + 1, sy + 1, *col)

    def _draw_ship_v2(self, thrust_on=False):
        old_x = self.x
        self.x = self._v2_screen_x(old_x)
        self._draw_ship(thrust_on)
        self.x = old_x

    def _collect_powerups_v2(self):
        for p in self.v2_powerups:
            if not p["on"]:
                continue
            if abs(self.x - p["x"]) <= 3 and abs(self.y - p["y"]) <= 3:
                p["on"] = False
                self.fuel = min(self.fuel_max, self.fuel + 260)
                self.total_score += 75

    def _dock_v2(self, pad_i):
        pad = self.v2_pads[pad_i]
        self.v2_docked = True
        self.v2_docked_pad = pad_i
        self.x = float(pad["x"] + pad["w"] // 2)
        self.y = float(pad["y"] - 5)
        self.vx = 0.0
        self.vy = 0.0
        self.angle = 90

    def _v2_landing_result(self):
        ix = clamp(int(self.x), 0, self.world_w - 1)
        gy = self.v2_terrain[ix]
        if self.y < gy - 1:
            return None
        soft = abs(self.vx) < 0.70 and abs(self.vy) < 1.25
        upright = self._angle_diff(self.angle, 90) <= 25
        landed_pad_i = -1
        for i, pad in enumerate(self.v2_pads):
            if pad["x"] <= ix < pad["x"] + pad["w"] and gy == pad["y"]:
                landed_pad_i = i
                break
        if landed_pad_i >= 0 and soft and upright:
            pad = self.v2_pads[landed_pad_i]
            if landed_pad_i != self.v2_target:
                if pad.get("done"):
                    self._dock_v2(landed_pad_i)
                    self.fuel = min(self.fuel_max, self.fuel + 80)
                    return "docked"
                return "crash"
            pad["done"] = True
            self.total_score += self.points + int(self.fuel) + 250
            self.v2_target += 1
            if self.v2_target >= len(self.v2_pads):
                return "won"
            self.points = 500 + self.v2_target * 80
            self.fuel = min(self.fuel_max, self.fuel + 180)
            self._dock_v2(landed_pad_i)
            return "landed"
        return "crash"

    def _draw_v2_scene(self, thrust_on=False):
        self._update_v2_camera()
        display.clear()
        self._draw_terrain_v2()
        self._draw_powerups_v2()
        self._draw_ship_v2(thrust_on)
        self._draw_fuel_bar()
        target = self.v2_pads[min(self.v2_target, len(self.v2_pads) - 1)]
        tx = self._v2_screen_x(target["x"] + target["w"] // 2)
        if 0 <= tx < WIDTH:
            draw_text_small(clamp(tx - 3, 0, WIDTH - 12), 3, "V", 0, 255, 0)
        display_score_and_time(global_score)

    def _run_v2_frame(self, joystick):
        global game_over, global_score
        c_button, z_button = joystick.read_buttons()
        if c_button:
            return False
        now = ticks_ms()
        self.frame += 1
        if ticks_diff(now, self.last_points_ms) >= 500:
            self.last_points_ms = now
            if self.points > 0:
                self.points -= 1
        d = joystick.read_direction([JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_UP])
        if d == JOYSTICK_LEFT:
            self.angle = (self.angle + 5) % 360
        elif d == JOYSTICK_RIGHT:
            self.angle = (self.angle - 5) % 360
        thrust_on = (z_button or d == JOYSTICK_UP) and self.fuel > 0
        if self.v2_docked:
            global_score = self.total_score + self.points
            if thrust_on:
                self.v2_docked = False
                self.v2_docked_pad = -1
                self.vy = -1.25
                self.y -= 2.0
            else:
                self._draw_v2_scene(False)
                return True
        ax = 0.0
        ay = self.g
        if thrust_on:
            c, s = self._cos_sin256(self.angle)
            ax += (c / 256.0) * self.thrust
            ay += (-s / 256.0) * self.thrust
            self.fuel -= 1
        self.vx = clamp(self.vx + ax, -2.8, 2.8)
        self.vy = clamp(self.vy + ay, -3.4, 3.0)
        self.x = clamp(self.x + self.vx, 1.0, self.world_w - 2.0)
        self.y = max(0.0, self.y + self.vy)
        self._collect_powerups_v2()
        result = self._v2_landing_result()
        if result == "crash":
            set_game_over_score(self.total_score)
            return False
        if result == "won":
            set_game_over_score(self.total_score, won=True)
            return False
        global_score = self.total_score + self.points
        self._draw_v2_scene(thrust_on)
        return True

    def _main_loop_v2(self, joystick):
        global game_over, global_score
        game_over = False
        global_score = 0
        self._reset_v2()
        frame_ms = 35
        last_frame = ticks_ms()
        while not game_over:
            if ticks_diff(ticks_ms(), last_frame) < frame_ms:
                sleep_ms(2)
                continue
            last_frame = ticks_ms()
            if not self._run_v2_frame(joystick):
                return

    async def _main_loop_v2_async(self, joystick):
        if asyncio is None:
            return self._main_loop_v2(joystick)
        global game_over, global_score
        game_over = False
        global_score = 0
        self._reset_v2()
        frame_ms = 35
        last_frame = ticks_ms()
        while not game_over:
            if ticks_diff(ticks_ms(), last_frame) < frame_ms:
                await asyncio.sleep(0.002)
                continue
            last_frame = ticks_ms()
            if not self._run_v2_frame(joystick):
                return

    def main_loop(self, joystick):
        if self.mode == "scroll":
            return self._main_loop_v2(joystick)
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()

        frame_ms = 35
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

                # time bonus counts down (faster landing = more points)
                if ticks_diff(now, self.last_points_ms) >= 500:
                    self.last_points_ms = now
                    if self.points > 0:
                        self.points -= 1

                # input
                d = joystick.read_direction(
                    [JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_UP]
                )
                if d == JOYSTICK_LEFT:
                    self.angle = (self.angle + 5) % 360
                elif d == JOYSTICK_RIGHT:
                    self.angle = (self.angle - 5) % 360

                thrust_on = (z_button or d == JOYSTICK_UP) and (self.fuel > 0)

                ax = 0.0
                ay = self.g
                if thrust_on:
                    c, s = self._cos_sin256(self.angle)
                    ax += (c / 256.0) * self.thrust
                    ay += (-s / 256.0) * self.thrust
                    self.fuel -= 1

                # physics
                self.vx += ax
                self.vy += ay

                # clamp velocity
                if self.vx > 2.2:
                    self.vx = 2.2
                if self.vx < -2.2:
                    self.vx = -2.2
                if self.vy > 3.0:
                    self.vy = 3.0
                if self.vy < -3.0:
                    self.vy = -3.0

                self.x += self.vx
                self.y += self.vy

                # bounds
                if self.x < 0:
                    self.x = 0
                    self.vx = 0
                elif self.x > WIDTH - 1:
                    self.x = WIDTH - 1
                    self.vx = 0

                if self.y < 0:
                    self.y = 0
                    self.vy = 0

                # landing/crash
                ix = int(self.x)
                gy = self.terrain[ix]
                if self.y >= gy - 1:
                    on_pad = self.pad_x <= ix <= (self.pad_x + self.pad_w - 1)
                    soft = abs(self.vx) < 0.65 and abs(self.vy) < 1.2
                    upright = self._angle_diff(self.angle, 90) <= 25

                    if on_pad and soft and upright:
                        # Successful landing: award points and advance level
                        level_bonus = (
                            self.points + int(self.fuel) + 200 + (self.level * 150)
                        )
                        self.total_score += level_bonus
                        global_score = self.total_score

                        display.clear()
                        draw_text(2, 12, "LVL" + str(self.level), 0, 255, 0)
                        draw_text(2, 24, "DONE", 0, 255, 0)
                        display_score_and_time(global_score)
                        sleep_ms(1800)

                        # Next level
                        self.level += 1
                        self.reset(keep_level=True)

                        # Short preview of new terrain
                        display.clear()
                        self._draw_terrain()
                        draw_text(2, 4, "LVL" + str(self.level), 255, 255, 0)
                        display_score_and_time(global_score)
                        sleep_ms(1500)

                        last_frame = ticks_ms()
                        continue
                    else:
                        global_score = (
                            self.total_score
                            if hasattr(self, "total_score")
                            else self.points
                        )
                        game_over = True
                        return

                # render
                display.clear()
                self._draw_terrain()
                self._draw_ship(thrust_on=thrust_on)
                self._draw_fuel_bar()
                display_score_and_time(self.points)
                global_score = self.points

                if self.frame % 45 == 0:
                    gc.collect()

            except RestartProgram:
                return

    async def main_loop_async(self, joystick):
        """Async version for pygbag: yields with asyncio.sleep()."""
        if asyncio is None:
            return self.main_loop(joystick)
        if self.mode == "scroll":
            return await self._main_loop_v2_async(joystick)

        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()

        frame_ms = 35
        last_frame = ticks_ms()

        while not game_over:
            try:
                c_button, z_button = joystick.read_buttons()
                if c_button:
                    return

                now = ticks_ms()
                if ticks_diff(now, last_frame) < frame_ms:
                    await asyncio.sleep(0.002)
                    continue
                last_frame = now
                self.frame += 1

                # time bonus counts down (faster landing = more points)
                if ticks_diff(now, self.last_points_ms) >= 500:
                    self.last_points_ms = now
                    if self.points > 0:
                        self.points -= 1

                # input
                d = joystick.read_direction(
                    [JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_UP]
                )
                if d == JOYSTICK_LEFT:
                    self.angle = (self.angle + 5) % 360
                elif d == JOYSTICK_RIGHT:
                    self.angle = (self.angle - 5) % 360

                thrust_on = (z_button or d == JOYSTICK_UP) and (self.fuel > 0)

                ax = 0.0
                ay = self.g
                if thrust_on:
                    c, s = self._cos_sin256(self.angle)
                    ax += (c / 256.0) * self.thrust
                    ay += (-s / 256.0) * self.thrust
                    self.fuel -= 1

                # physics
                self.vx += ax
                self.vy += ay

                # clamp velocity
                if self.vx > 2.2:
                    self.vx = 2.2
                if self.vx < -2.2:
                    self.vx = -2.2
                if self.vy > 3.0:
                    self.vy = 3.0
                if self.vy < -3.0:
                    self.vy = -3.0

                self.x += self.vx
                self.y += self.vy

                # bounds
                if self.x < 0:
                    self.x = 0
                    self.vx = 0
                elif self.x > WIDTH - 1:
                    self.x = WIDTH - 1
                    self.vx = 0

                if self.y < 0:
                    self.y = 0
                    self.vy = 0

                # landing/crash
                ix = int(self.x)
                gy = self.terrain[ix]
                if self.y >= gy - 1:
                    on_pad = self.pad_x <= ix <= (self.pad_x + self.pad_w - 1)
                    soft = abs(self.vx) < 0.65 and abs(self.vy) < 1.2
                    upright = self._angle_diff(self.angle, 90) <= 25

                    if on_pad and soft and upright:
                        # Successful landing: award points and advance level
                        level_bonus = (
                            self.points + int(self.fuel) + 200 + (self.level * 150)
                        )
                        self.total_score += level_bonus
                        global_score = self.total_score

                        display.clear()
                        draw_text(2, 12, "LVL" + str(self.level), 0, 255, 0)
                        draw_text(2, 24, "DONE", 0, 255, 0)
                        display_score_and_time(global_score)
                        await asyncio.sleep(1.8)

                        # Next level
                        self.level += 1
                        self.reset(keep_level=True)

                        # Short preview of new terrain
                        display.clear()
                        self._draw_terrain()
                        draw_text(2, 4, "LVL" + str(self.level), 255, 255, 0)
                        display_score_and_time(global_score)
                        await asyncio.sleep(1.5)

                        last_frame = ticks_ms()
                        continue
                    else:
                        global_score = (
                            self.total_score
                            if hasattr(self, "total_score")
                            else self.points
                        )
                        game_over = True
                        return

                # render
                display.clear()
                self._draw_terrain()
                self._draw_ship(thrust_on=thrust_on)
                self._draw_fuel_bar()
                display_score_and_time(self.points)
                global_score = self.points

                if self.frame % 45 == 0:
                    try:
                        gc.collect()
                    except Exception:
                        pass

            except RestartProgram:
                return


class KerbalGame(FrameLoopGame):
    """
    KERBAL
    Controls:
      - Left / Right: rotate rocket
      - Z or Up: thrust
      - C: return to menu
    Arcade orbital flight: launch, circularize, optionally return and land.
    """

    FRAME_MS = 35
    PLANET_R = 18.0
    MU = 34.0
    SCALE = 1.28

    def __init__(self, ctx=None):
        self.mission = get_context_setting(ctx, "mission", "orbit")
        self.assist = bool(get_context_setting(ctx, "assist", True))
        self.reset()

    def reset(self):
        self.cx = 0.0
        self.cy = 0.0
        self.x = 0.0
        self.y = -self.PLANET_R - 2.0
        self.vx = 0.0
        self.vy = 0.0
        self.angle = 90
        self.fuel_max = 860
        self.fuel = self.fuel_max
        self.thrust = 0.090
        self.score = 0
        self.orbit_hold = 0
        self.return_ready = False
        self.landed = False
        self.frame = 0
        self.prelaunch = True
        self.launch_grace = 0
        self.trail = []
        self.max_trail = 54
        self.last_score_ms = ticks_ms()

    def _cos_sin(self, angle_deg):
        a = math.radians(angle_deg % 360)
        return math.cos(a), math.sin(a)

    def _radius(self):
        return math.sqrt(self.x * self.x + self.y * self.y) + 1e-6

    def _surface_alt(self):
        return self._radius() - self.PLANET_R

    def _radial_tangent_speed(self):
        r = self._radius()
        ux = self.x / r
        uy = self.y / r
        radial = self.vx * ux + self.vy * uy
        tangent = self.vx * (-uy) + self.vy * ux
        return radial, tangent

    def _orbit_quality(self):
        alt = self._surface_alt()
        radial, tangent = self._radial_tangent_speed()
        target = math.sqrt(self.MU / max(8.0, self._radius()))
        alt_ok = 8.0 <= alt <= 24.0
        speed_ok = abs(abs(tangent) - target) < (0.20 if self.assist else 0.14)
        radial_ok = abs(radial) < (0.18 if self.assist else 0.10)
        return alt_ok and speed_ok and radial_ok, alt, target, radial, tangent

    def _screen(self, wx, wy):
        return int(WIDTH // 2 + wx * self.SCALE), int(
            PLAY_HEIGHT // 2 + wy * self.SCALE
        )

    def _draw_planet(self):
        px, py = self._screen(0, 0)
        r = int(self.PLANET_R * self.SCALE)
        for deg in range(0, 360, 10):
            a = math.radians(deg)
            x = px + int(math.cos(a) * r)
            y = py + int(math.sin(a) * r)
            if 0 <= x < WIDTH and 0 <= y < PLAY_HEIGHT:
                display.set_pixel(x, y, 40, 120, 255)
        for deg in range(0, 360, 30):
            a = math.radians(deg)
            x = px + int(math.cos(a) * (r - 2))
            y = py + int(math.sin(a) * (r - 2))
            if 0 <= x < WIDTH and 0 <= y < PLAY_HEIGHT:
                display.set_pixel(x, y, 20, 80, 160)

    def _draw_orbit_band(self):
        px, py = self._screen(0, 0)
        for rr, col in (
            (int((self.PLANET_R + 8.0) * self.SCALE), (25, 70, 25)),
            (int((self.PLANET_R + 24.0) * self.SCALE), (25, 70, 25)),
        ):
            for deg in range(0, 360, 18):
                a = math.radians(deg)
                x = px + int(math.cos(a) * rr)
                y = py + int(math.sin(a) * rr)
                if 0 <= x < WIDTH and 0 <= y < PLAY_HEIGHT:
                    display.set_pixel(x, y, *col)

    def _record_trail(self):
        if (self.frame & 1) != 0:
            return
        self.trail.append((self.x, self.y))
        if len(self.trail) > self.max_trail:
            self.trail.pop(0)

    def _draw_trail(self):
        n = len(self.trail)
        if n < 2:
            return
        for i, (tx, ty) in enumerate(self.trail):
            sx, sy = self._screen(tx, ty)
            if 0 <= sx < WIDTH and 0 <= sy < PLAY_HEIGHT:
                level = 45 + int(130 * (i + 1) / n)
                display.set_pixel(sx, sy, 20, level, 170)

    def _draw_flight_cues(self):
        sx, sy = self._screen(self.x, self.y)
        speed = math.sqrt(self.vx * self.vx + self.vy * self.vy)
        if speed > 0.08:
            vx = self.vx / speed
            vy = self.vy / speed
            px = sx + int(vx * 6)
            py = sy + int(vy * 6)
            set_pixel_clipped(px, py, 80, 255, 255)
            if self.return_ready:
                rx = sx - int(vx * 6)
                ry = sy - int(vy * 6)
                set_pixel_clipped(rx, ry, 255, 130, 40)
        if self.assist:
            c, s = self._cos_sin(self.angle)
            ax = sx + int(c * 7)
            ay = sy - int(s * 7)
            set_pixel_clipped(ax, ay, 255, 255, 70)

    def _draw_ship(self, thrust_on):
        sx, sy = self._screen(self.x, self.y)
        c, s = self._cos_sin(self.angle)
        nose = (sx + int(c * 4), sy - int(s * 4))
        left = (
            sx + int(math.cos(math.radians(self.angle + 140)) * 3),
            sy - int(math.sin(math.radians(self.angle + 140)) * 3),
        )
        right = (
            sx + int(math.cos(math.radians(self.angle - 140)) * 3),
            sy - int(math.sin(math.radians(self.angle - 140)) * 3),
        )
        draw_line(nose[0], nose[1], left[0], left[1], 255, 255, 255)
        draw_line(nose[0], nose[1], right[0], right[1], 255, 255, 255)
        draw_line(left[0], left[1], right[0], right[1], 255, 255, 255)
        if thrust_on:
            fx = sx - int(c * 5)
            fy = sy + int(s * 5)
            draw_line(sx, sy, fx, fy, 255, 100, 0)

    def _draw_hud(self, alt, target_speed, radial, tangent):
        draw_rectangle(0, PLAY_HEIGHT, WIDTH - 1, HEIGHT - 1, 0, 0, 0)
        fuel_w = int(20 * max(0, self.fuel) / self.fuel_max)
        draw_rectangle(1, PLAY_HEIGHT + 1, 20, PLAY_HEIGHT + 2, 45, 45, 45)
        if fuel_w > 0:
            draw_rectangle(1, PLAY_HEIGHT + 1, fuel_w, PLAY_HEIGHT + 2, 255, 210, 30)
        draw_text_small(24, PLAY_HEIGHT, "A" + str(max(0, int(alt))), 180, 220, 255)
        if self.prelaunch:
            draw_text_small(43, PLAY_HEIGHT, "GO", 255, 255, 90)
        elif self.return_ready:
            label = "LND" if alt < 7 else "RET"
            draw_text_small(43, PLAY_HEIGHT, label, 120, 255, 120)
        else:
            diff = int(abs(abs(tangent) - target_speed) * 10)
            draw_text_small(46, PLAY_HEIGHT, "D" + str(min(9, diff)), 180, 180, 180)
            hold_w = int(17 * min(110, self.orbit_hold) / 110)
            draw_rectangle(25, PLAY_HEIGHT + 4, 42, PLAY_HEIGHT + 4, 28, 28, 28)
            if hold_w > 0:
                draw_rectangle(
                    25, PLAY_HEIGHT + 4, 24 + hold_w, PLAY_HEIGHT + 4, 80, 255, 120
                )

    def _draw(self, thrust_on, alt, target_speed, radial, tangent):
        display.clear()
        self._draw_orbit_band()
        self._draw_trail()
        self._draw_planet()
        self._draw_flight_cues()
        self._draw_ship(thrust_on)
        ok, _alt, _target, _radial, _tangent = self._orbit_quality()
        if ok:
            draw_text_small(25, 2, "ORB", 80, 255, 120)
        self._draw_hud(alt, target_speed, radial, tangent)
        display_flush()

    def _step(self, joystick):
        global game_over, global_score
        c_button, z_button = joystick.read_buttons()
        if c_button:
            return False
        d = joystick.read_direction(
            [JOYSTICK_LEFT, JOYSTICK_RIGHT, JOYSTICK_UP], debounce=False
        )
        if d == JOYSTICK_LEFT:
            self.angle = (self.angle + 4) % 360
        elif d == JOYSTICK_RIGHT:
            self.angle = (self.angle - 4) % 360
        thrust_on = (z_button or d == JOYSTICK_UP) and self.fuel > 0

        if self.prelaunch:
            if thrust_on:
                self.prelaunch = False
                self.launch_grace = 80
                self.vx = 0.08
                self.vy = -0.10
                self.trail = []
            else:
                ok, alt, target_speed, radial, tangent = self._orbit_quality()
                global_score = 0
                self._draw(False, alt, target_speed, radial, tangent)
                return True

        r = self._radius()
        gx = -self.MU * self.x / (r * r * r)
        gy = -self.MU * self.y / (r * r * r)
        ax = gx
        ay = gy
        if thrust_on:
            c, s = self._cos_sin(self.angle)
            ax += c * self.thrust
            ay += -s * self.thrust
            self.fuel -= 1
        if self.assist and self._surface_alt() < 5 and self.vy > 0:
            self.vy *= 0.995
        if self.assist and self.launch_grace > 0 and self._surface_alt() < 7:
            self.vy *= 0.970

        self.vx = clamp(self.vx + ax, -1.55, 1.55)
        self.vy = clamp(self.vy + ay, -1.55, 1.55)
        if self.assist and not self.return_ready:
            alt_now = self._surface_alt()
            if self.launch_grace > 0 or alt_now < 28:
                r = self._radius()
                ux = self.x / r
                uy = self.y / r
                radial = self.vx * ux + self.vy * uy
                cap = 0.72 if self.launch_grace > 0 else 0.95
                if radial > cap:
                    excess = radial - cap
                    self.vx -= excess * ux
                    self.vy -= excess * uy
        self.x += self.vx
        self.y += self.vy
        self.frame += 1
        if self.launch_grace > 0:
            self.launch_grace -= 1
        self._record_trail()

        ok, alt, target_speed, radial, tangent = self._orbit_quality()
        if ok:
            self.orbit_hold += 1
            self.score += 2
        else:
            self.orbit_hold = max(0, self.orbit_hold - 2)

        if self.orbit_hold >= 110:
            if self.mission == "orbit":
                set_game_over_score(self.score + int(self.fuel), won=True)
                return False
            self.return_ready = True

        if self._radius() <= self.PLANET_R + 1.0:
            speed = math.sqrt(self.vx * self.vx + self.vy * self.vy)
            upright = abs(((self.angle - 90 + 180) % 360) - 180) < 32
            if self.return_ready and speed < 0.75 and upright:
                set_game_over_score(self.score + int(self.fuel) + 500, won=True)
            elif self.launch_grace > 0:
                r = self._radius()
                ux = self.x / r
                uy = self.y / r
                self.x = ux * (self.PLANET_R + 1.4)
                self.y = uy * (self.PLANET_R + 1.4)
                inward = self.vx * ux + self.vy * uy
                if inward < 0:
                    self.vx -= inward * ux
                    self.vy -= inward * uy
                self.vx *= 0.72
                self.vy *= 0.72
                global_score = self.score
                self._draw(thrust_on, alt, target_speed, radial, tangent)
                return True
            else:
                set_game_over_score(self.score)
            return False

        if (
            self._radius() > 58
            or self.fuel <= 0
            and self._surface_alt() > 32
            and not ok
        ):
            set_game_over_score(self.score)
            return False

        global_score = self.score + int(max(0, alt))
        self._draw(thrust_on, alt, target_speed, radial, tangent)
        return True

    def _build_step(self, joystick):
        self.reset()
        begin_game(0)

        def step():
            return self._step(joystick)

        return step


class UFODefenseGame:
    """
    UFO DEFENSE / Missile Command Mini
    Steuerung:
      - Stick: Fadenkreuz bewegen
      - Z: Rakete starten
      - C: zurück ins Menü
    """

    FRAME_MS = 35
    TURRETS = (4, 32, 59)
    DIRS_8 = (
        JOYSTICK_UP,
        JOYSTICK_DOWN,
        JOYSTICK_LEFT,
        JOYSTICK_RIGHT,
        JOYSTICK_UP_LEFT,
        JOYSTICK_UP_RIGHT,
        JOYSTICK_DOWN_LEFT,
        JOYSTICK_DOWN_RIGHT,
    )

    def __init__(self, ctx=None):
        self.launcher_mode = get_context_setting(ctx, "launcher", "turrets")
        self.spawn_mode = get_context_setting(ctx, "spawns", "wave")
        self.blast_style = get_context_setting(ctx, "blast", "filled")
        self.chain_reactions = bool(get_context_setting(ctx, "chain", True))
        self.reset()

    def reset(self):
        self.score = 0

        self.base_x = WIDTH // 2
        self.base_y = PLAY_HEIGHT - 1

        self.cx = WIDTH // 2
        self.cy = PLAY_HEIGHT // 3

        self.player_missiles = []
        self.enemy_missiles = []
        self.explosions = []

        self.shot_cd = 0

        xs = [12, 19, 26, 38, 45, 52]
        self.cities = [{"x": x, "alive": True} for x in xs]

        self.spawn_ms = 850
        self.wave_spawn_ms = 950
        self.min_spawn_ms = 260
        self.last_spawn = ticks_ms()
        self.base_enemy_speed = 0.4
        self.max_enemy_speed = 2.0
        self.enemy_speed = self.base_enemy_speed
        self.level = 1
        self.to_spawn = 6
        self.frame = 0
        self.start_ms = ticks_ms()
        # crosshair movement smoothing: ms between pixel moves (tweakable)
        self.cross_move_ms = 28
        self._last_cross_move = ticks_ms()

    def _line(self, x0, y0, x1, y1, col):
        # Delegate to module-level Bresenham helper (shared with LunarLanderGame)
        r, g, b = col
        draw_line(x0, y0, x1, y1, r, g, b)

    def _cities_alive(self):
        for c in self.cities:
            if c["alive"]:
                return True
        return False

    def _damage_city_at(self, x):
        for c in self.cities:
            if c["alive"] and abs(c["x"] - x) <= 3:
                c["alive"] = False
                break

    def _enemy_targets(self):
        targets = [c["x"] for c in self.cities if c["alive"]]
        if self.launcher_mode == "base":
            targets.append(self.base_x)
        if not targets:
            targets = (
                [self.base_x] if self.launcher_mode == "base" else list(self.TURRETS)
            )
        return targets

    def _spawn_enemy(self):
        targets = self._enemy_targets()
        tgt = targets[random.randint(0, len(targets) - 1)]

        sx = random.randint(0, WIDTH - 1)
        sy = 0
        tx = tgt
        ty = self.base_y + 1

        dx = tx - sx
        dy = ty - sy
        if self.spawn_mode == "wave":
            spd = min(1.15, 0.30 + 0.09 * self.level)
            steps = max(1.0, self.base_y / spd)
            vx = dx / steps
            vy = spd
        else:
            dist = math.sqrt(dx * dx + dy * dy) + 1e-6
            spd = self.enemy_speed
            vx = dx / dist * spd
            vy = dy / dist * spd

        self.enemy_missiles.append(
            {
                "x": float(sx),
                "y": float(sy),
                "px": float(sx),
                "py": float(sy),
                "tx": float(tx),
                "ty": float(ty),
                "vx": vx,
                "vy": vy,
            }
        )

    def _enemy_cap(self, now):
        # time-based caps: 0-60s -> 2, 60-180s -> 4, 180-300s -> 6, afterwards 6
        elapsed = ticks_diff(now, getattr(self, "start_ms", now))
        if elapsed < 60_000:
            return 2
        if elapsed < 180_000:
            return 4
        return 6

    def _launcher_x(self):
        if self.launcher_mode != "turrets":
            return self.base_x
        bx = self.TURRETS[0]
        for t in self.TURRETS:
            if abs(t - self.cx) < abs(bx - self.cx):
                bx = t
        return bx

    def _fire_player(self):
        sx = self._launcher_x()
        sy = self.base_y
        tx = self.cx
        ty = self.cy

        dx = tx - sx
        dy = ty - sy
        dist = math.sqrt(dx * dx + dy * dy) + 1e-6
        spd = 3.2 if self.launcher_mode == "turrets" else 2.9
        vx = dx / dist * spd
        vy = dy / dist * spd

        self.player_missiles.append(
            {
                "x": float(sx),
                "y": float(sy),
                "px": float(sx),
                "py": float(sy),
                "tx": float(tx),
                "ty": float(ty),
                "vx": vx,
                "vy": vy,
            }
        )

    def _add_explosion(self, x, y, max_r, color):
        self.explosions.append(
            {"x": float(x), "y": float(y), "r": 0, "dr": 1, "max": max_r, "col": color}
        )

    def _draw_explosion(self, ex):
        r = ex["r"]
        if r <= 0:
            return
        x0 = ex["x"]
        y0 = ex["y"]
        col = ex["col"]
        sp = display.set_pixel
        if self.blast_style == "filled":
            ir = int(r)
            r2 = r * r
            icx = int(x0)
            icy = int(y0)
            for dy in range(-ir, ir + 1):
                yy = icy + dy
                if yy < 0 or yy >= PLAY_HEIGHT:
                    continue
                for dx in range(-ir, ir + 1):
                    if dx * dx + dy * dy <= r2:
                        xx = icx + dx
                        if 0 <= xx < WIDTH:
                            sp(xx, yy, col[0], col[1], col[2])
            return

        for deg in range(0, 360, 18):
            a = math.radians(deg)
            x = int(x0 + math.cos(a) * r)
            y = int(y0 + math.sin(a) * r)
            if 0 <= x < WIDTH and 0 <= y < PLAY_HEIGHT:
                sp(x, y, col[0], col[1], col[2])

    def _update_explosions_and_hits(self):
        active_explosions = []
        chain_explosions = []
        for ex in self.explosions:
            ex["r"] += ex["dr"]
            if ex["r"] >= ex["max"]:
                ex["dr"] = -1
            if ex["r"] <= 0 and ex["dr"] < 0:
                continue

            r2 = (ex["r"] + 1) * (ex["r"] + 1)
            exx = ex["x"]
            exy = ex["y"]

            keep_enemy = []
            for em in self.enemy_missiles:
                dx = em["x"] - exx
                dy = em["y"] - exy
                if dx * dx + dy * dy <= r2:
                    self.score += 10
                    if self.chain_reactions:
                        chain_explosions.append(
                            {
                                "x": float(em["x"]),
                                "y": float(em["y"]),
                                "r": 0,
                                "dr": 1,
                                "max": 5,
                                "col": (255, 110, 30),
                            }
                        )
                    continue
                keep_enemy.append(em)
            self.enemy_missiles = keep_enemy
            active_explosions.append(ex)
        self.explosions = active_explosions + chain_explosions

    def _update_missiles(self):
        global game_over, global_score

        # player
        keep_player = []
        for m in self.player_missiles:
            m["px"], m["py"] = m["x"], m["y"]
            m["x"] += m["vx"]
            m["y"] += m["vy"]
            dx = m["x"] - m["tx"]
            dy = m["y"] - m["ty"]
            if dx * dx + dy * dy <= 7.0:
                self._add_explosion(
                    m["tx"],
                    m["ty"],
                    7 if self.blast_style == "filled" else 6,
                    (255, 180, 0),
                )
                continue
            elif m["y"] < 0 or m["y"] >= PLAY_HEIGHT:
                continue
            keep_player.append(m)
        self.player_missiles = keep_player

        # enemy
        keep_enemy = []
        for m in self.enemy_missiles:
            m["px"], m["py"] = m["x"], m["y"]
            m["x"] += m["vx"]
            m["y"] += m["vy"]
            if m["y"] >= m["ty"] or m["y"] >= PLAY_HEIGHT - 1:
                ix = int(m["x"])
                iy = int(m["y"])
                self._add_explosion(ix, iy, 5, (255, 60, 60))

                if self.launcher_mode == "base" and abs(ix - self.base_x) <= 3:
                    global_score = self.score
                    game_over = True
                    return

                self._damage_city_at(ix)
                if not self._cities_alive():
                    global_score = self.score
                    game_over = True
                    return
            else:
                keep_enemy.append(m)
        self.enemy_missiles = keep_enemy

    def _advance_spawning(self, now):
        if self.spawn_mode == "wave":
            if (
                self.to_spawn > 0
                and ticks_diff(now, self.last_spawn) >= self.wave_spawn_ms
            ):
                self._spawn_enemy()
                self.to_spawn -= 1
                self.last_spawn = now
            elif self.to_spawn == 0 and not self.enemy_missiles:
                self.score += 35 * self.level
                self.level += 1
                self.to_spawn = 6 + self.level
                if self.wave_spawn_ms > 360:
                    self.wave_spawn_ms -= 60
            return

        if ticks_diff(now, self.last_spawn) >= self.spawn_ms:
            self.last_spawn = now
            cap = self._enemy_cap(now)
            if len(self.enemy_missiles) < cap:
                self._spawn_enemy()
            self.level += 1
            self.spawn_ms = max(self.min_spawn_ms, 850 - self.level * 10)
            self.enemy_speed = min(
                self.max_enemy_speed, self.base_enemy_speed + self.level * 0.01
            )

    def _move_crosshair(self, joystick, now):
        d = joystick.read_direction(self.DIRS_8, debounce=False)
        if not d or ticks_diff(now, self._last_cross_move) < self.cross_move_ms:
            return
        dx, dy = direction_to_delta_8way(d)
        if dx or dy:
            self.cx = clamp(self.cx + dx * 2, 1, WIDTH - 2)
            self.cy = clamp(self.cy + dy * 2, 2, PLAY_HEIGHT - 8)
            self._last_cross_move = now

    def _draw_world(self):
        display.clear()
        sp = display.set_pixel
        draw_rectangle(0, self.base_y, WIDTH - 1, self.base_y, 60, 40, 20)

        # cities
        city_y = PLAY_HEIGHT - 4
        for c in self.cities:
            if c["alive"]:
                x = c["x"]
                draw_rectangle(x - 1, city_y, x + 1, city_y + 1, 0, 255, 0)

        # base / turrets
        by = self.base_y
        if self.launcher_mode == "turrets":
            for t in self.TURRETS:
                draw_rectangle(t - 1, by - 1, t + 1, by, 120, 120, 140)
                if 0 <= t < WIDTH and 0 <= by - 2 < PLAY_HEIGHT:
                    sp(t, by - 2, 180, 180, 200)
        else:
            bx = self.base_x
            for dx in (-1, 0, 1):
                x = bx + dx
                if 0 <= x < WIDTH and 0 <= by < PLAY_HEIGHT:
                    sp(x, by, 120, 120, 255)
            if 0 <= bx < WIDTH and 0 <= (by - 1) < PLAY_HEIGHT:
                sp(bx, by - 1, 120, 120, 255)

        # crosshair
        x = self.cx
        y = self.cy
        for dx in (-2, -1, 0, 1, 2):
            xx = x + dx
            if 0 <= xx < WIDTH and 0 <= y < PLAY_HEIGHT:
                sp(xx, y, 255, 255, 255)
        for dy in (-2, -1, 0, 1, 2):
            yy = y + dy
            if 0 <= x < WIDTH and 0 <= yy < PLAY_HEIGHT:
                sp(x, yy, 255, 255, 255)

        # missiles
        for m in self.player_missiles:
            self._line(m["px"], m["py"], m["x"], m["y"], (255, 255, 255))
        for m in self.enemy_missiles:
            self._line(m["px"], m["py"], m["x"], m["y"], (255, 0, 0))

        # explosions
        for ex in self.explosions:
            self._draw_explosion(ex)

        draw_text_small(1, 1, "W" + str(self.level), 170, 170, 170)

        display_score_and_time(self.score)

    def main_loop(self, joystick):
        global game_over, global_score
        game_over = False
        global_score = 0

        self.reset()

        frame_ms = 35
        last_frame = ticks_ms()

        while not game_over:
            try:
                c_button, z_button = joystick.read_buttons()
                if c_button:
                    return

                now = ticks_ms()

                self._move_crosshair(joystick, now)

                # shoot
                if self.shot_cd > 0:
                    self.shot_cd -= 1
                if z_button and self.shot_cd == 0 and len(self.player_missiles) < 4:
                    self._fire_player()
                    self.shot_cd = 8

                self._advance_spawning(now)

                # frame pacing
                if ticks_diff(now, last_frame) < frame_ms:
                    sleep_ms(2)
                    continue
                last_frame = now
                self.frame += 1

                self._update_missiles()
                if game_over:
                    global_score = self.score
                    return

                self._update_explosions_and_hits()
                self._draw_world()
                global_score = self.score

                if self.frame % 45 == 0:
                    gc.collect()

            except RestartProgram:
                return

    async def main_loop_async(self, joystick):
        """Async version for pygbag/browser runtimes."""
        if asyncio is None:
            return self.main_loop(joystick)
        global game_over, global_score
        game_over = False
        global_score = 0
        self.reset()
        frame_ms = 35
        last_frame = ticks_ms()
        while not game_over:
            try:
                c_button, z_button = joystick.read_buttons()
                if c_button:
                    return
                now = ticks_ms()
                self._move_crosshair(joystick, now)
                if self.shot_cd > 0:
                    self.shot_cd -= 1
                if z_button and self.shot_cd == 0 and len(self.player_missiles) < 4:
                    self._fire_player()
                    self.shot_cd = 8
                self._advance_spawning(now)
                if ticks_diff(now, last_frame) < frame_ms:
                    await asyncio.sleep(0.002)
                    continue
                last_frame = now
                self.frame += 1
                self._update_missiles()
                if game_over:
                    global_score = self.score
                    return
                self._update_explosions_and_hits()
                self._draw_world()
                global_score = self.score
                if self.frame % 45 == 0:
                    try:
                        gc.collect()
                    except Exception:
                        pass
            except RestartProgram:
                return


# -----------------------------
# DOOM-LITE / RAYCASTER GAME
# -----------------------------
try:
    from array import array
except ImportError:
    array = None


class DoomLiteGame:
    """
    DOOM-LITE (extrem abgesteckt) = Wolf3D-Raycaster + Sprites

    Steuerung:
      - UP/DOWN: vor/zurück
      - LEFT/RIGHT: drehen
      - Diagonal: drehen+laufen
      - Z: schießen
      - C: zurück ins Menü

    Ziel:
      - Gegner erledigen, Wellen überleben (endlos)
    """

    # Playfield ohne Score-Leiste
    PLAY_H = HEIGHT - 6

    # Maps: 16x16; '#' wall, '.' floor, 'D' door, 'K' key, 'Q' quad, 'X' exit.
    MAP_W = 16
    MAP_H = 16
    MAPS = (
        (
            b"################",
            b"#.....K........#",
            b"#..####..####..#",
            b"#..####..####..#",
            b"#..####..####..#",
            b"#..####..####..#",
            b"#..####..####..#",
            b"#......D.......#",
            b"#..####..####..#",
            b"#..####..####..#",
            b"#..####..####..#",
            b"#..####..####..#",
            b"#..####..####..#",
            b"#.Q..........X.#",
            b"#....######....#",
            b"################",
        ),
        (
            b"################",
            b"#.....#........#",
            b"#.###.#.######.#",
            b"#.#...#......#.#",
            b"#.#.####.###.#.#",
            b"#.#......#...#.#",
            b"#.######.#.###.#",
            b"#........#.....#",
            b"#.####.#####.#.#",
            b"#....#.....#.#.#",
            b"####.#####.#.#.#",
            b"#....#.....#...#",
            b"#.##.#.#######.#",
            b"#....#.........#",
            b"#.###########..#",
            b"################",
        ),
        (
            b"################",
            b"#........#.....#",
            b"#.######.#.###.#",
            b"#.#......#...#.#",
            b"#.#.########.#.#",
            b"#.#..........#.#",
            b"#.####.#######.#",
            b"#......#.......#",
            b"#.######.#####.#",
            b"#.#......#.....#",
            b"#.#.####.#.###.#",
            b"#.#....#.#...#.#",
            b"#.####.#.###.#.#",
            b"#......#.....#.#",
            b"#..#########...#",
            b"################",
        ),
        (
            b"################",
            b"#..............#",
            b"#.####.##.####.#",
            b"#.#....##....#.#",
            b"#.#.##.##.##.#.#",
            b"#...##....##...#",
            b"###.########.###",
            b"#..............#",
            b"#.####....####.#",
            b"#....#.##.#....#",
            b"####.#.##.#.####",
            b"#....#....#....#",
            b"#.##.######.##.#",
            b"#..............#",
            b"#..##########..#",
            b"################",
        ),
        (
            b"################",
            b"#..............#",
            b"#.##.######.##.#",
            b"#.#..........#.#",
            b"#.#.###..###.#.#",
            b"#...#......#...#",
            b"###.#.####.#.###",
            b"#.....#..#.....#",
            b"#.###.#..#.###.#",
            b"#...#......#...#",
            b"#.#.########.#.#",
            b"#.#..........#.#",
            b"#.##.######.##.#",
            b"#..............#",
            b"#..##########..#",
            b"################",
        ),
        (
            b"################",
            b"#..............#",
            b"#.####....####.#",
            b"#....#.##.#....#",
            b"####.#.##.#.####",
            b"#....#....#....#",
            b"#.##.######.##.#",
            b"#.#..........#.#",
            b"#.#.###..###.#.#",
            b"#...#......#...#",
            b"###.#.####.#.###",
            b"#.....#..#.....#",
            b"#.###.#..#.###.#",
            b"#..............#",
            b"#..##########..#",
            b"################",
        ),
    )
    STARTS = ((2.5, 2.5), (1.5, 1.5), (2.5, 13.5), (1.5, 7.5), (1.5, 1.5), (1.5, 13.5))

    # Raycaster Parameter
    ANGLE_MAX = 256  # 0..255 entspricht 0..360°
    FOV = 48  # ~67.5° (48/256 * 360)
    HALF_FOV = FOV // 2
    MAX_STEPS = 36
    MAX_DIST = 32.0
    NOISE_RADIUS2 = 56.25  # 7.5 tiles squared
    SHOT_MIN_DIST2 = 0.01
    ENEMY_MIN_SHOOT_DIST2 = 0.25
    CONTACT_DAMAGE_DIST2 = 0.20
    ENEMY_SHOOT_RANGE2 = (49.0, 67.24, 88.36)
    QUAD_SPREAD = (-3, 0, 3)
    INPUT_DIRECTIONS = (
        JOYSTICK_UP,
        JOYSTICK_DOWN,
        JOYSTICK_LEFT,
        JOYSTICK_RIGHT,
        JOYSTICK_UP_LEFT,
        JOYSTICK_UP_RIGHT,
        JOYSTICK_DOWN_LEFT,
        JOYSTICK_DOWN_RIGHT,
    )

    # These thresholds are stored as squared distances because the hot paths
    # only compare ranges. Keeping them squared avoids sqrt on every enemy.
    # Avoid the Quake fast inverse square root trick here. On CPython/Pygame,
    # MicroPython, and pygbag, Python-level float bit hacks are usually slower
    # and less portable than C/VM math. The faster cross-target win is to keep
    # distances squared and avoid sqrt entirely until projection needs it.

    # LUT für sin/cos (256 Steps, Scale 1024)
    # Lazy init to avoid large import-time allocations on MicroPython.
    _COS = None
    _SIN = None

    @classmethod
    def _ensure_trig(cls):
        if cls._COS is not None and cls._SIN is not None:
            return
        try:
            gc.collect()
        except Exception:
            pass

        if CONFIG_LOW_RAM_MODE and array:
            cos_lut = array("h")
            sin_lut = array("h")
            for i in range(256):
                ang = 2 * math.pi * i / 256
                cos_lut.append(int(math.cos(ang) * 1024))
                sin_lut.append(int(math.sin(ang) * 1024))
            cls._COS = cos_lut
            cls._SIN = sin_lut
        elif array:
            cos_lut = array("f")
            sin_lut = array("f")
            for i in range(256):
                ang = 2 * math.pi * i / 256
                cos_lut.append(math.cos(ang))
                sin_lut.append(math.sin(ang))
            cls._COS = cos_lut
            cls._SIN = sin_lut
        else:
            cos_lut = []
            sin_lut = []
            for i in range(256):
                ang = 2 * math.pi * i / 256
                if CONFIG_LOW_RAM_MODE:
                    cos_lut.append(int(math.cos(ang) * 1024))
                    sin_lut.append(int(math.sin(ang) * 1024))
                else:
                    cos_lut.append(math.cos(ang))
                    sin_lut.append(math.sin(ang))
            cls._COS = cos_lut
            cls._SIN = sin_lut

    def __init__(self):
        self._ensure_trig()
        self.zbuf = [self.MAX_DIST] * WIDTH  # Wanddistanz pro Screen-Spalte
        self.MAP = self.MAPS[0]
        self.level = 1
        self._minimap_walls = []
        self._minimap_initialized = False
        self._minimap_prev_player = None
        self._minimap_prev_aim = None
        self._minimap_prev_enemies = []
        self.lamps = []
        self.closed_doors = set()
        self.key_pos = None
        self.key_taken = False
        self.quad_pos = None
        self.quad_taken = False
        self.exit_pos = None
        self.render_hud = True
        self.render_minimap = True
        self.render_crosshair = True
        self.render_enemies = True
        self._attract_dir = 0
        self._attract_target_ang = 0
        self.reset()

    def reset(self):
        self.level = 1
        self._set_level(self.level)
        # Player (Map-Koordinaten, 1 Tile = 1.0)
        self.px, self.py = self.STARTS[0]
        self.ang = 0  # 0 = nach rechts

        self.score = 0
        self.lives = 3
        self.wave = 1

        self.shot_cd = 0
        self.muzzle_flash = 0
        self.weapon_recoil = 0
        self.bob_phase = 0
        self.quad_timer = 0
        self.wave_announce = 0  # frames left to show wave banner
        self.hit_flash = 0  # frames left to flash crosshair on hit
        self.dmg_flash = 0  # frames left to flash screen red when damaged
        self.key_flash = 0
        self.weapon_heat = 0

        # Keep the physical matrix and browser renderer coarse, but use native
        # columns for the desktop emulator where drawing a full 64-pixel view
        # is inexpensive and wall detail is more legible.
        self.render_stride = 1 if IS_DESKTOP else 2

        self.enemies = []
        self._spawn_wave(self.wave)

        self.last_frame = ticks_ms()
        self.frame_ms = (
            45 if CONFIG_LOW_RAM_MODE else CONFIG_FRAME_MS_DEFAULT
        )  # ~22-28 fps
        self.frame = 0

    # --- helpers ---
    def _set_level(self, level):
        self.level = level
        idx = (level - 1) % len(self.MAPS)
        self.MAP = self.MAPS[idx]
        self._minimap_walls = [
            (mx, my)
            for my in range(self.MAP_H)
            for mx in range(self.MAP_W)
            if self.MAP[my][mx] == 35
        ]
        self._minimap_initialized = False
        self._minimap_prev_player = None
        self._minimap_prev_aim = None
        self._minimap_prev_enemies = []
        self.closed_doors = set()
        self.key_pos = None
        self.key_taken = False
        self.quad_pos = None
        self.quad_taken = False
        self.exit_pos = None
        fallback_open = []
        start = self._player_start_for_level()
        best_key = None
        best_exit = None
        best_key_score = 999999
        best_exit_score = -1
        for my in range(1, self.MAP_H - 1):
            for mx in range(1, self.MAP_W - 1):
                ch = self.MAP[my][mx]
                if ch == 35:
                    continue
                fallback_open.append((mx, my))
                dist_score = abs(mx + 0.5 - start[0]) + abs(my + 0.5 - start[1])
                if dist_score < best_key_score and dist_score >= 3:
                    best_key = (mx, my)
                    best_key_score = dist_score
                if dist_score > best_exit_score:
                    best_exit = (mx, my)
                    best_exit_score = dist_score
                if ch == 68:  # 'D'
                    self.closed_doors.add((mx, my))
                elif ch == 75:  # 'K'
                    self.key_pos = (mx, my)
                elif ch == 81:  # 'Q'
                    self.quad_pos = (mx, my)
                elif ch == 88:  # 'X'
                    self.exit_pos = (mx, my)
        if self.key_pos is None:
            self.key_pos = best_key
        if self.exit_pos is None:
            self.exit_pos = best_exit
        if self.quad_pos is None and fallback_open:
            qstart = (idx * 11 + len(fallback_open) // 3) % len(fallback_open)
            for n in range(len(fallback_open)):
                qx, qy = fallback_open[(qstart + n) % len(fallback_open)]
                if (
                    (qx, qy) != self.key_pos
                    and (qx, qy) != self.exit_pos
                    and (qx, qy) not in self.closed_doors
                ):
                    self.quad_pos = (qx, qy)
                    break
        if not self.closed_doors and fallback_open:
            dx, dy = fallback_open[
                (idx * 7 + len(fallback_open) // 2) % len(fallback_open)
            ]
            if (dx, dy) != self.key_pos and (dx, dy) != self.exit_pos:
                self.closed_doors.add((dx, dy))
        self.lamps = self._make_lamps(idx)

    def _make_lamps(self, map_idx):
        lamps = []
        # Deterministic lamp placement per level: open cells near corridor bends
        # get most of the lights, with a fallback so every map has visible pools.
        for my in range(1, self.MAP_H - 1):
            for mx in range(1, self.MAP_W - 1):
                if self.MAP[my][mx] == 35:
                    continue
                wall_near = (
                    self.MAP[my - 1][mx] == 35
                    or self.MAP[my + 1][mx] == 35
                    or self.MAP[my][mx - 1] == 35
                    or self.MAP[my][mx + 1] == 35
                )
                if wall_near and ((mx * 7 + my * 11 + map_idx * 5) % 19) == 0:
                    lamps.append((mx + 0.5, my + 0.5, 150))
                    if len(lamps) >= 5:
                        return lamps
        for my in (2, 5, 8, 12):
            for mx in (2, 6, 10, 13):
                if len(lamps) >= 5:
                    return lamps
                if self.MAP[my][mx] != 35:
                    lamps.append((mx + 0.5, my + 0.5, 135))
        return lamps

    def _restore_minimap_cell(self, mx, my):
        if 0 <= mx < self.MAP_W and 0 <= my < self.MAP_H:
            if self.MAP[my][mx] == 35:
                display.set_pixel(mx, my, 0, 0, 160)
            elif (mx, my) in self.closed_doors:
                display.set_pixel(mx, my, 190, 120, 20)
            elif self.key_pos == (mx, my) and not self.key_taken:
                display.set_pixel(mx, my, 255, 230, 40)
            elif (
                self.quad_pos == (mx, my)
                and not self.quad_taken
                and self.quad_timer <= 0
            ):
                display.set_pixel(mx, my, 150, 70, 255)
            elif self.exit_pos == (mx, my):
                display.set_pixel(mx, my, 0, 180, 90 if self.key_taken else 40)
            else:
                display.set_pixel(mx, my, 0, 0, 0)

    def _player_start_for_level(self):
        return self.STARTS[(self.level - 1) % len(self.STARTS)]

    def _is_wall_tile(self, mx, my):
        if mx < 0 or mx >= self.MAP_W or my < 0 or my >= self.MAP_H:
            return True
        return self.MAP[my][mx] == 35 or (mx, my) in self.closed_doors

    def _is_wall_pos(self, x, y):
        return self._is_wall_tile(int(x), int(y))

    def configure_attract_maze(self):
        self.enemies = []
        self.lives = 0
        self.score = 0
        self.wave_announce = 0
        self.hit_flash = 0
        self.dmg_flash = 0
        self.render_hud = False
        self.render_minimap = False
        self.render_crosshair = False
        self.render_enemies = False
        self.level = random.randint(1, len(self.MAPS))
        self._set_level(self.level)
        self.px, self.py = self._player_start_for_level()
        self._attract_dir = random.randint(0, 3)
        self._attract_target_ang = (self._attract_dir * 64) & 255
        self.ang = self._attract_target_ang

    def _attract_open_dir(self, d):
        dir_dx = (1, 0, -1, 0)
        dir_dy = (0, -1, 0, 1)
        mx = int(self.px) + dir_dx[d]
        my = int(self.py) + dir_dy[d]
        return not self._is_wall_tile(mx, my)

    def _choose_attract_dir(self):
        cur = self._attract_dir
        left = (cur + 1) & 3
        right = (cur - 1) & 3
        back = (cur + 2) & 3
        side_choices = []
        if self._attract_open_dir(left):
            side_choices.append(left)
        if self._attract_open_dir(right):
            side_choices.append(right)
        if not self._attract_open_dir(cur):
            if side_choices:
                return side_choices[random.randint(0, len(side_choices) - 1)]
            if self._attract_open_dir(back):
                return back
            return cur
        if side_choices and random.randint(0, 99) < 28:
            return side_choices[random.randint(0, len(side_choices) - 1)]
        return cur

    def step_attract_maze(self, frame=0):
        dir_dx = (1, 0, -1, 0)
        dir_dy = (0, -1, 0, 1)
        centered = (
            abs(self.px - (int(self.px) + 0.5)) < 0.045
            and abs(self.py - (int(self.py) + 0.5)) < 0.045
        )
        if centered:
            self.px = int(self.px) + 0.5
            self.py = int(self.py) + 0.5
            self._attract_dir = self._choose_attract_dir()
            self._attract_target_ang = (self._attract_dir * 64) & 255

        delta = ((self._attract_target_ang - self.ang + 128) & 255) - 128
        if delta:
            step_ang = 8
            if abs(delta) <= step_ang:
                self.ang = self._attract_target_ang
            elif delta > 0:
                self.ang = (self.ang + step_ang) & 255
            else:
                self.ang = (self.ang - step_ang) & 255
        else:
            step = 0.080
            nx = self.px + dir_dx[self._attract_dir] * step
            ny = self.py + dir_dy[self._attract_dir] * step
            if self._is_wall_pos(nx, ny):
                self.px = int(self.px) + 0.5
                self.py = int(self.py) + 0.5
                self._attract_dir = self._choose_attract_dir()
                self._attract_target_ang = (self._attract_dir * 64) & 255
            else:
                self.px = nx
                self.py = ny

        if (frame & 511) == 0:
            self.level = (self.level % len(self.MAPS)) + 1
            self._set_level(self.level)
            self.px, self.py = self._player_start_for_level()
            self._attract_dir = random.randint(0, 3)
            self._attract_target_ang = (self._attract_dir * 64) & 255
            self.ang = self._attract_target_ang
        self._render()

    def _is_enemy_clear_pos(self, x, y):
        # Keep enemies visually away from walls so sprites do not scrape along
        # columns and corners. The margin is small enough for one-tile corridors.
        if self._is_wall_pos(x, y):
            return False
        margin = 0.20
        return (
            not self._is_wall_pos(x - margin, y)
            and not self._is_wall_pos(x + margin, y)
            and not self._is_wall_pos(x, y - margin)
            and not self._is_wall_pos(x, y + margin)
        )

    def _front_tile(self, reach=1.05):
        c, s = self._cos_sin(self.ang)
        return int(self.px + c * reach), int(self.py - s * reach)

    def _try_use_door(self):
        # Check a few distances so the player can open doors without exact pixel
        # alignment at corridor junctions.
        for reach in (0.55, 0.85, 1.15):
            tx, ty = self._front_tile(reach)
            if (tx, ty) in self.closed_doors:
                self.closed_doors.remove((tx, ty))
                self.score += 10
                self._minimap_initialized = False
                return True
        return False

    def _update_pickups_and_exit(self):
        if self.key_pos is not None and not self.key_taken:
            kx, ky = self.key_pos
            if int(self.px) == kx and int(self.py) == ky:
                self.key_taken = True
                self.key_flash = 45
                self.score += 100
                self._minimap_initialized = False
        if self.quad_pos is not None and not self.quad_taken and self.quad_timer <= 0:
            qx, qy = self.quad_pos
            if int(self.px) == qx and int(self.py) == qy:
                self.quad_taken = True
                self.quad_timer = 420
                self.hit_flash = 12
                self.score += 125
                self._minimap_initialized = False
        if self.exit_pos is not None:
            ex, ey = self.exit_pos
            if int(self.px) == ex and int(self.py) == ey:
                if self.key_taken:
                    self.score += 250 + self.lives * 50
                    self.wave += 1
                    self._set_level(self.level + 1)
                    self._spawn_wave(self.wave)
                    self.px, self.py = self._player_start_for_level()
                    self.ang = 0
                    return True
                self.key_flash = 20
        return False

    def _draw_world_marker(self, sp, wx, wy, kind, zbuf):
        dx = wx - self.px
        dy = wy - self.py
        d2 = dx * dx + dy * dy
        if d2 < 0.0225:
            return
        a = self._angle_to_units(dx, dy)
        delta = self._angle_delta(a, self.ang)
        if abs(delta) > self.HALF_FOV:
            return
        sx = int((self.HALF_FOV - delta) * WIDTH / self.FOV)
        dist = math.sqrt(d2)
        if sx < 0 or sx >= WIDTH or dist >= zbuf[sx] - 0.15:
            return
        size = int(self.PLAY_H / (dist * 4.0 + 1.0))
        if size < 2:
            size = 2
        if size > 7:
            size = 7
        y = self.PLAY_H // 2 + size
        if kind == "key":
            draw_rectangle(sx - 1, y - size, sx + 1, y - size + 1, 255, 230, 40)
            set_pixel_clipped(sx + 2, y - size + 1, 255, 180, 30)
            set_pixel_clipped(sx + 3, y - size + 1, 255, 180, 30)
        elif kind == "quad":
            q = size if size > 2 else 2
            draw_rectangle(sx - 1, y - q, sx + 1, y - q + 2, 120, 70, 255)
            set_pixel_clipped(sx, y - q - 1, 210, 160, 255)
            set_pixel_clipped(sx - 2, y - q + 1, 80, 170, 255)
            set_pixel_clipped(sx + 2, y - q + 1, 80, 170, 255)
        else:
            col = (60, 255, 140) if self.key_taken else (40, 110, 70)
            draw_rect_outline(sx - size, y - size * 2, sx + size, y, *col)
            set_pixel_clipped(sx, y - size, 200, 255, 220 if self.key_taken else 90)

    def _cos_sin(self, a):
        a &= 255
        c = self._COS[a]
        s = self._SIN[a]
        if CONFIG_LOW_RAM_MODE:
            return c / 1024.0, s / 1024.0
        return c, s

    def _angle_to_units(self, dx, dy):
        # dx,dy in Map-Koordinaten; Achtung y-Achse ist "nach unten"
        ang = math.atan2(-dy, dx)  # -dy -> mathematisch korrekt
        if ang < 0:
            ang += 2 * math.pi
        return int(ang * 256 / (2 * math.pi)) & 255

    def _angle_delta(self, a, b):
        # kleinste Differenz a-b in [-128..127]
        d = (a - b + 128) & 255
        return d - 128

    def _cast_ray(self, ray_ang):
        """
        DDA Raycast: liefert (dist, side)
        side: 0 = x-seite (vertikale Wand), 1 = y-seite (horizontale Wand)
        """
        # Hoist to locals – attribute lookups are expensive in MicroPython.
        COS = self._COS
        SIN = self._SIN
        MAP = self.MAP
        MAP_W = self.MAP_W
        MAP_H = self.MAP_H
        MAX_DIST = self.MAX_DIST
        closed_doors = self.closed_doors
        px = self.px
        py = self.py

        # Inline trig lookup. Low-RAM mode stores int16 values scaled by 1024.
        a = ray_ang & 255
        ray_dx = COS[a]
        ray_dy = -SIN[a]  # y nach unten
        if CONFIG_LOW_RAM_MODE:
            ray_dx = ray_dx / 1024.0
            ray_dy = ray_dy / 1024.0

        # avoid division by 0
        if ray_dx == 0:
            ray_dx = 1e-6
        if ray_dy == 0:
            ray_dy = 1e-6

        map_x = int(px)
        map_y = int(py)

        delta_x = abs(1.0 / ray_dx)
        delta_y = abs(1.0 / ray_dy)

        if ray_dx < 0:
            step_x = -1
            side_x = (px - map_x) * delta_x
        else:
            step_x = 1
            side_x = (map_x + 1.0 - px) * delta_x

        if ray_dy < 0:
            step_y = -1
            side_y = (py - map_y) * delta_y
        else:
            step_y = 1
            side_y = (map_y + 1.0 - py) * delta_y

        side = 0
        for _ in range(self.MAX_STEPS):
            if side_x < side_y:
                side_x += delta_x
                map_x += step_x
                side = 0
            else:
                side_y += delta_y
                map_y += step_y
                side = 1

            # Inline _is_wall_tile to avoid per-step method call overhead.
            if (
                map_x < 0
                or map_x >= MAP_W
                or map_y < 0
                or map_y >= MAP_H
                or MAP[map_y][map_x] == 35
                or (map_x, map_y) in closed_doors
            ):
                if side == 0:
                    dist = side_x - delta_x
                else:
                    dist = side_y - delta_y
                if dist < 0.05:
                    dist = 0.05
                if dist > MAX_DIST:
                    dist = MAX_DIST
                return dist, side

        return MAX_DIST, side

    def _spawn_wave(self, wave):
        self._set_level(wave)
        # sehr klein halten: 2..6 Gegner
        n = 2 + (wave // 2)
        if n > 7:
            n = 7
        self.enemies = []

        # Precompute all valid spawn points
        valid_spawns = []
        sx, sy = self._player_start_for_level()
        for x in range(1, self.MAP_W - 1):
            for y in range(1, self.MAP_H - 1):
                if not self._is_wall_tile(x, y):
                    # nicht direkt am Start
                    if abs(x + 0.5 - sx) + abs(
                        y + 0.5 - sy
                    ) >= 4 and self._is_enemy_clear_pos(x + 0.5, y + 0.5):
                        valid_spawns.append((x + 0.5, y + 0.5))

        # Shuffle or random choice valid spawns
        for _ in range(n):
            if not valid_spawns:
                break
            spawn = random.choice(valid_spawns)
            valid_spawns.remove(spawn)

            if wave >= 7 and random.randint(0, 99) < 25:
                typ = 2
            elif wave >= 3 and random.randint(0, 99) < 45:
                typ = 1
            else:
                typ = 0

            hp = 1 + typ
            if wave >= 8 and typ > 0:
                hp += 1
            # x, y, hp, cooldown, type, animation phase, alert x/y/timer,
            # strafe direction, muzzle flash. The final two fields give ranged
            # enemies distinct behavior without a separate object allocation.
            self.enemies.append(
                [
                    spawn[0],
                    spawn[1],
                    hp,
                    random.randint(20, 90),
                    typ,
                    random.randint(0, 31),
                    0.0,
                    0.0,
                    0,
                    -1 if random.randint(0, 1) else 1,
                    0,
                ]
            )

        self.wave_announce = 60  # show wave banner for ~2 s

    def _alert_enemies_to_noise(self, wx, wy):
        radius2 = self.NOISE_RADIUS2
        for e in self.enemies:
            # Older save/attract states may still have the pre-alert enemy shape.
            while len(e) < 11:
                e.append(0)
            if e[2] <= 0:
                continue
            dx = wx - e[0]
            dy = wy - e[1]
            d2 = dx * dx + dy * dy
            if d2 <= radius2:
                # Store the noise source, not the current player reference. That
                # makes enemies investigate where the shot happened.
                e[6] = wx
                e[7] = wy
                e[8] = 90 + int((radius2 - d2) * 0.8)

    def _shoot(self):
        """Fire a hitscan burst and return the number of enemies hit."""
        if self._try_use_door():
            self.weapon_recoil = 2
            return 0

        quad_active = self.quad_timer > 0
        shot_angles = self.QUAD_SPREAD if quad_active else (0,)
        damage = 2 if quad_active else 1
        aim_tolerance = 3 if quad_active else 4
        hit_indices = []
        hits = 0

        self.muzzle_flash = 8 if quad_active else 6
        self.weapon_recoil = 6 if quad_active else 5
        self.weapon_heat = min(12, self.weapon_heat + 3)
        play_sound("zap", self.wave)
        self._alert_enemies_to_noise(self.px, self.py)

        for angle_offset in shot_angles:
            shot_ang = (self.ang + angle_offset) & 255
            wall_dist, _ = self._cast_ray(shot_ang)
            wall_limit = wall_dist + 0.2
            wall_limit2 = wall_limit * wall_limit
            best_i = -1
            best_d2 = 999.0

            for i, enemy in enumerate(self.enemies):
                if i in hit_indices or enemy[2] <= 0:
                    continue
                dx = enemy[0] - self.px
                dy = enemy[1] - self.py
                dist2 = dx * dx + dy * dy
                if dist2 <= self.SHOT_MIN_DIST2 or dist2 >= wall_limit2:
                    continue
                enemy_ang = self._angle_to_units(dx, dy)
                if abs(self._angle_delta(enemy_ang, shot_ang)) > aim_tolerance:
                    continue
                if dist2 < best_d2:
                    best_d2 = dist2
                    best_i = i

            if best_i < 0:
                continue

            hit_indices.append(best_i)
            enemy = self.enemies[best_i]
            enemy[2] -= damage
            self.hit_flash = 10
            hits += 1
            typ = enemy[4] if len(enemy) > 4 else 0
            if enemy[2] <= 0:
                self.score += 50 + typ * 25 + (25 if quad_active else 0)
            else:
                self.score += 15 + (10 if quad_active else 0)

        return hits

    def _update_enemies(self):
        global game_over, global_score

        # Enemies bewegen sich selten (Performance + Doom-Feeling)
        if (self.frame & 1) == 1:
            return

        for enemy_index, e in enumerate(self.enemies):
            if len(e) < 4:
                e.append(0)  # upgrade legacy states to support cooldowns
            while len(e) < 11:
                e.append(0)

            if e[2] <= 0:
                continue

            dx = self.px - e[0]
            dy = self.py - e[1]
            dist2 = dx * dx + dy * dy

            # Contact damage uses squared distance like the rest of the AI.
            if dist2 < self.CONTACT_DAMAGE_DIST2:
                self.lives -= 1
                self.dmg_flash = 12
                if self.lives <= 0:
                    global_score = self.score
                    game_over = True
                    return
                # Respawn player
                self.px, self.py = self._player_start_for_level()
                return

            typ = e[4]
            e[5] = (e[5] + 1) & 31
            if e[10] > 0:
                e[10] -= 1

            # Enemies might shoot back occasionally if wave > 2
            should_check_los = ((self.frame + enemy_index) & 3) == 0
            if self.wave > 2 and e[3] <= 0 and should_check_los:
                # First do cheap squared range checks. Only visible candidates
                # pay for sqrt, because the ray result is a true distance.
                if (
                    dist2 > self.ENEMY_MIN_SHOOT_DIST2
                    and dist2 < self.ENEMY_SHOOT_RANGE2[typ]
                ):
                    dist = math.sqrt(dist2)
                    a = self._angle_to_units(dx, dy)
                    ray_dist, _ = self._cast_ray(a)
                    if ray_dist > dist - 0.2:
                        # Player visible! Bam.
                        self.lives -= 1
                        self.hit_flash = 10
                        self.dmg_flash = 12
                        if self.lives <= 0:
                            global_score = self.score
                            game_over = True
                            return
                        self.px, self.py = self._player_start_for_level()
                        e[10] = 5
                        # Reload enemy weapon
                        e[3] = random.randint(90, 210) - typ * 15
                        if e[3] < 55:
                            e[3] = 55
                        return
                    else:
                        e[3] = 30  # retry sooner if blocked
            elif e[3] > 0:
                e[3] -= 1

            # Move toward the last nearby shot noise first, then resume chasing.
            move_dx = dx
            move_dy = dy
            if e[8] > 0:
                e[8] -= 1
                alert_dx = e[6] - e[0]
                alert_dy = e[7] - e[1]
                # Stop using the alert once the enemy reaches roughly the tile
                # where the shot was fired.
                if alert_dx * alert_dx + alert_dy * alert_dy > 0.18:
                    move_dx = alert_dx
                    move_dy = alert_dy
                else:
                    e[8] = 0

            # Archetypes: basic enemies stalk, orange enemies strafe while
            # shooting, and purple enemies close distance more aggressively.
            step = 0.05 + (self.wave * 0.002) + typ * 0.006
            if typ == 2:
                step += 0.014
            if step > 0.09:
                step = 0.09

            strafe = typ == 1 and dist2 < 28.0 and e[8] <= 0
            if strafe:
                strafe_dir = e[9] if e[9] else 1
                move_dx, move_dy = -dy * strafe_dir, dx * strafe_dir

            # axis-priority move
            if abs(move_dx) > abs(move_dy):
                sx = step if move_dx > 0 else -step
                nx = e[0] + sx
                if self._is_enemy_clear_pos(nx, e[1]):
                    e[0] = nx
                else:
                    if strafe:
                        e[9] = -strafe_dir
                    sy = step if move_dy > 0 else -step
                    ny = e[1] + sy
                    if self._is_enemy_clear_pos(e[0], ny):
                        e[1] = ny
            else:
                sy = step if move_dy > 0 else -step
                ny = e[1] + sy
                if self._is_enemy_clear_pos(e[0], ny):
                    e[1] = ny
                else:
                    if strafe:
                        e[9] = -strafe_dir
                    sx = step if move_dx > 0 else -step
                    nx = e[0] + sx
                    if self._is_enemy_clear_pos(nx, e[1]):
                        e[0] = nx

    def _enemy_palette(self, typ, hp):
        if typ == 2:
            return (150, 35, 255, 255, 140, 40)
        if typ == 1:
            return (255, 120, 20, 255, 220, 40)
        if hp > 1:
            return (255, 45, 180, 255, 220, 40)
        return (230, 35, 35, 255, 230, 40)

    def _draw_enemy_sprite(
        self, sp, x0, x1, y0, y1, dist, zbuf, typ, hp, anim, light=255, firing=0
    ):
        body_r, body_g, body_b, eye_r, eye_g, eye_b = self._enemy_palette(typ, hp)
        h = y1 - y0 + 1
        w = x1 - x0 + 1
        if h <= 0 or w <= 0:
            return

        for xx in range(x0, x1 + 1):
            if xx < 0 or xx >= WIDTH or dist >= zbuf[xx]:
                continue
            rel_x = xx - x0
            center = (w - 1) // 2
            for yy in range(y0, y1 + 1):
                if yy < 0 or yy >= self.PLAY_H:
                    continue
                rel_y = yy - y0

                # Width profile: small horn/head, wider torso, separated legs.
                if rel_y < h // 7:
                    half = 0 if typ == 0 else 1
                    horn = typ > 0 and (rel_x == center - 1 or rel_x == center + 1)
                    if not horn and abs(rel_x - center) > half:
                        continue
                    rr, gg, bb = body_r // 2, body_g // 2, body_b // 2
                elif rel_y < h // 3:
                    half = max(1, w // 4)
                    if abs(rel_x - center) > half:
                        continue
                    eye_row = y0 + h // 4
                    eye_col = abs(rel_x - center) == 1 or w <= 2
                    if yy == eye_row and eye_col:
                        rr, gg, bb = eye_r, eye_g, eye_b
                    else:
                        rr, gg, bb = body_r, body_g // 2, body_b // 2
                elif rel_y < (h * 3) // 4:
                    half = max(1, w // 2 - 1)
                    if abs(rel_x - center) > half:
                        continue
                    edge = abs(rel_x - center) == half
                    if edge:
                        rr, gg, bb = body_r // 3, body_g // 3, body_b // 3
                    else:
                        rr, gg, bb = body_r, body_g, body_b
                else:
                    stride = (anim >> 3) & 1
                    leg_left = center - 1 - stride
                    leg_right = center + 1 + stride
                    if rel_x != leg_left and rel_x != leg_right:
                        continue
                    rr, gg, bb = body_r // 2, body_g // 2, body_b // 2

                if firing and rel_y == h // 2 and rel_x == center:
                    rr, gg, bb = 255, 235, 90

                if light < 255:
                    rr = (rr * light) // 255
                    gg = (gg * light) // 255
                    bb = (bb * light) // 255
                sp(xx, yy, rr, gg, bb)

    def _draw_weapon(self, sp):
        bob = 1 if (self.bob_phase & 8) else 0
        recoil = self.weapon_recoil if self.weapon_recoil < 4 else 4
        cx = WIDTH // 2
        base_y = self.PLAY_H - 8 + bob + recoil
        if base_y > self.PLAY_H - 6:
            base_y = self.PLAY_H - 6

        # Low-pixel weapon silhouette: center barrel, side grip, and muzzle flash.
        draw_rectangle(cx - 7, base_y + 5, cx - 4, self.PLAY_H - 1, 55, 42, 38)
        draw_rectangle(cx + 4, base_y + 5, cx + 7, self.PLAY_H - 1, 55, 42, 38)
        draw_rectangle(cx - 4, base_y + 3, cx + 4, self.PLAY_H - 1, 42, 42, 50)
        draw_rectangle(cx - 2, base_y, cx + 2, base_y + 5, 115, 115, 125)
        set_pixel_clipped(cx - 1, base_y - 1, 170, 170, 180)
        set_pixel_clipped(cx, base_y - 2, 190, 190, 200)
        set_pixel_clipped(cx + 1, base_y - 1, 170, 170, 180)
        if self.weapon_heat > 0:
            heat = min(255, 80 + self.weapon_heat * 14)
            set_pixel_clipped(cx - 1, base_y + 1, heat, heat // 3, 20)
            set_pixel_clipped(cx, base_y, 255, heat, 30)
            set_pixel_clipped(cx + 1, base_y + 1, heat, heat // 3, 20)
        if self.quad_timer > 0:
            set_pixel_clipped(cx - 3, base_y + 2, 120, 70, 255)
            set_pixel_clipped(cx + 3, base_y + 2, 120, 70, 255)
        if self.muzzle_flash > 0:
            flash_y = base_y - 4
            set_pixel_clipped(cx, flash_y, 255, 255, 120)
            set_pixel_clipped(cx - 1, flash_y + 1, 255, 150, 40)
            set_pixel_clipped(cx + 1, flash_y + 1, 255, 150, 40)
            set_pixel_clipped(cx, flash_y + 2, 255, 90, 20)

    def _render(self):
        # Hoist frequently-accessed attributes to locals once.
        # On MicroPython each 'self.X' lookup costs a dictionary probe;
        # reading a local is a single LOAD_FAST bytecode.
        sp = display.set_pixel
        PLAY_H = self.PLAY_H
        zbuf = self.zbuf
        COS = self._COS
        SIN = self._SIN
        low_ram_trig = CONFIG_LOW_RAM_MODE
        px = self.px
        py = self.py
        lamps = self.lamps
        muzzle_flash = self.muzzle_flash
        lamp_phase = self.frame >> 2
        dmg_flash = self.dmg_flash
        theme = (self.wave - 1) % 4

        # We combine sky, wall, and floor rendering in one pass per column
        # to prevent overwriting pixels multiple times. This dramatically
        # reduces the dirty-pixel mask modifications and saves CPU time.
        minimap_w = self.MAP_W + 2 if self.render_minimap else 0
        minimap_h = self.MAP_H + 2 if self.render_minimap else 0

        # Ray stride is target-aware: desktop renders native 64 columns while
        # browser and matrix targets retain paired columns for stable timing.
        col_step = self.render_stride
        draw_pair = col_step == 2
        angle_step_fp = (self.FOV << 16) // WIDTH
        # Positive angle points upward in map coordinates, so screen-left is
        # ang + HALF_FOV and screen-right is ang - HALF_FOV.
        ang_fp = ((self.ang + self.HALF_FOV) & 255) << 16

        for x in range(0, WIDTH, col_step):
            ray_ang = (ang_fp >> 16) & 255
            ang_fp -= angle_step_fp * col_step

            dist, side = self._cast_ray(ray_ang)
            zbuf[x] = dist
            # The renderer draws two screen columns per ray. Mirror the depth so
            # sprite clipping still works at native screen-column granularity.
            x2 = x + 1 if draw_pair else x
            if draw_pair:
                zbuf[x2] = dist

            ray_dx = COS[ray_ang]
            ray_dy = -SIN[ray_ang]
            if low_ram_trig:
                ray_dx = ray_dx / 1024.0
                ray_dy = ray_dy / 1024.0
            hit_x = px + ray_dx * dist
            hit_y = py + ray_dy * dist
            hit_mx = int(hit_x)
            hit_my = int(hit_y)
            if side == 0:
                hit_mx = int(hit_x + (-0.001 if ray_dx < 0 else 0.001))
            else:
                hit_my = int(hit_y + (-0.001 if ray_dy < 0 else 0.001))
            is_door = (hit_mx, hit_my) in self.closed_doors

            light = 42
            for li, (lx, ly, strength) in enumerate(lamps):
                ldx = hit_x - lx
                ldy = hit_y - ly
                d2 = ldx * ldx + ldy * ldy
                flicker = ((lamp_phase + li * 5) & 7) - 3
                light += int((strength + flicker * 4) / (1.0 + d2 * 1.35))
            if muzzle_flash > 0:
                # Local player flash: nearby walls and floor bloom briefly.
                light += muzzle_flash * 18 + max(0, 45 - int(dist * 9))
            if light > 255:
                light = 255

            line_h = int(PLAY_H / (dist + 1e-6))
            if line_h < 1:
                line_h = 1
            if line_h > PLAY_H:
                line_h = PLAY_H

            start = (PLAY_H - line_h) // 2
            end = start + line_h - 1
            if start < 0:
                start = 0
            if end >= PLAY_H:
                end = PLAY_H - 1

            b = light - int(dist * 7)
            if b < 18:
                b = 18
            if b > 255:
                b = 255

            wr = b if side == 0 else (b * 3) // 4

            # Apply theme color to wall
            if theme == 0:  # Brown
                wg = wr * 3 // 5
                wb = wr // 4
            elif theme == 1:  # Blue
                wb = wr
                wg = wr * 3 // 5
                wr = wr // 4
            elif theme == 2:  # Greenish
                wg = wr
                wb = wr // 3
                wr = wr // 3
            else:  # Purple
                wb = wr
                wg = wr // 4
            if is_door:
                wr, wg, wb = min(255, b + 20), (b * 3) // 4, max(15, b // 5)

            # Base sky and floor colors depending on theme
            if theme == 0:
                sky_r, sky_g, sky_b = 0, 0, 14 + muzzle_flash * 4
                fl_r, fl_g, fl_b = 8 + light // 10, 5 + light // 14, 0
            elif theme == 1:
                sky_r, sky_g, sky_b = 10 + muzzle_flash * 3, 0, 0
                fl_r, fl_g, fl_b = 0, 5 + light // 16, 8 + light // 10
            elif theme == 2:
                sky_r, sky_g, sky_b = 12 + muzzle_flash * 3, 5 + muzzle_flash * 2, 0
                fl_r, fl_g, fl_b = 0, 8 + light // 10, 0
            else:
                sky_r, sky_g, sky_b = 0, 8 + muzzle_flash * 3, 5 + muzzle_flash
                fl_r, fl_g, fl_b = 7 + light // 14, 0, 7 + light // 10

            # apply damage flash overeverything in this column
            if dmg_flash > 0:
                flash_r = 150 + dmg_flash * 6
                if flash_r > 255:
                    flash_r = 255
                sky_r, sky_g, sky_b = flash_r, 0, 0
                wr, wg, wb = flash_r, 0, 0
                fl_r, fl_g, fl_b = flash_r, 0, 0

            # Very small wall texture: subtle mortar/stone variation. Keep it
            # low contrast so lighting remains the main depth cue.
            wall_u = hit_y if side == 0 else hit_x
            pattern_base = int(wall_u * 8)
            wall_style = (hit_mx * 3 + hit_my * 5 + theme) & 3
            # The minimap owns the top-left overlay. Starting below it avoids a
            # branch for every pixel in the inner loops.
            skip_top = minimap_h if x < minimap_w else 0

            # Inline single-column draw (avoids draw_rectangle call overhead).
            # Draw sky, wall, and floor in order!
            for y in range(skip_top, start):
                sp(x, y, sky_r, sky_g, sky_b)
                if draw_pair:
                    sp(x2, y, sky_r, sky_g, sky_b)

            wall_start = start if start > skip_top else skip_top
            for y in range(wall_start, end + 1):
                pattern = (pattern_base + ((y - start) >> 1)) & 15
                if is_door and ((pattern_base + y) & 3) == 0:
                    pr, pg, pb = min(255, wr + 18), min(255, wg + 12), wb
                elif wall_style == 1 and (pattern_base & 3) == 0:
                    pr, pg, pb = (wr * 3) // 4, (wg * 3) // 4, (wb * 3) // 4
                elif wall_style == 2 and ((y - start) & 3) == 0:
                    pr, pg, pb = min(255, wr + 8), min(255, wg + 8), min(255, wb + 8)
                elif pattern == 0:
                    pr, pg, pb = min(255, wr + 12), min(255, wg + 12), min(255, wb + 12)
                elif pattern == 8:
                    pr, pg, pb = (wr * 7) // 8, (wg * 7) // 8, (wb * 7) // 8
                else:
                    pr, pg, pb = wr, wg, wb
                sp(x, y, pr, pg, pb)
                if draw_pair:
                    sp(x2, y, pr, pg, pb)

            floor_start = end + 1
            if floor_start < skip_top:
                floor_start = skip_top
            for y in range(floor_start, PLAY_H):
                sp(x, y, fl_r, fl_g, fl_b)
                if draw_pair:
                    sp(x2, y, fl_r, fl_g, fl_b)

        # sprites (enemies) als billboards
        # sortiert nach Entfernung (weit -> nah)
        # dx/dy stored alongside dist so we don't recalculate below.
        px = self.px
        py = self.py
        ang = self.ang
        if self.render_enemies:
            alive = []
            for e in self.enemies:
                if e[2] > 0:
                    dx = e[0] - px
                    dy = e[1] - py
                    # Sort by squared distance; ordering is identical to real
                    # distance and saves sqrt for off-screen enemies.
                    d2 = dx * dx + dy * dy
                    alive.append((d2, e, dx, dy))
            alive.sort(reverse=True)

            HALF_FOV = self.HALF_FOV
            FOV = self.FOV
            for d2, e, dx, dy in alive:
                a = self._angle_to_units(dx, dy)
                delta = self._angle_delta(a, ang)
                if abs(delta) > HALF_FOV:
                    continue

                sx = int((HALF_FOV - delta) * WIDTH / FOV)
                if sx < 0 or sx >= WIDTH:
                    continue

                dist = math.sqrt(d2)
                # sprite size
                sh = int(PLAY_H / (dist + 1e-6))
                if sh < 2:
                    sh = 2
                if sh > PLAY_H:
                    sh = PLAY_H
                sw = sh // 3
                if sw < 1:
                    sw = 1
                if sw > 8:
                    sw = 8

                y0 = (PLAY_H - sh) // 2
                y1 = y0 + sh - 1

                x0 = sx - sw // 2
                x1 = x0 + sw - 1

                typ = e[4] if len(e) > 4 else 0
                anim = e[5] if len(e) > 5 else 0
                firing = e[10] if len(e) > 10 else 0
                sprite_light = 62
                for li, (lx, ly, strength) in enumerate(lamps):
                    ldx = e[0] - lx
                    ldy = e[1] - ly
                    d2 = ldx * ldx + ldy * ldy
                    flicker = ((lamp_phase + li * 5) & 7) - 3
                    sprite_light += int((strength + flicker * 4) / (1.0 + d2 * 1.20))
                if muzzle_flash > 0:
                    sprite_light += max(0, muzzle_flash * 20 - int(dist * 12))
                if sprite_light > 255:
                    sprite_light = 255
                self._draw_enemy_sprite(
                    sp,
                    x0,
                    x1,
                    y0,
                    y1,
                    dist,
                    zbuf,
                    typ,
                    e[2],
                    anim,
                    sprite_light,
                    firing,
                )

        if self.key_pos is not None and not self.key_taken:
            self._draw_world_marker(
                sp, self.key_pos[0] + 0.5, self.key_pos[1] + 0.5, "key", zbuf
            )
        if self.quad_pos is not None and not self.quad_taken and self.quad_timer <= 0:
            self._draw_world_marker(
                sp, self.quad_pos[0] + 0.5, self.quad_pos[1] + 0.5, "quad", zbuf
            )
        if self.exit_pos is not None:
            self._draw_world_marker(
                sp, self.exit_pos[0] + 0.5, self.exit_pos[1] + 0.5, "exit", zbuf
            )

        if self.render_minimap:
            # minimap overlay: keep the background static and only refresh markers.
            if not self._minimap_initialized:
                draw_rectangle(0, 0, self.MAP_W + 1, self.MAP_H + 1, 0, 0, 0)
                for mx, my in self._minimap_walls:
                    sp(mx, my, 0, 0, 160)
                for mx, my in self.closed_doors:
                    sp(mx, my, 190, 120, 20)
                if self.key_pos is not None and not self.key_taken:
                    sp(self.key_pos[0], self.key_pos[1], 255, 230, 40)
                if (
                    self.quad_pos is not None
                    and not self.quad_taken
                    and self.quad_timer <= 0
                ):
                    sp(self.quad_pos[0], self.quad_pos[1], 150, 70, 255)
                if self.exit_pos is not None:
                    sp(
                        self.exit_pos[0],
                        self.exit_pos[1],
                        0,
                        180,
                        90 if self.key_taken else 40,
                    )
                self._minimap_initialized = True
            else:
                if self._minimap_prev_player is not None:
                    self._restore_minimap_cell(
                        self._minimap_prev_player[0], self._minimap_prev_player[1]
                    )
                if self._minimap_prev_aim is not None:
                    self._restore_minimap_cell(
                        self._minimap_prev_aim[0], self._minimap_prev_aim[1]
                    )
                for ex, ey in self._minimap_prev_enemies:
                    self._restore_minimap_cell(ex, ey)

            player_cell = (int(px), int(py))
            sp(player_cell[0], player_cell[1], 0, 255, 0)
            # direction hint
            dc, ds = self._cos_sin(ang)
            ax = int(px + dc * 0.7)
            ay = int(py - ds * 0.7)
            aim_cell = None
            if 0 <= ax < self.MAP_W and 0 <= ay < self.MAP_H:
                sp(ax, ay, 0, 200, 0)
                aim_cell = (ax, ay)
            current_enemy_cells = []
            for e in self.enemies:
                if e[2] > 0:
                    ex = int(e[0])
                    ey = int(e[1])
                    if 0 <= ex < self.MAP_W and 0 <= ey < self.MAP_H:
                        current_enemy_cells.append((ex, ey))
                        typ = e[4] if len(e) > 4 else 0
                        if typ == 2:
                            sp(ex, ey, 180, 60, 255)
                        elif typ == 1:
                            sp(ex, ey, 255, 130, 0)
                        else:
                            sp(ex, ey, 255, 0, 0)
            self._minimap_prev_player = player_cell
            self._minimap_prev_aim = aim_cell
            self._minimap_prev_enemies = current_enemy_cells

        if self.render_hud:
            # lives indicator - 2x2 red blocks (oben rechts)
            for i in range(self.lives):
                lx = WIDTH - 3 - i * 4
                ly = 1
                draw_rectangle(lx, ly, lx + 1, ly + 1, 220, 30, 30)
            if self.key_taken:
                draw_text_small(WIDTH - 22, 4, "KEY", 255, 230, 40)
            elif self.key_flash > 0:
                draw_text_small(WIDTH - 22, 4, "KEY", 255, 70, 40)
            if self.quad_timer > 0:
                draw_text_small(20, 1, "Q", 160, 90, 255)

        # wave announcement banner
        if self.wave_announce > 0:
            wlabel = "L" + str(self.level)
            wx = WIDTH // 2 - len(wlabel) * 3
            wy = PLAY_H // 2 - 3
            draw_rectangle(wx - 1, wy - 1, wx + len(wlabel) * 6, wy + 5, 0, 0, 0)
            draw_text_small(wx, wy, wlabel, 255, 220, 0)

        if self.render_crosshair:
            self._draw_weapon(sp)
            # crosshair (+ shape, flashes yellow on hit)
            cx = WIDTH // 2
            cy = PLAY_H // 2
            if self.hit_flash > 0:
                cr, cg, cb = 255, 255, 0
            else:
                cr, cg, cb = 200, 200, 200
            for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                xx = cx + dx
                yy = cy + dy
                if 0 <= xx < WIDTH and 0 <= yy < PLAY_H:
                    sp(xx, yy, cr, cg, cb)

        if self.render_hud:
            display_score_and_time(self.score)

    def _advance_game_frame(self, joystick):
        """Advance one game frame; shared by sync and browser runtime loops."""
        global game_over, global_score

        c_button, z_button = joystick.read_buttons()
        if c_button:
            return False

        self.frame += 1
        if self.wave_announce > 0:
            self.wave_announce -= 1
        if self.hit_flash > 0:
            self.hit_flash -= 1
        if self.muzzle_flash > 0:
            self.muzzle_flash -= 1
        if self.weapon_recoil > 0:
            self.weapon_recoil -= 1
        if self.weapon_heat > 0:
            self.weapon_heat -= 1
        if self.quad_timer > 0:
            self.quad_timer -= 1
        if self.key_flash > 0:
            self.key_flash -= 1
        if self.dmg_flash > 0:
            self.dmg_flash -= 1

        direction = joystick.read_direction(self.INPUT_DIRECTIONS, debounce=False)
        turn_x, move_y = direction_to_delta_8way(direction)
        if turn_x < 0:
            self.ang = (self.ang + 5) & 255
        elif turn_x > 0:
            self.ang = (self.ang - 5) & 255

        move = 0.0
        if move_y < 0:
            move = 0.12
        elif move_y > 0:
            move = -0.10
        if move:
            self.bob_phase = (self.bob_phase + 2) & 31
            cos_ang, sin_ang = self._cos_sin(self.ang)
            next_x = self.px + cos_ang * move
            next_y = self.py - sin_ang * move
            if not self._is_wall_pos(next_x, self.py):
                self.px = next_x
            if not self._is_wall_pos(self.px, next_y):
                self.py = next_y
            if self._update_pickups_and_exit():
                global_score = self.score
                self._render()
                return True

        if self.shot_cd > 0:
            self.shot_cd -= 1
        if z_button and self.shot_cd == 0:
            self._shoot()
            self.shot_cd = 10

        self._update_enemies()
        if game_over:
            global_score = self.score
            return False

        alive = 0
        for enemy in self.enemies:
            if enemy[2] > 0:
                alive += 1
        if alive == 0:
            self.score += 100
            self.wave += 1
            self._spawn_wave(self.wave)
            self.px, self.py = self._player_start_for_level()
            self.ang = 0

        global_score = self.score
        self._render()
        if (self.frame % 80) == 0:
            gc.collect()
        return True

    def main_loop(self, joystick):
        global game_over, global_score
        game_over = False
        global_score = 0
        self.reset()
        display_score_and_time(0)

        while not game_over:
            try:
                now = ticks_ms()
                if ticks_diff(now, self.last_frame) < self.frame_ms:
                    sleep_ms(2)
                    continue
                self.last_frame = now
                if not self._advance_game_frame(joystick):
                    return
            except RestartProgram:
                return

    async def main_loop_async(self, joystick):
        """Async version for pygbag: yields between shared simulation frames."""
        if asyncio is None:
            return self.main_loop(joystick)

        global game_over, global_score
        game_over = False
        global_score = 0
        self.reset()
        display_score_and_time(0)

        while not game_over:
            try:
                now = ticks_ms()
                if ticks_diff(now, self.last_frame) < self.frame_ms:
                    await asyncio.sleep(0.002)
                    continue
                self.last_frame = now
                if not self._advance_game_frame(joystick):
                    return
            except RestartProgram:
                return


class CityChaseGame(FrameLoopGame):
    """
    CITY
    Controls:
      - Up / Down: accelerate / brake
      - Left / Right: steer
      - Z: boost
      - C: return to menu
    Top-down city chase inspired by early overhead open-world crime games.
    """

    FRAME_MS = 38
    WORLD = 256
    BLOCK = 32
    ROAD_W = 10
    MAX_SPEED = 2.45

    def __init__(self, ctx=None):
        self.target_jobs = int(get_context_setting(ctx, "jobs", 3) or 3)
        self.traffic_enabled = bool(get_context_setting(ctx, "traffic", True))
        self.reset()

    def reset(self):
        self.x = 128.0
        self.y = 128.0
        self.angle = -90.0
        self.speed = 0.0
        self.condition = 100.0
        self.heat = 0.0
        self.energy = 100.0
        self.score = 0
        self.frame = 0
        self.jobs_done = 0
        self.phase = "pickup"
        self.bump_flash = 0
        self.boost_flash = 0
        self.hit_cooldown = 0
        self.entities = []
        self.pickup = self._random_road_point(46)
        self.dropoff = self._random_road_point(76)
        self._spawn_traffic(8 if self.traffic_enabled else 0)

    def _road_axis(self, value):
        m = int(value) % self.BLOCK
        return m < self.ROAD_W or m >= self.BLOCK - self.ROAD_W

    def _is_road(self, x, y):
        x = x % self.WORLD
        y = y % self.WORLD
        return self._road_axis(x) or self._road_axis(y)

    def _is_intersection(self, x, y):
        return self._road_axis(x) and self._road_axis(y)

    def _wrap_dist(self, a, b):
        d = abs(a - b)
        return min(d, self.WORLD - d)

    def _dist2_to_player(self, x, y):
        dx = self._wrap_dist(x, self.x)
        dy = self._wrap_dist(y, self.y)
        return dx * dx + dy * dy

    def _wrapped_delta_to_player(self, x, y):
        dx = (x - self.x + self.WORLD / 2) % self.WORLD - self.WORLD / 2
        dy = (y - self.y + self.WORLD / 2) % self.WORLD - self.WORLD / 2
        return dx, dy

    def _target_distance(self):
        tx, ty = self._target()
        dx, dy = self._wrapped_delta_to_player(tx, ty)
        return math.sqrt(dx * dx + dy * dy)

    def _random_road_point(self, min_dist=32):
        for _ in range(90):
            gx = random.randint(0, self.WORLD - 1)
            gy = random.randint(0, self.WORLD - 1)
            if not self._is_road(gx, gy):
                continue
            if self._dist2_to_player(gx, gy) >= min_dist * min_dist:
                return [float(gx), float(gy)]
        return [float((int(self.x) + min_dist) % self.WORLD), float(self.y)]

    def _dir_vec(self, d):
        if d == 0:
            return 1, 0
        if d == 1:
            return 0, 1
        if d == 2:
            return -1, 0
        return 0, -1

    def _valid_dirs(self, x, y):
        out = []
        for d in range(4):
            dx, dy = self._dir_vec(d)
            if self._is_road(x + dx * 5, y + dy * 5):
                out.append(d)
        return out or [0]

    def _spawn_traffic(self, count):
        for _ in range(count):
            px, py = self._random_road_point(28)
            dirs = self._valid_dirs(px, py)
            self.entities.append(
                [px, py, random.choice(dirs), 0, random.randint(0, 30)]
            )

    def _spawn_police(self):
        target = 0
        if self.heat > 18:
            target = 1 + min(3, int(self.heat // 35))
        current = 0
        for e in self.entities:
            if e[3] == 1:
                current += 1
        while current < target:
            px, py = self._random_road_point(62)
            dirs = self._valid_dirs(px, py)
            self.entities.append(
                [px, py, random.choice(dirs), 1, random.randint(0, 15)]
            )
            current += 1

    def _choose_police_dir(self, e):
        best = e[2]
        best_score = 999999.0
        for d in self._valid_dirs(e[0], e[1]):
            dx, dy = self._dir_vec(d)
            nx = (e[0] + dx * 8) % self.WORLD
            ny = (e[1] + dy * 8) % self.WORLD
            score = self._dist2_to_player(nx, ny)
            if score < best_score:
                best = d
                best_score = score
        return best

    def _update_entities(self):
        kept = []
        for e in self.entities:
            e[4] += 1
            if (
                e[3] == 1
                and self.heat <= 2
                and self._dist2_to_player(e[0], e[1]) > 70 * 70
            ):
                continue
            if self._is_intersection(e[0], e[1]) and e[4] > 12:
                if e[3] == 1:
                    e[2] = self._choose_police_dir(e)
                elif random.randint(0, 99) < 34:
                    e[2] = random.choice(self._valid_dirs(e[0], e[1]))
                e[4] = 0
            dx, dy = self._dir_vec(e[2])
            step = 1.22 if e[3] == 1 else 0.78
            if e[3] == 1:
                step += min(0.44, self.heat * 0.006)
            nx = (e[0] + dx * step) % self.WORLD
            ny = (e[1] + dy * step) % self.WORLD
            if self._is_road(nx, ny):
                e[0] = nx
                e[1] = ny
            else:
                e[2] = random.choice(self._valid_dirs(e[0], e[1]))
            if self._dist2_to_player(e[0], e[1]) < (7 * 7):
                if self.hit_cooldown <= 0:
                    if e[3] == 1:
                        self.condition -= 9.0
                        self.heat += 2.0
                    else:
                        self.condition -= 4.0
                        self.heat += 0.8
                    self.speed *= 0.48
                    self.bump_flash = 10
                    self.hit_cooldown = 14
            kept.append(e)
        self.entities = kept

    def _target(self):
        return self.pickup if self.phase == "pickup" else self.dropoff

    def _advance_job(self):
        tx, ty = self._target()
        if self._wrap_dist(self.x, tx) > 5 or self._wrap_dist(self.y, ty) > 5:
            return True
        if self.phase == "pickup":
            self.phase = "drop"
            self.score += 120
            self.heat = min(100.0, self.heat + 12.0)
            self.dropoff = self._random_road_point(70)
            return True
        self.jobs_done += 1
        self.score += 520 + int(self.condition)
        self.heat = min(100.0, self.heat + 18.0)
        if self.jobs_done >= self.target_jobs:
            set_game_over_score(self.score + int(self.condition * 8), won=True)
            return False
        self.phase = "pickup"
        self.pickup = self._random_road_point(55)
        self.dropoff = self._random_road_point(76)
        return True

    def _update(self, direction, boost):
        self.frame += 1
        if self.bump_flash > 0:
            self.bump_flash -= 1
        if self.boost_flash > 0:
            self.boost_flash -= 1
        if self.hit_cooldown > 0:
            self.hit_cooldown -= 1
        dx, dy = direction_to_delta_8way(direction)
        if dx < 0:
            self.angle -= 5.0 + min(3.0, abs(self.speed) * 1.2)
        elif dx > 0:
            self.angle += 5.0 + min(3.0, abs(self.speed) * 1.2)
        if dy < 0:
            self.speed += 0.105
        elif dy > 0:
            self.speed -= 0.130
        else:
            self.speed *= 0.982
        max_speed = self.MAX_SPEED
        if boost and self.energy > 1.5 and self.speed > 0.3:
            self.speed += 0.090
            self.energy -= 1.15
            self.heat = min(100.0, self.heat + 0.06)
            self.boost_flash = 4
            max_speed = self.MAX_SPEED + 0.82
        else:
            self.energy = min(100.0, self.energy + 0.08)
        self.speed = clamp(self.speed, -0.86, max_speed)

        rad = math.radians(self.angle)
        vx = math.cos(rad) * self.speed
        vy = math.sin(rad) * self.speed
        nx = (self.x + vx) % self.WORLD
        ny = (self.y + vy) % self.WORLD
        if self._is_road(nx, self.y):
            self.x = nx
        else:
            self.speed *= -0.26
            self.condition -= 1.2
            self.bump_flash = 6
        if self._is_road(self.x, ny):
            self.y = ny
        else:
            self.speed *= -0.26
            self.condition -= 1.2
            self.bump_flash = 6

        self.heat = clamp(self.heat - 0.018, 0.0, 100.0)
        self._spawn_police()
        self._update_entities()
        self.score += int(max(0.0, self.speed) * 0.8)
        if self.condition <= 0:
            set_game_over_score(self.score, won=False)
            return False
        return self._advance_job()

    def _screen_pos(self, wx, wy):
        dx, dy = self._wrapped_delta_to_player(wx, wy)
        sx = int(WIDTH // 2 + dx)
        sy = int(PLAY_HEIGHT // 2 + dy)
        return sx, sy

    def _draw_city(self):
        ox = self.x - WIDTH // 2
        oy = self.y - PLAY_HEIGHT // 2
        for sy in range(PLAY_HEIGHT):
            wy = (oy + sy) % self.WORLD
            yroad = self._road_axis(wy)
            for sx in range(WIDTH):
                wx = (ox + sx) % self.WORLD
                xroad = self._road_axis(wx)
                if xroad or yroad:
                    shade = 34 + ((int(wx) + int(wy)) & 3) * 5
                    if xroad and yroad:
                        display.set_pixel(sx, sy, shade + 14, shade + 14, shade + 16)
                    elif ((int(wx if yroad else wy) // 7) & 3) == 0:
                        display.set_pixel(sx, sy, 210, 205, 160)
                    else:
                        display.set_pixel(sx, sy, shade, shade, shade + 4)
                else:
                    bx = int(wx) // self.BLOCK
                    by = int(wy) // self.BLOCK
                    c = 24 + ((bx * 17 + by * 11) % 34)
                    display.set_pixel(sx, sy, c // 2, c, c + 12)

    def _draw_marker(self, point, color):
        sx, sy = self._screen_pos(point[0], point[1])
        if -5 <= sx < WIDTH + 5 and -5 <= sy < PLAY_HEIGHT + 5:
            draw_rect_outline(sx - 4, sy - 4, sx + 4, sy + 4, *color)
            set_pixel_clipped(sx, sy, 255, 255, 255)
            return True
        return False

    def _draw_target_pointer(self, point, color):
        dx, dy = self._wrapped_delta_to_player(point[0], point[1])
        if abs(dx) < 1 and abs(dy) < 1:
            return
        limit_x = WIDTH // 2 - 5
        limit_y = PLAY_HEIGHT // 2 - 8
        scale_x = limit_x / abs(dx) if abs(dx) > 0.1 else 999.0
        scale_y = limit_y / abs(dy) if abs(dy) > 0.1 else 999.0
        scale = min(scale_x, scale_y, 1.0)
        px = int(WIDTH // 2 + dx * scale)
        py = int(PLAY_HEIGHT // 2 + dy * scale)
        px = clamp(px, 3, WIDTH - 4)
        py = clamp(py, 8, PLAY_HEIGHT - 8)
        draw_line(
            WIDTH // 2,
            PLAY_HEIGHT // 2,
            px,
            py,
            color[0] // 2,
            color[1] // 2,
            color[2] // 2,
        )
        draw_rect_outline(px - 2, py - 2, px + 2, py + 2, *color)
        set_pixel_clipped(px, py, 255, 255, 255)

    def _draw_car(self, sx, sy, angle, body, trim):
        rad = math.radians(angle)
        fx = int(math.cos(rad) * 3)
        fy = int(math.sin(rad) * 3)
        rx = int(math.cos(rad + math.pi / 2) * 2)
        ry = int(math.sin(rad + math.pi / 2) * 2)
        draw_line(sx - fx - rx, sy - fy - ry, sx + fx, sy + fy, *body)
        draw_line(sx - fx + rx, sy - fy + ry, sx + fx, sy + fy, *body)
        draw_line(sx - rx, sy - ry, sx + rx, sy + ry, *trim)
        set_pixel_clipped(sx + fx, sy + fy, 255, 255, 255)

    def _draw_hud(self):
        draw_rectangle(0, 0, WIDTH - 1, 6, 0, 0, 0)
        draw_text_small(
            1, 1, "J" + str(self.jobs_done) + "/" + str(self.target_jobs), 255, 255, 255
        )
        heat_w = int(self.heat * 17 / 100)
        cond_w = int(self.condition * 17 / 100)
        draw_rectangle(25, 1, 42, 2, 25, 25, 25)
        draw_rectangle(45, 1, 62, 2, 25, 25, 25)
        if heat_w > 0:
            draw_rectangle(25, 1, 24 + heat_w, 2, 255, 45, 45)
        if cond_w > 0:
            draw_rectangle(45, 1, 44 + cond_w, 2, 45, 220, 90)
        label = "P" if self.phase == "pickup" else "D"
        draw_text_small(1, PLAY_HEIGHT - 6, label, 255, 240, 90)
        dist = min(99, int(self._target_distance()))
        draw_text_small(8, PLAY_HEIGHT - 6, str(dist), 180, 220, 255)

    def _draw(self):
        display.clear()
        self._draw_city()
        if self.phase == "pickup":
            if not self._draw_marker(self.pickup, (60, 255, 110)):
                self._draw_target_pointer(self.pickup, (60, 255, 110))
        else:
            if not self._draw_marker(self.dropoff, (255, 220, 60)):
                self._draw_target_pointer(self.dropoff, (255, 220, 60))
        for e in self.entities:
            sx, sy = self._screen_pos(e[0], e[1])
            if -6 <= sx < WIDTH + 6 and -6 <= sy < PLAY_HEIGHT + 6:
                if e[3] == 1:
                    self._draw_car(sx, sy, e[2] * 90, (255, 40, 40), (40, 90, 255))
                else:
                    self._draw_car(sx, sy, e[2] * 90, (70, 170, 255), (255, 230, 70))
        if self.bump_flash:
            body = (255, 70, 35)
        elif self.boost_flash:
            body = (255, 255, 255)
        else:
            body = (245, 245, 245)
        self._draw_car(WIDTH // 2, PLAY_HEIGHT // 2, self.angle, body, (255, 40, 210))
        self._draw_hud()
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        self.reset()
        begin_game(0)

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            d = joystick.read_direction(
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
                debounce=False,
            )
            if not self._update(d, z_button):
                return False
            self._draw()
            return True

        return step


class TopDownRacerGame(FrameLoopGame):
    """
    RACING
    Controls:
      - Up / Down: accelerate / brake
      - Left / Right: steer
      - Z: boost
      - C: return to menu
    Top-down circuit racer with scrolling road, traffic, boost, and lap finish.
    """

    FRAME_MS = 34
    CAR_Y = PLAY_HEIGHT - 14
    ROAD_HALF = 17
    LAP_LEN = 760.0

    def __init__(self, ctx=None):
        self.target_laps = int(get_context_setting(ctx, "laps", 3) or 3)
        self.traffic_enabled = bool(get_context_setting(ctx, "traffic", True))
        self.reset()

    def reset(self):
        self.world_y = 0.0
        self.speed = 0.0
        self.player_x = WIDTH // 2
        self.energy = 100.0
        self.score = 0
        self.lap = 1
        self.frame = 0
        self.bump_flash = 0
        self.boost_flash = 0
        self.rivals = []
        self.next_spawn_y = 46.0
        self.passed = 0
        self._spawn_until(self.world_y + 190.0)

    def _track_center(self, z):
        return WIDTH // 2 + math.sin(z * 0.028) * 12.0 + math.sin(z * 0.010 + 1.8) * 7.0

    def _sample_world_for_row(self, row):
        return self.world_y + (self.CAR_Y - row) * 2.15

    def _lane_x(self, z, lane):
        return self._track_center(z) + lane * (self.ROAD_HALF - 6)

    def _spawn_until(self, limit_y):
        if not self.traffic_enabled:
            return
        while self.next_spawn_y < limit_y:
            gap = random.randint(36, 68)
            self.next_spawn_y += gap
            lane = random.choice((-0.72, -0.25, 0.25, 0.72))
            kind = random.randint(0, 1)
            drift = random.randint(0, 80)
            self.rivals.append([self.next_spawn_y, lane, kind, drift])

    def _rival_x(self, rival):
        lane = rival[1]
        if rival[2] == 1:
            lane += math.sin((self.frame + rival[3]) * 0.035) * 0.12
        lane = clamp(lane, -0.9, 0.9)
        return self._lane_x(rival[0], lane)

    def _update(self, direction, boost):
        self.frame += 1
        if self.bump_flash > 0:
            self.bump_flash -= 1
        if self.boost_flash > 0:
            self.boost_flash -= 1

        dx, dy = direction_to_delta_8way(direction)
        if dy < 0:
            self.speed += 0.085
        elif dy > 0:
            self.speed -= 0.125
        else:
            self.speed *= 0.988

        max_speed = 3.05
        if boost and self.energy > 2.0 and self.speed > 0.8:
            self.speed += 0.105
            self.energy -= 1.05
            self.boost_flash = 4
            max_speed = 3.95
        else:
            self.energy = min(100.0, self.energy + 0.075)

        self.speed = clamp(self.speed, 0.0, max_speed)

        if dx:
            steer = 0.72 + self.speed * 0.23
            self.player_x += dx * steer
        self.player_x = clamp(self.player_x, 2.0, WIDTH - 3.0)

        center = self._track_center(self.world_y)
        margin = self.ROAD_HALF - 3
        if abs(self.player_x - center) > margin:
            self.speed *= 0.935
            self.energy -= 0.42 + self.speed * 0.20
            self.bump_flash = max(self.bump_flash, 2)

        self.world_y += self.speed
        self.lap = int(self.world_y // self.LAP_LEN) + 1
        self.score = int(self.world_y) + self.passed * 55 + int(self.energy * 2)

        kept = []
        for rival in self.rivals:
            rel = rival[0] - self.world_y
            sx = self._rival_x(rival)
            sy = self.CAR_Y - rel / 2.15
            if (
                -12.0 <= rel <= 9.0
                and abs(sy - self.CAR_Y) <= 6.0
                and abs(sx - self.player_x) <= 5.0
            ):
                self.energy -= 18.0 if rival[2] == 0 else 24.0
                self.speed *= 0.43
                self.bump_flash = 12
                continue
            if rel < -20.0:
                self.passed += 1
                continue
            kept.append(rival)
        self.rivals = kept
        self._spawn_until(self.world_y + 190.0)

        if self.energy <= 0.0:
            set_game_over_score(self.score, won=False)
            return False
        if self.world_y >= self.LAP_LEN * self.target_laps:
            self.score += int(self.energy * 15) + self.passed * 20 + 1000
            set_game_over_score(self.score, won=True)
            return False
        return True

    def _draw_car(self, x, y, body, trim, player=False):
        x = int(x)
        y = int(y)
        draw_rectangle(x - 2, y - 3, x + 2, y + 3, *body)
        draw_rectangle(x - 1, y - 4, x + 1, y - 3, *trim)
        set_pixel_clipped(x - 3, y - 2, 20, 20, 20)
        set_pixel_clipped(x + 3, y - 2, 20, 20, 20)
        set_pixel_clipped(x - 3, y + 2, 20, 20, 20)
        set_pixel_clipped(x + 3, y + 2, 20, 20, 20)
        if player:
            set_pixel_clipped(x, y - 5, 255, 255, 255)

    def _draw_road_row(self, row):
        z = self._sample_world_for_row(row)
        center = int(self._track_center(z))
        left = center - self.ROAD_HALF
        right = center + self.ROAD_HALF
        dash = int(z / 12) & 1
        finish = int(z) % int(self.LAP_LEN)
        for x in range(WIDTH):
            if left <= x <= right:
                if finish < 9 and ((x + row) & 3) < 2:
                    display.set_pixel(x, row, 245, 245, 245)
                elif x in (left, left + 1, right - 1, right):
                    if self.boost_flash:
                        display.set_pixel(x, row, 255, 80, 210)
                    else:
                        display.set_pixel(x, row, 255, 230, 50)
                elif abs(x - center) <= 1 and dash:
                    display.set_pixel(x, row, 220, 220, 220)
                else:
                    shade = 38 + ((row + int(self.world_y)) & 3) * 4
                    if self.bump_flash:
                        display.set_pixel(x, row, 90, 30, 32)
                    else:
                        display.set_pixel(x, row, shade, shade, shade + 8)
            else:
                grass = 20 + ((x * 3 + row + int(self.world_y)) & 7)
                display.set_pixel(x, row, 4, grass, 12)

    def _draw_hud(self):
        draw_rectangle(0, 0, WIDTH - 1, 6, 0, 0, 0)
        draw_text_small(
            1,
            1,
            "L" + str(min(self.lap, self.target_laps)) + "/" + str(self.target_laps),
            255,
            255,
            255,
        )
        bar_w = int(22 * self.energy / 100.0)
        draw_rectangle(WIDTH - 25, 1, WIDTH - 3, 3, 25, 25, 25)
        if bar_w > 0:
            col = (50, 235, 90) if self.energy > 30 else (255, 70, 30)
            draw_rectangle(WIDTH - 25, 1, WIDTH - 26 + bar_w, 3, *col)

    def _draw(self):
        display.clear()
        for row in range(PLAY_HEIGHT):
            self._draw_road_row(row)

        for rival in self.rivals:
            rel = rival[0] - self.world_y
            y = self.CAR_Y - rel / 2.15
            if -8 <= y < PLAY_HEIGHT + 8:
                x = self._rival_x(rival)
                if rival[2] == 0:
                    self._draw_car(x, y, (255, 70, 45), (255, 230, 70))
                else:
                    self._draw_car(x, y, (45, 160, 255), (255, 255, 255))

        if self.bump_flash:
            body = (255, 60, 35)
        elif self.boost_flash:
            body = (255, 255, 255)
        else:
            body = (235, 235, 245)
        self._draw_car(self.player_x, self.CAR_Y, body, (255, 40, 210), player=True)
        if self.boost_flash:
            draw_rectangle(
                int(self.player_x) - 1,
                self.CAR_Y + 4,
                int(self.player_x) + 1,
                self.CAR_Y + 6,
                40,
                170,
                255,
            )
        self._draw_hud()
        display_score_and_time(self.score)

    def _build_step(self, joystick):
        self.reset()
        begin_game(0)

        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            d = joystick.read_direction(
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
                debounce=False,
            )
            if not self._update(d, z_button):
                return False
            self._draw()
            return True

        return step


class RayRacerGame:
    """
    RAY RACER
    Raycaster-style anti-grav racer for the 64x64 matrix.

    Controls:
      - UP/DOWN: accelerate/brake
      - LEFT/RIGHT: steer
      - Z: boost
      - C: return to menu
    """

    PLAY_H = HEIGHT - 6
    HORIZON = 14
    TRACK_LEN = 900.0
    RACE_LAPS = 3
    FRAME_MS = 34
    NORMAL_MAX_SPEED = 2.25
    BOOST_MAX_SPEED = 3.10
    CRUISE_SPEED = NORMAL_MAX_SPEED * 0.5

    def __init__(self):
        self.row_depth = [0.0] * self.PLAY_H
        self.row_center = [WIDTH // 2] * self.PLAY_H
        self.row_half = [0] * self.PLAY_H
        self.reset()

    def reset(self):
        self.pos = 0.0
        self.speed = self.CRUISE_SPEED
        self.lane = 0.0
        self.energy = 100.0
        self.score = 0
        self.passed = 0
        self.lap = 1
        self.frame = 0
        self.bump_flash = 0
        self.boost_flash = 0
        self.objects = []
        self._spawn_until(self.pos + 145.0)
        self._prepare_depth_table()

    def _prepare_depth_table(self):
        span = self.PLAY_H - self.HORIZON
        for y in range(self.PLAY_H):
            if y < self.HORIZON:
                self.row_depth[y] = 0.0
                continue
            p = (y - self.HORIZON + 1) / span
            depth = 1.8 / (p * p)
            if depth > 72.0:
                depth = 72.0
            self.row_depth[y] = depth

    def _track_curve(self, z):
        # Three broad waves create readable F-Zero-like sweepers without maps.
        return (
            math.sin(z * 0.013) * 18.0
            + math.sin(z * 0.027 + 1.7) * 7.0
            + math.sin(z * 0.006) * 24.0
        )

    def _object_lane(self, obj):
        lane = obj[1]
        if obj[2] == 0:
            lane += math.sin((self.frame + obj[3]) * 0.055) * 0.13
        elif obj[2] == 1:
            lane += math.sin((self.frame + obj[3]) * 0.035) * 0.08
        if lane < -0.95:
            lane = -0.95
        elif lane > 0.95:
            lane = 0.95
        return lane

    def _spawn_until(self, z_limit):
        far = self.pos + 18.0
        for obj in self.objects:
            if obj[0] > far:
                far = obj[0]
        while far < z_limit:
            far += random.randint(16, 38)
            lane = random.choice((-0.72, -0.28, 0.28, 0.72))
            roll = random.randint(0, 99)
            if roll < 17:
                kind = 2  # energy gate
            elif roll < 42:
                kind = 1  # heavy rival
            else:
                kind = 0  # fast rival
            self.objects.append([far, lane, kind, random.randint(0, 127)])

    def _update(self, direction, boost):
        global game_over
        self.frame += 1
        if self.bump_flash > 0:
            self.bump_flash -= 1
        if self.boost_flash > 0:
            self.boost_flash -= 1

        sx, sy = direction_to_delta_8way(direction)

        if sy < 0:
            self.speed += 0.070
        elif sy > 0:
            self.speed -= 0.110
        else:
            if self.speed < self.CRUISE_SPEED:
                self.speed += 0.034
                if self.speed > self.CRUISE_SPEED:
                    self.speed = self.CRUISE_SPEED
            elif self.speed > self.CRUISE_SPEED:
                self.speed -= 0.022
                if self.speed < self.CRUISE_SPEED:
                    self.speed = self.CRUISE_SPEED

        max_speed = self.NORMAL_MAX_SPEED
        if boost and self.energy > 2.0 and self.speed > 0.35:
            self.speed += 0.085
            self.energy -= 1.15
            self.boost_flash = 4
            max_speed = self.BOOST_MAX_SPEED
        else:
            self.energy += 0.085
            if self.energy > 100.0:
                self.energy = 100.0

        if self.speed < 0.0:
            self.speed = 0.0
        elif self.speed > max_speed:
            self.speed = max_speed

        if sx:
            steer = 0.045 + self.speed * 0.022
            self.lane += sx * steer
        else:
            self.lane *= 0.992

        if self.lane < -1.38:
            self.lane = -1.38
        elif self.lane > 1.38:
            self.lane = 1.38

        if abs(self.lane) > 1.05:
            self.speed *= 0.935
            self.energy -= 0.55 + self.speed * 0.18
            self.bump_flash = 2

        self.pos += self.speed
        self.lap = int(self.pos // self.TRACK_LEN) + 1
        self.score = int(self.pos * 2) + self.passed * 65 + int(self.energy)

        kept = []
        for obj in self.objects:
            rel = obj[0] - self.pos
            lane = self._object_lane(obj)
            if rel < 1.25:
                if obj[2] == 2:
                    if abs(self.lane - lane) < 0.38:
                        self.energy += 22.0
                        if self.energy > 100.0:
                            self.energy = 100.0
                        self.score += 120
                elif abs(self.lane - lane) < (0.34 if obj[2] == 0 else 0.42):
                    self.energy -= 17.0 if obj[2] == 0 else 25.0
                    self.speed *= 0.42
                    self.bump_flash = 12
                else:
                    self.passed += 1
                continue
            kept.append(obj)
        self.objects = kept
        self._spawn_until(self.pos + 145.0)

        if self.energy <= 0.0:
            set_game_over_score(self.score, won=False)
            return
        if self.pos >= self.TRACK_LEN * self.RACE_LAPS:
            self.score += int(self.energy * 20) + 1500
            set_game_over_score(self.score, won=True)
            return
        game_over = False

    def _project_y(self, rel):
        if rel <= 1.8:
            return self.PLAY_H - 1
        if rel > 72.0:
            return -1
        span = self.PLAY_H - self.HORIZON
        p = math.sqrt(1.8 / rel)
        y = self.HORIZON + int(p * span)
        if y < self.HORIZON:
            y = self.HORIZON
        elif y >= self.PLAY_H:
            y = self.PLAY_H - 1
        return y

    def _draw_hovercar(self, sp, sx, sy, size, kind):
        if size < 2:
            size = 2
        half = size // 2
        if kind == 1:
            body = (255, 90, 30)
            glow = (255, 220, 40)
        else:
            body = (35, 210, 255)
            glow = (255, 35, 200)
        y0 = sy - size
        y1 = sy
        for y in range(y0, y1 + 1):
            if y < 0 or y >= self.PLAY_H:
                continue
            rel_y = y - y0
            row_half = max(1, half - abs(rel_y - size // 2) // 2)
            for x in range(sx - row_half, sx + row_half + 1):
                if 0 <= x < WIDTH:
                    if abs(x - sx) == row_half:
                        sp(x, y, glow[0], glow[1], glow[2])
                    else:
                        sp(x, y, body[0], body[1], body[2])
        for x in (sx - half - 1, sx + half + 1):
            if 0 <= x < WIDTH and 0 <= sy < self.PLAY_H:
                sp(x, sy, 255, 255, 255)

    def _draw_energy_gate(self, sp, sx, sy, size):
        half = max(2, size // 2)
        top = sy - size - 1
        for x in range(sx - half, sx + half + 1):
            if 0 <= x < WIDTH and 0 <= top < self.PLAY_H:
                sp(x, top, 60, 255, 110)
        for y in range(top, sy + 1):
            if 0 <= y < self.PLAY_H:
                for x in (sx - half, sx + half):
                    if 0 <= x < WIDTH:
                        sp(x, y, 30, 220, 120)
        if 0 <= sx < WIDTH and 0 <= sy - half < self.PLAY_H:
            sp(sx, sy - half, 255, 255, 160)

    def _render(self):
        sp = display.set_pixel
        base_curve = self._track_curve(self.pos)
        shake = self.bump_flash if self.bump_flash > 0 else 0
        if shake:
            shake = (shake & 1) * 2 - 1

        # Sky and distant skyline.
        for y in range(self.HORIZON):
            r = 5 + y * 2
            g = 5 + y
            b = 24 + y * 3
            if self.boost_flash:
                b += 28
            for x in range(WIDTH):
                sp(x, y, r, g, b if b < 255 else 255)
        for x in range(0, WIDTH, 7):
            h = 2 + ((x * 5 + int(self.pos)) % 6)
            for y in range(self.HORIZON - h, self.HORIZON):
                if 0 <= y < self.PLAY_H:
                    sp(x, y, 22, 22, 42)
                    if x + 1 < WIDTH:
                        sp(x + 1, y, 22, 22, 42)

        for y in range(self.HORIZON, self.PLAY_H):
            depth = self.row_depth[y]
            p = (y - self.HORIZON + 1) / (self.PLAY_H - self.HORIZON)
            curve = self._track_curve(self.pos + depth)
            center = (
                WIDTH // 2
                + int((curve - base_curve) * 0.72)
                - int(self.lane * p * 28.0)
                + shake
            )
            half = 3 + int(p * p * 34.0)
            self.row_center[y] = center
            self.row_half[y] = half
            left = center - half
            right = center + half
            stripe = int((self.pos + depth) * 0.23) & 1
            for x in range(WIDTH):
                if left <= x <= right:
                    edge = x == left or x == right or x == left + 1 or x == right - 1
                    lane_mark = (
                        abs(x - center) <= 1
                        and (int((self.pos + depth) * 0.45) & 3) < 2
                    )
                    side_mark = (
                        abs(x - (center - half // 2)) <= 1
                        or abs(x - (center + half // 2)) <= 1
                    ) and stripe
                    if edge:
                        if self.boost_flash:
                            sp(x, y, 255, 80, 255)
                        else:
                            sp(x, y, 35, 230, 255)
                    elif lane_mark:
                        sp(x, y, 255, 245, 160)
                    elif side_mark:
                        sp(x, y, 110, 120, 150)
                    else:
                        shade = 26 + int(p * 58)
                        if stripe:
                            shade += 12
                        if self.bump_flash:
                            sp(x, y, 120, 22, 24)
                        else:
                            sp(x, y, shade, shade + 6, shade + 18)
                else:
                    dist_edge = left - x if x < left else x - right
                    glow = 70 - dist_edge * 5
                    if glow > 0:
                        sp(x, y, glow // 3, glow, glow)
                    else:
                        ground = 8 + int(p * 16)
                        sp(x, y, ground, 7, 18 + int(p * 10))

        visible = []
        for obj in self.objects:
            rel = obj[0] - self.pos
            if 1.2 < rel < 72.0:
                visible.append((rel, obj))
        visible.sort(reverse=True)
        for rel, obj in visible:
            y = self._project_y(rel)
            if y < self.HORIZON:
                continue
            center = self.row_center[y]
            half = self.row_half[y]
            lane = self._object_lane(obj)
            sx = center + int(lane * half)
            size = int(36 / rel) + 2
            if size > 13:
                size = 13
            if obj[2] == 2:
                self._draw_energy_gate(sp, sx, y, size + 3)
            else:
                self._draw_hovercar(sp, sx, y, size, obj[2])

        # Player hovercraft and cockpit line.
        car_y = self.PLAY_H - 4
        car_x = WIDTH // 2
        if self.bump_flash:
            car_col = (255, 50, 35)
        elif self.boost_flash:
            car_col = (255, 255, 255)
        else:
            car_col = (245, 245, 255)
        for dy, w in ((0, 2), (1, 4), (2, 6), (3, 4)):
            yy = car_y + dy
            for x in range(car_x - w, car_x + w + 1):
                if 0 <= x < WIDTH and 0 <= yy < self.PLAY_H:
                    if abs(x - car_x) == w:
                        sp(x, yy, 255, 45, 210)
                    else:
                        sp(x, yy, car_col[0], car_col[1], car_col[2])
        if self.boost_flash:
            for x in range(car_x - 2, car_x + 3):
                sp(x, self.PLAY_H - 1, 80, 180, 255)

        # Top playfield status: lap and energy.
        draw_rectangle(0, 0, WIDTH - 1, 0, 0, 0, 0)
        draw_text_small(1, 1, "L" + str(self.lap), 255, 255, 255)
        bar = int(self.energy * 24 / 100)
        draw_rectangle(WIDTH - 27, 1, WIDTH - 3, 3, 20, 20, 20)
        if bar > 0:
            br, bg, bb = (40, 230, 100) if self.energy > 30 else (255, 80, 30)
            draw_rectangle(WIDTH - 27, 1, WIDTH - 28 + bar, 3, br, bg, bb)

        display_score_and_time(self.score)

    def _build_step(self, joystick):
        def step():
            c_button, z_button = joystick.read_buttons()
            if c_button:
                return False
            d = joystick.read_direction(
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
                debounce=False,
            )
            self._update(d, z_button)
            if game_over:
                return False
            self._render()
            if (self.frame % 90) == 0:
                gc.collect()
            return True

        return step

    def main_loop(self, joystick):
        begin_game(0)
        self.reset()
        display.clear()
        _run_game_loop_sync(self.FRAME_MS, self._build_step(joystick))

    async def main_loop_async(self, joystick):
        if asyncio is None:
            return self.main_loop(joystick)
        begin_game(0)
        self.reset()
        display.clear()
        await _run_game_loop_async(self.FRAME_MS, self._build_step(joystick))
