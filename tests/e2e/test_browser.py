"""End-to-end tests in Chromium, against the stamped site and the real Pyodide.

These cover what the unit tests can't, each written after a bug of exactly
that kind reached production or nearly did:

- the worker booting at all (Pyodide 314 refused classic workers, and a
  top-level failure left the page waiting forever with no error)
- every worker action on the real WebAssembly builds of pypdf, Pillow,
  cryptography and reportlab, including JS null crossing into Python
- the package cache on a second visit, which restores files outside pip
- the engine's whole unit suite running inside Pyodide itself
- the feedback form, the redaction checker, offline mode, and the analytics
  payload, through the actual UI

Run with: pip install -r requirements-e2e.txt && python -m pytest tests/e2e
"""
import base64
import io
import json
import os
import re
import zipfile

import pytest
from pypdf import PdfReader, PdfWriter

from test_engine import (box, make_encrypted_pdf, make_flat_page_png_base64, make_form_pdf, make_line_pdf,
                         make_pdf, make_pdf_with_raw_image, make_signature_png_base64)

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SECRET = "SECRET-123-45-6789"
BOOT_TIMEOUT_MS = 240_000


def read(rel):
    with open(os.path.join(BASE, rel), encoding="utf-8") as f:
        return f.read()


def b64(data):
    return base64.b64encode(data).decode()


def unb64(s):
    return base64.b64decode(s)


def worker_actions():
    return re.findall(r"action === '([A-Z_]+)'", read("assets/js/pdf_worker.js"))


def tool_count():
    m = re.search(r"const TOOL_META = \{(.*?)\n\s*\};", read("assets/js/app.js"), re.S)
    return len(re.findall(r"^\s*(\w+):\s*\{", m.group(1), re.M))


def webp_signature():
    from PIL import Image
    img = Image.new("RGBA", (120, 40), (0, 0, 0, 0))
    for x in range(10, 110):
        img.putpixel((x, 20 + (x % 7) - 3), (20, 20, 120, 255))
    buf = io.BytesIO()
    img.save(buf, "WEBP")
    return "data:image/webp;base64," + b64(buf.getvalue())


def pdf_with_metadata():
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    w.add_metadata({"/Author": "Jane Secret", "/Title": "Draft memo"})
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def pages(data):
    return len(PdfReader(io.BytesIO(data)).pages)


def image_filters(data):
    xobjects = PdfReader(io.BytesIO(data)).pages[0]["/Resources"]["/XObject"]
    return [str(xobjects[k].get_object().get("/Filter")) for k in xobjects]


def text(data):
    return "".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages)


# ── Page-side helpers ──────────────────────────────────────────────────────

BOOT_JS = """async (timeoutMs) => {
    const msgs = [];
    ensureWorker();
    worker.addEventListener('message', e => {
        if (e.data.type === 'BOOT_PROGRESS') msgs.push(e.data.msg);
        if (e.data.type === 'BOOT_ERROR') msgs.push('BOOT_ERROR: ' + e.data.error);
    });
    const t0 = performance.now();
    await new Promise((resolve, reject) => {
        const iv = setInterval(() => {
            if (isReady) { clearInterval(iv); resolve(); }
            const err = msgs.find(m => m.startsWith('BOOT_ERROR'));
            if (err) { clearInterval(iv); reject(new Error(err)); }
        }, 100);
        setTimeout(() => { clearInterval(iv); reject(new Error('boot timed out; messages: ' + msgs.join(' | '))); }, timeoutMs);
    });
    return { ms: Math.round(performance.now() - t0), msgs };
}"""

# Calls the real worker exactly as app.js does, with binary fields decoded from
# base64, and resolves with this job's own result.
CALL_JS = """async ({ action, payload, binary }) => {
    const bytes = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));
    const toB64 = u => { let s = ''; for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode(...u.subarray(i, i + 0x8000)); return btoa(s); };
    for (const key of binary) payload[key] = Array.isArray(payload[key]) ? payload[key].map(bytes) : bytes(payload[key]);
    const id = 'e2e-' + action + '-' + Math.random().toString(36).slice(2);
    return await new Promise(resolve => {
        const h = e => {
            if (e.data.id !== id || !['SUCCESS', 'ERROR'].includes(e.data.type)) return;
            worker.removeEventListener('message', h);
            resolve(e.data.type === 'SUCCESS' ? { ok: true, b64: toB64(new Uint8Array(e.data.result)) } : { ok: false, error: e.data.error });
        };
        worker.addEventListener('message', h);
        worker.postMessage({ id, action, payload });
    });
}"""


