"""Regression guard: no em dash, en dash, or curly quotes anywhere in
user-visible site content.

Em dashes in particular have repeatedly read as "AI generated" and had to
be swept out by hand; this exists so they can't quietly creep back in
through a future edit. Scans:
- Every static HTML page's visible markup, with <!-- --> comments and the
  // and /* */ comments inside <script> blocks stripped first, so a code
  comment can never trigger this (comments aren't visible to a site
  visitor, only what's actually on the page matters).
- generate_pages.py and core/pdf_engine.py's regular string literals
  (where user-facing titles, copy, and error/status messages live), using
  Python's own tokenizer to separate them from comments and triple-quoted
  docstrings, neither of which a visitor ever sees.

The 21 generated tool pages aren't scanned directly since they're
mechanically derived from generate_pages.py — scanning the source once
covers all of them and avoids 21x redundant failures for one root cause.
"""
import io
import os
import re
import tokenize
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BANNED = {
    "—": "em dash (—)",
    "–": "en dash (–)",
    "‘": "curly single quote, open (‘)",
    "’": "curly single quote, close (’)",
    "“": "curly double quote, open (“)",
    "”": "curly double quote, close (”)",
}

HTML_FILES = [
    "index.html",
    "about/index.html",
    "privacy/index.html",
    "security/index.html",
    "terms/index.html",
    "browser-compatibility/index.html",
]
PY_FILES = ["generate_pages.py", "core/pdf_engine.py"]

# Plain JS/JSON files scanned whole (after stripping // and /* */ comments for
# the JS ones): no HTML markup to strip comments out of, so strip_script_comments'
# <script> wrapping doesn't apply, just the comment-stripping regexes directly.
JS_FILES = ["assets/js/pdf_worker.js", "sw.js"]
JSON_FILES = ["manifest.json"]


def strip_js_comments(code):
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)
    return re.sub(r"(?<!:)//[^\n]*", "", code)  # (?<!:) skips http(s):// URLs


def read(relative_path):
    with open(os.path.join(BASE, relative_path), encoding="utf-8") as f:
        return f.read()


def strip_html_comments(html):
    return re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)


def strip_script_comments(html):
    """Strip // and /* */ comments from inside <script> blocks only, so
    JS status-message strings (which ARE user-visible) stay in the scan
    while code comments (which aren't) drop out."""
    def clean(m):
        body = re.sub(r"/\*.*?\*/", "", m.group(2), flags=re.DOTALL)
        body = re.sub(r"(?<!:)//[^\n]*", "", body)  # (?<!:) skips http(s):// URLs
        return m.group(1) + body + "</script>"
    return re.sub(r"(<script\b[^>]*>)(.*?)</script>", clean, html, flags=re.DOTALL)


def non_docstring_string_literals(code):
    """Yield (line_number, text) for every regular-quoted Python string
    literal, skipping comments (tokenize never returns them as STRING) and
    triple-quoted docstrings (every real docstring in this codebase uses
    triple quotes; no user-facing message does).

    Also yields FSTRING_MIDDLE tokens (the literal text segments of an
    f-string) where present: under PEP 701 (Python 3.12+), f-strings are
    tokenized as FSTRING_START/FSTRING_MIDDLE/FSTRING_END rather than a
    single STRING token, so an f-string's literal text (e.g. the "s left"
    in f"{n} left") would otherwise never be checked. Older Python versions
    (pre-3.12) have no FSTRING_MIDDLE token at all and tokenize an f-string
    as a plain STRING, already covered by the check above.
    """
    fstring_middle = getattr(tokenize, "FSTRING_MIDDLE", None)
    for tok in tokenize.generate_tokens(io.StringIO(code).readline):
        if tok.type == tokenize.STRING and not tok.string.startswith(("'''", '"""')):
            yield tok.start[0], tok.string
        elif fstring_middle is not None and tok.type == fstring_middle:
            yield tok.start[0], tok.string


class TestNoBannedPunctuation(unittest.TestCase):
    def _assert_clean(self, text, label, line_offset=0):
        for i, line in enumerate(text.splitlines(), start=1 + line_offset):
            for char, name in BANNED.items():
                if char in line:
                    self.fail(f"{label}, line {i}: found {name} in visible content: {line.strip()[:120]}")

    def test_html_pages_have_no_banned_punctuation(self):
        for rel in HTML_FILES:
            html = strip_script_comments(strip_html_comments(read(rel)))
            self._assert_clean(html, rel)

    def test_python_string_literals_have_no_banned_punctuation(self):
        for rel in PY_FILES:
            code = read(rel)
            for line_no, literal in non_docstring_string_literals(code):
                for char, name in BANNED.items():
                    if char in literal:
                        self.fail(f"{rel}, line {line_no}: found {name} in string literal: {literal[:120]}")

    def test_js_files_have_no_banned_punctuation(self):
        for rel in JS_FILES:
            self._assert_clean(strip_js_comments(read(rel)), rel)

    def test_json_files_have_no_banned_punctuation(self):
        for rel in JSON_FILES:
            self._assert_clean(read(rel), rel)


if __name__ == "__main__":
    unittest.main()
