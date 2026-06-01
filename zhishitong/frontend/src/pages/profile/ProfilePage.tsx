import React, { useState } from 'react'
import axios from 'axios'
import { useAuth } from '../../hooks/useAuth'
import GlassCard from '../../components/GlassCard'

const TIER_LABEL: Record<string, string> = { free: '免费版', pro: '专业版', pro_plus: '企业版' }
const TIER_COLORS: Record<string, string> = {
  free: 'var(--text-secondary)', pro: 'var(--accent)', pro_plus: 'var(--purple)',
}

export default function ProfilePage() {
  const { user } = useAuth()
  const [showPwdForm, setShowPwdForm] = useState(false)
  const [oldPwd, setOldPwd] = useState('')
  const [newPwd, setNewPwd] = useState('')
  const [confirmPwd, setConfirmPwd] = useState('')
  const [pwdError, setPwdError] = useState('')
  const [pwdSuccess, setPwdSuccess] = useState('')
  const [pwdLoading, setPwdLoading] = useState(false)
  if (!user) return null

  const roles: string[] = []
  if (user.is_admin) roles.push('信息管理员')
  if (user.is_school_admin) roles.push('学校管理员')
  if (user.is_dept_admin) roles.push('部门管理员')
  if (user.is_finance_admin) roles.push('财务管理员')
  if (roles.length === 0) roles.push('普通用户')

  // 判断身份：
  //   - 管理员（is_admin）→ 系统运维人员
  //   - 各类审批管理员（dept/school/finance）→ 教职工
  //   - 普通用户 → 学生
  const isSystemAdmin = !!user.is_admin
  const isStaff = !isSystemAdmin && (!!user.is_school_admin || !!user.is_dept_admin || !!user.is_finance_admin)
  const isStudent = !isSystemAdmin && !isStaff

  const initial = (user.real_name || user.username).charAt(0).toUpperCase()
  const displayName = user.real_name || user.username

  return (
    <div>
      <h1 className="page-title">个人信息</h1>

      <GlassCard strong>
        {/* 头像 + 基本身份 */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24,
          paddingBottom: 24, borderBottom: '1px solid var(--divider)',
        }}>
          <div style={{
            width: 64, height: 64, borderRadius: '50%',
            background: 'linear-gradient(135deg, var(--accent), var(--purple))',
            color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 26, fontWeight: 600, flexShrink: 0,
          }}>
            {initial}
          </div>
          <div>
            <div style={{ fontSize: 18, fontWeight: 600 }}>{displayName}</div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>
              {isStudent ? '👨‍🎓 学生' : isStaff ? '👨‍🏫 教职工' : isSystemAdmin ? '⚙️ 系统管理员' : ''} · {roles.join(' · ')}
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 2 }}>
              @{user.username}
            </div>
          </div>
        </div>

        {/* 双列信息网格 */}
        <div className="responsive-two-col-grid" style={{ gap: '0 24px' }}>

          {/* ── 基本信息 ── */}
          <SectionTitle label="基本信息" />

          <InfoRow label="真实姓名" value={user.real_name || '—'} />
          <InfoRow label="性别" value={user.gender || '—'} />
          <InfoRow label="联系电话" value={user.phone || '—'} />
          <InfoRow label="电子邮箱" value={user.email || '—'} />
          <InfoRow label="所属学校" value={user.school || '—'} />
          <InfoRow label="所属部门" value={user.department || '—'} />

          {/* ── 身份信息 ── */}
          {isStudent && (
            <>
              <SectionTitle label="👨‍🎓 学生信息" />
              <InfoRow label="学号" value={user.student_id || '—'} />
              <InfoRow label="专业" value={user.major || '—'} />
              <InfoRow label="班级" value={user.class_name || '—'} />
              <InfoRow label="入学年份" value={user.enrollment_year ? `${user.enrollment_year} 年` : '—'} />
              <InfoRow label="辅导员" value={user.advisor || '—'} />
            </>
          )}

          {isStaff && (
            <>
              <SectionTitle label="👨‍🏫 教职工信息" />
              <InfoRow label="工号" value={user.employee_id || '—'} />
              <InfoRow label="职称" value={user.title || '—'} />
            </>
          )}

          {isSystemAdmin && (
            <>
              <SectionTitle label="⚙️ 管理员信息" />
              <InfoRow label="工号" value={user.employee_id || '—'} />
              <InfoRow label="职称" value={user.title || '—'} />
            </>
          )}

          {/* ── 账号信息 ── */}
          <SectionTitle label="⚙️ 账号信息" />

          <InfoRow label="订阅层级">
            <span style={{ fontSize: 14, fontWeight: 600, color: TIER_COLORS[user.tier] || 'var(--text-primary)' }}>
              {TIER_LABEL[user.tier] || user.tier}
            </span>
          </InfoRow>
          <InfoRow label="账号状态">
            <span className={user.is_active ? 'glass-tag glass-tag-green' : 'glass-tag glass-tag-red'}>
              {user.is_active ? '● 正常' : '● 已禁用'}
            </span>
          </InfoRow>

          {user.tier !== 'free' && (
            <>
              <InfoRow label="LLM OCR 用量">
                <span style={{ fontSize: 14 }}>
                  {user.llm_ocr_used} / {user.llm_ocr_quota === 99999 ? '不限' : user.llm_ocr_quota}
                  {user.llm_ocr_quota > 0 && user.llm_ocr_quota !== 99999 && (
                    <span style={{ marginLeft: 6, fontSize: 12, color: 'var(--text-tertiary)' }}>
                      ({user.llm_ocr_quota - user.llm_ocr_used} 剩余)
                    </span>
                  )}
                </span>
              </InfoRow>
              <div />
            </>
          )}
        </div>
      </GlassCard>

      {/* ── 修改密码 ── */}
      <GlassCard style={{ marginTop: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 600 }}>🔐 修改密码</div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>定期更换密码以保护账号安全</div>
          </div>
          <button
            className="glass-btn glass-btn-outline glass-btn-sm"
            onClick={() => { setShowPwdForm(!showPwdForm); setPwdError(''); setPwdSuccess('') }}
          >
            {showPwdForm ? '取消' : '修改密码'}
          </button>
        </div>

        {showPwdForm && (
          <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid var(--divider)' }}>
            <div className="responsive-form-grid" style={{ gap: 12, maxWidth: 480 }}>
              <div style={{ gridColumn: '1 / -1' }}>
                <label style={{ display: 'block', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>原密码</label>
                <input type="password" value={oldPwd} onChange={e => setOldPwd(e.target.value)}
                  placeholder="请输入当前密码" className="glass-input" />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>新密码</label>
                <input type="password" value={newPwd} onChange={e => setNewPwd(e.target.value)}
                  placeholder="至少 8 位" className="glass-input" />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>确认新密码</label>
                <input type="password" value={confirmPwd} onChange={e => setConfirmPwd(e.target.value)}
                  placeholder="再次输入新密码" className="glass-input" />
              </div>
            </div>
            {pwdError && (
              <div style={{ color: 'var(--red)', fontSize: 13, marginTop: 8, padding: '6px 10px', background: 'rgba(255,59,48,0.08)', borderRadius: 8 }}>
                ⚠️ {pwdError}
              </div>
            )}
            {pwdSuccess && (
              <div style={{ color: 'var(--green)', fontSize: 13, marginTop: 8, padding: '6px 10px', background: 'rgba(52,199,89,0.08)', borderRadius: 8 }}>
                ✅ {pwdSuccess}
              </div>
            )}
            <button
              className="glass-btn glass-btn-sm"
              style={{ marginTop: 12 }}
              disabled={pwdLoading}
              onClick={async () => {
                setPwdError(''); setPwdSuccess('')
                if (!oldPwd) { setPwdError('请输入原密码'); return }
                if (newPwd.length < 8) { setPwdError('新密码至少 8 位'); return }
                if (newPwd !== confirmPwd) { setPwdError('两次密码不一致'); return }
                setPwdLoading(true)
                try {
                  await axios.put('/api/change-password', { old_password: oldPwd, new_password: newPwd })
                  setPwdSuccess('密码修改成功')
                  setOldPwd(''); setNewPwd(''); setConfirmPwd('')
                } catch (e: any) {
                  setPwdError(e?.response?.data?.detail || '修改失败')
                } finally { setPwdLoading(false) }
              }}
            >
              {pwdLoading ? '提交中…' : '确认修改'}
            </button>
          </div>
        )}
      </GlassCard>
    </div>
  )
}

function SectionTitle({ label }: { label: string }) {
  return (
    <div style={{
      gridColumn: '1 / -1',
      fontSize: 13, fontWeight: 600,
      color: 'var(--text-secondary)',
      padding: '12px 0 4px',
      borderBottom: '1px solid var(--divider)',
      marginBottom: 4,
    }}>
      {label}
    </div>
  )
}

function InfoRow({ label, value, children }: { label: string; value?: string; children?: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', padding: '5px 0' }}>
      <span style={{ fontSize: 11, color: 'var(--text-tertiary)', marginBottom: 1 }}>{label}</span>
      <span style={{ fontSize: 14 }}>
        {children || <span>{value}</span>}
      </span>
    </div>
  )
}
