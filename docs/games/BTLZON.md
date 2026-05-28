# Battlezone (`BTLZON`)

## Gameplay

Use left/right to rotate the tank view. Use up/down to drive toward or away from the enemy. Press `Z` to fire when the enemy tank is near the crosshair. Watch the radar for enemy bearing and distance. Avoid incoming shells; losing all lives ends the run.

## Technical details

A compact Battlezone-like game needs first-person vector feedback, radar, relative enemy motion, player shots, enemy shells, lives, and waves. In this repository, `BattlezoneGame` tracks enemy distance/bearing, wave, lives, cooldowns, incoming shell state, frame counter, and score. Movement can be represented relative to the player. In this repository, Steering adjusts enemy bearing; forward/back changes distance instead of simulating a full world map. Shooting should be readable and skill-based. In this repository, A shot destroys the tank only when the bearing is close to center and the enemy is in range. The LED matrix benefits from sparse vector shapes. In this repository, Rendering draws horizon/grid lines, crosshair, a wireframe tank, a radar box, incoming shells, lives, and score.
