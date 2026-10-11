const {test}=require('node:test'),assert=require('node:assert/strict');
const api=require('../scripts/step4_search_diagnostics.js');
const {JSDOM}=require('jsdom');const {execFileSync}=require('node:child_process');
test('search zero distinguishes API failure, zero response and 10 unresolved offers',()=>{
 assert.equal(api.summarize([], 'API_FAILURE').fetched_count,null);
 assert.equal(api.summarize([]).status,'API_RESPONSE_ZERO');
 const r=api.summarize(Array.from({length:10},()=>({name:'secret raw query',product_id:'secret'})));
 assert.equal(r.status,'NO_SAFE_PRICED_CANDIDATES');assert.equal(r.fetched_count,10);assert.equal(r.counts.UNRESOLVED,10);
 assert(!JSON.stringify(r).includes('secret'));
});
test('explicit causes are distinct and exclusive; missing causes remain unknown',()=>{
 const rows=[{quantity_parse_failed:true},{postage:'送料別'},{offer_type_mismatch:true},{excluded_reason:'unsafe'},{shipping_lookup_pending:true},{}];
 const r=api.summarize(rows);for(const k of ['QUANTITY_PARSE_FAILED','SHIPPING_UNKNOWN','PRODUCT_MISMATCH','DANGEROUS_EXCLUDED','PENDING','UNRESOLVED'])assert.equal(r.counts[k],1);
 assert.equal(Object.values(r.counts).reduce((a,b)=>a+b),6);
});
test('invalid URL and non-finite price do not count as safe prices',()=>{
 assert.equal(api.reason({shipping_included_price:100,shipping_included_url:'https://evil.example'}),'DANGEROUS_EXCLUDED');
 assert.equal(api.reason({shipping_included_price:Infinity,shipping_included_url:'https://item.rakuten.co.jp/a/b/'}),'UNRESOLVED');
 assert.equal(api.reason({shipping_included_price:100,shipping_included_url:'https://item.rakuten.co.jp/a/b/'}),'PRICED_SAFE');
});
test('new diagnostic event has no raw query and respects operator scope',async()=>{
 const html=execFileSync('python',['tests/render_analytics_fixture.py'],{encoding:'utf8'});
 const dom=new JSDOM(html,{url:'https://stusaurus.github.io/daily-cost-jp/products/?test=1&q=private-address',runScripts:'dangerously',beforeParse(w){w.fetch=async()=>({ok:true,json:async()=>({products:[],page_count:1})});}});
 await new Promise(r=>setTimeout(r,50));
 const events=dom.window.dataLayer.filter(e=>e[0]==='event'&&e[1]==='purchase_search_diagnostics');
 assert.equal(events.length,2);
 for(const e of events){assert.equal(e[2].operator_test,'1');assert.equal(e[2].page_location,'https://stusaurus.github.io/daily-cost-jp/products/');assert(!JSON.stringify(e[2]).includes('private-address'));assert.equal(e[2].diagnostic_status,'API_RESPONSE_ZERO');}
 dom.window.close();
});
test('new purpose preserves existing affiliate event and attribution',()=>{
 const fs=require('node:fs');const dom=new JSDOM('<a href="https://item.rakuten.co.jp/a/b/" data-conversion-source="category" data-purchase-purpose="small">楽天</a>',{url:'https://stusaurus.github.io/daily-cost-jp/categories/tissue/?test=1',runScripts:'outside-only'});
 const w=dom.window;const events=[];w.gtag=(...a)=>events.push(a);w.eval(fs.readFileSync('scripts/analytics_runtime.js','utf8'));
 w.document.querySelector('a').addEventListener('click',e=>e.preventDefault());w.document.querySelector('a').click();
 const e=events.find(e=>e[1]==='affiliate_click');assert.equal(e[2].conversion_source,'category');assert.equal(e[2].purchase_purpose,'small');assert.equal(e[2].operator_test,'1');dom.window.close();
});
