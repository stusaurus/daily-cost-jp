const { test } = require('node:test');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const { JSDOM } = require('jsdom');

test('late responses never mix old prices and links into a newer search', async () => {
  const html = execFileSync('python', ['tests/render_analytics_fixture.py'], {encoding:'utf8'});
  const pending = [];
  const dom = new JSDOM(html, {url:'https://stusaurus.github.io/daily-cost-jp/products/?test=1',runScripts:'dangerously',beforeParse(w){
    w.fetch = url => new Promise(resolve => pending.push({url,resolve}));
  }});
  const w = dom.window;
  const query = w.document.querySelector('#q');
  const flush = () => new Promise(r => setTimeout(r, 20));
  function enter(value){query.value=value;query.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));}
  const result = (name,id) => ({ok:true,json:async()=>({page_count:1,products:[{product_id:id,name,shipping_included_price:1000,shipping_included_url:'https://hb.afl.rakuten.co.jp/hgc/'+id,url:'https://product.rakuten.co.jp/'+id}]})});
  enter('先の検索');enter('後の検索');
  assert.equal(pending.length,2);
  pending[1].resolve(result('後の検索商品','new'));await flush();
  pending[0].resolve(result('先の検索商品','old'));await flush();
  assert.match(w.document.querySelector('#results').textContent,/後の検索商品/);
  assert.doesNotMatch(w.document.querySelector('#results').textContent,/先の検索商品/);
  assert.match(w.document.querySelector('.product-result-link').href,/\/new$/);
  assert.equal(w.document.querySelector('#searchBtn').disabled,false);
  assert.equal(w.dataLayer.filter(e=>e[0]==='event'&&e[1]==='realtime_product_search').length,1);
  dom.window.close();
});
