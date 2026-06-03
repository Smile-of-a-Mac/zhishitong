import unittest
import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from routers.rag_router import IntentRequest, ManualComplianceRequest, manual_compliance, parse_intent
from services.rag_service import parse_intent as svc_parse_intent


class ManualComplianceRouterTest(unittest.IsolatedAsyncioTestCase):
    async def test_intent_passes_current_user_as_account_context(self):
        user = SimpleNamespace(
            id=7,
            username="sdu_student_a",
            real_name="王小明",
            student_id="20240001",
            department="计算机学院",
            school="山东科技大学",
            major="软件工程",
            class_name="软工2401",
            phone="13800000000",
            advisor="李老师",
        )
        db = object()
        expected = {
            "document_type": "leave",
            "doc_label": "请假申请",
            "confidence": 0.9,
            "prefill_fields": {"applicant": "王小明"},
        }

        with patch("services.rag_service.parse_intent", AsyncMock(return_value=expected)) as mocked:
            result = await parse_intent(IntentRequest(text="我明天请一天病假"), current_user=user, db=db)

        self.assertEqual(result, expected)
        mocked.assert_awaited_once_with("我明天请一天病假", db, current_user=user)

    async def test_intent_prefill_uses_only_target_template_fields(self):
        user = SimpleNamespace(
            username="sdu_student_a",
            real_name="王小明",
            student_id="20240001",
            department="计算机学院",
            school="山东科技大学",
            major="软件工程",
            class_name="软工2401",
            phone="13800000000",
            email="student@example.com",
            advisor="李老师",
        )
        raw = '{"document_type":"leave","confidence":0.9,"prefill_fields":{"reason":"病假"}}'

        with patch("services.rag_service._call_llm", AsyncMock(return_value=raw)):
            result = await svc_parse_intent("我要请病假", current_user=user)

        fields = result["prefill_fields"]
        self.assertEqual(fields["applicant"], "王小明")
        self.assertEqual(fields["student_id"], "20240001")
        self.assertEqual(fields["college"], "计算机学院")
        self.assertEqual(fields["class_name"], "软工2401")
        self.assertEqual(fields["phone"], "13800000000")
        self.assertEqual(fields["advisor"], "李老师")
        self.assertEqual(fields["reason"], "病假")
        self.assertNotIn("department", fields)
        self.assertNotIn("school", fields)
        self.assertNotIn("email", fields)

    async def test_intent_does_not_use_current_account_for_other_applicant(self):
        user = SimpleNamespace(
            username="sdu_student_a",
            real_name="王小明",
            student_id="20240001",
            department="计算机学院",
            class_name="软工2401",
            phone="13800000000",
        )
        raw = '{"document_type":"leave","confidence":0.9,"prefill_fields":{"applicant":"李四","reason":"病假"}}'

        with patch("services.rag_service._call_llm", AsyncMock(return_value=raw)):
            result = await svc_parse_intent("帮李四填一个明天病假的请假申请", current_user=user)

        fields = result["prefill_fields"]
        self.assertEqual(fields["applicant"], "李四")
        self.assertEqual(fields["reason"], "病假")
        self.assertNotIn("student_id", fields)
        self.assertNotIn("phone", fields)

    async def test_intent_prompt_includes_real_template_field_contract(self):
        captured = {}

        async def fake_llm(prompt, *args, **kwargs):
            captured["prompt"] = prompt
            return '{"document_type":"leave","confidence":0.8,"prefill_fields":{}}'

        with patch("services.rag_service._call_llm", fake_llm):
            await svc_parse_intent("我要请假")

        prompt = captured["prompt"]
        self.assertIn('"leave"', prompt)
        self.assertIn("合法事务类型 key", prompt)
        self.assertIn("reimbursement", prompt)
        self.assertIn("prefill_fields", prompt)

    async def test_intent_rule_fill_handles_relative_leave_travel_details(self):
        user = SimpleNamespace(
            username="sdu_student_a",
            real_name="王小明",
            student_id="20240001",
            department="计算机学院",
            school="山东科技大学",
            major="软件工程",
            class_name="软工2401",
            phone="13800000000",
            advisor="李老师",
        )
        raw = '{"document_type":"leave","confidence":0.95,"prefill_fields":{"reason":"去滨州调研"}}'

        class FixedDate(datetime.date):
            @classmethod
            def today(cls):
                return cls(2026, 6, 3)

        with patch("services.rag_service._call_llm", AsyncMock(return_value=raw)), \
             patch("services.rag_service.datetime.date", FixedDate):
            result = await svc_parse_intent(
                "我导师叫我去滨州调研，我明后两天都不在学校，我坐长途汽车去，帮我请个假",
                current_user=user,
            )

        fields = result["prefill_fields"]
        self.assertEqual(result["document_type"], "leave")
        self.assertEqual(fields["leave_type"], "公假")
        self.assertEqual(fields["destination"], "滨州")
        self.assertEqual(fields["transportation"], "长途汽车")
        self.assertEqual(fields["start_date"], "2026-06-04")
        self.assertEqual(fields["end_date"], "2026-06-05")

    async def test_checks_manual_fields_without_creating_approval_record(self):
        user = SimpleNamespace(
            id=7,
            is_admin=False,
            is_school_admin=False,
            is_dept_admin=False,
            is_finance_admin=False,
        )
        db = object()
        expected = {
            "risk_level": "low",
            "compliance_summary": "基本合规",
            "compliance_items": [],
            "suggestions": ["提交前确认发票号码无误"],
            "policy_hits": [],
        }
        body = ManualComplianceRequest(
            document_type="reimbursement",
            fields={"amount": "48.06", "invoice_number": "INV-001"},
        )

        with patch("services.rag_service.check_compliance", AsyncMock(return_value=expected)) as mocked:
            result = await manual_compliance(body, current_user=user, db=db)

        self.assertEqual(result, expected)
        mocked.assert_awaited_once()
        form_json, doc_type, used_db = mocked.call_args.args
        self.assertEqual(doc_type, "reimbursement")
        self.assertIs(used_db, db)
        self.assertEqual(form_json["amount"], "48.06")
        self.assertEqual(form_json["invoice_no"], "INV-001")

    async def test_rejects_admin_accounts(self):
        user = SimpleNamespace(
            id=1,
            is_admin=True,
            is_school_admin=False,
            is_dept_admin=False,
            is_finance_admin=False,
        )
        body = ManualComplianceRequest(document_type="leave", fields={"reason": "病假"})

        with self.assertRaises(HTTPException) as ctx:
            await manual_compliance(body, current_user=user, db=object())

        self.assertEqual(ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
