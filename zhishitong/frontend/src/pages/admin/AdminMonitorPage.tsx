import React, { useEffect, useState } from 'react'
import axios from 'axios'
import GlassCard from '../../components/GlassCard'

// ===== 类型 =====
interface ServiceStatus {
  name: string
  status: 'ok' | 'degraded' | 'down'
  detail: string
  checked_at: string
}

interface SystemHealth {
  overall: string
  services: ServiceStatus[]
  uptime_seconds: number
  db_status: string
  disk_usage_percent: number | null
}

interface SystemStats {
  total_users: number
  active_users_today: number
  ocr_calls_today: number
  ocr_calls_by_tier: Record<string, number>
  approvals_today: number
  approvals_by_status: Record<string, number>
  errors_24h: number
  inference_uptime_percent: number
  redis_connected: boolean
  redis_version: string
  redis_memory_mb: number
  redis_clients: number
}

interface ErrorSummary {
  category: string
  message: string
  count: number
}

interface LogEntry {
  id: number | null
  timestamp: string
  category: string
  level: string
  message: string
  user_id: number | null
  record_id: number | null
  duration_ms: number | null
  error_trace: string | null
  extra: Record<string, any>
}

const CATEGORY_LABELS: Record<string, string> = {
  auth: '认证', ocr: 'OCR', approval: '审批', admin: '管理',
  system: '系统', inference: '推理',
}
const LEVEL_COLORS: Record<string, string> = {
  info: 'var(--accent)', warning: 'var(--orange)', error: 'var(--red)', critical: '#cf1322', debug: 'var(--text-tertiary)',
}
const STATUS_COLORS: Record<string, string> = { ok: 'var(--green)', degraded: 'var(--orange)', down: 'var(--red)' }
const STATUS_ICONS: Record<string, string> = { ok: '✓', degraded: '⚠', down: '✗' }

function formatUptime(s: number) {
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  const m = Math.floor((s % 3600) / 60)
  return d > 0 ? `${d}d ${h}h ${m}m` : `${h}h ${m}m`
}