def boot(page):
    return page.evaluate(BOOT_JS, BOOT_TIMEOUT_MS)


def call(page, action, payload, binary=("buffer",)):
    return page.evaluate(CALL_JS, {"action": action, "payload": payload, "binary": list(binary)})


# ── Every worker action ────────────────────────────────────────────────────

def worker_cases():
    """action -> (payload, binary keys, check(result_bytes, earlier_results)).
    Order matters only for UNLOCK, which unlocks PROTECT's output."""
    raw = make_pdf_with_raw_image()
    sig_png = make_signature_png_base64()
    return {
        "MERGE": ({"buffers": [b64(make_pdf(2)), b64(make_pdf(3))], "password": ""}, ("buffers",),
                  lambda r, _: pages(r) == 5),
        "SPLIT": ({"buffer": b64(make_pdf(4)), "indices": [0, 2], "password": ""}, ("buffer",),
                  lambda r, _: pages(r) == 2),
        "SPLIT_MULTI": ({"buffer": b64(make_pdf(3)), "ranges": [[0, 1], [2]], "password": ""}, ("buffer",),
                        lambda r, _: len(zipfile.ZipFile(io.BytesIO(r)).namelist()) == 2),
        "REORDER": ({"buffer": b64(make_pdf(3)), "order": [2, 0, 1], "password": ""}, ("buffer",),
                    lambda r, _: pages(r) == 3),
        "ANONYMIZE": ({"buffer": b64(pdf_with_metadata()), "password": ""}, ("buffer",),
                      lambda r, _: not (PdfReader(io.BytesIO(r)).metadata or {}).get("/Author")),
        "COMPRESS": ({"buffer": b64(raw), "password": ""}, ("buffer",),
                     lambda r, _: image_filters(r) == ["/DCTDecode"]),
        "BULK_PROCESS": ({"sub_action": "COMPRESS", "names": ["a.pdf", "b.pdf"],
                          "buffers": [b64(make_pdf(1)), b64(make_pdf(2))], "password": ""}, ("buffers",),
                         lambda r, _: len(zipfile.ZipFile(io.BytesIO(r)).namelist()) == 2),
        "ROTATE": ({"buffer": b64(make_pdf(2)), "degrees": 90, "indices": [0], "password": ""}, ("buffer",),
                   lambda r, _: PdfReader(io.BytesIO(r)).pages[0].rotation == 90),
        "REMOVE_PAGES": ({"buffer": b64(make_pdf(3)), "indices": [1], "password": ""}, ("buffer",),
                         lambda r, _: pages(r) == 2),
        "EXTRACT_TEXT": ({"buffer": b64(make_line_pdf()), "password": ""}, ("buffer",),
                         lambda r, _: SECRET in r.decode()),
        "WATERMARK": ({"buffer": b64(make_pdf(2)), "text": "CONFIDENTIAL", "opacity": 0.3, "password": ""}, ("buffer",),
                      lambda r, _: pages(r) == 2 and "CONFIDENTIAL" in text(r)),
        "ADD_PAGE_NUMBERS": ({"buffer": b64(make_pdf(3)), "position": "bottom-center", "startNum": 1, "password": ""},
                             ("buffer",), lambda r, _: "3" in text(r)),
        "ADD_FOOTER": ({"buffer": b64(make_pdf(1)), "password": ""}, ("buffer",),
                       lambda r, _: "NilPDF" in text(r)),
        "REPAIR": ({"buffer": b64(make_pdf(2)), "password": ""}, ("buffer",), lambda r, _: pages(r) == 2),
        "EDIT": ({"buffer": b64(make_pdf(1)), "password": "",
                  "edits": [{"page": 0, "type": "text", "x": 10, "y": 10, "text": "Hello", "size": 14}]}, ("buffer",),
                 lambda r, _: "Hello" in text(r)),
        # Page 2's entry is an explicit null. The engine skips pages whose image
        # is None; a JS null that reached Python as pyodide's jsnull would slip
        # past that check and be decoded as an image, failing the whole action.
        "REDACT": ({"buffer": b64(make_line_pdf()), "password": "",
                    "pageImages": {"0": make_flat_page_png_base64(800, 600), "1": None}}, ("buffer",),
                   lambda r, _: SECRET not in text(r) and "Page 2. nothing sensitive here" in text(r)),
        "SIGN": ({"buffer": b64(make_pdf(1)), "password": "",
                  "signatures": [{"page": 0, "x": 5, "y": 5, "width": 40, "height": 20, "image": webp_signature()}]},
                 ("buffer",), lambda r, _: pages(r) == 1),
        # A JS null reaches Python as jsnull unless the worker converts it; the
        # engine's None checks would let jsnull through.
        "FILL_FORM": ({"buffer": b64(make_form_pdf()), "fields": {"name_field": "Ada", "subscribe_cb": None},
                       "flatten": False, "password": ""}, ("buffer",),
                      lambda r, _: (PdfReader(io.BytesIO(r)).get_fields() or {})["name_field"].get("/V") == "Ada"),
        "PROTECT": ({"buffer": b64(make_pdf(1)), "newPassword": "pw-123", "password": ""}, ("buffer",),
                    lambda r, _: PdfReader(io.BytesIO(r)).is_encrypted),
        "UNLOCK": (None, ("buffer",), lambda r, _: not PdfReader(io.BytesIO(r)).is_encrypted),
        "CHECK_REDACTION": ({"buffer": b64(make_line_pdf(draw=box(0, 0, 0))), "password": ""}, ("buffer",),
                            lambda r, _: json.loads(r)["hidden_text_found"] is True),
        "FILL_AND_SIGN": ({"buffer": b64(make_form_pdf()), "fields": {"name_field": "Ada"}, "edits": [], "flatten": True,
                           "signatures": [{"page": 0, "x": 5, "y": 5, "width": 40, "height": 20, "image": sig_png}],
                           "password": ""}, ("buffer",), lambda r, _: pages(r) == 1),
    }


