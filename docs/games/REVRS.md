# Othello/Reversi (`REVRS`)

## Gameplay

- Place discs to trap opponent discs in straight lines.
- Trapped discs flip to your color.
- Play against a simple CPU until no valid moves remain.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| Valid moves require at least one flippable line. | `OthelloGame.is_valid_move()` checks all eight directions. |
| Applying a move flips discs along every valid line. | `apply_move()` updates the board and recalculates the score. |
| The CPU can choose from legal moves without complex search. | `cpu_move()` selects an available move for the opponent turn. |

