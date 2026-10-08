const {test}=require('node:test');
const assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
const {JSDOM}=require('jsdom');
test('editorial relocation cannot leave same-product search inert',async()=>{
  const html=execFileSync('python',['tests/render_exact_fixture.py'],{encoding:'utf8'});
  assert.ok(html.indexOf("document.addEventListener('DOMContentLoaded'")<html.indexOf('id="exact-name"'));
  const calls=[];
  const dom=new JSDOM(html,{url:'https://stusaurus.github.io/daily-cost-jp/',runScripts:'dangerously',beforeParse(w){
    w.HTMLElement.prototype.scrollIntoView=function(){};
    w.fetch=async url=>{calls.push(url);return {ok:true,json:async()=>({products:[{product_id:'one',name:'アリエール 部屋干しプラス 本体 690g',brand:'アリエール',shipping_included_price:1183,shipping_included_url:'https://hb.afl.rakuten.co.jp/hgc/verified'}]})};};
  }});
  await new Promise(r=>setImmediate(r));const d=dom.window.document;
  d.querySelector('#exact-name').value='アリエール 部屋干しプラス 本体 690g';d.querySelector('#exact-store-price').value='1000';d.querySelector('#exact-search').click();
  assert.match(d.querySelector('#exact-status').textContent,/確認中/);
  await new Promise(r=>setImmediate(r));assert.equal(calls.length,1);
  const choose=d.querySelector('.exact-choose');assert.ok(choose);assert.equal(choose.disabled,false);choose.click();
  assert.match(d.querySelector('#exact-result').textContent,/183/);
  assert.match(d.querySelector('#exact-result a').href,/verified/);dom.window.close();
});
