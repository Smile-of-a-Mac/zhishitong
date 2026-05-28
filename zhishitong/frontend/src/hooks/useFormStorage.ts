import { useState, useEffect } from 'react'

const STORAGE_PREFIX = 'zhishitong'

/**
 * 通用的表单数据自动保存/恢复 Hook。
 * 使用 sessionStorage，按 userId + key 隔离。
 */
export function useFormStorage<T extends Record<string, string>>(
  userId: string | number | undefined,
  key: string,
  initialValue: T = {} as T,
) {
  const storageKey = `${STORAGE_PREFIX}_${userId ?? 'guest'}_${key}`

  const [data, setData] = useState<T>(() => {
    try {
      const raw = sessionStorage.getItem(storageKey)
      if (raw) {
        const saved = JSON.parse(raw)
        if (saved?.key === key && saved?.userId === userId) {
          return saved.data as T
        }
      }
    } catch {}
    return initialValue
  })

  // 数据变化时自动保存
  useEffect(() => {
    if (Object.keys(data).length > 0) {
      try {
        sessionStorage.setItem(storageKey, JSON.stringify({ key, userId, data }))
      } catch {}
    }
  }, [data, storageKey, key, userId])

  /** 清除持久化数据 */
  const clear = () => {
    try { sessionStorage.removeItem(storageKey) } catch {}
    setData(initialValue)
  }

  return { data, setData, clear }
}
