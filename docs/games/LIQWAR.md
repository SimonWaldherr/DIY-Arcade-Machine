# Liquid War (`LIQWAR`)

## Gameplay

- Blue and red particles fight for control of the 64x58 playfield.
- Move the joystick to steer the blue attractor; nearby blue particles are pulled toward it.
- The red team is controlled by a simple AI attractor that pushes back against the blue swarm.
- Blue scores when particles reach the red side; red scores when particles reach the blue side.
- Press `Z` to reset the round and `C` to return to the game menu.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| Each team is a flock of particles pulled by an attractor point. | `LiquidWarGame` stores particles as compact dictionaries with position, velocity, and team values. |
| Particles separate from nearby particles to make a liquid-like front line. | `_apply_forces()` uses a small spatial bucket grid before applying collision impulses. |
| The AI moves its attractor toward the opposing centroid with some randomness. | `_update_ai()` derives a red attractor target from blue particle positions and adds noise. |
| Side crossings award points and recycle particles back to their home side. | `_score_and_respawn()` increments blue/red scores and calls `_respawn_particle()`. |
