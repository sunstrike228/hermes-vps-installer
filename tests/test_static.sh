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
# Verify the literal runtime expansion in install.sh.
# shellcheck disable=SC2016
grep -Fq 'https://raw.githubusercontent.com/NousResearch/hermes-agent/${HERMES_UPSTREAM_COMMIT}/scripts/install.sh' install.sh || fail "pinned official installer path is incorrect"
grep -Fq 'e4ea0a0ed7fc24761b2b425146893561a73216e1' install.sh || fail "Hermes commit is not pinned"
grep -Fq 'v1.1.0' install.sh || fail "installer asset tag is not pinned"
grep -Fq 'read -r -s' install.sh || fail "Telegram token is not read silently"
grep -Fq '</dev/tty' install.sh || fail "interactive input is not pipe-safe"
grep -Fq 'gpt-5.6-terra' install.sh || fail "Terra model is not configured"
grep -Fq 'gpt-5.6-sol' install.sh || fail "Sol fallback model is missing"
grep -Fq 'agent.reasoning_effort medium' install.sh || fail "medium effort is not configured"
grep -Fq 'agent.reasoning_effort_auto.enabled true' install.sh || fail "auto-effort is not enabled"
grep -Fq 'gateway install --system --run-as-user root --force --start-now --start-on-login' install.sh || fail "root system gateway install is missing"
grep -Fq 'systemctl is-active --quiet hermes-gateway.service' install.sh || fail "active service verification is missing"
grep -Fq 'HERMES_INSTALLER_TEST_MODE' install.sh || fail "isolated test mode is missing"
grep -Fq 'xz-utils' install.sh || fail "xz-utils clean-Ubuntu dependency is missing"
grep -Fq 'systemctl stop hermes-gateway.service' install.sh || fail "rerun gateway pause is missing"
grep -Fq 'systemctl start hermes-gateway.service' install.sh || fail "rerun gateway recovery is missing"

if grep -Eq 'GATEWAY_ALLOW_ALL_USERS|TELEGRAM_ALLOW_ALL_USERS|--yolo|approvals\.mode[[:space:]]+off' install.sh; then
  fail "unsafe access/approval bypass is present"
fi
if grep -Eq -- '--(telegram-)?token([=[:space:]])|bash[[:space:]]+-s[[:space:]]+--.*TELEGRAM' install.sh; then
  fail "Telegram token appears to be accepted as a command-line argument"
fi

[[ -f README.md ]] || fail "README.md is missing"
[[ -f LICENSE ]] || fail "LICENSE is missing"
[[ -f .github/workflows/ci.yml ]] || fail "GitHub Actions CI is missing"
grep -Fq 'v1.0.0/install.sh' README.md || fail "README does not use the stable tagged installer"
grep -Fq 'v1.0.0/install.sh | bash' README.md || fail "README root one-line command is missing"
grep -Fq 'v1.0.0/install.sh | sudo bash' README.md || fail "README sudo one-line command is missing"
grep -Fq '@BotFather' README.md || fail "BotFather instructions are missing"
grep -Fq 'gpt-5.6-terra' README.md || fail "README model is missing"
grep -Fq 'medium' README.md || fail "README reasoning level is missing"
grep -Fqi 'auto-effort' README.md || fail "README auto-effort setting is missing"
grep -Fq 'hermes gateway status --system --deep' README.md || fail "README diagnostics are missing"
grep -Eqi 'root.*(risk|риск|доступ)' README.md || fail "README root-risk warning is missing"
if grep -Eq '[0-9]{6,12}:[A-Za-z0-9_-]{30,}' README.md; then
  fail "README contains a token-like secret"
fi
grep -Fq 'shellcheck install.sh' .github/workflows/ci.yml || fail "CI does not run shellcheck"
grep -Fq 'python3 -m unittest discover -s tests -v' .github/workflows/ci.yml || fail "CI does not run Python tests"

printf 'static installer checks: PASS\n'
