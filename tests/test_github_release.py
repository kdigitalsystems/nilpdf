"""Tests for scripts/github_release.py, run against a stand-in for GitHub's API.

The script creates the GitHub Release for a tag, attaches the built package
and moves the major-version tag (v0). It runs with write access to the
repository, so what matters most here is what it must not do: release twice,
move v0 backwards, or let its token reach a log.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(BASE, "scripts", "github_release.py")
REPO = "kdigitalsystems/nilpdf"
TOKEN = "ghs_THIS-TOKEN-MUST-NEVER-BE-PRINTED"
COMMIT = "a1" * 20
OLDER = "b2" * 20


class FakeGitHub:
    """Just enough of the REST API: releases, their assets, and tag refs."""

    def __init__(self):
        self.releases = {}        # tag -> release
        self.uploads = {}         # (tag, file name) -> bytes
        self.refs = {}            # "tags/v0.2.1" -> sha
        self.requests = []        # (method, path, headers, body)
        self.fail = {}            # (method, path prefix) -> status to answer with
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def answer(self, status, body=None):
                raw = json.dumps(body).encode() if body is not None else b""
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def handle_any(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                outer.requests.append((self.command, self.path, dict(self.headers), body))
                for (method, prefix), status in outer.fail.items():
                    if method == self.command and self.path.startswith(prefix):
                        return self.answer(status, {"message": "the server said no"})
                return self.answer(*outer.route(self.command, self.path, body))

            do_GET = do_POST = do_PATCH = handle_any

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def route(self, method, path, body):
        prefix = f"/repos/{REPO}"
        if not path.startswith(prefix) and not path.startswith("/upload/"):
            return 404, {"message": "Not Found"}
        rest = path[len(prefix):]
        if method == "GET" and rest.startswith("/git/matching-refs/"):
            wanted = rest[len("/git/matching-refs/"):]
            return 200, [{"ref": f"refs/{ref}", "object": {"sha": sha}}
                         for ref, sha in sorted(self.refs.items()) if ref.startswith(wanted)]
        if method == "GET" and rest.startswith("/releases/tags/"):
            release = self.releases.get(rest[len("/releases/tags/"):])
            return (200, release) if release else (404, {"message": "Not Found"})
        if method == "POST" and rest == "/releases":
            data = json.loads(body)
            if data["tag_name"] in self.releases:
                return 422, {"message": "Validation Failed: already_exists"}
            release = {**data, "id": len(self.releases) + 1, "assets": [],
                       "html_url": f"https://github.com/{REPO}/releases/tag/{data['tag_name']}",
                       "upload_url": f"{self.url}/upload/{data['tag_name']}/assets{{?name,label}}"}
            self.releases[data["tag_name"]] = release
            return 201, release
        if method == "POST" and path.startswith("/upload/"):
            tag = path.split("/")[2]
            name = path.split("name=", 1)[1]
            if any(a["name"] == name for a in self.releases[tag]["assets"]):
                return 422, {"message": "Validation Failed: already_exists"}
            self.releases[tag]["assets"].append({"name": name, "size": len(body)})
            self.uploads[(tag, name)] = body
            return 201, {"name": name}
        if method == "PATCH" and rest.startswith("/git/refs/"):
            ref = rest[len("/git/refs/"):]
            if ref not in self.refs:
                return 422, {"message": "Reference does not exist"}
            self.refs[ref] = json.loads(body)["sha"]
            return 200, {"ref": f"refs/{ref}"}
        if method == "POST" and rest == "/git/refs":
            data = json.loads(body)
            ref = data["ref"].removeprefix("refs/")
            if ref in self.refs:
                return 422, {"message": "Reference already exists"}
            self.refs[ref] = data["sha"]
            return 201, {"ref": data["ref"]}
        return 404, {"message": "Not Found"}

    def made(self, method, fragment):
        return [r for r in self.requests if r[0] == method and fragment in r[1]]


class TestGitHubRelease(unittest.TestCase):
    def setUp(self):
        self.gh = FakeGitHub()
        self.addCleanup(self.gh.close)
        self.dist = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dist, ignore_errors=True)
        self.files = {"nilpdf-0.3.0-py3-none-any.whl": b"wheel bytes \x00\x01", "nilpdf-0.3.0.tar.gz": b"sdist bytes"}
        for name, data in self.files.items():
            with open(os.path.join(self.dist, name), "wb") as f:
                f.write(data)
        # The tag being released always exists by the time this runs.
        self.gh.refs["tags/v0.3.0"] = "tagobject"

    def run_script(self, tag="v0.3.0", commit=COMMIT, env=None, dist=None):
        full_env = {"PATH": os.environ["PATH"], "GITHUB_TOKEN": TOKEN, "GITHUB_REPOSITORY": REPO,
                    "GITHUB_API_URL": self.gh.url, **(env or {})}
        done = subprocess.run([sys.executable, SCRIPT, "--tag", tag, "--commit", commit, "--dist", dist or self.dist],
                              env=full_env, capture_output=True, text=True, timeout=60)
        done.all = done.stdout + done.stderr
        return done

    def test_creates_the_release_attaches_the_package_and_creates_the_major_tag(self):
        r = self.run_script()
        self.assertEqual(r.returncode, 0, r.all)
        release = self.gh.releases["v0.3.0"]
        self.assertEqual(release["name"], "nilpdf 0.3.0")
        self.assertIs(release["generate_release_notes"], True)
        self.assertEqual(release["make_latest"], "true")
        self.assertEqual({name: data for (_, name), data in self.gh.uploads.items()}, self.files)
        self.assertEqual(sorted(a["name"] for a in release["assets"]), sorted(self.files))
        self.assertEqual(self.gh.refs["tags/v0"], COMMIT)
        self.assertEqual(self.gh.refs["tags/v0.3.0"], "tagobject", "the version tag itself is never touched")

    def test_the_notes_say_how_to_use_this_version(self):
        self.run_script()
        body = self.gh.releases["v0.3.0"]["body"]
        self.assertIn(f"- uses: {REPO}@v0.3.0   # or @v0 for the newest 0.x", body)
        self.assertIn(f"pip install https://github.com/{REPO}/releases/download/v0.3.0/nilpdf-0.3.0-py3-none-any.whl", body)
        self.assertIn("no file is uploaded", body)

    def test_running_it_again_changes_nothing(self):
        """A failed release run is rerun as a whole, so every step must be
        safe to repeat."""
        self.assertEqual(self.run_script().returncode, 0)
        before = json.dumps([self.gh.releases, self.gh.refs], sort_keys=True)
        r = self.run_script()
        self.assertEqual(r.returncode, 0, r.all)
        self.assertEqual(json.dumps([self.gh.releases, self.gh.refs], sort_keys=True), before)
        self.assertEqual(len(self.gh.made("POST", "/releases")), 1)
        self.assertEqual(len(self.gh.made("POST", "/upload/")), 2)
        self.assertIn("already exists", r.stdout)
        self.assertIn("already attached", r.stdout)

    def test_a_half_finished_release_is_completed(self):
        """The first run created the release and one file, then died."""
        self.run_script()
        release = self.gh.releases["v0.3.0"]
        release["assets"] = release["assets"][:1]
        del self.gh.refs["tags/v0"]
        self.assertEqual(self.run_script().returncode, 0)
        self.assertEqual(sorted(a["name"] for a in release["assets"]), sorted(self.files))
        self.assertEqual(self.gh.refs["tags/v0"], COMMIT)

    def test_an_existing_major_tag_is_moved_forward(self):
        self.gh.refs.update({"tags/v0.2.1": "x", "tags/v0": OLDER})
        self.assertEqual(self.run_script().returncode, 0)
        self.assertEqual(self.gh.refs["tags/v0"], COMMIT)
        [(_, _, _, body)] = self.gh.made("PATCH", "/git/refs/tags/v0")
        self.assertEqual(json.loads(body), {"sha": COMMIT, "force": True})

    def test_releasing_an_older_version_never_moves_the_major_tag_back(self):
        """Publishing v0.2.1 again, by hand, after v0.3.0 is out: v0 must keep
        pointing at v0.3.0, and v0.2.1 must not become the "Latest" release."""
        self.gh.refs.update({"tags/v0.2.1": "x", "tags/v0": COMMIT})
        os.rename(os.path.join(self.dist, "nilpdf-0.3.0-py3-none-any.whl"),
                  os.path.join(self.dist, "nilpdf-0.2.1-py3-none-any.whl"))
        r = self.run_script(tag="v0.2.1", commit=OLDER)
        self.assertEqual(r.returncode, 0, r.all)
        self.assertEqual(self.gh.refs["tags/v0"], COMMIT)
        self.assertEqual(self.gh.made("PATCH", "/git/refs"), [])
        self.assertEqual(self.gh.releases["v0.2.1"]["make_latest"], "false")
        self.assertIn("v0 stays where it is: v0.3.0 is newer than v0.2.1.", r.stdout)

    def test_versions_are_compared_as_numbers_and_only_real_version_tags_count(self):
        self.gh.refs.update({"tags/v0.10.0": "x", "tags/v0.9.9": "x", "tags/v0.99.0-rc1": "x",
                             "tags/v0.x": "x", "tags/v1.0.0": "x"})
        self.gh.refs["tags/v0"] = OLDER
        self.assertEqual(self.run_script(tag="v0.3.0").returncode, 0)
        self.assertEqual(self.gh.refs["tags/v0"], OLDER, "v0.10.0 is newer than v0.3.0")
        del self.gh.refs["tags/v0.10.0"], self.gh.refs["tags/v0.9.9"]
        self.assertEqual(self.run_script(tag="v0.3.0").returncode, 0)
        self.assertEqual(self.gh.refs["tags/v0"], COMMIT, "a release candidate, v0.x and v1.0.0 don't hold v0 back")

    def test_each_major_version_has_its_own_tag(self):
        self.gh.refs["tags/v1.4.0"] = "x"
        self.assertEqual(self.run_script(tag="v1.4.0").returncode, 0)
        self.assertEqual(self.gh.refs["tags/v1"], COMMIT)
        self.assertNotIn("tags/v0", self.gh.refs)

    def test_the_token_is_sent_but_never_printed(self):
        r = self.run_script()
        self.assertTrue(self.gh.requests)
        for method, path, headers, _ in self.gh.requests:
            with self.subTest(request=f"{method} {path}"):
                self.assertEqual(headers.get("Authorization"), f"Bearer {TOKEN}")
        self.assertNotIn(TOKEN, r.all)
        self.assertNotIn(TOKEN, json.dumps([p for _, p, _, _ in self.gh.requests]))

    def test_a_failure_stops_it_with_the_reason_and_without_the_token(self):
        for method, prefix in (("GET", f"/repos/{REPO}/git/matching-refs"), ("POST", f"/repos/{REPO}/releases"),
                               ("POST", "/upload/"), ("POST", f"/repos/{REPO}/git/refs")):
            with self.subTest(failing=f"{method} {prefix}"):
                self.gh.fail = {(method, prefix): 500}
                r = self.run_script()
                self.assertEqual(r.returncode, 1)
                self.assertIn("github_release:", r.stderr)
                self.assertIn("HTTP 500", r.stderr)
                self.assertNotIn(TOKEN, r.all)
                self.assertNotIn("Traceback", r.all)
        self.gh.fail = {}
        self.assertEqual(self.run_script().returncode, 0, "and a rerun finishes the job")
        self.assertEqual(self.gh.refs["tags/v0"], COMMIT)

    def test_bad_arguments_are_refused_before_anything_is_sent(self):
        empty = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        cases = {
            "a tag that is not a version": dict(tag="v0"),
            "a branch name": dict(tag="main"),
            "a pre-release tag": dict(tag="v0.3.0-rc1"),
            "a short commit": dict(commit=COMMIT[:12]),
            "a ref instead of a commit": dict(commit="HEAD"),
            "no token": dict(env={"GITHUB_TOKEN": ""}),
            "no repository": dict(env={"GITHUB_REPOSITORY": ""}),
            "an empty dist directory": dict(dist=empty),
        }
        for label, kwargs in cases.items():
            with self.subTest(case=label):
                r = self.run_script(**kwargs)
                self.assertEqual(r.returncode, 1, r.all)
                self.assertIn("github_release:", r.stderr)
        self.assertEqual(self.gh.requests, [])
        self.assertEqual(self.gh.releases, {})


if __name__ == "__main__":
    unittest.main()
