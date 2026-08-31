"""Local development server for NilPDF.

    python3 dev_server.py     # then open http://localhost:8123

NilPDF needs cross-origin isolation (COOP + COEP) for Pyodide's
SharedArrayBuffer fast path, and `python3 -m http.server` sends neither
header, so the app degrades or fails to boot when served with it. This is a
plain static file server that adds them.

The COEP value here is deliberately the same one sw.js sets on real traffic
(`credentialless`, not the stricter `require-corp`). Serving dev under a
different policy than production means a cross-origin resource can load fine
on localhost and be blocked for users, or vice versa — the mismatch hides
exactly the class of bug this header causes.

Cache-Control is no-store so an edit is picked up on reload rather than
being served from the browser cache; that part is dev-only and has no
production equivalent.
"""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

PORT = 8123


class COEPHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "credentialless")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        super().end_headers()


if __name__ == "__main__":
    print(f"NilPDF dev server: http://localhost:{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), COEPHandler).serve_forever()
