import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import GlassCard from '../../components/GlassCard'
import { useAuth } from '../../hooks/useAuth'

interface TestSession {
  active: boolean
  overrides: Record<string, any>
  original: {
    username: string
    tier: string
    is_admin: boolean
    is_dept_admin: boolean
    is_school_admin: boolean
    is_finance_admin: boolean
    department: string | null
    school: string | null
  }
}

const PRESET_SCENARIOS = [
  { label: '👨‍🎓 学生 (Pro)', overrides: { tier: 'pro', is_admin: false, is_dept_admin: false, is_school_admin: false, is_finance_admin: false, department: '计算机学院', school: '山东科技大学' } },
  { label: '👨‍🏫 部门管理员', overrides: { tier: 'pro', is_admin: false, is_dept_admin: true, is_school_admin: false, is_finance_admin: false, department: '计算机学院', school: '山东科技大学' } },
  { label: '🏫 学校管理员', overrides: { tier: 'pro_plus', is_admin: false, is_dept_admin: false, is_school_admin: true, is_finance_admin: false, department: '', school: '山东科技大学' } },
  { label: '💰 财务管理员', overrides: { tier: 'pro_plus', is_admin: false, is_dept_admin: false, is_school_admin: false, is_finance_admin: true, department: '财务处', school: '山东科技大学' } },
  { label: '🆓 免费用户', overrides: { tier: 'free', is_admin: false, is_dept_admin: false, is_school_admin: false, is_finance_admin: false } },
  { label: '🧹 还原管理员', overrides: {}, reset: true },
]

