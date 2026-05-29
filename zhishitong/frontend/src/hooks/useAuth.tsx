import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import axios from 'axios'

axios.defaults.baseURL = ''
axios.defaults.withCredentials = true

const storedToken = localStorage.getItem('token')
if (storedToken) axios.defaults.headers.common['Authorization'] = `Bearer ${storedToken}`

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

  useEffect(() => {
    let isRefreshing = false
    let failedQueue: Array<{ resolve: (t: string) => void; reject: (e: any) => void }> = []

    const processQueue = (error: any, token: string | null = null) => {
      failedQueue.forEach(p => {
        if (error) p.reject(error)
        else p.resolve(token!)
      })
      failedQueue = []
    }

    const interceptorId = axios.interceptors.response.use(
      resp => resp,
      async error => {
        const originalRequest = error.config
        const url = originalRequest?.url || ''
        const skipRefresh = url.includes('/api/login') || url.includes('/api/register') || url.includes('/api/auth/refresh')

        if (error?.response?.status === 401 && originalRequest && !originalRequest._retry && !skipRefresh) {
          if (isRefreshing) {
            return new Promise((resolve, reject) => {
              failedQueue.push({ resolve, reject })
            }).then(token => {
              originalRequest.headers = originalRequest.headers || {}
              originalRequest.headers['Authorization'] = `Bearer ${token}`
              return axios(originalRequest)
            })
          }
          originalRequest._retry = true
          isRefreshing = true
          try {
            const res = await axios.post('/api/auth/refresh')
            const newToken = res.data.access_token
            setToken(newToken)
            localStorage.setItem('token', newToken)
            axios.defaults.headers.common['Authorization'] = `Bearer ${newToken}`
            processQueue(null, newToken)
            originalRequest.headers = originalRequest.headers || {}
            originalRequest.headers['Authorization'] = `Bearer ${newToken}`
            return axios(originalRequest)
          } catch (refreshError) {
            processQueue(refreshError, null)
            setUser(null)
            setToken(null)
            localStorage.removeItem('token')
            delete axios.defaults.headers.common['Authorization']
            return Promise.reject(refreshError)
          } finally {
            isRefreshing = false
          }
        }
        return Promise.reject(error)
      },
    )

    return () => axios.interceptors.response.eject(interceptorId)
  }, [])

  const refreshUser = useCallback(async () => {
    // 不设置 loading=true，避免触发 NeedAuth 卸载子组件导致页面状态丢失
    try {
      const res = await axios.get('/api/me')
      setUser(res.data)
    } catch (error: any) {
      const status = error?.response?.status
      if (status === 401) {
        setToken(null)
        setUser(null)
        localStorage.removeItem('token')
        delete axios.defaults.headers.common['Authorization']
      }
    } finally {
      // 仅在初始加载阶段需要关闭 loading；后续 refresh 不改变 loading 状态
      setLoading(false)
    }
  }, [])

  useEffect(() => { refreshUser() }, [refreshUser])

  const login = async (username: string, password: string) => {
    const res = await axios.post('/api/login', { username, password })
    const at = res.data.access_token
    // 保留 token 在内存中供 Authorization header 使用（向后兼容移动端）
    // Cookie 由后端 Set-Cookie 自动管理
    axios.defaults.headers.common['Authorization'] = `Bearer ${at}`
    localStorage.setItem('token', at)
    setToken(at)
    setUser(res.data.user)
  }

  const register = async (username: string, password: string) => {
    const res = await axios.post('/api/register', { username, password })
    const at = res.data.access_token
    axios.defaults.headers.common['Authorization'] = `Bearer ${at}`
    localStorage.setItem('token', at)
    setToken(at)
    setUser(res.data.user)
  }

  const logout = async () => {
    try { await axios.post('/api/auth/logout') } catch {}
    delete axios.defaults.headers.common['Authorization']
    localStorage.removeItem('token')
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
