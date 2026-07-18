#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

[[ -f install.sh ]] || fail "install.sh is missing"
[[ -x install.sh ]] || fail "install.sh is not executable"
bash -n install.sh

grep -Fq 'set -Eeuo pipefail' install.sh || fail "strict Bash mode is missing"
grep -Fq 'e4ea0a0ed7fc24761b2b425146893561a73216e1' install.sh || fail "Hermes commit is not pinned"
grep -Fq 'v1.0.0' install.sh || fail "installer asset tag is not pinned"
grep -Fq 'read -r -s' install.sh || fail "Telegram token is not read silently"
grep -Fq '</dev/tty' install.sh || fail "interactive input is not pipe-safe"
grep -Fq 'gpt-5.6-terra' install.sh || fail "Terra model is not configured"
grep -Fq 'agent.reasoning_effort medium' install.sh || fail "medium effort is not configured"
grep -Fq 'agent.reasoning_effort_auto.enabled true' install.sh || fail "auto-effort is not enabled"
grep -Fq 'gateway install --system --run-as-user root --force --start-now --start-on-login' install.sh || fail "root system gateway install is missing"
grep -Fq 'systemctl is-active --quiet hermes-gateway.service' install.sh || fail "active service verification is missing"
grep -Fq 'HERMES_INSTALLER_TEST_MODE' install.sh || fail "isolated test mode is missing"

if grep -Eq 'GATEWAY_ALLOW_ALL_USERS|TELEGRAM_ALLOW_ALL_USERS|--yolo|approvals\.mode[[:space:]]+off' install.sh; then
  fail "unsafe access/approval bypass is present"
fi
if grep -Eq -- '--(telegram-)?token([=[:space:]])|bash[[:space:]]+-s[[:space:]]+--.*TELEGRAM' install.sh; then
  fail "Telegram token appears to be accepted as a command-line argument"
fi

printf 'static installer checks: PASS\n'
