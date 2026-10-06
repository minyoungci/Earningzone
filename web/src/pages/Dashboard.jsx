import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useApi, getHealth, getWatchlist, getScreener, getSim, getSimAccounts, selectSimAccount } from '../api'
import { money, pct, num, retText, signedWon } from '../lib/format'
import Icon from '../components/ui/Icon'
import Badge from '../components/ui/Badge'
import Spinner from '../components/ui/Spinner'
import Heatmap from '../components/Heatmap'

function ErrorBox({ error }) {
  return <div className="dashboard-error" role="alert">{error?.message || '데이터를 불러오지 못했습니다. 잠시 후 다시 확인해 주세요.'}</div>
}

function AccountPanel({ accounts, state }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [expanded, setExpanded] = useState(() => window.matchMedia('(min-width: 1100px)').matches)
  const data = state.data
  const list = accounts.data?.accounts || []
  const active = accounts.data?.active
  const choose = async (id) => {
    if (busy || id === active) return
    setBusy(true); setError(null)
    try { await selectSimAccount(id) } catch (e) { setError(e) }
    finally { setBusy(false) }
  }
  return <aside className="glass account-panel" aria-label="모의계좌 요약">
    <div className="panel-heading"><h2>계좌<span className="account-mobile-name">{list.find((account) => account.id === active)?.name || '모의계좌'}</span></h2><Link to="/sim" className="text-link"><Icon name="plus" size={15} /> 관리</Link></div>
    <div className="account-caption">총 평가액 · 모의계좌</div>
    <div className="account-value">{data ? money(data.equity) : '—'}</div>
    {data && <div className={'account-return ' + retText(data.totalPnl)}>{signedWon(data.totalPnl)} <span>({pct(data.totalPnlPct)})</span></div>}
    {state.err && !data && <ErrorBox error={state.err} />}
    <details className="account-details" open={expanded} onToggle={(e) => setExpanded(e.currentTarget.open)}>
      <summary>계좌와 보유 종목<Icon name="chevron" size={16} /></summary>
      {accounts.err && <ErrorBox error={accounts.err} />}
      <div className="account-list">
        {list.map((account) => <button key={account.id} className={account.id === active ? 'account-choice is-active' : 'account-choice'} onClick={() => choose(account.id)} disabled={busy} aria-pressed={account.id === active}>
          <span className="account-name" title={account.name}>{account.name}</span>{account.id === active && <span aria-label="선택된 계좌">✓</span>}
        </button>)}
      </div>
      {error && <ErrorBox error={error} />}
      <div className="account-section-label">자산 구성</div>
      <div className="balance-line"><span>가용 현금</span><span>{money(data?.cash)}</span></div>
      <div className="balance-line"><span>보유 종목</span><span>{data ? money(data.equity - data.cash) : '—'}</span></div>
      <div className="account-section-label">보유 종목 · {data?.positions?.length ?? 0}</div>
      {data?.positions?.length ? data.positions.slice(0, 5).map((position) => <Link key={position.symbol} className="holding-line" to={'/symbol/' + position.symbol}>
        <span className="holding-avatar">{(position.name || position.symbol).slice(0, 1)}</span>
        <span className="min-w-0 flex-1"><span className="block truncate" title={position.name || position.symbol}>{position.name || position.symbol}</span><small>{position.qty}주 · {money(position.valueKrw)}</small></span>
        <Icon name="chevron" size={14} />
      </Link>) : <div className="dashboard-empty">아직 보유 종목이 없습니다.</div>}
      <Link to="/sim" className="section-footer">모의계좌 열기<Icon name="arrow" size={15} /></Link>
    </details>
    <p className="account-footnote">모의계좌 기준 · 금액은 원화 환산<br />실제 증권 계좌와 별도로 관리됩니다.</p>
  </aside>
}

