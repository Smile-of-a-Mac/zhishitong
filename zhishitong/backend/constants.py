"""
共享常量 — 文档类型标签映射，全项目唯一来源
"""
from typing import Optional

DOC_TYPE_LABELS: dict[str, str] = {
    "reimbursement": "报销申请",
    "leave": "请假申请",
    "club_application": "社团活动申请",
    "classroom_booking": "教室借用",
    "business_trip": "出差申请",
    "seal_application": "用章申请",
    "dorm_change": "宿舍调换",
    "scholarship": "奖学金申请",
    "suspend_resume": "休学/复学",
    "enrollment_proof": "在读证明",
    "abroad_application": "因公出国",
    "onboarding": "入职报到",
    "office_supplies": "办公用品领用",
    "book_purchase": "图书采购",
}


def get_doc_label(doc_type: Optional[str]) -> str:
    """文档类型 → 中文标签（唯一入口）"""
    if not doc_type:
        return "未知事务"
    return DOC_TYPE_LABELS.get(doc_type, doc_type)
