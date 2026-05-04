# Invaders (`INVADR`)

## Gameplay

- Move the ship left and right along the bottom of the playfield.
- Press `Z` to fire a shot upward.
- Clear alien waves for points; each cleared wave speeds up the next one.
- Avoid falling bombs and stop aliens from reaching the ship.
- Press `C` to return to the game menu.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| A fixed grid of aliens advances sideways and drops when it reaches an edge. | `InvaderGame` stores aliens as `[x, y, alive]` entries and updates them in `_step_aliens()`. |
| The player has one active bullet to keep state small and readable on the LED matrix. | `self.bullet` is either `None` or a two-value position list updated by `_step_bullet()`. |
| Aliens occasionally drop bombs from live rows. | `_drop_bomb()` picks a live alien and appends a compact bomb position to `self.bombs`. |
| The wave loop scales difficulty without growing memory. | `_spawn_wave()` rebuilds the fixed alien grid and lowers `alien_step_ms` after each clear. |
