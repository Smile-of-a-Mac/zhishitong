import React, { useEffect, useState } from 'react'
import axios from 'axios'
import type { User } from '../../hooks/useAuth'
import GlassCard from '../../components/GlassCard'

export default function SchoolAdminPage() {
  const [deptAdmins, setDeptAdmins] = useState<User[]>([])
  const [showAdd, setShowAdd] = useState(false)
  const [newUsername, setNewUsername] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newDept, setNewDept] = useState('')
  const [editId, setEditId] = useState<number | null>(null)
  const [editDept, setEditDept] = useState('')
  const [editActive, setEditActive] = useState(true)

  const fetch = async () => {
    try {
      const res = await axios.get('/api/admin/dept-admins')
      setDeptAdmins(res.data)
    } catch {}
  }
  useEffect(() => { fetch() }, [])

  const create = async () => {
    if (!newUsername.trim() || !newPassword.trim() || !newDept.trim()) {
      alert('请填写完整信息'); return
    }
    try {
      await axios.post('/api/admin/dept-admins', {
        username: newUsername, password: newPassword, department: newDept,
      })
      setShowAdd(false); setNewUsername(''); setNewPassword(''); setNewDept('')
      fetch()
    } catch (e: any) {
      alert(e?.response?.data?.detail || '创建失败')
    }
  }

  const saveEdit = async (id: number) => {
    try {
      await axios.put(`/api/admin/dept-admins/${id}`, {
        department: editDept, is_active: editActive,
      })
      setEditId(null); fetch()
    } catch (e: any) {
      alert(e?.response?.data?.detail || '更新失败')
    }
  }

  const remove = async (id: number, username: string) => {
    if (!confirm(`确认删除部门管理员「${username}」？`)) return
    try {
      await axios.delete(`/api/admin/dept-admins/${id}`)
      fetch()
    } catch (e: any) {
      alert(e?.response?.data?.detail || '删除失败')
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h1 className="page-title" style={{ margin: 0 }}>🏫 部门管理员管理</h1>
        <button onClick={() => { setShowAdd(!showAdd); setEditId(null) }}
          className="glass-btn">+ 新建管理员</button>
      </div>

      <GlassCard size="xs" style={{ marginBottom: 16, background: 'rgba(0,122,255,0.08)', border: '1px solid rgba(0,122,255,0.2)' }}>
        💡 部门管理员负责审批本部门事务，他们不能提交审批请求。创建后即可登录使用。
      </GlassCard>

      {/* 新建表单 */}
      {showAdd && (
        <GlassCard strong style={{ marginBottom: 16 }}>
          <h3 style={{ margin: '0 0 12px', fontSize: 15 }}>新建部门管理员</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr auto', gap: 8, alignItems: 'end' }}>
            <div>
              <label style={{ display: 'block', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 2 }}>用户名</label>
              <input value={newUsername} onChange={e => setNewUsername(e.target.value)} placeholder="例如: dept_cs"
                className="glass-input" />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 2 }}>密码</label>
              <input value={newPassword} onChange={e => setNewPassword(e.target.value)} placeholder="至少 6 位"
                className="glass-input" />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 2 }}>所属部门</label>
              <input value={newDept} onChange={e => setNewDept(e.target.value)} placeholder="如: 计算机学院"
                className="glass-input" />
            </div>
            <div>
              <button onClick={create} className="glass-btn glass-btn-success" style={{ marginRight: 6 }}>创建</button>
              <button onClick={() => setShowAdd(false)} className="glass-btn glass-btn-outline">取消</button>
            </div>
          </div>
        </GlassCard>
      )}

      {/* 列表 */}
      <GlassCard strong className="glass-table-wrapper" style={{ padding: 0 }}>
        <table className="glass-table">
          <thead><tr>
            <th>用户名</th>
            <th>部门</th>
            <th>状态</th>
            <th>创建时间</th>
            <th>操作</th>
          </tr></thead>
          <tbody>
            {deptAdmins.length === 0 ? (
              <tr><td colSpan={5} style={{ padding: 24, textAlign: 'center', color: 'var(--text-secondary)' }}>暂无部门管理员</td></tr>
            ) : (
              deptAdmins.map(d => (
                <tr key={d.id}>
                  <td>{d.username}</td>
                  <td>
                    {editId === d.id ? (
                      <input value={editDept} onChange={e => setEditDept(e.target.value)}
                        className="glass-input" style={{ width: 120, padding: '4px 8px', display: 'inline-block' }} />
                    ) : (d.department || '—')}
                  </td>
                  <td>
                    {editId === d.id ? (
                      <select value={editActive ? 'true' : 'false'} onChange={e => setEditActive(e.target.value === 'true')}
                        className="glass-input" style={{ width: 'auto', padding: '4px 8px', display: 'inline-block' }}>
                        <option value="true">启用</option>
                        <option value="false">停用</option>
                      </select>
                    ) : (
                      <span className={d.is_active ? 'glass-tag glass-tag-green' : 'glass-tag glass-tag-red'}>
                        {d.is_active ? '🟢 正常' : '🔴 停用'}
                      </span>
                    )}
                  </td>
                  <td style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                    {(d as any).created_at ? new Date((d as any).created_at).toLocaleDateString('zh-CN') : '—'}
                  </td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    {editId === d.id ? (
                      <>
                        <button onClick={() => saveEdit(d.id)} className="glass-btn glass-btn-sm" style={{ marginRight: 4 }}>保存</button>
                        <button onClick={() => setEditId(null)} className="glass-btn glass-btn-outline glass-btn-sm">取消</button>
                      </>
                    ) : (
                      <>
                        <button onClick={() => { setEditId(d.id); setEditDept(d.department || ''); setEditActive(d.is_active) }}
                          className="glass-btn glass-btn-outline glass-btn-sm" style={{ marginRight: 4 }}>编辑</button>
                        <button onClick={() => remove(d.id, d.username)}
                          className="glass-btn glass-btn-danger glass-btn-sm">删除</button>
                      </>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </GlassCard>
    </div>
  )
}
