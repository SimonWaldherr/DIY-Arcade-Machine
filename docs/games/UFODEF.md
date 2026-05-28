# UFO Defense (`UFODEF`)

## Gameplay

Protect the cities and the central base from incoming enemy missiles. Move the targeting reticle and launch defensive missiles. Trigger explosions at the right time to intercept hostile projectiles.

## Technical details

Missile-defense games revolve around trajectories, detonation radii, and target selection. In this repository, `UFODefenseGame` updates player missiles, enemy missiles, city state, and explosion growth each frame. Enemy missiles become more dangerous when they can target remaining strategic assets. In this repository, Incoming attacks choose from living cities or the base, so the threat changes as cities are lost. Explosion overlap is the core interception rule. In this repository, Expanding blast circles destroy enemy missiles that enter their radius. Time-based escalation works well when rounds are intended to last until the defense collapses. In this repository, The game raises active enemy caps after longer survival times.
