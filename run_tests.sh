#!/usr/bin/env bash
# Run every suite. The UI ones need a Qt platform; offscreen is the default.
set -euo pipefail
cd "$(dirname "$0")"

for suite in tests/test_packaging.py tests/test_parser.py tests/test_configs.py \
             tests/test_local_packages.py tests/test_probe.py tests/smoke_ui.py; do
    echo "=== $suite"
    python "$suite" > /dev/null
done
echo "all suites passed"
