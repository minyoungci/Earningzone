export function numeric(value) {
  if (value == null || String(value).trim() === '') return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

export function fibonacci(start, end) {
  const a = numeric(start), b = numeric(end)
  if (!(a > 0 && b > 0) || a === b) return []
  return [0, .236, .382, .5, .618, .786, 1].map((ratio) => ({ ratio, price: b + (a - b) * ratio }))
}

export function measuredTarget(high, low, breakout, direction = 'up') {
  const h = numeric(high), l = numeric(low), b = numeric(breakout)
  if (!(h > l && l > 0 && b > 0)) return null
  const target = b + (direction === 'up' ? 1 : -1) * (h - l)
  return target > 0 ? { height: h - l, target } : null
}

export function expectedMove(spot, ivPercent, days, basis = 'calendar') {
  const s = numeric(spot), iv = numeric(ivPercent), d = numeric(days)
  if (!(s > 0 && iv > 0 && d > 0) || !['calendar', 'trading'].includes(basis)) return null
  const move = s * iv / 100 * Math.sqrt(d / (basis === 'calendar' ? 365 : 252))
  return s - move > 0 && Number.isFinite(move) ? { move, lower: s - move, upper: s + move } : null
}

export function riskPlan(fields) {
  const keys = ['entry', 'stop', 'target', 'equity', 'riskPct', 'budget', 'cash', 'fx', 'feePct', 'taxPct', 'slipPct']
  const v = Object.fromEntries(keys.map((k) => [k, numeric(fields[k])]))
  if (Object.values(v).some((n) => n === null)) return { error: '모든 입력값을 채워 주세요. 비용이 없으면 0을 입력하세요.' }
  if (!(v.entry > v.stop && v.stop > 0 && v.target > v.entry)) return { error: '주식 롱 기준: 0 < 손절 < 진입 < 목표여야 합니다.' }
  if (!(v.equity > 0 && v.fx > 0 && v.budget >= 0 && v.cash >= 0 && v.riskPct > 0 && v.riskPct <= 100)) return { error: '자산·환율은 양수, 위험은 0 초과 100% 이하, 예산·현금은 0 이상이어야 합니다.' }
  if (['feePct', 'taxPct', 'slipPct'].some((k) => v[k] < 0 || v[k] >= 100)) return { error: '비용 비율은 0 이상 100% 미만이어야 합니다.' }
  if (v.feePct + v.taxPct + v.slipPct >= 100) return { error: '매도 비용의 합계는 100% 미만이어야 합니다.' }
  const buyCost = v.entry * (1 + (v.feePct + v.slipPct) / 100) * v.fx
  const exitStop = v.stop * (1 - (v.feePct + v.taxPct + v.slipPct) / 100) * v.fx
  const exitTarget = v.target * (1 - (v.feePct + v.taxPct + v.slipPct) / 100) * v.fx
  const unitRisk = buyCost - exitStop, unitReward = exitTarget - buyCost
  const riskBudget = v.equity * v.riskPct / 100
  const quantity = Math.floor(Math.min(riskBudget / unitRisk, v.budget / buyCost, v.cash / buyCost))
  const out = { quantity, riskBudget, unitRisk, unitReward, initialRisk: quantity * unitRisk, cost: quantity * buyCost, rr: unitReward / unitRisk }
  if (!Object.values(out).every(Number.isFinite) || !Number.isSafeInteger(quantity)) return { error: '입력값이 계산 범위를 벗어납니다.' }
  return out
}
