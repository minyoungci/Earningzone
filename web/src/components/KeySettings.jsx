import { useEffect, useState } from 'react'
import { getKeysStatus, saveKeys } from '../api'
import Icon from './ui/Icon'

/**
 * 사이드바 API 키 관리 — 키가 정상 동작 중일 때도 교체(로테이션)할 수 있다.
 * 값은 절대 표시하지 않고 저장 여부만 점으로 보여준다(백엔드 status 도 값 비노출).
 * 저장 시 백엔드가 OS 키체인에 기록 + 런타임 즉시 반영(재시작 불필요).
 */
export default function KeySettings() {
  const [st, setSt] = useState(null)
  const [open, setOpen] = useState(false)
  const [cid, setCid] = useState('')
  const [csec, setCsec] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null) // {ok, text}

  const refresh = () => getKeysStatus().then(setSt).catch(() => setSt(null))
  useEffect(() => { refresh() }, [])

  const submit = async () => {
    if (busy) return
    if (!cid.trim() || !csec.trim()) {
      setMsg({ ok: false, text: 'ID/SECRET 모두 입력' })
      return
    }
    setBusy(true); setMsg(null)
    try {
      const r = await saveKeys(cid.trim(), csec.trim())
      setCid(''); setCsec('')
      setMsg({ ok: true, text: r.saved_to_keychain ? '키체인에 저장됨 ✓' : '이번 세션에 적용됨 ✓' })
      refresh()
    } catch (e) {
      setMsg({ ok: false, text: e.message || '저장 실패' })
    }
    setBusy(false)
  }

  const dot = st?.loaded ? 'bg-emerald-400' : st?.has_id ? 'bg-amber-400' : 'bg-slate-500'
  const dotTitle = st?.loaded ? '키 연결됨' : st?.has_id ? '키 저장됨(미적용)' : '키 없음'

  return (
    <div className="glass-soft p-1">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="w-full flex items-center justify-between px-2 py-1.5 rounded-xl text-[11px] font-medium text-slate-300 hover:text-slate-100 hover:bg-white/5 transition-colors active:scale-[0.98]"
      >
        <span className="flex items-center gap-1.5">
          <Icon name="lock" size={16} /> API 키
        </span>
        <span className={`w-1.5 h-1.5 rounded-full ${dot}`} title={dotTitle} aria-label={dotTitle} />
      </button>
      {open && (
        <div className="px-2 pb-2 pt-1 flex flex-col gap-1.5">
          <input
            value={cid}
            onChange={(e) => setCid(e.target.value)}
            placeholder="TOSS_CLIENT_ID"
            autoComplete="off" spellCheck={false}
            className="w-full px-2.5 py-1.5 rounded-lg bg-black/25 border border-white/10 focus:border-indigo-400/50 outline-none text-[11px] stat-num placeholder:text-slate-600"
            aria-label="TOSS_CLIENT_ID"
          />
          <input
            type="password"
            value={csec}
            onChange={(e) => setCsec(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit()}
            placeholder="TOSS_CLIENT_SECRET"
            autoComplete="off" spellCheck={false}
            className="w-full px-2.5 py-1.5 rounded-lg bg-black/25 border border-white/10 focus:border-indigo-400/50 outline-none text-[11px] stat-num placeholder:text-slate-600"
            aria-label="TOSS_CLIENT_SECRET"
          />
          <button
            type="button"
            onClick={submit}
            disabled={busy}
            className="w-full px-2.5 py-1.5 rounded-lg text-[11px] font-semibold bg-indigo-500/15 text-indigo-200 border border-indigo-400/25 hover:bg-indigo-500/25 transition active:scale-[0.97] disabled:opacity-50"
          >
            {busy ? '저장 중…' : '키 저장(즉시 반영)'}
          </button>
          {msg && (
            <div className={`text-[10px] ${msg.ok ? 'text-emerald-300' : 'text-rose-300'}`}>{msg.text}</div>
          )}
        </div>
      )}
    </div>
  )
}
