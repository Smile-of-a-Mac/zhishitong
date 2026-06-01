import unittest

from routers.ocr_router import _model_used_for_provider
from services.key_pool import ResolvedKey
from services.ocr_service import OCRProvider


class OcrRouterLoggingTest(unittest.TestCase):
    def test_pdf_text_reports_json_fill_model(self):
        ocr_cfg = ResolvedKey(
            key_id=1,
            api_base="https://ocr.example",
            api_key="ocr-key",
            model="mimo-v2.5",
        )
        fill_cfg = ResolvedKey(
            key_id=2,
            api_base="https://json.example",
            api_key="json-key",
            model="deepseek-v4-flash",
        )

        used_model = _model_used_for_provider(OCRProvider.PDF_TEXT, ocr_cfg, fill_cfg)

        self.assertEqual(used_model, "deepseek-v4-flash")

    def test_llm_reports_ocr_model(self):
        ocr_cfg = ResolvedKey(
            key_id=1,
            api_base="https://ocr.example",
            api_key="ocr-key",
            model="mimo-v2.5",
        )
        fill_cfg = ResolvedKey(
            key_id=2,
            api_base="https://json.example",
            api_key="json-key",
            model="deepseek-v4-flash",
        )

        used_model = _model_used_for_provider(OCRProvider.LLM, ocr_cfg, fill_cfg)

        self.assertEqual(used_model, "mimo-v2.5")


if __name__ == "__main__":
    unittest.main()
