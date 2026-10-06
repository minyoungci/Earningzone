import { useState } from 'react'
import { motion } from 'framer-motion'
import Icon from '../components/ui/Icon'
import { useApi, getRegime, getMacro, getNews, getCalendar } from '../api'
import { num, pct, retText } from '../lib/format'
import { EASE_OUT } from '../lib/motion'
import Spinner from '../components/ui/Spinner'

const fade = {
  hidden: { opacity: 0, y: 18 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: EASE_OUT } },
}

// 섹션 에러/빈 상태 공통 박스 (Quant/Dashboard 패턴)
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

/* ════════════════ ① 리스크 전광판 (레짐) ════════════════ */

// 레짐 5단계 메타: 한국어 라벨 + 단계별 강조 색 (게이지·텍스트)
const STAGES = [
  { key: 'STABLE', emoji: '🔵', label: '안정', text: 'text-sky-300', bar: 'from-sky-500 to-sky-300' },
  { key: 'TENSION', emoji: '🟤', label: '긴장', text: 'text-stone-300', bar: 'from-stone-500 to-stone-300' },
  { key: 'COMPRESSION', emoji: '🟡', label: '압축', text: 'text-yellow-300', bar: 'from-yellow-500 to-yellow-300' },
  { key: 'FRACTURE', emoji: '🟠', label: '균열', text: 'text-orange-300', bar: 'from-orange-500 to-orange-300' },
  { key: 'TRIGGER', emoji: '🔴', label: '방아쇠', text: 'text-rose-300', bar: 'from-rose-500 to-rose-300' },
]
const stageMeta = (stage) => STAGES.find((s) => s.key === stage) || STAGES[0]

// 컴포넌트 카드 신호 색: calm=슬레이트 / warn=앰버 / hot=로즈
const SIGNAL_CLS = {
  calm: 'border-white/10 text-slate-300',
  warn: 'border-amber-400/30 text-amber-300 bg-amber-500/5',
  hot: 'border-rose-400/30 text-rose-300 bg-rose-500/5',
}
const SIGNAL_DOT = { calm: 'bg-slate-400', warn: 'bg-amber-400', hot: 'bg-rose-400' }

// 0~100 위험 스코어 게이지 — 단계 색 그라디언트 채움 + 20단위 눈금
function RiskGauge({ score = 0, stage }) {
  const meta = stageMeta(stage)
  const clamped = Math.max(0, Math.min(100, Number(score) || 0))
  return (
    <div className="w-full">
      <div className="relative h-3.5 rounded-full bg-white/10 overflow-hidden">
        {/* GPU 합성 scaleX 채움 — 레이아웃 width 애니 대신(리폴링 중 매 프레임 레이아웃 회피) */}
        <div
          className={`absolute inset-y-0 left-0 w-full origin-left rounded-full bg-gradient-to-r ${meta.bar}`}
          style={{ transform: `scaleX(${clamped / 100})`, transition: 'transform 450ms var(--ease-out)' }}
        />
        {/* 20/40/60/80 단계 경계 눈금 */}
        {[20, 40, 60, 80].map((t) => (
          <div key={t} className="absolute inset-y-0 w-px bg-white/25" style={{ left: `${t}%` }} />
        ))}
      </div>
      <div className="flex justify-between mt-1 text-[10px] text-slate-500 stat-num">
        <span>0</span><span>20</span><span>40</span><span>60</span><span>80</span><span>100</span>
      </div>
    </div>
  )
}

// 레짐 구성 요소 카드 (VIX/VVIX/SPX/TLT/UUP/HYG)
function ComponentCard({ c }) {
  const cls = SIGNAL_CLS[c.signal] || SIGNAL_CLS.calm
  return (
    <div className={`glass-soft p-3 border flex flex-col gap-1 ${cls}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-bold text-slate-400">{c.label}</span>
        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${SIGNAL_DOT[c.signal] || SIGNAL_DOT.calm}`} />
      </div>
      <div className="flex items-baseline gap-2">
        <span className="stat-num text-lg leading-none">{c.value == null ? '-' : num(c.value, 2)}</span>
        {c.change != null && (
          <span className={`stat-num text-[11px] ${retText(c.change)}`}>{pct(c.change, 1)}</span>
        )}
      </div>
      <div className="text-[10px] text-slate-500 leading-relaxed">{c.detail || ''}</div>
    </div>
  )
}

