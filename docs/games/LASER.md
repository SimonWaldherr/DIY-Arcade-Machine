# Laser (`LASER`)

## Gameplay

- Move the cursor over the mirror grid.
- Press `Z` to rotate the selected mirror.
- Guide the red beam from the left emitter into the green target on the right.
- Each solved board starts a harder board and awards more points for fewer moves.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| A mirror puzzle needs a grid, reflectors, a beam trace, loop detection, and a target condition. | `LaserGame` represents mirrors as `0`, `/`, and `\` values, then traces beam direction through the grid each frame. |
| Reflection should be deterministic and cheap. | The beam stores `(x, y, dx, dy)` states and changes direction with simple integer swaps at mirrors. |
| Infinite beam loops must not hang the game. | Trace state is recorded in a small `set`; repeated states end the trace as unsolved. |
| The display must show cause and effect clearly. | Mirrors are drawn as diagonal lines, the beam as bright pixels, and the emitter/target as edge markers. |

