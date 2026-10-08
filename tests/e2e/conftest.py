"""Fixtures for the browser tests: a stamped copy of the site, a local server
with the cross-origin isolation headers Pyodide needs, and Chromium.

The site under test is stamped by scripts/stamp_build.py, the same script the
deploy job runs, so these test the build users actually receive rather than
the unstamped source.
"""
import functools
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer

import pytest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.dirname(TESTS)
ARTIFACTS = os.path.join(BASE, "e2e-artifacts")
sys.path[:0] = [TESTS, BASE]

E2E_REQUIRED = os.environ.get("NILPDF_E2E") == "1"
ENDPOINT = "https://nilpdf-feedback.example.workers.dev"
SHA = "e2e0e2e0e2e0"

# Real analytics would count every CI run as visits, so it never loads here.
# gtag() itself is defined inline, so events still reach window.dataLayer.
BLOCKED = ("googletagmanager.com", "google-analytics.com")


def _load_dev_server():
    spec = importlib.util.spec_from_file_location("dev_server", os.path.join(BASE, "dev_server.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _stamped_copy(endpoint):
    root = tempfile.mkdtemp(prefix="nilpdf-site-")
    site = os.path.join(root, "site")
    shutil.copytree(BASE, site, ignore=shutil.ignore_patterns(
        ".git", ".venv", ".pytest_cache", "__pycache__", ".claude", "e2e-artifacts",
        "node_modules", "dist", "build", "*.egg-info"))
    args = [sys.executable, os.path.join(site, "scripts", "stamp_build.py"), "--root", site, "--sha", SHA]
    if endpoint:
        args += ["--endpoint", endpoint]
    subprocess.run(args, check=True, capture_output=True, env={**os.environ, "FEEDBACK_ENDPOINT": ""})
    return root, site


def _serve(site):
    handler_cls = _load_dev_server().COEPHandler

    class Quiet(handler_cls):
        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=site))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


@pytest.fixture(scope="session")
def site_url():
    """The site as deployed today: stamped, with no feedback endpoint set."""
    root, site = _stamped_copy(endpoint="")
    httpd, url = _serve(site)
    yield url
    httpd.shutdown()
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture(scope="session")
def site_url_with_relay():
    """The site with FEEDBACK_ENDPOINT configured, as once the Worker is deployed."""
    root, site = _stamped_copy(endpoint=ENDPOINT)
    httpd, url = _serve(site)
    yield url
    httpd.shutdown()
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture(scope="session")
def relay_endpoint():
    return ENDPOINT


@pytest.fixture(scope="session")
def browser():
    if not E2E_REQUIRED:
        pytest.importorskip("playwright.sync_api", reason="install requirements-e2e.txt to run the browser tests")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        b = pw.chromium.launch()
        yield b
        b.close()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    setattr(item, "rep_" + outcome.get_result().when, outcome.get_result())


@pytest.fixture
def context(browser, request):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, accept_downloads=True)
    ctx.route(lambda url: any(b in url for b in BLOCKED), lambda route: route.abort())
    ctx.page_errors = []
    yield ctx
    failed = getattr(request.node, "rep_call", None)
    if failed is not None and failed.failed:
        os.makedirs(ARTIFACTS, exist_ok=True)
        for i, page in enumerate(ctx.pages):
            try:
                page.screenshot(path=os.path.join(ARTIFACTS, f"{request.node.name}-{i}.png"), full_page=True)
            except Exception:
                pass
    ctx.close()


@pytest.fixture
def page(context):
    p = context.new_page()
    p.on("pageerror", lambda e: context.page_errors.append(str(e)))
    return p
