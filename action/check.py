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

Two inputs narrow what is checked, so a repository that already has PDFs can
adopt the check. Both are visible in the log, the summary and the report:

- exclude names files to skip: known false positives, or an archive.
- changed-only skips the PDFs git confirms are unchanged since the commit the
  run is compared with. Anything git can't vouch for is checked, and if the
  comparison can't be made at all, every file is.

Exit codes: 0 passed, 1 failed (hidden text or unreadable files, as the
fail-on-* inputs decide), 2 invalid inputs.
"""
import glob
import html
import json
import os
import re
import secrets
import subprocess
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


def lines_of(variable):
    """A multi-line input, one entry per line."""
    return [line.strip() for line in os.environ.get(variable, "").splitlines() if line.strip()]


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


# ── exclude ──────────────────────────────────────────────────────────────────

def exclude_regex(pattern):
    """A glob pattern as a regular expression over a file's path relative to
    the working directory. * and ? stay within one path segment and ** spans
    them, as in the paths input. A pattern that matches a directory covers
    everything inside it, so `archive` and `archive/` exclude the whole tree."""
    pattern = pattern.strip()
    if os.path.isabs(pattern):   # such as ${{ github.workspace }}/archive
        pattern = os.path.relpath(pattern)
    while pattern.startswith("./"):
        pattern = pattern[2:]
    pattern = pattern.rstrip("/")
    out, i = [], 0
    while i < len(pattern):
        ch = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif ch == "*":
            out.append("[^/]*")
            i += 1
        elif ch == "?":
            out.append("[^/]")
            i += 1
        elif ch == "[" and "]" in pattern[i + 2:]:
            end = pattern.index("]", i + 2)
            body = pattern[i + 1:end]
            negate = body[0] in "!^"
            out.append("[" + ("^/" if negate else "") + re.escape(body[negate:]).replace("\\-", "-") + "]")
            i = end + 1
        else:
            out.append(re.escape(ch))
            i += 1
    return re.compile("".join(out) + "(?:/.*)?")


def relative_path(path):
    """A file's path as exclude patterns see it: relative to the working
    directory, with forward slashes."""
    return os.path.relpath(os.path.abspath(path)).replace(os.sep, "/")


# ── changed-only ─────────────────────────────────────────────────────────────

class ChangedOnlyUnavailable(Exception):
    """git can't say what changed, so every file gets checked. `level` is how
    loudly to say so: a notice when there is simply nothing to compare with,
    a warning when the comparison was expected to work."""

    def __init__(self, reason, level="warning"):
        super().__init__(reason)
        self.level = level


def base_commit():
    """The commit this run is compared with, from the event that started it:
    a pull request's base, a merge queue's base, or the commit a push
    replaced. None when there isn't one, such as a manual or scheduled run or
    the first push of a branch. It ends up on a git command line, so anything
    but a full hexadecimal commit ID is refused."""
    try:
        with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
            event = json.load(f)
    except (KeyError, OSError, ValueError):
        return None
    for keys in (("pull_request", "base", "sha"), ("merge_group", "base_sha"), ("before",)):
        node = event
        for key in keys:
            node = node.get(key) if isinstance(node, dict) else None
        if isinstance(node, str) and re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", node) and set(node) != {"0"}:
            return node
    return None


class Git:
    """Runs git in the checkout the working directory is in.

    In a container job the checkout belongs to a different user than the one
    running the job, and git then refuses to read it ("dubious ownership").
    actions/checkout only lifts that for its own commands. So these commands
    get their own global config: it includes the user's, and adds a line that
    trusts the checkout. Nothing outside this process is changed, and git is
    told not to take locks, since it only reads here."""

    def __init__(self, scratch):
        config = os.path.join(scratch, "gitconfig")
        home = os.path.expanduser("~")
        if os.environ.get("GIT_CONFIG_GLOBAL"):
            originals = [os.environ["GIT_CONFIG_GLOBAL"]]
        else:
            xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")
            originals = [os.path.join(xdg, "git", "config"), os.path.join(home, ".gitconfig")]
        with open(config, "w", encoding="utf-8", errors="surrogateescape") as out:
            for original in originals:   # git skips an include that doesn't exist
                quoted = original.replace("\\", "\\\\").replace('"', '\\"')
                out.write(f'[include]\n\tpath = "{quoted}"\n')
            out.write("[safe]\n\tdirectory = *\n")
        self.env = {**os.environ, "GIT_CONFIG_GLOBAL": config, "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}
        self.top = None

    def run(self, *args):
        try:
            done = subprocess.run(["git", *args], cwd=self.top, env=self.env, capture_output=True, timeout=300)
        except FileNotFoundError:
            raise ChangedOnlyUnavailable("git is not installed on this runner") from None
        except subprocess.TimeoutExpired:
            raise ChangedOnlyUnavailable(f"git {args[0]} did not finish in five minutes") from None
        return done.returncode, done.stdout.decode("utf-8", "surrogateescape")

    def paths(self, *args):
        """The NUL-separated paths a command prints, relative to the top of
        the checkout."""
        code, out = self.run(*args)
        if code != 0:
            raise ChangedOnlyUnavailable(f"git {args[0]} failed")
        return {p for p in out.split("\0") if p}


def unchanged_since_base(files, scratch):
    """Which of `files` git confirms are unchanged since the base commit.

    A file is only skipped if all three hold: it is tracked in the
    checked-out commit, no commit since the base touched it, and the copy in
    the workspace hasn't been modified. So files a build step generated,
    untracked files and edited files are all still checked. Comparing the two
    commits directly, rather than from where the branches forked, can only
    add files to the changed set, never drop one the pull request touched.

    Returns (unchanged files, base commit). Raises ChangedOnlyUnavailable
    when the comparison can't be made."""
    base = base_commit()
    if not base:
        raise ChangedOnlyUnavailable("this run has no earlier commit to compare with", level="notice")
    git = Git(scratch)
    code, top = git.run("rev-parse", "--show-toplevel")
    if code != 0:
        raise ChangedOnlyUnavailable("the working directory is not a git checkout that git can read")
    git.top = top.rstrip("\n")
    code, head = git.run("rev-parse", "--verify", "HEAD^{commit}")
    if code != 0:
        raise ChangedOnlyUnavailable("the checkout has no commit checked out")
    if head.strip() == base:
        raise ChangedOnlyUnavailable(
            "the checked-out commit is the one to compare with, so there are no changes to find. "
            "On pull_request_target, the default checkout is the base branch, not the pull request")
    if git.run("cat-file", "-e", base + "^{commit}")[0] != 0:
        # actions/checkout fetches a single commit by default, so the base is
        # usually missing. One more commit is enough. --depth is only used in
        # a checkout that is already shallow: in a complete one it would mark
        # the repository shallow, which later steps might not expect.
        shallow = git.run("rev-parse", "--is-shallow-repository")[1].strip() == "true"
        git.run("fetch", "--quiet", "--no-tags", *(["--depth=1"] if shallow else []), "origin", base)
        if git.run("cat-file", "-e", base + "^{commit}")[0] != 0:
            raise ChangedOnlyUnavailable(
                f"the commit to compare with ({base[:7]}) is not in the checkout and could not be fetched. "
                "Give actions/checkout fetch-depth: 0, or let it keep its credentials")
    tracked = git.paths("ls-tree", "-r", "-z", "--name-only", "--full-tree", "HEAD")
    touched = git.paths("diff", "--name-only", "--no-renames", "--no-ext-diff", "-z", base, "HEAD")
    touched |= git.paths("diff", "--name-only", "--no-renames", "--no-ext-diff", "-z", "HEAD")
    vouched = tracked - touched
    top = os.path.realpath(git.top)
    unchanged = [f for f in files
                 if os.path.relpath(os.path.realpath(f), top).replace(os.sep, "/") in vouched]
    return unchanged, base


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


