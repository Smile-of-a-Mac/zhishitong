/**
 * 政策问答 AI 助手悬浮面板
 * 右下角悬浮按钮 → 点击展开聊天窗口
 *
 * 功能：
 *   - 仅登录用户可见
 *   - 聊天记录按用户 ID 隔离，持久化在 localStorage
 */
import React, { useState, useRef, useEffect, useCallback } from 'react'
import axios from 'axios'
import { useAuth } from '../hooks/useAuth'

interface ChatMsg {
  role: 'user' | 'assistant'
  content: string
  sources?: { doc_title: string; text: string }[]
}

const WELCOME: ChatMsg = {
  role: 'assistant',
  content: '你好！我是智审通政策助手，可以帮你解答各类审批政策问题。',
}

const SUGGESTED: string[] = [
  '报销需要什么材料？',
  '请假超过3天怎么办？',
  '差旅住宿费标准是多少？',
  '社团活动如何申请场地？',
]

/* ─── localStorage 工具 ─── */
const STORAGE_PREFIX = 'zhishitong_chat_'

function storageKey(userId: number) {
  return `${STORAGE_PREFIX}${userId}`
}

function loadMessages(userId: number): ChatMsg[] {
  try {
    const raw = localStorage.getItem(storageKey(userId))
    if (raw) {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed) && parsed.length > 0) return parsed
    }
  } catch { /* ignore */ }
  return [WELCOME]
}

function saveMessages(userId: number, msgs: ChatMsg[]) {
  try {
    localStorage.setItem(storageKey(userId), JSON.stringify(msgs))
  } catch { /* ignore quota */ }
}

