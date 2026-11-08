/* Public choice-flow evidence for the existing six-site release check.
 * Synthetic inputs stay inside a fresh context. No affiliate click is made;
 * analytics and advertising requests are blocked before navigation.
 */
'use strict';
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const ORIGIN='https://stusaurus.github.io';
const OUT=path.resolve('audit-results/six-site-choice-browser');
const SPECS=[
 ['daily','/daily-cost-jp/categories/laundry/'],
 ['baby','/baby-cost-jp/diapers/pants/m/'],
 ['food','/food-cost-jp/guides/pack-rice-24-servings-cost/'],
 ['kyo','/kyo-bodo-jp/scenes/two-player/'],
 ['pet','/pet-cost-jp/categories/pet-sheets/'],
 ['soto','/sotojitaku/camp/']
];
const BLOCK=/(?:googletagmanager\.com|google-analytics\.com|analytics\.google\.com|doubleclick\.net|googleadservices\.com|(?:^|\.)a8\.net|(?:^|\.)a8ad\.jp|afl\.rakuten\.co\.jp)/i;
async function exercise(page,id){
 if(id==='daily'){
  const section=page.locator('#buying-decisions');
  await section.waitFor();
  const links=await section.locator('a[href^="#"]').evaluateAll(ns=>ns.map(n=>n.getAttribute('href')));
  assert(links.length>0,'published price comparisons must lead to real product cards');
  for(const target of links)assert.equal(await page.locator(target).count(),1);
  await section.scrollIntoViewIfNeeded();
  return 'published comparison anchors resolve to product cards';
 }
 if(id==='baby'){
  const root=page.locator('[data-purchase-planner]');
  if(!await root.count())return 'CONDITIONAL: no eligible priced purchase planner';
  await root.locator('.purchase-size summary').click();
  await root.locator('[data-purchase-size-choice="7"]').click();
  assert.equal(await root.locator('[data-purchase-size-days]').inputValue(),'7');
  await root.locator('[data-purchase-stock]').fill('10000');
  await page.waitForFunction(()=>Array.from(document.querySelectorAll('[data-purchase-result]')).every(n=>n.textContent.includes('買い足し不要')));
  await root.scrollIntoViewIfNeeded();
  return 'size horizon 7 days; sufficient stock gives no-buy result';
 }
 if(id==='food'){
  const priced=page.locator('[data-rice-planner]');
  if(await priced.count()){
   await priced.locator('[data-rice-meal-choice="2"]').click();
   await priced.locator('[data-rice-stock-input]').fill('100000');
   await page.waitForFunction(()=>document.querySelector('[data-rice-planner-results]').textContent.includes('買い足し不要'));
   await priced.scrollIntoViewIfNeeded();
   return 'priced planner: 2 meals/day and stock give no-buy result';
  }
  const fallback=page.locator('[data-rice-quantity-only]');
  await fallback.waitFor();
  await fallback.locator('[data-rice-quantity-choice="2"]').click();
  await fallback.locator('[data-rice-quantity-stock]').fill('100000');
  await page.waitForFunction(()=>document.querySelector('[data-rice-quantity-summary]').textContent.includes('買い足し不要'));
  assert.equal(await fallback.locator('a[href*="rakuten"]').count(),0);
  await fallback.scrollIntoViewIfNeeded();
  return 'unpriced fallback: count-only no-buy, no invented purchase link';
 }
 if(id==='kyo'){
  const root=page.locator('[data-two-player-quick-filter]');
  await root.locator('[name="minutes"][value="30"]').check();
  await root.locator('[name="style"][value="cooperative"]').check();
  const shown=await root.locator('[data-two-game]:visible').evaluateAll(ns=>ns.map(n=>({time:Number(n.dataset.timeMax),coop:n.dataset.cooperative})));
  assert(shown.length>0&&shown.length<=3);
  assert(shown.every(n=>n.time<=30&&n.coop==='1'));
  await root.scrollIntoViewIfNeeded();
  return '30-minute cooperative filter only shows matching factual metadata';
 }
 if(id==='pet'){
  await page.locator('[data-group-button][data-group="regular"]').click();
  const panel=page.locator('[data-usage-panel]');
  if(await panel.evaluate(n=>n.tagName==='DETAILS'&&!n.open))await panel.locator('summary').click();
  await page.locator('[data-usage-preset="3"]').click();
  assert.equal(await page.locator('[data-usage-input]').inputValue(),'3');
  await page.locator('[data-sheet-stock-input]').fill('10000');
  await page.waitForFunction(()=>document.querySelector('[data-featured-usage]').textContent.includes('買い足し不要'));
  await panel.scrollIntoViewIfNeeded();
  return 'matching sheet size; 3/day and sufficient stock give no-buy result';
 }
 await page.locator('#main [data-start]').first().click();
 for(let step=0;step<7;step++)await page.locator('[data-next]').click();
 await page.locator('[data-go="owned"]').first().click();
 await page.locator('[data-owned="tent"]').click();
 await page.locator('[data-go="gear"]').first().click();
 assert.match(await page.locator('.purchase-insight').innerText(),/手持ち1/);
 await page.locator('[data-status="tent"]').selectOption('rent');
 assert.match(await page.locator('.purchase-insight').innerText(),/レンタル1/);
 await page.locator('[data-status="mat"]').selectOption('skip');
 assert.match(await page.locator('.purchase-insight').innerText(),/必要な道具を見送っています/);
 return 'owned, rental unbooked and missing essential equipment remain distinct';
}
async function main(){
 fs.mkdirSync(OUT,{recursive:true});
 const report={observedAt:new Date().toISOString(),analyticsBlocked:true,affiliateClicks:false,physicalDevice:false,checks:[]};
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  for(const width of [320,390,1440])for(const [id,pathname] of SPECS){
   const context=await browser.newContext({viewport:{width,height:900},locale:'ja-JP',isMobile:width<400,hasTouch:width<400,reducedMotion:'reduce'});
   await context.route('**/*',route=>{
    const u=new URL(route.request().url());
    return BLOCK.test(u.hostname)?route.fulfill({status:200,body:''}):route.continue();
   });
   const page=await context.newPage(),errors=[];
   page.setDefaultTimeout(15000);
   page.on('pageerror',e=>errors.push(e.message));
   const result={site:id,width,url:ORIGIN+pathname,status:'FAIL'};
   try{
    const response=await page.goto(result.url+'?test=1',{waitUntil:'domcontentloaded',timeout:45000});
    assert.equal(response.status(),200);
    result.evidence=await exercise(page,id);
    result.overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2);
    assert.equal(result.overflow,false,'horizontal overflow');
    assert.deepEqual(errors,[],'page errors');
    result.status=result.evidence.startsWith('CONDITIONAL:')?'CONDITIONAL':'PASS';
   }catch(e){result.error=e.message.slice(0,700);}
   await page.screenshot({path:path.join(OUT,id+'-'+width+'.png'),animations:'disabled'}).catch(()=>{});
   report.checks.push(result);
   console.log(id,width,result.status,result.error||result.evidence);
   await context.close();
  }
 }finally{
  await browser.close();
  report.failures=report.checks.filter(x=>x.status==='FAIL').length;
  fs.writeFileSync(path.join(OUT,'report.json'),JSON.stringify(report,null,2)+'\n');
 }
 if(report.failures)process.exitCode=1;
}
main().catch(e=>{console.error(e);process.exitCode=1;});
