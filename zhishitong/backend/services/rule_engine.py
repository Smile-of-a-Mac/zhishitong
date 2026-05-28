"""智能预审规则引擎 — 在 LLM 分析之前执行硬性规则检查"""
import json, re
from typing import List, Optional
from sqlalchemy.orm import Session
from models import RuleConfig, ApprovalRecord


def check_rules(
    db: Session,
    record: ApprovalRecord,
    filled_json: dict,
    document_type: str,
) -> List[dict]:
    """
    对一条审批记录执行所有适用规则，返回检查结果列表。
    规则优先级：全局规则 + 该文档类型的专属规则，按 priority 降序执行。
    """
    rules = (
        db.query(RuleConfig)
        .filter(
            RuleConfig.is_active == True,
            RuleConfig.document_type.in_([None, document_type]),
        )
        .order_by(RuleConfig.priority.desc())
        .all()
    )

    results = []
    for rule in rules:
        result = _evaluate_rule(rule, filled_json, record, db)
        results.append(result)

    all_passed = all(r["passed"] for r in results if r["severity"] == "error")
    return {"record_id": record.id, "all_passed": all_passed, "results": results}


def _evaluate_rule(rule: RuleConfig, data: dict, record: ApprovalRecord, db: Session) -> dict:
    """评估单条规则"""
    result = {
        "rule_key": rule.rule_key,
        "rule_name": rule.rule_name,
        "passed": True,
        "severity": rule.severity,
        "message": "",
        "field_key": rule.field_key,
    }

    try:
        if rule.rule_type == "field_required":
            # 必填字段检查
            if rule.field_key:
                value = data.get(rule.field_key)
                if value is None or (isinstance(value, str) and not value.strip()):
                    result["passed"] = False
                    result["message"] = rule.error_message

        elif rule.rule_type == "field_range":
            # 数值范围检查
            if rule.field_key and rule.field_key in data:
                value = data[rule.field_key]
                try:
                    num_val = float(value) if not isinstance(value, (int, float)) else value
                    threshold = float(rule.threshold_value) if rule.threshold_value else 0
                    passed = _compare(num_val, rule.operator or "lte", threshold)
                    if not passed:
                        result["passed"] = False
                        result["message"] = rule.error_message
                except (ValueError, TypeError):
                    pass  # 无法转为数字时跳过

        elif rule.rule_type == "duplicate_check":
            # 发票查重
            if rule.field_key and rule.field_key in data:
                value = data[rule.field_key]
                if value:
                    existing = (
                        db.query(ApprovalRecord)
                        .filter(
                            ApprovalRecord.id != record.id,
                            ApprovalRecord.document_type == rule.document_type,
                            ApprovalRecord.filled_json.contains(str(value)),
                            ApprovalRecord.status.in_(["pending", "approved"]),
                        )
                        .first()
                    )
                    if existing:
                        result["passed"] = False
                        result["message"] = rule.error_message

        elif rule.rule_type == "budget_check":
            # 预算检查：金额不能超过可用预算
            if rule.field_key and rule.field_key in data:
                value = data.get(rule.field_key)
                try:
                    amount = float(value) if not isinstance(value, (int, float)) else value
                    budget = float(rule.threshold_value) if rule.threshold_value else 0
                    if amount > budget:
                        result["passed"] = False
                        result["message"] = rule.error_message
                except (ValueError, TypeError):
                    pass

    except Exception as e:
        result["passed"] = False
        result["message"] = f"规则执行异常: {str(e)}"

    # 如果通过，清空 message
    if result["passed"]:
        result["message"] = ""

    return result


def _compare(a: float, op: str, b: float) -> bool:
    """比较运算符"""
    ops = {
        "gt": lambda x, y: x > y,
        "lt": lambda x, y: x < y,
        "gte": lambda x, y: x >= y,
        "lte": lambda x, y: x <= y,
        "eq": lambda x, y: abs(x - y) < 0.001,
    }
    return ops.get(op, lambda x, y: True)(a, b)


def get_default_rules() -> list:
    """返回系统预置的智能规则配置，供首次初始化使用"""
    return [
        {
            "rule_key": "reimburse_amount_positive",
            "rule_name": "报销金额必须大于0",
            "document_type": "reimbursement",
            "rule_type": "field_range",
            "field_key": "amount",
            "operator": "gt",
            "threshold_value": "0",
            "error_message": "报销金额必须大于 0 元",
            "severity": "error",
            "priority": 100,
        },
        {
            "rule_key": "reimburse_amount_limit",
            "rule_name": "单笔报销不超过5000元",
            "document_type": "reimbursement",
            "rule_type": "field_range",
            "field_key": "amount",
            "operator": "lte",
            "threshold_value": "5000",
            "error_message": "单笔报销金额超过 5000 元上限，需走线下审批",
            "severity": "warning",
            "priority": 90,
        },
        {
            "rule_key": "invoice_no_duplicate",
            "rule_name": "发票号码不能重复使用",
            "document_type": "reimbursement",
            "rule_type": "duplicate_check",
            "field_key": "invoice_no",
            "operator": None,
            "threshold_value": None,
            "error_message": "该发票号码已被使用过，疑似重复报销",
            "severity": "error",
            "priority": 80,
        },
        {
            "rule_key": "leave_days_limit",
            "rule_name": "单次请假不超过30天",
            "document_type": "leave",
            "rule_type": "field_range",
            "field_key": None,
            "operator": None,
            "threshold_value": None,
            "error_message": "请假天数需在合理范围内",
            "severity": "warning",
            "priority": 70,
        },
        {
            "rule_key": "trip_budget_check",
            "rule_name": "出差预估费用不超过预算",
            "document_type": "business_trip",
            "rule_type": "budget_check",
            "field_key": "estimated_cost",
            "operator": "lte",
            "threshold_value": "10000",
            "error_message": "出差预估费用超过 10000 元预算上限",
            "severity": "warning",
            "priority": 80,
        },
        {
            "rule_key": "applicant_name_required",
            "rule_name": "申请人姓名不能为空",
            "document_type": None,  # 全局规则
            "rule_type": "field_required",
            "field_key": "applicant",
            "operator": None,
            "threshold_value": None,
            "error_message": "申请人姓名为必填项，请补充",
            "severity": "error",
            "priority": 100,
        },
    ]
