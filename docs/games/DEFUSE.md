# Defuse (`DEFUSE`)

## Gameplay

Memorize the colored sequence shown at the top. Move left and right to select a wire. Press `Z` to cut wires in the requested order before time runs out.

## Technical details

A defuse puzzle needs a target sequence, selectable wires, cut state, and a timer. In this repository, `DefuseGame` stores the wire order, cursor, cut index, round timer, and current score. Rounds should become harder while staying readable. In this repository, Sequence length grows up to five and the timer shortens each round. Feedback must fit the matrix. In this repository, The top row shows the target colors, full-height colored wires show choices, and the timer is a small bar.