def test_every_worker_action_is_covered_here():
    """A new action in pdf_worker.js without a browser test fails the build."""
    assert set(worker_cases()) == set(worker_actions())


def test_every_worker_action_runs_in_the_real_runtime(page, site_url):
    page.goto(site_url + "/index.html", wait_until="load")
    result = boot(page)
    assert "Installing Python packages" in " ".join(result["msgs"]), result
    # Detach the app's own handler so it doesn't try to download each result.
    page.evaluate("() => { worker.onmessage = null; }")

    cases = worker_cases()
    outputs, failures = {}, []
    order = [a for a in cases if a != "UNLOCK"] + ["UNLOCK"]
    for action in order:
        payload, binary, check = cases[action]
        if action == "UNLOCK":
            payload = {"buffer": b64(outputs["PROTECT"]), "password": "pw-123"}
        res = call(page, action, payload, binary)
        if not res["ok"]:
            failures.append(f"{action}: worker error: {res['error']}")
            continue
        outputs[action] = unb64(res["b64"])
        try:
            ok = check(outputs[action], outputs)
        except Exception as exc:
            ok, msg = False, f"{type(exc).__name__}: {exc}"
        else:
            msg = "output check failed"
        if not ok:
            failures.append(f"{action}: {msg}")
    assert not failures, "\n".join(failures)
    assert not page.context.page_errors


def test_wrong_password_reaches_the_page_as_a_clean_message(page, site_url):
    page.goto(site_url + "/index.html", wait_until="load")
    boot(page)
    page.evaluate("() => { worker.onmessage = null; }")
    res = call(page, "EXTRACT_TEXT", {"buffer": b64(make_encrypted_pdf(password="pw")), "password": "nope"})
    assert res == {"ok": False, "error": "Incorrect or missing password."}


