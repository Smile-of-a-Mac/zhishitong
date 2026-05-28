import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import axios from 'axios'

export interface User {
  id: number; username: string; tier: string
  llm_ocr_quota: number; llm_ocr_used: number
  is_active: boolean; is_admin: boolean
  is_school_admin: boolean; is_dept_admin: boolean; is_finance_admin: boolean
  department: string | null; school: string | null
  // 个人信息
  real_name?: string | null; gender?: string | null
  phone?: string | null; email?: string | null
  student_id?: string | null; major?: string | null
  class_name?: string | null; enrollment_year?: number | null
  advisor?: string | null; employee_id?: string | null
  title?: string | null
}

interface AuthContextType {
  user: User | null; token: string | null; loading: boolean
  login: (u: string, p: string) => Promise<void>
  register: (u: string, p: string) => Promise<void>
  logout: () => void; refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextType>({
  user: null, token: null, loading: false,
  login: async () => {}, register: async () => {},
  logout: () => {}, refreshUser: async () => {},
})

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('token'))
  const [loading, setLoading] = useState(true)

  axios.defaults.baseURL = ''

  const refreshUser = useCallback(async () => {
    const t = localStorage.getItem('token')
    if (!t) { setUser(null); setToken(null); setLoading(false); return }
    axios.defaults.headers.common['Authorization'] = `Bearer ${t}`
    try {
      const res = await axios.get('/api/me')
      setUser(res.data)
    } catch (error: any) {
      const status = error?.response?.status
      if (status === 401) {
        localStorage.removeItem('token')
        delete axios.defaults.headers.common['Authorization']
        setToken(null)
        setUser(null)
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refreshUser() }, [refreshUser])

  const login = async (username: string, password: string) => {
    const res = await axios.post('/api/login', { username, password })
    localStorage.setItem('token', res.data.access_token)
    axios.defaults.headers.common['Authorization'] = `Bearer ${res.data.access_token}`
    setToken(res.data.access_token)
    setUser(res.data.user)
  }

  const register = async (username: string, password: string) => {
    const res = await axios.post('/api/register', { username, password })
    localStorage.setItem('token', res.data.access_token)
    axios.defaults.headers.common['Authorization'] = `Bearer ${res.data.access_token}`
    setToken(res.data.access_token)
    setUser(res.data.user)
  }

  const logout = () => {
    localStorage.removeItem('token')
    delete axios.defaults.headers.common['Authorization']
    // 清除所有用户会话数据，避免切换用户时看到上一个用户的数据
    sessionStorage.clear()
    setToken(null); setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, token, loading, login, register, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() { return useContext(AuthContext) }
