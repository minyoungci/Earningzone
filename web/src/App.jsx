import { lazy, Suspense } from 'react'
import { NavLink, Route, Routes, useLocation, Link } from 'react-router-dom'
import { AnimatePresence, motion, MotionConfig } from 'framer-motion'
import { EASE_OUT } from './lib/motion'
import SearchBar from './components/SearchBar'
import ThemeToggle from './components/ThemeToggle'
import KeySettings from './components/KeySettings'
import ErrorBoundary from './components/ErrorBoundary'
import SetupBanner from './components/SetupBanner'
import Spinner from './components/ui/Spinner'
import Icon from './components/ui/Icon'

// 페이지는 전부 lazy — 단일 청크(≈600KB)에 lightweight-charts 등이 몰리는 것을 방지.
// lightweight-charts 는 CandleChart/EquityChart 를 쓰는 페이지 청크로 자연 분리된다.
const Dashboard = lazy(() => import('./pages/Dashboard'))
const SymbolDetail = lazy(() => import('./pages/SymbolDetail'))
const Portfolio = lazy(() => import('./pages/Portfolio'))
const Intraday = lazy(() => import('./pages/Intraday'))
const Sim = lazy(() => import('./pages/Sim'))
const Quant = lazy(() => import('./pages/Quant'))
const Backtest = lazy(() => import('./pages/Backtest'))
const Autopilot = lazy(() => import('./pages/Autopilot'))
const Market = lazy(() => import('./pages/Market'))
const FinancialLibrary = lazy(() => import('./pages/FinancialLibrary'))

// short: 모바일 하단탭 전용 짧은 라벨(2~3자) — 8탭에서도 잘리지 않게. 없으면 label 사용.
const NAV = [
  { to: '/', label: '대시보드', short: '홈', icon: 'grid', end: true },
  { to: '/market', label: '마켓', short: '마켓', icon: 'globe' },
  { to: '/intraday', label: '인트라데이', short: '단기 분석', icon: 'zap' },
  { to: '/quant', label: '퀀트', short: '퀀트', icon: 'chart' },
  { to: '/sim', label: '모의투자', short: '모의투자', icon: 'wallet' },
  { to: '/autopilot', label: '오토파일럿', short: '자동매매', icon: 'bot' },
  { to: '/backtest', label: '백테스트', short: '백테스트', icon: 'flask' },
  { to: '/portfolio', label: '포트폴리오', short: '포트폴리오', icon: 'briefcase' },
  { to: '/learn', label: '분석 스터디', short: '스터디', icon: 'book' },
]

function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center py-24">
      <div className="glass p-8 max-w-md w-full text-center">
        <div className="text-5xl mb-4">🧭</div>
        <div className="text-xl font-extrabold text-white">페이지를 찾을 수 없습니다</div>
        <p className="text-sm text-slate-400 mt-2 leading-relaxed">
          요청하신 페이지가 존재하지 않거나 이동되었어요.
        </p>
        <Link
          to="/"
          className="inline-flex items-center gap-2 mt-6 px-5 py-3 rounded-2xl bg-white/[0.12] text-white text-sm font-semibold hover:bg-white/20 transition active:scale-[0.97]"
        >
          <span>📊</span> 대시보드로 돌아가기
        </Link>
      </div>
    </div>
  )
}

export default function App() {
  const location = useLocation()
  const current = NAV.find((n) => n.to === '/' ? location.pathname === '/' : location.pathname.startsWith(n.to))
  const mobileNav = NAV.filter((n) => ['/', '/market', '/quant', '/sim'].includes(n.to))
  const closeMenu = (event) => { const details = event.currentTarget.closest('details'); if (details) details.open = false }
  const escapeMenu = (event) => { if (event.key === 'Escape') { event.currentTarget.open = false; event.currentTarget.querySelector('summary')?.focus() } }
  return (
    <MotionConfig reducedMotion="user">
      <a className="skip-link" href="#main-content">본문으로 이동</a>
      <div className="app-shell">
        <aside className="app-sidebar">
          <Link to="/" className="brand-mark" aria-label="tossbot 홈">t<span aria-hidden="true">.</span></Link>
          <nav className="desktop-nav" aria-label="주요 메뉴">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end} title={n.label} className={({ isActive }) => isActive ? 'rail-link is-active' : 'rail-link'}>
                <Icon name={n.icon} size={22} /><span>{n.short}</span>
              </NavLink>
            ))}
          </nav>
          <div className="rail-footer"><span className="status-dot" /><span>모의투자</span></div>
        </aside>
        <main id="main-content" tabIndex={-1} className="app-main">
          <header className="app-topbar">
            <div className="workspace-title"><Link to="/" className="mobile-brand">tossbot</Link><span className="desktop-crumb">워크스페이스</span><span className="crumb-divider">/</span><span>{current?.label || '종목 분석'}</span></div>
            <div className="header-tools">
              <SearchBar />
              <details className="settings-menu" onKeyDown={escapeMenu}>
                <summary className="button-neutral" aria-label="화면 및 API 설정"><Icon name="settings" /><span className="settings-label">설정</span></summary>
                <div className="settings-popover"><div className="settings-heading">화면 및 연결 설정</div><ThemeToggle /><KeySettings /></div>
              </details>
            </div>
          </header>
          <div className="app-content">
            <SetupBanner />
            <AnimatePresence mode="wait" initial={false}>
              <motion.div key={location.pathname} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.12, ease: EASE_OUT }}>
                <ErrorBoundary key={location.pathname}>
                  <Suspense fallback={<Spinner label="페이지 불러오는 중…" />}>
                    <Routes location={location}>
                      <Route path="/" element={<Dashboard />} />
                      <Route path="/market" element={<Market />} />
                      <Route path="/learn" element={<FinancialLibrary />} />
                      <Route path="/symbol/:symbol" element={<SymbolDetail />} />
                      <Route path="/quant" element={<Quant />} />
                      <Route path="/sim" element={<Sim />} />
                      <Route path="/autopilot" element={<Autopilot />} />
                      <Route path="/backtest" element={<Backtest />} />
                      <Route path="/portfolio" element={<Portfolio />} />
                      <Route path="/intraday" element={<Intraday />} />
                      <Route path="/intraday/:symbol" element={<Intraday />} />
                      <Route path="*" element={<NotFound />} />
                    </Routes>
                  </Suspense>
                </ErrorBoundary>
              </motion.div>
            </AnimatePresence>
          </div>
        </main>
        <nav className="mobile-tabbar" aria-label="모바일 주요 메뉴">
          {mobileNav.map((n) => <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => isActive ? 'mobile-tab is-active' : 'mobile-tab'}><Icon name={n.icon} /><span>{n.short}</span></NavLink>)}
          <details className="mobile-more" onKeyDown={escapeMenu}>
            <summary className={current && !mobileNav.includes(current) ? 'mobile-tab is-active' : 'mobile-tab'}><Icon name="grid" /><span>더보기</span></summary>
            <div className="mobile-menu-panel"><div className="settings-heading">전체 메뉴</div>{NAV.map((n) => <NavLink key={n.to} to={n.to} end={n.end} onClick={closeMenu} className={({ isActive }) => isActive ? 'menu-link is-active' : 'menu-link'}><Icon name={n.icon} /><span>{n.label}</span></NavLink>)}</div>
          </details>
        </nav>
      </div>
    </MotionConfig>
  )
}
