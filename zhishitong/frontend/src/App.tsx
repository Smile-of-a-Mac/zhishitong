import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './hooks/useAuth'
import LoginPage from './pages/auth/LoginPage'
import WorkbenchPage from './pages/workbench/WorkbenchPage'
import HistoryPage from './pages/history/HistoryPage'
import AdminApiKeysPage from './pages/admin/AdminApiKeysPage'
import AdminSchoolsPage from './pages/admin/AdminSchoolsPage'
import AdminMonitorPage from './pages/admin/AdminMonitorPage'
import AdminUsersPage from './pages/admin/AdminUsersPage'
import AdminDataPage from './pages/admin/AdminDataPage'
import DeptAdminPage from './pages/dept/DeptAdminPage'
import SchoolAdminPage from './pages/school/SchoolAdminPage'
import FinanceAdminPage from './pages/finance/FinanceAdminPage'
import SchoolAffairsPage from './pages/school/SchoolAffairsPage'
import ManualFormPage from './pages/workbench/ManualFormPage'
import ProfilePage from './pages/profile/ProfilePage'
import NotificationsPage from './pages/workbench/NotificationsPage'
import DashboardPage from './pages/workbench/DashboardPage'
import ResourceBookingPage from './pages/workbench/ResourceBookingPage'
import AnnouncementsPage from './pages/workbench/AnnouncementsPage'
import Frame from './components/Frame'
import AIChatPanel from './components/AIChatPanel'

function NeedAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: '#999' }}>加载中...</div>
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

function NeedAdmin({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  if (!user?.is_admin) return <Navigate to="/" replace />
  return <>{children}</>
}

function NeedNormalUser({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  // 所有人（含管理员）都可以访问普通用户页面；管理员同时拥有管理入口
  return <>{children}</>
}

function NeedDeptStaff({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  if (!user?.is_dept_admin) return <Navigate to="/" replace />
  return <>{children}</>
}

function NeedSchoolStaff({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  if (!user?.is_school_admin) return <Navigate to="/" replace />
  return <>{children}</>
}

function NeedFinanceStaff({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  if (!user?.is_finance_admin) return <Navigate to="/" replace />
  return <>{children}</>
}

function NeedStaff({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  if (!(user?.is_dept_admin || user?.is_finance_admin || user?.is_school_admin || user?.is_admin)) return <Navigate to="/" replace />
  return <>{children}</>
}

// 财务管理员不能访问任何申请页面（角色分离）
function NoFinanceAdmin({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  if (user?.is_finance_admin) return <Navigate to="/finance" replace />
  return <>{children}</>
}

// 总管理员访问工作台时重定向到管理页
function AdminRedirect({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  if (user?.is_admin && !user?.is_dept_admin && !user?.is_school_admin && !user?.is_finance_admin) {
    return <Navigate to="/admin/members" replace />
  }
  return <>{children}</>
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<NeedAuth><AdminRedirect><NoFinanceAdmin><Frame><WorkbenchPage /></Frame></NoFinanceAdmin></AdminRedirect></NeedAuth>} />
        <Route path="/profile" element={<NeedAuth><Frame><ProfilePage /></Frame></NeedAuth>} />
        <Route path="/history" element={<NeedAuth><NoFinanceAdmin><Frame><HistoryPage /></Frame></NoFinanceAdmin></NeedAuth>} />
        <Route path="/notifications" element={<NeedAuth><Frame><NotificationsPage /></Frame></NeedAuth>} />
        <Route path="/dashboard" element={<NeedAuth><NeedStaff><Frame><DashboardPage /></Frame></NeedStaff></NeedAuth>} />
        <Route path="/resources" element={<NeedAuth><NoFinanceAdmin><Frame><ResourceBookingPage /></Frame></NoFinanceAdmin></NeedAuth>} />
        <Route path="/announcements" element={<NeedAuth><NoFinanceAdmin><Frame><AnnouncementsPage /></Frame></NoFinanceAdmin></NeedAuth>} />
        <Route path="/admin/api-keys" element={<NeedAuth><NeedAdmin><Frame><AdminApiKeysPage /></Frame></NeedAdmin></NeedAuth>} />
        <Route path="/admin/schools" element={<NeedAuth><NeedAdmin><Frame><AdminSchoolsPage /></Frame></NeedAdmin></NeedAuth>} />
        <Route path="/admin/members" element={<NeedAuth><NeedAdmin><Frame><AdminUsersPage /></Frame></NeedAdmin></NeedAuth>} />
        <Route path="/admin/monitor" element={<NeedAuth><NeedAdmin><Frame><AdminMonitorPage /></Frame></NeedAdmin></NeedAuth>} />
        <Route path="/admin/data" element={<NeedAuth><NeedAdmin><Frame><AdminDataPage /></Frame></NeedAdmin></NeedAuth>} />
        <Route path="/dept" element={<NeedAuth><NeedDeptStaff><Frame><DeptAdminPage /></Frame></NeedDeptStaff></NeedAuth>} />
        <Route path="/school" element={<NeedAuth><NeedSchoolStaff><Frame><SchoolAdminPage /></Frame></NeedSchoolStaff></NeedAuth>} />
        <Route path="/school/affairs" element={<NeedAuth><NeedSchoolStaff><Frame><SchoolAffairsPage /></Frame></NeedSchoolStaff></NeedAuth>} />
        <Route path="/finance" element={<NeedAuth><NeedFinanceStaff><Frame><FinanceAdminPage /></Frame></NeedFinanceStaff></NeedAuth>} />
        <Route path="/apply/:docType" element={<NeedAuth><NoFinanceAdmin><Frame><ManualFormPage /></Frame></NoFinanceAdmin></NeedAuth>} />
      </Routes>
      <AIChatPanel />
    </AuthProvider>
  )
}
