/* Real-browser QA against generated output. No GA requests or purchases. */
const {chromium}=require('playwright');
const http=require('node:http');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
(async()=>{
 const root=path.resolve('site');
 const server=http.createServer((req,res)=>{
  let rel=decodeURIComponent(new URL(req.url,'http://localhost').pathname).replace(/^\/daily-cost-jp\//,'');
  if(rel.endsWith('/'))rel+='index.html';
  const file=path.resolve(root,rel);
  if(!file.startsWith(root+path.sep)||!fs.existsSync(file)){res.writeHead(404);res.end();return;}
  res.setHeader('Content-Type',file.endsWith('.css')?'text/css':file.endsWith('.js')?'text/javascript':file.endsWith('.json')?'application/json':file.endsWith('.webp')?'image/webp':'text/html');res.end(fs.readFileSync(file));
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 let browser;
 try{
  browser=await chromium.launch({executablePath:process.env.CHROME_PATH||chromium.executablePath(),headless:true,args:['--no-sandbox']});
  fs.mkdirSync('qa-search',{recursive:true});
  const catalog=JSON.parse(fs.readFileSync('site/data.json','utf8'));
  for(const width of [1440,390,320])for(const cid of ['laundry','tissue','toilet-paper']){
   const page=await browser.newPage({viewport:{width,height:1000}});
   await page.route(/googletagmanager|google-analytics/,route=>route.abort());
   const errors=[];page.on('pageerror',error=>errors.push(error.message));
   await page.goto(`http://127.0.0.1:${server.address().port}/daily-cost-jp/categories/${cid}/?test=1`,{waitUntil:'domcontentloaded'});
   assert.equal(await page.locator('h1').count(),1);
   assert.ok(await page.locator('.search-price-group').count()>0);
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'horizontal overflow '+cid+' '+width);
   if(cid==='tissue'){
     const sizeBox=page.locator('#tissue-buy-size');
     assert.equal(await sizeBox.count(),1,'tissue must offer shopping-size choices');
     assert.equal(await sizeBox.locator('.tissue-size-card').count(),2);
     const offer=catalog.categories.tissue.small_pack_offer;
     const smallLink=sizeBox.locator('.tissue-size-card').first().locator('a.size-link');
     const href=await smallLink.getAttribute('href');
     if(offer){
       assert.equal(href,offer.url,'small offer must match quality-checked catalog');
       assert.equal(Number(await smallLink.getAttribute('data-shipping-price')),offer.price);
       assert.equal(await smallLink.getAttribute('data-id'),offer.item_code);
       assert.match(await sizeBox.innerText(),new RegExp(''+catalog.categories.tissue.small_pack_boxes+'箱'));
     }else{
       assert.ok(href.startsWith('../../products/?q='),'missing small stock must only link to in-site search');
       assert.match(await sizeBox.innerText(),/候補がありません/);
     }
     // Final laboratory design removes inline CSS. Assert actual computed
     // button styling, not merely the existence of HTML class names.
     const linksToStyle=await sizeBox.locator('a.size-link').evaluateAll(nodes=>nodes.map(node=>{
       const css=getComputedStyle(node);
       return {display:css.display,minHeight:parseFloat(css.minHeight),
               background:css.backgroundColor,decoration:css.textDecorationLine};
     }));
     assert.equal(linksToStyle.length,2);
     for(const appearance of linksToStyle){
       assert.equal(appearance.display,'inline-flex','tissue CTA lost final shared stylesheet');
       assert.ok(appearance.minHeight>=44,'tissue CTA tap target shrank');
       assert.notEqual(appearance.background,'rgba(0, 0, 0, 0)','tissue CTA has no visible background');
       assert.equal(appearance.decoration,'none','tissue CTA looks like a plain text link');
     }
     assert.equal(await sizeBox.locator('.tissue-size-card').nth(1).locator('a[href="#tissue"]').count(),1);
   }
   const links=await page.locator('.search-price-group .buy-button').evaluateAll(nodes=>nodes.map(n=>({url:n.href,id:n.dataset.id,price:Number(n.dataset.shippingPrice),name:n.dataset.productName})));
   for(const link of links){const item=catalog.categories[cid].items.find(p=>p.url===link.url);assert.ok(item);assert.equal(item.price,link.price);assert.equal(item.item_code,link.id);}
   await page.locator('.search-price-group .buy-button').first().evaluate(n=>n.addEventListener('click',e=>e.preventDefault()));
   await page.locator('.search-price-group .buy-button').first().click();
   const events=await page.evaluate(()=>dataLayer.filter(x=>x[0]==='event'&&x[1]==='affiliate_click').map(x=>x[2]));
   assert.equal(events.length,1);assert.equal(events[0].operator_test,'1');assert.equal(events[0].site_id,'daily-cost-jp');assert.equal(events[0].traffic_environment,'development');assert.equal(events[0].category_id,cid);assert.equal(events[0].link_url,links[0].url);
   assert.deepEqual(errors,[]);
   await page.evaluate(()=>window.scrollTo(0,0));
   await page.screenshot({path:`qa-search/${cid}-${width}.png`,fullPage:true});
   console.log(JSON.stringify({cid,width,candidates:links.length,overflow:false,affiliate_events:1}));
   await page.close();
  }
 }finally{await browser?.close();server.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
