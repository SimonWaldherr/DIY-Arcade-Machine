"""
Shared game utilities for DIY Arcade Machine.

This module provides reusable components and helper functions used across
multiple games to reduce code duplication and improve maintainability.

Components:
- ShadowBuffer: Display wrapper that tracks pixel changes for efficient updates
- BaseGame: Base class providing common game loop structure
- Common drawing helpers
- Shared game state management utilities
"""

import asyncio


class ShadowBuffer:
    """
    Display wrapper that tracks pixel changes to minimize redundant updates.
    
    This class wraps a display object and maintains a shadow copy of the
    current display state. It only forwards set_pixel calls when a pixel's
    color actually changes, reducing I/O on hardware displays and improving
    performance on all platforms.
    
    This is particularly valuable on HUB75 LED matrices where every pixel
    write triggers I2C/GPIO operations.
    """
    
    def __init__(self, width, height, display):
        """
        Initialize the shadow buffer.
        
        Args:
            width (int): Display width in pixels
            height (int): Display height in pixels
            display: Underlying display object with set_pixel, clear, start methods
        """
        self.width = width
        self.height = height
        self.display = display
        # Shadow buffer stores RGB values as tuples: (r, g, b)
        # Initialize with None to indicate "unknown" state
        self.shadow = [[None for _ in range(width)] for _ in range(height)]
    
    def set_pixel(self, x, y, r, g, b):
        """
        Set a pixel, but only update display if the color changed.
        
        Args:
            x, y (int): Pixel coordinates
            r, g, b (int): RGB color values (0-255)
        """
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return
        
        color = (int(r), int(g), int(b))
        
        # Only update if color changed
        if self.shadow[y][x] != color:
            self.shadow[y][x] = color
            self.display.set_pixel(x, y, r, g, b)
    
    def clear(self):
        """Clear the display and reset shadow buffer."""
        # Reset shadow to unknown state
        for y in range(self.height):
            for x in range(self.width):
                self.shadow[y][x] = None
        self.display.clear()
    
    def start(self):
        """Initialize the underlying display."""
        if hasattr(self.display, 'start'):
            self.display.start()
    
    def show(self):
        """Present the frame to the display."""
        if hasattr(self.display, 'show'):
            self.display.show()


class BaseGame:
    """
    Base class for arcade games providing common structure and utilities.
    
    This class implements the common pattern used by most games:
    - Initialization with score/lives
    - Main game loop with input handling
    - Async version for browser compatibility
    - Common exit handling (C button to quit)
    
    Subclasses should override:
    - reset(): Initialize/reset game state
    - update(joystick): Update game logic for one frame
    - draw(): Render the current game state
    """
    
    def __init__(self):
        """Initialize base game state."""
        self.score = 0
        self.lives = 3
        self.frame = 0
        self.last_frame_time = 0
        self.frame_ms = 33  # ~30 FPS default
    
    def reset(self):
        """
        Reset game state to initial values.
        
        Override this in subclasses to initialize game-specific state.
        Always call super().reset() to reset base state.
        """
        self.score = 0
        self.lives = 3
        self.frame = 0
    
    def update(self, joystick):
        """
        Update game logic for one frame.
        
        Override this in subclasses to implement game-specific logic.
        Return False to end the game loop.
        
        Args:
            joystick: Joystick/input handler object
            
        Returns:
            bool: True to continue, False to exit game
        """
        return True
    
    def draw(self):
        """
        Render the current game state.
        
        Override this in subclasses to draw game-specific graphics.
        """
        pass
    
    def main_loop(self, joystick):
        """
        Standard synchronous game loop.
        
        This implements the common pattern:
        1. Reset game state
        2. Loop:
           a. Check for exit (C button)
           b. Update game logic
           c. Draw frame
           d. Control frame rate
        
        Subclasses can override this for custom loop logic, but most
        games can just override reset(), update(), and draw().
        """
        # Import arcade_app globals at runtime to avoid circular imports
        import arcade_app
        
        arcade_app.game_over = False
        arcade_app.global_score = 0
        
        self.reset()
        arcade_app.display.clear()
        arcade_app.display_score_and_time(0, force=True)
        
        self.last_frame_time = arcade_app.ticks_ms()
        
        while not arcade_app.game_over:
            try:
                # Check for exit
                c_button, _ = joystick.nunchuck.buttons()
                if c_button:
                    return
                
                # Frame timing
                now = arcade_app.ticks_ms()
                if arcade_app.ticks_diff(now, self.last_frame_time) < self.frame_ms:
                    arcade_app.sleep_ms(2)
                    continue
                self.last_frame_time = now
                self.frame += 1
                
                # Update game logic
                if not self.update(joystick):
                    arcade_app.global_score = self.score
                    arcade_app.game_over = True
                    return
                
                # Draw
                self.draw()
                arcade_app.display_score_and_time(self.score)
                arcade_app.global_score = self.score
                
                # Periodic garbage collection
                if self.frame % 60 == 0:
                    arcade_app.maybe_collect(120)
                    
            except arcade_app.RestartProgram:
                return
    
    async def main_loop_async(self, joystick):
        """
        Async version of main loop for browser compatibility.
        
        This mirrors main_loop() but yields to the event loop between
        frames to keep the browser responsive.
        """
        # Import arcade_app globals at runtime to avoid circular imports
        import arcade_app
        
        arcade_app.game_over = False
        arcade_app.global_score = 0
        
        self.reset()
        arcade_app.display.clear()
        arcade_app.display_score_and_time(0, force=True)
        
        self.last_frame_time = arcade_app.ticks_ms()
        
        while not arcade_app.game_over:
            try:
                # Check for exit
                c_button, _ = joystick.nunchuck.buttons()
                if c_button:
                    return
                
                # Frame timing
                now = arcade_app.ticks_ms()
                if arcade_app.ticks_diff(now, self.last_frame_time) < self.frame_ms:
                    await asyncio.sleep(0.002)
                    continue
                self.last_frame_time = now
                self.frame += 1
                
                # Update game logic
                if not self.update(joystick):
                    arcade_app.global_score = self.score
                    arcade_app.game_over = True
                    return
                
                # Draw
                self.draw()
                arcade_app.display_score_and_time(self.score)
                arcade_app.global_score = self.score
                
                # Periodic garbage collection
                if self.frame % 60 == 0:
                    arcade_app.maybe_collect(120)
                
                # Yield to event loop
                await asyncio.sleep(0)
                    
            except arcade_app.RestartProgram:
                return