function AllocationDonut({ cash, invested }) {
  const total = Math.max(0, cash) + Math.max(0, invested)
  const share = total > 0 ? Math.max(0, invested) / total : 0
  return <svg className="allocation-donut" viewBox="0 0 160 160" role="img" aria-label={'자산 구성: 현금 ' + Math.round((1 - share) * 100) + '%, 보유 종목 ' + Math.round(share * 100) + '%'}>
    <circle cx="80" cy="80" r="58" fill="none" stroke="#aedbbf" strokeWidth="28" />
    <circle cx="80" cy="80" r="58" fill="none" stroke="#80baca" strokeWidth="28" pathLength="100" strokeDasharray={share * 100 + ' 100'} transform="rotate(-90 80 80)" />
  </svg>
}

function AllocationBlock({ label, amount, share, color }) {
  return <div className="allocation-block">
    <div className="allocation-title"><span>{label}</span><span>{Math.round(share * 100)}%</span></div>
    <div className="allocation-value">{money(amount)}</div>
    <div className="allocation-track"><span style={{ width: Math.round(share * 100) + '%', background: color }} /></div>
  </div>
}

export default function Dashboard() {
  const accounts = useApi(() => getSimAccounts(), [], { pollMs: 60000 })
  const state = useApi(() => getSim(), [accounts.data?.active], { pollMs: 15000 })
  const health = useApi(() => getHealth(), [], { pollMs: 60000 })
  const watch = useApi(() => getWatchlist(), [], { pollMs: 60000 })
  const watchUs = useApi(() => getWatchlist('us'), [], { pollMs: 60000 })
  const screen = useApi(() => getScreener(), [], { pollMs: 60000 })
  const [market, setMarket] = useState('kr')
  const currentWatch = market === 'kr' ? watch : watchUs
  const items = currentWatch.data?.items || []
  const signals = [...(screen.data?.items || [])].sort((a, b) => (b.score || 0) - (a.score || 0))
  const buyCount = signals.filter((item) => item.action === 'BUY').length
  const data = state.data
  const cash = data?.cash || 0
  const invested = Math.max(0, (data?.equity || 0) - cash)
  const total = cash + invested
  const activeName = accounts.data?.accounts.find((account) => account.id === accounts.data.active)?.name || '모의계좌'
  const updatedAt = watch.data?.generatedAt
  return <div className="dashboard-layout">
    <AccountPanel accounts={accounts} state={state} />
    <div className="dashboard-main">
      <section className="glass overview-card" aria-labelledby="overview-title">
        <div className="overview-heading">
          <div><h1 id="overview-title">투자 현황</h1><div className="overview-subtitle">{activeName} · {new Date().toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric' })}</div></div>
          <span className="pill-neutral"><span className="status-dot" />모의투자</span>
        </div>
        {state.loading ? <Spinner label="계좌 현황 불러오는 중…" /> : state.err && !data ? <ErrorBox error={state.err} /> : <>
          <div className="overview-grid">
            <div><div className="overview-primary"><AllocationDonut cash={cash} invested={invested} /><div>
              <div className="overview-number">{money(data?.equity)}</div><div className="overview-value-label">총 평가액</div>
              <div className={'overview-change ' + retText(data?.totalPnl)}>{signedWon(data?.totalPnl)} <span>({pct(data?.totalPnlPct)})</span></div>
            </div></div><div className="allocation-legend"><span><i className="legend-dot" style={{ background: '#aedbbf' }} />가용 현금</span><span><i className="legend-dot" style={{ background: '#80baca' }} />보유 종목</span></div></div>
            <div className="allocation-blocks"><AllocationBlock label="가용 현금" amount={cash} share={total > 0 ? cash / total : 0} color="#aedbbf" /><AllocationBlock label="보유 종목 평가액" amount={invested} share={total > 0 ? invested / total : 0} color="#80baca" /></div>
          </div>
          {data?.fxEstimated && <p className="quiet-note">환율 추정치가 적용된 평가액입니다.</p>}
          {state.err && data && <p className="dashboard-error mt-5">계좌 갱신 실패 · 마지막 확인 값을 표시합니다.</p>}
        </>}
        <div className="dashboard-summary">
          <div><div className="summary-label">보유 종목</div><div className="summary-value">{data ? data.positions.length + '개' : '—'}</div></div>
          <div><div className="summary-label">분석 전략</div><div className="summary-value">{health.data?.strategies != null ? health.data.strategies + '개' : '—'}</div></div>
          <div><div className="summary-label">매수 신호</div><div className="summary-value">{screen.data ? buyCount + '종목' : '—'}</div></div>
        </div>
      </section>
      <div className="dashboard-bottom">
        <section className="glass dashboard-section" aria-labelledby="watch-title">
          <div className="section-heading"><div><h2 id="watch-title">관심종목</h2><div className="section-description">현재가와 일간 등락을 한눈에</div></div><span className="pill-neutral">{items.length}종목</span></div>
          <div className="market-tabs" role="group" aria-label="관심종목 시장"><button aria-pressed={market === 'kr'} onClick={() => setMarket('kr')}>국내</button><button aria-pressed={market === 'us'} onClick={() => setMarket('us')}>미국</button></div>
          {currentWatch.loading ? <Spinner label="관심종목 불러오는 중…" /> : currentWatch.err && !currentWatch.data ? <ErrorBox error={currentWatch.err} /> : !items.length ? <div className="dashboard-empty">등록된 관심종목이 없습니다.</div> : <table className="watch-table">
            <thead><tr><th scope="col">종목</th><th scope="col">현재가</th><th scope="col">등락</th><th scope="col" className="watch-signal">신호</th></tr></thead>
            <tbody>{items.map((item) => <tr key={item.symbol}><td><Link className="stock-name" title={item.name || item.symbol} to={'/symbol/' + item.symbol}>{item.name || item.symbol}</Link><div className="stock-code">{item.symbol}</div></td><td>{money(item.price, item.currency)}</td><td className={retText(item.ret?.['1'])}>{pct(item.ret?.['1'])}</td><td className="watch-signal"><Badge action={item.action} /></td></tr>)}</tbody>
          </table>}
          {currentWatch.err && currentWatch.data && <p className="quiet-note">갱신 실패 · 마지막 확인 값을 표시합니다.</p>}
          <Link to="/market" className="section-footer">시장 현황 보기<Icon name="arrow" size={16} /></Link>
        </section>
        <section className="glass dashboard-section" aria-labelledby="signals-title">
          <div className="section-heading"><div><h2 id="signals-title">상위 분석 신호</h2><div className="section-description">전략 점수가 높은 종목</div></div><Link to="/quant" className="text-link">더 보기<Icon name="chevron" size={14} /></Link></div>
          {screen.loading ? <Spinner label="분석 신호 불러오는 중…" /> : screen.err && !screen.data ? <ErrorBox error={screen.err} /> : !signals.length ? <div className="dashboard-empty">표시할 분석 결과가 없습니다.</div> : <div className="signal-list">
            {signals.slice(0, 6).map((item, index) => <Link key={item.symbol} className="signal-tile" to={'/symbol/' + item.symbol}>
              <div className="signal-top"><span className="signal-rank">{index + 1}</span><Badge action={item.action} /></div><div className="signal-name" title={item.name || item.symbol}>{item.name || item.symbol}</div><div className="signal-price">{money(item.price, item.currency)}</div><div className="signal-score">전략 점수 <strong>{num(item.score, 1)}</strong></div>
            </Link>)}
          </div>}
          {screen.err && screen.data && <p className="quiet-note">분석 갱신 실패 · 마지막 결과를 표시합니다.</p>}
          <p className="quiet-note">분석 신호는 매매 판단을 돕는 참고 정보입니다.</p>
          <Link to="/backtest" className="section-footer">백테스트로 확인하기<Icon name="arrow" size={16} /></Link>
        </section>
      </div>
      <details className="glass dashboard-heatmap"><summary>점수 히트맵<Icon name="chevron" size={16} /></summary>{screen.loading ? <Spinner /> : screen.err && !screen.data ? <ErrorBox error={screen.err} /> : <Heatmap items={signals} limit={36} />}</details>
      <div className="flex items-center justify-between gap-3 text-xs text-slate-500 flex-wrap"><span>{updatedAt ? '시세 확인 · ' + new Date(updatedAt * 1000).toLocaleTimeString('ko-KR') : '시세를 확인하고 있습니다.'}</span><span>60초마다 시세 갱신</span></div>
    </div>
  </div>
}
