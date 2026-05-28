# Stick Archer (`STKARC`)

## Gameplay

- Aim the bow with `Up` and `Down`.
- Move a little with `Left` and `Right`.
- Hold `Z` to draw the bow and release `Z` to fire.
- Watch wind and arrow arc to defeat each stickman opponent.
- A knockout spawns falling body pieces before the next wave starts.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| A stickman archer duel needs aim, charge, projectile gravity, and target health. | `StickArcherGame` stores player aim angle, draw charge, health bars, and a list of active arrows. |
| Arrows should feel ballistic without requiring a full physics engine. | Each arrow has position, velocity, gravity, and a small wind acceleration applied per frame. |
| Ragdoll-style feedback can be approximated with loose falling parts. | Knockouts call `_spawn_parts()` to emit small body fragments with velocity, gravity, bounce, and TTL. |
| Enemy pressure keeps the duel active. | The enemy periodically fires a rough aimed shot and waves increase enemy health and fire cadence. |

