# Asteroids (`ASTRD`)

## Gameplay

Rotate, thrust, and shoot while drifting through space. Destroy all asteroids in a wave to continue surviving. Crashing into an asteroid ends the run.

## Technical details

Asteroids combines inertial ship movement, projectile lifetimes, and screen wraparound. In this repository, `AsteroidGame` manages nested `Ship`, `Projectile`, and `Asteroid` objects. Vector-style games can be represented with lines instead of filled sprites. In this repository, The ship and some effects are rendered with line drawing helpers instead of tile graphics. Splitting large asteroids into smaller ones creates progression inside a single wave. In this repository, Destroyed asteroids can spawn smaller variants and award score increments. Resource limits are important on embedded targets with many moving objects. In this repository, The code caps projectile and asteroid counts differently depending on runtime limits.
