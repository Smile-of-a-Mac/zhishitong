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
  const [detailUser, setDetailUser] = useState<User | null>(null)
  const [closing, setClosing] = useState(false)
  const [editForm, setEditForm] = useState({
    real_name: '', gender: '', phone: '', email: '',
    department: '', school: '',
    student_id: '', major: '', class_name: '', enrollment_year: '',
    advisor: '', employee_id: '', title: '',
    is_school_admin: false, is_dept_admin: false, is_finance_admin: false, is_active: true,
  })

  const closeDetail = () => {
    setClosing(true)
    setTimeout(() => { setDetailUser(null); setClosing(false) }, 250)
  }

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

  const openDetail = (u: User) => {
    setClosing(false)
    setDetailUser(u)
    setEditForm({
      real_name: u.real_name || '',
      gender: u.gender || '',
      phone: u.phone || '',
      email: u.email || '',
      department: u.department || '',
      school: u.school || '',
      student_id: u.student_id || '',
      major: u.major || '',
      class_name: u.class_name || '',
      enrollment_year: u.enrollment_year?.toString() || '',
      advisor: u.advisor || '',
      employee_id: u.employee_id || '',
      title: u.title || '',
      is_school_admin: !!u.is_school_admin,
      is_dept_admin: !!u.is_dept_admin,
      is_finance_admin: !!u.is_finance_admin,
      is_active: u.is_active,
    })
  }

  const saveDetail = async () => {
    if (!detailUser) return
    try {
      // enrollment_year 是整数，转换一下
      const payload = { ...editForm, enrollment_year: editForm.enrollment_year ? parseInt(editForm.enrollment_year, 10) : null }
      await axios.put(`/api/admin/members/${detailUser.id}`, payload)
      fetch()
      closeDetail()
    } catch (e: any) { alert(e?.response?.data?.detail || '更新失败') }
  }

  const disableMember = async () => {
    if (!detailUser) return
    if (!confirm(`确认禁用 ${detailUser.username}？禁用后无法登录。`)) return
    try {
      const res = await axios.put(`/api/admin/members/${detailUser.id}`, { is_active: false })
      setDetailUser(res.data)
      setEditForm(f => ({ ...f, is_active: false }))
      fetch()
    } catch (e: any) { alert(e?.response?.data?.detail || '禁用失败') }
  }

  const restoreMember = async () => {
    if (!detailUser) return
    try {
      await axios.put(`/api/admin/members/${detailUser.id}/restore`)
      const res = await axios.get(`/api/admin/members`)
      const u = res.data.find((x: User) => x.id === detailUser.id)
      if (u) { setDetailUser(u); setEditForm(f => ({ ...f, is_active: true })) }
      fetch()
    } catch (e: any) { alert(e?.response?.data?.detail || '恢复失败') }
  }

  const hardDeleteMember = async () => {
    if (!detailUser) return
    if (!confirm(`⚠️ 确认永久删除 ${detailUser.username}？此操作不可恢复！`)) return
    try {
      await axios.delete(`/api/admin/members/${detailUser.id}/hard`)
      setDetailUser(null)
      fetch()
    } catch (e: any) { alert(e?.response?.data?.detail || '删除失败') }
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
        <button onClick={() => fetch()} className="glass-btn glass-btn-outline glass-btn-sm">刷新</button>
        <span style={{ flex: 1 }} />
        <button onClick={() => setShowAdd(true)} className="glass-btn glass-btn-sm">
          添加成员
        </button>
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
            <button onClick={handleAdd} disabled={adding} className="glass-btn glass-btn-sm">{adding ? '添加中…' : '确认添加'}</button>
            <button onClick={() => setShowAdd(false)} className="glass-btn glass-btn-outline glass-btn-sm">取消</button>
          </div>
        </GlassCard>
      )}

      {loading ? <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-secondary)' }}>加载中...</div> : (
        <>
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
                      {u.is_admin ? '超级管理员' :
                       u.is_school_admin ? '学校管理员' :
                       u.is_dept_admin ? '部门管理员' :
                       u.is_finance_admin ? '财务管理员' :
                       '学生'}
                    </td>
                    <td>
                      <span className={u.is_active ? 'glass-tag glass-tag-green' : 'glass-tag glass-tag-red'}>
                        {u.is_active ? '正常' : '已禁用'}
                      </span>
                    </td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <button onClick={() => openDetail(u)}
                        className="glass-btn glass-btn-outline glass-btn-sm">查看详情</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </GlassCard>
        </>
      )}

      {/* 成员详情弹窗 */}
      {detailUser && (
        <div className={`modal-overlay${closing ? ' modal-closing' : ''}`}
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.35)', zIndex: 1000,
            display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}
          onClick={closeDetail}>
          <div className={`modal-card${closing ? ' modal-closing' : ''}`}
            style={{ maxWidth: 600, width: '100%', maxHeight: '90vh', overflowY: 'auto' }}
            onClick={e => e.stopPropagation()}>
            <GlassCard style={{ borderRadius: 22, padding: 24 }}>
            <div style={{ fontWeight: 700, fontSize: 18, marginBottom: 16, color: 'var(--text-primary)' }}>
              {detailUser.username}
              <span style={{ fontSize: 13, fontWeight: 400, color: 'var(--text-secondary)', marginLeft: 8 }}>
                {TIER_OPTIONS[detailUser.tier] || detailUser.tier}
              </span>
            </div>

            {/* 基本信息 */}
            <div className="responsive-form-grid" style={{ gap: 10, marginBottom: 16 }}>
              {[
                { label: '真实姓名', key: 'real_name', type: 'text' },
                { label: '性别', key: 'gender', type: 'text' },
                { label: '联系电话', key: 'phone', type: 'text' },
                { label: '电子邮箱', key: 'email', type: 'text' },
              ].map(f => (
                <div key={f.key}>
                  <label style={{ fontSize: 12, color: 'var(--text-secondary)', display: 'block', marginBottom: 2 }}>{f.label}</label>
                  <input value={(editForm as any)[f.key]} onChange={e => setEditForm(fm => ({ ...fm, [f.key]: e.target.value }))}
                    className="glass-input" style={{ padding: '6px 10px' }} />
                </div>
              ))}
              <div>
                <label style={{ fontSize: 12, color: 'var(--text-secondary)', display: 'block', marginBottom: 2 }}>所属学校</label>
                <select value={editForm.school} onChange={e => setEditForm(f => ({ ...f, school: e.target.value }))}
                  className="glass-input" style={{ padding: '6px 10px' }}>
                  {schools.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div>
                <label style={{ fontSize: 12, color: 'var(--text-secondary)', display: 'block', marginBottom: 2 }}>所属部门</label>
                <input value={editForm.department} onChange={e => setEditForm(f => ({ ...f, department: e.target.value }))}
                  className="glass-input" style={{ padding: '6px 10px' }} />
              </div>
            </div>

            {/* 学籍/工籍信息 */}
            <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 8, color: 'var(--text-primary)' }}>学籍 / 工籍信息</div>
            <div className="responsive-form-grid" style={{ gap: 10, marginBottom: 16 }}>
              {[
                { label: '学号', key: 'student_id' },
                { label: '专业', key: 'major' },
                { label: '班级', key: 'class_name' },
                { label: '入学年份', key: 'enrollment_year' },
                { label: '辅导员', key: 'advisor' },
                { label: '工号', key: 'employee_id' },
                { label: '职称', key: 'title' },
              ].map(f => (
                <div key={f.key}>
                  <label style={{ fontSize: 12, color: 'var(--text-secondary)', display: 'block', marginBottom: 2 }}>{f.label}</label>
                  <input value={(editForm as any)[f.key]} onChange={e => setEditForm(fm => ({ ...fm, [f.key]: e.target.value }))}
                    className="glass-input" style={{ padding: '6px 10px' }} />
                </div>
              ))}
            </div>

            {/* 角色 */}
            <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 8, color: 'var(--text-primary)' }}>角色权限</div>
            <div style={{ display: 'flex', gap: 16, fontSize: 13, marginBottom: 16, flexWrap: 'wrap' }}>
              {(['is_school_admin', 'is_dept_admin', 'is_finance_admin'] as const).map(role => (
                <label key={role} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, cursor: 'pointer' }}>
                  <input type="checkbox" checked={editForm[role]}
                    onChange={e => setEditForm(f => ({ ...f, [role]: e.target.checked }))} />
                  {ROLE_LABELS[role]}
                </label>
              ))}
            </div>

            <hr style={{ border: 'none', borderTop: '1px solid var(--divider)', marginBottom: 16 }} />

            {/* 操作按钮 */}
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <button onClick={saveDetail} className="glass-btn glass-btn-sm">💾 保存修改</button>
              <button onClick={() => resetPassword(detailUser.id, detailUser.username)}
                className="glass-btn glass-btn-outline glass-btn-sm">🔑 重置密码</button>
              {detailUser.is_active ? (
                <button onClick={disableMember} className="glass-btn glass-btn-danger glass-btn-sm">⛔ 禁用账号</button>
              ) : (
                <button onClick={restoreMember} className="glass-btn glass-btn-success glass-btn-sm">✅ 恢复账号</button>
              )}
              {!detailUser.is_active && (
                <button onClick={hardDeleteMember} className="glass-btn glass-btn-danger glass-btn-sm"
                  style={{ background: 'rgba(255,59,48,0.2)', border: '1px solid rgba(255,59,48,0.4)' }}>
                  🗑️ 永久删除
                </button>
              )}
              <span style={{ flex: 1 }} />
              <button onClick={closeDetail} className="glass-btn glass-btn-outline glass-btn-sm">关闭</button>
            </div>
          </GlassCard>
          </div>
        </div>
      )}
    </div>
  )
}
