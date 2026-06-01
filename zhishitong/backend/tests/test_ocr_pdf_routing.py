import unittest
from unittest.mock import AsyncMock, patch

from services.ocr_service import OCRProvider, ocr_with_tier


class PdfTextRoutingTest(unittest.IsolatedAsyncioTestCase):
    async def test_text_pdf_uses_json_fill_not_multimodal_llm(self):
        pdf_text = '报销申请单 申请人：张三 金额：123 元 事由：资料打印费用'

        async def fake_fill(raw_text, fill_api_key='', fill_api_base='', fill_model='', document_type=None):
            self.assertEqual(raw_text, pdf_text)
            self.assertEqual(fill_api_key, 'json-key')
            return {'amount': '123'}

        with (
            patch('services.ocr_service.extract_pdf_text', return_value=pdf_text),
            patch('services.ocr_service._fill_with_best', side_effect=fake_fill),
            patch('services.ocr_service.llm_multimodal_ocr', new=AsyncMock()) as multimodal_mock,
        ):
            raw, provider, filled = await ocr_with_tier(
                b'%PDF text layer',
                tier='pro',
                llm_quota_remaining=10,
                mime_type='application/pdf',
                api_base='https://ocr.example',
                api_key='multimodal-key',
                model='qwen-vl',
                fill_api_base='https://json.example',
                fill_api_key='json-key',
                fill_model='qwen-plus',
            )

        self.assertEqual(raw, pdf_text)
        self.assertEqual(provider, OCRProvider.PDF_TEXT)
        self.assertEqual(filled, {'amount': '123'})
        multimodal_mock.assert_not_called()


if __name__ == '__main__':
    unittest.main()
