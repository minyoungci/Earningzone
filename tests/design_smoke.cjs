const { chromium } = require('../.ds-sync/node_modules/playwright')
const fs = require('fs')
const path = require('path')
const base = 'http://127.0.0.1:8765'
const out = path.resolve(__dirname, '../.tmp/design_20261003')

async function main() {
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  const api = await browser.newContext()
  let accountId
  const results = []
  try {
    const response = await api.request.post(base + '/api/sim/accounts', { data: { name: 'Browser QA', cash: 1000000 } })
    if (!response.ok()) throw new Error('Could not create the temporary design account')
    accountId = (await response.json()).newId
    for (const width of [1440, 1024, 768, 390, 320]) {
      const context = await browser.newContext({ viewport: { width, height: 1000 }, reducedMotion: 'reduce' })
      await context.route('**/*', route => route.request().url().startsWith(base) ? route.continue() : route.abort())
      const page = await context.newPage()
      const errors = []
      page.on('pageerror', error => errors.push(error.message))
      await page.goto(base, { waitUntil: 'networkidle' })
      if (width === 1440) {
        await page.evaluate(() => fetch('/api/sim/accounts/select', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: 'default' }) }))
        await page.reload({ waitUntil: 'networkidle' })
      }
      await page.getByRole('heading', { name: '투자 현황', exact: true }).waitFor()
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)
      if (overflow || errors.length) throw new Error(JSON.stringify({ width, overflow, errors }))
      await page.getByRole('button', { name: '미국', exact: true }).click()
      await page.getByRole('link', { name: '애플', exact: true }).waitFor()
      await page.getByRole('button', { name: '국내', exact: true }).click()
      if (width < 768) {
        await page.locator('.mobile-more > summary').click()
        await page.locator('.mobile-menu-panel').getByRole('link', { name: '오토파일럿', exact: true }).click()
        await page.waitForURL(base + '/autopilot')
        if (await page.locator('.mobile-more').evaluate(el => el.open)) throw new Error('Mobile menu did not close after navigation')
        await page.goto(base, { waitUntil: 'networkidle' })
      }
      await page.locator('.settings-menu > summary').click()
      await page.getByRole('button', { name: '다크', exact: true }).click()
      await page.waitForFunction(() => document.documentElement.dataset.theme === 'wallet')
      await page.reload({ waitUntil: 'networkidle' })
      if (await page.locator('html').getAttribute('data-theme') !== 'wallet') throw new Error('Theme was not restored')
      await page.locator('.settings-menu > summary').click()
      await page.getByRole('button', { name: '라이트', exact: true }).click()
      await page.waitForFunction(() => document.documentElement.dataset.theme === 'clean')
      await page.locator('.settings-menu > summary').click()
      await page.screenshot({ path: path.join(out, `dashboard-${width}.png`), fullPage: true })
      if (width === 1440 || width === 390) await page.screenshot({ path: path.join(out, `preview-${width}.png`), fullPage: false })
      results.push({ width, overflow, errors, marketTabs: true, themePersistence: true, mobileNavigation: width < 768 })
      await context.close()
    }
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
    await context.route('**/*', route => route.request().url().startsWith(base) ? route.continue() : route.abort())
    const page = await context.newPage()
    const interactionErrors = []
    page.on('pageerror', error => interactionErrors.push(error.message))
    await page.goto(base, { waitUntil: 'networkidle' })
    await page.keyboard.press('Tab')
    if (await page.locator(':focus').innerText() !== '본문으로 이동') throw new Error('Skip link is not the first keyboard target')
    await page.keyboard.press('Enter')
    if (await page.locator(':focus').getAttribute('id') !== 'main-content') throw new Error('Skip link did not focus main')
    await page.getByRole('combobox', { name: '종목 이름 또는 코드 검색' }).fill('삼성전자')
    await page.getByRole('option').first().waitFor()
    await page.keyboard.press('Enter')
    await page.waitForURL(base + '/symbol/005930')
    await page.locator('canvas').first().waitFor()
    const canvasCount = await page.locator('canvas').count()
    await page.locator('.settings-menu > summary').click()
    await page.getByRole('button', { name: '다크', exact: true }).click()
    await page.waitForFunction(() => document.documentElement.dataset.theme === 'wallet')
    await page.getByRole('button', { name: '라이트', exact: true }).click()
    await page.waitForFunction(() => document.documentElement.dataset.theme === 'clean')
    if (await page.locator('canvas').count() !== canvasCount) throw new Error('Theme switching recreated the chart')
    if (interactionErrors.length) throw new Error(JSON.stringify(interactionErrors))
    results.push({ chartThemeSwitch: true, chartCanvasesPreserved: canvasCount })
    await page.goto(base, { waitUntil: 'networkidle' })
    await page.locator('.account-choice').filter({ hasText: 'Browser QA' }).first().click()
    await page.waitForFunction(() => document.querySelector('.overview-subtitle').innerText.includes('Browser QA'))
    const selected = await page.evaluate(async () => (await (await fetch('/api/sim/accounts')).json()).active)
    if (selected === 'default') throw new Error('Account selection was not persisted')
    await page.locator('.account-choice').filter({ hasText: '기본 계좌' }).click()
    await page.waitForFunction(() => !document.querySelector('.overview-subtitle').innerText.includes('Browser QA'))
    results.push({ keyboardSkip: true, keyboardSearch: true, accountSelection: true })
    const contrast = await page.evaluate(() => {
      const rgb = value => { const parts = value.match(/[\d.]+/g)?.map(Number) || []; return parts.length >= 3 ? [...parts.slice(0, 3), parts[3] ?? 1] : [0, 0, 0, 0] }
      const blend = (top, bottom) => top.slice(0, 3).map((channel, i) => channel * top[3] + bottom[i] * (1 - top[3]))
      const lum = value => value.map(channel => { const x = channel / 255; return x <= .04045 ? x / 12.92 : ((x + .055) / 1.055) ** 2.4 }).reduce((sum, channel, i) => sum + channel * [.2126, .7152, .0722][i], 0)
      const failures = []
      let count = 0
      for (const element of document.querySelectorAll('.dashboard-layout *, .app-sidebar *')) {
        const text = [...element.childNodes].filter(node => node.nodeType === Node.TEXT_NODE).map(node => node.textContent.trim()).join(' ')
        if (!text || !element.getClientRects().length || element.closest('svg')) continue
        const style = getComputedStyle(element)
        const layers = []
        for (let node = element; node; node = node.parentElement) layers.push(rgb(getComputedStyle(node).backgroundColor))
        let background = [255, 255, 255]
        for (const layer of layers.reverse()) background = blend(layer, background)
        const foreground = blend(rgb(style.color), background)
        const a = lum(foreground), b = lum(background)
        const ratio = (Math.max(a, b) + .05) / (Math.min(a, b) + .05)
        const large = parseFloat(style.fontSize) >= 24 || (parseFloat(style.fontSize) >= 18.66 && parseInt(style.fontWeight) >= 700)
        count++
        if (ratio < (large ? 3 : 4.5)) failures.push({ text: text.slice(0, 50), ratio: Number(ratio.toFixed(2)), color: style.color })
      }
      return { count, failures }
    })
    if (contrast.failures.length) throw new Error('Contrast: ' + JSON.stringify(contrast))
    results.push({ textContrast: contrast })
    await page.route('**/api/sim/state', route => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: '검사용 연결 오류' }) }))
    await page.reload({ waitUntil: 'networkidle' })
    await page.getByRole('alert').filter({ hasText: '검사용 연결 오류' }).first().waitFor()
    results.push({ accountErrorVisible: true })
    await context.close()
    fs.writeFileSync(path.join(out, 'design-results.json'), JSON.stringify(results, null, 2))
    console.log(JSON.stringify({ responsiveWidths: 5, results, passed: true }))
  } finally {
    try {
      if (accountId) {
        const selected = await api.request.post(base + '/api/sim/accounts/select', { data: { id: 'default' } })
        if (!selected.ok()) throw new Error('Could not restore the default fixture account')
        const deleted = await api.request.delete(base + '/api/sim/accounts/' + accountId)
        if (!deleted.ok()) throw new Error('Could not remove the temporary design account')
      }
    } finally { await browser.close() }
  }
}
main().catch(error => { console.error(error.stack); process.exitCode = 1 })
