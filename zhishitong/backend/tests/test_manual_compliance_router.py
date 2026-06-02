import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from routers.rag_router import ManualComplianceRequest, manual_compliance


class ManualComplianceRouterTest(unittest.IsolatedAsyncioTestCase):
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
