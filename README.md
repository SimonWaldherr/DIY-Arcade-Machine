# DIY-Arcade-Machine

[![Short video of the DIY Arcade Console in action (on YouTube)](https://img.youtube.com/vi/3mumzf_0GiM/0.jpg)](https://www.youtube.com/watch?v=3mumzf_0GiM)

## My Very Own Arcade Machine

Welcome to the DIY-Arcade-Machine project! This is a hands-on project to build your very own arcade machine using the Interstate 75 - RGB LED Matrix Driver from Pimoroni (PIM584), a 64x64 Pixel RGB LED Matrix with a Hub75 connector, and a KY-023 Joystick Module (or a Nunchuck). The project includes several games inspired by the classics: Simon, Snake, Qix, Breakout, Tetris, Asteroid, and Pong, all playable on a vibrant LED matrix display.

Don’t have the hardware yet? You can still try out the games by running the [PyGame Branch](https://github.com/SimonWaldherr/DIY-Arcade-Machine/tree/pygame), which simulates the experience on your PC or Mac.

## Table of Contents

- [Hardware Requirements](#hardware-requirements)
- [Software Requirements](#software-requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Games](#games)
  - [Simon](#simon)
  - [Asteroid](#asteroid)
  - [Snake](#snake)
  - [Pong](#pong)
  - [Breakout](#breakout)
  - [Qix / Xonix](#qix)
  - [Tetris](#tetris)
- [Fun](#fun)

## Hardware Requirements

- **Interstate 75 (W) by Pimoroni (PIM584)**
  - Available at: [Pimoroni](https://shop.pimoroni.com/products/interstate-75?variant=39443584417875) | [DigiKey](https://www.digikey.de/de/products/detail/pimoroni-ltd/PIM584/15851385) | [Adafruit](https://www.adafruit.com/product/5342) | [BerryBase](https://www.berrybase.de/pimoroni-interstate-75-controller-fuer-led-matrizen)
- **64x64 Pixel RGB LED Matrix with Hub75 connector**  
  - [Amazon link](https://amzn.to/3Yadyhh)
- **Joystick options**  
  - [Adafruit Wii Nunchuck Breakout Adapter](https://www.berrybase.de/adafruit-wii-nunchuck-breakout-adapter) + [Nunchuk](https://www.amazon.de/dp/B0D4V5JC71)
- **Wiring and Power Supply**
- **Optional 3D-printed enclosures**  
  - [LED Matrix Case](https://www.thingiverse.com/thing:6751325) or [the tilted version](https://www.thingiverse.com/thing:6781604)
- **Optional Mesh and Diffuser**  
  - [Mesh](https://www.thingiverse.com/thing:6751323)  
  - [Satin-Finished Plexiglass](https://acrylglas-shop.com/plexiglas-gs-led-9h04-sc-black-white-hinterleuchtung-3-mm-staerke)

## Software Requirements

- [MicroPython](https://github.com/pimoroni/pimoroni-pico/releases/download/v1.23.0-1/pico-v1.23.0-1-pimoroni-micropython.uf2)
- [Thonny IDE](https://thonny.org/)

## Installation

### 1. Set up your Microcontroller with MicroPython
- Follow the instructions for your microcontroller to flash it with MicroPython.

### 2. Connect the Hardware
- Connect the Interstate 75 to the RGB LED Matrix using the Hub75 connector.
- Connect the Nunchuck to the microcontroller.

### 3. Upload the Code
- Use Thonny (or another compatible tool) to copy the provided Python script to your microcontroller.

## Usage

### 1. Power Up
- Ensure all connections are secure, then power up the microcontroller.

### 2. Start the Game Selector
- Once powered, the game selector interface will appear on the LED matrix.

### 3. Select a Game
- Use the joystick to navigate the menu and select a game. Press the joystick button to start.

### 4. Play
- Refer to the instructions below for controls on each game.

### 5. Exit a Game
- To exit a game and return to the menu, press both joystick buttons simultaneously.

## Games

### Simon
A memory game where the player must recall and repeat a sequence of colors.
- **Controls**: Use the joystick to select the flashed color. Repeat the sequence as it grows.

### Asteroid
A classic shooter where the goal is to destroy asteroids.
- **Controls**: Use the joystick to rotate and move your ship. Press the button to shoot.

### Snake
Guide the snake to eat targets and grow in length, but avoid hitting the walls or yourself.
- **Controls**: Use the joystick to control the snake's direction (UP, DOWN, LEFT, RIGHT).

### Pong
A classic two-player table tennis game, where you control a paddle to keep the ball in play.
- **Controls**: Move the paddle up and down using the joystick.

### Breakout
Break the bricks with the ball without letting it fall off the screen.
- **Controls**: Use the joystick to move the paddle left and right. Break as many bricks as possible!

### Qix
Claim territory while avoiding enemies. Move strategically to win.
- **Controls**: Move with the joystick to claim territory while avoiding enemy contact.  
  - For a version written in Go using the Ebiten engine, [click here](https://github.com/SimonWaldherr/golang-examples/blob/master/non-std-lib/ebiten-qix.go).

### Tetris
Stack blocks to form complete lines and score points.
- **Controls**: Use the joystick to move and rotate the blocks. Speed them up by moving them down.

### Maze
A simple maze game

## Fun

Enjoy building and gaming on your very own DIY-Arcade-Machine! If you encounter any issues or need assistance, feel free to open an issue or reach out.

**Happy Gaming!**

