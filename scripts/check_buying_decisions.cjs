/* Compare the visible checkout choices, links and actual analytics events.
 * A local output directory is the default. BUYING_DECISION_BASE_URL selects
 * the deployed site. Analytics and outbound purchase requests are blocked.
 */
'use strict';
const {chromium,webkit}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const http=require('node:http');

function observedChoices(cid){
  const choices=[];
  for(const card of document.querySelectorAll(`article.product-card[id^="${cid}-rank-"]`)){
    const link=card.querySelector('a.buy-button');
    const value=card.querySelector('.lab-price-value');
    const unit=card.querySelector('.lab-price-unit');
    if(cid==='tissue'&&unit?.textContent.trim()!=='／100組')continue;
    if(cid==='toilet-paper'&&!['／シングル10m','／ダブル10m'].includes(unit?.textContent.trim()))continue;
    if(link&&value&&unit)choices.push({id:card.id,url:link.href,
      price:Number(link.dataset.shippingPrice),unit:unit.textContent.trim(),
      value:Number(value.textContent.replace(/[^0-9.]/g,''))});
  }
  for(const card of document.querySelectorAll(`.step4-recommendations[data-step4-category="${cid}"] article.step4-purpose`)){
    const link=card.querySelector('a.buy-button');
    if(!link)continue;
    // The final unit is the normalized unit when both /roll and /10m appear.
    const units=Array.from(card.querySelectorAll('p')).flatMap(p=>
      Array.from(p.textContent.matchAll(/¥([\d,.]+)／([^\s·<]+)/g)));
    const final=units.at(-1);
    if(final)choices.push({id:card.id,url:link.href,price:Number(link.dataset.shippingPrice),
      value:Number(final[1].replaceAll(',','')),unit:'／'+final[2]});
  }
  return choices;
}

