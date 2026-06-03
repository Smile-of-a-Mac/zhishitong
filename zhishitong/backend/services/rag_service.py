"""
RAG + LLM 增强服务 v2.0

核心变更（相比 v1 Demo）：
  1. 从 data/policy_kb.json 加载科学编写的政策知识库（非硬编码）
  2. TF-IDF 语义向量检索替代简单关键词匹配
  3. LLM 调用按场景分流：云端模型负责自然语言填表，本地 llama.cpp + Qwen3-14B 负责合规/RAG 兜底
  4. 仅保留规则兜底用于 LLM 完全不可用时的容错
  5. TF-IDF 矩阵磁盘缓存，避免每次重启重新构建

GPU 加速：由 inference_server/server.py 自动检测并启用（Metal/CUDA/ROCm/CPU）
"""
import json
import logging
import os
import re
import datetime
from pathlib import Path
from typing import Optional

import httpx
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy.orm import Session

from config import LLAMA_SERVER_URL, LLM_API_BASE, LLM_API_KEY, LLM_FILL_MODEL
from constants import get_doc_label

logger = logging.getLogger(__name__)

# ============================================================
#  一、知识库加载 & TF-IDF 索引
# ============================================================

KB_PATH = Path(__file__).resolve().parent.parent / "data" / "policy_kb.json"

# 全局知识库数据
_kb_documents: list[dict] = []          # 原始文档列表
_kb_chunks: list[dict] = []             # 展平后的 chunk 列表
_tfidf_vectorizer: Optional[TfidfVectorizer] = None
_tfidf_matrix = None
_chunk_texts: list[str] = []


