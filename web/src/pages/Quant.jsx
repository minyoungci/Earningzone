import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useApi, getQuant } from '../api'
import { money, num } from '../lib/format'
import { EASE_OUT, useHasHover } from '../lib/motion'
import Spinner from '../components/ui/Spinner'
import Badge from '../components/ui/Badge'
import Gauge from '../components/ui/Gauge'

const fade = {
  hidden: { opacity: 0, y: 18 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: EASE_OUT } },
}

// 섹션 에러/빈 상태 공통 박스 (Dashboard 패턴)
function StateBox({ children }) {
  return <div className="glass-soft p-6 text-sm text-slate-400 text-center">{children}</div>
}

function ErrorBox({ err }) {
  return (
    <div className="glass-soft p-6 text-sm text-rose-300 text-center">
      데이터를 불러오지 못했습니다 · {String(err?.message || err)}
    </div>
  )
}

// 시장 토글 탭: kr(한국 대형) / kosdaq(코스닥) / us(미국 대형) / usgrowth(미국 성장) / all(전체)
const MARKET_TABS = [
  { key: 'kr', label: '🇰🇷 대형' },
  { key: 'kosdaq', label: '🇰🇷 코스닥' },
  { key: 'us', label: '🇺🇸 대형' },
  { key: 'usgrowth', label: '🇺🇸 성장' },
  { key: 'all', label: '🌐 전체' },
]

// glass pill 스타일 시장 선택 탭 — 활성 탭은 그라디언트 강조
function MarketTabs({ market, onChange }) {
  return (
    <div
      role="tablist"
      aria-label="시장 선택"
      className="inline-flex items-center gap-1 p-1 rounded-full glass-soft"
    >
      {MARKET_TABS.map((t) => {
        const active = market === t.key
        return (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(t.key)}
            className={`px-4 py-1.5 rounded-full text-xs font-bold transition-colors duration-200 border ${
              active
                ? 'bg-gradient-to-r from-indigo-500/30 to-pink-500/20 text-white border-indigo-400/40 shadow-[0_0_14px_rgba(99,102,241,0.35)]'
                : 'text-slate-400 border-transparent hover:text-slate-200 hover:bg-white/5'
            }`}
          >
            {t.label}
          </button>
        )
      })}
    </div>
  )
}

// 랭킹 배지: 1~3위는 금·은·동, 나머지는 무채색
const rankCls = (rank) =>
  rank === 1
    ? 'bg-amber-500/20 text-amber-300 border-amber-400/40'
    : rank === 2
    ? 'bg-slate-400/20 text-slate-200 border-slate-300/40'
    : rank === 3
    ? 'bg-orange-500/15 text-orange-300 border-orange-400/30'
    : 'bg-white/5 text-slate-400 border-white/10'

// 팩터 소형 칩: 라벨 + 값
function FactorChip({ label, v, d = 1, suffix = '' }) {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-white/5 border border-white/10 text-[10px] text-slate-400">
      {label}
      <span className="stat-num text-slate-300">{v == null ? '-' : num(v, d) + suffix}</span>
    </span>
  )
}

// 매매 플랜 한 줄: 라벨 + 가격 레벨
function PlanRow({ label, children }) {
  return (
    <div className="flex items-center justify-between gap-2 text-xs">
      <span className="text-slate-500">{label}</span>
      <span className="stat-num text-slate-300 text-right">{children}</span>
    </div>
  )
}

