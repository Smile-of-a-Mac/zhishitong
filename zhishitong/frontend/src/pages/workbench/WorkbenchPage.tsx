import React, { useState, useEffect, useCallback } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import axios from 'axios'
import { useAuth } from '../../hooks/useAuth'
import { getDocTypeLabel, DOC_TYPE_LABELS } from '../../constants/docTypes'
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

// sessionStorage key + userId 校验（防止切换用户后看到上一个人的数据）
const STORAGE_KEY = 'zhishitong_workbench'

function saveState(userId: number, result: any, formType: string, formFields: Record<string, string>) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ userId, result, formType, formFields }))
  } catch {}
}

function loadState(userId: number): { result: any; formType: string; formFields: Record<string, string> } | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    // 归属校验：只恢复当前用户的数据
    if (parsed.userId !== userId) {
      sessionStorage.removeItem(STORAGE_KEY)
      return null
    }
    return parsed
  } catch { return null }
}

function clearState() {
  try { sessionStorage.removeItem(STORAGE_KEY) } catch {}
}

export default function WorkbenchPage() {
  const { user, refreshUser } = useAuth()
  const nav = useNavigate()
  const [file, setFile] = useState<File | null>(null)
  // 管理 object URL 防止内存泄漏
  const [fileObjectUrl, setFileObjectUrl] = useState<string | null>(null)
  const [result, setResult] = useState<any>(null)
  const [editFields, setEditFields] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [submitResult, setSubmitResult] = useState<any>(null)

  // 固定表单
  const [templates, setTemplates] = useState<Template[]>([])
  const [formType, setFormType] = useState('')
  const [formFields, setFormFields] = useState<Record<string, string>>({})
  const [formSubmitting, setFormSubmitting] = useState(false)
  const [formResult, setFormResult] = useState<any>(null)
  const [searchParams] = useSearchParams()
  const [resubmitId, setResubmitId] = useState<number | null>(null)
  const [resubmitLoading, setResubmitLoading] = useState(false)

  // NL 意图识别状态
  const [nlInput, setNlInput] = useState('')
  const [nlLoading, setNlLoading] = useState(false)
  const [nlResult, setNlResult] = useState<IntentResult | null>(null)
  const [showManualEntry, setShowManualEntry] = useState(false)

  // 加载模板
  useEffect(() => {
    axios.get('/api/templates').then(r => setTemplates(r.data || [])).catch(() => {})
  }, [])

  // 管理文件预览 URL（防止内存泄漏）
  useEffect(() => {
    if (!file) {
      if (fileObjectUrl) { URL.revokeObjectURL(fileObjectUrl); setFileObjectUrl(null) }
      return
    }
    const url = URL.createObjectURL(file)
    setFileObjectUrl(url)
    return () => { URL.revokeObjectURL(url) }
  }, [file])

  // 撤回后重新提交：加载已有记录到编辑表单
  useEffect(() => {
    const rid = searchParams.get('resubmit')
    if (!rid || !user) return
    const id = parseInt(rid)
    if (!id) return
    setResubmitLoading(true)
    axios.get(`/api/approvals/${id}`).then(r => {
      const rec = r.data
      setResubmitId(id)
      setResult({
        record_id: id,
        document_type: rec.document_type,
        filled_json: rec.filled_json ? JSON.parse(rec.filled_json) : {},
        provider: 'resubmit',
        text: '',
      })
      if (rec.filled_json) {
        try {
          const parsed = typeof rec.filled_json === 'string' ? JSON.parse(rec.filled_json) : rec.filled_json
          const init: Record<string, string> = {}
          for (const [k, v] of Object.entries(parsed)) {
            init[k] = String(v ?? '')
          }
          setFormFields(init)
        } catch {}
      }
    }).catch(e => {
      alert('加载记录失败: ' + (e?.response?.data?.detail || e.message))
    }).finally(() => setResubmitLoading(false))
  }, [searchParams, user])

  // 恢复上次状态
  useEffect(() => {
    if (!user) return
    const saved = loadState(user.id)
    if (saved) {
      setResult(saved.result)
      setFormType(saved.formType)
      setFormFields(saved.formFields)
    }
  }, [user])


  // 状态变化时自动保存
  useEffect(() => {
    if (!user) return
    if (result || formType || Object.keys(formFields).length > 0) {
      saveState(user.id, result, formType, formFields)
    }
  }, [result, formType, formFields, user])

  const selectedTemplate = templates.find(t => t.key === (result?.document_type || formType))

  // OCR 结果更新时自动填入表单
  useEffect(() => {
    if (result?.filled_json && typeof result.filled_json === 'object') {
      const init: Record<string, string> = {}
      for (const [k, v] of Object.entries(result.filled_json)) {
        init[k] = String(v ?? '')
      }
      setFormFields(init)
    }
  }, [result?.filled_json])

  // 提交：有 OCR 存储路径走申报，否则走手动申报
  const handleFormSubmit = async () => {
    const useType = result?.document_type || formType
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
    setFormResult(null)
    setSubmitResult(null)
    try {
      if (resubmitId) {
        // 撤回后重新提交 → 走 resubmit 接口
        const res = await axios.put(`/api/approvals/${resubmitId}/resubmit`, {
          record_id: resubmitId,
          edited_json: formFields,
        })
        setSubmitResult(res.data)
        setResubmitId(null)
        clearState()
      } else if (result?.storage_path) {
        // OCR 后有结果 → 走手动申报，同时附带 OCR 文件信息
        const res = await axios.post('/api/approvals/manual', {
          document_type: result.document_type || formType,
          fields: formFields,
          storage_path: result.storage_path,
          raw_ocr_text: result.text,
          original_filename: result.original_filename,
          mime_type: result.mime_type,
          file_size: result.file_size,
          ocr_provider: result.provider,
          ocr_model: '',  // 由后端记录
        })
        setSubmitResult(res.data)
        clearState()
      } else {
        // 无 OCR → 手动申报
        const res = await axios.post('/api/approvals/manual', {
          document_type: formType,
          fields: formFields,
        })
        setFormResult(res.data)
        setFormFields({})
        setFormType('')
        clearState()
      }
    } catch (e: any) {
      const err = e?.response?.data?.detail || '提交失败'
      if (result?.storage_path) {
        setSubmitResult({ error: err })
      } else {
        setFormResult({ error: err })
      }
    } finally { setFormSubmitting(false) }
  }

  const statusLabel = (s: string) =>
    s === 'approved' ? '✅ 已通过' : s === 'rejected' ? '❌ 退回' :
    s === 'pending' ? '⏳ 待审批' : s === 'needs_revision' ? '📝 需修改' :
    s === 'withdrawn' ? '↩️ 已撤回' : s === 'cancelled' ? '⊘ 已取消' : s

  const isAdminUser = user?.is_admin || user?.is_school_admin || user?.is_dept_admin

  // NL 意图识别处理器
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
        setShowManualEntry(true)
        setResult(null) // 清除 OCR 结果避免冲突
      }
    } catch {
      alert('意图识别失败，请重试或手动选择申请类型')
    } finally {
      setNlLoading(false)
    }
  }

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
              onKeyDown={e => {
                if (e.key === 'Enter' && !nlLoading) {
                  e.preventDefault()
                  handleNlIntent()
                }
              }}
            />
            <button
              className={`glass-btn glass-btn-sm${nlLoading ? '' : ''}`}
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
                  ? `，已预填 ${Object.keys(nlResult.prefill_fields).length} 个字段`
                  : ''}
              </span>
              <span style={{ marginLeft: 'auto', opacity: 0.7 }}>
                置信度 {Math.round(nlResult.confidence * 100)}%
              </span>
            </div>
          )}
        </GlassCard>
      )}

      {/* 撤回重新提交提示 */}
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
          <button onClick={() => { setResubmitId(null); setResult(null); setFormFields({}); clearState(); nav('/history') }}
            className="glass-btn glass-btn-outline glass-btn-sm">取消</button>
        </GlassCard>
      )}

      {/* ---- 上传区（大卡片，重提交时不显示） ---- */}
      {!resubmitId && (
      <div style={{
        transition: 'all 0.5s cubic-bezier(0.34, 1.56, 0.64, 1)',
        animation: 'fadeInUp 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) both',
      }}>
        <GlassCard strong style={{
          padding: result && !result.error ? '12px 16px' : '40px 20px',
          textAlign: 'center',
          transition: 'all 0.5s cubic-bezier(0.34, 1.56, 0.64, 1)',
        }}>
          {/* ── 未选文件 / 大卡片状态 ── */}
          {!file && !result && (
            <div style={{ transition: 'all 0.3s ease' }}>
              <div style={{ fontSize: 48, marginBottom: 12, opacity: 0.5 }}>📄</div>
              <p style={{ margin: '0 0 16px', color: 'var(--text-secondary)', fontSize: 14 }}>
                选择图片或 PDF 文件，自动识别文档内容并填写表单
              </p>
              <label className="glass-btn" style={{ cursor: 'pointer', padding: '10px 36px', fontSize: 15 }}>
                📁 选择文件
                <input type="file" accept="image/*,.pdf" style={{ display: 'none' }}
                  onChange={e => { setFile(e.target.files?.[0] || null); setResult(null); setSubmitResult(null); setFormResult(null); clearState() }} />
              </label>
            </div>
          )}

          {/* ── 已选文件，等待识别 ── */}
          {file && !result && (
            <div style={{ animation: 'scaleIn 0.3s cubic-bezier(0.34, 1.56, 0.64, 1) both' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 16, textAlign: 'left', justifyContent: 'center', flexWrap: 'wrap' }}>
                <div style={{
                  width: 64, height: 64, borderRadius: 'var(--radius-sm)',
                  background: 'var(--glass-bg)', border: '1px solid var(--glass-border)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  flexShrink: 0, overflow: 'hidden', fontSize: 32,
                }}>
                  {file.type.startsWith('image/') ? (
                    <img src={fileObjectUrl || ''} alt="预览"
                      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      onError={e => { (e.target as HTMLImageElement).style.display = 'none'; (e.target as HTMLImageElement).parentElement!.innerHTML = '🖼️' }}
                    />
                  ) : file.type === 'application/pdf' ? '📕' : '📄'}
                </div>
                <div style={{ textAlign: 'left' }}>
                  <div style={{ fontSize: 15, fontWeight: 500 }}>{file.name}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
                    {(file.size / 1024).toFixed(1)} KB · {file.type || '未知格式'}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <label className="glass-btn glass-btn-outline" style={{ cursor: 'pointer' }}>
                    🔄 重新选择
                    <input type="file" accept="image/*,.pdf" style={{ display: 'none' }}
                      onChange={e => { setFile(e.target.files?.[0] || null); setResult(null); setSubmitResult(null); setFormResult(null); clearState() }} />
                  </label>
                  <button onClick={async () => {
                    if (!file) return
                    setLoading(true); setResult(null); setSubmitResult(null); setFormResult(null); clearState()
                    try {
                      const form = new FormData()
                      form.append('file', file)
                      const res = await axios.post('/api/ocr', form)
                      setResult(res.data)
                      await refreshUser()
                    } catch (e: any) {
                      setResult({ error: e?.response?.data?.detail || '识别失败' })
                    } finally { setLoading(false) }
                  }} disabled={loading} className="glass-btn" style={{ fontSize: 14, padding: '8px 24px' }}>
                    {loading ? '⏳ 识别中...' : '🤖 开始识别'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* ── 识别完成 / 紧凑预览 ── */}
          {result && !result.error && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 12,
              transition: 'all 0.3s ease',
            }}>
              <div style={{
                width: 40, height: 40, borderRadius: 'var(--radius-xs)',
                background: 'rgba(52,199,89,0.12)', border: '1px solid rgba(52,199,89,0.2)',
                display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, flexShrink: 0,
              }}>✅</div>
              <div style={{ flex: 1, minWidth: 0, fontSize: 13 }}>
                <span style={{ fontWeight: 500 }}>
                  {file?.name || '识别完成'}
                </span>
                <span style={{ color: 'var(--text-secondary)', marginLeft: 8 }}>
                  {result.provider === 'llm_multimodal' ? '🤖 LLM' : '⚡ OCR'}
                  · {getDocTypeLabel(result.document_type)}
                  {result.quota_remaining !== null && ` · 剩余 ${result.quota_remaining} 次`}
                </span>
              </div>
              <label className="glass-btn glass-btn-outline glass-btn-sm" style={{ cursor: 'pointer', flexShrink: 0 }}>
                🔄 重新上传
                <input type="file" accept="image/*,.pdf" style={{ display: 'none' }}
                  onChange={e => { setFile(e.target.files?.[0] || null); setResult(null); setSubmitResult(null); setFormResult(null); clearState() }} />
              </label>
            </div>
          )}
          {/* ── OCR 错误 ── */}
          {result?.error && (
            <div style={{ fontSize: 13, color: 'var(--red)', display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'center', flexWrap: 'wrap' }}>
              ❌ {result.error}
              <button onClick={() => { setResult(null); setFile(null); clearState() }} className="glass-btn glass-btn-outline glass-btn-sm">重试</button>
            </div>
          )}

          {/* ── OCR 成功但未识别到任何数据 ── */}
          {result && !result.error && (!result.filled_json || typeof result.filled_json === 'string' || (typeof result.filled_json === 'object' && Object.keys(result.filled_json).length === 0)) && (
            <div style={{ fontSize: 13, color: 'var(--orange)', display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'center', flexWrap: 'wrap', marginTop: 8 }}>
              ⚠️ 未识别到任何表单数据，请确认上传的是清晰可读的申请表或重新上传
              <button onClick={() => { setResult(null); setFile(null); clearState() }} className="glass-btn glass-btn-outline glass-btn-sm">重新上传</button>
            </div>
          )}

          {/* ── OCR 成功但所有字段为空 ── */}
          {result && !result.error && result.filled_json && typeof result.filled_json === 'object' && Object.keys(result.filled_json).length > 0 && !Object.values(result.filled_json).some((v: any) => v !== null && v !== '' && v !== undefined) && (
            <div style={{ fontSize: 13, color: 'var(--orange)', display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'center', flexWrap: 'wrap', marginTop: 8 }}>
              ⚠️ 识别到表单模板但未能提取有效内容，请手动填写或更换更清晰的图片
              <button onClick={() => { setResult(null); setFile(null); clearState() }} className="glass-btn glass-btn-outline glass-btn-sm">手动填写</button>
            </div>
          )}
        </GlassCard>
      </div>
      )}

      {/* ---- 表单（识别到有效数据后才出现，或 NL 意图识别成功后显示） ---- */}
      {((result && !result.error && result.filled_json && typeof result.filled_json === 'object' && Object.keys(result.filled_json).length > 0 && Object.values(result.filled_json).some((v: any) => v !== null && v !== '' && v !== undefined)) || (showManualEntry && formType)) && (
        <div style={{
          overflow: 'hidden',
          animation: 'slideDown 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) forwards',
        }}>
          <GlassCard strong>
        <h3 className="section-title">📋 事务信息</h3>
        <p style={{ fontSize: 12, color: 'var(--text-secondary)', margin: '0 0 16px' }}>
          {showManualEntry && !result ? '已根据 AI 意图识别预填，可修改后提交' : 'OCR 已识别字段已自动填入，可编辑后提交'}
        </p>

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', fontSize: 12, color: '#888', marginBottom: 4 }}>事务类型</label>
          <select value={result?.document_type || formType} onChange={e => {
            const v = e.target.value
            if (!result?.storage_path) {
              setFormType(v)
              setFormFields({})
              setFormResult(null)
            }
          }} disabled={!!result?.storage_path} style={{
            width: '100%', padding: '6px 10px', border: '1px solid #d9d9d9',
            borderRadius: 4, fontSize: 13, background: result?.storage_path ? '#f5f5f5' : '#fff',
          }}>
            <option value="">-- 请选择 --</option>
            {templates.map(t => (
              <option key={t.key} value={t.key}>{t.icon} {t.label}</option>
            ))}
          </select>
        </div>

        {selectedTemplate && (() => {
          const isLongField = (f: TemplateField) => f.type === 'textarea'
          const shortFields = selectedTemplate.fields.filter(f => !isLongField(f))
          const longFields = selectedTemplate.fields.filter(f => isLongField(f))

          return (
            <>
              {/* 短字段：响应式双列网格 */}
              <div className="responsive-form-grid" style={{ marginBottom: 4 }}>
                {shortFields.map(f => {
                  const val = formFields[f.key] ?? ''
                  return (
                    <div key={f.key}>
                      <label style={{ display: 'block', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 2 }}>
                        {f.label} {f.required && <span style={{ color: 'var(--red)' }}>*</span>}
                      </label>
                      {f.type === 'select' && f.options ? (
                        <select value={val} onChange={e => setFormFields(m => ({ ...m, [f.key]: e.target.value }))} className="glass-input">
                          <option value="">-- 请选择 --</option>
                          {f.options.map(o => <option key={o} value={o}>{o}</option>)}
                        </select>
                      ) : f.type === 'boolean' ? (
                        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, cursor: 'pointer', padding: '6px 0' }}>
                          <input type="checkbox" checked={val === 'true'} onChange={e => setFormFields(m => ({ ...m, [f.key]: e.target.checked ? 'true' : 'false' }))} />
                          {f.label}
                        </label>
                      ) : (
                        <input type={f.type === 'number' ? 'number' : f.type === 'date' ? 'date' : 'text'}
                          value={val} onChange={e => setFormFields(m => ({ ...m, [f.key]: e.target.value }))}
                          placeholder={f.hint || ''} className="glass-input" />
                      )}
                    </div>
                  )
                })}
              </div>
              {/* 长字段：独占一行 */}
              {longFields.map(f => {
                const val = formFields[f.key] ?? ''
                return (
                  <div key={f.key} style={{ marginBottom: 10 }}>
                    <label style={{ display: 'block', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 2 }}>
                      {f.label} {f.required && <span style={{ color: 'var(--red)' }}>*</span>}
                    </label>
                    <textarea value={val} onChange={e => setFormFields(m => ({ ...m, [f.key]: e.target.value }))}
                      placeholder={f.hint || ''} className="glass-input" style={{ minHeight: 56 }} />
                  </div>
                )
              })}
            </>
          )
        })()}

        <div style={{ marginTop: 16, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          {(result?.storage_path || formType) && !isAdminUser && (
            <button onClick={handleFormSubmit} disabled={formSubmitting} className="glass-btn glass-btn-success" style={{ fontSize: 14, padding: '8px 24px' }}>
              {formSubmitting ? '提交中...' : '✅ 提交审批'}
            </button>
          )}
          {(result || formType || Object.keys(formFields).length > 0) && (
            <button onClick={() => {
              if (confirm('清除当前填写的内容？')) {
                setResult(null); setFormType(''); setFormFields({}); setSubmitResult(null); setFormResult(null); clearState()
              }
            }} className="glass-btn glass-btn-outline">🗑️ 清除</button>
          )}
          {isAdminUser && (
            <div className="glass-card glass-card-xs" style={{ background: 'rgba(255,149,0,0.1)', border: 'none', color: 'var(--orange)', fontSize: 13 }}>
              ⚠️ 管理员不能提交事务
            </div>
          )}
          {result?.text && (
            <details style={{ display: 'inline-block', fontSize: 12 }}>
              <summary style={{ cursor: 'pointer', color: 'var(--text-secondary)' }}>查看原文</summary>
              <div style={{
                position: 'absolute', background: 'var(--glass-bg)', backdropFilter: 'blur(10px)',
                border: '1px solid var(--glass-border)', padding: 12, borderRadius: 6,
                maxWidth: 500, maxHeight: 200, overflow: 'auto',
                fontFamily: 'monospace', fontSize: 11, whiteSpace: 'pre-wrap', zIndex: 100,
              }}>{result.text}</div>
            </details>
          )}
        </div>

        {/* 手动申报结果 */}
        {formResult && (
          <GlassCard size="xs" style={{ marginTop: 12, background: formResult.error ? 'rgba(255,59,48,0.08)' : 'rgba(52,199,89,0.08)', border: `1px solid ${formResult.error ? 'var(--red)' : 'var(--green)'}` }}>
            {formResult.error ? (
              <div style={{ color: 'var(--red)' }}>❌ {formResult.error}</div>
            ) : (
              <div>
                <div style={{ color: 'var(--green)', fontWeight: 600, marginBottom: 4 }}>✅ 申报成功，待审批</div>
                <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{formResult.decision_reason}</div>
              </div>
            )}
          </GlassCard>
        )}

        {/* 审批提交结果 */}
        {submitResult && (
          <GlassCard size="xs" style={{ marginTop: 12, background: submitResult.error ? 'rgba(255,59,48,0.08)' : 'rgba(0,122,255,0.08)', border: `1px solid ${submitResult.error ? 'var(--red)' : 'var(--accent)'}` }}>
            {submitResult.error ? (
              <div style={{ color: 'var(--red)' }}>❌ {submitResult.error}</div>
            ) : (
              <div>
                <div style={{ color: 'var(--accent)', fontWeight: 600, marginBottom: 4 }}>✅ 提交成功，待部门管理员审批</div>
                <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 8 }}>{submitResult.decision_reason}</div>
                {submitResult.suggestions && (() => {
                  try {
                    const sug = JSON.parse(submitResult.suggestions);
                    if (Array.isArray(sug) && sug.length > 0) return (
                      <div className="glass-card glass-card-xs" style={{ background: 'rgba(255,149,0,0.1)', border: 'none', marginBottom: 8 }}>
                        <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--orange)', marginBottom: 4 }}>💡 系统建议</div>
                        {sug.map((s: string, i: number) => <div key={i} style={{ fontSize: 13, color: 'var(--text-secondary)' }}>• {s}</div>)}
                      </div>
                    );
                  } catch {} return null;
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
