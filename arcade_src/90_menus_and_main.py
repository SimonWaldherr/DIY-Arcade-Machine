class GameOverMenu:
    """Unified end-of-run menu with retry, highscore view, and menu return."""

    def __init__(
        self,
        joystick,
        score,
        best,
        best_name="---",
        title="LOST",
        highscores=None,
        game_name=None,
    ):
        self.joystick = joystick
        self.score = int(score or 0)
        self.best = int(best or 0)
        self.best_name = best_name if isinstance(best_name, str) else "---"
        self.title = title
        self.highscores = highscores
        self.game_name = game_name
        self.opts = ("RETRY", "HISCR", "MENU")
        self.hs_top = 0

    def _title_color(self):
        if self.title == "WON":
            return (50, 255, 80)
        return (255, 55, 45)

    def _draw_button(self, x, y, label, selected):
        col = (255, 255, 255) if selected else (95, 95, 95)
        bg = (
            (28, 70, 34)
            if selected and self.title == "WON"
            else (70, 28, 28)
            if selected
            else (0, 0, 0)
        )
        w = len(label) * 6 + 5
        draw_rectangle(x - 2, y - 2, x + w - 1, y + 7, *bg)
        draw_rect_outline(x - 2, y - 2, x + w - 1, y + 7, *col)
        draw_text_small(x, y, label, *col)

    def _draw_menu(self, idx):
        display.clear()
        tr, tg, tb = self._title_color()
        draw_text((WIDTH - len(self.title) * 9) // 2, 2, self.title, tr, tg, tb)
        draw_text_small(2, 16, "SCORE", 170, 170, 170)
        draw_text_small(39, 16, str(self.score)[:4], 255, 255, 255)
        draw_text_small(2, 24, "BEST", 170, 170, 170)
        best_txt = (str(self.best) + " " + self.best_name)[:8]
        draw_text_small(32, 24, best_txt, 255, 220, 80)
        self._draw_button(14, 31, "RETRY", idx == 0)
        self._draw_button(14, 40, "HISCR", idx == 1)
        self._draw_button(17, 49, "MENU", idx == 2)
        draw_rectangle(0, PLAY_HEIGHT, WIDTH - 1, HEIGHT - 1, 0, 0, 0)
        draw_text_small(1, PLAY_HEIGHT, "Z OK", 120, 120, 120)
        draw_text_small(WIDTH - 36, PLAY_HEIGHT, "C MENU", 120, 120, 120)
        display_flush()

    def _highscore_entries(self):
        if self.highscores is None:
            if self.game_name:
                return (
                    [(self.game_name, self.best, self.best_name)]
                    if self.best > 0
                    else []
                )
            return []
        return self.highscores.entries(self.game_name)

    def _draw_highscores(self, top=0):
        display.clear()
        rows = self._highscore_entries()
        title = ("HISCR " + str(self.game_name or ""))[:10]
        draw_text_small(2, 1, title, 255, 220, 80)
        if not rows:
            draw_text_small(8, 25, "NO SCORE", 140, 140, 140)
        max_top = max(0, len(rows) - 5)
        top = clamp(top, 0, max_top)
        for i, row in enumerate(rows[top : top + 5]):
            game, score, name = row
            y = 11 + i * 9
            rank = str(top + i + 1)
            col = (255, 255, 255)
            draw_text_small(1, y, rank, *col)
            name_x = 8 if len(rank) == 1 else 14
            draw_text_small(name_x, y, str(name or "---")[:3], 120, 180, 255)
            score_txt = str(score)[-6:]
            draw_text_small(WIDTH - len(score_txt) * 6 - 1, y, score_txt, *col)
        draw_menu_scrollbar(top, 5, len(rows))
        draw_rectangle(0, PLAY_HEIGHT, WIDTH - 1, HEIGHT - 1, 0, 0, 0)
        draw_text_small(1, PLAY_HEIGHT, "Z BACK", 120, 120, 120)
        draw_text_small(WIDTH - 36, PLAY_HEIGHT, "C MENU", 120, 120, 120)
        display_flush()

    def run(self):
        _wait_for_primary_release(self.joystick, timeout_ms=2000)
        idx = 0
        prev = -1
        last_move = ticks_ms()
        move_delay = 130

        while True:
            now = ticks_ms()
            if idx != prev:
                prev = idx
                self._draw_menu(idx)

            if ticks_diff(now, last_move) > move_delay:
                d = self.joystick.read_direction(
                    [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT],
                    debounce=True,
                )
                if d in (JOYSTICK_UP, JOYSTICK_LEFT):
                    idx = (idx - 1) % len(self.opts)
                    last_move = now
                elif d in (JOYSTICK_DOWN, JOYSTICK_RIGHT):
                    idx = (idx + 1) % len(self.opts)
                    last_move = now

            c_button, z_button = self.joystick.read_buttons()
            if c_button:
                _wait_for_primary_release(self.joystick)
                return "MENU"
            if z_button:
                _wait_for_primary_release(self.joystick)
                selected = self.opts[idx]
                if selected == "HISCR":
                    result = self._show_highscores_sync()
                    if result == "MENU":
                        return "MENU"
                    prev = -1
                else:
                    return selected

            sleep_ms(16)

    def _show_highscores_sync(self):
        self.hs_top = 0
        prev_top = -1
        last_move = ticks_ms()
        move_delay = 130
        while True:
            if self.hs_top != prev_top:
                prev_top = self.hs_top
                self._draw_highscores(self.hs_top)
            now = ticks_ms()
            if ticks_diff(now, last_move) > move_delay:
                d = self.joystick.read_direction(
                    [JOYSTICK_UP, JOYSTICK_DOWN], debounce=True
                )
                rows = self._highscore_entries()
                max_top = max(0, len(rows) - 5)
                if d == JOYSTICK_UP and self.hs_top > 0:
                    self.hs_top -= 1
                    last_move = now
                elif d == JOYSTICK_DOWN and self.hs_top < max_top:
                    self.hs_top += 1
                    last_move = now
            c_button, z_button = self.joystick.read_buttons()
            if c_button:
                _wait_for_primary_release(self.joystick)
                return "MENU"
            if z_button:
                _wait_for_primary_release(self.joystick)
                return "BACK"
            sleep_ms(16)

    async def run_async(self):
        """Async version of run() for use in pygbag/browser environments."""
        if asyncio is None:
            return self.run()
        await _wait_for_primary_release_async(self.joystick, timeout_ms=2000)
        idx = 0
        prev = -1
        last_move = ticks_ms()
        move_delay = 130
        while True:
            now = ticks_ms()
            if idx != prev:
                prev = idx
                self._draw_menu(idx)

            if ticks_diff(now, last_move) > move_delay:
                d = self.joystick.read_direction(
                    [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT],
                    debounce=True,
                )
                if d in (JOYSTICK_UP, JOYSTICK_LEFT):
                    idx = (idx - 1) % len(self.opts)
                    last_move = now
                elif d in (JOYSTICK_DOWN, JOYSTICK_RIGHT):
                    idx = (idx + 1) % len(self.opts)
                    last_move = now

            c_button, z_button = self.joystick.read_buttons()
            if c_button:
                await _wait_for_primary_release_async(self.joystick)
                return "MENU"
            if z_button:
                await _wait_for_primary_release_async(self.joystick)
                selected = self.opts[idx]
                if selected == "HISCR":
                    result = await self._show_highscores_async()
                    if result == "MENU":
                        return "MENU"
                    prev = -1
                else:
                    return selected

            await asyncio.sleep(0.016)

    async def _show_highscores_async(self):
        self.hs_top = 0
        prev_top = -1
        last_move = ticks_ms()
        move_delay = 130
        while True:
            if self.hs_top != prev_top:
                prev_top = self.hs_top
                self._draw_highscores(self.hs_top)
            now = ticks_ms()
            if ticks_diff(now, last_move) > move_delay:
                d = self.joystick.read_direction(
                    [JOYSTICK_UP, JOYSTICK_DOWN], debounce=True
                )
                rows = self._highscore_entries()
                max_top = max(0, len(rows) - 5)
                if d == JOYSTICK_UP and self.hs_top > 0:
                    self.hs_top -= 1
                    last_move = now
                elif d == JOYSTICK_DOWN and self.hs_top < max_top:
                    self.hs_top += 1
                    last_move = now
            c_button, z_button = self.joystick.read_buttons()
            if c_button:
                await _wait_for_primary_release_async(self.joystick)
                return "MENU"
            if z_button:
                await _wait_for_primary_release_async(self.joystick)
                return "BACK"
            await asyncio.sleep(0.016)


def draw_menu_scrollbar(top, view, total):
    """Draw the shared vertical scrollbar used by game and settings lists."""
    if total <= 0:
        return
    track_x = WIDTH - 1
    track_y = 2
    track_h = PLAY_HEIGHT - 4
    draw_line(track_x, track_y, track_x, track_y + track_h - 1, 35, 35, 35)
    if total <= view:
        draw_rectangle(
            track_x - 1, track_y, track_x, track_y + track_h - 1, 160, 160, 160
        )
        return
    thumb_h = max(4, int(track_h * view / total))
    thumb_h = min(track_h, thumb_h)
    max_top = max(1, total - view)
    thumb_y = track_y + int((track_h - thumb_h) * top / max_top)
    draw_rectangle(track_x - 1, thumb_y, track_x, thumb_y + thumb_h - 1, 220, 220, 220)


class GameSettingsMenu:
    """Small shared option editor for games that declare GameSettings entries."""

    def __init__(self, joystick, game_name, settings):
        self.joystick = joystick
        self.game_name = game_name
        self.settings = settings

    def _draw(self, idx):
        opts = self.settings.definitions_for(self.game_name)
        display.clear()
        draw_text(1, 1, self.game_name[:6], 120, 180, 255)
        # Keep the bottom HUD band free for button hints; option rows stay above it.
        view = 4
        top = 0
        if len(opts) > view:
            top = idx - view + 1
            if top < 0:
                top = 0
            max_top = len(opts) - view
            if top > max_top:
                top = max_top
        for row in range(view):
            opt_i = top + row
            if opt_i >= len(opts):
                break
            opt = opts[opt_i]
            y = 15 + row * 10
            col = (255, 255, 255) if opt_i == idx else (110, 110, 110)
            label = opt[1]
            choice_i = self.settings.choice_index(self.game_name, opt_i)
            choice_label = str(opt[2][choice_i][1])
            draw_text_small(2, y, label[:5], *col)
            val_x = max(31, WIDTH - len(choice_label) * 6 - 2)
            draw_text_small(val_x, y, choice_label, *col)
        draw_menu_scrollbar(top, view, len(opts))
        draw_text_small(1, PLAY_HEIGHT, "Z+", 120, 120, 120)
        draw_text_small(WIDTH - 36, PLAY_HEIGHT, "C BACK", 120, 120, 120)
        display_flush()

    async def run_async(self):
        opts = self.settings.definitions_for(self.game_name)
        if not opts:
            return
        idx = 0
        prev_idx = -1
        prev_values = None
        last_move = ticks_ms()
        move_delay = 135

        while True:
            values = tuple(
                self.settings.choice_index(self.game_name, i) for i in range(len(opts))
            )
            if idx != prev_idx or values != prev_values:
                prev_idx = idx
                prev_values = values
                self._draw(idx)

            now = ticks_ms()
            if ticks_diff(now, last_move) > move_delay:
                d = self.joystick.read_direction(
                    [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT],
                    debounce=True,
                )
                if d == JOYSTICK_UP and idx > 0:
                    idx -= 1
                    last_move = now
                elif d == JOYSTICK_DOWN and idx < len(opts) - 1:
                    idx += 1
                    last_move = now
                elif d == JOYSTICK_LEFT:
                    self.settings.cycle(self.game_name, idx, -1)
                    last_move = now
                elif d == JOYSTICK_RIGHT:
                    self.settings.cycle(self.game_name, idx, 1)
                    last_move = now

            c_button, z_button = self.joystick.read_buttons()
            if c_button:
                await _wait_for_primary_release_async(self.joystick)
                return
            if z_button:
                self.settings.cycle(self.game_name, idx, 1)
                await _wait_for_primary_release_async(self.joystick)

            await yield_runtime(0.016)
            if asyncio is None:
                sleep_ms(16)


class GameSelect:
    """Main game selector menu; choose a game to play with joystick."""

    # Tuple shape: (menu_id, game_class, flags). GAME_FLAG_HEAVY entries can be
    # hidden by runtime configuration for constrained targets.
    GAME_REGISTRY = (
        ("DEMOS", DemosGame, 0),
        ("2048", Game2048, GAME_FLAG_HEAVY),
        ("AIRHKY", AirHockeyGame, 0),
        ("ARENA", ArenaGame, 0),
        ("ARTILL", ArtilleryGame, 0),
        ("ASTRD", AsteroidGame, GAME_FLAG_HEAVY),
        ("BEAT", BeatGame, 0),
        ("BEJWL", BejeweledGame, GAME_FLAG_HEAVY),
        ("BILLI", BilliardsGame, 0),
        ("BLOBBY", BlobbyVolleyGame, 0),
        ("BOMBER", BomberGame, 0),
        ("BRKOUT", BreakoutGame, 0),
        ("BUBBLE", BubbleBobbleGame, 0),
        ("BTLZON", BattlezoneGame, 0),
        ("CAVEFL", CaveFlyGame, 0),
        ("CENTI", CentipedeGame, 0),
        ("CGOLG", CgolgGame, 0),
        ("CITY", CityChaseGame, 0),
        ("CLIMB", ClimberGame, 0),
        ("COLMNS", ColumnsGame, 0),
        ("CONNECT", ConnectGame, 0),
        ("DEFUSE", DefuseGame, 0),
        ("DEFEND", DefenderGame, 0),
        ("DIGDUG", DigDugGame, 0),
        ("DODGE", DodgeGame, 0),
        ("DONKEY", DonkeyGame, 0),
        ("DOOMLT", DoomLiteGame, GAME_FLAG_HEAVY),
        ("FLAPPY", FlappyGame, 0),
        ("FLOOD", FloodGame, 0),
        ("FIGHT", StreetFightersGame, 0),
        ("FROGGR", FroggerGame, 0),
        ("GALAGA", GalagaGame, 0),
        ("GALAXY", GalaxyGame, 0),
        ("GOLF", GolfGame, 0),
        ("INVADR", InvaderGame, 0),
        ("JOUST", JoustGame, 0),
        ("KEEN", KeenGame, 0),
        ("KERBAL", KerbalGame, GAME_FLAG_HEAVY),
        ("LANDER", LunarLanderGame, GAME_FLAG_HEAVY),
        ("LASER", LaserGame, 0),
        ("LIGHTS", LightsOutGame, 0),
        ("LOCO", LocoMotionGame, GAME_FLAG_HEAVY),
        ("LOOP", TimeLoopGame, 0),
        ("MAZE", MazeGame, GAME_FLAG_HEAVY),
        ("MARBLE", MarbleGame, 0),
        ("MINES", MinesGame, 0),
        ("MOON", MoonPatrolGame, 0),
        ("ORBIT", OrbitGame, 0),
        ("ORBTAL", OrbitalGame, 0),
        ("PACMAN", PacmanGame, 0),
        ("PAIRS", PairsGame, 0),
        ("PAPER", PaperboyGame, 0),
        ("PEGGLE", PeggleGame, 0),
        ("PICROS", PicrossGame, 0),
        ("PINBAL", PinballGame, 0),
        ("PITFAL", PitfallGame, 0),
        ("POLAR", PolarGame, 0),
        ("PONG", PongGame, 0),
        ("QIX", QixGame, GAME_FLAG_HEAVY),
        ("RACING", TopDownRacerGame, 0),
        ("RAYRCR", RayRacerGame, GAME_FLAG_HEAVY),
        ("REACT", ReactionGridGame, 0),
        ("REVRS", OthelloGame, GAME_FLAG_HEAVY),
        ("RTYPE", RTypeGame, GAME_FLAG_HEAVY),
        ("SABOTR", SabotrGame, 0),
        ("SIMON", SimonGame, 0),
        ("SIGNAL", SignalGame, 0),
        ("SLALOM", SlalomGame, 0),
        ("SNAKE", SnakeGame, 0),
        ("SOCCER", SoccerGame, 0),
        ("SONAR", SonarGame, 0),
        ("SOKO", SokobanGame, GAME_FLAG_HEAVY),
        ("STACK", StackerGame, 0),
        ("STKARC", StickArcherGame, 0),
        ("TAPPER", TapperGame, 0),
        ("TEMPEST", TempestGame, 0),
        ("TETRIS", TetrisGame, GAME_FLAG_HEAVY),
        ("TILT", TiltGame, 0),
        ("TRON", TronGame, 0),
        ("TWRDEF", TowerDefenseGame, 0),
        ("UFODEF", UFODefenseGame, GAME_FLAG_HEAVY),
        ("WIRES", WiresGame, 0),
        ("WORMS", WormsGame, 0),
        ("ZAXXON", ZaxxonGame, 0),
    )

    def __init__(self):
        refresh_runtime_config()
        self.joystick = Joystick()
        self.highscores = HighScores()
        self.settings = GameSettings()
        self.game_registry = tuple(
            g
            for g in self.GAME_REGISTRY
            if (CONFIG_ENABLE_HEAVY_GAMES or not (g[2] & GAME_FLAG_HEAVY))
            and _name_enabled(g[0], CONFIG_ENABLED_GAMES, CONFIG_DISABLED_GAMES)
        )
        self.sorted_games = tuple(g[0] for g in self.game_registry)
        self.selected = 0
        self.top = 0

    def _game_class(self, name):
        for game_name, cls, _flags in self.game_registry:
            if game_name == name:
                return cls
        return None

    def _make_game_instance(self, game_name, game_cls):
        ctx = {"game_name": game_name, "settings": self.settings.snapshot(game_name)}
        init_code = getattr(getattr(game_cls, "__init__", None), "__code__", None)
        # Older games still have __init__(self). Newer games accept ctx so they can
        # use the shared settings system without forcing every class to change.
        if init_code is not None and getattr(init_code, "co_argcount", 1) >= 2:
            return game_cls(ctx)
        return game_cls()

    def _draw_scrollbar(self, top, view, total):
        draw_menu_scrollbar(top, view, total)

    def _move_selection(self, delta, view, total):
        if total <= 0:
            return
        # Wrap around both ends so Up at the first entry lands on the last game.
        self.selected = (self.selected + delta) % total
        max_top = max(0, total - view)
        if self.selected < self.top:
            self.top = self.selected
        elif self.selected > self.top + view - 1:
            self.top = clamp(self.selected - view + 1, 0, max_top)

    async def _run_game_instance(self, game):
        # Prefer async loops when available so pygbag/browser frames keep rendering.
        if asyncio is not None and hasattr(game, "main_loop_async"):
            await game.main_loop_async(self.joystick)
        else:
            game.main_loop(self.joystick)
        await yield_runtime(0)

    async def _handle_game_over(self, game_name):
        # Highscore prompts live here so every game can just set global_score.
        best = self.highscores.best(game_name)
        best_name = self.highscores.best_name(game_name)
        if self.highscores.qualifies(game_name, global_score):
            entry_title = "NEW HS" if global_score > best else "SAVE"
            if asyncio is not None:
                initials = await InitialsEntryMenu(
                    self.joystick, global_score, best, best_name, entry_title
                ).run_async()
            else:
                initials = InitialsEntryMenu(
                    self.joystick, global_score, best, best_name, entry_title
                ).run()
            if initials:
                self.highscores.update(game_name, global_score, initials)

        best = self.highscores.best(game_name)
        best_name = self.highscores.best_name(game_name)
        title = globals().get("game_result", "LOST")
        if asyncio is not None:
            return await GameOverMenu(
                self.joystick,
                global_score,
                best,
                best_name,
                title,
                self.highscores,
                game_name,
            ).run_async()
        return GameOverMenu(
            self.joystick,
            global_score,
            best,
            best_name,
            title,
            self.highscores,
            game_name,
        ).run()

    async def run_game_selector(self):
        # wait for lingering button presses to prevent instant re-entry
        await _wait_for_primary_release_async(self.joystick, timeout_ms=2000)
        games = self.sorted_games
        prev_selected = -1
        prev_top = -1
        view = 4
        row_y = (3, 16, 29, 42)
        last_move = ticks_ms()
        move_delay = 140

        while True:
            now = ticks_ms()

            if self.selected != prev_selected or self.top != prev_top:
                prev_selected = self.selected
                prev_top = self.top
                display.clear()
                for i in range(view):
                    gi = self.top + i
                    if gi >= len(games):
                        break
                    name = games[gi]
                    is_sel = gi == self.selected
                    col = (255, 255, 255) if is_sel else (111, 111, 111)
                    y = row_y[i]
                    draw_text(6, y, name, *col)

                    hs = self.highscores.best(name)
                    hn = self.highscores.best_name(name)
                    hs_str = str(hs) + " " + str(hn)
                    hs_x = max(0, WIDTH - len(hs_str) * 6 - 3)
                    draw_text_small(hs_x, y + 8, hs_str, 120, 120, 0)

                self._draw_scrollbar(self.top, view, len(games))
                draw_text_small(1, PLAY_HEIGHT, "Z GO", 120, 120, 120)
                if self.settings.has_options(games[self.selected]):
                    draw_text_small(WIDTH - 30, PLAY_HEIGHT, "C OPT", 80, 180, 255)

                display_flush()

            if ticks_diff(now, last_move) > move_delay:
                d = self.joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN])
                if d == JOYSTICK_UP:
                    self._move_selection(-1, view, len(games))
                    last_move = now
                elif d == JOYSTICK_DOWN:
                    self._move_selection(1, view, len(games))
                    last_move = now

            c_button, z_button = self.joystick.read_buttons()
            if z_button:
                await _wait_for_primary_release_async(self.joystick)
                return games[self.selected]
            if c_button:
                game_name = games[self.selected]
                await _wait_for_primary_release_async(self.joystick)
                if self.settings.has_options(game_name):
                    await GameSettingsMenu(
                        self.joystick, game_name, self.settings
                    ).run_async()
                    prev_selected = -1
                    prev_top = -1
                else:
                    return game_name

            await yield_runtime(0.030)
            if asyncio is not None:
                continue
            sleep_ms(30)

    async def run(self):
        global game_over, global_score, game_result

        while True:
            game_name = await self.run_game_selector()

            # retry loop
            while True:
                game_over = False
                game_result = "LOST"
                global_score = 0

                game_cls = self._game_class(game_name)
                if game_cls is None:
                    break
                game = self._make_game_instance(game_name, game_cls)
                await self._run_game_instance(game)

                if game_over:
                    if await self._handle_game_over(game_name) == "RETRY":
                        continue
                break