function PickCard({ pick, rank, index }) {
  const nav = useNavigate()
  const hasHover = useHasHover()
  const {
    symbol, name, price, currency, quantScore,
    factors = {}, plan = {}, action, reasons = [], options,
  } = pick || {}
  const rr = plan.rr

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
      {/* 헤더: 랭킹 + 종목명/코드 + 액션 배지 */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0">
          <span
            className={`shrink-0 w-8 h-8 rounded-xl border flex items-center justify-center text-sm font-extrabold stat-num ${rankCls(rank)}`}
          >
            {rank}
          </span>
          <div className="min-w-0">
            <div className="font-bold text-[15px] truncate group-hover:text-white transition-colors">
              {name || symbol}
            </div>
            <div className="text-xs text-slate-500 font-mono mt-0.5">{symbol}</div>
          </div>
        </div>
        <Badge action={action} />
      </div>

      {/* 현재가 + 퀀트 스코어 큰 숫자 */}
      <div className="flex items-end justify-between gap-3">
        <div className="stat-num text-2xl leading-none">{money(price, currency)}</div>
        <div className="flex flex-col items-end">
          <span className="text-[10px] text-slate-500">QUANT SCORE</span>
          <span className="stat-num text-3xl leading-none bg-gradient-to-r from-indigo-300 to-pink-300 bg-clip-text text-transparent">
            {num(quantScore, 1)}
          </span>
        </div>
      </div>

      {/* 게이지 (0~100 스코어 → -10..+10 스케일로 변환해 재사용) */}
      <Gauge score={(quantScore || 0) / 10} max={10} />

      {/* 팩터 칩 */}
      <div className="flex flex-wrap gap-1.5">
        <FactorChip label="M20" v={factors.mom20} suffix="%" />
        <FactorChip label="M60" v={factors.mom60} suffix="%" />
        <FactorChip label="RSI" v={factors.rsi} d={0} />
        <FactorChip label="ADX" v={factors.adx} d={0} />
        <FactorChip label="거래량" v={factors.volumeSurge} suffix="x" />
        {/* pos52 는 백엔드(levels.range_52w)가 이미 0~100 스케일로 반환 */}
        <FactorChip label="52주" v={factors.pos52} d={0} suffix="%" />
      </div>

      {/* 매매 플랜 */}
      <div className="glass-soft rounded-2xl p-3 flex flex-col gap-1.5">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] font-bold text-slate-400">매매 플랜</span>
          {plan.inZone && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-400/30">
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75 animate-ping" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-400" />
              </span>
              진입 구간 도달
            </span>
          )}
        </div>
        <PlanRow label="진입존">
          {plan.entryLow == null || plan.entryHigh == null
            ? '-'
            : `${money(plan.entryLow, currency)} ~ ${money(plan.entryHigh, currency)}`}
        </PlanRow>
        <PlanRow label="목표">
          <span className="text-up">{plan.target == null ? '-' : money(plan.target, currency)}</span>
        </PlanRow>
        <PlanRow label="손절">
          <span className="text-down">{plan.stop == null ? '-' : money(plan.stop, currency)}</span>
        </PlanRow>
        <PlanRow label="R:R">
          <span className={rr != null && rr >= 1.5 ? 'text-emerald-300 font-bold' : ''}>
            {rr == null ? '-' : `1 : ${num(rr, 2)}`}
          </span>
        </PlanRow>
        {plan.note && (
          <div className="text-[11px] text-slate-500 leading-relaxed pt-1 border-t border-white/5">
            {plan.note}
          </div>
        )}
      </div>

      {/* 추천 이유 — 백엔드 reasons(팩터 기반 한국어 근거) ✓ 불릿, 최대 4줄 */}
      {reasons.length > 0 && (
        <div className="flex flex-col gap-1">
          <span className="text-[11px] font-bold text-slate-400">추천 이유</span>
          <ul className="flex flex-col gap-0.5">
            {reasons.slice(0, 4).map((r, i) => (
              <li key={i} className="flex items-start gap-1.5 text-[11px] text-slate-400 leading-relaxed">
                <span className="text-emerald-400 shrink-0">✓</span>
                <span className="min-w-0">{r}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 옵션 플로우(미국 종목, CBOE 15분 지연) — P/C·ATM IV 칩 + 신호 요약 */}
      {options && (
        <div className="glass-soft rounded-2xl p-3 flex flex-col gap-1.5">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-bold text-violet-300">옵션 플로우</span>
            <span className="text-[10px] text-slate-500">CBOE · 15분 지연</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {options.pcVol != null && (
              <FactorChip label="P/C" v={options.pcVol} d={2} />
            )}
            {options.atmIV != null && (
              <FactorChip label="ATM IV" v={options.atmIV * 100} d={0} suffix="%" />
            )}
            {(options.hot || []).slice(0, 1).map((h) => (
              <span key={h.expiry + h.type + h.strike}
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] border ${h.type === 'C' ? 'bg-emerald-500/10 text-emerald-300 border-emerald-400/25' : 'bg-rose-500/10 text-rose-300 border-rose-400/25'}`}>
                🔥 {h.strike}{h.type === 'C' ? '콜' : '풋'} OI {h.ratio}배
              </span>
            ))}
          </div>
          {(options.alerts || []).slice(0, 2).map((a, i) => (
            <div key={i} className="text-[11px] text-slate-400 leading-relaxed">· {a.detail}</div>
          ))}
        </div>
      )}
    </motion.button>
  )
}

// 수급 레이더 의견 배지: BUY/SELL 은 기존 Badge 재사용, WATCH 는 커스텀 앰버 칩
function OpinionBadge({ opinion }) {
  if (opinion === 'WATCH') {
    return (
      <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold border bg-amber-500/15 text-amber-300 border-amber-400/30">
        관찰
      </span>
    )
  }
  return <Badge action={opinion} />
}

// 수급 레이더 카드: 종목/현재가/의견 + 감지된 수급 신호(label 칩 + detail 한 줄)
function FlowAlertCard({ item, index }) {
  const nav = useNavigate()
  const hasHover = useHasHover()
  const { symbol, name, price, currency, flowScore, opinion, alerts = [] } = item || {}

  return (
    <motion.button
      type="button"
      onClick={() => nav(`/symbol/${symbol}`)}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, delay: index * 0.04, ease: EASE_OUT }}
      whileHover={hasHover ? { y: -4 } : undefined}
      whileTap={{ scale: 0.985 }}
      className="glass glass-hover p-5 text-left w-full flex flex-col gap-3 group"
    >
      {/* 헤더: 종목명/코드 + 의견 배지 */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-bold text-[15px] truncate group-hover:text-white transition-colors">
            {name || symbol}
          </div>
          <div className="text-xs text-slate-500 font-mono mt-0.5">{symbol}</div>
        </div>
        <OpinionBadge opinion={opinion} />
      </div>

      {/* 현재가 + 수급 점수 */}
      <div className="flex items-end justify-between gap-3">
        <div className="stat-num text-xl leading-none">{money(price, currency)}</div>
        <div className="flex flex-col items-end">
          <span className="text-[10px] text-slate-500">FLOW SCORE</span>
          <span className="stat-num text-2xl leading-none bg-gradient-to-r from-amber-300 to-rose-300 bg-clip-text text-transparent">
            {num(flowScore, 0)}
          </span>
        </div>
      </div>

      {/* 감지 신호 리스트: label 칩 + detail 한 줄 */}
      <div className="flex flex-col gap-1.5">
        {alerts.map((a, i) => (
          <div key={i} className="flex items-start gap-2 min-w-0">
            <span className="shrink-0 inline-flex items-center px-2 py-0.5 rounded-full bg-white/5 border border-white/10 text-[10px] font-bold text-slate-300">
              {a.label}
            </span>
            <span className="text-[11px] text-slate-400 leading-relaxed truncate">{a.detail}</span>
          </div>
        ))}
      </div>
    </motion.button>
  )
}

export default function Quant() {
  // 시장 선택 상태 — 전환 시 deps 로 재조회 (60초 폴링 유지)
  const [market, setMarket] = useState('kr')
  // 60초 주기 백그라운드 폴링 (깜빡임 없이 값만 갱신)
  const quant = useApi(() => getQuant(10, market), [market], { pollMs: 60000 })
  // 시장 전환 직후엔 이전 시장 응답이 남아있을 수 있어 stale 로 간주(스피너 표시).
  // 응답에 market 키가 없으면(구버전 서버) 기존 동작 그대로.
  const isStale = quant.data?.market != null && quant.data.market !== market
  const meta = isStale ? null : quant.data
  const picks = meta?.picks || []
  // 같은 analyze 패스에서 추출한 수급 이상 신호(추가 API 호출 없음)
  const flowAlerts = meta?.flowAlerts || []
  const pending = quant.loading || (isStale && !quant.err)
  // 새 유니버스는 첫 스크리닝에 수십 초 걸릴 수 있음 → 안내 문구
  const loadingLabel =
    market === 'kr' || market === 'kosdaq'
      ? '퀀트 스크리닝 중(첫 조회는 오래 걸려요)…'
      : '미국 유니버스 스크리닝 중(첫 조회는 오래 걸려요)…'

  return (
    <div className="max-w-7xl mx-auto flex flex-col gap-8">
      {/* ── 히어로 헤더 ── */}
      <motion.header
        variants={fade}
        initial="hidden"
        animate="show"
        className="glass p-6 md:p-8 overflow-hidden relative"
      >
        <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-3xl md:text-4xl font-extrabold tracking-tight bg-gradient-to-r from-indigo-300 via-sky-200 to-pink-300 bg-clip-text text-transparent">
                퀀트 종목 발굴
              </h1>
              {meta?.universeSize != null && (
                <span className="px-3 py-1 rounded-full text-xs font-bold bg-indigo-500/15 text-indigo-200 border border-indigo-400/30">
                  유니버스 {meta.universeSize}종목
                </span>
              )}
            </div>
            <p className="text-slate-400 text-sm mt-2 max-w-xl leading-relaxed">
              모멘텀·추세질·수급·진입타이밍 팩터를 가중 결합한 퀀트 스코어로 한국 대형·코스닥,
              미국 대형·성장주 유니버스를 스크리닝합니다. 카드를 눌러 상세 분석으로 이동하세요.
            </p>
          </div>
          {meta?.generatedAt && (
            <div className="text-xs text-slate-500 shrink-0 flex items-center gap-2">
              {/* 실시간 폴링 인디케이터 (60초 주기 백그라운드 갱신) */}
              <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-emerald-500/10 text-emerald-300 border border-emerald-400/20">
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75 animate-ping" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-400" />
                </span>
                실시간 갱신 중
              </span>
              <span>
                업데이트 · <span className="stat-num text-slate-400">{meta.generatedAt}</span>
              </span>
            </div>
          )}
        </div>

        {/* 시장 토글 탭 (kr/kosdaq/us/usgrowth/all) — 전환 시 해당 유니버스로 재스크리닝.
            탭 5개 pill 이 좁은 화면(≈375px)보다 넓어 헤더 overflow-hidden 에 잘릴 수 있어
            래퍼에 가로 스크롤을 허용한다. */}
        <div className="mt-5 flex items-center gap-3 flex-wrap">
          <div className="max-w-full overflow-x-auto py-1 -my-1 px-1 -mx-1">
            <MarketTabs market={market} onChange={setMarket} />
          </div>
          <span className="text-[11px] text-slate-500">
            새 시장 첫 스크리닝은 수십 초 걸릴 수 있어요
          </span>
        </div>
      </motion.header>

      {/* ── 픽 카드 그리드 ── */}
      <section>
        <div className="flex items-baseline justify-between mb-4">
          <h2 className="text-lg font-bold">퀀트 스코어 TOP {picks.length || 10}</h2>
          {picks.length > 0 && (
            <span className="text-xs text-slate-500 stat-num">{picks.length}종목</span>
          )}
        </div>

        {pending ? (
          <div className="glass-soft"><Spinner label={loadingLabel} /></div>
        ) : quant.err ? (
          <ErrorBox err={quant.err} />
        ) : !picks.length ? (
          <StateBox>조건을 만족하는 종목이 없습니다.</StateBox>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {picks.map((pick, i) => (
              <PickCard key={pick.symbol} pick={pick} rank={i + 1} index={i} />
            ))}
          </div>
        )}
      </section>

      {/* ── 수급 레이더: 전체 유니버스에서 거래량·호가·OBV 기반 수급 이상만 추출 ── */}
      {!pending && !quant.err && (
        <section>
          <div className="flex items-baseline justify-between mb-4">
            <h2 className="text-lg font-bold">🚨 수급 레이더</h2>
            {flowAlerts.length > 0 && (
              <span className="text-xs text-slate-500 stat-num">{flowAlerts.length}종목</span>
            )}
          </div>

          {!flowAlerts.length ? (
            <StateBox>현재 감지된 수급 이상 신호 없음</StateBox>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {flowAlerts.map((f, i) => (
                <FlowAlertCard key={f.symbol} item={f} index={i} />
              ))}
            </div>
          )}

          {/* 데이터 출처 각주 */}
          <p className="mt-3 text-[11px] text-slate-500 leading-relaxed">
            한국 종목은 거래량·호가·OBV 기반 수급 신호(토스 API는 옵션 미제공),
            미국 종목은 여기에 <span className="text-violet-300">CBOE 옵션 플로우</span>(P/C·신규
            대량 포지션·단기 콜 집중, 15분 지연)를 더해 분석합니다
          </p>
        </section>
      )}

      {/* ── 하단 고지 ── */}
      <div className="glass-soft p-4 text-[11px] text-slate-500 text-center leading-relaxed">
        ⚠️ 교육용 · 투자 권유 아님. 퀀트 스코어와 매매 플랜은 과거 데이터 기반 참고 지표입니다.
      </div>
    </div>
  )
}
