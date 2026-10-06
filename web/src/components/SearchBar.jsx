import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { searchStocks } from '../api'
import { EASE_OUT } from '../lib/motion'
import Icon from './ui/Icon'

export default function SearchBar() {
  const [q, setQ] = useState('')
  const [items, setItems] = useState([])
  const [open, setOpen] = useState(false)
  const [hi, setHi] = useState(0)
  const nav = useNavigate()
  const boxRef = useRef(null)
  // 응답 경쟁(out-of-order) 방지: 매 요청마다 증가하는 시퀀스 토큰으로 최신 응답만 반영.
  const seqRef = useRef(0)

  useEffect(() => {
    if (!q.trim()) { setItems([]); return }
    const t = setTimeout(() => {
      const seq = ++seqRef.current
      searchStocks(q)
        .then((d) => {
          if (seq !== seqRef.current) return // 더 최신 요청이 출발했으면 옛 응답 무시
          setItems(d.items || []); setOpen(true); setHi(0)
        })
        .catch(() => {
          if (seq !== seqRef.current) return
          setItems([])
        })
    }, 220)
    return () => clearTimeout(t)
  }, [q])

  useEffect(() => {
    const onClick = (e) => { if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  const go = (sym) => {
    if (!sym) return
    // 옛 목록이 재포커스 시 다시 뜨는 것을 막기 위해 결과를 비운다.
    bumpSeq()
    setOpen(false); setItems([]); setQ(''); nav(`/symbol/${sym}`)
  }
  // 진행 중인 fetch 응답이 무효화되도록 시퀀스를 올린다.
  const bumpSeq = () => { seqRef.current++ }

  const onKey = (e) => {
    if (!open || !items.length) {
      if (e.key === 'Enter' && q.trim()) go(q.trim().toUpperCase())
      return
    }
    if (e.key === 'ArrowDown') { e.preventDefault(); setHi((h) => Math.min(h + 1, items.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setHi((h) => Math.max(h - 1, 0)) }
    else if (e.key === 'Enter') { e.preventDefault(); go(items[hi]?.symbol) }
    else if (e.key === 'Escape') setOpen(false)
  }

  return (
    <div className="search-box relative w-full max-w-md" ref={boxRef}>
      <div className="glass-soft flex items-center gap-2 px-4 py-2.5">
        <Icon name="search" size={18} className="text-slate-400 shrink-0" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={onKey}
          onFocus={() => items.length && setOpen(true)}
          placeholder="종목 이름 또는 코드 검색"
          aria-label="종목 이름 또는 코드 검색"
          className="bg-transparent outline-none text-sm flex-1 min-w-0 placeholder:text-slate-500"
          role="combobox"
          aria-expanded={open && items.length > 0}
          aria-controls="searchbar-listbox"
          aria-autocomplete="list"
          aria-activedescendant={open && items.length > 0 ? `searchbar-opt-${hi}` : undefined}
        />
      </div>
      {open && items.length > 0 && (
        <motion.div
          id="searchbar-listbox"
          role="listbox"
          initial={{ opacity: 0, scale: 0.97 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.15, ease: EASE_OUT }}
          style={{ transformOrigin: 'top' }}
          className="absolute z-50 mt-2 w-full glass p-2 max-h-80 overflow-auto"
        >
          {items.map((it, i) => (
            <button
              key={it.symbol}
              id={`searchbar-opt-${i}`}
              role="option"
              aria-selected={i === hi}
              onMouseDown={(e) => { e.preventDefault(); go(it.symbol) }}
              onMouseEnter={() => setHi(i)}
              className={`w-full text-left px-3 py-2 rounded-xl flex items-center justify-between transition ${i === hi ? 'bg-white/10' : 'hover:bg-white/5'}`}
            >
              <span className="font-semibold text-sm">{it.name || it.symbol}</span>
              <span className="text-xs text-slate-400 stat-num">{it.symbol}{it.market ? ` · ${it.market}` : ''}</span>
            </button>
          ))}
        </motion.div>
      )}
    </div>
  )
}
