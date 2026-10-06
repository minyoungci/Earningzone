import { useState, useEffect } from 'react'
import { Link, useParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { EASE_OUT } from '../lib/motion'
import { useApi, getAnalysis } from '../api'
import { money, pct, num, retText, actionText, actionLabel } from '../lib/format'
import GlassCard from '../components/ui/GlassCard'
import Badge from '../components/ui/Badge'
import Gauge from '../components/ui/Gauge'
import Spinner from '../components/ui/Spinner'
import StatTile from '../components/ui/StatTile'
import ChartWorkbench from '../components/ChartWorkbench'
import ChartTiming from '../components/ChartTiming'
import IndicatorGrid from '../components/IndicatorGrid'
import SignalBoard from '../components/SignalBoard'
import LevelBar from '../components/LevelBar'

// 구조 라벨
const structLabel = (s) =>
  ({ uptrend: '상승추세', downtrend: '하락추세', range: '횡보' }[s] || s || '-')

const structTone = (s) =>
  s === 'uptrend' ? 'text-up' : s === 'downtrend' ? 'text-down' : 'text-slate-300'

const biasTone = (b) =>
  b === 'bullish' || b === 'bull'
    ? 'text-emerald-300'
    : b === 'bearish' || b === 'bear'
    ? 'text-rose-300'
    : 'text-slate-300'

const biasLabel = (b) =>
  ({ bullish: '강세', bull: '강세', bearish: '약세', bear: '약세' }[b] || b || '중립')

// 에러 메시지에서 detail 문자열을 안전하게 추출
const errMsg = (e) => String(e?.message || e || '').trim()

// 백엔드가 404로 '종목을 찾을 수 없습니다' detail을 주거나, HTTP 404 폴백인 경우를 404류로 본다.
// (status가 에러 객체에 실리지 않아 메시지 내용으로 판별)
const isNotFound = (e) => {
  const m = errMsg(e)
  return m.includes('종목을 찾을 수 없') || m.includes('찾을 수 없') || /\b404\b/.test(m)
}

export default function SymbolDetail() {
  const { symbol } = useParams()
  // 실시간: 분석은 10초, 캔들은 30초마다 백그라운드 자동 갱신(화면 깜빡임 없음)
  const a = useApi(() => getAnalysis(symbol), [symbol], { pollMs: 10000 })
  const data = a.data
  const agg = data?.aggregate || {}
  const ret = data?.ret || {}

  // 마지막 실시간 갱신 시각(데이터가 새로 들어올 때마다 기록)
  const [updatedAt, setUpdatedAt] = useState(null)
  useEffect(() => {
    if (data) setUpdatedAt(new Date())
  }, [data])

  // 로딩
  if (a.loading && !data) {
    return (
      <div className="max-w-7xl mx-auto">
        <BackLink />
        <GlassCard className="mt-4">
          <Spinner label={`${symbol} 분석 불러오는 중…`} />
        </GlassCard>
      </div>
    )
  }

  // 에러: 404류(종목 없음)는 친절한 안내, 그 외(서버오류)는 detail 그대로 노출
  if (a.err) {
    const notFound = isNotFound(a.err)
    return (
      <div className="max-w-7xl mx-auto">
        <BackLink />
        <GlassCard className="mt-4">
          {notFound ? (
            <>
              <div className="text-slate-200 font-semibold mb-1">검색 결과가 없습니다</div>
              <div className="text-sm text-slate-400">
                ‘{symbol}’ 종목을 찾을 수 없어요. 종목 코드를 다시 확인해 주세요.
              </div>
            </>
          ) : (
            <>
              <div className="text-rose-300 font-semibold mb-1">분석을 불러오지 못했습니다</div>
              <div className="text-sm text-slate-400">{errMsg(a.err) || '서버 오류가 발생했어요.'}</div>
            </>
          )}
          <button
            onClick={a.reload}
            className="mt-3 px-4 py-2 rounded-2xl glass-soft glass-hover text-sm"
          >
            다시 시도
          </button>
        </GlassCard>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="max-w-7xl mx-auto">
        <BackLink />
        <GlassCard className="mt-4">
          <div className="text-slate-400 text-sm">데이터가 없습니다.</div>
        </GlassCard>
      </div>
    )
  }

  const r1 = ret['1']
  const action = agg.action || 'HOLD'
  const div = data.divergence || {}
  const candlePatterns = data.candlePatterns || []
  const chartPatterns = data.chartPatterns || []

  return (
    <div className="max-w-7xl mx-auto flex flex-col gap-5">
      <BackLink />

      {/* 헤더 */}
      <GlassCard className="!p-6">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-5">
          <div className="min-w-0">
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-white truncate">
                {data.name || symbol}
              </h1>
              <span className="text-xs text-slate-500 font-mono">{symbol}</span>
              <span className={`text-sm font-semibold ${structTone(data.structure)}`}>
                {structLabel(data.structure)}
              </span>
            </div>
            <div className="flex items-end gap-3 mt-2">
              <span className="stat-num text-3xl text-white">{money(data.price, data.currency)}</span>
              <span className={`text-base font-bold tabular-nums ${retText(r1)}`}>
                {r1 == null ? '' : pct(r1, 2)}
              </span>
            </div>
            <div className="flex items-center gap-2 mt-2 text-[11px] text-slate-400">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-400" />
              </span>
              <span>
                실시간 갱신 중
                {updatedAt ? ` · ${updatedAt.toLocaleTimeString('ko-KR')}` : ''}
              </span>
              <button
                onClick={() => { a.reload(); c.reload() }}
                className="ml-1 px-2 py-0.5 rounded-full glass-soft glass-hover"
              >
                새로고침
              </button>
            </div>
          </div>

          {/* 종합 점수 */}
          <div className="w-full lg:w-80 shrink-0">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-slate-400">종합 시그널</span>
              <Badge action={action} />
            </div>
            <Gauge score={agg.total} max={10} />
            <div className="flex items-center justify-between mt-2 text-xs">
              <span className="text-emerald-300 tabular-nums">
                매수 {agg.nBuy ?? 0} · 강도 {num(agg.buyW, 1)}
              </span>
              <span className={`font-bold ${actionText(action)}`}>{actionLabel(action)}</span>
              <span className="text-rose-300 tabular-nums">
                매도 {agg.nSell ?? 0} · 강도 {num(agg.sellW, 1)}
              </span>
            </div>
          </div>
        </div>

        {/* 수익률 타일 */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 mt-5">
          {['1', '5', '20', '60'].map((k) => (
            <StatTile
              key={k}
              label={`${k}일 수익률`}
              value={ret[k] == null ? '-' : pct(ret[k], 2)}
              valueClass={retText(ret[k])}
            />
          ))}
        </div>
      </GlassCard>

      {/* 차트 */}
      <ChartWorkbench symbol={symbol} />
      <ChartTiming symbol={symbol} currency={data.currency} />

      {/* 지표 + 레벨 */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        <GlassCard delay={0.1} className="xl:col-span-2">
          <h2 className="text-sm font-bold text-slate-200 mb-3">기술 지표</h2>
          <IndicatorGrid indicators={data.indicators} disparity20={data.disparity20} currency={data.currency} />
        </GlassCard>

        <GlassCard delay={0.15}>
          <h2 className="text-sm font-bold text-slate-200 mb-4">지지 · 저항 · 피봇</h2>
          <LevelBar levels={data.levels} price={data.price} currency={data.currency} />
        </GlassCard>
      </div>

      {/* 시그널 보드 */}
      <GlassCard delay={0.2}>
        <h2 className="text-sm font-bold text-slate-200 mb-4">전략 시그널</h2>
        <SignalBoard signals={data.signals} />
      </GlassCard>

      {/* 다이버전스 / 패턴 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {/* 다이버전스 */}
        <GlassCard delay={0.25}>
          <h2 className="text-sm font-bold text-slate-200 mb-3">다이버전스</h2>
          {div.summary || div.rsi || div.macd ? (
            <div className="flex flex-col gap-2.5">
              {div.summary && (
                <div className="glass-soft p-3 flex items-center justify-between">
                  <span className="text-xs text-slate-400">종합</span>
                  <span className={`text-sm font-bold ${biasTone(div.summary)}`}>
                    {biasLabel(div.summary)}
                  </span>
                </div>
              )}
              <DivRow label="RSI" d={div.rsi} />
              <DivRow label="MACD" d={div.macd} />
            </div>
          ) : (
            <div className="text-xs text-slate-500">감지된 다이버전스 없음</div>
          )}
        </GlassCard>

        {/* 캔들 패턴 */}
        <GlassCard delay={0.3}>
          <h2 className="text-sm font-bold text-slate-200 mb-3">캔들 패턴</h2>
          <PatternList items={candlePatterns} />
        </GlassCard>

        {/* 차트 패턴 */}
        <GlassCard delay={0.35}>
          <h2 className="text-sm font-bold text-slate-200 mb-3">차트 패턴</h2>
          <PatternList items={chartPatterns} />
        </GlassCard>
      </div>

      {/* 불균형 */}
      {data.imbalance != null && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.4 }}
          className="text-[11px] text-slate-500 text-center"
        >
          수급 불균형 지표: {typeof data.imbalance === 'object' ? JSON.stringify(data.imbalance) : num(data.imbalance, 2)}
        </motion.div>
      )}
    </div>
  )
}