def test_second_visit_boots_from_the_package_cache(page, site_url):
    page.goto(site_url + "/index.html", wait_until="load")
    boot(page)
    page.wait_for_function("""async () => {
        try { const d = await navigator.storage.getDirectory(); await d.getFileHandle('packages.bin'); return true; }
        catch { return false; } }""", timeout=120_000, polling=500)
    page.reload(wait_until="load")
    result = boot(page)
    assert "Packages ready (cached)" in " ".join(result["msgs"]), result
    page.evaluate("() => { worker.onmessage = null; }")
    # Pillow and cryptography are compiled; make sure the cached copies load.
    assert call(page, "COMPRESS", {"buffer": b64(make_pdf_with_raw_image()), "password": ""})["ok"]
    protected = call(page, "PROTECT", {"buffer": b64(make_pdf(1)), "newPassword": "pw", "password": ""})
    assert protected["ok"]
    assert call(page, "UNLOCK", {"buffer": protected["b64"], "password": "pw"})["ok"]
    sig = {"page": 0, "x": 5, "y": 5, "width": 40, "height": 20, "image": webp_signature()}
    assert call(page, "SIGN", {"buffer": b64(make_pdf(1)), "signatures": [sig], "password": ""})["ok"]


def test_engine_unit_suite_passes_inside_pyodide(page, site_url):
    """The whole engine suite, run by the WebAssembly builds the site uses,
    with exactly the packages the worker installs."""
    worker = read("assets/js/pdf_worker.js")
    version = re.search(r"const PYODIDE_VERSION = '([^']+)'", worker).group(1)
    pins = re.findall(r'"([^"]+)"', re.search(r"micropip\.install\(\[(.*?)\]", worker, re.S).group(1))
    page.goto(site_url + "/index.html", wait_until="load")
    summary = page.evaluate("""async ({ version, pins }) => {
        const { loadPyodide } = await import(`https://cdn.jsdelivr.net/pyodide/${version}/full/pyodide.mjs`);
        const py = await loadPyodide();
        await py.loadPackage('micropip');
        await py.pyimport('micropip').install(pins);
        py.FS.mkdirTree('/work/core');
        py.FS.writeFile('/work/core/pdf_engine.py', await (await fetch('/core/pdf_engine.py')).text());
        py.FS.writeFile('/work/test_engine.py', await (await fetch('/tests/test_engine.py')).text());
        return py.runPython(`
import io, json, sys, unittest
sys.path.insert(0, '/work')
res = unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromName('test_engine'))
json.dumps({'ran': res.testsRun, 'problems': [f"{t.id()}: {tb.strip().splitlines()[-1]}" for t, tb in res.failures + res.errors]})
`);
    }""", {"version": version, "pins": pins})
    summary = json.loads(summary)
    assert summary["ran"] > 100, summary
    assert not summary["problems"], "\n".join(summary["problems"])


# ── The UI ─────────────────────────────────────────────────────────────────

def test_page_loads_cleanly(page, site_url):
    failed = []
    page.on("requestfailed", lambda r: failed.append(r.url) if site_url in r.url else None)
    page.goto(site_url + "/index.html", wait_until="load")
    state = page.evaluate("""() => ({
        libs: [typeof pdfjsLib, typeof Sortable, typeof JSZip, typeof PDFLib],
        isolated: window.crossOriginIsolated,
        tools: Object.keys(TOOL_META).length,
        handlers: [typeof switchTab, typeof openTool, typeof openFeedback, typeof submitFeedback],
    })""")
    # Each CDN library has an SRI hash; a mismatch leaves it undefined.
    assert "undefined" not in state["libs"], state
    assert state["isolated"] is True
    assert state["tools"] == tool_count()
    assert "undefined" not in state["handlers"], state
    assert not failed, failed
    assert not page.context.page_errors


def test_redaction_checker(page, site_url):
    page.goto(site_url + "/index.html", wait_until="load")
    page.evaluate("() => { ensureWorker(); openTool('checkredact'); }")
    page.wait_for_function("() => isReady === true", timeout=BOOT_TIMEOUT_MS, polling=200)

    def check(name, data):
        page.set_input_files("#checkredact-upload", {"name": name, "mimeType": "application/pdf", "buffer": data})
        page.click("#checkredact-btn")
        page.wait_for_function("() => /^Done/.test(document.getElementById('checkredact-status').textContent)",
                               timeout=120_000)
        return page.evaluate("""() => ({
            verdict: document.querySelector('#checkredact-results .redaction-verdict strong').textContent,
            hits: [...document.querySelectorAll('#checkredact-results .redaction-hit')].map(e => e.textContent),
            injected: !!document.querySelector('#checkredact-results img'),
        })""")

    leak = check("leak.pdf", make_line_pdf(draw=box(0, 0, 0)))
    assert leak["verdict"].startswith("Hidden text found") and any(SECRET in h for h in leak["hits"]), leak
    assert check("clean.pdf", make_line_pdf())["verdict"] == "No hidden text found"
    hostile = check("x.pdf", make_line_pdf(draw=box(0, 0, 0), text='<img src=x onerror="window.__xss=1">'))
    assert hostile["injected"] is False and page.evaluate("() => window.__xss") is None


