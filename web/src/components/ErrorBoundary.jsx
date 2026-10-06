import { Component } from 'react'

/**
 * 렌더 중 throw 를 격리하는 에러 바운더리.
 * - App.jsx 에서 <Routes> 를 감싸 한 페이지의 렌더 결함이 앱 전체(8탭)를
 *   백지화하지 않게 하고, main.jsx 에서 루트를 한 번 더 감싸 네비게이션 등
 *   셸 크래시도 흡수한다.
 * - key={location.pathname} 로 쓰면 라우트 이동 시 에러 상태가 자동 리셋된다.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    // 원인 추적용 — 화면에는 일반 안내만 노출한다.
    console.error('렌더링 오류:', error, info?.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex flex-col items-center justify-center py-24">
          <div className="glass p-8 max-w-md w-full text-center">
            <div className="text-5xl mb-4">💥</div>
            <div className="text-xl font-extrabold text-white">화면을 표시하지 못했습니다</div>
            <p className="text-sm text-slate-400 mt-2 leading-relaxed">
              이 섹션에서 예기치 못한 오류가 발생했어요. 다른 탭은 정상 동작합니다.
            </p>
            <button
              type="button"
              onClick={() => this.setState({ error: null })}
              className="inline-flex items-center gap-2 mt-6 px-5 py-3 rounded-2xl bg-white/[0.12] text-white text-sm font-semibold hover:bg-white/20 transition active:scale-[0.97]"
            >
              ↻ 다시 시도
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
