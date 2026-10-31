"""Rules for the workflows themselves, so CI can't quietly drift.

A change to a workflow isn't tested by running it until it lands, and some
mistakes never fail at all: a job that quietly moves to a GitHub-hosted runner,
an action tag that gets repointed upstream, a deploy that stops waiting for the
browser tests, a pull-request job that picks up write permissions. These pin
the rules down.
"""
import glob
import os
import re
import shutil
import subprocess
import tempfile
import unittest

import yaml

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW_DIR = os.path.join(BASE, ".github", "workflows")
GITHUB_HOSTED = re.compile(r"^(ubuntu|windows|macos)-", re.I)


def read(rel):
    with open(os.path.join(BASE, rel), encoding="utf-8") as f:
        return f.read()


def load_workflows():
    out = {}
    for path in sorted(glob.glob(os.path.join(WORKFLOW_DIR, "*.yml")) + glob.glob(os.path.join(WORKFLOW_DIR, "*.yaml"))):
        with open(path, encoding="utf-8") as f:
            text = f.read()
        out[os.path.basename(path)] = (yaml.safe_load(text), text)
    return out


def triggers(wf):
    # YAML 1.1 reads a bare `on:` key as the boolean True.
    return wf.get("on", wf.get(True)) or {}


def labels(job):
    runs_on = job.get("runs-on")
    return [runs_on] if isinstance(runs_on, str) else list(runs_on or [])


def uses_steps(job):
    return [s["uses"] for s in job.get("steps", []) if "uses" in s]


WORKFLOWS = load_workflows()


class TestRunners(unittest.TestCase):
    def test_workflows_were_found(self):
        self.assertIn("static.yml", WORKFLOWS)
        self.assertIn("release.yml", WORKFLOWS)

    def test_every_job_runs_on_self_hosted_runners_only(self):
        for name, (wf, _) in WORKFLOWS.items():
            for job_id, job in wf["jobs"].items():
                with self.subTest(workflow=name, job=job_id):
                    ls = labels(job)
                    self.assertIn("self-hosted", ls, f"{job_id} must run on a self-hosted runner")
                    hosted = [lb for lb in ls if GITHUB_HOSTED.match(str(lb))]
                    self.assertFalse(hosted, f"{job_id} asks for a GitHub-hosted runner: {hosted}")

    def test_jobs_that_need_docker_ask_for_a_docker_runner(self):
        """Container jobs, and the PyPI publish action (which starts its own
        container), fail on a runner without Docker. Not every self-hosted
        runner has it."""
        for name, (wf, _) in WORKFLOWS.items():
            for job_id, job in wf["jobs"].items():
                needs_docker = "container" in job or any("gh-action-pypi-publish" in u for u in uses_steps(job))
                if needs_docker:
                    with self.subTest(workflow=name, job=job_id):
                        self.assertIn("docker", labels(job))

    def test_container_jobs_that_need_git_install_it_before_checkout(self):
        """Without git in the container, checkout downloads a plain tarball with
        no .git directory. git commands then fail, and so does actionlint, which
        finds the project by its .git. The slim Python images ship without git."""
        uses_git = re.compile(r"\bgit\s|actionlint")
        for name, (wf, _) in WORKFLOWS.items():
            for job_id, job in wf["jobs"].items():
                steps = job.get("steps", [])
                checkout = next((i for i, s in enumerate(steps) if "actions/checkout" in s.get("uses", "")), None)
                if "container" not in job or checkout is None:
                    continue
                after = " ".join(s.get("run", "") for s in steps[checkout + 1:])
                if not uses_git.search(after):
                    continue
                with self.subTest(workflow=name, job=job_id):
                    before = " ".join(s.get("run", "") for s in steps[:checkout])
                    self.assertRegex(before, r"apt-get install[^\n]*\bgit\b",
                                     f"{job_id} uses git after checkout but never installs it before")

    def test_every_job_has_a_timeout(self):
        for name, (wf, _) in WORKFLOWS.items():
            for job_id, job in wf["jobs"].items():
                with self.subTest(workflow=name, job=job_id):
                    self.assertIn("timeout-minutes", job, "a hung job would hold a shared runner indefinitely")


