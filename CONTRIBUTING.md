# Contributing to DIY Arcade Machine

Thank you for your interest in contributing to the DIY Arcade Machine project! This guide will help you understand the codebase structure and best practices for adding new games or features.

## Code Organization

The project follows clean code principles (DRY, KISS, YAGNI) to maintain simplicity and readability:

### Main Files

- **`main.py`**: Minimal entry point that routes to arcade_app based on platform
- **`arcade_app.py`**: Main application containing all games and core logic (~11,000 lines)
- **`game_utils.py`**: Reusable utilities and base classes for games and menus
- **`env.py`**: Platform detection utilities (MicroPython, Desktop, Browser)

### Module Structure

```
arcade_app.py
├── Runtime Detection & Setup
├── Display & Controller Abstraction
├── Drawing Utilities (text, shapes, colors)
├── Game Infrastructure (high scores, menus)
├── Games (22+ game classes)
└── Main Entry Points (sync & async)
```

## Adding a New Game

### Option 1: Using BaseGame (Recommended)

The easiest way to add a game is to extend `game_utils.BaseGame`:

```python
from game_utils import BaseGame

class MyGame(BaseGame):
    def reset(self):
        """Initialize game state."""
        super().reset()  # Resets score, lives, frame counter
        self.player_x = 32
        self.player_y = 32
        # ... initialize your game state
    
    def update(self, joystick):
        """Update game logic for one frame.
        
        Returns:
            bool: True to continue, False to end game
        """
        # Handle input
        direction = joystick.read_direction([JOYSTICK_UP, JOYSTICK_DOWN])
        
        # Update game state
        # ... your game logic here
        
        # Check win/lose conditions
        if self.lives <= 0:
            return False  # End game
        
        return True  # Continue
    
    def draw(self):
        """Render the current frame."""
        import arcade_app
        
        # Draw game elements
        arcade_app.display.set_pixel(self.player_x, self.player_y, 255, 255, 255)
        # ... draw your game
```

Benefits:
- ✓ Automatic game loop (handles timing, input, scoring)
- ✓ Built-in async support for browser
- ✓ Frame rate management
- ✓ Garbage collection
- ✓ Less boilerplate code

### Option 2: Custom Implementation

For games with unique requirements, implement your own `main_loop()` and optionally `main_loop_async()`:

```python
class MyCustomGame:
    def __init__(self):
        self.score = 0
    
    def main_loop(self, joystick):
        """Synchronous game loop."""
        import arcade_app
        
        arcade_app.game_over = False
        arcade_app.global_score = 0
        
        while not arcade_app.game_over:
            # Check exit
            c_button, z_button = joystick.nunchuck.buttons()
            if c_button:
                return
            
            # Your game logic
            # ...
            
            arcade_app.display_score_and_time(self.score)
            arcade_app.sleep_ms(30)
    
    async def main_loop_async(self, joystick):
        """Async version for browser."""
        # Similar to main_loop but with await asyncio.sleep(0)
        pass
```

## Using Utility Functions

### Collision Detection

```python
from game_utils import rect_collision, point_in_rect

# Check if two rectangles overlap
if rect_collision(x1, y1, w1, h1, x2, y2, w2, h2):
    print("Collision!")

# Check if point is in rectangle
if point_in_rect(px, py, rx, ry, rw, rh):
    print("Hit!")
```

### Distance & Math

```python
from game_utils import distance, clamp, lerp

# Calculate distance between two points
d = distance(x1, y1, x2, y2)

# Clamp value to range
health = clamp(health, 0, 100)

# Linear interpolation
position = lerp(start_pos, end_pos, 0.5)
```

### Coordinate Wrapping

```python
from game_utils import wrap_coordinate

# Wraparound for Snake-style toroidal field
x = wrap_coordinate(x, WIDTH)
y = wrap_coordinate(y, HEIGHT)
```

## Creating Menus

Extend `BaseMenu` for simple menu screens:

```python
from game_utils import BaseMenu

class MyMenu(BaseMenu):
    def get_options(self):
        """Return list of menu items."""
        return ["START", "OPTIONS", "QUIT"]
    
    def draw(self):
        """Custom drawing (optional)."""
        super().draw()  # Default draws options
        # Add custom elements
        import arcade_app
        arcade_app.draw_text(10, 5, "MY GAME", 255, 255, 0)

# Use the menu
menu = MyMenu(joystick)
choice = menu.run()  # Returns selected option or None if cancelled
```

## Drawing Functions

### Available in arcade_app:

```python
import arcade_app

# Text
arcade_app.draw_text(x, y, "TEXT", r, g, b)  # Large 8x8 font
arcade_app.draw_text_small(x, y, "TEXT", r, g, b)  # Small 5x5 font

# Shapes
arcade_app.draw_rectangle(x1, y1, x2, y2, r, g, b)  # Filled rectangle
arcade_app.draw_line(x0, y0, x1, y1, r, g, b)  # Line

# Individual pixels
arcade_app.display.set_pixel(x, y, r, g, b)

# HUD
arcade_app.display_score_and_time(score)  # Shows score + clock
```

## Platform Compatibility

### Platform Detection

```python
from env import is_micropython, is_browser, is_desktop

if is_micropython:
    # Use hardware-specific code
    pass
elif is_browser:
    # Browser-specific optimizations
    pass
else:  # is_desktop
    # Desktop development features
    pass
```

### Memory Management

MicroPython has limited RAM. Follow these guidelines:

- ✓ Use generators instead of lists when possible
- ✓ Call `gc.collect()` periodically in long loops
- ✓ Avoid large global data structures
- ✓ Pre-allocate buffers when practical
- ✓ Use integer math instead of float when possible

```python
import gc

# Periodic collection
if frame % 60 == 0:
    gc.collect()
```

## Code Style

### Follow Existing Patterns

- Use type hints where helpful but don't overdo it
- Add docstrings to classes and complex functions
- Keep functions focused and small
- Use descriptive variable names
- Follow PEP 8 style guide

### Comments

```python
# Good: Explain WHY, not WHAT
# Avoid collision with tail segment when snake is growing
if occupying and not (tail_will_move and new_head == tail):
    game_over = True

# Bad: States the obvious
# Set x to 10
x = 10
```

## Testing

Run the compatibility test suite:

```bash
python test_compatibility.py
```

Test your game on all platforms:
1. **Desktop**: `python main.py` - Fast iteration during development
2. **Browser**: `pygbag --serve .` - Test async compatibility
3. **Hardware**: Upload to MicroPython device - Test memory usage

## Registering Your Game

Add your game to the GameSelect class in arcade_app.py:

```python
self.game_classes = {
    # ... existing games ...
    "MYGAME": MyGame,  # Your game here
}
```

The game will automatically appear in the menu with high score tracking.

## Best Practices

### DRY (Don't Repeat Yourself)
- Use `game_utils` base classes
- Extract common patterns into helper functions
- Reuse existing drawing and collision utilities

### KISS (Keep It Simple, Stupid)
- Simple algorithms that work > complex optimizations
- Clear code > clever code
- Focus on readability

### YAGNI (You Aren't Gonna Need It)
- Don't add features "just in case"
- Implement what's needed for the game to work
- Refactor when patterns emerge, not before

## Getting Help

- Check existing games for examples
- Review game_utils.py for available utilities
- Read the main README.md for platform-specific details
- Look at similar games for patterns

## Questions?

Open an issue on GitHub or refer to the main README.md for more information.

Happy coding! 🎮
