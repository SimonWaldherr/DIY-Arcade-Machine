# Tetris (`TETRIS`)

## Gameplay

Move and rotate falling tetrominoes to complete horizontal lines. Cleared lines award more points when multiple rows disappear at once. The game ends when a new piece can no longer spawn safely.

## Technical details

Tetris needs a playfield matrix, active piece state, collision checks, and row compaction. In this repository, `TetrisGame` stores the locked field separately from the current falling `Piece`. The seven tetrominoes can be represented as shape definitions and rotated at runtime. In this repository, The nested `Piece` class uses predefined block arrangements and validates rotations before applying them. Scoring depends on how many rows are cleared in a single lock event. In this repository, The implementation applies classic tiered rewards for one, two, three, or four cleared lines. Automatic gravity plus manual movement and rotation create the complete loop. In this repository, Timed falling is combined with joystick movement, rotation, and faster drop input.
