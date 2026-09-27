"""Regression guard: public copy must not make privacy claims the site breaks.

NilPDF's privacy promise is about files, and that promise is true: documents
are processed in the browser and never uploaded. But the site also loads
Google Analytics, a deliberate and disclosed choice (see privacy/index.html).
Copy that claims "zero tracking" or a bare "100% private" is therefore false
about the page it appears on, and for a privacy product a caught false claim
does more damage than no claim. The first visitor who opens devtools sees the
analytics request.

Every one of these phrases was on the live site at once: in the meta, Open
Graph and Twitter descriptions (what search results and link previews show),
in visible copy, in the PWA manifest, and in strings app.js writes into the
meta tags at runtime. They were replaced with claims scoped to files.

The ban is conditional on analytics actually being present. If the site ever
drops Google Analytics, "zero tracking" becomes true, and this test stops
objecting without anyone having to remember it exists.
"""
import os
import re
import subprocess
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Claims about the visitor rather than the file. Case-insensitive.
FALSE_WHILE_TRACKING = [
    r"zero tracking",
    r"no tracking",
    r"without tracking",
    r"tracking[- ]free",
    r"100% private",
]

ANALYTICS_MARKER = "googletagmanager.com/gtag/js"


def read(relative_path):
    with open(os.path.join(BASE, relative_path), encoding="utf-8") as f:
        return f.read()


def public_text_files():
    """Everything a visitor can read: every HTML page, the SPA script that
    rewrites meta tags at runtime, the PWA manifest, and the README (the
    project's public face on GitHub)."""
    html = subprocess.run(
        ["git", "ls-files", "*.html"], cwd=BASE, capture_output=True, text=True, check=True
    ).stdout.split()
    return sorted(html) + ["assets/js/app.js", "manifest.json", "README.md"]


def site_loads_analytics():
    return ANALYTICS_MARKER in read("index.html")


class TestNoFalsePrivacyClaims(unittest.TestCase):
    def test_no_tracking_claims_while_analytics_is_loaded(self):
        if not site_loads_analytics():
            self.skipTest("Site does not load analytics, so tracking claims are not false")

        pattern = re.compile("|".join(FALSE_WHILE_TRACKING), re.IGNORECASE)
        for path in public_text_files():
            content = read(path)
            for match in pattern.finditer(content):
                start = max(0, match.start() - 50)
                snippet = content[start:match.end() + 30].replace("\n", " ")
                with self.subTest(path=path, claim=match.group(0)):
                    self.fail(
                        f"{path} claims '{match.group(0)}' but the site loads Google Analytics: "
                        f"...{snippet}... Scope the claim to files (e.g. 'your files never leave "
                        f"your device'), which is true, or remove analytics."
                    )

    def test_scan_actually_covers_the_site(self):
        """Guard against the file list silently shrinking to nothing."""
        files = public_text_files()
        self.assertIn("index.html", files)
        self.assertIn("redact-pdf/index.html", files)
        self.assertGreater(len(files), 25, "Expected every landing page to be scanned")


def tool_meta_ids(app_js):
    m = re.search(r"const TOOL_META = \{(.*?)\n\s*\};", app_js, re.DOTALL)
    assert m, "Could not find TOOL_META in app.js"
    return set(re.findall(r"^\s*(\w+):\s*\{", m.group(1), re.MULTILINE))


class TestUsageEventsCarryNoFileData(unittest.TestCase):
    """The one analytics event the app sends records which tool finished, and
    must never carry anything about the file. These tests pin that down
    structurally rather than trusting every future call site to be careful."""

    @classmethod
    def setUpClass(cls):
        cls.app = read("assets/js/app.js")
        cls.tools = tool_meta_ids(cls.app)

    def test_exactly_one_event_call_and_it_sends_only_the_tool(self):
        calls = re.findall(r"gtag\(\s*['\"]event['\"]\s*,\s*['\"](\w+)['\"]\s*,\s*(\{[^}]*\})\s*\)", self.app)
        self.assertEqual(
            len(calls), 1,
            f"Expected one gtag('event', ...) call site (recordToolUse), found {len(calls)}. "
            f"Route new usage events through recordToolUse so the payload stays controlled.",
        )
        name, payload = calls[0]
        self.assertEqual(name, "tool_complete")
        self.assertEqual(
            re.sub(r"\s", "", payload), "{tool}",
            f"The usage event payload must be exactly {{ tool }}; found {payload}. "
            f"Anything else risks sending file-derived data to analytics.",
        )
        self.assertEqual(self.app.count("gtag("), 1, "gtag is called somewhere other than recordToolUse")

    def test_event_is_gated_on_the_tool_allowlist(self):
        fn = re.search(r"function recordToolUse\(tool\) \{(.*?)\n    \}", self.app, re.DOTALL)
        self.assertIsNotNone(fn, "recordToolUse not found")
        self.assertIn("TOOL_META", fn.group(1), "recordToolUse must only send ids present in TOOL_META")

    def test_every_counted_operation_names_its_tool(self):
        self.assertNotIn(
            "incrementCounter();", self.app,
            "A call to incrementCounter() passes no tool, so that tool's usage is silently uncounted",
        )
        for tool in re.findall(r"incrementCounter\('(\w+)'\)", self.app):
            with self.subTest(tool=tool):
                self.assertIn(tool, self.tools, f"incrementCounter('{tool}') is not a TOOL_META id")

    def test_every_worker_job_resolves_to_a_real_tool(self):
        """Mirrors toolForJob: 'status' is merge, otherwise strip '-status'."""
        job_ids = set(re.findall(r"postMessage\(\s*\{\s*id:\s*'([\w-]+)'", self.app))
        prefixes = set(re.findall(r"prefix:\s*'(\w+)'", self.app))
        job_ids |= {f"{p}-status" for p in prefixes}
        self.assertGreater(len(job_ids), 15, "Worker job ids not found; regex may be stale")
        for job in sorted(job_ids):
            tool = "merge" if job == "status" else re.sub(r"-status$", "", job)
            with self.subTest(job=job):
                self.assertIn(tool, self.tools, f"Worker job '{job}' maps to '{tool}', which is not a tool")


if __name__ == "__main__":
    unittest.main()
