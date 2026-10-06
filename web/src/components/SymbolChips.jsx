import { motion } from 'framer-motion'
import { retText } from '../lib/format'
import { EASE_OUT } from '../lib/motion'

/**
 * 상단 종목 칩 셀렉터.
 * items: getWatchlist().items 형태 [{symbol,name,price,ret,action,...}]
 * selected: 현재 선택된 symbol
 * onSelect: (symbol, name) => void
 */
export default function SymbolChips({ items = [], selected, onSelect }) {
  if (!items.length) return null
  return (
    <div className="flex gap-2 overflow-x-auto py-1 -my-1 -mx-1 px-1 snap-x">
      {items.map((it, i) => {
        const active = it.symbol === selected
        const r1 = it.ret?.['1']
        return (
          <motion.button
            key={it.symbol}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: i * 0.02, ease: EASE_OUT }}
            whileTap={{ scale: 0.97 }}
            onClick={() => onSelect?.(it.symbol, it.name)}
            className={`snap-start shrink-0 px-4 py-2.5 rounded-2xl border text-left transition-colors duration-200 ${
              active
                ? 'bg-white/[0.12] border-white/25 shadow-inner'
                : 'glass-soft hover:bg-white/[0.08]'
            }`}
          >
            <div className="flex items-center gap-2">
              <span className={`text-sm font-bold ${active ? 'text-white' : 'text-slate-200'}`}>
                {it.name || it.symbol}
              </span>
              <span className="text-[10px] text-slate-500 font-mono">{it.symbol}</span>
            </div>
            <div className={`text-xs font-semibold tabular-nums mt-0.5 ${retText(r1)}`}>
              {r1 == null ? '—' : (r1 >= 0 ? '+' : '') + Number(r1).toFixed(2) + '%'}
            </div>
          </motion.button>
        )
      })}
    </div>
  )
}