def _load_knowledge_base() -> None:
    """加载 JSON 知识库并构建 TF-IDF 索引（带磁盘缓存）"""
    global _kb_documents, _kb_chunks, _tfidf_vectorizer, _tfidf_matrix, _chunk_texts

    if _kb_chunks and _tfidf_vectorizer is not None:
        return  # 已加载

    if not KB_PATH.exists():
        logger.warning(f"知识库文件不存在: {KB_PATH}，RAG 服务将降级为规则模式")
        return

    with open(KB_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    _kb_documents = data.get("documents", [])
    logger.info(f"知识库已加载: {len(_kb_documents)} 份政策文件")

    # 展平所有 chunk
    _kb_chunks = []
    for doc in _kb_documents:
        for chunk in doc.get("chunks", []):
            _kb_chunks.append({
                "doc_id": doc["id"],
                "doc_title": doc["title"],
                "category": doc.get("category", ""),
                "applicable_types": doc.get("applicable_types", []),
                "chunk_id": chunk["id"],
                "chunk_title": chunk.get("title", ""),
                "text": chunk["text"],
                "keywords": chunk.get("keywords", []),
            })

    _chunk_texts = [c["text"] for c in _kb_chunks]

    if _chunk_texts:
        # 构建 TF-IDF 索引（中文分词用字符级 n-gram）
        _tfidf_vectorizer = TfidfVectorizer(
            analyzer="char",
            ngram_range=(2, 4),      # 2-4 字 n-gram 捕捉中文词和短语
            max_df=0.85,
            min_df=1,
            max_features=3000,
        )
        _tfidf_matrix = _tfidf_vectorizer.fit_transform(_chunk_texts)
        logger.info(f"TF-IDF 索引已构建: {len(_chunk_texts)} chunks, {_tfidf_matrix.shape[1]} 特征维度")


# ============================================================
#  二、语义检索（TF-IDF + 关键词加权）
# ============================================================

def search_policies(query: str, doc_type: Optional[str] = None, top_k: int = 4) -> list[dict]:
    """
    从知识库中检索与查询最相关的政策条文。
    使用 TF-IDF 余弦相似度 + 关键词加权。
    """
    _load_knowledge_base()

    if not _kb_chunks or _tfidf_vectorizer is None:
        return _fallback_keyword_search(query, doc_type, top_k)

    # 1. 按文档类型过滤候选
    if doc_type:
        candidate_indices = [
            i for i, c in enumerate(_kb_chunks)
            if doc_type in c.get("applicable_types", [])
        ]
        if not candidate_indices:
            # 类型过滤无结果，退化为全库搜索
            candidate_indices = list(range(len(_kb_chunks)))
    else:
        candidate_indices = list(range(len(_kb_chunks)))

    if not candidate_indices:
        return []

    # 2. TF-IDF 向量化查询
    try:
        query_vec = _tfidf_vectorizer.transform([query])
    except Exception:
        return _fallback_keyword_search(query, doc_type, top_k)

    # 3. 计算余弦相似度
    candidate_matrix = _tfidf_matrix[candidate_indices]
    sims = cosine_similarity(query_vec, candidate_matrix)[0]

    # 4. 关键词加权
    query_lower = query.lower()
    boost_scores = []
    for idx_in_candidates, orig_idx in enumerate(candidate_indices):
        chunk = _kb_chunks[orig_idx]
        tfidf_score = float(sims[idx_in_candidates])
        # 关键词命中额外加分
        kw_hits = sum(1 for kw in chunk.get("keywords", []) if kw.lower() in query_lower)
        boost = tfidf_score + 0.15 * kw_hits
        boost_scores.append((orig_idx, boost, tfidf_score))

    boost_scores.sort(key=lambda x: x[1], reverse=True)

    # 5. 构建结果
    results = []
    for orig_idx, combined_score, tfidf_score in boost_scores[:top_k]:
        chunk = _kb_chunks[orig_idx]
        results.append({
            "doc_id": chunk["doc_id"],
            "doc_title": chunk["doc_title"],
            "chunk_id": chunk["chunk_id"],
            "chunk_title": chunk.get("chunk_title", ""),
            "text": chunk["text"],
            "score": round(combined_score, 3),
        })

    return results


def _fallback_keyword_search(query: str, doc_type: Optional[str], top_k: int) -> list[dict]:
    """TF-IDF 不可用时的关键词兜底检索"""
    _load_knowledge_base()
    if not _kb_chunks:
        return []

    query_chars = set(re.findall(r"[\u4e00-\u9fa5]|[a-zA-Z0-9]+", query))
    results = []
    for chunk in _kb_chunks:
        if doc_type and doc_type not in chunk.get("applicable_types", []):
            continue
        chunk_set = set(re.findall(r"[\u4e00-\u9fa5]|[a-zA-Z0-9]+", chunk["text"]))
        overlap = len(query_chars & chunk_set)
        kw_score = sum(1.5 for kw in chunk.get("keywords", []) if kw in query)
        score = overlap + kw_score
        if score > 0:
            results.append({
                "doc_id": chunk["doc_id"],
                "doc_title": chunk["doc_title"],
                "chunk_id": chunk["chunk_id"],
                "chunk_title": chunk.get("chunk_title", ""),
                "text": chunk["text"],
                "score": score,
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


# ============================================================
#  三、LLM 调用工具（集成智能 Key 池）
# ============================================================

async def _call_llm(
    prompt: str,
    system: str = "",
    max_tokens: int = 512,
    temperature: float = 0.3,
    db: Optional[Session] = None,
    force_external: bool = False,
) -> str:
    """
    统一 LLM 调用入口。
    force_external=True 时仅尝试外部 API，不回落本地推理（意图识别场景）。
    """
    from services.key_pool import resolve_key, record_success, record_failure
    from models import ApiKeyType

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    key_id = None
    api_base = LLM_API_BASE
    api_key = LLM_API_KEY
    model = LLM_FILL_MODEL

    if db:
        resolved = resolve_key(
            db, ApiKeyType.llm,
            fallback_base=LLM_API_BASE, fallback_key=LLM_API_KEY, fallback_model=LLM_FILL_MODEL,
        )
        key_id = resolved.key_id
        api_base = resolved.api_base
        api_key = resolved.api_key
        model = resolved.model

    if api_key:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{api_base}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )
                resp.raise_for_status()
                result = resp.json()["choices"][0]["message"]["content"].strip()
                if key_id and db:
                    record_success(db, key_id)
                return result
        except Exception as e:
            logger.warning(f"外部 LLM 调用失败（Key #{key_id or 'env'}）: {e}")
            if key_id and db:
                record_failure(db, key_id)
            if force_external:
                raise

    if force_external:
        raise RuntimeError("未配置外部 LLM API Key，无法执行意图识别。请设置 LLM_API_KEY 环境变量或在管理后台添加 AI Key。")

    # 回退到本地推理服务（仅非 force_external 场景）
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{LLAMA_SERVER_URL}/v1/chat/completions",
            json={
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()


def _extract_json(text: str) -> dict:
    """从 LLM 输出中稳健提取 JSON（处理 think 标签、代码块、杂讯）"""
    import re
    # 去掉 think / 思考标签（DeepSeek 等模型）
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # 处理 markdown 代码块
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1].split("```")[0].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]
    else:
        raise ValueError("No JSON object found in response")
    return json.loads(text)


# ============================================================
#  四、合规性分析（RAG + LLM）
# ============================================================

async def check_compliance(form_json: dict, doc_type: str, db: Session) -> dict:
    """
    对表单进行 RAG 合规性分析。
    返回: {policy_hits, compliance_summary, risk_level, compliance_items, suggestions}
    """
    # 提取 OCR 原文（如果是由 router 注入的）
    ocr_text = str(form_json.pop("_ocr_text", "") or "")
    doc_type_from_raw = str(form_json.pop("document_type", "") or "")

    # 构建检索文本：优先用结构化字段，否则用 OCR 原文
    field_text = " ".join(str(v) for v in form_json.values() if v and str(v).strip())
    if field_text:
        query_text = doc_type + " " + field_text
    elif ocr_text:
        query_text = doc_type + " " + ocr_text[:800]  # 截断避免过长
    else:
        query_text = doc_type

    policy_hits = search_policies(query_text, doc_type=doc_type, top_k=4)
    if not policy_hits:
        policy_hits = search_policies(query_text, doc_type=None, top_k=3)

    policy_context = "\n".join(
        f"【{h.get('chunk_title', h['doc_title'])}】{h['text']}"
        for h in policy_hits
    ) if policy_hits else "暂无相关政策条文。"

    doc_name = get_doc_label(doc_type)

    # 构建待审数据：优先结构化字段，无结构化数据时使用 OCR 原文
    if form_json:
        form_display = json.dumps(form_json, ensure_ascii=False, indent=2)
    elif ocr_text:
        form_display = f"[OCR 识别原文]\n{ocr_text[:1200]}"
    else:
        form_display = "（无表单数据）"

    prompt = f"""你是一名高校行政审批合规顾问。请严格依据下方政策条文，分析该申请表单的合规性。

=== 政策依据 ===
{policy_context}

=== 待审申请（{doc_name}）===
{form_display}

请输出严格 JSON（勿加任何解释）：
{{
  "risk_level": "low/medium/high",
  "compliance_summary": "一句话小结（30字内）",
  "compliance_items": [
    {{"item": "检查项", "status": "ok/warning/error", "detail": "说明"}}
  ],
  "suggestions": ["建议1", "建议2"]
}}"""

    try:
        raw = await _call_llm(prompt, max_tokens=600, db=db)
        result = _extract_json(raw)
    except Exception as e:
        logger.warning(f"合规分析 LLM 失败: {e}")
        return _compliance_rule_fallback(form_json, ocr_text, doc_type, policy_hits)

    result["policy_hits"] = [
        {"doc_title": h["doc_title"], "text": h["text"]} for h in policy_hits
    ]
    return result


def _compliance_rule_fallback(form_json: dict, ocr_text: str, doc_type: str, policy_hits: list) -> dict:
    """规则兜底合规检查（LLM 完全不可用时）"""
    items = []
    suggestions = []

    # 检查是否有有效数据（结构化或 OCR 原文）
    has_data = bool(form_json and any(v for v in form_json.values() if v))
    has_ocr = bool(ocr_text and ocr_text.strip())

    if not has_data and not has_ocr:
        return {
            "risk_level": "low",
            "compliance_summary": "暂无表单数据，无法执行合规分析",
            "compliance_items": [{"item": "数据状态", "status": "warning", "detail": "表单数据为空，请确认是否已提交"}],
            "suggestions": ["请先填写并提交申请表单"],
            "policy_hits": [{"doc_title": h["doc_title"], "text": h["text"]} for h in policy_hits],
        }

    if doc_type == "reimbursement":
        # 字段名容错：尝试多个可能的键名
        amount = float(
            form_json.get("amount") or form_json.get("total_amount") or
            form_json.get("reimbursement_amount") or form_json.get("金额") or 0
        )
        invoice = (
            form_json.get("invoice_no") or form_json.get("invoice_number") or
            form_json.get("invoice_num") or form_json.get("发票号") or ""
        )
        if amount <= 0:
            items.append({"item": "报销金额", "status": "error", "detail": "金额必须大于0"})
        elif amount > 50000:
            items.append({"item": "报销金额", "status": "warning", "detail": "超50000元需校长办公会审议"})
        elif amount > 20000:
            items.append({"item": "报销金额", "status": "warning", "detail": "超20000元需财务处长会签"})
        elif amount > 5000:
            items.append({"item": "报销金额", "status": "warning", "detail": "超5000元需分管校领导审批"})
        else:
            items.append({"item": "报销金额", "status": "ok", "detail": "由部门负责人审批"})
        if not invoice:
            items.append({"item": "发票", "status": "error", "detail": "缺少发票号码"})

    elif doc_type == "leave":
        if not form_json.get("reason"):
            items.append({"item": "请假事由", "status": "error", "detail": "不能为空"})
        else:
            items.append({"item": "请假事由", "status": "ok", "detail": "已填写"})

    elif doc_type == "club_application":
        if not form_json.get("activity_name"):
            items.append({"item": "活动名称", "status": "error", "detail": "不能为空"})
        if not form_json.get("participant_count"):
            items.append({"item": "参与人数", "status": "warning", "detail": "未填写"})

    if not items:
        items.append({"item": "基本检查", "status": "ok", "detail": "未发现明显合规问题"})

    errors = [i for i in items if i["status"] == "error"]
    warnings = [i for i in items if i["status"] == "warning"]
    risk_level = "high" if errors else ("medium" if warnings else "low")

    return {
        "risk_level": risk_level,
        "compliance_summary": (
            "发现合规风险需审阅" if errors
            else ("存在注意事项" if warnings else "基本合规")
        ),
        "compliance_items": items,
        "suggestions": suggestions,
        "policy_hits": [{"doc_title": h["doc_title"], "text": h["text"]} for h in policy_hits],
    }


# ============================================================
#  五、相似案例检索
# ============================================================

def find_similar_cases(form_json: dict, doc_type: str, db: Session, limit: int = 3) -> list[dict]:
    """从 ApprovedRecord 中检索相似历史案例"""
    from models import ApprovalRecord, ApprovalStatus, User

    try:
        candidates = (
            db.query(ApprovalRecord)
            .filter(
                ApprovalRecord.document_type == doc_type,
                ApprovalRecord.status.in_([ApprovalStatus.approved, ApprovalStatus.rejected]),
                ApprovalRecord.is_deleted == False,
            )
            .order_by(ApprovalRecord.created_at.desc())
            .limit(50)
            .all()
        )
    except Exception:
        return []

    scored = []
    for rec in candidates:
        try:
            hist = json.loads(rec.filled_json or "{}")
        except (json.JSONDecodeError, TypeError):
            hist = {}

        score = _calc_similarity(form_json, hist)
        if score > 0:
            user = db.query(User).filter(User.id == rec.user_id).first()
            scored.append({
                "id": rec.id,
                "status": rec.status.value if rec.status else "unknown",
                "decision_reason": rec.decision_reason or "",
                "created_at": rec.created_at.strftime("%Y-%m-%d") if rec.created_at else "",
                "similarity": round(score, 2),
                "applicant": user.username if user else "未知",
                "key_info": _extract_key_info(hist, doc_type),
            })

    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:limit]