export default function AdminMonitorPage() {
  const [health, setHealth] = useState<SystemHealth | null>(null)
  const [stats, setStats] = useState<SystemStats | null>(null)
  const [errors, setErrors] = useState<ErrorSummary[]>([])
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [logFilter, setLogFilter] = useState({ category: '', level: '' })
  const [tab, setTab] = useState<'overview' | 'logs' | 'errors'>('overview')

  const fetchAll = async () => {
    try {
      const [h, s, e, l] = await Promise.all([
        axios.get('/api/admin/monitor/health').then(r => r.data),
        axios.get('/api/admin/monitor/stats').then(r => r.data),
        axios.get('/api/admin/monitor/errors?hours=24').then(r => r.data),
        axios.get('/api/admin/monitor/logs?limit=50').then(r => r.data),
      ])
      setHealth(h); setStats(s); setErrors(e); setLogs(l)
    } catch (err) {
      console.error('Failed to fetch monitor data', err)
    }
  }

  const fetchLogs = async () => {
    const params = new URLSearchParams()
    if (logFilter.category) params.set('category', logFilter.category)
    if (logFilter.level) params.set('level', logFilter.level)
    params.set('limit', '100')
    const l = await axios.get(`/api/admin/monitor/logs?${params}`).then(r => r.data)
    setLogs(l)
  }

  useEffect(() => { fetchAll() }, [])
  useEffect(() => { fetchLogs() }, [logFilter])

  const overallColor = health?.overall === 'healthy' ? 'var(--green)' : health?.overall === 'degraded' ? 'var(--orange)' : 'var(--red)'
  const overallText = health?.overall === 'healthy' ? '健康' : health?.overall === 'degraded' ? '降级' : '严重'

  return (
    <div>
      <h1 className="page-title">🖥️ 系统监控</h1>

      {/* 标签切换 */}
      <GlassCard size="sm" style={{ marginBottom: 16, display: 'flex', gap: 8, alignItems: 'center', padding: '12px 16px' }}>
        {(['overview', 'logs', 'errors'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`glass-btn glass-btn-sm ${tab === t ? '' : 'glass-btn-outline'}`}
            style={{ fontWeight: tab === t ? 550 : 400 }}>
            {t === 'overview' ? '📊 概览' : t === 'logs' ? '📋 日志' : '❌ 错误'}
          </button>
        ))}
        <span style={{ flex: 1 }} />
        <button onClick={fetchAll} className="glass-btn glass-btn-outline glass-btn-sm">刷新</button>
      </GlassCard>

      {/* ===== 概览 ===== */}
      {tab === 'overview' && (
        <>
          {/* 总体状态横幅 */}
          {health && (
            <GlassCard size="sm" style={{
              marginBottom: 16, display: 'flex', alignItems: 'center', gap: 12,
              background: overallColor.replace(')', '15)').replace('var(', 'rgba(').replace('--green', '52,199,89').replace('--orange', '255,149,0').replace('--red', '255,59,48'),
            }}>
              <span style={{
                width: 12, height: 12, borderRadius: '50%', background: overallColor,
                display: 'inline-block',
              }} />
              <span style={{ fontWeight: 600, fontSize: 15 }}>系统状态: {overallText}</span>
              <span style={{ color: 'var(--text-secondary)', fontSize: 13, marginLeft: 'auto' }}>
                运行时间: {formatUptime(health.uptime_seconds)}
              </span>
              {health.disk_usage_percent !== null && (
                <span style={{ color: health.disk_usage_percent > 80 ? 'var(--red)' : 'var(--text-secondary)', fontSize: 13 }}>
                  磁盘: {health.disk_usage_percent}%
                </span>
              )}
            </GlassCard>
          )}

          {/* 服务卡片 */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 12, marginBottom: 16 }}>
            {health?.services.map(svc => (
              <GlassCard key={svc.name} size="sm">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: 13, fontWeight: 500 }}>{svc.name}</span>
                  <span style={{ color: STATUS_COLORS[svc.status], fontWeight: 600, fontSize: 13 }}>
                    {STATUS_ICONS[svc.status]} {svc.status === 'ok' ? '正常' : svc.status === 'degraded' ? '降级' : '宕机'}
                  </span>
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>{svc.detail}</div>
              </GlassCard>
            ))}
          </div>

          {/* 统计卡片 */}
          {stats && (
            <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))' }}>
              {[
                { label: '总用户', value: stats.total_users },
                { label: '今日新增', value: stats.active_users_today },
                { label: '今日 OCR', value: stats.ocr_calls_today },
                { label: '今日审批', value: stats.approvals_today },
                { label: '24h 错误', value: stats.errors_24h, warn: stats.errors_24h > 0 },
              ].map(card => (
                <GlassCard key={card.label} size="sm" className="stat-card">
                  <div className="stat-card-label">{card.label}</div>
                  <div className="stat-card-value" style={{ color: card.warn ? 'var(--red)' : 'var(--text-primary)' }}>
                    {card.value}
                  </div>
                </GlassCard>
              ))}
              {/* Redis 卡片 */}
              <GlassCard size="sm" className="stat-card">
                <div className="stat-card-label">Redis</div>
                <div className="stat-card-value" style={{ fontSize: 13, color: stats.redis_connected ? 'var(--green)' : 'var(--red)' }}>
                  {stats.redis_connected ? '已连接' : '未连接'}
                </div>
                {stats.redis_connected && (
                  <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>
                    v{stats.redis_version} · {stats.redis_memory_mb}MB · {stats.redis_clients} 连接
                  </div>
                )}
              </GlassCard>
            </div>
          )}

          {/* 按层级分布 */}
          {stats && (
            <div className="responsive-panel-grid">
              <GlassCard size="sm">
                <div className="section-title">OCR 调用分布（按层级）</div>
                {Object.entries(stats.ocr_calls_by_tier).map(([tier, cnt]) => (
                  <div key={tier} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontSize: 13 }}>
                    <span>{tier}</span>
                    <span style={{ fontWeight: 600 }}>{cnt}</span>
                  </div>
                ))}
              </GlassCard>
              <GlassCard size="sm">
                <div className="section-title">审批状态分布（今日）</div>
                {Object.entries(stats.approvals_by_status).map(([status, cnt]) => (
                  <div key={status} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontSize: 13 }}>
                    <span>{status}</span>
                    <span style={{ fontWeight: 600 }}>{cnt}</span>
                  </div>
                ))}
              </GlassCard>
            </div>
          )}
        </>
      )}

      {/* ===== 日志 ===== */}
      {tab === 'logs' && (
        <>
          {/* 筛选 */}
          <GlassCard size="sm" style={{ marginBottom: 12, display: 'flex', gap: 8 }}>
            <select value={logFilter.category} onChange={e => setLogFilter({ ...logFilter, category: e.target.value })}
              className="glass-input" style={{ width: 'auto', padding: '4px 8px' }}>
              <option value="">全部分类</option>
              {Object.entries(CATEGORY_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <select value={logFilter.level} onChange={e => setLogFilter({ ...logFilter, level: e.target.value })}
              className="glass-input" style={{ width: 'auto', padding: '4px 8px' }}>
              <option value="">全部级别</option>
              {['info', 'warning', 'error', 'critical'].map(l => <option key={l} value={l}>{l.toUpperCase()}</option>)}
            </select>
          </GlassCard>

          {/* 日志列表 */}
          <GlassCard size="sm" style={{ padding: 0, background: '#1e1e1e', fontFamily: 'monospace', fontSize: 12, maxHeight: 500, overflow: 'auto' }}>
            {logs.length === 0 ? (
              <div style={{ color: '#888', padding: '16px', textAlign: 'center' }}>暂无日志</div>
            ) : logs.map((l, i) => {
              const extraTags: string[] = []
              if (l.extra?.provider) extraTags.push(l.extra.provider)
              if (l.extra?.model) extraTags.push(l.extra.model)
              if (l.extra?.tier) extraTags.push(l.extra.tier)
              if (l.extra?.status) extraTags.push(String(l.extra.status))
              return (
              <div key={i} style={{
                padding: '3px 12px', borderBottom: '1px solid #333',
                display: 'flex', gap: 8, alignItems: 'flex-start',
              }}>
                <span style={{ color: '#888', whiteSpace: 'nowrap', minWidth: 140 }}>
                  {l.timestamp?.slice(11, 19) || '--:--:--'}
                </span>
                <span style={{
                  color: LEVEL_COLORS[l.level] || '#888', fontWeight: 600,
                  minWidth: 56, textAlign: 'center',
                }}>[{l.level.toUpperCase()}]</span>
                <span style={{ color: '#61afef', minWidth: 52 }}>
                  {CATEGORY_LABELS[l.category] || l.category}
                </span>
                <span style={{ color: '#abb2bf', flex: 1, wordBreak: 'break-all' }}>{l.message}</span>
                {extraTags.length > 0 && (
                  <span style={{ color: '#e5c07b', whiteSpace: 'nowrap', fontSize: 11 }}>
                    {extraTags.join(' · ')}
                  </span>
                )}
                {l.duration_ms !== null && (
                  <span style={{ color: '#888', whiteSpace: 'nowrap' }}>{l.duration_ms}ms</span>
                )}
              </div>
            )})}
          </GlassCard>
        </>
      )}

      {/* ===== 错误 ===== */}
      {tab === 'errors' && (
        <>
          {errors.length === 0 ? (
            <GlassCard style={{ textAlign: 'center', color: 'var(--green)', fontSize: 16, padding: 40 }}>
              ✅ 近 24 小时无错误，系统运行良好
            </GlassCard>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {errors.map((e, i) => (
                <GlassCard key={i} size="xs" style={{
                  display: 'flex', alignItems: 'center', gap: 12,
                  background: 'rgba(255,59,48,0.08)', border: '1px solid rgba(255,59,48,0.2)',
                }}>
                  <span style={{
                    background: 'var(--red)', color: '#fff', borderRadius: '50%',
                    width: 20, height: 20, display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 11, fontWeight: 700, flexShrink: 0,
                  }}>{e.count}</span>
                  <span className="glass-tag glass-tag-red">{CATEGORY_LABELS[e.category] || e.category}</span>
                  <span style={{ fontSize: 13, flex: 1 }}>{e.message}</span>
                </GlassCard>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
