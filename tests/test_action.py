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
CLEANUP = os.path.join(BASE, "action", "cleanup.sh")
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
        self.assertIn("action/cleanup.sh", runs)
        for step in ACTION["runs"]["steps"]:
            self.assertEqual(step.get("shell"), "bash", step["name"])

    def test_the_last_step_always_removes_the_virtual_environment(self):
        """Even when the install or the check fails. In a container job on a
        self-hosted runner the environment belongs to root, and the runner
        can't delete it later: CI left 60 of them, 2.7 GB, before this."""
        last = ACTION["runs"]["steps"][-1]
        self.assertEqual(last.get("if"), "always()")
        self.assertIn("action/cleanup.sh", last["run"])
        self.assertEqual(last["env"], {"NILPDF_VENV": "${{ steps.install.outputs.venv }}"})

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
        self.assertEqual(inputs["changed-only"]["default"], "false", "check everything unless asked not to")
        self.assertEqual(inputs["exclude"]["default"], "")

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

    def test_install_records_the_environment_before_it_can_fail(self):
        """The cleanup step can only remove what the install step reported, so
        the path is written out before the first pip call."""
        script = read("action/install.sh")
        self.assertLess(script.index('echo "venv=$venv" >> "${GITHUB_OUTPUT'), script.index("pip_install hatchling"))
        self.assertIn("--no-cache-dir", script, "a pip cache would stay in the runner's shared home directory")

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
            if "uses: kdigitalsystems/nilpdf@" in block:
                yield block

    def test_examples_name_the_current_release(self):
        """Every version the docs mention is either this release or the
        major-version tag that follows it, and each document pins the exact
        release somewhere, so a version bump can't leave the docs behind."""
        current = f"v{source_version()}"
        major = current.split(".")[0]
        for doc in self.DOCS:
            with self.subTest(doc=doc):
                tags = re.findall(r"kdigitalsystems/nilpdf@([\w.<>-]+)", read(doc))
                self.assertIn(current, tags)
                for tag in tags:
                    self.assertIn(tag, (current, major, "<commit-sha>"))

    def test_install_commands_work_without_pypi(self):
        """`pip install nilpdf` only works once the package is on PyPI, and for
        a while the READMEs said it when it wasn't. Until the first publish
        succeeds, every copy-and-paste block installs from GitHub, which
        always works. (When PyPI is live, change the commands and this test.)"""
        from_github = f"pip install git+https://github.com/kdigitalsystems/nilpdf@v{source_version()}"
        for doc in self.DOCS:
            with self.subTest(doc=doc):
                text = read(doc)
                self.assertIn(from_github, text)
                for block in re.findall(r"```[a-z]*\n(.*?)```", text, re.S):
                    self.assertNotRegex(block, r"pip install (?:-\S+ +)*[\"']?nilpdf\b(?! @)")

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
        for name in list(ACTION["inputs"]) + list(ACTION["outputs"]):
            with self.subTest(name=name):
                self.assertIn(f"`{name}`", readme)


