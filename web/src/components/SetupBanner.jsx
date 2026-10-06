import { useState } from 'react'
import { useApi, getSelftest, saveKeys } from '../api'

// stage 별 안내(제목·다음 행동). ok/네트워크 일시오류는 배너를 띄우지 않는다.
// form:true 인 단계(nokey/auth)는 앱 안에서 바로 키를 입력·저장할 수 있다(데스크톱 앱).
const GUIDE = {
  nokey: {
    title: '토스 API 키를 입력하세요',
    steps: ['아래에 토스증권 Open API 의 CLIENT_ID / CLIENT_SECRET 을 붙여넣고 저장하세요.',
      '키는 OS 자격 증명 관리자(키체인)에 안전하게 저장되며, 평문 파일로 남지 않습니다.'],
    form: true,
  },
  auth: {
    title: '키 인증에 실패했습니다',
    steps: ['CLIENT_ID / CLIENT_SECRET 값에 오타·공백이 없는지 확인하고 아래에서 다시 저장하세요.',
      '토스증권 WTS > 설정 > Open API 에서 키를 재확인·재발급할 수 있습니다.'],
    form: true,
  },
  ip: {
    title: '허용되지 않은 IP입니다',
    steps: ['아래 “현재 공인 IP”를 복사해, 토스증권 개발자센터의 키 설정 > 허용 IP 에 추가하세요.',
      '추가 후 잠시 뒤 “다시 확인”을 누르세요.'],
  },
}

export default function SetupBanner() {
  // 30초마다 자가진단 — 문제 해결 시 자동으로 배너가 사라진다.
  const { data, loading, reload } = useApi(() => getSelftest(), [], { pollMs: 30000 })
  const [copied, setCopied] = useState(false)
  const [cid, setCid] = useState('')
  const [csec, setCsec] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveErr, setSaveErr] = useState('')

  // 정상이거나(첫 로딩 포함) 일시적 네트워크 오류면 배너를 띄우지 않는다.
  if (!data || data.ok || data.stage === 'network' || data.stage === 'api') return null
  const g = GUIDE[data.stage]
  if (!g) return null

  const copyIp = async () => {
    if (!data.publicIp) return
    try {
      await navigator.clipboard.writeText(data.publicIp)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { /* 클립보드 불가 무시 */ }
  }

  const submitKeys = async () => {
    if (saving) return
    if (!cid.trim() || !csec.trim()) { setSaveErr('CLIENT_ID / CLIENT_SECRET 를 모두 입력하세요'); return }
    setSaving(true); setSaveErr('')
    try {
      await saveKeys(cid.trim(), csec.trim())
      setCid(''); setCsec('')
      reload() // 새 키로 자가진단 재검사 → 정상이면 배너 자동 사라짐
    } catch (e) {
      setSaveErr(e.message || '저장에 실패했습니다')
    }
    setSaving(false)
  }

  return (
    <div className="mb-5 rounded-2xl border border-amber-400/30 bg-amber-500/[0.08] p-4">
      <div className="flex items-start gap-3">
        <span className="text-xl leading-none">⚠️</span>
        <div className="min-w-0 flex-1">
          <div className="font-bold text-amber-200">{g.title}</div>
          <div className="text-sm text-slate-300 mt-1">{data.message}</div>
          <ol className="mt-2 space-y-1 text-[13px] text-slate-400 list-decimal list-inside">
            {g.steps.map((s, i) => <li key={i}>{s}</li>)}
          </ol>

          {g.form && (
            <div className="mt-3 flex flex-col gap-2 max-w-md">
              <input
                value={cid}
                onChange={(e) => setCid(e.target.value)}
                placeholder="TOSS_CLIENT_ID"
                autoComplete="off" spellCheck={false}
                className="glass-soft w-full px-3 py-2 rounded-xl bg-transparent border border-transparent focus:border-amber-400/40 outline-none text-sm stat-num"
                aria-label="TOSS_CLIENT_ID"
              />
              <input
                type="password"
                value={csec}
                onChange={(e) => setCsec(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && submitKeys()}
                placeholder="TOSS_CLIENT_SECRET"
                autoComplete="off" spellCheck={false}
                className="glass-soft w-full px-3 py-2 rounded-xl bg-transparent border border-transparent focus:border-amber-400/40 outline-none text-sm stat-num"
                aria-label="TOSS_CLIENT_SECRET"
              />
              <div className="flex items-center gap-2">
                <button
                  onClick={submitKeys}
                  disabled={saving}
                  className="px-3 py-1.5 rounded-xl text-sm font-semibold bg-amber-500/20 text-amber-100 border border-amber-400/40 hover:bg-amber-500/30 transition active:scale-[0.97] disabled:opacity-50"
                >
                  {saving ? '저장 중…' : '키 저장하고 연결'}
                </button>
                {saveErr && <span className="text-[12px] text-rose-300">{saveErr}</span>}
              </div>
            </div>
          )}

          {data.stage === 'ip' && data.publicIp && (
            <div className="mt-3 flex items-center gap-2 flex-wrap">
              <span className="text-[11px] text-slate-400">현재 공인 IP</span>
              <code className="stat-num px-2 py-1 rounded-lg bg-black/30 border border-white/10 text-amber-200">
                {data.publicIp}
              </code>
              <button
                onClick={copyIp}
                className="text-[11px] px-2 py-1 rounded-lg glass-soft glass-hover"
              >
                {copied ? '복사됨 ✓' : '복사'}
              </button>
            </div>
          )}

          <button
            onClick={reload}
            disabled={loading}
            className="mt-3 px-3 py-1.5 rounded-xl text-sm font-semibold bg-amber-500/15 text-amber-200 border border-amber-400/30 hover:bg-amber-500/25 transition active:scale-[0.97] disabled:opacity-50"
          >
            다시 확인
          </button>
        </div>
      </div>
    </div>
  )
}
