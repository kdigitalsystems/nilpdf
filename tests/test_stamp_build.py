"""The deploy job's stamping step, tested on a copy of the site.

This replacement step used to be inline Python in the workflow, where nothing
could test it, and a replace-all in exactly this step disabled the production
feedback form for months. These run scripts/stamp_build.py itself.
"""
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(BASE, "scripts", "stamp_build.py")
FILES = ("index.html", "assets/js/app.js", "sw.js")
SHA = "0123456789abcdef0123456789abcdef01234567"
ENDPOINT = "https://nilpdf-feedback.example.workers.dev"
NODE = shutil.which("node") or shutil.which("nodejs")


def load_script():
    spec = importlib.util.spec_from_file_location("stamp_build", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


stamp_build = load_script()


class StampTestCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="nilpdf-stamp-")
        for rel in FILES:
            os.makedirs(os.path.dirname(os.path.join(self.root, rel)), exist_ok=True)
            shutil.copy(os.path.join(BASE, rel), os.path.join(self.root, rel))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def read(self, rel):
        with open(os.path.join(self.root, rel), encoding="utf-8") as f:
            return f.read()

    def run_script(self, *args, env=None):
        return subprocess.run([sys.executable, SCRIPT, "--root", self.root, *args],
                              capture_output=True, text=True, env={**os.environ, **(env or {})})


class TestStamping(StampTestCase):
    def test_stamps_every_placeholder(self):
        r = self.run_script("--sha", SHA, "--endpoint", ENDPOINT, "--date", "2026-01-02")
        self.assertEqual(r.returncode, 0, r.stderr)
        placeholders = [*stamp_build.STAMPS, stamp_build.ENDPOINT_PLACEHOLDER]
        for rel in FILES:
            leftover = [p for p in placeholders if p in self.read(rel)]
            self.assertFalse(leftover, f"{rel} still has deploy placeholders after stamping: {leftover}")
        self.assertIn("app.js?v=0123456 2026-01-02", self.read("index.html"))
        self.assertIn("pdf_worker.js?v=0123456 2026-01-02", self.read("assets/js/app.js"))
        self.assertIn("'nilpdf-0123456'", self.read("sw.js"))
        self.assertIn(f"_FEEDBACK_ENDPOINT = '{ENDPOINT}'", self.read("assets/js/app.js"))

    def test_reads_sha_and_endpoint_from_the_environment_like_the_workflow(self):
        r = self.run_script(env={"COMMIT_SHA": SHA, "FEEDBACK_ENDPOINT": ENDPOINT})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(ENDPOINT, self.read("assets/js/app.js"))

    def test_without_an_endpoint_the_fallback_placeholder_stays(self):
        r = self.run_script("--sha", SHA, env={"FEEDBACK_ENDPOINT": ""})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("__FEEDBACK_ENDPOINT__", self.read("assets/js/app.js"))
        self.assertIn("GitHub issue fallback", r.stdout)

    def test_stamped_build_still_lets_feedback_through(self):
        """The production bug: a replace-all also rewrote the guard that checks
        for the placeholder, so the guard compared the endpoint with itself and
        the form refused every submission. Evaluate the stamped guard."""
        if not NODE:
            self.skipTest("Node.js not available")
        self.run_script("--sha", SHA, "--endpoint", ENDPOINT)
        app = self.read("assets/js/app.js")
        guard = re.search(r"if \((![^)]*?_FEEDBACK_ENDPOINT[^\n]*?)\) \{", app).group(1)
        script = f"const _FEEDBACK_ENDPOINT = {ENDPOINT!r}; console.log(({guard}) ? 'BLOCKED' : 'ALLOWED');"
        out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.stdout.strip(), "ALLOWED", out.stderr)

    def test_stamped_scripts_still_parse(self):
        if not NODE:
            self.skipTest("Node.js not available")
        self.run_script("--sha", SHA, "--endpoint", ENDPOINT)
        for rel, ext in (("assets/js/app.js", ".js"), ("sw.js", ".js")):
            path = os.path.join(self.root, "check" + ext)
            shutil.copy(os.path.join(self.root, rel), path)
            out = subprocess.run([NODE, "--check", path], capture_output=True, text=True, timeout=30)
            self.assertEqual(out.returncode, 0, f"{rel} no longer parses after stamping: {out.stderr}")


class TestStampingRefusesBadInput(StampTestCase):
    def assert_refused_and_untouched(self, result, message):
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(message, result.stderr)
        for rel in FILES:
            with open(os.path.join(BASE, rel), encoding="utf-8") as f:
                self.assertEqual(self.read(rel), f.read(), f"{rel} was modified by a failed run")

    def test_non_https_endpoint_is_refused(self):
        self.assert_refused_and_untouched(self.run_script("--sha", SHA, "--endpoint", "http://insecure.example"),
                                          "https://")

    def test_malformed_sha_is_refused(self):
        self.assert_refused_and_untouched(self.run_script("--sha", "not-a-sha"), "hex commit id")

    def test_missing_placeholder_fails_before_writing_anything(self):
        """sw.js is stamped after index.html and app.js; if its placeholder is
        missing, the earlier files must not have been written either."""
        path = os.path.join(self.root, "sw.js")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        with open(path, "w", encoding="utf-8") as f:
            f.write(text.replace("__SW_VERSION__", "hardcoded"))
        r = self.run_script("--sha", SHA)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("__SW_VERSION__ placeholder not found in sw.js", r.stderr)
        self.assertIn("__BUILD_VERSION__", self.read("index.html"), "index.html was written by a failed run")


class TestDeployUsesTheScript(unittest.TestCase):
    def test_deploy_job_runs_this_script_rather_than_inline_replacement(self):
        with open(os.path.join(BASE, ".github/workflows/static.yml"), encoding="utf-8") as f:
            workflow = f.read()
        self.assertIn("scripts/stamp_build.py", workflow)
        self.assertNotIn(".replace('__", workflow, "stamping logic is back inline in the workflow, untested")


if __name__ == "__main__":
    unittest.main()
