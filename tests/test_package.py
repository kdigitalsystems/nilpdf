"""The pip package, tested the way a user meets it.

These build the real wheel and sdist from pyproject.toml, install the wheel,
and run the installed `nilpdf` command. That catches what testing the source
can't: a file missing from the wheel, a broken console-script entry point, an
engine that drifted from the one the browser loads, the website leaking into
the sdist, or a dependency the package forgot to declare.

Everything runs offline: the wheel is built with the hatchling backend already
installed (requirements.txt) and installed with --no-deps into a scratch
directory, using the dependencies this test environment already has.
"""
import email.parser
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_engine import box, make_encrypted_pdf, make_line_pdf  # noqa: E402

HAVE_BUILD_TOOLS = (importlib.util.find_spec("hatchling") is not None
                    and importlib.util.find_spec("pip") is not None)


def read(rel):
    with open(os.path.join(BASE, rel), encoding="utf-8") as f:
        return f.read()


def source_version():
    return re.search(r'^__version__ = "([^"]+)"', read("python/nilpdf/__init__.py"), re.M).group(1)


def console_scripts():
    """[project.scripts] from pyproject.toml. tomllib only exists from Python
    3.11, and the package supports 3.10, so fall back to reading the table."""
    text = read("pyproject.toml")
    try:
        import tomllib
    except ModuleNotFoundError:
        table = re.search(r"^\[project\.scripts\]\n(.*?)(?=^\[|\Z)", text, re.M | re.S).group(1)
        return dict(re.findall(r'^([\w-]+)\s*=\s*"([^"]+)"', table, re.M))
    return tomllib.loads(text)["project"]["scripts"]


def build(kind, outdir, project_dir=BASE):
    """Call the PEP 517 hook directly, in a subprocess so the build runs from
    the project directory exactly as pip would run it."""
    code = f"import hatchling.build as b, sys; print(b.build_{kind}(sys.argv[1]))"
    out = subprocess.run([sys.executable, "-c", code, outdir], cwd=project_dir,
                         capture_output=True, text=True, check=True)
    return os.path.join(outdir, out.stdout.strip().splitlines()[-1])


@unittest.skipUnless(HAVE_BUILD_TOOLS, "hatchling and pip are needed to build and install the package")
class PackageTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="nilpdf-pkg-")
        cls.dist = os.path.join(cls.tmp, "dist")
        os.makedirs(cls.dist)
        cls.wheel = build("wheel", cls.dist)
        cls.sdist = build("sdist", cls.dist)
        cls.site = os.path.join(cls.tmp, "site")
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--no-deps", "--no-compile",
                        "--target", cls.site, cls.wheel], check=True, capture_output=True)
        cls.exe = os.path.join(cls.site, "bin", "nilpdf")
        cls.env = {**os.environ, "PYTHONPATH": cls.site, "PYTHONIOENCODING": "utf-8"}

        fx = cls.fx = os.path.join(cls.tmp, "fx")
        os.makedirs(os.path.join(fx, "tree", "sub"))
        cls.write("clean.pdf", make_line_pdf())
        cls.write("hidden.pdf", make_line_pdf(draw=box(0, 0, 0)))
        cls.write("tree/a_clean.pdf", make_line_pdf())
        cls.write("tree/sub/b_whiteout.PDF", make_line_pdf(draw=box(1, 1, 1)))
        cls.write("notes.txt", b"not a pdf")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def write(cls, rel, data):
        with open(os.path.join(cls.fx, rel), "wb") as f:
            f.write(data)

    def nilpdf(self, *args, stdin=None):
        return subprocess.run([self.exe, *args], cwd=self.fx, env=self.env, input=stdin,
                              capture_output=True, timeout=120)

    def out(self, result):
        return result.stdout.decode("utf-8") + result.stderr.decode("utf-8")


