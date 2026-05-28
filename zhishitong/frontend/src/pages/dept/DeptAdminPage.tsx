import React, { useEffect, useState } from 'react'
import axios from 'axios'
import { getDocTypeLabel } from '../../constants/docTypes'
import { getFieldLabel } from '../../constants/fieldLabels'
import GlassCard from '../../components/GlassCard'
import AIDecisionPanel from '../../components/AIDecisionPanel'

interface DeptRecord {
  id: number
  username: string
  department: string | null
  original_filename: string | null
  document_type: string | null
  status: string
  current_stage: string
  filled_json: string | null
  decision_reason: string | null
  suggestions: string | null
  missing_info: string | null
  stages: any[]
  image_url?: string
  is_deleted: boolean
  created_at: string
}

interface DeptStats {
  department: string
  total_records: number
  pending: number
  approved: number
  rejected: number
  today_new: number
}

const STATUS_LABELS: Record<string, string> = {
  pending: '⏳ 待审批',
  approved: '✅ 已通过',
  rejected: '❌ 不通过',
  needs_revision: '📝 需修改',
  cancelled: '⊘ 申请已取消',
  withdrawn: '↩️ 已撤回',
}

export default function DeptAdminPage() {
  const [records, setRecords] = useState<DeptRecord[]>([])
  const [stats, setStats] = useState<DeptStats | null>(null)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [filterStatus, setFilterStatus] = useState('')
  const [filterStage, setFilterStage] = useState('')
  const [loading, setLoading] = useState(true)
  const [reviewId, setReviewId] = useState<number | null>(null)
  const [reviewAction, setReviewAction] = useState<'approved' | 'rejected' | 'needs_revision'>('approved')
  const [reviewReason, setReviewReason] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [selectedRecord, setSelectedRecord] = useState<DeptRecord | null>(null)
  const [suggesting, setSuggesting] = useState(false)

  // ── 审批意见模板 ──
  const [templates, setTemplates] = useState<any[]>([])
  const [showTemplates, setShowTemplates] = useState(false)
  const [newTplContent, setNewTplContent] = useState('')
  const [newTplCategory, setNewTplCategory] = useState('general')

  const fetchTemplates = async () => {
    try {
      const res = await axios.get('/api/approvals/opinion-templates')
      setTemplates(res.data || [])
    } catch { }
  }

  const addTemplate = async () => {
    if (!newTplContent.trim()) return
    try {
      await axios.post('/api/approvals/opinion-templates', {
        category: newTplCategory, content: newTplContent,
      })
      setNewTplContent('')
      fetchTemplates()
    } catch (e: any) { alert(e?.response?.data?.detail || '添加失败') }
  }

  const deleteTemplate = async (id: number) => {
    try { await axios.delete(`/api/approvals/opinion-templates/${id}`); fetchTemplates() }
    catch { }
  }

  const quickFill = (content: string) => {
    setReviewReason(content)
  }

  // ── 审批代理 ──
  const [delegations, setDelegations] = useState<any[]>([])
  const [showDelegations, setShowDelegations] = useState(false)
  const [delDelegateId, setDelDelegateId] = useState('')
  const [delStart, setDelStart] = useState('')
  const [delEnd, setDelEnd] = useState('')
  const [delReason, setDelReason] = useState('')

  const fetchDelegations = async () => {
    try {
      const res = await axios.get('/api/approvals/delegations')
      setDelegations(res.data || [])
    } catch { }
  }

  const addDelegation = async () => {
    if (!delDelegateId || !delStart || !delEnd) { alert('请填写完整信息'); return }
    try {
      await axios.post('/api/approvals/delegations', {
        delegate_id: parseInt(delDelegateId),
        start_date: delStart,
        end_date: delEnd,
        reason: delReason,
      })
      setDelDelegateId(''); setDelStart(''); setDelEnd(''); setDelReason('')
      fetchDelegations()
    } catch (e: any) { alert(e?.response?.data?.detail || '设置失败') }
  }

  const cancelDelegation = async (id: number) => {
    try { await axios.delete(`/api/approvals/delegations/${id}`); fetchDelegations() }
    catch { }
  }
  const fetchRecords = async () => {
    setLoading(true)
    const params: any = { page, page_size: 20 }
    if (filterStatus) params.status = filterStatus
    if (filterStage) params.stage = filterStage
    try {
      const res = await axios.get('/api/dept/records', { params })
      setRecords(res.data.items); setTotal(res.data.total)
    } catch { } finally { setLoading(false) }
  }

  const fetchStats = async () => {
    try { const res = await axios.get('/api/dept/stats'); setStats(res.data) } catch { }
  }

  useEffect(() => { fetchRecords(); fetchStats() }, [page, filterStatus, filterStage])
  // 切换筛选时回到第一页
  useEffect(() => { if (page !== 1) setPage(1) }, [filterStatus, filterStage])

  const getAiSuggestion = async () => {
    if (!reviewId) return
    setSuggesting(true)
    try {
      const res = await axios.post('/api/approvals/suggest-review', {
        record_id: reviewId, action: reviewAction, admin_reason: reviewReason,
      })
      const suggestion = res.data.suggestion || ''
      if (suggestion && !suggestion.startsWith('获取建议失败') && !suggestion.startsWith('未配置')) {
        setReviewReason(prev => prev ? prev + '\n---\n' + suggestion : suggestion)
      }
    } catch (e: any) {
      // 静默失败，不干扰用户
    } finally { setSuggesting(false) }
  }

  const openReview = (record: DeptRecord, action: 'approved' | 'rejected' | 'needs_revision') => {
    setReviewId(record.id)
    setReviewAction(action)
    setReviewReason('')
    setSelectedRecord(record)
  }

  const submitReview = async () => {
    if (!reviewId) return
    if ((reviewAction === 'rejected' || reviewAction === 'needs_revision') && !reviewReason.trim()) {
      alert('驳回或需修改时请填写审批理由'); return
    }
    setSubmitting(true)
    try {
      await axios.put(`/api/dept/records/${reviewId}/status`, {
        status: reviewAction,
        reason: reviewReason,
      })
      setReviewId(null); setReviewReason(''); setSelectedRecord(null)
      fetchRecords(); fetchStats()
    } catch (e: any) {
      alert(e?.response?.data?.detail || '操作失败')
    } finally { setSubmitting(false) }
  }

  const showDetail = async (id: number) => {
    try {
      const res = await axios.get(`/api/dept/records/${id}`)
      setSelectedRecord(res.data)
    } catch { }
  }

  return (
    <div>
      <h1 className="page-title">📋 部门事务管理</h1>

      {/* 统计卡片 */}
      {stats && (
        <div className="stats-grid">
          {[
            { label: '总事务', value: stats.total_records, color: 'var(--accent)' },
            { label: '待审批', value: stats.pending, color: 'var(--orange)' },
            { label: '已通过', value: stats.approved, color: 'var(--green)' },
            { label: '不通过', value: stats.rejected, color: 'var(--red)' },
            { label: '今日新增', value: stats.today_new, color: 'var(--purple)' },
          ].map(card => (
            <GlassCard key={card.label} size="sm" className="stat-card">
              <div className="stat-card-label">{card.label}</div>
              <div className="stat-card-value" style={{ color: card.color }}>{card.value}</div>
            </GlassCard>
          ))}
        </div>
      )}

      {/* ── 审批工具面板 ── */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <button className="glass-btn glass-btn-outline glass-btn-sm"
          onClick={() => { setShowTemplates(!showTemplates); if (!showTemplates) fetchTemplates(); setShowDelegations(false) }}>
          📝 审批意见模板
        </button>
        <button className="glass-btn glass-btn-outline glass-btn-sm"
          onClick={() => { setShowDelegations(!showDelegations); if (!showDelegations) fetchDelegations(); setShowTemplates(false) }}>
          🔄 审批代理
        </button>
      </div>

      {/* 意见模板面板 */}
      {showTemplates && (
        <GlassCard size="sm" style={{ marginBottom: 12 }}>
          <h4 style={{ margin: '0 0 8px', fontSize: 14 }}>📝 审批意见模板</h4>
          <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
            <select value={newTplCategory} onChange={e => setNewTplCategory(e.target.value)}
              className="glass-input" style={{ width: 'auto', fontSize: 12 }}>
              <option value="general">通用</option>
              <option value="approve">通过</option>
              <option value="reject">驳回</option>
              <option value="revision">需修改</option>
            </select>
            <input className="glass-input" placeholder="输入模板内容..." value={newTplContent}
              onChange={e => setNewTplContent(e.target.value)} style={{ flex: 1, fontSize: 12 }} />
            <button className="glass-btn glass-btn-sm" onClick={addTemplate}>添加</button>
          </div>
          {templates.length === 0 ? (
            <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>暂无模板，添加后可快速填入审批意见</div>
          ) : (
            templates.map((t: any) => (
              <div key={t.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '4px 0', borderBottom: '1px solid var(--divider)', fontSize: 12 }}>
                <span style={{ flex: 1, cursor: 'pointer' }} onClick={() => quickFill(t.content)}>{t.content}</span>
                <button onClick={() => deleteTemplate(t.id)} className="glass-btn glass-btn-sm"
                  style={{ color: '#FF3B30', fontSize: 10, padding: '2px 6px' }}>删除</button>
              </div>
            ))
          )}
        </GlassCard>
      )}

      {/* 代理管理面板 */}
      {showDelegations && (
        <GlassCard size="sm" style={{ marginBottom: 12 }}>
          <h4 style={{ margin: '0 0 8px', fontSize: 14 }}>🔄 审批代理设置</h4>
          <div style={{ display: 'flex', gap: 6, marginBottom: 8, flexWrap: 'wrap', alignItems: 'center', fontSize: 12 }}>
            <input className="glass-input" placeholder="被委托人ID" value={delDelegateId}
              onChange={e => setDelDelegateId(e.target.value)} style={{ width: 90 }} />
            <input className="glass-input" type="date" value={delStart}
              onChange={e => setDelStart(e.target.value)} style={{ width: 120 }} />
            <span>至</span>
            <input className="glass-input" type="date" value={delEnd}
              onChange={e => setDelEnd(e.target.value)} style={{ width: 120 }} />
            <input className="glass-input" placeholder="原因（选填）" value={delReason}
              onChange={e => setDelReason(e.target.value)} style={{ flex: 1, minWidth: 100 }} />
            <button className="glass-btn glass-btn-sm" onClick={addDelegation}>设置代理</button>
          </div>
          {delegations.length === 0 ? (
            <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>暂无代理设置</div>
          ) : (
            delegations.map((d: any) => (
              <div key={d.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '4px 0', borderBottom: '1px solid var(--divider)', fontSize: 12 }}>
                <span>
                  委托给 <b>{d.delegate_name || d.delegate_id}</b>
                  {' '}{new Date(d.start_date).toLocaleDateString()} ~ {new Date(d.end_date).toLocaleDateString()}
                  {d.reason && ` (${d.reason})`}
                </span>
                <button onClick={() => cancelDelegation(d.id)} className="glass-btn glass-btn-sm"
                  style={{ color: '#FF3B30', fontSize: 10, padding: '2px 6px' }}>取消代理</button>
              </div>
            ))
          )}
        </GlassCard>
      )}

      {/* 筛选 */}
      <GlassCard size="sm" style={{ marginBottom: 12, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-secondary)' }}>筛选：</span>
        <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
          className="glass-input" style={{ width: 'auto', padding: '4px 8px' }}>
          <option value="">全部状态</option>
          <option value="pending">待审批</option>
          <option value="approved">已通过</option>
          <option value="rejected">不通过</option>
          <option value="needs_revision">需修改</option>
        </select>
        <select value={filterStage} onChange={e => setFilterStage(e.target.value)}
          className="glass-input" style={{ width: 'auto', padding: '4px 8px' }}>
          <option value="">全部阶段</option>
          <option value="dept_review">部门审批</option>
          <option value="finance_review">财务审批</option>
          <option value="school_review">学校审批</option>
          <option value="completed">已完成</option>
        </select>
        <button onClick={() => { setFilterStatus(''); setFilterStage(''); fetchRecords(); fetchStats() }}
          className="glass-btn glass-btn-outline glass-btn-sm">🔄 刷新</button>
        <span style={{ marginLeft: 'auto', fontSize: 13, color: 'var(--text-secondary)' }}>共 {total} 条</span>
      </GlassCard>

      {/* 列表 */}
      {loading ? <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-secondary)' }}>加载中...</div> :
        records.length === 0 ? <GlassCard style={{ textAlign: 'center', color: 'var(--text-secondary)' }}>暂无事务</GlassCard> : (
          <GlassCard strong className="glass-table-wrapper" style={{ padding: 0 }}>
            <table className="glass-table">
              <thead><tr>
                <th>用户</th>
                <th>部门</th>
                <th>文档</th>
                <th>类型</th>
                <th>状态</th>
                <th>审批理由</th>
                <th>时间</th>
                <th>操作</th>
              </tr></thead>
              <tbody>
                {records.map(r => (
                  <tr key={r.id} style={{ background: r.status === 'pending' ? 'rgba(255,149,0,0.05)' : 'transparent' }}>
                    <td>{r.username}</td>
                    <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{r.department || '—'}</td>
                    <td style={{ maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      <a href="#" onClick={e => { e.preventDefault(); showDetail(r.id) }} className="glass-link" style={{ fontSize: 13 }}>
                        {r.original_filename || '—'}
                      </a>
                    </td>
                    <td>{getDocTypeLabel(r.document_type)}</td>
                    <td style={{ fontWeight: 500 }}>
                      {STATUS_LABELS[r.status] || r.status}
                    </td>
                    <td style={{ maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 12, color: 'var(--text-secondary)' }}>
                      {r.decision_reason || '—'}
                    </td>
                    <td style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                      {new Date(r.created_at).toLocaleDateString('zh-CN')}
                    </td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <button onClick={() => showDetail(r.id)}
                        className="glass-btn glass-btn-outline glass-btn-sm">📋 查看详情</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </GlassCard>
        )}

      {/* 分页 */}
      <div style={{ marginTop: 12, display: 'flex', justifyContent: 'center', gap: 8, alignItems: 'center' }}>
        <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}
          className="glass-btn glass-btn-outline glass-btn-sm">上一页</button>
        <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{page}</span>
        <button disabled={page * 20 >= total} onClick={() => setPage(p => p + 1)}
          className="glass-btn glass-btn-outline glass-btn-sm">下一页</button>
      </div>

      {/* 统一详情 + 审批弹窗 */}
      {selectedRecord && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
        }} onClick={() => { setSelectedRecord(null); setReviewId(null) }}>
          <GlassCard strong style={{ width: 560, maxWidth: '90vw', maxHeight: '90vh', overflow: 'auto' }}
            onClick={e => e.stopPropagation()}>
            <h3 style={{ margin: '0 0 16px', fontSize: 17 }}>
              📋 事务详情 #{selectedRecord.id}
              <span style={{ marginLeft: 12, fontSize: 14, fontWeight: 400, color: 'var(--text-secondary)' }}>
                {STATUS_LABELS[selectedRecord.status]}
              </span>
            </h3>

            {/* ---- 基本信息 ---- */}
            <GlassCard size="xs" style={{ marginBottom: 12, fontSize: 13, color: 'var(--text-secondary)' }}>
              <div>👤 申请人：{selectedRecord.username}</div>
              <div>🏢 部门：{selectedRecord.department || '—'}</div>
              <div>📄 文件：{selectedRecord.original_filename || '—'}</div>
              <div>🏷️ 类型：{getDocTypeLabel(selectedRecord.document_type)}</div>
              <div>📌 阶段：{selectedRecord.current_stage === 'dept_review' ? '📋 部门审批' : selectedRecord.current_stage === 'finance_review' ? '💰 财务审批' : selectedRecord.current_stage === 'school_review' ? '🏫 学校审批' : selectedRecord.current_stage}</div>
              {selectedRecord.decision_reason && (
                <div style={{ marginTop: 4, color: 'var(--accent)' }}>📋 分析：{selectedRecord.decision_reason}</div>
              )}
            </GlassCard>

            {/* ---- 图片 ---- */}
            {selectedRecord.image_url && (
              <div style={{ marginBottom: 12, textAlign: 'center' }}>
                <img src={selectedRecord.image_url} alt="文件" style={{
                  maxWidth: '100%', maxHeight: 240, borderRadius: 'var(--radius-xs)',
                  border: '1px solid var(--glass-border)', cursor: 'pointer',
                }} onClick={() => window.open(selectedRecord.image_url, '_blank')} />
              </div>
            )}

            {/* ---- 表单字段 ---- */}
            {selectedRecord.filled_json && (() => {
              try {
                const data = JSON.parse(selectedRecord.filled_json);
                const entries = Object.entries(data);
                if (entries.length > 0) return (
                  <GlassCard size="xs" style={{ background: 'rgba(0,122,255,0.06)', border: '1px solid rgba(0,122,255,0.15)', marginBottom: 12 }}>
                    <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--accent)', marginBottom: 6 }}>📋 事务详情</div>
                    <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
                      <tbody>
                        {entries.map(([k, v]) => (
                          <tr key={k} style={{ borderBottom: '1px solid var(--divider)' }}>
                            <td style={{ padding: '4px 8px', color: 'var(--text-secondary)', width: 120 }}>{getFieldLabel(k)}</td>
                            <td style={{ padding: '4px 8px', color: 'var(--text-primary)' }}>{String(v ?? '')}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </GlassCard>
                );
              } catch {} return null;
            })()}

            {/* ---- 审批历程 ---- */}
            {selectedRecord.stages && selectedRecord.stages.length > 0 && (
              <GlassCard size="xs" style={{ background: 'rgba(52,199,89,0.06)', border: '1px solid rgba(52,199,89,0.15)', marginBottom: 12 }}>
                <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>📋 审批历程</div>
                {selectedRecord.stages.map((s: any, i: number) => (
                  <div key={i} style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 3 }}>
                    • {s.label || s.stage}：{s.status === 'approved' ? '✅ 通过' : s.status === 'rejected' ? '❌ 驳回' : '⏳'} — {s.reviewer || '系统'}（{s.reason || '无意见'}）
                  </div>
                ))}
              </GlassCard>
            )}

            {/* ---- LLM 建议 ---- */}
            {selectedRecord.suggestions && (() => {
              try {
                const sug = JSON.parse(selectedRecord.suggestions);
                if (Array.isArray(sug) && sug.length > 0) return (
                  <GlassCard size="xs" style={{ background: 'rgba(255,149,0,0.08)', border: '1px solid rgba(255,149,0,0.2)', marginBottom: 12 }}>
                    <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--orange)', marginBottom: 4 }}>💡 智能建议</div>
                    {sug.map((s: string, i: number) => <div key={i} style={{ fontSize: 13, color: 'var(--text-secondary)' }}>• {s}</div>)}
                  </GlassCard>
                );
              } catch {} return null;
            })()}

            {/* ---- 审批操作区 ---- */}
            {selectedRecord.status === 'pending' && selectedRecord.current_stage === 'dept_review' && (
              <>
                <hr className="glass-divider" />
                <h4 style={{ margin: '0 0 8px', fontSize: 14 }}>✍️ 审批操作</h4>

                {/* 操作按钮 */}
                <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                  {[
                    { action: 'approved' as const, label: '✓ 通过', color: 'var(--green)' },
                    { action: 'needs_revision' as const, label: '📝 需修改', color: 'var(--orange)' },
                    { action: 'rejected' as const, label: '✗ 不通过', color: 'var(--red)' },
                  ].map(btn => (
                    <button key={btn.action} onClick={() => {
                      setReviewId(selectedRecord.id)
                      setReviewAction(btn.action)
                      setReviewReason(reviewId === selectedRecord.id && reviewAction === btn.action ? reviewReason : '')
                    }} style={{
                      flex: 1, padding: '8px 0', border: `1px solid ${btn.color}`,
                      background: reviewId === selectedRecord.id && reviewAction === btn.action ? btn.color : 'transparent',
                      color: reviewId === selectedRecord.id && reviewAction === btn.action ? '#fff' : btn.color,
                      borderRadius: 6, cursor: 'pointer', fontSize: 13, fontWeight: 500,
                      transition: 'all 0.2s ease',
                    }}>{btn.label}</button>
                  ))}
                </div>

                {/* 意见输入（选中操作后展开） */}
                {reviewId === selectedRecord.id && (
                  <>
                    {/* AI 辅助决策面板 */}
                    <AIDecisionPanel
                      recordId={selectedRecord.id}
                      decision={reviewAction === 'approved' ? 'approved' : reviewAction === 'rejected' ? 'rejected' : 'needs_revision'}
                      onFillOpinion={(text) => setReviewReason(prev => prev ? prev + '\n' + text : text)}
                    />
                    <textarea value={reviewReason} onChange={e => setReviewReason(e.target.value)}
                      placeholder={reviewAction === 'approved' ? '审批意见（选填，无需可留空）' : '请填写审批理由'}
                      className="glass-input" style={{ minHeight: 70, marginTop: 10 }} />
                    <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <button onClick={getAiSuggestion} disabled={suggesting}
                        className="glass-btn glass-btn-outline glass-btn-sm" style={{ borderColor: 'var(--purple)', color: 'var(--purple)' }}>
                        {suggesting ? '生成中...' : '💡 获取智能建议'}
                      </button>
                      <button onClick={submitReview} disabled={submitting} className="glass-btn" style={{
                        background: reviewAction === 'approved' ? 'var(--green)' : reviewAction === 'needs_revision' ? 'var(--orange)' : 'var(--red)',
                        marginLeft: 'auto',
                      }}>{submitting ? '提交中...' : '确认提交'}</button>
                    </div>
                  </>
                )}
              </>
            )}

            <div style={{ marginTop: 16, textAlign: 'right' }}>
              <button onClick={() => { setSelectedRecord(null); setReviewId(null) }}
                className="glass-btn glass-btn-outline">关闭</button>
            </div>
          </GlassCard>
        </div>
      )}
    </div>
  )
}
