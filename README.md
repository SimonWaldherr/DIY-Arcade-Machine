# DIY Arcade Machine

[![Short video of the DIY Arcade Console in action (on YouTube)](https://img.youtube.com/vi/3mumzf_0GiM/0.jpg)](https://www.youtube.com/watch?v=3mumzf_0GiM)

A complete mini arcade system that runs on **both hardware and desktop**: play a collection of classic-inspired games on a **64×64 RGB LED matrix** (HUB75 + MicroPython) or on your computer with a **PyGame-based emulator**.

## Features

- **Dual Runtime Support**
  - **MicroPython + HUB75 LED Matrix**: Runs on RP2040-based boards (Interstate 75)
  - **Desktop (CPython) + PyGame**: Full emulator for development and testing
- **16+ Built-in Games**: Simon, Snake, Pong, Breakout, Tetris, Asteroids, Qix, Maze, Flappy, PacMan, R-Type, Cave Flyer, Pitfall, Lunar Lander, UFO Defense, Doom-Lite, and more
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
  - [MicroPython Setup](#micropython-setup)
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
   python main.py
   ```

A 640×640 window will appear showing the emulated LED matrix (10× scale).

### MicroPython Setup

#### Quick Method (Recommended)

The project now uses a **tiny bootstrap** approach to avoid on-device compilation memory errors:

1. **Install `mpy-cross`** (optional but highly recommended):
   ```bash
   brew install micropython  # macOS
   # or: pip install mpy-cross
   ```

2. **Connect your Interstate 75** via USB

3. **Upload with the interactive script**:
   ```bash
   ./upload.sh
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

## Game List

The arcade includes **16+ games** accessible via the main menu:

| Game ID | Name | Description |
|---------|------|-------------|
| `DEMOS` | Demo Showcase | Zero-player demos: Snake, Conway's Life, Langton's Ants, Floodfill Maze, Fire |
| `SIMON` | Simon Says | Memory sequence game with colored quadrants |
| `SNAKE` | Snake | Classic snake with red/green targets, wraparound |
| `PONG` | Pong | Paddle vs. AI, increasing difficulty |
| `BRKOUT` | Breakout | Brick breaker with rainbow bricks |
| `ASTRD` | Asteroids | Rotate, thrust, shoot asteroids in space |
| `QIX` | Qix | Territory capture, avoid the enemy |
| `TETRIS` | Tetris | Falling blocks with line clearing |
| `MAZE` | Maze Explorer | Fog-of-war maze with gems, enemies, shooting |
| `FLAPPY` | Flappy Bird | Navigate through moving pipe gaps |
| `RTYPE` | R-Type Shooter | Side-scrolling endless shooter |
| `PACMAN` | Pac-Man | Collect pellets, avoid ghosts, power pellets |
| `CAVEFL` | Cave Flyer | Tunnel navigation (starts wide, narrows progressively) |
| `PITFAL` | Pitfall Runner | Endless runner with snakes, pits, treasures (safe start zone) |
| `LANDER` | Lunar Lander | Multi-level landing challenge (increasing difficulty) |
| `UFODEF` | UFO Defense | Missile Command-style defense (diagonal control) |
| `DOOMLT` | Doom Lite | Mini raycaster FPS with enemies |

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
