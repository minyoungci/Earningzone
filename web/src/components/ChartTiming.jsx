import { Link } from 'react-router-dom'
import { getChartTiming, useApi } from '../api'
import { money } from '../lib/format'
import GlassCard from './ui/GlassCard'

const names = { waiting: '조건 확인 대기', watching: '돌파 대기', breakout: '리테스트 대기', retest: '후속 종가 대기', confirmed: '차트 조건 확인', filtered: '추가 조건 미달', invalidated: '무효화', expired: '대기 만료', blocked: '진입 보류' }

export default function ChartTiming({ symbol, currency }) {
  const { data, err, loading, reload } = useApi(() => getChartTiming(symbol), [symbol])
  return <GlassCard>
    <div className="flex justify-between gap-3 flex-wrap mb-3">
      <h2 className="font-bold">자동매매 · 차트 확인 전략</h2>
      <Link to="/autopilot?strategy=chart_confirmed" className="study-link">모의 자동매매 설정 →</Link>
    </div>
    {err ? <div role="alert" className="text-sm text-amber-300">분석 실패: {err.message} <button onClick={reload}>다시 시도</button></div> : <>
      <p className="text-sm font-semibold">{loading && !data ? '조건 분석 중…' : names[data?.phase] || '조건 확인 대기'}</p>
      <p className="text-sm text-slate-400 mt-1">{data?.reason}</p>
      {data?.plan && <div className="flex flex-wrap gap-x-5 gap-y-2 mt-3 text-sm stat-num">
        <span>확인 {data.plan.confirmedAt}</span>
        <span>손절 {money(data.plan.stop, currency)}</span>
        <span>측정 목표 {money(data.plan.target, currency)}</span>
        <span>확인봉 거래량 {data.plan.rvol.toFixed(2)}배</span>
      </div>}
    </>}
    <p className="text-xs text-slate-500 mt-3">완성 일봉의 돌파·리테스트·후속 종가, EMA20/50, 거래량으로 판단합니다. 실제 진입은 현재가·비용 반영 순손익비·계좌 위험 한도를 다시 확인합니다. 모의 전용 실험 전략이며 수익 성과는 검증 전입니다.</p>
  </GlassCard>
}
