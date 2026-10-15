#!/bin/bash

set -e
set -x

export PIP_CONSTRAINT="$(cd "$(dirname "$0")" && pwd)/constraints.txt"

if [[ "${TOXENV}" == "py34" ]]; then
    # Python 3.4's `python3 -m venv`, run from the Travis per-leg virtualenv,
    # installs into that outer virtualenv instead of the new venv, so install
    # tox into the leg's interpreter directly.
    python -m pip install "tox<4"
else
    # Run tox from its own venv so it does not share packages with the Travis
    # per-leg virtualenv; tox then finds the leg's interpreter (pythonX.Y) on PATH.
    python3 -m venv "$HOME/toxenv"
    "$HOME/toxenv/bin/python" -m pip install -U "pip<21"
    "$HOME/toxenv/bin/python" -m pip install "tox<4"
fi
