"""
AI 增强功能路由

端点：
  POST /api/ai/intent         — 自然语言意图识别
  POST /api/ai/compliance/{id} — 合规性 RAG 分析
  POST /api/ai/similar/{id}   — 相似历史案例检索
  POST /api/ai/opinion        — 审批意见草稿生成
  POST /api/ai/chat           — 政策问答 Chatbot
  POST /api/ai/search         — 自然语言搜索 → 过滤参数
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import ApprovalRecord, User
from auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai", tags=["AI增强"])


# ============================================================
#  Pydantic 请求体
# ============================================================

class IntentRequest(BaseModel):
    text: str

class OpinionRequest(BaseModel):
    record_id: int
    decision: str  # approved / rejected / needs_revision

class ChatRequest(BaseModel):
    question: str
    doc_type: Optional[str] = None
    history: Optional[list[dict]] = None  # [{role, content}]

class NlSearchRequest(BaseModel):
    query: str


# ============================================================
#  1. 自然语言意图识别
# ============================================================

@router.post("/intent")
async def parse_intent(body: IntentRequest, current_user: User = Depends(get_current_user)):
    """识别用户描述的申请意图，返回推荐的文档类型和预填字段"""
    if not body.text or not body.text.strip():
        raise HTTPException(status_code=400, detail="请输入描述文本")
    from services.rag_service import parse_intent as svc_parse
    try:
        result = await svc_parse(body.text.strip())
        return result
    except Exception as e:
        logger.error(f"意图识别失败: {e}")
        raise HTTPException(status_code=500, detail="意图识别服务暂时不可用")


# ============================================================
#  2. 合规性 RAG 分析
# ============================================================

@router.post("/compliance/{record_id}")
async def check_compliance(
    record_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """对指定审批记录进行 RAG 合规性分析（需有查看权限）"""
    record = db.query(ApprovalRecord).filter(
        ApprovalRecord.id == record_id,
        ApprovalRecord.is_deleted == False,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")

    # 权限检查：本人 / 管理员 / 部门管理员（同部门）
    applicant = db.query(User).filter(User.id == record.user_id).first()
    is_own = record.user_id == current_user.id
    is_admin = current_user.is_admin or current_user.is_school_admin
    is_dept_admin = (
        current_user.is_dept_admin
        and applicant
        and applicant.department == current_user.department
        and applicant.school == current_user.school
    )
    is_finance_admin = current_user.is_finance_admin and record.document_type == "reimbursement"
    if not (is_own or is_admin or is_dept_admin or is_finance_admin):
        raise HTTPException(status_code=403, detail="无权访问此记录")

    try:
        form_json = json.loads(record.filled_json or "{}")
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"合规分析: record {record_id} filled_json 解析失败，尝试从 OCR 文本提取")
        form_json = {}

    # 如果 filled_json 为空，尝试用 OCR 原文做合规分析（至少知道内容）
    use_raw_text = not form_json or all(v in (None, "") for v in form_json.values())
    if use_raw_text and record.ocr_text:
        logger.info(f"合规分析: record {record_id} 无结构化数据，使用 OCR 原文")
        form_json = {"_ocr_text": record.ocr_text, "document_type": record.document_type or ""}

    from services.rag_service import check_compliance as svc_compliance
    try:
        result = await svc_compliance(form_json, record.document_type or "", db)
        return result
    except Exception as e:
        logger.error(f"合规分析失败 record={record_id}: {e}")
        raise HTTPException(status_code=500, detail="合规分析服务暂时不可用")


# ============================================================
#  3. 相似案例检索
# ============================================================

@router.post("/similar/{record_id}")
async def similar_cases(
    record_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """检索与指定记录最相似的历史案例（仅管理员和部门管理员可用）"""
    is_staff = (
        current_user.is_admin
        or current_user.is_school_admin
        or current_user.is_dept_admin
        or current_user.is_finance_admin
    )
    if not is_staff:
        raise HTTPException(status_code=403, detail="仅管理员可查看历史案例")

    record = db.query(ApprovalRecord).filter(
        ApprovalRecord.id == record_id,
        ApprovalRecord.is_deleted == False,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")

    try:
        form_json = json.loads(record.filled_json or "{}")
    except (json.JSONDecodeError, TypeError):
        form_json = {}

    from services.rag_service import find_similar_cases
    cases = find_similar_cases(form_json, record.document_type or "", db)
    return {"cases": cases}


# ============================================================
#  4. 审批意见草稿生成
# ============================================================

@router.post("/opinion")
async def generate_opinion(
    body: OpinionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """生成审批意见草稿（仅管理员可用）"""
    is_staff = (
        current_user.is_admin
        or current_user.is_school_admin
        or current_user.is_dept_admin
        or current_user.is_finance_admin
    )
    if not is_staff:
        raise HTTPException(status_code=403, detail="仅管理员可使用此功能")

    if body.decision not in ("approved", "rejected", "needs_revision"):
        raise HTTPException(status_code=400, detail="decision 参数无效")

    record = db.query(ApprovalRecord).filter(
        ApprovalRecord.id == body.record_id,
        ApprovalRecord.is_deleted == False,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")

    try:
        form_json = json.loads(record.filled_json or "{}")
        issues = json.loads(record.missing_info or "[]")
        if isinstance(issues, str):
            issues = []
        suggestions = json.loads(record.suggestions or "[]")
        all_issues = (issues or []) + (suggestions or [])
    except (json.JSONDecodeError, TypeError):
        form_json = {}
        all_issues = []

    from services.rag_service import generate_opinion as svc_opinion, search_policies
    policy_hits = search_policies(
        record.document_type or "", doc_type=record.document_type, top_k=2
    )

    try:
        opinion = await svc_opinion(
            form_json, record.document_type or "", body.decision, all_issues, policy_hits
        )
        return {"opinion": opinion}
    except Exception as e:
        logger.error(f"意见生成失败 record={body.record_id}: {e}")
        raise HTTPException(status_code=500, detail="意见生成服务暂时不可用")


# ============================================================
#  5. 政策问答 Chatbot
# ============================================================

@router.post("/chat")
async def chat(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    """政策知识库 RAG 问答"""
    if not body.question or not body.question.strip():
        raise HTTPException(status_code=400, detail="请输入问题")

    from services.rag_service import answer_question
    try:
        result = await answer_question(
            body.question.strip(),
            doc_type=body.doc_type,
            chat_history=body.history,
        )
        return result
    except Exception as e:
        logger.error(f"政策问答失败: {e}")
        raise HTTPException(status_code=500, detail="问答服务暂时不可用")


# ============================================================
#  6. 自然语言搜索 → 过滤参数
# ============================================================

@router.post("/search")
async def nl_search(
    body: NlSearchRequest,
    current_user: User = Depends(get_current_user),
):
    """将自然语言搜索文本转换为结构化过滤参数"""
    if not body.query or not body.query.strip():
        raise HTTPException(status_code=400, detail="搜索文本不能为空")

    from services.rag_service import nl_to_filter
    try:
        filters = await nl_to_filter(body.query.strip())
        return {"filters": filters, "original_query": body.query}
    except Exception as e:
        logger.error(f"NL 搜索失败: {e}")
        raise HTTPException(status_code=500, detail="搜索解析服务暂时不可用")
