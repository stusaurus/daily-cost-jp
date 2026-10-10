#!/usr/bin/env node
/* Read-only Playwright inspection of production purchase CTAs.
 * GA requests are blocked; no affiliate link is opened or clicked.
 * Outputs reviewable observations only. Never changes website or product data.
 */
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const {URL} = require('node:url');

const SITE = 'https://stusaurus.github.io/daily-cost-jp/';
const CORE = ['/categories/laundry/', '/categories/tissue/', '/categories/toilet-paper/'];
const SIZES = [1440, 390, 320];
const MAX_PAGES = 5;
const BLOCKED = /(?:googletagmanager\.com|google-analytics\.com|analytics\.google\.com|googleadservices\.com|doubleclick\.net|hb\.afl\.rakuten\.co\.jp)/i;

function isAllowedPath(value) {
  if (typeof value !== 'string' || value.length > 100) return false;
  return value === '/' || value === '/products/' || value === '/today/' ||
    /^\/categories\/[a-z0-9-]+\/$/.test(value);
}

function selectPages(report, limit = MAX_PAGES, jointReport = null, extraCategories = []) {
  const result = [...CORE];
  // CI regression targets must still be restricted to local category paths.
  if (Array.isArray(extraCategories)) {
    for (const page of extraCategories) {
      if (typeof page === 'string' && /^\/categories\/[a-z0-9-]+\/$/.test(page) &&
          !result.includes(page) && result.length < limit) result.push(page);
    }
  }
  // Use joined search/affiliate evidence only when both sources were obtained.
  // The shortlist is a path allowlist, not a general web crawler.
  if (jointReport && jointReport.source === 'GA4 + Search Console read-only page triage' &&
      jointReport.status === 'JOINT_PROVISIONAL' &&
      Array.isArray(jointReport.top_investigations)) {
    for (const candidate of jointReport.top_investigations) {
      const pathname = candidate && candidate.confidence === 'INVESTIGATION_ONLY' && candidate.path;
      if (isAllowedPath(pathname) && !result.includes(pathname) && result.length < limit) {
        result.push(pathname);
      }
    }
  }
  if (report && Array.isArray(report.top_investigations)) {
    for (const candidate of report.top_investigations) {
      const pathname = candidate && candidate.page;
      if (isAllowedPath(pathname) && !result.includes(pathname) && result.length < limit) {
        result.push(pathname);
      }
    }
  }
  return result.slice(0, Math.max(CORE.length, limit));
}

function isRakutenHref(href) {
  try {
    const u = new URL(href);
    return u.protocol === 'https:' && (u.hostname === 'rakuten.co.jp' ||
      u.hostname.endsWith('.rakuten.co.jp')) && !u.username && !u.password;
  } catch (_) { return false; }
}

function assess(observation) {
  const problems = [];
  const add = (severity, code, message) => problems.push({severity, code, message});
  if (observation.httpStatus !== 200) add('error', 'HTTP_UNAVAILABLE', 'ページがHTTP 200で表示されない');
  if (observation.h1Count !== 1) add('error', 'HEADING_MISSING_OR_DUPLICATE', '主見出しの個数が1ではない');
  if (observation.documentWidth > observation.viewport + 2) {
    add('warning', 'HORIZONTAL_OVERFLOW', '表示領域からはみ出す横スクロールがある');
  }
  if (observation.kind === 'category') {
    if (observation.coreCategory && observation.priceGroups === 0) {
      add('error', 'MISSING_PRODUCT_COMPARISON', '主要カテゴリの価格比較欄が表示されない');
    }
    if (observation.ctaCount === 0) add('error', 'MISSING_RAKUTEN_CTA', '楽天へ進むボタンがない');
    if (observation.hiddenCtaCount === observation.ctaCount && observation.ctaCount > 0) {
      add('error', 'NO_VISIBLE_RAKUTEN_CTA', '楽天ボタンが画面上に表示されない');
    }
    if (observation.invalidHrefCount > 0) {
      add('error', 'UNEXPECTED_CTA_DESTINATION', '楽天ボタンに意図しないリンク先が含まれる');
    }
    if (observation.tinyCtaCount > 0) {
      add('warning', 'SMALL_TAP_TARGET', '高さまたは幅44px未満の購入ボタンがある');
    }
  }
  if (observation.pageErrors.length) add('warning', 'SCRIPT_ERROR', 'ページ側でJavaScriptの例外を検出');
  return {
    status: problems.some(p => p.severity === 'error') ? 'FAIL' :
      problems.length ? 'REVIEW' : 'PASS',
    problems,
  };
}

