import React, { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import axios from 'axios'
import { useAuth } from '../../hooks/useAuth'
import { getDocTypeLabel } from '../../constants/docTypes'
import { APPROVAL_STATUS_EMOJI } from '../../constants/approvalStatus'
import GlassCard from '../../components/GlassCard'

// NL 意图识别结果类型
interface IntentResult {
  document_type: string
  doc_label: string
  confidence: number
  prefill_fields: Record<string, string>
}

const TIER_LABEL: Record<string, string> = { free: '免费版', pro: '专业版', pro_plus: '企业版' }

interface TemplateField {
  key: string; label: string; type: string
  required: boolean; options?: string[]; hint?: string
}
interface Template {
  key: string; label: string; icon: string; fields: TemplateField[]
}

// OCR 返回的结果结构
interface OcrResult {
  text: string
  provider: string
  tier: string
  quota_remaining: number | null
  document_type: string | null
  filled_json: Record<string, unknown> | null
  storage_path: string
  original_filename: string
  mime_type: string
  file_size: number
}

// sessionStorage 持久化
const STORAGE_KEY = 'zhishitong_workbench_v2'

function saveState(userId: number, data: {
  ocrResult: OcrResult | null
  formType: string
  formFields: Record<string, string>
}) {
  try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ userId, ...data })) } catch {}
}

function loadState(userId: number) {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (parsed.userId !== userId) { sessionStorage.removeItem(STORAGE_KEY); return null }
    return parsed as { ocrResult: OcrResult | null; formType: string; formFields: Record<string, string> }
  } catch { return null }
}

function clearState() {
  try { sessionStorage.removeItem(STORAGE_KEY) } catch {}
}

// ── 状态机：idle → selected → recognizing → done(success/fail) ──
type OcrPhase = 'idle' | 'selected' | 'recognizing' | 'success' | 'fail'

