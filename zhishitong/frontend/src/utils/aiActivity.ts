import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios'

const AI_ACTIVITY_EVENT = 'zhishitong:ai-activity'
const AI_REQUEST_MARK = '__zhishitongAiTracked'

type TrackedConfig = InternalAxiosRequestConfig & { [AI_REQUEST_MARK]?: boolean }

let activeCount = 0
let installed = false

const AI_ENDPOINTS = [
  // 政策问答 /api/ai/chat 不触发背景动画（只在 OCR 和审批时触发）
  /^\/api\/ocr(?:\?|$)/,
  /^\/api\/ai\/(?:intent|manual-compliance|compliance\/\d+|opinion)(?:\?|$)/,
  /^\/api\/approvals\/suggest-review(?:\?|$)/,
  /^\/api\/approvals\/manual(?:\?|$)/,
  /^\/api\/approvals\/\d+\/resubmit(?:\?|$)/,
]

function normalizeUrl(url?: string) {
  if (!url) return ''
  try {
    return new URL(url, window.location.origin).pathname + new URL(url, window.location.origin).search
  } catch {
    return url
  }
}

function isAiRequest(url?: string) {
  const normalized = normalizeUrl(url)
  return AI_ENDPOINTS.some(pattern => pattern.test(normalized))
}

function emitAiActivity() {
  window.dispatchEvent(
    new CustomEvent(AI_ACTIVITY_EVENT, {
      detail: { active: activeCount > 0, count: activeCount },
    }),
  )
}

function beginAiRequest(config: TrackedConfig) {
  if (!isAiRequest(config.url) || config[AI_REQUEST_MARK]) return config
  config[AI_REQUEST_MARK] = true
  activeCount += 1
  emitAiActivity()
  return config
}

function endAiRequest(config?: TrackedConfig) {
  if (!config?.[AI_REQUEST_MARK]) return
  config[AI_REQUEST_MARK] = false
  activeCount = Math.max(0, activeCount - 1)
  emitAiActivity()
}

export function setupAiActivityTracking() {
  if (installed) return
  installed = true

  axios.interceptors.request.use(config => beginAiRequest(config as TrackedConfig))
  axios.interceptors.response.use(
    response => {
      endAiRequest(response.config as TrackedConfig)
      return response
    },
    (error: AxiosError) => {
      endAiRequest(error.config as TrackedConfig | undefined)
      return Promise.reject(error)
    },
  )
}

export function addAiActivityListener(listener: (active: boolean, count: number) => void) {
  const handler = (event: Event) => {
    const detail = (event as CustomEvent<{ active: boolean; count: number }>).detail
    listener(!!detail?.active, detail?.count ?? 0)
  }
  window.addEventListener(AI_ACTIVITY_EVENT, handler)
  listener(activeCount > 0, activeCount)
  return () => window.removeEventListener(AI_ACTIVITY_EVENT, handler)
}
