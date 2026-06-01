import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import axios from 'axios'
import { useAuth } from '../hooks/useAuth'

type NavItem = { to: string; label: string }
type NavSection = { header?: string; items: NavItem[]; previewCount?: number; collapsed?: boolean; onToggle?: () => void }

const APPLY_NAV: NavItem[] = [
  { to: '/apply/reimbursement', label: '💰 报销申请' },
  { to: '/apply/leave', label: '📝 请假申请' },
  { to: '/apply/club_application', label: '🎉 社团活动申请' },
  { to: '/apply/scholarship', label: '🏆 奖学金申请' },
  { to: '/apply/suspend_resume', label: '🎓 休学/复学' },
  { to: '/apply/enrollment_proof', label: '📄 在读证明' },
  { to: '/apply/diploma_verification', label: '📜 学历学位证明' },
  { to: '/apply/transcript_print', label: '📜 成绩单打印' },
  { to: '/apply/class_reschedule', label: '🔀 调停课申请' },
  { to: '/apply/makeup_exam', label: '📝 缓考/补考' },
  { to: '/apply/exam_review', label: '📋 试卷查阅' },
  { to: '/apply/classroom_booking', label: '🏫 教室借用' },
  { to: '/apply/dorm_change', label: '🏠 宿舍调换' },
  { to: '/apply/seal_application', label: '🔖 用章申请' },
]

const TOOL_NAV: NavItem[] = [
  { to: '/history', label: '📋 历史记录' },
  { to: '/resources', label: '📅 资源预约' },
]

const COMMUNITY_NAV: NavItem[] = [
  { to: '/announcements', label: '📢 公告制度' },
  { to: '/notifications', label: '🔔 消息通知' },
]

const ADMIN_NAV: NavItem[] = [
  { to: '/admin/test', label: '🧪 模拟测试' },
  { to: '/admin/api-keys', label: '🔑 API Key' },
  { to: '/admin/schools', label: '🏫 学校管理' },
  { to: '/admin/members', label: '👥 成员管理' },
  { to: '/admin/monitor', label: '🖥️ 系统监控' },
  { to: '/admin/data', label: '📊 数据管理' },
]

const DEPT_NAV: NavItem[] = [
  { to: '/dept', label: '📋 部门事务' },
  { to: '/dashboard', label: '📊 数据看板' },
]

const SCHOOL_NAV: NavItem[] = [
  { to: '/school/affairs', label: '📋 全校事务' },
  { to: '/dashboard', label: '📊 数据看板' },
]

function NavLink({ to, label, currentPath, onClick, favorite, onToggleFavorite }: {
  to: string
  label: string
  currentPath: string
  onClick?: () => void
  favorite?: boolean
  onToggleFavorite?: () => void
}) {
  const isActive = currentPath === to || (to !== '/profile' && to !== '/' && currentPath.startsWith(to))
  return (
    <Link
      to={to}
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        textDecoration: 'none',
        fontSize: 14,
        fontWeight: isActive ? 600 : 400,
        color: isActive ? 'var(--accent)' : 'var(--text-primary)',
        padding: '10px 14px 10px 12px',
        borderRadius: 10,
        borderLeft: `3px solid ${isActive ? 'var(--accent)' : 'transparent'}`,
        background: isActive ? 'rgba(0,122,255,0.08)' : 'transparent',
        transition: 'background 0.15s ease, color 0.15s ease',
        marginBottom: 2,
        WebkitUserSelect: 'none',
        userSelect: 'none',
      } as React.CSSProperties}
      onMouseEnter={e => { if (!isActive) (e.currentTarget as HTMLElement).style.background = 'rgba(128,128,128,0.07)' }}
      onMouseLeave={e => { if (!isActive) (e.currentTarget as HTMLElement).style.background = 'transparent' }}
    >
      <span style={{ flex: 1, minWidth: 0 }}>{label}</span>
      {onToggleFavorite && (
        <button
          type="button"
          aria-label={favorite ? '取消收藏' : '收藏'}
          onClick={e => { e.preventDefault(); e.stopPropagation(); onToggleFavorite() }}
          style={{
            border: 'none', background: 'transparent', color: favorite ? 'var(--orange)' : 'var(--text-tertiary)',
            cursor: 'pointer', padding: '2px 0 2px 6px', fontSize: 14, lineHeight: 1,
          }}
        >
          {favorite ? '★' : '☆'}
        </button>
      )}
    </Link>
  )
}

