import unittest
import io

from PIL import Image

from services.ocr_service import _extract_json_dict_from_text, _optimize_image_for_ocr, _postprocess_leave_fields


class LlmJsonExtractionTest(unittest.TestCase):
    def test_extracts_json_after_reasoning_text(self):
        text = '我们先分析发票字段。最终结果如下：{"amount":"48.06","invoice_no":"123"}'
        self.assertEqual(
            _extract_json_dict_from_text(text),
            {'amount': '48.06', 'invoice_no': '123'},
        )

    def test_returns_none_when_only_reasoning_without_json(self):
        text = '我们根据OCR文本提取信息。文档类型是reimbursement。字段定义中有多个字段。'
        self.assertIsNone(_extract_json_dict_from_text(text))

    def test_extracts_json_code_block(self):
        text = '```json\n{"date":"2026-06-01"}\n```'
        self.assertEqual(_extract_json_dict_from_text(text), {'date': '2026-06-01'})

    def test_leave_type_maps_unknown_to_personal_leave(self):
        fixed = _postprocess_leave_fields({'leave_type': '婚假'}, '请假申请')
        self.assertEqual(fixed.get('leave_type'), '事假')

    def test_leave_type_infers_other_leave_from_raw_text(self):
        fixed = _postprocess_leave_fields({}, '请假类型：婚假\n请假事由：办理结婚登记')
        self.assertEqual(fixed.get('leave_type'), '事假')

    def test_leave_type_keeps_public_leave(self):
        fixed = _postprocess_leave_fields({'leave_type': '公假'}, '请假申请')
        self.assertEqual(fixed.get('leave_type'), '公假')

    def test_optimizes_large_image_for_ocr(self):
        image = Image.new('RGB', (4000, 2400), 'white')
        buf = io.BytesIO()
        image.save(buf, format='PNG')

        optimized, mime = _optimize_image_for_ocr(buf.getvalue(), max_side=1600)

        self.assertEqual(mime, 'image/jpeg')
        out = Image.open(io.BytesIO(optimized))
        self.assertLessEqual(max(out.size), 1600)


if __name__ == '__main__':
    unittest.main()
