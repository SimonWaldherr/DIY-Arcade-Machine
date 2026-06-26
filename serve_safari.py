"""Tiny HTTP server that adds Cross-Origin-Isolation headers.

Safari requires COOP + COEP headers for SharedArrayBuffer (used by pygbag).
Use COEP credentialless so pygbag runtime files can still be loaded from the
pygame-web CDN when that CDN does not send Cross-Origin-Resource-Policy.
Run after `make web` to serve the build/web/ folder in a Safari-compatible way:

    python serve_safari.py [port]   # default port: 8000

An optional second argument selects a different build directory, for example:

    python serve_safari.py 8000 build/ios
"""

import http.server
import os
import sys
import threading
import webbrowser

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
DEFAULT_BUILD_DIR = os.path.join(os.path.dirname(__file__), "build", "web")
BUILD_DIR = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_BUILD_DIR


class COEPHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BUILD_DIR, **kwargs)

    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "credentialless")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} {fmt % args}")


def _open_browser():
    webbrowser.open(f"http://localhost:{PORT}")


with http.server.HTTPServer(("", PORT), COEPHandler) as httpd:
    print(f"Serving {BUILD_DIR} on http://localhost:{PORT}")
    print("Cross-Origin-Opener-Policy:  same-origin")
    print("Cross-Origin-Embedder-Policy: credentialless")
    print("Press Ctrl-C to stop.\n")
    threading.Timer(0.8, _open_browser).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
