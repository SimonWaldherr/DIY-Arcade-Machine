# Galaxy (`GALAXY`)

## Gameplay

Move the cursor between planets. Press `Z` on your planet to select it. Press `Z` on another planet to send half its ships as a fleet. Capture neutral and enemy planets by arriving with more ships than the defender. Eliminate the enemy to advance to a harder galaxy.

## Technical details

Planet conquest needs planets, owners, ship counts, growth, and moving fleets. In this repository, `GalaxyGame` stores planets as compact records and fleets as moving packets with owner and ship count. The player interaction should be two-step and readable on 64x64. In this repository, `_player_action()` first selects an owned planet, then sends a fleet to the cursor planet. Combat is simple subtraction and ownership transfer. In this repository, `_arrive()` adds friendly ships or subtracts enemy ships, flipping ownership when the defender drops below zero. The AI should pressure the player without complex planning. In this repository, `_ai_action()` sends from the strongest enemy planet toward the cheapest nearby target.
