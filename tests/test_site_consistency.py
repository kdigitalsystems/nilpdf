"""Static consistency checks across index.html, assets/js/app.js,
generate_pages.py, and sitemap.xml.

These don't touch the PDF engine — they exist because every tool this
session (Protect, Fill & Sign, Unlock) needed registering in half a dozen
places (TOOL_META, SINGLE_FILE_TOOLS, the workspace tab bar, the homepage
card grid, the footer links, the SEO-page generator, the sitemap), and a
tool that's missing from just one of them is easy to ship without noticing
in manual testing. These tests turn that into something CI catches
automatically the moment a new tool (or a rename/removal) misses one of
the required spots.
"""
import importlib.util
import os
import re
import shutil
import subprocess
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node") or shutil.which("nodejs")


def read(relative_path):
    with open(os.path.join(BASE, relative_path), encoding="utf-8") as f:
        return f.read()


def worker_packages():
    """The requirement strings pdf_worker.js installs, e.g. "pypdf==6.19.0".
    The browser tests import this too, so there is one parser to keep current."""
    m = re.search(r"^const PACKAGES = \[(.*?)\];", read("assets/js/pdf_worker.js"), re.M)
    return re.findall(r"[\"']([^\"']+)[\"']", m.group(1)) if m else []


def load_generate_pages():
    spec = importlib.util.spec_from_file_location(
        "generate_pages", os.path.join(BASE, "generate_pages.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tool_meta_ids(app_js):
    """Tool ids declared in app.js's TOOL_META object."""
    m = re.search(r"const TOOL_META = \{(.*?)\n\s*\};", app_js, re.DOTALL)
    assert m is not None, "Could not find TOOL_META block in assets/js/app.js"
    ids = set(re.findall(r"^\s*(\w+):\s*\{", m.group(1), re.MULTILINE))
    assert ids, "TOOL_META parsed but no tool ids were found — regex may be stale"
    return ids


class TestToolRegistration(unittest.TestCase):
    """Every tool id that appears in TOOL_META must appear consistently in
    every other place a tool is registered.

    TOOL_META and SINGLE_FILE_TOOLS live in assets/js/app.js; the tab bar,
    homepage cards, footer links and workspace sections are markup in
    index.html. The split is why these checks read two files."""

    @classmethod
    def setUpClass(cls):
        cls.html = read("index.html")
        cls.app = read("assets/js/app.js")

    def _tool_meta_ids(self):
        return tool_meta_ids(self.app)

    def _single_file_tools(self):
        m = re.search(r"const SINGLE_FILE_TOOLS = \[(.*?)\];", self.app)
        self.assertIsNotNone(m, "Could not find SINGLE_FILE_TOOLS in assets/js/app.js")
        return set(re.findall(r"'(\w+)'", m.group(1)))

    def _tab_buttons(self):
        ids = set(re.findall(r"switchTab\(event, '(\w+)'\)", self.html))
        self.assertTrue(ids, "No switchTab(...) tab buttons found — regex may be stale")
        return ids

    def _homepage_tool_cards(self):
        ids = set(re.findall(r'class="tool-card" data-category="\w+" onclick="openTool\(\'(\w+)\'\)"', self.html))
        self.assertTrue(ids, "No homepage .tool-card entries found — regex may be stale")
        return ids

    def _footer_links(self):
        m = re.search(r'<div class="site-footer-tool-cols">(.*?)</div>', self.html, re.DOTALL)
        self.assertIsNotNone(m, "Could not find site-footer-tool-cols in index.html")
        ids = set(re.findall(r"openTool\('(\w+)'\)", m.group(1)))
        self.assertTrue(ids, "No footer tool links found — regex may be stale")
        return ids

    def test_tool_meta_matches_tab_buttons(self):
        self.assertEqual(self._tool_meta_ids(), self._tab_buttons())

    def test_tool_meta_matches_homepage_cards(self):
        self.assertEqual(self._tool_meta_ids(), self._homepage_tool_cards())

    def test_tool_meta_matches_footer_links(self):
        self.assertEqual(self._tool_meta_ids(), self._footer_links())

    def test_single_file_tools_is_subset_of_tool_meta(self):
        unknown = self._single_file_tools() - self._tool_meta_ids()
        self.assertFalse(unknown, f"SINGLE_FILE_TOOLS references unknown tool id(s): {unknown}")

    def test_every_tool_has_a_workspace_section(self):
        for tool_id in self._tool_meta_ids():
            self.assertIn(
                f'id="tool-{tool_id}"', self.html,
                f"TOOL_META has '{tool_id}' but no matching workspace section (id=\"tool-{tool_id}\")",
            )

    def test_no_duplicate_tool_card_ids(self):
        html_ids = re.findall(r'class="tool-card" data-category="\w+" onclick="openTool\(\'(\w+)\'\)"', self.html)
        dupes = {t for t in html_ids if html_ids.count(t) > 1}
        self.assertFalse(dupes, f"Duplicate homepage tool card(s): {dupes}")


class TestGeneratePagesConsistency(unittest.TestCase):
    """generate_pages.py's TOOLS list must be internally consistent and
    aligned with app.js's TOOL_META."""

    @classmethod
    def setUpClass(cls):
        cls.gp = load_generate_pages()

    def test_every_tool_entry_has_required_keys(self):
        required = {
            "slug", "tool_id", "title", "h1", "tagline", "description", "keywords",
            "bullets", "body_text", "how_to_name", "how_to_steps", "faq", "related",
        }
        for tool in self.gp.TOOLS:
            missing = required - set(tool.keys())
            self.assertFalse(missing, f"{tool.get('slug', '?')} is missing key(s): {missing}")

    def test_no_duplicate_slugs(self):
        slugs = [t["slug"] for t in self.gp.TOOLS]
        dupes = {s for s in slugs if slugs.count(s) > 1}
        self.assertFalse(dupes, f"Duplicate slug(s) in TOOLS: {dupes}")

    def test_no_duplicate_tool_ids(self):
        ids = [t["tool_id"] for t in self.gp.TOOLS]
        dupes = {i for i in ids if ids.count(i) > 1}
        self.assertFalse(dupes, f"Duplicate tool_id(s) in TOOLS: {dupes}")

    def test_every_related_slug_points_to_a_real_tool(self):
        slugs = {t["slug"] for t in self.gp.TOOLS}
        for tool in self.gp.TOOLS:
            for rel_slug, _label in tool.get("related", []):
                self.assertIn(
                    rel_slug, slugs,
                    f"{tool['slug']}'s 'related' list links to nonexistent slug '{rel_slug}'",
                )

    def test_no_tool_lists_itself_as_related(self):
        for tool in self.gp.TOOLS:
            related_slugs = {rel_slug for rel_slug, _label in tool.get("related", [])}
            self.assertNotIn(tool["slug"], related_slugs, f"{tool['slug']} lists itself as a related tool")

    def test_tool_ids_match_app_js_tool_meta(self):
        meta_ids = tool_meta_ids(read("assets/js/app.js"))
        gp_ids = {t["tool_id"] for t in self.gp.TOOLS}
        self.assertEqual(
            meta_ids, gp_ids,
            "generate_pages.py's TOOLS tool_ids don't match app.js's TOOL_META keys",
        )


class TestSitemapConsistency(unittest.TestCase):
    def test_every_generated_page_is_in_sitemap(self):
        sitemap = read("sitemap.xml")
        gp = load_generate_pages()
        for tool in gp.TOOLS:
            url = f"https://nilpdf.com/{tool['slug']}/"
            self.assertIn(url, sitemap, f"{tool['slug']} has no <loc> entry in sitemap.xml")


class TestBrowserDependencyPins(unittest.TestCase):
    """The versions CI tests must be the versions the browser installs.

    pypdf and reportlab are pure-Python wheels micropip pulls from PyPI at the
    user's first visit, so they are pinned in two places: requirements.txt (what
    the test job installs) and the PACKAGES list in pdf_worker.js (what
    every visitor installs). If those drift, the suite is validating the engine
    against libraries nobody actually runs, and a breaking upstream release ships
    to users with CI still green. A Dependabot PR bumping requirements.txt alone
    fails here until pdf_worker.js is bumped with it.

    cryptography and Pillow are excluded on purpose: in the browser they resolve
    to the compiled WASM wheels in Pyodide's own lockfile and cannot be pinned by
    us, so they carry no version in the micropip call to compare against.
    """

    SHARED = ["pypdf", "reportlab"]

    def _requirements_pins(self):
        pins = {}
        for line in read("requirements.txt").splitlines():
            line = line.split("#")[0].strip()
            m = re.match(r"^([A-Za-z0-9_.\-]+)==([A-Za-z0-9_.\-]+)$", line)
            if m:
                pins[m.group(1).lower()] = m.group(2)
        self.assertTrue(pins, "No pinned requirements parsed — regex may be stale")
        return pins

    def _worker_pins(self):
        specs = worker_packages()
        self.assertTrue(specs, "Could not find `const PACKAGES = [...];` in pdf_worker.js")
        pins = {}
        for spec in specs:
            if "==" in spec:
                name, version = spec.split("==", 1)
                pins[name.lower()] = version
        return pins

    def test_shared_packages_are_pinned_in_both_places(self):
        req, worker = self._requirements_pins(), self._worker_pins()
        for pkg in self.SHARED:
            with self.subTest(package=pkg):
                self.assertIn(pkg, req, f"{pkg} is not pinned in requirements.txt")
                self.assertIn(
                    pkg, worker,
                    f"{pkg} has no ==version pin in pdf_worker.js's PACKAGES; "
                    f"every visitor would get whatever is latest on PyPI that day",
                )

    def test_pinned_versions_match(self):
        req, worker = self._requirements_pins(), self._worker_pins()
        for pkg in self.SHARED:
            with self.subTest(package=pkg):
                self.assertEqual(
                    req.get(pkg), worker.get(pkg),
                    f"{pkg} is pinned to {req.get(pkg)} in requirements.txt but "
                    f"{worker.get(pkg)} in assets/js/pdf_worker.js. CI would be testing a "
                    f"different version than the browser installs — bump both together.",
                )

    def test_the_pinned_list_is_what_gets_installed(self):
        worker = read("assets/js/pdf_worker.js")
        self.assertRegex(worker, r"micropip\.install\(PACKAGES\)")
        self.assertEqual(len(re.findall(r"micropip\.install\(", worker)), 1,
                         "a second micropip.install() would bypass the pins checked here")

    def test_changing_a_pin_evicts_returning_visitors_package_cache(self):
        """Returning visitors load packages from OPFS, keyed by PKG_CACHE_KEY. If a
        pin changes and the key doesn't, they keep the old pypdf indefinitely
        while CI tests the new one. Evaluates the real constants in Node."""
        if not NODE:
            self.skipTest("Node.js is not installed")
        worker = read("assets/js/pdf_worker.js")
        consts = re.findall(r"^const (?:PYODIDE_VERSION|PACKAGES|PKG_CACHE_KEY) = .*;$", worker, re.M)
        self.assertEqual(len(consts), 3, "expected PYODIDE_VERSION, PACKAGES and PKG_CACHE_KEY, one line each")
        pypdf = self._worker_pins()["pypdf"]

        def key(source_lines):
            out = subprocess.run([NODE, "-e", "\n".join(source_lines) + "\nconsole.log(PKG_CACHE_KEY)"],
                                 capture_output=True, text=True, timeout=30)
            self.assertEqual(out.returncode, 0, out.stderr)
            return out.stdout.strip()

        current = key(consts)
        for label, old, new in (("pypdf pin", f"pypdf=={pypdf}", "pypdf==0.0.1"),
                                ("Pyodide version", "'v", "'v0")):
            with self.subTest(change=label):
                changed = [c.replace(old, new, 1) if c.startswith(("const PACKAGES", "const PYODIDE")) else c
                           for c in consts]
                self.assertNotEqual(changed, consts, "the substitution did not apply")
                self.assertNotEqual(key(changed), current)

    def test_worker_pins_nothing_pyodide_controls(self):
        """Pinning cryptography or Pillow in PACKAGES would ask PyPI for a
        version that has no WASM wheel, so boot could fail for every user."""
        worker = self._worker_pins()
        for pkg in ("cryptography", "pillow"):
            with self.subTest(package=pkg):
                self.assertNotIn(
                    pkg, worker,
                    f"{pkg} is version-pinned in pdf_worker.js. It ships as a compiled WASM "
                    f"wheel from Pyodide's lockfile; pin it by changing PYODIDE_VERSION instead.",
                )


class TestWorkerIsAModuleWorker(unittest.TestCase):
    """Pyodide no longer runs in classic workers: its loader throws "Classic web
    workers are not supported". Loaded cross-origin, Chromium hides that message
    and reports only "NetworkError: failed to load", and a failure at the top of a
    worker happens before any error handler exists, so the page just waits
    forever. Reverting either side of this contract would break every tool while
    looking like a network problem."""

    def test_app_creates_the_worker_as_a_module(self):
        self.assertRegex(
            read("assets/js/app.js"),
            r"new Worker\(\s*'\./assets/js/pdf_worker\.js[^']*'\s*,\s*\{\s*type:\s*'module'\s*\}\s*\)",
            "pdf_worker.js must be created with { type: 'module' }",
        )

    def test_worker_does_not_use_importScripts(self):
        # Comments are stripped first: the worker's own header explains why
        # importScripts() can't be used, and that must not count as a call.
        code = re.sub(r"/\*.*?\*/", "", read("assets/js/pdf_worker.js"), flags=re.DOTALL)
        code = re.sub(r"^\s*//.*$", "", code, flags=re.MULTILINE)
        self.assertFalse(
            re.search(r"\bimportScripts\s*\(", code),
            "pdf_worker.js calls importScripts, which is unavailable in module workers; "
            "Pyodide also rejects classic workers",
        )

    def test_pyodide_version_has_a_single_source_of_truth(self):
        worker = read("assets/js/pdf_worker.js")
        pinned = re.findall(r"cdn\.jsdelivr\.net/pyodide/(v[\d.]+)/", worker)
        self.assertFalse(pinned, f"Pyodide URL hardcodes {pinned}; build it from PYODIDE_VERSION instead")
        self.assertRegex(worker, r"const PYODIDE_VERSION = 'v[\d.]+';")


class TestSvgVisibilityToggles(unittest.TestCase):
    """SVG elements have no `hidden` property, so `svgEl.hidden = x` in app.js
    is a silent no-op that sets an expando and never touches the attribute.

    The feedback button's spinner was toggled that way, and CSS gave it
    display:block, which also overrode the [hidden] attribute it started with.
    Together they left the spinner visible and spinning next to "Send Feedback"
    on the live site at all times, making the form look permanently stuck.
    Nothing errored, so nothing noticed. SVGs must be toggled with
    toggleAttribute/setAttribute/removeAttribute instead.
    """

    def test_no_svg_is_toggled_via_the_hidden_property(self):
        html = read("index.html")
        app = read("assets/js/app.js")
        svg_ids = re.findall(r'<svg\b[^>]*\bid="([^"]+)"', html)
        self.assertTrue(svg_ids, "No <svg id=...> found in index.html; regex may be stale")

        for svg_id in svg_ids:
            lookup = rf"document\.getElementById\(['\"]{re.escape(svg_id)}['\"]\)"
            # Direct form:   document.getElementById('x').hidden = ...
            targets = [lookup]
            # Via a variable: const v = document.getElementById('x'); ... v.hidden = ...
            targets += [re.escape(v) for v in re.findall(rf"\b(?:const|let|var)\s+(\w+)\s*=\s*{lookup}", app)]
            for target in targets:
                with self.subTest(svg=svg_id, via=target):
                    self.assertIsNone(
                        re.search(rf"{target}\.hidden\s*=(?!=)", app),
                        f"app.js sets .hidden on <svg id=\"{svg_id}\">, which does nothing. "
                        f"Use toggleAttribute('hidden', bool) instead.",
                    )


class TestStatedToolCountIsTrue(unittest.TestCase):
    """The site states how many tools it has ("22 free PDF tools", "Twenty-two
    ways to handle a PDF") in the meta tags, the manifest, the hero, the share
    text and every landing page footer. Each new tool silently made all of those
    wrong. The count is now checked against TOOL_META."""

    WORDS = {20: "Twenty", 21: "Twenty-one", 22: "Twenty-two", 23: "Twenty-three", 24: "Twenty-four",
             25: "Twenty-five", 26: "Twenty-six", 27: "Twenty-seven", 28: "Twenty-eight", 29: "Twenty-nine", 30: "Thirty"}

    def test_every_stated_count_matches_the_number_of_tools(self):
        app = read("assets/js/app.js")
        m = re.search(r"const TOOL_META = \{(.*?)\n\s*\};", app, re.DOTALL)
        actual = len(re.findall(r"^\s*(\w+):\s*\{", m.group(1), re.MULTILINE))
        sources = {p: read(p) for p in ("index.html", "assets/js/app.js", "manifest.json", "generate_pages.py")}
        stated = []
        for path, text in sources.items():
            stated += [(path, int(n)) for n in re.findall(r"\b(\d+) (?:free )?PDF tools", text)]
            for n, word in self.WORDS.items():
                if f"{word} ways to handle a PDF" in text:
                    stated.append((path, n))
        self.assertTrue(stated, "No stated tool count found; regex may be stale")
        wrong = [(path, n) for path, n in stated if n != actual]
        self.assertFalse(wrong, f"TOOL_META has {actual} tools, but the copy says: {wrong}")


class TestWorkerActionWiring(unittest.TestCase):
    """Every process_* function pdf_worker.js dispatches to must actually
    exist in core/pdf_engine.py — this is exactly the class of bug a typo'd
    function name or a removed-but-still-referenced function would cause,
    and it would otherwise only surface as a runtime error in the browser."""

    def test_every_worker_action_calls_an_existing_engine_function(self):
        worker_js = read("assets/js/pdf_worker.js")
        engine_py = read("core/pdf_engine.py")
        called = set(re.findall(r"self\.pyodide\.globals\.get\('(\w+)'\)", worker_js))
        self.assertTrue(called, "No process_* dispatch calls found in pdf_worker.js — regex may be stale")
        for fn_name in called:
            self.assertRegex(
                engine_py, rf"\bdef {re.escape(fn_name)}\(",
                f"pdf_worker.js calls '{fn_name}' but core/pdf_engine.py defines no such function",
            )


if __name__ == "__main__":
    unittest.main()
