# Artillery Simulator (`ARTILL`)

## Gameplay

- Use up/down to aim the cannon barrel.
- Use left/right to adjust shot power.
- Press `Z` to fire.
- Wind changes each round and bends the shell while it flies.
- Destroy the red enemy gun to advance; the CPU fires back after its turn.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| A small artillery game needs readable terrain, angle/power control, turn order, shell physics, wind, craters, and hit detection. | `ArtilleryGame` stores a terrain heightfield, player/enemy gun positions, angle, power, wind, turn state, active shell, explosions, score, and round. |
| Shells should feel predictable but not static. | The shell integrates velocity with gravity and per-round wind; misses crater the terrain and switch turns. |
| The CPU should be understandable on the LED matrix. | The enemy waits briefly, estimates a shot, and adds small randomness so rounds remain beatable. |
| The 64x64 display needs simple silhouettes. | Rendering draws sky, terrain columns, two tanks, the player aim line, shell, explosion, and compact HUD values. |
