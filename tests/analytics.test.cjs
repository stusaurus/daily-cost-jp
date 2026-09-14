const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { JSDOM } = require('jsdom');
const { execFileSync } = require('node:child_process');
const runtime = fs.readFileSync('scripts/analytics_runtime.js', 'utf8');
const BASE = 'https://stusaurus.github.io/daily-cost-jp/';
const affiliateURL = 'https://hb.afl.rakuten.co.jp/hgc/test';
function page(path = '', html = '', opts = {}) {
  const dom = new JSDOM(html, {url: BASE + path, runScripts:'outside-only'});
  const w = dom.window;
  const events = [];
  w.gtag = (...args) => events.push(args);
  if (opts.test) w.localStorage.setItem('daily_cost_operator_test_v1', '1');
  if (opts.nav) w.sessionStorage.setItem('daily_cost_feature_navigation_v1', JSON.stringify(opts.nav));
  if (opts.blocked) {
    for (const key of ['localStorage', 'sessionStorage']) Object.defineProperty(w, key, {get(){throw Error('blocked');}});
  }
  w.eval(runtime);
  // Stop real navigation only; allow all analytics propagation.
  w.document.addEventListener('click', e=>e.preventDefault());
  const click = (selector, type='click', button=0) => w.document.querySelector(selector).dispatchEvent(new w.MouseEvent(type,{bubbles:true,cancelable:true,button}));
  return {w,events,click,affiliate:()=>events.filter(e=>e[1]==='affiliate_click')};
}
function link(cls = '', extra = '') {return `<a href="${affiliateURL}" class="${cls}" ${extra}><span>楽天へ</span></a>`;}
for (const [path, html, expected] of [
  ['', '<section class="category-section" id="tissue">'+link('buy-button')+'</section>', 'category'],
  ['categories/tissue/', link('buy-button'), 'category'],
  ['today/', link('buy-button'), 'daily_pick'],
  ['today/', link('deal-image'), 'daily_pick'],
  ['', link('home-rank-first'), 'ranking'],
  ['trends/', '<div class="card">'+link('rakuten')+'</div>', 'ranking'],
  ['trends/', link(), 'trend'],
  ['', link('', 'data-exact-rakuten'), 'same_product_compare'],
  ['', link(), 'other'],
  ['products/', link('product-result-link'), 'product_search'],
]) test('source '+expected+' on '+path+' '+html.slice(0,45), ()=>{
  const p=page(path,html); p.click('a span');
  assert.equal(p.affiliate().length,1);
  assert.equal(p.affiliate()[0][2].conversion_source,expected);
  assert.equal(p.affiliate()[0][2].link_url,affiliateURL);
});
test('top pick hash and successful judge are category-specific last touches',()=>{
  const p=page('', '<a class="top-pick" href="#tissue">top</a><section class="category-section" id="tissue">'+link('buy-button')+'</section><section class="category-section" id="water">'+link('buy-button')+'</section>');
  p.click('.top-pick'); p.click('#tissue .buy-button');
  assert.equal(p.affiliate()[0][2].conversion_source,'top_pick');
  p.w.gtag('event','buy_judge',{category_id:'tissue'});
  p.click('#tissue .buy-button'); p.click('#water .buy-button');
  assert.equal(p.affiliate()[1][2].conversion_source,'buy_judge');
  assert.equal(p.affiliate()[2][2].conversion_source,'category');
  assert.ok(p.events.some(e=>e[1]==='buy_judge'));
});
test('exact-destination navigation carries source once and expires',()=>{
  const p=page('today/', '<a class="today-category-link" href="../categories/tissue/">category</a>');
  p.click('a');
  const nav=JSON.parse(p.w.sessionStorage.getItem('daily_cost_feature_navigation_v1'));
  const target=page('categories/tissue/',link('buy-button'),{nav});
  target.click('a'); assert.equal(target.affiliate()[0][2].conversion_source,'daily_pick');
  assert.equal(target.w.sessionStorage.getItem('daily_cost_feature_navigation_v1'),null);
  for(const wrong of [{...nav,target:'/wrong'}, {...nav,at:Date.now()-1800001}]) {
    const t=page('categories/tissue/',link('buy-button'),{nav:wrong}); t.click('a');
    assert.equal(t.affiliate()[0][2].conversion_source,'category');
  }
});
test('trend search then typed/Enter search resets source only on new results',()=>{
  const p=page('products/', '<input id="q"><button id="searchBtn">search</button><button class="chip" data-q="water">trend</button>'+link('product-result-link'));
  p.click('.chip'); p.w.gtag('event','realtime_product_search',{search_term:'water'}); p.click('a');
  assert.equal(p.affiliate()[0][2].conversion_source,'trend');
  p.w.document.querySelector('#q').dispatchEvent(new p.w.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
  p.click('a'); assert.equal(p.affiliate()[1][2].conversion_source,'trend');
  p.w.gtag('event','realtime_product_search',{search_term:'tissue'}); p.click('a');
  assert.equal(p.affiliate()[2][2].conversion_source,'product_search');
  assert.equal(p.affiliate()[2][2].search_term,'tissue');
});
test('operator flag enabled, persisted, disabled and never added for normal traffic',()=>{
  for(const [path,opts,marked] of [['?test=1&utm_source=x',{},true],['today/',{test:true},true],['?test=0',{test:true},false],['',{},false],['?test=1',{blocked:true},true],['',{blocked:true},false]]) {
    const p=page(path,link(),opts); p.w.gtag('event','product_result_click',{}); p.click('a');
    for(const e of p.events.filter(e=>e[0]==='event')) assert.equal(e[2].operator_test,marked?'1':undefined);
    assert.equal(p.events.some(e=>e[0]==='set' && e[1].operator_test==='1'),marked);
    assert.equal(new URL(p.w.location.href).searchParams.has('test'),false);
  }
});
test('external non-Rakuten and deceptive domains ignored; middle click counted',()=>{
  const p=page('', '<a id="bad" href="https://rakuten.co.jp.evil.test/">bad</a><a id="internal" href="today/">today</a>'+link('real'));
  p.click('#bad');p.click('#internal');assert.equal(p.affiliate().length,0);
  p.click('.real','auxclick',2);assert.equal(p.affiliate().length,0);
  p.click('.real','auxclick',1);assert.equal(p.affiliate().length,1);
});
test('actual generated product page: search -> result -> ONE affiliate and ONE legacy click', async()=>{
  const html=execFileSync('python',['tests/render_analytics_fixture.py'],{encoding:'utf8'});
  const errors=[];
  const dom=new JSDOM(html,{url:BASE+'products/?test=1',runScripts:'dangerously',beforeParse(w){
    w.addEventListener('error',e=>errors.push(e.message));
    w.fetch=async()=>({ok:true,json:async()=>({page_count:1,products:[{
      product_id:'offline',name:'試験用ティッシュ',shipping_included_price:1000,
      shipping_included_url:affiliateURL,url:affiliateURL,sale_quantity_label:'10箱入り'
    }]})});
  }});
  const w=dom.window;
  w.document.addEventListener('click',e=>e.preventDefault());
  w.document.querySelector('#q').value='ティッシュ';
  w.document.querySelector('#searchBtn').click();
  await new Promise(r=>setTimeout(r,30));
  assert.ok(w.document.querySelector('.product-result-link'));
  w.document.querySelector('.product-result-link').click();
  const events=w.dataLayer.filter(e=>e[0]==='event');
  for(const name of ['realtime_product_search','product_result_click','affiliate_click']) {
    assert.equal(events.filter(e=>e[1]===name).length,1,name);
    assert.equal(events.find(e=>e[1]===name)[2].operator_test,'1');
  }
  const affiliate=events.find(e=>e[1]==='affiliate_click')[2];
  assert.equal(affiliate.conversion_source,'product_search');
  assert.equal(affiliate.search_term,'ティッシュ');
  assert.equal(affiliate.shipping_included_price,1000);
  assert.deepEqual(errors,[]);
  dom.window.close();
});
