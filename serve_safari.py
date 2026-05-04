"""Tiny HTTP server that adds Cross-Origin-Isolation headers.

Safari requires COOP + COEP headers for SharedArrayBuffer (used by pygbag).
Run after `make web` to serve the build/web/ folder in a Safari-compatible way:

    python serve_safari.py [port]   # default port: 8000
"""

import http.server
import os
import sys
import threading
import webbrowser

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
BUILD_DIR = os.path.join(os.path.dirname(__file__), "build", "web")


class COEPHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BUILD_DIR, **kwargs)

    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} {fmt % args}")


def _open_browser():
    webbrowser.open(f"http://localhost:{PORT}")


with http.server.HTTPServer(("", PORT), COEPHandler) as httpd:
    print(f"Serving build/web/ on http://localhost:{PORT}")
    print("Cross-Origin-Opener-Policy:  same-origin")
    print("Cross-Origin-Embedder-Policy: require-corp")
    print("Press Ctrl-C to stop.\n")
    threading.Timer(0.8, _open_browser).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
