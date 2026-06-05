import React, { useEffect, useState } from 'react'
import axios from 'axios'
import { getDocTypeLabel } from '../../constants/docTypes'
import GlassCard from '../../components/GlassCard'

export default function AdminDataPage() {
  const [records, setRecords] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [filter, setFilter] = useState({ status: '', username: '', school: '', page: 1 })
  const [loading, setLoading] = useState(true)

  const doFetch = async (f: { page: number; status: string; username: string; school: string }) => {
    setLoading(true)
    const params: any = { page: f.page, page_size: 20 }
    if (f.status) params.status = f.status
    if (f.username) params.username = f.username
    if (f.school) params.school = f.school
    try {
      const res = await axios.get('/api/admin/data', { params })
      setRecords(res.data.items); setTotal(res.data.total)
    } catch {} finally { setLoading(false) }
  }

  useEffect(() => { doFetch(filter) }, [filter.page])

  const restore = async (id: number) => { await axios.put(`/api/admin/data/${id}/restore`); doFetch(filter) }
  const hardDelete = async (id: number) => {
    if (!confirm('⚠️ 彻底删除不可恢复！确认？')) return
    await axios.delete(`/api/admin/data/${id}`); doFetch(filter)
  }

  return (
    <div>
      <h1 className="page-title">📊 数据管理</h1>
      <GlassCard strong>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
          <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-secondary)' }}>筛选：</span>
          <select value={filter.status} onChange={e => setFilter(f => ({ ...f, status: e.target.value }))}
            className="glass-input" style={{ width: 'auto', padding: '4px 8px' }}>
            <option value="">全部状态</option><option value="active">正常</option><option value="deleted">已删除</option>
          </select>
          <input placeholder="用户名搜索" value={filter.username}
            onChange={e => setFilter(f => ({ ...f, username: e.target.value }))}
            className="glass-input" style={{ width: 140, padding: '4px 8px' }} />
          <select value={filter.school} onChange={e => setFilter(f => ({ ...f, school: e.target.value }))}
            className="glass-input" style={{ width: 'auto', padding: '4px 8px' }}>
            <option value="">全部学校</option>
            <option value="山东科技大学">山东科技大学</option>
            <option value="山东科技大学（济南校区）">山东科技大学（济南校区）</option>
          </select>
          <button onClick={() => {
              const newFilter = { ...filter, page: 1 };
              setFilter(newFilter);
              doFetch(newFilter);
            }}
            className="glass-btn glass-btn-sm">查询</button>
          <span style={{ marginLeft: 'auto', fontSize: 13, color: 'var(--text-secondary)' }}>共 {total} 条</span>
        </div>
        {loading ? <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-secondary)' }}>加载中...</div> :
         records.length === 0 ? <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-secondary)' }}>暂无数据</div> : (
          <div className="glass-table-wrapper">
            <table className="glass-table">
              <thead><tr>
                <th>用户</th>
                <th>文件名</th>
                <th>类型</th>
                <th>状态</th>
                <th>删除标记</th>
                <th>时间</th>
                <th>操作</th>
              </tr></thead>
              <tbody>
                {records.map(r => (
                  <tr key={r.id}>
                    <td>{r.username}</td>
                    <td style={{ maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.original_filename || '—'}</td>
                    <td>{getDocTypeLabel(r.document_type)}</td>
                    <td>{r.status}</td>
                    <td>{r.is_deleted ? <span style={{ color: 'var(--orange)' }}>🗑 {r.deleted_by}</span> : '—'}</td>
                    <td style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>{new Date(r.created_at).toLocaleDateString('zh-CN')}</td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      {r.is_deleted && <button onClick={() => restore(r.id)} className="glass-btn glass-btn-success glass-btn-sm" style={{ marginRight: 4 }}>恢复</button>}
                      <button onClick={() => hardDelete(r.id)} className="glass-btn glass-btn-danger glass-btn-sm">彻底删除</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div style={{ marginTop: 12, display: 'flex', justifyContent: 'center', gap: 8, alignItems: 'center' }}>
          <button disabled={filter.page <= 1} onClick={() => setFilter(f => ({ ...f, page: f.page - 1 }))}
            className="glass-btn glass-btn-outline glass-btn-sm">上一页</button>
          <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{filter.page}</span>
          <button disabled={filter.page * 20 >= total} onClick={() => setFilter(f => ({ ...f, page: f.page + 1 }))}
            className="glass-btn glass-btn-outline glass-btn-sm">下一页</button>
        </div>
      </GlassCard>
      <GlassCard size="xs" style={{ marginTop: 12, background: 'rgba(255,149,0,0.08)', border: '1px solid rgba(255,149,0,0.2)' }}>
        ⚠️ 彻底删除将永久移除文件及数据，不可恢复
      </GlassCard>
    </div>
  )
}