export default function WorkbenchPage() {
  const { user, refreshUser } = useAuth()
  const nav = useNavigate()
  const [searchParams] = useSearchParams()

  // OCR 上传区
  const [phase, setPhase] = useState<OcrPhase>('idle')
  const [file, setFile] = useState<File | null>(null)
  const [filePreviewUrl, setFilePreviewUrl] = useState<string | null>(null)
  const [ocrResult, setOcrResult] = useState<OcrResult | null>(null)
  const [ocrError, setOcrError] = useState<string>('')
  const [recognizing, setRecognizing] = useState(false)

  // 表单
  const [templates, setTemplates] = useState<Template[]>([])
  const [formType, setFormType] = useState('')
  const [formFields, setFormFields] = useState<Record<string, string>>({})
  const [formSubmitting, setFormSubmitting] = useState(false)
  const [formError, setFormError] = useState('')
  const [submitResult, setSubmitResult] = useState<any>(null)

  // 撤回重新提交
  const [resubmitId, setResubmitId] = useState<number | null>(null)
  const [resubmitLoading, setResubmitLoading] = useState(false)

  // NL 意图识别
  const [nlInput, setNlInput] = useState('')
  const [nlLoading, setNlLoading] = useState(false)
  const [nlResult, setNlResult] = useState<IntentResult | null>(null)
  const [showNlForm, setShowNlForm] = useState(false)
  const [ocrTextOpen, setOcrTextOpen] = useState(false)

  // ── 加载模板 ──
  useEffect(() => {
    axios.get('/api/templates').then(r => setTemplates(r.data || [])).catch(() => {})
  }, [])

  // ── 文件预览 URL ──
  useEffect(() => {
    if (!file) { setFilePreviewUrl(null); return }
    const url = URL.createObjectURL(file)
    setFilePreviewUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  // ── 撤回重新提交：从 URL 参数加载 ──
  useEffect(() => {
    const rid = searchParams.get('resubmit')
    if (!rid || !user) return
    const id = parseInt(rid)
    if (!id) return
    setResubmitLoading(true)
    axios.get(`/api/approvals/${id}`).then(r => {
      const rec = r.data
      setResubmitId(id)
      // 构造一个最小 ocrResult 让表单区出现
      setOcrResult({
        text: '',
        provider: 'resubmit',
        tier: user.tier,
        quota_remaining: null,
        document_type: rec.document_type,
        filled_json: rec.filled_json
          ? (typeof rec.filled_json === 'string' ? JSON.parse(rec.filled_json) : rec.filled_json)
          : {},
        storage_path: 'resubmit',
        original_filename: '',
        mime_type: '',
        file_size: 0,
      })
      setPhase('success')
      if (rec.filled_json) {
        try {
          const parsed = typeof rec.filled_json === 'string' ? JSON.parse(rec.filled_json) : rec.filled_json
          const init: Record<string, string> = {}
          for (const [k, v] of Object.entries(parsed)) init[k] = String(v ?? '')
          setFormFields(init)
        } catch {}
      }
    }).catch(e => {
      alert('加载记录失败: ' + (e?.response?.data?.detail || e.message))
    }).finally(() => setResubmitLoading(false))
  }, [searchParams, user])

  // ── 恢复上次未提交的状态（只在 idle 且没有 file 时执行一次）──
  const [restored, setRestored] = useState(false)
  useEffect(() => {
    if (!user || restored || phase !== 'idle' || file) return
    setRestored(true)
    const saved = loadState(user.id)
    if (!saved) return
    if (saved.ocrResult) {
      setOcrResult(saved.ocrResult)
      setPhase('success')
      setFormType(saved.ocrResult.document_type || saved.formType || '')
    } else {
      setFormType(saved.formType || '')
    }
    setFormFields(saved.formFields || {})
  }, [user, restored, phase, file])

  // ── 客户端文档类型推断（当后端未检测到时兜底）──
  const inferDocTypeFromFields = (filled: Record<string, unknown> | null): string | null => {
    if (!filled || typeof filled !== 'object' || Array.isArray(filled)) return null
    const keys = new Set(Object.keys(filled).filter(k => {
      const v = filled[k]
      return v !== null && v !== '' && v !== undefined
    }))
    if (keys.size === 0) return null

    // 报销：金额 + 发票号 / 金额 + 事由 / 金额 ≥2个字段
    if (keys.has('invoice_no') || keys.has('invoice_number') || keys.has('total_amount')) return 'reimbursement'
    if (keys.has('amount') && keys.size >= 2) return 'reimbursement'

    // 请假：请假类型 / 起止日期 / duration / 去向+交通工具+事由
    if (keys.has('leave_type')) return 'leave'
    if (keys.has('start_date') && keys.has('end_date') && keys.has('reason')) return 'leave'
    if (keys.has('duration')) return 'leave'
    if (keys.has('destination') && keys.has('transportation')) return 'leave'
    if (keys.has('advisor') && keys.has('reason') && keys.has('destination')) return 'leave'

    // 社团活动
    if (keys.has('club_name') || keys.has('activity')) return 'club_application'

    // 教室借用
    if (keys.has('room_no')) return 'classroom_booking'

    // 出差：目的地 + 事由/预估费用
    if (keys.has('destination') && (keys.has('purpose') || keys.has('estimated_cost'))) return 'business_trip'

    // 用章
    if (keys.has('seal_type') || keys.has('document_name')) return 'seal_application'

    // 宿舍调换
    if (keys.has('dorm_from') || keys.has('dorm_to')) return 'dorm_change'

    // 奖学金
    if (keys.has('scholarship_type') || keys.has('gpa') || keys.has('rank')) return 'scholarship'

    // 休学/复学
    if (keys.has('suspend_type')) return 'suspend_resume'

    // 出国
    if (keys.has('country') || keys.has('visa_type') || keys.has('passport_no')) return 'abroad_application'

    // 仅有 applicant + amount → 大概率报销
    if (keys.has('applicant') && keys.has('amount') && keys.size <= 3) return 'reimbursement'

    return null
  }

  // ── OCR 结果填入表单 ──
  useEffect(() => {
    if (!ocrResult?.filled_json || typeof ocrResult.filled_json !== 'object' || Array.isArray(ocrResult.filled_json)) return
    const init: Record<string, string> = {}
    for (const [k, v] of Object.entries(ocrResult.filled_json)) {
      if (v !== null && v !== undefined) init[k] = String(v)
    }
    setFormFields(init)
    // 优先用后端检测结果，否则客户端兜底推断
    if (ocrResult.document_type) {
      setFormType(ocrResult.document_type)
    } else {
      const inferred = inferDocTypeFromFields(ocrResult.filled_json)
      if (inferred) {
        setFormType(inferred)
        // 同时更新 ocrResult 中的 document_type 以保持 UI 一致
        setOcrResult(prev => prev ? { ...prev, document_type: inferred } : prev)
      }
    }
  }, [ocrResult])

  // ── 自动保存 ──
  useEffect(() => {
    if (!user) return
    if (phase === 'success' || formType || Object.keys(formFields).length > 0) {
      saveState(user.id, { ocrResult, formType, formFields })
    }
  }, [ocrResult, formType, formFields, user, phase])

  // ── 重置到初始状态 ──
  const resetAll = () => {
    setPhase('idle')
    setFile(null)
    setFilePreviewUrl(null)
    setOcrResult(null)
    setOcrError('')
    setFormType('')
    setFormFields({})
    setFormError('')
    setSubmitResult(null)
    setShowNlForm(false)
    setNlResult(null)
    setNlInput('')
    setOcrTextOpen(false)
    clearState()
  }

  // ── 选择文件 ──
  const handleFileSelected = (f: File | null) => {
    if (!f) return
    setFile(f)
    setPhase('selected')
    setOcrResult(null)
    setOcrError('')
    setSubmitResult(null)
    setFormError('')
    clearState()
  }

  // ── 开始识别 ──
  const handleRecognize = async () => {
    if (!file || recognizing) return
    setRecognizing(true)
    setPhase('recognizing')
    setOcrError('')
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await axios.post<OcrResult>('/api/ocr', form)
      setOcrResult(res.data)
      setPhase('success')
      refreshUser().catch(() => {})
    } catch (e: any) {
      const msg = e?.response?.data?.detail || '识别失败，请重试'
      setOcrError(msg)
      setPhase('fail')
    } finally {
      setRecognizing(false)
    }
  }

  // ── NL 意图识别 ──
  const handleNlIntent = async () => {
    if (!nlInput.trim() || nlLoading) return
    setNlLoading(true)
    try {
      const res = await axios.post('/api/ai/intent', { text: nlInput.trim() })
      const data: IntentResult = res.data
      setNlResult(data)
      if (data.document_type) {
        setFormType(data.document_type)
        if (data.prefill_fields && Object.keys(data.prefill_fields).length > 0) {
          const fields: Record<string, string> = {}
          for (const [k, v] of Object.entries(data.prefill_fields)) {
            if (v) fields[k] = String(v)
          }
          setFormFields(fields)
        }
        setShowNlForm(true)
      }
    } catch {
      alert('意图识别失败，请重试或手动选择申请类型')
    } finally {
      setNlLoading(false)
    }
  }

  // ── 提交表单 ──
  const handleSubmit = async () => {
    const useType = ocrResult?.document_type || formType
    if (!useType) { alert('请选择事务类型'); return }
    const tpl = templates.find(t => t.key === useType)
    if (tpl) {
      const missing = tpl.fields.filter(f => f.required && !formFields[f.key])
      if (missing.length > 0) {
        alert(`请填写必填字段: ${missing.map(f => f.label).join('、')}`)
        return
      }
    }
    setFormSubmitting(true)
    setFormError('')
    setSubmitResult(null)
    try {
      let res: any
      if (resubmitId) {
        res = await axios.put(`/api/approvals/${resubmitId}/resubmit`, {
          record_id: resubmitId,
          edited_json: formFields,
        })
      } else if (ocrResult && ocrResult.storage_path !== 'resubmit') {
        res = await axios.post('/api/approvals/manual', {
          document_type: useType,
          fields: formFields,
          storage_path: ocrResult.storage_path,
          raw_ocr_text: ocrResult.text,
          original_filename: ocrResult.original_filename,
          mime_type: ocrResult.mime_type,
          file_size: ocrResult.file_size,
          ocr_provider: ocrResult.provider,
          ocr_model: '',
        })
      } else {
        res = await axios.post('/api/approvals/manual', {
          document_type: useType,
          fields: formFields,
        })
      }
      setSubmitResult(res.data)
      setResubmitId(null)
      clearState()
    } catch (e: any) {
      setFormError(e?.response?.data?.detail || '提交失败，请重试')
    } finally {
      setFormSubmitting(false)
    }
  }

  const isAdminUser = !!(user?.is_admin || user?.is_school_admin || user?.is_dept_admin)

  // 已识别到的有效字段（至少一个非空值）
  const hasFilledFields = !!(
    ocrResult?.filled_json &&
    typeof ocrResult.filled_json === 'object' &&
    !Array.isArray(ocrResult.filled_json) &&
    Object.values(ocrResult.filled_json).some(v => v !== null && v !== '' && v !== undefined)
  )

  // 当前选中的模板
  const selectedTemplate = templates.find(t => t.key === (ocrResult?.document_type || formType))

  // 表单区可见：OCR 成功 OR NL 识别成功且有选模板
  const showForm = phase === 'success' || (showNlForm && !!formType)

  return (
    <div>
      <h1 className="page-title">智能审批工作台</h1>
      <p className="page-subtitle">
        当前层级：{TIER_LABEL[user?.tier || 'free']}
        {user?.tier === 'pro' && (
          <span style={{ marginLeft: 12 }}>
            LLM OCR 剩余 {Math.max(0, (user.llm_ocr_quota || 0) - (user.llm_ocr_used || 0))} 次
          </span>
        )}
      </p>

      {/* ── AI 意图识别 ── */}
      {!resubmitId && (
        <GlassCard size="xs" style={{ marginBottom: 12, padding: '12px 16px' }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
            <span>🤖</span> 用自然语言描述申请，AI 自动识别类型并预填表单
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              className="glass-input"
              style={{ flex: 1, fontSize: 13 }}
              placeholder="例如：我要报销上周出差北京的交通费约800元…"
              value={nlInput}
              onChange={e => setNlInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !nlLoading) { e.preventDefault(); handleNlIntent() } }}
            />
            <button
              className="glass-btn glass-btn-sm"
              disabled={nlLoading || !nlInput.trim()}
              onClick={handleNlIntent}
              style={{ flexShrink: 0 }}
            >
              {nlLoading ? '识别中…' : '✨ 识别'}
            </button>
          </div>
          {nlResult && (
            <div style={{
              marginTop: 8, padding: '6px 10px', borderRadius: 8,
              background: 'rgba(52,199,89,0.08)', border: '1px solid rgba(52,199,89,0.2)',
              fontSize: 12, color: 'var(--text-secondary)',
              display: 'flex', alignItems: 'center', gap: 8,
            }}>
              <span>✅</span>
              <span>
                已识别为 <strong style={{ color: '#34C759' }}>{nlResult.doc_label}</strong>
                {Object.keys(nlResult.prefill_fields).length > 0
                  ? `，已预填 ${Object.keys(nlResult.prefill_fields).length} 个字段` : ''}
              </span>
              <span style={{ marginLeft: 'auto', opacity: 0.7 }}>
                置信度 {Math.round(nlResult.confidence * 100)}%
              </span>
            </div>
          )}
        </GlassCard>
      )}

      {/* ── 撤回重新提交提示 ── */}
      {resubmitLoading && (
        <GlassCard style={{ textAlign: 'center', padding: 20, color: 'var(--text-secondary)', marginBottom: 12 }}>
          加载撤回记录...
        </GlassCard>
      )}
      {resubmitId && (
        <GlassCard size="xs" style={{
          marginBottom: 12, background: 'rgba(90,200,250,0.08)',
          border: '1px solid rgba(90,200,250,0.2)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <span>↩️ <strong>正在编辑已撤回的申请 #{resubmitId}</strong> — 修改表单后点击提交将重新进入审批流程</span>
          <button onClick={() => { setResubmitId(null); resetAll(); nav('/history') }}
            className="glass-btn glass-btn-outline glass-btn-sm">取消</button>
        </GlassCard>
      )}

      {/* ── 上传区（撤回重提时不显示） ── */}
      {!resubmitId && (
        <div style={{ marginBottom: 14, animation: 'fadeInUp 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) both' }}>
          <GlassCard strong style={{
            padding: phase === 'success' ? '12px 16px' : '40px 20px',
            textAlign: 'center',
            transition: 'padding 0.4s ease',
          }}>
            {/* ── idle：大按钮选文件 ── */}
            {phase === 'idle' && (
              <div>
                <div style={{ fontSize: 48, marginBottom: 12, opacity: 0.5 }}>📄</div>
                <p style={{ margin: '0 0 16px', color: 'var(--text-secondary)', fontSize: 14 }}>
                  选择图片或 PDF 文件，自动识别文档内容并填写表单
                </p>
                <label className="glass-btn glass-btn-lg" style={{ cursor: 'pointer' }}>
                  选择文件上传
                  <input type="file" accept="image/*,.pdf" style={{ display: 'none' }}
                    onChange={e => handleFileSelected(e.target.files?.[0] || null)} />
                </label>
                <p style={{ margin: '12px 0 0', fontSize: 12, color: 'var(--text-tertiary)' }}>支持 JPG、PNG、PDF，最大 20MB</p>
              </div>
            )}

            {/* ── selected / recognizing：显示文件信息和识别按钮 ── */}
            {(phase === 'selected' || phase === 'recognizing') && file && (
              <div style={{ animation: 'scaleIn 0.3s cubic-bezier(0.34, 1.56, 0.64, 1) both' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 16, textAlign: 'left', justifyContent: 'center', flexWrap: 'wrap' }}>
                  {/* 文件预览 */}
                  <div style={{
                    width: 64, height: 64, borderRadius: 'var(--radius-sm)',
                    background: 'var(--glass-bg)', border: '1px solid var(--glass-border)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    flexShrink: 0, overflow: 'hidden', fontSize: 32,
                  }}>
                    {file.type.startsWith('image/') && filePreviewUrl ? (
                      <img src={filePreviewUrl} alt="预览"
                        style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    ) : file.type === 'application/pdf' ? '📕' : '📄'}
                  </div>
                  {/* 文件信息 */}
                  <div style={{ textAlign: 'left' }}>
                    <div style={{ fontSize: 15, fontWeight: 500 }}>{file.name}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
                      {(file.size / 1024).toFixed(1)} KB · {file.type || '未知格式'}
                    </div>
                  </div>
                  {/* 操作按钮 */}
                  <div className="btn-group" style={{ justifyContent: 'center' }}>
                    <label className="glass-btn glass-btn-outline" style={{ cursor: 'pointer' }}>
                      重新选择
                      <input type="file" accept="image/*,.pdf" style={{ display: 'none' }}
                        onChange={e => handleFileSelected(e.target.files?.[0] || null)} />
                    </label>
                    <button
                      onClick={handleRecognize}
                      disabled={recognizing}
                      className="glass-btn"
                    >
                      {recognizing ? '识别中…' : '开始识别'}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* ── success：紧凑文件条 ── */}
            {phase === 'success' && ocrResult && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{
                  width: 40, height: 40, borderRadius: 'var(--radius-xs)',
                  background: 'rgba(52,199,89,0.12)', border: '1px solid rgba(52,199,89,0.2)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, flexShrink: 0,
                }}>✅</div>
                <div style={{ flex: 1, minWidth: 0, fontSize: 13, textAlign: 'left' }}>
                  <span style={{ fontWeight: 500 }}>
                    {ocrResult.original_filename || file?.name || '识别完成'}
                  </span>
                  <span style={{ color: 'var(--text-secondary)', marginLeft: 8 }}>
                    {ocrResult.provider === 'llm_multimodal' ? '🤖 LLM'
                      : ocrResult.provider === 'pdf_text' ? '📕 PDF文本'
                      : '⚡ OCR'}
                    {ocrResult.document_type && ` · ${getDocTypeLabel(ocrResult.document_type)}`}
                    {ocrResult.quota_remaining != null && ` · 剩余 ${ocrResult.quota_remaining} 次`}
                  </span>
                </div>
                <label className="glass-btn glass-btn-outline glass-btn-sm" style={{ cursor: 'pointer', flexShrink: 0 }}>
                  换文件
                  <input type="file" accept="image/*,.pdf" style={{ display: 'none' }}
                    onChange={e => handleFileSelected(e.target.files?.[0] || null)} />
                </label>
              </div>
            )}

            {/* ── fail：错误提示 ── */}
            {phase === 'fail' && (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
                <div style={{ fontSize: 14, color: 'var(--red)', display: 'flex', alignItems: 'center', gap: 6 }}>
                  {ocrError}
                </div>
                <div className="btn-group">
                  <button onClick={() => setPhase('selected')} className="glass-btn glass-btn-sm">重试识别</button>
                  <button onClick={resetAll} className="glass-btn glass-btn-outline glass-btn-sm">重新选文件</button>
                </div>
              </div>
            )}

            {/* ── success 但字段全空：提示 ── */}
            {phase === 'success' && !hasFilledFields && !resubmitId && (
              <div style={{ fontSize: 13, color: 'var(--orange)', display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'center', flexWrap: 'wrap', marginTop: 12 }}>
                ⚠️ 已提取原文，但未识别出表单字段。请选择事务类型后手动填写。
              </div>
            )}
          </GlassCard>
        </div>
      )}

      {/* ── 表单区 ── */}
      {showForm && (
        <div style={{ animation: 'slideDown 0.4s ease both' }}>
          <GlassCard strong>
            <h3 className="section-title">📋 事务信息</h3>
            <p style={{ fontSize: 12, color: 'var(--text-secondary)', margin: '0 0 16px' }}>
              {resubmitId
                ? '修改表单后点击提交将重新进入审批流程'
                : showNlForm && !ocrResult
                  ? '已根据 AI 意图识别预填，可修改后提交'
                  : hasFilledFields
                    ? 'OCR 已识别字段已自动填入，可编辑后提交'
                    : '已提取原文，请选择事务类型并补全字段后提交'}
            </p>

            {/* 事务类型选择 */}
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>
                事务类型{!(ocrResult?.document_type || formType) && <span style={{ color: 'var(--red)' }}> *</span>}
              </label>
              <select
                value={ocrResult?.document_type || formType}
                onChange={e => {
                  const v = e.target.value
                  if (ocrResult) {
                    setOcrResult(prev => prev ? { ...prev, document_type: v } : prev)
                  }
                  setFormType(v)
                  // 仅在没有 OCR 填充字段时清空（避免冲掉已识别的字段）
                  if (!hasFilledFields) setFormFields({})
                }}
                className="glass-input"
                style={{
                  borderColor: !(ocrResult?.document_type || formType) ? 'var(--red)' : undefined,
                  borderWidth: !(ocrResult?.document_type || formType) ? 2 : undefined,
                }}
              >
                <option value="">-- 请选择事务类型 --</option>
                {templates.map(t => (
                  <option key={t.key} value={t.key}>{t.icon} {t.label}</option>
                ))}
              </select>
              {ocrResult?.document_type || formType ? (
                <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 3 }}>
                  ✅ 已自动识别，如不正确可手动更改
                </div>
              ) : (
                <div style={{ fontSize: 12, color: 'var(--orange)', marginTop: 6, display: 'flex', alignItems: 'center', gap: 4 }}>
                  ⬆️ 请先从上方选择事务类型，选择后对应表单字段将自动出现
                </div>
              )}
            </div>

            {/* 表单字段 */}
            {selectedTemplate && (() => {
              const longFields = selectedTemplate.fields.filter(f => f.type === 'textarea')
              const shortFields = selectedTemplate.fields.filter(f => f.type !== 'textarea')
              const renderField = (f: TemplateField) => {
                const val = formFields[f.key] ?? ''
                return (
                  <div key={f.key} style={f.type === 'textarea' ? { marginBottom: 10 } : {}}>
                    <label style={{ display: 'block', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 2 }}>
                      {f.label}{f.required && <span style={{ color: 'var(--red)' }}> *</span>}
                    </label>
                    {f.type === 'select' && f.options ? (
                      <select value={val} onChange={e => setFormFields(m => ({ ...m, [f.key]: e.target.value }))} className="glass-input">
                        <option value="">-- 请选择 --</option>
                        {f.options.map(o => <option key={o} value={o}>{o}</option>)}
                      </select>
                    ) : f.type === 'boolean' ? (
                      <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, cursor: 'pointer', padding: '6px 0' }}>
                        <input type="checkbox" checked={val === 'true'}
                          onChange={e => setFormFields(m => ({ ...m, [f.key]: e.target.checked ? 'true' : 'false' }))} />
                        {f.label}
                      </label>
                    ) : f.type === 'textarea' ? (
                      <textarea value={val} onChange={e => setFormFields(m => ({ ...m, [f.key]: e.target.value }))}
                        placeholder={f.hint || ''} className="glass-input" style={{ minHeight: 60 }} />
                    ) : (
                      <input
                        type={f.type === 'number' ? 'number' : f.type === 'date' ? 'date' : f.type === 'datetime' ? 'datetime-local' : 'text'}
                        value={val} onChange={e => setFormFields(m => ({ ...m, [f.key]: e.target.value }))}
                        placeholder={f.hint || ''} className="glass-input" />
                    )}
                  </div>
                )
              }
              return (
                <>
                  <div className="responsive-form-grid" style={{ marginBottom: 4 }}>
                    {shortFields.map(renderField)}
                  </div>
                  {longFields.map(renderField)}
                </>
              )
            })()}

            {/* 操作按钮行 */}
            <div className="btn-group" style={{ marginTop: 20, justifyContent: 'flex-end' }}>
              <button onClick={() => {
                if (confirm('确定要清除所有已填写的内容吗？')) resetAll()
              }} className="glass-btn glass-btn-outline glass-btn-sm">
                清空重填
              </button>
              {!isAdminUser && (
                <button
                  onClick={handleSubmit}
                  disabled={formSubmitting || !!(submitResult && !submitResult.error)}
                  className="glass-btn glass-btn-success glass-btn-lg"
                >
                  {formSubmitting ? '提交中…' : '提交审批'}
                </button>
              )}
              {isAdminUser && (
                <div style={{ background: 'rgba(255,149,0,0.1)', border: '1px solid rgba(255,149,0,0.2)', borderRadius: 8, padding: '6px 14px', color: 'var(--orange)', fontSize: 13, fontWeight: 500 }}>
                  管理员不能提交事务
                </div>
              )}
            </div>

            {/* 查看 OCR 原文 */}
            {ocrResult?.text && (
              <div style={{ display: 'inline-block', fontSize: 12, marginTop: 4 }}>
                <div
                  onClick={() => setOcrTextOpen(o => !o)}
                  style={{ cursor: 'pointer', color: 'var(--text-secondary)', fontWeight: 500, userSelect: 'none' }}
                >
                  {ocrTextOpen ? '▾' : '▸'} 查看原文
                </div>
                <div className={`collapsible-section${ocrTextOpen ? ' open' : ''}`}>
                  <div>
                    <div className="collapsible-inner" style={{
                      background: 'var(--glass-bg)', backdropFilter: 'blur(10px)',
                      border: '1px solid var(--glass-border)', padding: 12, borderRadius: 6,
                      maxWidth: 500, maxHeight: 200, overflow: 'auto',
                      fontFamily: 'monospace', fontSize: 11, whiteSpace: 'pre-wrap',
                      marginTop: 4,
                    }}>{ocrResult.text}</div>
                  </div>
                </div>
              </div>
            )}

            {/* 表单级错误 */}
            {formError && (
              <div style={{ marginTop: 10, color: 'var(--red)', fontSize: 13 }}>❌ {formError}</div>
            )}

            {/* 提交结果 */}
            {submitResult && (
              <GlassCard size="xs" style={{
                marginTop: 12,
                background: submitResult.error ? 'rgba(255,59,48,0.08)' : 'rgba(0,122,255,0.08)',
                border: `1px solid ${submitResult.error ? 'var(--red)' : 'var(--accent)'}`,
              }}>
                {submitResult.error ? (
                  <div style={{ color: 'var(--red)' }}>❌ {submitResult.error}</div>
                ) : (
                  <div>
                    <div style={{ color: 'var(--accent)', fontWeight: 600, marginBottom: 4 }}>
                      ✅ {resubmitId ? '重新提交成功' : '提交成功'}，待部门管理员审批
                    </div>
                    {submitResult.decision_reason && (
                      <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 8 }}>
                        {submitResult.decision_reason}
                      </div>
                    )}
                    {submitResult.suggestions && (() => {
                      try {
                        const sug = JSON.parse(submitResult.suggestions)
                        if (Array.isArray(sug) && sug.length > 0) return (
                          <div className="glass-card glass-card-xs" style={{ background: 'rgba(255,149,0,0.1)', border: 'none', marginBottom: 8 }}>
                            <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--orange)', marginBottom: 4 }}>💡 系统建议</div>
                            {sug.map((s: string, i: number) => <div key={i} style={{ fontSize: 13, color: 'var(--text-secondary)' }}>• {s}</div>)}
                          </div>
                        )
                      } catch {} return null
                    })()}
                    <button onClick={() => nav('/history')} className="glass-btn">查看历史记录</button>
                  </div>
                )}
              </GlassCard>
            )}
          </GlassCard>
        </div>
      )}
    </div>
  )
}
