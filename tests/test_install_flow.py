import json
import os
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
TOKEN = "1234567890:" + ("A" * 35)


def write_executable(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    path.chmod(0o755)


class InstallerFlowTests(unittest.TestCase):
    def test_full_test_mode_flow_uses_only_expected_inputs_and_commands(self):
        with tempfile.TemporaryDirectory() as tmp_raw:
            tmp = Path(tmp_raw)
            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            home = tmp / "root" / ".hermes"
            home.mkdir(parents=True)
            call_log = tmp / "calls.log"

            write_executable(
                bin_dir / "hermes",
                r"""
                #!/usr/bin/env bash
                set -euo pipefail
                printf 'hermes %s\n' "$*" >> "$CALL_LOG"
                if [[ "${1:-}" == "--version" ]]; then
                  echo 'Hermes Agent test-version'
                elif [[ "${1:-}" == "auth" && "${2:-}" == "list" ]]; then
                  echo 'openai-codex (0 credentials):'
                elif [[ "${1:-}" == "auth" && "${2:-}" == "add" ]]; then
                  echo 'Open https://auth.openai.com/codex/device and enter TEST-CODE'
                elif [[ "${1:-}" == "chat" ]]; then
                  echo 'OK'
                elif [[ "${1:-}" == "gateway" && "${2:-}" == "status" ]]; then
                  echo 'gateway active'
                fi
                """,
            )
            write_executable(
                bin_dir / "systemctl",
                r"""
                #!/usr/bin/env bash
                set -euo pipefail
                printf 'systemctl %s\n' "$*" >> "$CALL_LOG"
                case "${1:-}" in
                  is-active|is-enabled) exit 0 ;;
                  *) exit 0 ;;
                esac
                """,
            )

            official = tmp / "official-install.sh"
            write_executable(
                official,
                r"""
                #!/usr/bin/env bash
                set -euo pipefail
                printf 'official %s\n' "$*" >> "$CALL_LOG"
                """,
            )

            helper = tmp / "telegram-helper.py"
            helper.write_text(
                textwrap.dedent(
                    r"""
                    import json
                    import os
                    import stat
                    import sys
                    from pathlib import Path

                    action = sys.argv[1]
                    with open(os.environ["CALL_LOG"], "a", encoding="utf-8") as handle:
                        handle.write(f"helper {action}\n")
                    if action == "prepare":
                        print(json.dumps({"id": 42, "username": "guide_bot"}))
                    elif action == "claim":
                        print(json.dumps({"user_id": "103", "chat_id": "103", "username": "owner", "first_name": "Owner"}))
                    elif action == "save-env":
                        path = Path(os.environ["HERMES_ENV_PATH"])
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text(
                            "TELEGRAM_BOT_TOKEN=" + os.environ["TELEGRAM_BOT_TOKEN"] + "\n"
                            "TELEGRAM_ALLOWED_USERS=" + os.environ["TELEGRAM_ALLOWED_USERS"] + "\n"
                            "TELEGRAM_HOME_CHANNEL=" + os.environ["TELEGRAM_HOME_CHANNEL"] + "\n",
                            encoding="utf-8",
                        )
                        path.chmod(0o600)
                        print(json.dumps({"saved": True}))
                    elif action == "notify":
                        print(json.dumps({"sent": True}))
                    else:
                        raise SystemExit(2)
                    """
                ).lstrip(),
                encoding="utf-8",
            )

            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{bin_dir}:{env['PATH']}",
                    "CALL_LOG": str(call_log),
                    "HERMES_HOME": str(home),
                    "HERMES_INSTALLER_TEST_MODE": "1",
                    "HERMES_TEST_TELEGRAM_TOKEN": TOKEN,
                    "HERMES_INSTALLER_OFFICIAL_PATH": str(official),
                    "HERMES_INSTALLER_HELPER_PATH": str(helper),
                    "TELEGRAM_CLAIM_TIMEOUT": "2",
                }
            )

            result = subprocess.run(
                ["bash"],
                input=(REPO / "install.sh").read_text(encoding="utf-8"),
                cwd=REPO,
                env=env,
                text=True,
                capture_output=True,
                timeout=30,
            )

            combined = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, combined)
            self.assertNotIn(TOKEN, combined)
            calls = call_log.read_text(encoding="utf-8")
            self.assertNotIn(TOKEN, calls)
            self.assertIn("official --skip-setup --non-interactive", calls)
            self.assertIn("--commit e4ea0a0ed7fc24761b2b425146893561a73216e1", calls)
            self.assertIn("helper prepare", calls)
            self.assertIn("helper claim", calls)
            self.assertIn("helper save-env", calls)
            self.assertIn("hermes auth add openai-codex", calls)
            self.assertIn("hermes config set model.default gpt-5.6-terra", calls)
            self.assertIn("hermes config set agent.reasoning_effort medium", calls)
            self.assertIn("hermes config set agent.reasoning_effort_auto.enabled true", calls)
            self.assertIn(
                "hermes gateway install --system --run-as-user root --force --start-now --start-on-login",
                calls,
            )
            self.assertIn("systemctl is-active --quiet hermes-gateway.service", calls)
            self.assertIn("helper notify", calls)

            env_file = home / ".env"
            self.assertTrue(env_file.exists())
            self.assertEqual(stat.S_IMODE(env_file.stat().st_mode), 0o600)
            self.assertIn("TELEGRAM_ALLOWED_USERS=103", env_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
