# Pitfall Runner (`PITFAL`)

## Gameplay

- Run through an endless path with pits, snakes, and treasure.
- Charge and release jumps to clear danger or reach rewards.
- Distance and treasure collection both increase the score.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| Endless runners use a spawn stream of hazards and rewards that move toward the player. | `PitfallGame` stores upcoming obstacles as dictionaries with kinds such as pit, snake, and treasure. |
| Variable jump strength adds timing depth without increasing button complexity. | Holding jump changes the launch strength before gravity takes over. |
| Early safe zones help onboard players before full difficulty begins. | The first stretch spawns only safe treasure placements before pits and snakes are introduced. |
| A simple ground-based collision system is enough for low-resolution side views. | The code uses axis-aligned overlap checks and float-based vertical physics for the runner. |
