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
  // The optional laundry value option is nested inside the everyday card.
  // Observe its actual rendered price, unit and merchant link independently:
  // the summary is only valid if the target is a visible, verifiable choice.
  if(cid==='laundry'){
    for(const card of document.querySelectorAll(
      '.step4-recommendations[data-step4-category="laundry"] .step4-value-choice'
    )){
      const link=card.querySelector('a.buy-button');
      const shown=card.textContent.match(/(100g|100ml)あたり¥[0-9,.]+から¥([0-9,.]+)になります/);
      if(link&&shown)choices.push({
        id:card.id,
        url:link.href,
        price:Number(link.dataset.shippingPrice),
        unit:'／'+shown[1],
        value:Number(shown[2].replaceAll(',',''))
      });
    }
  }
  return choices;
}

async function verifySoftener(browser,type,base,catalog,width,output){
  const page=await browser.newPage({viewport:{width,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const origin=new URL(base).origin;
  await page.route('**/*',route=>new URL(route.request().url()).origin===origin?route.continue():route.abort());
  try{
    const response=await page.goto(base+'categories/softener/?test=1',{waitUntil:'domcontentloaded'});
    assert.equal(response.status(),200);
    const calculator=page.locator('#softener-wash-calculator');
    const raw=catalog.categories.softener?.items||[];
    if(!await calculator.count()){
      assert.equal(raw.length,0,'softener calculator missing despite published catalog items');
      return {browser:type.name(),width,category:'softener',status:'NO_CATALOG_ITEMS'};
    }
    assert.equal(await calculator.count(),1);
    const rows=calculator.locator('[data-softener-row]');
    assert.equal(await rows.count(),2);
    const a=rows.nth(0),b=rows.nth(1);
    const select=row=>row.locator('[data-softener-offer]');
    const dose=row=>row.locator('[data-softener-dose]');
    const result=row=>row.locator('[data-softener-result]');
    const options=await select(a).locator('option[data-price]').evaluateAll(opts=>opts.map(o=>({
      value:o.value,card:o.dataset.sourceCard,price:Number(o.dataset.price),amount:Number(o.dataset.amount),
      unit:o.dataset.unit,text:o.textContent
    })));
    assert(options.length>0,'no verified offers');
    const cards=await page.locator('article.product-card').evaluateAll(nodes=>nodes.map(card=>({
      id:card.id,url:card.querySelector('a.buy-button')?.getAttribute('href'),
      name:card.querySelector('h3')?.getAttribute('title'),
      price:Number(card.querySelector('a.buy-button')?.dataset.shippingPrice)
    })));
    for(const opt of options){
      assert(['g','ml'].includes(opt.unit)&&opt.price>0&&opt.amount>0);
      // The rendered product name may have display-only campaign cleanup.
      // Bind to the exact card and raw merchant URL instead, checking the
      // accepted catalog's independent price/quantity arithmetic.
      assert(opt.card&&/^softener-rank-\d+$/.test(opt.card),'missing source card identity');
      const matches=cards.filter(c=>c.id===opt.card);
      assert.equal(matches.length,1,'source card must be unique');
      const c=matches[0];
      assert.equal(c.price,opt.price,'source card price mismatch');
      const offers=raw.filter(r=>r.url===c.url&&Number(r.price)===opt.price&&
        r.postage==='送料込み'&&r.metric==='100'+opt.unit);
      assert(offers.some(r=>Math.abs(Number(r.price)/Number(r.unit_price)*100-opt.amount)
        <=Math.max(0.01,opt.amount*0.000101)), 'source catalog quantity mismatch: '+opt.card);
    }
    assert(await dose(a).isDisabled());
    assert(await dose(b).isDisabled());
    const first=options[0],second=options.at(-1);
    await select(a).selectOption(first.value);
    await select(b).selectOption(second.value);
    const useA=Math.min(10,first.amount),useB=Math.min(20,second.amount);
    assert.match(await a.locator('[data-softener-dose-label]').innerText(),new RegExp(first.unit));
    assert.match(await b.locator('[data-softener-dose-label]').innerText(),new RegExp(second.unit));
    await dose(a).fill(String(useA));await dose(b).fill(String(useB));
    const money=n=>'¥'+n.toLocaleString('ja-JP',{minimumFractionDigits:2,maximumFractionDigits:2});
    const costA=first.price/first.amount*useA,costB=second.price/second.amount*useB;
    assert((await result(a).innerText()).includes(money(costA)));
    assert((await result(b).innerText()).includes(money(costB)));
    const difference=calculator.locator('#softener-wash-difference');
    const diff=Math.abs(costA-costB);
    if(diff<0.005)assert.match(await difference.innerText(),/ほぼ同じ/);
    else{
      assert((await difference.innerText()).includes(money(diff)));
      assert((await difference.innerText()).includes(costA<costB?'商品A':'商品B'));
    }
    await calculator.scrollIntoViewIfNeeded();
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'softener document overflow');
    for(const el of await calculator.locator('select,input').all()){
      const box=await el.boundingBox();assert(box&&box.width>0&&box.height>=44&&box.x>=0&&box.x+box.width<=width+1,'calculator input overflow or undersized touch target');
    }
    await page.screenshot({path:path.join(output,type.name()+'-softener-'+width+'.png')});
    await dose(b).fill(String(second.amount+1));assert.equal(await difference.innerText(),'');
    await select(a).selectOption('');assert(await dose(a).isDisabled());assert.equal(await dose(a).inputValue(),'');
    assert.deepEqual(errors,[]);
    return {browser:type.name(),width,category:'softener',status:'PASS',offers:options.length,costA,costB};
  }finally{await page.close();}
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
        for(const width of [320,390,1440]){
          const result=await verifySoftener(browser,type,base,catalog,width,output);
          results.push(result);
          console.log('SOFTENER_CALCULATOR_QA '+JSON.stringify(result));
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
