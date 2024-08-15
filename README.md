# DIY-Arcade-Machine

## my very own arcade machine

Welcome to the DIY-Arcade-Machine project! This project is a fun and interactive way to create your very own arcade machine using the Interstate 75 - RGB LED Matrix Driver from Pimoroni (PIM584), a 64x64 Pixel RGB LED Matrix with Hub75 connector, and a KY-023 Joystick Module. The project includes three classic games: Simon, Snake, and Pong, all playable on a colorful LED matrix display.

## Table of Contents

- [Hardware Requirements](#hardware-requirements)
- [Software Requirements](#software-requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Games](#games)
  - [Simon](#simon)
  - [Snake](#snake)
  - [Pong](#pong)
  - [Breakout](#breakout)
  - TicTacToe / XXO
  - Qix / Xonix
- [Fun](#fun)

## Hardware Requirements

- [Interstate 75 (W) from Pimoroni (PIM584)](https://www.berrybase.de/pimoroni-interstate-75-controller-fuer-led-matrizen)
- [64x64 Pixel RGB LED Matrix with Hub75 connector](https://amzn.to/3Yadyhh)
- [KY-023 Joystick Module](https://www.az-delivery.de/products/joystick-modul)
- Connecting wires and power supply

## Software Requirements

- [MicroPython](https://github.com/pimoroni/pimoroni-pico/releases/download/v1.23.0-1/pico-v1.23.0-1-pimoroni-micropython.uf2)
- [Thonny](https://thonny.org/)

## Installation

1. **Set up your microcontroller with MicroPython**:
   - Follow the instructions for your specific microcontroller to install MicroPython.

2. **Connect the hardware**:
   - Connect the Interstate 75 to the RGB LED Matrix using the Hub75 connector.
   - Connect the KY-023 Joystick Module to the appropriate GPIO pins on the microcontroller.

3. **Upload the code**:
   - Copy the provided Python script to your microcontroller using a tool like Thonny.

## Usage

1. **Power up your microcontroller**:
   - Ensure that all components are properly connected and power up your microcontroller.

2. **Run the main script**:
   - The script will start the game selector interface on the LED matrix display.

3. **Select a game**:
   - Use the joystick to navigate and select a game from the menu. Press the joystick button to start the selected game.

## Games

### Simon

Simon is a memory game where the player must remember and repeat a sequence of colors.

- **Controls**:
  - Use the joystick to select the corresponding quadrant of the flashed color.
  - Repeat the sequence shown on the display.

### Snake

Snake is a classic game where the player controls a snake to eat targets and grow in length.

- **Controls**:
  - Use the joystick to control the direction of the snake (UP, DOWN, LEFT, RIGHT).
  - Avoid running into the snake's own body.

### Pong

Pong is a classic table tennis game where the player controls a paddle to hit a ball back and forth.

- **Controls**:
  - Use the joystick to move the paddle up and down.
  - Keep the ball in play to score points.

### Breakout

Breakout is the game where you break the wall bricks with a ball

- **Controls**:
  - Use the joystick to move the paddle left and right.
  - Keep the ball in play and break bricks to score points.

## Fun

Enjoy building and playing on your very own DIY-Arcade-Machine! If you have any questions or need further assistance, feel free to reach out.

Happy Gaming!
