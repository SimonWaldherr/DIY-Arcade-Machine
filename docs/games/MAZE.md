# Maze Explorer (`MAZE`)

## Gameplay

- Explore a procedurally generated maze under fog of war.
- Collect gems and avoid roaming enemies.
- Clear the level and move into harder versions with more pressure.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| The maze is a traversable grid produced by a generation algorithm and revealed over time. | `MazeGame` builds its own maze structure and tracks explored cells. |
| Fog of war separates known space, visible space, and unknown space for exploration tension. | The renderer distinguishes explored areas from currently visible ones. |
| A collectible loop plus enemy pressure turns a static maze into an action game. | Gems raise the score, while multiple enemies are spawned and scaled by level. |
| Grid-based movement and compact storage keep the game practical on embedded hardware. | The code uses byte-oriented grid state and direct index lookups rather than heavyweight objects. |
