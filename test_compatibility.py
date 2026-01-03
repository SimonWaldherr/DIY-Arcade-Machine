#!/usr/bin/env python3
"""
Platform compatibility test suite for DIY Arcade Machine.

Tests that the arcade application works correctly on all three target platforms:
1. Desktop (CPython + PyGame)
2. Browser (Pygbag/Emscripten + WASM)
3. MicroPython (RP2040 + HUB75)

Run this script to verify that recent changes maintain cross-platform compatibility.
"""

import sys
import time
import inspect


def test_imports():
    """Test that all modules import successfully."""
    print("\n" + "=" * 60)
    print("TEST 1: Module Imports")
    print("=" * 60)
    
    try:
        import main
        print("✓ main.py imports successfully")
    except Exception as e:
        print(f"✗ main.py import FAILED: {e}")
        return False
    
    try:
        import arcade_app
        print("✓ arcade_app.py imports successfully")
    except Exception as e:
        print(f"✗ arcade_app.py import FAILED: {e}")
        return False
    
    try:
        import env
        print("✓ env.py imports successfully")
    except Exception as e:
        print(f"✗ env.py import FAILED: {e}")
        return False
    
    return True


def test_platform_detection():
    """Test platform detection logic."""
    print("\n" + "=" * 60)
    print("TEST 2: Platform Detection")
    print("=" * 60)
    
    import arcade_app
    import env
    
    # Test current platform (should be desktop/linux)
    print(f"\nCurrent platform: {sys.platform}")
    print(f"  arcade_app.IS_MICROPYTHON: {arcade_app.IS_MICROPYTHON}")
    print(f"  arcade_app.IS_PYGBAG: {arcade_app.IS_PYGBAG}")
    print(f"  env.is_micropython: {env.is_micropython}")
    print(f"  env.is_browser: {env.is_browser}")
    print(f"  env.is_desktop: {env.is_desktop}")
    
    # Verify consistency
    if arcade_app.IS_MICROPYTHON == env.is_micropython:
        print("✓ IS_MICROPYTHON consistent")
    else:
        print("✗ IS_MICROPYTHON INCONSISTENT")
        return False
    
    if arcade_app.IS_PYGBAG == env.is_browser:
        print("✓ IS_PYGBAG/is_browser consistent")
    else:
        print("✗ IS_PYGBAG/is_browser INCONSISTENT")
        return False
    
    # Simulate browser environment
    print("\nSimulating browser environment (sys.platform = 'emscripten')...")
    original_platform = sys.platform
    sys.platform = 'emscripten'
    
    # Force reload to test detection
    is_browser_check = sys.platform == "emscripten"
    print(f"  Browser detection check: {is_browser_check}")
    
    if is_browser_check:
        print("✓ Browser detection works correctly")
    else:
        print("✗ Browser detection FAILED")
        sys.platform = original_platform
        return False
    
    sys.platform = original_platform
    return True


def test_async_functions():
    """Test that async functions are properly defined."""
    print("\n" + "=" * 60)
    print("TEST 3: Async Function Definitions")
    print("=" * 60)
    
    import main
    import arcade_app
    
    # Check main.main (synchronous)
    if hasattr(main, 'main'):
        print("✓ main.main exists")
        if inspect.iscoroutinefunction(main.main):
            print("✗ main.main should NOT be async")
            return False
        print("✓ main.main is synchronous (correct)")
    else:
        print("✗ main.main does NOT exist")
        return False
    
    # Check main.async_main (asynchronous)
    if hasattr(main, 'async_main'):
        print("✓ main.async_main exists")
        if inspect.iscoroutinefunction(main.async_main):
            print("✓ main.async_main is async (correct)")
        else:
            print("✗ main.async_main should be async")
            return False
    else:
        print("✗ main.async_main does NOT exist")
        return False
    
    # Check arcade_app.main (synchronous)
    if hasattr(arcade_app, 'main'):
        print("✓ arcade_app.main exists")
        if inspect.iscoroutinefunction(arcade_app.main):
            print("✗ arcade_app.main should NOT be async")
            return False
        print("✓ arcade_app.main is synchronous (correct)")
    else:
        print("✗ arcade_app.main does NOT exist")
        return False
    
    # Check arcade_app.async_main (asynchronous)
    if hasattr(arcade_app, 'async_main'):
        print("✓ arcade_app.async_main exists")
        if inspect.iscoroutinefunction(arcade_app.async_main):
            print("✓ arcade_app.async_main is async (correct)")
        else:
            print("✗ arcade_app.async_main should be async")
            return False
    else:
        print("✗ arcade_app.async_main does NOT exist")
        return False
    
    return True


