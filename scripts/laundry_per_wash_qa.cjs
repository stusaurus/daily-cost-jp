/* Real calculator interaction, with external traffic blocked. */
const assert=require('node:assert/strict');
module.exports=async function(browser,origin){
  for(const width of [320,390,1440]){
    const page=await browser.newPage({viewport:{width,height:1000}}),errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/*',r=>new URL(r.request().url()).origin===origin?r.continue():r.abort());
    try{
      const response=await page.goto(origin+'/daily-cost-jp/tools/laundry-cost-per-wash/?test=1');
      assert.equal(response.status(),200);
      assert.equal(await page.locator('h1').count(),1);
      assert.equal(await page.locator('link[rel=canonical]').getAttribute('href'),
        'https://stusaurus.github.io/daily-cost-jp/tools/laundry-cost-per-wash/');
      assert(await page.locator('meta[name=description]').getAttribute('content'));
      await page.locator('#wash-sample').click();
      assert.equal(await page.locator('#wash-a-cost').innerText(),'17.94円');
      assert.equal(await page.locator('#wash-b-cost').innerText(),'15.67円');
      assert.equal(await page.locator('#wash-month-diff').innerText(),'45.47円');
      assert.equal(await page.locator('#wash-year-diff').innerText(),'545.60円');
      assert(await page.locator('#wash-example-note').isVisible());
      await page.locator('#wash-a-shipping').fill('500');
      assert(await page.locator('#wash-result').isHidden());
      assert(await page.locator('#wash-example-note').isVisible());
      await page.locator('button[type=submit]').click();
      assert.equal(await page.locator('#wash-a-cost').innerText(),'32.94円');
      await page.locator('#wash-a-unit').selectOption('g');
      assert(await page.locator('#wash-result').isHidden());
      await page.locator('#wash-a-content').fill('');
      await page.locator('button[type=submit]').click();
      assert(await page.locator('#wash-result').isHidden());
      assert.match(await page.locator('#wash-error').innerText(),/入力/);
      await page.locator('button[type=reset]').click();
      assert(await page.locator('#wash-example-note').isHidden());
      assert.equal(await page.locator('#wash-a-price').inputValue(),'');
      await page.locator('#wash-sample').click();
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'calculator overflow '+width);
      const attribution=await page.evaluate(()=>({operator:window.__operatorTest,
        layer:(window.dataLayer||[]).map(x=>Array.from(x))}));
      assert(attribution.layer.some(x=>JSON.stringify(x).includes('operator_test')),'operator attribution missing');
      assert(await page.locator('a[href="/daily-cost-jp/categories/laundry/"]').count()>=3);
      assert.equal(await page.locator('.purchase-horizon a[href="/daily-cost-jp/categories/laundry/"]').count(),1);
      assert.equal(await page.locator('#wash-purchase-count').innerText(),'3か月・60回分');
      assert.equal(await page.locator('#wash-a-payment').innerText(),'1,196.00円');
      assert.equal(await page.locator('#wash-b-payment').innerText(),'1,880.00円');
      assert.match(await page.locator('#wash-purchase-tradeoff').innerText(),/逆転/);
      assert.deepEqual(errors,[]);
      await page.screenshot({path:`qa-search/laundry-calculator-${width}.png`,fullPage:true});
      console.log(JSON.stringify({page:'laundry-calculator',width,calculations:true,invalidCleared:true,fictionalNotice:true,overflow:false,errors}));
    }finally{await page.close();}
  }
};
