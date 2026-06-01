import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../hooks/useAuth'

export default function LoginPage() {
  const [loading, setLoading] = useState(false)
  const [cardEntered, setCardEntered] = useState(false)
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [showDemo, setShowDemo] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [fieldErrors, setFieldErrors] = useState<{ username?: string; password?: string; confirmPassword?: string }>({})
  const { login, register } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    const rafId = requestAnimationFrame(() => {
      setCardEntered(true)
    })
    return () => cancelAnimationFrame(rafId)
  }, [])

  const handleSubmit = async () => {
    setError('')
    setFieldErrors({})

    const errs: { username?: string; password?: string; confirmPassword?: string } = {}
    if (!username.trim()) errs.username = '请输入用户名'
    if (!password) errs.password = '请输入密码'
    else if (mode === 'register' && password.length < 8) errs.password = '密码至少 8 位'
    if (mode === 'register') {
      if (!confirmPassword) errs.confirmPassword = '请确认密码'
      else if (password !== confirmPassword) errs.confirmPassword = '两次密码不一致'
    }
    if (Object.keys(errs).length > 0) { setFieldErrors(errs); return }

    setLoading(true)
    try {
      if (mode === 'login') {
        await login(username, password)
      } else {
        await register(username, password)
      }
      navigate('/')
    } catch (e: any) {
      const status = e?.response?.status
      const detail = e?.response?.data?.detail || ''
      if (status === 401) {
        setError(detail || '用户名或密码错误，请检查后重试')
      } else if (status === 403) {
        setError(detail || '账号已被禁用，请联系管理员')
      } else if (status === 400) {
        setError(detail || '请检查输入信息')
      } else if (!e?.response) {
        setError('无法连接到服务器，请检查网络或确认服务已启动')
      } else {
        setError(detail || '操作失败，请稍后重试')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page-wrapper">
      <div className={`login-card${cardEntered ? ' login-card-enter' : ''}`}>
        <div style={{ textAlign: 'center', marginBottom: 28 }}>
          <div style={{ fontSize: 28, fontWeight: 700, marginBottom: 4, color: 'var(--text-primary)' }}>智审通</div>
          <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>高校行政审批自动化 Agent</div>
        </div>

        {/* 切换 tabs */}
        <div className="login-tab-group">
          {(['login', 'register'] as const).map(m => (
            <div
              key={m}
              onClick={() => { setMode(m); setError(''); setFieldErrors({}) }}
              className={mode === m ? 'login-tab-active' : 'login-tab-inactive'}
            >
              {m === 'login' ? '登录' : '注册'}
            </div>
          ))}
        </div>

        <form onSubmit={e => { e.preventDefault(); handleSubmit() }}>
        <div style={{ marginBottom: 12 }}>
          <input
            placeholder="请输入用户名"
            value={username}
            onChange={e => { setUsername(e.target.value); setFieldErrors(prev => ({ ...prev, username: undefined })); setError('') }}
            className="login-input"
            style={{ borderColor: fieldErrors.username ? 'var(--red)' : undefined }}
          />
          {fieldErrors.username && (
            <div style={{ color: 'var(--red)', fontSize: 12, marginTop: 3, paddingLeft: 4 }}>{fieldErrors.username}</div>
          )}
        </div>
        <div style={{ marginBottom: 16 }}>
          <input
            type="password"
            placeholder="请输入密码"
            value={password}
            onChange={e => { setPassword(e.target.value); setFieldErrors(prev => ({ ...prev, password: undefined })); setError('') }}
            className="login-input"
            style={{ borderColor: fieldErrors.password ? 'var(--red)' : undefined }}
          />
          {fieldErrors.password && (
            <div style={{ color: 'var(--red)', fontSize: 12, marginTop: 3, paddingLeft: 4 }}>{fieldErrors.password}</div>
          )}
        </div>

        <div className={`login-collapse${mode === 'register' ? ' login-collapse-open' : ''}`}>
          <div className={`login-collapse-content${mode === 'register' ? ' login-collapse-content-open' : ''}`} style={{ marginBottom: 16 }}>
            <input
              type="password"
              placeholder="请再次输入密码"
              value={confirmPassword}
              onChange={e => { setConfirmPassword(e.target.value); setFieldErrors(prev => ({ ...prev, confirmPassword: undefined })); setError('') }}
              className="login-input"
              style={{ borderColor: fieldErrors.confirmPassword ? 'var(--red)' : undefined }}
            />
            {fieldErrors.confirmPassword && (
              <div style={{ color: 'var(--red)', fontSize: 12, marginTop: 3, paddingLeft: 4 }}>{fieldErrors.confirmPassword}</div>
            )}
          </div>
        </div>

        {error && (
          <div style={{
            color: 'var(--red)', fontSize: 13, marginBottom: 12,
            padding: '8px 12px', background: 'rgba(255,59,48,0.08)',
            borderRadius: 'var(--radius-xs)', border: '1px solid rgba(255,59,48,0.2)',
            display: 'flex', alignItems: 'flex-start', gap: 6,
          }}>
            <span style={{ flexShrink: 0 }}>⚠️</span>
            <span>{error}</span>
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="glass-btn glass-btn-lg"
          style={{ width: '100%' }}
        >
          {loading ? '处理中…' : mode === 'login' ? '登  录' : '注  册'}
        </button>
        </form>

        <hr className="glass-divider" />

        <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.8 }}>
          <div
            onClick={() => setShowDemo(v => !v)}
            style={{ cursor: 'pointer', fontWeight: 600, color: 'var(--text-secondary)', userSelect: 'none' }}
          >
            📘 演示账号
          </div>
          <div className={`login-collapse${showDemo ? ' login-collapse-open' : ''}`}>
            <div>
              <div className={`login-collapse-content${showDemo ? ' login-collapse-content-open' : ''}`} style={{ marginTop: 8, background: 'rgba(0,0,0,0.04)', borderRadius: 8, padding: '10px 12px' }}>
                <strong>系统管理员：</strong><br />
                admin — 信息管理员（密码由部署方提供）<br /><br />
                <strong>山东科技大学 (Pro)：</strong><br />
                sdu_school_admin — 学校管理员<br />
                sdu_dept_cs — 部门管理员（计算机学院）<br />
                sdu_dept_fin — 部门管理员（财务处）<br />
                sdu_finance_admin — 财务管理员<br />
                sdu_student_a / sdu_student_b — 学生<br /><br />
                <strong>山东科技大学（济南校区）(Free)：</strong><br />
                sdujn_school_admin — 学校管理员<br />
                sdujn_dept_cs — 部门管理员<br />
                sdujn_dept_fin — 部门管理员<br />
                sdujn_finance_admin — 财务管理员<br />
                sdujn_student_a / sdujn_student_b — 学生
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