class TestWhatGetsShipped(PackageTestCase):
    def test_wheel_ships_the_exact_engine_the_browser_loads(self):
        with zipfile.ZipFile(self.wheel) as w:
            shipped = w.read("nilpdf/engine.py")
        with open(os.path.join(BASE, "core/pdf_engine.py"), "rb") as f:
            self.assertEqual(shipped, f.read(), "the wheel's engine differs from core/pdf_engine.py")

    def test_wheel_contains_only_the_package(self):
        with zipfile.ZipFile(self.wheel) as w:
            code = sorted(n for n in w.namelist() if not n.startswith("nilpdf-"))
        self.assertEqual(code, ["nilpdf/__init__.py", "nilpdf/__main__.py", "nilpdf/cli.py", "nilpdf/engine.py"])

    def test_metadata_declares_what_the_checker_needs_and_no_more(self):
        with zipfile.ZipFile(self.wheel) as w:
            info = next(n for n in w.namelist() if n.endswith(".dist-info/METADATA"))
            meta = email.parser.Parser().parsestr(w.read(info).decode())
            entry_points = w.read(info.replace("METADATA", "entry_points.txt")).decode()
        self.assertEqual(meta["Name"], "nilpdf")
        self.assertEqual(meta["Version"], source_version())
        self.assertEqual(meta["License-Expression"], "MIT")
        self.assertEqual(meta["Requires-Python"], ">=3.10")
        requires = meta.get_all("Requires-Dist")
        base = [r for r in requires if "extra ==" not in r]
        self.assertEqual(len(base), 1, f"unexpected unconditional dependencies: {base}")
        self.assertTrue(base[0].startswith("pypdf[crypto]"), base)
        # The floor is the version CI tests. A lower one would let pip pair the
        # checker with a pypdf nobody tested and that has known advisories.
        tested = re.search(r"(?m)^pypdf==(\S+)$", read("requirements.txt")).group(1)
        self.assertRegex(base[0], rf">={re.escape(tested)}(,|$)",
                         f"the pypdf floor must be the version requirements.txt tests ({tested})")
        for heavy in ("pillow", "reportlab"):
            matches = [r for r in requires if r.lower().startswith(heavy)]
            self.assertTrue(matches, f"{heavy} should be offered through the full extra")
            for r in matches:
                # Either quote style is valid in an environment marker.
                self.assertRegex(r, r"extra\s*==\s*[\"']full[\"']", f"{heavy} must only come with the full extra")
        self.assertIn("nilpdf = nilpdf.cli:main", entry_points)

    def test_sdist_contains_the_package_not_the_website(self):
        with tarfile.open(self.sdist) as t:
            names = {n.split("/", 1)[1] for n in t.getnames() if "/" in n}
        for needed in ("pyproject.toml", "LICENSE", "core/pdf_engine.py", "python/nilpdf/cli.py", "python/README.md"):
            self.assertIn(needed, names)
        website = [n for n in names if n.endswith((".html", ".css", ".png", ".svg")) or n.startswith("assets/")]
        self.assertFalse(website, f"website files leaked into the sdist: {website[:5]}")

    def test_wheel_builds_from_the_sdist_alone(self):
        unpack = os.path.join(self.tmp, "from-sdist")
        with tarfile.open(self.sdist) as t:
            t.extractall(unpack, filter="data") if sys.version_info >= (3, 12) else t.extractall(unpack)
        root = os.path.join(unpack, os.listdir(unpack)[0])
        out = os.path.join(self.tmp, "dist2")
        os.makedirs(out)
        with zipfile.ZipFile(build("wheel", out, project_dir=root)) as w:
            self.assertIn("nilpdf/engine.py", w.namelist())


class TestCheckRedactionCommand(PackageTestCase):
    def test_version(self):
        r = self.nilpdf("--version")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.out(r).strip(), f"nilpdf {source_version()}")

    def test_clean_file_exits_0(self):
        r = self.nilpdf("check-redaction", "clean.pdf")
        self.assertEqual(r.returncode, 0, self.out(r))
        self.assertIn("OK      clean.pdf: no hidden text", self.out(r))

    def test_hidden_text_exits_1_and_shows_the_text(self):
        r = self.nilpdf("check-redaction", "hidden.pdf")
        self.assertEqual(r.returncode, 1, self.out(r))
        self.assertIn("HIDDEN  hidden.pdf", self.out(r))
        self.assertIn("SECRET-123-45-6789", self.out(r))

    def test_directories_are_searched_recursively(self):
        r = self.nilpdf("check-redaction", "tree")
        self.assertEqual(r.returncode, 1, self.out(r))
        self.assertIn("tree/a_clean.pdf: no hidden text", self.out(r))
        self.assertIn("b_whiteout.PDF: hidden text", self.out(r), "upper-case .PDF must be found too")
        self.assertIn("white shape", self.out(r))
        self.assertIn("Checked 2 files: 1 with hidden text, 1 clean.", self.out(r))

    def test_json_report(self):
        r = self.nilpdf("check-redaction", "--json", "clean.pdf", "hidden.pdf")
        self.assertEqual(r.returncode, 1)
        report = json.loads(r.stdout)
        self.assertEqual(report["nilpdf_version"], source_version())
        self.assertTrue(report["hidden_text_found"])
        by_path = {f["path"]: f for f in report["files"]}
        self.assertFalse(by_path["clean.pdf"]["hidden_text_found"])
        self.assertEqual(by_path["hidden.pdf"]["findings"][0]["kind"], "covered_text")

    def test_encrypted_pdf(self):
        self.write("enc.pdf", make_encrypted_pdf(password="pw"))
        missing = self.nilpdf("check-redaction", "enc.pdf")
        self.assertEqual(missing.returncode, 2)
        self.assertIn("wrong or missing password", self.out(missing))
        self.assertEqual(self.nilpdf("check-redaction", "enc.pdf", "--password", "pw").returncode, 0)

    def test_unreadable_inputs_exit_2_cleanly(self):
        r = self.nilpdf("check-redaction", "notes.txt", "missing.pdf")
        self.assertEqual(r.returncode, 2)
        out = self.out(r)
        self.assertIn("notes.txt: not a PDF file", out)
        self.assertIn("missing.pdf: cannot read file", out)
        self.assertNotIn("Traceback", out)
        self.assertNotIn("EOF marker", out, "pypdf's internal warnings must not leak into the report")

    def test_hidden_text_wins_over_errors_in_the_exit_code(self):
        self.assertEqual(self.nilpdf("check-redaction", "hidden.pdf", "notes.txt").returncode, 1)

    def test_empty_directory_exits_2(self):
        os.makedirs(os.path.join(self.fx, "empty"), exist_ok=True)
        r = self.nilpdf("check-redaction", "empty")
        self.assertEqual(r.returncode, 2)
        self.assertIn("no PDF files found", self.out(r))

    def test_standard_input(self):
        with open(os.path.join(self.fx, "hidden.pdf"), "rb") as f:
            r = self.nilpdf("check-redaction", "-", stdin=f.read())
        self.assertEqual(r.returncode, 1)
        self.assertIn("HIDDEN  <stdin>", self.out(r))

    def test_python_dash_m(self):
        r = subprocess.run([sys.executable, "-m", "nilpdf", "check-redaction", "hidden.pdf"],
                           cwd=self.fx, env=self.env, capture_output=True, timeout=120)
        self.assertEqual(r.returncode, 1, r.stderr.decode())

    def test_untrusted_text_cannot_reach_the_terminal_raw(self):
        """Document properties and file names are attacker-controlled. Control
        characters must come out escaped, never as live escape sequences, bell
        characters, newlines that forge report lines, or bidi overrides."""
        from pypdf import PdfReader, PdfWriter
        w = PdfWriter(clone_from=PdfReader(io.BytesIO(make_line_pdf(draw=box(0, 0, 0)))))
        w.add_metadata({"/Title": "\x1b[2J\x1b[31mGOTCHA\x07", "/Author": "Mallory‮edoc\nFAKE LINE"})
        buf = io.BytesIO()
        w.write(buf)
        self.write("evil\x1b[31mname.pdf", buf.getvalue())
        r = self.nilpdf("check-redaction", "-v", "evil\x1b[31mname.pdf")
        out = self.out(r)
        for raw in ("\x1b", "\x07", "‮"):
            self.assertNotIn(raw, out)
        self.assertIn("\\x1b[2J", out)
        self.assertFalse(any(line.startswith("FAKE LINE") for line in out.splitlines()))


