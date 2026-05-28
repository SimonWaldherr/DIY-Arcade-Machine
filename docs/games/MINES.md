# Mines (`MINES`)

## Gameplay

Move the cursor around the minefield. Press `Z` to reveal a field. Reveal all safe fields without opening a mine.

## Technical details

A minesweeper puzzle needs hidden mines, revealed cells, neighbor counts, and a loss condition. In this repository, `MinesGame` keeps compact boolean grids for mines and revealed cells. Empty regions should open quickly. In this repository, Revealing a zero-count cell recursively reveals adjacent safe cells. The 64x64 matrix needs large readable cells. In this repository, The board uses an 8x7 grid with seven-pixel cells and small numeric glyphs.
