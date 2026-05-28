# Bomber (`BOMBER`)

## Gameplay

Move through the compact block maze. Press `Z` to place a timed bomb. Bomb blasts destroy loose blocks and defeat enemies. Avoid enemies and your own blast radius. Clearing every enemy starts the next level with a larger enemy count.

## Technical details

A bomber maze needs grid movement, blocked cells, timed bombs, blast propagation, and enemy state. In this repository, `BomberGame` uses a 9x8 grid, per-cell block flags, bomb timers, short-lived blast cells, and simple enemy direction state. Bomb blasts should feel spatial and predictable. In this repository, `_blast_cells()` expands from the bomb center up to two cells in each cardinal direction and stops at walls or blocks. Destructible and fixed blocks need different behavior. In this repository, Fixed pillar blocks are generated on odd grid intersections; loose blocks can be removed by blasts for score. The game must stay readable on 64x64 pixels. In this repository, Each grid cell is seven pixels wide, using distinct colors for blocks, bombs, blasts, enemies, and the player.
