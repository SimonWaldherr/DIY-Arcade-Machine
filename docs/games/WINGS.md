# Wings (`WINGS`)

## Gameplay

- Fly a carrier-based strike plane.
- Use up/down for altitude and left/right for speed.
- Press `Z` to fire low or drop bombs from higher altitude.
- Destroy depots and flak positions.
- Land on the carrier while low and slow to refuel and rearm.
- Crashing, running out of fuel, or being hit by flak ends the run.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| A Wings-of-Fury-inspired strike game needs altitude, speed, fuel, ammunition, ground targets, weapons, and a landing/rearm loop. | `WingsGame` stores plane position, speed, fuel, ammo, distance, shots, targets, and carrier timing. |
| Weapons should reflect flight state without extra buttons. | Pressing `Z` fires a gun when low and launches a bomb when higher above the ground. |
| Carrier operations need a simple readable rule. | The carrier appears on a distance cycle; landing succeeds only when the plane is low and slow, then fuel and ammo are restored. |
| Resource pressure creates strategy on a tiny screen. | Fuel drains with speed, ammo is limited, and the player must balance attack runs against safe return windows. |