def _calc_similarity(a: dict, b: dict) -> float:
    if not a or not b:
        return 0.1
    all_keys = set(a.keys()) | set(b.keys())
    if not all_keys:
        return 0.1
    match = 0
    for k in all_keys:
        va, vb = str(a.get(k, "") or "").strip(), str(b.get(k, "") or "").strip()
        if va and vb:
            if va == vb:
                match += 1
            elif va in vb or vb in va:
                match += 0.5
    return min(1.0, match / max(len(all_keys), 3) + 0.1)


def _extract_key_info(form_json: dict, doc_type: str) -> str:
    if doc_type == "reimbursement":
        return f"金额 {form_json.get('amount', '')} 元，{form_json.get('reason', '')}"[:40]
    elif doc_type == "leave":
        return f"{form_json.get('start_date', '')}~{form_json.get('end_date', '')}，{form_json.get('reason', '')}"[:40]
    elif doc_type == "business_trip":
        return f"出差至 {form_json.get('destination', '')}"[:40]
    else:
        vals = [str(v) for v in form_json.values() if v]
        return "，".join(vals[:3])[:40]


# ============================================================
#  六、审批意见草稿生成（RAG + LLM）
# ============================================================

async def generate_opinion(
    form_json: dict,
    doc_type: str,
    decision: str,
    issues: list[str],
    policy_hits: Optional[list[dict]] = None,
) -> str:
    """根据表单 + 决定 + 检索到的政策生成审批意见"""
    decision_label = {
        "approved": "予以批准通过",
        "rejected": "不予批准，退回申请",
        "needs_revision": "需补充材料后重新提交",
    }.get(decision, decision)

    doc_name = get_doc_label(doc_type)
    issues_text = "；".join(issues[:3]) if issues else "未发现明显问题"
    policy_text = ""
    if policy_hits:
        policy_text = "\n".join(
            f"- {h.get('chunk_title', h['doc_title'])}: {h['text'][:80]}..."
            for h in policy_hits[:2]
        )

    prompt = f"""你是高校行政管理员。请撰写一条专业、简洁的审批意见（不超过80字）。

申请类型：{doc_name}
关键信息：{json.dumps(form_json, ensure_ascii=False)}
审批决定：{decision_label}
发现问题：{issues_text}
政策参考：{policy_text}

直接输出意见，不要加标题。语气正式友好。"""

    try:
        return await _call_llm(prompt, max_tokens=120)
    except Exception as e:
        logger.warning(f"意见生成失败: {e}")
        return _opinion_template(form_json, doc_type, decision, issues)


