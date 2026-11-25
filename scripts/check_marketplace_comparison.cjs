const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { chromium, webkit } = require('playwright');

const categoryIds = (process.env.MARKETPLACE_QA_CATEGORIES || 'laundry,softener').split(',');
const requireComparison = process.env.MARKETPLACE_QA_REQUIRED === '1';
const VC_HOST = 'ck.jp.ap.valuecommerce.com';
const prefix = '/daily-cost-jp/';

async function localSite(root) {
  const server = http.createServer((request, response) => {
    let relative = new URL(request.url, 'http://localhost').pathname.slice(prefix.length);
    if (!relative || relative.endsWith('/')) relative += 'index.html';
    const file = path.resolve(root, relative);
    if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
      response.writeHead(404).end();
      return;
    }
    response.setHeader('Content-Type', {
      '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css',
      '.json': 'application/json', '.svg': 'image/svg+xml', '.webp': 'image/webp',
    }[path.extname(file)] || 'application/octet-stream');
    response.end(fs.readFileSync(file));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  return { base: `http://127.0.0.1:${server.address().port}${prefix}`, server };
}

function yen(text) {
  assert.match(text, /^¥[\d,]+$/, 'money label must show yen');
  return Number(text.slice(1).replaceAll(',', ''));
}

async function checkOffer(card, marketplace, group, catalog) {
  const link = card.locator('a.marketplace-buy');
  assert.equal(await link.count(), 1);
  assert.equal(await link.getAttribute('data-marketplace'), marketplace);
  assert.equal(await link.getAttribute('target'), '_blank');
  const rel = (await link.getAttribute('rel')).split(' ');
  assert(['sponsored', 'noopener', 'nofollow'].every(value => rel.includes(value)));
  const box = await link.boundingBox();
  assert(box && box.height >= 44 && box.width >= 44, 'purchase target size');
  const url = new URL(await link.getAttribute('href'));
  const item = await link.getAttribute('data-marketplace-item');
  assert.equal(url.protocol, 'https:');
  assert(!url.username && !url.password && !url.port, 'canonical affiliate host');
  const values = await card.locator('dd').allTextContents();
  const price = yen(values[0]);
  if (marketplace === 'rakuten') {
    assert.equal(url.hostname, 'hb.afl.rakuten.co.jp');
    const match = catalog.find(entry => entry.item_code === item && entry.url === url.href);
    assert(match, 'Rakuten link must be an approved catalogue offer');
    assert.equal(price, match.price);
    assert(match.name.includes(group.jan), 'Rakuten JAN evidence in published catalogue');
  } else {
    assert.equal(url.hostname, VC_HOST);
    assert.equal(url.pathname, '/servlet/referral');
    for (const value of ['sid', 'pid']) assert(/^\d+$/.test(url.searchParams.get(value)));
    const target = new URL(url.searchParams.get('vc_url'));
    assert.equal(target.protocol, 'https:');
    if (target.hostname === 'store.shopping.yahoo.co.jp') {
      const store = target.pathname.match(/^\/([\w-]+)\/([\w.-]+)\.html$/);
      assert(store && item === `${store[1]}_${store[2]}`, 'Yahoo product target must match seller and item');
    } else {
      const store = target.pathname.match(/^\/store\/h-lohaco\/item\/([\w-]+)\/?$/i);
      assert(target.hostname === 'lohaco.yahoo.co.jp' && store
        && ['rd-lohaco', 'h-lohaco'].some(seller => item.toLowerCase() === `${seller}_${store[1].toLowerCase()}`),
      'LOHACO product target must match item');
    }
  }
  if (values[1] === '要確認') {
    assert.deepEqual(values.slice(2), ['要確認', '—']);
    return null;
  }
  const total = yen(values[2]);
  assert.equal(total, price + yen(values[1]), 'purchase total');
  assert(values[3].endsWith(` / 100${group.unit}`));
  const unitPrice = Number(values[3].split(' ')[0].slice(1).replaceAll(',', ''));
  assert(Math.abs(unitPrice - total * 100 / (group.pack * group.amount)) <= 0.051, 'unit price');
  return total;
}

async function verifyPage(page, base, width, category, catalog) {
  const origin = new URL(base).origin;
  await page.context().route('**/*', route =>
    new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
  const pageErrors = [];
  page.on('pageerror', () => pageErrors.push('page exception'));
  const res = await page.goto(base + `categories/${category}/?test=1`, { waitUntil: 'domcontentloaded' });
  assert.equal(res.status(), 200);
  assert.equal(await page.locator('h1').count(), 1);
  const section = page.locator('#marketplace-comparison');
  if (!await section.count()) {
    assert(!requireComparison, `${category} has no comparable pair in the generated page`);
    return { status: 'not_displayed' };
  }
  assert.equal(await section.count(), 1);
  assert(await section.isVisible());
  const credit = page.locator('footer a[href="https://developer.yahoo.co.jp/sitemap/"]');
  assert.equal(await credit.textContent(), 'Webサービス by Yahoo! JAPAN');
  assert(await credit.isVisible());
  const articles = await section.locator('.marketplace-product').all();
  const identities = new Set();
  let comparable = 0;
  for (const article of articles) {
    const group = await article.evaluate(el => ({
      jan: el.dataset.jan, pack: Number(el.dataset.pack),
      amount: Number(el.dataset.unitAmount), unit: el.dataset.unit,
    }));
    assert(/^\d{13}$/.test(group.jan) && group.amount > 0 && group.pack > 0 && /^(g|ml)$/.test(group.unit));
    const key = `${group.jan}/${group.pack}`;
    assert(!identities.has(key), 'duplicate package');
    identities.add(key);
    const cards = await article.locator('.marketplace-offer').all();
    assert.equal(cards.length, 2);
    const rakuten = await checkOffer(cards[0], 'rakuten', group, catalog);
    const yahoo = await checkOffer(cards[1], 'yahoo', group, catalog);
    const note = await article.locator('p > strong').textContent();
    if (rakuten === null || yahoo === null) {
      assert.match(note, /送料が未確定/);
    } else {
      comparable++;
      if (rakuten === yahoo) assert.match(note, /同じ/);
      else {
        assert(note.includes(rakuten < yahoo ? '楽天市場' : 'Yahoo!ショッピング'));
        assert(note.includes('¥' + Math.abs(rakuten - yahoo).toLocaleString('en-US')));
      }
    }
  }
  assert(comparable > 0, 'display requires a pair with confirmed purchase totals');
  assert(await section.evaluate(el => el.scrollWidth <= el.clientWidth + 1), 'comparison overflow');
  const cards = await articles[0].locator('.marketplace-offer').all();
  const cardBoxes = await Promise.all(cards.map(card => card.boundingBox()));
  assert(width <= 540 ? cardBoxes[1].y > cardBoxes[0].y : cardBoxes[1].x > cardBoxes[0].x,
    'stack on mobile and compare side by side on desktop');
  for (const [index, marketplace] of ['rakuten', 'yahoo'].entries()) {
    const link = cards[index].locator('a');
    await link.evaluate(el => el.addEventListener('click', event => event.preventDefault(), { once: true }));
    await link.click();
    const events = await page.evaluate(() => window.dataLayer.filter(row => row[0] === 'event')
      .map(row => [row[1], row[2]]));
    const marketEvents = events.filter(event => event[0] === `marketplace_${marketplace}_click`);
    assert.equal(marketEvents.length, 1);
    const info = marketEvents[0][1];
    assert.equal(info.category_id, category);
    assert.equal(info.operator_test, '1');
    assert.equal(info.conversion_source, 'same_product_compare');
    assert.equal(info.link_url, undefined);
    assert.equal(events.filter(event => event[0] === 'affiliate_click').length, 1,
      'Yahoo event must stay out of the existing Rakuten report');
  }
  assert.deepEqual(pageErrors, []);
  return { status: 'pass', pairs: articles.length, comparable };
}

async function main() {
  const local = process.env.MARKETPLACE_QA_BASE_URL ? null
    : await localSite(path.resolve(process.env.MARKETPLACE_QA_SITE_DIR || 'site'));
  const base = process.env.MARKETPLACE_QA_BASE_URL || local.base;
  try {
    const response = await fetch(base + 'data.json');
    assert.equal(response.status, 200);
    const { categories } = await response.json();
    for (const engine of [chromium, webkit]) {
      const browser = await engine.launch({ headless: true });
      try {
        for (const width of [320, 390, 1440]) {
          for (const category of categoryIds) {
            const page = await browser.newPage({ viewport: { width, height: 900 } });
            try {
              const result = await verifyPage(page, base, width, category, categories[category].items);
              console.log(JSON.stringify({ browser: engine.name(), width, category, ...result }));
            } finally {
              await page.close();
            }
          }
        }
      } finally {
        await browser.close();
      }
    }
  } finally {
    local?.server.close();
  }
}

main().catch(error => {
  // Assertions on full URLs could echo affiliate identifiers. Only surface
  // the fixed assertion message, and omit browser request logs and URLs.
  const message = error.code === 'ERR_ASSERTION' && !error.generatedMessage
    ? error.message : 'marketplace browser verification failed';
  console.error(message, error.stack?.match(/check_marketplace_comparison\.cjs:\d+:\d+/)?.[0] || '');
  process.exitCode = 1;
});
