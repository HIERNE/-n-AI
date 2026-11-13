import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.structuring import llm_extractor


class LlmProviderTimingTests(unittest.TestCase):
    def test_logs_successful_gemini_attempt_without_logging_prompt(self):
        client = Mock()
        client.models.generate_content.return_value = SimpleNamespace(text="{}")

        with (
            patch.object(llm_extractor, "GEMINI_API_KEYS", ["test-key"]),
            patch.object(llm_extractor.genai, "Client", return_value=client),
            patch.object(llm_extractor, "_generate_xai_content") as xai_fallback,
            self.assertLogs("src.structuring.llm_extractor", level="INFO") as logs,
        ):
            result = llm_extractor._generate_content("private invoice OCR text")

        self.assertEqual(result, "{}")
        xai_fallback.assert_not_called()
        self.assertTrue(
            any(
                "provider=gemini attempt=1 status=success" in line
                for line in logs.output
            )
        )
        self.assertFalse(any("private invoice OCR text" in line for line in logs.output))


if __name__ == "__main__":
    unittest.main()
