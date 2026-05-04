# DIY Arcade Machine

![Python](https://img.shields.io/badge/Python-3.x-blue?style=flat-square&logo=python)
![MicroPython](https://img.shields.io/badge/MicroPython-RP2040-green?style=flat-square)
![PyGame](https://img.shields.io/badge/PyGame-Supported-yellow?style=flat-square)

[![Short video of the DIY Arcade Console in action (on YouTube)](https://img.youtube.com/vi/3mumzf_0GiM/0.jpg)](https://www.youtube.com/watch?v=3mumzf_0GiM)

A complete mini arcade system that runs on **hardware, desktop, and in the browser**: play a collection of classic-inspired games on a **64×64 RGB LED matrix** (HUB75 + MicroPython), on your computer with a **PyGame emulator**, or directly in the browser via **WebAssembly (pygbag)**.

## Features

- **Triple Runtime Support**
  - **MicroPython + HUB75 LED Matrix**: Runs on RP2040-based boards (Interstate 75)
  - **Desktop (CPython) + PyGame**: Full emulator for development and testing
  - **Browser (WebAssembly) + pygbag**: Play directly in any modern browser, no install needed
- **24 Built-in Games**: Simon, Snake, Pong, Breakout, Tetris, Asteroids, Qix, Maze, Flappy, PacMan, R-Type, Cave Flyer, Pitfall, Lunar Lander, UFO Defense, Doom-Lite, Bejeweled, Sokoban, and more
- **Intro Screen**: Animated logo display on startup
- **64×64 Display Layout**
  - 58-pixel playfield (rows 0-57)
  - 6-pixel HUD at bottom (score + clock)
- **High Score System**: Persistent scores with 3-letter initials entry
- **Memory-Optimized**: Buffered framebuffer, packed grid storage, lazy font loading
- **Controller Support**
  - MicroPython: Wii Nunchuk-style I2C controller (with auto-detection for variants)
  - Desktop: Keyboard emulation (arrow keys + Z/X)

---

## Table of Contents

- [Hardware Requirements](#hardware-requirements)
- [Software Requirements](#software-requirements)
- [Installation](#installation)
  - [Desktop Setup](#desktop-setup)
  - [Browser Setup (pygbag)](#browser-setup-pygbag)
  - [MicroPython Setup](#micropython-setup)
- [Make Commands](#make-commands)
- [Game List](#game-list)
- [Controls](#controls)
- [Usage](#usage)
- [Architecture](#architecture)
- [Troubleshooting](#troubleshooting)

---

## Hardware Requirements

### For Physical Arcade Machine

- **Interstate 75 (W) by Pimoroni (PIM584)** - RP2040-based HUB75 driver board
  - [Pimoroni](https://shop.pimoroni.com/products/interstate-75?variant=39443584417875) | [DigiKey](https://www.digikey.de/de/products/detail/pimoroni-ltd/PIM584/15851385) | [Adafruit](https://www.adafruit.com/product/5342) | [BerryBase](https://www.berrybase.de/pimoroni-interstate-75-controller-fuer-led-matrizen)
- **64×64 Pixel RGB LED Matrix** with HUB75 connector
  - [Example on Amazon](https://amzn.to/3Yadyhh)
- **Controller** (one of):
  - [Wii Nunchuk](https://www.amazon.de/dp/B0D4V5JC71) + [Breakout Adapter](https://www.berrybase.de/adafruit-wii-nunchuck-breakout-adapter)
  - Compatible I2C joystick module
- **Power Supply**: 5V adequate for LED matrix (typically 2-4A)
- **Optional**:
  - [3D-Printed Enclosure](https://www.thingiverse.com/thing:6751325) or [Tilted Version](https://www.thingiverse.com/thing:6781604)
  - [Diffuser Mesh](https://www.thingiverse.com/thing:6751323)
  - [Satin Plexiglass Diffuser](https://acrylglas-shop.com/plexiglas-gs-led-9h04-sc-black-white-hinterleuchtung-3-mm-staerke)

---

## Software Requirements

### MicroPython Hardware

- [MicroPython Firmware](https://github.com/pimoroni/pimoroni-pico/releases/download/v1.23.0-1/pico-v1.23.0-1-pimoroni-micropython.uf2) (Pimoroni build recommended)
- Optional: [Thonny IDE](https://thonny.org/) for uploading files
- Optional: `mpy-cross` for compiling to bytecode (reduces boot RAM usage)

### Desktop

- Python 3.7+
- PyGame 2.x

---

## Installation

### Desktop Setup

1. **Install dependencies**:
   ```bash
   pip install pygame
   ```

2. **Run the game**:
   ```bash
   make run
   # or manually: python main.py
   ```

A 640×640 window will appear showing the emulated LED matrix (10× scale).

### Browser Setup (pygbag)

[pygbag](https://pygame-web.github.io/) packages the PyGame emulator as WebAssembly so it runs in any modern browser — no Python installation needed.

1. **Install pygbag**:
   ```bash
   make web-install
   # or manually: pip install pygbag
   ```

2. **Build and serve**:
   ```bash
   make web           # Chrome / Firefox
   make web-safari    # Safari (adds required COOP+COEP headers)
   ```

   pygbag bundles the game and starts a local server. Navigate to `http://localhost:8000` when prompted.

3. **Controls in browser**: same keyboard mapping as desktop — Arrow Keys, `Z`/`Space` to confirm, `X`/`Escape` to cancel.

> **Browser support:** Chrome and Firefox work out of the box. Safari requires `Cross-Origin-Isolation` headers (`make web-safari` handles this automatically).
>
> **Note:** High scores are stored in-memory while the page is open and reset on page reload.

### MicroPython Setup

#### Quick Method (Recommended)

The project now uses a **tiny bootstrap** approach to avoid on-device compilation memory errors:

1. **Install `mpy-cross`** (optional but highly recommended):
   ```bash
   brew install micropython  # macOS
   # or: pip install mpy-cross
   ```

2. **Connect your Interstate 75** via USB

3. **Upload with Make**:
   ```bash
   make upload
   # or manually: ./upload.sh
   ```
   
   The script will:
   - Auto-detect connected devices
   - Compile `arcade_app.py` → `arcade_app.mpy` (if `mpy-cross` available)
   - Upload both `main.py` (tiny bootstrap) and the compiled module

4. **Reboot the device** - games start automatically

#### Manual Method

If you prefer manual upload via Thonny or `ampy`:

1. Flash MicroPython firmware to Interstate 75
2. Upload `main.py` (tiny bootstrap file)
3. Upload `arcade_app.py` or `arcade_app.mpy` (the main application)
4. Optional: Upload `highscores.json` if you want to preserve scores

---

## Make Commands

For ease of use, a `Makefile` is provided with the following commands:

- `make install`: Installs desktop dependencies (PyGame)
- `make run`: Runs the PyGame emulator locally (`python main.py`)
- `make web-install`: Installs pygbag for browser/WebAssembly builds
- `make web`: Builds the WebAssembly version and serves it at `http://localhost:8000`
- `make upload`: Compiles and uploads the code to the hardware (`./upload.sh`)
- `make build`: Precompiles `arcade_app.py` into bytecode (`arcade_app.mpy`)
- `make clean`: Cleans up previous build artifacts and pycache
- `make clean-all`: Cleans up all files and the python virtual environment

---

## Game List

The arcade includes **24 games** accessible via the main menu. **DEMOS** always appears at the top; all other games are listed alphabetically.

Detailed per-game documentation is available in [docs/games](./docs/games/README.md).

| Game ID | Name | Description |
|---------|------|-------------|
| `DEMOS` | Demo Showcase | Zero-player demos: Snake, Life, Plasma, Cube, Tunnel, Matrix, Fire |
| `2048` | 2048 | Sliding tile puzzle with merge scoring |
| `ASTRD` | Asteroids | Rotate, thrust, shoot asteroids in space |
| `BEJWL` | Bejeweled | Match-3 gem swapping puzzle |
| `BRKOUT` | Breakout | Brick breaker with rainbow bricks |
| `CAVEFL` | Cave Flyer | Tunnel navigation (starts wide, narrows progressively) |
| `DODGE` | Dodge | Avoid falling blocks, dash to dodge |
| `DOOMLT` | Doom Lite | Mini raycaster FPS with rotating levels and enemy sprites |
| `FLAPPY` | Flappy Bird | Navigate through moving pipe gaps |
| `LANDER` | Lunar Lander | Multi-level landing challenge (increasing difficulty) |
| `LOCO` | LocoMotion | Sliding railway puzzle with train routing |
| `MAZE` | Maze Explorer | Fog-of-war maze with gems, enemies, shooting |
| `PACMAN` | Pac-Man | Collect pellets, avoid ghosts, power pellets |
| `PITFAL` | Pitfall Runner | Endless runner with snakes, pits, treasures (safe start zone) |
| `PONG` | Pong | Paddle vs. AI, increasing difficulty |
| `QIX` | Qix | Territory capture, avoid the enemy |
| `REVRS` | Othello/Reversi | Board game with simple CPU opponent |
| `RTYPE` | R-Type Shooter | Side-scrolling endless shooter |
| `SIMON` | Simon Says | Memory sequence game with colored quadrants |
| `SNAKE` | Snake | Classic snake with red/green targets, wraparound |
| `SOKO` | Sokoban | Crate-pushing puzzle levels |
| `TETRIS` | Tetris | Falling blocks with line clearing |
| `TRON` | Tron Lightcycle | Leave a trail, steer 90° turns, dodge the enemy cycle |
| `UFODEF` | UFO Defense | Missile Command-style defense (diagonal control) |

Each game tracks high scores with optional initials entry.

---

## Controls

### Common Controls

**Menu Navigation**:
- **Up/Down**: Navigate menu
- **Z (or Space/Enter)**: Select/Confirm
- **C (or X/Escape)**: Back/Cancel

**In-Game**:
- **Directional movement**: Arrow keys / Joystick
- **Primary action** (jump/shoot/rotate): Z button / Space / Enter
- **Secondary/Back**: C button / X / Escape

### Desktop Keyboard Mapping

| Action | Keys |
|--------|------|
| Move | Arrow Keys |
| Confirm/Action | `Z`, `Space`, or `Enter` |
| Back/Cancel | `X` or `Escape` |

### MicroPython Controller

- **I2C Address**: 0x52 (standard Nunchuk)
- **Pins**: SCL=21, SDA=20 (configurable in code)
- **Buttons**:
  - **C button**: Back/Cancel
  - **Z button**: Confirm/Action
- **Analog stick**: 8-directional movement (includes diagonals)

The code auto-detects controller variants including the "new signature" controllers (`A0 20 10 00 FF FF`).
