// Deduplicate reads in progress; writes invalidate those reads immediately.
const reads = new Map()

async function requestJson(url, opts = {}) {
  const { timeoutMs, signal, ...init } = opts
  const controller = new AbortController()
  const abort = () => controller.abort()
  if (signal?.aborted) abort()
  signal?.addEventListener('abort', abort, { once: true })
  const limit = timeoutMs ?? (/^\/api\/(quant(?:\?|$)|screener|calendar)/.test(url) ? 180000 : 30000)
  const timer = setTimeout(abort, limit)
  try {
    let response
    try {
      response = await fetch(url, { ...init, signal: controller.signal })
    } catch {
      throw new Error(controller.signal.aborted ? '응답 대기 시간이 초과되었습니다. 다시 시도하세요' : '서버에 연결할 수 없습니다')
    }
    let data
    try { data = await response.json() } catch {
      throw new Error('요청 처리 중 오류가 발생했습니다')
    }
    if (!response.ok) {
      const detail = typeof data?.detail === 'string' ? data.detail : null
      throw new Error(detail || (response.status === 422 ? '입력값을 확인해 주세요' : `요청 처리 중 오류가 발생했습니다 (HTTP ${response.status})`))
    }
    if ((init.method || 'GET').toUpperCase() !== 'GET') {
      reads.clear()
      if (typeof window !== 'undefined') window.dispatchEvent(new Event('tossbot:updated'))
    }
    return data
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', abort)
  }
}

export function fetchJson(url, opts = {}) {
  const headers = new Headers(opts.headers)
  try {
    const token = localStorage.getItem('tossbot-token')
    if (token) headers.set('X-Access-Token', token)
  } catch { /* Local storage can be unavailable in a webview. */ }
  const init = { ...opts, headers }
  if ((opts.method || 'GET').toUpperCase() !== 'GET' || opts.signal) return requestJson(url, init)
  const key = JSON.stringify([url, [...headers.entries()], opts.timeoutMs])
  if (reads.has(key)) return reads.get(key)
  const pending = requestJson(url, init).finally(() => {
    if (reads.get(key) === pending) reads.delete(key)
  })
  reads.set(key, pending)
  return pending
}
