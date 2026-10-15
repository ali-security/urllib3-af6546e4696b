#!/bin/bash

set -e
set -x

export PIP_CONSTRAINT="$(cd "$(dirname "$0")" && pwd)/constraints.txt"

if [[ "${TOXENV}" == "py34" ]]; then
    TOX=(python -m tox)
    # tox 3.14 (the last release installable on 3.4) has no --skip-pkg-install;
    # its second run re-installs the local sdist, which needs no index access.
    SKIP_PKG_INSTALL=()
else
    TOX=("$HOME/toxenv/bin/tox")
    SKIP_PKG_INSTALL=(--skip-pkg-install)
fi

# Install the test environment at the real date (the package index's TLS
# certificate is not valid in 2019).
"${TOX[@]}" --notest

# Then run the suite with the clock at the 1.24.2 release date: the dummyserver
# test certificates expired in 2021, and test_recent_date asserts RECENT_DATE is
# within two years of today. tox only forwards the faketime variables to the
# test command when they are listed in TOX_TESTENV_PASSENV.
export FAKETIME_DONT_RESET=1
export PIP_DISABLE_PIP_VERSION_CHECK=1
export TOX_TESTENV_PASSENV="LD_PRELOAD FAKETIME FAKETIME_DONT_RESET"
# test_source_address_error requests "/source_address?('192.0.2.255', 0)"; current
# 2.7/3.5+ interpreters reject URLs containing spaces (bpo-30458), so the request
# never reaches the code under test.
faketime '2019-04-17 12:00:00' "${TOX[@]}" "${SKIP_PKG_INSTALL[@]}" -- \
    --deselect "test/with_dummyserver/test_connectionpool.py::TestConnectionPool::test_source_address_error"