export default function AIChatPanel() {
  const { user } = useAuth()

  // ---- 按用户 ID 加载/切换聊天记录 ----
  const [messages, setMessages] = useState<ChatMsg[]>([WELCOME])

  // 用户切换时重新加载
  useEffect(() => {
    if (user?.id) {
      setMessages(loadMessages(user.id))
    } else {
      setMessages([WELCOME])
    }
  }, [user?.id])

  // 消息变更时自动保存（只在用户登录时）
  useEffect(() => {
    if (user?.id && messages.length > 0) {
      saveMessages(user.id, messages)
    }
  }, [messages, user?.id])

  const [open, setOpen] = useState(false)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, open])

  // ---- 未登录不渲染 ----
  if (!user) return null

  const send = async (text: string) => {
    const q = text || input.trim()
    if (!q || loading) return
    setInput('')

    const newMsg: ChatMsg = { role: 'user', content: q }
    const nextHistory = [...messages, newMsg]
    setMessages(nextHistory)
    setLoading(true)

    try {
      const res = await axios.post('/api/ai/chat', {
        question: q,
        history: nextHistory.slice(-6).map(m => ({ role: m.role, content: m.content })),
      })
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: res.data.answer || '暂时无法回答，请联系相关部门。',
          sources: res.data.sources || [],
        },
      ])
    } catch {
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: '服务暂时不可用，请稍后重试。' },
      ])
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      {/* ── 悬浮按钮 ── */}
      <button
        onClick={() => setOpen(v => !v)}
        style={{
          position: 'fixed',
          bottom: 24,
          right: 24,
          width: 52,
          height: 52,
          borderRadius: '50%',
          background: 'var(--accent-color, #007aff)',
          border: 'none',
          color: '#fff',
          fontSize: 22,
          cursor: 'pointer',
          boxShadow: '0 4px 20px rgba(0,122,255,0.4)',
          zIndex: 999,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          transition: 'transform 0.2s ease, box-shadow 0.2s ease',
        }}
        title="政策助手"
        onMouseEnter={e => {
          ;(e.currentTarget as HTMLButtonElement).style.transform = 'scale(1.1)'
          ;(e.currentTarget as HTMLButtonElement).style.boxShadow =
            '0 6px 28px rgba(0,122,255,0.55)'
        }}
        onMouseLeave={e => {
          ;(e.currentTarget as HTMLButtonElement).style.transform = 'scale(1)'
          ;(e.currentTarget as HTMLButtonElement).style.boxShadow =
            '0 4px 20px rgba(0,122,255,0.4)'
        }}
      >
        {open ? '✕' : '🤖'}
      </button>

      {/* ── 聊天窗口（始终渲染，用 CSS transition 控制动画） ── */}
      <div
        style={{
          position: 'fixed',
          bottom: 88,
          right: 24,
          width: 340,
          maxHeight: 520,
          display: 'flex',
          flexDirection: 'column',
          background: 'var(--glass-bg, rgba(255,255,255,0.85))',
          backdropFilter: 'blur(25px) saturate(180%)',
          WebkitBackdropFilter: 'blur(25px) saturate(180%)',
          border: '1px solid var(--glass-border, rgba(255,255,255,0.5))',
          borderRadius: 18,
          boxShadow: open ? '0 8px 40px rgba(0,0,0,0.15)' : '0 2px 8px rgba(0,0,0,0)',
          zIndex: 998,
          overflow: 'hidden',
          pointerEvents: open ? 'auto' : 'none',
          opacity: open ? 1 : 0,
          transform: open ? 'translateY(0) scale(1)' : 'translateY(16px) scale(0.95)',
          transition: 'opacity 0.3s cubic-bezier(0.34, 1.56, 0.64, 1), transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.3s ease',
        }}
      >
          {/* 头部 */}
          <div
            style={{
              padding: '12px 16px',
              borderBottom: '1px solid var(--divider, rgba(60,60,67,0.1))',
              fontWeight: 600,
              fontSize: 14,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              flexShrink: 0,
            }}
          >
            <span style={{ fontSize: 18 }}>🤖</span>
            <span>政策智能助手</span>
            <span
              style={{
                marginLeft: 'auto',
                fontSize: 11,
                background: 'rgba(52,199,89,0.12)',
                padding: '2px 8px',
                borderRadius: 20,
                color: '#34C759',
              }}
            >
              RAG 知识库
            </span>
            <button
              onClick={() => {
                setMessages([WELCOME])
                if (user?.id) localStorage.removeItem(storageKey(user.id))
              }}
              style={{
                fontSize: 11,
                background: 'rgba(120,120,128,0.1)',
                border: 'none',
                borderRadius: 12,
                padding: '2px 8px',
                color: 'var(--text-secondary)',
                cursor: 'pointer',
              }}
              title="清空聊天记录"
            >
              🗑️
            </button>
          </div>

          {/* 消息列表 */}
          <div
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: '12px 12px 4px',
              display: 'flex',
              flexDirection: 'column',
              gap: 8,
            }}
          >
            {messages.map((msg, i) => (
              <div
                key={i}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
                  gap: 4,
                }}
              >
                <div
                  className={msg.role === 'assistant' ? 'ai-chat-assistant-bubble' : undefined}
                  style={{
                    maxWidth: '88%',
                    padding: '8px 12px',
                    borderRadius: msg.role === 'user' ? '14px 14px 4px 14px' : '14px 14px 14px 4px',
                    background:
                      msg.role === 'user'
                        ? 'var(--accent-color, #007aff)'
                        : 'rgba(120,120,128,0.1)',
                    color: msg.role === 'user' ? '#fff' : 'var(--text-primary)',
                    fontSize: 13,
                    lineHeight: 1.5,
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {msg.content}
                </div>
                {/* 来源引用 */}
                {msg.sources && msg.sources.length > 0 && (
                  <div style={{ maxWidth: '88%', display: 'flex', flexDirection: 'column', gap: 3 }}>
                    {msg.sources.map((s, si) => (
                      <div
                        key={si}
                        style={{
                          fontSize: 11,
                          color: 'var(--text-secondary)',
                          background: 'rgba(0,122,255,0.06)',
                          border: '1px solid rgba(0,122,255,0.12)',
                          borderRadius: 8,
                          padding: '3px 8px',
                        }}
                        title={s.text}
                      >
                        📄 {s.doc_title}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}

            {/* 加载指示 */}
            {loading && (
              <div style={{ alignSelf: 'flex-start', padding: '8px 12px', fontSize: 13, color: 'var(--text-secondary)' }}>
                <span style={{ animation: 'pulse 1.2s infinite' }}>💭 思考中...</span>
              </div>
            )}

            {/* 快捷建议（首屏） */}
            {messages.length === 1 && !loading && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 4 }}>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>快速提问：</div>
                {SUGGESTED.map(s => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    style={{
                      textAlign: 'left',
                      padding: '6px 10px',
                      fontSize: 12,
                      background: 'rgba(0,122,255,0.07)',
                      border: '1px solid rgba(0,122,255,0.15)',
                      borderRadius: 10,
                      cursor: 'pointer',
                      color: 'var(--accent-color, #007aff)',
                    }}
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}

            <div ref={bottomRef} />
          </div>

          {/* 输入区 */}
          <div
            style={{
              padding: '8px 12px 12px',
              borderTop: '1px solid var(--divider)',
              display: 'flex',
              gap: 8,
              flexShrink: 0,
            }}
          >
            <input
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  send(input)
                }
              }}
              placeholder="输入政策问题..."
              style={{
                flex: 1,
                padding: '7px 12px',
                borderRadius: 20,
                border: '1px solid var(--glass-border)',
                background: 'rgba(120,120,128,0.08)',
                fontSize: 13,
                outline: 'none',
                color: 'var(--text-primary)',
              }}
            />
            <button
              onClick={() => send(input)}
              disabled={loading || !input.trim()}
              style={{
                width: 36,
                height: 36,
                borderRadius: '50%',
                background: loading || !input.trim() ? 'rgba(120,120,128,0.2)' : 'var(--accent-color, #007aff)',
                border: 'none',
                color: '#fff',
                fontSize: 16,
                cursor: loading || !input.trim() ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
                transition: 'background 0.2s',
              }}
            >
              ↑
            </button>
          </div>
        </div>
    </>
  )
}
