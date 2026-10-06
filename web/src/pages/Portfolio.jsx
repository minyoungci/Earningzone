import { useApi, getSim, getWatchlist } from '../api'
import { won, won0, pct, retText, money, signedWon, FX_ESTIMATED_NOTE } from '../lib/format'
import GlassCard from '../components/ui/GlassCard'
import Badge from '../components/ui/Badge'
import Spinner from '../components/ui/Spinner'
import StatTile from '../components/ui/StatTile'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { EASE_OUT } from '../lib/motion'

// ── 헬퍼: 가변 JSON에서 안전하게 값 뽑기 ──────────────────────
const nz = (v) => v != null && !Number.isNaN(Number(v))
const f = (v) => (nz(v) ? Number(v) : null)
const pnlClass = (v) => (v == null || v === 0 ? 'text-slate-300' : v > 0 ? 'text-up' : 'text-down')

// positions(또는 유사 배열) 탐색
function findPositions(p) {
  if (!p || typeof p !== 'object') return []
  const cands = [p.positions, p.holdings, p.items, p.stocks]
  for (const c of cands) if (Array.isArray(c)) return c
  return []
}

// 포지션 1개 정규화(sim state 우선, 키 이름 가변 대응)
function normPos(raw, priceMap) {
  if (!raw || typeof raw !== 'object') return null
  const symbol = String(raw.symbol ?? raw.code ?? raw.ticker ?? '')
  if (!symbol) return null
  const meta = priceMap[symbol] || {}
  // 통화: 미국주식($) / 국내주식(원) 구분 — 주당 값 표기에 사용
  const currency = raw.currency === 'USD' ? 'USD' : 'KRW'
  const qty = f(raw.qty ?? raw.quantity ?? raw.shares)
  // 주당 평단/현재가는 그 포지션 통화의 native 값(USD면 달러)
  const avg = f(raw.avgPrice ?? raw.avg ?? raw.avgCost ?? raw.entry)
  // 현재가: 저장본엔 없을 수 있어 watchlist 가격으로 보강
  const price = f(raw.currentPrice ?? raw.price ?? raw.last ?? raw.current) ?? f(meta.price)
  const name = raw.name || meta.name || symbol
  // 손익/평가금액은 백엔드가 이미 원화로 환산해 준다(valueKrw, pnl)
  let pnl = f(raw.pnl ?? raw.unrealized ?? raw.profit)
  let pnlPct = f(raw.pnlPct ?? raw.unrealizedPct ?? raw.retPct)
  if (pnl == null && qty != null && avg != null && price != null) pnl = (price - avg) * qty
  if (pnlPct == null && avg != null && price != null && avg > 0) pnlPct = (price / avg - 1) * 100
  // 평가금액(원화 환산): valueKrw 우선, 없으면 qty*price(KRW 종목에 한해 의미)
  const value = f(raw.valueKrw) ?? (qty != null && price != null ? qty * price : f(raw.marketValue ?? raw.value))
  return { symbol, name, currency, qty, avg, price, pnl, pnlPct, value, action: meta.action }
}

