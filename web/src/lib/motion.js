// 모션 토큰 — Emil Kowalski(animations.dev) 디자인 엔지니어링 기준.
// framer-motion 빌트인 이징('easeOut' 등)은 너무 약해서, 강한 커스텀 cubic-bezier 를
// 앱 전역의 기본값으로 쓴다. transition.ease 에 배열을 그대로 넘기면 된다.
import { useSyncExternalStore } from 'react'

export const EASE_OUT = [0.23, 1, 0.32, 1] // 진입/이탈 UI (강한 ease-out)
export const EASE_IN_OUT = [0.77, 0, 0.175, 1] // 화면 내 이동/모프
export const EASE_DRAWER = [0.32, 0.72, 0, 1] // iOS식 드로어 커브

// 터치 기기에서 framer 의 whileHover 리프트는 탭하면 발동 후 고착된다.
// (hover: hover) and (pointer: fine) 가 참일 때만 hover 모션을 걸기 위한 구독형 훅.
const HOVER_QUERY = '(hover: hover) and (pointer: fine)'
const canMatch = () => typeof window !== 'undefined' && typeof window.matchMedia === 'function'

export function useHasHover() {
  return useSyncExternalStore(
    (onChange) => {
      if (!canMatch()) return () => {}
      const mql = window.matchMedia(HOVER_QUERY)
      mql.addEventListener('change', onChange)
      return () => mql.removeEventListener('change', onChange)
    },
    () => (canMatch() ? window.matchMedia(HOVER_QUERY).matches : false),
    () => false, // SSR/초기: hover 없다고 가정(리프트 미적용이 안전)
  )
}
