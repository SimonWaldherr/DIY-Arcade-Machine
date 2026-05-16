# Defuse (`DEFUSE`)

## Gameplay

- Memorize the colored sequence shown at the top.
- Move left and right to select a wire.
- Press `Z` to cut wires in the requested order before time runs out.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| A defuse puzzle needs a target sequence, selectable wires, cut state, and a timer. | `DefuseGame` stores the wire order, cursor, cut index, round timer, and current score. |
| Rounds should become harder while staying readable. | Sequence length grows up to five and the timer shortens each round. |
| Feedback must fit the matrix. | The top row shows the target colors, full-height colored wires show choices, and the timer is a small bar. |

