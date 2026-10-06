import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useApi, getSim, getAutopilot, startAutopilot, stopAutopilot, getRegime, getSimAccounts, resetAutopilotLogs } from '../api'
import { won0, pct, retText, money, signedWon, FX_ESTIMATED_NOTE } from '../lib/format'
import GlassCard from '../components/ui/GlassCard'
import StatTile from '../components/ui/StatTile'
import Spinner from '../components/ui/Spinner'

// ── 오토파일럿 모니터링 (모의 전용) ─────────────────────────────────
// 5초 폴링으로 autopilot 상태 + 모의계좌를 함께 보여주는 관제 화면.
// 실주문 경로와 완전히 분리 — 여기서 보이는 매매는 전부 모의계좌(sim)다.

const MARKET_LABEL = { kr: '한국 대형', kosdaq: '코스닥', us: '미국 대형', usgrowth: '미국 성장', all: '전체' }

// 로그 시각 표기: epoch(초/밀리초)·문자열 모두 허용 (Sim.jsx 와 동일 규칙)
const apLogTime = (l) => {
  const t = l.time ?? l.ts ?? l.at
  if (t == null) return ''
  if (typeof t === 'number') {
    return new Date(t > 1e12 ? t : t * 1000).toLocaleTimeString('ko-KR', { hour12: false })
  }
  const d = new Date(t)
  return Number.isNaN(d.getTime()) ? String(t) : d.toLocaleTimeString('ko-KR', { hour12: false })
}

const clampPct = (v) => Math.max(0, Math.min(100, v))

// ── 레짐 미니 배너: 시장 위험 단계 한 줄 요약 (60초 폴링) ───────────
// stage 별 배경 틴트 — 계약 (R) 의 5단계(🔵🟤🟡🟠🔴)와 1:1 매핑
const REGIME_TINT = {
  STABLE: 'bg-sky-500/10 border-sky-400/25',
  TENSION: 'bg-amber-800/15 border-amber-600/25',
  COMPRESSION: 'bg-yellow-500/10 border-yellow-400/25',
  FRACTURE: 'bg-orange-500/10 border-orange-400/30',
  TRIGGER: 'bg-rose-500/15 border-rose-400/35',
}

function RegimeBanner() {
  // 60초 폴링 — 실패/로딩 중이면 조용히 숨김(오토파일럿 관제 자체는 영향 없음)
  const { data: rg } = useApi(() => getRegime(), [], { pollMs: 60000 })
  if (!rg || !rg.stage) return null
  const tint = REGIME_TINT[rg.stage] || 'glass-soft'
  return (
    <div className={`rounded-2xl border px-4 py-3 flex items-center gap-3 flex-wrap ${tint}`}>
      <span className="text-xl leading-none">{rg.emoji}</span>
      <span className="font-bold text-sm">{rg.stage}</span>
      {rg.score != null && (
        <span className="text-[11px] px-2 py-0.5 rounded-full glass-soft text-slate-300 stat-num">위험도 {rg.score}</span>
      )}
      <span className="text-xs text-slate-300 flex-1 min-w-[180px]">{rg.guidance}</span>
      <Link to="/market" className="text-[11px] text-slate-400 hover:underline shrink-0">자세히 →</Link>
    </div>
  )
}

// ── 손절~목표 진행바: 손절=0% · 목표=100% 로 보고 현재가 위치를 표시 ──
function PlanBar({ plan, currentPrice, currency }) {
  const target = plan?.target
  const stop = plan?.stop
  const entry = plan?.entryPrice
  // target/stop 이 없거나 구간이 0 이면 바 생략
  if (target == null || stop == null || Number(target) === Number(stop)) return null
  const range = Number(target) - Number(stop)
  const posPct = currentPrice != null ? clampPct(((Number(currentPrice) - Number(stop)) / range) * 100) : null
  const entryPct = entry != null ? clampPct(((Number(entry) - Number(stop)) / range) * 100) : null

  return (
    <div className="mt-2">
      <div className="relative h-2 rounded-full bg-white/[0.08]">
        {/* 손절(빨강)~목표(초록) 그라데이션 트랙 */}
        <div className="absolute inset-0 rounded-full bg-gradient-to-r from-rose-500/30 via-white/5 to-emerald-500/30" />
        {/* 진입가 마커 (회색 눈금) */}
        {entryPct != null && (
          <div
            className="absolute top-1/2 -translate-y-1/2 w-0.5 h-3 rounded bg-slate-400/70"
            style={{ left: `${entryPct}%` }}
            title={`진입 ${money(entry, currency)}`}
          />
        )}
        {/* 현재가 마커 (흰 점) */}
        {posPct != null && (
          <div
            className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-3 h-3 rounded-full bg-white shadow"
            style={{ left: `${posPct}%` }}
            title={`현재 ${money(currentPrice, currency)}`}
          />
        )}
      </div>
      <div className="flex items-center justify-between mt-1 text-[11px]">
        <span className="text-rose-300 stat-num">손절 {money(stop, currency)}</span>
        {posPct != null && <span className="text-slate-400 stat-num">{posPct.toFixed(0)}%</span>}
        <span className="text-emerald-300 stat-num">목표 {money(target, currency)}</span>
      </div>
    </div>
  )
}

