"""Platform detection and environment utilities for DIY Arcade Machine.

This module provides a centralized location for runtime platform detection,
isolating browser-specific (pygbag/WASM) concerns from desktop and embedded
(MicroPython) runtime logic.

The detection mechanism uses ``sys.platform`` and ``sys.implementation`` to
reliably identify the target runtime environment. This allows the arcade
application to adapt its behavior appropriately for each platform while
maintaining a single codebase.

Platform Support
----------------
The arcade supports three distinct runtime environments:

1. **MicroPython (RP2040/embedded)**:
   - Runs on Raspberry Pi Pico with HUB75 LED matrix
   - Detected via ``sys.implementation.name == "micropython"``
   - Uses hardware I2C for Nunchuk controller input
   - Direct LED matrix control via hub75 driver

2. **Desktop (CPython + PyGame)**:
   - Development and testing environment
   - Detected when not MicroPython and not browser
   - Uses PyGame for display emulation and keyboard input
   - Full debugging capabilities

3. **Browser (Pygbag/Emscripten/WASM)**:
   - Web deployment via WebAssembly
   - Detected via ``sys.platform == "emscripten"``
   - Requires async/await for cooperative multitasking
   - Uses PyGame compiled to WASM

Module Variables
----------------
is_micropython : bool
    True when running on MicroPython (RP2040/embedded hardware).
    
is_browser : bool
    True when running in browser via pygbag (Emscripten/WASM).
    Note: Uses ``sys.platform`` detection as recommended by pygbag.
    
is_desktop : bool
    True when running on desktop CPython with PyGame.

Legacy Aliases
--------------
IS_MICROPYTHON : bool
    Alias for ``is_micropython`` (backwards compatibility).
    
IS_PYGBAG : bool
    Alias for ``is_browser`` (backwards compatibility).
    
IS_DESKTOP : bool
    Alias for ``is_desktop`` (backwards compatibility).

Example Usage
-------------
Basic platform detection::

    from env import is_browser, is_micropython, is_desktop
    
    if is_browser:
        print("Running in browser via pygbag")
    elif is_micropython:
        print("Running on embedded MicroPython")
    elif is_desktop:
        print("Running on desktop CPython")

Conditional feature enabling::

    from env import is_browser
    
    if not is_browser:
        # Enable features not available in browser
        import threading
        enable_multiprocessing()

Platform-specific initialization::

    from env import get_platform_name, require_desktop
    
    print(f"Detected platform: {get_platform_name()}")
    
    # Fail fast if wrong platform
    require_desktop()  # Raises RuntimeError if not desktop

Notes
-----
- Platform detection occurs at module import time
- Detection results are cached in module-level variables
- Use ``require_*`` functions for strict platform enforcement
- Browser detection uses ``sys.platform`` per pygbag best practices

See Also
--------
main.py : Entry point with platform-specific routing
arcade_app.py : Main application with platform adaptations
"""

import sys

# ============================================================================
# Platform Detection
# ============================================================================
# Detection is performed at module import time and results are cached in
# module-level boolean variables. This approach ensures consistent platform
# identification throughout the application lifecycle.

# Detect MicroPython embedded runtime
# Uses sys.implementation.name which is the canonical way to detect
# MicroPython vs CPython. This is reliable across all MicroPython builds.
try:
    is_micropython = sys.implementation.name == "micropython"
except Exception:
    # If sys.implementation is missing (very old Python), assume not MicroPython
    is_micropython = False

# Detect pygbag browser runtime (Emscripten/WASM)
# IMPORTANT: Use sys.platform (not platform.system()) for browser detection.
# Pygbag patches sys.platform to "emscripten" and this is the recommended
# detection method per pygbag documentation. The platform module may not
# be available or reliable in WASM environments.
try:
    is_browser = sys.platform == "emscripten"
except Exception:
    # If platform detection fails, assume not browser
    is_browser = False

# Desktop is the remaining case: CPython but not browser
# This is the development and testing environment with full PyGame support.
is_desktop = not is_micropython and not is_browser

# Legacy compatibility aliases
# These uppercase names maintain backwards compatibility with existing code
# that may reference the old naming convention. New code should prefer the
# lowercase variants (is_micropython, is_browser, is_desktop).
IS_MICROPYTHON = is_micropython
IS_PYGBAG = is_browser
IS_DESKTOP = is_desktop


