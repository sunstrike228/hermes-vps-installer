#!/usr/bin/env bash
set -Eeuo pipefail

INSTALLER_VERSION="v1.1.0"
HERMES_UPSTREAM_COMMIT="e4ea0a0ed7fc24761b2b425146893561a73216e1"
OFFICIAL_INSTALLER_URL="https://raw.githubusercontent.com/NousResearch/hermes-agent/${HERMES_UPSTREAM_COMMIT}/scripts/install.sh"
ASSET_BASE_URL="${HERMES_INSTALLER_ASSET_BASE:-https://raw.githubusercontent.com/sunstrike228/hermes-vps-installer/${INSTALLER_VERSION}}"
HERMES_HOME="${HERMES_HOME:-/root/.hermes}"
export HERMES_HOME
HERMES_ENV_PATH="${HERMES_HOME}/.env"
TEST_MODE="${HERMES_INSTALLER_TEST_MODE:-0}"
DRY_RUN="${HERMES_INSTALLER_DRY_RUN:-0}"
CURRENT_STAGE="initialization"
TMP_DIR=""
TELEGRAM_TOKEN=""
TELEGRAM_OWNER_ID=""
TELEGRAM_CHAT_ID=""
BOT_USERNAME=""
PREPARE_JSON=""
SELECTED_MODEL="gpt-5.6-terra"
HELPER_PATH=""
RESTORE_EXISTING_GATEWAY="0"

print_stage() {
  CURRENT_STAGE="$1"
  printf '\n\033[1;36m==> %s\033[0m\n' "$CURRENT_STAGE"
}

info() {
  printf '\033[0;36m%s\033[0m\n' "$*"
}

warn() {
  printf '\033[1;33mWARNING: %s\033[0m\n' "$*" >&2
}

fatal() {
  printf '\033[1;31mERROR [%s]: %s\033[0m\n' "$CURRENT_STAGE" "$*" >&2
  exit 1
}

cleanup() {
  TELEGRAM_TOKEN=""
  if [[ "$RESTORE_EXISTING_GATEWAY" == "1" ]]; then
    systemctl start hermes-gateway.service >/dev/null 2>&1 || \
      warn "Could not restore the previously running Hermes gateway."
  fi
  if [[ -n "$TMP_DIR" && -d "$TMP_DIR" ]]; then
    rm -rf -- "$TMP_DIR"
  fi
}

on_error() {
  local line="$1"
  local code="$2"
  printf '\033[1;31mERROR [%s]: command failed near line %s (exit %s)\033[0m\n' \
    "$CURRENT_STAGE" "$line" "$code" >&2
  exit "$code"
}

trap cleanup EXIT
trap 'on_error "$LINENO" "$?"' ERR

