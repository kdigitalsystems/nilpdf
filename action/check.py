"""The check step of the NilPDF GitHub Action (action.yml in the repository root).

Reads the action's inputs from NILPDF_* environment variables, checks the PDFs
with the nilpdf package the install step put in a private virtual environment,
and reports the result the way GitHub shows it: the step log, one annotation
per problem file, a job summary, and step outputs.

File names, error messages and the hidden text come from files that may be
untrusted, for example a pull request from a stranger. So:

- log lines are escaped with the CLI's _safe() and printed between
  ::stop-commands:: markers, so nothing in them can act as a workflow command;
- annotations use GitHub's workflow-command escaping;
- the job summary is HTML-escaped.

The hidden text itself is the information that leaked, and logs are kept for
months and readable by anyone with access to the repository. It is left out
of the log, annotations and summary unless show-text is true. The JSON report
written to the runner always has it.

Exit codes: 0 passed, 1 failed (hidden text or unreadable files, as the
fail-on-* inputs decide), 2 invalid inputs.
"""
import glob
import html
import json
import os
import secrets
import sys
import tempfile

from nilpdf import __version__
from nilpdf.cli import KIND_LABELS, _check_one, _collect, _safe

GLOB_CHARS = set("*?[")
MAX_SUMMARY_ROWS = 200
CHECKER_URL = "https://nilpdf.com/check-pdf-redaction/"


class InputError(Exception):
    pass


def flag(name):
    raw = os.environ.get(f"NILPDF_{name.upper().replace('-', '_')}", "")
    value = raw.strip().lower()
    if value in ("true", "false"):
        return value == "true"
    raise InputError(f"{name} must be true or false, not {raw!r}")


def expand(patterns):
    """Glob patterns become the PDFs and directories they match. A pattern
    that matches nothing is kept as typed, so it is reported as a missing
    file instead of being skipped without a word."""
    out = []
    for pattern in patterns:
        if GLOB_CHARS & set(pattern):
            matches = [m for m in sorted(glob.glob(pattern, recursive=True))
                       if os.path.isdir(m) or m.lower().endswith(".pdf")]
            out.extend(matches or [pattern])
        else:
            out.append(pattern)
    return list(dict.fromkeys(_collect(out)))


# ── GitHub's formats ─────────────────────────────────────────────────────────

def escape_data(text):
    return _safe(text).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def escape_property(text):
    return escape_data(text).replace(":", "%3A").replace(",", "%2C")


def annotate(level, title, message, file=None):
    props = {"title": title}
    if file:
        props["file"] = annotation_path(file)
    joined = ",".join(f"{k}={escape_property(v)}" for k, v in props.items())
    print(f"::{level} {joined}::{escape_data(message)}")


def annotation_path(path):
    """Annotations link to files by their path in the repository."""
    workspace = os.environ.get("GITHUB_WORKSPACE")
    if workspace and os.path.isabs(path):
        rel = os.path.relpath(path, workspace)
        if not rel.startswith(".."):
            return rel
    return path


def write_outputs(**values):
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        for key, value in values.items():
            f.write(f"{key}={value}\n")


# ── Describing results ───────────────────────────────────────────────────────

def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def finding_text(finding, show_text):
    text = finding.get("text") or ""
    if not text:
        return "(text under the mark)"
    return _safe(text) if show_text else plural(len(text), "character")


def describe_findings(result, show_text):
    """One short line per finding: where it is, what kind, and either the
    text or just its length."""
    lines = []
    for f in result.get("findings") or []:
        kind = KIND_LABELS.get(f.get("kind"), _safe(f.get("kind", "")))
        lines.append(f"page {_safe(f.get('page'))}, {kind}: {finding_text(f, show_text)}")
    return lines


def print_log(results, show_text):
    token = secrets.token_hex(16)
    print(f"::stop-commands::{token}")
    try:
        for r in results:
            path = _safe(r["path"])
            if "error" in r:
                print(f"ERROR   {path}: {_safe(r['error'])}")
            elif r.get("hidden_text_found"):
                print(f"HIDDEN  {path}: hidden text in {plural(len(r.get('findings') or []), 'place')}")
                for line in describe_findings(r, show_text):
                    print(f"  {line}")
            else:
                print(f"OK      {path}: no hidden text ({plural(r.get('pages') or 0, 'page')})")
    finally:
        print(f"::{token}::")


