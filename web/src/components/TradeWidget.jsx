import { useState } from 'react'
import { placeOrder } from '../api'

export default function TradeWidget({ symbol, name = '', onDone }) {
  const [qty, setQty] = useState(1)
  const [note, setNote] = useState('') // 매매 근거 메모(선택) — sim 히스토리·매매 저널에 기록
  const [msg, setMsg] = useState(null)
  const [busy, setBusy] = useState(false)

  const trade = async (side) => {
    if (busy) return // 연타·중복주문 방지(단일 busy 가드)
    // 분수/지수 입력(1.5, 1e3 등)은 백엔드에서 int 절사되므로 제출 시 정수화해 표시-체결 불일치를 막는다.
    const n = Math.floor(Number(qty))
    if (!symbol) { setMsg({ ok: false, text: '종목 코드를 입력하세요.' }); return }
    if (!Number.isFinite(n) || n <= 0) { setMsg({ ok: false, text: '수량을 확인하세요.' }); return }
    setBusy(true); setMsg(null)
    try {
      const st = await placeOrder(symbol, side, n, name, note.trim())
      setMsg({ ok: true, text: `${side === 'BUY' ? '매수' : '매도'} ${n}주 체결 완료` })
      setNote('') // 주문 성공 시 메모 비움 — 다음 주문에 이전 근거가 딸려가지 않게
      onDone && onDone(st)
    } catch (e) {
      setMsg({ ok: false, text: e.message })
    }
    setBusy(false)
  }

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <button onClick={() => setQty((q) => Math.max(1, Number(q) - 1))} className="glass-soft w-9 h-9 rounded-xl hover:bg-white/10 transition active:scale-95">−</button>
        <input
          type="number" min="1" step="1" value={qty}
          onChange={(e) => setQty(e.target.value)}
          onBlur={(e) => {
            // 분수·음수·빈값을 정수로 보정해 표시값과 체결 수량을 일치시킨다.
            const n = Math.floor(Number(e.target.value))
            setQty(Number.isFinite(n) && n >= 1 ? n : 1)
          }}
          className="glass-soft text-center w-24 h-9 rounded-xl bg-transparent outline-none stat-num"
        />
        <button onClick={() => setQty((q) => Number(q) + 1)} className="glass-soft w-9 h-9 rounded-xl hover:bg-white/10 transition active:scale-95">+</button>
        <span className="text-xs text-slate-400 ml-1">주</span>
      </div>
      {/* 메모(근거) — 선택: 저널에 남아 매매를 복기할 수 있게 한다 */}
      <input
        value={note}
        onChange={(e) => setNote(e.target.value)}
        maxLength={120}
        placeholder="메모(근거) — 선택 · 예: 써폿존 반등 노림"
        className="glass-soft w-full px-3 py-2 rounded-xl bg-transparent outline-none text-sm mb-3"
        aria-label="메모(근거) — 선택"
      />
      <div className="grid grid-cols-2 gap-2">
        <button disabled={busy} onClick={() => trade('BUY')}
          className="py-2.5 rounded-xl font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-400/30 hover:bg-emerald-500/30 disabled:opacity-50 transition active:scale-[0.97]">매수</button>
        <button disabled={busy} onClick={() => trade('SELL')}
          className="py-2.5 rounded-xl font-bold bg-rose-500/20 text-rose-300 border border-rose-400/30 hover:bg-rose-500/30 disabled:opacity-50 transition active:scale-[0.97]">매도</button>
      </div>
      {msg && <div className={`text-xs mt-2 ${msg.ok ? 'text-emerald-400' : 'text-rose-400'}`}>{msg.text}</div>}
      <div className="text-[11px] text-slate-500 mt-2">현재가로 즉시 체결(모의). 수수료 0.015% · 매도세 0.18% 반영.</div>
    </div>
  )
}
