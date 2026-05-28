# Orbit (`ORBIT`)

## Gameplay

- Aim with the direction controls.
- Hold `Z` to eject mass and accelerate in the aimed direction.
- Absorb smaller blobs to grow.
- Avoid larger blobs; touching one ends the run.
- Reach the target mass to advance to a denser level with gravity wells.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| A blob-physics game needs mass, velocity, absorption, and risk from larger bodies. | `OrbitGame` stores player radius, velocity, target radius, and moving blobs with their own radii. |
| Propulsion should trade size for movement. | `_thrust()` shrinks the player, emits a small mass blob, and accelerates the player along the aim vector. |
| Absorption should conserve a mass-like quantity without heavy simulation. | `_advance()` combines radius squared values with a simple square-root growth rule. |
| Gravity can add path planning without clutter. | Later levels add attractive or repulsive wells that accelerate the player and blobs each frame. |

