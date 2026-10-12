const {test}=require('node:test');
const assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
const {JSDOM}=require('jsdom');
const diagnostics=require('../scripts/step4_search_diagnostics.js');
const html=execFileSync('python',['tests/render_analytics_fixture.py'],{encoding:'utf8'});
const product={product_id:'fixture',name:'検証用洗剤 本体 690g',url:'https://product.rakuten.co.jp/fixture/'};
const flush=()=>new Promise(r=>setTimeout(r,60));

test('lookup errors, deadline, limit and unverified response remain distinct anonymous counts',()=>{
 const rows=['API_FAILURE','TIME_LIMIT','UNVERIFIED','NOT_ATTEMPTED'].map(shipping_lookup_status=>({shipping_lookup_status}));
 const result=diagnostics.summarize(rows);
 for(const reason of ['LOOKUP_API_FAILURE','LOOKUP_TIME_LIMIT','LOOKUP_UNVERIFIED','LOOKUP_NOT_ATTEMPTED'])assert.equal(result.counts[reason],1);
 assert.equal(result.counts.SHIPPING_UNKNOWN,0);assert.equal(result.counts.QUANTITY_PARSE_FAILED,0);
 assert.match(diagnostics.explanation(result),/API応答後も同一出品/);
 assert.match(diagnostics.explanation(result),/APIの失敗/);
 assert.equal(Object.values(result.counts).reduce((a,b)=>a+b),4);
 assert(!JSON.stringify(diagnostics.eventPayload(result,'final')).includes('検証用'));
});

for(const scenario of ['api-failed','one-valid-empty','malformed','hanging','verified','wrong-form','rejected-primary','deadline']){
 test('search recovery preserves prices and distinguishes '+scenario,async()=>{
  let clock=0;
  const dom=new JSDOM(html,{url:'https://stusaurus.github.io/daily-cost-jp/products/?test=1',runScripts:'dangerously',beforeParse(w){
   w.CSS={escape:s=>s};const timer=w.setTimeout.bind(w);
   w.setTimeout=(fn,ms,...args)=>timer(fn,[12000,20000,1150].includes(ms)?1:ms,...args);
   if(scenario==='deadline')w.Date.now=()=>clock;
   w.fetch=async(url,options)=>{
    if(url.includes('product-search'))return{ok:true,json:async()=>({products:[product]})};
    if(scenario==='hanging')return new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new Error('ABORTED'))));
    if(scenario==='deadline'){clock=90001;return{ok:true,json:async()=>({found:false})};}
    if(['verified','wrong-form','rejected-primary'].includes(scenario))return{ok:true,json:async()=>({found:true,shipping_included_price:1376,shipping_included_url:'https://item.rakuten.co.jp/fixture/verified/',shipping_match_name:scenario==='wrong-form'||scenario==='rejected-primary'&&url.includes('kiyo0625puma')?'検証用洗剤 詰め替え 690g':product.name})};
    if(scenario==='one-valid-empty'&&url.includes('stuffedsaurus'))return{ok:true,json:async()=>({found:false})};
    return{ok:scenario==='malformed',json:async()=>({error:'fixture failure'})};
   };
  }});
  const w=dom.window;const q=w.document.querySelector('#q');q.value='検証用';q.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));await flush();
  const priced=['verified','rejected-primary'].includes(scenario);
  const expected=priced?'PRICED_SAFE':scenario==='wrong-form'?'PRODUCT_MISMATCH':scenario==='deadline'?'LOOKUP_TIME_LIMIT':scenario==='one-valid-empty'?'LOOKUP_UNVERIFIED':'LOOKUP_API_FAILURE';
  const counts=JSON.parse(w.document.querySelector('#status').dataset.searchDiagnosticCounts);
  assert.equal(counts[expected],1,scenario);
  const events=w.dataLayer.filter(e=>e[1]==='purchase_search_diagnostics');assert.equal(events.length,2);
  assert(events.every(e=>e[2].operator_test==='1'&&!JSON.stringify(e[2]).includes('検証用')));
  assert(events.every(e=>Object.keys(e[2]).length<=25),'GA4 event parameter limit');
  const link=w.document.querySelector('.product-result-link');
  assert.equal(link.dataset.shippingPrice,priced?'1376':'');
  if(!priced)assert.equal(link.href,product.url);
  const recovery=w.document.querySelector('#search-recovery');assert.equal(recovery.hidden,priced);
  assert.equal(recovery.querySelectorAll('a').length,3);
  assert([...recovery.querySelectorAll('a')].every(a=>a.href.startsWith('https://stusaurus.github.io/daily-cost-jp/categories/')));
  dom.window.close();
 });
}