def summary_html(results, show_text, counts):
    checked, hidden, errors = counts

    def esc(text):
        return html.escape(_safe(text), quote=True)

    if hidden:
        verdict = f"**Hidden text found in {plural(hidden, 'file')}** of {checked} checked."
    elif errors:
        verdict = f"**No hidden text found, but {plural(errors, 'file')} could not be checked** ({checked} in total)."
    else:
        verdict = f"**No hidden text in {plural(checked, 'file')}.**"
    lines = ["### NilPDF redaction check", "", verdict, ""]

    problems = [r for r in results if "error" in r or r.get("hidden_text_found")]
    if problems:
        lines.append("<table><tr><th>File</th><th>Result</th><th>Details</th></tr>")
        for r in problems[:MAX_SUMMARY_ROWS]:
            if "error" in r:
                result, details = "Could not be checked", esc(r["error"])
            else:
                result, details = "Hidden text", "<br>".join(esc(line) for line in describe_findings(r, show_text))
            lines.append(f"<tr><td><code>{esc(r['path'])}</code></td><td>{result}</td><td>{details}</td></tr>")
        lines.append("</table>")
        if len(problems) > MAX_SUMMARY_ROWS:
            lines.append(f"\n…and {len(problems) - MAX_SUMMARY_ROWS} more. The JSON report lists every file.")
        lines.append("")
    if hidden and not show_text:
        lines.append("The hidden text isn't shown here, because it is the information that leaked and job logs "
                     "are kept. Set `show-text: true` to include it, or open the file in "
                     f"[NilPDF's redaction checker]({CHECKER_URL}), which runs in your browser without uploading it.")
    if hidden:
        lines.append("")
        lines.append("Drawing a box over text only covers it. Redact with a tool that removes the text, "
                     "then check the file again.")
    return "\n".join(lines) + "\n"


def write_summary(text):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)


def write_report(results, hidden):
    directory = os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()
    fd, path = tempfile.mkstemp(prefix="nilpdf-report-", suffix=".json", dir=directory)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"nilpdf_version": __version__, "hidden_text_found": bool(hidden), "files": results},
                  f, indent=2, ensure_ascii=False)
    return path


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    try:
        fail_on_hidden = flag("fail-on-hidden-text")
        fail_on_error = flag("fail-on-error")
        show_text = flag("show-text")
    except InputError as exc:
        annotate("error", "NilPDF: invalid input", str(exc))
        return 2

    patterns = [line.strip() for line in os.environ.get("NILPDF_PATHS", "").splitlines() if line.strip()]
    if not patterns:
        print("No paths given, so there is nothing to check.")
        write_outputs(**{"hidden-text-found": "false", "files-checked": 0,
                         "files-with-hidden-text": 0, "files-with-errors": 0, "report": ""})
        return 0

    files = expand(patterns)
    if files:
        password = os.environ.get("NILPDF_PASSWORD", "")
        results = [_check_one(f, password) for f in files]
    else:
        results = [{"path": ", ".join(patterns), "error": "no PDF files found"}]
    hidden = sum(1 for r in results if r.get("hidden_text_found"))
    errors = sum(1 for r in results if "error" in r)
    checked = len(files)

    print_log(results, show_text)
    for r in results:
        if "error" in r:
            annotate("error" if fail_on_error else "warning", "PDF could not be checked",
                     f"{r['path']}: {r['error']}", file=r["path"] if files else None)
        elif r.get("hidden_text_found"):
            found = describe_findings(r, show_text)
            annotate("error" if fail_on_hidden else "warning", "Hidden text in PDF",
                     f"Hidden text in {plural(len(found), 'place')}: " + "; ".join(found), file=r["path"])

    report = write_report(results, hidden)
    write_summary(summary_html(results, show_text, (checked, hidden, errors)))
    write_outputs(**{"hidden-text-found": "true" if hidden else "false", "files-checked": checked,
                     "files-with-hidden-text": hidden, "files-with-errors": errors, "report": report})

    failed = (hidden and fail_on_hidden) or (errors and fail_on_error)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
