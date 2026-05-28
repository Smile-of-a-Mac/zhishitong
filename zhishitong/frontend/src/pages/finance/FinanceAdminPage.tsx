import React, { useEffect, useState } from 'react'
import axios from 'axios'
import { getDocTypeLabel } from '../../constants/docTypes'
import { getFieldLabel } from '../../constants/fieldLabels'
import GlassCard from '../../components/GlassCard'
import ApprovalProgressBar from '../../components/ApprovalProgressBar'
import { STATUS_LABELS, STAGE_LABELS } from '../../utils/constants'

interface FinanceRecord {
  id: number; username: string; department: string | null
  original_filename: string | null; document_type: string | null
  status: string; current_stage: string
  filled_json: string | null; decision_reason: string | null
  suggestions: string | null; missing_info: string | null
  stages: any[]; image_url?: string; is_deleted: boolean; created_at: string
}

interface FinanceStats {
  department: string; total_records: number
  pending: number; approved: number; rejected: number; today_new: number
}

export default function FinanceAdminPage() {
  const [records, setRecords] = useState<FinanceRecord[]>([])
  const [stats, setStats] = useState<FinanceStats | null>(null)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [filterStatus, setFilterStatus] = useState('')
  const [loading, setLoading] = useState(true)
  const [selectedRecord, setSelectedRecord] = useState<FinanceRecord | null>(null)
  const [reviewId, setReviewId] = useState<number | null>(null)
  const [reviewAction, setReviewAction] = useState<'approved' | 'rejected'>('approved')
  const [reviewReason, setReviewReason] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [suggesting, setSuggesting] = useState(false)

  const fetchRecords = async () => {
    setLoading(true)
    const params: any = { page, page_size: 20 }
    if (filterStatus) params.status = filterStatus
    try {
      const res = await axios.get('/api/finance/records', { params })
      setRecords(res.data.items); setTotal(res.data.total)
    } catch {} finally { setLoading(false) }
  }

  const fetchStats = async () => {
    try { const res = await axios.get('/api/finance/stats'); setStats(res.data) } catch {}
  }

  useEffect(() => { fetchRecords(); fetchStats() }, [page])
  useEffect(() => { setPage(1); fetchRecords() }, [filterStatus])

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

  const submitReview = async () => {
    if (!reviewId) return
    if (reviewAction === 'rejected' && !reviewReason.trim()) {
      alert('驳回时请填写审批理由'); return
    }
    setSubmitting(true)
    try {
      await axios.put(`/api/finance/records/${reviewId}/status`, {
        status: reviewAction, reason: reviewReason,
      })
      setReviewId(null); setReviewReason(''); setSelectedRecord(null)
      fetchRecords(); fetchStats()
    } catch (e: any) {
      alert(e?.response?.data?.detail || '操作失败')
    } finally { setSubmitting(false) }
  }

  return (
    <div>
      <h1 className="page-title">💰 财务管理</h1>

      {stats && (
        <div className="stats-grid">
          {[
            { label: '待审批报销', value: stats.pending, color: 'var(--orange)' },
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

      <GlassCard size="sm" style={{ marginBottom: 12, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-secondary)' }}>筛选：</span>
        <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
          className="glass-input" style={{ width: 'auto', padding: '4px 8px' }}>
          <option value="">全部状态</option>
          <option value="pending">待审批</option>
          <option value="approved">已通过</option>
          <option value="rejected">不通过</option>
        </select>
        <button onClick={() => { setFilterStatus(''); fetchRecords(); fetchStats() }}
          className="glass-btn glass-btn-outline glass-btn-sm">🔄 刷新</button>
        <span style={{ marginLeft: 'auto', fontSize: 13, color: 'var(--text-secondary)' }}>共 {total} 条报销待审</span>
      </GlassCard>

      {loading ? <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-secondary)' }}>加载中...</div> :
        records.length === 0 ? <GlassCard style={{ textAlign: 'center', color: 'var(--text-secondary)' }}>暂无待财务审批的报销事务</GlassCard> : (
          <GlassCard strong className="glass-table-wrapper" style={{ padding: 0 }}>
            <table className="glass-table">
              <thead><tr>
                <th>申请人</th>
                <th>部门</th>
                <th>文件</th>
                <th>当前阶段</th>
                <th>状态</th>
                <th>审批意见</th>
                <th>提交时间</th>
                <th>操作</th>
              </tr></thead>
              <tbody>
                {records.map(r => (
                  <tr key={r.id} style={{ background: r.status === 'pending' ? 'rgba(255,149,0,0.05)' : 'transparent' }}>
                    <td>{r.username}</td>
                    <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{r.department || '—'}</td>
                    <td style={{ maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {r.original_filename || '—'}
                    </td>
                    <td style={{ fontSize: 12 }}>{STAGE_LABELS[r.current_stage] || r.current_stage}</td>
                    <td style={{ fontWeight: 500 }}>{STATUS_LABELS[r.status] || r.status}</td>
                    <td style={{ maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 12, color: 'var(--text-secondary)' }}>
                      {r.decision_reason || '—'}
                    </td>
                    <td style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                      {new Date(r.created_at).toLocaleDateString('zh-CN')}
                    </td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <button onClick={() => { setSelectedRecord(r); setReviewId(null) }}
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
              <span style={{ marginLeft: 12, fontSize: 14, fontWeight: 400, color: '#666' }}>
                {STATUS_LABELS[selectedRecord.status]}
              </span>
            </h3>

            <div style={{ padding: 12, background: '#f6f8fa', borderRadius: 6, marginBottom: 12, fontSize: 13, color: '#666' }}>
              <div>👤 申请人：{selectedRecord.username}</div>
              <div>🏢 部门：{selectedRecord.department || '—'}</div>
              <div>📄 文件：{selectedRecord.original_filename || '—'}</div>
              <div>🏷️ 类型：{getDocTypeLabel(selectedRecord.document_type)}</div>
              <div>📌 阶段：{STAGE_LABELS[selectedRecord.current_stage]}</div>
              {selectedRecord.decision_reason && <div style={{ marginTop: 4, color: '#1677ff' }}>📋 部门意见：{selectedRecord.decision_reason}</div>}
            </div>

            {selectedRecord.image_url && (
              <div style={{ marginBottom: 12, textAlign: 'center' }}>
                <img src={selectedRecord.image_url} alt="文件" style={{ maxWidth: '100%', maxHeight: 240, borderRadius: 6, border: '1px solid #e8e8e8', cursor: 'pointer' }}
                  onClick={() => window.open(selectedRecord.image_url, '_blank')} />
              </div>
            )}

            {selectedRecord.filled_json && (() => {
              try {
                const data = JSON.parse(selectedRecord.filled_json);
                const entries = Object.entries(data);
                if (entries.length > 0) return (
                  <div style={{ padding: 12, background: '#f0f5ff', borderRadius: 6, marginBottom: 12 }}>
                    <div style={{ fontWeight: 600, fontSize: 13, color: '#1677ff', marginBottom: 6 }}>📋 提取数据</div>
                    <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
                      <tbody>{entries.map(([k, v]) => (
                        <tr key={k} style={{ borderBottom: '1px solid #e8e8e8' }}>
                          <td style={{ padding: '4px 8px', color: '#888', width: 120 }}>{getFieldLabel(k)}</td>
                          <td style={{ padding: '4px 8px', color: '#333' }}>{String(v ?? '')}</td>
                        </tr>
                      ))}</tbody>
                    </table>
                  </div>
                );
              } catch {} return null;
            })()}

            {selectedRecord.stages && selectedRecord.stages.length > 0 && (
              <div style={{ padding: 12, background: '#f6ffed', borderRadius: 6, marginBottom: 12 }}>
                <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>📋 审批历程</div>
                {selectedRecord.stages.map((s: any, i: number) => (
                  <div key={i} style={{ fontSize: 13, color: '#666', marginBottom: 3 }}>
                    • {s.label || s.stage}：{s.status === 'approved' ? '✅ 通过' : s.status === 'rejected' ? '❌ 驳回' : '⏳'} — {s.reviewer || '系统'}（{s.reason || '无意见'}）
                  </div>
                ))}
              </div>
            )}

            {selectedRecord.suggestions && (() => {
              try { const sug = JSON.parse(selectedRecord.suggestions);
                if (Array.isArray(sug) && sug.length > 0) return (
                  <GlassCard size="xs" style={{ background: 'rgba(255,149,0,0.08)', border: '1px solid rgba(255,149,0,0.2)', marginBottom: 12 }}>
                    <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--orange)', marginBottom: 4 }}>💡 智能建议</div>
                    {sug.map((s: string, i: number) => <div key={i} style={{ fontSize: 13, color: 'var(--text-secondary)' }}>• {s}</div>)}
                  </GlassCard>
                );
              } catch {} return null;
            })()}

            {selectedRecord.status === 'pending' && (
              <>
                <hr className="glass-divider" />
                <h4 style={{ margin: '0 0 8px', fontSize: 14 }}>✍️ 财务审批</h4>
                <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                  {[
                    { action: 'approved' as const, label: '✓ 通过', color: 'var(--green)' },
                    { action: 'rejected' as const, label: '✗ 驳回', color: 'var(--red)' },
                  ].map(btn => (
                    <button key={btn.action} onClick={() => {
                      setReviewId(selectedRecord.id); setReviewAction(btn.action)
                      if (reviewId !== selectedRecord.id || reviewAction !== btn.action) setReviewReason('')
                    }} style={{
                      flex: 1, padding: '8px 0', border: `1px solid ${btn.color}`,
                      background: reviewId === selectedRecord.id && reviewAction === btn.action ? btn.color : 'transparent',
                      color: reviewId === selectedRecord.id && reviewAction === btn.action ? '#fff' : btn.color,
                      borderRadius: 6, cursor: 'pointer', fontSize: 13, fontWeight: 500,
                      transition: 'all 0.2s ease',
                    }}>{btn.label}</button>
                  ))}
                </div>
                {reviewId === selectedRecord.id && (
                  <>
                    <textarea value={reviewReason} onChange={e => setReviewReason(e.target.value)}
                      placeholder="请填写审批理由（必填）" className="glass-input" style={{ minHeight: 70 }} />
                    <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <button onClick={getAiSuggestion} disabled={suggesting}
                        className="glass-btn glass-btn-outline glass-btn-sm" style={{ borderColor: 'var(--purple)', color: 'var(--purple)' }}>
                        {suggesting ? '生成中...' : '💡 获取智能建议'}
                      </button>
                      <button onClick={submitReview} disabled={submitting}
                        className="glass-btn" style={{ marginLeft: 'auto', background: reviewAction === 'approved' ? 'var(--green)' : 'var(--red)' }}>
                        {submitting ? '提交中...' : '确认审批'}
                      </button>
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
