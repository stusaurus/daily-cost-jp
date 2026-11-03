const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {execFileSync} = require('node:child_process');
const {JSDOM} = require('jsdom');

const markup = execFileSync('python3', ['-c',
  "from scripts.add_a8_lenet import card, CLICK_TRACKER; print(card() + CLICK_TRACKER)"],
  {encoding: 'utf8'});
const runtime = fs.readFileSync('scripts/analytics_runtime.js', 'utf8');
const official = 'https://px.a8.net/svt/ejp?a8mat=4BGCF1+ATDIEQ+2W7Y+67JUA';
const pixel = 'https://www10.a8.net/0.gif?a8mat=4BGCF1+ATDIEQ+2W7Y+67JUA';

function boot(testMode) {
  const dom = new JSDOM('<!doctype html><html><head></head><body><main>' + markup + '</main></body></html>', {
    url: 'https://stusaurus.github.io/daily-cost-jp/categories/laundry/?test=' + testMode,
    runScripts: 'outside-only',
  });
  const {window: w} = dom;
  const events = [];
  w.gtag = (...args) => events.push(args);
  w.eval(runtime);
  w.eval(w.document.getElementById('a8-lenet-click-tracker').textContent);
  w.document.addEventListener('click', event => event.preventDefault());
  return {dom, w, events, doc: w.document};
}

test('Lenet advert preserves provided tracking link, pixel and disclosure', () => {
  const {dom, doc} = boot(1);
  try {
    const card = doc.getElementById('a8-lenet-option');
    assert.ok(card);
    assert.match(card.textContent, /広告｜A8.netアフィリエイト/);
    assert.match(card.textContent, /楽天の商品ランキング・単価計算には含めていません/);
    const anchor = card.querySelector('a');
    assert.equal(anchor.href, official);
    assert.equal(anchor.getAttribute('rel'), 'nofollow');
    assert.match(anchor.textContent, /宅配クリーニング「リネット」/);
    const img = card.querySelector('img');
    assert.equal(img.getAttribute('src'), pixel);
    assert.equal(img.getAttribute('width'), '1');
    assert.equal(img.getAttribute('height'), '1');
    assert.equal(doc.querySelectorAll('a[href^="https://px.a8.net"]').length, 1);
  } finally {dom.window.close();}
});

for (const [testMode, expected] of [[1, '1'], [0, '0']]) {
  test('Lenet click emits one A8 affiliate event with operator_test=' + expected, () => {
    const {dom, w, events, doc} = boot(testMode);
    try {
      doc.querySelector('#a8-lenet-option a').dispatchEvent(
        new w.MouseEvent('click', {bubbles: true, cancelable: true})
      );
      const clicks = events.filter(e => e[0] === 'event' && e[1] === 'affiliate_click');
      assert.equal(clicks.length, 1);
      assert.equal(clicks[0][2].affiliate, 'a8');
      assert.equal(clicks[0][2].merchant, 'lenet');
      assert.equal(clicks[0][2].program, 'lenet_delivery_cleaning');
      assert.equal(clicks[0][2].category_id, 'laundry');
      assert.equal(clicks[0][2].conversion_source, 'category');
      assert.equal(clicks[0][2].operator_test, expected);
      assert.equal(clicks[0][2].site_id, 'daily-cost-jp');
      assert.equal(events.filter(e => e[0] === 'event' && e[1] === 'purchase').length, 0);
    } finally {dom.window.close();}
  });
}
