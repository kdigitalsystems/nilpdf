"""Stamp deploy-time values into the site, in place. Run by the deploy job.

    python3 scripts/stamp_build.py --sha "$COMMIT_SHA" [--endpoint URL] [--root DIR]

Replaces three placeholders:

  __BUILD_VERSION__     index.html (CSS link, app.js script tag) and
                        assets/js/app.js (version const, pdf_worker.js URL).
                        Changes on every deploy, so browsers fetch fresh assets.
  __SW_VERSION__        sw.js cache name. A new name makes the service worker
                        drop the previous deploy's cache.
  __FEEDBACK_ENDPOINT__ assets/js/app.js, only when an endpoint is given: the
                        public URL of the Cloudflare Worker in feedback-worker/,
                        which holds the GitHub token. Without it the feedback
                        form falls back to a pre-filled GitHub issue.

No credential is ever stamped. Everything written into the site is served to
browsers and is therefore public; a token in the page would be a published
token. This used to be inline Python in the deploy workflow, where it couldn't
be tested, and a bug in exactly this kind of replacement disabled the
production feedback form for months. tests/test_stamp_build.py runs this file.

Exits non-zero, and changes nothing, if any placeholder is missing or an input
is malformed: a deploy that half-stamps is worse than one that stops.
"""
import argparse
import datetime
import os
import re
import sys

STAMPS = {
    "__BUILD_VERSION__": ("index.html", "assets/js/app.js"),
    "__SW_VERSION__": ("sw.js",),
}
ENDPOINT_PLACEHOLDER = "__FEEDBACK_ENDPOINT__"
ENDPOINT_FILE = "assets/js/app.js"


def stamp(root, sha, endpoint="", date=None):
    """Return {path: new_text} for every file that changes. Raises ValueError
    on bad input or a missing placeholder, before anything is written."""
    if not re.fullmatch(r"[0-9a-f]{7,40}", sha or ""):
        raise ValueError(f"--sha must be a hex commit id, got {sha!r}")
    endpoint = (endpoint or "").strip()
    if endpoint and not endpoint.startswith("https://"):
        # app.js only treats an https:// value as configured; anything else
        # would silently fall back to the GitHub-issue path.
        raise ValueError(f"the feedback endpoint must be an https:// URL, got {endpoint!r}")

    short = sha[:7]
    date = date or datetime.date.today().isoformat()
    values = {"__BUILD_VERSION__": f"{short} {date}", "__SW_VERSION__": short}
    if endpoint:
        values[ENDPOINT_PLACEHOLDER] = endpoint

    texts = {}
    for placeholder, paths in {**STAMPS, **({ENDPOINT_PLACEHOLDER: (ENDPOINT_FILE,)} if endpoint else {})}.items():
        for rel in paths:
            if rel not in texts:
                with open(os.path.join(root, rel), encoding="utf-8") as f:
                    texts[rel] = f.read()
            if placeholder not in texts[rel]:
                raise ValueError(f"{placeholder} placeholder not found in {rel}")
            texts[rel] = texts[rel].replace(placeholder, values[placeholder])
    return texts


def main(argv=None):
    parser = argparse.ArgumentParser(description="Stamp deploy-time values into the site.")
    parser.add_argument("--root", default=".", help="site root (default: current directory)")
    parser.add_argument("--sha", default=os.environ.get("COMMIT_SHA", ""), help="commit id (default: $COMMIT_SHA)")
    parser.add_argument("--endpoint", default=os.environ.get("FEEDBACK_ENDPOINT", ""),
                        help="feedback relay URL (default: $FEEDBACK_ENDPOINT)")
    parser.add_argument("--date", default=None, help="build date, YYYY-MM-DD (default: today)")
    args = parser.parse_args(argv)
    try:
        texts = stamp(args.root, args.sha, args.endpoint, args.date)
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    for rel, text in texts.items():
        with open(os.path.join(args.root, rel), "w", encoding="utf-8") as f:
            f.write(text)
        print(f"stamped {rel}")
    if not args.endpoint.strip():
        print("note: FEEDBACK_ENDPOINT is not set, so feedback uses the pre-filled GitHub issue fallback.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
