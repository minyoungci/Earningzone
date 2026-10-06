export default function StatTile({ label, value, sub, valueClass = '', className = '' }) {
  return (
    <div className={`glass-soft p-4 ${className}`}>
      {/* 라벨=마이크로캡(자간+), 값=큰 숫자(자간−) — 크기별 트래킹(Apple §15) */}
      <div className="label-cap mb-1.5">{label}</div>
      <div className={`stat-num text-xl leading-none ${valueClass}`}>{value}</div>
      {sub != null && <div className="text-xs text-slate-500 mt-1.5">{sub}</div>}
    </div>
  )
}
