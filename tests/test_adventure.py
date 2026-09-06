"""Story progression, input handling and rendering contracts for HARBOR."""
import unittest

import arcade_app as app
from test_arcade_app import _DisplayStub, _JoystickStub, _CountingDisplay


class HarborAdventureTests(unittest.TestCase):
    def setUp(self):
        self.saved = app.display, app.game_over, app.global_score, app.game_result
        app.display = _DisplayStub()
        self.game = app.HarborAdventureGame()
        self.game.pages = []

    def tearDown(self):
        app.display, app.game_over, app.global_score, app.game_result = self.saved

    def act(self, target):
        self.game._interact(target)
        self.game.pages = []

    def _complete_main_story(self, expected_score=240):
        game = self.game
        self.act("crate")
        self.act("rope")
        self.act("inn")
        self.act("keeper")
        self.assertTrue(game.choices)
        game._talk(1)
        self.assertIn("LINSE", game.inventory)
        self.assertNotIn("MUENZE", game.inventory)
        self.act("hook")
        game._inventory_click(game.inventory.index("SEIL"))
        game._inventory_click(game.inventory.index("HAKEN"))
        self.assertEqual(game.selected, "ANKER")
        self.assertNotIn("SEIL", game.inventory)
        self.assertNotIn("HAKEN", game.inventory)
        self.act("harbor")
        game._inventory_click(game.inventory.index("ANKER"))
        self.act("grate")
        self.assertIn("SCHLUESSEL", game.inventory)
        game._inventory_click(game.inventory.index("SCHLUESSEL"))
        self.act("tower")
        self.assertEqual(game.room, 2)
        self.assertTrue(game.door_open)
        game._inventory_click(game.inventory.index("LINSE"))
        self.act("lamp")
        self.act("crank")
        self.assertTrue(game.won)
        self.assertEqual(game.score, expected_score)
        self.assertEqual(game.inventory, [])
        score = game.score
        self.act("crank")
        self.assertEqual(game.score, score)

    def test_story_can_be_completed_and_awards_win(self):
        self._complete_main_story()

    def test_puzzles_do_not_allow_shortcuts_or_consume_wrong_items(self):
        game = self.game
        self.act("tower")
        self.assertEqual(game.room, 0)
        self.act("grate")
        self.assertFalse(game.key_found)
        self.act("lamp")  # Not visible in the harbour.
        self.assertFalse(game.lens_installed)
        self.act("rope")
        game.selected = "SEIL"
        self.act("grate")
        self.assertEqual(game.inventory, ["SEIL"])
        self.act("rope")
        self.assertEqual(game.inventory, ["SEIL"])
        self.act("inn")
        game._talk(1)
        self.assertNotIn("LINSE", game.inventory)
        game.room = 2
        self.act("crank")
        self.assertFalse(game.won)

    def test_dialogue_pages_fit_display_and_advance(self):
        game = self.game
        game._say("Ein aussergewoehnlichlangeswort und viele weitere Worte. " * 10)
        self.assertGreater(len(game.pages), 1)
        self.assertTrue(all(len(page) <= 5 for page in game.pages))
        self.assertTrue(all(len(line) <= 10 for page in game.pages for line in page))
        count = len(game.pages)
        for unused in range(count):
            game._activate()
        self.assertFalse(game.pages)

    def test_inventory_combination_works_in_both_orders(self):
        for first, second in (("SEIL", "HAKEN"), ("HAKEN", "SEIL")):
            game = app.HarborAdventureGame()
            game.inventory = [first, second]
            game._inventory_click(0)
            game._inventory_click(1)
            self.assertEqual(game.inventory, ["ANKER"])
            game._inventory_click(0)
            self.assertIsNone(game.selected)

    def test_cancel_is_edge_triggered_and_does_not_accidentally_exit(self):
        joystick = _JoystickStub()
        step = self.game._build_step(joystick)
        self.assertTrue(step())
        joystick.buttons = (True, False)
        self.assertTrue(step())
        self.assertFalse(self.game.pages)
        self.assertTrue(step())  # Holding cancel must not leave the game.
        joystick.buttons = (False, False)
        self.assertTrue(step())
        joystick.buttons = (True, False)
        self.assertFalse(step())

    def test_final_dialogue_finishes_with_game_win(self):
        joystick = _JoystickStub()
        step = self.game._build_step(joystick)
        self.game.won = True
        self.game.score = 240
        self.game._say("ENDE")
        self.assertTrue(step())
        joystick.buttons = (False, True)
        self.assertFalse(step())
        self.assertTrue(app.game_over)
        self.assertEqual(app.global_score, 240)
        self.assertEqual(app.game_result, "WON")

    def test_all_side_quests_complete_once_without_main_items(self):
        game = self.game
        self.act("market")
        self.act("bread")
        self.act("oil")
        self.act("beach")
        self.act("bottle")
        self.act("sand")
        game.selected = "BROT"
        self.act("gull")
        self.assertNotIn("BROT", game.inventory)
        self.assertIn("GLOCKE", game.inventory)
        self.act("market")
        game.selected = "GLOCKE"
        self.act("trader")
        self.assertTrue(game.bell_returned)
        self.act("workshop")
        game.selected = "BRIEF"
        self.act("post")
        game._inventory_click(game.inventory.index("ZAHNRAD"))
        game._inventory_click(game.inventory.index("OEL"))
        self.assertEqual(game.selected, "LAUFRAD")
        self.act("clock")
        self.assertEqual(game._quest_count(), 3)
        self.assertEqual(game.score, 200)
        self.assertFalse(game.won)
        self.assertEqual(game.inventory, [])
        self.act("clock")
        self.act("post")
        self.act("maker")
        self.act("market")
        self.act("trader")
        self.assertEqual(game.score, 200)
        self.assertFalse(game.coin_found)
        self.act("harbor")
        # Replay the existing main story with side-quest rewards retained.
        self._complete_main_story(expected_score=440)

    def test_optional_tasks_reject_wrong_items_and_preserve_progress(self):
        game = self.game
        self.act("crate")
        self.act("market")
        game.selected = "MUENZE"
        self.act("trader")
        self.assertFalse(game.bell_returned)
        self.act("workshop")
        self.act("clock")
        self.act("post")
        self.assertFalse(game.clock_fixed)
        self.assertFalse(game.letter_delivered)
        self.assertIn("MUENZE", game.inventory)
        self.act("beach")
        self.act("sand")
        self.act("workshop")
        game.selected = "ZAHNRAD"
        self.act("clock")
        self.assertIn("ZAHNRAD", game.inventory)
        self.assertFalse(game.clock_fixed)
        self.act("beach")
        self.act("sand")
        self.assertEqual(game.inventory.count("ZAHNRAD"), 1)

    def test_paged_inventory_can_combine_items_across_pages(self):
        game = self.game
        game.inventory = ["MUENZE", "SEIL", "HAKEN", "ZAHNRAD", "OEL", "BRIEF", "BROT"]
        game.cursor_x, game.cursor_y = 40, 50
        game._activate()
        self.assertEqual(game.selected, "ZAHNRAD")
        game.cursor_x = 57
        game._activate()
        self.assertEqual(game.inventory_page, 1)
        self.assertEqual(game.selected, "ZAHNRAD")
        game.cursor_x = 5
        game._activate()
        self.assertIn("LAUFRAD", game.inventory)
        self.assertNotIn("OEL", game.inventory)
        self.assertNotIn("ZAHNRAD", game.inventory)
        game.pages = []
        game.inventory = ["LAUFRAD"]
        game._draw()
        self.assertEqual(game.inventory_page, 0)
        game.cursor_x = 5
        game._activate()
        self.assertIsNone(game.selected)

    def test_new_routes_are_bidirectional_and_hotspots_do_not_overlap(self):
        game = self.game
        for target, room in (("market", 3), ("beach", 4), ("workshop", 5),
                             ("beach", 4), ("market", 3), ("workshop", 5),
                             ("market", 3), ("harbor", 0)):
            self.act(target)
            self.assertEqual(game.room, room)
        for hotspots in game.HOTSPOTS:
            for index, (_, _, a) in enumerate(hotspots):
                for _, _, b in hotspots[index + 1:]:
                    self.assertFalse(a[0] <= b[2] and b[0] <= a[2]
                                     and a[1] <= b[3] and b[1] <= a[3])

    def test_journal_reports_completion_and_reset_clears_quests(self):
        game = self.game
        self.act("market")
        game.bell_returned = True
        game._interact("journal")
        text = " ".join(line for page in game.pages for line in page)
        self.assertIn("1 VON 3", text)
        self.assertIn("ERLEDIGT", text)
        game.inventory_page = 2
        game.reset()
        self.assertEqual(game._quest_count(), 0)
        self.assertEqual(game.inventory_page, 0)
        self.assertEqual(game.inventory, [])

    def test_hotspots_and_idle_rendering(self):
        self.assertIn(("HARBOR", app.HarborAdventureGame, 0), app.GameSelect.GAME_REGISTRY)
        game = self.game
        for room, hotspots in enumerate(game.HOTSPOTS):
            game.room = room
            for target, unused_label, (x1, y1, x2, y2) in hotspots:
                game.cursor_x, game.cursor_y = (x1 + x2) // 2, (y1 + y2) // 2
                self.assertEqual(game._target(), target)
        display = _CountingDisplay()
        app.display = display
        game._draw()
        first = display.pixel_writes
        display.pixel_writes = 0
        game._draw()
        self.assertLess(display.pixel_writes, first // 3)


if __name__ == "__main__":
    unittest.main()