function safeName(page) {
  return page === '/' ? 'home' : page.replace(/[^a-z0-9-]+/gi, '-').replace(/^-|-$/g, '');
}

function markdown(report) {
  const lines = [
    '## 日用品サイト：PC・スマホ購入導線の自動実画面監査',
    '',
    '- 実行：' + report.generated_at_utc,
    '- サイト：' + SITE,
    '- 検査対象：' + report.pages.join('、'),
    '- GA4への送信を遮断し、楽天リンクは一切クリックしていません。',
    '- 商品価格・楽天リンク・ページのコードは変更していません。',
    '- **FAILは再検証が必要な技術的問題。REVIEWは要確認事項であり、成約率の低さを証明しません。**',
    '',
    '| ページ | 画面幅 | 判定 | 楽天ボタン | 横はみ出し | 主な確認事項 |',
    '|---|---:|---|---:|---|---|',
  ];
  for (const r of report.observations) {
    const issues = r.problems.map(p => p.code).join('・') || '検出なし';
    lines.push('| ' + r.path + ' | ' + r.viewport + 'px | ' + r.status +
      ' | ' + (r.ctaCount ?? '—') + ' | ' +
      ((r.documentWidth ?? 0) > r.viewport + 2 ? 'あり' : 'なし') + ' | ' +
      issues.replace(/[|\r\n]/g, ' ') + ' |');
  }
  lines.push('', '### 判定上の注意',
    '商品比較ページとカテゴリページでは購入ボタンの設計が異なります。カテゴリページのみ既存の価格比較欄・購入リンクを必須検査しています。',
    'リンク先URLの構文は検査しますが、**楽天への外部遷移や購入操作は実行していません。**',
    'ページ表示の自動QAは購入・売上・実際のアフィリエイト成果を計測するものではありません。',
    '');
  return lines.join('\n');
}

async function inspect(browser, pathname, viewport, outDir) {
  const target = SITE + pathname.substring(1) + '?test=1';
  const context = await browser.newContext({
    viewport: {width: viewport, height: 900},
    locale: 'ja-JP', isMobile: viewport <= 390,
    hasTouch: viewport <= 390,
    reducedMotion: 'reduce',
  });
  await context.route('**/*', async route => {
    if (BLOCKED.test(route.request().url())) return route.abort();
    return route.continue();
  });
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  const errors = [];
  page.on('pageerror', error => errors.push(String(error.message).slice(0, 200)));
  const record = {
    path: pathname, viewport,
    kind: pathname.startsWith('/categories/') ? 'category' : 'general',
    coreCategory: CORE.includes(pathname),
    httpStatus: null, h1Count: 0, documentWidth: 0,
    priceGroups: 0, ctaCount: 0, hiddenCtaCount: 0,
    tinyCtaCount: 0, invalidHrefCount: 0,
    invalidHrefExamples: [], pageErrors: errors,
    screenshot: null,
  };
  try {
    const response = await page.goto(target, {waitUntil: 'domcontentloaded', timeout: 20000});
    record.httpStatus = response ? response.status() : null;
    await page.waitForTimeout(700);
    const dom = await page.evaluate(({coreCategory}) => {
      const visible = el => {
        const rect = el.getBoundingClientRect();
        const css = getComputedStyle(el);
        return rect.height > 0 && rect.width > 0 && css.display !== 'none' &&
          css.visibility !== 'hidden' && css.opacity !== '0';
      };
      // The core 3 categories use a dedicated price-group layout. The other
      // category pages use ranking cards and text-labelled Rakuten anchors.
      // Requiring the core markup everywhere falsely flags valid product pages.
      const buttons = coreCategory ?
        [...document.querySelectorAll('.search-price-group .buy-button')] :
        [...document.querySelectorAll('a[href]')].filter(el =>
          /^楽天で(?:商品を)?確認する/.test((el.textContent || '').trim()));
      return {
        h1Count: document.querySelectorAll('h1').length,
        documentWidth: document.documentElement.scrollWidth,
        priceGroups: document.querySelectorAll('.search-price-group').length,
        buttons: buttons.map(el => {
          const rect = el.getBoundingClientRect();
          return {href: el.href, visible: visible(el), width: rect.width, height: rect.height};
        }),
      };
    }, {coreCategory: record.coreCategory});
    record.h1Count = dom.h1Count;
    record.documentWidth = dom.documentWidth;
    record.priceGroups = dom.priceGroups;
    record.ctaCount = dom.buttons.length;
    record.hiddenCtaCount = dom.buttons.filter(b => !b.visible).length;
    record.tinyCtaCount = dom.buttons.filter(b => b.visible &&
      (b.width < 44 || b.height < 44)).length;
    const invalid = dom.buttons.filter(b => !isRakutenHref(b.href));
    record.invalidHrefCount = invalid.length;
    record.invalidHrefExamples = invalid.slice(0, 3).map(b => b.href.slice(0, 200));
    const imageName = safeName(pathname) + '-' + viewport + '.png';
    try {
      await page.screenshot({path: path.join(outDir, imageName), fullPage: true, timeout: 15000});
      record.screenshot = imageName;
    } catch (error) {
      record.screenshotError = String(error.message).slice(0, 200);
    }
  } catch (error) {
    record.pageErrors.push('NAVIGATION_FAILED: ' + String(error.message).slice(0, 200));
  } finally {
    const decision = assess(record);
    Object.assign(record, decision);
    await context.close();
  }
  return record;
}

