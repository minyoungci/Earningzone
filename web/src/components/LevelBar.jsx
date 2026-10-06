import { money, num } from '../lib/format'

/**
 * levels: getAnalysis().levels
 * price: 현재가
 * 관측 구간 위치(legacy pos52 키) 바 + 지지/저항(nearest) + 피봇.
 */
export default function LevelBar({ levels = {}, price, currency = 'KRW' }) {
  const L = levels || {}
  const pos = L.pos52 == null ? null : Math.max(0, Math.min(100, Number(L.pos52)))
  const sup = L.nearestSupport
  const res = L.nearestResistance
  const piv = L.pivots || {}

  return (
    <div className="flex flex-col gap-5">
      {/* 최대 200봉으로 산출하므로 52주 전체로 표시하지 않는다. */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-slate-400 font-medium">관측 구간 가격 위치</span>
          {L.fromHigh != null && (
            <span className="text-[11px] text-down tabular-nums">
              고점대비 {num(L.fromHigh, 1)}%
            </span>
          )}
        </div>
        <div className="relative h-2.5 rounded-full bg-gradient-to-r from-sky-500/40 via-white/10 to-rose-500/40 overflow-visible">
          {pos != null && (
            <div
              className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-3.5 h-3.5 rounded-full bg-white shadow-[0_0_10px_rgba(255,255,255,0.6)] border-2 border-slate-900"
              style={{ left: `${pos}%` }}
            />
          )}
        </div>
        <div className="flex items-center justify-between mt-1.5 text-[11px]">
          <span className="text-sky-300 tabular-nums">
            저 {L.low52 == null ? '-' : money(L.low52, currency)}
          </span>
          <span className="text-slate-400 tabular-nums">
            {pos == null ? '' : `${num(pos, 0)}%`}
          </span>
          <span className="text-rose-300 tabular-nums">
            고 {L.high52 == null ? '-' : money(L.high52, currency)}
          </span>
        </div>
      </div>

      {/* 지지 / 저항 */}
      <div className="grid grid-cols-2 gap-2.5">
        <div className="glass-soft p-3">
          <div className="text-[11px] text-sky-300 mb-1">최근접 지지</div>
          <div className="stat-num text-base text-slate-100">{sup == null ? '-' : money(sup, currency)}</div>
          {L.distToSupport != null && (
            <div className="text-[11px] text-slate-500 mt-0.5">{num(L.distToSupport, 1)}% 아래</div>
          )}
        </div>
        <div className="glass-soft p-3">
          <div className="text-[11px] text-rose-300 mb-1">최근접 저항</div>
          <div className="stat-num text-base text-slate-100">{res == null ? '-' : money(res, currency)}</div>
          {L.distToResistance != null && (
            <div className="text-[11px] text-slate-500 mt-0.5">{num(L.distToResistance, 1)}% 위</div>
          )}
        </div>
      </div>

      {/* 추가 지지/저항 라인 */}
      {(Array.isArray(L.supports) || Array.isArray(L.resistances)) && (
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]">
          <div className="flex flex-wrap gap-1.5">
            {(L.supports || []).slice(0, 3).map((s, i) => (
              <span key={'s' + i} className="px-2 py-0.5 rounded-md bg-sky-500/10 text-sky-300 border border-sky-400/20 tabular-nums">
                {money(s, currency)}
              </span>
            ))}
          </div>
          <div className="flex flex-wrap gap-1.5 justify-end">
            {(L.resistances || []).slice(0, 3).map((r, i) => (
              <span key={'r' + i} className="px-2 py-0.5 rounded-md bg-rose-500/10 text-rose-300 border border-rose-400/20 tabular-nums">
                {money(r, currency)}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* 피봇 */}
      {piv && piv.p != null && (
        <div>
          <div className="text-xs text-slate-400 font-medium mb-2">피봇 포인트</div>
          <div className="grid grid-cols-3 sm:grid-cols-7 gap-1.5 text-center">
            {[
              { k: 'S3', v: piv.s3, c: 'text-sky-300' },
              { k: 'S2', v: piv.s2, c: 'text-sky-300' },
              { k: 'S1', v: piv.s1, c: 'text-sky-300' },
              { k: 'P', v: piv.p, c: 'text-amber-300' },
              { k: 'R1', v: piv.r1, c: 'text-rose-300' },
              { k: 'R2', v: piv.r2, c: 'text-rose-300' },
              { k: 'R3', v: piv.r3, c: 'text-rose-300' },
            ].map((x) => (
              <div key={x.k} className="glass-soft py-2 px-1">
                <div className={`text-[10px] font-bold ${x.c}`}>{x.k}</div>
                <div className="stat-num text-[11px] text-slate-200 mt-0.5">
                  {x.v == null ? '-' : money(x.v, currency)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
