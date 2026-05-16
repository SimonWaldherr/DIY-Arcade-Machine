# Arena (`ARENA`)

## Gameplay

- Move around the arena with the joystick.
- Hold `Z` to fire in the last movement direction.
- Clear waves of chasing enemies without being touched.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| An arena survival game needs player motion, projectiles, enemy pursuit, and wave spawning. | `ArenaGame` stores enemies and shots in small lists and advances them on a frame timer. |
| Combat should work with one stick and one button. | The firing direction is the most recent movement direction, so no separate aim mode is needed. |
| Waves should scale within a tiny playfield. | Each cleared wave adds score and spawns more enemies from the edges. |

