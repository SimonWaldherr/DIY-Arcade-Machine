"""Peggle shot physics and shared game flow regression tests."""

import unittest
from unittest.mock import patch

import arcade_app as app


class Joystick:
    def read_buttons(self):
        return False, False

    def read_direction(self, directions, debounce=True):
        return None


class PeggleTests(unittest.TestCase):
    def test_launch_limits_and_centered_start(self):
        game = app.PeggleGame()
        self.assertTrue(game._launch())
        self.assertEqual(game.ball[2], 0)
        self.assertEqual(game.shots, 7)
        self.assertFalse(game._launch())
        game.ball = None
        game.shots = 0
        self.assertFalse(game._launch())

    def test_preview_matches_flight_without_mutating_board(self):
        for aim in range(7):
            game = app.PeggleGame()
            game.pegs = []
            game.aim = aim
            points = game._aim_points()
            self.assertIsNone(game.ball)
            self.assertEqual(game.shots, 8)
            game._launch()
            actual = []
            for frame in range(18):
                game._advance_ball()
                if game.ball is None:
                    break
                if frame % 2 == 0:
                    actual.append(tuple(int(v) for v in game.ball[:2]))
            self.assertEqual(points, actual)

    def test_peg_reflects_from_side_and_scores_only_once(self):
        game = app.PeggleGame()
        game.pegs = [[32, 25, 1, 1]]
        game.ball = [27.5, 25, 3, 0]
        game._advance_ball()
        self.assertLess(game.ball[2], 0)
        self.assertEqual(game.score, 100)
        game._advance_ball()
        self.assertEqual(game.score, 100)

    def test_fast_ball_hits_peg_and_blue_scores_less(self):
        game = app.PeggleGame()
        game.pegs = [[32, 25, 0, 1]]
        game.ball = [26, 25, 12, 0]
        game._advance_ball()
        self.assertEqual(game.score, 25)
        self.assertEqual(game.pegs[0][3], 0)

    def test_bucket_catch_refunds_one_shot_but_miss_does_not(self):
        for x, shots, score in ((32, 8, 50), (3, 7, 0)):
            game = app.PeggleGame()
            game.shots = 7
            game.ball = [x, 53.8, 0, 2]
            game._advance_ball()
            self.assertIsNone(game.ball)
            self.assertEqual(game.shots, shots)
            self.assertEqual(game.score, score)
            game._advance_ball()
            self.assertEqual(game.shots, shots)

    def test_all_maps_and_aims_finish_a_shot(self):
        for index in range(3):
            for aim in range(7):
                game = app.PeggleGame({'settings': {'map': index}})
                self.assertGreater(game._orange_left(), 0)
                game.aim = aim
                game._launch()
                for _ in range(500):
                    game._advance_ball()
                    if game.ball is None:
                        break
                    self.assertGreaterEqual(game.ball[1], 2)
                self.assertIsNone(game.ball)

    def test_final_orange_waits_for_bucket_and_win_beats_empty_ammo(self):
        game = app.PeggleGame()
        with patch.object(app, 'begin_game'), patch.object(app, 'set_game_over_score') as finish, patch.object(game, '_draw'):
            step = game._build_step(Joystick())
            game.pegs = []
            game.shots = 0
            game.ball = [32, 20, 0, 1]
            self.assertTrue(step())
            finish.assert_not_called()
            game.ball = [32, 53.8, 0, 2]
            self.assertFalse(step())
            finish.assert_called_once_with(150, won=True)

    def test_empty_ammo_with_orange_remaining_loses(self):
        game = app.PeggleGame()
        with patch.object(app, 'begin_game'), patch.object(app, 'set_game_over_score') as finish:
            step = game._build_step(Joystick())
            game.shots = 0
            self.assertFalse(step())
            finish.assert_called_once_with(0)


if __name__ == '__main__':
    unittest.main()
