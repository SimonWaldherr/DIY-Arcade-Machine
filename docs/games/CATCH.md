# Catch (`CATCH`)

## Gameplay

- Move the basket left and right to catch falling stars.
- Use the faster slide movement when you need to cover more ground quickly.
- Avoid bombs and do not miss too many stars.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| A catching game needs a controllable catcher, falling items, and score tracking. | `CatchGame` keeps basket position, active drops, missed stars, and the current score. |
| Different item types can share the same fall logic while changing the collision result. | Each drop stores its x/y position, speed, bomb flag, and color hue in a compact list. |
| Difficulty should ramp up as the score increases. | Spawn speed increases over time and the drop interval tightens every five points. |
| The catcher should feel responsive even on a small display. | Holding `Z` makes the basket move faster than the normal left/right step. |
