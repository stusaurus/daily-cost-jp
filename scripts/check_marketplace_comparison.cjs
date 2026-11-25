const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { chromium, webkit } = require('playwright');

const requestedCategories = process.env.MARKETPLACE_QA_CATEGORIES?.split(',');
const requireComparison = process.env.MARKETPLACE_QA_REQUIRED === '1';
const VC_HOST = 'ck.jp.ap.valuecommerce.com';
const prefix = '/daily-cost-jp/';
const comparisonFragment = '#marketplace-comparison';
const testEventKey = 'marketplace_navigation_test_events';

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
    const evidence = [
      match.name.normalize('NFKC'),
      new URL(url.searchParams.get('pc')).pathname,
    ].flatMap(value => value.match(/(?<!\d)\d{13}(?!\d)/g) || []);
    const validJans = evidence.filter(code => [...code].reverse()
      .reduce((sum, digit, index) => sum + Number(digit) * (index % 2 ? 3 : 1), 0) % 10 === 0);
    assert(validJans.every(jan => jan === group.jan), 'Rakuten JAN evidence cannot conflict');
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
  assert(values[3].endsWith(` / ${group.priceUnit}`));
  const unitPrice = Number(values[3].split(' ')[0].slice(1).replaceAll(',', ''));
  assert(Math.abs(unitPrice - total * group.scale / (group.pack * group.amount * group.factor)) <= 0.051, 'unit price');
  return total;
}

async function followComparisonLink(page, link, category, entry) {
  const box = await link.boundingBox();
  assert(box && box.height >= 44 && box.width >= 44, 'comparison navigation target size');
  await link.evaluate((el, key) => {
    el.addEventListener('click', () => {
      const events = window.dataLayer.filter(row => row[0] === 'event').map(row => [row[1], row[2]]);
      sessionStorage.setItem(key, JSON.stringify(events));
    }, { once: true });
  }, testEventKey);
  const pathname = prefix + 'categories/' + category + '/';
  await Promise.all([
    page.waitForURL(url => url.pathname === pathname && url.hash === comparisonFragment),
    link.click()
  ]);
  const events = await page.evaluate(key => JSON.parse(sessionStorage.getItem(key)), testEventKey);
  const clicks = events.filter(row => row[0] === 'marketplace_compare_click');
  assert.equal(clicks.length, 1, 'one event for a comparison navigation click');
  assert.equal(clicks[0][1].category_id, category);
  assert.equal(clicks[0][1].entry_point, entry);
  assert.equal(clicks[0][1].operator_test, '1');
  assert(!events.some(row => row[0] === 'affiliate_click'), 'navigation must not count as a purchase click');
  await page.waitForFunction(() => {
    const title = document.getElementById('marketplace-title');
    if (!title) return false;
    const bounds = title.getBoundingClientRect();
    return bounds.top >= 0 && bounds.bottom <= window.innerHeight;
  }, null, { timeout: 3500 });
}

