import React, { useEffect, useState } from 'react'
import axios from 'axios'

interface AuthImageProps {
  src: string
  alt?: string
  className?: string
  style?: React.CSSProperties
  onClick?: (e: React.MouseEvent) => void
}

/**
 * 带认证的图片组件 — 通过 axios 获取受保护的图片资源
 */
export default function AuthImage({ src, alt, className, style, onClick }: AuthImageProps) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (!src) return
    let cancelled = false
    setError(false)
    setBlobUrl(null)

    axios.get(src, { responseType: 'blob' })
      .then(res => {
        if (!cancelled) {
          const url = URL.createObjectURL(res.data)
          setBlobUrl(url)
        }
      })
      .catch(() => {
        if (!cancelled) setError(true)
      })

    return () => {
      cancelled = true
      if (blobUrl) URL.revokeObjectURL(blobUrl)
    }
  }, [src])

  if (error) {
    return (
      <div style={{
        ...style,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'var(--glass-bg)', border: '1px solid var(--glass-border)',
        borderRadius: 'var(--radius-xs)', color: 'var(--text-tertiary)', fontSize: 13,
        minHeight: 120,
      }}>
        图片加载失败
      </div>
    )
  }

  if (!blobUrl) {
    return (
      <div style={{
        ...style,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'var(--glass-bg)', border: '1px solid var(--glass-border)',
        borderRadius: 'var(--radius-xs)', color: 'var(--text-tertiary)', fontSize: 13,
        minHeight: 120,
      }}>
        加载中…
      </div>
    )
  }

  return (
    <img src={blobUrl} alt={alt} className={className} style={style} onClick={onClick} />
  )
}
