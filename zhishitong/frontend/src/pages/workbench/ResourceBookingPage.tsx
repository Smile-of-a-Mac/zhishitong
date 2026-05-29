import React, { useEffect, useState } from 'react'
import axios from 'axios'
import { useAuth } from '../../hooks/useAuth'
import GlassCard from '../../components/GlassCard'

interface Resource {
  id: number; name?: string; plate_number?: string; location?: string;
  model?: string; capacity?: number; seats?: number;
  equipment?: string; driver?: string; is_active: boolean;
}

interface Booking {
  id: number; resource_type: string; resource_id: number; resource_name: string;
  user_id: number; username: string; title: string;
  start_time: string; end_time: string; status: string;
  participants: string; reject_reason: string; created_at: string;
}

type TabType = 'meeting_room' | 'vehicle'

export default function ResourceBookingPage() {
  const { user } = useAuth()
  const [tab, setTab] = useState<TabType>('meeting_room')
  const [rooms, setRooms] = useState<Resource[]>([])
  const [vehicles, setVehicles] = useState<Resource[]>([])
  const [bookings, setBookings] = useState<Booking[]>([])
  const [loading, setLoading] = useState(true)
  const [errorMsg, setErrorMsg] = useState('')

  // 新建预约表单
  const [showForm, setShowForm] = useState(false)
  const [formResId, setFormResId] = useState(0)
  const [formTitle, setFormTitle] = useState('')
  const [formStart, setFormStart] = useState('')
  const [formEnd, setFormEnd] = useState('')
  const [formParticipants, setFormParticipants] = useState('')
  const [formError, setFormError] = useState('')

  const isAdmin = user?.is_admin || user?.is_school_admin

  const fetchData = async () => {
    setLoading(true)
    setErrorMsg('')
    try {
      const [r, v, b] = await Promise.all([
        axios.get('/api/resources/rooms'),
        axios.get('/api/resources/vehicles'),
        axios.get('/api/resources/bookings', { params: { resource_type: tab } }),
      ])
      setRooms(r.data)
      setVehicles(v.data)
      setBookings(b.data)
    } catch (e) {
      setErrorMsg('加载资源数据失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [tab])

  const resources = tab === 'meeting_room' ? rooms : vehicles

  const handleBook = async () => {
    setFormError('')
    if (!formTitle || !formStart || !formEnd) {
      setFormError('请填写完整信息')
      return
    }
    try {
      await axios.post('/api/resources/bookings', {
        resource_type: tab,
        resource_id: formResId,
        title: formTitle,
        start_time: formStart,
        end_time: formEnd,
        participants: formParticipants,
      })
      setShowForm(false)
      setFormTitle(''); setFormStart(''); setFormEnd(''); setFormParticipants('')
      fetchData()
    } catch (e: any) {
      setFormError(e?.response?.data?.detail || '网络错误')
    }
  }

  const handleCancel = async (id: number) => {
    await axios.delete(`/api/resources/bookings/${id}`)
    fetchData()
  }

  const handleApprove = async (id: number, status: string) => {
    await axios.post(`/api/resources/bookings/${id}/approve`, { status, reject_reason: '' })
    fetchData()
  }

  const statusBadge = (s: string) => {
    const map: Record<string, { label: string; color: string }> = {
      pending: { label: '待审批', color: '#FF9500' },
      approved: { label: '已通过', color: '#34C759' },
      rejected: { label: '已驳回', color: '#FF3B30' },
      cancelled: { label: '已取消', color: '#8E8E93' },
    }
    const m = map[s] || { label: s, color: '#999' }
    return <span style={{ fontSize: 11, padding: '2px 6px', borderRadius: 8, background: m.color + '20', color: m.color }}>{m.label}</span>
  }

  if (loading) return <GlassCard style={{ padding: 30, textAlign: 'center', color: 'var(--text-secondary)' }}>加载中...</GlassCard>

  if (errorMsg) {
    return (
      <GlassCard style={{ padding: 30, textAlign: 'center' }}>
        <p style={{ color: 'var(--red)', marginBottom: 12 }}>⚠️ {errorMsg}</p>
        <button className="glass-btn glass-btn-outline glass-btn-sm" onClick={fetchData}>重试</button>
      </GlassCard>
    )
  }

  return (
    <div>
      <h1 className="page-title">📅 资源预约</h1>
      <GlassCard size="sm" style={{ marginBottom: 16 }}>
        {/* Tab 切换 */}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button
            className={`glass-btn ${tab === 'meeting_room' ? 'glass-btn-primary' : 'glass-btn-outline'} glass-btn-sm`}
            onClick={() => setTab('meeting_room')}
          >
            🏢 会议室
          </button>
          <button
            className={`glass-btn ${tab === 'vehicle' ? 'glass-btn-primary' : 'glass-btn-outline'} glass-btn-sm`}
            onClick={() => setTab('vehicle')}
          >
            🚗 车辆
          </button>
        </div>
      </GlassCard>

      {/* 资源列表 */}
      <GlassCard style={{ padding: 16, marginBottom: 16 }}>
        <h3 className="section-title" style={{ margin: '0 0 12px' }}>{tab === 'meeting_room' ? '🏢 可用会议室' : '🚗 可用车辆'}</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 10 }}>
          {resources.map(r => (
            <GlassCard key={r.id} size="xs" style={{ padding: 12, cursor: 'pointer' }}
              onClick={() => { setFormResId(r.id); setShowForm(true) }}>
              <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4 }}>
                {tab === 'meeting_room' ? r.name : r.plate_number}
              </div>
              {tab === 'meeting_room' ? (
                <>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>📍 {r.location}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>👥 容纳 {r.capacity} 人</div>
                  {r.equipment && <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>📋 {r.equipment}</div>}
                </>
              ) : (
                <>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>🚘 {r.model} · {r.seats}座</div>
                  {r.driver && <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>👤 {r.driver}</div>}
                </>
              )}
              <div style={{ marginTop: 8, fontSize: 12, color: 'var(--accent-color)' }}>点击预约 →</div>
            </GlassCard>
          ))}
        </div>
      </GlassCard>

      {/* 预约记录 */}
      <GlassCard style={{ padding: 16 }}>
        <h3 className="section-title" style={{ margin: '0 0 12px' }}>📋 预约记录</h3>
        {bookings.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 20, color: 'var(--text-secondary)', fontSize: 13 }}>暂无预约记录</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {bookings.map(b => (
              <GlassCard key={b.id} size="xs" style={{ padding: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>{b.title}</span>
                  {statusBadge(b.status)}
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                  {b.resource_name} · {new Date(b.start_time).toLocaleString('zh-CN')} ~ {new Date(b.end_time).toLocaleString('zh-CN')}
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                  申请人: {b.username}
                  {b.participants && ` · 参与人: ${b.participants}`}
                </div>
                {b.reject_reason && (
                  <div style={{ fontSize: 12, color: '#FF3B30', marginTop: 4 }}>驳回原因: {b.reject_reason}</div>
                )}
                <div style={{ marginTop: 6, display: 'flex', gap: 6 }}>
                  {b.status === 'pending' && isAdmin && (
                    <>
                      <button className="glass-btn glass-btn-sm" style={{ color: '#34C759', fontSize: 12 }}
                        onClick={() => handleApprove(b.id, 'approved')}>通过</button>
                      <button className="glass-btn glass-btn-sm" style={{ color: '#FF3B30', fontSize: 12 }}
                        onClick={() => handleApprove(b.id, 'rejected')}>驳回</button>
                    </>
                  )}
                  {b.status !== 'cancelled' && (b.user_id === user?.id || isAdmin) && (
                    <button className="glass-btn glass-btn-sm glass-btn-outline" style={{ fontSize: 12 }}
                      onClick={() => handleCancel(b.id)}>取消</button>
                  )}
                </div>
              </GlassCard>
            ))}
          </div>
        )}
      </GlassCard>

      {/* 新建预约弹窗 */}
      {showForm && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
        }} onClick={() => setShowForm(false)}>
          <GlassCard strong style={{ padding: 24, width: '90%', maxWidth: 400, maxHeight: '80vh', overflow: 'auto' }}
            onClick={e => e.stopPropagation()}>
            <h3 style={{ margin: '0 0 16px', fontSize: 18, fontWeight: 600 }}>新建预约</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <input className="glass-input" placeholder="预约事由" value={formTitle}
                onChange={e => setFormTitle(e.target.value)} />
              <div>
                <label style={{ fontSize: 12, color: 'var(--text-secondary)' }}>开始时间</label>
                <input className="glass-input" type="datetime-local" value={formStart}
                  onChange={e => setFormStart(e.target.value)} style={{ width: '100%' }} />
              </div>
              <div>
                <label style={{ fontSize: 12, color: 'var(--text-secondary)' }}>结束时间</label>
                <input className="glass-input" type="datetime-local" value={formEnd}
                  onChange={e => setFormEnd(e.target.value)} style={{ width: '100%' }} />
              </div>
              <input className="glass-input" placeholder="参与人员（逗号分隔）" value={formParticipants}
                onChange={e => setFormParticipants(e.target.value)} />
              {formError && <div style={{ color: '#FF3B30', fontSize: 12 }}>{formError}</div>}
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <button className="glass-btn glass-btn-outline glass-btn-sm" onClick={() => setShowForm(false)}>取消</button>
                <button className="glass-btn glass-btn-primary glass-btn-sm" onClick={handleBook}>确认预约</button>
              </div>
            </div>
          </GlassCard>
        </div>
      )}
    </div>
  )
}
