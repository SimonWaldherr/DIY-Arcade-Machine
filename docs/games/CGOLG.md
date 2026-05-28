# Conway's Game of Life Game (`CGOLG`)

## Gameplay

This is a competitive Conway's Game of Life battle. The player spawns blue Life creatures from the left quarter of the playfield. The CPU opponent spawns red Life creatures from the right quarter. All spawnable creatures are moving forms aimed toward the opponent: diagonal gliders and horizontal spaceships. Normal Conway rules drive the grid: live cells survive with 2 or 3 neighbors, and dead cells are born with exactly 3 neighbors. Cell color is inherited from nearby live cells. Blue and red ancestry can mix into purple collision zones. Blue cells reaching the right quarter damage the enemy base. Red cells reaching the left quarter damage the player base. Win by reducing the enemy base to zero. Lose when the player base reaches zero.

## Controls

Use `LEFT` and `RIGHT` to select a creature, `UP` and `DOWN` to move the spawn lane, `Z` to spawn the selected creature when enough energy is available, and `C` to return to the menu.

## Technical details

A battle layer runs Conway's rules over a fixed grid while each live cell carries ownership/color metadata. In this repository, `CgolgGame` stores alive state plus red and blue channels in compact `bytearray` buffers. Newborn cells inherit color from the three cells that caused the birth. Surviving cells retain most of their own color and drift toward nearby colors. In this repository, `_generation()` computes neighbor counts plus red/blue sums, then writes the next alive/color buffers. The player and enemy can only seed directed moving patterns from their own quarter, so pressure naturally travels toward the other side. In this repository, `_spawn_pattern()` clamps player spawns to `x < WIDTH // 4` and enemy spawns to the mirrored right quarter. The CPU should feel active without expensive planning. In this repository, `_enemy_spawn()` uses energy, simple board-density scans, and randomized directed pattern choice to keep pressure on the player. The LED matrix should make territory readable at a glance. In this repository, Rendering uses blue for player ancestry, red for enemy ancestry, mixed red/blue channels for contested cells, and previews the currently selected mover with direction arrows.
