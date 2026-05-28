# Orbital (`ORBTAL`)

## Gameplay

Aim the cannon with `Left` and `Right`. Press `Z` to fire a bouncing shot. Every circle starts with the number `3`. Each touch counts that circle down by one. At `0`, the circle bursts and awards bonus points. If circles crowd the launcher, the run ends.

## Technical details

A bounce-shot puzzle needs launcher angle, a moving projectile, reflective walls, and circular obstacles. In this repository, `OrbitalGame` stores one active shot with position, velocity, age, and last-hit state. Circles should be stateful targets, not just bumpers. In this repository, Each circle stores radius, countdown value, and a short contact cooldown. The requested `3 -> 2 -> 1 -> 0` rule is the core scoring loop. In this repository, `_advance_shot()` decrements the touched circle and removes it with a burst when the value reaches zero. The playfield should gradually become risky. In this repository, Long-lived shots can settle into new numbered circles, and circles near the launcher trigger game over.
