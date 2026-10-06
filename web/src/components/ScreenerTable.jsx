import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { money, num, actionText, actionLabel } from '../lib/format'
import { EASE_OUT } from '../lib/motion'
import Badge from './ui/Badge'

// 순위 메달 색
const rankCls = (i) =>
  i === 0 ? 'text-amber-300' : i === 1 ? 'text-slate-200' : i === 2 ? 'text-orange-300' : 'text-slate-500'

export default function ScreenerTable({ items = [], limit = 12 }) {
  const nav = useNavigate()
  const rows = items.slice(0, limit)

  if (!rows.length) {
    return <div className="text-slate-500 text-sm p-6 text-center">표시할 종목이 없습니다.</div>
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-separate border-spacing-y-1">
        <thead>
          <tr className="text-[11px] text-slate-500 text-left">
            <th className="font-medium px-3 py-1 w-12">#</th>
            <th className="font-medium px-3 py-1">종목</th>
            <th className="font-medium px-3 py-1 text-right">현재가</th>
            <th className="font-medium px-3 py-1 text-right">점수</th>
            <th className="font-medium px-3 py-1 text-center hidden sm:table-cell">신호</th>
            <th className="font-medium px-3 py-1 text-right">매수/매도</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <motion.tr
              key={r.symbol}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3, delay: Math.min(i, 10) * 0.03, ease: EASE_OUT }}
              onClick={() => nav(`/symbol/${r.symbol}`)}
              className="glass-soft cursor-pointer [&>td:first-child]:rounded-l-2xl [&>td:last-child]:rounded-r-2xl hover:bg-white/[0.08] transition-colors"
            >
              <td className={`px-3 py-2.5 stat-num font-bold ${rankCls(i)}`}>{i + 1}</td>
              <td className="px-3 py-2.5">
                <div className="font-semibold truncate max-w-[10rem]">{r.name || r.symbol}</div>
                <div className="text-[10px] text-slate-500 font-mono">{r.symbol}</div>
              </td>
              <td className="px-3 py-2.5 text-right stat-num">{money(r.price, r.currency)}</td>
              <td className={`px-3 py-2.5 text-right stat-num font-bold ${actionText(r.action)}`}>
                {r.score >= 0 ? '+' : ''}{num(r.score, 1)}
              </td>
              <td className="px-3 py-2.5 text-center hidden sm:table-cell">
                <Badge action={r.action} />
              </td>
              <td className="px-3 py-2.5 text-right stat-num text-xs">
                <span className="text-emerald-300">{r.nBuy ?? 0}</span>
                <span className="text-slate-600 mx-1">/</span>
                <span className="text-rose-300">{r.nSell ?? 0}</span>
              </td>
            </motion.tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
