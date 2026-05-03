# Breakout (`BRKOUT`)

## Gameplay

- Move the paddle horizontally and keep the ball in play.
- Every brick destroyed adds points.
- The round ends when the ball falls below the paddle.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| Breakout is driven by ball reflection against walls, a paddle, and a brick grid. | `BreakoutGame` updates a moving ball and checks collisions against a fixed brick layout. |
| Bricks are often stored as a simple occupancy grid because they only need alive/dead state. | The implementation uses a small rows-and-columns brick structure sized for the LED matrix. |
| Color-coding brick rows improves readability without changing mechanics. | Brick colors are generated row by row, using hue-based coloring helpers. |
| Destroying a brick is an immediate state mutation followed by a redraw. | A hit removes the brick, flips ball direction, and refreshes the visible playfield. |
