#!/usr/bin/env bash
# The install step of the NilPDF GitHub Action (action.yml in the repository root).
#
# Installs nilpdf from the action's own checkout into a private virtual
# environment, so the code that runs is exactly the tagged version the
# workflow asked for, and nothing is added to the job's own Python. Prints the
# environment's Python as the step output `python`, and its directory as
# `venv` for action/cleanup.sh. pip keeps no cache: on a self-hosted runner it
# would land in a home directory shared by every job, and stay there.
#
# Every command here runs from inside that new environment's directory, never
# from the workspace: `python -m` puts the current directory first on the
# module path, so a checked-out pull request containing a file like venv.py
# could otherwise take over the step.
set -euo pipefail

action_dir=${GITHUB_ACTION_PATH:?GITHUB_ACTION_PATH is not set}

python=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 &&
       "$candidate" -I -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
        python=$(command -v "$candidate")
        break
    fi
done
if [ -z "$python" ]; then
    echo "::error title=NilPDF needs Python::Python 3.10 or newer was not found on this runner. Add actions/setup-python before this step."
    exit 1
fi

venv=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/nilpdf-action.XXXXXX")
# Recorded straight away, so the action's last step removes the environment
# even if the install fails part-way.
echo "venv=$venv" >> "${GITHUB_OUTPUT:-/dev/null}"
cd "$venv"

if ! "$python" -I -m venv "$venv/env" >venv.log 2>&1; then
    cat venv.log
    echo "::error title=NilPDF could not create a virtual environment::$python could not create one. On Debian or Ubuntu, install the python3-venv package, or add actions/setup-python before this step."
    exit 1
fi
bin="$venv/env/bin"
[ -d "$bin" ] || bin="$venv/env/Scripts"   # Windows

# Pin the engine's PDF library and the build backend to the versions this
# release was tested with. cryptography, needed only for encrypted PDFs, is
# left to resolve to its latest release, which carries the latest fixes.
grep -E '^(pypdf|hatchling)==' "$action_dir/requirements.txt" > constraints.txt
pip_install() {
    "$bin/python" -I -m pip install --quiet --disable-pip-version-check --no-input --no-cache-dir \
        -c constraints.txt "$@"
}
pip_install hatchling
pip_install --no-build-isolation "$action_dir"

"$bin/python" -I -c 'import nilpdf; print(f"Installed nilpdf {nilpdf.__version__}")'
echo "python=$bin/python" >> "${GITHUB_OUTPUT:-/dev/null}"
