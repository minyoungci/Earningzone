import { useEffect, useRef, useState } from 'react'
import { createChart } from 'lightweight-charts'

import { normTime, sortDedupeByTime, candlesKey, overlaysKey, priceLinesKey } from '../lib/chartData'
import { chartThemeOptions, watchChartTheme } from '../lib/chartTheme'

/**
 * candles: [{time, open, high, low, close, volume}]
 * overlays: [{label, data:[{time,value}], color, width}]
 * priceLines: [{price, color, title}]
 */
export default function CandleChart({ candles = [], overlays = [], priceLines = [], markers = [], height = 420, showVolume = true }) {
  const ref = useRef(null)
  const chartRef = useRef(null)
  const csRef = useRef(null)
  const volRef = useRef(null)
  const overlaySeriesRef = useRef([]) // 생성한 라인 시리즈 추적(데이터 재주입 시 정리)
  const priceLineRef = useRef([]) // 생성한 priceLine 추적
  const fittedRef = useRef(false)
  const [renderError, setRenderError] = useState(false)

  // (a) 차트/시리즈 '생성' effect — height/showVolume 변화 시에만 재생성
  useEffect(() => {
    if (!ref.current) return
    const chart = createChart(ref.current, {
      height,
      autoSize: true,
      ...chartThemeOptions(),
      timeScale: { ...chartThemeOptions().timeScale, timeVisible: true, secondsVisible: false },
    })
    const stopWatchingTheme = watchChartTheme(chart)
    const cs = chart.addCandlestickSeries({
      upColor: '#fb7185', downColor: '#38bdf8', wickUpColor: '#fb7185', wickDownColor: '#38bdf8', borderVisible: false,
    })
    fittedRef.current = false
    chartRef.current = chart
    csRef.current = cs

    if (showVolume) {
      const vol = chart.addHistogramSeries({ priceScaleId: '', priceFormat: { type: 'volume' } })
      vol.priceScale().applyOptions({ scaleMargins: { top: 0.84, bottom: 0 } })
      volRef.current = vol
    } else {
      volRef.current = null
    }

    return () => {
      stopWatchingTheme()
      overlaySeriesRef.current = []
      priceLineRef.current = []
      chart.remove()
      chartRef.current = null
      csRef.current = null
      volRef.current = null
    }
  }, [height, showVolume])

  // (b) 데이터 주입 effect — candles 경량 키/overlays/priceLines 변화 시 setData
  useEffect(() => {
    const chart = chartRef.current
    const cs = csRef.current
    if (!chart || !cs) return

    setRenderError(false)
    try {
      const candleRows = sortDedupeByTime(
        candles.map((c) => ({ time: normTime(c.time), open: c.open, high: c.high, low: c.low, close: c.close }))
          .filter((c) => [c.open, c.high, c.low, c.close].every(Number.isFinite)),
      )
      cs.setData(candleRows)
      cs.setMarkers(markers.map((m) => ({ ...m, time: normTime(m.time) })).filter((m) => m.time != null)
        .sort((a, b) => (typeof a.time === 'number' ? a.time : Date.parse(a.time) / 1000) - (typeof b.time === 'number' ? b.time : Date.parse(b.time) / 1000)))

      if (volRef.current) {
        const volRows = sortDedupeByTime(
          candles.map((c) => ({
            time: normTime(c.time), value: Number.isFinite(c.volume) ? Math.max(0, c.volume) : 0,
            color: c.close >= c.open ? 'rgba(251,113,133,0.35)' : 'rgba(56,189,248,0.35)',
          })),
        )
        volRef.current.setData(volRows)
      }

      // Keep overlay series and price lines alive during polling updates.
      while (overlaySeriesRef.current.length > overlays.length) {
        chart.removeSeries(overlaySeriesRef.current.pop())
      }
      overlays.forEach((o, i) => {
        const options = { color: o.color || '#fbbf24', lineWidth: o.width || 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }
        const line = overlaySeriesRef.current[i] || chart.addLineSeries(options)
        line.applyOptions(options)
        line.setData(sortDedupeByTime((o.data || []).filter((p) => Number.isFinite(p.value))))
        overlaySeriesRef.current[i] = line
      })
      const validPriceLines = priceLines.filter((pl) => Number.isFinite(pl.price))
      while (priceLineRef.current.length > validPriceLines.length) {
        cs.removePriceLine(priceLineRef.current.pop())
      }
      validPriceLines.forEach((pl, i) => {
        const options = { price: pl.price, color: pl.color || '#a78bfa', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: pl.title || '' }
        const line = priceLineRef.current[i] || cs.createPriceLine(options)
        line.applyOptions(options)
        priceLineRef.current[i] = line
      })
      if (candleRows.length && !fittedRef.current) {
        chart.timeScale().fitContent()
        fittedRef.current = true
      } else if (!candleRows.length) {
        fittedRef.current = false
      }
    } catch (e) {
      // setData 가 throw 해도 차트영역 전체가 깨지지 않게 폴백 처리
      console.error('CandleChart setData 실패:', e)
      setRenderError(true)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candlesKey(candles), overlaysKey(overlays), priceLinesKey(priceLines), JSON.stringify(markers), height, showVolume])

  // 컨테이너(ref)는 candles 유무와 무관하게 '항상' 마운트한다.
  // 빈 candles 로 early-return 하면 생성 effect(deps [height, showVolume])가 ref=null 로
  // 한 번 실행되고 끝 — 이후 폴링으로 데이터가 와도 chartRef 가 null 이라 영원히 차트가 안 뜬다.
  // '데이터 없음'/에러 문구는 오버레이로 표시.
  return (
    <div style={{ position: 'relative', width: '100%', height }}>
      <div ref={ref} style={{ width: '100%', height }} />
      {!candles.length && (
        <div className="absolute inset-0 flex items-center justify-center text-slate-500 text-sm">
          차트 데이터 없음
        </div>
      )}
      {renderError && (
        <div className="absolute inset-0 flex items-center justify-center text-slate-500 text-sm">
          차트를 표시할 수 없습니다
        </div>
      )}
    </div>
  )
}
