# Frogger (`FROGGR`)

## Gameplay

- Hop across traffic lanes without getting hit.
- Reach the top of the screen to clear a level.
- Each successful crossing increases the difficulty.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| Frogger uses lane-based traffic patterns with a player that advances in discrete hops. | `FroggerGame` builds multiple lanes of moving cars and moves the player in 4-pixel steps. |
| Difficulty can scale by adding lanes, speeding traffic, and reducing gaps. | Lane count, car speed, and spacing all tighten as `level` increases. |
| Reaching the goal should reward progress and immediately restart play. | Crossing the road adds score, increments the level, rebuilds the lanes, and resets the player. |
| A compact collision system is enough for lane-based movement. | The game uses simple rectangle overlap checks between the player and each car. |
