const {chromium}=require('playwright');
const fs=require('node:fs/promises');
(async()=>{
 await fs.mkdir('qa-viewports',{recursive:true});const browser=await chromium.launch();const checks=[];
 for(const width of [1440,390,320]){
  const context=await browser.newContext({viewport:{width,height:900},isMobile:width<500,hasTouch:width<500,locale:'ja-JP'});
  const page=await context.newPage();
  for(const [name,route] of [['home',''],['laundry','categories/laundry/'],['tissue','categories/tissue/'],['toilet-paper','categories/toilet-paper/']]){
   await page.goto('https://stusaurus.github.io/daily-cost-jp/'+route+'?test=1',{waitUntil:'networkidle'});
   await page.evaluate(()=>document.fonts.ready);
   await page.screenshot({path:`qa-viewports/${width}-${name}-viewport.png`});
   checks.push({width,name,...await page.evaluate(()=>({scrollY,documentWidth:document.documentElement.scrollWidth,backToTopVisible:getComputedStyle(document.querySelector('#back-to-top')).visibility}))});
  }
  await context.close();
 }
 await browser.close();await fs.writeFile('qa-viewports/report.json',JSON.stringify(checks,null,2));console.log(JSON.stringify(checks));
})().catch(e=>{console.error(e);process.exitCode=1;});
