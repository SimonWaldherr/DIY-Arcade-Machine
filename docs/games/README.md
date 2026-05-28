# Game Documentation

This folder documents the games selectable from the DIY Arcade Machine menu. The pages follow the registry order in `arcade_app.py`, so `DEMOS` comes first and the remaining entries track the live menu rather than the older commented-out prototypes.

## Games

`DEMOS` is always the first entry, and the active game pages are [2048](./2048.md), [ARENA](./ARENA.md), [ARTILL](./ARTILL.md), [ASTRD](./ASTRD.md), [BEJWL](./BEJWL.md), [BOMBER](./BOMBER.md), [BRKOUT](./BRKOUT.md), [BTLZON](./BTLZON.md), [CAVEFL](./CAVEFL.md), [CENTI](./CENTI.md), [CGOLG](./CGOLG.md), [CLIMB](./CLIMB.md), [DEFUSE](./DEFUSE.md), [DOOMLT](./DOOMLT.md), [FLAPPY](./FLAPPY.md), [FROGGR](./FROGGR.md), [GOLF](./GOLF.md), [INVADR](./INVADR.md), [KEEN](./KEEN.md), [LANDER](./LANDER.md), [LASER](./LASER.md), [LOCO](./LOCO.md), [MAZE](./MAZE.md), [MINES](./MINES.md), [PACMAN](./PACMAN.md), [PAIRS](./PAIRS.md), [PINBAL](./PINBAL.md), [PITFAL](./PITFAL.md), [PONG](./PONG.md), [QIX](./QIX.md), [RAYRCR](./RAYRCR.md), [REVRS](./REVRS.md), [RTYPE](./RTYPE.md), [SABOTR](./SABOTR.md), [SIMON](./SIMON.md), [SNAKE](./SNAKE.md), [SOCCER](./SOCCER.md), [SOKO](./SOKO.md), [STACK](./STACK.md), [TETRIS](./TETRIS.md), [TRON](./TRON.md), [TWRDEF](./TWRDEF.md), and [UFODEF](./UFODEF.md).

## Shared technical context

All games render into the same **64×64 LED matrix layout** with a **58-pixel playfield** and a **6-pixel HUD**. The project runs on **MicroPython + HUB75 hardware** and on **CPython + PyGame**. Scores are persisted through the shared `HighScores` flow in `arcade_app.py`, and the game selector itself is implemented by `GameSelect` in `arcade_app.py`.
