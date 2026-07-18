import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.mock_telegram_server import MockTelegramServer


REPO = Path(__file__).resolve().parents[1]
HELPER = REPO / "lib" / "telegram_claim.py"
TOKEN = "1234567890:" + ("A" * 35)
PAYLOAD = "claim_Integration123"


class MockTelegramApiIntegrationTests(unittest.TestCase):
    def test_helper_cli_prepares_claims_saves_and_notifies_without_exposing_token(self):
        with MockTelegramServer(token=TOKEN, claim_payload=PAYLOAD) as server:
            base_env = os.environ.copy()
            base_env.update(
                {
                    "TELEGRAM_BOT_TOKEN": TOKEN,
                    "TELEGRAM_API_BASE": server.base_url,
                    "HERMES_INSTALLER_TEST_MODE": "1",
                }
            )

            prepared = subprocess.run(
                ["python3", str(HELPER), "prepare"],
                env=base_env,
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            self.assertEqual(json.loads(prepared.stdout)["username"], "integration_bot")
            self.assertNotIn(TOKEN, prepared.stdout + prepared.stderr)

            claim_env = base_env | {
                "TELEGRAM_CLAIM_PAYLOAD": PAYLOAD,
                "TELEGRAM_CLAIM_TIMEOUT": "5",
            }
            claimed = subprocess.run(
                ["python3", str(HELPER), "claim"],
                env=claim_env,
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
            )
            self.assertEqual(claimed.returncode, 0, claimed.stderr)
            owner = json.loads(claimed.stdout)
            self.assertEqual(owner["user_id"], "777")
            self.assertNotIn(TOKEN, claimed.stdout + claimed.stderr)

            with tempfile.TemporaryDirectory() as tmp:
                env_path = Path(tmp) / ".env"
                save_env = claim_env | {
                    "HERMES_ENV_PATH": str(env_path),
                    "TELEGRAM_ALLOWED_USERS": owner["user_id"],
                    "TELEGRAM_HOME_CHANNEL": owner["chat_id"],
                }
                saved = subprocess.run(
                    ["python3", str(HELPER), "save-env"],
                    env=save_env,
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=10,
                )
                self.assertEqual(saved.returncode, 0, saved.stderr)
                self.assertEqual(stat.S_IMODE(env_path.stat().st_mode), 0o600)

            notice_env = claim_env | {
                "TELEGRAM_HOME_CHANNEL": owner["chat_id"],
                "TELEGRAM_NOTIFY_TEXT": "integration complete",
            }
            notified = subprocess.run(
                ["python3", str(HELPER), "notify"],
                env=notice_env,
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
            )
            self.assertEqual(notified.returncode, 0, notified.stderr)
            self.assertEqual(server.sent_messages, [("777", "integration complete")])
            self.assertNotIn(TOKEN, notified.stdout + notified.stderr)


if __name__ == "__main__":
    unittest.main()
