#!/usr/bin/env node
'use strict';
/* Fixed public pages, deterministic measurements. No affiliate/Google requests. */
const fs=require('node:fs'), path=require('node:path'), crypto=require('node:crypto');
const {execFileSync}=require('node:child_process');
const SITE='https://stusaurus.github.io/daily-cost-jp/';
const PAGES=['/','/categories/laundry/','/categories/tissue/','/categories/toilet-paper/','/products/','/today/'];
const WIDTHS=[1440,390,320], TARGET='#home-ranking-hero .home-rank-all';
const CSS='scripts/design/laboratory.css';
const BLOCK='\n/* STEP3 home-ranking-link-tap-v1: restore the existing 44px interaction area. */\n#home-ranking-hero .home-rank-all{display:inline-flex;align-items:center;min-height:44px}\n';
const sha=value=>crypto.createHash('sha256').update(value).digest('hex');
const git=(...args)=>execFileSync('git',args,{encoding:'utf8'}).trim();
function repair(css){
 if(typeof css!=='string'||css.length>200000||css.includes('STEP3 home-ranking-link-tap-v1')||css.includes('.home-rank-all'))return null;
 if(!css.includes('.lab-masthead')||!css.includes('.lab-section-head'))return null;
 return css+BLOCK;
}
function requestPolicy(value,type){
 const u=new URL(value);if(u.protocol!=='https:'||u.username||u.password)return 'block';
 if(u.hostname==='thumbnail.image.rakuten.co.jp'&&type==='image')return 'image';
 if(['daily-cost-api.kiyo0625puma.workers.dev','daily-cost-api.stuffedsaurus.workers.dev'].includes(u.hostname)&&['/api/product-search','/api/shipping-lookup'].includes(u.pathname))return 'mock';
 if(u.origin===new URL(SITE).origin&&u.pathname.startsWith('/daily-cost-jp/')&&!u.pathname.includes('..'))return 'site';
 return 'block';
}
function contrast(a,b){const luminance=c=>c.map(n=>{n/=255;return n<=.04045?n/12.92:((n+.055)/1.055)**2.4}).reduce((s,n,i)=>s+n*[.2126,.7152,.0722][i],0);const x=luminance(a),y=luminance(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);}
function assess(dom){
 const out=[];const add=(code,selector,evidence)=>out.push({code,selector,evidence});
 if(dom.documentWidth>dom.width+2)add('HORIZONTAL_OVERFLOW','html',{documentWidth:dom.documentWidth,width:dom.width,elements:dom.overflow});
 for(const e of dom.controls){
  if(e.width<44||e.height<44)add(e.recipeTarget?'HOME_RANKING_TAP_TARGET':'SMALL_TAP_TARGET',e.selector,{width:e.width,height:e.height,minHeight:e.minHeight,display:e.display});
  if(!e.name)add('ACCESSIBLE_NAME_MISSING',e.selector,{tag:e.tag});
 }
 for(const e of dom.text){
  if(e.clipped&&!e.intentionalClamp)add('TEXT_CLIPPING_REVIEW',e.selector,{scrollHeight:e.scrollHeight,height:e.height});
  if(e.contrast!==null&&e.contrast<e.requiredContrast)add('CONTRAST_REVIEW',e.selector,{ratio:e.contrast,required:e.requiredContrast});
 }
 for(const e of dom.overlaps)add('TEXT_OVERLAP_REVIEW',e.selector,{occluder:e.occluder});
 const counts=new Map();return out.filter(e=>{const n=counts.get(e.code)||0;counts.set(e.code,n+1);return e.code==='HOME_RANKING_TAP_TARGET'||n<3;});
}
function measure(){
 const visible=e=>{const r=e.getBoundingClientRect(),c=getComputedStyle(e);return r.width>1&&r.height>1&&c.display!=='none'&&c.visibility!=='hidden'&&c.opacity!=='0'&&!e.closest('[hidden]')&&c.clipPath!=='inset(50%)';};
 const selector=e=>{if(e.id)return '#'+CSS.escape(e.id);const parts=[];for(let n=e;n&&n!==document.body&&parts.length<6;n=n.parentElement){if(n.id){parts.unshift('#'+CSS.escape(n.id));break;}parts.unshift(n.tagName.toLowerCase()+':nth-of-type('+([...n.parentElement.children].filter(s=>s.tagName===n.tagName).indexOf(n)+1)+')');}return parts.join('>');};
 const controls=[...document.querySelectorAll('a[href],button,input:not([type=hidden]),select')].filter(visible).slice(0,700).map(e=>{
  const r=e.getBoundingClientRect(),c=getComputedStyle(e),label=e.id&&document.querySelector('label[for="'+CSS.escape(e.id)+'"]');
  return {selector:e.matches('#home-ranking-hero .home-rank-all')?'#home-ranking-hero .home-rank-all':selector(e),recipeTarget:e.matches('#home-ranking-hero .home-rank-all'),tag:e.tagName,width:r.width,height:r.height,minHeight:c.minHeight,display:c.display,name:(e.getAttribute('aria-label')||label?.textContent||e.textContent||e.getAttribute('placeholder')||e.getAttribute('title')||'').trim().slice(0,70)};
 });
 const overflow=[...document.querySelectorAll('main *')].filter(visible).filter(e=>{const r=e.getBoundingClientRect();return (r.right>innerWidth+2||r.left<-2)&&!e.closest('.comparison-table-wrap');}).slice(0,20).map(e=>({selector:selector(e),left:e.getBoundingClientRect().left,right:e.getBoundingClientRect().right}));
 const text=[...document.querySelectorAll('h1,h2,h3,p,button')].filter(visible).slice(0,140).map(e=>{
  const c=getComputedStyle(e),r=e.getBoundingClientRect();let bg=null;
  for(let n=e;n;n=n.parentElement){const v=getComputedStyle(n).backgroundColor.match(/^rgba?\(([^)]+)\)$/);if(v){const a=v[1].split(',').map(Number);if(a.length===3||a[3]===1){bg=a.slice(0,3);break;}if(a[3]>0)break;}}
  const fg=c.color.match(/^rgb\(([^)]+)\)$/);return {selector:selector(e),height:r.height,scrollHeight:e.scrollHeight,clipped:e.scrollHeight>e.clientHeight+2&&['hidden','clip'].includes(c.overflowY),intentionalClamp:c.webkitLineClamp!=='none'&&c.webkitLineClamp!=='0',fg:fg?fg[1].split(',').map(Number):null,bg,requiredContrast:parseFloat(c.fontSize)>=24||(parseFloat(c.fontSize)>=18.66&&Number(c.fontWeight)>=700)?3:4.5};
 });
 const overlaps=[];
 for(const e of [...document.querySelectorAll('h1,h2,h3,button')].filter(visible).slice(0,120)){const r=e.getBoundingClientRect();if(r.top<100||r.bottom>innerHeight)continue;const n=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);if(n&&!e.contains(n)&&!n.contains(e))overlaps.push({selector:selector(e),occluder:selector(n)});}
 const target=document.querySelector('#home-ranking-hero .home-rank-all');
 const targetInfo=target?{count:document.querySelectorAll('#home-ranking-hero .home-rank-all').length,href:target.getAttribute('href'),tag:target.tagName,rect:{width:target.getBoundingClientRect().width,height:target.getBoundingClientRect().height},display:getComputedStyle(target).display,minHeight:getComputedStyle(target).minHeight,color:getComputedStyle(target).color,font:getComputedStyle(target).font}:null;
 const protectedState={title:document.title,meta:[...document.querySelectorAll('meta,link[rel=canonical]')].map(n=>n.outerHTML),links:[...document.querySelectorAll('a')].map(n=>[n.getAttribute('href'),[...n.attributes].filter(a=>a.name.startsWith('data-')||a.name==='rel').map(a=>[a.name,a.value])]),scripts:[...document.scripts].map(n=>[n.getAttribute('src'),n.textContent]),text:document.body.textContent};
 return {width:innerWidth,documentWidth:document.documentElement.scrollWidth,h1Count:document.querySelectorAll('h1').length,controls,overflow,text,overlaps,target:targetInfo,protectedState};
}
async function interactions(page,pathname){
 const results=[];
 if(pathname==='/'&&await page.locator('#judge-category').count()){await page.locator('#judge-category').selectOption('tissue');if(!/箱/.test(await page.locator('#judge-unit').innerText()))throw Error('Category unit selection failed');await page.locator('#judge-button').click();if(!/入力してください/.test(await page.locator('#judge-result').innerText()))throw Error('Judge empty-input validation failed');results.push('category-selector-and-empty-price-validation');}
 if(pathname==='/products/'){
  const field=page.locator('#q');if(await field.count()!==1)throw Error('Search input missing');
  await field.fill('x');await page.locator('#searchBtn').click();
  if(!/2文字以上/.test(await page.locator('#status').innerText()))throw Error('Short search validation failed');
  await field.fill('STEP3監査');await page.locator('#searchBtn').click();
  await page.waitForFunction(()=>document.querySelector('#status')?.textContent.includes('候補：0件'));
  if(await page.locator('#searchBtn').isDisabled())throw Error('Search remained disabled');
  results.push('search-validation-and-mocked-empty-response');
 }else{
  const compare=page.locator('[data-product-tool=compare]');
  if(await compare.count()<2)throw Error('Comparison targets unavailable');
  await compare.nth(0).click();await compare.nth(1).click();await page.locator('#show-comparison').click();
  if(!await page.locator('#purchase-tool-panel').isVisible())throw Error('Comparison panel failed');
  if(await page.locator('#purchase-tool-panel a[data-conversion-source=comparison]').count()<1)throw Error('Comparison attribution missing');
  const save=page.locator('[data-product-tool=save]').first();await save.click();await page.locator('#show-saved').click();
  if(await page.locator('#purchase-tool-panel a[data-conversion-source=saved]').count()<1)throw Error('Saved panel failed');
  await page.reload({waitUntil:'domcontentloaded'});await page.locator('#show-saved').click();
  if(await page.locator('#purchase-tool-panel a[data-conversion-source=saved]').count()<1)throw Error('Saved persistence failed');
  results.push('compare-save-and-reload-persistence');
 }
 return results;
}
async function observe(browser,pathname,width,outDir,override=null,snapshot=false){
 const context=await browser.newContext({viewport:{width,height:900},locale:'ja-JP',reducedMotion:'reduce'});
 let cssHash=null,htmlHash=null,closing=false;const networkErrors=[];
 await context.route('**/*',async route=>{
  try{
   const u=new URL(route.request().url()),policy=requestPolicy(u.href,route.request().resourceType());
   if(policy==='block')return await route.abort();
   if(policy==='mock')return await route.fulfill({json:{products:[],page_count:1},headers:{'access-control-allow-origin':'*'}});
   if(policy==='image')return snapshot?await route.abort():await route.continue();
   let rel=u.pathname.slice('/daily-cost-jp/'.length);if(!rel||rel.endsWith('/'))rel+='index.html';
   if(snapshot){const f=path.join('audit-results/step3-snapshot',rel);if(!fs.existsSync(f))return await route.abort();let body=fs.readFileSync(f);if(rel==='assets/laboratory.css'){cssHash=sha(body);if(override!==null)body=Buffer.from(override);}return await route.fulfill({body,contentType:rel.endsWith('.css')?'text/css':rel.endsWith('.js')?'text/javascript':rel.endsWith('.json')?'application/json':'text/html'});}
   if(rel!=='assets/laboratory.css')return await route.continue();
   const response=await route.fetch({timeout:20000});if(response.status()!==200){networkErrors.push('CSS_HTTP_UNAVAILABLE');return await route.fulfill({response});}
   let body=await response.body();cssHash=sha(body);if(override!==null)body=Buffer.from(override);return await route.fulfill({response,body});
  }catch(_){if(!closing)networkErrors.push('ROUTE_UNAVAILABLE');try{await route.abort();}catch(_){} }
 });
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message.slice(0,100)));page.setDefaultTimeout(10000);
 const record={path:pathname,viewport:width,url:SITE+pathname.slice(1)+'?test=1',status:'UNAVAILABLE',css_hash:null,issues:[],screenshot:null,reproduction:['Open URL with ?test=1','Set viewport width','Inspect DOM rectangle and computed CSS; no affiliate navigation']};
 try{
  const response=await page.goto(record.url,{waitUntil:'domcontentloaded',timeout:30000});await page.waitForTimeout(300);htmlHash=sha(await response.body());
  if(!snapshot)await page.waitForFunction(()=>[...document.images].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&r.top<innerHeight&&r.bottom>0&&e.currentSrc;}).every(e=>e.complete&&e.naturalWidth>0),{},{timeout:10000});
  const dom=await page.evaluate(measure);dom.text.forEach(e=>{e.contrast=e.fg&&e.bg?contrast(e.fg,e.bg):null;delete e.fg;delete e.bg;});
  record.http_status=response?.status();record.css_hash=cssHash;record.html_hash=htmlHash;record.protected_hash=sha(JSON.stringify(dom.protectedState));delete dom.protectedState;
  record.dom={width:dom.width,documentWidth:dom.documentWidth,h1Count:dom.h1Count,overflow:dom.overflow,controls_examined:dom.controls.length,text_nodes_examined:dom.text.length};record.issues=assess(dom);record.target=dom.target;record.keyboard=[];
  for(let i=0;i<3;i++){await page.keyboard.press('Tab');record.keyboard.push(await page.evaluate(()=>{const e=document.activeElement,c=getComputedStyle(e);return {tag:e.tagName,id:e.id,outlineWidth:c.outlineWidth,outlineStyle:c.outlineStyle,boxShadow:c.boxShadow};}));}
  if(record.keyboard.some(e=>e.tag!=='BODY'&&e.outlineStyle==='none'&&e.boxShadow==='none'))record.issues.push({code:'KEYBOARD_FOCUS_REVIEW',selector:'body',evidence:record.keyboard});
  const name=(pathname==='/'?'home':pathname.replace(/[^a-z0-9-]/g,'-'))+'-'+width+'.png';
  fs.mkdirSync(outDir,{recursive:true});await page.screenshot({path:path.join(outDir,name),fullPage:false});record.screenshot=name;record.screenshot_hash=sha(fs.readFileSync(path.join(outDir,name)));record.screenshot_scope='viewport';
  for(let i=0;i<record.issues.length;i++){const issue=record.issues[i];issue.url=record.url;issue.viewport=width;issue.reproduction=['Open URL with ?test=1','Set viewport to '+width+'px','Scroll to '+issue.selector,'Inspect DOM rectangle/computed CSS'];const image='issue-'+name.replace('.png','')+'-'+i+'.png';try{await page.locator(issue.selector).first().screenshot({path:path.join(outDir,image),timeout:3000});issue.screenshot=image;}catch(_){issue.screenshot=name;issue.screenshot_scope='viewport; element capture unavailable';}}
  if(pathname==='/'&&dom.target){await page.locator(TARGET).screenshot({path:path.join(outDir,'target-'+width+'.png')});record.target_screenshot='target-'+width+'.png';record.target_screenshot_hash=sha(fs.readFileSync(path.join(outDir,record.target_screenshot)));}
  record.interactions=await interactions(page,pathname);
  if(record.http_status!==200||dom.h1Count!==1||errors.length||networkErrors.length||!cssHash)throw Error('HTTP/heading/script/stylesheet validation failed');
  record.status='PASS';
 }catch(error){record.error=error.message.slice(0,180);}finally{record.page_errors=errors;record.network_errors=networkErrors;closing=true;await context.unrouteAll({behavior:'ignoreErrors'});await context.close();}
 return record;
}
function compare(before,after,original,candidate){
 if(before.length!==18||after.length!==18||repair(original)!==candidate)throw Error('Missing exact recipe or complete screen matrix');
 const differences=[];
 for(let i=0;i<before.length;i++){
  const a=before[i],b=after[i];
  if(a.path!==b.path||a.viewport!==b.viewport||a.status!=='PASS'||b.status!=='PASS'||a.css_hash!==sha(original)||b.css_hash!==sha(original)||a.protected_hash!==b.protected_hash)throw Error('Unknown/changed source or failed protected-state/interaction verification');
  if(b.dom.documentWidth>b.viewport+2)throw Error('Horizontal overflow; never hide it');
  const old=new Set(a.issues.map(v=>v.code+':'+v.selector));
  if(b.issues.some(v=>!old.has(v.code+':'+v.selector)))throw Error('New UI review finding introduced');
  if(a.path==='/'&&(!b.target||b.target.count!==1||b.target.rect.height<44||b.target.rect.width<44||a.target.href!==b.target.href||a.target.color!==b.target.color||a.target.font!==b.target.font))throw Error('Target remains small or protected appearance/destination changed');
  differences.push({path:a.path,viewport:a.viewport,before:a.screenshot_hash,after:b.screenshot_hash,protected_hash:a.protected_hash,target_before:a.target?.rect,target_after:b.target?.rect,target_before_image:a.target_screenshot_hash,target_after_image:b.target_screenshot_hash});
 }
 return differences;
}
async function main(){
 const {chromium}=require('playwright');const mode=process.argv[2]||'audit',snapshot=process.argv.includes('--snapshot');
 if(!['audit','verify','mock'].includes(mode))throw Error('Unknown audit mode');
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  if(mode==='mock'){
   fs.mkdirSync('audit-results/step3-mock',{recursive:true});
   for(const width of WIDTHS){const page=await browser.newPage({viewport:{width,height:900}});await page.setContent('<style>body{margin:18px}.lab-masthead{}.lab-section-head{}</style><section id="home-ranking-hero"><a class="home-rank-all" href="trends/">楽天総合ランキングTOP50を見る →</a></section>');
    const before=await page.locator(TARGET).boundingBox();await page.screenshot({path:`audit-results/step3-mock/before-${width}.png`});await page.addStyleTag({content:BLOCK});const after=await page.locator(TARGET).boundingBox();await page.screenshot({path:`audit-results/step3-mock/after-${width}.png`});if(!(before.height<44&&after.height>=44))throw Error('Mock recipe regression');await page.close();}
   console.log('STEP3 mock browser recipe: 1440/390/320 PASS');return;
  }
  const base=git('rev-parse','HEAD'),before=[];
  for(const pathname of PAGES)for(const width of WIDTHS){const r=await observe(browser,pathname,width,'audit-results/step3-ui/before',null,snapshot);before.push(r);console.log(JSON.stringify({path:pathname,width,status:r.status,target:r.target?.rect,error:r.error}));}
  const report={source:'daily-cost UI audit v1',site:SITE,base_sha:base,generated_at_utc:new Date().toISOString(),read_only:true,mode:snapshot?'snapshot':'live',status:before.every(r=>r.status==='PASS')?'PASS':'UNAVAILABLE',observations:before};
  fs.mkdirSync('audit-results/step3-ui',{recursive:true});fs.writeFileSync('audit-results/step3-ui/report.json',JSON.stringify(report,null,2));
  if(mode==='verify'){
   const planFile='audit-results/step2-plan.json';let original;
   if(fs.existsSync(planFile)){const plan=JSON.parse(fs.readFileSync(planFile));original=execFileSync('git',['show',plan.base_sha+':'+CSS],{encoding:'utf8'});}
   else{const ref=process.env.STEP3_BASE_SHA;if(!ref||!/^[a-f0-9]{40}$/.test(ref))throw Error('Missing fixed PR base SHA');original=execFileSync('git',['show',ref+':'+CSS],{encoding:'utf8'});}
   const candidate=fs.readFileSync(CSS,'utf8'),after=[];
   for(const pathname of PAGES)for(const width of WIDTHS)after.push(await observe(browser,pathname,width,'audit-results/step3-ui/after',candidate,snapshot));
   const differences=compare(before,after,original,candidate);
   fs.writeFileSync('audit-results/step3-ui/after.json',JSON.stringify(after,null,2));
   fs.writeFileSync('audit-results/step3-ui/differences.json',JSON.stringify(differences,null,2));
   fs.writeFileSync('audit-results/step3-ui/comparison.html','<!doctype html><meta charset="utf-8"><title>STEP3 fixed CSS before / after</title><style>body{font:16px sans-serif}section{display:flex;gap:30px;padding:20px;border-bottom:1px solid #ccc}img{max-width:100%}</style><h1>Fixed tap-area verification — no publication</h1>'+WIDTHS.map(w=>'<h2>'+w+'px</h2><section><div>Before<br><img src="before/target-'+w+'.png"></div><div>After<br><img src="after/target-'+w+'.png"></div></section>').join('')+'<p>Complete viewport screenshots and protected-state / geometry hashes: differences.json</p>');
   fs.writeFileSync('audit-results/step3-ui/verification.json',JSON.stringify({status:'PASS',base_sha:base,candidate_hash:sha(candidate),report_hash:sha(fs.readFileSync('audit-results/step3-ui/report.json')),differences_hash:sha(fs.readFileSync('audit-results/step3-ui/differences.json')),screens:18,mode:report.mode}));
   console.log('STEP3 exact CSS, protected state, interaction and 18-screen before/after verification PASS');
  }else if(report.status!=='PASS')throw Error('UI data unavailable; never considered healthy');
 }finally{await browser.close();}
}
module.exports={SITE,PAGES,WIDTHS,TARGET,CSS,BLOCK,sha,repair,requestPolicy,contrast,assess,compare};
if(require.main===module)main().catch(e=>{console.error('STEP3 audit stopped: '+e.message);process.exitCode=1});
