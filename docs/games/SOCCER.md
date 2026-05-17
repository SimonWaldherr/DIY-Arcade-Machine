# Championship Soccer (`SOCCER`)

## Gameplay

- Each team has one striker, two defenders, and one goalkeeper.
- The striker and defenders move in formation.
- The goalkeeper is computer controlled unless he has possession.
- Move the blue formation forward, backward, up, and down with the joystick.
- If the blue goalkeeper has the ball, the joystick controls him inside the goal area.
- Press `Z` while blue has the ball to shoot toward the red goal.
- The match has two halves; score as many goals as possible before time expires.

## Technical details

| Language-agnostic design | Python implementation in this repository |
| --- | --- |
| Atari-style soccer needs small teams, formation movement, ball possession, kicks, goals, and match timing. | `SoccerGame` stores team formations, ball state, goal counts, half number, and a countdown clock. |
| Formation play keeps the game readable on 64x64. | `_formation()` derives striker, defender, and goalkeeper positions from a compact anchor rather than simulating every player independently. |
| The ball should feel arcade-simple. | Possession sticks to the nearest player; kicks release the ball with velocity and wall/goal handling. |
