# Climber (`CLIMB`)

## Gameplay

- Drift left and right to land on platforms.
- Use `Z` for a short jet-assisted jump.
- Keep climbing; falling below the screen ends the run.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| A vertical climbing game needs gravity, bounce platforms, wraparound movement, and scrolling. | `ClimberGame` updates the player's velocity, platform collisions, and vertical scroll offset each frame. |
| Difficulty comes from platform spacing and width. | New platforms are generated above the visible area and shrink as score increases. |
| The display should keep motion legible. | Platforms are horizontal colored bars and the player is a bright 4x4 block. |