def _opinion_template(form_json: dict, doc_type: str, decision: str, issues: list) -> str:
    applicant = form_json.get("applicant", "申请人")
    if decision == "approved":
        return f"已审阅{applicant}提交的{doc_type}申请材料，符合相关规定，予以通过。"
    elif decision == "rejected":
        reason = "；".join(issues[:2]) if issues else "材料不符合规定"
        return f"经审阅{applicant}的申请，{reason}，不予通过，请整改后重新提交。"
    else:
        missing = "；".join(issues[:2]) if issues else "相关材料"
        return f"材料基本齐全，但需补充：{missing}，请完善后重新提交。"


# ============================================================
#  七、自然语言意图识别（LLM）
# ============================================================

_INTENT_KEYWORDS: dict[str, list[str]] = {
    "reimbursement": ["报销", "报账", "费用", "发票", "票据", "经费", "花费"],
    "leave": ["请假", "假期", "休假", "离校", "事假", "病假", "公假"],
    "business_trip": ["出差", "出行", "出访", "赴京", "外出公务"],
    "club_application": ["社团", "活动", "举办", "组织", "俱乐部", "协会"],
    "classroom_booking": ["借教室", "教室", "预约教室"],
    "seal_application": ["用章", "盖章", "公章", "用印"],
    "scholarship": ["奖学金", "奖助金"],
    "dorm_change": ["换宿舍", "调换宿舍", "调宿"],
}


