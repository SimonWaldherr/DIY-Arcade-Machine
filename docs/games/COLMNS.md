# Columns (`COLMNS`)

## Gameplay

- A vertical triple of colored gems falls into the well.
- Move it with `Left` and `Right`.
- Press `Up` to cycle the three colors within the falling triple.
- Hold `Down` to soft-drop; press `Z` to hard-drop instantly.
- Line up three or more gems of one color horizontally, vertically, or
  diagonally to clear them.
- Cleared gems collapse the stack; new lines formed by the collapse clear too,
  building a chain that multiplies the points.
- The well speeds up as you clear gems.
- The run ends when the stack reaches the top and a new triple cannot spawn.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| A Columns clone needs a falling triple, an eight-direction match scan, gravity collapse, and cascading chains. | `ColumnsGame` keeps a flat `COLS x ROWS` grid plus the active triple's column, top row, and three colors. |
| The triple must move and reshuffle with one stick and one button. | `_move()` validates the target cells before shifting; `_cycle()` rotates the bottom gem to the top; `Z` triggers `_hard_drop()`. |
| Matches run in four axes and each line should be counted once. | `_find_matches()` walks right, down, and both diagonals, starting a run only where the previous cell breaks it. |
| Clearing should cascade. | `_resolve()` loops match → clear → `_apply_gravity()` until stable, scoring each pass with an increasing chain multiplier. |
| Difficulty should ramp. | The fall interval shrinks with the level, which advances every 25 cleared gems. |
