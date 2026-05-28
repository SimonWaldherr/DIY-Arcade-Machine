# Ray Racer (`RAYRCR`)

## Gameplay

Race a neon anti-grav craft through a curving pseudo-3D track. Steer around rival hovercars, collect green energy gates, and use boost without draining the craft. Finish three laps before the energy meter runs out.

## Controls

**UP/DOWN**: accelerate above cruise speed and brake below it. **LEFT/RIGHT**: steer. **Z**: boost while energy is available. **C**: return to the game menu.

## Technical details

A raytrace-style racer projects a 3D-feeling road by sampling track distance for each screen row. In this repository, `RayRacerGame` precomputes row depths and renders a curved road from horizon to foreground each frame. The track can feel fast without storing tile maps by combining broad curve waves. In this repository, `_track_curve()` layers three sine curves, then subtracts the player's lateral offset during projection. Rivals and pickups are billboard objects in track space. In this repository, `objects` stores forward distance, lane, type, and animation phase, then `_project_y()` maps them onto the road. Arcade racing needs readable feedback at 64x64 resolution. In this repository, Neon edge rails, lane stripes, impact flashes, a player hovercraft, lap text, and an energy bar all render inside the 58-pixel playfield. The shared arcade flow handles highscores and retry/menu behavior. In this repository, The game uses `begin_game()`, `set_game_over_score()`, and the common sync/async frame-loop helpers.
