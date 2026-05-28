# Pairs (`PAIRS`)

## Gameplay

Move the cursor over a 4x4 card board. Press `Z` to flip cards. Match equal pairs; mismatched cards briefly stay visible and then close. Clearing the board starts a new shuffled board.

## Technical details

A memory game needs hidden values, cursor movement, open-card state, matched-card state, and mismatch timing. In this repository, `PairsGame` shuffles eight pairs into a 4x4 board and tracks open/matched cards separately. The player needs a readable reveal even on 64x64 pixels. In this repository, Revealed cards use a distinct color plus a small number glyph; hidden cards use a consistent back color. Mismatches should be visible long enough to learn from. In this repository, A short `pause_until` delay keeps the two cards open before hiding them again. Scoring should reward memory efficiency. In this repository, Matched pairs award points based on the current attempt count, with a board-clear bonus.
