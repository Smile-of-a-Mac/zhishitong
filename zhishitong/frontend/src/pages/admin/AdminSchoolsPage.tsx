import React, { useEffect, useState } from 'react'
import axios from 'axios'
import GlassCard from '../../components/GlassCard'

interface SchoolInfo {
  school: string
  tier: string
  user_count: number
}

const TIER_OPTIONS: Record<string, string> = { free: '免费版', pro: '专业版' }

export default function AdminSchoolsPage() {
  const [schools, setSchools] = useState<SchoolInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [changing, setChanging] = useState<{ school: string; tier: string } | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [newSchool, setNewSchool] = useState({ name: '', tier: 'free' })
  const [creating, setCreating] = useState(false)
  const [createResult, setCreateResult] = useState<any>(null)

  const fetch = async () => {
    setLoading(true)
    try {
      const res = await axios.get('/api/admin/schools')
      setSchools(res.data)
    } catch {} finally { setLoading(false) }
  }

  useEffect(() => { fetch() }, [])

  const changeTier = async (school: string, tier: string) => {
    if (!confirm(`确认将「${school}」切换为 ${TIER_OPTIONS[tier]}？\n此操作将影响该校所有用户。`)) return
    setChanging({ school, tier })
    try {
      await axios.put(`/api/admin/schools/${encodeURIComponent(school)}/tier`, { tier })
      fetch()
    } catch (e: any) {
      alert(e?.response?.data?.detail || '操作失败')
    } finally { setChanging(null) }
  }

  const handleCreate = async () => {
    if (!newSchool.name.trim()) { alert('请输入学校名称'); return }
    setCreating(true)
    setCreateResult(null)
    try {
      const res = await axios.post('/api/admin/schools', newSchool)
      setCreateResult(res.data)
      setNewSchool({ name: '', tier: 'free' })
      fetch()
    } catch (e: any) { alert(e?.response?.data?.detail || '操作失败') }
    finally { setCreating(false) }
  }

  return (
    <div>
      <h1 className="page-title">🏫 学校管理</h1>
      <p className="page-subtitle">管理各学校的服务等级，切换等级将影响该校全体用户</p>

      <GlassCard size="sm" style={{ marginBottom: 12, display: 'flex', gap: 8, alignItems: 'center' }}>
        <button onClick={() => setShowCreate(!showCreate)} className="glass-btn glass-btn-sm">
          {showCreate ? '取消创建' : '➕ 创建学校'}
        </button>
        <button onClick={() => fetch()} className="glass-btn glass-btn-outline glass-btn-sm">🔄 刷新</button>
      </GlassCard>

      {/* 创建学校表单 */}
      {showCreate && (
        <GlassCard size="sm" style={{ marginBottom: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>创建新学校</div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <input placeholder="学校名称（如：华南理工大学）" value={newSchool.name}
              onChange={e => setNewSchool(s => ({ ...s, name: e.target.value }))}
              className="glass-input" style={{ flex: 1, minWidth: 200, padding: '6px 10px' }} />
            <select value={newSchool.tier} onChange={e => setNewSchool(s => ({ ...s, tier: e.target.value }))}
              className="glass-input" style={{ width: 'auto', padding: '6px 10px' }}>
              <option value="free">免费版</option>
              <option value="pro">专业版</option>
            </select>
            <button onClick={handleCreate} disabled={creating}
              className="glass-btn glass-btn-sm">{creating ? '创建中...' : '确认创建'}</button>
          </div>
          {createResult && (
            <GlassCard size="xs" style={{ marginTop: 8, background: 'rgba(52,199,89,0.08)', border: '1px solid rgba(52,199,89,0.2)' }}>
              <div style={{ fontWeight: 600, color: 'var(--green)', marginBottom: 4 }}>✅ {createResult.detail}</div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                已自动创建以下管理员账户：
                {createResult.accounts?.map((a: any) => (
                  <div key={a.username} style={{ marginTop: 2 }}>
                    • {a.username} / {a.password} — {a.role}
                  </div>
                ))}
              </div>
            </GlassCard>
          )}
        </GlassCard>
      )}

      {loading ? <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-secondary)' }}>加载中...</div> : (
        <GlassCard strong className="glass-table-wrapper" style={{ padding: 0 }}>
          <table className="glass-table">
            <thead><tr>
              <th>学校</th>
              <th>服务等级</th>
              <th>用户数</th>
              <th>操作</th>
            </tr></thead>
            <tbody>
              {schools.length === 0 ? (
                <tr><td colSpan={4} style={{ textAlign: 'center', color: 'var(--text-secondary)' }}>暂无学校数据</td></tr>
              ) : schools.map(s => (
                <tr key={s.school}>
                  <td style={{ fontWeight: 600 }}>{s.school}</td>
                  <td>
                    <span className={s.tier === 'pro' ? 'glass-tag glass-tag-green' : 'glass-tag'}>
                      {TIER_OPTIONS[s.tier] || s.tier}
                    </span>
                  </td>
                  <td>{s.user_count} 人</td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <button
                      onClick={() => changeTier(s.school, 'pro')}
                      disabled={s.tier === 'pro' || (changing?.school === s.school && changing?.tier === 'pro')}
                      className="glass-btn glass-btn-sm"
                      style={{ marginRight: 4, opacity: s.tier === 'pro' ? 0.5 : 1 }}
                    >升级 Pro</button>
                    <button
                      onClick={() => changeTier(s.school, 'free')}
                      disabled={s.tier === 'free' || (changing?.school === s.school && changing?.tier === 'free')}
                      className="glass-btn glass-btn-outline glass-btn-sm"
                      style={{ opacity: s.tier === 'free' ? 0.5 : 1 }}
                    >降级 Free</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </GlassCard>
      )}
    </div>
  )
}