def get_platform_name():
    """Return a human-readable platform name.
    
    This function returns a string identifying the current runtime platform.
    Useful for logging, debugging, and user-facing platform information.
    
    Returns
    -------
    str
        One of the following platform identifiers:
        - "micropython" : Running on embedded MicroPython (RP2040)
        - "browser" : Running in browser via pygbag/WASM
        - "desktop" : Running on desktop CPython with PyGame
    
    Examples
    --------
    >>> from env import get_platform_name
    >>> platform = get_platform_name()
    >>> print(f"Running on: {platform}")
    Running on: desktop
    
    >>> # Platform-specific logging
    >>> import logging
    >>> logger = logging.getLogger(__name__)
    >>> logger.info(f"Arcade starting on {get_platform_name()}")
    
    Notes
    -----
    The returned string is always lowercase for consistent string matching.
    """
    if is_micropython:
        return "micropython"
    elif is_browser:
        return "browser"
    else:
        return "desktop"


def require_browser():
    """Raise an error if not running in browser environment.
    
    This function enforces that code is running in the browser/pygbag
    environment. Use at the start of browser-specific code paths to fail
    fast with a clear error message if executed on wrong platform.
    
    Raises
    ------
    RuntimeError
        If not running in pygbag browser environment (sys.platform != "emscripten").
        Error message includes the detected platform name for debugging.
    
    Examples
    --------
    >>> from env import require_browser
    >>> 
    >>> def browser_only_feature():
    ...     require_browser()  # Guard at function entry
    ...     # Browser-specific code here
    ...     setup_wasm_interface()
    
    Notes
    -----
    This is a defensive programming pattern - use when mixing platform-specific
    code in shared modules. For pure platform modules, prefer import-time checks.
    
    See Also
    --------
    require_desktop : Enforce desktop environment
    require_micropython : Enforce MicroPython environment
    """
    if not is_browser:
        raise RuntimeError(
            "This code requires browser environment (pygbag/Emscripten). "
            f"Current platform: {get_platform_name()}"
        )


def require_desktop():
    """Raise an error if not running in desktop environment.
    
    This function enforces that code is running in the desktop CPython
    environment with PyGame. Use at the start of desktop-specific code
    paths (e.g., file I/O, debugging tools) to fail fast if executed
    on wrong platform.
    
    Raises
    ------
    RuntimeError
        If not running in desktop CPython environment.
        Error message includes the detected platform name for debugging.
    
    Examples
    --------
    >>> from env import require_desktop
    >>> 
    >>> def save_screenshot(filename):
    ...     require_desktop()  # Guard at function entry
    ...     # Desktop-only file operations
    ...     pygame.image.save(surface, filename)
    
    >>> def debug_mode():
    ...     require_desktop()
    ...     import pdb
    ...     pdb.set_trace()
    
    Notes
    -----
    Desktop environment is the development/testing platform with full
    Python standard library access (file I/O, threading, subprocesses).
    
    See Also
    --------
    require_browser : Enforce browser environment
    require_micropython : Enforce MicroPython environment
    """
    if not is_desktop:
        raise RuntimeError(
            "This code requires desktop CPython environment. "
            f"Current platform: {get_platform_name()}"
        )


def require_micropython():
    """Raise an error if not running in MicroPython environment.
    
    This function enforces that code is running on embedded MicroPython
    hardware (RP2040 with HUB75 display). Use at the start of hardware-
    specific code paths to fail fast if executed on wrong platform.
    
    Raises
    ------
    RuntimeError
        If not running in MicroPython embedded environment.
        Error message includes the detected platform name for debugging.
    
    Examples
    --------
    >>> from env import require_micropython
    >>> 
    >>> def setup_hardware():
    ...     require_micropython()  # Guard at function entry
    ...     # MicroPython-only hardware setup
    ...     import machine
    ...     i2c = machine.I2C(0, scl=machine.Pin(21), sda=machine.Pin(20))
    
    >>> def read_nunchuk():
    ...     require_micropython()
    ...     # Direct I2C hardware access
    ...     data = i2c.readfrom(0x52, 6)
    
    Notes
    -----
    MicroPython environment has limited standard library but direct
    hardware access (I2C, GPIO, RTC). Code requiring hardware imports
    (machine, hub75) should use this guard.
    
    See Also
    --------
    require_browser : Enforce browser environment
    require_desktop : Enforce desktop environment
    """
    if not is_micropython:
        raise RuntimeError(
            "This code requires MicroPython environment. "
            f"Current platform: {get_platform_name()}"
        )
