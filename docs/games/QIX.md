# Qix (`QIX`)

## Gameplay

- Move around the border and draw trails into empty territory.
- Closing a trail converts an area into claimed territory.
- Reach the required claimed percentage while avoiding enemy contact.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| Territory-capture games rely on a cell grid with values for empty, border, trail, and captured regions. | `QixGame` uses the shared packed grid helpers and explicit cell markers. |
| Flood-fill is the core algorithm for deciding which enclosed region is safe to claim. | The game calls the reusable `flood_fill()` support logic defined earlier in `arcade_app.py`. |
| Enemies create pressure by threatening trails before they become permanent walls. | Opponents move independently and cause a loss on contact with the player or exposed trail. |
| Progress is easier to communicate as territory percentage than raw points. | The HUD presents claimed-area progress and advancing a level increases the challenge. |