function RegimeHero() {
  // 60초 폴링 — 리스크 레짐은 서버 캐시 300s 이지만 화면은 가볍게 갱신
  const { data, err, loading } = useApi(getRegime, [], { pollMs: 60000 })

  if (loading) return <div className="glass"><Spinner label="리스크 레짐 계산 중…" /></div>
  if (err && !data) return <ErrorBox err={err} />
  if (!data) return <StateBox>레짐 데이터가 없습니다.</StateBox>

  const meta = stageMeta(data.stage)
  const components = data.components || []

  return (
    <motion.section variants={fade} initial="hidden" animate="show" className="glass p-6 md:p-8 flex flex-col gap-5">
      {/* 헤더: 큰 이모지 + 단계명 + 스코어 */}
      <div className="flex flex-col md:flex-row md:items-center gap-4 md:gap-6">
        <div className="flex items-center gap-4 min-w-0">
          <span className={'regime-indicator ' + meta.text}><Icon name="globe" size={26} /></span>
          <div className="min-w-0">
            <div className="flex items-baseline gap-2 flex-wrap">
              <h1 className={`text-2xl md:text-3xl font-extrabold tracking-tight ${meta.text}`}>
                {data.stage} · {meta.label}
              </h1>
            </div>
            <p className="text-sm text-slate-300 mt-1 leading-relaxed">{data.guidance}</p>
          </div>
        </div>
        <div className="md:ml-auto flex flex-col items-start md:items-end shrink-0">
          <span className="text-[10px] text-slate-500">RISK SCORE</span>
          <span className={`stat-num text-4xl leading-none ${meta.text}`}>{num(data.score, 0)}</span>
          {data.generatedAt && (
            <span className="text-[10px] text-slate-500 mt-1">
              업데이트 <span className="stat-num">{data.generatedAt}</span>
            </span>
          )}
        </div>
      </div>

      {/* 0~100 게이지 */}
      <RiskGauge score={data.score} stage={data.stage} />

      {/* 구성 요소 6카드 */}
      <div className="grid gap-2.5 grid-cols-2 sm:grid-cols-3 lg:grid-cols-6">
        {components.map((c) => (
          <ComponentCard key={c.key} c={c} />
        ))}
      </div>

      {/* 5단계 범례 */}
      <div className="flex flex-wrap gap-x-4 gap-y-1.5">
        {STAGES.map((s) => {
          const active = s.key === data.stage
          return (
            <span
              key={s.key}
              className={`inline-flex items-center gap-1.5 text-[11px] ${
                active ? `font-bold ${s.text}` : 'text-slate-500'
              }`}
            >
              {s.emoji} {s.key} <span className="opacity-70">{s.label}</span>
            </span>
          )
        })}
      </div>

      {/* 데이터 한계 각주 (예: MOVE 프록시) */}
      {data.note && (
        <p className="text-[11px] text-slate-500 leading-relaxed border-t border-white/5 pt-3">※ {data.note}</p>
      )}
    </motion.section>
  )
}

/* ════════════════ ② 시장 반응 보드 (매크로) ════════════════ */

// 외부 라이브러리 없는 인라인 SVG 스파크라인 — 값을 0..1 로 정규화해 polyline 으로 그린다
function Sparkline({ values = [], up = true, w = 96, h = 28 }) {
  const vs = (values || []).filter((v) => v != null && Number.isFinite(Number(v))).map(Number)
  if (vs.length < 2) return <div style={{ width: w, height: h }} />
  const min = Math.min(...vs)
  const max = Math.max(...vs)
  const span = max - min || 1 // 평평한 시리즈도 0 나눗셈 없이 중앙선으로
  const pad = 2
  const pts = vs
    .map((v, i) => {
      const x = pad + (i / (vs.length - 1)) * (w - pad * 2)
      const y = pad + (1 - (v - min) / span) * (h - pad * 2)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
  return (
    // 등락색은 프로젝트 공통(text-up=상승 빨강 / text-down=하락 파랑)을 currentColor 로 상속
    <svg
      width={w}
      height={h}
      viewBox={`0 0 ${w} ${h}`}
      className={`shrink-0 ${up ? 'text-up' : 'text-down'}`}
      aria-hidden="true"
    >
      <polyline
        points={pts}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
        opacity="0.9"
      />
    </svg>
  )
}

// 매크로 타일: 라벨 / 가격 / 1일·5일 등락 / 스파크라인
function MacroTile({ item, index }) {
  const { label, price, currency, chg1d, chg5d, spark } = item || {}
  const priceText =
    price == null
      ? '-'
      : currency === 'KRW'
      ? Number(price).toLocaleString('ko-KR')
      : Number(price).toLocaleString('en-US', { maximumFractionDigits: 2 })
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: index * 0.03, ease: EASE_OUT }}
      className="glass-soft p-3.5 flex flex-col gap-1.5"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-bold text-slate-400 truncate">{label}</span>
        {chg5d != null && (
          <span className={`stat-num text-[10px] ${retText(chg5d)}`}>5D {pct(chg5d, 1)}</span>
        )}
      </div>
      <div className="flex items-end justify-between gap-2">
        <div className="min-w-0">
          <div className="stat-num text-lg leading-none truncate">{priceText}</div>
          <div className={`stat-num text-xs mt-1 ${retText(chg1d)}`}>{chg1d == null ? '-' : pct(chg1d, 2)}</div>
        </div>
        <Sparkline values={spark} up={(chg1d ?? 0) >= 0} />
      </div>
    </motion.div>
  )
}