class TestCleanupScript(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def cleanup(self, venv):
        return subprocess.run(["bash", CLEANUP], env={"PATH": os.environ["PATH"], "NILPDF_VENV": venv},
                              capture_output=True, text=True, timeout=30)

    def test_removes_the_environment(self):
        venv = os.path.join(self.tmp, "nilpdf-action.aB3dE9")
        os.makedirs(os.path.join(venv, "env", "bin"))
        open(os.path.join(venv, "env", "bin", "python"), "w").close()
        r = self.cleanup(venv)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(venv))

    def test_removes_nothing_it_did_not_create(self):
        """The path comes from a step output. If that is ever empty or wrong,
        this deletes nothing rather than whatever the path happens to be."""
        for name in ("", "important", "nilpdf-action.", "nilpdf-action.toolong1", "nilpdf-actionXaB3dE9"):
            with self.subTest(name=name):
                target = os.path.join(self.tmp, name) if name else self.tmp
                os.makedirs(target, exist_ok=True)
                open(os.path.join(target, "keep"), "w").close()
                r = self.cleanup(target if name else "")
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertTrue(os.path.exists(os.path.join(target, "keep")))

    def test_a_missing_environment_is_not_an_error(self):
        """The install step may have failed before creating it."""
        self.assertEqual(self.cleanup(os.path.join(self.tmp, "nilpdf-action.aB3dE9")).returncode, 0)


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

    def run_check(self, paths, cwd=None, event=None, env=None, **inputs):
        """Run the check step. `event` is the payload of the event that
        started the run, as GitHub writes it to GITHUB_EVENT_PATH."""
        cwd = cwd or self.fx
        output = os.path.join(self.gh, "output")
        summary = os.path.join(self.gh, "summary")
        for path in (output, summary):
            open(path, "w").close()
        env = {
            **self.env,
            "GITHUB_OUTPUT": output, "GITHUB_STEP_SUMMARY": summary,
            "GITHUB_WORKSPACE": cwd, "RUNNER_TEMP": self.gh,
            "NILPDF_PATHS": paths,
            "NILPDF_EXCLUDE": inputs.get("exclude", ""),
            "NILPDF_CHANGED_ONLY": inputs.get("changed_only", "false"),
            "NILPDF_PASSWORD": inputs.get("password", ""),
            "NILPDF_FAIL_ON_HIDDEN_TEXT": inputs.get("fail_on_hidden_text", "true"),
            "NILPDF_FAIL_ON_ERROR": inputs.get("fail_on_error", "true"),
            "NILPDF_SHOW_TEXT": inputs.get("show_text", "false"),
            **(env or {}),
        }
        # These tests run inside a GitHub Actions job themselves, so the real
        # job's event must never leak into the check under test.
        env.pop("GITHUB_EVENT_PATH", None)
        if event is not None:
            env["GITHUB_EVENT_PATH"] = os.path.join(self.gh, "event.json")
            with open(env["GITHUB_EVENT_PATH"], "w", encoding="utf-8") as f:
                json.dump(event, f)
        r = subprocess.run([sys.executable, CHECK], cwd=cwd, env=env, capture_output=True, timeout=120)
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

    def in_check_module(self, code, *args):
        """Run a snippet with action/check.py imported as `check`, and return
        the JSON it prints."""
        setup = ("import importlib.util, json, sys\n"
                 f"spec = importlib.util.spec_from_file_location('check', {CHECK!r})\n"
                 "check = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(check)\n")
        done = subprocess.run([sys.executable, "-c", setup + code, *args], env=self.env, cwd=self.fx,
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)


