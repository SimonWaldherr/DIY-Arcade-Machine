# Sky War (`SKYWAR`)

## Gameplay

- Fly a helicopter across a scrolling battlefield.
- Move in four directions to line up shots and dodge fire.
- Hold `Z` to fire the forward cannon.
- Destroy drones, tanks, and turrets for points.
- You have three lives; collisions and turret fire cost a life.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| A Silkworm-style battlefield shooter needs a low-flying player craft, mixed air/ground enemies, bullets, and a scrolling ground line. | `SkyWarGame` tracks player position, forward shots, enemy shots, enemy objects, lives, spawn pacing, and a ground-scroll offset. |
| Air and ground targets should share update logic but draw differently. | Enemy entries store a type tag (`drone`, `tank`, or `turret`) plus position and speed; drawing and scoring branch on the tag. |
| One-button shooting should stay readable on the arcade controls. | `Z` fires a straight cannon shot from the helicopter nose, while movement remains entirely on the joystick. |
| Difficulty should rise without changing the rules. | Enemy spawn delay tightens as score increases, adding pressure while preserving the same controls. |

