/**
 * 共享 API 工具函数
 */
import axios from 'axios'

/** 统一解析 API 错误信息 */
export function parseApiError(error: any, fallback = '请求失败'): string {
  const detail = error?.response?.data?.detail
  if (!detail) return fallback
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((d: any) => d?.msg || d?.message || JSON.stringify(d)).join('；')
  }
  try {
    return JSON.stringify(detail)
  } catch {
    return fallback
  }
}

/** 请求失败时弹出错误提示 */
export function alertApiError(error: any, fallback = '操作失败') {
  alert(parseApiError(error, fallback))
}