function MacroBoard() {
  const { data, err, loading } = useApi(getMacro, [], { pollMs: 60000 })

  return (
    <motion.section variants={fade} initial="hidden" animate="show">
      <div className="flex items-baseline justify-between mb-4">
        <h2 className="text-lg font-bold">🌡️ 시장 반응 보드</h2>
        {data?.generatedAt && (
          <span className="text-xs text-slate-500 stat-num">{data.generatedAt}</span>
        )}
      </div>

      {loading ? (
        <div className="glass-soft"><Spinner label="매크로 보드 불러오는 중…" /></div>
      ) : err && !data ? (
        <ErrorBox err={err} />
      ) : !(data?.items || []).length ? (
        <StateBox>매크로 데이터가 없습니다.</StateBox>
      ) : (
        <>
          {/* 지금 시장이 무엇에 반응 중인지 한 줄 요약 */}
          {data.reaction && (
            <div className="glass-soft p-3 mb-3 text-sm text-slate-300 leading-relaxed">💬 {data.reaction}</div>
          )}
          <div className="grid gap-2.5 grid-cols-2 sm:grid-cols-3 lg:grid-cols-5">
            {data.items.map((it, i) => (
              <MacroTile key={it.key} item={it} index={i} />
            ))}
          </div>
        </>
      )}
    </motion.section>
  )
}

/* ════════════════ ③ 중요 뉴스 ════════════════ */

// 태그 칩 색: 카테고리별 은은한 틴트
const TAG_CLS = {
  연준: 'bg-indigo-500/15 text-indigo-300 border-indigo-400/25',
  지표: 'bg-sky-500/15 text-sky-300 border-sky-400/25',
  실적: 'bg-emerald-500/15 text-emerald-300 border-emerald-400/25',
  지정학: 'bg-orange-500/15 text-orange-300 border-orange-400/25',
  에너지: 'bg-amber-500/15 text-amber-300 border-amber-400/25',
  환율: 'bg-violet-500/15 text-violet-300 border-violet-400/25',
}
const tagCls = (t) => TAG_CLS[t] || 'bg-white/5 text-slate-400 border-white/10'

function NewsRow({ item, index }) {
  return (
    <motion.a
      href={item.link}
      target="_blank"
      rel="noopener noreferrer"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: Math.min(index, 12) * 0.02, ease: EASE_OUT }}
      className={`block px-4 py-3 rounded-2xl transition hover:bg-white/5 ${
        item.important ? 'bg-rose-500/5 border border-rose-400/15' : 'border border-transparent'
      }`}
    >
      <div className="flex items-start gap-2">
        {item.important && (
          <span className="shrink-0 mt-0.5 inline-flex items-center px-1.5 py-0.5 rounded-md text-[10px] font-extrabold bg-rose-500/20 text-rose-300 border border-rose-400/40">
            중요
          </span>
        )}
        <span className="text-sm text-slate-200 leading-snug min-w-0">{item.title}</span>
      </div>
      <div className="flex items-center gap-2 mt-1.5 flex-wrap">
        {(item.tags || []).map((t) => (
          <span key={t} className={`inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] border ${tagCls(t)}`}>
            {t}
          </span>
        ))}
        <span className="text-[10px] text-slate-500 ml-auto shrink-0">
          {item.source}{item.time ? ` · ${item.time}` : ''}
        </span>
      </div>
    </motion.a>
  )
}

