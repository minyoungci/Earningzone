import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { EASE_OUT } from '../lib/motion'
import { useNavigate, useParams } from 'react-router-dom'
import { useApi, getWatchlist, getIntraday, getCandles } from '../api'
import {
  num,
  pct,
  money,
  actionText,
  actionLabel,
  categoryLabel,
  retText,
} from '../lib/format'
import GlassCard from '../components/ui/GlassCard'
import Badge from '../components/ui/Badge'
import Gauge from '../components/ui/Gauge'
import Spinner from '../components/ui/Spinner'
import StatTile from '../components/ui/StatTile'
import CandleChart from '../components/CandleChart'
import SymbolChips from '../components/SymbolChips'

const DEFAULT_SYMBOL = '005930'

const fade = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: EASE_OUT } },
}

export default function Intraday() {
  const { symbol: routeSymbol } = useParams()
  const navigate = useNavigate()

  const { data: wl, err: wlErr, loading: wlLoading } = useApi(() => getWatchlist(), [])
  const items = wl?.items || []

  const [selected, setSelected] = useState(routeSymbol || DEFAULT_SYMBOL)

  // 라우트 파라미터가 바뀌면 선택 동기화
  useEffect(() => {
    if (routeSymbol) setSelected(routeSymbol)
  }, [routeSymbol])

  const selectedName = useMemo(
    () => items.find((i) => i.symbol === selected)?.name || '',
    [items, selected],
  )

  const onSelect = (sym) => {
    setSelected(sym)
    navigate(`/intraday/${sym}`)
  }

  const {
    data: intra,
    err: intraErr,
    loading: intraLoading,
  } = useApi(() => getIntraday(selected, selectedName), [selected, selectedName], { pollMs: 15000 })
  const {
    data: cd,
    err: cdErr,
    loading: cdLoading,
  } = useApi(() => getCandles(selected, '1m', 200), [selected], { pollMs: 15000 })

  // 폴링으로 intra 가 갱신될 때마다 '마지막 갱신 시각' 을 기록 (백그라운드 갱신 표시용)
  const [updatedAt, setUpdatedAt] = useState(null)
  useEffect(() => {
    if (intra) setUpdatedAt(Date.now())
  }, [intra])

  // 폴링 1회 실패로 표시 중이던 차트/분석이 에러 박스로 교체되지 않게,
  // '데이터가 아예 없는 실패'만 에러 분기(err && !data). 데이터가 있으면 배지만 표시.
  const intraFail = intraErr && !intra
  const cdFail = cdErr && !cd
  const staleFail = (intraErr && intra) || (cdErr && cd)

  const ind = intra?.indicators || {}
  const agg = intra?.aggregate || {}
  const signals = intra?.signals || []
  const buys = signals.filter((s) => s.action === 'BUY')
  const sells = signals.filter((s) => s.action === 'SELL')
  const candles = cd?.candles || []

  const vwap = ind.vwap
  const price = intra?.price
  const vwapDiff =
    vwap != null && price != null ? ((price - vwap) / vwap) * 100 : null

  const priceLines = vwap != null ? [{ price: vwap, title: 'VWAP', color: '#a78bfa' }] : []

  return (
    <div className="flex flex-col gap-5 max-w-[1400px] mx-auto">
      {/* 헤더 */}
      <motion.div variants={fade} initial="hidden" animate="show">
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight flex items-center gap-2">
            인트라데이
          </h1>
          <span className="text-xs px-2.5 py-1 rounded-full bg-violet-500/15 text-violet-300 border border-violet-400/25 font-mono">
            1분봉
          </span>
          {/* 실시간 폴링 인디케이터 (15초 주기 백그라운드 갱신) */}
          {updatedAt != null && (
            <span className="text-[11px] px-2 py-1 rounded-full bg-emerald-500/10 text-emerald-300 border border-emerald-400/20 inline-flex items-center gap-1.5">
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75 animate-ping" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-400" />
              </span>
              실시간 갱신 중
            </span>
          )}
          {staleFail && (
            <span className="text-[11px] px-2 py-1 rounded-full bg-amber-500/10 text-amber-300 border border-amber-400/20">
              갱신 실패 · 마지막 값 표시 중
            </span>
          )}
        </div>
        <p className="text-sm text-slate-400 mt-1">
          분봉 차트와 실시간 시그널 · VWAP 기준 단기 흐름
          {updatedAt != null && (
            <span className="text-slate-500">
              {' '}· 업데이트{' '}
              <span className="stat-num">{new Date(updatedAt).toLocaleTimeString('ko-KR')}</span>
            </span>
          )}
        </p>
      </motion.div>

      {/* 종목 칩 */}
      <GlassCard delay={0.05} className="!p-3">
        {wlLoading ? (
          <Spinner label="종목 불러오는 중…" className="!p-3" />
        ) : wlErr ? (
          <div className="text-rose-300 text-sm p-3">종목 목록을 불러오지 못했어요: {wlErr.message}</div>
        ) : items.length === 0 ? (
          <div className="text-slate-400 text-sm p-3">표시할 종목이 없어요.</div>
        ) : (
          <SymbolChips items={items} selected={selected} onSelect={onSelect} />
        )}
      </GlassCard>

      {/* 차트 + 종합 */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        {/* 차트 */}
        <GlassCard delay={0.1} className="xl:col-span-2 min-w-0">
          <div className="flex items-baseline justify-between gap-3 mb-3 flex-wrap">
            <div className="flex items-baseline gap-2">
              <h2 className="text-lg font-bold">{intra?.name || selectedName || selected}</h2>
              <span className="text-xs text-slate-500 font-mono">{selected}</span>
            </div>
            {price != null && (
              <div className="text-right">
                <div className="stat-num text-xl">{money(price, intra?.currency)}</div>
                <div className={`text-xs font-semibold ${retText(intra?.ret?.['1'])}`}>
                  1분 {pct(intra?.ret?.['1'], 2)}
                </div>
              </div>
            )}
          </div>

          {cdLoading ? (
            <Spinner label="차트 불러오는 중…" />
          ) : cdFail ? (
            <div className="text-rose-300 text-sm p-6">차트를 불러오지 못했어요: {cdErr.message}</div>
          ) : candles.length === 0 ? (
            <div className="text-slate-500 text-sm p-6">분봉 데이터가 없어요.</div>
          ) : (
            <CandleChart candles={candles} priceLines={priceLines} height={400} />
          )}

          {vwap != null && (
            <div className="flex items-center gap-2 mt-3 text-xs text-slate-400">
              <span className="inline-block w-3 h-0.5 rounded bg-[#a78bfa]" />
              VWAP {money(vwap, intra?.currency)}
              {vwapDiff != null && (
                <span className={`font-semibold ${retText(vwapDiff)}`}>
                  · 현재가 {vwapDiff >= 0 ? '위' : '아래'} {pct(vwapDiff, 2)}
                </span>
              )}
            </div>
          )}
        </GlassCard>

        {/* 종합 점수 */}
        <GlassCard delay={0.15} className="min-w-0">
          <div className="text-sm font-semibold text-slate-300 mb-3">종합 판단</div>
          {intraLoading ? (
            <Spinner label="분석 중…" />
          ) : intraFail ? (
            <div className="text-rose-300 text-sm p-2">분석을 불러오지 못했어요: {intraErr.message}</div>
          ) : (
            <div className="flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <Badge action={agg.action} className="text-sm px-3.5 py-1.5" />
                <div className="text-right">
                  <div className={`stat-num text-3xl ${actionText(agg.action)}`}>
                    {agg.total != null ? (agg.total > 0 ? '+' : '') + num(agg.total, 1) : '—'}
                  </div>
                  <div className="text-[11px] text-slate-500">종합 스코어</div>
                </div>
              </div>

              <Gauge score={agg.total} max={10} />

              <div className="grid grid-cols-2 gap-2 pt-1">
                <div className="glass-soft p-3 text-center">
                  <div className="text-emerald-300 stat-num text-xl">{agg.nBuy ?? 0}</div>
                  <div className="text-[11px] text-slate-500 mt-0.5">매수 시그널</div>
                </div>
                <div className="glass-soft p-3 text-center">
                  <div className="text-rose-300 stat-num text-xl">{agg.nSell ?? 0}</div>
                  <div className="text-[11px] text-slate-500 mt-0.5">매도 시그널</div>
                </div>
              </div>

              {(agg.buyW != null || agg.sellW != null) && (
                <div className="flex items-center justify-between text-[11px] text-slate-400 px-1">
                  <span>매수 가중 {num(agg.buyW, 1)}</span>
                  <span>매도 가중 {num(agg.sellW, 1)}</span>
                </div>
              )}
            </div>
          )}
        </GlassCard>
      </div>

      {/* 주요 지표 타일 */}
      <GlassCard delay={0.2}>
        <div className="text-sm font-semibold text-slate-300 mb-3">주요 지표</div>
        {intraLoading ? (
          <Spinner />
        ) : intraFail ? (
          <div className="text-rose-300 text-sm p-2">지표를 불러오지 못했어요.</div>
        ) : (
          <motion.div
            initial="hidden"
            animate="show"
            variants={{ show: { transition: { staggerChildren: 0.03 } } }}
            className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3"
          >
            <Tile
              label="VWAP 대비"
              value={vwapDiff == null ? '—' : pct(vwapDiff, 2)}
              sub={vwap == null ? null : money(vwap, intra?.currency)}
              valueClass={retText(vwapDiff)}
            />
            <Tile
              label="RSI"
              value={num(ind.rsi, 1)}
              sub={ind.rsi == null ? null : ind.rsi >= 70 ? '과매수' : ind.rsi <= 30 ? '과매도' : '중립'}
              valueClass={ind.rsi == null ? '' : ind.rsi >= 70 ? 'text-up' : ind.rsi <= 30 ? 'text-down' : ''}
            />
            <Tile
              label="MACD Hist"
              value={num(ind.macdHist, 2)}
              valueClass={ind.macdHist == null ? '' : ind.macdHist > 0 ? 'text-up' : ind.macdHist < 0 ? 'text-down' : ''}
            />
            <Tile
              label="Stoch %K"
              value={num(ind.stochK, 1)}
              sub={ind.stochD == null ? null : `%D ${num(ind.stochD, 1)}`}
            />
            <Tile
              label="ADX"
              value={num(ind.adx, 1)}
              sub={ind.adx == null ? null : ind.adx >= 25 ? '추세강' : '횡보'}
            />
            <Tile
              label="거래량비"
              value={ind.volRatio == null ? '—' : num(ind.volRatio, 2) + '×'}
              valueClass={ind.volRatio == null ? '' : ind.volRatio >= 1.5 ? 'text-up' : ''}
            />
            <Tile label="MFI" value={num(ind.mfi, 1)} />
            <Tile label="CCI" value={num(ind.cci, 0)} />
            <Tile
              label="Williams %R"
              value={num(ind.williamsR, 1)}
            />
            <Tile
              label="Boll %B"
              value={ind.bollPctB == null ? '—' : num(ind.bollPctB, 2)}
            />
            <Tile label="ATR %" value={ind.atrPct == null ? '—' : pct(ind.atrPct, 2)} />
            <Tile
              label="OBV 기울기"
              value={num(ind.obvSlope, 2)}
              valueClass={ind.obvSlope == null ? '' : ind.obvSlope > 0 ? 'text-up' : ind.obvSlope < 0 ? 'text-down' : ''}
            />
          </motion.div>
        )}
      </GlassCard>

      {/* 시그널 보드 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <SignalColumn
          title="매수 시그널"
          accent="emerald"
          signals={buys}
          loading={intraLoading}
          err={intraFail}
          delay={0.25}
        />
        <SignalColumn
          title="매도 시그널"
          accent="rose"
          signals={sells}
          loading={intraLoading}
          err={intraFail}
          delay={0.3}
        />
      </div>
    </div>
  )
}

function Tile({ label, value, sub, valueClass }) {
  return (
    <motion.div variants={fade}>
      <StatTile label={label} value={value} sub={sub} valueClass={valueClass} />
    </motion.div>
  )
}

function SignalColumn({ title, accent, signals, loading, err, delay }) {
  const dot = accent === 'emerald' ? 'bg-emerald-400' : 'bg-rose-400'
  return (
    <GlassCard delay={delay} className="min-w-0">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${dot}`} />
          <span className="text-sm font-semibold text-slate-200">{title}</span>
        </div>
        <span className="text-xs text-slate-500">{signals.length}건</span>
      </div>

      {loading ? (
        <Spinner />
      ) : err ? (
        <div className="text-rose-300 text-sm p-2">시그널을 불러오지 못했어요.</div>
      ) : signals.length === 0 ? (
        <div className="text-slate-500 text-sm p-6 text-center">해당 시그널이 없어요.</div>
      ) : (
        <motion.ul
          initial="hidden"
          animate="show"
          variants={{ show: { transition: { staggerChildren: 0.04 } } }}
          className="flex flex-col gap-2"
        >
          {signals.map((s, i) => (
            <motion.li
              key={`${s.name}-${i}`}
              variants={fade}
              className="glass-soft p-3 glass-hover"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-sm font-semibold text-slate-100 truncate">{s.name}</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-white/[0.06] text-slate-400 border border-white/10 shrink-0">
                    {categoryLabel(s.category)}
                  </span>
                </div>
                <span className={`text-xs font-bold shrink-0 ${actionText(s.action)}`}>
                  {actionLabel(s.action)}
                </span>
              </div>
              {s.reason && (
                <div className="text-xs text-slate-400 mt-1 leading-relaxed">{s.reason}</div>
              )}
              {s.strength != null && (
                <div className="mt-2 h-1 rounded-full bg-white/[0.06] overflow-hidden">
                  <div
                    className={`h-full rounded-full ${accent === 'emerald' ? 'bg-emerald-400/70' : 'bg-rose-400/70'}`}
                    style={{ width: `${Math.max(0, Math.min(1, s.strength)) * 100}%` }}
                  />
                </div>
              )}
            </motion.li>
          ))}
        </motion.ul>
      )}
    </GlassCard>
  )
}
