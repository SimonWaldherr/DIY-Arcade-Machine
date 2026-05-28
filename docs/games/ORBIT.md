# Orbit (`ORBIT`)

## Gameplay

Aim with the direction controls. Hold `Z` to eject mass and accelerate in the aimed direction. Absorb smaller blobs to grow. Avoid larger blobs; touching one ends the run. Reach the target mass to advance to a denser level with gravity wells.

## Technical details

A blob-physics game needs mass, velocity, absorption, and risk from larger bodies. In this repository, `OrbitGame` stores player radius, velocity, target radius, and moving blobs with their own radii. Propulsion should trade size for movement. In this repository, `_thrust()` shrinks the player, emits a small mass blob, and accelerates the player along the aim vector. Absorption should conserve a mass-like quantity without heavy simulation. In this repository, `_advance()` combines radius squared values with a simple square-root growth rule. Gravity can add path planning without clutter. In this repository, Later levels add attractive or repulsive wells that accelerate the player and blobs each frame.
