"""模板服务 — 审批表单 Schema 加载 & 类型检测"""
import json
import re
from pathlib import Path
from typing import Optional
from config import TEMPLATES_PATH

_templates: Optional[dict] = None


def _load() -> dict:
    global _templates
    if _templates is None:
        if TEMPLATES_PATH.exists():
            _templates = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))
        else:
            _templates = {"templates": {}, "detection_rules": {}}
    return _templates


def list_templates() -> list[dict]:
    data = _load()
    result = []
    for key, tpl in data.get("templates", {}).items():
        result.append({"key": key, "label": tpl["label"], "icon": tpl.get("icon", "")})
    return result


def get_template(document_type: str) -> Optional[dict]:
    data = _load()
    return data.get("templates", {}).get(document_type)


def detect_document_type(text: str) -> Optional[str]:
    """
    基于关键词匹配自动检测文档类型。
    Free 层用，无需 LLM。
    """
    data = _load()
    rules = data.get("detection_rules", {})

    if not text.strip():
        return None

    scores = {}
    text_lower = text.lower()

    for doc_type, rule in rules.items():
        keywords = rule.get("keywords", [])
        weight = rule.get("weight", 1)
        score = 0
        for kw in keywords:
            if kw.lower() in text_lower:
                score += weight
        if score > 0:
            scores[doc_type] = score

    if not scores:
        return None

    return max(scores, key=scores.get)


def validate_fields(document_type: str, data: dict) -> list[str]:
    """验证用户提交的 JSON 是否符合模板字段要求，返回问题列表"""
    tpl = get_template(document_type)
    if not tpl:
        return [f"未知文档类型: {document_type}"]

    issues = []
    for field in tpl.get("fields", []):
        key = field["key"]
        if field.get("required") and (not data.get(key)):
            issues.append(f"缺少必填字段: {field['label']}")

        # 类型检查
        if key in data and data[key] is not None:
            ftype = field["type"]
            val = data[key]
            if ftype == "number" and not isinstance(val, (int, float)):
                issues.append(f"{field['label']} 应为数字")
            elif ftype == "date":
                if not re.match(r"^\d{4}-\d{2}-\d{2}", str(val)):
                    issues.append(f"{field['label']} 格式应为 YYYY-MM-DD")

    return issues
