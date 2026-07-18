# Hermes Ubuntu VPS Installer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Опубликовать проверенный одно-командный установщик Hermes для Ubuntu VPS с Telegram token prompt, безопасной привязкой владельца, Codex OAuth, `gpt-5.6-terra`, `medium` reasoning, auto-effort и автоматически запущенным root systemd gateway.

**Architecture:** Самодостаточный `install.sh` оркестрирует официальный pinned Hermes installer, конфигурацию и systemd. Секретный Telegram token передаётся только через окружение отдельному Python helper `lib/telegram_claim.py`; helper валидирует Bot API, выполняет deep-link claim и атомарно обновляет `.env`. Shell и Python функции покрываются unit/static/integration тестами; реальная Terra проверяется через текущий валидный Codex OAuth, а Ubuntu install/service flow — в изолированном окружении.

**Tech Stack:** Bash 4+, Python 3 stdlib, Telegram Bot HTTP API, Hermes CLI, systemd, unittest, shellcheck, Git/GitHub Actions.

## Global Constraints

- Поддерживается Ubuntu VPS с systemd; запуск установщика и gateway от `root`.
- Никаких setup/model/gateway меню: только Telegram token, Telegram deep-link Start и Codex device login.
- Provider `openai-codex`; model `gpt-5.6-terra`; base effort `medium`; auto-effort enabled.
- Telegram token нельзя печатать, передавать CLI-аргументом или сохранять с правами шире `0600`.
- Нельзя включать `GATEWAY_ALLOW_ALL_USERS`, YOLO или approval bypass.
- Gateway должен запускаться сразу и включаться на boot.
- Нельзя молча подменять Terra другой моделью.
- Completion claims требуют свежих тестов, live raw-URL fetch и проверки опубликованного SHA-256.

---

### Task 1: Telegram helper, тесты token/claim/env

**Files:**
- Create: `lib/telegram_claim.py`
- Create: `tests/test_telegram_claim.py`