class TestCheckStep(ActionTestCase):
    def test_a_clean_file_passes(self):
        r = self.run_check("clean.pdf")
        self.assertEqual(r.returncode, 0, r.log)
        self.assertEqual(r.outputs, {"hidden-text-found": "false", "files-checked": "1", "files-skipped": "0",
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



class TestExclude(ActionTestCase):
    """exclude is how a repository accepts a known false positive or leaves an
    archive alone. What it skips must stay visible."""

    def test_patterns(self):
        """Patterns are matched against the whole path from the workspace, the
        same way the paths input reads globs."""
        cases = [
            # pattern, path, excluded?
            ("hidden.pdf", "hidden.pdf", True),
            ("./hidden.pdf", "hidden.pdf", True),
            ("hidden.pdf", "tree/hidden.pdf", False),       # not at any depth unless asked
            ("**/hidden.pdf", "tree/sub/hidden.pdf", True),
            ("**/hidden.pdf", "hidden.pdf", True),
            ("tree", "tree/sub/b.pdf", True),                # a directory covers what is in it
            ("tree/", "tree/a.pdf", True),
            ("tree", "tree2/a.pdf", False),
            ("tree", "a/tree/b.pdf", False),
            ("*.pdf", "a.pdf", True),
            ("*.pdf", "tree/a.pdf", False),                  # * stays within one directory
            ("tree/**", "tree/sub/b.pdf", True),
            ("tree/*/b.pdf", "tree/sub/b.pdf", True),
            ("tree/*/b.pdf", "tree/sub/deeper/b.pdf", False),
            ("archive/**/*.pdf", "archive/2019/q1/a.pdf", True),
            ("archive/**/*.pdf", "archive/a.pdf", True),
            ("scan-?.pdf", "scan-1.pdf", True),
            ("scan-?.pdf", "scan-10.pdf", False),
            ("scan-[0-9].pdf", "scan-7.pdf", True),
            ("scan-[!0-9].pdf", "scan-7.pdf", False),
            ("scan-[!0-9].pdf", "scan-x.pdf", True),
            # Regular-expression characters in a file name mean themselves.
            ("a+b (1).pdf", "a+b (1).pdf", True),
            ("a+b (1).pdf", "aab (1).pdf", False),
            ("a.pdf", "axpdf", False),
            ("[draft].pdf", "[draft].pdf", False),           # a character class, as in a glob
            ("[[]draft].pdf", "[draft].pdf", True),
            # An absolute path, as ${{ github.workspace }}/tree would give.
            (os.path.join(self.fx, "tree"), "tree/sub/b.pdf", True),
            (os.path.join(self.fx, "tree", "*.pdf"), "tree/a.pdf", True),
            (os.path.join(self.fx, "tree"), "clean.pdf", False),
        ]
        got = self.in_check_module(
            "print(json.dumps([bool(check.exclude_regex(p).fullmatch(path)) for p, path, _ in json.loads(sys.argv[1])]))",
            json.dumps(cases))
        for (pattern, path, expected), actual in zip(cases, got):
            with self.subTest(pattern=pattern, path=path):
                self.assertEqual(actual, expected)

    def test_an_excluded_file_is_skipped_and_reported(self):
        r = self.run_check(".", exclude="hidden.pdf\ntree/sub")
        self.assertEqual(r.returncode, 0, r.log)
        self.assertEqual(r.outputs["files-checked"], "2")
        self.assertEqual(r.outputs["files-skipped"], "2")
        self.assertEqual(r.outputs["hidden-text-found"], "false")
        note = "2 PDFs matching exclude were not checked."
        self.assertIn(note, r.log)
        self.assertIn(note, r.summary)
        self.assertEqual(sorted(r.report["skipped"]["excluded"]), ["hidden.pdf", "tree/sub/b_whiteout.PDF"])
        self.assertEqual([f["path"] for f in r.report["files"]], ["clean.pdf", "tree/a_clean.pdf"])

    def test_a_pattern_has_to_match_the_whole_path(self):
        """`b_whiteout.PDF` names a file at the top of the workspace. It must
        not also skip tree/sub/b_whiteout.PDF, or one careless pattern could
        hide files all over a repository."""
        r = self.run_check(".", exclude="b_whiteout.PDF\nhidden.pdf")
        self.assertEqual(r.returncode, 1, r.log)
        self.assertEqual(r.report["skipped"]["excluded"], ["hidden.pdf"])
        self.assertEqual([c[1]["file"] for c in r.commands], ["tree/sub/b_whiteout.PDF"])

    def test_without_exclude_the_same_run_fails(self):
        r = self.run_check(".")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.outputs["files-skipped"], "0")
        self.assertNotIn("not checked", r.summary)

    def test_exclude_wins_over_a_path_named_explicitly(self):
        r = self.run_check("hidden.pdf\nclean.pdf", exclude="hidden.pdf")
        self.assertEqual(r.returncode, 0, r.log)
        self.assertEqual((r.outputs["files-checked"], r.outputs["files-skipped"]), ("1", "1"))

    def test_excluding_everything_passes_and_says_so(self):
        r = self.run_check("hidden.pdf", exclude="*.pdf")
        self.assertEqual(r.returncode, 0, r.log)
        self.assertEqual(r.outputs["files-checked"], "0")
        self.assertIn("**No PDFs needed checking.**", r.summary)
        self.assertIn("1 PDF matching exclude was not checked.", r.summary)

    def test_a_missing_path_is_still_an_error(self):
        """exclude skips files that exist. It can't hide a typo in paths."""
        r = self.run_check("nope.pdf", exclude="nope.pdf")
        self.assertEqual(r.returncode, 1, r.log)
        self.assertEqual(r.outputs["files-with-errors"], "1")


def git(cwd, *args):
    """Run git with no user or system configuration, so a developer's own
    settings (signing, hooks, templates) can't change what these tests see."""
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
           "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z"}
    done = subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
                           "-c", "init.defaultBranch=main", *args],
                          cwd=cwd, env=env, capture_output=True, text=True, timeout=60)
    if done.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {done.stderr}")
    return done.stdout.strip()


