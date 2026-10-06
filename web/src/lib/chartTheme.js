export function chartThemeOptions() {
  const style = getComputedStyle(document.documentElement)
  const color = (key, fallback) => style.getPropertyValue(key).trim() || fallback
  const text = color('--chart-text', '#626b78')
  const grid = color('--chart-grid', '#eef0f4')
  const border = color('--line', '#e8eaee')
  const crosshair = color('--chart-crosshair', '#b0a5ca')
  return {
    layout: { background: { color: 'transparent' }, textColor: text, fontFamily: 'Pretendard, system-ui, sans-serif' },
    grid: { vertLines: { color: grid }, horzLines: { color: grid } },
    rightPriceScale: { borderColor: border },
    timeScale: { borderColor: border },
    crosshair: { mode: 1, vertLine: { color: crosshair }, horzLine: { color: crosshair } },
  }
}

export function watchChartTheme(chart) {
  const observer = new MutationObserver(() => chart.applyOptions(chartThemeOptions()))
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
  return () => observer.disconnect()
}
