const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {execFileSync} = require('node:child_process');
const {JSDOM} = require('jsdom');

const markup = execFileSync('python3', ['-c',
  "from scripts.add_a8_matsukiyo import card, CLICK_TRACKER; print(card('laundry', '洗濯洗剤') + CLICK_TRACKER)"],
  {encoding:'utf8'});
const runtime = fs.readFileSync('scripts/analytics_runtime.js', 'utf8');
const official = 'https://px.a8.net/svt/ejp?a8mat=4BGCF1+A1E4Z6+5QFO+5YJRM';
const pixel = 'https://www19.a8.net/0.gif?a8mat=4BGCF1+A1E4Z6+5QFO+5YJRM';

function boot(suffix) {
  const dom = new JSDOM('<!doctype html><html><head></head><body><main>' + markup + '</main></body></html>', {
    url:'https://stusaurus.github.io/daily-cost-jp/categories/laundry/' + suffix,
    runScripts:'outside-only'
  });
  const events = [];
  const w = dom.window;
  w.gtag = (...args) => events.push(args);
  w.eval(runtime);
  w.eval(w.document.getElementById('a8-matsukiyo-click-tracker').textContent);
  w.document.addEventListener('click', e => e.preventDefault());
  return {dom, w, events, document:w.document};
}

test('original A8 link, visible disclosure, and one tracking pixel are preserved', () => {
  const {dom, document} = boot('?test=1');
  try {
    const card = document.querySelector('#a8-matsukiyo-option');
    assert.ok(card);
    assert.match(card.textContent, /広告｜A8.netアフィリエイト/);
    assert.match(card.textContent, /クーポンが必ず利用できることは保証しません/);
    const link = card.querySelector('a[href^="https://px.a8.net"]');
    assert.equal(link.getAttribute('href'), official);
    assert.equal(link.getAttribute('rel'), 'nofollow');
    assert.match(link.textContent, /【マツキヨココカラオンラインストア】/);
    const img = card.querySelector('img');
    assert.equal(img.getAttribute('src'), pixel);
    assert.equal(img.getAttribute('width'), '1');
    assert.equal(img.getAttribute('height'), '1');
    assert.equal(document.querySelectorAll('a[href^="https://px.a8.net"]').length, 1);
  } finally {dom.window.close()}
});

test('A8 click records affiliate_click once and inherits operator_test and category context', () => {
  const {dom,document,w,events} = boot('?test=1');
  try {
    const link=document.querySelector('#a8-matsukiyo-option a');
    link.dispatchEvent(new w.MouseEvent('click', {bubbles:true,cancelable:true}));
    const tracked=events.filter(e=>e[0]==='event'&&e[1]==='affiliate_click');
    assert.equal(tracked.length, 1);
    assert.equal(tracked[0][2].affiliate,'a8');
    assert.equal(tracked[0][2].merchant,'matsukiyococokara');
    assert.equal(tracked[0][2].program,'matsukiyococokara_online');
    assert.equal(tracked[0][2].category_id,'laundry');
    assert.equal(tracked[0][2].conversion_source,'category');
    assert.equal(tracked[0][2].operator_test,'1');
    assert.equal(tracked[0][2].site_id,'daily-cost-jp');
    assert.equal(link.getAttribute('href'),official);
  } finally {dom.window.close()}
});

test('real-user click is distinguished from test and no purchase event is fabricated', () => {
  const {dom,document,w,events} = boot('?test=0');
  try {
    document.querySelector('#a8-matsukiyo-option a').dispatchEvent(new w.MouseEvent('click', {bubbles:true,cancelable:true}));
    const tracked=events.filter(e=>e[0]==='event'&&e[1]==='affiliate_click');
    assert.equal(tracked.length,1);
    assert.equal(tracked[0][2].operator_test,'0');
    assert.equal(events.filter(e=>e[0]==='event'&&e[1]==='purchase').length,0);
    assert.equal(tracked[0][2].link_url,undefined);
  } finally {dom.window.close()}
});
