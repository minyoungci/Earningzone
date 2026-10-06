import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { num } from '../lib/format'
import { EASE_OUT, useHasHover } from '../lib/motion'

// 점수(-10..+10) → 배경 스타일. 매수=초록, 매도=빨강, 중립=회색. 농도는 |점수|에 비례.
function tileStyle(score) {
  const s = Number(score) || 0
  const intensity = Math.min(1, Math.abs(s) / 8) // 0..1
  const alpha = (0.1 + intensity * 0.55).toFixed(2)
  if (s > 0.3) {
    return { background: `rgba(16,185,129,${alpha})`, borderColor: `rgba(52,211,153,${0.2 + intensity * 0.4})` }
  }
  if (s < -0.3) {
    return { background: `rgba(244,63,94,${alpha})`, borderColor: `rgba(251,113,133,${0.2 + intensity * 0.4})` }
  }
  return { background: 'rgba(255,255,255,0.05)', borderColor: 'rgba(255,255,255,0.1)' }
}

export default function Heatmap({ items = [], limit = 36 }) {
  const nav = useNavigate()
  const hasHover = useHasHover()
  const tiles = items.slice(0, limit)

  if (!tiles.length) {
    return <div className="text-slate-500 text-sm p-6 text-center">표시할 데이터가 없습니다.</div>
  }

  return (
    <div>
      <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-2">
        {tiles.map((t, i) => (
          <motion.button
            key={t.symbol}
            type="button"
            onClick={() => nav(`/symbol/${t.symbol}`)}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.3, delay: i * 0.015, ease: EASE_OUT }}
            whileHover={hasHover ? { y: -2 } : undefined}
            whileTap={{ scale: 0.96 }}
            style={tileStyle(t.score)}
            className="rounded-xl border p-2.5 text-left flex flex-col justify-between min-h-[68px] transition-shadow hover:shadow-lg"
            title={`${t.name || t.symbol} · 점수 ${num(t.score, 1)}`}
          >
            <div className="text-[11px] font-semibold text-white/90 truncate leading-tight">
              {t.name || t.symbol}
            </div>
            <div className="stat-num text-base font-bold text-white">
              {t.score >= 0 ? '+' : ''}{num(t.score, 1)}
            </div>
          </motion.button>
        ))}
      </div>

      {/* 범례 */}
      <div className="flex items-center justify-center gap-4 mt-4 text-[11px] text-slate-500">
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded" style={{ background: 'rgba(244,63,94,0.6)' }} /> 매도
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded" style={{ background: 'rgba(255,255,255,0.08)' }} /> 중립
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded" style={{ background: 'rgba(16,185,129,0.6)' }} /> 매수
        </span>
      </div>
    </div>
  )
}