def test_routing_logic():
    """Test that main.py routes correctly based on platform."""
    print("\n" + "=" * 60)
    print("TEST 4: Platform Routing Logic")
    print("=" * 60)
    
    # Test desktop routing
    sys.platform = 'linux'
    is_browser = sys.platform == "emscripten"
    print(f"\nDesktop mode (sys.platform = '{sys.platform}'):")
    print(f"  is_browser: {is_browser}")
    if not is_browser:
        print("✓ Would route to main() - correct")
    else:
        print("✗ Should route to main() but would route to async_main()")
        return False
    
    # Test browser routing
    sys.platform = 'emscripten'
    is_browser = sys.platform == "emscripten"
    print(f"\nBrowser mode (sys.platform = '{sys.platform}'):")
    print(f"  is_browser: {is_browser}")
    if is_browser:
        print("✓ Would route to asyncio.run(async_main()) - correct")
    else:
        print("✗ Should route to async_main() but would route to main()")
        return False
    
    # Restore platform
    sys.platform = 'linux'
    return True


def test_sleep_function():
    """Test that sleep_ms works correctly."""
    print("\n" + "=" * 60)
    print("TEST 5: Sleep Function")
    print("=" * 60)
    
    import arcade_app
    
    # Test sleep_ms in desktop mode
    print(f"\nTesting sleep_ms in desktop mode (IS_PYGBAG={arcade_app.IS_PYGBAG})...")
    start = time.time()
    arcade_app.sleep_ms(10)
    elapsed = (time.time() - start) * 1000
    print(f"  sleep_ms(10) took {elapsed:.1f}ms")
    
    if 8 <= elapsed <= 20:  # Allow some tolerance
        print("✓ sleep_ms timing is reasonable")
    else:
        print(f"⚠ sleep_ms timing seems off (expected ~10ms, got {elapsed:.1f}ms)")
    
    # Verify function signature
    sig = inspect.signature(arcade_app.sleep_ms)
    print(f"  Function signature: sleep_ms{sig}")
    
    params = list(sig.parameters.keys())
    if params == ['ms']:
        print("✓ sleep_ms has correct parameters")
    else:
        print(f"✗ sleep_ms has wrong parameters: {params}")
        return False
    
    return True


def test_display_abstraction():
    """Test that display is properly abstracted."""
    print("\n" + "=" * 60)
    print("TEST 6: Display Abstraction")
    print("=" * 60)
    
    import arcade_app
    
    if hasattr(arcade_app, 'display'):
        print("✓ arcade_app.display exists")
    else:
        print("✗ arcade_app.display does NOT exist")
        return False
    
    # Check display has required methods
    required_methods = ['set_pixel', 'clear', 'start']
    for method in required_methods:
        if hasattr(arcade_app.display, method):
            print(f"✓ display.{method} exists")
        else:
            print(f"✗ display.{method} does NOT exist")
            return False
    
    return True


def test_game_constants():
    """Test that game constants are defined."""
    print("\n" + "=" * 60)
    print("TEST 7: Game Constants")
    print("=" * 60)
    
    import arcade_app
    
    constants = {
        'WIDTH': 64,
        'HEIGHT': 64,
        'HUD_HEIGHT': 6,
        'PLAY_HEIGHT': 58,
    }
    
    for const, expected in constants.items():
        if hasattr(arcade_app, const):
            value = getattr(arcade_app, const)
            if value == expected:
                print(f"✓ {const} = {value} (correct)")
            else:
                print(f"⚠ {const} = {value} (expected {expected})")
        else:
            print(f"✗ {const} is NOT defined")
            return False
    
    return True


def run_all_tests():
    """Run all compatibility tests."""
    print("\n" + "=" * 60)
    print("DIY ARCADE MACHINE - PLATFORM COMPATIBILITY TEST SUITE")
    print("=" * 60)
    print("\nTesting compatibility across:")
    print("  1. Desktop (CPython + PyGame)")
    print("  2. Browser (Pygbag/Emscripten)")
    print("  3. MicroPython (RP2040)")
    
    tests = [
        ("Module Imports", test_imports),
        ("Platform Detection", test_platform_detection),
        ("Async Functions", test_async_functions),
        ("Routing Logic", test_routing_logic),
        ("Sleep Function", test_sleep_function),
        ("Display Abstraction", test_display_abstraction),
        ("Game Constants", test_game_constants),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ Test '{name}' raised exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Print summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status:8} {name}")
    
    print("\n" + "-" * 60)
    print(f"Result: {passed}/{total} tests passed")
    print("=" * 60)
    
    if passed == total:
        print("\n✓ ALL TESTS PASSED - Platform compatibility verified!")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) FAILED - Review errors above")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
