# Demo Showcase (`DEMOS`)

## Gameplay

- This is a zero-player entry made for attract-mode style visuals.
- It rotates through self-running demos such as Snake, Conway's Life, a fire effect, Langton's ants, a flood-fill maze animation, falling Matrix code, a 3D Starfield, a rolling and pulsing 3D wireframe Cube, an Orbit particle sculpture, a radial Warp star tunnel, a classic Bounce screensaver, a zooming vector Tunnel, a Demoscene Plasma effect, and a Mystify screensaver effect.
- Press `LEFT` or `RIGHT` on the Joystick to cycle between these different demo effects.
- There is no win condition and no score; the point is to showcase the display and game engine.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| A demo hub owns a list of autonomous simulations and swaps between them on input. | `DemosGame` stores the enabled demo ids in `self.demos` and cycles them inside its update loop via Joystick directions. |
| Each simulation keeps its own compact state because it never needs player input. | The code uses lightweight structures such as `bytearray` grids, queue-like lists, and simple tuples for positions. |
| Cellular automata and procedural visuals are good fits for an LED matrix because they produce readable motion at low resolution. | `DemosGame` includes Conway's Life, Langton's ants, a flood-fill animation, a fire effect, an auto-playing snake variant, a Matrix digital rain effect, a 3D Starfield simulation, a sine-wave RGB plasma simulation ("PLASMA"), a rotating and scaling 3D wireframe cube ("CUBE"), a layered orbit particle sculpture ("ORBIT"), a radial warp-speed star tunnel ("WARP"), a bouncing logo ("BOUNCE"), a zooming vector tunnel ("TUNNEL"), and a vector-driven polygon animation ("MYSTIFY"). |
| Memory pressure can change which demos are active on embedded hardware. | The demo list is conditionally populated. If `CONFIG_LOW_RAM_MODE` is enabled, only Snake, Life, Plasma, and Cube are enabled. |
