# Simon Says (`SIMON`)

## Gameplay

- Repeat the growing color sequence shown on the screen.
- Each successful round adds one more step.
- A wrong input ends the run, and the score is the number of completed sequence steps.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| The game state is a sequence of color ids plus a pointer to the current player input step. | `SimonGame` keeps the sequence in `self.sequence` and validates player inputs against it. |
| The screen is divided into four large interaction zones so a low-resolution display stays readable. | `draw_quad_screen()` renders four colored quadrants over the playfield. |
| Input is mapped from directional gestures to quadrant ids. | `translate()` converts joystick diagonals into quadrant indexes from `0` to `3`. |
| Playback and user feedback rely on timed flashes rather than moving objects. | `flash_color()` and `play_sequence()` use `sleep_ms()` to pace highlights and gaps. |
