"""Static consistency checks across index.html, generate_pages.py, and
sitemap.xml.

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
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(relative_path):
    with open(os.path.join(BASE, relative_path), encoding="utf-8") as f:
        return f.read()


def load_generate_pages():
    spec = importlib.util.spec_from_file_location(
        "generate_pages", os.path.join(BASE, "generate_pages.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestToolRegistration(unittest.TestCase):
    """Every tool id that appears in TOOL_META must appear consistently in
    every other place index.html registers a tool."""

    @classmethod
    def setUpClass(cls):
        cls.html = read("index.html")

    def _tool_meta_ids(self):
        m = re.search(r"const TOOL_META = \{(.*?)\n\s*\};", self.html, re.DOTALL)
        self.assertIsNotNone(m, "Could not find TOOL_META block in index.html")
        ids = set(re.findall(r"^\s*(\w+):\s*\{", m.group(1), re.MULTILINE))
        self.assertTrue(ids, "TOOL_META parsed but no tool ids were found — regex may be stale")
        return ids

    def _single_file_tools(self):
        m = re.search(r"const SINGLE_FILE_TOOLS = \[(.*?)\];", self.html)
        self.assertIsNotNone(m, "Could not find SINGLE_FILE_TOOLS in index.html")
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
    aligned with index.html's TOOL_META."""

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

    def test_tool_ids_match_index_html_tool_meta(self):
        html = read("index.html")
        m = re.search(r"const TOOL_META = \{(.*?)\n\s*\};", html, re.DOTALL)
        self.assertIsNotNone(m, "Could not find TOOL_META block in index.html")
        meta_ids = set(re.findall(r"^\s*(\w+):\s*\{", m.group(1), re.MULTILINE))
        gp_ids = {t["tool_id"] for t in self.gp.TOOLS}
        self.assertEqual(
            meta_ids, gp_ids,
            "generate_pages.py's TOOLS tool_ids don't match index.html's TOOL_META keys",
        )


class TestSitemapConsistency(unittest.TestCase):
    def test_every_generated_page_is_in_sitemap(self):
        sitemap = read("sitemap.xml")
        gp = load_generate_pages()
        for tool in gp.TOOLS:
            url = f"https://nilpdf.com/{tool['slug']}/"
            self.assertIn(url, sitemap, f"{tool['slug']} has no <loc> entry in sitemap.xml")


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
