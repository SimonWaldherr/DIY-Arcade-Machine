# LocoMotion (`LOCO`)

## Gameplay

- Rearrange railway tiles to build a valid route.
- Start the train once the track looks connected.
- Complete levels by guiding the train from start to end.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| Track tiles encode their open directions as bit flags. | `LocoMotionGame` uses `N`, `E`, `S`, and `W` bits for rail connectivity. |
| The edit mode moves a cursor and slides tiles. | The game tracks `cur_x`, `cur_y`, and an empty tile position for puzzle moves. |
| The run mode advances a train along connected rails. | Train state uses tile coordinates, direction, progress, and per-frame speed. |

