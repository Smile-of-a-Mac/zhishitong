/**
 * AI 辅助决策面板（嵌入审批详情页）
 * 功能：合规分析 + 相似案例 + 意见草稿生成
 */
import React, { useState, useEffect } from 'react'
import axios from 'axios'

interface Props {
  recordId: number
  decision?: 'approved' | 'rejected' | 'needs_revision'
  onFillOpinion?: (opinion: string) => void
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

interface SimilarCase {
  id: number
  status: string
  key_info: string
  applicant: string
  created_at: string
  similarity: number
}

const RISK_COLOR: Record<string, string> = {
  low: '#34C759',
  medium: '#FF9500',
  high: '#FF3B30',
}
const RISK_LABEL: Record<string, string> = {
  low: '✅ 低风险',
  medium: '⚠️ 中等风险',
  high: '🚨 高风险',
}
const STATUS_ICON: Record<string, string> = {
  ok: '✅',
  warning: '⚠️',
  error: '❌',
}

export default function AIDecisionPanel({ recordId, decision, onFillOpinion }: Props) {
  const [tab, setTab] = useState<'compliance' | 'similar'>('compliance')
  const [compliance, setCompliance] = useState<ComplianceResult | null>(null)
  const [complianceLoading, setComplianceLoading] = useState(false)
  const [cases, setCases] = useState<SimilarCase[]>([])
  const [casesLoading, setCasesLoading] = useState(false)
  const [opinionLoading, setOpinionLoading] = useState(false)
  const [policyOpen, setPolicyOpen] = useState(false)

  // 自动加载合规分析
  useEffect(() => {
    if (!recordId) return
    loadCompliance()
    loadSimilar()
  }, [recordId])

  const loadCompliance = async () => {
    setComplianceLoading(true)
    try {
      const res = await axios.post(`/api/ai/compliance/${recordId}`)
      setCompliance(res.data)
    } catch {
      // 静默失败
    } finally {
      setComplianceLoading(false)
    }
  }

  const loadSimilar = async () => {
    setCasesLoading(true)
    try {
      const res = await axios.post(`/api/ai/similar/${recordId}`)
      setCases(res.data.cases || [])
    } catch {
      // 静默失败
    } finally {
      setCasesLoading(false)
    }
  }

  const generateOpinion = async () => {
    if (!decision || !onFillOpinion) return
    setOpinionLoading(true)
    try {
      const res = await axios.post('/api/ai/opinion', {
        record_id: recordId,
        decision,
      })
      onFillOpinion(res.data.opinion || '')
    } catch (e: any) {
      // 静默失败
    } finally {
      setOpinionLoading(false)
    }
  }

  return (
    <div
      style={{
        marginTop: 12,
        borderRadius: 12,
        border: '1px solid rgba(90,200,250,0.25)',
        background: 'rgba(0,122,255,0.04)',
        overflow: 'hidden',
      }}
    >
      {/* 标题栏 — 始终展开 */}
      <div
        style={{
          padding: '8px 14px',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          borderBottom: '1px solid rgba(90,200,250,0.2)',
          background: 'rgba(0,122,255,0.06)',
        }}
      >
        <span style={{ fontSize: 14 }}>🧠</span>
        <span style={{ fontWeight: 600, fontSize: 13 }}>AI 辅助决策</span>
        {compliance && (
          <span
            style={{
              marginLeft: 4,
              fontSize: 11,
              fontWeight: 600,
              color: RISK_COLOR[compliance.risk_level],
              background: `${RISK_COLOR[compliance.risk_level]}15`,
              padding: '2px 8px',
              borderRadius: 20,
            }}
          >
            {RISK_LABEL[compliance.risk_level]}
          </span>
        )}
      </div>

      <div style={{ padding: '10px 14px 14px' }}>
          {/* Tabs */}
          <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
            {(['compliance', 'similar'] as const).map(t => (
              <button
                key={t}
                onClick={() => setTab(t)}
                style={{
                  padding: '4px 12px',
                  fontSize: 12,
                  borderRadius: 20,
                  border: 'none',
                  cursor: 'pointer',
                  background:
                    tab === t ? 'var(--accent-color, #007aff)' : 'rgba(120,120,128,0.1)',
                  color: tab === t ? '#fff' : 'var(--text-secondary)',
                  fontWeight: tab === t ? 600 : 400,
                  transition: 'all 0.2s',
                }}
              >
                {t === 'compliance' ? '📋 合规分析' : '📂 相似案例'}
              </button>
            ))}
          </div>

          {/* ── 合规分析 Tab ── */}
          {tab === 'compliance' && (
            <>
              {complianceLoading && (
                <div style={{ fontSize: 13, color: 'var(--text-secondary)', padding: '8px 0' }}>
                  🔍 正在检索政策知识库...
                </div>
              )}
              {!complianceLoading && compliance && (
                <>
                  {/* 摘要 */}
                  <div
                    style={{
                      fontSize: 13,
                      color: RISK_COLOR[compliance.risk_level],
                      fontWeight: 600,
                      marginBottom: 8,
                    }}
                  >
                    {compliance.compliance_summary}
                  </div>

                  {/* 逐项结果 */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 8 }}>
                    {compliance.compliance_items?.map((item, i) => (
                      <div
                        key={i}
                        style={{
                          display: 'flex',
                          gap: 8,
                          fontSize: 12,
                          padding: '4px 8px',
                          borderRadius: 8,
                          background:
                            item.status === 'error'
                              ? 'rgba(255,59,48,0.08)'
                              : item.status === 'warning'
                              ? 'rgba(255,149,0,0.08)'
                              : 'rgba(52,199,89,0.07)',
                        }}
                      >
                        <span>{STATUS_ICON[item.status]}</span>
                        <span style={{ fontWeight: 500 }}>{item.item}：</span>
                        <span style={{ color: 'var(--text-secondary)' }}>{item.detail}</span>
                      </div>
                    ))}
                  </div>

                  {/* 建议 */}
                  {compliance.suggestions?.length > 0 && (
                    <div style={{ marginBottom: 8 }}>
                      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--orange)', marginBottom: 4 }}>
                        💡 建议
                      </div>
                      {compliance.suggestions.map((s, i) => (
                        <div key={i} style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 2 }}>
                          • {s}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* 政策依据 */}
                  {compliance.policy_hits?.length > 0 && (
                    <div style={{ marginTop: 4 }}>
                      <div
                        onClick={() => setPolicyOpen(o => !o)}
                        style={{ fontSize: 12, cursor: 'pointer', color: 'var(--accent-color, #007aff)', fontWeight: 500, userSelect: 'none' }}
                      >
                        {policyOpen ? '▾' : '▸'} 查看引用政策（{compliance.policy_hits.length} 条）
                      </div>
                      <div className={`collapsible-section${policyOpen ? ' open' : ''}`}>
                        <div>
                          <div className="collapsible-inner" style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 4 }}>
                        {compliance.policy_hits.map((h, i) => (
                          <div
                            key={i}
                            style={{
                              fontSize: 11,
                              padding: '4px 8px',
                              borderRadius: 8,
                              background: 'rgba(0,122,255,0.06)',
                              border: '1px solid rgba(0,122,255,0.1)',
                            }}
                          >
                            <div style={{ fontWeight: 600, color: 'var(--accent-color, #007aff)', marginBottom: 2 }}>
                              {h.doc_title}
                            </div>
                            <div style={{ color: 'var(--text-secondary)', lineHeight: 1.4 }}>{h.text}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                    </div>
                  )}
                </>
              )}
              {!complianceLoading && !compliance && (
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>加载失败，请重试</div>
              )}
            </>
          )}

          {/* ── 相似案例 Tab ── */}
          {tab === 'similar' && (
            <>
              {casesLoading && (
                <div style={{ fontSize: 13, color: 'var(--text-secondary)', padding: '8px 0' }}>
                  🔍 正在检索历史案例...
                </div>
              )}
              {!casesLoading && cases.length === 0 && (
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>暂无相似历史案例</div>
              )}
              {!casesLoading && cases.map(c => (
                <div
                  key={c.id}
                  style={{
                    padding: '8px 10px',
                    borderRadius: 10,
                    border: '1px solid var(--glass-border)',
                    marginBottom: 6,
                    fontSize: 12,
                    background:
                      c.status === 'approved'
                        ? 'rgba(52,199,89,0.07)'
                        : c.status === 'rejected'
                        ? 'rgba(255,59,48,0.06)'
                        : 'rgba(120,120,128,0.06)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                    <span style={{ fontWeight: 600 }}>
                      #{c.id} — {c.status === 'approved' ? '✅ 已通过' : c.status === 'rejected' ? '❌ 驳回' : c.status}
                    </span>
                    <span style={{ color: 'var(--text-secondary)' }}>
                      相似度 {Math.round(c.similarity * 100)}%
                    </span>
                  </div>
                  <div style={{ color: 'var(--text-secondary)', marginBottom: 2 }}>
                    {c.key_info}
                  </div>
                  <div style={{ color: 'var(--text-secondary)' }}>
                    申请人：{c.applicant} · {c.created_at}
                  </div>
                </div>
              ))}
            </>
          )}

        </div>
    </div>
  )
}
