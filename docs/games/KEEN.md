# Keen (`KEEN`)

## Gameplay

- Use left/right to run.
- Press up or `Z` to jump.
- Collect gems for points.
- Collect the key before entering the exit door.
- Jump on enemies to defeat them; touching them from the side ends the run.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| A small Keen-like platformer needs side-scrolling maps, collision against tiles, jumping, collectibles, keys, exits, and enemies. | `KeenGame` stores tile maps, player position/velocity, camera offset, items, enemies, key state, level, and score. |
| Platform collision needs to stay simple and reliable. | Movement is split into horizontal and vertical axis steps and checked against solid `#` tiles. |
| Levels should be readable on a 64x64 display. | Tiles are 4x4 pixels; the camera follows the player across wider maps while showing gems, key, exit, enemies, and the player. |
| Win conditions should be direct. | The player must collect the key and reach the exit; completing all maps records a won score. |