function BackLink() {
  return (
    <Link
      to="/"
      className="inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-white transition-colors w-fit"
    >
      <span className="text-base">←</span> 대시보드로
    </Link>
  )
}

function DivRow({ label, d }) {
  const reg = d?.regular
  const hid = d?.hidden
  const has = reg || hid
  return (
    <div className="glass-soft p-3">
      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-300 font-semibold">{label}</span>
        {!has && <span className="text-[11px] text-slate-500">없음</span>}
      </div>
      {has && (
        <div className="flex gap-2 mt-1.5">
          {reg && (
            <span className={`text-[11px] px-2 py-0.5 rounded-md border ${biasTone(reg)} border-white/10 bg-white/[0.04]`}>
              정규 · {biasLabel(reg)}
            </span>
          )}
          {hid && (
            <span className={`text-[11px] px-2 py-0.5 rounded-md border ${biasTone(hid)} border-white/10 bg-white/[0.04]`}>
              히든 · {biasLabel(hid)}
            </span>
          )}
        </div>
      )}
    </div>
  )
}

function PatternList({ items = [] }) {
  if (!items.length) return <div className="text-xs text-slate-500">감지된 패턴 없음</div>
  return (
    <div className="flex flex-col gap-2">
      {items.map((p, i) => (
        <motion.div
          key={(p.name || '') + i}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.25, delay: Math.min(i, 10) * 0.03, ease: EASE_OUT }}
          className="glass-soft p-2.5 flex items-center justify-between gap-2"
        >
          <span className="text-xs text-slate-200 truncate">{p.name}</span>
          {p.bias && (
            <span className={`text-[11px] font-bold shrink-0 ${biasTone(p.bias)}`}>
              {biasLabel(p.bias)}
            </span>
          )}
        </motion.div>
      ))}
    </div>
  )
}
