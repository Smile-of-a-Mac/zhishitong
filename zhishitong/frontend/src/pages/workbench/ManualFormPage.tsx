import React, { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import axios from 'axios'
import GlassCard from '../../components/GlassCard'
import { useAuth } from '../../hooks/useAuth'
import { getDocLabel, getDocIcon, VALID_DOC_TYPES } from '../../constants/docTypes'
import { useFormStorage } from '../../hooks/useFormStorage'

interface TemplateField {
  key: string; label: string; type: string
  required: boolean; options?: string[]; hint?: string
}
interface Template {
  key: string; label: string; icon: string; fields: TemplateField[]
}

export default function ManualFormPage() {
  const { docType } = useParams<{ docType: string }>()
  const nav = useNavigate()
  const { user } = useAuth()
  const [templates, setTemplates] = useState<Template[]>([])
  const { data: formFields, setData: setFormFields, clear: clearFormStorage } = useFormStorage<Record<string, string>>(
    user?.id, `manual_${docType}`, {}
  )
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<any>(null)

  useEffect(() => {
    axios.get('/api/templates').then(r => {
      setTemplates(r.data || [])
    }).catch(() => {})
  }, [docType])

  const tpl = templates.find(t => t.key === docType)

  // 自动计算请假天数
  const computedDays = (() => {
    if (docType !== 'leave') return null
    const s = formFields['start_date']
    const e = formFields['end_date']
    if (s && e) {
      const d1 = new Date(s), d2 = new Date(e)
      const diff = Math.ceil((d2.getTime() - d1.getTime()) / 86400000)
      return diff >= 0 ? diff + 1 : 0
    }
    return null
  })()

  const handleSubmit = async () => {
    if (!docType || !tpl) { alert('无效的事务类型'); return }
    const missing = tpl.fields.filter(f => f.required && !formFields[f.key])
    if (missing.length > 0) {
      alert(`请填写必填字段: ${missing.map(f => f.label).join('、')}`)
      return
    }
    setSubmitting(true); setResult(null)
    try {
      const submitData = { ...formFields }
      if (computedDays !== null) submitData['days'] = String(computedDays)
      const res = await axios.post('/api/approvals/manual', {
        document_type: docType,
        fields: submitData,
      })
      setResult(res.data)
      clearFormStorage()
    } catch (e: any) {
      setResult({ error: e?.response?.data?.detail || '提交失败' })
    } finally { setSubmitting(false) }
  }

  const icon = getDocIcon(docType)
  const title = getDocLabel(docType)

  if (!docType || !VALID_DOC_TYPES.includes(docType)) {
    return <GlassCard style={{ textAlign: 'center', color: 'var(--text-secondary)' }}>未知的事务类型</GlassCard>
  }

  // 部门管理员不能提交请假/社团活动（避免审批自己提交的申请）
  if (user?.is_dept_admin && (docType === 'leave' || docType === 'club_application')) {
    return (
      <GlassCard style={{ textAlign: 'center', color: 'var(--text-secondary)', padding: 40 }}>
        <div style={{ fontSize: 40, marginBottom: 12 }}>🚫</div>
        <p>部门管理员不能提交「{getDocLabel(docType)}」申请</p>
        <p style={{ fontSize: 13 }}>请使用普通用户账号提交，避免审批自己提交的申请</p>
        <button onClick={() => nav('/dept')} className="glass-btn glass-btn-sm" style={{ marginTop: 8 }}>返回部门管理</button>
      </GlassCard>
    )
  }

  return (
    <div>
      <h1 className="page-title" style={{ marginBottom: 4 }}>{icon} {title}</h1>
      <p className="page-subtitle">手动填写信息后提交审批</p>

      {!tpl ? <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-secondary)' }}>加载中...</div> : (
        <GlassCard strong>
          {(() => {
            const isLongField = (f: TemplateField) => f.type === 'textarea'
            const shortFields = tpl.fields.filter(f => !isLongField(f))
            const longFields = tpl.fields.filter(f => isLongField(f))

            const renderField = (f: TemplateField) => {
              const val = formFields[f.key] ?? ''
              const isDaysAuto = f.key === 'days' && computedDays !== null
              const fieldId = `field_${f.key}`
              return (
                <>
                  <label htmlFor={fieldId} style={{ display: 'block', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 2 }}>
                    {f.label} {f.required && <span style={{ color: 'var(--red)' }}>*</span>}
                    {isDaysAuto && (
                      <span style={{ marginLeft: 8, color: 'var(--accent)', fontWeight: 600 }}>（自动计算: {computedDays}天）</span>
                    )}
                  </label>
                  {f.type === 'select' && f.options ? (
                    <select id={fieldId} value={val} onChange={e => setFormFields(m => ({ ...m, [f.key]: e.target.value }))} className="glass-input">
                      <option value="">-- 请选择 --</option>
                      {f.options.map(o => <option key={o} value={o}>{o}</option>)}
                    </select>
                  ) : f.type === 'boolean' ? (
                    <label htmlFor={fieldId} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, cursor: 'pointer', padding: '6px 0' }}>
                      <input id={fieldId} type="checkbox" checked={val === 'true'} onChange={e => setFormFields(m => ({ ...m, [f.key]: e.target.checked ? 'true' : 'false' }))} />
                      {f.label}
                    </label>
                  ) : f.type === 'textarea' ? (
                    <textarea id={fieldId} value={val} onChange={e => setFormFields(m => ({ ...m, [f.key]: e.target.value }))}
                      placeholder={f.hint || ''} className="glass-input" style={{ minHeight: 60 }} />
                  ) : (
                    <input id={fieldId} type={f.type === 'number' ? 'number' : f.type === 'date' ? 'date' : f.type === 'datetime' ? 'datetime-local' : 'text'}
                      value={isDaysAuto ? computedDays! : val}
                      onChange={e => setFormFields(m => ({ ...m, [f.key]: e.target.value }))}
                      disabled={isDaysAuto}
                      placeholder={f.hint || ''} className="glass-input" />
                  )}
                  {f.hint && !isDaysAuto && <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 2 }}>{f.hint}</div>}
                </>
              )
            }

            return (
              <>
                {/* 短字段：响应式双列网格 */}
                <div className="responsive-form-grid" style={{ marginBottom: 4 }}>
                  {shortFields.map(f => (
                    <div key={f.key}>{renderField(f)}</div>
                  ))}
                </div>
                {/* 长字段：独占一行 */}
                {longFields.map(f => (
                  <div key={f.key} style={{ marginBottom: 10 }}>{renderField(f)}</div>
                ))}
              </>
            )
          })()}

          <button onClick={handleSubmit} disabled={submitting} className="glass-btn" style={{ marginTop: 16, padding: '8px 32px', fontSize: 14, width: '100%' }}>
            {submitting ? '提交中...' : '📤 提交申报'}
          </button>

          {result && (
            <GlassCard size="xs" style={{ marginTop: 12, background: result.error ? 'rgba(255,59,48,0.08)' : 'rgba(52,199,89,0.08)', border: `1px solid ${result.error ? 'var(--red)' : 'var(--green)'}` }}>
              {result.error ? (
                <div style={{ color: 'var(--red)' }}>❌ {result.error}</div>
              ) : (
                <div>
                  <div style={{ color: 'var(--green)', fontWeight: 600 }}>✅ 申报成功</div>
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>{result.decision_reason}</div>
                  <button onClick={() => nav('/history')} className="glass-btn glass-btn-outline glass-btn-sm" style={{ marginTop: 8 }}>查看历史</button>
                </div>
              )}
            </GlassCard>
          )}
        </GlassCard>
      )}
    </div>
  )
}
