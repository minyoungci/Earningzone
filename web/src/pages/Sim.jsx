import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  useApi, getSim, resetSim, getBroker, selectBroker, getAutopilot, startAutopilot, stopAutopilot,
  searchStocks, getQuant, getJournal,
  getSimAccounts, createSimAccount, selectSimAccount, deleteSimAccount,
} from '../api'
import { won0, pct, retText, money, signedWon, FX_ESTIMATED_NOTE } from '../lib/format'
import { EASE_OUT } from '../lib/motion'
import GlassCard from '../components/ui/GlassCard'
import StatTile from '../components/ui/StatTile'
import Spinner from '../components/ui/Spinner'
import TradeWidget from '../components/TradeWidget'

// 합계/손익은 백엔드가 이미 원화로 환산해 주므로 원(₩)으로 표기
const signed = signedWon

// ── 자동매매 실행 브로커 선택 (토스증권 | 한국투자증권) ─────────────
// 분석/차트/시그널은 토스 데이터 기반으로 공유되고, 여기서 고른 브로커는
// 자동매매의 '주문 실행'에만 적용된다. (DRY_RUN 기본 ON — 실주문 안 나감)
function BrokerCard() {
  const { data, loading, err, reload } = useApi(() => getBroker(), [])
  const [busy, setBusy] = useState(false)

  const pick = async (name) => {
    if (busy || !data || data.active === name) return
    setBusy(true)
    try {
      await selectBroker(name)
      reload()
    } finally {
      setBusy(false)
    }
  }

  if (loading && !data) return null
  if (err && !data) return null
  const d = data || {}

  return (
    <GlassCard>
      <div className="flex items-center justify-between mb-3">
        <div className="font-bold">자동매매 실행 브로커</div>
        <span className="text-[11px] px-2 py-0.5 rounded-full glass-soft text-amber-300">
          {d.dryRun ? 'DRY_RUN · 실주문 차단' : 'LIVE'}
        </span>
      </div>
      <div className="grid sm:grid-cols-2 gap-3">
        {(d.brokers || []).map((b) => {
          const active = d.active === b.name
          return (
            <button
              key={b.name}
              onClick={() => pick(b.name)}
              disabled={busy || !b.configured}
              className={`text-left p-4 rounded-2xl border transition ${
                active
                  ? 'border-emerald-400/40 bg-emerald-500/10'
                  : 'border-transparent glass-soft hover:bg-white/[0.08]'
              } ${!b.configured ? 'opacity-60 cursor-not-allowed' : ''}`}
            >
              <div className="flex items-center justify-between">
                <span className="font-semibold">{b.label}</span>
                {active && (
                  <span className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 font-bold">
                    사용 중
                  </span>
                )}
              </div>
              <div className="text-xs text-slate-400 mt-1.5">
                {b.configured ? (
                  <span className="text-emerald-300/90">연결됨 · {b.mode}</span>
                ) : (
                  <span className="text-rose-300/90">미연결</span>
                )}
              </div>
              <div className="text-[11px] text-slate-500 mt-1">{b.note}</div>
            </button>
          )
        })}
      </div>
      <div className="text-[11px] text-slate-500 mt-3">
        분석·차트·시그널은 토스 데이터로 공유됩니다. 브로커는 자동매매 주문 실행에만 적용돼요.
        한국투자증권은 <span className="text-slate-400">KIS Developers</span>(apiportal.koreainvestment.com)에서
        앱키 발급 후 <span className="stat-num text-slate-400">KIS_APP_KEY · KIS_APP_SECRET · KIS_ACCOUNT</span> 환경변수로 연결하세요.
      </div>
    </GlassCard>
  )
}

