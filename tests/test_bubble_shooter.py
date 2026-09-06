"""Bubble Shooter grid, collision, scoring and input regressions."""
import unittest
from unittest.mock import patch

import arcade_app as app
from test_arcade_app import _DisplayStub, _JoystickStub


class BubbleShooterTests(unittest.TestCase):
    def test_registry_and_playable_frame(self):
        self.assertIn(('BUBSHO', app.BubbleShooterGame, 0), app.GameSelect.GAME_REGISTRY)
        with patch.object(app, 'display', _DisplayStub()), patch.object(app, 'begin_game'):
            game = app.BubbleShooterGame()
            joystick = _JoystickStub()
            step = game._build_step(joystick)
            self.assertTrue(step())
            joystick.buttons = (True, False)
            self.assertFalse(step())

    def test_hex_neighbors_are_symmetric_and_geometrically_adjacent(self):
        game = app.BubbleShooterGame()
        for row in range(game.ROWS):
            for col in range(10 - row % 2):
                cell = row, col
                x, y = game._center(cell)
                for neighbor in game._neighbors(cell):
                    self.assertIn(cell, game._neighbors(neighbor))
                    nx, ny = game._center(neighbor)
                    self.assertIn((nx - x) ** 2 + (ny - y) ** 2, (34, 36))

    def test_match_drops_only_unsupported_bubbles_and_refreshes_colors(self):
        game = app.BubbleShooterGame()
        game.board = {(0, 0): 0, (0, 1): 0, (1, 0): 0,
                      (2, 0): 1, (3, 0): 2, (0, 8): 3, (1, 8): 3}
        game.next_color = 0
        game._resolve((1, 0))
        self.assertEqual(game.board, {(0, 8): 3, (1, 8): 3})
        self.assertEqual(game.score, 70)
        self.assertEqual((game.current, game.next_color), (3, 3))
        self.assertEqual(game.misses, 0)

    def test_pair_does_not_pop_and_fifth_miss_lowers_ceiling(self):
        game = app.BubbleShooterGame()
        game.board = {(0, 0): 0, (0, 1): 0}
        game.misses = 4
        game._resolve((0, 1))
        self.assertEqual(len(game.board), 2)
        self.assertEqual(game.score, 0)
        self.assertEqual((game.misses, game.ceiling), (0, 5))

    def test_clear_board_wins_and_danger_line_loses(self):
        for win in (True, False):
            game = app.BubbleShooterGame()
            with patch.object(app, 'begin_game'), patch.object(app, 'set_game_over_score') as finish:
                step = game._build_step(_JoystickStub())
                if win:
                    game.board = {(0, 0): 0, (0, 1): 0, (1, 0): 0}
                    game._resolve((1, 0))
                else:
                    game.board = {(8, 0): 0}
                    game._resolve((8, 0))
                self.assertFalse(step())
                finish.assert_called_once_with(30 if win else 0, won=win)

    def test_projectile_reflects_both_walls(self):
        game = app.BubbleShooterGame()
        for x, vx in ((3.1, -3), (59.9, 3)):
            ball = [x, 40, vx, -1]
            game._move_projectile(ball)
            self.assertGreaterEqual(ball[0], 3)
            self.assertLessEqual(ball[0], 60)
            self.assertEqual(ball[2], -vx)

    def test_attachment_does_not_overwrite_and_full_neighborhood_loses(self):
        game = app.BubbleShooterGame()
        game.board = {(0, 4): 0}
        game.ball = [29, 13, 0, -3, 1]
        game._attach((0, 4))
        self.assertEqual(game.board[(0, 4)], 0)
        self.assertEqual(len(game.board), 2)
        self.assertIsNone(game.ball)
        game.board = {p: 0 for p in game._neighbors((3, 3))}
        game.board[(3, 3)] = 0
        original = dict(game.board)
        game.ball = [25, 25, 0, -3, 1]
        game._attach((3, 3))
        self.assertTrue(game.lost)
        self.assertEqual(game.board, original)

    def test_every_angle_finishes_and_held_fire_does_not_relaunch(self):
        for aim in range(13):
            game = app.BubbleShooterGame()
            game.aim = aim
            self.assertTrue(game._launch())
            self.assertFalse(game._launch())
            for _ in range(100):
                game._advance()
                if game.ball is None:
                    break
            self.assertIsNone(game.ball)
        with patch.object(app, 'begin_game'), patch.object(app.BubbleShooterGame, '_draw'):
            game = app.BubbleShooterGame()
            joystick = _JoystickStub(buttons=(False, True))
            step = game._build_step(joystick)
            game.board = {(0, 4): 0, (0, 5): 1}
            game.current = 2
            step()
            for _ in range(100):
                game._advance()
            self.assertIsNone(game.ball)
            step()
            self.assertIsNone(game.ball)
            joystick.buttons = (False, False)
            step()
            joystick.buttons = (False, True)
            step()
            self.assertIsNotNone(game.ball)


if __name__ == '__main__':
    unittest.main()
