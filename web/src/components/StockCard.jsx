import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { money, pct, retText, num } from '../lib/format'
import { EASE_OUT, useHasHover } from '../lib/motion'
import Badge from './ui/Badge'
import Gauge from './ui/Gauge'

const STRUCT = {
  uptrend: { label: '상승추세', cls: 'text-up bg-rose-500/10 border-rose-400/20' },
  downtrend: { label: '하락추세', cls: 'text-down bg-sky-500/10 border-sky-400/20' },
  range: { label: '횡보', cls: 'text-slate-300 bg-white/5 border-white/10' },
}

// 등락 한 칸: 라벨 + 색상 퍼센트
function Ret({ label, v }) {
  return (
    <div className="flex flex-col items-center min-w-0">
      <span className="text-[10px] text-slate-500">{label}</span>
      <span className={`stat-num text-sm ${retText(v)}`}>{pct(v)}</span>
    </div>
  )
}

export default function StockCard({ item, index = 0 }) {
  const nav = useNavigate()
  const hasHover = useHasHover()
  const {
    symbol, name, price, currency, ret = {}, structure, rsi,
    action, score, nBuy = 0, nSell = 0,
  } = item || {}
  const st = STRUCT[structure] || STRUCT.range

  return (
    <motion.button
      type="button"
      onClick={() => nav(`/symbol/${symbol}`)}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, delay: index * 0.04, ease: EASE_OUT }}
      whileHover={hasHover ? { y: -4 } : undefined}
      whileTap={{ scale: 0.985 }}
      className="glass glass-hover p-5 text-left w-full flex flex-col gap-4 group"
    >
      {/* 헤더: 종목명/코드 + 종합배지 */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-bold text-[15px] truncate group-hover:text-white transition-colors">
            {name || symbol}
          </div>
          <div className="text-xs text-slate-500 font-mono mt-0.5">{symbol}</div>
        </div>
        <Badge action={action} />
      </div>

      {/* 현재가 + 구조/RSI */}
      <div className="flex items-end justify-between gap-3">
        <div className="stat-num text-2xl leading-none">{money(price, currency)}</div>
        <div className="flex flex-col items-end gap-1">
          <span className={`text-[11px] px-2 py-0.5 rounded-full border ${st.cls}`}>{st.label}</span>
          {rsi != null && (
            <span className="text-[11px] text-slate-500">RSI {num(rsi)}</span>
          )}
        </div>
      </div>

      {/* 게이지 */}
      <div className="flex items-center gap-3">
        <Gauge score={score} max={10} className="flex-1" />
        <span className="stat-num text-xs text-slate-400 w-10 text-right">
          {score >= 0 ? '+' : ''}{num(score, 1)}
        </span>
      </div>

      {/* 등락 + 매수/매도 */}
      <div className="flex items-center justify-between gap-2 pt-1 border-t border-white/5">
        <div className="flex gap-4">
          <Ret label="1일" v={ret['1']} />
          <Ret label="5일" v={ret['5']} />
          <Ret label="20일" v={ret['20']} />
        </div>
        <div className="flex items-center gap-2 text-[11px]">
          <span className="px-2 py-0.5 rounded-full bg-emerald-500/12 text-emerald-300 stat-num">
            매수 {nBuy}
          </span>
          <span className="px-2 py-0.5 rounded-full bg-rose-500/12 text-rose-300 stat-num">
            매도 {nSell}
          </span>
        </div>
      </div>
    </motion.button>
  )
}
