"""审批路由 — 提交审批 / 查询 / 状态 / 软删除 / 智能建议 / 手动申报 / 规则检查 / 代理"""
import json, time, logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_
import httpx

from database import get_db
from models import User, ApprovalRecord, ApprovalStatus, DeletedBy
from schemas import (
    ApprovalSubmit, ApprovalOut, ApprovalListOut,
    ReviewSuggestRequest, ManualSubmit,
)
from auth import get_current_user, require_admin
from services.approval_service import run_approval
from services.logging_service import LogCategory, log, log_error
from services.workflow import get_first_stage
from services.template_service import get_template
from services.ocr_service import _normalize_json_keys, _FIELD_KEY_MAP
from services.crypto_service import decrypt
from services.notification_service import notify_submitted, notify_urged
from constants import get_doc_label

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


def _notify_dept_admins(db: Session, applicant: User, record: ApprovalRecord):
    """通知申请人的部门管理员：有新事务待审批"""
    try:
        dept_admins = db.query(User).filter(
            User.is_dept_admin == True,
            User.school == applicant.school,
            User.department == applicant.department,  # 仅通知申请人所属部门的管理员
            User.is_active == True,
        ).all()
        if not dept_admins:
            return
        admin_ids = [a.id for a in dept_admins]
        doc_label = get_doc_label(record.document_type)
        notify_submitted(
            db, record.id, applicant.id,
            applicant.real_name or applicant.username,
            doc_label, admin_ids,
        )
    except Exception:
        pass  # 通知失败不影响主流程


