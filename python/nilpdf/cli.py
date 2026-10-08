"""The ``nilpdf`` command line tool.

``nilpdf check-redaction`` reports text that is still in a PDF but hidden from
view: under black boxes, white-out or pasted images, under redaction marks
that were never applied, or in an earlier saved version of the file.

Exit codes are the contract CI pipelines and pre-commit hooks rely on:

    0  every file was checked and none has hidden text
    1  at least one file has hidden text
    2  no hidden text was found, but a file could not be checked
       (unreadable, not a PDF, wrong password), or the arguments were wrong
"""
import argparse
import json
import logging
import sys
import unicodedata
from pathlib import Path

from . import __version__, check_redaction

EXIT_CLEAN = 0
EXIT_HIDDEN = 1
EXIT_ERROR = 2

KIND_LABELS = {
    "covered_text": "hidden under a box",
    "unapplied_redaction": "redaction not applied",
    "earlier_revision": "in an earlier saved version",
}

CHECK_DESCRIPTION = """\
Report text that is still in a PDF but hidden from view. A black box drawn
over text only covers it: the text stays in the file, where copy, search and
extraction can still find it. This checks every page for text under opaque
shapes or images, redaction marks that were never applied, and text kept in
earlier saved versions of the file. It needs only the redacted file.

Everything runs locally. No file is uploaded and no network request is made."""

CHECK_EPILOG = """\
exit codes:
  0  no hidden text in any file
  1  hidden text found in at least one file
  2  a file could not be checked, or bad arguments

limitations:
  Text that was never in the file as text, such as a scanned page with a
  black bar burned into the image, can't be checked this way. Positions are
  estimated from average character widths, so a reported phrase can include a
  neighbouring word or miss one at the edge of a box.

examples:
  nilpdf check-redaction filing.pdf
  nilpdf check-redaction docs/                 # every PDF under docs/
  nilpdf check-redaction --json out/*.pdf > report.json
  curl -s https://example.com/doc.pdf | nilpdf check-redaction -"""