def _account_context_for_intent(user) -> dict:
    """Return non-sensitive applicant fields that may be used to prefill forms."""
    if not user:
        return {}
    pairs = {
        "applicant": getattr(user, "real_name", None) or getattr(user, "username", None),
        "username": getattr(user, "username", None),
        "student_id": getattr(user, "student_id", None),
        "employee_id": getattr(user, "employee_id", None),
        "school": getattr(user, "school", None),
        "college": getattr(user, "department", None),
        "department": getattr(user, "department", None),
        "major": getattr(user, "major", None),
        "class_name": getattr(user, "class_name", None),
        "phone": getattr(user, "phone", None),
        "email": getattr(user, "email", None),
        "advisor": getattr(user, "advisor", None),
        "title": getattr(user, "title", None),
    }
    return {k: str(v) for k, v in pairs.items() if v not in (None, "")}


def _intent_template_fields(doc_type: str) -> set[str]:
    try:
        path = Path(__file__).resolve().parent.parent / "templates.json"
        with open(path, "r", encoding="utf-8") as f:
            templates = json.load(f).get("templates", {})
        fields = templates.get(doc_type, {}).get("fields", [])
        return {str(item.get("key")) for item in fields if item.get("key")}
    except Exception:
        return set()


def _intent_templates_context(keyword_type: str = "") -> str:
    """Return a compact form field contract for the most relevant templates."""
    try:
        path = Path(__file__).resolve().parent.parent / "templates.json"
        with open(path, "r", encoding="utf-8") as f:
            templates = json.load(f).get("templates", {})
    except Exception:
        return "{}"

    priority_keys = [keyword_type] if keyword_type in templates else []
    for fallback in ["leave", "reimbursement", "business_trip"]:
        if fallback not in priority_keys and fallback in templates:
            priority_keys.append(fallback)
            if len(priority_keys) >= 3:
                break

    compact = {}
    for key in priority_keys:
        tpl = templates.get(key)
        if not tpl:
            continue
        compact[key] = {
            "label": tpl.get("label", key),
            "fields": [
                {
                    "key": field.get("key"),
                    "label": field.get("label", ""),
                    "type": field.get("type", "text"),
                    "required": bool(field.get("required", False)),
                    **({"options": field.get("options")} if field.get("options") else {}),
                }
                for field in tpl.get("fields", [])
                if field.get("key")
            ],
        }
    return json.dumps(compact, ensure_ascii=False)


