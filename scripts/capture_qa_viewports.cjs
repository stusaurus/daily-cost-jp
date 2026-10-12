'use strict';
const {chromium}=require('playwright');
const fs=require('node:fs/promises');
const {SITE,PAGES,WIDTHS,requestPolicy,interactions}=require('./step3_ui_audit.cjs');
async function capture(){
 await fs.mkdir('qa-viewports',{recursive:true});
 const policy=JSON.parse(await fs.readFile('scripts/step6_seo_policy.json','utf8'));
 const browser=await chromium.launch();const checks=[];
 const report={at:new Date().toISOString(),site:SITE,analytics_blocked:true,affiliate_navigation_blocked:true,
  search_api:'MOCKED_EMPTY_SAFE_RESPONSE',checks,publication:null};
 try{
 for(const width of WIDTHS){
 for(const route of PAGES){
  const context=await browser.newContext({viewport:{width,height:900},isMobile:width<500,hasTouch:width<500,locale:'ja-JP'});
  try{
   // Browser requests may reach only first-party pages and product images.
   // Existing feature checks use an empty API fixture; no affiliate destination
   // or Google analytics request can leave this context.
   await context.route('**/*',async route=>{
    const decision=requestPolicy(route.request().url(),route.request().resourceType());
    if(decision==='mock')return route.fulfill({json:{products:[],page_count:1},headers:{'access-control-allow-origin':'*'}});
    if(decision==='block')return route.abort();
    return route.continue();
   });
   const page=await context.newPage();page.setDefaultTimeout(15000);
   page.on('pageerror',error=>{report.page_errors??=[];report.page_errors.push({width,route,message:error.message});});
   if(!report.publication){
    const response=await context.request.get(SITE+'build-info.json');
    if(response.status()!==200)throw Error('Public build manifest unavailable');
    const info=await response.json();
    if(!/^[a-f0-9]{40}$/.test(info.commit))throw Error('Public build commit unavailable');
    if(process.env.EXPECTED_PUBLIC_COMMIT&&info.commit!==process.env.EXPECTED_PUBLIC_COMMIT)throw Error('Public revision changed; repeat against latest main');
    report.publication={commit:info.commit,run_id:info.run_id,catalog_updated_at:info.catalog_updated_at};
   }
    const name=route==='/'?'home':route.replace(/[^a-z0-9-]/g,'-');
    const response=await page.goto(SITE+route.slice(1)+'?test=1',{waitUntil:'networkidle'});
    if(response.status()!==200)throw Error('Public page unavailable: '+route);
    await page.evaluate(()=>document.fonts.ready);
    const initial=await page.evaluate(()=>({scrollY,documentWidth:document.documentElement.scrollWidth,
     backToTopVisible:getComputedStyle(document.querySelector('#back-to-top')).visibility,
     seoHelp:document.querySelectorAll('#step6-comparison-help').length}));
    const category=route.match(/^\/categories\/([^/]+)\/$/)?.[1];
    if(category&&Object.hasOwn(policy.pages,category)&&initial.seoHelp!==(policy.pages[category]?1:0))throw Error('Approved SEO content not reflected: '+route);
    if(initial.documentWidth!==width||initial.scrollY!==0||initial.backToTopVisible!=='hidden')throw Error(`Initial viewport regression ${width} ${route}`);
    await page.screenshot({path:`qa-viewports/${width}-${name}-viewport.png`});
    if(initial.seoHelp){
     await page.locator('#step6-comparison-help').screenshot({path:`qa-viewports/${width}-${name}-seo-help.png`});
    }
    await page.evaluate(()=>window.scrollTo({top:650,behavior:'instant'}));
    await page.locator('#back-to-top').waitFor({state:'visible'});
    await page.locator('#back-to-top').click();await page.waitForFunction(()=>scrollY===0);
    await page.locator('#back-to-top').waitFor({state:'hidden'});
    report.last_context=await page.evaluate(()=>({unitText:document.querySelector('#judge-unit')?.textContent,unitHTML:document.querySelector('#judge-unit')?.outerHTML,selected:document.querySelector('#judge-category')?.value,measurementContext:typeof window.dailyCostMeasurementContext}));
    const operations=await interactions(page,route);
    checks.push({width,route,...initial,operations,status:'PASS',clickReturnsToTop:true});
  }finally{await context.close();}
 }
 }
 report.status='PASS';console.log(JSON.stringify({status:report.status,checks:checks.length,publication:report.publication}));
 }catch(error){report.status='FAIL';report.error=error.message;throw error;}
 finally{await fs.writeFile('qa-viewports/report.json',JSON.stringify(report,null,2));await browser.close();}
}
if(require.main===module)capture().catch(e=>{console.error(e.message);process.exitCode=1;});