@unittest.skipUnless(shutil.which("git"), "git is needed to build the repositories these tests check")
class TestChangedOnly(ActionTestCase):
    """changed-only may skip a PDF only when git confirms it hasn't changed.
    Whenever that is in doubt, the file is checked."""

    LEAK = staticmethod(lambda: make_line_pdf(draw=box(0, 0, 0)))
    CLEAN = staticmethod(lambda text="A clean page": make_line_pdf(text=text))

    def setUp(self):
        super().setUp()
        # "origin" has the base commit: a legacy PDF with hidden text that
        # was there before the check existed, and a clean one.
        self.origin = os.path.join(self.gh, "origin")
        os.makedirs(os.path.join(self.origin, "docs"))
        git(self.origin, "init", "-q")
        # Lets a shallow clone fetch one commit by its ID, as github.com does.
        git(self.origin, "config", "uploadpack.allowAnySHA1InWant", "true")
        self.commit(self.origin, "base", {"legacy.pdf": self.LEAK(), "docs/clean.pdf": self.CLEAN()})
        self.base = git(self.origin, "rev-parse", "HEAD")

    def commit(self, repo, message, files=(), remove=()):
        for rel, data in dict(files).items():
            path = os.path.join(repo, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
        for rel in remove:
            os.remove(os.path.join(repo, rel))
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", message)
        return git(repo, "rev-parse", "HEAD")

    def clone(self, *args):
        """A checkout of origin's current commit, as actions/checkout leaves it."""
        repo = os.path.join(self.gh, f"checkout-{len(os.listdir(self.gh))}")
        git(self.gh, "clone", "-q", *args, "file://" + self.origin, repo)
        return repo

    def pull_request(self, base=None):
        return {"pull_request": {"base": {"sha": base or self.base}}}

    def assert_everything_checked(self, r, level, because):
        self.assertEqual(r.outputs["files-skipped"], "0", r.log)
        self.assertEqual(r.outputs["files-with-hidden-text"], "1", "legacy.pdf should have been checked")
        self.assertEqual(r.returncode, 1)
        [(name, props, message)] = [c for c in r.commands if c[1].get("title", "").startswith("changed-only")]
        self.assertEqual((name, props["title"]), (level, "changed-only: every PDF was checked"))
        self.assertIn(because, message)
        self.assertTrue(message.endswith("Every PDF in paths was checked."), message)
        self.assertIsNone(r.report["skipped"]["compared_with"])

    # ── It narrows the check ────────────────────────────────────────────────

    def test_only_what_the_pull_request_changed_is_checked(self):
        self.commit(self.origin, "pr", {"docs/new.pdf": self.CLEAN(), "docs/clean.pdf": self.CLEAN("Edited")})
        repo = self.clone()
        r = self.run_check(".", changed_only="true", cwd=repo, event=self.pull_request())
        self.assertEqual(r.returncode, 0, r.log)
        self.assertEqual((r.outputs["files-checked"], r.outputs["files-skipped"]), ("2", "1"))
        self.assertEqual(sorted(f["path"] for f in r.report["files"]), ["docs/clean.pdf", "docs/new.pdf"])
        self.assertEqual(r.report["skipped"], {"excluded": [], "unchanged": ["legacy.pdf"], "compared_with": self.base})
        note = f"1 PDF unchanged since commit {self.base[:7]} was not checked (changed-only)."
        self.assertIn(note, r.log)
        self.assertIn(note, r.summary)
        self.assertEqual(r.commands, [])
        # The same checkout without changed-only fails on the legacy file.
        self.assertEqual(self.run_check(".", cwd=repo, event=self.pull_request()).returncode, 1)

    def test_a_leak_the_pull_request_adds_fails(self):
        self.commit(self.origin, "pr", {"docs/filing.pdf": self.LEAK()})
        r = self.run_check(".", changed_only="true", cwd=self.clone(), event=self.pull_request())
        self.assertEqual(r.returncode, 1, r.log)
        self.assertEqual([c[1]["file"] for c in r.commands], ["docs/filing.pdf"])
        self.assertEqual(r.outputs["files-skipped"], "2")

    def test_a_pull_request_that_touches_no_pdf_passes(self):
        self.commit(self.origin, "pr", {"README.md": b"hello"})
        r = self.run_check(".", changed_only="true", cwd=self.clone(), event=self.pull_request())
        self.assertEqual(r.returncode, 0, r.log)
        self.assertEqual((r.outputs["files-checked"], r.outputs["files-skipped"]), ("0", "2"))
        self.assertIn("**No PDFs needed checking.**", r.summary)

    def test_a_push_is_compared_with_the_commit_it_replaced(self):
        head = self.commit(self.origin, "push", {"docs/filing.pdf": self.LEAK()})
        r = self.run_check(".", changed_only="true", cwd=self.clone(), event={"before": self.base, "after": head})
        self.assertEqual((r.returncode, r.outputs["files-checked"], r.outputs["files-skipped"]), (1, "1", "2"))

    def test_a_merge_queue_is_compared_with_its_base(self):
        self.commit(self.origin, "queued", {"docs/new.pdf": self.CLEAN()})
        r = self.run_check(".", changed_only="true", cwd=self.clone(), event={"merge_group": {"base_sha": self.base}})
        self.assertEqual((r.returncode, r.outputs["files-checked"]), (0, "1"))

    def test_a_shallow_checkout_fetches_the_one_commit_it_needs(self):
        """actions/checkout fetches a single commit by default, so the base
        isn't there until it is fetched. Only that commit is fetched, not the
        history behind it, which in a large repository could be gigabytes."""
        older = self.base
        base = self.commit(self.origin, "the base, with history behind it", {"notes.txt": b"x"})
        self.commit(self.origin, "pr", {"docs/new.pdf": self.CLEAN()})
        repo = self.clone("--depth=1")

        def has(commit):
            return subprocess.run(["git", "cat-file", "-e", commit], cwd=repo, capture_output=True).returncode == 0

        self.assertFalse(has(base))
        r = self.run_check(".", changed_only="true", cwd=repo, event=self.pull_request(base))
        self.assertEqual(r.returncode, 0, r.log)
        self.assertEqual((r.outputs["files-checked"], r.outputs["files-skipped"]), ("1", "2"))
        self.assertTrue(has(base))
        self.assertFalse(has(older), "the history behind the base was fetched too")
        self.assertEqual(git(repo, "rev-parse", "--is-shallow-repository"), "true")

    def test_fetching_the_base_does_not_make_a_complete_checkout_shallow(self):
        """A complete clone that happens to lack the base (it lives on a
        branch that was never fetched) must stay complete: later steps in the
        same job may rely on the history."""
        git(self.origin, "checkout", "-q", "-b", "side")
        side = self.commit(self.origin, "on a side branch", {"side.txt": b"x"})
        git(self.origin, "checkout", "-q", "main")
        self.commit(self.origin, "pr", {"docs/new.pdf": self.CLEAN()})
        repo = self.clone("--single-branch", "--branch", "main")
        self.assertNotEqual(subprocess.run(["git", "cat-file", "-e", side], cwd=repo, capture_output=True).returncode, 0)
        r = self.run_check(".", changed_only="true", cwd=repo, event=self.pull_request(side))
        self.assertEqual(r.outputs["files-skipped"], "2", r.log)
        self.assertEqual(git(repo, "rev-parse", "--is-shallow-repository"), "false")

    def test_run_from_a_subdirectory(self):
        self.commit(self.origin, "pr", {"docs/new.pdf": self.CLEAN(), "other.pdf": self.LEAK()})
        repo = self.clone()
        r = self.run_check(".", changed_only="true", cwd=os.path.join(repo, "docs"), event=self.pull_request())
        self.assertEqual(r.returncode, 0, r.log)
        self.assertEqual(sorted(f["path"] for f in r.report["files"]), ["new.pdf"])
        self.assertEqual(r.report["skipped"]["unchanged"], ["clean.pdf"])

    def test_unusual_file_names(self):
        names = ["with space.pdf", "naïve ünïcode.pdf", EVIL_NAME]
        self.commit(self.origin, "names", {n: self.LEAK() for n in names})
        base = git(self.origin, "rev-parse", "HEAD")
        self.commit(self.origin, "pr", {names[0]: self.CLEAN()})
        r = self.run_check(".", changed_only="true", cwd=self.clone(), event=self.pull_request(base))
        self.assertEqual(r.returncode, 0, r.log)
        self.assertEqual([f["path"] for f in r.report["files"]], ["with space.pdf"])
        self.assertEqual(r.outputs["files-skipped"], "4")

    def test_it_works_together_with_exclude(self):
        self.commit(self.origin, "pr", {"docs/new.pdf": self.CLEAN(), "docs/known.pdf": self.LEAK()})
        r = self.run_check(".", changed_only="true", exclude="docs/known.pdf", cwd=self.clone(),
                           event=self.pull_request())
        self.assertEqual(r.returncode, 0, r.log)
        self.assertEqual(r.report["skipped"]["excluded"], ["docs/known.pdf"])
        self.assertEqual(sorted(r.report["skipped"]["unchanged"]), ["docs/clean.pdf", "legacy.pdf"])
        self.assertEqual((r.outputs["files-checked"], r.outputs["files-skipped"]), ("1", "3"))

    def test_the_users_git_configuration_still_applies(self):
        """The check gives git its own global config so it can trust the
        checkout. That config includes the user's, which a self-hosted runner
        may need to reach the remote at all: here, a URL rewrite."""
        self.commit(self.origin, "pr", {"docs/new.pdf": self.CLEAN()})
        repo = self.clone("--depth=1")
        git(repo, "remote", "set-url", "origin", "file:///mirror/that/does/not/exist")
        config = os.path.join(self.gh, "user.gitconfig")
        with open(config, "w") as f:
            f.write(f'[url "file://{self.origin}"]\n\tinsteadOf = file:///mirror/that/does/not/exist\n')
        r = self.run_check(".", changed_only="true", cwd=repo, event=self.pull_request(),
                           env={"GIT_CONFIG_GLOBAL": config})
        self.assertEqual((r.returncode, r.outputs["files-checked"], r.outputs["files-skipped"]), (0, "1", "2"), r.log)

    def test_it_leaves_nothing_in_the_runners_temp_directory(self):
        self.commit(self.origin, "pr", {"docs/new.pdf": self.CLEAN()})
        self.run_check(".", changed_only="true", cwd=self.clone(), event=self.pull_request())
        self.assertEqual([n for n in os.listdir(self.gh) if n.startswith("nilpdf-git-")], [])

    @unittest.skipUnless(hasattr(os, "geteuid") and os.geteuid() == 0,
                         "needs root, as in a container job: the checkout must belong to another user")
    def test_a_checkout_owned_by_another_user(self):
        """In a container job, git refuses to read the runner's checkout
        ("dubious ownership") unless told it is safe."""
        self.commit(self.origin, "pr", {"docs/new.pdf": self.CLEAN()})
        repo = self.clone()
        for root, dirs, files in os.walk(repo):
            for name in dirs + files:
                os.chown(os.path.join(root, name), 1000, 1000, follow_symlinks=False)
        os.chown(repo, 1000, 1000)
        r = self.run_check(".", changed_only="true", cwd=repo, event=self.pull_request())
        self.assertEqual(r.returncode, 0, r.log)
        self.assertEqual((r.outputs["files-checked"], r.outputs["files-skipped"]), ("1", "2"))

    # ── It never skips what git can't vouch for ─────────────────────────────

    def test_generated_untracked_and_edited_files_are_always_checked(self):
        """A workflow that builds PDFs and then checks them has files git has
        never seen. Skipping those would skip the whole point."""
        self.commit(self.origin, "pr", {".gitignore": b"build/\n"})
        repo = self.clone()
        os.makedirs(os.path.join(repo, "build"))
        for rel, data in (("build/generated.pdf", self.LEAK()),        # ignored by git
                          ("untracked.pdf", self.LEAK()),               # never added
                          ("docs/clean.pdf", self.LEAK())):             # tracked, edited after checkout
            with open(os.path.join(repo, rel), "wb") as f:
                f.write(data)
        r = self.run_check(".", changed_only="true", cwd=repo, event=self.pull_request())
        self.assertEqual(r.returncode, 1, r.log)
        self.assertEqual(sorted(c[1]["file"] for c in r.commands),
                         ["build/generated.pdf", "docs/clean.pdf", "untracked.pdf"])
        self.assertEqual(r.report["skipped"]["unchanged"], ["legacy.pdf"])

    def test_a_staged_edit_is_checked_too(self):
        self.commit(self.origin, "pr", {"README.md": b"hello"})
        repo = self.clone()
        with open(os.path.join(repo, "docs", "clean.pdf"), "wb") as f:
            f.write(self.LEAK())
        git(repo, "add", "docs/clean.pdf")
        r = self.run_check("docs", changed_only="true", cwd=repo, event=self.pull_request())
        self.assertEqual((r.returncode, r.outputs["files-with-hidden-text"]), (1, "1"), r.log)

    def test_changes_on_the_base_branch_only_add_to_what_is_checked(self):
        """If the workflow checks out the pull request's own head rather than
        the merge, files the base branch changed since look changed too. They
        get checked: more than needed, never less."""
        repo = self.clone()
        git(repo, "checkout", "-q", "-b", "feature")
        self.commit(repo, "pr", {"docs/new.pdf": self.CLEAN()})
        newer_base = self.commit(self.origin, "base moves on", {"legacy.pdf": self.CLEAN("Fixed on main")})
        git(repo, "fetch", "-q", "origin")
        r = self.run_check(".", changed_only="true", cwd=repo, event=self.pull_request(newer_base))
        self.assertEqual(sorted(f["path"] for f in r.report["files"]), ["docs/new.pdf", "legacy.pdf"])
        self.assertEqual(r.returncode, 1, "the checkout still has the old legacy.pdf, and it is checked")

    # ── When the comparison can't be made, everything is checked ────────────

    def test_no_base_commit_checks_everything_with_a_notice(self):
        self.commit(self.origin, "more", {"docs/new.pdf": self.CLEAN()})
        repo = self.clone()
        events = {
            "a manual or scheduled run": {"inputs": {}},
            "the first push of a branch": {"before": "0" * 40, "after": self.base},
            "an event with no payload": None,
        }
        for label, event in events.items():
            with self.subTest(event=label):
                r = self.run_check(".", changed_only="true", cwd=repo, event=event)
                self.assert_everything_checked(r, "notice", "this run has no earlier commit to compare with")

    def test_a_base_that_is_not_a_commit_id_is_ignored(self):
        """The base comes from the event payload and goes onto a git command
        line. Only a full hexadecimal ID is accepted."""
        self.commit(self.origin, "more", {"docs/new.pdf": self.CLEAN()})
        repo = self.clone()
        planted = os.path.join(self.gh, "planted")
        for bad in ("HEAD", "main", self.base[:12], self.base.upper(), f"--output={planted}",
                    f"{self.base}\n--output={planted}", f"{self.base} --output={planted}", 12345, ["x"], None):
            with self.subTest(base=bad):
                r = self.run_check(".", changed_only="true", cwd=repo,
                                   event={"pull_request": {"base": {"sha": bad}}})
                self.assert_everything_checked(r, "notice", "no earlier commit")
        self.assertFalse(os.path.exists(planted))

    def test_the_checked_out_commit_being_the_base_checks_everything(self):
        r = self.run_check(".", changed_only="true", cwd=self.clone(), event=self.pull_request())
        self.assert_everything_checked(r, "warning", "pull_request_target")

    def test_not_a_git_checkout_checks_everything(self):
        plain = os.path.join(self.gh, "plain")
        os.makedirs(plain)
        with open(os.path.join(plain, "legacy.pdf"), "wb") as f:
            f.write(self.LEAK())
        r = self.run_check(".", changed_only="true", cwd=plain, event=self.pull_request())
        self.assert_everything_checked(r, "warning", "not a git checkout")

    def test_git_not_installed_checks_everything(self):
        self.commit(self.origin, "pr", {"docs/new.pdf": self.CLEAN()})
        empty = os.path.join(self.gh, "empty-path")
        os.makedirs(empty)
        r = self.run_check(".", changed_only="true", cwd=self.clone(), event=self.pull_request(), env={"PATH": empty})
        self.assert_everything_checked(r, "warning", "git is not installed")

    def test_a_base_that_cannot_be_fetched_checks_everything(self):
        self.commit(self.origin, "pr", {"docs/new.pdf": self.CLEAN()})
        repo = self.clone("--depth=1")
        git(repo, "remote", "set-url", "origin", "file://" + os.path.join(self.gh, "gone"))
        r = self.run_check(".", changed_only="true", cwd=repo, event=self.pull_request())
        self.assert_everything_checked(r, "warning", f"({self.base[:7]}) is not in the checkout and could not be fetched")

    def test_a_base_from_another_repository_checks_everything(self):
        self.commit(self.origin, "pr", {"docs/new.pdf": self.CLEAN()})
        r = self.run_check(".", changed_only="true", cwd=self.clone(), event=self.pull_request("ab" * 20))
        self.assert_everything_checked(r, "warning", "could not be fetched")

    def test_off_by_default(self):
        self.commit(self.origin, "pr", {"docs/new.pdf": self.CLEAN()})
        r = self.run_check(".", cwd=self.clone(), event=self.pull_request())
        self.assertEqual((r.returncode, r.outputs["files-checked"], r.outputs["files-skipped"]), (1, "3", "0"))
        self.assertEqual(r.report["skipped"], {"excluded": [], "unchanged": [], "compared_with": None})


if __name__ == "__main__":
    unittest.main()