# ---------- Intro ----------
async def _show_intro():
    """Show logo.png on desktop/web or a colour-fade animation on MicroPython."""

    async def _yield():
        await yield_runtime(0)

    def _intro_key_pressed():
        if IS_MICROPYTHON:
            return False
        try:
            import pygame  # type: ignore

            pygame.event.pump()
            for event in pygame.event.get():
                if event.type == pygame.KEYDOWN:
                    return True
                if event.type == pygame.QUIT:
                    raise RestartProgram()
            keys = pygame.key.get_pressed()
            for key in (
                pygame.K_SPACE,
                pygame.K_RETURN,
                pygame.K_ESCAPE,
                pygame.K_z,
                pygame.K_x,
                pygame.K_UP,
                pygame.K_DOWN,
                pygame.K_LEFT,
                pygame.K_RIGHT,
            ):
                if keys[key]:
                    return True
        except RestartProgram:
            raise
        except Exception:
            pass
        return False

    def _intro_skip_requested(joystick=None):
        if _intro_key_pressed():
            return True
        if joystick is not None:
            try:
                c_btn, z_btn = joystick.read_buttons()
                if c_btn or z_btn:
                    return True
            except RestartProgram:
                raise
            except Exception:
                pass
        return False

    def _draw_png_logo(path):
        try:
            import struct
            import zlib

            with open(path, "rb") as fh:
                data = fh.read()
            if data[:8] != b"\x89PNG\r\n\x1a\n":
                return False
            pos = 8
            width = height = color_type = None
            compressed = []
            while pos + 8 <= len(data):
                length = struct.unpack(">I", data[pos : pos + 4])[0]
                kind = data[pos + 4 : pos + 8]
                chunk = data[pos + 8 : pos + 8 + length]
                pos += 12 + length
                if kind == b"IHDR":
                    (
                        width,
                        height,
                        bit_depth,
                        color_type,
                        compression,
                        filter_method,
                        interlace,
                    ) = struct.unpack(">IIBBBBB", chunk)
                    if (
                        bit_depth != 8
                        or compression != 0
                        or filter_method != 0
                        or interlace != 0
                        or color_type not in (2, 6)
                    ):
                        return False
                elif kind == b"IDAT":
                    compressed.append(chunk)
                elif kind == b"IEND":
                    break
            if not width or not height or not compressed:
                return False
            channels = 4 if color_type == 6 else 3
            row_len = width * channels
            raw = zlib.decompress(b"".join(compressed))
            rows = []
            i = 0
            prev = [0] * row_len
            for _ in range(height):
                filt = raw[i]
                i += 1
                row = list(raw[i : i + row_len])
                i += row_len
                for x in range(row_len):
                    left = row[x - channels] if x >= channels else 0
                    up = prev[x]
                    up_left = prev[x - channels] if x >= channels else 0
                    if filt == 1:
                        row[x] = (row[x] + left) & 255
                    elif filt == 2:
                        row[x] = (row[x] + up) & 255
                    elif filt == 3:
                        row[x] = (row[x] + ((left + up) >> 1)) & 255
                    elif filt == 4:
                        p = left + up - up_left
                        pa = abs(p - left)
                        pb = abs(p - up)
                        pc = abs(p - up_left)
                        row[x] = (
                            row[x]
                            + (
                                left
                                if pa <= pb and pa <= pc
                                else up
                                if pb <= pc
                                else up_left
                            )
                        ) & 255
                rows.append(row)
                prev = row
            for y in range(HEIGHT):
                sy = (y * height) // HEIGHT
                row = rows[sy]
                for x in range(WIDTH):
                    sx = ((x * width) // WIDTH) * channels
                    r = row[sx]
                    g = row[sx + 1]
                    b = row[sx + 2]
                    if channels == 4:
                        a = row[sx + 3]
                        r = (r * a) // 255
                        g = (g * a) // 255
                        b = (b * a) // 255
                    display.set_pixel(x, y, r, g, b)
            return True
        except Exception:
            return False

    display.clear()
    shown = False
    joystick = None if IS_MICROPYTHON else Joystick()
    if not IS_MICROPYTHON:
        try:
            import os as _os_intro

            import pygame  # type: ignore

            _candidates = []
            for _base in (
                _os_intro.getcwd(),
                _os_intro.path.dirname(_os_intro.path.abspath(__file__)),
                _os_intro.path.dirname(_os_intro.path.abspath(sys.argv[0]))
                if getattr(sys, "argv", None)
                else "",
            ):
                if _base:
                    _lp = _os_intro.path.join(_base, "logo.png")
                    if _lp not in _candidates:
                        _candidates.append(_lp)
            img = None
            for _lp in _candidates:
                try:
                    img = pygame.image.load(_lp)
                    break
                except Exception:
                    pass
            if img is not None:
                blit_image = getattr(display, "blit_image", None)
                if blit_image is None or not blit_image(img):
                    img = pygame.transform.scale(img, (WIDTH, HEIGHT))
                    for y in range(HEIGHT):
                        for x in range(WIDTH):
                            c = img.get_at((x, y))
                            display.set_pixel(x, y, c[0], c[1], c[2])
                display_flush()
                await _yield()
                if _intro_skip_requested(joystick):
                    display.clear()
                    display_flush()
                    await _yield()
                    return
                shown = True
            # The pure-Python PNG decoder is a fallback for unusual desktop
            # ports only. PyGame's native loader is substantially faster in
            # WebAssembly and avoids thousands of Python-level pixel writes.
            if not shown:
                for _lp in _candidates:
                    if _draw_png_logo(_lp):
                        display_flush()
                        await _yield()
                        if _intro_skip_requested(joystick):
                            display.clear()
                            display_flush()
                            await _yield()
                            return
                        shown = True
                        break
        except Exception:
            pass

    if not shown:
        colours = [(255, 60, 0), (255, 200, 0), (0, 180, 255), (0, 220, 80)]
        strip_h = HEIGHT // len(colours)
        if IS_MICROPYTHON:
            # RP2040 startup should reach the menu quickly; avoid full-screen fades.
            for ci, col in enumerate(colours):
                y0 = ci * strip_h
                y1 = y0 + strip_h if ci < len(colours) - 1 else HEIGHT
                for y in range(y0, y1):
                    for x in range(WIDTH):
                        display.set_pixel(x, y, col[0], col[1], col[2])
            display_flush()
            await _yield()
        else:
            # Desktop/web keeps the smoother fade.
            for step in range(32):
                t = (step + 1) / 32.0
                for ci, col in enumerate(colours):
                    y0 = ci * strip_h
                    y1 = y0 + strip_h if ci < len(colours) - 1 else HEIGHT
                    for y in range(y0, y1):
                        for x in range(WIDTH):
                            display.set_pixel(
                                x, y, int(col[0] * t), int(col[1] * t), int(col[2] * t)
                            )
                display_flush()
                await _yield()
                await sleep_ms_async(30)
                if _intro_skip_requested(joystick):
                    display.clear()
                    display_flush()
                    await _yield()
                    return
                try:
                    maybe_collect(120)
                except Exception:
                    pass
        draw_centered_text_lines(("DIY", "ARCADE"), start_y=18, line_height=12)
        display_flush()
        await _yield()

        if IS_MICROPYTHON:
            await sleep_ms_async(900)
            display.clear()
            display_flush()
            await _yield()
            return

    # On hardware, never poll buttons during intro startup.
    if IS_MICROPYTHON:
        display.clear()
        display_flush()
        await _yield()
        return

    # Keep desktop/web startup interruptible.
    # The HTML loader already provides a branded browser splash screen. Keep
    # the in-canvas logo brief so web users reach the menu without a 3s pause.
    intro_hold_ms = 650 if IS_WEB else 250 if IS_MICROPYTHON else 3000
    deadline = ticks_add(ticks_ms(), intro_hold_ms)
    while ticks_diff(deadline, ticks_ms()) > 0:
        if _intro_skip_requested(joystick):
            if joystick is not None:
                _wait_for_primary_release(joystick, timeout_ms=500)
            break
        await _yield()
        await sleep_ms_async(10 if IS_MICROPYTHON else 15)

    display.clear()
    display_flush()
    await _yield()


async def _start_display_runtime():
    """Bring up the display and optional framebuffer before intro/menu code runs."""
    try:
        gc.collect()
    except Exception:
        pass
    _boot_log("before display.start")
    display.start()
    _boot_log("after display.start")
    try:
        refresh_runtime_config()
        init_buffered_display()
    except Exception:
        pass
    _boot_log("buffered on" if USE_BUFFERED_DISPLAY else "buffered off")
    reset_menu_display(0)
    await yield_runtime(0)


async def _recover_to_menu(delay_ms=800):
    """Show an error marker, then restore enough state for the selector."""
    display.clear()
    draw_text(1, 20, "ERR", 255, 0, 0)
    await sleep_ms_async(delay_ms)
    reset_menu_display(0)
    maybe_collect(1)
    await yield_runtime(0)


# ---------- Main ----------
async def main():
    await _start_display_runtime()

    try:
        await _show_intro()
    except RestartProgram:
        reset_menu_display(0)
        await yield_runtime(0)

    selector = GameSelect()
    while True:
        await yield_runtime(0)
        try:
            await selector.run()
        except RestartProgram:
            reset_menu_display(0)
            continue
        except Exception as e:
            # Failsafe: show simple error marker and reset to menu
            print("Error:", e)
            await _recover_to_menu()


if __name__ == "__main__":
    if asyncio is not None:
        asyncio.run(main())
    else:
        import sys as _sys

        print("asyncio unavailable", file=_sys.stderr)
