# Pairs (`PAIRS`)

## Gameplay

- Move the cursor over a 4x4 card board.
- Press `Z` to flip cards.
- Match equal pairs; mismatched cards briefly stay visible and then close.
- Clearing the board starts a new shuffled board.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| A memory game needs hidden values, cursor movement, open-card state, matched-card state, and mismatch timing. | `PairsGame` shuffles eight pairs into a 4x4 board and tracks open/matched cards separately. |
| The player needs a readable reveal even on 64x64 pixels. | Revealed cards use a distinct color plus a small number glyph; hidden cards use a consistent back color. |
| Mismatches should be visible long enough to learn from. | A short `pause_until` delay keeps the two cards open before hiding them again. |
| Scoring should reward memory efficiency. | Matched pairs award points based on the current attempt count, with a board-clear bonus. |

