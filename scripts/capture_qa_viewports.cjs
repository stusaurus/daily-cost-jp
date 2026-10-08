const {chromium}=require('playwright');
const fs=require('node:fs/promises');
(async()=>{
 await fs.mkdir('qa-viewports',{recursive:true});const browser=await chromium.launch();const checks=[];
 try{
 for(const width of [1440,390,320]){
  const context=await browser.newContext({viewport:{width,height:900},isMobile:width<500,hasTouch:width<500,locale:'ja-JP'});
  const page=await context.newPage();
  for(const [name,route] of [['home',''],['laundry','categories/laundry/'],['tissue','categories/tissue/'],['toilet-paper','categories/toilet-paper/']]){
   await page.goto('https://stusaurus.github.io/daily-cost-jp/'+route+'?test=1',{waitUntil:'networkidle'});
   await page.evaluate(()=>document.fonts.ready);
   await page.screenshot({path:`qa-viewports/${width}-${name}-viewport.png`});
   const initial=await page.evaluate(()=>({scrollY,documentWidth:document.documentElement.scrollWidth,backToTopVisible:getComputedStyle(document.querySelector('#back-to-top')).visibility}));
   if(initial.documentWidth!==width||initial.scrollY!==0||initial.backToTopVisible!=='hidden')throw new Error(`Initial viewport regression ${width} ${name}: ${JSON.stringify(initial)}`);
   await page.evaluate(()=>window.scrollTo({top:650,behavior:'instant'}));
   await page.locator('#back-to-top').waitFor({state:'visible'});
   await page.locator('#back-to-top').click();
   await page.waitForFunction(()=>scrollY===0);
   await page.locator('#back-to-top').waitFor({state:'hidden'});
   checks.push({width,name,...initial,afterScrollVisible:true,clickReturnsToTop:true});
  }
  await context.close();
 }
 await fs.writeFile('qa-viewports/report.json',JSON.stringify(checks,null,2));console.log(JSON.stringify(checks));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
