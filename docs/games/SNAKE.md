# Snake (`SNAKE`)

## Gameplay

- Guide the snake around the playfield and eat red targets to grow.
- Green targets are temporary and shrink the snake instead of helping it.
- The snake wraps around the screen edges, but hitting your own body ends the game.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| The snake is an ordered list of body segments with a separate target length. | `SnakeGame` stores segments in `self.snake` and the intended size in `self.snake_length`. |
| Collectibles can apply different effects such as growth, score increase, or shrink penalties. | Red targets increase length and score; green targets halve the current length. |
| Wraparound movement removes wall pressure and shifts difficulty toward path planning. | `update_snake_position()` applies modulo-based wrapping on both axes. |
| Speed can scale with the snake size to keep the game tense. | The frame delay decreases as the snake grows, with a lower clamp to avoid becoming uncontrollable. |
