# Pygbag Browser Deployment Guide

This document describes how to build, test, and deploy the DIY Arcade Machine to run in modern web browsers using **pygbag**.

## Overview

Pygbag packages Python + PyGame applications to run in browsers via WebAssembly (WASM). This arcade machine has been adapted for browser deployment while maintaining full compatibility with desktop and embedded (MicroPython) platforms.

## Architecture

### Platform Abstraction

The codebase uses a three-tier runtime detection system:

```python
# Platform detection (uses sys.platform for browser)
IS_MICROPYTHON  # True on RP2040/embedded hardware
IS_PYGBAG       # True in browser (sys.platform == "emscripten")
IS_DESKTOP      # True on desktop CPython
```

### Browser-Specific Adaptations

1. **Async Entry Point** (`main.py`):
   - Detects browser platform via `sys.platform == "emscripten"`
   - Calls `asyncio.run(async_main())` for browser
   - Calls synchronous `main()` for desktop/embedded

2. **Cooperative Yielding** (`arcade_app.py`):
   - `sleep_ms()` flushes display without blocking in browser mode
   - `display.show()` calls `pygame.event.pump()` which yields to browser
   - No explicit `await` needed in game loops - pygame handles it

3. **Asset Management**:
   - All graphics are procedurally generated (no external files)
   - No audio dependencies
   - All code is self-contained in Python modules

## Prerequisites

### Required Software

```bash
# Install pygbag
pip install pygbag

# Recommended: latest version
pip install --upgrade pygbag
```

### System Requirements

- Python 3.9+ (pygbag requires modern async features)
- Web browser with WebAssembly support (Chrome, Firefox, Safari, Edge)
- ~50MB disk space for build artifacts

## Building for Browser

### Basic Build

```bash
# Build from the repository root
pygbag .

# Or specify the entry point explicitly
pygbag main.py
```

This creates a `build/web` directory with the WASM bundle.

### Build Options

```bash
# Specify output directory
pygbag --build my_build_dir .

# Include additional dependencies (if you add them)
pygbag --git="https://github.com/user/repo" .

# Set custom template
pygbag --template custom.tmpl .

# Enable debug mode
pygbag --debug .
```

### Build Output

After building, you'll have:
```
build/web/
  ├── index.html          # Entry HTML page
  ├── main.py             # Your bootstrap code
  ├── arcade_app.py       # Main application
  ├── env.py              # Platform detection module
  ├── pythonrc.py         # Pygbag initialization
  └── (various .wasm and .so files)
```

## Testing Locally

### Using Python HTTP Server

```bash
# Build first
pygbag .

# Serve from build directory
python3 -m http.server --directory build/web 8000

# Open browser to http://localhost:8000
```

### Using Pygbag Server

```bash
# Pygbag includes a development server
pygbag --serve .

# Opens automatically at http://localhost:8000
```

### Testing Tips

1. **Clear Browser Cache**: Browsers aggressively cache WASM modules
   ```javascript
   // In browser console
   location.reload(true);  // Hard reload
   ```

2. **Check Console**: Press F12 to see Python print() output and errors

3. **Performance**: First load is slow (downloads ~5MB), subsequent loads are cached

## Deployment

### GitHub Pages

1. Build the project:
   ```bash
   pygbag --build docs .
   ```

2. Commit the `docs/` directory:
   ```bash
   git add docs/
   git commit -m "Build for GitHub Pages"
   git push
   ```

3. Enable GitHub Pages:
   - Go to repository Settings → Pages
   - Source: Deploy from branch `main`, folder `/docs`
   - Save and wait ~1 minute

4. Access at: `https://username.github.io/repository/`

### Static Hosting

The `build/web` directory is self-contained and can be deployed to:
- Netlify: Drag and drop the folder
- Vercel: `vercel --prod build/web`
- AWS S3: `aws s3 sync build/web s3://bucket-name/`
- Any static host that supports WASM

### MIME Type Requirements

Ensure your web server serves these MIME types:
```
.wasm   → application/wasm
.js     → text/javascript
.data   → application/octet-stream
```

Most modern hosts configure this automatically.

## Troubleshooting

### Build Issues

**Problem**: `pygbag: command not found`
```bash
# Solution: Install in correct environment
pip install --user pygbag
# Or use pipx
pipx install pygbag
```

**Problem**: `ImportError` for pygame
```bash
# Solution: pygbag includes pygame, don't pre-install it
pip uninstall pygame
pip install pygbag
```

**Problem**: Missing dependencies
```bash
# Solution: Use --git flag to include external packages
pygbag --git="https://github.com/user/dependency" .
```

### Runtime Issues

**Problem**: Black screen on load
- **Check browser console** for Python exceptions
- **Verify MIME types** (see deployment section)
- **Hard refresh** to clear cache: Ctrl+Shift+R (Windows/Linux) or Cmd+Shift+R (Mac)