async function main(){
  const output=process.env.BUYING_DECISION_QA_DIR||'qa-buying-decisions';
  const expectActive=process.env.BUYING_DECISION_EXPECT_ACTIVE==='true';
  fs.mkdirSync(output,{recursive:true});
  let server;
  let base=process.env.BUYING_DECISION_BASE_URL;
  if(!base){
    const root=path.resolve(process.env.BUYING_DECISION_SITE_DIR||'site');
    server=http.createServer((req,res)=>{
      let rel=decodeURIComponent(new URL(req.url,'http://localhost').pathname).replace(/^\/daily-cost-jp\//,'');
      if(!rel||rel.endsWith('/'))rel+='index.html';
      const file=path.resolve(root,rel);
      if(!file.startsWith(root+path.sep)||!fs.existsSync(file)){res.writeHead(404);res.end();return;}
      const ext=path.extname(file);
      res.setHeader('Content-Type',({'.css':'text/css','.js':'text/javascript','.json':'application/json','.webp':'image/webp','.svg':'image/svg+xml','.png':'image/png'})[ext]||'text/html');
      res.end(fs.readFileSync(file));
    });
    await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
    base=`http://127.0.0.1:${server.address().port}/daily-cost-jp/`;
  }
  if(!base.endsWith('/'))base+='/';
  const results=[];
  try{
    const response=await fetch(base+'data.json');assert.equal(response.status,200);
    const catalog=await response.json();
    for(const type of [chromium,webkit]){
      const browser=await type.launch({headless:true});
      try{
        for(const width of [320,390,1440])for(const cid of ['laundry','tissue','toilet-paper']){
          const page=await browser.newPage({viewport:{width,height:1000}});
          const errors=[];page.on('pageerror',e=>errors.push(e.message));
          await page.route(/googletagmanager|google-analytics|googleadservices|doubleclick|googlesyndication|a8\.net|valuecommerce|hb\.afl\.rakuten\.co\.jp/,r=>r.abort());
          const response=await page.goto(base+`categories/${cid}/?test=1`,{waitUntil:'networkidle'});
          assert.equal(response.status(),200);
          assert.equal(await page.locator('h1').count(),1);
          const summary=page.locator('#buying-decisions');assert.equal(await summary.count(),1);
          const choices=await page.evaluate(observedChoices,cid);
          const purposeChoices=choices.filter(c=>c.id.startsWith(cid+'-purpose-'));
          if(expectActive)assert(purposeChoices.some(c=>c.id===cid+'-purpose-small'),
            'active-mode QA must exercise a real published small-pack offer: '+cid);
          const raw=catalog.categories[cid];
          const offers=[...raw.items,...(raw.purpose_candidates||[]),...(raw.small_pack_offer?[raw.small_pack_offer]:[])];
          const rows=summary.locator('tbody tr');assert(await rows.count()>=2);
          const selected=[];
          for(const row of await rows.all()){
            const id=await row.getAttribute('data-decision-target');
            const choice=choices.find(c=>c.id===id);assert(choice,'summary must target a rendered card');
            const target=page.locator('#'+id);assert.equal(await target.count(),1);
            const unitText=await row.locator('.decision-unit').innerText();
            const split=unitText.match(/^¥([\d,.]+)(／.+)$/);assert(split,'explicit comparison unit');
            assert.equal(split[2],choice.unit);
            const group=choices.filter(c=>c.unit===choice.unit);
            const label=await row.locator('th').innerText();
            if(label==='支払総額を抑える')assert.equal(choice.price,Math.min(...group.map(c=>c.price)));
            else assert(Math.abs(choice.value-Math.min(...group.map(c=>c.value)))<0.11,'lowest displayed unit cost');
            assert((await row.locator('td').first().innerText()).includes('¥'+choice.price.toLocaleString('ja-JP')));
            const buy=target.locator('a.buy-button');
            const href=await buy.getAttribute('href');
            const source=offers.find(o=>o.url===href&&Number(o.price)===choice.price&&o.postage==='送料込み');
            assert(source,'target price and Rakuten URL must match the accepted catalog');
            const expectedName=source.name;
            const renderedName=await row.locator('.decision-product').getAttribute('title');
            assert(renderedName&&expectedName.includes(renderedName.slice(-Math.min(20,renderedName.length))), 'product identity');
            const before=await page.evaluate(()=>(window.dataLayer||[]).filter(x=>x[0]==='event'&&x[1]==='affiliate_click').length);
            await row.locator('a').click();
            assert.equal(new URL(page.url()).hash,'#'+id);
            assert(await target.isVisible());
            const after=await page.evaluate(()=>(window.dataLayer||[]).filter(x=>x[0]==='event'&&x[1]==='affiliate_click').length);
            assert.equal(after,before,'internal choice navigation is not an affiliate click');
            selected.push({label,id,price:choice.price,unit:choice.unit});
          }
          const first=page.locator('#'+selected[0].id+' a.buy-button');
          const firstHref=await first.getAttribute('href');
          // A real pointer click exercises capture listeners while preventing
          // navigation; no request is sent to a merchant or affiliate host.
          await first.evaluate(el=>el.addEventListener('click',e=>e.preventDefault(),{once:true}));
          await first.click();
          const event=await page.evaluate(()=>Array.from(window.dataLayer||[]).filter(x=>x[0]==='event'&&x[1]==='affiliate_click').at(-1)?.[2]);
          assert(event,'affiliate event was emitted locally');
          assert.equal(event.operator_test,'1');assert.equal(event.category_id,cid);
          assert.equal(event.link_url,firstHref);assert.equal(event.shipping_included_price,selected[0].price);
          assert.equal(event.conversion_source,'category');
          assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'document overflow');
          assert.deepEqual(errors,[],'JavaScript errors');
          await summary.scrollIntoViewIfNeeded();
          await page.screenshot({path:path.join(output,`${type.name()}-${cid}-${width}.png`)});
          results.push({browser:type.name(),width,category:cid,status:'PASS',purpose_choices:purposeChoices.length,selected,operator_test:event.operator_test});
          await page.close();
        }
      }finally{await browser.close();}
    }
  }finally{
    if(server)await new Promise(resolve=>server.close(resolve));
    fs.writeFileSync(path.join(output,'report.json'),JSON.stringify({base,expectActive,results},null,2));
  }
  console.log('BUYING_DECISIONS_QA '+JSON.stringify({checked:results.length,failed:0}));
}
main().catch(error=>{console.error(error);process.exitCode=1;});
