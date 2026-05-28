# Lunar Lander (`LANDER`)

## Gameplay

Rotate the lander, use thrust carefully, and spend fuel efficiently. Touch down softly on the landing pad to reach the next level. Hard impacts or bad landing angles cause a crash.

## Technical details

Lunar Lander combines gravity, thrust, rotation, collision with terrain, and a safe landing zone. In this repository, `LunarLanderGame` tracks floating-point position, velocity, angle, fuel, and terrain geometry. Later levels can increase challenge by shrinking the pad and strengthening gravity. In this repository, Level progression reduces pad width, lowers available fuel, and raises gravity over time. Landing quality can depend on vertical speed, horizontal speed, and angle at contact. In this repository, Successful touchdowns award extra score for remaining fuel and favorable landing angle. Trigonometric control is easier to optimize with lookup tables on small devices. In this repository, The game precomputes angle-based sine and cosine values for ship rendering and thrust direction.