@router.get("", response_model=ApprovalListOut)
def list_approvals(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(ApprovalRecord).filter(
        ApprovalRecord.user_id == user.id,
        ApprovalRecord.is_deleted == False,
    )
    total = q.count()
    records = q.order_by(ApprovalRecord.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    items = [
        ApprovalOut(
            id=r.id,
            document_type=r.document_type,
            status=r.status.value if r.status else "pending",
            current_stage=r.current_stage,
            decision_reason=r.decision_reason,
            filled_json=r.filled_json,
            original_filename=r.original_filename,
            image_url=f"/api/files/{r.id}" if r.storage_path and r.storage_path != "manual" else None,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in records
    ]
    return ApprovalListOut(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=ApprovalOut)
async def submit_approval(
    body: ApprovalSubmit,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """提交 OCR 记录进入审批流程"""
    t_start = time.time()

    # 管理员角色的用户不能提交审批请求
    if user.is_admin or user.is_school_admin or user.is_dept_admin or user.is_finance_admin:
        raise HTTPException(403, "管理员账号不能提交审批请求，请使用普通用户账号")

    record = (
        db.query(ApprovalRecord)
        .filter(
            ApprovalRecord.id == body.record_id,
            ApprovalRecord.user_id == user.id,
            ApprovalRecord.is_deleted == False,
        )
        .first()
    )
    if not record:
        raise HTTPException(404, "OCR 记录不存在")

    # 如果用户修改了 JSON
    if body.edited_json:
        record.filled_json = json.dumps(body.edited_json, ensure_ascii=False)
        db.commit()

    # 执行 LangGraph 审批
    try:
        record = await run_approval(record, db)
    except TimeoutError as e:
        log_error(LogCategory.APPROVAL, f"审批流程超时: record_id={body.record_id}", exc=e, user_id=user.id)
        raise HTTPException(504, f"审批流程超时，请稍后重试")
    except ValueError as e:
        log_error(LogCategory.APPROVAL, f"审批参数错误: record_id={body.record_id}", exc=e, user_id=user.id)
        raise HTTPException(400, f"审批参数错误: {e}")
    except Exception as e:
        import uuid
        ref_id = str(uuid.uuid4())[:8]
        log_error(LogCategory.APPROVAL, f"审批流程异常 [{ref_id}]: record_id={body.record_id}", exc=e, user_id=user.id)
        raise HTTPException(500, f"审批流程异常 (追踪ID: {ref_id})")

    duration_ms = round((time.time() - t_start) * 1000)

    # 通知部门管理员：有新的待审批事务
    _notify_dept_admins(db, user, record)

    log(
        LogCategory.APPROVAL,
        "info",
        f"审批完成: {record.document_type or 'unknown'} → {record.status.value}",
        user_id=user.id,
        record_id=record.id,
        duration_ms=duration_ms,
        doc_type=record.document_type,
        status=record.status.value,
        reason=record.decision_reason,
    )

    return ApprovalOut(
        id=record.id,
        document_type=record.document_type,
        status=record.status.value,
        current_stage=record.current_stage,
        decision_reason=record.decision_reason,
        filled_json=record.filled_json,
        suggestions=record.suggestions,
        missing_info=record.missing_info,
        original_filename=record.original_filename,
        image_url=f"/api/files/{record.id}" if record.storage_path and record.storage_path != "manual" else None,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("/{record_id}", response_model=ApprovalOut)
def get_approval(
    record_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 管理员可查看所有记录；普通用户只能看自己的
    is_admin = user.is_admin or user.is_dept_admin or user.is_school_admin or user.is_finance_admin
    filters = [
        ApprovalRecord.id == record_id,
        ApprovalRecord.is_deleted == False,
    ]
    if not is_admin:
        filters.append(ApprovalRecord.user_id == user.id)

    record = db.query(ApprovalRecord).filter(*filters).first()
    if not record:
        raise HTTPException(404, "记录不存在")
    return ApprovalOut(
        id=record.id,
        document_type=record.document_type,
        status=record.status.value,
        current_stage=record.current_stage,
        decision_reason=record.decision_reason,
        filled_json=record.filled_json,
        suggestions=record.suggestions,
        missing_info=record.missing_info,
        original_filename=record.original_filename,
        image_url=f"/api/files/{record.id}" if record.storage_path and record.storage_path != "manual" else None,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.delete("/{record_id}")
def soft_delete(
    record_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """用户删除：仅允许删除已结案的记录（approved/rejected/cancelled），标记软删除"""
    record = (
        db.query(ApprovalRecord)
        .filter(
            ApprovalRecord.id == record_id,
            ApprovalRecord.user_id == user.id,
            ApprovalRecord.is_deleted == False,
        )
        .first()
    )
    if not record:
        raise HTTPException(404, "记录不存在或已删除")

    # 只有已结案、已撤回或需修改的记录才能取消
    deletable = {ApprovalStatus.approved, ApprovalStatus.rejected, ApprovalStatus.cancelled, ApprovalStatus.withdrawn, ApprovalStatus.needs_revision}
    if record.status not in deletable:
        raise HTTPException(400, "只能取消已经结案、已撤回或需修改的申请")

    from datetime import datetime
    # needs_revision / withdrawn → 标记为已取消（学生和管理员均可继续看到），其他已结案 → 软删除
    if record.status in {ApprovalStatus.needs_revision, ApprovalStatus.withdrawn}:
        record.status = ApprovalStatus.cancelled
        record.decision_reason = "[申请人取消]"
        # 不设置 is_deleted，学生仍能看到并进一步删除
    else:
        record.is_deleted = True
        record.deleted_by = DeletedBy.USER
        record.deleted_at = datetime.now()
    db.commit()
    return {"detail": "已取消"}


@router.put("/{record_id}/withdraw")
def withdraw_record(
    record_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """撤回申请：将 pending 状态的申请撤回，学生可以重新编辑后再次提交"""
    record = (
        db.query(ApprovalRecord)
        .filter(
            ApprovalRecord.id == record_id,
            ApprovalRecord.user_id == user.id,
            ApprovalRecord.is_deleted == False,
        )
        .first()
    )
    if not record:
        raise HTTPException(404, "记录不存在或已删除")

    if record.status != ApprovalStatus.pending:
        raise HTTPException(400, "只能撤回待审批状态的申请")

    record.status = ApprovalStatus.withdrawn
    record.decision_reason = "[用户撤回]"
    db.commit()
    db.refresh(record)

    log(LogCategory.APPROVAL, "info",
        f"用户撤回申请: record_id={record_id}",
        user_id=user.id, record_id=record_id)

    return {
        "detail": "申请已撤回，可重新编辑后提交",
        "record_id": record_id,
        "status": "withdrawn",
    }


@router.put("/{record_id}/resubmit", response_model=ApprovalOut)
async def resubmit_record(
    record_id: int,
    body: ApprovalSubmit,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """重新提交已撤回或需修改的申请"""
    record = (
        db.query(ApprovalRecord)
        .filter(
            ApprovalRecord.id == record_id,
            ApprovalRecord.user_id == user.id,
            ApprovalRecord.is_deleted == False,
        )
        .first()
    )
    if not record:
        raise HTTPException(404, "记录不存在或已删除")

    if record.status not in {ApprovalStatus.withdrawn, ApprovalStatus.needs_revision}:
        raise HTTPException(400, "只能重新提交已撤回或需修改的申请")

    # 更新表单数据
    if body.edited_json:
        record.filled_json = json.dumps(body.edited_json, ensure_ascii=False)

    # 重置状态为 pending
    record.status = ApprovalStatus.pending
    record.current_stage = get_first_stage(record.document_type, json.loads(record.filled_json) if record.filled_json else {})
    record.decision_reason = None
    record.suggestions = None
    record.missing_info = None
    record.stage_history_json = "[]"
    db.commit()

    # 重新运行审批辅助引擎
    try:
        record = await run_approval(record, db)
    except TimeoutError as e:
        log_error(LogCategory.APPROVAL, f"重新提交审批超时: record_id={record_id}", exc=e, user_id=user.id)
        raise HTTPException(504, "审批超时，请稍后重试")
    except ValueError as e:
        log_error(LogCategory.APPROVAL, f"重新提交审批参数错误: record_id={record_id}", exc=e, user_id=user.id)
        raise HTTPException(400, str(e))
    except Exception as e:
        import uuid
        ref_id = str(uuid.uuid4())[:8]
        log_error(LogCategory.APPROVAL, f"重新提交审批异常 [{ref_id}]: record_id={record_id}", exc=e, user_id=user.id)

    db.refresh(record)

    log(LogCategory.APPROVAL, "info",
        f"用户重新提交撤回申请: record_id={record_id}",
        user_id=user.id, record_id=record_id)

    return ApprovalOut(
        id=record.id,
        document_type=record.document_type,
        status=record.status.value,
        current_stage=record.current_stage,
        decision_reason=record.decision_reason,
        filled_json=record.filled_json,
        suggestions=record.suggestions,
        missing_info=record.missing_info,
        original_filename=record.original_filename,
        image_url=f"/api/files/{record.id}" if record.storage_path and record.storage_path != "manual" else None,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


# ========== 审批意见智能建议 ==========

@router.post("/suggest-review")
def suggest_review(
    body: ReviewSuggestRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """调用 LLM 生成审批意见智能建议（仅审批管理员可用）"""
    # 权限检查：仅审批角色可用
    if not (user.is_admin or user.is_school_admin or user.is_dept_admin or user.is_finance_admin):
        raise HTTPException(403, "仅审批管理员可使用智能建议")
    record = db.query(ApprovalRecord).filter(
        ApprovalRecord.id == body.record_id,
        ApprovalRecord.hard_deleted == False,
    ).first()
    if not record:
        raise HTTPException(404, "事务不存在")

    # 获取事务数据
    try:
        filled = json.loads(record.filled_json) if record.filled_json else {}
    except (json.JSONDecodeError, TypeError):
        filled = {}

    # 获取模板字段说明
    tpl = get_template(record.document_type) if record.document_type else None
    fields_desc = ""
    if tpl:
        fields_desc = "\n".join([
            f"  - {f['label']} ({f['key']})"
            for f in tpl.get("fields", [])
        ])

    action_label = {"approved": "通过", "rejected": "不通过/驳回", "needs_revision": "需修改"}.get(body.action, body.action)

    prompt = f"""你正在以审批管理员的身份审核一份事务。请**以审批管理员的口气**，直接写出对申请人的审批批语（不要写"建议"或"你应该"之类的第三人称）。批语应直接面向申请人。

申请人提交的事务: {record.document_type or '未知'}
审批决定: {action_label}
审批意见补充: {body.admin_reason or '（无补充）'}

申请人提交的表单数据:
{json.dumps(filled, ensure_ascii=False, indent=2)}

参考字段说明:
{fields_desc if fields_desc else '无'}

要求:
1. 以审批管理员的身份写，用"你"称呼申请人（如"你的报销申请中..."）
2. 如果通过，简要肯定并给出确认信息
3. 如果驳回或需修改，指出具体哪项信息有问题、为什么有问题、需要如何修改
4. 语气专业、简洁、有同理心，50-200字
5. 直接输出批语内容，不要加"批语："等前缀
"""

    # 查找可用的 json_fill Key 调用 LLM
    from models import ApiKey, ApiKeyType
    api_base = ""
    api_key_str = ""
    model = ""
    key_obj = db.query(ApiKey).filter(
        ApiKey.key_type == ApiKeyType.json_fill,
        ApiKey.is_active == True,
    ).order_by(ApiKey.fail_count.asc()).first()
    if key_obj:
        try:
            api_base = key_obj.api_base
            api_key_str = decrypt(key_obj.api_key_encrypted)
            model = key_obj.default_model
        except Exception:
            pass

    if not api_key_str:
        from config import LLM_API_BASE, LLM_API_KEY, LLM_FILL_MODEL
        api_base, api_key_str, model = LLM_API_BASE, LLM_API_KEY, LLM_FILL_MODEL

    if not api_key_str:
        return {"suggestion": "未配置 LLM API Key，无法生成智能建议", "reason": ""}

    try:
        import httpx
        resp = httpx.post(
            f"{api_base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key_str}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 512,
            },
            timeout=30,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return {"suggestion": content.strip(), "reason": body.admin_reason}
    except Exception as e:
        logger.warning(f"智能建议生成失败: {e}")
        return {"suggestion": f"生成建议失败: {e}", "reason": ""}


# ========== 手动申报（无 OCR） ==========

@router.post("/manual", response_model=ApprovalOut)
async def manual_submit(
    body: ManualSubmit,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """用户手动填写表单提交事务（不经过 OCR）"""
    if user.is_admin or user.is_school_admin or user.is_dept_admin or user.is_finance_admin:
        raise HTTPException(403, "管理员账号不能提交事务")

    # 字段归一化
    filled = _normalize_json_keys(body.fields)

    doc_type = body.document_type
    first_stage = get_first_stage(doc_type, filled)

    # 校验必填字段
    tpl = get_template(doc_type)
    if tpl:
        missing = []
        for f in tpl.get("fields", []):
            if f.get("required") and not filled.get(f["key"]):
                missing.append(f["label"])
        if missing:
            raise HTTPException(400, f"缺少必填字段: {', '.join(missing)}")

    record = ApprovalRecord(
        user_id=user.id,
        storage_path=body.storage_path or "manual",
        original_filename=body.original_filename or f"手动申报-{doc_type}",
        document_type=doc_type,
        filled_json=json.dumps(filled, ensure_ascii=False),
        current_stage=first_stage,
        stage_history_json="[]",
        raw_ocr_text=body.raw_ocr_text or f"手动填写申报 - {doc_type}",
        ocr_provider=body.ocr_provider or "manual",
        ocr_model=body.ocr_model or "",
        mime_type=body.mime_type or "",
        file_size=body.file_size or 0,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # 运行审批辅助引擎
    try:
        record = await run_approval(record, db)
    except TimeoutError as e:
        log_error(LogCategory.APPROVAL, f"手动申报审批超时", exc=e, user_id=user.id)
        raise HTTPException(504, "审批超时，请稍后重试")
    except ValueError as e:
        log_error(LogCategory.APPROVAL, f"手动申报审批参数错误", exc=e, user_id=user.id)
        raise HTTPException(400, str(e))
    except Exception as e:
        import uuid
        ref_id = str(uuid.uuid4())[:8]
        log_error(LogCategory.APPROVAL, f"手动申报审批异常 [{ref_id}]", exc=e, user_id=user.id)
        raise HTTPException(500, f"审批流程异常 (追踪ID: {ref_id})")

    # 通知部门管理员：有新的手动申报待审批
    _notify_dept_admins(db, user, record)

    log(
        LogCategory.APPROVAL, "info",
        f"手动申报: {doc_type} → {record.status.value}",
        user_id=user.id, record_id=record.id, doc_type=doc_type,
    )

    return ApprovalOut(
        id=record.id,
        document_type=record.document_type,
        status=record.status.value,
        current_stage=record.current_stage,
        decision_reason=record.decision_reason,
        filled_json=record.filled_json,
        suggestions=record.suggestions,
        missing_info=record.missing_info,
        created_at=record.created_at,
        updated_at=record.updated_at,
        original_filename=record.original_filename,
        image_url=None,
    )


# ========== 智能预审规则检查 ==========

@router.post("/check-rules")
def check_approval_rules(
    record_id: int = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """对一条审批记录执行智能预审规则检查"""
    record = db.query(ApprovalRecord).filter(
        ApprovalRecord.id == record_id,
        ApprovalRecord.is_deleted == False,
    ).first()
    if not record:
        raise HTTPException(404, "记录不存在")

    try:
        filled = json.loads(record.filled_json) if record.filled_json else {}
    except (json.JSONDecodeError, TypeError):
        filled = {}

    from services.rule_engine import check_rules
    result = check_rules(db, record, filled, record.document_type or "")
    return result


# ========== 审批意见模板 CRUD ==========

from models import ApprovalOpinionTemplate
from schemas import OpinionTemplateCreate, OpinionTemplateOut

@router.get("/opinion-templates", response_model=list[OpinionTemplateOut])
def list_opinion_templates(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取当前用户的审批意见模板"""
    if not (user.is_dept_admin or user.is_finance_admin or user.is_school_admin or user.is_admin):
        raise HTTPException(403)
    templates = (
        db.query(ApprovalOpinionTemplate)
        .filter(ApprovalOpinionTemplate.user_id == user.id)
        .order_by(ApprovalOpinionTemplate.sort_order)
        .all()
    )
    return [OpinionTemplateOut.model_validate(t) for t in templates]


@router.post("/opinion-templates", response_model=OpinionTemplateOut)
def create_opinion_template(
    data: OpinionTemplateCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """添加审批意见模板"""
    if not (user.is_dept_admin or user.is_finance_admin or user.is_school_admin or user.is_admin):
        raise HTTPException(403)
    tpl = ApprovalOpinionTemplate(
        user_id=user.id,
        category=data.category,
        content=data.content,
        sort_order=data.sort_order,
    )
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return OpinionTemplateOut.model_validate(tpl)


@router.delete("/opinion-templates/{template_id}")
def delete_opinion_template(
    template_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除审批意见模板"""
    tpl = db.query(ApprovalOpinionTemplate).filter(
        ApprovalOpinionTemplate.id == template_id,
        ApprovalOpinionTemplate.user_id == user.id,
    ).first()
    if not tpl:
        raise HTTPException(404)
    db.delete(tpl)
    db.commit()
    return {"ok": True}


# ========== 审批代理/委托 ==========

from models import ApprovalDelegation
from schemas import DelegationCreate, DelegationOut

@router.get("/delegations", response_model=list[DelegationOut])
def list_delegations(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查看我的委托（我委托别人 + 别人委托我）"""
    given = db.query(ApprovalDelegation).filter(
        ApprovalDelegation.delegator_id == user.id,
        ApprovalDelegation.is_active == True,
    ).all()
    received = db.query(ApprovalDelegation).filter(
        ApprovalDelegation.delegate_id == user.id,
        ApprovalDelegation.is_active == True,
    ).all()

    results = []
    for d in given + received:
        delegate_user = db.query(User).filter(User.id == d.delegate_id).first()
        results.append(DelegationOut(
            id=d.id,
            delegator_id=d.delegator_id,
            delegate_id=d.delegate_id,
            delegate_name=delegate_user.real_name or delegate_user.username if delegate_user else "",
            start_date=d.start_date,
            end_date=d.end_date,
            is_active=d.is_active,
            reason=d.reason,
            created_at=d.created_at,
        ))
    return results


@router.post("/delegations", response_model=DelegationOut)
def create_delegation(
    data: DelegationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """设置审批代理"""
    if not (user.is_dept_admin or user.is_finance_admin or user.is_school_admin):
        raise HTTPException(403)

    # 检查被委托人是否存在且是同校审批角色
    delegate = db.query(User).filter(User.id == data.delegate_id).first()
    if not delegate:
        raise HTTPException(404, "被委托人不存在")

    delegation = ApprovalDelegation(
        delegator_id=user.id,
        delegate_id=data.delegate_id,
        start_date=datetime.fromisoformat(data.start_date),
        end_date=datetime.fromisoformat(data.end_date),
        reason=data.reason,
    )
    db.add(delegation)
    db.commit()
    db.refresh(delegation)

    delegate_user = db.query(User).filter(User.id == delegation.delegate_id).first()
    return DelegationOut(
        id=delegation.id,
        delegator_id=delegation.delegator_id,
        delegate_id=delegation.delegate_id,
        delegate_name=delegate_user.real_name or delegate_user.username if delegate_user else "",
        start_date=delegation.start_date,
        end_date=delegation.end_date,
        is_active=delegation.is_active,
        reason=delegation.reason,
        created_at=delegation.created_at,
    )


@router.delete("/delegations/{delegation_id}")
def cancel_delegation(
    delegation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """取消委托"""
    d = db.query(ApprovalDelegation).filter(
        ApprovalDelegation.id == delegation_id,
        ApprovalDelegation.delegator_id == user.id,
    ).first()
    if not d:
        raise HTTPException(404)
    d.is_active = False
    db.commit()
    return {"ok": True}


# ========== 催办 ==========

from services.notification_service import notify_urged

@router.post("/urge")
def urge_approval(
    record_id: int = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """用户催办待审批的申请"""
    record = db.query(ApprovalRecord).filter(
        ApprovalRecord.id == record_id,
        ApprovalRecord.user_id == user.id,
        ApprovalRecord.is_deleted == False,
    ).first()
    if not record:
        raise HTTPException(404, "记录不存在")
    if record.status != ApprovalStatus.pending:
        raise HTTPException(400, "只能催办待审批状态的申请")

    # 查找当前阶段的审批人
    from models import User as UserModel
    stage = record.current_stage or "dept_review"
    if stage == "dept_review":
        admins = db.query(UserModel).filter(
            UserModel.is_dept_admin == True,
            UserModel.is_active == True,
        ).all()
    elif stage == "finance_review":
        admins = db.query(UserModel).filter(
            UserModel.is_finance_admin == True,
            UserModel.is_active == True,
        ).all()
    elif stage == "school_review":
        admins = db.query(UserModel).filter(
            UserModel.is_school_admin == True,
            UserModel.is_active == True,
        ).all()
    else:
        admins = []

    admin_ids = [a.id for a in admins]

    # 检查代理
    for d in db.query(ApprovalDelegation).filter(
        ApprovalDelegation.delegator_id.in_(admin_ids),
        ApprovalDelegation.is_active == True,
    ).all():
        if d.delegate_id not in admin_ids:
            admin_ids.append(d.delegate_id)

    doc_type_label = record.document_type or "事务"
    notify_urged(db, record_id, admin_ids, user.real_name or user.username, doc_type_label)

    log(LogCategory.APPROVAL, "info",
        f"用户催办: record_id={record_id}", user_id=user.id, record_id=record_id)

    return {"detail": "已催办", "notified_count": len(admin_ids)}
