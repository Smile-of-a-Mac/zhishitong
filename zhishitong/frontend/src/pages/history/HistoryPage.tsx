import React, { useEffect, useState, useCallback, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import axios from 'axios'
import { getDocTypeLabel } from '../../constants/docTypes'
import { getFieldLabel } from '../../constants/fieldLabels'
import GlassCard from '../../components/GlassCard'
import AuthImage from '../../components/AuthImage'
import ApprovalProgressBar from '../../components/ApprovalProgressBar'
import { STAGE_LABELS, STATUS_LABELS } from '../../utils/constants'
import { parseApiError } from '../../utils/api'

type TabKey = 'all' | 'pending' | 'approved' | 'rejected'

interface TemplateOption {
  key: string
  label: string
  icon?: string
}

const parseDecisionReason = (value: string | null | undefined): { text: string; annotations: Record<string, string> } => {
  if (!value) return { text: '', annotations: {} }
  try {
    const parsed = JSON.parse(value)
    if (!parsed || typeof parsed !== 'object') return { text: value, annotations: {} }
    const annotations: Record<string, string> = {}
    if (Array.isArray(parsed.field_annotations)) {
      parsed.field_annotations.forEach((item: any) => {
        if (item?.field_key && item?.issue) annotations[item.field_key] = item.issue
      })
    }
    return { text: parsed.reason || value, annotations }
  } catch {
    return { text: value, annotations: {} }
  }
}

const TAB_CONFIG: { key: TabKey; label: string; icon: string; statuses: string[] }[] = [
  { key: 'all', label: '全部', icon: '📋', statuses: [] },
  { key: 'pending', label: '审批中', icon: '⏳', statuses: ['pending', 'needs_revision'] },
  { key: 'approved', label: '已通过', icon: '✅', statuses: ['approved'] },
  { key: 'rejected', label: '已驳回', icon: '❌', statuses: ['rejected'] },
]

export default function HistoryPage() {
  const [records, setRecords] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [detail, setDetail] = useState<any>(null)
  const [detailClosing, setDetailClosing] = useState(false)
  const [fieldsOpen, setFieldsOpen] = useState(false)
  const [activeTab, setActiveTab] = useState<TabKey>('all')
  const [errorMsg, setErrorMsg] = useState('')
  const [templates, setTemplates] = useState<TemplateOption[]>([])
  const [searchText, setSearchText] = useState('')
  const [debouncedSearchText, setDebouncedSearchText] = useState('')
  const [docTypeFilter, setDocTypeFilter] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [filtersOpen, setFiltersOpen] = useState(false)
  const nav = useNavigate()
  const [searchParams] = useSearchParams()

  useEffect(() => {
    axios.get('/api/templates').then(res => setTemplates(res.data || [])).catch(() => {})
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearchText(searchText.trim()), 300)
    return () => window.clearTimeout(timer)
  }, [searchText])

  const fetch = useCallback(async () => {
    setLoading(true)
    setErrorMsg('')
    try {
      const params: Record<string, string | number> = { page_size: 50 }
      if (debouncedSearchText) params.q = debouncedSearchText
      if (docTypeFilter) params.doc_type = docTypeFilter
      if (dateFrom) params.date_from = dateFrom
      if (dateTo) params.date_to = dateTo
      const res = await axios.get('/api/approvals', { params })
      setRecords(res.data.items || [])
    } catch (e: any) {
      setRecords([])
      setErrorMsg(parseApiError(e, '加载历史记录失败'))
    } finally { setLoading(false) }
  }, [debouncedSearchText, docTypeFilter, dateFrom, dateTo])

  useEffect(() => { fetch() }, [fetch])

  // 支持 ?detail=recordId 从通知页面跳转来自动打开详情
  const detailFetchedRef = React.useRef<number | null>(null)
  useEffect(() => {
    const detailId = searchParams.get('detail')
    if (!detailId || loading) return
    const id = parseInt(detailId)
    if (!id) return
    // 避免重复请求同一个 detail
    if (detailFetchedRef.current === id) return
    detailFetchedRef.current = id

    // 如果记录已在列表中，直接打开详情（无需发请求）
    const existing = records.find(r => r.id === id)
    if (existing) {
      setDetail(existing)
      return
    }
    // 不在列表中（如管理员查看他人记录），单独请求
    showDetail(id)
  }, [searchParams, records, loading])

  const activeTabConfig = TAB_CONFIG.find(t => t.key === activeTab)
  const detailDecision = parseDecisionReason(detail?.decision_reason)
  const filteredRecords = activeTab === 'all'
    ? records
    : records.filter(r => (activeTabConfig?.statuses || []).includes(r.status))

  const handleDelete = async (id: number) => {
    if (!confirm('删除后不可恢复，确认删除？')) return
    try { await axios.delete(`/api/approvals/${id}`); fetch() }
    catch (e: any) { alert(parseApiError(e, '删除失败')) }
  }

  const handleWithdraw = async (id: number) => {
    if (!confirm('确认撤回该申请？撤回后可重新编辑提交')) return
    try { await axios.put(`/api/approvals/${id}/withdraw`); fetch() }
    catch (e: any) { alert(parseApiError(e, '撤回失败')) }
  }

  const handleUrge = async (id: number) => {
    try {
      await axios.post(`/api/approvals/urge?record_id=${id}`)
      alert('已催办，审批人将收到通知')
    } catch (e: any) { alert(parseApiError(e, '催办失败')) }
  }

  const handleResubmit = (id: number) => { nav(`/?resubmit=${id}`) }

  const currentFilterParams = () => {
    const params: Record<string, string> = {}
    if (debouncedSearchText) params.q = debouncedSearchText
    if (docTypeFilter) params.doc_type = docTypeFilter
    if (dateFrom) params.date_from = dateFrom
    if (dateTo) params.date_to = dateTo
    return params
  }

  const handleExport = async () => {
    try {
      const res = await axios.get('/api/approvals/export', {
        params: currentFilterParams(),
        responseType: 'blob',
      })
      const url = URL.createObjectURL(res.data)
      const link = document.createElement('a')
      link.href = url
      link.download = `智审通_记录导出_${new Date().toISOString().slice(0, 10)}.csv`
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    } catch (e: any) {
      alert(parseApiError(e, '导出失败'))
    }
  }

  const showDetail = async (id: number) => {
    try {
      const res = await axios.get(`/api/approvals/${id}`)
      setDetail(res.data)
      setDetailClosing(false)
      setFieldsOpen(false)
    } catch (e: any) {
      alert(parseApiError(e, '加载详情失败'))
    }
  }

  const closeDetail = () => {
    setDetailClosing(true)
    setTimeout(() => {
      setDetail(null)
      setDetailClosing(false)
    }, 250)
  }

  const statusLabel = (s: string) => STATUS_LABELS[s] || s

  const isConcluded = (s: string) => ['approved', 'rejected', 'cancelled'].includes(s)
  const canCancel = (s: string) => s === 'needs_revision'
  const stageLabel = (stage: string | undefined) => {
    if (!stage) return '—'
    return STAGE_LABELS[stage] || stage
  }

  const waitingLabel = (hours: number) => {
    if (hours < 24) return `${hours} 小时`
    return `${Math.floor(hours / 24)} 天`
  }

  // 统计各状态数量
  const countByStatus = (s: TabKey) => {
    const cfg = TAB_CONFIG.find(t => t.key === s)
    if (!cfg || cfg.key === 'all') return records.length
    return records.filter(r => cfg.statuses.includes(r.status)).length
  }

  return (
    <div>
      <h1 className="page-title">历史记录</h1>

      {/* Tab 导航 — iOS 风格分段控件 */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
        {TAB_CONFIG.map(tab => {
          const count = countByStatus(tab.key)
          const isActive = activeTab === tab.key
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 5,
                padding: '8px 18px',
                border: 'none',
                borderRadius: 22,
                fontSize: 14,
                fontWeight: isActive ? 550 : 400,
                fontFamily: 'var(--font-stack)',
                cursor: 'pointer',
                background: isActive ? 'var(--accent)' : 'var(--glass-bg)',
                color: isActive ? '#fff' : 'var(--text-secondary)',
                boxShadow: isActive ? '0 2px 12px rgba(0,122,255,0.3)' : 'none',
                transition: 'all 0.25s cubic-bezier(0.34, 1.56, 0.64, 1)',
                outline: 'none',
                WebkitUserSelect: 'none',
                userSelect: 'none',
              } as React.CSSProperties}
            >
              <span>{tab.icon}</span>
              <span>{tab.label}</span>
              <span style={{
                background: isActive ? 'rgba(255,255,255,0.25)' : 'rgba(128,128,128,0.12)',
                color: isActive ? '#fff' : 'var(--text-secondary)',
                borderRadius: 10, padding: '1px 8px', fontSize: 12, fontWeight: 600,
                minWidth: 22, textAlign: 'center',
              }}>{count}</span>
            </button>
          )
        })}
      </div>

      <GlassCard size="xs" style={{ marginBottom: 16, padding: '12px 14px' }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ position: 'relative', flex: '1 1 260px' }}>
            <span style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', fontSize: 14, opacity: 0.65 }}>🔍</span>
            <input
              className="glass-input"
              type="search"
              value={searchText}
              onChange={e => setSearchText(e.target.value)}
              placeholder="搜索事由、金额、发票号…"
              aria-label="搜索历史记录"
              style={{ width: '100%', paddingLeft: 36 }}
            />
          </div>
          <button
            className="glass-btn glass-btn-outline glass-btn-sm"
            onClick={() => setFiltersOpen(v => !v)}
            aria-expanded={filtersOpen}
          >
            筛选{(docTypeFilter || dateFrom || dateTo) ? ' · 已启用' : ''}
          </button>
          <button className="glass-btn glass-btn-outline glass-btn-sm" onClick={handleExport}>📥 导出</button>
        </div>
        {filtersOpen && (
          <div style={{ marginTop: 12, display: 'grid', gridTemplateColumns: 'minmax(180px, 1.2fr) repeat(2, minmax(150px, 1fr)) auto', gap: 10, alignItems: 'end' }}>
            <label style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
              事务类型
              <select className="glass-input" value={docTypeFilter} onChange={e => setDocTypeFilter(e.target.value)} style={{ marginTop: 4 }}>
                <option value="">全部类型</option>
                {templates.map(t => <option key={t.key} value={t.key}>{t.icon || ''} {t.label}</option>)}
              </select>
            </label>
            <label style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
              开始日期
              <input className="glass-input" type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} style={{ marginTop: 4 }} />
            </label>
            <label style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
              截止日期
              <input className="glass-input" type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} style={{ marginTop: 4 }} />
            </label>
            <button
              className="glass-btn glass-btn-outline glass-btn-sm"
              onClick={() => { setSearchText(''); setDocTypeFilter(''); setDateFrom(''); setDateTo('') }}
            >
              重置
            </button>
          </div>
        )}
      </GlassCard>

      {errorMsg && (
        <GlassCard size="xs" style={{ marginBottom: 12, background: 'rgba(255,59,48,0.08)', border: '1px solid rgba(255,59,48,0.2)' }}>
          <div style={{ color: 'var(--red)', fontSize: 13, marginBottom: 8 }}>⚠️ {errorMsg}</div>
          <button className="glass-btn glass-btn-outline glass-btn-sm" onClick={fetch}>重试</button>
        </GlassCard>
      )}

      {loading ? (
        <GlassCard className="state-panel state-panel-loading">加载中...</GlassCard>
      ) : filteredRecords.length === 0 ? (
        <GlassCard className="state-panel state-panel-empty">
          暂无记录
        </GlassCard>
      ) : (
        <GlassCard strong className="glass-table-wrapper" style={{ padding: 0 }}>
          <table className="glass-table">
            <thead>
              <tr>
                <th>类型</th>
                <th>状态</th>
                <th>当前阶段</th>
                <th>决策理由</th>
                <th>时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {filteredRecords.map(r => (
                <tr key={r.id}
                  style={{ cursor: 'pointer', transition: 'background 0.15s ease' }}
                  className="glass-table-row-hover"
                  onClick={() => showDetail(r.id)}>
                  <td>{getDocTypeLabel(r.document_type)}</td>
                  <td>{statusLabel(r.status)}</td>
                  <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                    {r.status === 'pending' ? (
                      <div>
                        <ApprovalProgressBar currentStage={r.current_stage || 'dept_review'} documentType={r.document_type} avgHours={r.stage_info?.avg_hours} />
                        {r.stage_info && (
                          <div style={{
                            display: 'inline-flex', alignItems: 'center', gap: 4, marginTop: 6,
                            padding: '3px 8px', borderRadius: 999,
                            background: 'rgba(255,149,0,0.12)', color: 'var(--orange)',
                            fontSize: 11, fontWeight: 600,
                          }}>
                            ⏳ 待 <strong>{r.stage_info.current_reviewer_name || '审批人'}</strong>
                            {r.stage_info.current_reviewer_dept ? `（${r.stage_info.current_reviewer_dept}）` : ''}审批 · 已等待 {waitingLabel(r.stage_info.waiting_hours || 0)}
                          </div>
                        )}
                      </div>
                    ) : (
                      stageLabel(r.current_stage)
                    )}
                  </td>
                  <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-secondary)' }}>
                    {parseDecisionReason(r.decision_reason).text || '—'}</td>
                  <td style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
                    {new Date(r.created_at).toLocaleDateString('zh-CN')}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <div className="btn-group" style={{ gap: 6 }}>
                      {r.status === 'pending' && (
                        <button onClick={e => { e.stopPropagation(); handleUrge(r.id) }}
                          className="glass-btn glass-btn-sm"
                          style={{ color: '#FF9500' }}>催办</button>
                      )}
                      {isConcluded(r.status) ? (
                        <button onClick={e => { e.stopPropagation(); handleDelete(r.id) }}
                          className="glass-btn glass-btn-danger glass-btn-sm">删除</button>
                      ) : r.status === 'withdrawn' ? (
                        <>
                          <button onClick={e => { e.stopPropagation(); handleResubmit(r.id) }}
                            className="glass-btn glass-btn-sm">重新提交</button>
                          <button onClick={e => { e.stopPropagation(); handleDelete(r.id) }}
                            className="glass-btn glass-btn-danger glass-btn-sm">删除</button>
                        </>
                      ) : canCancel(r.status) ? (
                        <>
                          <button onClick={e => { e.stopPropagation(); handleResubmit(r.id) }}
                            className="glass-btn glass-btn-sm">修改</button>
                          <button onClick={e => { e.stopPropagation(); handleDelete(r.id) }}
                            className="glass-btn glass-btn-danger glass-btn-sm">取消</button>
                        </>
                      ) : (
                        r.status === 'pending' ? null : (
                          <button onClick={e => { e.stopPropagation(); handleWithdraw(r.id) }}
                            className="glass-btn glass-btn-outline glass-btn-sm">撤回</button>
                        )
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </GlassCard>
      )}

      {/* 详情弹窗 */}
      {detail && (
        <div
          className={`modal-overlay${detailClosing ? ' modal-closing' : ''}`}
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
          }}
          onClick={closeDetail}
        >
          <GlassCard
            strong
            className={`modal-card${detailClosing ? ' modal-closing' : ''}`}
            style={{ width: 520, maxWidth: '90vw', maxHeight: '85vh', overflow: 'auto' }}
            onClick={e => e.stopPropagation()}
          >
            <h3 style={{ margin: '0 0 16px', fontSize: 18 }}>
              审批详情 #{detail.id}
              <span style={{ marginLeft: 12, fontSize: 14, fontWeight: 400 }}>
                {statusLabel(detail.status)}
              </span>
            </h3>

            <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
              <div style={{ marginBottom: 4 }}>类型：{getDocTypeLabel(detail.document_type)}</div>
              <div style={{ marginBottom: 4 }}>文件：{detail.original_filename || '手动申报'}</div>
              <div style={{ marginBottom: 4 }}>
                时间：{new Date(detail.created_at).toLocaleString('zh-CN')}
              </div>

              {/* 图片预览 — 使用 AuthImage 携带认证 */}
              {detail.image_url && (
                <div style={{ marginBottom: 12 }}>
                  <AuthImage
                    src={detail.image_url}
                    alt="上传文件"
                    style={{
                      maxWidth: '100%', maxHeight: 300, borderRadius: 'var(--radius-xs)',
                      border: '1px solid var(--glass-border)', cursor: 'pointer', objectFit: 'contain',
                    }}
                    onClick={() => window.open(detail.image_url, '_blank')}
                  />
                  <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 2 }}>点击放大</div>
                </div>
              )}
              {detail.decision_reason && (
                <GlassCard size="xs" style={{ marginBottom: 8 }}>
                  <strong>分析/决策理由：</strong>
                  <div style={{ marginTop: 4, color: 'var(--text-primary)' }}>{detailDecision.text}</div>
                </GlassCard>
              )}

              {/* LLM 修改建议 */}
              {detail.suggestions && (() => {
                try {
                  const sug = JSON.parse(detail.suggestions);
                  if (Array.isArray(sug) && sug.length > 0) {
                    return (
                      <GlassCard size="xs" style={{ background: 'rgba(255,149,0,0.08)', border: '1px solid rgba(255,149,0,0.2)', marginBottom: 8 }}>
                        <div style={{ fontWeight: 600, fontSize: 12, color: 'var(--orange)', marginBottom: 4 }}>智能建议</div>
                        {sug.map((s: string, i: number) => (
                          <div key={i} style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 2 }}>• {s}</div>
                        ))}
                      </GlassCard>
                    );
                  }
                } catch {}
                return null;
              })()}

              {/* 缺失信息 */}
              {detail.missing_info && (() => {
                try {
                  const miss = JSON.parse(detail.missing_info);
                  if (Array.isArray(miss) && miss.length > 0) {
                    return (
                      <GlassCard size="xs" style={{ background: 'rgba(255,59,48,0.08)', border: '1px solid rgba(255,59,48,0.2)', marginBottom: 8 }}>
                        <div style={{ fontWeight: 600, fontSize: 12, color: 'var(--red)', marginBottom: 4 }}>缺失信息</div>
                        {miss.map((m: string, i: number) => (
                          <div key={i} style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 2 }}>• 缺少「{m}」</div>
                        ))}
                      </GlassCard>
                    );
                  }
                } catch {}
                return null;
              })()}

              {/* 表单数据 — 用 React 状态控制展开/收起，双向动画 */}
              {detail.filled_json && (
                <div style={{ marginTop: 8 }}>
                  <div
                    onClick={() => setFieldsOpen(o => !o)}
                    style={{ cursor: 'pointer', color: 'var(--accent)', fontSize: 13, fontWeight: 500, userSelect: 'none' }}
                  >
                    {fieldsOpen ? '▾' : '▸'} 查看提交的字段数据
                  </div>
                  <div className={`collapsible-section${fieldsOpen ? ' open' : ''}`}>
                    <div>
                      <div className="collapsible-inner">
                        <GlassCard size="xs" style={{ marginTop: 8 }}>
                          {(() => {
                            try {
                              const data = typeof detail.filled_json === 'string' ? JSON.parse(detail.filled_json) : detail.filled_json;
                              return Object.entries(data).map(([k, v]) => {
                                const issue = detailDecision.annotations[k]
                                return (
                                <div key={k} style={{
                                  padding: '4px 0', borderBottom: '1px solid var(--divider)', display: 'flex',
                                  outline: issue ? '1px dashed var(--red)' : undefined,
                                  background: issue ? 'rgba(255,59,48,0.06)' : undefined,
                                }}>
                                  <span style={{ color: 'var(--text-secondary)', minWidth: 100 }}>{getFieldLabel(k)}</span>
                                  <span style={{ color: 'var(--text-primary)' }}>
                                    {String(v ?? '')}
                                    {issue && <div style={{ color: 'var(--red)', fontSize: 12, marginTop: 3 }}>🚩 {issue}</div>}
                                  </span>
                                </div>
                              )});
                            } catch { return <div>无法解析</div>; }
                          })()}
                        </GlassCard>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>

            <div style={{ marginTop: 16, textAlign: 'right' }}>
              <button onClick={closeDetail} className="glass-btn glass-btn-outline">关闭</button>
            </div>
          </GlassCard>
        </div>
      )}
    </div>
  )
}
