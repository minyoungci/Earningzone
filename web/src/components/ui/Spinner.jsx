export default function Spinner({ label = '불러오는 중…', className = '' }) {
  return (
    <div className={`flex items-center gap-3 text-slate-400 text-sm p-8 ${className}`}>
      {/* 빠른 스피너 = 로딩이 빨라 보인다(체감 성능, Emil) */}
      <span className="w-5 h-5 rounded-full border-2 border-white/20 border-t-white/80 animate-spin [animation-duration:600ms]" />
      {label}
    </div>
  )
}
