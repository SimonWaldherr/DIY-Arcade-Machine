# LocoMotion (`LOCO`)

## Gameplay

Rotate railway tiles to build a valid route. Start the train once the track looks connected. Start and end tiles stay fixed. Complete levels by guiding the train from start to end.

## Technical details

Track tiles encode their open directions as bit flags. In this repository, `LocoMotionGame` uses `N`, `E`, `S`, and `W` bits for rail connectivity. The edit mode moves a cursor and rotates track pieces. In this repository, The game tracks `cur_x` and `cur_y`; short primary presses rotate normal tiles, while endpoint presses start the run. The run mode advances a train along connected rails. In this repository, Train state uses tile coordinates, direction, progress, and per-frame speed.
