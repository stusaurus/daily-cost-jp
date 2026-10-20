const { chromium } = require('playwright');
const fs = require('node:fs/promises');
const ROOT = 'https://stusaurus.github.io/daily-cost-jp/';
const {requestPolicy} = require('./step3_ui_audit.cjs');
const {isRakutenHref} = require('./ga4_live_cta_audit.cjs');
const report = { at: new Date().toISOString(), browser: '', pages: [], interactions: [], errors: [],
  analytics: 'NETWORK_BLOCKED', affiliate_navigation: 'URL_VALIDATION_ONLY', blocked_requests: 0 };
async function isolate(context, receipt) {
  // Context routing also covers a future popup's first request. Service workers
  // are disabled by the caller so they cannot bypass this policy.
  await context.route('**/*', route => {
    const decision = requestPolicy(route.request().url(), route.request().resourceType());
    // This existing live QA intentionally exercises the read-only Worker API.
    // Every other external origin is denied by the shared STEP3 allowlist.
    if (decision === 'block') { receipt.blocked_requests++; return route.abort(); }
    return route.continue();
  });
}
async function inspectAffiliateLink(link) {
  const href = await link.getAttribute('href');
  if (!isRakutenHref(href)) throw Error('Invalid Rakuten purchase URL');
  return {href, status:'URL_VALIDATED_NO_CLICK', destination:'NOT_REQUESTED'};
}
async function check(label, fn) {
  try { const data = await fn(); report.interactions.push({ label, status:'observed', ...data }); }
  catch(e) { report.interactions.push({ label, status:'failed', error:e.message }); }
}
async function inspect(page, width, slug) {
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(async()=>{for(let y=0;y<document.body.scrollHeight;y+=700){window.scrollTo(0,y);await new Promise(r=>setTimeout(r,80));}window.scrollTo(0,0);});
  await page.waitForTimeout(1000);
  const geometry = await page.evaluate(() => {
    const vw = innerWidth;
    const visible = el => { const r = el.getBoundingClientRect(); const s=getComputedStyle(el); return r.width>0 && r.height>0 && s.visibility!=='hidden' && s.display!=='none'; };
    const overflow = [...document.querySelectorAll('main *,header *,nav *,h1')].filter(visible).filter(el => {
      const r=el.getBoundingClientRect();
      if(el.closest('.comparison-table-wrap'))return false;
      return r.left < -1 || r.right > vw+1;
    }).map(el=>({tag:el.tagName,class:el.className,text:el.textContent.trim().slice(0,100),right:el.getBoundingClientRect().right})).slice(0,30);
    const clipped = [...document.querySelectorAll('h1,h2,h3,.name,.price,.product-name,.product-name-short,.exact-name')].filter(visible).filter(el=> {
      const s=getComputedStyle(el);return (s.overflow==='hidden' || s.overflowY==='hidden') && el.scrollHeight>el.clientHeight+2 && s.textOverflow!=='ellipsis';
    }).map(el=>el.textContent.trim().slice(0,100));
    const controls=[...document.querySelectorAll('main button,main a.btn,main a.product-cta,nav a,input')].filter(visible).map(el=>({text:el.textContent.trim().slice(0,50),width:el.getBoundingClientRect().width,height:el.getBoundingClientRect().height}));
    return { viewport:vw, documentWidth:document.documentElement.scrollWidth, overflow,clipped,controls };
  });
  const links = await page.locator('a[href*="hb.afl.rakuten.co.jp"]').evaluateAll(els=>els.map(el=>({text:el.textContent.trim(),url:el.href,rel:el.rel})));
  await page.screenshot({ path:`qa-evidence/${width}-${slug}.png`, fullPage:true });
  await fs.writeFile(`qa-evidence/${width}-${slug}.txt`, await page.locator('body').innerText());
  report.pages.push({width,slug,url:page.url(),title:await page.title(),...geometry,affiliateLinks:links});
  console.log(`${width} ${slug} viewport=${geometry.viewport} doc=${geometry.documentWidth} overflowing=${geometry.overflow.length} clipped=${geometry.clipped.length}`);
}
async function main(){
  await fs.mkdir('qa-evidence',{recursive:true});
  const browser=await chromium.launch();report.browser=browser.version();
  // QA must target the deployed revision, not the old Pages build.
  const deployment=await browser.newContext();
  let ready=false;
  for(let attempt=0;attempt<30;attempt++){
    const response=await deployment.request.get(ROOT+'products/?qa_revision=verified-shipping');
    const home=await deployment.request.get(ROOT+'?qa_revision=exact-init');
    if((await response.text()).includes('VERIFIED_SHIPPING_FALLBACK')&&(await home.text()).includes("document.addEventListener('DOMContentLoaded', () => {\n  const API = 'https://daily-cost-api.kiyo0625puma.workers.dev/api/product-search'")){ready=true;break;}
    console.log('Waiting for corrected Pages deployment');await new Promise(r=>setTimeout(r,20000));
  }
  await deployment.close();if(!ready)throw new Error('Corrected Pages revision was not deployed');
  for(const width of [1440,390,320]) {
    const context=await browser.newContext({viewport:{width,height:900},isMobile:width<500,hasTouch:width<500,deviceScaleFactor:1,locale:'ja-JP',serviceWorkers:'block'});
    await isolate(context,report);
    const page=await context.newPage();
    page.setDefaultTimeout(20000);
    page.on('pageerror',error=>report.errors.push({width,type:'pageerror',message:error.message}));
    const responses=[];page.on('response',async res=>{if(res.url().includes('/api/product-search')||res.url().includes('/api/shipping-lookup')){try{responses.push({url:res.url(),status:res.status(),body:await res.json()});}catch{}}});
    for(const [slug,path] of [['home',''],['laundry','categories/laundry/'],['tissue','categories/tissue/'],['toilet-paper','categories/toilet-paper/']]) {
      await check(`${width} ${slug}`,async()=>{
        await page.goto(ROOT+path+'?test=1',{waitUntil:'networkidle'});
        await inspect(page,width,slug);
        if(slug==='laundry') {
          await check(`${width} save and compare`,async()=>{
            await page.locator('[data-product-tool="save"]').first().waitFor({timeout:30000});
            await page.locator('[data-product-tool="save"]').first().click();
            await page.locator('#show-saved').click();
            const saved=await page.locator('#purchase-tool-panel').innerText();
            await page.locator('[data-product-tool="compare"]').nth(0).click();
            await page.locator('[data-product-tool="compare"]').nth(1).click();
            await page.locator('#show-comparison').click();
            const compared=await page.locator('#purchase-tool-panel').innerText();
            await inspect(page,width,'compare');
            await page.reload({waitUntil:'networkidle'});
            await page.locator('#show-saved').click();
            return { saved,compared,persisted:await page.locator('#purchase-tool-panel').innerText() };
          });
          await check(`${width} category affiliate URL (no outbound click)`,async()=>{
            const link=page.locator('a[href*="hb.afl.rakuten.co.jp"]').first();
            return inspectAffiliateLink(link);
          });
        }
        return { url:page.url() };
      });
    }
    await check(`${width} home search and store judge`,async()=>{
      await page.goto(ROOT+'?test=1',{waitUntil:'networkidle'});
      if(await page.locator('#exact-name').count()) {
        await page.locator('#exact-name').fill('アリエール 部屋干しプラス 本体 690g');await page.locator('#exact-store-price').fill('1000');await page.locator('#exact-search').click();
        await page.waitForFunction(()=>document.querySelector('#exact-status').textContent.length>0);
        await page.waitForFunction(()=>!document.querySelector('#exact-search').disabled,{},{timeout:90000});
        await page.locator('.exact-choose:not([disabled])').first().click();
        await page.locator('#exact-result.show').waitFor();
        report.interactions.push({label:`${width} exact comparison verdict`,status:'observed',text:await page.locator('#exact-result').innerText()});
        await page.locator('#exact-store-compare').screenshot({path:`qa-evidence/${width}-exact-compare.png`});
        await inspect(page,width,'store-judge');
      }
      const home=page.locator('#product-finder-home');
      await home.locator('input').fill('アリエール');await home.getByRole('button',{name:'探す',exact:true}).click();
      await page.waitForURL('**/products/**');
      await page.locator('#searchBtn').waitFor();
      await page.waitForFunction(()=>document.querySelector('#searchBtn')&&!document.querySelector('#searchBtn').disabled,{},{timeout:90000});
      await page.waitForFunction(()=>!document.body.innerText.includes('追加確認中'),{},{timeout:120000}).catch(()=>{});
      await inspect(page,width,'search-ariel');
      const link=page.locator('.product-result-link:not([data-shipping-price=""])').first();
      let clicked=null;
      if(await link.count())clicked=await inspectAffiliateLink(link);
      const events=await page.evaluate(()=> (window.dataLayer||[]).map(x=>Array.from(x)).filter(x=>x[0]==='event'&&x[1]==='affiliate_click'));
      return {text:(await page.locator('main').innerText()).slice(0,18000),clicked,events};
    });
    await check(`${width} Scottie search and affiliate`,async()=>{
      await page.goto(ROOT+'products/?test=1',{waitUntil:'networkidle'});
      await page.getByRole('searchbox').fill('スコッティ ティッシュペーパー');await page.getByRole('button',{name:'検索',exact:true}).click();
      await page.waitForFunction(()=>!document.querySelector('#searchBtn').disabled,{},{timeout:90000});
      await page.waitForFunction(()=>!document.body.innerText.includes('追加確認中'),{},{timeout:120000}).catch(()=>{});
      await inspect(page,width,'search-scottie');
      const link=page.locator('.product-result-link[data-shipping-price]:not([data-shipping-price=""])').first();
      const priced=await link.count();
      let clicked=null;
      if(priced)clicked=await inspectAffiliateLink(link);
      const events=await page.evaluate(()=> (window.dataLayer||[]).map(x=>Array.from(x)).filter(x=>x[0]==='event'&&x[1]==='affiliate_click'));
      return {priced,clicked,events};
    });
    await fs.writeFile(`qa-evidence/${width}-responses.json`,JSON.stringify(responses,null,2));
    await context.close();
  }
  await browser.close();
  await fs.writeFile('qa-evidence/report.json',JSON.stringify(report,null,2));
  console.log(JSON.stringify({pages:report.pages.length,failed:report.interactions.filter(x=>x.status==='failed').map(x=>({label:x.label,error:x.error})),errors:report.errors},null,2));
}
module.exports={isolate,inspectAffiliateLink};
if(require.main===module)main().catch(async e=>{report.fatal=e.message;await fs.writeFile('qa-evidence/report.json',JSON.stringify(report,null,2));console.error(e.message);process.exitCode=1;});
