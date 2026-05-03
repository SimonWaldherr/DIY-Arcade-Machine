# Tron Lightcycle (`TRON`)

## Gameplay

- Travel continuously and only turn in ninety-degree steps.
- Your trail becomes a permanent wall behind you.
- An enemy lightcycle shares the arena, leaves its own trail, and respawns into open space after a crash.
- Touching the wall, the enemy, or any occupied trail cell ends the run.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| Lightcycle games treat the arena as an occupancy map that fills over time. | `TronGame` stores trail occupancy in a linear byte array covering the playfield. |
| Turning is usually expressed as relative left/right commands, not absolute directions. | The code uses lookup tables to convert left and right turn inputs into new movement directions. |
| A turbo action can increase risk by moving multiple steps in one frame. | Pressing the action button makes the bike advance two cells instead of one. |
| Simple AI can feel fair if it looks ahead and respawns only where it has room to move. | The enemy chooses turns by comparing open distance ahead/left/right and respawns only after finding a clear start with enough forward space. |
| Survival scoring naturally maps to travelled distance. | The score increments while the cycle stays alive and moving. |
