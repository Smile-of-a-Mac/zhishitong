"""
事务审批流程定义

每个事务类型的多阶段审批流程。
"""
from typing import Optional

# 阶段配置：每个事务类型的审批阶段顺序
WORKFLOWS: dict[str, dict] = {
    "reimbursement": {
        "label": "报销申请",
        "stages": [
            {"key": "dept_review",    "label": "部门审批",    "role": "dept_admin"},
            {"key": "finance_review", "label": "财务审批",    "role": "finance_admin"},
            {"key": "school_review",  "label": "学校审批",    "role": "school_admin"},
        ],
        # 条件跳过规则：如果金额 ≤ 5000，跳过 school_review
        "skip_rules": {
            "school_review": lambda data: _amount_le(data, 5000),
        },
    },
    "leave": {
        "label": "请假申请",
        "stages": [
            {"key": "dept_review",    "label": "学院/辅导员审批", "role": "dept_admin"},
        ],
        "skip_rules": {},
    },
    "club_application": {
        "label": "社团活动申请",
        "stages": [
            {"key": "dept_review",    "label": "学院/指导老师审批", "role": "dept_admin"},
            {"key": "school_review",  "label": "学校/团委审批",    "role": "school_admin"},
        ],
        "skip_rules": {},
    },
    # ===== 山科大实际流程 =====
    "transcript_print": {
        "label": "成绩单打印",
        "stages": [
            {"key": "dept_review",    "label": "学院审核",   "role": "dept_admin"},
            {"key": "school_review",  "label": "教务处办理", "role": "school_admin"},
        ],
        "skip_rules": {},
    },
    "diploma_verification": {
        "label": "学历学位证明",
        "stages": [
            {"key": "dept_review",    "label": "学院审核",   "role": "dept_admin"},
            {"key": "school_review",  "label": "教务处办理", "role": "school_admin"},
        ],
        "skip_rules": {},
    },
    "exam_review": {
        "label": "试卷查阅",
        "stages": [
            {"key": "dept_review",    "label": "教务管理审核", "role": "dept_admin"},
        ],
        "skip_rules": {},
    },
    "class_reschedule": {
        "label": "调停课申请",
        "stages": [
            {"key": "dept_review",    "label": "学院审核",   "role": "dept_admin"},
            {"key": "school_review",  "label": "教务处审批", "role": "school_admin"},
        ],
        "skip_rules": {},
    },
    "makeup_exam": {
        "label": "缓考/补考申请",
        "stages": [
            {"key": "dept_review",    "label": "学院审核",   "role": "dept_admin"},
            {"key": "school_review",  "label": "教务处审批", "role": "school_admin"},
        ],
        "skip_rules": {},
    },
    "enrollment_proof": {
        "label": "在读证明申请",
        "stages": [
            {"key": "dept_review",    "label": "学院审核",   "role": "dept_admin"},
            {"key": "school_review",  "label": "教务处办理", "role": "school_admin"},
        ],
        "skip_rules": {},
    },
    "suspend_resume": {
        "label": "休学/复学申请",
        "stages": [
            {"key": "dept_review",    "label": "学院审核",           "role": "dept_admin"},
            {"key": "school_review",  "label": "教务处/研究生院审批", "role": "school_admin"},
        ],
        "skip_rules": {},
    },
    "scholarship": {
        "label": "奖学金申请",
        "stages": [
            {"key": "dept_review",    "label": "学院评审", "role": "dept_admin"},
            {"key": "school_review",  "label": "学校评审", "role": "school_admin"},
        ],
        "skip_rules": {},
    },
}


def get_workflow(doc_type: Optional[str]) -> dict:
    return WORKFLOWS.get(doc_type or "", {})


def get_stages(doc_type: Optional[str], filled_data: dict | None = None) -> list[dict]:
    """获取事务的完整审批阶段列表（已处理跳过规则）"""
    wf = get_workflow(doc_type)
    stages = list(wf.get("stages", []))
    if not stages:
        # 兜底：至少有一个部门审批
        return [{"key": "dept_review", "label": "部门审批", "role": "dept_admin"}]

    skip_rules = wf.get("skip_rules", {})
    if filled_data:
        result = []
        for s in stages:
            rule = skip_rules.get(s["key"])
            if rule and rule(filled_data):
                # 标记为已跳过，不加入列表
                continue
            result.append(s)
        return result
    return stages


def get_first_stage(doc_type: Optional[str], filled_data: dict | None = None) -> str:
    stages = get_stages(doc_type, filled_data)
    return stages[0]["key"] if stages else "dept_review"


def get_next_stage(doc_type: Optional[str], current: str, filled_data: dict | None = None) -> Optional[str]:
    """获取下一个待审批阶段"""
    stages = get_stages(doc_type, filled_data)
    for i, s in enumerate(stages):
        if s["key"] == current and i + 1 < len(stages):
            return stages[i + 1]["key"]
    return None


def get_stage_label(doc_type: Optional[str], stage_key: str) -> str:
    wf = get_workflow(doc_type)
    for s in wf.get("stages", []):
        if s["key"] == stage_key:
            return s["label"]
    return stage_key


def get_stage_role(doc_type: Optional[str], stage_key: str) -> Optional[str]:
    wf = get_workflow(doc_type)
    for s in wf.get("stages", []):
        if s["key"] == stage_key:
            return s.get("role")
    return None


# ===== 跳过规则辅助函数 =====

def _amount_le(data: dict, limit: float) -> bool:
    try:
        return float(data.get("amount", 0)) <= limit
    except (ValueError, TypeError):
        return False



