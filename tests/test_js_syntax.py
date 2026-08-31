"""Catch JavaScript syntax errors before they ship.

assets/js/app.js is the whole SPA (thousands of lines, one per-tool IIFE
after another) and there is no build step in front of it — a single
unbalanced brace or stray token anywhere in it silently breaks every tool,
not just the one being edited, and nothing in the Python test suite would
notice. This uses `node --check` (parse-only, no execution) to confirm the
standalone JS files and every remaining inline <script> block are
syntactically valid.

Skips cleanly if Node isn't available on the runner rather than failing CI
for an unrelated environment reason.
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node") or shutil.which("nodejs")


def read(relative_path):
    with open(os.path.join(BASE, relative_path), encoding="utf-8") as f:
        return f.read()


def extract_inline_scripts(html):
    """Return the body of every <script> tag with no src= and no non-JS
    type= (e.g. the JSON-LD blocks on SEO pages aren't JavaScript)."""
    scripts = []
    for m in re.finditer(r"<script\b([^>]*)>(.*?)</script>", html, re.DOTALL):
        attrs, body = m.groups()
        if "src=" in attrs:
            continue
        if re.search(r'type\s*=\s*["\']application/ld\+json["\']', attrs):
            continue
        if body.strip():
            scripts.append(body)
    return scripts


def node_check(code):
    """Run `node --check` on a snippet of JS. Returns (ok, stderr)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(code)
        path = f.name
    try:
        result = subprocess.run([NODE, "--check", path], capture_output=True, text=True, timeout=30)
        return result.returncode == 0, result.stderr
    finally:
        os.unlink(path)


@unittest.skipUnless(NODE, "Node.js not available on this runner — skipping JS syntax check")
class TestJavaScriptSyntax(unittest.TestCase):
    def test_index_html_inline_scripts_are_syntactically_valid(self):
        scripts = extract_inline_scripts(read("index.html"))
        self.assertTrue(scripts, "No inline <script> blocks found in index.html — extraction regex may be stale")
        for i, script in enumerate(scripts):
            ok, stderr = node_check(script)
            self.assertTrue(ok, f"index.html inline <script> block #{i + 1} has a syntax error:\n{stderr}")

    def test_standalone_js_files_are_syntactically_valid(self):
        for path in ("assets/js/app.js", "assets/js/pdf_worker.js", "sw.js"):
            with self.subTest(path=path):
                ok, stderr = node_check(read(path))
                self.assertTrue(ok, f"{path} has a syntax error:\n{stderr}")


if __name__ == "__main__":
    unittest.main()