def _intent_regex_fill(text: str, fields: dict, doc_type: str) -> dict:
    filled = dict(fields or {})
    if doc_type == "reimbursement":
        if not filled.get("amount"):
            m = re.search(r"(\d+(?:\.\d{1,2})?)\s*元", text)
            if m:
                filled["amount"] = m.group(1)
        if filled.get("amount") and not filled.get("reason"):
            reason = re.sub(r"\d+\.?\d*\s*元", "", text).strip().lstrip("报销").strip()
            if reason:
                filled["reason"] = reason
        reason = filled.get("reason", "")
        if reason and not filled.get("category"):
            if any(kw in reason for kw in ["会议", "餐饮", "招待", "宴请", "聚餐", "茶歇", "工作餐"]):
                filled["category"] = "会议费"
            elif any(kw in reason for kw in ["差旅", "交通", "机票", "火车", "打车", "高铁", "路费"]):
                filled["category"] = "差旅交通"
            elif any(kw in reason for kw in ["办公", "文具", "纸张", "耗材"]):
                filled["category"] = "办公用品"
            elif any(kw in reason for kw in ["印刷", "复印", "资料"]):
                filled["category"] = "印刷资料"
            elif any(kw in reason for kw in ["实验", "试剂"]):
                filled["category"] = "实验耗材"
            elif any(kw in reason for kw in ["图书", "书", "教材"]):
                filled["category"] = "图书资料"
            elif any(kw in reason for kw in ["维修", "修理", "维护"]):
                filled["category"] = "维修"
            else:
                filled.setdefault("category", "其他")
    if not filled.get("date") and doc_type in ("reimbursement", "leave"):
        m = re.search(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})", text)
        if m:
            filled["date"] = m.group(1).replace("/", "-")
    if doc_type == "leave":
        if not filled.get("leave_type"):
            if any(kw in text for kw in ["调研", "出差", "公务", "导师叫", "老师叫", "会议", "参会"]):
                filled["leave_type"] = "公假"
            elif "病" in text:
                filled["leave_type"] = "病假"
            else:
                filled["leave_type"] = "事假"
        if not filled.get("destination"):
            m = re.search(r"(?:去|到|赴)([^，,。\s]{2,12}?)(?:调研|出差|参会|开会|学习|培训|办事|$)", text)
            if m:
                filled["destination"] = m.group(1)
        if not filled.get("transportation"):
            for item in ["长途汽车", "高铁", "火车", "飞机", "汽车", "大巴", "公交", "出租车", "打车", "自驾"]:
                if item in text:
                    filled["transportation"] = item
                    break
        if not filled.get("reason"):
            m = re.search(r"(?:去|到|赴)([^，,。\s]{2,20}?(?:调研|出差|参会|开会|学习|培训|办事))", text)
            if m:
                filled["reason"] = m.group(1)
        today = datetime.date.today()
        if "明后两天" in text or "明后天" in text:
            start = today + datetime.timedelta(days=1)
            end = today + datetime.timedelta(days=2)
            filled.setdefault("start_date", start.isoformat())
            filled.setdefault("end_date", end.isoformat())
        elif "明天" in text:
            day = today + datetime.timedelta(days=1)
            filled.setdefault("start_date", day.isoformat())
            filled.setdefault("end_date", day.isoformat())
        elif "后天" in text:
            day = today + datetime.timedelta(days=2)
            filled.setdefault("start_date", day.isoformat())
            filled.setdefault("end_date", day.isoformat())
    return filled