function NewsSection() {
  const { data, err, loading } = useApi(getNews, [], { pollMs: 300000 })
  const items = data?.items || []
  // 중요 뉴스를 상단에 고정하고 나머지는 원래 순서(최신순) 유지
  const sorted = [...items.filter((n) => n.important), ...items.filter((n) => !n.important)]

  return (
    <motion.section variants={fade} initial="hidden" animate="show">
      <div className="flex items-baseline justify-between mb-4">
        <h2 className="text-lg font-bold">📰 중요 뉴스</h2>
        {data?.generatedAt && <span className="text-xs text-slate-500 stat-num">{data.generatedAt}</span>}
      </div>

      {loading ? (
        <div className="glass-soft"><Spinner label="뉴스 불러오는 중…" /></div>
      ) : err && !data ? (
        <ErrorBox err={err} />
      ) : !sorted.length ? (
        <StateBox>표시할 뉴스가 없습니다.</StateBox>
      ) : (
        <div className="glass p-2 flex flex-col gap-1 max-h-[520px] overflow-y-auto">
          {sorted.map((n, i) => (
            <NewsRow key={(n.link || n.title) + i} item={n} index={i} />
          ))}
        </div>
      )}
    </motion.section>
  )
}

/* ════════════════ ④ 이번 주 캘린더 ════════════════ */

// 우리 유니버스(tossbot/config.py US_UNIVERSE + US_GROWTH_UNIVERSE)와의 교집합 하이라이트용 티커 셋
const OUR_UNIVERSE = new Set([
  // US 대형
  'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA', 'AVGO', 'JPM', 'V',
  'MA', 'UNH', 'XOM', 'LLY', 'JNJ', 'PG', 'HD', 'COST', 'WMT', 'KO',
  'PEP', 'ORCL', 'NFLX', 'AMD', 'CRM', 'ADBE', 'QCOM', 'TXN', 'INTC', 'DIS',
  // US 성장
  'IONQ', 'RKLB', 'SOFI', 'AFRM', 'UPST', 'RIVN', 'LCID', 'PLUG', 'JOBY', 'ACHR',
  'OKLO', 'SMR', 'RGTI', 'QBTS', 'SOUN', 'BBAI', 'LUNR', 'ASTS', 'TMDX', 'CELH',
  'HIMS', 'ROKU', 'U', 'PATH', 'ETSY', 'PINS', 'DKNG', 'HOOD', 'CRSP', 'BEAM',
])

// 경제지표 중요도 배지 (Nasdaq importance 값이 다양할 수 있어 느슨하게 매핑)
const impCls = (imp) => {
  const v = String(imp || '').toLowerCase()
  if (v.includes('high') || v === '3') return 'bg-rose-500/15 text-rose-300 border-rose-400/30'
  if (v.includes('med') || v === '2') return 'bg-amber-500/15 text-amber-300 border-amber-400/30'
  return 'bg-white/5 text-slate-400 border-white/10'
}

function EconRow({ e }) {
  const isUS = e.country === 'United States' || e.country === '미국'
  return (
    <div className={`flex items-center gap-3 px-4 py-2.5 rounded-2xl ${isUS ? 'bg-white/5' : ''}`}>
      <div className="w-20 shrink-0">
        <div className="stat-num text-xs text-slate-300">{e.date}</div>
        {e.time && <div className="stat-num text-[10px] text-slate-500">{e.time}</div>}
      </div>
      <span className={`shrink-0 inline-flex items-center px-1.5 py-0.5 rounded-md text-[10px] font-bold border ${impCls(e.importance)}`}>
        {isUS ? '🇺🇸' : ''} {e.country || '-'}
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-sm text-slate-200 truncate">{e.event}</div>
        <div className="text-[10px] text-slate-500 stat-num">
          발표 {e.actual || '-'} · 예상 {e.forecast || '-'} · 이전 {e.previous || '-'}
        </div>
      </div>
    </div>
  )
}