async function main() {
  const inputIndex = process.argv.indexOf('--ga4');
  const input = inputIndex >= 0 ? process.argv[inputIndex + 1] : null;
  let report = null;
  if (input) {
    try { report = JSON.parse(fs.readFileSync(input, 'utf8')); }
    catch (error) { throw new Error('GA4 input artifact missing or invalid: ' + error.message); }
  }
  if (report && report.source !== 'GA4 Data API') throw new Error('Unexpected GA4 artifact source');
  const jointIndex = process.argv.indexOf('--joint');
  const jointFile = jointIndex >= 0 ? process.argv[jointIndex + 1] : null;
  let joint = null;
  if (jointFile) {
    try { joint = JSON.parse(fs.readFileSync(jointFile, 'utf8')); }
    catch (error) { throw new Error('Joint report missing or invalid: ' + error.message); }
    if (joint.source !== 'GA4 + Search Console read-only page triage' || joint.site !== SITE) {
      throw new Error('Unexpected joint analytics report source or site');
    }
  }
  const extraIndex = process.argv.indexOf('--extra-category');
  const extra = extraIndex >= 0 ? process.argv[extraIndex + 1] : null;
  const pages = selectPages(report, MAX_PAGES, joint, extra ? [extra] : []);
  const outDir = path.resolve('audit-results/live-cta-qa');
  fs.mkdirSync(outDir, {recursive: true});
  const {chromium} = require('playwright');
  const browser = await chromium.launch({headless: true, args: ['--no-sandbox']});
  const observations = [];
  try {
    for (const pathname of pages) {
      for (const size of SIZES) {
        const record = await inspect(browser, pathname, size, outDir);
        observations.push(record);
        console.log(pathname + ' ' + size + 'px ' + record.status +
          ' CTA=' + record.ctaCount);
      }
    }
  } finally {
    await browser.close();
  }
  const output = {
    generated_at_utc: new Date().toISOString(),
    site: SITE, pages,
    ga4_period: report?.period_last_28 || null,
    ga4_status: report?.status || 'NOT_PROVIDED',
    joined_gsc_status: joint?.status || 'NOT_PROVIDED',
    read_only: true, analytics_blocked: true, external_links_clicked: false,
    observations,
    counts: {
      passed: observations.filter(r => r.status === 'PASS').length,
      review: observations.filter(r => r.status === 'REVIEW').length,
      failed: observations.filter(r => r.status === 'FAIL').length,
    },
  };
  fs.writeFileSync(path.join(outDir, 'report.json'), JSON.stringify(output, null, 2));
  fs.writeFileSync(path.join(outDir, 'report.md'), markdown(output));
  console.log('Browser QA completed: ' + JSON.stringify(output.counts));
  if (output.counts.failed > 0) process.exitCode = 1;
}

if (require.main === module) main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});

module.exports = {isAllowedPath, selectPages, isRakutenHref, assess, markdown, safeName};
