import { useEffect, useState } from 'react'
import { getAuth } from '../api'
import Icon from './ui/Icon'

/** localStorage 키 — index.html 의 FOUC 방지 스크립트와 동일해야 한다 */
const STORAGE_KEY = 'tossbot-theme'
/** 컨트롤 토큰 localStorage 키 — api.js 의 X-Access-Token 자동 첨부와 동일해야 한다 */
const TOKEN_KEY = 'tossbot-token'

const OPTIONS = [
  { id: 'clean', label: '라이트', icon: 'sun' },
  { id: 'wallet', label: '다크', icon: 'moon' },
]

/**
 * 테마 선택 — 라이트(기본) / 다크.
 * · 클릭 시 <html data-theme="clean|wallet"> 설정.
 * · 선택은 localStorage('tossbot-theme') 에 저장 → 새로고침 시
 *   index.html 인라인 스크립트가 첫 페인트 전에 복원(FOUC 방지)
 */
export default function ThemeToggle() {
  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === 'wallet' ? 'wallet' : 'clean'
    } catch (e) {
      return 'clean'
    }
  })

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try { localStorage.setItem(STORAGE_KEY, theme) } catch (e) { /* 저장 실패 무해 */ }
  }, [theme])

  // 쓰기 게이트 상태 — {gate, ok}. 게이트 OFF(로컬 개발)면 토큰 버튼 자체를 숨긴다.
  const [auth, setAuth] = useState(null)
  useEffect(() => {
    let alive = true
    getAuth()
      .then((a) => { if (alive) setAuth(a) })
      .catch(() => { /* 확인 실패 시 버튼 미표시(무해) */ })
    return () => { alive = false }
  }, [])

  // 🔑 토큰 입력/삭제 — 저장 후 새로고침해 모든 요청에 헤더가 반영되게 한다.
  const onToken = () => {
    const v = window.prompt('컨트롤 토큰 입력(열람만 하려면 비워두세요)')
    if (v === null) return // 취소 — 변경 없음
    try {
      if (v.trim()) localStorage.setItem(TOKEN_KEY, v.trim())
      else localStorage.removeItem(TOKEN_KEY)
    } catch (e) { /* 저장 실패 무해 */ }
    location.reload()
  }

  return (
    <div className="flex items-stretch gap-2">
      <div className="glass-soft p-1 flex gap-1 flex-1" role="group" aria-label="테마 선택">
        {OPTIONS.map((o) => {
          const active = theme === o.id
          return (
            <button
              key={o.id}
              type="button"
              aria-pressed={active}
              onClick={() => setTheme(o.id)}
              className={`flex-1 px-2 py-2 rounded-xl text-sm font-medium transition-colors flex items-center justify-center gap-2 ${
                active
                  ? 'bg-violet-500/20 text-violet-200 border border-violet-400/30'
                  : 'text-slate-400 hover:text-slate-200 border border-transparent'
              }`}
            >
              <Icon name={o.icon} size={16} />{o.label}
            </button>
          )
        })}
      </div>
      {/* 🔑 컨트롤 토큰 — 게이트 ON 일 때만 표시. 초록 점=컨트롤 가능, '열람 모드'=GET 전용 */}
      {auth?.gate && (
        <button
          type="button"
          onClick={onToken}
          title={auth.ok ? '컨트롤 권한 활성 — 클릭해 토큰 변경/삭제' : '열람 모드 — 클릭해 컨트롤 토큰 입력'}
          className="glass-soft px-2 py-1.5 rounded-xl text-[11px] font-medium text-slate-300 hover:text-slate-100 transition-colors flex items-center gap-1.5 shrink-0"
        >
          <Icon name="lock" size={15} />
          {auth.ok ? (
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" aria-label="컨트롤 권한 활성" />
          ) : (
            <span className="text-slate-500">열람 모드</span>
          )}
        </button>
      )}
    </div>
  )
}