def _safe(text):
    """Make text from a PDF safe to print to a terminal.

    Hidden text, document properties and file names come from untrusted
    files. Control and formatting characters are escaped, so a crafted PDF
    can't send terminal escape sequences, break a report line with a newline,
    or reverse the displayed direction of text with bidi overrides.
    """
    out = []
    for ch in str(text):
        if unicodedata.category(ch)[0] == "C":
            out.append(f"\\x{ord(ch):02x}" if ord(ch) <= 0xFF else f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    return "".join(out)


def _collect(paths):
    """Expand directories to the PDFs inside them, searched recursively.
    ``-`` means standard input. Explicit file paths are kept as given, so a
    missing or misnamed file is reported rather than silently skipped."""
    files = []
    for raw in paths:
        p = Path(raw)
        if raw != "-" and p.is_dir():
            files.extend(str(f) for f in sorted(p.rglob("*")) if f.is_file() and f.suffix.lower() == ".pdf")
        else:
            files.append(raw)
    return files


def _describe_error(exc):
    msg = str(exc).strip() or type(exc).__name__
    if "Incorrect password" in msg:
        return "wrong or missing password (use --password)"
    try:
        from pypdf.errors import PdfReadError
    except ImportError:  # pragma: no cover - pypdf is a hard dependency
        PdfReadError = ()
    if isinstance(exc, PdfReadError):
        return f"not a readable PDF ({msg})"
    return f"could not be checked ({type(exc).__name__}: {msg})"


def _check_one(path, password):
    label = "<stdin>" if path == "-" else path
    try:
        data = sys.stdin.buffer.read() if path == "-" else Path(path).read_bytes()
    except OSError as exc:
        return {"path": label, "error": f"cannot read file ({exc.strerror or exc})"}
    # PDFs may carry junk before the header, but readers only look in the first 1 KB.
    if b"%PDF-" not in data[:1024]:
        return {"path": label, "error": "not a PDF file (no PDF header)"}
    try:
        report = check_redaction(data, password=password)
    except Exception as exc:  # malformed PDFs raise many unrelated exception types
        return {"path": label, "error": _describe_error(exc)}
    return {"path": label, **report}


def _print_result(result, verbose):
    path = _safe(result["path"])
    if "error" in result:
        print(f"ERROR   {path}: {result['error']}")
        return
    findings = result.get("findings") or []
    if result.get("hidden_text_found"):
        n = len(findings)
        print(f"HIDDEN  {path}: hidden text in {n} place{'' if n == 1 else 's'}")
        for f in findings:
            label = KIND_LABELS.get(f.get("kind"), _safe(f.get("kind", "")))
            text = _safe(f.get("text") or "(text under the mark)")
            print(f"  page {f.get('page')}, {label}: {text}")
            print(f"    {_safe(f.get('detail', ''))}")
    else:
        pages = result.get("pages")
        print(f"OK      {path}: no hidden text ({pages} page{'' if pages == 1 else 's'})")
    invisible = result.get("invisible_text_pages") or []
    if invisible:
        pages = ", ".join(str(p) for p in invisible)
        print(f"  note: page(s) {pages} carry an invisible text layer, typical of scanned documents with OCR. "
              "Words blacked out in the scan itself may still be in it.")
    if verbose:
        for key, value in (result.get("metadata") or {}).items():
            print(f"  property {key}: {_safe(value)}")


def _run_check(args):
    files = _collect(args.paths)
    if not files:
        print("nilpdf: no PDF files found in the given paths", file=sys.stderr)
        return EXIT_ERROR
    if files.count("-") > 1:
        print("nilpdf: '-' (standard input) can only be given once", file=sys.stderr)
        return EXIT_ERROR

    results = [_check_one(f, args.password) for f in files]
    hidden = sum(1 for r in results if r.get("hidden_text_found"))
    errors = sum(1 for r in results if "error" in r)
    clean = len(results) - hidden - errors

    if args.json:
        json.dump({"nilpdf_version": __version__, "hidden_text_found": bool(hidden), "files": results},
                  sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        for r in results:
            _print_result(r, args.verbose)
        if len(results) > 1:
            parts = [f"{hidden} with hidden text", f"{clean} clean"]
            if errors:
                parts.append(f"{errors} could not be checked")
            print(f"\nChecked {len(results)} files: {', '.join(parts)}.")

    if hidden:
        return EXIT_HIDDEN
    return EXIT_ERROR if errors else EXIT_CLEAN


def build_parser():
    parser = argparse.ArgumentParser(
        prog="nilpdf",
        description="PDF tools that keep your files on your machine. https://nilpdf.com",
    )
    parser.add_argument("--version", action="version", version=f"nilpdf {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")

    check = commands.add_parser(
        "check-redaction",
        help="find text still hiding in a redacted PDF",
        description=CHECK_DESCRIPTION,
        epilog=CHECK_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    check.add_argument("paths", nargs="+", metavar="PATH",
                       help="PDF files, or directories to search recursively. Use - to read from standard input.")
    check.add_argument("--password", default="", help="password for encrypted PDFs, used for every file")
    check.add_argument("--json", action="store_true", help="print one JSON report instead of text")
    check.add_argument("-v", "--verbose", action="store_true",
                       help="also list document properties such as title and author, which can reveal information too")
    return parser


def main(argv=None):
    # Hidden text can be any Unicode. Never crash on a terminal or pipe that
    # can't encode it; escape what it can't show instead.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")

    # pypdf logs a warning for every irregularity it repairs while parsing, and
    # real-world PDFs have plenty. Those warnings arrive on stderr out of order
    # with the report and bury it in CI logs. Errors still surface through the
    # report itself. (Only the CLI does this; the library leaves the caller's
    # logging alone.)
    logging.getLogger("pypdf").setLevel(logging.ERROR)

    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help(sys.stderr)
        return EXIT_ERROR
    return _run_check(args)
