# Flappy Bird (`FLAPPY`)

## Gameplay

- Tap or press to give the bird an upward impulse.
- Gravity constantly pulls the bird back down.
- Pass through pipe gaps to score; touching a pipe or leaving the screen ends the game.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| Flappy-style games are built from one vertical body, gravity, impulses, and scrolling obstacles. | `FlappyGame` updates a bird with vertical velocity and a list of left-moving pipes. |
| Obstacles are easiest to model as rectangles with a fixed gap between upper and lower halves. | Each pipe entry stores its x-position and gap placement for collision and scoring. |
| Scoring should trigger once per obstacle after the player passes it. | Pipes are marked as passed so each one can award exactly one point. |
| Simple physics are enough when the display resolution is low. | The code uses a small capped velocity, a constant gravity step, and a fixed flap impulse. |