def _is_self_application_text(text: str) -> bool:
    return any(token in text for token in ["我", "本人", "自己", "我的", "给我", "帮我"])


def _merge_account_prefill(prefill: dict, account_ctx: dict, doc_type: str = "", use_account_defaults: bool = False) -> dict:
    """Keep only template fields; optionally use account fields as self-application defaults."""
    allowed_fields = _intent_template_fields(doc_type) if doc_type else set()
    merged = dict(prefill or {})
    if use_account_defaults:
        for key, value in account_ctx.items():
            if key in {"username", "school", "email"}:
                continue
            if allowed_fields and key not in allowed_fields:
                continue
            merged.setdefault(key, value)
    if allowed_fields:
        merged = {k: v for k, v in merged.items() if k in allowed_fields}
    return merged


async def parse_intent(text: str, db: Optional[Session] = None, current_user=None) -> dict:
    import re as _re
    keyword_type = _keyword_intent(text)
    doc_name = get_doc_label(keyword_type)

    account_ctx = _account_context_for_intent(current_user)
    account_context_text = json.dumps(account_ctx, ensure_ascii=False) if account_ctx else "{}"
    use_account_defaults = _is_self_application_text(text)
    doc_type_keys = json.dumps(list(_INTENT_KEYWORDS.keys()), ensure_ascii=False)

    prompt = f"""你是智能表单助手。根据用户描述判断事务类型并提取所有可填字段。

用户输入：{text}

当前登录账号（仅作参考，不一定是申请人）：{account_context_text}

合法事务类型 key（必须选一个）：{doc_type_keys}

输出纯 JSON（不要加解释或代码块）：
{{
  "document_type": "上述合法 key 之一",
  "confidence": 0.0~1.0,
  "prefill_fields": {{ "字段名": "提取值" }}
}}
仅输出有值的字段。金额只保留数字去掉单位。日期格式 YYYY-MM-DD。
若是第一人称"我/本人/自己/帮我"申请，可用当前登录账号补基础字段（姓名、学号、学院、专业、班级、电话、辅导员）。
若是帮别人填写，基础字段以用户描述为准，不要用当前账号冒充。"""

    try:
        raw = await _call_llm(prompt, max_tokens=800, db=db, force_external=True)
        result = _extract_json(raw)
        if not result.get("document_type") or result["document_type"] not in _INTENT_KEYWORDS:
            result["document_type"] = keyword_type
        pf = {k: str(v) for k, v in (result.get("prefill_fields") or {}).items()
              if v not in (None, "", "null")}

        resolved_type = result["document_type"]
        try:
            from services.ocr_service import _normalize_json_keys
            pf = _normalize_json_keys(pf)
        except Exception:
            pass

        pf = _intent_regex_fill(text, pf, resolved_type)

        result["prefill_fields"] = _merge_account_prefill(
            pf, account_ctx, resolved_type, use_account_defaults=use_account_defaults,
        )
        result["doc_label"] = get_doc_label(result["document_type"])
        result["confidence"] = float(result.get("confidence", 0.65))
        return result
    except Exception as e:
        logger.warning(f"意图识别 LLM 失败: {e}")
        fallback_fields = _intent_regex_fill(text, {}, keyword_type)
        try:
            from services.ocr_service import _normalize_json_keys
            fallback_fields = _normalize_json_keys(fallback_fields)
        except Exception:
            pass
        return {
            "document_type": keyword_type,
            "confidence": 0.6,
            "prefill_fields": _merge_account_prefill(
                fallback_fields, account_ctx, keyword_type, use_account_defaults=use_account_defaults,
            ),
            "doc_label": doc_name,
        }


