import React, { useEffect, useState } from 'react'
import axios from 'axios'
import GlassCard from '../../components/GlassCard'
import { DOC_TYPE_LABELS } from '../../constants/docTypes'

interface DashboardData {
  total_users: number
  total_approvals: number
  pending_approvals: number
  today_new_approvals: number
  approvals_by_day: { date: string; count: number }[]
  approvals_by_type: { document_type: string; count: number }[]
  approvals_by_status: Record<string, number>
  avg_processing_hours: number
  approval_rate: number
  rejection_rate: number
  top_departments: { department: string; total: number; approved: number; pending: number }[]
  top_applicants: { username: string; count: number }[]
}



const statusLabels: Record<string, string> = {
  pending: '⏳ 待审批', approved: '✅ 已通过', rejected: '❌ 已驳回',
  needs_revision: '⚠️ 需修改', cancelled: '🚫 已取消', withdrawn: '↩️ 已撤回',
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [errorMsg, setErrorMsg] = useState('')

  const fetchData = async () => {
    setLoading(true)
    setErrorMsg('')
    try {
      const res = await axios.get('/api/dashboard/overview')
      setData(res.data)
    } catch (error: any) {
      setData(null)
      const detail = error?.response?.data?.detail
      setErrorMsg(typeof detail === 'string' ? detail : '加载看板数据失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [])

  if (loading) {
    return <GlassCard style={{ padding: 30, textAlign: 'center', color: 'var(--text-secondary)' }}>加载中...</GlassCard>
  }

  if (errorMsg) {
    return (
      <GlassCard style={{ padding: 30, textAlign: 'center', color: 'var(--red)' }}>
        <div style={{ marginBottom: 12 }}>⚠️ {errorMsg}</div>
        <button className="glass-btn glass-btn-outline glass-btn-sm" onClick={fetchData}>重试</button>
      </GlassCard>
    )
  }

  if (!data) {
    return <GlassCard style={{ padding: 30, textAlign: 'center', color: 'var(--text-secondary)' }}>暂无数据</GlassCard>
  }

  const maxDayCount = Math.max(1, ...data.approvals_by_day.map(d => d.count))

  return (
    <div>
      <h1 className="page-title">📊 数据看板</h1>
      <p className="page-subtitle">覆盖审批量、效率、阶段分布和部门活跃度，用于快速识别流程瓶颈</p>

      {/* 概览卡片 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10, marginBottom: 16 }}>
        <StatCard label="总用户" value={data.total_users} color="var(--accent-color)" />
        <StatCard label="总审批量" value={data.total_approvals} color="#5856D6" />
        <StatCard label="待审批" value={data.pending_approvals} color="#FF9500" />
        <StatCard label="今日新增" value={data.today_new_approvals} color="#34C759" />
      </div>

      <GlassCard size="sm" style={{ padding: 16, marginBottom: 12 }}>
        <h3 className="section-title" style={{ margin: '0 0 12px' }}>效率指标</h3>
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
          <div>
            <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>平均处理时长</span>
            <div style={{ fontSize: 22, fontWeight: 700 }}>{data.avg_processing_hours}h</div>
          </div>
          <div>
            <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>审批通过率</span>
            <div style={{ fontSize: 22, fontWeight: 700, color: '#34C759' }}>{(data.approval_rate * 100).toFixed(1)}%</div>
          </div>
          <div>
            <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>驳回率</span>
            <div style={{ fontSize: 22, fontWeight: 700, color: '#FF3B30' }}>{(data.rejection_rate * 100).toFixed(1)}%</div>
          </div>
        </div>
      </GlassCard>

      {/* 30天趋势 */}
      <GlassCard size="sm" style={{ padding: 16, marginBottom: 12 }}>
        <h3 className="section-title" style={{ margin: '0 0 12px' }}>近30天审批趋势</h3>
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height: 80 }}>
          {data.approvals_by_day.map((d, i) => (
            <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
              <div style={{
                width: '100%', maxWidth: 14, borderRadius: '4px 4px 0 0',
                height: `${(d.count / maxDayCount) * 70}px`,
                background: d.count > 0 ? 'var(--accent-color)' : 'var(--divider)',
                minHeight: 2,
                transition: 'height 0.3s',
              }} />
              {i % 5 === 0 && (
                <span style={{ fontSize: 8, color: 'var(--text-secondary)', marginTop: 2 }}>{d.date}</span>
              )}
            </div>
          ))}
        </div>
      </GlassCard>

      {/* 按类型 + 状态 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 10, marginBottom: 12 }}>
        <GlassCard size="sm" style={{ padding: 14 }}>
          <h3 className="section-title" style={{ margin: '0 0 10px', fontSize: 14 }}>按类型分布</h3>
          {data.approvals_by_type.slice(0, 8).map(t => (
            <div key={t.document_type} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontSize: 13 }}>
              <span>{DOC_TYPE_LABELS[t.document_type] || t.document_type}</span>
              <span style={{ fontWeight: 600 }}>{t.count}</span>
            </div>
          ))}
        </GlassCard>
        <GlassCard size="sm" style={{ padding: 14 }}>
          <h3 className="section-title" style={{ margin: '0 0 10px', fontSize: 14 }}>状态分布</h3>
          {Object.entries(data.approvals_by_status).map(([k, v]) => (
            <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontSize: 13 }}>
              <span>{statusLabels[k] || k}</span>
              <span style={{ fontWeight: 600 }}>{v}</span>
            </div>
          ))}
        </GlassCard>
      </div>

      {/* 部门排名 */}
      {data.top_departments.length > 0 && (
        <GlassCard size="sm" style={{ padding: 14, marginBottom: 12 }}>
          <h3 className="section-title" style={{ margin: '0 0 10px', fontSize: 14 }}>部门审批量排名</h3>
          {data.top_departments.map((d, i) => (
            <div key={d.department} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '6px 0', fontSize: 13,
            }}>
              <span><span style={{ color: 'var(--text-secondary)', marginRight: 8 }}>#{i + 1}</span>{d.department}</span>
              <span>
                总计 {d.total}
                <span style={{ color: '#34C759', marginLeft: 8 }}>✓{d.approved}</span>
                <span style={{ color: '#FF9500', marginLeft: 8 }}>⏳{d.pending}</span>
              </span>
            </div>
          ))}
        </GlassCard>
      )}

      {/* 高频申请人 */}
      <GlassCard size="sm" style={{ padding: 14 }}>
        <h3 className="section-title" style={{ margin: '0 0 10px', fontSize: 14 }}>高频申请人</h3>
        {data.top_applicants.map((a, i) => (
          <div key={a.username} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontSize: 13 }}>
            <span><span style={{ color: 'var(--text-secondary)', marginRight: 8 }}>#{i + 1}</span>{a.username}</span>
            <span style={{ fontWeight: 600 }}>{a.count} 次</span>
          </div>
        ))}
      </GlassCard>
    </div>
  )
}

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <GlassCard size="sm" style={{ padding: '14px 16px', textAlign: 'center' }}>
      <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 700, color }}>{value}</div>
    </GlassCard>
  )
}
