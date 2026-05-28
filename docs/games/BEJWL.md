# Bejeweled (`BEJWL`)

## Gameplay

Move the cursor across the gem grid. Select two adjacent gems to swap them. Matching groups disappear, refill from above, and score points.

## Technical details

A match-3 board stores a color index per cell. In this repository, `BejeweledGame.grid` is an 8x8 list of color indices. Valid swaps are adjacent selections that produce a match. In this repository, `main_loop()` swaps selected cells, checks `_find_matches()`, and reverts invalid swaps. Removed gems trigger cascades. In this repository, `_remove_matches_and_score()` clears matched cells, collapses columns, and refills missing cells.
