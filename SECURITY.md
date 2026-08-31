# Security Policy

NilPDF processes PDF files entirely inside the user's browser, using Python
compiled to WebAssembly (Pyodide). There is no backend service capable of
receiving uploaded document contents — the application has no server-side
code path for accepting a file. See [nilpdf.com/security](https://nilpdf.com/security/)
for the full architecture writeup, including how to verify local processing
yourself using browser developer tools.

## Supported versions

NilPDF is a single continuously-deployed static site — there are no
historical versions to track. Security fixes are applied to `main` and
deployed on merge.

## Reporting a vulnerability

If you discover a security issue (for example, a code path that would cause
document data to be transmitted anywhere, an XSS vector, or a dependency with
a known exploitable vulnerability), please report it privately rather than
opening a public issue:

- Use the feedback form on [nilpdf.com](https://nilpdf.com/) and select "Bug report."
- Please include enough detail to reproduce the issue and, if applicable, a
  minimal test PDF that triggers it (redact any sensitive content first).

Please avoid publicly disclosing a vulnerability until it has been addressed.

## Scope

In scope:
- The NilPDF web application (`index.html`, `assets/js/app.js`,
  `assets/js/pdf_worker.js`, `core/pdf_engine.py`)
- The feedback relay Worker (`feedback-worker/`)
- The CI/CD deployment pipeline (`.github/workflows/`)

Out of scope:
- Third-party libraries themselves (pdf.js, Pyodide, pypdf, reportlab, Pillow)
  — please report upstream to those projects as well if relevant.
- The hosting provider's own infrastructure (GitHub Pages).

## Subresource integrity

Because every PDF is processed by code running in your browser, that code is the
security boundary. A tampered script would be able to read a document you opened,
regardless of the fact that nothing is uploaded. The third-party libraries the app
depends on therefore matter as much as our own code.

**Verified.** The four cdnjs `<script>` tags in `index.html` (pdf.js, Sortable,
jszip, pdf-lib) carry SHA-384 `integrity` hashes. If the CDN serves altered bytes
for any of them, the browser refuses to execute the file and the tool fails
closed rather than running modified code.

**Not verified, and why.** Two loads have no integrity check available to them:

- **The pdf.js worker** (`pdf.worker.min.js`). pdf.js starts this itself through
  the `Worker` constructor, which accepts no integrity attribute. It is pinned to
  the same version as the verified `pdf.min.js`.
- **Pyodide and the Python wheels.** The runtime is loaded with `importScripts()`
  in `assets/js/pdf_worker.js`, and `importScripts` has no SRI equivalent. Even
  with one, Pyodide then fetches its own `.wasm` payload and the package wheels
  without verifying them, so hashing only the loader would give a misleading
  impression of coverage. Package versions are pinned (see `requirements.txt`),
  which makes the download reproducible but does not authenticate it.

Closing the second gap means self-hosting the Pyodide distribution and the wheels
from this origin, where they would be covered by the same TLS and hosting trust as
the rest of the site. That is a deliberate, tested change rather than a
configuration tweak, and it has not been made yet.

## Credential handling

The deployed site contains no credentials, and the deploy pipeline is not permitted
to introduce any: everything written into a static site is served to visitors, so a
token in the page would be a published token. The GitHub token used by the in-app
feedback form is held by the Cloudflare Worker in `feedback-worker/`, which the
browser calls without authenticating.

This is enforced, not just documented — `tests/test_no_client_secrets.py` fails the
build if a token literal, an `Authorization` header, a direct GitHub API call, or a
`${{ secrets.* }}` reference appears anywhere in the client files or the deploy job.

## Known limitations

- No formal third-party security audit has been performed.
- A Content-Security-Policy is not yet deployed. GitHub Pages does not allow
  custom response headers, so it would have to be a `<meta http-equiv>` policy;
  the app also uses inline `onclick=` handlers throughout its markup, so any
  such policy would need `script-src 'unsafe-inline'` until those are converted
  to attached listeners. A `connect-src` restriction would still be worthwhile
  on its own and is the most likely next step.
- Integrity is not verified for the Pyodide runtime or its wheels. See
  "Subresource integrity" above.
- Password-protected PDFs are decrypted in-browser, in memory; the password is
  never transmitted, but it is held in JS memory for the duration of processing.