**Problem**: Controls not working
- **Use keyboard**: Arrow keys + Z/Space (desktop controls work in browser)
- **Check focus**: Click canvas if keyboard input isn't registering

**Problem**: Slow performance
- **Expected on first load**: ~5MB WASM download
- **Subsequent loads**: Should be cached and fast
- **Consider**: Browser limits pygame to ~60 FPS

**Problem**: Game loops freeze
- **Verify**: `display.show()` is called in game loops
- **Check**: No blocking `time.sleep()` calls in IS_PYGBAG mode
- **Ensure**: `pygame.event.pump()` is called regularly

### Cache Management

```bash
# Clear pygbag build cache
rm -rf build/

# Force clean rebuild
pygbag --clean .

# Browser cache clearing:
# Chrome: DevTools → Network → Disable cache (keep DevTools open)
# Firefox: about:config → browser.cache.disk.enable → false
```

## Known Limitations

### Browser Platform Constraints

1. **No Threading**: Use asyncio instead of threads
2. **No Subprocess**: Cannot call external commands
3. **No Native Extensions**: Pure Python only (pygame is built-in)
4. **File System**: Uses Emscripten virtual filesystem (limited)
5. **Performance**: ~10-30% slower than native due to WASM overhead

### Application-Specific

1. **Audio**: No sound (not implemented in current version)
2. **High Scores**: Saved in browser localStorage (not persistent across devices)
3. **Display**: Fixed 64×64 resolution (upscaled to canvas)

## Best Practices

### Code Guidelines

1. **Avoid Blocking Calls**:
   ```python
   # Bad (blocks browser)
   if IS_PYGBAG:
       time.sleep(1.0)
   
   # Good (yields via display)
   display_flush()
   ```

2. **Platform Detection**:
   ```python
   # Use sys.platform (not platform.system())
   IS_PYGBAG = sys.platform == "emscripten"
   ```

3. **Event Loop Yielding**:
   ```python
   # Ensure pygame.event.pump() is called regularly
   pygame.event.pump()  # Built into display.show()
   ```

### Asset Management

All assets should be in the project directory:
```python
# Good
image = pygame.image.load("assets/sprite.png")

# Bad (won't bundle)
image = pygame.image.load("../external/sprite.png")
```

### Import Patterns

For conditional imports:
```python
# Use importlib for desktop-only modules
if not IS_PYGBAG:
    import importlib
    threading = importlib.import_module("threading")
```

## Performance Optimization

### Reduce Build Size

1. **Remove unused modules**: Pygbag analyzes imports
2. **Compress assets**: Use PNG instead of BMP
3. **Minify code**: Use `pygbag --optimize`

### Runtime Performance

1. **Profile with browser DevTools**: F12 → Performance tab
2. **Reduce draw calls**: Batch operations where possible
3. **Optimize loops**: Cache frequently accessed data
4. **Monitor FPS**: Target 30 FPS minimum for playability

## Development Workflow

Recommended iterative development cycle:

```bash
# 1. Develop locally with desktop runtime
python main.py

# 2. Test changes quickly
pygbag --serve .

# 3. Full build for deployment
pygbag --build docs .

# 4. Test production build
python3 -m http.server --directory docs 8000
```

## Migration Notes

### Changes Made for Pygbag

1. **Platform Detection** (arcade_app.py:73-76):
   - Changed from `platform.system() == "Emscripten"`
   - To `sys.platform == "emscripten"` (pygbag best practice)

2. **Sleep Function** (arcade_app.py:130-157):
   - Removed blocking `time.sleep()` in IS_PYGBAG mode
   - Relies on `display_flush()` → `pygame.event.pump()` for yielding

3. **Entry Point** (main.py):
   - Added async/sync branching based on platform
   - Calls `arcade_app.async_main()` in browser
   - No code after `asyncio.run()` (browser requirement)

4. **New Module** (env.py):
   - Centralized platform detection utilities
   - Provides `is_browser`, `is_micropython`, `is_desktop` flags
   - Legacy compatibility: `IS_PYGBAG`, `IS_MICROPYTHON`

### Preserved Architecture

- ✅ All game classes remain synchronous (no async/await in game logic)
- ✅ State management unchanged
- ✅ Frame processing routines intact
- ✅ Display abstraction maintained
- ✅ Desktop and MicroPython compatibility preserved

## Additional Resources

- [Pygbag Documentation](https://pygame-web.github.io/)
- [Pygame Web Examples](https://github.com/pygame-web/pygbag)
- [Emscripten WASM Guide](https://emscripten.org/)
- [WebAssembly Specification](https://webassembly.org/)

## Support

For issues specific to this arcade implementation:
1. Check browser console for Python errors
2. Verify `sys.platform == "emscripten"` detection
3. Ensure `pygame.event.pump()` is being called
4. Test desktop version first to isolate platform issues

For pygbag-specific issues:
- [Pygbag GitHub Issues](https://github.com/pygame-web/pygbag/issues)
- [Pygame Web Discord](https://discord.gg/pygame)
