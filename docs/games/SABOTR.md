# Saboteur Stealth (`SABOTR`)

## Gameplay

Move through patrol maps without entering enemy sight windows. Hold `Z` to sneak more slowly. Press `Z` next to a guard to perform a takedown. If a guard sees the player or a body, the run ends. Reach the green target to clear the map. Maps include room layouts and open-area patrol layouts. The campaign now includes additional room/open layouts with reachable targets.

## Technical details

A compact stealth game needs tile maps, patrols, sight cones, takedowns, bodies, and objectives. In this repository, `SabotrGame` uses 16x14 maps, wall grids, guard lists, body positions, player state, and a target tile. Guard sight must be readable on a tiny screen. In this repository, `_guard_fov()` returns straight and widened sight cells, and rendering paints those cells before guards and the player. Detection should be simple and strict. In this repository, `_caught()` ends the run when a guard sees the player or any body. Stealth maps must always have a valid objective route. In this repository, `SabotrGame.MAPS` contains multiple 16x14 maps whose player start can reach the target tile.
