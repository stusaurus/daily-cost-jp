/* Deterministic browser evidence. All offers are synthetic; no purchases/GA. */
const fs=require('node:fs'),assert=require('node:assert/strict');
module.exports=async function(browser,localOrigin){
 const result={mode:'SYNTHETIC_SEARCH_RESPONSES',real_price_or_sales_proof:false,timers:'lookup pauses accelerated',checks:[]};
 const product={product_id:'qa-one',name:'検証用洗剤 本体 690g',url:'https://product.rakuten.co.jp/fixture/'};
 for(const width of [1440,390,320])for(const scenario of ['unverified','api-failed','rejected-primary'])for(const phase of ['before','after']){
  const context=await browser.newContext({viewport:{width,height:950},locale:'ja-JP'});
  const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{const timer=window.setTimeout.bind(window);window.setTimeout=(f,ms,...a)=>timer(f,ms===1150?0:ms,...a);});
  await page.route('**/*',async route=>{
   const u=new URL(route.request().url());
   if(/googletagmanager|google-analytics/.test(u.hostname)||u.hostname.endsWith('.rakuten.co.jp')&&route.request().isNavigationRequest())return route.abort();
   if(u.hostname.endsWith('.workers.dev')){
    if(u.pathname.endsWith('/product-search'))return route.fulfill({json:{products:Array.from({length:10},(_,i)=>({...product,product_id:'qa-'+i})),page_count:1}});
    if(scenario==='api-failed')return route.fulfill({status:503,json:{error:'synthetic'}});
    if(scenario==='rejected-primary')return route.fulfill({json:{found:true,shipping_included_price:1376,shipping_included_url:'https://item.rakuten.co.jp/fixture/verified/',shipping_match_name:u.hostname.includes('kiyo0625puma')?'検証用洗剤 詰め替え 690g':product.name}});
    return route.fulfill({json:{found:false}});
   }
   return route.continue();
  });
  try{
   const origin=phase==='before'?'https://stusaurus.github.io':localOrigin;
   await page.goto(origin+'/daily-cost-jp/products/?test=1',{waitUntil:'domcontentloaded'});
   await page.locator('#q').fill('検証用');await page.locator('#searchBtn').click();
   await page.waitForFunction(()=>window.dataLayer?.some(e=>e[1]==='purchase_search_diagnostics'&&e[2].diagnostic_phase==='final'));
   assert.equal(errors.length,0,errors.join(';'));
   const counts=JSON.parse(await page.locator('#status').getAttribute('data-search-diagnostic-counts'));
   const priced=await page.locator('.product-result-link[data-shipping-price="1376"]').count();
   if(phase==='after'){
    assert.equal(counts[scenario==='api-failed'?'LOOKUP_API_FAILURE':scenario==='unverified'?'LOOKUP_UNVERIFIED':'PRICED_SAFE'],10);
    assert.equal(priced,scenario==='rejected-primary'?10:0);
    if(!priced){
     assert(await page.locator('#search-recovery').isVisible());
     assert.equal(await page.locator('#search-recovery a').count(),3);
     const taps=await page.locator('#search-recovery a').evaluateAll(es=>es.map(e=>e.getBoundingClientRect().height));assert(taps.every(h=>h>=44));
     for(const href of await page.locator('#search-recovery a').evaluateAll(es=>es.map(e=>e.getAttribute('href'))))assert(fs.existsSync('site/'+href.replace('../','')+'index.html'));
    }
   }else {
    // The live baseline already contains PR #95. Verified fallback prices are
    // therefore expected for the rejected-primary fixture on BOTH revisions.
    // Unverified and API-failed candidates must still never show a price.
    assert.equal(priced,scenario==='rejected-primary'?10:0);
   }
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2),'horizontal overflow');
   const events=await page.evaluate(()=>window.dataLayer.filter(e=>e[1]==='purchase_search_diagnostics').map(e=>e[2]));
   assert.equal(events.length,2);assert(events.every(e=>e.operator_test==='1'&&!JSON.stringify(e).includes('検証用')));
   assert.equal(await page.evaluate(()=>window.dataLayer.filter(e=>e[1]==='affiliate_click').length),0);
   await page.screenshot({path:`qa-search/${phase}-search-${scenario}-${width}.png`,fullPage:true});
   result.checks.push({width,scenario,phase,priced,status:'PASS',counts,analytics:'BLOCKED',affiliate_navigation:'BLOCKED'});
  }finally{await context.close();}
 }
 fs.writeFileSync('qa-search/search-recovery-report.json',JSON.stringify(result,null,2));
 console.log('Search recovery browser checks: '+result.checks.length+' PASS');
};
