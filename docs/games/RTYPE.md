# R-Type Shooter (`RTYPE`)

## Gameplay

Fly through an endless side-scrolling battlefield. Shoot enemy ships, dodge enemy fire, and collect power-ups. The longer you survive, the faster and busier the screen becomes.

## Technical details

A side-scrolling shooter needs a player ship, enemy waves, bullets, and spawn pacing. In this repository, `RTypeGame` maintains capped lists for player bullets, enemy bullets, enemies, and power-ups. Distinct enemy archetypes keep a simple game varied without needing a huge content set. In this repository, The implementation includes straight-moving drones, wobbling enemies, and shooter variants. Temporary power-ups are often timers attached to the player state. In this repository, Collecting a power-up starts a countdown that grants a temporary advantage. Spawn rates can scale from the score to increase pressure organically. In this repository, The enemy spawn delay decreases as the score rises, with a lower bound for stability.
