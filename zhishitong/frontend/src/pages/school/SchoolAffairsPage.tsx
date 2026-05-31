import React, { useEffect, useState } from 'react'
import axios from 'axios'
import { getDocTypeLabel } from '../../constants/docTypes'
import { getFieldLabel } from '../../constants/fieldLabels'
import GlassCard from '../../components/GlassCard'
import AuthImage from '../../components/AuthImage'

interface SchoolRecord {
  id: number; username: string; department: string | null
  original_filename: string | null; document_type: string | null
  status: string; current_stage: string
  filled_json: string | null; decision_reason: string | null
  suggestions: string | null; missing_info: string | null
  stages: any[]; is_deleted: boolean; created_at: string
}

const STAGE_LABELS: Record<string, string> = {
  dept_review: '📋 部门审批',
  finance_review: '💰 财务审批',
  school_review: '🏫 学校审批',
  completed: '✅ 已完成',
}

const STATUS_LABELS: Record<string, string> = {
  pending: '⏳ 待审批',
  approved: '✅ 已通过',
  rejected: '❌ 不通过',
  needs_revision: '📝 需修改',
  cancelled: '⊘ 取消',
  withdrawn: '↩️ 已撤回',
}

const DOC_ICONS: Record<string, string> = {
  reimbursement: '💰', leave: '📝', club_application: '🎉',
  classroom_booking: '🏫', business_trip: '✈️',
}

