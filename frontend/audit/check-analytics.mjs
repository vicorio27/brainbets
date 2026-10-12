// Checks the "mercado más acertado por día" column and the market filter in Analytics.
import { chromium } from 'playwright'

const BASE = process.env.AUDIT_BASE_URL || 'http://localhost:80'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
const errors = []
page.on('pageerror', (e) => errors.push(e.message))
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))

await page.goto(BASE + '/analytics', { waitUntil: 'networkidle' })
await page.waitForSelector('tbody tr')

const headers = await page.$$eval('thead th', (ths) => ths.map((t) => t.textContent.trim()))
const firstRow = await page.$eval('tbody tr', (tr) => tr.innerText.replace(/\s+/g, ' '))
const chips = await page.$$eval('p button', (bs) => bs.map((b) => b.innerText.replace(/\s+/g, ' ')))
console.log('columnas:', headers.join(' | '))
console.log('primera fila:', firstRow)
console.log('días como mejor:', chips.join(' · '))

await page.click('tbody tr')
const detail = await page.$eval('tbody tr.bg-slate-50', (tr) => tr.innerText.replace(/\s+/g, ' '))
console.log('detalle del día:', detail)

const options = await page.$$eval('select[aria-label="Mercado"] option', (os) => os.map((o) => o.value))
await page.selectOption('select[aria-label="Mercado"]', options[1])
const filteredHeaders = await page.$$eval('thead th', (ths) => ths.map((t) => t.textContent.trim()))
const filteredRow = await page.$eval('tbody tr', (tr) => tr.innerText.replace(/\s+/g, ' '))
const total = await page.$eval('tfoot tr', (tr) => tr.innerText.replace(/\s+/g, ' '))
console.log('filtrado por', options[1], '→ columnas:', filteredHeaders.join(' | '))
console.log('primera fila:', filteredRow)
console.log('total:', total)
console.log('errores de consola:', errors.length ? errors : 'ninguno')

await browser.close()
