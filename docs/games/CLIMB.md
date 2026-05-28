# Climber (`CLIMB`)

## Gameplay

Drift left and right to land on platforms. Use `Z` for a short jet-assisted jump. Keep climbing; falling below the screen ends the run.

## Technical details

A vertical climbing game needs gravity, bounce platforms, wraparound movement, and scrolling. In this repository, `ClimberGame` updates the player's velocity, platform collisions, and vertical scroll offset each frame. Difficulty comes from platform spacing and width. In this repository, New platforms are generated above the visible area and shrink as score increases. The display should keep motion legible. In this repository, Platforms are horizontal colored bars and the player is a bright 4x4 block.