require_no_arguments() {
  if (( $# != 0 )); then
    fatal "This installer accepts no command-line arguments. Telegram token is requested securely."
  fi
}

preflight() {
  print_stage "Preflight"
  if [[ "$TEST_MODE" == "1" ]]; then
    info "Test mode: host preflight is isolated."
    return
  fi
  [[ "$(id -u)" == "0" ]] || fatal "Run as root: curl ... | sudo bash"
  [[ -r /etc/os-release ]] || fatal "/etc/os-release is missing"
  # shellcheck disable=SC1091
  source /etc/os-release
  [[ "${ID:-}" == "ubuntu" ]] || fatal "Only Ubuntu is supported (detected: ${ID:-unknown})"
  command -v systemctl >/dev/null 2>&1 || fatal "systemd/systemctl is required"
  [[ -d /run/systemd/system ]] || fatal "systemd is not PID 1 on this VPS"
  [[ -r /dev/tty && -w /dev/tty ]] || fatal "An interactive TTY is required"
  local available_kb
  available_kb="$(df -Pk / | awk 'NR==2 {print $4}')"
  [[ "$available_kb" =~ ^[0-9]+$ ]] || fatal "Could not determine free disk space"
  (( available_kb >= 2097152 )) || fatal "At least 2 GB of free disk space is required"
  warn "Hermes and its terminal tools will run as root, as explicitly selected for this guide."
}

ensure_dependencies() {
  print_stage "System dependencies"
  if [[ "$TEST_MODE" == "1" ]]; then
    info "Test mode: dependency installation skipped."
    return
  fi
  local missing=()
  local command_name
  for command_name in curl git python3 xz; do
    command -v "$command_name" >/dev/null 2>&1 || missing+=("$command_name")
  done
  if (( ${#missing[@]} > 0 )); then
    apt-get update -y
    DEBIAN_FRONTEND=noninteractive apt-get install -y curl ca-certificates git python3 xz-utils
  fi
  command -v curl >/dev/null 2>&1 || fatal "curl is unavailable"
  command -v git >/dev/null 2>&1 || fatal "git is unavailable"
  command -v python3 >/dev/null 2>&1 || fatal "python3 is unavailable"
  command -v xz >/dev/null 2>&1 || fatal "xz is unavailable"
}

download_file() {
  local url="$1"
  local destination="$2"
  curl --proto '=https' --tlsv1.2 --fail --silent --show-error --location \
    --retry 3 --retry-delay 2 --connect-timeout 15 --max-time 180 \
    "$url" -o "$destination"
}

prepare_temp_files() {
  TMP_DIR="$(mktemp -d -t hermes-vps-installer.XXXXXX)"
  chmod 700 "$TMP_DIR"
}

install_hermes() {
  print_stage "Install Hermes Agent"
  local official_installer="${TMP_DIR}/hermes-official-install.sh"
  if [[ "$TEST_MODE" == "1" && -n "${HERMES_INSTALLER_OFFICIAL_PATH:-}" ]]; then
    cp -- "$HERMES_INSTALLER_OFFICIAL_PATH" "$official_installer"
  else
    download_file "$OFFICIAL_INSTALLER_URL" "$official_installer"
  fi
  chmod 700 "$official_installer"
  CALL_LOG="${CALL_LOG:-}" bash "$official_installer" \
    --skip-setup \
    --non-interactive \
    --commit "$HERMES_UPSTREAM_COMMIT" \
    --hermes-home "$HERMES_HOME"
  command -v hermes >/dev/null 2>&1 || fatal "Hermes command was not installed"
  hermes --version
}

prepare_helper() {
  print_stage "Telegram setup helper"
  HELPER_PATH="${TMP_DIR}/telegram_claim.py"
  if [[ "$TEST_MODE" == "1" && -n "${HERMES_INSTALLER_HELPER_PATH:-}" ]]; then
    cp -- "$HERMES_INSTALLER_HELPER_PATH" "$HELPER_PATH"
  else
    download_file "${ASSET_BASE_URL}/lib/telegram_claim.py" "$HELPER_PATH"
  fi
  chmod 600 "$HELPER_PATH"
}

validate_token_online() {
  local helper="$1"
  local prepare_json
  if ! prepare_json="$(TELEGRAM_BOT_TOKEN="$TELEGRAM_TOKEN" python3 "$helper" prepare)"; then
    return 1
  fi
  PREPARE_JSON="$prepare_json"
  BOT_USERNAME="$(json_field username <<<"$PREPARE_JSON")"
  [[ "$BOT_USERNAME" =~ ^[A-Za-z0-9_]{5,32}$ ]] || fatal "Telegram returned an invalid bot username"
}

prompt_telegram_token() {
  local helper="$1"
  print_stage "Telegram Bot Token"
  if [[ "$TEST_MODE" == "1" ]]; then
    TELEGRAM_TOKEN="${HERMES_TEST_TELEGRAM_TOKEN:-}"
    [[ -n "$TELEGRAM_TOKEN" ]] || fatal "Telegram token was not provided"
    validate_token_online "$helper" || fatal "Telegram rejected the provided token"
    return
  fi
  local attempt
  for attempt in 1 2 3 4 5; do
    printf 'Paste the token from @BotFather (input is hidden): ' >/dev/tty
    IFS= read -r -s TELEGRAM_TOKEN </dev/tty
    printf '\n' >/dev/tty
    if [[ -z "$TELEGRAM_TOKEN" ]]; then
      warn "Empty token. Attempt ${attempt}/5."
      continue
    fi
    if validate_token_online "$helper" 2>/dev/tty; then
      info "Token accepted - bot @${BOT_USERNAME}."
      return
    fi
    TELEGRAM_TOKEN=""
    warn "Telegram rejected this token. Check O vs 0, l vs 1 and letter case, then try again. Attempt ${attempt}/5."
  done
  fatal "Telegram token was not accepted after 5 attempts"
}

pause_existing_gateway() {
  if [[ "$TEST_MODE" == "1" ]]; then
    return
  fi
  if systemctl is-active --quiet hermes-gateway.service; then
    print_stage "Pause existing Telegram gateway"
    RESTORE_EXISTING_GATEWAY="1"
    systemctl stop hermes-gateway.service
    info "Existing gateway paused so it cannot consume the one-time owner claim."
  fi
}

json_field() {
  local field="$1"
  python3 -c 'import json,sys; value=json.load(sys.stdin); result=value.get(sys.argv[1], ""); print(result)' "$field"
}

configure_telegram() {
  local helper="$1"
  print_stage "Claim Telegram bot ownership"
  [[ -n "$BOT_USERNAME" ]] || fatal "Telegram bot was not validated"

  local claim_payload
  claim_payload="h_$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')"
  info "Open this private claim link and press Start:"
  printf '\033[1;34mhttps://t.me/%s?start=%s\033[0m\n' "$BOT_USERNAME" "$claim_payload"
  info "Waiting for the secure owner claim (up to ${TELEGRAM_CLAIM_TIMEOUT:-600}s)..."

  local claim_json
  claim_json="$(
    TELEGRAM_BOT_TOKEN="$TELEGRAM_TOKEN" \
    TELEGRAM_CLAIM_PAYLOAD="$claim_payload" \
    TELEGRAM_CLAIM_TIMEOUT="${TELEGRAM_CLAIM_TIMEOUT:-600}" \
    python3 "$helper" claim
  )"
  TELEGRAM_OWNER_ID="$(json_field user_id <<<"$claim_json")"
  TELEGRAM_CHAT_ID="$(json_field chat_id <<<"$claim_json")"
  [[ "$TELEGRAM_OWNER_ID" =~ ^[0-9]+$ ]] || fatal "Telegram owner id is invalid"
  [[ "$TELEGRAM_CHAT_ID" =~ ^-?[0-9]+$ ]] || fatal "Telegram chat id is invalid"

  mkdir -p "$HERMES_HOME"
  chmod 700 "$HERMES_HOME"
  TELEGRAM_BOT_TOKEN="$TELEGRAM_TOKEN" \
  TELEGRAM_ALLOWED_USERS="$TELEGRAM_OWNER_ID" \
  TELEGRAM_HOME_CHANNEL="$TELEGRAM_CHAT_ID" \
  HERMES_ENV_PATH="$HERMES_ENV_PATH" \
    python3 "$helper" save-env >/dev/null
  chmod 600 "$HERMES_ENV_PATH"
  info "Telegram owner securely bound to @${BOT_USERNAME}."
}

codex_credentials_present() {
  hermes auth list openai-codex 2>/dev/null | grep -Eq 'openai-codex \([1-9][0-9]* credentials?\)'
}

authorize_codex() {
  print_stage "OpenAI Codex subscription authentication"
  if codex_credentials_present; then
    info "Existing Codex OAuth credential found; reusing it."
    return
  fi
  info "The final interactive step is next. Open the displayed Codex URL and enter its one-time code."
  if [[ "$TEST_MODE" == "1" ]]; then
    hermes auth add openai-codex
  else
    hermes auth add openai-codex </dev/tty
  fi
}

configure_model() {
  print_stage "Hermes model configuration"
  hermes config set model.provider openai-codex
  hermes config set agent.reasoning_effort medium
  hermes config set agent.reasoning_effort_auto.enabled true
}

codex_smoke() {
  local model="$1"
  local output="${TMP_DIR}/codex-smoke-${model}.log"
  hermes chat \
    -q 'Reply with exactly: OK' \
    -m "$model" \
    --provider openai-codex \
    -t safe \
    -Q >"$output" 2>&1
}

verify_codex() {
  print_stage "Codex smoke test"
  if codex_smoke gpt-5.6-terra; then
    SELECTED_MODEL="gpt-5.6-terra"
  else
    warn "gpt-5.6-terra did not respond on this account; trying fallback gpt-5.6-sol..."
    tail -n 10 "${TMP_DIR}/codex-smoke-gpt-5.6-terra.log" >&2 || true
    if codex_smoke gpt-5.6-sol; then
      SELECTED_MODEL="gpt-5.6-sol"
    else
      warn "Fallback smoke test failed. Output follows:"
      tail -n 30 "${TMP_DIR}/codex-smoke-gpt-5.6-sol.log" >&2 || true
      fatal "Neither gpt-5.6-terra nor gpt-5.6-sol is available; Codex authentication or model access failed"
    fi
  fi
  hermes config set model.default "$SELECTED_MODEL"
  info "Codex responded successfully via ${SELECTED_MODEL}."
}

install_gateway() {
  print_stage "Install and start Telegram gateway"
  hermes gateway install --system --run-as-user root --force --start-now --start-on-login
  if [[ "$TEST_MODE" != "1" ]]; then
    sleep 3
  fi
  systemctl is-enabled --quiet hermes-gateway.service
  systemctl is-active --quiet hermes-gateway.service
  hermes gateway status --system --deep
  RESTORE_EXISTING_GATEWAY="0"
}

notify_owner() {
  local helper="$1"
  print_stage "Telegram completion notice"
  local notice
  notice="Hermes встановлено і запущено.

Модель: ${SELECTED_MODEL}
Reasoning: medium + авто
Міст: активний

Спробуй команди: /status, /new, /goal"
  TELEGRAM_BOT_TOKEN="$TELEGRAM_TOKEN" \
  TELEGRAM_HOME_CHANNEL="$TELEGRAM_CHAT_ID" \
  TELEGRAM_NOTIFY_TEXT="$notice" \
    python3 "$helper" notify >/dev/null
}

show_dry_run() {
  cat <<EOF
Hermes VPS installer dry run
Ubuntu: required
Run as: root
Hermes commit: ${HERMES_UPSTREAM_COMMIT}
Provider: openai-codex
Model: gpt-5.6-terra (fallback: gpt-5.6-sol)
Reasoning: medium
Auto-effort: enabled
Gateway: systemd system service, enabled and started
Interactive inputs: Telegram token, Telegram claim link, Codex device link/code
EOF
}

main() {
  require_no_arguments "$@"
  preflight
  if [[ "$DRY_RUN" == "1" ]]; then
    show_dry_run
    return
  fi
  ensure_dependencies
  prepare_temp_files
  install_hermes
  prepare_helper
  prompt_telegram_token "$HELPER_PATH"
  pause_existing_gateway
  configure_telegram "$HELPER_PATH"
  authorize_codex
  configure_model
  verify_codex
  install_gateway
  notify_owner "$HELPER_PATH"

  printf '\n\033[1;32mHermes installation completed successfully.\033[0m\n'
  printf 'Bot: https://t.me/%s\n' "$BOT_USERNAME"
  printf 'Model: %s\n' "$SELECTED_MODEL"
  printf 'Reasoning: medium + auto-effort\n'
  printf 'Gateway: active and enabled on boot\n'
  printf 'Diagnostics: hermes gateway status --system --deep\n'
}

main "$@"