// ── 상태 헤더: 가동 배지 · 사이클 · 설정 · 시작/중지 컨트롤 ──────────
function StatusHeader({ d, reload }) {
  const [params] = useSearchParams()
  const [busy, setBusy] = useState(false)
  const [actionErr, setActionErr] = useState(null)
  // 시작 폼 기본값: 주기 60초 · 최대 3종목 · 1회 예산 100만원 · 한국 시장 · 레짐 가드 on
  // account: '' 이면 active 계좌(셀렉트 기본값)를 그대로 사용
  const [form, setForm] = useState({ intervalSec: 60, maxPositions: 3, budgetKrw: 1000000, market: 'kr', regimeGuard: true, account: '', strategy: params.get('strategy') === 'chart_confirmed' ? 'chart_confirmed' : 'legacy', riskPct: .5, minRR: 1.5 })
  // 모의 계좌 목록 — 시작 폼 셀렉트 + 가동 중 계좌명 매핑에 사용 (실패 시 셀렉트 숨김 → 서버가 active 계좌로 처리)
  const { data: accts } = useApi(() => getSimAccounts(), [])
  const accounts = Array.isArray(accts?.accounts) ? accts.accounts : []
  // status.account(id) → 계좌 이름. 목록에 없으면 id 그대로 표기.
  const accountName = (id) => accounts.find((a) => a.id === id)?.name || id

  const running = !!d.running
  const cfg = d.settings || {}
  const market = cfg.market || d.market || 'kr'

  const setField = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const start = async () => {
    if (busy) return
    setBusy(true)
    setActionErr(null)
    try {
      // 계좌: 셀렉트 선택값 > active 기본값. 목록 로드 실패 등으로 없으면 생략(서버가 active 로 처리).
      const account = form.account || accts?.active || null
      await startAutopilot({
        intervalSec: Number(form.intervalSec) || 60,
        maxPositions: Number(form.maxPositions) || 3,
        budgetKrw: Number(form.budgetKrw) || 1000000,
        market: form.market || 'kr',
        regimeGuard: !!form.regimeGuard,
        strategy: form.strategy,
        riskPct: Number(form.riskPct),
        minRR: Number(form.minRR),
        ...(account ? { account } : {}),
      })
      reload()
    } catch (e) {
      setActionErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  const stop = async () => {
    if (busy) return
    setBusy(true)
    setActionErr(null)
    try {
      await stopAutopilot()
      reload()
    } catch (e) {
      setActionErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <GlassCard>
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          {running ? (
            <span className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 font-bold flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              가동 중
            </span>
          ) : (
            <span className="text-[11px] px-2 py-0.5 rounded-full glass-soft text-slate-400 font-bold">중지됨</span>
          )}
          <span className="text-[11px] px-2 py-0.5 rounded-full glass-soft text-slate-300 stat-num">
            사이클 {d.cycles ?? 0}회
          </span>
          <span className="text-[11px] px-2 py-0.5 rounded-full glass-soft text-slate-300 stat-num">
            마지막 {d.lastCycleAt || '—'}
          </span>
        </div>
        <span className="text-[11px] px-2 py-0.5 rounded-full glass-soft text-amber-300">모의 전용 · 실주문 없음</span>
      </div>

      {running ? (
        <div className="flex items-end justify-between gap-3 flex-wrap">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 flex-1 min-w-[260px]">
            <div className="glass-soft rounded-xl px-3 py-2">
              <div className="text-[11px] text-slate-400">진입 전략</div>
              <div className="font-semibold text-sm">{cfg.strategy === 'chart_confirmed' ? '차트 확인' : '퀀트 지지 구간'}</div>
              {cfg.strategy === 'chart_confirmed' && <div className="text-xs text-slate-400 mt-1">위험 {cfg.riskPct}% · 순손익비 ≥ {cfg.minRR}</div>}
            </div>
            <div className="glass-soft rounded-xl px-3 py-2">
              <div className="text-[11px] text-slate-400">주기</div>
              <div className="stat-num font-semibold text-sm">{cfg.intervalSec ?? '—'}초</div>
            </div>
            <div className="glass-soft rounded-xl px-3 py-2">
              <div className="text-[11px] text-slate-400">최대 보유</div>
              <div className="stat-num font-semibold text-sm">{cfg.maxPositions ?? '—'}종목</div>
            </div>
            <div className="glass-soft rounded-xl px-3 py-2">
              <div className="text-[11px] text-slate-400">1회 예산</div>
              <div className="stat-num font-semibold text-sm">{cfg.budgetKrw != null ? won0(cfg.budgetKrw) + '원' : '—'}</div>
            </div>
            <div className="glass-soft rounded-xl px-3 py-2">
              <div className="text-[11px] text-slate-400">시장</div>
              <div className="font-semibold text-sm">{MARKET_LABEL[market] || market}</div>
            </div>
            {/* 계좌 타일 — status.account(id) 를 계좌 이름으로 매핑(모르면 id). 오토파일럿은 시작 시 계좌에 고정 */}
            {d.account && (
              <div className="glass-soft rounded-xl px-3 py-2">
                <div className="text-[11px] text-slate-400">계좌</div>
                <div className="font-semibold text-sm truncate" title={d.account}>{accountName(d.account)}</div>
              </div>
            )}
            {/* 레짐 요약 — status.regime {stage,emoji,score} (계약 (A)) + 가드 on/off */}
            {d.regime && (
              <div className="glass-soft rounded-xl px-3 py-2">
                <div className="text-[11px] text-slate-400">레짐 · 가드 {cfg.regimeGuard === false ? 'OFF' : 'ON'}</div>
                <div className="font-semibold text-sm">
                  {d.regime.emoji} {d.regime.stage}
                  {d.regime.score != null && <span className="stat-num text-slate-400 text-xs"> · {d.regime.score}</span>}
                </div>
              </div>
            )}
          </div>
          <button
            onClick={stop}
            disabled={busy}
            className="px-4 py-2.5 rounded-xl text-sm font-bold bg-rose-500/15 text-rose-300 border border-rose-400/30 hover:bg-rose-500/25 transition active:scale-[0.97] disabled:opacity-50"
          >
            ■ 중지
          </button>
        </div>
      ) : (
        <div>
        <div className="flex flex-wrap gap-3 mb-4">
          <label className="flex-1 min-w-[180px]"><span className="text-xs text-slate-400">진입 전략</span>
            <select aria-label="진입 전략" value={form.strategy} onChange={setField('strategy')} className="glass-soft w-full px-3 py-2 rounded-xl bg-transparent text-sm mt-1">
              <option value="legacy">퀀트 지지 구간 · 기존</option><option value="chart_confirmed">차트 확인 · 실험</option>
            </select>
          </label>
          {form.strategy === 'chart_confirmed' && <>
            <label className="flex-1 min-w-[130px]"><span className="text-xs text-slate-400">1종목 예상 손절 위험 (%)</span><input aria-label="1종목 예상 손절 위험 (%)" type="number" min="0.1" max="2" step="0.1" value={form.riskPct} onChange={setField('riskPct')} className="glass-soft w-full px-3 py-2 rounded-xl bg-transparent text-sm mt-1" /></label>
            <label className="flex-1 min-w-[130px]"><span className="text-xs text-slate-400">최소 순손익비</span><input aria-label="최소 순손익비" type="number" min="1" max="5" step="0.1" value={form.minRR} onChange={setField('minRR')} className="glass-soft w-full px-3 py-2 rounded-xl bg-transparent text-sm mt-1" /></label>
          </>}
        </div>
        {form.strategy === 'chart_confirmed' && <p className="text-xs text-slate-400 mb-4 leading-relaxed">완성 일봉의 돌파 → 리테스트 → 후속 종가, EMA20/50 상승 정렬, 확인봉 거래량 1.2배를 확인합니다. 현재가·수수료·매도세·환율을 반영해 순손익비와 수량을 계산합니다. 같은 신호 재진입을 막고 계획을 저장합니다. 손절 위험은 갭 발생 시 초과할 수 있으며, 기존 백테스트는 이 전략의 성과를 검증하지 않습니다.</p>}
        <div className="flex items-end gap-3 flex-wrap">
          <label className="flex-1 min-w-[90px]">
            <span className="text-[11px] text-slate-400">주기 (초)</span>
            <input
              type="number"
              min="10"
              value={form.intervalSec}
              onChange={setField('intervalSec')}
              className="glass-soft w-full px-3 py-2 rounded-xl bg-transparent outline-none text-sm stat-num mt-1"
            />
          </label>
          <label className="flex-1 min-w-[90px]">
            <span className="text-[11px] text-slate-400">최대 보유 (종목)</span>
            <input
              type="number"
              min="1"
              value={form.maxPositions}
              onChange={setField('maxPositions')}
              className="glass-soft w-full px-3 py-2 rounded-xl bg-transparent outline-none text-sm stat-num mt-1"
            />
          </label>
          <label className="flex-1 min-w-[110px]">
            <span className="text-[11px] text-slate-400">1회 예산 (원)</span>
            <input
              type="number"
              min="10000"
              step="10000"
              value={form.budgetKrw}
              onChange={setField('budgetKrw')}
              className="glass-soft w-full px-3 py-2 rounded-xl bg-transparent outline-none text-sm stat-num mt-1"
            />
          </label>
          <label className="flex-1 min-w-[90px]">
            <span className="text-[11px] text-slate-400">시장</span>
            <select
              value={form.market}
              onChange={setField('market')}
              className="glass-soft w-full px-3 py-2 rounded-xl bg-transparent outline-none text-sm mt-1"
            >
              <option value="kr" className="bg-slate-900">한국 대형</option>
              <option value="kosdaq" className="bg-slate-900">코스닥</option>
              <option value="us" className="bg-slate-900">미국 대형</option>
              <option value="usgrowth" className="bg-slate-900">미국 성장</option>
              <option value="all" className="bg-slate-900">전체</option>
            </select>
          </label>
          {/* 계좌 셀렉트 — 기본 active. 목록 로드 전/실패 시 숨김(서버가 active 계좌로 시작) */}
          {accounts.length > 0 && (
            <label className="flex-1 min-w-[110px]">
              <span className="text-[11px] text-slate-400">계좌</span>
              <select
                value={form.account || accts?.active || ''}
                onChange={setField('account')}
                className="glass-soft w-full px-3 py-2 rounded-xl bg-transparent outline-none text-sm mt-1"
              >
                {accounts.map((a) => (
                  <option key={a.id} value={a.id} className="bg-slate-900">{a.name || a.id}</option>
                ))}
              </select>
            </label>
          )}
          <button
            onClick={start}
            disabled={busy}
            className="px-4 py-2.5 rounded-xl text-sm font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-400/30 hover:bg-emerald-500/25 transition active:scale-[0.97] disabled:opacity-50"
          >
            ▶ 시작
          </button>
        </div>
        {/* 레짐 가드 — 기본 on. startAutopilot 페이로드에 regimeGuard 로 전달 */}
        <label className="flex items-center gap-2 mt-3 cursor-pointer select-none flex-wrap">
          <input
            type="checkbox"
            checked={!!form.regimeGuard}
            onChange={(e) => setForm((f) => ({ ...f, regimeGuard: e.target.checked }))}
            className="w-4 h-4 accent-emerald-400"
          />
          <span className="text-sm font-semibold text-slate-200">레짐 가드</span>
          <span className="text-[11px] text-slate-400">시장 위험 단계가 높으면 신규 진입 자동 축소/중단</span>
        </label>
        </div>
      )}

      {actionErr && <div className="text-xs text-amber-300/90 mt-3">⚠️ {String(actionErr)}</div>}
    </GlassCard>
  )
}

export default function Autopilot() {
  // 5초 폴링: 오토파일럿 상태 + 모의계좌를 함께 갱신
  const { data: ap, loading: apLoading, err: apErr, reload: reloadAp } = useApi(() => getAutopilot(), [], { pollMs: 5000 })
  const { data: sim } = useApi(() => getSim(), [], { pollMs: 5000 })
  const [resetErr, setResetErr] = useState(null)

  // 로그·오류만 초기화; 저장된 보호 계획은 유지한다.
  const resetLogs = async () => {
    if (!window.confirm('매매 로그·오류를 비울까요?\n(포지션·진입 계획·설정은 그대로 유지됩니다)')) return
    setResetErr(null)
    try {
      await resetAutopilotLogs()
      reloadAp()
    } catch (e) {
      setResetErr(e.message)
    }
  }

  if (apLoading && !ap) return <Spinner label="오토파일럿 상태 불러오는 중…" />
  if (apErr && !ap) return <GlassCard className="text-rose-300">불러오기 실패: {apErr.message}</GlassCard>

  const d = ap || {}
  const s = sim || {}
  const tot = s.totalPnl || 0
  const plans = d.plans || {}
  const watch = Array.isArray(d.watch) ? d.watch : []
  const logs = Array.isArray(d.log) ? d.log : [] // 백엔드가 이미 최신순
  const errs = Array.isArray(d.errors) ? d.errors : d.errors ? [d.errors] : []
  const positions = Array.isArray(s.positions) ? s.positions : []

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6 max-w-6xl">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-extrabold flex items-center gap-2">오토파일럿</h1>
          <p className="text-sm text-slate-400">종목 스크리닝 · 차트 확인 · 매매 계획 관제 · 모의계좌 전용</p>
        </div>
        {/* 로그 초기화 — 로그·오류·진입 계획만 비움 (window.confirm 후 실행) */}
        <button
          onClick={resetLogs}
          className="text-[11px] px-3 py-1.5 rounded-xl glass-soft text-slate-300 hover:bg-white/10 hover:text-slate-100 transition active:scale-[0.97] shrink-0"
        >
          🧹 로그 초기화
        </button>
      </div>
      {resetErr && <div className="text-xs text-amber-300/90">⚠️ {String(resetErr)}</div>}

      {/* 0) 레짐 미니 배너 — 시장 위험 단계 (60초 폴링, stage 별 배경 틴트) */}
      <RegimeBanner />

      {/* 1) 상태 헤더 + 시작/중지 컨트롤 */}
      <StatusHeader d={d} reload={reloadAp} />

      {/* 6) 백엔드 에러 경고 (최근 것부터) */}
      {errs.length > 0 && (
        <GlassCard className="border border-amber-400/20">
          <div className="text-sm font-bold text-amber-300 mb-2">⚠️ 최근 오류</div>
          <div className="space-y-1 max-h-32 overflow-auto pr-1">
            {errs.slice(0, 5).map((e, i) => (
              <div key={i} className="text-xs text-amber-300/80 truncate">{String(e)}</div>
            ))}
          </div>
        </GlassCard>
      )}

      {/* 2) 계좌 요약 4타일 — getSim() 은 active 계좌 대상 (오토파일럿 계좌와 다를 수 있음) */}
      <div>
        <div className="text-[11px] text-slate-500 mb-1.5">※ 아래 잔고는 현재 선택된 계좌 기준</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatTile label="평가자산" value={won0(s.equity) + '원'} sub={`수익률 ${pct(s.totalPnlPct)}`} valueClass={retText(tot)} />
          <StatTile label="현금" value={won0(s.cash) + '원'} />
          <StatTile label="총손익" value={signedWon(tot)} valueClass={retText(tot)} sub={`초기 ${won0(s.initialCash)}원`} />
          <StatTile label="실현 / 미실현" value={`${signedWon(s.realizedPnl)} / ${signedWon(s.unrealizedPnl)}`} />
        </div>
      </div>

      {s.fxEstimated && (
        <div className="text-xs text-amber-300/90 -mt-3">⚠️ {FX_ESTIMATED_NOTE} · 원화 환산값은 참고용입니다.</div>
      )}

      {/* 3) 보유 포지션 — sim 포지션 × 오토파일럿 계획(목표/손절) 결합 */}
      <GlassCard>
        <div className="font-bold mb-3">보유 포지션</div>
        {!positions.length ? (
          <div className="text-slate-500 text-sm py-6 text-center">보유 포지션 없음 — 가동하면 진입존 도달 종목을 자동 매수합니다</div>
        ) : (
          <div className="grid md:grid-cols-2 gap-3">
            {positions.map((p) => {
              const plan = plans[p.symbol]
              return (
                <div key={p.symbol} className="glass-soft rounded-2xl p-4">
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <Link to={`/symbol/${p.symbol}`} className="font-semibold hover:underline truncate block">
                        {p.name || p.symbol}
                      </Link>
                      <div className="text-xs text-slate-500 stat-num">{p.symbol} · {p.qty}주</div>
                    </div>
                    <div className={`text-right stat-num shrink-0 ${retText(p.pnl)}`}>
                      <div className="font-semibold">{signedWon(p.pnl)}</div>
                      <div className="text-xs">{pct(p.pnlPct)}</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 mt-2 text-xs text-slate-400 stat-num flex-wrap">
                    <span>진입 {money(plan?.entryPrice ?? p.avgPrice, p.currency)}</span>
                    <span>→</span>
                    <span className="text-slate-200">현재 {money(p.currentPrice, p.currency)}</span>
                  </div>
                  {/* 손절~목표 진행바 (계획 없으면 생략) */}
                  <PlanBar plan={plan} currentPrice={p.currentPrice} currency={p.currency} />
                </div>
              )
            })}
          </div>
        )}
      </GlassCard>

      {/* 4) 감시 후보 — 최근 스크리닝 픽 */}
      <GlassCard>
        <div className="font-bold mb-3">감시 후보</div>
        {!watch.length ? (
          <div className="text-slate-500 text-sm py-6 text-center">감시 종목 없음 — 가동하면 스크리닝 픽이 표시됩니다</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-400 text-xs">
                  <th className="text-left py-2">종목</th>
                  <th className="text-right">현재가</th>
                  <th className="text-right">점수</th>
                  <th className="text-center">액션</th>
                  <th className="text-center">진입존</th>
                </tr>
              </thead>
              <tbody>
                {watch.map((w) => (
                  <tr key={w.symbol} className="border-t border-white/5">
                    <td className="py-2.5">
                      <Link to={`/symbol/${w.symbol}`} className="font-semibold hover:underline">{w.name || w.symbol}</Link>
                      <div className="text-xs text-slate-500 stat-num">{w.symbol}</div>
                      {w.timing?.reason && <div className="text-xs text-slate-400 mt-1 max-w-xs">{w.timing.entryReason || w.timing.reason}</div>}
                    </td>
                    <td className="text-right stat-num">{money(w.price, w.currency)}</td>
                    <td className="text-right stat-num">{w.quantScore != null ? Number(w.quantScore).toFixed(1) : '—'}</td>
                    <td className="text-center">
                      <span className={`text-[11px] px-2 py-0.5 rounded-full font-bold ${
                        w.action === 'BUY'
                          ? 'bg-emerald-500/15 text-emerald-300'
                          : w.action === 'SELL'
                          ? 'bg-rose-500/15 text-rose-300'
                          : 'glass-soft text-slate-400'
                      }`}>
                        {w.action === 'BUY' ? '매수' : w.action === 'SELL' ? '매도' : '관망'}
                      </span>
                    </td>
                    <td className="text-center">
                      {w.inZone ? (
                        <span className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 font-bold">진입존</span>
                      ) : (
                        <span className="text-slate-600">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </GlassCard>

      {/* 5) 매매 로그 스트림 (최신순) */}
      <GlassCard>
        <div className="font-bold mb-3">매매 로그</div>
        {!logs.length ? (
          <div className="text-slate-500 text-sm py-4">아직 자동매매 없음 — 시작하면 써폿존 진입 종목을 자동 매수합니다</div>
        ) : (
          <div className="space-y-1 max-h-96 overflow-auto pr-1">
            {logs.map((l, i) => (
              <div key={i} className="flex items-center gap-2 text-sm py-2 border-b border-white/5">
                <span className="text-[11px] text-slate-500 stat-num shrink-0 w-16">{apLogTime(l)}</span>
                <span className={`font-bold shrink-0 w-8 ${l.side === 'BUY' ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {l.side === 'BUY' ? '매수' : '매도'}
                </span>
                <span className="font-semibold truncate">{l.name || l.symbol}</span>
                <span className="stat-num text-slate-300 shrink-0">{l.qty}주 @ {money(l.price, l.currency)}</span>
                <span className="text-[11px] text-slate-500 flex-1 truncate text-right">{l.reason || ''}</span>
              </div>
            ))}
          </div>
        )}
        <div className="text-[11px] text-slate-500 mt-3">
          오토파일럿은 모의계좌(sim)에서만 동작하며 브로커/실주문과 완전히 분리되어 있습니다.
        </div>
      </GlassCard>
    </motion.div>
  )
}
