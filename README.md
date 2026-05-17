# DIY Arcade Machine

![Python](https://img.shields.io/badge/Python-3.x-blue?style=flat-square&logo=python)
![MicroPython](https://img.shields.io/badge/MicroPython-RP2040-green?style=flat-square)
![PyGame](https://img.shields.io/badge/PyGame-CE-yellow?style=flat-square)
[![Deploy to GitHub Pages](https://github.com/SimonWaldherr/DIY-Arcade-Machine/actions/workflows/deploy-pages.yml/badge.svg)](https://github.com/SimonWaldherr/DIY-Arcade-Machine/actions/workflows/deploy-pages.yml)

[![Short video of the DIY Arcade Console in action (on YouTube)](https://img.youtube.com/vi/3mumzf_0GiM/0.jpg)](https://www.youtube.com/watch?v=3mumzf_0GiM)

A complete mini arcade system that runs on **hardware, desktop, and in the browser**: play a collection of classic-inspired games on a **64×64 RGB LED matrix** (HUB75 + MicroPython), on your computer with a **PyGame emulator**, or directly in the browser via **WebAssembly (pygbag)**.

## Features

- **Triple Runtime Support**
  - **MicroPython + HUB75 LED Matrix**: Runs on RP2040-based boards (Interstate 75)
  - **Desktop (CPython) + PyGame**: Full emulator for development and testing
  - **Browser (WebAssembly) + pygbag**: Play directly in any modern browser, no install needed
- **39 Built-in Games**: Classics, puzzle games, racers, shooters, reflex challenges, and compact original arcade games built for the 64×64 matrix
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

- [Quick Start](#quick-start)
- [Web build (Pygbag)](#web-build-pygbag)
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

## Quick Start

### Run on desktop

```bash
pip install pygame-ce        # or: make install
python main.py               # or: make run
```

### Test in browser locally

```bash
pip install pygame-ce pygbag==0.9.2   # or: make web-install
python -m pygbag .                    # build + serve at http://localhost:8000
# Safari: make web-safari (adds required COOP+COEP headers)
```

### Deploy to GitHub Pages

Push to `main` — the [GitHub Actions workflow](.github/workflows/deploy-pages.yml) builds the
WebAssembly bundle with `python -m pygbag --build .` (Python 3.11) and deploys it to GitHub Pages automatically.

---

## Web build (Pygbag)

**Local preview** (build + serve at `http://localhost:8000`):
```bash
pip install pygame-ce pygbag==0.9.2
python -m pygbag .
```

**CI / offline bundle** (writes to `build/web/`):
```bash
python -m pygbag --build .
```

**GitHub Pages**: in your repo go to *Settings → Pages → Source* and select **GitHub Actions**. Every push to `main` triggers the workflow which builds and deploys automatically.

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
- pygame-ce 2.x (Community Edition — drop-in replacement for pygame)

---

## Installation

### Desktop Setup

1. **Install dependencies**:
   ```bash
   pip install pygame-ce
   ```

2. **Run the game**:
   ```bash
   make run
   # or manually: python main.py
   ```

A 640×640 window will appear showing the emulated LED matrix (10× scale).

### Browser Setup (pygbag)

[pygbag](https://pygame-web.github.io/) packages the game as WebAssembly so it runs in any modern browser — no Python installation needed.

1. **Install dependencies**:
   ```bash
   pip install pygame-ce pygbag==0.9.2
   # or via make: make web-install
   ```

2. **Build and serve locally**:
   ```bash
   python -m pygbag .    # build + serve at http://localhost:8000
   make web              # same, via Makefile (Chrome / Firefox)
   make web-safari       # Safari (adds required COOP+COEP headers)
   ```

3. **Controls in browser**: same keyboard mapping as desktop — Arrow Keys, `Z`/`Space` to confirm, `X`/`Escape` to cancel.

> **Browser support:** Chrome and Firefox work out of the box. Safari requires `Cross-Origin-Isolation` headers (`make web-safari` handles this automatically).
>
> **Automated deployment:** every push to `main` triggers the GitHub Actions workflow which builds with `python -m pygbag --build .` (Python 3.11) and deploys the result to GitHub Pages automatically.
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

The arcade includes demo animations and over 30 games. Each game is documented in detail in the [Game Documentation](./docs/games/README.md) with gameplay notes and technical descriptions.

Detailed per-game documentation is available in [docs/games](./docs/games/README.md).

| Game ID | Name | Description |
|---------|------|-------------|
| `DEMOS` | Demo Showcase | Zero-player demos: Snake, Life, Cube, Spark, Plasma, Orbit, Warp, Bounce, Tunnel, Matrix, Fire |
| `2048` | 2048 | Sliding tile puzzle with merge scoring |
| `ARENA` | Arena | Top-down wave survival with movement and shooting |
| `ASTRD` | Asteroids | Rotate, thrust, shoot asteroids in space |
| `BEJWL` | Bejeweled | Match-3 gem swapping puzzle |
| `BOMBER` | Bomber | Timed bombs, block clearing, and maze enemies |
| `BRKOUT` | Breakout | Brick breaker with rainbow bricks |
| `CATCH` | Catch | Catch stars, avoid bombs, and keep the basket moving |
| `CAVEFL` | Cave Flyer | Tunnel navigation (starts wide, narrows progressively) |
| `CGOLG` | Conway's Game of Life Game | Competitive Life battle with directed gliders and spaceships |
| `CLIMB` | Climber | Platform-jumping tower climb with scrolling height |
| `DEFUSE` | Defuse | Cut colored wires in sequence before the timer expires |
| `DODGE` | Dodge | Avoid falling blocks, dash to dodge |
| `DOOMLT` | Doom Lite | Mini raycaster FPS with rotating levels and enemy sprites |
| `FLAPPY` | Flappy Bird | Navigate through moving pipe gaps |
| `FROGGR` | Frogger | Hop across traffic lanes and advance through harder levels |
| `GOLF` | Golf | Tiny minigolf courses with aim, power, bounces, and obstacles |
| `INVADR` | Invaders | Shoot marching alien waves, protect shields, hit saucers |
| `LANDER` | Lunar Lander | Multi-level landing challenge (increasing difficulty) |
| `LASER` | Laser | Mirror-rotation puzzle: guide the beam into the target |
| `LOCO` | LocoMotion | Rotating railway puzzle with train routing |
| `MAZE` | Maze Explorer | Fog-of-war maze with gems, enemies, shooting |
| `MINES` | Mines | Minesweeper-style reveal puzzle for the LED matrix |
| `PACMAN` | Pac-Man | Collect pellets, avoid ghosts, power pellets |
| `PAIRS` | Pairs | Memory card matching on a 4x4 board |
| `PITFAL` | Pitfall Runner | Endless runner with snakes, pits, treasures (safe start zone) |
| `PONG` | Pong | Paddle vs. AI, increasing difficulty |
| `QIX` | Qix | Territory capture, avoid the enemy |
| `RAYRCR` | Ray Racer | Raytrace-style anti-grav racing with boost, energy gates, and rival hovercars |
| `REVRS` | Othello/Reversi | Board game with simple CPU opponent |
| `RTYPE` | R-Type Shooter | Side-scrolling endless shooter |
| `SIMON` | Simon Says | Memory sequence game with colored quadrants |
| `SKYWAR` | Sky War | Helicopter battlefield shooter with air and ground targets |
| `SNAKE` | Snake | Classic snake with red/green targets, wraparound |
| `SOKO` | Sokoban | Crate-pushing puzzle levels |
| `STACK` | Stacker | Timing game: trim and stack moving blocks |
| `TETRIS` | Tetris | Falling blocks with line clearing |
| `TRON` | Tron Lightcycle | Leave a trail, steer 90° turns, dodge the enemy cycle |
| `TWRDEF` | Tower Defense | Build and upgrade towers to stop enemy waves on a winding path |
| `UFODEF` | UFO Defense | Missile Command-style defense (diagonal control) |
| `WINGS` | Wings | Carrier strike game with fuel, ammo, targets, and landing |

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
