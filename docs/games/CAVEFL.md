# Cave Flyer (`CAVEFL`)

## Gameplay

- Fly through a scrolling tunnel that gradually becomes tighter.
- Stay inside the open gap while the cave walls drift.
- A single wall collision ends the run.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| Endless tunnel games are driven by a stream of wall boundaries rather than full-map generation. | `CaveFlyGame` keeps left and right cave edges for each visible row in a ring-buffer style structure. |
| Difficulty rises by reducing the safe gap width over time. | The tunnel starts wider and narrows as the score increases, with a minimum clamp. |
| Direct flight control can avoid gravity entirely and focus on positional precision. | The player moves laterally through the cave instead of using a jump-or-fall model. |
| Ring buffers are a good fit for scrolling terrain because they avoid shifting full arrays every frame. | The implementation advances a head pointer and rewrites only the newest tunnel row. |