export default function Frame({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth()
  const loc = useLocation()
  const nav = useNavigate()

  // ── 移动端侧边栏开关 ──
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(false)
  const [favoriteApplyPaths, setFavoriteApplyPaths] = useState<string[]>([])
  const [allApplyOpen, setAllApplyOpen] = useState(true)
  const [applyMoreAnimating, setApplyMoreAnimating] = useState(false)
  // 点击导航后自动关闭（移动端）
  const closeSidebar = () => setSidebarOpen(false)

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 1024px)')
    setIsMobile(mq.matches)
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

  const allApplyOpenKey = user?.id ? `zhishitong_apply_all_open_${user.id}` : ''
  useEffect(() => {
    if (!user?.id) {
      setFavoriteApplyPaths([])
      return
    }
    let cancelled = false
    axios.get('/api/user/preferences/favorites')
      .then(res => {
        if (cancelled) return
        const favorites = Array.isArray(res.data?.favorites) ? res.data.favorites : []
        setFavoriteApplyPaths(favorites.filter((v: unknown): v is string => typeof v === 'string'))
      })
      .catch(() => {
        if (!cancelled) setFavoriteApplyPaths([])
      })
    return () => { cancelled = true }
  }, [user?.id])

  useEffect(() => {
    if (!allApplyOpenKey) { setAllApplyOpen(true); return }
    const saved = localStorage.getItem(allApplyOpenKey)
    if (saved === 'true' || saved === 'false') {
      setAllApplyOpen(saved === 'true')
      return
    }
    setAllApplyOpen(favoriteApplyPaths.length === 0)
  }, [allApplyOpenKey, favoriteApplyPaths.length])

  const toggleFavoriteApply = (to: string) => {
    if (!user?.id) return
    setFavoriteApplyPaths(prev => {
      const next = prev.includes(to) ? prev.filter(p => p !== to) : [...prev, to]
      axios.put('/api/user/preferences/favorites', { favorites: next })
        .then(res => {
          const saved = Array.isArray(res.data?.favorites) ? res.data.favorites : next
          setFavoriteApplyPaths(saved.filter((v: unknown): v is string => typeof v === 'string'))
        })
        .catch(() => setFavoriteApplyPaths(prev))
      return next
    })
  }

  const toggleAllApplyOpen = () => {
    setApplyMoreAnimating(true)
    setAllApplyOpen(prev => {
      const next = !prev
      if (allApplyOpenKey) localStorage.setItem(allApplyOpenKey, String(next))
      return next
    })
    window.setTimeout(() => setApplyMoreAnimating(false), 260)
  }

  // ── 未读通知数 ──
  const [unreadCount, setUnreadCount] = useState(0)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchUnread = useCallback(async () => {
    try {
      if (document.visibilityState !== 'visible') return
      const res = await axios.get('/api/notifications/unread-count')
      setUnreadCount(res.data.unread_count || 0)
    } catch {
      // 轮询失败不打断用户
    }
  }, [])

  useEffect(() => {
    fetchUnread()

    const startInterval = () => {
      if (intervalRef.current) return
      intervalRef.current = setInterval(fetchUnread, 30000)
    }

    const stopInterval = () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }

    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        fetchUnread()
        startInterval()
      } else {
        stopInterval()
      }
    }

    startInterval()
    document.addEventListener('visibilitychange', handleVisibility)
    return () => {
      stopInterval()
      document.removeEventListener('visibilitychange', handleVisibility)
    }
  }, [fetchUnread])

  // 按角色构建分组导航
  const sections: NavSection[] = []
  const isAdminOnly = user?.is_admin && !user?.is_dept_admin && !user?.is_school_admin && !user?.is_finance_admin

  if (isAdminOnly) {
    // 总管理员：仅系统管理 + 个人信息
    sections.push({ header: '系统管理', items: ADMIN_NAV })
  } else if (user?.is_finance_admin) {
    sections.push({ header: '审批', items: [
      { to: '/finance', label: '💰 报销审批' },
      { to: '/dashboard', label: '📊 数据看板' },
    ]})
    sections.push({ header: '工具', items: [
      { to: '/history', label: '📋 历史记录' },
      { to: '/notifications', label: '🔔 消息通知' },
    ]})
  } else {
    sections.push({ items: [{ to: '/', label: '🤖 智能审批' }] })

    const applyItems = user?.is_dept_admin
      ? [{ to: '/apply/reimbursement', label: '💰 报销申请' }]
      : APPLY_NAV
    const favoriteItems = applyItems.filter(item => favoriteApplyPaths.includes(item.to)).slice(0, 5)
    const regularItems = applyItems.filter(item => !favoriteItems.some(f => f.to === item.to))
    if (favoriteItems.length > 0) sections.push({ header: '⭐ 常用', items: favoriteItems })
    const regularHasActive = regularItems.some(item => loc.pathname === item.to || loc.pathname.startsWith(item.to))
    sections.push({
      header: '📋 全部事务',
      items: regularItems,
      previewCount: user?.is_dept_admin ? undefined : 3,
      collapsed: !allApplyOpen && !regularHasActive,
      onToggle: toggleAllApplyOpen,
    })

    sections.push({ header: '工具', items: TOOL_NAV })
    sections.push({ header: '社区', items: COMMUNITY_NAV })

    if (user?.is_dept_admin)   sections.push({ header: '部门管理', items: DEPT_NAV })
    if (user?.is_school_admin) sections.push({ header: '学校管理', items: SCHOOL_NAV })
  }

  sections.push({ header: '账号', items: [{ to: '/profile', label: '👤 个人信息' }] })

  return (
    <div className="app-layout" style={{ display: 'flex', minHeight: '100vh', gap: 0 }}>
      {/* 移动端汉堡按钮 — 左下角，与小助手悬浮按钮水平对齐 */}
      {isMobile && (
        <button
          onClick={() => setSidebarOpen(o => !o)}
          aria-label={sidebarOpen ? '关闭菜单' : '打开菜单'}
          style={{
            position: 'fixed', bottom: 24,
            left: sidebarOpen ? 'calc(var(--sidebar-width) + 28px)' : 24,
            zIndex: 1100,
            width: 52, height: 52, borderRadius: '50%',
            background: 'var(--glass-bg-strong)', border: '1px solid var(--glass-border)',
            backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)',
            cursor: 'pointer', fontSize: 18, display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: 'var(--text-primary)',
            boxShadow: '0 4px 20px rgba(0,0,0,0.1)',
            padding: 0, lineHeight: 1,            transition: 'left 0.35s cubic-bezier(0.2, 0.85, 0.2, 1), transform 0.2s ease',          }}
        >
          <span style={{
            display: 'inline-block',
            transform: `rotate(${sidebarOpen ? 90 : 0}deg)`,
            transition: 'transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)',
          }}>
            {sidebarOpen ? '✕' : '☰'}
          </span>
        </button>
      )}

      {/* 移动端遮罩 */}
      <div
        onClick={closeSidebar}
        style={{
          position: 'fixed', inset: 0, zIndex: 1050,
          background: 'rgba(0,0,0,0.35)', backdropFilter: 'blur(4px)',
          opacity: isMobile && sidebarOpen ? 1 : 0,
          pointerEvents: isMobile && sidebarOpen ? 'auto' : 'none',
          transition: 'opacity 0.3s ease',
        }}
      />

      {/* 侧边栏 — 桌面端 sticky 侧栏，移动端 fixed 抽屉 */}
      <aside className="glass-card glass-card-strong" style={{
        width: 'var(--sidebar-width)',
        display: 'flex',
        flexDirection: 'column',
        borderRadius: 20,
        padding: 0,
        position: isMobile ? 'fixed' : 'sticky',
        top: 12,
        left: 12,
        ...(isMobile
          ? { height: 'calc(100dvh - 24px)', margin: 0 }
          : { height: 'calc(100vh - 24px)', margin: 12 }
        ),
        flexShrink: 0,
        alignSelf: 'flex-start',
        overflow: 'hidden',
        zIndex: isMobile ? 1060 : 'auto',
        boxShadow: isMobile ? '0 8px 40px rgba(0,0,0,0.2)' : undefined,
        ...(isMobile ? {
          opacity: sidebarOpen ? 1 : 0,
          transform: sidebarOpen ? 'translateX(0)' : 'translateX(-16px)',
          pointerEvents: sidebarOpen ? 'auto' : 'none',
          transition: 'opacity 0.3s cubic-bezier(0.2, 0.85, 0.2, 1), transform 0.35s cubic-bezier(0.2, 0.85, 0.2, 1)',
        } : {}),
      }}>
        {/* Logo 区域 */}
        <div style={{
          padding: '20px 16px 16px',
          borderBottom: '1px solid var(--divider)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
        }}>
          <div>
            <div style={{ fontSize: 20, fontWeight: 700, letterSpacing: 0.5 }}>
              智审通
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>
              高校行政审批自动化 Agent
            </div>
          </div>
          <Link to="/notifications" onClick={closeSidebar} style={{ position: 'relative', textDecoration: 'none' }}>
            <span style={{ fontSize: 20 }}>🔔</span>
            {unreadCount > 0 && (
              <span style={{
                position: 'absolute', top: -6, right: -8,
                background: '#FF3B30', color: '#fff',
                fontSize: 10, fontWeight: 700,
                minWidth: 18, height: 18, borderRadius: 9,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                padding: '0 4px',
              }}>
                {unreadCount > 99 ? '99+' : unreadCount}
              </span>
            )}
          </Link>
        </div>

        {/* 导航 */}
        <nav style={{
          flex: 1,
          padding: '12px 12px 16px',
          overflowY: 'auto',
        }}>
          {sections.map((section, si) => (
            <div key={si} style={{ marginBottom: 4 }}>
              {section.header ? (
                <div style={{
                  fontSize: 11, fontWeight: 650, letterSpacing: '0.05em',
                  textTransform: 'uppercase', color: 'var(--text-tertiary)',
                  padding: si === 0 ? '4px 12px 4px' : '14px 12px 4px',
                }}>
                  {section.header}
                </div>
              ) : (
                si > 0 && <div style={{ height: 1, background: 'var(--divider)', margin: '8px 12px 10px' }} />
              )}
              {(() => {
                const previewCount = section.previewCount || section.items.length
                const visibleItems = section.items.slice(0, previewCount)
                const hiddenItems = section.items.slice(previewCount)
                const renderItem = (item: NavItem) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    label={item.label}
                    currentPath={loc.pathname}
                    onClick={closeSidebar}
                    favorite={favoriteApplyPaths.includes(item.to)}
                    onToggleFavorite={APPLY_NAV.some(apply => apply.to === item.to) ? () => toggleFavoriteApply(item.to) : undefined}
                  />
                )
                return (
                  <>
                    {visibleItems.map(renderItem)}
                    {hiddenItems.length > 0 && (
                      <>
                        <div style={{
                          display: 'grid',
                          gridTemplateRows: section.collapsed ? '0fr' : '1fr',
                          opacity: section.collapsed ? 0 : 1,
                          overflow: 'hidden',
                          visibility: section.collapsed && !applyMoreAnimating ? 'hidden' : 'visible',
                          pointerEvents: section.collapsed ? 'none' : 'auto',
                          transition: applyMoreAnimating ? 'grid-template-rows 0.24s cubic-bezier(0.2, 0.85, 0.2, 1), opacity 0.18s ease' : 'none',
                        }}>
                          <div style={{ minHeight: 0 }}>
                          {hiddenItems.map(renderItem)}
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={section.onToggle}
                          aria-expanded={!section.collapsed}
                          style={{
                            width: 'calc(100% - 24px)', margin: '6px 12px 2px', padding: '8px 10px',
                            border: '1px solid var(--glass-border)', borderRadius: 999,
                            background: section.collapsed ? 'rgba(0,122,255,0.06)' : 'var(--glass-bg)',
                            color: section.collapsed ? 'var(--accent)' : 'var(--text-secondary)',
                            cursor: 'pointer', fontSize: 12, fontWeight: 600,
                            fontFamily: 'var(--font-stack)',
                            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                            transition: 'background 0.2s ease, color 0.2s ease, transform 0.2s ease',
                          }}
                        >
                          <span>{section.collapsed ? `展开其余 ${hiddenItems.length} 项` : '收起更多事务'}</span>
                          <span style={{ transform: `rotate(${section.collapsed ? 0 : 180}deg)`, transition: 'transform 0.2s ease' }}>⌄</span>
                        </button>
                      </>
                    )}
                  </>
                )
              })()}
            </div>
          ))}
        </nav>

        {/* 底部用户信息 */}
        <div style={{
          padding: '14px 16px',
          borderTop: '1px solid var(--divider)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 12, flexShrink: 0,
              background: 'linear-gradient(135deg, var(--accent) 0%, var(--purple) 100%)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 14, fontWeight: 700, color: '#fff',
            }}>
              {user?.username?.[0]?.toUpperCase() ?? '?'}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{
                fontSize: 13, fontWeight: 600,
                color: 'var(--text-primary)',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>
                {user?.username}
              </div>
              {user?.school && (
                <div style={{
                  fontSize: 11, color: 'var(--text-secondary)', marginTop: 1,
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {user.school}
                </div>
              )}
            </div>
          </div>
          <button
            onClick={() => { logout(); nav('/login') }}
            className="glass-btn glass-btn-outline"
            style={{ width: '100%', padding: '8px 0', fontSize: 14 }}
          >
            退出登录
          </button>
        </div>
      </aside>

      {/* 主内容区 */}
      <main>
        {/* 模拟状态提示（SimulationBanner 自行判断是否激活，无需外层守卫） */}
        <SimulationBanner />
        <div className="content-container">
          {children}
        </div>
      </main>
    </div>
  )
}

/** 管理员模拟身份提示条 + 侧栏退出按钮 */
function SimulationBanner({ isSidebar = false }: { isSidebar?: boolean }) {
  const loc = useLocation()
  const nav = useNavigate()
  const { refreshUser } = useAuth()
  const [sim, setSim] = useState<{ active: boolean; overrides: Record<string, any> } | null>(null)

  useEffect(() => {
    axios.get('/api/admin/test-session')
      .then(r => setSim(r.data))
      .catch(() => {})
  }, [loc.pathname])  // 路由切换时重新检查

  if (!sim?.active) return null

  const exit = async () => {
    await axios.delete('/api/admin/test-session')
    setSim(null)
    await refreshUser()    // 重新拉取真实身份，刷新 React 上下文
    nav('/admin/members')  // React Router 跳转，无需整页刷新
  }

  // 侧栏版本：紧凑按钮
  if (isSidebar) {
    return (
      <button
        onClick={exit}
        className="glass-btn glass-btn-sm"
        style={{
          width: '100%', marginTop: 6,
          background: 'rgba(255,149,0,0.15)',
          border: '1px solid var(--orange)',
          color: 'var(--orange)',
          fontWeight: 600,
        }}
      >
        ⚡ 退出模拟
      </button>
    )
  }

  // 主内容区横幅版本
  return (
    <div style={{
      margin: '0 0 12px 0',
      padding: '6px 14px',
      borderRadius: 10,
      background: 'rgba(255,149,0,0.12)',
      border: '1px solid rgba(255,149,0,0.25)',
      display: 'flex', alignItems: 'center', gap: 10,
      fontSize: 13,
      flexWrap: 'wrap',
    }}>
      <span style={{ color: 'var(--orange)', fontWeight: 600 }}>⚡ 模拟身份激活中</span>
      <span style={{ color: 'var(--text-secondary)' }}>
        {sim.overrides.tier || ''}
        {sim.overrides.is_dept_admin ? ' · 部门管理员' : ''}
        {sim.overrides.is_school_admin ? ' · 学校管理员' : ''}
        {sim.overrides.is_finance_admin ? ' · 财务管理员' : ''}
        {!sim.overrides.is_dept_admin && !sim.overrides.is_school_admin && !sim.overrides.is_finance_admin && sim.overrides.is_admin === false ? ' · 普通用户' : ''}
      </span>
      <button onClick={exit}
        className="glass-btn glass-btn-sm"
        style={{ marginLeft: 'auto', background: 'var(--orange)', color: '#fff', flexShrink: 0 }}>
        🚪 退出模拟
      </button>
    </div>
  )
}
