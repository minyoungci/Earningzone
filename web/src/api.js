// tossbot 백엔드(FastAPI) 호출 + 데이터 훅. (vite proxy: /api → :8000)
import { useEffect, useRef, useState } from 'react'

import { fetchJson } from './lib/http'

export const getHealth = () => fetchJson('/api/health')
// 토스 연결 자가진단 — {ok, stage, publicIp, message}. 처음 실행 시 설정 배너용.
export const getSelftest = () => fetchJson('/api/selftest')
// 쓰기 게이트 상태 — {gate: ACCESS_TOKEN 설정 여부, ok: 게이트 OFF 이거나 토큰 유효}
export const getAuth = () => fetchJson('/api/auth')
// 데스크톱 앱: 토스 키 저장 상태(값 비노출) / OS 키체인에 저장 + 런타임 즉시 반영
export const getKeysStatus = () => fetchJson('/api/settings/keys')
export const saveKeys = (client_id, client_secret) =>
  fetchJson('/api/settings/keys', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ client_id, client_secret }),
  })
// market: 'kr' | 'us' — 기존 getWatchlist() 호출 하위호환(기본 kr)
export const getWatchlist = (market = 'kr') => fetchJson(`/api/watchlist?market=${market}`)
export const getScreener = () => fetchJson('/api/screener')
export const getAnalysis = (symbol, name = '') =>
  fetchJson(`/api/analyze/${symbol}?name=${encodeURIComponent(name)}`)
export const getCandles = (symbol, interval = '1d', count = 200) =>
  fetchJson(`/api/candles/${symbol}?interval=${interval}&count=${count}`)
export const getBacktest = (symbol, { interval = '1d', count = 200, stop = 0.08, capital = 10000000 } = {}) =>
  fetchJson(`/api/backtest/${symbol}?interval=${interval}&count=${count}&stop=${stop}&capital=${capital}`)
export const getIntraday = (symbol, name = '') =>
  fetchJson(`/api/intraday/${symbol}?name=${encodeURIComponent(name)}`)
export const getPortfolio = () => fetchJson('/api/portfolio')

// 종목 검색 + 모의투자
export const searchStocks = (q) => fetchJson(`/api/search?q=${encodeURIComponent(q)}`)
export const getSim = () => fetchJson('/api/sim/state')
// note: 매매 근거 메모(선택) — 매매 저널에 함께 기록된다. 기존 4인자 호출 하위호환.
export const placeOrder = (symbol, side, qty, name = '', note = '') =>
  fetchJson('/api/sim/order', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol, side, qty, name, note }),
  })
// 자동매매 실행 브로커 (toss | kis) — 분석은 공유, 주문 실행만 전환
export const getBroker = () => fetchJson('/api/broker')
export const selectBroker = (broker) =>
  fetchJson('/api/broker/select', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ broker }),
  })
export const resetSim = (cash = null) =>
  fetchJson('/api/sim/reset', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cash }),
  })

// 모의투자 다중 계좌 — 목록/생성/선택/삭제 (state·order·reset 은 활성 계좌 대상)
export const getSimAccounts = () => fetchJson('/api/sim/accounts')
export const createSimAccount = (name, cash = 10000000) =>
  fetchJson('/api/sim/accounts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, cash }),
  })
export const selectSimAccount = (id) =>
  fetchJson('/api/sim/accounts/select', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id }),
  })
export const deleteSimAccount = (id) =>
  fetchJson(`/api/sim/accounts/${encodeURIComponent(id)}`, { method: 'DELETE' })

// 퀀트 종목 발굴 + 전략 카테고리 비교 백테스트
// market: 'kr' | 'us' | 'all' — 기존 getQuant(top) 호출 하위호환(기본 kr)
export const getQuant = (top = 10, market = 'kr') =>
  fetchJson(`/api/quant?top=${top}&market=${market}`)
export const getQuantPlan = (symbol, name = '') =>
  fetchJson(`/api/quant/plan/${symbol}?name=${encodeURIComponent(name)}`)
export const getBacktestCompare = (symbol, { count = 200, stop = 0.08 } = {}) =>
  fetchJson(`/api/backtest/${symbol}/compare?count=${count}&stop=${stop}`)

// 오토파일럿 (모의투자 전용 자동매매 루프)
export const getAutopilot = () => fetchJson('/api/autopilot')
export const startAutopilot = (opts = {}) =>
  fetchJson('/api/autopilot/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(opts),
  })
export const stopAutopilot = () =>
  fetchJson('/api/autopilot/stop', { method: 'POST' })
// 오토파일럿 로그/에러만 비움 — 보유 종목의 목표/손절 계획은 유지
export const resetAutopilotLogs = () =>
  fetchJson('/api/autopilot/reset', { method: 'POST' })

// 마켓 페이지 (리스크 레짐 · 매크로 보드 · 뉴스 · 캘린더) + 매매 저널 + 알림
export const getChartStudy = (symbol, interval = '1d', span = 3, basis = 'wick') =>
  fetchJson(`/api/chart-study/${encodeURIComponent(symbol)}?interval=${interval}&span=${span}&basis=${basis}`)
