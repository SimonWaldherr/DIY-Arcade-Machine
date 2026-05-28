# Stacker (`STACK`)

## Gameplay

Time each `Z` press to lock the moving block on top of the stack. Only the overlapping part of the current block survives to the next layer. Missing the previous layer ends the game. Reaching the top of the playfield wins and awards a completion bonus. Press `C` to return to the menu.

## Technical details

The game tracks locked layers separately from the currently moving layer. In this repository, `StackerGame.locked` stores `(x, y, width, color_index)` entries, while `bar_x`, `bar_y`, and `bar_w` describe the active block. A lock action computes horizontal overlap with the previous layer. In this repository, `StackerGame._drop()` intersects the active bar with `prev_x` and `prev_w`; no overlap calls `set_game_over_score(..., won=False)`. Difficulty increases as the tower grows. In this repository, `StackerGame._drop()` increases `self.speed` based on `self.score`. Win and loss both use the shared high-score flow. In this repository, Losing and top-out completion call `set_game_over_score()`, with wins using `won=True`.
