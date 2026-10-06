const { chromium } = require('../.ds-sync/node_modules/playwright')
const fs = require('fs')
const path = require('path')

const base = process.env.TOSSBOT_TEST_URL || 'http://127.0.0.1:8765'
const out = process.env.TOSSBOT_TEST_OUTPUT || path.resolve(__dirname, '../.tmp/maintenance_20261003')

async function main() {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' })
  const results = []
  try {
    for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
      const context = await browser.newContext({ viewport })
      // Block fonts, CDNs, and any other external traffic during offline UI checks.
      await context.route('**/*', route => route.request().url().startsWith(base) ? route.continue() : route.abort())
      const page = await context.newPage()
      const errors = []
      page.on('pageerror', e => errors.push(e.message))
      page.on('console', m => { if (m.type() === 'error' && !m.text().includes('ERR_FAILED')) errors.push(m.text()) })
      for (const route of ['/', '/market', '/intraday', '/quant', '/sim', '/autopilot', '/backtest', '/portfolio', '/symbol/005930']) {
        errors.length = 0
        await page.goto(base + route, { waitUntil: 'networkidle' })
        await page.locator('main').waitFor()
        await page.waitForFunction(() => !document.querySelector('main')?.innerText.includes('페이지 불러오는 중'))
        const body = await page.locator('main').innerText()
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)
        const failed = body.includes('문제가 발생했습니다') || body.includes('차트를 표시할 수 없습니다')
        results.push({ route, viewport: viewport.width, errors: [...errors], overflow, failed })
        if (errors.length || overflow || failed) throw new Error(JSON.stringify(results.at(-1)))
      }
      await page.screenshot({ path: path.join(out, `ui-${viewport.width}.png`), fullPage: true })
      await context.close()
    }
    // Verify account switching and manual trade workflow against the isolated server.
    const page = await browser.newPage()
    await page.route('**/*', route => route.request().url().startsWith(base) ? route.continue() : route.abort())
    await page.goto(base + '/sim', { waitUntil: 'networkidle' })
    const workflow = await page.evaluate(async () => {
      const call = async (url, body) => {
        const r = await fetch(url, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined)
        if (!r.ok) throw new Error(`${url}: ${r.status}`)
        return r.json()
      }
      const created = await call('/api/sim/accounts', { name: 'Browser QA', cash: 1000000 })
      await call('/api/sim/accounts/select', { id: created.newId })
      await call('/api/sim/order', { symbol: '005930', side: 'BUY', qty: 1 })
      const bought = await call('/api/sim/state')
      await call('/api/sim/order', { symbol: '005930', side: 'SELL', qty: 1 })
      const journal = await call('/api/journal')
      await call('/api/sim/accounts/select', { id: 'default' })
      const original = await call('/api/sim/state')
      const deleted = await fetch('/api/sim/accounts/' + created.newId, { method: 'DELETE' })
      if (!deleted.ok) throw new Error('Could not remove the temporary workflow account')
      return { bought: bought.positions.length, trades: journal.trades, defaultPositions: original.positions.length }
    })
    if (workflow.bought !== 1 || workflow.trades !== 1 || workflow.defaultPositions !== 0) throw new Error(JSON.stringify(workflow))
    results.push({ workflow, passed: true })

    // Submit through the real form and check that the ledger and displayed history refresh.
    await page.reload({ waitUntil: 'networkidle' })
    await page.getByLabel('메모(근거) — 선택').fill('UI smoke BUY')
    await page.getByRole('button', { name: '매수', exact: true }).click()
    await page.getByText('매수 1주 체결 완료', { exact: true }).waitFor()
    await page.waitForFunction(() => document.querySelector('main').innerText.includes('UI smoke BUY'))
    const bought = await page.evaluate(async () => (await (await fetch('/api/sim/state')).json()).positions.length)
    if (bought !== 1) throw new Error('The buy form did not update the isolated ledger')
    await page.getByLabel('메모(근거) — 선택').fill('UI smoke SELL')
    await page.getByRole('button', { name: '매도', exact: true }).click()
    await page.getByText('매도 1주 체결 완료', { exact: true }).waitFor()
    await page.waitForFunction(() => document.querySelector('main').innerText.includes('UI smoke SELL'))
    const sold = await page.evaluate(async () => (await (await fetch('/api/sim/state')).json()).positions.length)
    if (sold !== 0) throw new Error('The sell form did not update the isolated ledger')
    results.push({ uiForm: { buy: true, sell: true, historyRefresh: true }, passed: true })
    fs.writeFileSync(path.join(out, 'browser-results.json'), JSON.stringify(results, null, 2))
    console.log(JSON.stringify({ pages: 18, errors: 0, workflow, uiForm: true, passed: true }))
  } finally { await browser.close() }
}
main().catch(error => { console.error(error.message); process.exitCode = 1 })