class TestSupplyChain(unittest.TestCase):
    def test_actions_are_pinned_to_full_commit_shas(self):
        """A tag like @v7 can be moved to different code after the fact; a
        commit SHA can't. On self-hosted runners an action runs with our
        network access and hardware, so pin everything."""
        for name, (_, text) in WORKFLOWS.items():
            for line in text.splitlines():
                m = re.match(r"^\s*(?:-\s*)?uses:\s*(\S+)(.*)$", line)
                if not m or m.group(1).startswith(("./", "docker://")):
                    continue
                with self.subTest(workflow=name, uses=m.group(1)):
                    self.assertRegex(m.group(1), r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
                    self.assertRegex(m.group(2), r"#\s*v\d", "add the version as a comment, e.g. # v7.0.1")

    def test_downloaded_tools_are_checksum_verified(self):
        static = read(".github/workflows/static.yml")
        for url in re.findall(r"https://github\.com/[^\s]+/releases/download/[^\s]+", static):
            with self.subTest(url=url):
                self.assertIn("sha256sum -c", static, f"{url} is downloaded without checking its checksum")

    def test_no_pull_request_target(self):
        """pull_request_target runs fork code with the base repo's secrets and
        write token. On self-hosted runners that's a direct path to our machines."""
        for name, (wf, _) in WORKFLOWS.items():
            with self.subTest(workflow=name):
                self.assertNotIn("pull_request_target", triggers(wf))


class TestPermissions(unittest.TestCase):
    ELEVATED = {"deploy", "publish"}

    def test_workflows_default_to_read_only(self):
        for name, (wf, _) in WORKFLOWS.items():
            perms = wf.get("permissions")
            with self.subTest(workflow=name):
                self.assertIsInstance(perms, dict, "set workflow-level permissions explicitly")
                writes = {k: v for k, v in perms.items() if v == "write" and k != "actions"}
                self.assertFalse(writes, f"workflow-level write permissions: {writes}")

    def test_only_deploy_and_publish_get_id_tokens_or_write_access(self):
        for name, (wf, _) in WORKFLOWS.items():
            for job_id, job in wf["jobs"].items():
                writes = {k for k, v in (job.get("permissions") or {}).items() if v == "write"}
                if job_id in self.ELEVATED:
                    continue
                with self.subTest(workflow=name, job=job_id):
                    self.assertFalse(writes, f"{job_id} asks for write access: {writes}")

    def test_elevated_jobs_never_run_for_pull_requests(self):
        static = WORKFLOWS["static.yml"][0]["jobs"]["deploy"]
        self.assertIn("github.event_name != 'pull_request'", static["if"])
        self.assertNotIn("pull_request", triggers(WORKFLOWS["release.yml"][0]))


class TestPipelineShape(unittest.TestCase):
    def test_deploy_waits_for_every_other_check(self):
        jobs = WORKFLOWS["static.yml"][0]["jobs"]
        others = set(jobs) - {"deploy"}
        self.assertEqual(set(jobs["deploy"]["needs"]), others,
                         "deploy must need every check, or a failing one won't stop a deploy")

    def test_the_suite_runs_on_the_oldest_and_newest_supported_python(self):
        static = WORKFLOWS["static.yml"]
        jobs = static[0]["jobs"]
        tested = set(jobs["compat"]["strategy"]["matrix"]["python"])
        tested.add(re.search(r"python:(\d+\.\d+)", jobs["test"]["container"]["image"]).group(1))
        floor = re.search(r'requires-python = ">=(\d+\.\d+)"', read("pyproject.toml")).group(1)
        self.assertIn(floor, tested, "the package's minimum Python isn't tested")
        self.assertIn("3.14", tested, "the browser's Python (Pyodide 314) isn't tested")

    def test_browser_test_image_matches_the_playwright_pin(self):
        image = WORKFLOWS["static.yml"][0]["jobs"]["e2e"]["container"]["image"]
        image_version = re.search(r":v(\d+\.\d+\.\d+)", image).group(1)
        pin = re.search(r"^playwright==(\S+)$", read("requirements-e2e.txt"), re.M).group(1)
        self.assertEqual(image_version, pin, "the Playwright image and the pip pin must be the same version")

    def test_coverage_floor_is_enforced_in_ci(self):
        self.assertRegex(read("pyproject.toml"), r"(?m)^fail_under = \d+")
        self.assertIn("--cov", read(".github/workflows/static.yml"))


class TestBrowserTestsWaitProperly(unittest.TestCase):
    def test_no_async_predicate_is_passed_to_wait_for_function(self):
        """Playwright's wait_for_function() treats the Promise an async function
        returns as truthy, so it returns without waiting. That made the warm-boot
        test reload before the package cache was saved, and fail on slow runners.
        Use wait_until() in tests/e2e/test_browser.py for async checks."""
        for path in glob.glob(os.path.join(BASE, "tests", "e2e", "*.py")):
            source = read(os.path.relpath(path, BASE))
            for m in re.finditer(r"wait_for_function\(\s*(?:\"\"\"|\"|')\s*async\b", source):
                line = source.count("\n", 0, m.start()) + 1
                self.fail(f"{os.path.relpath(path, BASE)}:{line} passes an async predicate to wait_for_function")


class TestReleaseWorkflow(unittest.TestCase):
    def setUp(self):
        self.wf, self.text = WORKFLOWS["release.yml"]
        self.jobs = self.wf["jobs"]

    def test_triggers(self):
        on = triggers(self.wf)
        self.assertEqual(on["push"], {"tags": ["v*"]})
        self.assertIn("workflow_dispatch", on)
        self.assertEqual(on["workflow_dispatch"]["inputs"]["publish"]["default"], False,
                         "a manual run must be a dry run unless publish is ticked")

    def test_publish_is_gated_behind_a_verified_build(self):
        publish = self.jobs["publish"]
        self.assertEqual(publish["needs"], "build")
        self.assertEqual(publish["environment"]["name"], "pypi")
        self.assertEqual(publish["permissions"], {"id-token": "write"})
        self.assertNotIn("container", publish, "the publish action starts its own container")
        self.assertTrue(any("gh-action-pypi-publish" in u for u in uses_steps(publish)))
        self.assertNotIn("password:", self.text, "use trusted publishing, not a stored token")

    def test_publish_clears_root_owned_files_before_anything_else(self):
        """The publish job runs on the host, after container jobs that ran as
        root in the same workspace. Its first step must clear their files, or
        the publish action can't write to .github/.tmp."""
        steps = self.wf["jobs"]["publish"]["steps"]
        first = steps[0].get("run", "")
        self.assertRegex(first, r'docker run --rm -v "\$GITHUB_WORKSPACE:/w"')
        self.assertIn("find /w -mindepth 1 -delete", first)

    def test_build_refuses_bad_releases_before_publishing(self):
        steps = " ".join(str(s.get("run", "")) for s in self.jobs["build"]["steps"])
        self.assertIn("__version__", steps, "the tag must be checked against the package version")
        self.assertIn("merge-base --is-ancestor HEAD origin/main", steps, "only commits on main may be released")
        self.assertIn("pytest", steps, "the tests must run at the tagged commit")
        self.assertIn("twine check --strict", steps)
        self.assertIn("nilpdf --version", steps, "the built wheel must be installed and run")



@unittest.skipUnless(shutil.which("git") and shutil.which("bash"), "needs git and bash")
class TestReleaseGateBehaviour(unittest.TestCase):
    """Run the release workflow's tag check itself, rather than grepping for it:
    a future edit could keep the words and drop the `exit 1`. Uses a throwaway
    git repo where main is one commit and an unmerged branch is the next."""

    STEP = "The tag must match the package version and be on main"

    def setUp(self):
        steps = WORKFLOWS["release.yml"][0]["jobs"]["build"]["steps"]
        self.script = next(s["run"] for s in steps if s.get("name") == self.STEP)
        self.tmp = tempfile.mkdtemp(prefix="nilpdf-release-gate-")
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.repo, "python", "nilpdf"))
        self.git_env = {**os.environ, "HOME": self.tmp, "GIT_CONFIG_NOSYSTEM": "1",
                        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
        self.git("init", "-q", "-b", "main")
        self.write_version("1.2.3")
        self.git("add", "-A")
        self.git("commit", "-qm", "on main")
        self.main_sha = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/remotes/origin/main", self.main_sha)
        self.git("checkout", "-qb", "feature")
        self.git("commit", "-q", "--allow-empty", "-m", "not merged")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, env=self.git_env, check=True,
                              capture_output=True, text=True).stdout.strip()

    def write_version(self, version):
        with open(os.path.join(self.repo, "python", "nilpdf", "__init__.py"), "w") as f:
            f.write(f'__version__ = "{version}"\n')

    def run_gate(self, tag):
        output = os.path.join(self.tmp, "github_output")
        open(output, "w").close()
        r = subprocess.run(["bash", "-e", "-c", self.script], cwd=self.repo, capture_output=True, text=True,
                           env={**self.git_env, "RELEASE_TAG": tag, "GITHUB_OUTPUT": output,
                                "GITHUB_WORKSPACE": self.repo})
        with open(output) as f:
            return r, f.read()

    def test_a_tag_that_does_not_match_the_version_is_refused(self):
        self.git("checkout", "-q", "main")
        r, out = self.run_gate("v9.9.9")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("does not match __version__ 1.2.3", r.stdout + r.stderr)
        self.assertNotIn("version=", out)

    def test_a_commit_that_is_not_on_main_is_refused(self):
        r, out = self.run_gate("v1.2.3")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("is not on main", r.stdout + r.stderr)
        self.assertNotIn("version=", out)

    def test_a_matching_tag_on_main_passes_and_exports_the_version(self):
        self.git("checkout", "-q", "main")
        r, out = self.run_gate("v1.2.3")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("version=1.2.3", out)

