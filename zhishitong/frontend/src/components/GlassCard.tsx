import React from 'react'

interface GlassCardProps {
  children: React.ReactNode
  className?: string
  strong?: boolean
  size?: 'md' | 'sm' | 'xs'
  style?: React.CSSProperties
  as?: 'div' | 'section' | 'article' | 'form'
  onClick?: (e: React.MouseEvent) => void
}

/**
 * 玻璃拟态卡片组件
 * - hover 时悬浮亮起效果（轻微上浮 + 边框光晕）
 * - 无鼠标坐标跟踪
 */
export default function GlassCard({
  children,
  className = '',
  strong = false,
  size = 'md',
  style,
  as: Tag = 'div',
  onClick,
}: GlassCardProps) {
  const sizeClass = size === 'sm' ? 'glass-card-sm' : size === 'xs' ? 'glass-card-xs' : ''

  return (
    <Tag
      className={`glass-card ${strong ? 'glass-card-strong' : ''} ${sizeClass} ${className}`}
      style={style}
      onClick={onClick}
    >
      {children}
    </Tag>
  )
}
