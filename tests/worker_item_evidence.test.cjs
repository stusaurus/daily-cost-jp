const test=require("node:test");
const assert=require("node:assert/strict");
const path=require("node:path");
const {pathToFileURL}=require("node:url");
const source=pathToFileURL(path.join(__dirname,"..","cloudflare-api","src","safe-index.js")).href;
const env={RAKUTEN_APPLICATION_ID:"app",RAKUTEN_ACCESS_KEY:"key",RAKUTEN_AFFILIATE_ID:"affiliate"};
const exact="https://item.rakuten.co.jp/safe-shop/model-123/";
const itemCode="safe-shop:model-123";
const affiliate="https://hb.afl.rakuten.co.jp/hgc/x/?pc="+encodeURIComponent(exact);
async function getListing(suffix, fields) {
  const old=global.fetch;let calls=0;
  try{
    global.fetch=async input=>{
      calls++;
      const u=new URL(String(input));
      assert.ok(u.hostname==="openapi.rakuten.co.jp");
      assert.equal(u.searchParams.get("itemCode"),itemCode);
      const els=new Set((u.searchParams.get("elements")||"").split(","));
      for(const field of ["postageFlag","taxFlag","itemPriceMin3","itemPriceMax3","availability"])assert.ok(els.has(field),field);
      return new Response(JSON.stringify({items:[{
        itemName:"Coleman テント MODEL123 本体",itemCode,itemPrice:25000,itemUrl:exact,affiliateUrl:affiliate,
        shopCode:"safe-shop",availability:1,mediumImageUrls:["https://thumbnail.image.rakuten.co.jp/test.jpg"],...fields
      }]}),{status:200});
    };
    const worker=(await import(source+"?evidence="+suffix)).default;
    const url="https://example.workers.dev/api/item-lookup?url="+encodeURIComponent(exact)+"&itemCode="+encodeURIComponent(itemCode)+"&q=MODEL123";
    const response=await worker.fetch(new Request(url,{headers:{Origin:"https://stusaurus.github.io"}}),env);
    return {status:response.status,body:await response.json(),calls};
  }finally{global.fetch=old;}
}

test("2026 official tax/postage/availability/sellable range becomes visible without declaring SKU fixed",async()=>{
  const r=await getListing("verified",{postageFlag:0,taxFlag:0,itemPriceMin3:25000,itemPriceMax3:25000,itemPriceBaseField:"item_price_min3"});
  assert.equal(r.status,200);
  assert.equal(r.body.found,true);
  assert.equal(r.calls,1);
  assert.equal(r.body.item_code,itemCode);
  assert.equal(r.body.item_url,exact);
  assert.equal(r.body.affiliate_url,affiliate);
  assert.equal(r.body.postage_flag,0);
  assert.equal(r.body.tax_flag,0);
  assert.equal(r.body.availability,1);
  assert.equal(r.body.purchasable_min_price,25000);
  assert.equal(r.body.purchasable_max_price,25000);
  assert.equal(r.body.seller_variant_verified,false);
});
test("API omitted fields are unknown rather than inferred free shipping/tax included/single SKU",async()=>{
  const r=await getListing("missing",{});
  assert.equal(r.status,200);
  assert.equal(r.body.postage_flag,null);
  assert.equal(r.body.tax_flag,null);
  assert.equal(r.body.purchasable_min_price,null);
  assert.equal(r.body.purchasable_max_price,null);
  assert.equal(r.body.seller_variant_verified,false);
});
test("API flags preserve adverse evidence such as postage required or variable price",async()=>{
  const r=await getListing("adverse",{postageFlag:1,taxFlag:1,itemPriceMin3:25000,itemPriceMax3:44000});
  assert.equal(r.status,200);
  assert.equal(r.body.postage_flag,1);
  assert.equal(r.body.tax_flag,1);
  assert.equal(r.body.purchasable_min_price,25000);
  assert.equal(r.body.purchasable_max_price,44000);
  assert.equal(r.body.seller_variant_verified,false);
});