export default function AdminTestPage() {
  const navigate = useNavigate()
  const { refreshUser } = useAuth()
  const [session, setSession] = useState<TestSession | null>(null)
  const [customTier, setCustomTier] = useState('')
  const [customDept, setCustomDept] = useState('')
  const [customSchool, setCustomSchool] = useState('')
  const [customIsAdmin, setCustomIsAdmin] = useState(false)
  const [customDeptAdmin, setCustomDeptAdmin] = useState(false)
  const [customSchoolAdmin, setCustomSchoolAdmin] = useState(false)
  const [customFinanceAdmin, setCustomFinanceAdmin] = useState(false)

  const fetchSession = async () => {
    try {
      const { data } = await axios.get('/api/admin/test-session')
      setSession(data)
    } catch {}
  }
  useEffect(() => { fetchSession() }, [])

  const applyOverrides = async (overrides: Record<string, any>, reset = false) => {
    try {
      await axios.post('/api/admin/test-session', { ...overrides, reset })
      await fetchSession()
      if (reset) {
        // 还原管理员：刷新上下文并跳转回管理员工作台
        await refreshUser()
        navigate('/admin/members')
      } else {
        alert('✅ 模拟已激活！刷新任意页面即可看到效果。\n\n返回工作台测试不同角色的功能。')
      }
    } catch (e: any) {
      alert('❌ ' + (e?.response?.data?.detail || '操作失败'))
    }
  }

  const applyCustom = () => {
    const overrides: Record<string, any> = {}
    if (customTier) overrides.tier = customTier
    if (customDept) overrides.department = customDept
    if (customSchool) overrides.school = customSchool
    overrides.is_admin = customIsAdmin
    overrides.is_dept_admin = customDeptAdmin
    overrides.is_school_admin = customSchoolAdmin
    overrides.is_finance_admin = customFinanceAdmin
    if (Object.keys(overrides).length === 0) {
      alert('请至少设置一个参数')
      return
    }
    applyOverrides(overrides)
  }

  const badge = (val: any) => {
    if (val === true) return <span className="glass-tag glass-tag-green">✓</span>
    if (val === false) return <span className="glass-tag glass-tag-red">✗</span>
    return <span style={{ color: 'var(--text-secondary)' }}>{val || '—'}</span>
  }

  return (
    <div>
      {/* 模拟激活时的醒告横幅 */}
      {session?.active && (
        <GlassCard size="xs" style={{
          marginBottom: 16,
          background: 'rgba(255,149,0,0.12)',
          border: '1px solid rgba(255,149,0,0.3)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8,
        }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--orange)' }}>
            ⚡ 当前正在模拟 {session.overrides.tier || session.original.tier} 身份
            {session.overrides.is_dept_admin ? ' · 部门管理员' : ''}
            {session.overrides.is_school_admin ? ' · 学校管理员' : ''}
            {session.overrides.is_finance_admin ? ' · 财务管理员' : ''}
            {!session.overrides.is_dept_admin && !session.overrides.is_school_admin && !session.overrides.is_finance_admin && session.overrides.is_admin === false ? ' · 普通用户' : ''}
          </span>
          <button onClick={async () => {
            await axios.delete('/api/admin/test-session')
            await refreshUser()   // 刷新真实身份
            navigate('/admin/members')  // 跳回管理员工作台
          }} className="glass-btn glass-btn-sm" style={{ background: 'var(--orange)', color: '#fff' }}>
            🚪 退出模拟
          </button>
        </GlassCard>
      )}

      <h1 className="page-title">🧪 模拟测试面板</h1>
      <p className="page-subtitle">管理员可临时切换角色/订阅/学校，无需反复登出登录。仅影响当前页面，不修改数据库。</p>

      {/* 当前状态 */}
      {session && (
        <GlassCard strong style={{ marginBottom: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <h2 className="section-title" style={{ margin: 0 }}>📌 当前身份</h2>
            {session.active && (
              <span className="glass-tag glass-tag-orange" style={{ fontSize: 13 }}>
                ⚡ 模拟中
              </span>
            )}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 8 }}>
            <div><span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>用户名</span><div style={{ fontWeight: 600 }}>{session.original.username}</div></div>
            <div><span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>订阅层级</span><div>{badge(session.active ? session.overrides.tier || session.original.tier : session.original.tier)}</div></div>
            <div><span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>系统管理员</span><div>{badge(session.active ? session.overrides.is_admin ?? session.original.is_admin : session.original.is_admin)}</div></div>
            <div><span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>部门管理员</span><div>{badge(session.active ? session.overrides.is_dept_admin ?? session.original.is_dept_admin : session.original.is_dept_admin)}</div></div>
            <div><span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>学校管理员</span><div>{badge(session.active ? session.overrides.is_school_admin ?? session.original.is_school_admin : session.original.is_school_admin)}</div></div>
            <div><span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>财务管理员</span><div>{badge(session.active ? session.overrides.is_finance_admin ?? session.original.is_finance_admin : session.original.is_finance_admin)}</div></div>
            <div><span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>学校</span><div>{badge(session.active ? session.overrides.school || session.original.school : session.original.school)}</div></div>
            <div><span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>部门</span><div>{badge(session.active ? session.overrides.department || session.original.department : session.original.department)}</div></div>
          </div>
        </GlassCard>
      )}

      {/* 快捷场景 */}
      <GlassCard strong style={{ marginBottom: 20 }}>
        <h2 className="section-title">🎭 快捷场景切换</h2>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {PRESET_SCENARIOS.map((s, i) => (
            <button key={i} onClick={() => applyOverrides(s.overrides, s.reset || false)}
              className={s.reset ? 'glass-btn glass-btn-outline glass-btn-sm' : 'glass-btn glass-btn-sm'}>
              {s.label}
            </button>
          ))}
        </div>
      </GlassCard>

      {/* 自定义参数 */}
      <GlassCard strong>
        <h2 className="section-title">⚙️ 自定义参数</h2>
        <div className="responsive-form-grid" style={{ gap: 8, maxWidth: 600 }}>
          <div>
            <label style={{ fontSize: 11, color: 'var(--text-secondary)', display: 'block', marginBottom: 2 }}>订阅层级</label>
            <select value={customTier} onChange={e => setCustomTier(e.target.value)} className="glass-input">
              <option value="">保持原样</option>
              <option value="free">free — 免费版</option>
              <option value="pro">pro — 专业版</option>
              <option value="pro_plus">pro_plus — 企业版</option>
            </select>
          </div>
          <div>
            <label style={{ fontSize: 11, color: 'var(--text-secondary)', display: 'block', marginBottom: 2 }}>学校</label>
            <input value={customSchool} onChange={e => setCustomSchool(e.target.value)}
              placeholder="如: 山东科技大学" className="glass-input" />
          </div>
          <div>
            <label style={{ fontSize: 11, color: 'var(--text-secondary)', display: 'block', marginBottom: 2 }}>部门</label>
            <input value={customDept} onChange={e => setCustomDept(e.target.value)}
              placeholder="如: 计算机学院" className="glass-input" />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, paddingTop: 4 }}>
            <label style={{ fontSize: 12 }}><input type="checkbox" checked={customIsAdmin} onChange={e => setCustomIsAdmin(e.target.checked)} /> 系统管理员</label>
            <label style={{ fontSize: 12 }}><input type="checkbox" checked={customDeptAdmin} onChange={e => setCustomDeptAdmin(e.target.checked)} /> 部门管理员</label>
            <label style={{ fontSize: 12 }}><input type="checkbox" checked={customSchoolAdmin} onChange={e => setCustomSchoolAdmin(e.target.checked)} /> 学校管理员</label>
            <label style={{ fontSize: 12 }}><input type="checkbox" checked={customFinanceAdmin} onChange={e => setCustomFinanceAdmin(e.target.checked)} /> 财务管理员</label>
          </div>
        </div>
        <button onClick={applyCustom} className="glass-btn" style={{ marginTop: 12 }}>✅ 应用自定义参数</button>
      </GlassCard>

      {/* 快速导航 */}
      <GlassCard style={{ marginTop: 20 }}>
        <h2 className="section-title">🔗 测试入口（模拟后点击跳转）</h2>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {[
            { to: '/', label: '🤖 智能审批' },
            { to: '/history', label: '📋 历史记录' },
            { to: '/dept', label: '📋 部门管理' },
            { to: '/school/affairs', label: '🏫 全校事务' },
            { to: '/finance', label: '💰 财务审批' },
            { to: '/dashboard', label: '📊 数据看板' },
            { to: '/admin/monitor', label: '🖥️ 系统监控' },
            { to: '/admin/api-keys', label: '🔑 API Key' },
          ].map(item => (
            <a key={item.to} href={item.to}
              className="glass-btn glass-btn-outline glass-btn-sm"
              style={{ textDecoration: 'none' }}>
              {item.label}
            </a>
          ))}
        </div>
      </GlassCard>
    </div>
  )
}
