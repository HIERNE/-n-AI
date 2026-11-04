import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import logging_config


class ActivityLogTests(unittest.TestCase):
    def test_activity_events_are_written_as_json_without_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            logger_name = "smart_invoice_parser.test"
            logger = logging.getLogger(logger_name)
            for handler in logger.handlers[:]:
                logger.removeHandler(handler)
                handler.close()

            with patch.object(logging_config, "_LOG_DIRECTORY", Path(directory)), patch.object(
                logging_config, "_APP_LOGGER_NAME", logger_name
            ):
                logging_config.log_activity(
                    "login_succeeded",
                    user_id=42,
                    resource_type="invoice",
                    resource_id=7,
                    status="confirmed",
                )
                for handler in logger.handlers:
                    handler.flush()
                    handler.close()
                    logger.removeHandler(handler)

            lines = (Path(directory) / "app.log").read_text(
                encoding="utf-8"
            ).splitlines()
            self.assertEqual(len(lines), 1)
            event = json.loads(lines[0].split("ACTIVITY ", 1)[1])
            self.assertEqual(event, {
                "action": "login_succeeded",
                "user_id": 42,
                "resource_type": "invoice",
                "resource_id": 7,
                "status": "confirmed",
            })
            self.assertNotIn("password", lines[0].lower())


if __name__ == "__main__":
    unittest.main()