export const getChartTiming = (symbol) => fetchJson(`/api/chart-timing/${encodeURIComponent(symbol)}`)
export const getFinancialLibrary = (q = '') => fetchJson(`/api/financial/library?q=${encodeURIComponent(q)}`)
export const getFinancialDocument = (key) => fetchJson(`/api/financial/documents/${encodeURIComponent(key)}`)
export const getRegime = () => fetchJson('/api/regime')
export const getMacro = () => fetchJson('/api/macro')
export const getNews = () => fetchJson('/api/news')
export const getCalendar = (days = 7) => fetchJson(`/api/calendar?days=${days}`)
export const getJournal = () => fetchJson('/api/journal')
export const getNotifyStatus = () => fetchJson('/api/notify')
export const testNotify = () => fetchJson('/api/notify/test', { method: 'POST' })

// 범용 데이터 훅: const {data, err, loading, reload} = useApi(() => getWatchlist(), [])
//   폴링 예: useApi(() => getIntraday(sel, name), [sel, name], { pollMs: 15000 })
//   - loading 은 '데이터가 아직 없을 때만' true (최초 마운트만 스피너).
//   - reload()/폴링 재호출은 data 가 이미 있으면 백그라운드 갱신(화면 유지, 깜빡임 없음).
//   - 폴링 에러 시 기존 data 를 유지하고 err 만 갱신.
//   - deps(파라미터)가 바뀌면 이전 data 를 리셋하고 스피너를 다시 띄운다
//     (이전 파라미터의 결과가 새 결과로 오인되는 것 방지 — 예: 백테스트 재실행).
//   - 이전 요청이 미완료면 폴링 틱을 스킵(인플라이트 가드)하고,
//     요청 시퀀스로 늦게 도착한 옛 응답이 새 응답을 덮어쓰지 않게 한다.
//   - document.hidden 이면 폴링을 건너뛴다.
//   - 2인자 호출 useApi(fn, deps) 하위호환 유지.
export function useApi(fn, deps = [], opts = {}) {
  const { pollMs } = opts
  const fnRef = useRef(fn)
  fnRef.current = fn
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [loading, setLoading] = useState(true)
  const [tick, setTick] = useState(0)
  // 최신 data 를 effect 의존성에 넣지 않고 참조하기 위해 ref 로 추적.
  const dataRef = useRef(null)
  useEffect(() => { dataRef.current = data }, [data])
  // deps 직렬화 키 — '파라미터 변경'과 'reload()/pollMs 변경'을 구분하기 위해 추적.
  const depsKeyRef = useRef(null)
  // 요청 시퀀스 — 최신 요청의 응답만 반영(out-of-order 경합 방지).
  const seqRef = useRef(0)

  useEffect(() => {
    let alive = true
    // 파라미터(deps)가 바뀐 재실행이면 이전 데이터를 리셋해 스피너를 다시 띄운다.
    // reload()/pollMs 변경은 deps 키가 그대로라 리셋되지 않음(백그라운드 갱신 유지).
    const depsKey = JSON.stringify(deps)
    if (depsKeyRef.current !== null && depsKeyRef.current !== depsKey) {
      dataRef.current = null
      setData(null)
      setErr(null)
    }
    depsKeyRef.current = depsKey

    // 인플라이트 가드 — 이전 요청이 미완료면 이번 틱을 스킵(느린 응답 시 요청 적체 방지).
    // effect 스코프 로컬이라 deps 변경/reload 로 effect 가 새로 돌면 가드도 초기화된다.
    let inFlight = false
    // data 가 아직 없을 때만 스피너. 이후 reload/폴링은 백그라운드 갱신.
    const run = () => {
      if (!alive || inFlight) return
      inFlight = true
      const seq = ++seqRef.current
      const hasData = dataRef.current != null
      if (!hasData) setLoading(true)
      Promise.resolve().then(() => fnRef.current())
        .then((d) => {
          inFlight = false
          if (!alive || seq !== seqRef.current) return
          dataRef.current = d
          setData(d); setErr(null); setLoading(false)
        })
        .catch((e) => {
          inFlight = false
          if (!alive || seq !== seqRef.current) return
          // 폴링/백그라운드 에러 시 기존 data 는 유지하고 err 만 갱신.
          setErr(e); setLoading(false)
        })
    }
    run()

    let id = null
    if (pollMs) {
      id = setInterval(() => {
        // 탭이 백그라운드면 폴링 스킵.
        if (typeof document !== 'undefined' && document.hidden) return
        run()
      }, pollMs)
    }
    const wake = () => { if (!document.hidden) run() }
    const changed = () => setTick((t) => t + 1)
    window.addEventListener('focus', wake)
    document.addEventListener('visibilitychange', wake)
    window.addEventListener('tossbot:updated', changed)
    return () => {
      alive = false
      if (id) clearInterval(id)
      window.removeEventListener('focus', wake)
      document.removeEventListener('visibilitychange', wake)
      window.removeEventListener('tossbot:updated', changed)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick, pollMs])
  return { data, err, loading, reload: () => setTick((t) => t + 1) }
}
