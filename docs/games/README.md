# Game Documentation

This folder documents every game selectable from the DIY Arcade Machine menu.
Each file combines gameplay notes with technical descriptions in two views:

- **Language-agnostic**: the game logic, rules, state transitions, and rendering ideas.
- **Python in this repository**: where the same ideas live in `arcade_app.py` and how they are represented here.

## Games

**DEMOS** is always the first entry in the menu; all other games are listed alphabetically.

| Game ID | Name | File |
| --- | --- | --- |
| `DEMOS` | Demo Showcase | [DEMOS.md](./DEMOS.md) |
| `2048` | 2048 | [2048.md](./2048.md) |
| `ASTRD` | Asteroids | [ASTRD.md](./ASTRD.md) |
| `BEJWL` | Bejeweled | [BEJWL.md](./BEJWL.md) |
| `BRKOUT` | Breakout | [BRKOUT.md](./BRKOUT.md) |
| `CAVEFL` | Cave Flyer | [CAVEFL.md](./CAVEFL.md) |
| `DODGE` | Dodge | [DODGE.md](./DODGE.md) |
| `DOOMLT` | Doom Lite | [DOOMLT.md](./DOOMLT.md) |
| `FLAPPY` | Flappy Bird | [FLAPPY.md](./FLAPPY.md) |
| `LANDER` | Lunar Lander | [LANDER.md](./LANDER.md) |
| `LOCO` | LocoMotion | [LOCO.md](./LOCO.md) |
| `MAZE` | Maze Explorer | [MAZE.md](./MAZE.md) |
| `PACMAN` | Pac-Man | [PACMAN.md](./PACMAN.md) |
| `PITFAL` | Pitfall Runner | [PITFAL.md](./PITFAL.md) |
| `PONG` | Pong | [PONG.md](./PONG.md) |
| `QIX` | Qix | [QIX.md](./QIX.md) |
| `REVRS` | Othello/Reversi | [REVRS.md](./REVRS.md) |
| `RTYPE` | R-Type Shooter | [RTYPE.md](./RTYPE.md) |
| `SIMON` | Simon Says | [SIMON.md](./SIMON.md) |
| `SNAKE` | Snake | [SNAKE.md](./SNAKE.md) |
| `SOKO` | Sokoban | [SOKO.md](./SOKO.md) |
| `TETRIS` | Tetris | [TETRIS.md](./TETRIS.md) |
| `TRON` | Tron Lightcycle | [TRON.md](./TRON.md) |
| `UFODEF` | UFO Defense | [UFODEF.md](./UFODEF.md) |

## Shared technical context

- All games render into the same **64×64 LED matrix layout** with a **58-pixel playfield** and a **6-pixel HUD**.
- The project runs on **MicroPython + HUB75 hardware** and on **CPython + PyGame**.
- Scores are persisted through the shared `HighScores` flow in `arcade_app.py`.
- The game selector is implemented by `GameSelect` in `arcade_app.py`.
