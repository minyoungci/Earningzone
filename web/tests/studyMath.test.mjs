import test from 'node:test'
import assert from 'node:assert/strict'
import { expectedMove, fibonacci, measuredTarget, numeric, riskPlan } from '../src/lib/studyMath.js'

test('synthetic geometry examples and chronological retracement direction', () => {
  assert.equal(measuredTarget(120,100,122).target,142)
  assert.ok(Math.abs(measuredTarget(125.5,105.25,104,'down').target-83.75)<1e-8)
  const up = fibonacci(100,200)
  assert.equal(up[0].price,200); assert.equal(up.at(-1).price,100)
  assert.equal(up.find(f=>f.ratio===.5).price,150)
  assert.equal(fibonacci(200,100).find(f=>f.ratio===.382).price,138.2)
  assert.deepEqual(fibonacci('',100),[])
  assert.equal(measuredTarget(100,110,120),null)
})

test('EM uses percentage IV and explicit calendar/trading day basis', () => {
  assert.equal(expectedMove(100,20,365).move,20)
  assert.equal(expectedMove(100,20,252,'trading').move,20)
  assert.ok(Math.abs(expectedMove(100,20,5).move-100*.2*Math.sqrt(5/365))<1e-10)
  assert.equal(expectedMove(100,'',5),null)
  assert.equal(expectedMove(100,-20,5),null)
  assert.equal(numeric(''),null); assert.equal(numeric(Infinity),null)
})

const base = { entry:100,stop:90,target:120,equity:10000,riskPct:1,budget:10000,cash:10000,fx:1,feePct:0,taxPct:0,slipPct:0 }
test('risk sizing independently caps risk, budget, cash; includes both sides costs and FX', () => {
  assert.deepEqual(riskPlan(base),{quantity:10,riskBudget:100,unitRisk:10,unitReward:20,initialRisk:100,cost:1000,rr:2})
  assert.equal(riskPlan({...base,budget:450}).quantity,4)
  assert.equal(riskPlan({...base,cash:230}).quantity,2)
  assert.equal(riskPlan({...base,fx:100}).quantity,0)
  const costs = riskPlan({...base,feePct:1,taxPct:1,slipPct:1})
  // Entry 102, stop proceeds 87.3, target proceeds 116.4.
  assert.ok(Math.abs(costs.unitRisk-14.7)<1e-9)
  assert.ok(Math.abs(costs.unitReward-14.4)<1e-9)
  assert.equal(costs.quantity,6)
  assert.equal(riskPlan({...base,cash:0}).quantity,0)
  for (const patch of [{stop:100},{target:90},{fx:''},{equity:-1},{feePct:100},{riskPct:0}]) assert.ok(riskPlan({...base,...patch}).error)
})
