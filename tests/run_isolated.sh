#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

bash -n install.sh
if command -v shellcheck >/dev/null 2>&1; then
  shellcheck install.sh tests/*.sh
else
  printf 'shellcheck not installed; skipping local lint (CI installs it)\n' >&2
fi
python3 -m compileall -q lib tests
python3 -m unittest discover -s tests -v
bash tests/test_static.sh

dry_output="$(HERMES_INSTALLER_DRY_RUN=1 bash install.sh 2>&1)"
grep -Fq 'Model: gpt-5.6-terra' <<<"$dry_output"
grep -Fq 'Reasoning: medium' <<<"$dry_output"
grep -Fq 'Auto-effort: enabled' <<<"$dry_output"
grep -Fq 'Gateway: systemd system service, enabled and started' <<<"$dry_output"

printf 'isolated installer verification: PASS\n'
