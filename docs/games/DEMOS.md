# Demo Showcase (`DEMOS`)

## Gameplay

- This is a zero-player entry made for attract-mode style visuals.
- It rotates through self-running demos such as Snake, Conway's Life, Spark particles, a fire effect, Langton's ants, a flood-fill maze animation, falling Matrix code, a 3D Starfield, a rolling and pulsing 3D wireframe Cube, an Orbit particle sculpture, a radial Warp star tunnel, a classic Bounce screensaver, a zooming vector Tunnel, a Demoscene Plasma effect, a Mystify screensaver effect, a spiral Vortex, and colored Comet trails.
- Press `LEFT` or `RIGHT` on the Joystick to cycle between these different demo effects.
- If `CONFIG_ENABLE_GAME_DEMOS` is enabled, the same selector can also launch short CPU-driven previews for the playable games in the registry.
- There is no win condition and no score; the point is to showcase the display and game engine.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| A demo hub owns a list of autonomous simulations and swaps between them on input. | `DemosGame` stores the enabled demo ids in `self.demos` and cycles them inside its update loop via Joystick directions. |
| Each simulation keeps its own compact state because it never needs player input. | The code uses lightweight structures such as `bytearray` grids, queue-like lists, and simple tuples for positions. |
| Cellular automata and procedural visuals are good fits for an LED matrix because they produce readable motion at low resolution. | `DemosGame` includes Conway's Life, Langton's ants, a flood-fill animation, a fire effect, an auto-playing snake variant, a Matrix digital rain effect, a 3D Starfield simulation, a sine-wave RGB plasma simulation ("PLASMA"), a rotating and scaling 3D wireframe cube ("CUBE"), a layered orbit particle sculpture ("ORBIT"), a radial warp-speed star tunnel ("WARP"), a bouncing logo ("BOUNCE"), a zooming vector tunnel ("TUNNEL"), a vector-driven polygon animation ("MYSTIFY"), a spiral line field ("VORTEX"), colored particle trails ("COMETS"), and a particle burst effect ("SPARK"). |
| Playable-game previews should stay in sync with the menu. | `GAME_DEMOS` and `GAME_CLASS_NAMES` mirror the `GameSelect` registry, including newer entries such as `ARENA`, `BOMBER`, `CLIMB`, `DEFUSE`, `GOLF`, `LASER`, `MINES`, `PAIRS`, `SKYWAR`, and `WINGS`. |
| Memory pressure can change which demos are active on embedded hardware. | The demo list is conditionally populated. If `CONFIG_LOW_RAM_MODE` is enabled, the compact Snake, Life, Cube, Vortex, Comets, Spark, and Rings effects are enabled. |
