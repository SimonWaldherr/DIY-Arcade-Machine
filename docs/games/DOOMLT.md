# Doom Lite (`DOOMLT`)

## Gameplay

- Explore rotating pseudo-3D arenas and clear enemy waves.
- Shoot distinct enemy types before they reach you or get line-of-sight.
- Survive long enough to push the wave count and score upward.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| A raycaster turns a 2D tile map into a first-person column view by casting rays per screen column. | `DoomLiteGame` uses a DDA-style raycasting pass across a compact map. |
| Enemies, player shots, and wave progression sit on top of the same 2D navigation map. | The class combines map traversal, enemy AI, lives, shooting, and level switching in one loop. |
| Multiple compact maps keep later waves from feeling identical while preserving predictable memory use. | `DoomLiteGame.MAPS` stores four 16x16 arenas and rotates them as waves advance. |
| First-person enemies need a readable silhouette at very low resolution. | Enemy sprites are drawn as small billboards with head/body/leg profiles, bright eyes, and per-type colors instead of filled rectangles. |
| Precomputed trigonometric tables reduce repeated math cost in constrained environments. | The Python code builds sine and cosine lookup tables and switches strategy in low-RAM mode. |
| A simplified FPS can still communicate depth by using column height and distance shading. | Wall slices are drawn with distance-aware sizing and a minimap is also prepared for the HUD experience. |
