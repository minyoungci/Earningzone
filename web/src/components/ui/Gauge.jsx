// 종합점수 게이지 (-max..+max). 중앙 0선 기준 좌(매도/빨강)·우(매수/초록).
export default function Gauge({ score = 0, max = 10, className = '' }) {
  const clamped = Math.max(-max, Math.min(max, Number(score) || 0))
  const w = (Math.abs(clamped) / max) * 50
  const buy = clamped >= 0
  return (
    <div className={`relative h-3 rounded-full bg-white/10 overflow-hidden ${className}`}>
      <div className="absolute inset-y-0 left-1/2 w-px bg-white/30 z-10" />
      <div
        className={`absolute inset-y-0 ${buy ? 'left-1/2 bg-gradient-to-r from-emerald-500/70 to-emerald-400' : 'right-1/2 bg-gradient-to-l from-rose-500/70 to-rose-400'}`}
        style={{ width: `${w}%` }}
      />
    </div>
  )
}
