# Pac-Man (`PACMAN`)

## Gameplay

Move through the maze and eat all pellets. Avoid ghosts unless a power pellet is active. Power pellets temporarily flip the chase dynamic and make escape easier.

## Technical details

Pac-Man is driven by a fixed maze, queued movement, collectibles, and enemy pursuit logic. In this repository, `PacmanGame` uses a built-in map and updates the player and ghost positions on a regular logic tick. Pellet maps are efficient as simple grid values rather than separate objects per pellet. In this repository, The maze stores walls, normal pellets, and power pellets in compact per-cell state. Frightened mode changes ghost behavior for a limited time after a power pellet. In this repository, A power timer flips ghost decision-making from chasing toward safer movement. Grid movement benefits from accepting a queued direction before the character reaches the next cell center. In this repository, The player stores intended direction changes and applies them when the next tile allows it.
