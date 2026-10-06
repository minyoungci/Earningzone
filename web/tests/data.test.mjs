import test from 'node:test'
import assert from 'node:assert/strict'
import { candlesKey, sortDedupeByTime, normTime } from '../src/lib/chartData.js'
import { fetchJson } from '../src/lib/http.js'

test('daily bars sort chronologically, retain the last duplicate, and skip invalid dates', () => {
  const rows = sortDedupeByTime([{ time: '2026-01-03', value: 3 }, { time: 'invalid', value: 0 }, { time: '2026-01-01', value: 1 }, { time: '2026-01-01', value: 2 }])
  assert.deepEqual(rows, [{ time: '2026-01-01', value: 2 }, { time: '2026-01-03', value: 3 }])
  assert.equal(normTime('2026-02-30'), null)
})

test('intraday timestamps normalize consistently across time zones', () => {
  assert.equal(normTime('2026-01-01T09:00:00+09:00'), normTime('2026-01-01T00:00:00Z'))
})

test('historical corrections and high/low updates invalidate a chart', () => {
  const first = [{ time: '2026-01-01', open: 10, high: 12, low: 8, close: 11, volume: 1 }]
  const corrected = [{ ...first[0], high: 14 }]
  assert.notEqual(candlesKey(first), candlesKey(corrected))
})

test('concurrent GETs share one network request', async () => {
  let calls = 0
  globalThis.fetch = async () => { calls++; return new Response(JSON.stringify({ ok: true })) }
  const responses = await Promise.all(Array.from({ length: 8 }, () => fetchJson('/api/dedup-test')))
  assert.equal(calls, 1)
  assert.equal(responses.length, 8)
})

test('write requests are never deduplicated', async () => {
  let calls = 0
  globalThis.fetch = async () => { calls++; return new Response('{}') }
  await Promise.all([fetchJson('/api/write-test', { method: 'POST' }), fetchJson('/api/write-test', { method: 'POST' })])
  assert.equal(calls, 2)
})

test('validation details are presented as a readable error', async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({ detail: [{ msg: 'invalid' }] }), { status: 422 })
  await assert.rejects(fetchJson('/api/validation-test'), /입력값/)
})

test('requests have a bounded wait time', async () => {
  globalThis.fetch = (_url, { signal }) => new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(new Error('aborted'))))
  await assert.rejects(fetchJson('/api/timeout-test', { timeoutMs: 5 }), /대기 시간/)
})

test('a write invalidates a read in progress without deleting its replacement', async () => {
  let resolveOld
  let calls = 0
  globalThis.fetch = async (_url, init) => {
    if (init.method === 'POST') return new Response('{}')
    calls++
    if (calls === 1) return new Promise((resolve) => { resolveOld = resolve })
    return new Response('{"version":2}')
  }
  const old = fetchJson('/api/state-test')
  await fetchJson('/api/state-test', { method: 'POST' })
  const fresh = await fetchJson('/api/state-test')
  resolveOld(new Response('{"version":1}'))
  assert.equal((await old).version, 1)
  assert.equal(fresh.version, 2)
  assert.equal(calls, 2)
})
