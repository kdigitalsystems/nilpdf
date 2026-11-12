#!/usr/bin/env python3
"""Publish a tagged version on GitHub: create its Release, attach the built
package, and move the major-version tag to it.

The release workflow (.github/workflows/release.yml) runs this once a tag has
passed its checks. It does three things, and every one can be repeated safely,
so a failed run can simply be run again:

1. Creates the GitHub Release for the tag, unless it already exists. A
   Release is what GitHub Marketplace lists, and what people see under
   "Releases" when they decide whether a project is alive.
2. Attaches the wheel and the source archive, skipping any already there, so
   the package can be installed straight from GitHub.
3. Moves the major-version tag (v0 for 0.x.y) to the release, so workflows
   that say `uses: kdigitalsystems/nilpdf@v0` pick up fixes, such as a patched
   PDF library, without anyone editing them. It only moves forward: releasing
   an older tag again leaves it alone.

    GITHUB_TOKEN=... python3 scripts/github_release.py \\
        --repo kdigitalsystems/nilpdf --tag v0.3.0 --commit <sha> --dist dist/

The token needs `contents: write`. It is only ever sent in the Authorization
header, and never printed.

tests/test_github_release.py runs this against a stand-in for GitHub's API.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

VERSION_TAG = re.compile(r"v(\d+)\.(\d+)\.(\d+)")
COMMIT = re.compile(r"[0-9a-f]{40}")


class ReleaseError(Exception):
    pass


class GitHub:
    def __init__(self, api_url, repo, token):
        self.base = f"{api_url.rstrip('/')}/repos/{repo}"
        self.token = token

    def request(self, method, url, body=None, content_type="application/json", ok=(200, 201)):
        """Returns (status, parsed JSON). A status in `ok` or 404/422 comes
        back to the caller, which decides what it means; anything else is an
        error."""
        if not url.startswith("http"):
            url = self.base + url
        data = body if isinstance(body, bytes) or body is None else json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "nilpdf-release",
            **({"Content-Type": content_type} if data is not None else {}),
        })
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                status, raw = resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            status, raw = exc.code, exc.read()
        except urllib.error.URLError as exc:
            raise ReleaseError(f"{method} {url}: {exc.reason}") from None
        try:
            parsed = json.loads(raw) if raw else None
        except ValueError:
            parsed = None
        if status not in ok and status not in (404, 422):
            message = parsed.get("message") if isinstance(parsed, dict) else None
            raise ReleaseError(f"{method} {url}: HTTP {status}{': ' + str(message) if message else ''}")
        return status, parsed


def parse_version(tag):
    m = VERSION_TAG.fullmatch(tag)
    return tuple(int(part) for part in m.groups()) if m else None


def released_versions(gh, major):
    """Every vMAJOR.x.y tag in the repository, as version tuples."""
    status, refs = gh.request("GET", f"/git/matching-refs/tags/v{major}.")
    if status != 200:
        raise ReleaseError(f"could not list the v{major}.x.y tags: HTTP {status}")
    found = (parse_version(ref["ref"].removeprefix("refs/tags/")) for ref in refs)
    return [v for v in found if v and v[0] == major]


def release_notes(repo, tag, version, wheel):
    """What goes above GitHub's generated list of changes: how to use this
    version, since that is what someone landing on the page wants."""
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    lines = [
        'Find text still hiding in a "redacted" PDF. Everything runs on your own machine or runner; '
        "no file is uploaded.",
        "",
        "**In GitHub Actions**",
        "",
        "```yaml",
        f"- uses: {repo}@{tag}   # or @v{version[0]} for the newest {version[0]}.x",
        "  with:",
        "    paths: published/",
        "```",
        "",
    ]
    if wheel:
        lines += [
            "**On the command line** (Python 3.10 or newer)",
            "",
            "```bash",
            f"pip install {server}/{repo}/releases/download/{tag}/{urllib.parse.quote(wheel)}",
            "nilpdf check-redaction filing.pdf",
            "```",
            "",
        ]
    lines += [f"[Documentation]({server}/{repo}/tree/{tag}#github-action)", ""]
    return "\n".join(lines)


def ensure_release(gh, repo, tag, version, newest, wheel):
    status, release = gh.request("GET", f"/releases/tags/{tag}")
    if status == 200:
        print(f"Release {tag} already exists.")
        return release
    status, release = gh.request("POST", "/releases", {
        "tag_name": tag,
        "name": f"nilpdf {'.'.join(map(str, version))}",
        "body": release_notes(repo, tag, version, wheel),
        "generate_release_notes": True,
        # Publishing an older version again must not make it "Latest".
        "make_latest": "true" if newest else "false",
    })
    if status != 201:
        message = release.get("message") if isinstance(release, dict) else None
        raise ReleaseError(f"could not create the release for {tag}: HTTP {status} {message or ''}".rstrip())
    print(f"Created release {tag}: {release.get('html_url', '')}")
    return release


def upload_assets(gh, release, files):
    attached = {asset["name"] for asset in release.get("assets") or []}
    upload_url = release["upload_url"].split("{", 1)[0]
    for path in files:
        name = os.path.basename(path)
        if name in attached:
            print(f"{name} is already attached.")
            continue
        with open(path, "rb") as f:
            data = f.read()
        status, _ = gh.request("POST", f"{upload_url}?name={urllib.parse.quote(name)}", data,
                               content_type="application/octet-stream")
        if status != 201:
            raise ReleaseError(f"could not attach {name}: HTTP {status}")
        print(f"Attached {name} ({len(data):,} bytes).")


def move_major_tag(gh, major, commit):
    ref = f"tags/v{major}"
    status, _ = gh.request("PATCH", f"/git/refs/{ref}", {"sha": commit, "force": True})
    if status == 200:
        print(f"Moved v{major} to {commit[:7]}.")
        return
    # GitHub answers 422 (or 404) when the tag doesn't exist yet.
    status, body = gh.request("POST", "/git/refs", {"ref": f"refs/{ref}", "sha": commit})
    if status != 201:
        message = body.get("message") if isinstance(body, dict) else None
        raise ReleaseError(f"could not create the v{major} tag: HTTP {status} {message or ''}".rstrip())
    print(f"Created v{major} at {commit[:7]}.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"), help="owner/name")
    parser.add_argument("--tag", required=True, help="the version tag, such as v0.3.0")
    parser.add_argument("--commit", required=True, help="the commit the tag points to")
    parser.add_argument("--dist", required=True, help="directory holding the built wheel and source archive")
    parser.add_argument("--api-url", default=os.environ.get("GITHUB_API_URL") or "https://api.github.com")
    args = parser.parse_args(argv)

    try:
        version = parse_version(args.tag)
        if not version:
            raise ReleaseError(f"{args.tag!r} is not a version tag like v1.2.3")
        if not COMMIT.fullmatch(args.commit):
            raise ReleaseError("--commit must be a full 40-character commit ID")
        if not args.repo or not re.fullmatch(r"[\w.-]+/[\w.-]+", args.repo):
            raise ReleaseError("--repo (or GITHUB_REPOSITORY) must be owner/name")
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            raise ReleaseError("GITHUB_TOKEN is not set")
        files = sorted(os.path.join(args.dist, name) for name in os.listdir(args.dist)
                       if name.endswith((".whl", ".tar.gz")))
        if not files:
            raise ReleaseError(f"no wheel or source archive in {args.dist}")
        wheel = next((os.path.basename(f) for f in files if f.endswith(".whl")), None)

        gh = GitHub(args.api_url, args.repo, token)
        versions = released_versions(gh, version[0])
        newest = version >= max(versions, default=version)
        release = ensure_release(gh, args.repo, args.tag, version, newest, wheel)
        upload_assets(gh, release, files)
        if newest:
            move_major_tag(gh, version[0], args.commit)
        else:
            latest = "v" + ".".join(map(str, max(versions)))
            print(f"v{version[0]} stays where it is: {latest} is newer than {args.tag}.")
    except (ReleaseError, OSError) as exc:
        print(f"github_release: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