def test_feedback_falls_back_to_a_prefilled_github_issue(page, context, site_url):
    context.route("https://github.com/**", lambda route: route.abort())
    page.goto(site_url + "/index.html", wait_until="load")
    page.evaluate("() => openFeedback()")
    spinner_at_rest = page.evaluate(
        "() => getComputedStyle(document.getElementById('feedback-submit-spinner')).display")
    assert spinner_at_rest == "none", "the submit spinner is visible before anything was submitted"
    page.select_option("#feedback-type", "bug")
    page.fill("#feedback-message", 'Merge drops page 3 when "Apply" is pressed & held')
    with context.expect_page():
        page.click("#feedback-submit")
    href = page.get_attribute("#feedback-github-link", "href")
    assert href.startswith("https://github.com/kdigitalsystems/nilpdf/issues/new?"), href
    from urllib.parse import parse_qs, urlsplit
    q = parse_qs(urlsplit(href).query)
    assert q["title"][0].startswith("[Bug report] Merge drops page 3"), q
    assert q["labels"] == ["bug"]
    assert page.is_visible("#feedback-github-state")


def test_feedback_uses_the_relay_once_its_endpoint_is_stamped(page, context, site_url_with_relay, relay_endpoint):
    seen = []

    def relay(route):
        seen.append({"method": route.request.method, "headers": route.request.headers,
                     "body": json.loads(route.request.post_data)})
        route.fulfill(status=200, content_type="application/json", body='{"issue_number": 1}')

    context.route(relay_endpoint + "/**", relay)
    context.route(relay_endpoint, relay)
    page.goto(site_url_with_relay + "/index.html", wait_until="load")
    page.evaluate("() => openFeedback()")
    assert page.text_content("#feedback-submit-text").strip() == "Send Feedback"
    page.fill("#feedback-message", "works")
    page.click("#feedback-submit")
    page.wait_for_selector("#feedback-success-state", state="visible", timeout=30_000)
    assert len(seen) == 1 and seen[0]["method"] == "POST"
    assert seen[0]["body"] == {"type": "general", "name": "", "message": "works"}
    assert "authorization" not in {k.lower() for k in seen[0]["headers"]}


def test_app_still_works_offline_after_one_visit(page, context, site_url):
    page.goto(site_url + "/index.html", wait_until="load")
    page.wait_for_function("() => navigator.serviceWorker.controller !== null", timeout=60_000)
    page.wait_for_timeout(1500)  # let the install-time precache finish
    context.set_offline(True)
    try:
        page.reload(wait_until="load")
        state = page.evaluate("() => ({ tools: Object.keys(TOOL_META).length, ui: typeof switchTab })")
    finally:
        context.set_offline(False)
    assert state == {"tools": tool_count(), "ui": "function"}, state


def test_analytics_receives_only_the_tool_name(page, site_url):
    page.goto(site_url + "/index.html", wait_until="load")
    page.evaluate("() => { ensureWorker(); openTool('merge'); }")
    page.wait_for_function("() => isReady === true", timeout=BOOT_TIMEOUT_MS, polling=200)
    before = page.evaluate("() => window.dataLayer.length")
    page.set_input_files("#pdf-upload", [
        {"name": "contract-acme.pdf", "mimeType": "application/pdf", "buffer": make_pdf(2)},
        {"name": "nda-acme.pdf", "mimeType": "application/pdf", "buffer": make_pdf(1)},
    ])
    page.wait_for_function("() => !document.getElementById('merge-btn').disabled")
    with page.expect_download():
        page.click("#merge-btn")
    pushed = page.evaluate("""(n) => window.dataLayer.slice(n).map(a =>
        (a && typeof a.length === 'number' && !Array.isArray(a)) ? Array.from(a) : a)""", before)
    events = [e for e in pushed if isinstance(e, list) and e and e[0] == "event"]
    assert events == [["event", "tool_complete", {"tool": "merge"}]], pushed
    assert "acme" not in json.dumps(pushed), "a file name reached analytics"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
