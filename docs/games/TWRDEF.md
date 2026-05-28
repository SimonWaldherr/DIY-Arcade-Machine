# Tower Defense (`TWRDEF`)

## Gameplay

Some levels have a one-tile-wide brown road; enemies must follow it toward the blue base. Other levels are open fields; enemies pathfind across any cell that is not occupied by a tower. Move the cursor with the joystick. Press `Z` on an empty buildable tile to place a tower. Press `Z` on an existing tower to upgrade it. In open-field levels, the game rejects builds that would close the last route to the base. Towers target automatically. Higher levels add range, damage, slow, and splash. Earn money by defeating enemies and survive as many waves as possible. The run ends when too many enemies reach the base.

## Controls

Use `LEFT`, `RIGHT`, `UP`, and `DOWN` to move the build cursor, `Z` to build or upgrade a tower, and `C` to return to the menu.

## Technical details

A compact tower defense needs level layouts, buildable cells, wave spawning, tower targeting, projectiles, economy, and base health. In this repository, `TowerDefenseGame` stores one-cell road layouts, open-field layouts, towers, enemies, shots, money, wave state, and lives in small lists and scalar fields. Towers should be easy to control on one joystick and one action button. In this repository, `_try_build_or_upgrade()` builds on empty legal cells and upgrades existing towers with the same `Z` action. Open-field maps must stay solvable for enemies. In this repository, `_find_route()` performs small-grid BFS and `_can_build()` rejects placements that would block the spawn or any active enemy from reaching the base. Difficulty should scale through enemy count, speed, and special units. In this repository, `_start_wave()` and `_spawn_enemy()` increase wave size and introduce runners plus slower boss enemies. The LED matrix must show the tactical state quickly. In this repository, Rendering draws one-tile roads or open-field grid lines, colored towers by level, enemy health ticks, shots, a build cursor, wave, money, and base lives.
