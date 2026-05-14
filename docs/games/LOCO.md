# LocoMotion (`LOCO`)

## Gameplay

- Rotate railway tiles to build a valid route.
- Start the train once the track looks connected. Start and end tiles stay fixed.
- Complete levels by guiding the train from start to end.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| Track tiles encode their open directions as bit flags. | `LocoMotionGame` uses `N`, `E`, `S`, and `W` bits for rail connectivity. |
| The edit mode moves a cursor and rotates track pieces. | The game tracks `cur_x` and `cur_y`; short primary presses rotate normal tiles, while endpoint presses start the run. |
| The run mode advances a train along connected rails. | Train state uses tile coordinates, direction, progress, and per-frame speed. |
