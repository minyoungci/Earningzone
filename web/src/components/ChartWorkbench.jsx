import { cloneElement, useId, useState } from 'react'
import { Link } from 'react-router-dom'
import { getChartStudy, useApi } from '../api'
import { expectedMove, fibonacci, measuredTarget, riskPlan } from '../lib/studyMath'
import CandleChart from './CandleChart'
import GlassCard from './ui/GlassCard'
import Spinner from './ui/Spinner'
import '../study.css'

const fmt = (v, digits = 2) => Number.isFinite(v) ? v.toLocaleString('ko-KR', { maximumFractionDigits: digits }) : '—'
const structureNames = { uptrend: '고점·저점 상승', downtrend: '고점·저점 하락', mixed: '혼합 구조', broken: '기존 구조 이탈', insufficient: '피벗 확인 대기' }
const stateNames = { watching: '돌파 대기', breakout: '돌파 · 리테스트 대기', retest: '리테스트 유지 · 후속 대기', confirmed: '후속 종가 확인', invalidated: '무효화', expired: '20봉 대기 만료' }
const Source = ({ doc = 'CHART_METHODS', children = '계산 방법과 한계' }) => <Link className="study-link" to={`/learn?doc=${doc}`}>{children} →</Link>
function Field({ label, value, onChange, suffix, children }) {
  const id = useId()
  return <label className="study-field"><span id={id}>{label}{suffix && <small>{suffix}</small>}</span>{children ? cloneElement(children, { 'aria-labelledby': id }) : <input aria-labelledby={id} type="number" step="any" value={value} onChange={(e) => onChange(e.target.value)} />}</label>
}
function Check({ checked, onChange, children }) { return <label className="study-check"><input type="checkbox" checked={checked} onChange={onChange} />{children}</label> }

