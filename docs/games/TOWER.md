# Tower Defense (`TOWER`)

## Gameplay

- Enemies travel from the left side of the grid to the right side.
- Move the cursor with the joystick and press `Z` to place a tower.
- Towers can be placed only if enemies still have a valid route from start to finish.
- Press `Z` on an existing tower to upgrade it when enough money is available.
- Lose lives when enemies reach the exit; press `C` to return to the game menu.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| The playfield is a small logical grid rendered to the LED matrix. | `TowerDefenseGame` uses a 16-column tile grid over the shared 58-pixel playfield. |
| Build validation must preserve at least one path. | `path_exists()` performs a BFS over the occupancy grid before tower placement is committed. |
| Enemies follow the current path and update when the grid changes. | `spawn_enemy()` stores a tile path for each enemy, and `_move_enemies()` advances along tile centers. |
| Towers choose targets in range and fire projectiles. | The main loop scans towers, creates projectile dictionaries, and applies hit damage to enemies. |
