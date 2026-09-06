"""New map reachability, puzzle solving and selectable-layout regressions."""
from collections import deque
import unittest
import arcade_app as app
from test_arcade_app import _DisplayStub

DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def cells(rows, chars):
    return {(x, y) for y, row in enumerate(rows) for x, c in enumerate(row) if c in chars}


def reach(rows, start, blocked='#'):
    seen = {start}
    pending = [start]
    while pending:
        x, y = pending.pop()
        for dx, dy in DIRS:
            p = x + dx, y + dy
            if (0 <= p[1] < len(rows) and 0 <= p[0] < len(rows[0])
                    and rows[p[1]][p[0]] not in blocked and p not in seen):
                seen.add(p)
                pending.append(p)
    return seen


class MapTests(unittest.TestCase):
    def setUp(self):
        self.old = app.display
        app.display = _DisplayStub()

    def tearDown(self):
        app.display = self.old

    def test_new_maze_objectives_are_reachable(self):
        for kind, chars in ((app.PacmanGame, '.oG'), (app.SabotrGame, 'TG')):
            for rows in kind.MAPS[-2:]:
                self.assertTrue(all(len(row) == 16 for row in rows))
                start = next(iter(cells(rows, 'P')))
                self.assertTrue(cells(rows, chars) <= reach(rows, start))
        for index in range(len(app.DoomLiteGame.MAPS) - 2, len(app.DoomLiteGame.MAPS)):
            rows = tuple(r.decode() for r in app.DoomLiteGame.MAPS[index])
            start = tuple(int(v) for v in app.DoomLiteGame.STARTS[index])
            self.assertTrue(cells(rows, 'K') <= reach(rows, start, '#D'))
            self.assertTrue(cells(rows, 'QX') <= reach(rows, start))
        for kind in (app.SonarGame, app.TimeLoopGame):
            for rows in kind.MAPS:
                start = next(iter(cells(rows, 'P')))
                self.assertTrue(cells(rows, 'CEAB') <= reach(rows, start))

    def test_tilt_maps_have_a_complete_sliding_solution(self):
        for rows in app.TiltGame.MAPS:
            start = next(iter(cells(rows, 'P')))
            state = (start, frozenset(cells(rows, '*')))
            pending, seen = deque([state]), {state}
            solved = False
            while pending:
                (x, y), remaining = pending.popleft()
                if not remaining:
                    solved = True
                    break
                for dx, dy in DIRS:
                    nx, ny = x, y
                    left = set(remaining)
                    while rows[ny + dy][nx + dx] != '#':
                        nx, ny = nx + dx, ny + dy
                        left.discard((nx, ny))
                    state = ((nx, ny), frozenset(left))
                    if state not in seen:
                        seen.add(state)
                        pending.append(state)
            self.assertTrue(solved, rows)

    def test_new_sokoban_boards_have_push_solutions(self):
        for raw in app.SokobanGame.SOK_LEVELS[-2:]:
            rows = tuple(r.decode() for r in raw)
            goals = cells(rows, 'G')
            boxes = frozenset(cells(rows, 'B'))
            self.assertEqual(len(goals), len(boxes))
            state = (next(iter(cells(rows, 'P'))), boxes)
            pending, seen = deque([state]), {state}
            solved = False
            while pending:
                player, boxes = pending.popleft()
                if boxes <= goals:
                    solved = True
                    break
                for dx, dy in DIRS:
                    p = player[0] + dx, player[1] + dy
                    if rows[p[1]][p[0]] == '#':
                        continue
                    moved = boxes
                    if p in boxes:
                        q = p[0] + dx, p[1] + dy
                        if rows[q[1]][q[0]] == '#' or q in boxes:
                            continue
                        moved = (boxes - {p}) | {q}
                    state = p, frozenset(moved)
                    if state not in seen:
                        seen.add(state)
                        pending.append(state)
            self.assertTrue(solved)

    def test_selectable_maps_load_and_wires_and_laser_solutions_work(self):
        kinds = (app.TiltGame, app.SonarGame, app.TimeLoopGame, app.WiresGame,
                 app.MazeGame, app.BomberGame, app.GolfGame, app.LaserGame,
                 app.RayRacerGame, app.DigDugGame, app.CityChaseGame,
                 app.TopDownRacerGame, app.MarbleGame, app.DonkeyGame,
                 app.PeggleGame, app.BreakoutGame, app.WormsGame, app.ArtilleryGame)
        for kind in kinds:
            for index in range(3):
                with self.subTest(game=kind.__name__, map=index):
                    game = kind({'settings': {'map': index}})
                    self.assertEqual(game.map_index, index)
        for index in range(3):
            game = app.WiresGame({'settings': {'map': index}})
            game.grid = list(game.SOLUTION)
            self.assertTrue(game._is_solved())
            game = app.LaserGame({'settings': {'map': index}})
            for level in (1, 3, 6):
                game.level = level
                game._new_level()
                for x, y, tile in game.solution_mirrors:
                    game.grid[y][x] = tile
                self.assertTrue(game._trace()[1])

    def test_new_tower_routes_are_in_bounds_and_axis_aligned(self):
        for mode, route in app.TowerDefenseGame.LEVELS[-2:]:
            self.assertEqual(mode, 'PATH')
            for x, y in route:
                self.assertTrue(0 <= x < 8 and 0 <= y < 7)
            for a, b in zip(route, route[1:]):
                self.assertTrue((a[0] == b[0]) != (a[1] == b[1]))

    def test_bomber_blast_preserves_new_fixed_walls(self):
        for index, point in ((1, (2, 2)), (2, (3, 2))):
            game = app.BomberGame({'settings': {'map': index}})
            game._explode(*point)
            self.assertTrue(game.blocks[point[1]][point[0]])

    def test_adventure_new_locations_return_to_workshop(self):
        game = app.HarborAdventureGame()
        game.room = 5
        for target, expected in (('archive', 6), ('cliff', 7), ('archive', 6), ('workshop', 5)):
            game._interact(target)
            self.assertEqual(game.room, expected)
