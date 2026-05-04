# Sokoban (`SOKO`)

## Gameplay

- Push crates onto goal squares.
- Crates can only be pushed, not pulled.
- Use undo when a push blocks the puzzle.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| Sokoban levels separate static walls/goals from dynamic boxes/player state. | `SokobanGame` stores `walls`, `goals`, `boxes`, and player coordinates separately. |
| A push succeeds only when the target and beyond-target cells are free. | `_try_move()` validates walls, boxes, and bounds before moving. |
| Undo needs enough history to restore player and box positions. | `_undo()` restores records saved by successful moves. |

