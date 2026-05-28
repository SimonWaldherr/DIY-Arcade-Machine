# Maze Explorer (`MAZE`)

## Gameplay

Explore a procedurally generated maze under fog of war. Collect gems and avoid roaming enemies. Clear the level and move into harder versions with more pressure.

## Technical details

The maze is a traversable grid produced by a generation algorithm and revealed over time. In this repository, `MazeGame` builds its own maze structure and tracks explored cells. Fog of war separates known space, visible space, and unknown space for exploration tension. In this repository, The renderer distinguishes explored areas from currently visible ones. A collectible loop plus enemy pressure turns a static maze into an action game. In this repository, Gems raise the score, while multiple enemies are spawned and scaled by level. Grid-based movement and compact storage keep the game practical on embedded hardware. In this repository, The code uses byte-oriented grid state and direct index lookups rather than heavyweight objects.