def skipped_notes(skipped):
    """One sentence for each reason files were left out, so a narrowed check
    never looks like a full one."""
    notes = []
    if skipped["unchanged"]:
        n = len(skipped["unchanged"])
        notes.append(f"{plural(n, 'PDF')} unchanged since commit {skipped['base'][:7]} "
                     f"{'was' if n == 1 else 'were'} not checked (changed-only).")
    if skipped["excluded"]:
        n = len(skipped["excluded"])
        notes.append(f"{plural(n, 'PDF')} matching exclude {'was' if n == 1 else 'were'} not checked.")
    return notes


def summary_html(results, show_text, counts, skipped):
    checked, hidden, errors = counts

    def esc(text):
        return html.escape(_safe(text), quote=True)

    if hidden:
        verdict = f"**Hidden text found in {plural(hidden, 'file')}** of {checked} checked."
    elif errors:
        verdict = f"**No hidden text found, but {plural(errors, 'file')} could not be checked** ({checked} in total)."
    elif not checked:
        verdict = "**No PDFs needed checking.**"
    else:
        verdict = f"**No hidden text in {plural(checked, 'file')}.**"
    lines = ["### NilPDF redaction check", "", verdict, ""]
    notes = skipped_notes(skipped)
    if notes:
        lines += [" ".join(notes) + " The JSON report lists them.", ""]

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