class TestLibraryAndIsolation(PackageTestCase):
    def run_python(self, code):
        return subprocess.run([sys.executable, "-c", code], cwd=self.fx, env=self.env,
                              capture_output=True, text=True, timeout=120)

    def test_python_api_accepts_paths_and_bytes(self):
        r = self.run_python(
            "import nilpdf, pathlib\n"
            "a = nilpdf.check_redaction('hidden.pdf')\n"
            "b = nilpdf.check_redaction(pathlib.Path('hidden.pdf').read_bytes())\n"
            "c = nilpdf.check_redaction(pathlib.Path('clean.pdf'))\n"
            "print(a['hidden_text_found'], b['findings'][0]['page'], c['hidden_text_found'])\n")
        self.assertEqual(r.stdout.strip(), "True 1 False", r.stderr)

    def test_check_needs_no_pillow_reportlab_or_network(self):
        """The base install has neither Pillow nor reportlab, and the README
        promises no network requests. Run the check with both libraries and
        every socket call made to fail, and it must still work."""
        r = self.run_python(
            "import sys, socket, importlib.abc\n"
            "class Block(importlib.abc.MetaPathFinder):\n"
            "    def find_spec(self, name, path, target=None):\n"
            "        if name.split('.')[0] in ('PIL', 'reportlab'):\n"
            "            raise ImportError('blocked in test: ' + name)\n"
            "sys.meta_path.insert(0, Block())\n"
            "def no_network(*a, **k):\n"
            "    raise AssertionError('network access attempted')\n"
            "socket.socket = socket.create_connection = socket.getaddrinfo = no_network\n"
            "from nilpdf.cli import main\n"
            "sys.exit(main(['check-redaction', 'hidden.pdf', 'clean.pdf']))\n")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("SECRET-123-45-6789", r.stdout)


class TestIntegrationFiles(unittest.TestCase):
    """The pre-commit hook and the docs must agree with the package."""

    def test_pre_commit_hook_runs_the_real_command(self):
        hook = read(".pre-commit-hooks.yaml")
        scripts = console_scripts()
        entry = re.search(r"^\s*entry:\s*(.+)$", hook, re.M).group(1).split()
        self.assertIn(entry[0], scripts, "the hook's entry must be a console script the package installs")
        self.assertEqual(entry[1:], ["check-redaction"])
        self.assertRegex(hook, r"(?m)^\s*language:\s*python\s*$")
        self.assertRegex(hook, r"(?m)^\s*types:\s*\[pdf\]\s*$")

    def test_readme_pins_the_current_release(self):
        """The pre-commit example pins a tag; bumping the version must bump it."""
        self.assertIn(f"rev: v{source_version()}", read("python/README.md"))


if __name__ == "__main__":
    unittest.main()