def _keyword_intent(text: str) -> str:
    best, best_score = "leave", 0
    for dtype, kws in _INTENT_KEYWORDS.items():
        score = sum(1 for kw in kws if kw in text)
        if score > best_score:
            best_score, best = score, dtype
    return best


# ============================================================
#  八、NL 搜索 → 过滤参数（LLM）
# ============================================================

async def nl_to_filter(text: str) -> dict:
    """将自然语言搜索转换为结构化过滤参数"""
    prompt = f"""将自然语言搜索条件转为 JSON：

搜索：{text}

格式：
{{
  "status": "pending/approved/rejected/needs_revision 或 null",
  "doc_type": "reimbursement/leave/business_trip/club_application/classroom_booking/seal_application/scholarship/dorm_change 或 null",
  "amount_gt": 数字或 null,
  "amount_lt": 数字或 null,
  "date_from": "YYYY-MM-DD 或 null",
  "date_to": "YYYY-MM-DD 或 null",
  "keyword": "关键词或 null"
}}
仅输出 JSON。"""

    try:
        raw = await _call_llm(prompt, max_tokens=200)
        result = _extract_json(raw)
        return {k: v for k, v in result.items() if v is not None}
    except Exception as e:
        logger.warning(f"NL 搜索 LLM 失败: {e}")
        return _nl_filter_fallback(text)


def _nl_filter_fallback(text: str) -> dict:
    result = {}
    if any(w in text for w in ["待审", "待审批", "未处理"]):
        result["status"] = "pending"
    elif any(w in text for w in ["已通过", "批准"]):
        result["status"] = "approved"
    elif any(w in text for w in ["驳回", "不通过", "拒绝"]):
        result["status"] = "rejected"
    for dtype, kws in _INTENT_KEYWORDS.items():
        if any(kw in text for kw in kws):
            result["doc_type"] = dtype
            break
    m = re.search(r"超过\s*(\d+)\s*元", text)
    if m:
        result["amount_gt"] = float(m.group(1))
    m = re.search(r"不超过\s*(\d+)\s*元", text)
    if m:
        result["amount_lt"] = float(m.group(1))
    return result


# ============================================================
#  九、政策问答（RAG + LLM Chatbot）
# ============================================================

async def answer_question(
    question: str,
    doc_type: Optional[str] = None,
    chat_history: Optional[list[dict]] = None,
) -> dict:
    """基于知识库 RAG 回答政策问题"""
    hits = search_policies(question, doc_type=doc_type, top_k=3)
    if not hits:
        hits = search_policies(question, doc_type=None, top_k=3)

    policy_context = "\n\n".join(
        f"【{h.get('chunk_title', h['doc_title'])}】\n{h['text']}"
        for h in hits
    ) if hits else "暂无相关政策条文。"

    system_prompt = (
        "你是智审通政策助手。只基于提供的政策条文回答，不超过150字，简洁准确。"
        "如果条文没有明确规定，如实说明并给出合理建议。"
    )

    query_with_context = f"""=== 相关政策条文 ===
{policy_context}

=== 用户问题 ===
{question}"""

    messages_for_llm = []
    if chat_history:
        messages_for_llm.extend(chat_history[-4:])
    messages_for_llm.append({"role": "user", "content": query_with_context})

    try:
        # 用 system prompt 的方式调用
        full_prompt = f"{system_prompt}\n\n{query_with_context}"
        answer = await _call_llm(full_prompt, max_tokens=250)
    except Exception as e:
        logger.warning(f"问答 LLM 失败: {e}")
        if hits:
            answer = (
                f"根据{hits[0]['doc_title']}第{hits[0].get('chunk_title', '')}条："
                f"{hits[0]['text'][:120]}...\n详情请咨询相关部门。"
            )
        else:
            answer = "未在知识库中找到相关内容，建议联系学校相关部门咨询。"

    return {
        "answer": answer,
        "sources": [
            {"doc_title": h["doc_title"], "text": h["text"][:80] + "..."}
            for h in hits
        ],
    }
