export function normTime(time) {
  if (typeof time === 'number') return Number.isFinite(time) && time >= 0 ? time : null
  if (typeof time !== 'string') return null
  if (/^\d{4}-\d{2}-\d{2}$/.test(time)) {
    const date = new Date(`${time}T00:00:00Z`)
    return Number.isFinite(+date) && date.toISOString().slice(0, 10) === time ? time : null
  }
  const stamp = Date.parse(time)
  return Number.isFinite(stamp) ? Math.floor(stamp / 1000) : null
}

export function sortDedupeByTime(rows) {
  const unique = new Map()
  for (const row of rows) {
    const time = normTime(row.time)
    if (time == null) continue
    const key = typeof time === 'number' ? time : Date.parse(`${time}T00:00:00Z`) / 1000
    unique.set(key, { ...row, time })
  }
  return [...unique].sort(([a], [b]) => a - b).map(([, row]) => row)
}

export const candlesKey = (candles) => JSON.stringify(candles.map(
  (c) => [c.time, c.open, c.high, c.low, c.close, c.volume],
))
export const overlaysKey = (overlays) => JSON.stringify(overlays.map(
  (o) => [o.color, o.width, (o.data || []).map((p) => [p.time, p.value])],
))
export const priceLinesKey = (lines) => JSON.stringify(lines.map((p) => [p.price, p.title, p.color]))
