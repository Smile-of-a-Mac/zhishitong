import React, { useEffect, useState } from 'react'
import axios from 'axios'
import GlassCard from '../../components/GlassCard'

interface Announcement {
  id: number; title: string; content: string; category: string;
  document_type: string | null; is_pinned: boolean; is_published: boolean;
  author_name: string; view_count: number;
  created_at: string; updated_at: string;
}

const categoryLabels: Record<string, string> = {
  announcement: '📢 公告',
  policy: '📜 制度',
  guide: '📖 指南',
}

export default function AnnouncementsPage() {
  const [items, setItems] = useState<Announcement[]>([])
  const [category, setCategory] = useState('')
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<Announcement | null>(null)

  const fetchList = async () => {
    setLoading(true)
    try {
      const res = await axios.get('/api/announcements', {
        params: category ? { category } : undefined,
      })
      setItems(res.data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchList() }, [category])

  const viewDetail = async (id: number) => {
    try {
      const res = await axios.get(`/api/announcements/${id}`)
      setSelected(res.data)
    } catch (e) { console.error(e) }
  }

  const timeFormat = (d: string) => {
    return new Date(d).toLocaleDateString('zh-CN')
  }

  if (loading) return <GlassCard style={{ padding: 30, textAlign: 'center', color: 'var(--text-secondary)' }}>加载中...</GlassCard>

  // 详情视图
  if (selected) {
    return (
      <div>
        <button className="glass-btn glass-btn-outline glass-btn-sm" onClick={() => setSelected(null)}
          style={{ marginBottom: 12 }}>
          ← 返回列表
        </button>
        <GlassCard strong style={{ padding: 20 }}>
          <div style={{ display: 'flex', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 8, background: 'var(--glass-bg-strong)' }}>
              {categoryLabels[selected.category] || selected.category}
            </span>
            {selected.document_type && (
              <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 8, background: 'var(--accent-color)' + '20', color: 'var(--accent-color)' }}>
                {selected.document_type}
              </span>
            )}
            {selected.is_pinned && (
              <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 8, background: '#FF950020', color: '#FF9500' }}>📌 置顶</span>
            )}
          </div>
          <h1 style={{ fontSize: 22, fontWeight: 700, margin: '12px 0' }}>{selected.title}</h1>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 16 }}>
            {selected.author_name} · {timeFormat(selected.created_at)} · 👁 {selected.view_count} 次阅读
          </div>
          <hr style={{ border: 'none', borderTop: '1px solid var(--divider)', margin: '16px 0' }} />
          <div style={{ fontSize: 15, lineHeight: 1.8, whiteSpace: 'pre-wrap', color: 'var(--text-primary)' }}>
            {selected.content}
          </div>
        </GlassCard>
      </div>
    )
  }

  // 列表视图
  return (
    <div>
      <h1 className="page-title">📢 公告 & 制度文库</h1>
      <GlassCard size="sm" style={{ marginBottom: 16 }}>
        {/* 分类筛选 */}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className={`glass-btn glass-btn-sm ${category === '' ? 'glass-btn-primary' : 'glass-btn-outline'}`}
            onClick={() => setCategory('')}>全部</button>
          <button className={`glass-btn glass-btn-sm ${category === 'announcement' ? 'glass-btn-primary' : 'glass-btn-outline'}`}
            onClick={() => setCategory('announcement')}>📢 公告</button>
          <button className={`glass-btn glass-btn-sm ${category === 'policy' ? 'glass-btn-primary' : 'glass-btn-outline'}`}
            onClick={() => setCategory('policy')}>📜 制度</button>
          <button className={`glass-btn glass-btn-sm ${category === 'guide' ? 'glass-btn-primary' : 'glass-btn-outline'}`}
            onClick={() => setCategory('guide')}>📖 指南</button>
        </div>
      </GlassCard>

      {items.length === 0 ? (
        <GlassCard style={{ padding: 40, textAlign: 'center', color: 'var(--text-secondary)' }}>
          暂无内容
        </GlassCard>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {items.map(a => (
            <GlassCard key={a.id} size="xs" onClick={() => viewDetail(a.id)}
              style={{ padding: 14, cursor: 'pointer' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                {a.is_pinned && <span style={{ fontSize: 14 }}>📌</span>}
                <span style={{ fontSize: 11, padding: '1px 6px', borderRadius: 6, background: 'var(--glass-bg-strong)', color: 'var(--text-secondary)' }}>
                  {categoryLabels[a.category] || a.category}
                </span>
                <span style={{ fontWeight: 600, fontSize: 14, flex: 1 }}>{a.title}</span>
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', display: 'flex', justifyContent: 'space-between' }}>
                <span>{a.author_name} · {timeFormat(a.created_at)}</span>
                <span>👁 {a.view_count}</span>
              </div>
            </GlassCard>
          ))}
        </div>
      )}
    </div>
  )
}