async function verifyDirectory(page, base, available, entry) {
  const origin = new URL(base).origin;
  await page.context().route('**/*', route =>
    new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
  const path = entry === 'home' ? '' : 'categories/';
  const response = await page.goto(base + path + '?test=1', {waitUntil: 'domcontentloaded'});
  assert.equal(response.status(), 200);
  const nav = page.locator('#marketplace-navigation');
  const links = nav.locator('a[data-marketplace-entry]');
  const linked = await links.evaluateAll(items => items.map(link => link.dataset.categoryId));
  assert.equal(await nav.count(), linked.length ? 1 : 0);
  const scoped = requestedCategories
    ? linked.filter(id => requestedCategories.includes(id))
    : linked;
  assert.deepEqual(scoped.sort(), available.slice().sort());
  for (const link of await links.all()) {
    const id = await link.getAttribute('data-category-id');
    const url = new URL(await link.getAttribute('href'), base);
    assert.equal(url.origin, origin);
    assert.equal(url.pathname, prefix + 'categories/' + id + '/');
    assert.equal(url.hash, comparisonFragment);
    assert.equal(await link.getAttribute('data-marketplace-entry'), entry);
  }
  if (available.length) {
    const category = available[0];
    const link = nav.locator(`[data-category-id="${category}"]`);
    await followComparisonLink(page, link, category, entry);
  }
  return { status: 'pass', linked_categories: available.length };
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
  const jump = page.locator('#marketplace-navigation a[data-marketplace-entry="category"]');
  if (!await section.count()) {
    assert.equal(await jump.count(), 0, 'a category without comparable data must have no comparison jump');
    assert(!requireComparison, `${category} has no comparable pair in the generated page`);
    return { status: 'not_displayed' };
  }
  assert.equal(await section.count(), 1);
  assert(await section.isVisible());
  assert.equal(await jump.count(), 1);
  assert.equal(await jump.getAttribute('href'), comparisonFragment);
  assert.equal(await jump.getAttribute('data-category-id'), category);
  await followComparisonLink(page, jump, category, 'category');
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
      scale: Number(el.dataset.priceScale), factor: Number(el.dataset.priceFactor),
      priceUnit: el.dataset.priceUnit,
    }));
    assert(/^\d{13}$/.test(group.jan) && group.amount > 0 && group.pack > 0);
    assert(group.factor > 0 && group.scale > 0);
    const expectedUnit = { water: '1L', 'toilet-paper': '10m', tissue: '100組' }[category]
      || (/^(g|ml)$/.test(group.unit) ? '100' + group.unit : '1' + group.unit);
    assert.equal(group.priceUnit, expectedUnit);
    const key = `${group.jan}/${group.pack}`;
    assert(!identities.has(key), 'duplicate package');
    identities.add(key);
    const cards = await article.locator('.marketplace-offer').all();
    assert.equal(cards.length, 2);
    const rakuten = await checkOffer(cards[0], 'rakuten', group, catalog);
    const yahoo = await checkOffer(cards[1], 'yahoo', group, catalog);
    const summary = article.locator('.marketplace-totals dd');
    const totals = await summary.allTextContents();
    assert.deepEqual(totals, [rakuten, yahoo].map(total => total === null
      ? '送料要確認' : '¥' + total.toLocaleString('en-US')));
    if (rakuten !== null && yahoo !== null && rakuten !== yahoo) {
      assert.equal(await article.locator('.marketplace-leading-total dd').textContent(),
        '¥' + Math.min(rakuten, yahoo).toLocaleString('en-US'));
    }
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
  const totals = await articles[0].locator('.marketplace-totals dd').all();
  const totalBoxes = await Promise.all(totals.map(total => total.boundingBox()));
  assert(totalBoxes[1].x > totalBoxes[0].x && Math.abs(totalBoxes[0].y - totalBoxes[1].y) <= 1,
    'both purchase totals are next to one another at every viewport');
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
    const coverageResponse = await fetch(base + 'marketplace-coverage.json');
    assert.equal(coverageResponse.status, 200);
    const { categories: coverage } = await coverageResponse.json();
    assert.deepEqual(Object.keys(coverage).sort(), Object.keys(categories).sort());
    const configured = Object.keys(coverage).filter(category => coverage[category].status !== 'not_configured');
    const categoryIds = requestedCategories || configured;
    for (const engine of [chromium, webkit]) {
      const browser = await engine.launch({ headless: true });
      try {
        for (const width of [320, 390, 1440]) {
          const available = [];
          for (const category of categoryIds) {
            const page = await browser.newPage({ viewport: { width, height: 900 } });
            try {
              const result = await verifyPage(page, base, width, category, categories[category].items);
              assert.equal(result.comparable || 0, coverage[category].comparable, 'coverage must match rendered pairs');
              if (result.comparable > 0) available.push(category);
              console.log(JSON.stringify({ browser: engine.name(), width, category, ...result }));
            } finally {
              await page.close();
            }
          }
          for (const entry of ['home', 'directory']) {
            const page = await browser.newPage({ viewport: { width, height: 900 } });
            try {
              const result = await verifyDirectory(page, base, available, entry);
              console.log(JSON.stringify({ browser: engine.name(), width, entry, ...result }));
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
