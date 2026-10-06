// Claude Design 동기화용 디자인-시스템 엔트리.
// 앱의 글래스 컴포넌트들을 '명명 익스포트'로 모아 window.<globalName>.* 로 노출한다.
// (원본 컴포넌트는 default export 라 배럴에서 이름을 붙여 재노출한다.)
import { MemoryRouter } from 'react-router-dom'
import { MotionGlobalConfig } from 'framer-motion'

// 미리보기 프로바이더: (1) 라우터 훅(useNavigate/Link)을 위한 MemoryRouter,
// (2) 글래스 디자인은 다크 배경 전제라(반투명 흰 표면 + 밝은 텍스트) 앱과 동일한
// 다크 캔버스를 깔아준다 — 이게 없으면 흰 배경에서 카드가 보이지 않는다.
// cfg.provider.component = "Providers" 로 모든 프리뷰를 감싼다.
export function Providers({ children }) {
  // 프리뷰는 정적 스크린샷이라 framer-motion 진입 애니메이션(opacity:0→1)이 끝나기
  // 전에 캡처되면 빈 화면이 된다. Providers 는 프리뷰에서만 쓰이므로 여기서만 끈다
  // (실제 디자인 에이전트 출력에는 영향 없음 — 거기선 Providers 를 거치지 않는다).
  MotionGlobalConfig.skipAnimations = true
  return (
    <MemoryRouter>
      <div
        style={{
          background: '#060912',
          color: '#e2e8f0',
          minHeight: '100%',
          padding: 24,
          boxSizing: 'border-box',
          fontFamily: 'Pretendard, Inter, system-ui, sans-serif',
        }}
      >
        {children}
      </div>
    </MemoryRouter>
  )
}

// 글래스 프리미티브
export { default as GlassCard } from './components/ui/GlassCard.jsx'
export { default as Badge } from './components/ui/Badge.jsx'
export { default as Gauge } from './components/ui/Gauge.jsx'
export { default as Spinner } from './components/ui/Spinner.jsx'
export { default as StatTile } from './components/ui/StatTile.jsx'

// 도메인(프레젠테이션)
export { default as StockCard } from './components/StockCard.jsx'
export { default as LevelBar } from './components/LevelBar.jsx'
export { default as SignalBoard } from './components/SignalBoard.jsx'
export { default as SymbolChips } from './components/SymbolChips.jsx'
export { default as Heatmap } from './components/Heatmap.jsx'

// 도메인(데이터 바인딩 — 미리보기는 목 데이터로 구성)
export { default as IndicatorGrid } from './components/IndicatorGrid.jsx'
export { default as ScreenerTable } from './components/ScreenerTable.jsx'
export { default as CandleChart } from './components/CandleChart.jsx'
export { default as SearchBar } from './components/SearchBar.jsx'
export { default as TradeWidget } from './components/TradeWidget.jsx'
