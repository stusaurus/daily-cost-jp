'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {isAllowedPath, selectPages, isRakutenHref, assess, markdown, safeName} =
  require('../scripts/ga4_live_cta_audit.cjs');

const base = {
  path: '/categories/tissue/', viewport: 390, kind: 'category',
  httpStatus: 200, h1Count: 1, documentWidth: 390,
  priceGroups: 3, ctaCount: 4, hiddenCtaCount: 0,
  tinyCtaCount: 0, invalidHrefCount: 0, pageErrors: [],
};

test('only local static site paths can be selected for browser navigation', () => {
  for (const ok of ['/', '/products/', '/today/', '/categories/laundry/', '/categories/toilet-paper/']) {
    assert.equal(isAllowedPath(ok), true);
  }
  for (const wrong of [
    'https://evil.example/', '//evil.example/', '/daily-cost-jp/', '/../admin/',
    '/categories/../../', '/categories/tissue/?q=1', '/categories/%2e%2e/',
    '/categories/あ/', '/categories/not-safe//', '', '/categories/tissue#anchor',
  ]) assert.equal(isAllowedPath(wrong), false, wrong);
});

test('always inspect the core categories and at most two GA4 candidate extras', () => {
  const selection = selectPages({
    top_investigations: [
      {page: '/categories/tissue/'}, {page: 'https://evil.example/'},
      {page: '/products/'}, {page: '/today/'}, {page: '/categories/soap/'},
    ],
  });
  assert.deepEqual(selection, [
    '/categories/laundry/', '/categories/tissue/', '/categories/toilet-paper/',
    '/products/', '/today/',
  ]);
  assert.equal(selectPages({top_investigations: [{page: '//bad/'}]}).length, 3);
  assert.equal(selectPages(null).length, 3);
});

test('trusted GSC+GA4 candidates are inspected before GA4-only extras', () => {
  const joint = {
    source: 'GA4 + Search Console read-only page triage',
    status: 'JOINT_PROVISIONAL',
    top_investigations: [
      {path: '/categories/laundry/', confidence: 'INVESTIGATION_ONLY'},
      {path: '/categories/soap/', confidence: 'INVESTIGATION_ONLY'},
      {path: '//evil.example/', confidence: 'INVESTIGATION_ONLY'},
      {path: '/today/', confidence: 'INVESTIGATION_ONLY'},
    ],
  };
  const ga4 = {top_investigations: [{page: '/products/'}]};
  assert.deepEqual(selectPages(ga4, 5, joint), [
    '/categories/laundry/', '/categories/tissue/', '/categories/toilet-paper/',
    '/categories/soap/', '/today/',
  ]);
});

test('unavailable or untrusted joint data never adds unauthorized paths', () => {
  const ga4 = {top_investigations: [{page: '/products/'}]};
  for (const joint of [
    {source: 'GA4 + Search Console read-only page triage', status: 'GSC_UNAVAILABLE',
      top_investigations: [{path: '/today/', confidence: 'INVESTIGATION_ONLY'}]},
    {source: 'untrusted', status: 'JOINT_PROVISIONAL',
      top_investigations: [{path: '/today/', confidence: 'INVESTIGATION_ONLY'}]},
    {source: 'GA4 + Search Console read-only page triage', status: 'JOINT_PROVISIONAL',
      top_investigations: [{path: '/today/', confidence: 'NO_JOINED_DECISION'}]},
  ]) {
    assert.deepEqual(selectPages(ga4, 5, joint), [
      '/categories/laundry/', '/categories/tissue/', '/categories/toilet-paper/',
      '/products/',
    ]);
  }
});

test('Rakuten link validation is URL and hostname strict; never follows links', () => {
  assert.equal(isRakutenHref('https://hb.afl.rakuten.co.jp/ichiba/abc'), true);
  assert.equal(isRakutenHref('https://item.rakuten.co.jp/seller/item'), true);
  assert.equal(isRakutenHref('https://evil-rakuten.co.jp/'), false);
  assert.equal(isRakutenHref('https://rakuten.co.jp.evil/'), false);
  assert.equal(isRakutenHref('javascript:alert(1)'), false);
  assert.equal(isRakutenHref('http://hb.afl.rakuten.co.jp/ichiba'), false);
  assert.equal(isRakutenHref('/relative-url'), false);
});

test('valid category data is pass, and no outbound clicks are required', () => {
  assert.deepEqual(assess(base), {status: 'PASS', problems: []});
});

test('missing CTA and price group are failures on category pages', () => {
  const result = assess({...base, priceGroups: 0, ctaCount: 0, hiddenCtaCount: 0});
  assert.equal(result.status, 'FAIL');
  assert(result.problems.some(p => p.code === 'MISSING_PRODUCT_COMPARISON'));
  assert(result.problems.some(p => p.code === 'MISSING_RAKUTEN_CTA'));
});

test('invalid destination and all hidden CTAs are failures', () => {
  const result = assess({...base, invalidHrefCount: 1, hiddenCtaCount: 4});
  assert.equal(result.status, 'FAIL');
  assert(result.problems.some(p => p.code === 'UNEXPECTED_CTA_DESTINATION'));
  assert(result.problems.some(p => p.code === 'NO_VISIBLE_RAKUTEN_CTA'));
});

test('horizontal overflow, small mobile target and JS errors are review items', () => {
  const result = assess({...base, documentWidth: 404, tinyCtaCount: 1,
    pageErrors: ['One example']});
  assert.equal(result.status, 'REVIEW');
  assert(result.problems.some(p => p.code === 'HORIZONTAL_OVERFLOW'));
  assert(result.problems.some(p => p.code === 'SMALL_TAP_TARGET'));
  assert(result.problems.some(p => p.code === 'SCRIPT_ERROR'));
});

test('general landing pages do not require category price groups', () => {
  assert.equal(assess({...base, kind: 'general', ctaCount: 0, priceGroups: 0}).status, 'PASS');
});

test('HTTP failures and duplicate heading are actionable but do not edit production', () => {
  const result = assess({...base, httpStatus: 404, h1Count: 0});
  assert.equal(result.status, 'FAIL');
  assert(result.problems.some(p => p.code === 'HTTP_UNAVAILABLE'));
  assert(result.problems.some(p => p.code === 'HEADING_MISSING_OR_DUPLICATE'));
});

test('human-readable output clarifies observation is not sales or actual affiliate test', () => {
  const text = markdown({
    generated_at_utc: '2026-10-10T00:00:00Z',
    pages: ['/categories/tissue/'],
    observations: [{...base, ...assess(base)}],
  });
  assert.match(text, /一切クリックしていません/);
  assert.match(text, /購入/);
  assert.match(text, /商品価格/);
  assert.equal(safeName('/'), 'home');
  assert.equal(safeName('/categories/toilet-paper/'), 'categories-toilet-paper');
});