export default function Portfolio() {
  // 모의투자(Sim)와 동일 소스 — 웹에서 매수한 보유분이 그대로 보이도록 한다
  const { data: pf, err, loading } = useApi(() => getSim(), [], { pollMs: 5000 })
  const { data: wl } = useApi(() => getWatchlist(), [], { pollMs: 60000 })

  if (loading) {
    return (
      <div className="glass p-2">
        <Spinner label="포트폴리오 불러오는 중…" />
      </div>
    )
  }

  if (err) {
    return (
      <GlassCard className="border-rose-400/20">
        <div className="text-rose-300 font-semibold mb-1">불러오기 실패</div>
        <div className="text-sm text-slate-400">{String(err.message || err)}</div>
      </GlassCard>
    )
  }

  // watchlist → 가격/시그널 맵
  const wlItems = Array.isArray(wl?.items) ? wl.items : []
  const priceMap = {}
  for (const it of wlItems) if (it?.symbol) priceMap[it.symbol] = it
  const sig = wlItems.reduce(
    (a, it) => {
      if (it.action === 'BUY') a.buy++
      else if (it.action === 'SELL') a.sell++
      else a.hold++
      return a
    },
    { buy: 0, sell: 0, hold: 0 }
  )

  const positions = findPositions(pf)
    .map((r) => normPos(r, priceMap))
    .filter(Boolean)

  // 합계 — value/pnl 은 모두 원화 환산값이므로 단순 합산 가능(달러+원 혼합 금지 충족)
  const totMv = positions.reduce((s, p) => s + (p.value || 0), 0)
  const totPnl = positions.reduce((s, p) => s + (p.pnl || 0), 0)
  // 원가(원화): 평가금액 − 평가손익 = 매수 원가(원화 환산)
  const totCost = positions.reduce(
    (s, p) => s + ((p.value || 0) - (p.pnl || 0)),
    0
  )

  // 요약 카드: 존재하는 키만 노출 (가변 JSON 방어) — sim state 키 사용
  const realized = f(pf?.realizedPnl)
  const cash = f(pf?.cash ?? pf?.startCash)
  const equity = f(pf?.equity) ?? (cash != null ? cash + (realized || 0) + totPnl : null)
  const daily = f(pf?.dailyPnl ?? pf?.dayPnl)
  const fxEstimated = pf?.fxEstimated === true

  const summary = [
    equity != null && { label: '평가자산', value: won(equity), cls: '' },
    positions.length > 0 && {
      label: '평가금액',
      value: won(totMv),
      sub: totCost > 0 ? `원가 ${won0(totCost)}원` : null,
      cls: '',
    },
    positions.length > 0 && {
      label: '평가손익(미실현)',
      value: pct(totMv > 0 && totCost > 0 ? (totMv / totCost - 1) * 100 : null),
      sub: signedWon(totPnl),
      cls: pnlClass(totPnl),
    },
    realized != null && {
      label: '실현손익(누적)',
      value: signedWon(realized),
      cls: pnlClass(realized),
    },
    daily != null && {
      label: '일중손익',
      value: signedWon(daily),
      cls: pnlClass(daily),
    },
    cash != null && { label: '현금', value: won(cash), cls: '' },
  ].filter(Boolean)

  const note = pf?.note
  const savedAt = pf?.savedAt || (pf?.dayDate ? `기준일 ${pf.dayDate}` : null)

  return (
    <div className="flex flex-col gap-6 max-w-6xl">
      {/* 헤더 */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="flex flex-wrap items-end justify-between gap-3"
      >
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight flex items-center gap-2">
            포트폴리오
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            모의 트레이딩 상태 · 투자 권유 아님
            {savedAt && <span className="text-slate-500"> · {savedAt}</span>}
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className="px-2.5 py-1 rounded-full bg-white/5 text-slate-300 stat-num">
            보유 {positions.length}종목
          </span>
        </div>
      </motion.div>

      {/* 요약 카드 */}
      {summary.length > 0 && (
        <motion.div
          initial="hidden"
          animate="show"
          variants={{ show: { transition: { staggerChildren: 0.05 } } }}
          className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3"
        >
          {summary.map((s) => (
            <motion.div
              key={s.label}
              variants={{ hidden: { opacity: 0, y: 12 }, show: { opacity: 1, y: 0 } }}
            >
              <StatTile label={s.label} value={s.value} sub={s.sub} valueClass={s.cls} />
            </motion.div>
          ))}
        </motion.div>
      )}

      {fxEstimated && (
        <div className="text-xs text-amber-300/90 -mt-3">⚠️ {FX_ESTIMATED_NOTE} · 원화 환산값은 참고용입니다.</div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 포지션 표 */}
        <GlassCard delay={0.05} className="lg:col-span-2 p-0 overflow-hidden">
          <div className="flex items-center justify-between px-5 pt-5 pb-3">
            <h2 className="font-bold text-[15px]">보유 종목</h2>
            {positions.length > 0 && (
              <span className="text-xs text-slate-500">모의투자 보유 기준</span>
            )}
          </div>

          {positions.length === 0 ? (
            <div className="px-5 pb-8 pt-2 text-center">
              <div className="text-4xl mb-3 opacity-60">📭</div>
              <div className="font-semibold text-slate-200">보유 종목 없음</div>
              <div className="text-sm text-slate-400 mt-1.5 leading-relaxed">
                {note || '아직 보유 중인 종목이 없습니다.'}
                <br />
                <Link
                  to="/sim"
                  className="text-[12px] px-1.5 py-0.5 rounded bg-white/[0.08] text-indigo-300 mt-2 inline-block hover:bg-white/[0.12] transition"
                >
                  모의투자 탭에서 매수하기 →
                </Link>
              </div>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[11px] text-slate-500 border-y border-white/5">
                    <th className="text-left font-medium px-5 py-2.5">종목</th>
                    <th className="text-right font-medium px-2 py-2.5">수량</th>
                    <th className="text-right font-medium px-2 py-2.5">평단</th>
                    <th className="text-right font-medium px-2 py-2.5">현재가</th>
                    <th className="text-right font-medium px-2 py-2.5">평가손익</th>
                    <th className="text-right font-medium px-5 py-2.5">손익률</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p, i) => (
                    <motion.tr
                      key={p.symbol}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ duration: 0.25, delay: Math.min(i, 8) * 0.04, ease: EASE_OUT }}
                      className="border-b border-white/[0.04] hover:bg-white/[0.03] transition-colors"
                    >
                      <td className="px-5 py-3">
                        <Link to={`/symbol/${p.symbol}`} className="group inline-block">
                          <div className="font-semibold group-hover:text-white transition-colors truncate max-w-[140px]">
                            {p.name}
                          </div>
                          <div className="text-[11px] text-slate-500 font-mono">{p.symbol}</div>
                        </Link>
                      </td>
                      <td className="text-right px-2 py-3 stat-num text-slate-300">
                        {p.qty != null ? won0(p.qty) : '-'}
                      </td>
                      <td className="text-right px-2 py-3 stat-num text-slate-300">
                        {p.avg != null ? money(p.avg, p.currency) : '-'}
                      </td>
                      <td className="text-right px-2 py-3 stat-num">
                        {p.price != null ? (
                          money(p.price, p.currency)
                        ) : (
                          <span className="text-slate-600">-</span>
                        )}
                      </td>
                      <td className={`text-right px-2 py-3 stat-num ${pnlClass(p.pnl)}`}>
                        {p.pnl != null
                          ? `${p.pnl >= 0 ? '+' : ''}${won0(Math.round(p.pnl))}`
                          : '-'}
                      </td>
                      <td className={`text-right px-5 py-3 stat-num ${retText(p.pnlPct)}`}>
                        {p.pnlPct != null ? pct(p.pnlPct) : '-'}
                      </td>
                    </motion.tr>
                  ))}
                </tbody>
                {totMv > 0 && (
                  <tfoot>
                    <tr className="border-t border-white/10 text-[13px]">
                      <td className="px-5 py-3 font-semibold text-slate-300">합계</td>
                      <td colSpan={2} />
                      <td className="text-right px-2 py-3 stat-num text-slate-400">
                        {won0(Math.round(totMv))}
                      </td>
                      <td className={`text-right px-2 py-3 stat-num font-semibold ${pnlClass(totPnl)}`}>
                        {`${totPnl >= 0 ? '+' : ''}${won0(Math.round(totPnl))}`}
                      </td>
                      <td
                        className={`text-right px-5 py-3 stat-num font-semibold ${retText(
                          totCost > 0 ? (totMv / totCost - 1) * 100 : null
                        )}`}
                      >
                        {totCost > 0 ? pct((totMv / totCost - 1) * 100) : '-'}
                      </td>
                    </tr>
                  </tfoot>
                )}
              </table>
            </div>
          )}
        </GlassCard>

        {/* 사이드: 현재 시그널 요약 */}
        <GlassCard delay={0.1} className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="font-bold text-[15px]">현재 시그널</h2>
            <Link to="/" className="text-xs text-indigo-300 hover:text-indigo-200 transition-colors">
              대시보드 →
            </Link>
          </div>

          {wlItems.length === 0 ? (
            <div className="text-sm text-slate-500 py-4">워치리스트 데이터 없음</div>
          ) : (
            <>
              <div className="grid grid-cols-3 gap-2">
                <SigTile label="매수" n={sig.buy} action="BUY" />
                <SigTile label="관망" n={sig.hold} action="HOLD" />
                <SigTile label="매도" n={sig.sell} action="SELL" />
              </div>

              <div className="text-[11px] text-slate-500 leading-relaxed">
                워치리스트 {wlItems.length}종목 기준 종합 시그널 집계
              </div>

              {/* 매수 후보 상위 */}
              {wlItems.some((it) => it.action === 'BUY') && (
                <div className="border-t border-white/5 pt-3">
                  <div className="text-[11px] text-slate-500 mb-2">매수 시그널 종목</div>
                  <div className="flex flex-col gap-1.5">
                    {wlItems
                      .filter((it) => it.action === 'BUY')
                      .slice(0, 5)
                      .map((it) => (
                        <Link
                          key={it.symbol}
                          to={`/symbol/${it.symbol}`}
                          className="flex items-center justify-between gap-2 px-2.5 py-2 rounded-xl glass-soft glass-hover"
                        >
                          <div className="min-w-0">
                            <div className="text-[13px] font-semibold truncate">
                              {it.name || it.symbol}
                            </div>
                            <div className="text-[10px] text-slate-500 font-mono">{it.symbol}</div>
                          </div>
                          <div className="flex items-center gap-2 shrink-0">
                            <span className={`stat-num text-xs ${retText(it.ret?.['1'])}`}>
                              {pct(it.ret?.['1'])}
                            </span>
                            <Badge action={it.action} />
                          </div>
                        </Link>
                      ))}
                  </div>
                </div>
              )}
            </>
          )}
        </GlassCard>
      </div>

      <p className="text-[11px] text-slate-600 text-center pb-2">
        ⚠️ 산출 수치는 교육용 모의이며 투자 권유가 아닙니다.
      </p>
    </div>
  )
}

// 시그널 카운트 타일
function SigTile({ label, n, action }) {
  const cls =
    action === 'BUY'
      ? 'text-emerald-300'
      : action === 'SELL'
      ? 'text-rose-300'
      : 'text-slate-300'
  return (
    <div className="glass-soft p-3 text-center">
      <div className={`stat-num text-2xl ${cls}`}>{n}</div>
      <div className="text-[11px] text-slate-400 mt-0.5">{label}</div>
    </div>
  )
}
