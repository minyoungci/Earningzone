import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { createChart } from 'lightweight-charts'
import { chartThemeOptions, watchChartTheme } from '../lib/chartTheme'
import { useApi, getBacktest, getBacktestCompare } from '../api'
import { num, pct, money, signedMoney, retText } from '../lib/format'
import { EASE_OUT } from '../lib/motion'
import GlassCard from '../components/ui/GlassCard'
import StatTile from '../components/ui/StatTile'
import Spinner from '../components/ui/Spinner'

const DEFAULT_SYMBOL = '005930'

const fade = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: EASE_OUT } },
}

// 한국식 등락 색(상승=빨강/하락=파랑) — 차트 라인용 hex
const UP = '#fb7185'
const DOWN = '#38bdf8'

// time 정규화: ISO(분봉)는 unix초로, 'yyyy-mm-dd'(일봉)는 그대로. (CandleChart 와 동일)
const normTime = (t) =>
  typeof t === 'string' && t.includes('T') ? Math.floor(Date.parse(t) / 1000) : t

// lightweight-charts setData 는 '엄격 증가·중복 없는 time' 을 요구한다.
// time 기준 정렬 + 중복 제거(뒤 값 우선). (CandleChart 패턴 재사용)
const sortDedupeByTime = (rows) => {
  const sorted = [...rows].sort((a, b) => a.time - b.time)
  const out = []
  for (const r of sorted) {
    if (out.length && out[out.length - 1].time === r.time) {
      out[out.length - 1] = r
    } else {
      out.push(r)
    }
  }
  return out
}

// 경량 키: equityCurve 길이 + 마지막 time·equity·buyHold (내용 동일 시 재주입 회피)
// 마지막 '값' 포함 — 같은 종목·기간에서 손절%만 바꿔 재실행하면 길이·마지막 time 이
// 동일할 수 있어, 값 변화를 못 보면 이전 실행의 곡선이 그대로 남는다.
const curveKey = (curve) => {
  if (!curve.length) return '0'
  const last = curve[curve.length - 1]
  return `${curve.length}:${last?.time ?? ''}:${last?.equity ?? ''}:${last?.buyHold ?? ''}`
}

/**
 * 에쿼티 커브 라인 차트 — equity(전략) vs buyHold(매수후보유) 비교.
 * curve: [{ time, equity, buyHold }]
 */
