# DIY-Arcade-Machine

this branch contains the PyGame version - which emulates the real Arcade hardware.  

[![short video of the diy arcade console in action (on youtube)](https://img.youtube.com/vi/er3-OS2g9QY/0.jpg)](https://www.youtube.com/watch?v=er3-OS2g9QY)

## my very own arcade machine

Welcome to the DIY-Arcade-Machine project! This project is a fun and interactive way to create your very own arcade machine using the Interstate 75 - RGB LED Matrix Driver from Pimoroni (PIM584), a 64x64 Pixel RGB LED Matrix with Hub75 connector, and a KY-023 Joystick Module. The project includes six classic games: Simon, Snake, Qix, Breakout, Tic-Tac-Toe and Pong, all playable on a colorful LED matrix display.

## Table of Contents

- [Software Requirements](#software-requirements)
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

## Software Requirements

- [Python](https://www.python.org)
- [PyGame](https://www.pygame.org/)

## Usage

1. **Run the main script**:
   - The script will start the game selector.

2. **Select a game**:
   - Use the arrow keys to navigate and select a game from the menu. Press the "Y" key to start the selected game.

## Games

### Simon

Simon is a memory game where the player must remember and repeat a sequence of colors.

- **Controls**:
  - Use the arrow keys to select the corresponding quadrant of the flashed color.
  - Repeat the sequence shown on the display.

### Asteroid

Asteroid is a game where you have to shoot the asteroids.

- **Controls**:
  - Use the arrow keys to rotate and accelerate the space ship.
  - Use the joystick button to shoot.

### Snake

Snake is a classic game where the player controls a snake to eat targets and grow in length.

- **Controls**:
  - Use the arrow keys to control the direction of the snake (UP, DOWN, LEFT, RIGHT).
  - Avoid running into the snake's own body.

### Pong

Pong is a classic table tennis game where the player controls a paddle to hit a ball back and forth.

- **Controls**:
  - Use the arrow keys to move the paddle up and down.
  - Keep the ball in play to score points.

### Breakout

Breakout is the game where you break the wall bricks with a ball.

- **Controls**:
  - Use the arrow keys to move the paddle left and right.
  - Keep the ball in play and break bricks to score points.
 
### Qix

Qix is a game where you claim territory on a map, but if you get hit a the enemy you loose.

- **Controls**:
  - Use the arrow keys to move the player.
  - claim terretory and avoid to get hit.

i also implemented the game in golang using ebiten, you can find it [here](https://github.com/SimonWaldherr/golang-examples/blob/master/non-std-lib/ebiten-qix.go).

### Tetris

Tetris is a game where you have to stack blocks to make lines.

- **Controls**:
  - Use the arrow keys to move the blocks left and right.
  - Use the arrow keys to rotate the blocks.
  - Use the arrow keys to move the blocks down faster.

## Fun

Enjoy building and playing on your very own DIY-Arcade-Machine! If you have any questions or need further assistance, feel free to reach out.

Happy Gaming!
