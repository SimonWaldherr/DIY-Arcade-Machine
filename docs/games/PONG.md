# Pong (`PONG`)

## Gameplay

Control the left paddle and rally the ball against the AI paddle on the right. Missing the ball costs a life and score. Returning shots and scoring against the AI raises the total score.

## Technical details

Pong needs only two paddles, one ball, and simple reflection rules. In this repository, `PongGame` updates a single ball position and two vertical paddle positions each frame. An arcade version can use an opponent that follows the ball instead of full prediction. In this repository, The right paddle uses a deliberately imperfect chase heuristic that gets faster as the score rises. Miss detection and paddle hits are enough to create the core scoring loop. In this repository, Left-side misses remove a life, while right-side misses award bonus points. Low-resolution screens benefit from single-pixel or tiny-rectangle sprites. In this repository, The ball is drawn as a tiny object and the paddles are narrow vertical rectangles.
