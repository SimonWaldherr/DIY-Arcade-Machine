# Centipede (`CENTI`)

## Gameplay

- Move in the lower play zone.
- Press `Z` to fire upward.
- Shoot centipede segments before they descend into the player zone.
- Mushrooms block and redirect the centipede; shots can clear damaged mushrooms.
- Clearing the whole centipede starts the next wave.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| A Centipede-style game needs a bottom player zone, upward shots, mushrooms, segmented enemies, and wave progression. | `CentipedeGame` uses a compact 32x29 logical grid mapped to 2x2 LED pixels. |
| The centipede should feel like the Atari pattern without heavy pathfinding. | Each segment moves horizontally, reverses on walls or mushrooms, and drops one row when blocked. |
| Mushrooms are both obstacles and tactical targets. | `mushrooms` store grid position and hit points; bullets damage them and centipede segments create new mushrooms when destroyed. |
