import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { getFinancialDocument, getFinancialLibrary, useApi } from '../api'
import GlassCard from '../components/ui/GlassCard'
import Spinner from '../components/ui/Spinner'
import FinancialMarkdown from '../components/FinancialMarkdown'
import '../study.css'

export default function FinancialLibrary() {
  const [params, setParams] = useSearchParams(), doc = params.get('doc') || 'README'
  const [query, setQuery] = useState(''), [debounced, setDebounced] = useState('')
  useEffect(() => { const timer = setTimeout(() => setDebounced(query),250); return () => clearTimeout(timer) }, [query])
  const index = useApi(getFinancialLibrary, []), search = useApi(() => debounced ? getFinancialLibrary(debounced) : Promise.resolve(null), [debounced])
  const document = useApi(() => getFinancialDocument(doc), [doc])
  const base = index.data, selected = debounced ? search.data : base
  return <div className="financial-library max-w-7xl mx-auto">
    <div className="study-heading library-heading"><div><span className="study-eyebrow">ANALYSIS & ALGORITHMS</span><h1>분석 시스템과 알고리즘</h1><p>차트 해석부터 종목 점수, 모의매매 조건과 위험 관리까지 구현된 흐름을 설명합니다.</p></div><Link className="button-neutral" to="/">종목 찾기 →</Link></div>
    {base && <div className="study-library-meta"><span>공개 문서 {base.counts.guides}</span><span>구현 원리 · 계산식 · 한계</span><span>{base.snapshot} 문서 기준</span><a href="#financial-reader" className="study-link">문서 검색으로 이동 ↓</a></div>}
    <div className="study-methods">{base?.methods.map((method) => <GlassCard key={method.id} className="study-method"><span className="study-eyebrow">{method.mode}</span><h2>{method.title}</h2><p>{method.description}</p><p className="study-caption">{method.limits}</p><div>{method.docs.map((key) => <Link key={key} to={`/learn?doc=${key}`}>{base.documents.find((d) => d.id === key)?.title || key} →</Link>)}</div></GlassCard>)}</div>
    <GlassCard id="financial-reader" className="study-library-browser">
      <div className="study-heading"><div><h2>공개 문서 탐색</h2><p className="study-caption">현재 코드의 규칙과 계산 가정을 설명합니다. 모의 동작 검증과 투자 성과 검증은 구분합니다.</p></div></div>
      <label className="study-field library-search"><span>문서 검색 · 제목 / 본문</span><input type="search" maxLength={100} placeholder="예: 리테스트, 다이버전스, 손절" value={query} onChange={(e) => setQuery(e.target.value)} /></label>
      {(index.err || search.err) && <p role="alert" className="study-error">문서 목록을 불러오지 못했습니다. <button onClick={() => { index.reload(); search.reload() }}>다시 시도</button></p>}
      {index.loading || (debounced && search.loading) ? <Spinner label="문서 불러오는 중…" /> : <div className="study-reader-layout">
        <nav className="study-doc-nav" aria-label="공개 설명 문서"><section><h3>시스템 설명</h3>{!selected?.documents?.length && <p>검색 결과가 없습니다.</p>}{selected?.documents.map((d) => <button key={d.id} className={doc === d.id ? 'is-active' : ''} aria-current={doc === d.id ? 'page' : undefined} onClick={() => setParams({ doc: d.id })}>{d.title}</button>)}</section></nav>
        <article className="study-document">{document.loading ? <Spinner label="문서 불러오는 중…" /> : document.err ? <p role="alert" className="study-error">문서를 불러오지 못했습니다. <button onClick={document.reload}>다시 시도</button></p> : document.data && <><div className="study-document-meta"><strong>{document.data.title}</strong><span>공개용 시스템 설명</span></div><FinancialMarkdown content={document.data.content} currentPath={document.data.path} documents={base?.documents || []} images={[]} /></>}</article>
      </div>}
    </GlassCard>
  </div>
}
