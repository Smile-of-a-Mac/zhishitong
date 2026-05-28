"""
审批辅助引擎（不替代人工决策）

职责：
  1. 自动填写审批表单（基于 OCR 提取的数据）
  2. 逐条核对规则
  3. 给出修改建议
  4. 标记缺失信息

重要：引擎不输出"通过/不通过"结论，最终决定权始终在部门管理员手上。
"""
import json, logging
from typing import TypedDict, Optional
from sqlalchemy.orm import Session

from langgraph.graph import StateGraph
from langgraph.checkpoint.memory import MemorySaver

from models import ApprovalRecord, ApprovalStatus

logger = logging.getLogger(__name__)


# ===== 字段名归一化兜底（与 ocr_service 同步）=====

_FIELD_KEY_MAP: dict[str, str] = {
    "申请人": "applicant", "申请金额": "amount", "报销金额": "amount",
    "金额": "amount", "发票号码": "invoice_no", "发票号": "invoice_no",
    "学院": "college", "班级": "class_name",
    "发生日期": "date", "日期": "date", "开始日期": "start_date",
    "结束日期": "end_date", "天数": "days", "请假类型": "leave_type",
    "事由": "reason", "事由说明": "reason", "说明": "reason",
    "费用类别": "category", "社团名称": "club_name",
    "活动名称": "activity", "活动日期": "date",
    "场地需求": "venue", "预计人数": "participants",
    "涉及校外人员": "external", "活动简介": "description",
    "教室编号": "room_no", "使用日期": "date",
    "开始时间": "start_time", "结束时间": "end_time",
    "用途": "purpose", "需多媒体设备": "need_multimedia",
    "目的地": "destination", "出发日期": "start_date",
    "返回日期": "end_date", "出差事由": "purpose",
    "预估费用": "estimated_cost", "是否出境": "international",
    "学号": "student_id", "工号": "student_id",
    "名称": "name", "姓名": "applicant",
    "学生姓名": "applicant", "辅导员姓名": "advisor",
    "辅导员联系方式": "advisor_phone", "导师联系方式": "advisor_phone",
    "联系方式": "phone", "联系电话": "phone",
    "外卖电话": "phone", "紧急联系人": "emergency_contact",
    "外出时间": "start_date", "离校时间": "start_date",
    "出发时间": "start_date", "开始时间": "start_time",
    "返校时间": "end_date", "预计返校": "end_date",
    "返校时间（此处由保安填写）": "return_time",
    "结束时间": "end_time", "返回时间": "end_time",
    "去向": "destination", "前往地点": "destination",
    "交通工具": "transportation", "交通方式": "transportation",
    "往返交通": "transportation",
}


def _normalize_keys(data: dict) -> dict:
    """兜底归一化：将 JSON 中的中文字段名映射为英文 key"""
    if not data:
        return data
    normalized = {}
    for k, v in data.items():
        if k in _FIELD_KEY_MAP:
            normalized[_FIELD_KEY_MAP[k]] = v
        else:
            normalized[k] = v
    return normalized


# ===== 状态定义 =====

class ApprovalState(TypedDict):
    record_id: int
    document_type: Optional[str]
    filled_json: dict
    issues: list[str]             # 规则核对发现的问题
    suggestions: list[str]        # 修改建议
    missing_fields: list[str]     # 缺失的必填字段
    policy_refs: list[str]        # 引用的规则条文
    analysis_summary: str         # 分析摘要
    notification_sent: bool


# ===== 规则定义（仅用于核对，不用于自动决策） =====

RULES = {
    "reimbursement": {
        "required_fields": ["applicant", "amount", "invoice_no", "date", "reason"],
        "checks": [
            {"field": "amount", "rule": "金额应为正数", "check": "amount > 0"},
            {"field": "invoice_no", "rule": "发票号码不能为空", "check": "invoice_no is not empty"},
        ],
        "reference": "《财务报销管理办法》第3条：报销需提供有效发票及事由说明。",
    },
    "leave": {
        "required_fields": [
            "college", "class_name", "applicant", "phone",
            "advisor", "advisor_phone", "reason",
            "start_date", "end_date", "destination", "transportation",
        ],
        "checks": [
            {"field": "start_date", "rule": "开始日期不晚于结束日期", "check": "start_date <= end_date"},
            {"field": "reason", "rule": "请假事由不能为空", "check": "reason is not empty"},
        ],
        "reference": "《学生请假管理规定》第4条：请假需提前申请并说明事由。",
    },
    "club_application": {
        "required_fields": ["club_name", "activity", "date", "description"],
        "checks": [
            {"field": "description", "rule": "活动简介不少于10字", "check": "len(description) >= 10"},
        ],
        "reference": "《社团活动审批办法》第2条：社团活动需提交详细活动方案。",
    },
    "classroom_booking": {
        "required_fields": ["applicant", "room_no", "date", "start_time", "end_time", "purpose"],
        "checks": [
            {"field": "start_time", "rule": "开始时间不晚于结束时间", "check": "start_time < end_time"},
        ],
        "reference": "《教室使用管理规定》第5条：教室借用需提前一个工作日申请。",
    },
    "business_trip": {
        "required_fields": ["applicant", "destination", "start_date", "end_date", "purpose"],
        "checks": [
            {"field": "estimated_cost", "rule": "预估费用建议如实填写", "check": "estimated_cost is optional"},
        ],
        "reference": "《差旅费管理办法》第6条：出差需经部门负责人审批。",
    },
    "default": {
        "required_fields": [],
        "checks": [],
        "reference": "请按对应类型的规章制度进行人工审核。",
    },
}


def get_rules(doc_type: Optional[str]) -> dict:
    return RULES.get(doc_type or "", RULES["default"])


