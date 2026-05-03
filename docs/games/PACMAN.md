# Pac-Man (`PACMAN`)

## Gameplay

- Move through the maze and eat all pellets.
- Avoid ghosts unless a power pellet is active.
- Power pellets temporarily flip the chase dynamic and make escape easier.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| Pac-Man is driven by a fixed maze, queued movement, collectibles, and enemy pursuit logic. | `PacmanGame` uses a built-in map and updates the player and ghost positions on a regular logic tick. |
| Pellet maps are efficient as simple grid values rather than separate objects per pellet. | The maze stores walls, normal pellets, and power pellets in compact per-cell state. |
| Frightened mode changes ghost behavior for a limited time after a power pellet. | A power timer flips ghost decision-making from chasing toward safer movement. |
| Grid movement benefits from accepting a queued direction before the character reaches the next cell center. | The player stores intended direction changes and applies them when the next tile allows it. |
