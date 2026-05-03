# Doom Lite (`DOOMLT`)

## Gameplay

- Explore a compact pseudo-3D arena and clear enemy waves.
- Shoot enemies before they reach you.
- Survive long enough to push the wave count and score upward.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| A raycaster turns a 2D tile map into a first-person column view by casting rays per screen column. | `DoomLiteGame` uses a DDA-style raycasting pass across a compact map. |
| Enemies, player shots, and wave progression sit on top of the same 2D navigation map. | The class combines map traversal, enemy AI, lives, and shooting in one loop. |
| Precomputed trigonometric tables reduce repeated math cost in constrained environments. | The Python code builds sine and cosine lookup tables and switches strategy in low-RAM mode. |
| A simplified FPS can still communicate depth by using column height and distance shading. | Wall slices are drawn with distance-aware sizing and a minimap is also prepared for the HUD experience. |