function EquityChart({ curve = [], height = 360 }) {
  const ref = useRef(null)
  const chartRef = useRef(null)
  const eqRef = useRef(null)
  const bhRef = useRef(null)
  const [renderError, setRenderError] = useState(false)

  // (a) 차트/시리즈 생성 — height 변화 시에만 재생성
  useEffect(() => {
    if (!ref.current) return
    const chart = createChart(ref.current, {
      height,
      autoSize: true,
      ...chartThemeOptions(),
      timeScale: { ...chartThemeOptions().timeScale, timeVisible: false, secondsVisible: false },
    })
    const stopWatchingTheme = watchChartTheme(chart)
    // 전략 에쿼티: 면적 라인(강조)
    const eq = chart.addAreaSeries({
      lineColor: '#a78bfa',
      topColor: 'rgba(167,139,250,0.28)',
      bottomColor: 'rgba(167,139,250,0.02)',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      crosshairMarkerVisible: true,
    })
    // 매수후보유: 비교용 점선 라인
    const bh = chart.addLineSeries({
      color: 'rgba(148,163,184,0.85)',
      lineWidth: 2,
      lineStyle: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      crosshairMarkerVisible: false,
    })
    chartRef.current = chart
    eqRef.current = eq
    bhRef.current = bh

    let ro = null
    if (typeof ResizeObserver !== 'undefined' && ref.current) {
      ro = new ResizeObserver(() => {
        if (chartRef.current && ref.current) {
          chart.applyOptions({ width: ref.current.clientWidth, height })
        }
      })
      ro.observe(ref.current)
    }

    return () => {
      stopWatchingTheme()
      if (ro) ro.disconnect()
      chart.remove()
      chartRef.current = null
      eqRef.current = null
      bhRef.current = null
    }
  }, [height])

  // (b) 데이터 주입 — curve 경량 키 변화 시 setData
  useEffect(() => {
    const chart = chartRef.current
    const eq = eqRef.current
    const bh = bhRef.current
    if (!chart || !eq || !bh) return
    if (!curve.length) return

    setRenderError(false)
    try {
      eq.setData(
        sortDedupeByTime(
          curve
            .filter((p) => p.equity != null)
            .map((p) => ({ time: normTime(p.time), value: Number(p.equity) })),
        ),
      )
      bh.setData(
        sortDedupeByTime(
          curve
            .filter((p) => p.buyHold != null)
            .map((p) => ({ time: normTime(p.time), value: Number(p.buyHold) })),
        ),
      )
      chart.timeScale().fitContent()
    } catch (e) {
      console.error('EquityChart setData 실패:', e)
      setRenderError(true)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [curveKey(curve)])

  // 컨테이너(ref)는 curve 유무와 무관하게 '항상' 마운트 — 빈 curve 로 early-return 하면
  // 생성 effect(deps [height])가 ref=null 로 끝나 이후 curve 가 채워져도 차트가 안 뜬다.
  return (
    <div style={{ position: 'relative', width: '100%', height }}>
      <div ref={ref} style={{ width: '100%', height }} />
      {!curve.length && (
        <div className="absolute inset-0 flex items-center justify-center text-slate-500 text-sm">
          에쿼티 데이터 없음
        </div>
      )}
      {renderError && (
        <div className="absolute inset-0 flex items-center justify-center text-slate-500 text-sm">
          차트를 표시할 수 없습니다
        </div>
      )}
    </div>
  )
}

// 청산 사유 한글 라벨 + 배지 색
const EXIT_LABEL = { signal: '시그널', stop: '손절', support_break: '지지이탈' }
const exitLabel = (r) => EXIT_LABEL[r] || r || '-'
const exitBg = (r) =>
  r === 'stop'
    ? 'bg-rose-500/15 text-rose-300 border-rose-400/30'
    : r === 'support_break'
    ? 'bg-amber-500/15 text-amber-200 border-amber-400/30'
    : 'bg-slate-500/15 text-slate-300 border-slate-400/30'

// ── 전략 실험실 ─────────────────────────────────────────────────────────────
// 카테고리 키 → 한국어 라벨 (표시 순서 고정 · all=94개 전체 전략 합성)
const LAB_CATEGORIES = [
  ['all', '전체'],
  ['trend', '추세'],
  ['momentum', '모멘텀'],
  ['volatility', '변동성'],
  ['meanrev', '평균회귀'],
  ['breakout', '돌파'],
  ['structure', '구조'],
]

// 응답 모양 방어: 카테고리 결과를 results/categories/최상위 어디서든 찾고,
// 지표는 entry.metrics 또는 entry 자체에서 읽는다 (getBacktest 의 metrics 키와 동일 계약).
const labMetrics = (data, key) => {
  const entry = data?.results?.[key] ?? data?.categories?.[key] ?? data?.[key]
  if (!entry || typeof entry !== 'object') return null
  return entry.metrics && typeof entry.metrics === 'object' ? entry.metrics : entry
}

// best 카테고리 키: 서버가 best/bestCategory 로 알려주면 우선, 없으면 총수익률 최고로 폴백
const labBestKey = (data, rows) => {
  const b = data?.best ?? data?.bestCategory
  const key = typeof b === 'string' ? b : b?.category ?? b?.key
  if (key && rows.some((r) => r.key === key && r.met)) return key
  let bestK = null
  let bestV = -Infinity
  for (const r of rows) {
    const v = r.met?.totalReturnPct
    if (v != null && Number(v) > bestV) { bestV = Number(v); bestK = r.key }
  }
  return bestK
}

/**
 * 전략 실험실 — 동일 종목·기간·손절 조건으로 전략 카테고리별 백테스트를 한 번에 비교.
 * 계산 비용이 커서 자동 호출하지 않고 '전략 비교 실행' 버튼으로만(온디맨드) 트리거한다.
 * 부모에서 params 로 key 를 걸어 종목/기간/손절이 바뀌면 이전 결과를 초기화한다.
 */
function StrategyLab({ symbol, count, stop }) {
  const [status, setStatus] = useState('idle') // idle | loading | done | error
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const seqRef = useRef(0) // 연타/언마운트 후 늦게 도착한 응답 무시용 시퀀스

  const runCompare = () => {
    const seq = ++seqRef.current
    setStatus('loading')
    setError(null)
    getBacktestCompare(symbol, { count, stop })
      .then((d) => {
        if (seqRef.current !== seq) return
        setData(d)
        setStatus('done')
      })
      .catch((e) => {
        if (seqRef.current !== seq) return
        setError(e)
        setStatus('error')
      })
  }

  const rows = LAB_CATEGORIES.map(([key, label]) => ({ key, label, met: labMetrics(data, key) }))
  const bestKey = status === 'done' ? labBestKey(data, rows) : null
  const hasAnyRow = rows.some((r) => r.met)

  return (
    <GlassCard delay={0.2}>
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h3 className="text-lg font-bold">🧪 전략 실험실 — 카테고리별 성과 비교</h3>
          <p className="text-xs text-slate-400 mt-1">
            같은 조건으로 전략군(추세·모멘텀·변동성·평균회귀·돌파·구조)을 각각 백테스트해 비교합니다.
          </p>
        </div>
        <button
          type="button"
          onClick={runCompare}
          disabled={status === 'loading'}
          className="glass-soft px-4 py-2.5 rounded-xl text-sm font-semibold hover:bg-white/10 transition active:scale-[0.97] disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {status === 'loading' ? '비교 실행 중…' : status === 'idle' ? '▶ 전략 비교 실행' : '↻ 다시 비교'}
        </button>
      </div>

      {status === 'idle' && (
        <div className="text-slate-500 text-sm py-6 text-center">
          7가지 전략 구성을 한 번에 백테스트합니다. 계산량이 커서 버튼을 눌렀을 때만 실행돼요.
        </div>
      )}

      {status === 'loading' && <Spinner label="전략 비교 실행 중… (계산량이 많아 다소 걸립니다)" />}

      {status === 'error' && (
        <div className="text-center py-8">
          <div className="text-3xl mb-2">🚫</div>
          <div className="text-rose-300 font-semibold text-sm">
            {error?.message || '전략 비교에 실패했습니다'}
          </div>
          <p className="text-xs text-slate-400 mt-1">잠시 후 다시 시도해 보세요.</p>
        </div>
      )}

      {status === 'done' && !hasAnyRow && (
        <div className="text-slate-500 text-sm py-8 text-center">비교 결과가 비어 있습니다.</div>
      )}

      {status === 'done' && hasAnyRow && (
        <div className="overflow-x-auto mt-4">
          <table className="w-full text-sm min-w-[720px]">
            <thead>
              <tr className="text-slate-400 text-xs border-b border-white/10">
                <th className="text-left py-2 font-medium">전략</th>
                <th className="text-right font-medium">수익률</th>
                <th className="text-right font-medium">승률</th>
                <th className="text-right font-medium">거래수</th>
                <th className="text-right font-medium">MDD</th>
                <th className="text-right font-medium">샤프</th>
                <th className="text-right font-medium">PF</th>
                <th className="text-right font-medium pr-1">노출도</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ key, label, met }) => {
                const isBest = key === bestKey
                return (
                  <tr
                    key={key}
                    className={`border-b border-white/5 transition ${
                      isBest ? 'bg-emerald-500/10 hover:bg-emerald-500/15' : 'hover:bg-white/[0.03]'
                    }`}
                  >
                    <td className="py-2.5 whitespace-nowrap">
                      <span className={isBest ? 'font-semibold text-emerald-200' : 'text-slate-200'}>
                        {label}
                      </span>
                      {key === 'all' && <span className="text-[11px] text-slate-500 ml-1">(94)</span>}
                      {isBest && (
                        <span className="ml-2 text-[11px] px-2 py-0.5 rounded-full border bg-emerald-500/15 text-emerald-300 border-emerald-400/30">
                          이 종목 최적
                        </span>
                      )}
                    </td>
                    <td className={`text-right stat-num ${retText(met?.totalReturnPct)}`}>
                      {pct(met?.totalReturnPct, 2)}
                    </td>
                    <td
                      className={`text-right stat-num ${
                        met?.winRate == null ? '' : met.winRate >= 50 ? 'text-up' : 'text-down'
                      }`}
                    >
                      {pct(met?.winRate, 1)}
                    </td>
                    <td className="text-right stat-num text-slate-300">
                      {met?.numTrades == null ? '-' : `${met.numTrades}회`}
                    </td>
                    <td className="text-right stat-num text-down">
                      {met?.maxDrawdownPct == null ? '-' : pct(-Math.abs(met.maxDrawdownPct), 2)}
                    </td>
                    <td
                      className={`text-right stat-num ${
                        met?.sharpe == null ? '' : met.sharpe >= 1 ? 'text-up' : met.sharpe < 0 ? 'text-down' : ''
                      }`}
                    >
                      {num(met?.sharpe, 2)}
                    </td>
                    <td
                      className={`text-right stat-num ${
                        met?.profitFactor == null ? '' : met.profitFactor >= 1 ? 'text-up' : 'text-down'
                      }`}
                    >
                      {met?.profitFactor == null ? '-' : num(met.profitFactor, 2)}
                    </td>
                    <td className="text-right stat-num text-slate-300 pr-1">{pct(met?.exposurePct, 1)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-[11px] text-slate-500 mt-3">
        ※ 동일 기간·동일 손절 기준, 카테고리 임계는 전략 수 비례 스케일
      </p>
    </GlassCard>
  )
}

export default function Backtest() {
  // 입력(폼) 상태 — 실행 버튼/엔터로만 '확정' 파라미터를 갱신해 불필요한 재호출 방지
  const [symInput, setSymInput] = useState(DEFAULT_SYMBOL)
  const [countInput, setCountInput] = useState('200')
  const [stopInput, setStopInput] = useState('8') // % 단위 입력
  const [intervalInput, setIntervalInput] = useState('1d')

  // 확정 파라미터 — 이 값들이 바뀔 때만 useApi 가 재호출
  const [params, setParams] = useState({
    symbol: DEFAULT_SYMBOL,
    interval: '1d',
    count: 200,
    stop: 0.08,
  })

  const run = () => {
    const sym = (symInput || '').toUpperCase().trim()
    if (!sym) return
    const count = Math.max(70, Math.min(200, parseInt(countInput, 10) || 200))
    const stopPctNum = parseFloat(stopInput)
    const stop = Number.isFinite(stopPctNum) && stopPctNum > 0 ? stopPctNum / 100 : 0.08
    setParams({ symbol: sym, interval: intervalInput, count, stop })
  }

  const { data, err, loading } = useApi(
    () => getBacktest(params.symbol, { interval: params.interval, count: params.count, stop: params.stop }),
    [params.symbol, params.interval, params.count, params.stop],
  )

  const m = data?.metrics || {}
  const trades = data?.trades || []
  const curve = data?.equityCurve || []
  const ccy = data?.currency || 'KRW'

  // 빈 데이터: 에러는 없지만 지표/커브가 사실상 비어 있는 경우
  const isEmpty = !loading && !err && data && curve.length === 0 && trades.length === 0

  // 전략이 매수후보유 대비 초과 성과인지
  const alpha =
    m.totalReturnPct != null && m.buyHoldReturnPct != null ? m.totalReturnPct - m.buyHoldReturnPct : null

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col gap-5 max-w-[1400px] mx-auto">
      {/* 헤더 */}
      <motion.div variants={fade} initial="hidden" animate="show">
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight flex items-center gap-2">
            백테스트
          </h1>
          <span className="text-xs px-2.5 py-1 rounded-full bg-violet-500/15 text-violet-300 border border-violet-400/25 font-mono">
            {params.interval}
          </span>
        </div>
        <p className="text-sm text-slate-400 mt-1">
          과거 데이터로 전략을 검증 · 매수후보유(Buy&amp;Hold)와 비교
        </p>
      </motion.div>

      {/* 컨트롤 바 */}
      <GlassCard delay={0.05} className="!p-4">
        <form
          onSubmit={(e) => { e.preventDefault(); run() }}
          className="grid grid-cols-2 md:grid-cols-5 gap-3 items-end"
        >
          <label className="flex flex-col gap-1 col-span-2 md:col-span-1">
            <span className="text-xs text-slate-400">종목코드</span>
            <input
              value={symInput}
              onChange={(e) => setSymInput(e.target.value.toUpperCase())}
              placeholder="예: 005930, AAPL"
              className="glass-soft w-full px-3 py-2.5 rounded-xl bg-transparent outline-none text-sm stat-num placeholder:text-slate-500"
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-400">기간(봉 수)</span>
            <input
              type="number"
              min={70}
              max={200}
              value={countInput}
              onChange={(e) => setCountInput(e.target.value)}
              className="glass-soft w-full px-3 py-2.5 rounded-xl bg-transparent outline-none text-sm stat-num"
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-400">손절(%)</span>
            <input
              type="number"
              min={0}
              step={0.5}
              value={stopInput}
              onChange={(e) => setStopInput(e.target.value)}
              className="glass-soft w-full px-3 py-2.5 rounded-xl bg-transparent outline-none text-sm stat-num"
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-400">주기</span>
            {/* 토스 캔들은 일봉 기준이 백테스트에 유의미(분봉 200봉은 ~3시간으로 부족). 일봉 고정. */}
            <div className="glass-soft w-full px-3 py-2.5 rounded-xl text-sm text-slate-300 select-none">일봉</div>
          </label>

          <button
            type="submit"
            className="glass-soft px-4 py-2.5 rounded-xl text-sm font-semibold hover:bg-white/10 transition active:scale-[0.97] col-span-2 md:col-span-1"
          >
            ▶ 백테스트 실행
          </button>
        </form>
      </GlassCard>

      {/* 본문: 로딩/에러/빈데이터 3분기 */}
      {loading ? (
        <GlassCard delay={0.1}>
          <Spinner label="백테스트 실행 중…" />
        </GlassCard>
      ) : err ? (
        <GlassCard delay={0.1} className="text-center py-12">
          <div className="text-4xl mb-3">🚫</div>
          <div className="text-rose-300 font-semibold">
            {/* 404 '종목을 찾을 수 없습니다' / 데이터부족 등 백엔드 detail 을 그대로 표기 */}
            {err.message || '백테스트를 불러오지 못했습니다'}
          </div>
          <p className="text-sm text-slate-400 mt-2">종목코드와 기간을 확인하고 다시 실행해 보세요.</p>
        </GlassCard>
      ) : isEmpty ? (
        <GlassCard delay={0.1} className="text-center py-12">
          <div className="text-4xl mb-3">📭</div>
          <div className="text-slate-300 font-semibold">표시할 거래·데이터가 없습니다</div>
          <p className="text-sm text-slate-400 mt-2">
            기간 내 진입 시그널이 없거나 데이터가 부족합니다. 기간을 늘려 보세요.
          </p>
        </GlassCard>
      ) : (
        <>
          {/* 종목 헤더 */}
          <motion.div variants={fade} initial="hidden" animate="show" className="flex items-baseline gap-3 flex-wrap px-1">
            <h2 className="text-lg font-bold">{data?.name || params.symbol}</h2>
            <span className="text-xs text-slate-500 font-mono">{data?.symbol || params.symbol}</span>
            {data?.bars != null && <span className="text-xs text-slate-500">· {data.bars}봉</span>}
            <span className="text-xs text-slate-500">· {ccy === 'USD' ? '달러($)' : '원(₩)'} 기준</span>
          </motion.div>

          {/* 지표 카드 그리드 */}
          <motion.div
            initial="hidden"
            animate="show"
            variants={{ show: { transition: { staggerChildren: 0.03 } } }}
            className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3"
          >
            <Tile
              label="총수익률"
              value={pct(m.totalReturnPct, 2)}
              sub={alpha == null ? null : `매수후보유 ${pct(m.buyHoldReturnPct, 2)}`}
              valueClass={retText(m.totalReturnPct)}
            />
            <Tile
              label="vs 매수후보유"
              value={alpha == null ? '—' : pct(alpha, 2)}
              sub="초과 성과(α)"
              valueClass={retText(alpha)}
            />
            <Tile
              label="최종자산"
              value={money(m.finalEquity, ccy)}
              sub={m.initialCapital == null ? null : `초기 ${money(m.initialCapital, ccy)}`}
            />
            <Tile
              label="거래 수"
              value={m.numTrades == null ? '—' : `${m.numTrades}회`}
              sub={
                m.winningTrades == null
                  ? null
                  : `승 ${m.winningTrades} · 패 ${m.losingTrades ?? 0}`
              }
            />
            <Tile
              label="승률"
              value={m.winRate == null ? '—' : pct(m.winRate, 1)}
              valueClass={m.winRate == null ? '' : m.winRate >= 50 ? 'text-up' : 'text-down'}
            />
            <Tile
              label="최대낙폭(MDD)"
              value={m.maxDrawdownPct == null ? '—' : pct(-Math.abs(m.maxDrawdownPct), 2)}
              valueClass="text-down"
            />
            <Tile
              label="샤프"
              value={num(m.sharpe, 2)}
              valueClass={m.sharpe == null ? '' : m.sharpe >= 1 ? 'text-up' : m.sharpe < 0 ? 'text-down' : ''}
            />
            <Tile
              label="Profit Factor"
              value={m.profitFactor == null ? '—' : num(m.profitFactor, 2)}
              valueClass={m.profitFactor == null ? '' : m.profitFactor >= 1 ? 'text-up' : 'text-down'}
            />
            <Tile
              label="평균 보유봉"
              value={m.avgHoldBars == null ? '—' : `${num(m.avgHoldBars, 1)}봉`}
              sub={
                m.avgWinPct == null && m.avgLossPct == null
                  ? null
                  : `이익 ${pct(m.avgWinPct, 1)} / 손실 ${pct(m.avgLossPct, 1)}`
              }
            />
            <Tile
              label="노출도"
              value={m.exposurePct == null ? '—' : pct(m.exposurePct, 1)}
              sub="보유 시간 비중"
            />
          </motion.div>

          {/* 에쿼티 커브 */}
          <GlassCard delay={0.1}>
            <div className="flex items-baseline justify-between gap-3 mb-3 flex-wrap">
              <h3 className="text-lg font-bold">에쿼티 커브</h3>
              <div className="flex items-center gap-4 text-xs text-slate-400">
                <span className="inline-flex items-center gap-1.5">
                  <span className="inline-block w-3 h-0.5 rounded bg-[#a78bfa]" /> 전략
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="inline-block w-3 h-0.5 rounded bg-slate-400" /> 매수후보유
                </span>
              </div>
            </div>
            <EquityChart curve={curve} height={360} />
          </GlassCard>

          {/* 거래 내역 */}
          <GlassCard delay={0.15}>
            <div className="flex items-baseline justify-between mb-3">
              <h3 className="text-lg font-bold">거래 내역</h3>
              <span className="text-xs text-slate-500 stat-num">{trades.length}건</span>
            </div>
            {trades.length === 0 ? (
              <div className="text-slate-500 text-sm py-8 text-center">기간 내 체결된 거래가 없습니다.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm min-w-[640px]">
                  <thead>
                    <tr className="text-slate-400 text-xs border-b border-white/10">
                      <th className="text-left py-2 font-medium">#</th>
                      <th className="text-left font-medium">진입</th>
                      <th className="text-right font-medium">진입가</th>
                      <th className="text-left font-medium pl-4">청산</th>
                      <th className="text-right font-medium">청산가</th>
                      <th className="text-right font-medium">수익률</th>
                      <th className="text-right font-medium">손익</th>
                      <th className="text-right font-medium">보유</th>
                      <th className="text-right font-medium pr-1">사유</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trades.map((t, i) => (
                      <tr key={i} className="border-b border-white/5 hover:bg-white/[0.03] transition">
                        <td className="py-2.5 text-slate-500 stat-num">{i + 1}</td>
                        <td className="text-slate-300 stat-num whitespace-nowrap">{t.entryTime ?? '-'}</td>
                        <td className="text-right stat-num">{money(t.entryPrice, ccy)}</td>
                        <td className="text-slate-300 stat-num whitespace-nowrap pl-4">{t.exitTime ?? '-'}</td>
                        <td className="text-right stat-num">{money(t.exitPrice, ccy)}</td>
                        <td className={`text-right stat-num ${retText(t.retPct)}`}>{pct(t.retPct, 2)}</td>
                        <td className={`text-right stat-num ${retText(t.pnl)}`}>{signedMoney(t.pnl, ccy)}</td>
                        <td className="text-right stat-num text-slate-400">{t.bars == null ? '-' : `${t.bars}봉`}</td>
                        <td className="text-right pr-1">
                          <span className={`text-[11px] px-2 py-0.5 rounded-full border ${exitBg(t.exitReason)}`}>
                            {exitLabel(t.exitReason)}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </GlassCard>
        </>
      )}

      {/* 전략 실험실 — 온디맨드 카테고리 비교 (자동 호출 금지: 계산 비용 큼) */}
      <StrategyLab
        key={`${params.symbol}:${params.count}:${params.stop}`}
        symbol={params.symbol}
        count={params.count}
        stop={params.stop}
      />

      {/* 디스클레이머 */}
      <div className="text-xs text-amber-300/90 text-center px-2 pt-1">
        ⚠️ 과거 성과가 미래를 보장하지 않습니다 · 교육용
      </div>
    </motion.div>
  )
}

function Tile({ label, value, sub, valueClass }) {
  return (
    <motion.div variants={fade}>
      <StatTile label={label} value={value} sub={sub} valueClass={valueClass} />
    </motion.div>
  )
}
