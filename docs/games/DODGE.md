# Dodge (`DODGE`)

## Gameplay

- Move the player block sideways to avoid falling hazards.
- Use the dash action for emergency repositioning.
- Survive as long as possible while the spawn rate increases.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| The game loop is based on obstacle spawning, downward motion, and collision cleanup. | `DodgeGame` keeps a list of active falling blocks and removes them after they pass the player. |
| Difficulty can be increased by reducing the time between spawns. | The spawn interval shrinks with the score down to a configured minimum. |
| A dash mechanic usually reuses the last movement direction instead of adding a new control scheme. | The player stores `last_dir` and doubles that motion when the action button is used. |
| Survival score can be tied to obstacles successfully avoided. | Points are awarded when hazards leave the bottom of the playfield without hitting the player. |