// ── 계좌 바 (모의 다중 계좌 전환) ───────────────────────────────────
// getSimAccounts() 결과(accounts)는 상위 Sim 이 소유 — 여기서는 표시·조작만.
// 전환/생성/삭제 성공 시 onChanged() 로 sim/저널/계좌바 전체를 갱신한다.
function AccountBar({ accounts, onChanged }) {
  const [busy, setBusy] = useState(false)
  const [actionErr, setActionErr] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ name: '', cash: 10000000 })

  if (!accounts) return null
  const list = accounts.accounts || []
  const activeId = accounts.active

  // 공통 실행기 — 성공 시 전체 reload, 실패 시 서버 detail(400 메시지 포함) 표출
  const run = async (fn) => {
    if (busy) return
    setBusy(true)
    setActionErr(null)
    try {
      await fn()
      onChanged()
    } catch (e) {
      setActionErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  const select = (id) => {
    if (id === activeId) return
    run(() => selectSimAccount(id))
  }

  const create = () => {
    const name = form.name.trim()
    if (!name) { setActionErr('계좌 이름을 입력하세요'); return }
    run(async () => {
      const res = await createSimAccount(name, Number(form.cash) || 10000000)
      // 생성 후 자동 선택 — 서버가 주는 newId 로 정확히(같은 초 생성 휴리스틱 문제 제거),
      // 구응답(newId 없음) 폴백은 createdAt 최신.
      const newId = res.newId
        || ((res.accounts || []).reduce(
          (a, b) => (!a || (b.createdAt || 0) > (a.createdAt || 0) ? b : a), null) || {}).id
      if (newId && newId !== res.active) await selectSimAccount(newId)
      setShowForm(false)
      setForm({ name: '', cash: 10000000 })
    })
  }

  const del = (id, name) => {
    if (!window.confirm(`'${name}' 계좌를 삭제할까요? (보유·내역 모두 삭제)`)) return
    // 마지막 남은 계좌면 서버가 400 을 돌려주고 그 메시지를 아래에 표출한다.
    run(() => deleteSimAccount(id))
  }

  return (
    <GlassCard className="!p-4">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm font-bold mr-1">계좌</span>
        {list.map((a) => {
          const active = a.id === activeId
          return (
            <div
              key={a.id}
              className={`flex items-center gap-1 pl-3 pr-2 py-1.5 rounded-xl border transition ${
                active
                  ? 'border-emerald-400/40 bg-emerald-500/10'
                  : 'border-transparent glass-soft hover:bg-white/[0.08]'
              }`}
            >
              <button onClick={() => select(a.id)} disabled={busy} className="text-left disabled:opacity-60">
                <span className={`text-sm font-semibold ${active ? 'text-emerald-300' : ''}`}>{a.name}</span>
                <span className="text-[11px] text-slate-400 ml-2">
                  보유 {a.positions}종목 · <span className="stat-num">{won0(a.cash)}</span>원
                </span>
              </button>
              {active && (
                <button
                  onClick={() => del(a.id, a.name)}
                  disabled={busy}
                  title="이 계좌 삭제"
                  aria-label="이 계좌 삭제"
                  className="text-slate-500 hover:text-rose-300 transition text-xs px-1 disabled:opacity-60"
                >
                  🗑️
                </button>
              )}
            </div>
          )
        })}
        <button
          onClick={() => { setShowForm((s) => !s); setActionErr(null) }}
          disabled={busy}
          className="text-[12px] px-3 py-1.5 rounded-xl font-bold glass-soft text-sky-300 hover:bg-white/10 transition active:scale-[0.97] disabled:opacity-60"
        >
          ＋ 새 계좌
        </button>
      </div>

      {showForm && (
        <div className="flex items-end gap-2 flex-wrap mt-3">
          <label className="flex-1 min-w-[140px]">
            <span className="text-[11px] text-slate-400">계좌 이름</span>
            <input
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              onKeyDown={(e) => { if (e.key === 'Enter') create() }}
              placeholder="예: 공격형 연습"
              className="glass-soft w-full px-3 py-2 rounded-xl bg-transparent outline-none text-sm mt-1"
            />
          </label>
          <label className="flex-1 min-w-[130px]">
            <span className="text-[11px] text-slate-400">초기 자금 (원)</span>
            <input
              type="number"
              min="100000"
              step="100000"
              value={form.cash}
              onChange={(e) => setForm((f) => ({ ...f, cash: e.target.value }))}
              className="glass-soft w-full px-3 py-2 rounded-xl bg-transparent outline-none text-sm stat-num mt-1"
            />
          </label>
          <button
            onClick={create}
            disabled={busy}
            className="px-4 py-2 rounded-xl text-sm font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-400/30 hover:bg-emerald-500/25 transition active:scale-[0.97] disabled:opacity-50"
          >
            생성
          </button>
        </div>
      )}

      {actionErr && <div className="text-xs text-amber-300/90 mt-2">⚠️ {String(actionErr)}</div>}
    </GlassCard>
  )
}

// ── 퀀트 오토파일럿 (모의 전용) ─────────────────────────────────────
// 서버가 주기적으로 써폿존 진입 종목을 스캔해 모의계좌(sim)에서만 자동 매매.
// 브로커/실주문 경로와는 완전히 분리 — 실주문은 절대 나가지 않는다.
const apLogTime = (l) => {
  const t = l.time ?? l.ts ?? l.at
  if (t == null) return ''
  if (typeof t === 'number') {
    // epoch 초/밀리초 모두 허용
    return new Date(t > 1e12 ? t : t * 1000).toLocaleTimeString('ko-KR', { hour12: false })
  }
  const d = new Date(t)
  return Number.isNaN(d.getTime()) ? String(t) : d.toLocaleTimeString('ko-KR', { hour12: false })
}

// 시장 코드 → 표시 라벨 (Autopilot 페이지와 동일 값)
const SIM_MARKET_LABEL = {
  kr: '한국 대형', kosdaq: '코스닥', us: '미국 대형', usgrowth: '미국 성장', all: '전체',
}

function AutopilotCard({ onTrade, accounts }) {
  const { data, reload } = useApi(() => getAutopilot(), [], { pollMs: 5000 })
  const [busy, setBusy] = useState(false)
  const [actionErr, setActionErr] = useState(null)
  // 시작 폼 기본값: 주기 60초 · 최대 3종목 · 1회 예산 100만원 · 한국 대형 · 계좌는 활성(active)
  const [form, setForm] = useState({ intervalSec: 60, maxPositions: 3, budgetKrw: 1000000, market: 'kr', account: '' })

  // 계좌 id → 이름 매핑 (모르면 id 그대로)
  const accName = (id) => {
    const a = (accounts?.accounts || []).find((x) => x.id === id)
    return a ? a.name : (id || '—')
  }

  // 직전 가동 시장을 폼에 승계 — Sim 에서 중지→시작해도 시장이 조용히 kr 로 리셋되지 않게.
  const marketSynced = useRef(false)
  useEffect(() => {
    const m = data?.settings?.market || data?.market
    if (!marketSynced.current && m && SIM_MARKET_LABEL[m]) {
      marketSynced.current = true
      setForm((f) => ({ ...f, market: m }))
    }
  }, [data])

  const d = data || {}
  // autopilot.status() 는 설정을 settings 키로 반환
  const cfg = d.settings || d.config || d
  const running = !!d.running
  const log = Array.isArray(d.log) ? d.log : []

  // 매매 발생(log 길이 변화) 시 상위 Sim 잔고/보유도 백그라운드 갱신
  const prevLogLen = useRef(null)
  useEffect(() => {
    if (!data) return
    if (prevLogLen.current !== null && log.length !== prevLogLen.current && onTrade) onTrade()
    prevLogLen.current = log.length
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data])

  const setField = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const start = async () => {
    if (busy) return
    setBusy(true)
    setActionErr(null)
    try {
      await startAutopilot({
        intervalSec: Number(form.intervalSec) || 60,
        maxPositions: Number(form.maxPositions) || 3,
        budgetKrw: Number(form.budgetKrw) || 1000000,
        market: form.market || 'kr',
        // 미선택(빈 값)이면 서버가 시작 시점의 활성 계좌를 캡처한다.
        account: form.account || accounts?.active || null,
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

  if (!data) return null

  const errs = d.errors
  const errLine = actionErr || (Array.isArray(errs) ? errs[errs.length - 1] : errs)
  const logs = log // 백엔드가 이미 최신순(newest-first)으로 반환

  return (
    <GlassCard>
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <span className="font-bold">🤖 퀀트 오토파일럿</span>
          {running ? (
            <span className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 font-bold flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              가동 중
            </span>
          ) : (
            <span className="text-[11px] px-2 py-0.5 rounded-full glass-soft text-slate-400 font-bold">중지됨</span>
          )}
        </div>
        <span className="text-[11px] px-2 py-0.5 rounded-full glass-soft text-amber-300">모의 전용 · 실주문 없음</span>
      </div>

      {running ? (
        <div className="flex items-end justify-between gap-3 mb-4 flex-wrap">
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 flex-1 min-w-[240px]">
            <div className="glass-soft rounded-xl px-3 py-2">
              <div className="text-[11px] text-slate-400">계좌</div>
              <div className="font-semibold text-sm truncate">{accName(d.account ?? cfg.account)}</div>
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
              <div className="font-semibold text-sm">{SIM_MARKET_LABEL[cfg.market] || cfg.market || '—'}</div>
            </div>
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
        <div className="flex items-end gap-3 mb-4 flex-wrap">
          <label className="flex-1 min-w-[100px]">
            <span className="text-[11px] text-slate-400">주기 (초)</span>
            <input
              type="number"
              min="10"
              value={form.intervalSec}
              onChange={setField('intervalSec')}
              className="glass-soft w-full px-3 py-2 rounded-xl bg-transparent outline-none text-sm stat-num mt-1"
            />
          </label>
          <label className="flex-1 min-w-[100px]">
            <span className="text-[11px] text-slate-400">최대 보유 (종목)</span>
            <input
              type="number"
              min="1"
              value={form.maxPositions}
              onChange={setField('maxPositions')}
              className="glass-soft w-full px-3 py-2 rounded-xl bg-transparent outline-none text-sm stat-num mt-1"
            />
          </label>
          <label className="flex-1 min-w-[120px]">
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
          <label className="flex-1 min-w-[110px]">
            <span className="text-[11px] text-slate-400">시장</span>
            <select
              value={form.market}
              onChange={setField('market')}
              className="glass-soft w-full px-3 py-2 rounded-xl bg-transparent outline-none text-sm mt-1 [&>option]:bg-slate-900"
            >
              <option value="kr">한국 대형</option>
              <option value="kosdaq">코스닥</option>
              <option value="us">미국 대형</option>
              <option value="usgrowth">미국 성장</option>
              <option value="all">전체</option>
            </select>
          </label>
          <label className="flex-1 min-w-[110px]">
            <span className="text-[11px] text-slate-400">계좌</span>
            {/* 기본 = 현재 활성 계좌. 여기서 고른 계좌는 가동 내내 유지된다(활성 전환 무관). */}
            <select
              value={form.account || accounts?.active || ''}
              onChange={setField('account')}
              className="glass-soft w-full px-3 py-2 rounded-xl bg-transparent outline-none text-sm mt-1 [&>option]:bg-slate-900"
            >
              {(accounts?.accounts || []).map((a) => (
                <option key={a.id} value={a.id}>{a.name}</option>
              ))}
            </select>
          </label>
          <button
            onClick={start}
            disabled={busy}
            className="px-4 py-2.5 rounded-xl text-sm font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-400/30 hover:bg-emerald-500/25 transition active:scale-[0.97] disabled:opacity-50"
          >
            ▶ 시작
          </button>
        </div>
      )}

      {errLine && <div className="text-xs text-amber-300/90 mb-3">⚠️ {String(errLine)}</div>}

      <div className="text-sm font-bold mb-2">자동매매 로그</div>
      {!logs.length ? (
        <div className="text-slate-500 text-sm py-4">아직 자동매매 없음 — 시작하면 써폿존 진입 종목을 자동 매수합니다</div>
      ) : (
        <div className="space-y-1 max-h-72 overflow-auto pr-1">
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
  )
}

// ── 종목 검색 자동완성 입력 (거래 패널용) ───────────────────────────
// SearchBar.jsx 의 패턴(디바운스·시퀀스 토큰·외부클릭 닫기·키보드 ↑↓)을 따르되,
// 페이지 이동 대신 선택한 심볼을 상위 sym 상태에 채운다.
function SymbolSearch({ value, onChange }) {
  const [items, setItems] = useState([])
  const [open, setOpen] = useState(false)
  const [hi, setHi] = useState(0)
  const boxRef = useRef(null)
  const inputRef = useRef(null)
  // 응답 경쟁(out-of-order) 방지: 매 요청마다 증가하는 시퀀스 토큰으로 최신 응답만 반영.
  const seqRef = useRef(0)
  // 드롭다운에서 '선택'해 값이 바뀐 경우엔 재검색하지 않기 위한 플래그.
  const pickedRef = useRef(false)

  useEffect(() => {
    if (pickedRef.current) { pickedRef.current = false; return }
    if (!value || !value.trim()) { setItems([]); setOpen(false); return }
    const t = setTimeout(() => {
      const seq = ++seqRef.current
      searchStocks(value)
        .then((d) => {
          if (seq !== seqRef.current) return // 더 최신 요청이 출발했으면 옛 응답 무시
          setItems((d.items || []).slice(0, 6)); setHi(0)
          // 입력이 포커스 상태일 때만 드롭다운 열기 — 마운트 초기값·[거래] 버튼 등
          // 프로그램적 값 변경으로 사용자가 보지 않는 드롭다운이 저절로 열리는 것 방지.
          setOpen(document.activeElement === inputRef.current)
        })
        .catch(() => {
          if (seq !== seqRef.current) return
          setItems([])
        })
    }, 250)
    return () => clearTimeout(t)
  }, [value])

  useEffect(() => {
    const onClick = (e) => { if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  const pick = (sym) => {
    if (!sym) return
    seqRef.current++ // 진행 중인 fetch 응답 무효화
    pickedRef.current = true
    setOpen(false); setItems([])
    onChange(sym)
  }

  const onKey = (e) => {
    if (!open || !items.length) {
      if (e.key === 'Enter') setOpen(false)
      return
    }
    if (e.key === 'ArrowDown') { e.preventDefault(); setHi((h) => Math.min(h + 1, items.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setHi((h) => Math.max(h - 1, 0)) }
    else if (e.key === 'Enter') { e.preventDefault(); pick(items[hi]?.symbol) }
    else if (e.key === 'Escape') setOpen(false)
  }

  return (
    <div className="relative mb-4" ref={boxRef}>
      <input
        ref={inputRef}
        value={value}
        onChange={(e) => onChange(e.target.value.toUpperCase().trim())}
        onKeyDown={onKey}
        onFocus={() => items.length && setOpen(true)}
        placeholder="종목코드·이름 (예: 005930, 삼성전자, AAPL)"
        className="glass-soft w-full px-3 py-2.5 rounded-xl bg-transparent outline-none text-sm stat-num"
        role="combobox"
        aria-expanded={open && items.length > 0}
        aria-controls="simsym-listbox"
        aria-autocomplete="list"
        aria-activedescendant={open && items.length > 0 ? `simsym-opt-${hi}` : undefined}
      />
      {open && items.length > 0 && (
        <motion.div
          id="simsym-listbox"
          role="listbox"
          initial={{ opacity: 0, scale: 0.97 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.15, ease: EASE_OUT }}
          style={{ transformOrigin: 'top' }}
          className="absolute z-50 mt-2 w-full glass p-2 max-h-72 overflow-auto"
        >
          {items.map((it, i) => (
            <button
              key={it.symbol}
              id={`simsym-opt-${i}`}
              role="option"
              aria-selected={i === hi}
              onMouseDown={(e) => { e.preventDefault(); pick(it.symbol) }}
              onMouseEnter={() => setHi(i)}
              className={`w-full text-left px-3 py-2 rounded-xl flex items-center justify-between transition ${i === hi ? 'bg-white/10' : 'hover:bg-white/5'}`}
            >
              <span className="font-semibold text-sm truncate">{it.name || it.symbol}</span>
              <span className="text-xs text-slate-400 stat-num shrink-0 ml-2">{it.symbol}{it.market ? ` · ${it.market}` : ''}</span>
            </button>
          ))}
        </motion.div>
      )}
    </div>
  )
}

// ── 오늘의 추천 (퀀트 스크리너 상위 픽) ────────────────────────────
// /api/quant 상위 6종목을 시장 미니토글과 함께 보여주고,
// [거래] 클릭 시 거래 패널의 심볼을 채워 바로 매매 연습으로 잇는다.
const SIM_MARKETS = [
  { key: 'kr', label: '대형' },
  { key: 'kosdaq', label: '코스닥' },
  { key: 'us', label: '미국' },
  { key: 'usgrowth', label: '성장' },
]

const actionBadge = (action) => {
  if (action === 'BUY') return 'bg-emerald-500/20 text-emerald-300'
  if (action === 'SELL') return 'bg-rose-500/20 text-rose-300'
  return 'glass-soft text-slate-400'
}

function PicksCard({ onTrade }) {
  const [simMkt, setSimMkt] = useState('kr')
  const { data, loading, err } = useApi(() => getQuant(6, simMkt), [simMkt])
  const picks = data?.picks || []
  // 시장 전환 직후엔 이전 시장 데이터가 남아 있으므로 스크리닝 중임을 표시.
  const screening = loading || (data && data.market && data.market !== simMkt)

  return (
    <GlassCard>
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="font-bold">💡 오늘의 추천</div>
        <div className="flex gap-1">
          {SIM_MARKETS.map((m) => (
            <button
              key={m.key}
              onClick={() => setSimMkt(m.key)}
              className={`text-[11px] px-2 py-1 rounded-lg font-bold transition ${
                simMkt === m.key ? 'bg-white/15 text-white' : 'glass-soft text-slate-400 hover:bg-white/10'
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      {screening ? (
        <div className="text-slate-500 text-sm py-6 text-center">스크리닝 중(첫 조회는 오래 걸려요)…</div>
      ) : err && !picks.length ? (
        <div className="text-xs text-amber-300/90 py-4">⚠️ {err.message}</div>
      ) : !picks.length ? (
        <div className="text-slate-500 text-sm py-4">추천 종목 없음</div>
      ) : (
        <div className="space-y-2">
          {picks.map((p) => (
            <div key={p.symbol} className="glass-soft rounded-xl px-3 py-2.5">
              <div className="flex items-center gap-2">
                <Link to={`/symbol/${p.symbol}`} className="font-semibold text-sm truncate hover:underline flex-1">
                  {p.name || p.symbol}
                </Link>
                <span className="stat-num text-xs text-slate-300 shrink-0">{p.quantScore}점</span>
                <span className={`text-[11px] px-2 py-0.5 rounded-full font-bold shrink-0 ${actionBadge(p.action)}`}>
                  {p.action}
                </span>
                {p.plan?.inZone && (
                  <span className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 font-bold shrink-0">
                    진입존
                  </span>
                )}
                <button
                  onClick={() => onTrade(p.symbol)}
                  className="text-[11px] px-2.5 py-1 rounded-lg font-bold bg-sky-500/15 text-sky-300 border border-sky-400/30 hover:bg-sky-500/25 transition shrink-0"
                >
                  거래
                </button>
              </div>
              {Array.isArray(p.reasons) && p.reasons.length > 0 && (
                <div className="mt-1.5 space-y-0.5">
                  {p.reasons.slice(0, 2).map((r, i) => (
                    <div key={i} className="text-[11px] text-slate-400 truncate">✓ {r}</div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="text-[11px] text-slate-500 mt-3">교육용 참고 — 투자 권유 아님</div>
    </GlassCard>
  )
}

// ── 매매 저널 (sim 히스토리 기반 통계) ─────────────────────────────
// /api/journal 을 30초 폴링 — SELL 실현손익 기반 승률/PF/기대값R/누적실현 4타일 +
// 최근 거래 리스트(주문 메모 포함). 본전(실현손익 0) 트레이드는 승/패 어느 쪽에도 안 센다.
// ver: 계좌 전환/초기화 시 상위 Sim 이 올려 주는 갱신 카운터 — deps 에 넣어 즉시 재조회
function JournalCard({ ver = 0 }) {
  const { data, err } = useApi(() => getJournal(), [ver], { pollMs: 30000 })
  if (!data) {
    // 최초 로딩 실패 시에만 안내 — 폴링 실패는 기존 데이터 유지(useApi 규약)
    if (err) return null
    return null
  }
  const j = data
  // profitFactor: 손실 트레이드가 0건이면 백엔드가 null(무한대) 반환 → ∞ 로 표기
  const pf = j.trades === 0 ? '-' : j.profitFactor == null ? '∞' : Number(j.profitFactor).toFixed(2)
  const expR = j.trades === 0 ? '-' : (Number(j.expectancyR) >= 0 ? '+' : '') + Number(j.expectancyR || 0).toFixed(2) + 'R'
  const recent = Array.isArray(j.recent) ? j.recent : []

  return (
    <GlassCard>
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="font-bold">📒 매매 저널</div>
        <span className="text-[11px] text-slate-500">모의(sim) · SELL 실현손익 기준</span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <StatTile label="승률" value={`${j.winRate ?? 0}%`} sub={`${j.wins ?? 0}승 ${j.losses ?? 0}패 · ${j.trades ?? 0}회`} />
        <StatTile label="손익비 (PF)" value={pf} sub="이익합 ÷ |손실합|" />
        <StatTile label="기대값 R" value={expR} valueClass={j.trades ? retText(j.expectancyR) : ''} sub="트레이드당 평균 R" />
        <StatTile
          label="누적 실현손익"
          value={signed(j.totalRealizedKrw)}
          valueClass={retText(j.totalRealizedKrw)}
          sub={`평균 익 ${signed(j.avgWinKrw)} · 손 ${signed(j.avgLossKrw)}`}
        />
      </div>

      <div className="text-sm font-bold mb-2">최근 거래</div>
      {!recent.length ? (
        <div className="text-slate-500 text-sm py-4">기록 없음 — 첫 매매부터 근거 메모를 남겨 보세요</div>
      ) : (
        <div className="space-y-1 max-h-72 overflow-auto pr-1">
          {recent.map((r, i) => (
            <div key={i} className="py-2 border-b border-white/5">
              <div className="flex items-center gap-2 text-sm">
                <span className="text-[11px] text-slate-500 stat-num shrink-0 w-20">{r.time || ''}</span>
                <span className={`font-bold shrink-0 ${r.side === 'BUY' ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {r.side === 'BUY' ? '매수' : '매도'}
                </span>
                <span className="font-semibold truncate flex-1">{r.name || r.symbol}</span>
                <span className="stat-num text-slate-300 shrink-0">{r.qty}주 @ {money(r.price, r.currency)}</span>
                {r.realized != null && (
                  <span className={`stat-num text-xs shrink-0 ${retText(r.realized)}`}>{signed(r.realized)}</span>
                )}
              </div>
              {/* 주문 메모(근거) — 회색 한 줄, 시간 컬럼(w-20)+간격만큼 들여쓰기 */}
              {r.note ? (
                <div className="text-xs text-slate-500 mt-1 pl-[88px] truncate">📝 {r.note}</div>
              ) : null}
            </div>
          ))}
        </div>
      )}

      <div className="text-[11px] text-slate-500 mt-3">기록이 매매를 신중하게 만듭니다</div>
    </GlassCard>
  )
}

export default function Sim() {
  const { data, loading, err, reload } = useApi(() => getSim(), [])
  // 다중 계좌 목록 — 계좌 바 + 오토파일럿 계좌 셀렉트가 공유
  const accountsApi = useApi(() => getSimAccounts(), [])
  // 계좌 전환/초기화 시 저널 등 하위 카드 재조회용 카운터
  const [accVer, setAccVer] = useState(0)
  const [sym, setSym] = useState('005930')
  // '오늘의 추천' [거래] 클릭 시 거래 패널 상단으로 스크롤하기 위한 ref
  const tradeRef = useRef(null)

  // 계좌 전환·생성·삭제·초기화 후 sim/저널/계좌바 전부 갱신
  const reloadAll = () => {
    reload()
    accountsApi.reload()
    setAccVer((v) => v + 1)
  }

  const tradeFromPick = (symbol) => {
    setSym(symbol)
    tradeRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const onReset = async () => {
    if (window.confirm('현재 선택된 계좌를 1,000만원으로 초기화할까요? (보유·내역 삭제)')) {
      await resetSim()
      reloadAll()
    }
  }

  if (loading) return <Spinner label="모의계좌 불러오는 중…" />
  // 갱신(reload) 실패 시 표시 중이던 계좌가 통째로 에러 박스로 교체되지 않게,
  // '데이터가 아예 없는 실패'만 전면 에러 처리. 데이터가 있으면 아래에서 배지만 표시.
  if (err && !data) return <GlassCard className="text-rose-300">불러오기 실패: {err.message}</GlassCard>
  const d = data || {}
  const tot = d.totalPnl || 0

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6 max-w-6xl">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-extrabold flex items-center gap-2">모의투자</h1>
          <p className="text-sm text-slate-400">실제 시세로 매매 연습 · 투자 권유 아님</p>
        </div>
        {/* 초기화는 현재 활성(선택된) 계좌만 대상 — 다른 계좌는 건드리지 않는다 */}
        <button onClick={onReset} className="glass-soft px-4 py-2 text-sm rounded-xl hover:bg-white/10 transition active:scale-[0.97]">이 계좌 초기화</button>
      </div>

      {err && data && (
        <div className="text-xs text-amber-300/90">⚠️ 갱신 실패 · 마지막 값 표시 중 — {err.message}</div>
      )}

      <AccountBar accounts={accountsApi.data} onChanged={reloadAll} />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatTile label="평가자산" value={won0(d.equity) + '원'} sub={`수익률 ${pct(d.totalPnlPct)}`} valueClass={retText(tot)} />
        <StatTile label="현금" value={won0(d.cash) + '원'} />
        <StatTile label="총손익" value={signed(tot)} valueClass={retText(tot)} sub={`초기 ${won0(d.initialCash)}원`} />
        <StatTile label="실현 / 미실현" value={`${signed(d.realizedPnl)} / ${signed(d.unrealizedPnl)}`} />
      </div>

      {d.fxEstimated && (
        <div className="text-xs text-amber-300/90 -mt-3">⚠️ {FX_ESTIMATED_NOTE} · 원화 환산값은 참고용입니다.</div>
      )}

      <BrokerCard />

      <AutopilotCard onTrade={reload} accounts={accountsApi.data} />

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <GlassCard>
            <div className="font-bold mb-3">보유 종목</div>
            {!d.positions || !d.positions.length ? (
              <div className="text-slate-500 text-sm py-8 text-center">보유 종목 없음 — 오른쪽 거래 패널에서 매수해 보세요.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-slate-400 text-xs">
                      <th className="text-left py-2">종목</th>
                      <th className="text-right">수량</th>
                      <th className="text-right">평단</th>
                      <th className="text-right">현재가</th>
                      <th className="text-right">평가손익</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.positions.map((p) => (
                      <tr key={p.symbol} className="border-t border-white/5">
                        <td className="py-2.5">
                          <Link to={`/symbol/${p.symbol}`} className="font-semibold hover:underline">{p.name || p.symbol}</Link>
                          <div className="text-xs text-slate-500 stat-num">{p.symbol}</div>
                        </td>
                        <td className="text-right stat-num">{p.qty}</td>
                        <td className="text-right stat-num">{money(p.avgPrice, p.currency)}</td>
                        <td className="text-right stat-num">{money(p.currentPrice, p.currency)}</td>
                        <td className={`text-right stat-num ${retText(p.pnl)}`}>
                          {signed(p.pnl)}
                          <div className="text-xs">{pct(p.pnlPct)}</div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </GlassCard>

          <GlassCard>
            <div className="font-bold mb-3">거래 내역</div>
            {!d.history || !d.history.length ? (
              <div className="text-slate-500 text-sm py-4">내역 없음</div>
            ) : (
              <div className="space-y-1 max-h-72 overflow-auto pr-1">
                {d.history.map((h, i) => (
                  <div key={i} className="py-2 border-b border-white/5">
                    <div className="flex items-center justify-between text-sm">
                      <span className={`font-bold w-10 ${h.side === 'BUY' ? 'text-emerald-400' : 'text-rose-400'}`}>{h.side === 'BUY' ? '매수' : '매도'}</span>
                      <span className="flex-1 px-3 truncate">{h.name || h.symbol}</span>
                      <span className="stat-num text-slate-300 shrink-0">{h.qty}주 @ {money(h.price, h.currency)}</span>
                    </div>
                    {/* 주문 시 남긴 메모(근거) — 있으면 회색 한 줄로 표시 */}
                    {h.note ? (
                      <div className="text-xs text-slate-500 mt-1 pl-10 truncate">📝 {h.note}</div>
                    ) : null}
                  </div>
                ))}
              </div>
            )}
          </GlassCard>

          <JournalCard ver={accVer} />
        </div>

        <div className="space-y-6">
          <div ref={tradeRef} className="scroll-mt-6">
            <GlassCard>
              <div className="font-bold mb-3">거래하기</div>
              <SymbolSearch value={sym} onChange={setSym} />
              <TradeWidget symbol={sym} onDone={reload} />
            </GlassCard>
          </div>
          <PicksCard onTrade={tradeFromPick} />
        </div>
      </div>
    </motion.div>
  )
}