**Interfaces:**
- Produces: `validate_token(token)`, `TelegramClient`, `claim_owner(client, payload, timeout_seconds)`, `upsert_env(path, values)`, CLI actions `prepare`, `claim`, `save-env`, `notify`.
- Consumes: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS`, `TELEGRAM_HOME_CHANNEL`, optional test-only `TELEGRAM_API_BASE`.

- [ ] **Step 1: Write failing tests** for valid/invalid token formats, webhook rejection, ignoring stale/non-private/wrong claim messages, accepting exact `/start <payload>`, preserving unrelated `.env` keys, and mode `0600`.
- [ ] **Step 2: Run RED** with `python3 -m unittest -v tests.test_telegram_claim`; expected failure is missing `lib.telegram_claim`.
- [ ] **Step 3: Implement minimal helper** using `urllib.request`, bounded long polling, `secrets.compare_digest`, JSON-only non-secret stdout, `tempfile.mkstemp` + `os.replace`, and no third-party packages.
- [ ] **Step 4: Run GREEN** with `python3 -m unittest -v tests.test_telegram_claim`; expected all tests pass.
- [ ] **Step 5: Commit** as `feat: add secure Telegram owner claim helper`.

### Task 2: Installer orchestration with strict shell tests

**Files:**
- Create: `install.sh`
- Create: `tests/test_static.sh`
- Create: `tests/test_install_flow.py`

**Interfaces:**
- Consumes helper CLI from Task 1.
- Produces one executable root installer; supports test-only `HERMES_INSTALLER_DRY_RUN=1`, `HERMES_INSTALLER_HELPER_PATH`, `HERMES_INSTALLER_OFFICIAL_URL`, and command shims through `PATH`.

- [ ] **Step 1: Write failing static/flow tests** asserting Bash syntax target, root/Ubuntu/systemd preflight, `/dev/tty` secret read, pinned official commit, exact Hermes config commands, root system service command, no allow-all/YOLO, helper download pin, stage failure propagation and no secret in argv/output.
- [ ] **Step 2: Run RED** with `bash tests/test_static.sh && python3 -m unittest -v tests.test_install_flow`; expected failure because `install.sh` is absent.
- [ ] **Step 3: Implement minimal installer** with `set -Eeuo pipefail`, stage logging, cleanup trap, apt preflight, pinned official installer, token prompt, helper prepare/claim/save, Codex credential detection/login, exact config, Terra smoke test, systemd install/status and Telegram completion notification.
- [ ] **Step 4: Run GREEN** with static and flow tests; expected all pass and no token leakage in captured output/process arguments.
- [ ] **Step 5: Refactor** duplicated command/error handling while keeping tests green.
- [ ] **Step 6: Commit** as `feat: add one-command Ubuntu installer`.

### Task 3: Public docs, release UX and CI

**Files:**
- Create: `README.md`
- Create: `LICENSE`
- Create: `.github/workflows/ci.yml`
- Modify: `docs/superpowers/specs/2026-07-18-hermes-vps-installer-design.md`

**Interfaces:**
- Produces stable tagged command and troubleshooting/uninstall commands.

- [ ] **Step 1: Write README acceptance checker** in `tests/test_static.sh` requiring the tagged one-line command, explicit root warning, BotFather steps, exact model/reasoning settings, diagnostic commands and no example real token.
- [ ] **Step 2: Run RED**; expected failure because README/CI/license are absent.
- [ ] **Step 3: Add README, MIT license and CI** running `bash -n`, shellcheck, Python unittest and static tests on Ubuntu.
- [ ] **Step 4: Run GREEN** locally and validate YAML syntax.
- [ ] **Step 5: Commit** as `docs: add installer guide and CI`.

### Task 4: Isolated and live verification

**Files:**
- Create: `tests/mock_telegram_server.py`
- Create: `tests/run_isolated.sh`
- Create: `docs/verification.md`

**Interfaces:**
- Produces repeatable verification report without recording credentials.

- [ ] **Step 1: Add failing integration test** that runs helper against a local Bot API mock and installer flow against command shims, including wrong claim then correct claim.
- [ ] **Step 2: Run RED**, confirm failure before mock/integration implementation.
- [ ] **Step 3: Implement mock server and isolated runner**; no external secrets.
- [ ] **Step 4: Run full local suite**: `bash -n install.sh`, `shellcheck install.sh`, `python3 -m unittest discover -s tests -v`, `bash tests/test_static.sh`, `bash tests/run_isolated.sh`.
- [ ] **Step 5: Run real Codex Terra smoke test** on the current authenticated host with explicit `gpt-5.6-terra` and record only status/output, never tokens.
- [ ] **Step 6: Run safe live Telegram `getMe` prepare check** against the currently configured bot without calling `getUpdates` or changing gateway state; record redacted result.
- [ ] **Step 7: Exercise official install + service path** in an available disposable Ubuntu environment. If no nested systemd runtime is available, verify official install in a container and service-unit behavior through command shims, then state the exact limitation instead of claiming full systemd E2E.
- [ ] **Step 8: Write `docs/verification.md`** with commands, dates, exit statuses and any honest limitations.
- [ ] **Step 9: Commit** as `test: verify installer flow`.

### Task 5: GitHub publication and remote verification

**Files:**
- Modify only if remote verification finds a regression.

**Interfaces:**
- Produces `https://github.com/sunstrike228/hermes-vps-installer`, tag/release `v1.0.0`, and stable raw installer URL.

- [ ] **Step 1: Run full suite immediately before publication** and require zero failures.
- [ ] **Step 2: Create public GitHub repository** from the existing local repo, set description/topics, and push `main`.
- [ ] **Step 3: Confirm GitHub Actions passes**; inspect failed logs and fix via TDD if needed.
- [ ] **Step 4: Create signed/annotated tag and GitHub release `v1.0.0`** only after CI passes.
- [ ] **Step 5: Fetch tagged `install.sh` and helper from `raw.githubusercontent.com`**, run `bash -n`, compare their SHA-256 to local files and verify helper reference resolves to the same tag.
- [ ] **Step 6: Test the exact user-facing command in dry-run/isolation mode** from the published URL.
- [ ] **Step 7: Report the tested command, repository, SHA-256, evidence, remaining limitations and root-risk warning.**
