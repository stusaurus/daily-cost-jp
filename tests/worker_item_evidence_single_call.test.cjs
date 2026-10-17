const test=require("node:test");
const assert=require("node:assert/strict");
const path=require("node:path");
const {pathToFileURL}=require("node:url");
const source=pathToFileURL(path.join(__dirname,"..","cloudflare-api","src","safe-index.js")).href;
const env={RAKUTEN_APPLICATION_ID:"app",RAKUTEN_ACCESS_KEY:"key",RAKUTEN_AFFILIATE_ID:"aff"};
const exact="https://item.rakuten.co.jp/safe-shop/real-item/";
const affiliate="https://hb.afl.rakuten.co.jp/hgc/x/?pc="+encodeURIComponent(exact);
async function run(tag,{itemCode="safe-shop:sku",url=exact,upstream=200,itemUrl=exact}={}){
 const original=global.fetch;let calls=0;
 try{
  global.fetch=async (input)=>{
   calls++;
   const u=new URL(String(input));
   assert.equal(u.hostname,"openapi.rakuten.co.jp");
   assert.equal(u.searchParams.get("itemCode"),"safe-shop:sku");
   if(upstream===429)return new Response(null,{status:429});
   return new Response(JSON.stringify({items:[{
    itemName:"Coleman テント MODEL1 本体",itemCode:"safe-shop:sku",
    itemUrl,affiliateUrl:affiliate,itemPrice:14500,
    availability:1,postageFlag:0,taxFlag:0,
    itemPriceMin3:14500,itemPriceMax3:14500,
    shopCode:"safe-shop",mediumImageUrls:["https://thumbnail.image.rakuten.co.jp/a.jpg"]
   }]}),{status:200});
  };
  const handler=(await import(source+"?single-evidence="+tag)).default;
  const req=new Request("https://example.workers.dev/api/item-evidence?url="+encodeURIComponent(url)+"&itemCode="+encodeURIComponent(itemCode),{headers:{Origin:"https://stusaurus.github.io"}});
  const response=await handler.fetch(req,env);
  return {response,body:await response.json(),calls};
 }finally{global.fetch=original;}
}

test("API evidence: exact code+URL makes one upstream call without seller HTML or shop search",async()=>{
 const r=await run("match");
 assert.equal(r.calls,1);
 assert.equal(r.response.status,200);
 assert.equal(r.body.found,true);
 assert.equal(r.body.lookup_method,"exact_item_code_only");
 assert.equal(r.body.postage_flag,0);
 assert.equal(r.body.purchasable_min_price,14500);
 assert.equal(r.body.seller_variant_verified,false);
});
test("API evidence: unrelated seller code is rejected before upstream call",async()=>{
 const r=await run("wrongshop",{itemCode:"another:sku"});
 assert.equal(r.calls,0);assert.equal(r.response.status,400);assert.equal(r.body.found,false);
});
test("API evidence: item code result with another product URL is never substituted",async()=>{
 const r=await run("related",{itemUrl:"https://item.rakuten.co.jp/safe-shop/related/"});
 assert.equal(r.calls,1);assert.equal(r.response.status,200);
 assert.equal(r.body.found,false);assert.equal(r.body.reason,"exact_item_not_found");
});
test("API evidence: itemUrl may be official affiliate URL when it redirects to exactly the same product",async()=>{
 const r=await run("affiliate-item-url",{itemUrl:affiliate});
 assert.equal(r.calls,1);assert.equal(r.response.status,200);
 assert.equal(r.body.found,true);assert.equal(r.body.item_url,exact);
});
test("API evidence: 429 stops immediately and propagates safely",async()=>{
 const r=await run("429",{upstream:429});
 assert.equal(r.calls,1);assert.equal(r.response.status,502);
 assert.equal(r.body.found,false);assert.equal(r.body.upstream_status,429);
 assert.equal(JSON.stringify(r.body).includes("key"),false);
});
