import { motion } from 'framer-motion'
import { num, pct, money } from '../lib/format'
import { EASE_OUT } from '../lib/motion'

// 지표 한 칸: 값 + 라벨 + 상태(과매수/과매도/중립) 색.
function Cell({ label, value, tone = 'neutral', hint, i }) {
  const toneClass =
    tone === 'hot'
      ? 'text-rose-300'
      : tone === 'cold'
      ? 'text-sky-300'
      : tone === 'up'
      ? 'text-up'
      : tone === 'down'
      ? 'text-down'
      : 'text-slate-100'
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: 0.02 * i, ease: EASE_OUT }}
      className="glass-soft p-3.5 hover:bg-white/[0.07] transition-colors"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] text-slate-400 font-medium">{label}</span>
        {hint && (
          <span
            className={`text-[9px] px-1.5 py-0.5 rounded-full border ${
              tone === 'hot'
                ? 'border-rose-400/30 text-rose-300 bg-rose-500/10'
                : tone === 'cold'
                ? 'border-sky-400/30 text-sky-300 bg-sky-500/10'
                : 'border-white/10 text-slate-400 bg-white/[0.04]'
            }`}
          >
            {hint}
          </span>
        )}
      </div>
      <div className={`stat-num text-lg mt-1 ${toneClass}`}>{value}</div>
    </motion.div>
  )
}

/**
 * indicators: getAnalysis().indicators
 * disparity20: 이격도(20)
 */
export default function IndicatorGrid({ indicators = {}, disparity20, currency = 'KRW' }) {
  const I = indicators || {}

  const rsiTone = I.rsi == null ? 'neutral' : I.rsi >= 70 ? 'hot' : I.rsi <= 30 ? 'cold' : 'neutral'
  const stochTone =
    I.stochK == null ? 'neutral' : I.stochK >= 80 ? 'hot' : I.stochK <= 20 ? 'cold' : 'neutral'
  const mfiTone = I.mfi == null ? 'neutral' : I.mfi >= 80 ? 'hot' : I.mfi <= 20 ? 'cold' : 'neutral'
  const williamsTone =
    I.williamsR == null ? 'neutral' : I.williamsR >= -20 ? 'hot' : I.williamsR <= -80 ? 'cold' : 'neutral'
  const cciTone = I.cci == null ? 'neutral' : I.cci >= 100 ? 'hot' : I.cci <= -100 ? 'cold' : 'neutral'
  const adxTone = I.adx == null ? 'neutral' : I.adx >= 25 ? 'up' : 'neutral'
  const pctB = I.bollPctB
  const pctBTone = pctB == null ? 'neutral' : pctB >= 1 ? 'hot' : pctB <= 0 ? 'cold' : 'neutral'
  const dispTone =
    disparity20 == null ? 'neutral' : disparity20 >= 105 ? 'hot' : disparity20 <= 95 ? 'cold' : 'neutral'
  const rocTone = I.roc == null ? 'neutral' : I.roc > 0 ? 'up' : I.roc < 0 ? 'down' : 'neutral'

  const cells = [
    { label: 'RSI(14)', value: num(I.rsi, 1), tone: rsiTone, hint: rsiTone === 'hot' ? '과매수' : rsiTone === 'cold' ? '과매도' : null },
    { label: 'MACD Hist', value: num(I.macdHist, 2), tone: I.macdHist == null ? 'neutral' : I.macdHist > 0 ? 'up' : 'down' },
    { label: 'Stoch %K', value: num(I.stochK, 1), tone: stochTone, hint: stochTone === 'hot' ? '과매수' : stochTone === 'cold' ? '과매도' : null },
    { label: 'Stoch %D', value: num(I.stochD, 1), tone: 'neutral' },
    { label: 'ADX', value: num(I.adx, 1), tone: adxTone, hint: adxTone === 'up' ? '추세' : null },
    { label: 'CCI', value: num(I.cci, 0), tone: cciTone, hint: cciTone === 'hot' ? '과매수' : cciTone === 'cold' ? '과매도' : null },
    { label: 'Williams %R', value: num(I.williamsR, 1), tone: williamsTone, hint: williamsTone === 'hot' ? '과매수' : williamsTone === 'cold' ? '과매도' : null },
    { label: 'MFI', value: num(I.mfi, 1), tone: mfiTone, hint: mfiTone === 'hot' ? '과매수' : mfiTone === 'cold' ? '과매도' : null },
    { label: 'ROC', value: I.roc == null ? '-' : pct(I.roc, 2), tone: rocTone },
    { label: 'Boll %B', value: num(pctB, 2), tone: pctBTone, hint: pctBTone === 'hot' ? '상단돌파' : pctBTone === 'cold' ? '하단돌파' : null },
    { label: 'ATR %', value: I.atrPct == null ? '-' : num(I.atrPct, 2) + '%', tone: 'neutral' },
    { label: '이격도(20)', value: disparity20 == null ? '-' : num(disparity20, 1), tone: dispTone, hint: dispTone === 'hot' ? '과열' : dispTone === 'cold' ? '침체' : null },
    { label: 'VWAP', value: I.vwap == null ? '-' : money(I.vwap, currency), tone: 'neutral' },
    { label: '+DI / -DI', value: `${num(I.plusDI, 0)} / ${num(I.minusDI, 0)}`, tone: I.plusDI != null && I.minusDI != null ? (I.plusDI >= I.minusDI ? 'up' : 'down') : 'neutral' },
    { label: 'OBV 기울기', value: num(I.obvSlope, 2), tone: I.obvSlope == null ? 'neutral' : I.obvSlope > 0 ? 'up' : 'down' },
    { label: '거래량비', value: I.volRatio == null ? '-' : num(I.volRatio, 2) + 'x', tone: I.volRatio == null ? 'neutral' : I.volRatio >= 1.5 ? 'up' : 'neutral' },
  ]

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2.5">
      {cells.map((c, i) => (
        <Cell key={c.label} {...c} i={i} />
      ))}
    </div>
  )
}
