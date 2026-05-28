# Golf (`GOLF`)

## Gameplay

Aim with left and right. Adjust power with up and down. Press `Z` to shoot and putt the ball into the hole. Too many strokes on one hole ends the run.

## Technical details

A minigolf game needs aim, power, ball physics, walls, obstacles, and a cup. In this repository, `GolfGame` tracks angle, power, velocity, friction, wall bounces, obstacle collisions, and hole progression. Scoring should reward clean play. In this repository, Each completed hole adds points based on low stroke count and hole number. The small screen needs simple visual targets. In this repository, The aim line, power bar, bright ball, outlined cup, and block obstacles are drawn directly on the matrix.
