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
- The NilPDF web application (`index.html`, `assets/js/pdf_worker.js`, `core/pdf_engine.py`)
- The CI/CD deployment pipeline (`.github/workflows/`)

Out of scope:
- Third-party libraries themselves (pdf.js, Pyodide, pypdf, reportlab, Pillow)
  — please report upstream to those projects as well if relevant.
- The hosting provider's own infrastructure (GitHub Pages).

## Known limitations

- No formal third-party security audit has been performed.
- A Content-Security-Policy header restricting script sources is not yet deployed.
- Password-protected PDFs are decrypted in-browser, in memory; the password is
  never transmitted, but it is held in JS memory for the duration of processing.