test('new query immediately clears previous diagnostic and recovery state',async()=>{
 let call=0;
 const dom=new JSDOM(html,{url:'https://stusaurus.github.io/daily-cost-jp/products/?test=1',runScripts:'dangerously',beforeParse(w){w.fetch=async()=>++call===1?{ok:true,json:async()=>({products:[]})}:new Promise(()=>{});}});
 const w=dom.window,q=w.document.querySelector('#q');
 q.value='先の検索';q.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));await flush();
 assert.equal(w.document.querySelector('#search-recovery').hidden,false);
 q.value='後の検索';q.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
 assert.equal(w.document.querySelector('#search-recovery').hidden,true);
 assert.doesNotMatch(w.document.querySelector('#search-diagnostic-note').textContent,/取得できませんでした/);
 dom.window.close();
});

test('explicit bottles are checked first without reordering result identities',async()=>{
 const calls=[];const products=[{...product,product_id:'refill',name:'検証用洗剤 詰め替え 2600g'},{...product,product_id:'bottle'}];
 const dom=new JSDOM(html,{url:'https://stusaurus.github.io/daily-cost-jp/products/?test=1',runScripts:'dangerously',beforeParse(w){w.CSS={escape:s=>s};const timer=w.setTimeout.bind(w);w.setTimeout=(f,ms,...a)=>timer(f,ms===1150?1:ms,...a);w.fetch=async url=>{calls.push(url);return{ok:true,json:async()=>url.includes('product-search')?{products}:{found:false}}};}});
 const w=dom.window,q=w.document.querySelector('#q');q.value='検証用';q.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));await flush();
 assert.match(decodeURIComponent(calls[1]),/本体/);
 assert.deepEqual([...w.document.querySelectorAll('.card')].map(c=>c.dataset.productId),['refill','bottle']);
 dom.window.close();
});

test('short query invalidates a previous in-flight product response',async()=>{
 let resolve;
 const dom=new JSDOM(html,{url:'https://stusaurus.github.io/daily-cost-jp/products/?test=1',runScripts:'dangerously',beforeParse(w){w.fetch=()=>new Promise(r=>resolve=r);}});
 const w=dom.window,q=w.document.querySelector('#q');q.value='前の検索';q.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
 q.value='あ';q.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
 resolve({ok:true,json:async()=>({products:[product]})});await flush();
 assert.equal(w.document.querySelectorAll('.product-result-link').length,0);
 assert.equal(w.document.querySelector('#searchBtn').disabled,false);
 assert.match(w.document.querySelector('#status').textContent,/2文字以上/);
 assert.equal(w.dataLayer.filter(e=>e[1]==='realtime_product_search').length,0);
 dom.window.close();
});

test('verified offer becomes visible first while other lookups are still pending',async()=>{
 const products=[{...product,product_id:'refill',name:'検証用洗剤 詰め替え 2600g'},{...product,product_id:'bottle'}];
 const dom=new JSDOM(html,{url:'https://stusaurus.github.io/daily-cost-jp/products/?test=1',runScripts:'dangerously',beforeParse(w){w.CSS={escape:s=>s};w.fetch=async url=>{
  if(url.includes('product-search'))return{ok:true,json:async()=>({products})};
  if(decodeURIComponent(url).includes('本体'))return{ok:true,json:async()=>({found:true,shipping_included_price:1376,shipping_included_url:'https://item.rakuten.co.jp/fixture/verified/',shipping_match_name:product.name})};
  return new Promise(()=>{});
 };}});
 const w=dom.window,q=w.document.querySelector('#q');q.value='検証用';q.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));await flush();
 assert.equal(w.document.querySelector('.card').dataset.productId,'bottle');
 assert.equal(w.document.querySelector('.product-result-link').dataset.shippingPrice,'1376');
 assert.equal(JSON.parse(w.document.querySelector('#status').dataset.searchDiagnosticCounts).PENDING,1);
 assert.equal(w.dataLayer.filter(e=>e[1]==='purchase_search_diagnostics').length,1);
 dom.window.close();
});