class TestRunnerDiskIsFreed(unittest.TestCase):
    """Container jobs run as root, and the runner doesn't, so the runner can't
    delete what they leave on its disk. Before this, every CI run left about
    240 MB in the runner's temp directory, and one root-owned file there stops
    the runner's own clean-up of everything else in it."""

    STEP = "Free the runner's disk space"
    HOST_RUN = 'docker run --rm -v "$GITHUB_WORKSPACE:/w" python:3.14-slim find /w -mindepth 1 -delete'

    def container_run(self):
        runs = {job["steps"][-1]["run"] for wf, _ in WORKFLOWS.values()
                for job in wf["jobs"].values() if "container" in job}
        self.assertEqual(len(runs), 1, "every container job should free the disk the same way")
        return runs.pop()

    def test_every_job_ends_by_freeing_the_disk_even_on_failure(self):
        for name, (wf, _) in WORKFLOWS.items():
            for job_id, job in wf["jobs"].items():
                with self.subTest(workflow=name, job=job_id):
                    last = job["steps"][-1]
                    self.assertEqual(last.get("name"), self.STEP)
                    self.assertEqual(last.get("if"), "always()")
                    if "container" not in job:
                        self.assertEqual(last["run"], self.HOST_RUN)

    def test_pip_keeps_no_cache_on_the_runner(self):
        for name in ("static.yml", "release.yml"):
            with self.subTest(workflow=name):
                self.assertEqual(WORKFLOWS[name][0].get("env", {}).get("PIP_NO_CACHE_DIR"), "1")

    def test_a_missing_variable_deletes_nothing(self):
        """`find ""` would fail anyway, but ${VAR:?} makes the intent explicit:
        an unset path stops the step before any find runs."""
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        open(os.path.join(tmp, "keep"), "w").close()
        env = {"PATH": os.environ["PATH"], "GITHUB_WORKSPACE": "", "RUNNER_TEMP": tmp, "GITHUB_EVENT_PATH": "x"}
        r = subprocess.run(["bash", "-c", self.container_run()], cwd=tmp, env=env, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(os.path.exists(os.path.join(tmp, "keep")))

    @unittest.skipUnless(hasattr(os, "geteuid") and os.geteuid() == 0,
                         "needs root, as in CI: it makes files owned by both root and the runner's user")
    def test_it_removes_what_root_left_and_nothing_else(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        ws, temp = os.path.join(tmp, "ws"), os.path.join(tmp, "temp")
        runner_uid = 1000
        started = 1_700_000_000

        def make(rel, uid=0, age=None, content=b"x"):
            path = os.path.join(tmp, rel)
            if rel.endswith("/"):
                os.makedirs(path, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as f:
                    f.write(content)
            os.chown(path, uid, uid)
            return path

        for rel in ("ws/.git/config", "ws/index.html", "ws/sub/deep/file.pdf", "ws/.hidden"):
            make(rel)
        event = make("temp/_github_workflow/event.json", runner_uid)
        kept = {
            "temp/_github_workflow/": runner_uid,      # the runner's own files, made during the job
            "temp/_runner_file_commands/": runner_uid,
            "temp/step-script.sh": runner_uid,
            "temp/_github_home/": runner_uid,
            "temp/_github_home/.cache/": 0,            # another job's cache, below the top level
            "temp/other-project-data/": 0,             # root-owned, but from before this job
        }
        removed = {
            "temp/nilpdf-action.aB3dE9/": 0,           # left by an older run of the action
            "temp/nilpdf-report-x1.json": 0,
            "temp/artifact.tar": 0,                     # made by root during this job
            "temp/new-dir/": 0,
            "temp/new-dir/nested/file": 0,
        }
        for rel, uid in {**kept, **removed}.items():
            make(rel, uid)
        # Timestamps last: creating entries inside a directory updates its mtime.
        os.utime(event, (started, started))
        for rel in ("temp/other-project-data/", "temp/nilpdf-action.aB3dE9/", "temp/nilpdf-report-x1.json"):
            os.utime(os.path.join(tmp, rel), (started - 3600, started - 3600))
        for rel in ("temp/artifact.tar", "temp/new-dir/", "temp/_runner_file_commands/", "temp/step-script.sh",
                    "temp/_github_home/"):
            os.utime(os.path.join(tmp, rel), (started + 60, started + 60))

        env = {"PATH": os.environ["PATH"], "GITHUB_WORKSPACE": ws, "RUNNER_TEMP": temp, "GITHUB_EVENT_PATH": event}
        r = subprocess.run(["bash", "-c", self.container_run()], cwd=ws, env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

        self.assertTrue(os.path.isdir(ws))
        self.assertEqual(os.listdir(ws), [], "the checkout is gone, the workspace directory stays")
        for rel in kept:
            with self.subTest(kept=rel):
                self.assertTrue(os.path.exists(os.path.join(tmp, rel)))
        for rel in removed:
            with self.subTest(removed=rel):
                self.assertFalse(os.path.exists(os.path.join(tmp, rel)))


if __name__ == "__main__":
    unittest.main()
