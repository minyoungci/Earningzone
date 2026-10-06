// 숫자/통화/색상 포맷 유틸 (한국식: 상승=빨강, 하락=파랑)
export const won = (v) => (v == null ? '-' : Number(v).toLocaleString('ko-KR') + '원')
export const won0 = (v) => (v == null ? '-' : Number(v).toLocaleString('ko-KR'))
export const pct = (v, d = 1) => (v == null ? '-' : (v > 0 ? '+' : '') + Number(v).toFixed(d) + '%')
export const num = (v, d = 0) => (v == null ? '-' : Number(v).toFixed(d))

// 통화 인식 가격 표기: 미국=달러($, 소수 2자리), 한국=원
export const money = (v, ccy = 'KRW') => {
  if (v == null) return '-'
  const n = Number(v)
  return ccy === 'USD'
    ? '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : n.toLocaleString('ko-KR') + '원'
}
export const signedMoney = (v, ccy = 'KRW') =>
  v == null ? '-' : (v >= 0 ? '+' : '-') + money(Math.abs(v), ccy)
export const ccyUnit = (ccy = 'KRW') => (ccy === 'USD' ? '$' : '원')

// 부호 있는 원화 표기(합계/손익 전용 — 이미 원화 환산된 값에 사용)
export const signedWon = (v) =>
  v == null ? '-' : (v >= 0 ? '+' : '') + won0(Math.round(v)) + '원'

// 환율 추정치 적용 안내 문구(요약 근처 작은 경고에 사용)
export const FX_ESTIMATED_NOTE = '환율 추정치 적용'

export const actionLabel = (a) => ({ BUY: '매수', SELL: '매도', HOLD: '관망' }[a] || a)

// 시그널 배지: 매수=초록, 매도=빨강, 관망=회색
export const actionBg = (a) =>
  a === 'BUY'
    ? 'bg-emerald-500/15 text-emerald-300 border-emerald-400/30'
    : a === 'SELL'
    ? 'bg-rose-500/15 text-rose-300 border-rose-400/30'
    : 'bg-slate-500/15 text-slate-300 border-slate-400/30'

export const actionText = (a) =>
  a === 'BUY' ? 'text-emerald-400' : a === 'SELL' ? 'text-rose-400' : 'text-slate-400'

// 가격 등락(한국식): +빨강 / -파랑
export const retText = (v) =>
  v == null ? 'text-slate-400' : v > 0 ? 'text-up' : v < 0 ? 'text-down' : 'text-slate-400'

export const categoryLabel = (c) =>
  ({ trend: '추세', momentum: '모멘텀', volatility: '변동성', meanrev: '평균회귀', breakout: '돌파', structure: '구조' }[c] || c)