export default function SchoolAffairsPage() {
  const [records, setRecords] = useState<SchoolRecord[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [filterType, setFilterType] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [filterStage, setFilterStage] = useState('')
  const [loading, setLoading] = useState(true)
  const [selectedRecord, setSelectedRecord] = useState<SchoolRecord | null>(null)
  const [reviewId, setReviewId] = useState<number | null>(null)
  const [reviewAction, setReviewAction] = useState<'approved' | 'rejected'>('approved')
  const [reviewReason, setReviewReason] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [suggesting, setSuggesting] = useState(false)

  const fetchRecords = async () => {
    setLoading(true)
    const params: any = { page, page_size: 30 }
    if (filterType) params.document_type = filterType
    if (filterStatus) params.status = filterStatus
    if (filterStage) params.stage = filterStage
    try {
      const res = await axios.get('/api/school/affairs', { params })
      setRecords(res.data.items); setTotal(res.data.total)
    } catch {} finally { setLoading(false) }
  }

  useEffect(() => { fetchRecords() }, [page, filterType, filterStatus, filterStage])
  useEffect(() => { setPage(1) }, [filterType, filterStatus, filterStage])

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

  const openSchoolReview = (record: SchoolRecord, action: 'approved' | 'rejected') => {
    setReviewId(record.id)
    setReviewAction(action)
    setReviewReason('')
    setSelectedRecord(record)
  }

  const submitReview = async () => {
    if (!reviewId) return
    if (reviewAction === 'rejected' && !reviewReason.trim()) {
      alert('驳回时请填写审批理由'); return
    }
    setSubmitting(true)
    try {
      await axios.put(`/api/school/records/${reviewId}/status`, {
        status: reviewAction, reason: reviewReason,
      })
      setReviewId(null); setReviewReason(''); setSelectedRecord(null)
      fetchRecords()
    } catch (e: any) {
      alert(e?.response?.data?.detail || '操作失败')
    } finally { setSubmitting(false) }
  }

  return (
    <div>
      <h1 className="page-title">📋 全校事务总览</h1>

      <GlassCard size="sm" style={{ marginBottom: 12, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-secondary)' }}>筛选：</span>
        <select value={filterType} onChange={e => setFilterType(e.target.value)}
          className="glass-input" style={{ width: 'auto', padding: '4px 8px' }}>
          <option value="">全部类型</option>
          <option value="reimbursement">💰 报销</option>
          <option value="leave">📝 请假</option>
          <option value="club_application">🎉 社团活动</option>
          <option value="classroom_booking">🏫 教室借用</option>
          <option value="business_trip">✈️ 出差</option>
        </select>
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
        <button onClick={() => fetchRecords()}
          className="glass-btn glass-btn-outline glass-btn-sm">刷新</button>
        <span style={{ marginLeft: 'auto', fontSize: 13, color: 'var(--text-secondary)' }}>共 {total} 条</span>
      </GlassCard>

      {loading ? <GlassCard className="state-panel state-panel-loading">加载中...</GlassCard> :
        records.length === 0 ? <GlassCard className="state-panel state-panel-empty">暂无事务</GlassCard> : (
          <GlassCard strong className="glass-table-wrapper" style={{ padding: 0 }}>
            <table className="glass-table">
              <thead><tr>
                <th>申请人</th>
                <th>部门</th>
                <th>类型</th>
                <th>当前阶段</th>
                <th>状态</th>
                <th>处理意见</th>
                <th>时间</th>
                <th>操作</th>
              </tr></thead>
              <tbody>
                {records.map(r => (
                  <tr key={r.id} style={{ background: r.status === 'pending' && r.current_stage === 'school_review' ? 'rgba(255,149,0,0.05)' : 'transparent' }}>
                    <td>{r.username}</td>
                    <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{r.department || '—'}</td>
                    <td>
                      {DOC_ICONS[r.document_type || ''] || ''} {getDocTypeLabel(r.document_type)}
                    </td>
                    <td style={{ fontSize: 12 }}>
                      <span className={`glass-tag ${r.current_stage === 'school_review' ? 'glass-tag-orange' : ''}`}
                        style={{ background: r.current_stage === 'school_review' ? 'rgba(255,149,0,0.12)' : 'var(--glass-bg)', border: 'none' }}>
                        {STAGE_LABELS[r.current_stage] || r.current_stage}
                      </span>
                    </td>
                    <td style={{ fontWeight: 500 }}>{STATUS_LABELS[r.status] || r.status}</td>
                    <td style={{ maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 12, color: 'var(--text-secondary)' }}>
                      {r.decision_reason || '—'}
                    </td>
                    <td style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                      {new Date(r.created_at).toLocaleDateString('zh-CN')}
                    </td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      {r.current_stage === 'school_review' && r.status === 'pending' ? (
                        <div className="btn-group" style={{ gap: 4 }}>
                          <button onClick={() => openSchoolReview(r, 'approved')}
                            className="glass-btn glass-btn-success glass-btn-sm">通过</button>
                          <button onClick={() => openSchoolReview(r, 'rejected')}
                            className="glass-btn glass-btn-danger glass-btn-sm">驳回</button>
                        </div>
                      ) : (
                        <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </GlassCard>
        )}

      {/* 分页 */}
      <div style={{ marginTop: 16, display: 'flex', justifyContent: 'center', gap: 8, alignItems: 'center' }}>
        <button disabled={page <= 1} onClick={() => setPage(p => p - 1)} className="glass-btn glass-btn-outline glass-btn-sm">上一页</button>
        <span style={{ fontSize: 13, color: 'var(--text-secondary)', fontWeight: 500 }}>第 {page} 页</span>
        <button disabled={page * 30 >= total} onClick={() => setPage(p => p + 1)}
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

            <GlassCard size="xs" style={{ marginBottom: 12, fontSize: 13, color: 'var(--text-secondary)' }}>
              <div>👤 申请人：{selectedRecord.username}</div>
              <div>🏢 部门：{selectedRecord.department || '—'}</div>
              <div>📄 文件：{selectedRecord.original_filename || '—'}</div>
              <div>🏷️ 类型：{getDocTypeLabel(selectedRecord.document_type)}</div>
              <div>📌 阶段：{STAGE_LABELS[selectedRecord.current_stage]}</div>
              {selectedRecord.decision_reason && <div style={{ marginTop: 4, color: 'var(--accent)' }}>📋 意见：{selectedRecord.decision_reason}</div>}
            </GlassCard>

            {(selectedRecord as any).image_url && (
              <div style={{ marginBottom: 12, textAlign: 'center' }}>
                <AuthImage src={(selectedRecord as any).image_url} alt="文件" style={{ maxWidth: '100%', maxHeight: 240, borderRadius: 'var(--radius-xs)', border: '1px solid var(--glass-border)', cursor: 'pointer', objectFit: 'contain' }}
                  onClick={() => window.open((selectedRecord as any).image_url, '_blank')} />
              </div>
            )}

            {selectedRecord.filled_json && (() => {
              try {
                const data = JSON.parse(selectedRecord.filled_json);
                const entries = Object.entries(data);
                if (entries.length > 0) return (
                  <GlassCard size="xs" style={{ background: 'rgba(0,122,255,0.06)', border: '1px solid rgba(0,122,255,0.15)', marginBottom: 12 }}>
                    <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--accent)', marginBottom: 6 }}>📋 提取数据</div>
                    <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
                      <tbody>{entries.map(([k, v]) => (
                        <tr key={k} style={{ borderBottom: '1px solid var(--divider)' }}>
                          <td style={{ padding: '4px 8px', color: 'var(--text-secondary)', width: 120 }}>{getFieldLabel(k)}</td>
                          <td style={{ padding: '4px 8px', color: 'var(--text-primary)' }}>{String(v ?? '')}</td>
                        </tr>
                      ))}</tbody>
                    </table>
                  </GlassCard>
                );
              } catch {} return null;
            })()}

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

            {selectedRecord.status === 'pending' && selectedRecord.current_stage === 'school_review' && (
              <>
                <hr className="glass-divider" />
                <h4 style={{ margin: '0 0 8px', fontSize: 14 }}>✍️ 学校审批</h4>
                <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                  {[
                    { action: 'approved' as const, label: '通过', color: 'var(--green)' },
                    { action: 'rejected' as const, label: '驳回', color: 'var(--red)' },
                  ].map(btn => (
                    <button key={btn.action} onClick={() => {
                      setReviewId(selectedRecord.id); setReviewAction(btn.action)
                      if (reviewId !== selectedRecord.id || reviewAction !== btn.action) setReviewReason('')
                    }} style={{
                      flex: 1, padding: '10px 0', border: `1.5px solid ${btn.color}`,
                      background: reviewId === selectedRecord.id && reviewAction === btn.action ? btn.color : 'transparent',
                      color: reviewId === selectedRecord.id && reviewAction === btn.action ? '#fff' : btn.color,
                      borderRadius: 10, cursor: 'pointer', fontSize: 14, fontWeight: 550,
                      fontFamily: 'var(--font-stack)',
                      transition: 'all 0.25s cubic-bezier(0.34, 1.56, 0.64, 1)',
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
                        {suggesting ? '生成中…' : 'AI 智能填写意见'}
                      </button>
                      <span style={{ flex: 1 }} />
                      <button onClick={submitReview} disabled={submitting}
                        className="glass-btn glass-btn-lg"
                        style={{ background: reviewAction === 'approved' ? 'var(--green)' : 'var(--red)' }}>
                        {submitting ? '提交中…' : '确认审批'}
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
