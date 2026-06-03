import React, { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import axios from 'axios'
import GlassCard from '../../components/GlassCard'
import { useAuth } from '../../hooks/useAuth'
import { getDocLabel, getDocIcon, VALID_DOC_TYPES } from '../../constants/docTypes'
import { useFormStorage } from '../../hooks/useFormStorage'
import { normalizeFormInputValue } from '../../utils/formValues'

interface TemplateField {
  key: string; label: string; type: string
  required: boolean; options?: string[]; hint?: string
}
interface Template {
  key: string; label: string; icon: string; fields: TemplateField[]
}
interface ComplianceItem {
  item: string
  status: 'ok' | 'warning' | 'error'
  detail: string
}
interface ComplianceResult {
  risk_level: 'low' | 'medium' | 'high'
  compliance_summary: string
  compliance_items: ComplianceItem[]
  suggestions: string[]
  policy_hits: { doc_title: string; text: string }[]
}

const RISK_COLOR: Record<ComplianceResult['risk_level'], string> = {
  low: 'var(--green)',
  medium: 'var(--orange)',
  high: 'var(--red)',
}
const RISK_LABEL: Record<ComplianceResult['risk_level'], string> = {
  low: '低风险',
  medium: '中等风险',
  high: '高风险',
}
const STATUS_ICON: Record<ComplianceItem['status'], string> = {
  ok: '✅',
  warning: '⚠️',
  error: '❌',
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
  const [checkingCompliance, setCheckingCompliance] = useState(false)
  const [compliance, setCompliance] = useState<ComplianceResult | null>(null)
  const [complianceError, setComplianceError] = useState('')
  const [complianceSnapshot, setComplianceSnapshot] = useState('')
  const [policyOpen, setPolicyOpen] = useState(false)
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

  const buildSubmitData = () => {
    const submitData = { ...formFields }
    if (computedDays !== null) submitData['days'] = String(computedDays)
    return submitData
  }

  const handleComplianceCheck = async () => {
    if (!docType || !tpl) { alert('无效的事务类型'); return }
    const submitData = buildSubmitData()
    setCheckingCompliance(true)
    setComplianceError('')
    setPolicyOpen(false)
    try {
      const res = await axios.post('/api/ai/manual-compliance', {
        document_type: docType,
        fields: submitData,
      })
      setCompliance(res.data)
      setComplianceSnapshot(JSON.stringify(submitData))
    } catch (e: any) {
      setComplianceError(e?.response?.data?.detail || '合规自查失败，请稍后重试')
    } finally {
      setCheckingCompliance(false)
    }
  }

  const handleSubmit = async () => {
    if (!docType || !tpl) { alert('无效的事务类型'); return }
    const missing = tpl.fields.filter(f => f.required && !formFields[f.key])
    if (missing.length > 0) {
      alert(`请填写必填字段: ${missing.map(f => f.label).join('、')}`)
      return
    }
    setSubmitting(true); setResult(null)
    try {
      const submitData = buildSubmitData()
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
  const complianceStale = compliance && JSON.stringify(buildSubmitData()) !== complianceSnapshot

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
      <p className="page-subtitle">手动填写信息后可先合规自查，确认无误再提交审批</p>

      {!tpl ? <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-secondary)' }}>加载中...</div> : (
        <GlassCard strong>
          {(() => {
            const isLongField = (f: TemplateField) => f.type === 'textarea'
            const shortFields = tpl.fields.filter(f => !isLongField(f))
            const longFields = tpl.fields.filter(f => isLongField(f))

            const renderField = (f: TemplateField) => {
              const rawVal = formFields[f.key] ?? ''
              const val = normalizeFormInputValue(f.key, rawVal, docType || '', templates)
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

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 10, marginTop: 8 }}>
            <button
              type="button"
              onClick={handleComplianceCheck}
              disabled={checkingCompliance || submitting}
              className="glass-btn glass-btn-lg"
              style={{ width: '100%' }}
            >
              {checkingCompliance ? '自查中…' : '提交前合规自查'}
            </button>
            <button onClick={handleSubmit} disabled={submitting || checkingCompliance} className="glass-btn glass-btn-success glass-btn-lg" style={{ width: '100%' }}>
              {submitting ? '提交中…' : '提交申报'}
            </button>
          </div>

          {(checkingCompliance || complianceError || compliance) && (
            <GlassCard className="ai-generated-panel ai-reveal" size="xs" style={{ marginTop: 12, background: 'rgba(0,122,255,0.05)', border: '1px solid rgba(0,122,255,0.16)' }}>
              {checkingCompliance && !compliance ? (
                <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>🔍 正在检索政策知识库并生成合规建议...</div>
              ) : complianceError ? (
                <div style={{ color: 'var(--red)' }}>❌ {complianceError}</div>
              ) : compliance && (
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                    <span style={{ fontWeight: 700, color: RISK_COLOR[compliance.risk_level] }}>📋 合规自查：{RISK_LABEL[compliance.risk_level]}</span>
                    {complianceStale && <span style={{ fontSize: 11, color: 'var(--orange)' }}>表单已修改，请重新自查</span>}
                  </div>
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 8 }}>{compliance.compliance_summary}</div>

                  {compliance.compliance_items?.length > 0 && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 10 }}>
                      {compliance.compliance_items.map((item, i) => (
                        <div key={i} style={{ display: 'flex', gap: 8, fontSize: 12, padding: '6px 8px', borderRadius: 10, background: item.status === 'error' ? 'rgba(255,59,48,0.08)' : item.status === 'warning' ? 'rgba(255,149,0,0.08)' : 'rgba(52,199,89,0.07)' }}>
                          <span>{STATUS_ICON[item.status]}</span>
                          <span style={{ fontWeight: 600 }}>{item.item}：</span>
                          <span style={{ color: 'var(--text-secondary)' }}>{item.detail}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {compliance.suggestions?.length > 0 && (
                    <div style={{ marginBottom: 10 }}>
                      <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--orange)', marginBottom: 4 }}>💡 合规建议</div>
                      {compliance.suggestions.map((s, i) => (
                        <div key={i} style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5 }}>• {s}</div>
                      ))}
                    </div>
                  )}

                  {compliance.policy_hits?.length > 0 && (
                    <div>
                      <button type="button" onClick={() => setPolicyOpen(o => !o)} className="glass-btn glass-btn-sm" style={{ marginBottom: policyOpen ? 6 : 0 }}>
                        {policyOpen ? '收起引用政策' : `查看引用政策（${compliance.policy_hits.length} 条）`}
                      </button>
                      <div className={`collapsible-section${policyOpen ? ' open' : ''}`}>
                        <div>
                          <div className="collapsible-inner" style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 6 }}>
                            {compliance.policy_hits.map((h, i) => (
                              <div key={i} style={{ fontSize: 11, padding: '6px 8px', borderRadius: 8, background: 'rgba(0,122,255,0.06)', border: '1px solid rgba(0,122,255,0.1)' }}>
                                <div style={{ fontWeight: 700, color: 'var(--accent)', marginBottom: 2 }}>{h.doc_title}</div>
                                <div style={{ color: 'var(--text-secondary)', lineHeight: 1.45 }}>{h.text}</div>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </GlassCard>
          )}

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
