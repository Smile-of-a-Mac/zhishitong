import React, { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import axios from 'axios'
import GlassCard from '../../components/GlassCard'

interface Notification {
  id: number
  type: string
  title: string
  body: string
  record_id: number | null
  is_read: boolean
  created_at: string
}

const TYPE_LABEL: Record<string, string> = {
  approval_submitted: '新申请',
  approval_approved: '已通过',
  approval_rejected: '已驳回',
  approval_needs_revision: '需修改',
  approval_urged: '催办',
  approval_overdue: '超时',
  stage_advanced: '阶段变更',
  system_announcement: '系统公告',
}

const TYPE_ICON: Record<string, string> = {
  approval_submitted: '📩',
  approval_approved: '✅',
  approval_rejected: '❌',
  approval_needs_revision: '📝',
  approval_urged: '⏰',
  approval_overdue: '⚠️',
  stage_advanced: '🔄',
  system_announcement: '📢',
}

const TYPE_COLOR: Record<string, string> = {
  approval_submitted: 'var(--accent)',
  approval_approved: 'var(--green)',
  approval_rejected: 'var(--red)',
  approval_needs_revision: 'var(--orange)',
  approval_urged: 'var(--orange)',
  approval_overdue: 'var(--red)',
  stage_advanced: 'var(--accent)',
  system_announcement: 'var(--purple)',
}

// 有对应审批记录、可以跳转查看的类型
const HAS_RECORD_TYPES = new Set([
  'approval_submitted', 'approval_approved', 'approval_rejected',
  'approval_needs_revision', 'approval_urged', 'approval_overdue', 'stage_advanced',
])

export default function NotificationsPage() {
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [errorMsg, setErrorMsg] = useState('')
  const [detail, setDetail] = useState<Notification | null>(null)
  const nav = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const fetchNotifications = async () => {
    setLoading(true)
    setErrorMsg('')
    try {
      const res = await axios.get('/api/notifications', { params: { page_size: 50 } })
      const data = res.data
      setNotifications(data.items || [])
      setUnreadCount(data.unread_count || 0)
    } catch (e: any) {
      const status = e?.response?.status
      if (status) setErrorMsg(`请求失败 (${status})`)
      else setErrorMsg('网络错误，无法获取通知')
      setNotifications([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchNotifications() }, [])

  const markRead = async (id: number) => {
    await axios.post(`/api/notifications/${id}/read`)
    setNotifications(prev => prev.map(n => n.id === id ? { ...n, is_read: true } : n))
    setUnreadCount(prev => Math.max(0, prev - 1))
    // 同步更新详情弹窗中的已读状态
    setDetail(prev => prev && prev.id === id ? { ...prev, is_read: true } : prev)
  }

  const openDetail = (n: Notification) => {
    setDetail(n)
    // 自动标记已读
    if (!n.is_read) markRead(n.id)
  }

  const goToRecord = (recordId: number) => {
    setDetail(null)
    nav(`/history?detail=${recordId}`)
  }

  // 支持 URL 参数 ?record_id=xxx 直接跳转审批详情
  useEffect(() => {
    const rid = searchParams.get('record_id')
    const did = searchParams.get('detail')
    if (rid) {
      nav(`/history?detail=${rid}`, { replace: true })
      return
    }
    if (did) {
      nav(`/history?detail=${did}`, { replace: true })
    }
  }, [searchParams, nav])

  const markAllRead = async () => {
    await axios.post('/api/notifications/read-all')
    setNotifications(prev => prev.map(n => ({ ...n, is_read: true })))
    setUnreadCount(0)
  }

  const typeLabel = (t: string) => TYPE_LABEL[t] || t

  const timeAgo = (d: string) => {
    const diff = Date.now() - new Date(d).getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 1) return '刚刚'
    if (mins < 60) return `${mins} 分钟前`
    const hours = Math.floor(mins / 60)
    if (hours < 24) return `${hours} 小时前`
    const days = Math.floor(hours / 24)
    return `${days} 天前`
  }

  const fullTime = (d: string) => new Date(d).toLocaleString('zh-CN')

  if (loading) {
    return <GlassCard style={{ padding: 30, textAlign: 'center', color: 'var(--text-secondary)' }}>加载中...</GlassCard>
  }

  if (errorMsg) {
    return (
      <GlassCard style={{ padding: 30, textAlign: 'center' }}>
        <p style={{ color: 'var(--red)', marginBottom: 12 }}>⚠️ {errorMsg}</p>
        <button className="glass-btn glass-btn-outline glass-btn-sm" onClick={fetchNotifications}>重试</button>
      </GlassCard>
    )
  }

  return (
    <div>
      <h1 className="page-title" style={{ marginBottom: 6 }}>消息通知</h1>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        fontSize: 14, color: 'var(--text-secondary)',
        paddingBottom: 16, borderBottom: '1px solid var(--divider)', marginBottom: 24,
      }}>
        <span>共 {notifications.length} 条消息，未读 {unreadCount} 条</span>
        {unreadCount > 0 && (
          <button className="glass-btn glass-btn-outline glass-btn-sm" onClick={markAllRead}>
            全部已读 ({unreadCount})
          </button>
        )}
      </div>

      {notifications.length === 0 ? (
        <GlassCard style={{ padding: 40, textAlign: 'center', color: 'var(--text-secondary)' }}>
          暂无通知
        </GlassCard>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {notifications.map(n => (
            <GlassCard
              key={n.id}
              strong={!n.is_read}
              onClick={() => openDetail(n)}
              style={{
                padding: '14px 16px',
                cursor: 'pointer',
                opacity: n.is_read ? 0.7 : 1,
                position: 'relative',
                transition: 'opacity 0.2s ease, box-shadow 0.2s ease',
              }}
            >
              {!n.is_read && (
                <span style={{
                  position: 'absolute', top: 16, right: 16,
                  width: 8, height: 8, borderRadius: '50%',
                  background: 'var(--accent)',
                }} />
              )}
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span style={{
                  fontSize: 12, fontWeight: 500,
                  color: TYPE_COLOR[n.type] || 'var(--accent)',
                }}>
                  {TYPE_ICON[n.type] || '📌'} {typeLabel(n.type)}
                </span>
                <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                  {timeAgo(n.created_at)}
                </span>
              </div>
              <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 2 }}>{n.title}</div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                {n.body.length > 80 ? n.body.slice(0, 80) + '…' : n.body}
              </div>
            </GlassCard>
          ))}
        </div>
      )}

      {/* 详情弹窗 */}
      {detail && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
          padding: 16,
        }} onClick={() => setDetail(null)}>
          <GlassCard strong style={{ width: 520, maxWidth: '95vw', maxHeight: '85vh', overflow: 'auto' }}
            onClick={e => e.stopPropagation()}>
            {/* 头部 */}
            <div style={{
              display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16,
              paddingBottom: 12, borderBottom: '1px solid var(--divider)',
            }}>
              <span style={{ fontSize: 28 }}>{TYPE_ICON[detail.type] || '📌'}</span>
              <div style={{ flex: 1 }}>
                <div style={{
                  fontSize: 12, fontWeight: 500,
                  color: TYPE_COLOR[detail.type] || 'var(--accent)',
                }}>
                  {typeLabel(detail.type)}
                  {detail.is_read ? ' · 已读' : ''}
                </div>
                <div style={{ fontSize: 16, fontWeight: 600, marginTop: 2 }}>{detail.title}</div>
              </div>
              <button onClick={() => setDetail(null)}
                style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: 'var(--text-secondary)', padding: '4px 8px' }}>
                ✕
              </button>
            </div>

            {/* 正文 */}
            <div style={{
              fontSize: 14, color: 'var(--text-primary)', lineHeight: 1.7,
              marginBottom: 16, whiteSpace: 'pre-wrap',
            }}>
              {detail.body}
            </div>

            {/* 时间 */}
            <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginBottom: 16 }}>
              {fullTime(detail.created_at)}
            </div>

            {/* 操作按钮 */}
            {detail.record_id && HAS_RECORD_TYPES.has(detail.type) && (
              <button
                onClick={() => goToRecord(detail.record_id!)}
                className="glass-btn"
                style={{ width: '100%', padding: '10px 0', fontSize: 14 }}
              >
                📋 查看审批详情
              </button>
            )}
          </GlassCard>
        </div>
      )}
    </div>
  )
}
