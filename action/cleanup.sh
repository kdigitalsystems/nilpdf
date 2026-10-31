#!/usr/bin/env bash
# The last step of the NilPDF GitHub Action (action.yml in the repository
# root): remove the virtual environment install.sh made, about 40 MB. It runs
# even when an earlier step failed.
#
# On a self-hosted runner, in a job that runs inside a container, the
# environment belongs to root. The runner itself doesn't run as root, so it
# can't delete it later, and every run would leave another one behind.
set -euo pipefail

venv=${NILPDF_VENV:-}
# Only ever a directory install.sh created: <temp>/nilpdf-action.XXXXXX.
case "$venv" in
    */nilpdf-action.??????) ;;
    *) exit 0 ;;
esac
if [ -d "$venv" ]; then
    rm -rf -- "$venv"
fi
