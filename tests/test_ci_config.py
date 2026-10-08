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

if __name__ == "__main__":
    unittest.main()
