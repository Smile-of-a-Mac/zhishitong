import React, { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import axios from 'axios'
import { getDocTypeLabel } from '../../constants/docTypes'
import GlassCard from '../../components/GlassCard'
import ApprovalProgressBar from '../../components/ApprovalProgressBar'
import { STAGE_LABELS, STATUS_LABELS } from '../../utils/constants'
import { parseApiError } from '../../utils/api'

type TabKey = 'all' | 'pending' | 'approved' | 'rejected'

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
  const [activeTab, setActiveTab] = useState<TabKey>('all')
  const [errorMsg, setErrorMsg] = useState('')
  const nav = useNavigate()
  const [searchParams] = useSearchParams()

  const fetch = async () => {
    setLoading(true)
    setErrorMsg('')
    try {
      const res = await axios.get('/api/approvals?page_size=50')
      setRecords(res.data.items || [])
    } catch (e: any) {
      setRecords([])
      setErrorMsg(parseApiError(e, '加载历史记录失败'))
    } finally { setLoading(false) }
  }
  useEffect(() => { fetch() }, [])

  // 支持 ?detail=recordId 从通知页面跳转来自动打开详情
  useEffect(() => {
    const detailId = searchParams.get('detail')
    if (detailId) {
      const id = parseInt(detailId)
      if (id && records.length > 0) {
        // 如果记录已在列表中，直接打开详情
        const existing = records.find(r => r.id === id)
        if (existing) {
          showDetail(id)
          return
        }
      }
      // 否则先发起一次查询
      if (id) showDetail(id)
    }
  }, [searchParams, records])

  const activeTabConfig = TAB_CONFIG.find(t => t.key === activeTab)
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

  const showDetail = async (id: number) => {
    try {
      const res = await axios.get(`/api/approvals/${id}`)
      setDetail(res.data)
    } catch (e: any) {
      alert(parseApiError(e, '加载详情失败'))
    }
  }

  if (loading) return <GlassCard style={{ color: 'var(--text-secondary)', padding: 40, textAlign: 'center' }}>加载中...</GlassCard>

  const statusLabel = (s: string) => STATUS_LABELS[s] || s

  const isConcluded = (s: string) => ['approved', 'rejected', 'cancelled'].includes(s)
  const canCancel = (s: string) => s === 'needs_revision'
  const stageLabel = (stage: string | undefined) => {
    if (!stage) return '—'
    return STAGE_LABELS[stage] || stage
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

      {/* Tab 导航 */}
      <GlassCard size="sm" style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {TAB_CONFIG.map(tab => (
          <button
            key={tab.key}
            className={`glass-btn glass-btn-sm ${activeTab === tab.key ? 'glass-btn-primary' : 'glass-btn-outline'}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.icon} {tab.label} ({countByStatus(tab.key)})
          </button>
        ))}
      </div>
      </GlassCard>

      {errorMsg && (
        <GlassCard size="xs" style={{ marginBottom: 12, background: 'rgba(255,59,48,0.08)', border: '1px solid rgba(255,59,48,0.2)' }}>
          <div style={{ color: 'var(--red)', fontSize: 13, marginBottom: 8 }}>⚠️ {errorMsg}</div>
          <button className="glass-btn glass-btn-outline glass-btn-sm" onClick={fetch}>重试</button>
        </GlassCard>
      )}

      {filteredRecords.length === 0 ? (
        <GlassCard style={{ textAlign: 'center', color: 'var(--text-secondary)', padding: 30 }}>
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
                      <ApprovalProgressBar currentStage={r.current_stage || 'dept_review'} documentType={r.document_type} />
                    ) : (
                      stageLabel(r.current_stage)
                    )}
                  </td>
                  <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-secondary)' }}>
                    {r.decision_reason || '—'}</td>
                  <td style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
                    {new Date(r.created_at).toLocaleDateString('zh-CN')}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    {r.status === 'pending' && (
                      <button onClick={e => { e.stopPropagation(); handleUrge(r.id) }}
                        className="glass-btn glass-btn-sm" style={{ marginRight: 4, color: '#FF9500' }}>催办</button>
                    )}
                    {isConcluded(r.status) ? (
                      <button onClick={e => { e.stopPropagation(); handleDelete(r.id) }}
                        className="glass-btn glass-btn-danger glass-btn-sm">删除</button>
                    ) : r.status === 'withdrawn' ? (
                      <>
                        <button onClick={e => { e.stopPropagation(); handleResubmit(r.id) }}
                          className="glass-btn glass-btn-sm" style={{ marginRight: 4 }}>重新提交</button>
                        <button onClick={e => { e.stopPropagation(); handleDelete(r.id) }}
                          className="glass-btn glass-btn-danger glass-btn-sm">删除</button>
                      </>
                    ) : canCancel(r.status) ? (
                      <>
                        <button onClick={e => { e.stopPropagation(); handleResubmit(r.id) }}
                          className="glass-btn glass-btn-sm" style={{ marginRight: 4 }}>修改</button>
                        <button onClick={e => { e.stopPropagation(); handleDelete(r.id) }}
                          className="glass-btn glass-btn-danger glass-btn-sm">取消</button>
                      </>
                    ) : (
                      r.status === 'pending' ? null : (
                        <button onClick={e => { e.stopPropagation(); handleWithdraw(r.id) }}
                          className="glass-btn glass-btn-outline glass-btn-sm">撤回</button>
                      )
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </GlassCard>
      )}

      {/* 详情弹窗 */}
      {detail && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
        }} onClick={() => setDetail(null)}>
          <GlassCard strong style={{ width: 520, maxWidth: '90vw', maxHeight: '85vh', overflow: 'auto' }}
            onClick={e => e.stopPropagation()}>
            <h3 style={{ margin: '0 0 16px', fontSize: 18 }}>
              审批详情 #{detail.id}
              <span style={{ marginLeft: 12, fontSize: 14, fontWeight: 400 }}>
                {statusLabel(detail.status)}
              </span>
            </h3>

            <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
              <div style={{ marginBottom: 4 }}>📄 类型：{getDocTypeLabel(detail.document_type)}</div>
              <div style={{ marginBottom: 4 }}>📁 文件：{detail.original_filename || '手动申报'}</div>
              <div style={{ marginBottom: 4 }}>
                📅 时间：{new Date(detail.created_at).toLocaleString('zh-CN')}
              </div>

              {/* 图片预览 */}
              {detail.image_url && (
                <div style={{ marginBottom: 12 }}>
                  <img src={detail.image_url} alt="上传文件" style={{
                    maxWidth: '100%', maxHeight: 300, borderRadius: 'var(--radius-xs)',
                    border: '1px solid var(--glass-border)', cursor: 'pointer',
                  }} onClick={() => window.open(detail.image_url, '_blank')} />
                  <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 2 }}>点击放大</div>
                </div>
              )}
              {detail.decision_reason && (
                <GlassCard size="xs" style={{ marginBottom: 8 }}>
                  <strong>📋 分析/决策理由：</strong>
                  <div style={{ marginTop: 4, color: 'var(--text-primary)' }}>{detail.decision_reason}</div>
                </GlassCard>
              )}

              {/* LLM 修改建议 */}
              {detail.suggestions && (() => {
                try {
                  const sug = JSON.parse(detail.suggestions);
                  if (Array.isArray(sug) && sug.length > 0) {
                    return (
                      <GlassCard size="xs" style={{ background: 'rgba(255,149,0,0.08)', border: '1px solid rgba(255,149,0,0.2)', marginBottom: 8 }}>
                        <div style={{ fontWeight: 600, fontSize: 12, color: 'var(--orange)', marginBottom: 4 }}>💡 智能建议</div>
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
                        <div style={{ fontWeight: 600, fontSize: 12, color: 'var(--red)', marginBottom: 4 }}>⚠️ 缺失信息</div>
                        {miss.map((m: string, i: number) => (
                          <div key={i} style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 2 }}>• 缺少「{m}」</div>
                        ))}
                      </GlassCard>
                    );
                  }
                } catch {}
                return null;
              })()}

              {/* 表单数据 */}
              {detail.filled_json && (
                <details style={{ marginTop: 8 }}>
                  <summary style={{ cursor: 'pointer', color: 'var(--accent)', fontSize: 13 }}>📋 查看提交的字段数据</summary>
                  <GlassCard size="xs" style={{ marginTop: 8 }}>
                    {(() => {
                      try {
                        const data = typeof detail.filled_json === 'string' ? JSON.parse(detail.filled_json) : detail.filled_json;
                        return Object.entries(data).map(([k, v]) => (
                          <div key={k} style={{ padding: '4px 0', borderBottom: '1px solid var(--divider)', display: 'flex' }}>
                            <span style={{ color: 'var(--text-secondary)', minWidth: 80 }}>{k}:</span>
                            <span style={{ color: 'var(--text-primary)' }}>{String(v ?? '')}</span>
                          </div>
                        ));
                      } catch { return <div>无法解析</div>; }
                    })()}
                  </GlassCard>
                </details>
              )}
            </div>

            <div style={{ marginTop: 16, textAlign: 'right' }}>
              <button onClick={() => setDetail(null)} className="glass-btn glass-btn-outline">关闭</button>
            </div>
          </GlassCard>
        </div>
      )}
    </div>
  )
}