function EarningsRow({ e }) {
  const mine = OUR_UNIVERSE.has(String(e.symbol || '').toUpperCase())
  return (
    <div
      className={`flex items-center gap-3 px-4 py-2.5 rounded-2xl ${
        mine ? 'bg-indigo-500/10 border border-indigo-400/25' : ''
      }`}
    >
      <div className="w-20 shrink-0 stat-num text-xs text-slate-300">{e.date}</div>
      <span className="shrink-0 stat-num text-xs font-bold text-slate-200 w-16 truncate">{e.symbol}</span>
      <div className="min-w-0 flex-1 text-sm text-slate-300 truncate">{e.name}</div>
      {e.time && <span className="shrink-0 text-[10px] text-slate-500">{e.time}</span>}
      {mine && (
        <span className="shrink-0 inline-flex items-center px-1.5 py-0.5 rounded-md text-[10px] font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-400/40">
          유니버스
        </span>
      )}
    </div>
  )
}

function CalendarSection() {
  const [tab, setTab] = useState('econ') // 'econ' 지표 | 'earnings' 실적
  const { data, err, loading } = useApi(() => getCalendar(7), [], { pollMs: 1800000 })

  const econ = data?.econ || []
  const earnings = data?.earnings || []
  // 미국 이벤트 우선 정렬은 백엔드 계약이지만 방어적으로 한 번 더 보장
  const econSorted = [
    ...econ.filter((e) => e.country === 'United States' || e.country === '미국'),
    ...econ.filter((e) => !(e.country === 'United States' || e.country === '미국')),
  ]
  // 유니버스 교집합 실적을 상단으로
  const earnSorted = [
    ...earnings.filter((e) => OUR_UNIVERSE.has(String(e.symbol || '').toUpperCase())),
    ...earnings.filter((e) => !OUR_UNIVERSE.has(String(e.symbol || '').toUpperCase())),
  ]

  return (
    <motion.section variants={fade} initial="hidden" animate="show">
      <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
        <h2 className="text-lg font-bold">🗓️ 이번 주 캘린더</h2>
        {/* 지표/실적 탭 */}
        <div role="tablist" aria-label="캘린더 종류" className="inline-flex items-center gap-1 p-1 rounded-full glass-soft">
          {[
            { key: 'econ', label: `지표 ${econ.length ? `(${econ.length})` : ''}` },
            { key: 'earnings', label: `실적 ${earnings.length ? `(${earnings.length})` : ''}` },
          ].map((t) => (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={tab === t.key}
              onClick={() => setTab(t.key)}
              className={`px-4 py-1.5 rounded-full text-xs font-bold transition-colors duration-200 border ${
                tab === t.key
                  ? 'bg-gradient-to-r from-indigo-500/30 to-pink-500/20 text-white border-indigo-400/40'
                  : 'text-slate-400 border-transparent hover:text-slate-200 hover:bg-white/5'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="glass-soft"><Spinner label="캘린더 불러오는 중…" /></div>
      ) : err && !data ? (
        <ErrorBox err={err} />
      ) : tab === 'econ' ? (
        !econSorted.length ? (
          <StateBox>이번 주 경제지표 일정이 없습니다.</StateBox>
        ) : (
          <div className="glass p-2 flex flex-col gap-0.5 max-h-[440px] overflow-y-auto">
            {econSorted.map((e, i) => (
              <EconRow key={`${e.date}-${e.event}-${i}`} e={e} />
            ))}
          </div>
        )
      ) : !earnSorted.length ? (
        <StateBox>이번 주 실적 발표 일정이 없습니다.</StateBox>
      ) : (
        <div className="glass p-2 flex flex-col gap-0.5 max-h-[440px] overflow-y-auto">
          {earnSorted.map((e, i) => (
            <EarningsRow key={`${e.date}-${e.symbol}-${i}`} e={e} />
          ))}
        </div>
      )}
    </motion.section>
  )
}

/* ════════════════ 페이지 ════════════════ */

export default function Market() {
  return (
    <div className="max-w-7xl mx-auto flex flex-col gap-8">
      {/* ① 리스크 전광판 히어로 */}
      <RegimeHero />

      {/* ② 시장 반응 보드 */}
      <MacroBoard />

      {/* ③ 중요 뉴스 + ④ 캘린더 — 넓은 화면에서 2열 */}
      <div className="grid gap-8 xl:grid-cols-2">
        <NewsSection />
        <CalendarSection />
      </div>

      {/* 하단 각주 */}
      <div className="glass-soft p-4 text-[11px] text-slate-500 text-center leading-relaxed">
        교육용 · 데이터: CBOE(15분 지연)·토스·Nasdaq·RSS
      </div>
    </div>
  )
}
