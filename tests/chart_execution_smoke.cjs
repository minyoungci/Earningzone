const { chromium } = require('../.ds-sync/node_modules/playwright')
const fs = require('fs')
const path = require('path')
const base = process.env.TOSSBOT_TEST_URL || 'http://127.0.0.1:8765'
const out = path.resolve(__dirname, '../.tmp/interpretive_20261004')
const assert = (ok, message) => { if (!ok) throw new Error(message) }

async function main() {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' })
  const results = []
  try {
    for (const width of [1440, 390, 320]) {
      const context = await browser.newContext({ viewport: { width, height: 1000 }, reducedMotion: 'reduce' })
      const errors = [], writes = []
      await context.route('**/*', route => {
        const request = route.request()
        if (request.method() !== 'GET') writes.push(request.url())
        return request.url().startsWith(base) ? route.continue() : route.abort()
      })
      const page = await context.newPage()
      page.on('pageerror', error => errors.push(error.message))
      page.on('console', m => { if (m.type() === 'error' && !m.text().includes('ERR_FAILED')) errors.push(m.text()) })
      await page.goto(base + '/symbol/005930', { waitUntil: 'networkidle' })
      await page.getByRole('heading', { name: '자동매매 · 차트 확인 전략', exact: true }).waitFor()
      const timing = await (await page.request.get(base + '/api/chart-timing/005930')).json()
      assert(timing.version === 'chart-confirmed-v1', 'Timing API missing')
      assert(writes.length === 0, 'Viewing a chart issued writes')
      await page.getByRole('link', { name: '모의 자동매매 설정 →', exact: true }).click()
      await page.getByLabel('진입 전략', { exact: true }).waitFor()
      assert(await page.getByLabel('진입 전략', { exact: true }).inputValue() === 'chart_confirmed', 'Link did not select chart policy')
      await page.getByLabel('1종목 예상 손절 위험 (%)', { exact: true }).fill('0.4')
      await page.getByLabel('최소 순손익비', { exact: true }).fill('2')
      assert(!await page.evaluate(() => document.documentElement.scrollWidth > innerWidth+1), `Overflow ${width}`)
      await page.screenshot({ path: path.join(out, `strategy-${width}.png`), fullPage: true })
      const startResponse = page.waitForResponse(r => r.url().endsWith('/api/autopilot/start') && r.request().method() === 'POST')
      await page.getByRole('button', { name: '▶ 시작', exact: true }).click()
      const response = await startResponse
      assert(response.ok(), 'Start rejected')
      const settings = (await response.json()).settings
      assert(settings.strategy === 'chart_confirmed' && settings.riskPct === .4 && settings.minRR === 2, 'Policy settings lost')
      await page.getByRole('button', { name: '■ 중지', exact: true }).waitFor()
      const stopResponse = page.waitForResponse(r => r.url().endsWith('/api/autopilot/stop') && r.request().method() === 'POST')
      await page.getByRole('button', { name: '■ 중지', exact: true }).click()
      assert((await stopResponse).ok(), 'Stop rejected')
      await page.getByLabel('진입 전략', { exact: true }).waitFor()
      assert(errors.length === 0, JSON.stringify(errors))
      assert(writes.every(url => /\/api\/autopilot\/(start|stop)$/.test(url)), 'Unexpected mutation')
      results.push({ width, timing: timing.phase, settings, errors, startStop: true, overflow: false })
      await context.close()
    }
    fs.writeFileSync(path.join(out, 'chart-browser-results.json'), JSON.stringify(results, null, 2))
    console.log(JSON.stringify({ passed: true, widths: results.length, errors: 0, isolatedStartStop: true }))
  } finally { await browser.close() }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
