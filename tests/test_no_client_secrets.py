"""Regression guard: no credential may be shipped to the browser.

An earlier version of the feedback form stamped a real GitHub PAT into the
deployed index.html and called api.github.com directly from the page. That
token was readable by every visitor via view-source, and `public_repo` scope
grants write access to every public repository on the account, not just this
one. It was replaced by the Cloudflare Worker in feedback-worker/, which
holds the token server-side.

Nothing in the test suite would have caught the original mistake, and the
deploy pipeline is exactly the kind of place a "just stamp it in" shortcut
reappears under time pressure. These tests fail the build if a credential,
or the machinery for sending one, comes back to the client.

Scope: files served to browsers, plus the workflow that stamps them.
feedback-worker/ is deliberately excluded — it runs server-side and is
*supposed* to read a token (from an env binding, never a literal).

These are substring checks, so they also trip on a client file merely
mentioning the API host in a comment. That is intentional: the cheapest way
to keep the guard unambiguous is to keep the string out of shipped files
entirely.
"""
import os
import re
import shutil
import subprocess
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Everything here is downloaded verbatim by a visitor's browser.
CLIENT_FILES = ["index.html", "assets/js/app.js", "assets/js/pdf_worker.js", "sw.js"]

# Literal credential shapes. GitHub's documented token prefixes plus the
# generic "40 hex characters" of a classic PAT.
TOKEN_PATTERNS = [
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}"), "a GitHub token literal (ghp_/gho_/ghu_/ghs_/ghr_)"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), "a GitHub fine-grained PAT literal (github_pat_)"),
    (re.compile(r"['\"][0-9a-f]{40}['\"]"), "a 40-hex-character string (classic PAT shape)"),
]


def read(relative_path):
    with open(os.path.join(BASE, relative_path), encoding="utf-8") as f:
        return f.read()


class TestNoCredentialsInClientFiles(unittest.TestCase):
    def test_no_token_literals(self):
        for path in CLIENT_FILES:
            content = read(path)
            for pattern, label in TOKEN_PATTERNS:
                with self.subTest(path=path, pattern=label):
                    match = pattern.search(content)
                    self.assertIsNone(
                        match,
                        f"{path} appears to contain {label}: {match.group(0)[:12] + '...' if match else ''}. "
                        f"Credentials must live in the feedback-worker, never in a file served to browsers.",
                    )

    def test_no_authorization_header_sent_from_the_browser(self):
        """The page must never attach an Authorization header to a request.

        If it does, it is holding a credential — there is no other reason to
        send one — regardless of how that credential got there.
        """
        for path in CLIENT_FILES:
            with self.subTest(path=path):
                self.assertFalse(
                    "Authorization" in read(path),
                    f"{path} sets an Authorization header. Client-side code has no credential to "
                    f"authenticate with; route the call through feedback-worker/ instead.",
                )

    def test_client_never_calls_the_github_api(self):
        for path in CLIENT_FILES:
            with self.subTest(path=path):
                self.assertFalse(
                    "api.github.com" in read(path),
                    f"{path} calls the GitHub API directly. Writes to GitHub must go through "
                    f"feedback-worker/, which holds the token server-side.",
                )


class TestDeployPipelineStampsNoSecret(unittest.TestCase):
    """The deploy job may stamp public values (build version, Worker URL) into
    the site. It must never stamp anything out of `secrets`."""

    def test_workflow_does_not_stamp_a_secret_into_the_site(self):
        workflow = read(".github/workflows/static.yml")
        secrets_used = set(re.findall(r"\$\{\{\s*secrets\.(\w+)\s*\}\}", workflow))
        self.assertFalse(
            secrets_used,
            f"static.yml passes secret(s) {sorted(secrets_used)} into the build. Anything written "
            f"into the deployed site is public; secrets belong in the Cloudflare Worker.",
        )

    def test_feedback_endpoint_placeholder_is_still_wired_up(self):
        """Guards the other direction: if the placeholder is renamed or dropped
        without updating the workflow, the form silently breaks in production."""
        self.assertTrue(
            "__FEEDBACK_ENDPOINT__" in read("assets/js/app.js"),
            "app.js no longer contains the __FEEDBACK_ENDPOINT__ placeholder the deploy job replaces",
        )
        self.assertTrue(
            "__FEEDBACK_ENDPOINT__" in read(".github/workflows/static.yml"),
            "static.yml no longer stamps __FEEDBACK_ENDPOINT__, so the deployed form would stay disabled",
        )


class TestStampingSurvivesDeploy(unittest.TestCase):
    """The deploy step replaces placeholders with a plain replace-all, which is a
    sharp edge: a placeholder written twice gets rewritten in both places.

    The previous token-based feedback guard read
        if (!TOKEN || TOKEN === '__GH_FEEDBACK_TOKEN__')
    so stamping turned it into `TOKEN === '<the real token>'`, which is always
    true. The live form reported itself unavailable for every submission while
    looking perfectly correct in the source. This reproduces the deploy
    substitution and asserts the guard still lets a stamped build through.
    """

    ENDPOINT = "https://nilpdf-feedback.example.workers.dev"

    def _stamped_app_js(self):
        app = read("assets/js/app.js")
        return app.replace("__FEEDBACK_ENDPOINT__", self.ENDPOINT).replace(
            "__BUILD_VERSION__", "abc1234 2026-01-01"
        )

    def test_feedback_guard_still_passes_after_stamping(self):
        """Evaluate the real guard expression against the real stamped value."""
        stamped = self._stamped_app_js()
        match = re.search(r"if \((![^)]*?_FEEDBACK_ENDPOINT[^\n]*?)\) \{", stamped)
        self.assertIsNotNone(match, "Could not locate the feedback endpoint guard in app.js")
        guard = match.group(1)

        self.assertNotIn(
            self.ENDPOINT, guard,
            f"After stamping, the guard compares the endpoint against itself: `{guard}`. "
            f"It would disable the feedback form on exactly the builds that are configured "
            f"correctly. Test the value's shape instead of the placeholder literal.",
        )

        node = shutil.which("node") or shutil.which("nodejs")
        if not node:
            self.skipTest("Node.js not available on this runner")

        # A stamped build must submit; an unstamped one must be refused.
        for value, should_block, label in (
            (self.ENDPOINT, False, "stamped build"),
            ("__FEEDBACK_ENDPOINT__", True, "unstamped build"),
        ):
            with self.subTest(build=label):
                script = f"const _FEEDBACK_ENDPOINT = {value!r}; console.log(({guard}) ? 'BLOCKED' : 'ALLOWED');"
                out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
                self.assertEqual(out.returncode, 0, f"guard failed to evaluate: {out.stderr}")
                verdict = out.stdout.strip()
                self.assertEqual(
                    verdict, "BLOCKED" if should_block else "ALLOWED",
                    f"On a {label} the feedback guard returned {verdict}.",
                )


if __name__ == "__main__":
    unittest.main()