// Remount manual scenarios on symbol change; never carry another symbol's anchors.
export default function ChartWorkbench({ symbol }) { return <Workbench key={symbol} symbol={symbol} /> }
function Workbench({ symbol }) {
  const [interval, setInterval] = useState('1d'), [basis, setBasis] = useState('wick'), [span, setSpan] = useState(3)
  const api = useApi(() => getChartStudy(symbol, interval, span, basis), [symbol, interval, span, basis], { pollMs: 30000 })
  const data = api.data, bars = data?.candles || [], ps = data?.pivots || [], m = data?.metrics || {}, q = data?.quality
  const [ma, setMa] = useState('EMA'), [averages, setAverages] = useState([8, 21]), [showPivots, setShowPivots] = useState(true), [showZones, setShowZones] = useState(true)
  const [tab, setTab] = useState('geometry'), [showScenario, setShowScenario] = useState(false)
  const [anchors, setAnchors] = useState({ start: '', end: '', indexA: '', indexB: '', high: '', low: '', breakout: '', direction: 'up' })
  const [em, setEm] = useState({ spot: '', iv: '', days: '5', basis: 'calendar' })
  const [risk, setRisk] = useState({ entry: '', stop: '', target: '', equity: '', riskPct: '1', budget: '', cash: '', fx: /^\d{6}$/.test(symbol) ? '1' : '', feePct: '0', taxPct: '0', slipPct: '0' })
  const change = (setter, key) => (value) => setter((old) => ({ ...old, [key]: value }))
  const fib = fibonacci(anchors.start, anchors.end), target = measuredTarget(anchors.high, anchors.low, anchors.breakout, anchors.direction)
  const move = expectedMove(em.spot, em.iv, em.days, em.basis), plan = riskPlan(risk)
  const overlays = (data?.overlays || []).filter((o) => averages.some((p) => o.label === `${ma}${p}`))
  const a = bars[Number(anchors.indexA)], b = bars[Number(anchors.indexB)]
  if (showScenario && tab === 'geometry' && anchors.indexA !== '' && anchors.indexB !== '' && Number(anchors.indexA) < Number(anchors.indexB) && a && b && Number(anchors.start) > 0 && Number(anchors.end) > 0) {
    overlays.push({ label: '수동 추세선', color: '#17a387', data: [{ time: a.time, value: Number(anchors.start) }, { time: b.time, value: Number(anchors.end) }] })
  }
  const priceLines = showZones ? (data?.zones || []).flatMap((z) => [{ price: z.lower, title: `${z.direction === 'up' ? '고점' : '저점'} 구간 하단`, color: '#8d83c4' }, { price: z.upper, title: '구간 상단', color: '#8d83c4' }]) : []
  if (showScenario) {
    if (tab === 'geometry') {
      priceLines.push(...fib.map((f) => ({ price: f.price, title: `Fib ${fmt(f.ratio * 100, 1)}%`, color: '#b28941' })))
      if (target) priceLines.push({ price: target.target, title: '수동 측정 목표', color: '#17a387' })
    }
    if (tab === 'em' && move) priceLines.push({ price: move.lower, title: '가정 EM 하단', color: '#428fa3' }, { price: move.upper, title: '가정 EM 상단', color: '#428fa3' })
    if (tab === 'risk' && !plan.error) priceLines.push(...['entry', 'stop', 'target'].map((key, i) => ({ price: Number(risk[key]), title: ['가정 진입', '가정 손절', '가정 목표'][i], color: ['#78838d', '#d27078', '#17a387'][i] })))
  }
  const markers = showPivots ? ps.map((p) => ({ time: p.time, position: p.side === 'high' ? 'aboveBar' : 'belowBar', shape: 'circle', color: p.side === 'high' ? '#7b61c9' : '#428fa3', text: p.label })) : []
  return <GlassCard className="study-workbench" delay={0.05}>
    <div className="study-heading"><div><span className="study-eyebrow">CHART STUDY</span><h2>차트 분석 도구</h2><p>가격 구조부터 확인하고, 시나리오와 초기 위험을 계산하세요.</p></div><Source /></div>
    <div className="study-toolbar">
      <Field label="시간 단위"><select value={interval} onChange={(e) => { setInterval(e.target.value); setShowScenario(false); setAnchors((old) => ({ ...old, indexA: '', indexB: '' })) }}><option value="1d">일봉</option><option value="1m">1분봉</option></select></Field>
      <Field label="피벗 가격"><select value={basis} onChange={(e) => setBasis(e.target.value)}><option value="wick">꼬리 포함</option><option value="body">몸통 기준</option></select></Field>
      <Field label="좌·우 확인 봉"><select value={span} onChange={(e) => setSpan(Number(e.target.value))}>{[2,3,5,10].map((v) => <option key={v} value={v}>{v}봉</option>)}</select></Field>
      <Field label="이동평균"><select value={ma} onChange={(e) => setMa(e.target.value)}><option>EMA</option><option>SMA</option></select></Field>
      <div className="study-checks">{[8,20,21,50,60,200].map((p) => <Check key={p} checked={averages.includes(p)} onChange={() => setAverages((old) => old.includes(p) ? old.filter((n) => n !== p) : [...old, p])}>{p}</Check>)}<Check checked={showPivots} onChange={() => setShowPivots(!showPivots)}>피벗</Check><Check checked={showZones} onChange={() => setShowZones(!showZones)}>가격 구간</Check></div>
    </div>
    {api.err && <div role="alert" className="study-error">분석 갱신 실패: {String(api.err.message || api.err)} <button onClick={api.reload}>다시 시도</button></div>}
    {api.loading && !data ? <Spinner label="차트 분석 불러오는 중…" /> : <CandleChart candles={bars} overlays={overlays} priceLines={priceLines} markers={markers} height={440} />}
    {q && <div className="study-caption">완성 추정 {q.closed}/{q.received}봉 · 미완성 {q.unclosed} · 제외 {q.rejected} · 중복 {q.duplicates}{q.stale && <strong> · 데이터 오래됨 / 없음</strong>}<br />관측 {m.start || '—'} ~ {m.end || '—'} · 관측 고저 {fmt(m.low)} ~ {fmt(m.high)} · ATR14 {fmt(m.atr14)}<br />피벗 표시는 과거 위치, 확인은 우측 {span}봉 후. <span title={q.closurePolicy}>일봉은 이전 UTC 날짜만 분석합니다.</span></div>}
    <div className="study-metrics">
      <div><span>가격 구조</span><strong>{structureNames[data?.structure] || '확인 대기'}</strong></div>
      <div><span>RVOL · 직전 20봉</span><strong>{fmt(m.rvol20)}배</strong></div>
      <div><span>방향 거래량 · 20봉 대리값</span><strong>{fmt(m.directionVolume20 == null ? null : m.directionVolume20 * 100)}%</strong></div>
      <div><span>{interval === '1d' ? '실현 변동성 · 252일 연율' : '실현 변동성 · 분봉당'}</span><strong>{fmt(m.realizedVol20 == null ? null : m.realizedVol20 * 100)}%</strong></div>
    </div>
    <div className="study-analysis-grid">
      <section className="study-panel"><h3>돌파 · 리테스트</h3>{!data?.zones?.length && <p>ATR와 확인 피벗이 충분하면 구간을 표시합니다.</p>}{data?.zones?.map((z) => <div className="study-observation" key={z.direction}><strong>{z.direction === 'up' ? '고점 돌파' : '저점 이탈'} · {stateNames[z.state]}</strong><p>{fmt(z.lower)} ~ {fmt(z.upper)} · 독립 접촉 {z.independentTouches}회</p><small>구간 확정 {z.establishedAt} · 반폭 ATR14×0.25</small><div>{z.events.slice(-3).map((e, i) => <small key={i}>{e.time} {stateNames[e.state]}<br /></small>)}</div></div>)}<p className="study-caption">구간 경계 밖 종가 → 다음 봉부터 접촉·유지 → 리테스트 봉 고/저점 밖 후속 종가. 20봉 대기 한도는 분석용 휴리스틱입니다.</p></section>
      <section className="study-panel"><h3>다이버전스 · 거래량 맥락</h3>{data?.divergences?.length ? data.divergences.map((d) => <div className="study-observation" key={`${d.indicator}${d.direction}`}><strong>{d.indicator} · {d.direction === 'bullish' ? '상승' : '하락'} {d.state === 'candidate' ? '후보' : '무효'}</strong><p>{d.from} → {d.to}</p><small>판단 가능 {d.availableAt} · 지표 {fmt(d.valueA)} → {fmt(d.valueB)}</small></div>) : <p>최근 두 확인 피벗에서 다이버전스 후보가 없습니다.</p>}<p>최근 20봉 큰 음봉 + RVOL≥1.5: <strong>{m.distributionDates?.length ?? '—'}회</strong><br />시가 갭 / 직전 ATR: {fmt(data?.gap?.gapATR)} · 종가 위치 {fmt(data?.gap?.closeLocation == null ? null : data.gap.closeLocation * 100)}%</p><p className="study-caption">수급의 대리값입니다. 실적 일정이 연결되지 않아 PEG로 확정하지 않습니다.</p></section>
    </div>
    <details className="study-details"><summary>피벗 관측 시각과 확인 시각 ({ps.length})</summary><div className="study-table-wrap"><table><thead><tr><th>구조</th><th>가격</th><th>피벗 봉</th><th>확인 봉</th></tr></thead><tbody>{ps.slice(-20).reverse().map((p) => <tr key={`${p.time}${p.side}`}><td>{p.label}</td><td>{fmt(p.price)}</td><td>{p.time}</td><td>{p.confirmedAt}</td></tr>)}</tbody></table></div></details>
    <section className="study-scenario">
      <div className="study-heading"><h3>시나리오 계산</h3><Check checked={showScenario} onChange={() => setShowScenario(!showScenario)}>현재 도구의 선 표시</Check></div>
      <div className="study-tabs" role="group" aria-label="시나리오 도구">{[['geometry','피보나치 · 목표'],['em','예상 변동폭'],['risk','위험 · 수량']].map(([id,label]) => <button key={id} aria-pressed={tab === id} onClick={() => setTab(id)}>{label}</button>)}</div>
      {tab === 'geometry' && <div>
        <p className="study-caption">시작 → 끝은 시간 순서입니다. 되돌림 0%는 끝 가격, 100%는 시작 가격입니다. 추세선은 지정한 두 봉 사이에 표시합니다.</p>
        <div className="study-fields"><Field label="시작 가격" value={anchors.start} onChange={change(setAnchors,'start')} /><Field label="끝 가격" value={anchors.end} onChange={change(setAnchors,'end')} />{[['indexA','시작 봉'],['indexB','끝 봉']].map(([key,label]) => <Field key={key} label={label}><select value={anchors[key]} onChange={(e) => change(setAnchors,key)(e.target.value)}><option value="">봉 선택</option>{bars.map((bar,i) => <option key={bar.time} value={i}>{bar.time}</option>)}</select></Field>)}</div>
        <div className="study-levels">{fib.length ? fib.map((f) => <span key={f.ratio}>{fmt(f.ratio*100,1)}% <strong>{fmt(f.price)}</strong></span>) : <p>서로 다른 양수 가격을 입력하세요.</p>}</div>
        <h4>측정 목표 · 삼각형 / 더블탑·바텀</h4><div className="study-fields"><Field label="측정 상단" value={anchors.high} onChange={change(setAnchors,'high')} /><Field label="측정 하단 / 넥라인" value={anchors.low} onChange={change(setAnchors,'low')} /><Field label="돌파 / 이탈 가격" value={anchors.breakout} onChange={change(setAnchors,'breakout')} /><Field label="방향"><select value={anchors.direction} onChange={(e) => change(setAnchors,'direction')(e.target.value)}><option value="up">상방 · 높이 더하기</option><option value="down">하방 · 높이 빼기</option></select></Field></div><p aria-live="polite">높이 {fmt(target?.height)} · 측정 목표 <strong>{fmt(target?.target)}</strong></p><Source doc="CHART_METHODS">측정 방법과 한계</Source>
      </div>}
      {tab === 'em' && <div><p className="study-caption">만기와 기간에 맞는 연율 IV를 직접 입력하세요. S × IV × √(기간/연간 기준)의 선형 근사이며 확률을 보장하지 않습니다.</p><div className="study-fields"><Field label="기준 가격" value={em.spot} onChange={change(setEm,'spot')} /><Field label="연율 IV" suffix="% · 수동 가정" value={em.iv} onChange={change(setEm,'iv')} /><Field label="남은 기간" suffix={em.basis === 'calendar' ? '달력일' : '거래일'} value={em.days} onChange={change(setEm,'days')} /><Field label="연간 기준"><select value={em.basis} onChange={(e) => change(setEm,'basis')(e.target.value)}><option value="calendar">달력일 / 365</option><option value="trading">거래일 / 252</option></select></Field></div><p aria-live="polite">가정 범위 <strong>{fmt(move?.lower)} ~ {fmt(move?.upper)}</strong> · ±{fmt(move?.move)}</p><Source doc="CHART_METHODS" /></div>}
      {tab === 'risk' && <div><p className="study-caption">주식 롱 · 가격은 종목 통화, 자산·예산·현금·위험은 원화. 환율은 종목 통화 1단위당 원화입니다. 비용 기본값 0은 계산 가정이므로 실제 비용을 입력하세요.</p><button className="button-neutral" disabled={!bars.length} onClick={() => setRisk((old) => ({ ...old, entry: String(bars.at(-1).close) }))}>완성 봉 종가를 진입 가정에 넣기</button><div className="study-fields risk-fields">{[['entry','진입 가격'],['stop','손절 가격'],['target','목표 가격'],['fx','환율 · 원/종목 통화'],['equity','계좌 자산 · 원'],['riskPct','위험 비율 · %'],['budget','매수 예산 · 원'],['cash','가용 현금 · 원'],['feePct','편도 수수료 · %'],['taxPct','매도 세금 · %'],['slipPct','편도 슬리피지 · %']].map(([key,label]) => <Field key={key} label={label} value={risk[key]} onChange={change(setRisk,key)} />)}</div><div aria-live="polite">{plan.error ? <p className="study-caption">{plan.error}</p> : <><div className="study-metrics"><div><span>위험·예산·현금 중 최소 수량</span><strong>{fmt(plan.quantity,0)}주</strong></div><div><span>비용 포함 초기 위험</span><strong>{fmt(plan.initialRisk,0)}원</strong></div><div><span>비용 포함 매수 금액</span><strong>{fmt(plan.cost,0)}원</strong></div><div><span>순손익비 · R:R</span><strong>{fmt(plan.rr)} : 1</strong></div></div>{plan.rr <= 0 && <p className="study-error">비용이 목표 수익보다 큽니다.</p>}{plan.quantity === 0 && <p>예산·현금 또는 위험 한도가 1주 매수에 부족합니다.</p>}</>}</div><Source doc="RISK_AND_BACKTEST">계산 기준과 한계</Source></div>}
    </section>
    <p className="study-caption">OHLCV와 입력 가정을 계산한 분석입니다. 시나리오 입력은 계좌·주문·자동매매 정책에 저장되지 않습니다.</p>
  </GlassCard>
}