def write_report(results, hidden, skipped):
    directory = os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()
    fd, path = tempfile.mkstemp(prefix="nilpdf-report-", suffix=".json", dir=directory)
    with os.fdopen(fd, "w", encoding="utf-8", errors="backslashreplace") as f:
        json.dump({"nilpdf_version": __version__, "hidden_text_found": bool(hidden), "files": results,
                   "skipped": {"excluded": skipped["excluded"], "unchanged": skipped["unchanged"],
                               "compared_with": skipped["base"]}},
                  f, indent=2, ensure_ascii=False)
    return path


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    try:
        fail_on_hidden = flag("fail-on-hidden-text")
        fail_on_error = flag("fail-on-error")
        show_text = flag("show-text")
        changed_only = flag("changed-only")
    except InputError as exc:
        annotate("error", "NilPDF: invalid input", str(exc))
        return 2

    patterns = lines_of("NILPDF_PATHS")
    if not patterns:
        print("No paths given, so there is nothing to check.")
        write_outputs(**{"hidden-text-found": "false", "files-checked": 0, "files-skipped": 0,
                         "files-with-hidden-text": 0, "files-with-errors": 0, "report": ""})
        return 0

    found = expand(patterns)
    # Only files that exist can be skipped. A path that doesn't exist stays
    # in, so it is still reported as an error.
    skippable = [f for f in found if os.path.isfile(f)]
    skipped = {"excluded": [], "unchanged": [], "base": None}

    excludes = [exclude_regex(pattern) for pattern in lines_of("NILPDF_EXCLUDE")]
    if excludes:
        skipped["excluded"] = [f for f in skippable if any(rx.fullmatch(relative_path(f)) for rx in excludes)]
        excluded = set(skipped["excluded"])
        skippable = [f for f in skippable if f not in excluded]

    if changed_only and skippable:
        with tempfile.TemporaryDirectory(prefix="nilpdf-git-", dir=os.environ.get("RUNNER_TEMP") or None) as scratch:
            try:
                skipped["unchanged"], skipped["base"] = unchanged_since_base(skippable, scratch)
            except ChangedOnlyUnavailable as exc:
                annotate(exc.level, "changed-only: every PDF was checked",
                         f"changed-only could not narrow the check, because {exc}. Every PDF in paths was checked.")

    left_out = set(skipped["excluded"]) | set(skipped["unchanged"])
    files = [f for f in found if f not in left_out]
    if files:
        password = os.environ.get("NILPDF_PASSWORD", "")
        results = [_check_one(f, password) for f in files]
    elif found:
        results = []
    else:
        results = [{"path": ", ".join(patterns), "error": "no PDF files found"}]
    hidden = sum(1 for r in results if r.get("hidden_text_found"))
    errors = sum(1 for r in results if "error" in r)
    checked = len(files)

    print_log(results, show_text)
    for note in skipped_notes(skipped):
        print(note)
    for r in results:
        if "error" in r:
            annotate("error" if fail_on_error else "warning", "PDF could not be checked",
                     f"{r['path']}: {r['error']}", file=r["path"] if files else None)
        elif r.get("hidden_text_found"):
            found = describe_findings(r, show_text)
            annotate("error" if fail_on_hidden else "warning", "Hidden text in PDF",
                     f"Hidden text in {plural(len(found), 'place')}: " + "; ".join(found), file=r["path"])

    report = write_report(results, hidden, skipped)
    write_summary(summary_html(results, show_text, (checked, hidden, errors), skipped))
    write_outputs(**{"hidden-text-found": "true" if hidden else "false", "files-checked": checked,
                     "files-skipped": len(left_out), "files-with-hidden-text": hidden,
                     "files-with-errors": errors, "report": report})

    failed = (hidden and fail_on_hidden) or (errors and fail_on_error)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
