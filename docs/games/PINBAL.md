# Pinball (`PINBAL`)

## Gameplay

Hold `Z` while the ball is in the launch lane to charge the plunger. Release `Z` to launch; longer hold means a stronger spring. Use left and right to trigger the flippers. Hit bumpers and targets to score. Lighting all targets raises the multiplier. The run ends after the last ball drains.

## Technical details

A compact pinball table needs launch control, flippers, bumpers, targets, gravity, drains, and scoring. In this repository, `PinballGame` tracks ball position/velocity, plunger charge, flipper input, bumpers, target lights, multiplier, balls, and score. The spring should feel tactile with one button. In this repository, Holding `Z` increases `charge`; releasing it launches the ball with charge-dependent velocity. Pinball collision needs to stay stable even when the ball is moving quickly. In this repository, The physics step uses small substeps plus circle and segment collision helpers for bumpers, posts, flippers, walls, and the launch lane. The LED matrix needs readable table elements. In this repository, Rendering draws rails, a plunger lane, bumpers, targets, flippers, ball, ball count, multiplier, and score.
