'use strict';
/* Before/after at production URLs with captured first-party bytes. Block all
   Google and affiliate navigations; network images only use the existing CDN. */
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
const BASE='https://stusaurus.github.io/daily-cost-jp/';
const pages=['','categories/laundry/','categories/tissue/','categories/toilet-paper/','products/','today/'];
const widths=[1440,390,320];
function protectedState(){
 return {head:[...document.querySelectorAll('title,meta,link[rel=canonical],script')].map(e=>e.outerHTML),
 cards:[...document.querySelectorAll('.product-card,.lab-archive-row,.deal-card')].map(e=>e.outerHTML),
 ranking:[...document.querySelectorAll('#home-ranking-hero,.lab-unit-groups,#normalized-comparison')].map(e=>e.outerHTML)};
}
async function inspect(browser,root,route,width,phase){
 const context=await browser.newContext({viewport:{width,height:950},locale:'ja-JP'});
 const errors=[];const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 await context.route('**/*',async r=>{
  const u=new URL(r.request().url());
  if(u.origin===new URL(BASE).origin&&u.pathname.startsWith('/daily-cost-jp/')){
   let rel=u.pathname.slice('/daily-cost-jp/'.length);if(!rel||rel.endsWith('/'))rel+='index.html';
   const file=path.join(root,rel);if(!fs.existsSync(file))return r.abort();
   const mime=rel.endsWith('.js')?'text/javascript':rel.endsWith('.json')?'application/json':rel.endsWith('.css')?'text/css':rel.endsWith('.svg')?'image/svg+xml':rel.endsWith('.webp')?'image/webp':rel.endsWith('.png')?'image/png':'text/html';
   return r.fulfill({body:fs.readFileSync(file),contentType:mime});
  }
  if(u.hostname==='thumbnail.image.rakuten.co.jp'&&r.request().resourceType()==='image')return r.continue();
  if(u.hostname.endsWith('.workers.dev'))return r.fulfill({json:{products:[],page_count:1,found:false}});
  return r.abort();
 });
 try{
  await page.goto(BASE+route+'?test=1',{waitUntil:'domcontentloaded',timeout:30000});
  await page.waitForTimeout(350);
  const protect=sha(JSON.stringify(await page.evaluate(protectedState)));
  const beforeWidth=await page.evaluate(()=>document.documentElement.scrollWidth);
  assert(beforeWidth<=width+2,'Horizontal overflow '+beforeWidth);
  assert.equal(errors.length,0,errors.join(';'));
  if(route==='products/'){
   await page.locator('#q').fill('アリエール');await page.locator('#searchBtn').click();
   await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('候補：0件'));
   assert.equal(await page.locator('#searchBtn').isDisabled(),false);
  }else{
   await page.locator('[data-product-tool=compare]').first().waitFor();
   const compares=page.locator('[data-product-tool=compare]');assert(await compares.count()>=2);
   await compares.nth(0).click();await compares.nth(1).click();await page.locator('#show-comparison').click();
   assert(await page.locator('#purchase-tool-panel a').count()>0);
   await page.locator('[data-product-tool=save]').first().click();await page.reload({waitUntil:'domcontentloaded'});
   await page.locator('[data-product-tool=save][aria-pressed=true]').first().waitFor();
   await page.locator('#show-saved').click();assert(await page.locator('#purchase-tool-panel a').count()>0);
   await page.locator('#purchase-tool-panel button').last().click();
  }
  if(phase==='after'&& !['products/','today/'].includes(route)){
   assert(await page.locator('.step4-recommendations').count()>0);
   const links=await page.locator('.step4-recommendations a').evaluateAll(es=>es.map(e=>({href:e.href,height:e.getBoundingClientRect().height,name:e.textContent.trim()})));
   assert(links.every(e=>e.height>=44&&e.name));
   for(const e of links.filter(e=>e.href.includes('rakuten.co.jp'))){const u=new URL(e.href);assert(u.protocol==='https:'&&u.hostname.endsWith('.rakuten.co.jp'));}
   const target=page.locator('.step4-recommendations').first();await target.scrollIntoViewIfNeeded();
   await target.screenshot({path:`audit-results/step4-qa/${phase}-${route.replaceAll('/','-')||'home'}-${width}-recommendations.png`});
  }
  await page.screenshot({path:`audit-results/step4-qa/${phase}-${route.replaceAll('/','-')||'home'}-${width}.png`,fullPage:true});
  return {route,width,phase,status:'PASS',protected_hash:protect,document_width:beforeWidth,operations:'search or compare/save/reload',affiliate_navigation:'BLOCKED',google_requests:'BLOCKED'};
 }finally{await context.close();}
}
(async()=>{
 fs.mkdirSync('audit-results/step4-qa',{recursive:true});
 const before=process.argv[2]||'audit-results/step4-preview-before',after=process.argv[3]||'audit-results/step4-preview-after';
 assert.equal(sha(fs.readFileSync(path.join(before,'data.json'))),sha(fs.readFileSync(path.join(after,'data.json'))));
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE||undefined,args:['--no-sandbox']});
 const rows=[];
 try{for(const route of pages)for(const width of widths){const a=await inspect(browser,before,route,width,'before'),b=await inspect(browser,after,route,width,'after');assert.equal(a.protected_hash,b.protected_hash,'Protected DOM changed');rows.push({before:a,after:b});console.log(route||'home',width,'PASS');}}
 finally{await browser.close();fs.writeFileSync('audit-results/step4-qa/report.json',JSON.stringify({mode:'captured-production-before-after',pairs:rows,all_pass:rows.length===18},null,2));}
})().catch(e=>{console.error(e);process.exitCode=1;});
