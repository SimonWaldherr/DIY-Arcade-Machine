# Invaders (`INVADR`)

## Gameplay

- Move the ship left and right along the bottom of the playfield.
- Press `Z` to fire a shot upward.
- Clear alien waves for points; each cleared wave speeds up the next one.
- Use the shields as cover, but both your shots and alien bombs chip holes in them.
- Hit the mystery saucer crossing the top for a larger bonus.
- Avoid falling bombs and stop aliens from reaching the ship.
- Press `C` to return to the game menu.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| A fixed grid of aliens advances sideways and drops when it reaches an edge. | `InvaderGame` stores aliens as `[x, y, alive, type]` entries and updates them in `_step_aliens()`. |
| The player has one active bullet to keep state small and readable on the LED matrix. | `self.bullet` is either `None` or a two-value position list updated by `_step_bullet()`; firing is edge-triggered so holding `Z` does not auto-stream shots. |
| Shields are destructible cover. | `_build_shields()` creates compact `bytearray` masks and `_hit_shield()` erodes small 3x3 chunks on impact. |
| Aliens drop bombs from the bottom-most live alien in a column. | `_drop_bomb()` builds a bottom-row candidate list before appending a compact bomb position to `self.bombs`. |
| A mystery saucer periodically crosses the top. | `_step_ufo()` spawns and moves a bonus target, and `_step_bullet()` awards bonus points on collision. |
| The wave loop scales difficulty without growing memory. | `_spawn_wave()` rebuilds the fixed alien grid and lowers `alien_step_ms` after each clear. |
