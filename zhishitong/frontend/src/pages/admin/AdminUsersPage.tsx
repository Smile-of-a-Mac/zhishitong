import React, { useEffect, useState } from 'react'
import axios from 'axios'
import type { User } from '../../hooks/useAuth'
import GlassCard from '../../components/GlassCard'

const ROLE_LABELS: Record<string, string> = {
  is_school_admin: '学校管理员',
  is_dept_admin: '部门管理员',
  is_finance_admin: '财务管理员',
}

const TIER_OPTIONS: Record<string, string> = { free: '免费版', pro: '专业版' }

export default function AdminUsersPage() {
  const [users, setUsers] = useState<User[]>([])
  const [schools, setSchools] = useState<string[]>([])
  const [schoolFilter, setSchoolFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [addForm, setAddForm] = useState({ username: '', password: '', real_name: '', school: '', department: '',
    is_school_admin: false, is_dept_admin: false, is_finance_admin: false })
  const [adding, setAdding] = useState(false)

  const fetch = async () => {
    setLoading(true)
    try {
      const params: any = {}
      if (schoolFilter) params.school = schoolFilter
      const [usersRes, schoolsRes] = await Promise.all([
        axios.get('/api/admin/members', { params }),
        axios.get('/api/admin/schools'),
      ])
      setUsers(usersRes.data)
      setSchools(schoolsRes.data.map((s: any) => s.school))
    } catch {} finally { setLoading(false) }
  }

  useEffect(() => { fetch() }, [schoolFilter])

  const deleteMember = async (id: number, username: string) => {
    if (!confirm(`确认禁用账号 ${username}？禁用后该用户将无法登录。`)) return
    try {
      await axios.delete(`/api/admin/members/${id}`)
      fetch()
    } catch (e: any) { alert(e?.response?.data?.detail || '操作失败') }
  }

  const resetPassword = async (id: number, username: string) => {
    const newPwd = prompt(`请输入 ${username} 的新密码（至少 6 位）：`)
    if (!newPwd) return
    if (newPwd.length < 6) { alert('密码至少 6 位'); return }
    try {
      await axios.put(`/api/admin/members/${id}/reset-password`, { new_password: newPwd })
      alert(`已重置 ${username} 的密码`)
    } catch (e: any) { alert(e?.response?.data?.detail || '操作失败') }
  }

  const restoreMember = async (id: number) => {
    try {
      await axios.put(`/api/admin/members/${id}/restore`)
      fetch()
    } catch (e: any) { alert(e?.response?.data?.detail || '操作失败') }
  }

  const toggleRole = async (id: number, role: string, current: boolean) => {
    try {
      await axios.put(`/api/admin/members/${id}/roles`, { [role]: !current })
      fetch()
    } catch (e: any) { alert(e?.response?.data?.detail || '操作失败') }
  }

  const handleAdd = async () => {
    if (!addForm.username.trim() || !addForm.password || !addForm.school) {
      alert('请填写用户名、密码和学校'); return
    }
    setAdding(true)
    try {
      await axios.post('/api/admin/members', addForm)
      setShowAdd(false)
      setAddForm({ username: '', password: '', real_name: '', school: '', department: '',
        is_school_admin: false, is_dept_admin: false, is_finance_admin: false })
      fetch()
    } catch (e: any) { alert(e?.response?.data?.detail || '操作失败') }
    finally { setAdding(false) }
  }

  return (
    <div>
      <h1 className="page-title">👥 成员管理</h1>

      <GlassCard size="sm" style={{ marginBottom: 12, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-secondary)' }}>学校：</span>
        <select value={schoolFilter} onChange={e => setSchoolFilter(e.target.value)}
          className="glass-input" style={{ width: 'auto', padding: '4px 8px' }}>
          <option value="">全部学校</option>
          {schools.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <button onClick={() => fetch()} className="glass-btn glass-btn-outline glass-btn-sm">🔄 刷新</button>
        <button onClick={() => setShowAdd(true)} className="glass-btn glass-btn-sm" style={{ marginLeft: 'auto' }}>➕ 添加成员</button>
      </GlassCard>

      {/* 添加成员表单 */}
      {showAdd && (
        <GlassCard size="sm" style={{ marginBottom: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ fontWeight: 600, fontSize: 14 }}>添加新成员</div>
          <div className="responsive-form-grid" style={{ gap: 8 }}>
            <input placeholder="用户名 *" value={addForm.username} onChange={e => setAddForm(f => ({ ...f, username: e.target.value }))}
              className="glass-input" style={{ padding: '6px 10px' }} />
            <input type="password" placeholder="密码 *" value={addForm.password} onChange={e => setAddForm(f => ({ ...f, password: e.target.value }))}
              className="glass-input" style={{ padding: '6px 10px' }} />
            <input placeholder="真实姓名" value={addForm.real_name} onChange={e => setAddForm(f => ({ ...f, real_name: e.target.value }))}
              className="glass-input" style={{ padding: '6px 10px' }} />
            <select value={addForm.school} onChange={e => setAddForm(f => ({ ...f, school: e.target.value }))}
              className="glass-input" style={{ padding: '6px 10px' }}>
              <option value="">选择学校 *</option>
              {schools.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <input placeholder="部门（如计算机学院）" value={addForm.department} onChange={e => setAddForm(f => ({ ...f, department: e.target.value }))}
              className="glass-input" style={{ padding: '6px 10px' }} />
          </div>
          <div style={{ display: 'flex', gap: 12, fontSize: 13 }}>
            <label><input type="checkbox" checked={addForm.is_school_admin} onChange={e => setAddForm(f => ({ ...f, is_school_admin: e.target.checked }))} /> 学校管理员</label>
            <label><input type="checkbox" checked={addForm.is_dept_admin} onChange={e => setAddForm(f => ({ ...f, is_dept_admin: e.target.checked }))} /> 部门管理员</label>
            <label><input type="checkbox" checked={addForm.is_finance_admin} onChange={e => setAddForm(f => ({ ...f, is_finance_admin: e.target.checked }))} /> 财务管理员</label>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={handleAdd} disabled={adding} className="glass-btn glass-btn-sm">{adding ? '添加中...' : '确认添加'}</button>
            <button onClick={() => setShowAdd(false)} className="glass-btn glass-btn-outline glass-btn-sm">取消</button>
          </div>
        </GlassCard>
      )}

      {loading ? <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-secondary)' }}>加载中...</div> : (
        <GlassCard strong className="glass-table-wrapper" style={{ padding: 0 }}>
          <table className="glass-table" style={{ fontSize: 14 }}>
            <thead><tr>
              <th>用户名</th>
              <th>真实姓名</th>
              <th>学校</th>
              <th>部门</th>
              <th>层级</th>
              <th>角色</th>
              <th>状态</th>
              <th>操作</th>
            </tr></thead>
            <tbody>
              {users.length === 0 ? (
                <tr><td colSpan={8} style={{ textAlign: 'center', color: 'var(--text-secondary)' }}>暂无成员</td></tr>
              ) : users.map(u => (
                <tr key={u.id}>
                  <td>{u.username}</td>
                  <td>{u.real_name || '—'}</td>
                  <td style={{ fontSize: 12 }}>{u.school || '—'}</td>
                  <td style={{ fontSize: 12 }}>{u.department || '—'}</td>
                  <td>{TIER_OPTIONS[u.tier] || u.tier}</td>
                  <td style={{ fontSize: 12 }}>
                    {(['is_school_admin', 'is_dept_admin', 'is_finance_admin'] as const).map(role => (
                      <label key={role} style={{ display: 'inline-flex', alignItems: 'center', gap: 2, marginRight: 6, cursor: 'pointer' }}
                        onClick={() => toggleRole(u.id, role, !!u[role])}>
                        <input type="checkbox" checked={!!u[role]} readOnly />
                        {ROLE_LABELS[role]}
                      </label>
                    ))}
                  </td>
                  <td>
                    <span className={u.is_active ? 'glass-tag glass-tag-green' : 'glass-tag glass-tag-red'}>
                      {u.is_active ? '正常' : '已禁用'}
                    </span>
                  </td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <button onClick={() => resetPassword(u.id, u.username)}
                      className="glass-btn glass-btn-outline glass-btn-sm" style={{ marginRight: 4 }}>重置密码</button>
                    {u.is_active ? (
                      <button onClick={() => deleteMember(u.id, u.username)}
                        className="glass-btn glass-btn-danger glass-btn-sm">禁用</button>
                    ) : (
                      <button onClick={() => restoreMember(u.id)}
                        className="glass-btn glass-btn-sm">恢复</button>
                    )}
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
