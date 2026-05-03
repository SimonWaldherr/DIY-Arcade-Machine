# Demo Showcase (`DEMOS`)

## Gameplay

- This is a zero-player entry made for attract-mode style visuals.
- It rotates through self-running demos such as Snake, Conway's Life, fire, Langton's ants, and a flood-fill maze animation.
- There is no win condition and no score; the point is to showcase the display and game engine.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| A demo hub owns a list of autonomous simulations and swaps between them after a timed interval. | `DemosGame` stores the enabled demo ids in `self.demos` and cycles them inside its update loop. |
| Each simulation keeps its own compact state because it never needs player input. | The code uses lightweight structures such as `bytearray` grids, queue-like lists, and simple tuples for positions. |
| Cellular automata and procedural visuals are good fits for an LED matrix because they produce readable motion at low resolution. | `DemosGame` includes Conway's Life, Langton's ants, a flood-fill animation, a fire effect, and an auto-playing snake variant. |
| Memory pressure can change which demos are active on embedded hardware. | The demo list is reduced in low-RAM mode through `CONFIG_LOW_RAM_MODE`. |
