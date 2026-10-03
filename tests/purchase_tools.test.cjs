const { test } = require('node:test');
const assert = require('node:assert/strict');
const { JSDOM } = require('jsdom');
const fs = require('node:fs');
const code = fs.readFileSync('scripts/purchase_tools.js','utf8');
const source = fs.readFileSync('scripts/analytics_runtime.js','utf8');
async function fixture(blockStorage=false) {
  const dom=new JSDOM(`<section id="purchase-tools"><button id="show-saved"></button><button id="show-comparison"></button><p id="purchase-tool-status"></p><div id="purchase-tool-panel" hidden></div></section><article class="product-card"><div class="product-body"><h3>A</h3><a href="https://hb.afl.rakuten.co.jp/a">楽天</a></div></article><article class="product-card"><div class="product-body"><h3>B</h3><a href="https://hb.afl.rakuten.co.jp/b">楽天</a></div></article>`,{url:'https://stusaurus.github.io/daily-cost-jp/categories/tissue/',runScripts:'outside-only'});
  dom.window.fetch=async()=>({ok:true,json:async()=>[
    {key:'a',category:'tissue',name:'A',url:'https://hb.afl.rakuten.co.jp/a',quantity:'60箱',price:3600,unit:['100組',40],rank:1,updated_at:'2026-10-03T06:00:00+09:00'},
    {key:'b',category:'tissue',name:'B',url:'https://hb.afl.rakuten.co.jp/b',quantity:'60箱',price:4200,unit:['100組',35],rank:2,updated_at:'2026-10-03T06:00:00+09:00'}]});
  if(blockStorage)Object.defineProperty(dom.window,'localStorage',{value:{getItem:()=>null,setItem:()=>{throw Error('quota');}}});
  dom.window.eval(code);await new Promise(resolve=>setImmediate(resolve));return dom;
}
test('comparison orders equal content correctly despite box rank, resolves saved IDs and labels affiliate source',async()=>{
  const dom=await fixture();const d=dom.window.document;
  d.querySelectorAll('[data-product-tool="compare"]').forEach(b=>b.click());d.getElementById('show-comparison').click();
  assert.match(d.getElementById('purchase-tool-panel').textContent,/単価差は最大¥5.00/);
  assert.equal(d.querySelector('#purchase-tool-panel li strong').textContent,'B');
  assert.equal(d.querySelector('#purchase-tool-panel a').dataset.conversionSource,'comparison');
  d.querySelector('[data-product-tool="save"]').click();d.getElementById('show-saved').click();
  assert.equal(d.querySelector('#purchase-tool-panel a').dataset.conversionSource,'saved');
  assert.deepEqual(JSON.parse(dom.window.localStorage.getItem('daily_cost_saved_products_v1')),['a']);dom.window.close();
});
test('storage failure is reported without losing comparison',async()=>{
  const dom=await fixture(true);const d=dom.window.document;
  d.querySelector('[data-product-tool="save"]').click();assert.match(d.getElementById('purchase-tool-status').textContent,/保存できませんでした/);
  d.querySelector('[data-product-tool="compare"]').click();d.getElementById('show-comparison').click();assert.match(d.getElementById('purchase-tool-panel').textContent,/A/);dom.window.close();
});
test('comparison explains a real total/unit inversion and can be dismissed without losing selections',async()=>{
  const dom=await fixture();const d=dom.window.document;
  d.querySelectorAll('[data-product-tool="compare"]').forEach(b=>b.click());d.getElementById('show-comparison').click();
  assert.match(d.getElementById('purchase-tool-panel').textContent,/支払総額が低い候補と、単価が低い候補は異なります/);
  Array.from(d.querySelectorAll('#purchase-tool-panel button')).find(b=>b.textContent==='比較・保存の一覧を閉じる').click();
  assert.equal(d.getElementById('purchase-tool-panel').hidden,true);
  assert.match(d.getElementById('show-comparison').textContent,/2/);dom.window.close();
});
