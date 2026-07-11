"""Portable logic tests that do not require a display or audio device."""

import unittest

import arcade_app as app


class _DisplayStub:
    def clear(self):
        pass

    def fill_rect(self, *args):
        pass

    def set_pixel(self, *args):
        pass

    def show(self):
        pass


class _CountingDisplay(_DisplayStub):
    def __init__(self):
        self.pixel_writes = 0

    def set_pixel(self, *args):
        self.pixel_writes += 1

    def fill_rect(self, x1, y1, x2, y2, *args):
        self.pixel_writes += max(0, x2 - x1 + 1) * max(0, y2 - y1 + 1)


class _JoystickStub:
    def __init__(self, direction=None, buttons=(False, False)):
        self.direction = direction
        self.buttons = buttons

    def read_direction(self, possible_directions, debounce=True):
        if self.direction in possible_directions:
            return self.direction
        return None

    def read_buttons(self):
        return self.buttons


class ArcadeGameTests(unittest.TestCase):
    @staticmethod
    def _runs(values):
        runs = []
        current = 0
        for value in values:
            if value:
                current += 1
            elif current:
                runs.append(current)
                current = 0
        if current:
            runs.append(current)
        return "".join(str(run) for run in runs) or "0"

    def setUp(self):
        self.original_display = app.display
        self.original_play_sound = app.play_sound
        self.original_game_state = (
            app.game_over,
            app.global_score,
            app.game_result,
        )
        app.display = _DisplayStub()
        app.play_sound = lambda kind, tone=0: None

    def tearDown(self):
        app.display = self.original_display
        app.play_sound = self.original_play_sound
        app.game_over, app.global_score, app.game_result = self.original_game_state

    def test_new_games_are_registered_once(self):
        registry = app.GameSelect.GAME_REGISTRY
        names = [entry[0] for entry in registry]

        self.assertEqual(len(names), len(set(names)))
        self.assertIn(("LIGHTS", app.LightsOutGame, 0), registry)
        self.assertIn(("PICROS", app.PicrossGame, 0), registry)
        self.assertIn(("REACT", app.ReactionGridGame, 0), registry)
        self.assertIn(("SLALOM", app.SlalomGame, 0), registry)
        self.assertIn(("DIGDUG", app.DigDugGame, 0), registry)
        self.assertIn(("JOUST", app.JoustGame, 0), registry)
        self.assertIn("DIGDUG", app.DemosGame.GAME_DEMOS)
        self.assertIn("JOUST", app.DemosGame.GAME_DEMOS)
        self.assertEqual(app.DemosGame.GAME_CLASS_NAMES["DIGDUG"], "DigDugGame")
        self.assertEqual(app.DemosGame.GAME_CLASS_NAMES["JOUST"], "JoustGame")

    def test_new_classics_build_a_playable_frame(self):
        joystick = _JoystickStub()
        for game_type in (app.DigDugGame, app.JoustGame):
            game = game_type()
            step = game._build_step(joystick)

            self.assertTrue(step())

    def test_content_blocklists_hide_games_and_demos(self):
        disabled_games = app.CONFIG_DISABLED_GAMES
        disabled_demos = app.CONFIG_DISABLED_DEMOS
        try:
            app.CONFIG_DISABLED_GAMES = ("DIGDUG",)
            app.CONFIG_DISABLED_DEMOS = ("MATRIX",)

            selector = app.GameSelect()
            demos = app.DemosGame()

            self.assertNotIn("DIGDUG", selector.sorted_games)
            self.assertIn("JOUST", selector.sorted_games)
            self.assertNotIn("MATRIX", demos.demos)
        finally:
            app.CONFIG_DISABLED_GAMES = disabled_games
            app.CONFIG_DISABLED_DEMOS = disabled_demos

    def test_lights_out_toggle_is_reversible(self):
        game = app.LightsOutGame()
        before = game.grid[:]

        game._flip_pattern(2, 2)
        changed = sum(
            old_value != new_value for old_value, new_value in zip(before, game.grid)
        )
        self.assertEqual(changed, 5)

        game._flip_pattern(2, 2)
        self.assertEqual(game.grid, before)

    def test_lights_out_scramble_is_not_empty(self):
        for _unused in range(20):
            game = app.LightsOutGame()
            self.assertFalse(game._is_solved())
            self.assertTrue(game.needs_redraw)

    def test_reaction_target_changes_and_stays_in_grid(self):
        game = app.ReactionGridGame()

        for _unused in range(25):
            previous = game.target
            game._spawn_target()
            self.assertNotEqual(game.target, previous)
            self.assertGreaterEqual(game.target, 0)
            self.assertLess(game.target, game.GRID_W * game.GRID_H)

    def test_grid_games_do_not_redraw_without_input(self):
        joystick = _JoystickStub()
        for game_type in (
            app.LightsOutGame,
            app.ReactionGridGame,
            app.PicrossGame,
        ):
            game = game_type()
            step = game._build_step(joystick)
            self.assertFalse(game.needs_redraw)

            self.assertTrue(step())
            self.assertFalse(game.needs_redraw)

    def test_shared_grid_cursor_clamps_to_board(self):
        game = app.LightsOutGame()
        game.cursor_x = 0
        game.cursor_y = 0
        game.last_move = app.ticks_add(app.ticks_ms(), -1000)

        game._move_cursor(_JoystickStub(app.JOYSTICK_LEFT))

        self.assertEqual((game.cursor_x, game.cursor_y), (0, 0))

    def test_picross_clues_and_completed_pattern(self):
        game = app.PicrossGame()
        for pattern, row_clues, column_clues in game.PUZZLES:
            self.assertEqual(
                tuple(self._runs(value == "1" for value in row) for row in pattern),
                row_clues,
            )
            self.assertEqual(
                tuple(
                    self._runs(pattern[y][x] == "1" for y in range(game.GRID_H))
                    for x in range(game.GRID_W)
                ),
                column_clues,
            )

        game.grid = [1 if value == "1" else 0 for row in game.pattern for value in row]

        self.assertTrue(game._matches_pattern())
        game.grid[0] = 1 - game.grid[0]
        self.assertFalse(game._matches_pattern())

    def test_slalom_gate_pass_and_collision(self):
        game = app.SlalomGame()
        game.snow = []
        center = app.WIDTH // 2
        game.x = center
        game.gates = [[game.PLAYER_Y - 0.1, center, 20, False]]

        self.assertTrue(game._advance_gates(False))
        self.assertEqual(game.score, 1)

        app.game_over = False
        game.score = 0
        game.x = 2.0
        game.gates = [[game.PLAYER_Y - 0.1, center, 20, False]]

        self.assertFalse(game._advance_gates(False))
        self.assertTrue(app.game_over)

    def test_slalom_keeps_gate_list_and_limits_turns(self):
        game = app.SlalomGame()
        game.x = app.WIDTH // 2
        game.gates = [[0.0, app.WIDTH // 2, 20, False]]
        gates = game.gates

        self.assertTrue(game._advance_gates(False))
        self.assertIs(game.gates, gates)

        game._spawn_gate(-5.0)

        self.assertIs(game.gates, gates)
        self.assertLessEqual(
            abs(game.gates[-1][1] - game.gates[-2][1]),
            game.MAX_GATE_SHIFT,
        )

    def test_doom_ray_buffer_matches_the_target_stride(self):
        game = app.DoomLiteGame()

        self.assertEqual(game.render_stride, 1 if app.IS_DESKTOP else 2)
        game._render()

        self.assertEqual(len(game.zbuf), app.WIDTH)
        self.assertTrue(all(distance > 0 for distance in game.zbuf))

    def test_doom_quad_burst_hits_distinct_visible_enemies(self):
        game = app.DoomLiteGame()
        game.px = 2.5
        game.py = 2.5
        game.ang = 128
        game.score = 0
        game.quad_timer = 60
        game.enemies = [
            [1.5, 2.43, 1, 60, 0, 0, 0.0, 0.0, 0, 1, 0],
            [1.5, 2.50, 1, 60, 0, 0, 0.0, 0.0, 0, 1, 0],
            [1.5, 2.57, 1, 60, 0, 0, 0.0, 0.0, 0, 1, 0],
        ]

        hits = game._shoot()

        self.assertEqual(hits, 3)
        self.assertTrue(all(enemy[2] <= 0 for enemy in game.enemies))
        self.assertGreater(game.score, 0)

    def test_doom_enemy_state_gains_strafe_and_muzzle_slots(self):
        game = app.DoomLiteGame()
        game.frame = 2
        game.wave = 3
        enemy = [1.5, 2.5, 2, 60, 1, 0, 0.0, 0.0, 0]
        game.enemies = [enemy]

        game._update_enemies()

        self.assertEqual(len(enemy), 11)
        self.assertIn(enemy[9], (-1, 0, 1))

    def test_doom_shared_frame_advances_the_simulation(self):
        game = app.DoomLiteGame()
        game.enemies = []
        frame = game.frame

        self.assertTrue(game._advance_game_frame(_JoystickStub()))
        self.assertEqual(game.frame, frame + 1)
        self.assertGreater(len(game.enemies), 0)

    def test_demo_heavy_effects_use_target_aware_frame_pacing(self):
        demo = app.DemosGame()
        original_web = app.IS_WEB
        try:
            app.IS_WEB = True
            self.assertEqual(
                demo._frame_ms_for_demo("MANDEL"),
                demo.TARGET_HEAVY_FRAME_MS,
            )
            self.assertEqual(demo._frame_ms_for_demo("MATRIX"), demo.FRAME_MS)
        finally:
            app.IS_WEB = original_web

    def test_demo_animation_work_lists_are_reused(self):
        demo = app.DemosGame()

        demo._ants_init()
        ants_previous = demo._ants_prev
        ants_changed = demo._ants_changed
        demo._ants_step()
        self.assertIs(demo._ants_prev, ants_previous)
        self.assertIs(demo._ants_changed, ants_changed)
        self.assertEqual(len(ants_previous), len(demo._ants))

        demo._radar_init()
        radar_blips = demo._radar_blips
        radar_rings = demo._radar_rings
        radar_blips.append([app.WIDTH // 2, app.HEIGHT // 2, 40])
        demo._radar_step()
        self.assertIs(demo._radar_blips, radar_blips)
        self.assertIs(demo._radar_rings, radar_rings)
        self.assertEqual(tuple(len(ring) for ring in radar_rings), (32, 32, 32))

        demo._firwrk_init()
        rockets = demo._fw_rockets
        particles = demo._fw_particles
        rockets.append([32.0, 25.0, -0.1, 25.0, 0])
        demo._firwrk_step()
        self.assertIs(demo._fw_rockets, rockets)
        self.assertIs(demo._fw_particles, particles)
        self.assertLessEqual(len(particles), demo.MAX_FIREWORK_PARTICLES)

    def test_demo_pendulum_trail_keeps_its_storage(self):
        demo = app.DemosGame()
        demo._pendul_init()
        trail = demo._pend_trail

        for _unused in range(52):
            demo._pendul_step()

        self.assertIs(demo._pend_trail, trail)
        self.assertEqual(len(trail), 48)

    def test_air_hockey_restores_only_moving_regions_after_first_frame(self):
        display = _CountingDisplay()
        app.display = display
        game = app.AirHockeyGame({"settings": {"players": "two"}})

        game._draw()
        initial_writes = display.pixel_writes
        display.pixel_writes = 0
        game.left_x += game.MALLET_SPEED
        game.puck_x += game.puck_vx
        game.puck_y += game.puck_vy
        game._draw()

        self.assertTrue(game._rink_ready)
        self.assertLess(display.pixel_writes, initial_writes // 3)

    def test_worms_reuses_static_terrain_between_turn_updates(self):
        display = _CountingDisplay()
        app.display = display
        game = app.WormsGame({"settings": {"players": "two", "worms": 2}})

        game._draw()
        initial_writes = display.pixel_writes
        display.pixel_writes = 0
        game.angle += 2
        game._draw()

        self.assertFalse(game._terrain_dirty)
        self.assertLess(display.pixel_writes, initial_writes // 3)

    def test_tron_two_player_resolves_same_cell_collision_as_draw(self):
        game = app.TronGame({"settings": {"players": "two"}})
        game.trail = bytearray(app.WIDTH * app.PLAY_HEIGHT)
        game.head_x, game.head_y, game.direction = 20, 20, game.DIR_RIGHT
        game.enemy_x, game.enemy_y, game.enemy_dir = 22, 20, game.DIR_LEFT
        game._occupy(game.head_x, game.head_y)
        game._occupy(game.enemy_x, game.enemy_y)

        p1_alive, p2_alive = game._step_two_player(False, False)

        self.assertFalse(p1_alive)
        self.assertFalse(p2_alive)
        self.assertEqual((game.head_x, game.head_y), (20, 20))
        self.assertEqual((game.enemy_x, game.enemy_y), (22, 20))

    def test_tron_two_player_allows_both_turbo_buttons(self):
        game = app.TronGame({"settings": {"players": "two"}})
        game.trail = bytearray(app.WIDTH * app.PLAY_HEIGHT)
        game.head_x, game.head_y, game.direction = 10, 20, game.DIR_RIGHT
        game.enemy_x, game.enemy_y, game.enemy_dir = 50, 20, game.DIR_LEFT
        game._occupy(game.head_x, game.head_y)
        game._occupy(game.enemy_x, game.enemy_y)

        p1_alive, p2_alive = game._step_two_player(False, True)

        self.assertTrue(p1_alive)
        self.assertTrue(p2_alive)
        self.assertEqual((game.head_x, game.head_y), (11, 20))
        self.assertEqual((game.enemy_x, game.enemy_y), (48, 20))


if __name__ == "__main__":
    unittest.main()
