import { motion } from 'framer-motion'
import { categoryLabel, actionLabel } from '../lib/format'
import { EASE_OUT } from '../lib/motion'

const CAT_ORDER = ['trend', 'momentum', 'volatility', 'meanrev', 'breakout', 'structure']

// strength(0..1) 바. 매수=초록, 매도=빨강, 관망=회색.
function StrengthBar({ action, strength = 0 }) {
  const w = Math.max(0, Math.min(1, Number(strength) || 0)) * 100
  const grad =
    action === 'BUY'
      ? 'from-emerald-500/70 to-emerald-400'
      : action === 'SELL'
      ? 'from-rose-500/70 to-rose-400'
      : 'from-slate-500/60 to-slate-400'
  return (
    <div className="h-1.5 rounded-full bg-white/[0.08] overflow-hidden">
      {/* 레이아웃 width 대신 GPU 합성 scaleX 로 채움 — 실시간 리폴링 중 매 프레임 레이아웃 회피 */}
      <motion.div
        className={`h-full rounded-full bg-gradient-to-r ${grad} origin-left`}
        style={{ width: `${w}%` }}
        initial={{ scaleX: 0 }}
        animate={{ scaleX: 1 }}
        transition={{ duration: 0.35, ease: EASE_OUT }}
      />
    </div>
  )
}

function SignalRow({ s, i }) {
  const dot =
    s.action === 'BUY' ? 'bg-emerald-400' : s.action === 'SELL' ? 'bg-rose-400' : 'bg-slate-400'
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3, delay: 0.02 * i, ease: EASE_OUT }}
      className="glass-soft p-3 hover:bg-white/[0.07] transition-colors"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dot}`} />
          <span className="text-sm font-semibold text-slate-100 truncate">{s.name}</span>
        </div>
        <span className="text-[10px] text-slate-500 tabular-nums shrink-0">
          {Math.round((Number(s.strength) || 0) * 100)}%
        </span>
      </div>
      {s.reason && <div className="text-[11px] text-slate-400 mt-1 leading-snug">{s.reason}</div>}
      <div className="mt-2">
        <StrengthBar action={s.action} strength={s.strength} />
      </div>
    </motion.div>
  )
}

function Column({ title, count, accent, signals }) {
  return (
    <div className="flex flex-col gap-2.5 min-w-0">
      <div className="flex items-center justify-between">
        <span className={`text-sm font-bold ${accent}`}>{title}</span>
        <span className="text-xs text-slate-500 tabular-nums">{count}개</span>
      </div>
      {signals.length === 0 ? (
        <div className="glass-soft p-4 text-xs text-slate-500 text-center">시그널 없음</div>
      ) : (
        signals.map((s, i) => <SignalRow key={(s.name || '') + i} s={s} i={i} />)
      )}
    </div>
  )
}

/**
 * signals: getAnalysis().signals
 * 매수/매도로 분리하고, 각 칼럼 안에서 카테고리 순으로 정렬.
 */
export default function SignalBoard({ signals = [] }) {
  const list = Array.isArray(signals) ? signals : []
  if (!list.length) {
    return <div className="text-sm text-slate-500 p-4">시그널 데이터 없음</div>
  }

  const byCat = (a, b) => {
    const ca = CAT_ORDER.indexOf(a.category)
    const cb = CAT_ORDER.indexOf(b.category)
    if (ca !== cb) return (ca < 0 ? 99 : ca) - (cb < 0 ? 99 : cb)
    return (Number(b.strength) || 0) - (Number(a.strength) || 0)
  }

  const buys = list.filter((s) => s.action === 'BUY').sort(byCat)
  const sells = list.filter((s) => s.action === 'SELL').sort(byCat)
  const holds = list.filter((s) => s.action !== 'BUY' && s.action !== 'SELL').sort(byCat)

  // 카테고리 요약 칩
  const catCounts = {}
  list.forEach((s) => {
    const c = s.category || 'etc'
    catCounts[c] = catCounts[c] || { BUY: 0, SELL: 0 }
    if (s.action === 'BUY') catCounts[c].BUY++
    else if (s.action === 'SELL') catCounts[c].SELL++
  })
  const cats = CAT_ORDER.filter((c) => catCounts[c])

  return (
    <div className="flex flex-col gap-4">
      {cats.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {cats.map((c) => (
            <span
              key={c}
              className="glass-soft px-2.5 py-1 rounded-full text-[11px] flex items-center gap-1.5"
            >
              <span className="text-slate-300 font-medium">{categoryLabel(c)}</span>
              {catCounts[c].BUY > 0 && (
                <span className="text-emerald-300 tabular-nums">매수 {catCounts[c].BUY}</span>
              )}
              {catCounts[c].SELL > 0 && (
                <span className="text-rose-300 tabular-nums">매도 {catCounts[c].SELL}</span>
              )}
            </span>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Column title="매수 시그널" count={buys.length} accent="text-emerald-300" signals={buys} />
        <Column title="매도 시그널" count={sells.length} accent="text-rose-300" signals={sells} />
      </div>

      {holds.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-bold text-slate-300">{actionLabel('HOLD')} 시그널</span>
            <span className="text-xs text-slate-500 tabular-nums">{holds.length}개</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
            {holds.map((s, i) => (
              <SignalRow key={(s.name || '') + i} s={s} i={i} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
