"""Pixel-equivalence checks for Doom's native span renderer."""
import unittest
import arcade_app as app


class Pixels:
    def __init__(self, native):
        self.pixels = bytearray(64 * 64 * 3)
        self.calls = 0
        if not native:
            self.fill_rect = None

    def set_pixel(self, x, y, r, g, b):
        self.calls += 1
        if 0 <= x < 64 and 0 <= y < 64:
            offset = (y * 64 + x) * 3
            self.pixels[offset:offset + 3] = bytes((r & 255, g & 255, b & 255))

    def fill_rect(self, x1, y1, x2, y2, r, g, b):
        for y in range(y1, y2 + 1):
            for x in range(x1, x2 + 1):
                self.set_pixel(x, y, r, g, b)

    def show(self):
        pass


class DoomRenderTests(unittest.TestCase):
    def test_native_spans_match_pixel_fallback(self):
        original = app.display, app.USE_BUFFERED_DISPLAY, app._FRAME_PRESENT_MANAGED
        try:
            app._FRAME_PRESENT_MANAGED = True
            app.USE_BUFFERED_DISPLAY = False
            game = app.DoomLiteGame()
            game.render_minimap = False
            game.render_hud = False
            for stride, angle, damage, muzzle in ((1, 0, 0, 0), (2, 64, 0, 3),
                                                   (1, 130, 4, 0), (2, 250, 0, 0)):
                game.render_stride = stride
                game.ang = angle
                game.dmg_flash = damage
                game.muzzle_flash = muzzle
                slow = Pixels(False)
                app.display = slow
                game._render()
                depth = list(game.zbuf)
                fast = Pixels(True)
                app.display = fast
                game._render()
                self.assertEqual(slow.pixels, fast.pixels)
                self.assertEqual(depth, game.zbuf)
                self.assertTrue(all(d > 0 for d in depth))
        finally:
            app.display, app.USE_BUFFERED_DISPLAY, app._FRAME_PRESENT_MANAGED = original