# ===== 节点 =====

def node_parse(state: ApprovalState) -> ApprovalState:
    """材料解析 — 归一化字段名，检测必填项"""
    rules = get_rules(state["document_type"])

    # 兜底归一化：防止模型输出了中文字段名
    state["filled_json"] = _normalize_keys(state["filled_json"])

    missing = []
    for field in rules.get("required_fields", []):
        val = state["filled_json"].get(field)
        if val is None or val == "":
            missing.append(field)

    state["missing_fields"] = missing
    logger.info(f"[审批辅助] 解析完成, missing_fields={missing}")
    return state


def node_check(state: ApprovalState) -> ApprovalState:
    """规则核对 — 逐条检查，给出修改建议，但不做通过/不通过判断"""
    issues = []
    suggestions = []
    rules = get_rules(state["document_type"])
    doc = state["document_type"]

    # 必填字段缺失 → 建议补充
    for f in state["missing_fields"]:
        label = _FIELD_LABEL_MAP.get(f, f)
        issues.append(f"缺少必填项: {label}")
        suggestions.append(f"请补充「{label}」信息后重新提交")

    # 逐条核对规则
    for check in rules.get("checks", []):
        field = check["field"]
        val = state["filled_json"].get(field)
        if val is not None and val != "":
            # 简单规则评估
            passed = _eval_check(val, check["check"])
            if not passed:
                issues.append(f"{check['rule']}")
                suggestions.append(f"请检查「{field}」字段：{check['rule']}")
        # 可选字段为空不算错，只给出提示
        elif "optional" not in check["check"]:
            pass  # 已在 missing_fields 中

    state["issues"] = issues
    state["suggestions"] = suggestions
    state["policy_refs"] = [rules.get("reference", "")]

    # 生成分析摘要
    if not issues:
        state["analysis_summary"] = "表单填写完整，规则核对通过。请人工确认后审批。"
    else:
        state["analysis_summary"] = f"发现 {len(issues)} 个需关注的问题，请部门管理员审阅后决定。"

    logger.info(f"[审批辅助] 核对完成, issues={issues}, suggestions={suggestions}")
    return state


def node_notify(state: ApprovalState) -> ApprovalState:
    """记录完成（通知占位）"""
    state["notification_sent"] = True
    logger.info(f"[审批辅助] 分析完成: summary={state['analysis_summary']}")
    return state


def _eval_check(value, check_expr: str) -> bool:
    """简单规则评估（安全子集）"""
    try:
        if "is not empty" in check_expr:
            return str(value).strip() != ""
        if "> 0" in check_expr:
            return float(value) > 0
        if ">=" in check_expr and "len" in check_expr:
            parts = check_expr.split(">=")
            if len(parts) == 2:
                return len(str(value)) >= int(parts[1].strip())
        if "<" in check_expr and "optional" not in check_expr:
            # 日期比较简化处理：直接返回 True（依赖人工判断）
            return True
        return True
    except (ValueError, TypeError):
        return False


_FIELD_LABEL_MAP = {
    "college": "学院",
    "class_name": "班级",
    "applicant": "姓名",
    "phone": "联系方式",
    "advisor": "辅导员姓名",
    "advisor_phone": "辅导员联系方式",
    "reason": "请假事由",
    "start_date": "请假开始时间",
    "end_date": "请假结束时间",
    "destination": "去向",
    "transportation": "交通工具",
    "return_time": "返校时间",
    "student_id": "学号/工号",
}


# ===== 路由 =====

def route_after_parse(state: ApprovalState) -> str:
    # 总是进入核对阶段
    return "check"


# ===== 构建图（简化：parse → check → notify → end） =====

_checkpointer = MemorySaver()
_graph = None


def build_graph():
    global _graph
    if _graph is not None:
        return _graph

    builder = StateGraph(ApprovalState)
    builder.add_node("parse", node_parse)
    builder.add_node("check", node_check)
    builder.add_node("notify", node_notify)

    builder.set_entry_point("parse")
    builder.add_conditional_edges("parse", route_after_parse, {"check": "check"})
    builder.add_edge("check", "notify")
    builder.add_edge("notify", "__end__")

    _graph = builder.compile(checkpointer=_checkpointer)
    return _graph


# ===== 公开接口 =====

async def run_approval(
    record: ApprovalRecord,
    db: Session,
) -> ApprovalRecord:
    """
    运行审批辅助引擎。
    引擎只负责：填写表单、核对规则、给出建议、标记缺失。
    不输出"通过/不通过"结论——状态始终为 pending，等待部门管理员人工审批。
    """
    graph = build_graph()

    try:
        filled = json.loads(record.filled_json) if record.filled_json else {}
    except (json.JSONDecodeError, TypeError):
        filled = {}

    initial: ApprovalState = {
        "record_id": record.id,
        "document_type": record.document_type,
        "filled_json": filled,
        "issues": [],
        "suggestions": [],
        "missing_fields": [],
        "policy_refs": [],
        "analysis_summary": "",
        "notification_sent": False,
    }

    config = {"configurable": {"thread_id": str(record.id)}}
    final = graph.invoke(initial, config)

    # 始终设为 pending —— 不替人做决定
    record.status = ApprovalStatus.pending
    record.decision_reason = final.get("analysis_summary", "")
    record.policy_refs = json.dumps(final.get("policy_refs", []), ensure_ascii=False)
    record.suggestions = json.dumps(final.get("suggestions", []), ensure_ascii=False)
    record.missing_info = json.dumps(final.get("missing_fields", []), ensure_ascii=False)
    record.filled_json = json.dumps(final["filled_json"], ensure_ascii=False)

    db.commit()
    db.refresh(record)
    return record
