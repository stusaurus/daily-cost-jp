const test = require("node:test");
const assert = require("node:assert/strict");
const {pathToFileURL} = require("node:url");
const path = require("node:path");
const workerUrl = pathToFileURL(path.join(__dirname, "..", "cloudflare-api", "src", "safe-index.js")).href;
const env = {RAKUTEN_APPLICATION_ID:"app", RAKUTEN_ACCESS_KEY:"key", RAKUTEN_AFFILIATE_ID:"aff"};
const origin = "https://stusaurus.github.io";
const itemUrl = "https://item.rakuten.co.jp/kkkkk/10000650/";
const related = "https://item.rakuten.co.jp/kkkkk/related/";
const affiliate = u => "https://hb.afl.rakuten.co.jp/hgc/test/?pc=" + encodeURIComponent(u);
const item = u => ({itemName:"SOTO レギュレーターストーブ ST-310",itemCode:"kkkkk:actual",itemPrice:7480,itemUrl:u,affiliateUrl:affiliate(u),shopCode:"kkkkk",shopName:"store",availability:1,mediumImageUrls:["https://thumbnail.image.rakuten.co.jp/test.jpg"]});
const request = () => new Request("https://example.workers.dev/api/item-lookup?url="+encodeURIComponent(itemUrl)+"&itemCode="+encodeURIComponent("kkkkk:stale")+"&q="+encodeURIComponent("ST-310"),{headers:{Origin:origin}});

async function exercise(scenario,label){
  const original = global.fetch;
  try {
    const calls = [];
    global.fetch = async input => {
      const url = String(input);calls.push(url);
      if (url === itemUrl) throw new Error("blocked item HTML");
      if (!url.startsWith("https://openapi.rakuten.co.jp/")) throw new Error("unexpected URL");
      const params = new URL(url).searchParams;
      if(params.has("itemCode")) return new Response(null,{status:scenario==="rate-limit"?429:404});
      if(params.has("keyword")) {
        if(scenario==="rate-limit") throw new Error("429 must stop before fallback");
        return new Response(JSON.stringify({items: [item(scenario==="related"?related:itemUrl)]}),{status:200,headers:{"content-type":"application/json"}});
      }
      throw new Error("unhandled API");
    };
    const worker=(await import(workerUrl+"?"+label)).default;
    const response=await worker.fetch(request(),env);
    return {response,body:await response.json(),calls};
  } finally {global.fetch=original;}
}

test("404 for a stale exact SKU falls back to verified same-shop exact URL",async()=>{
  const r=await exercise("exact","404-exact");
  assert.equal(r.response.status,200);
  assert.equal(r.body.found,true);
  assert.equal(r.body.item_url,itemUrl);
  assert.equal(r.body.affiliate_url,affiliate(itemUrl));
  assert.equal(r.body.lookup_method,"item_url_shop_search");
  assert.ok(r.calls.some(x=>new URL(x).searchParams.has("itemCode")));
  assert.ok(r.calls.some(x=>new URL(x).searchParams.has("keyword")));
});

test("404 fallback still rejects a closely named different seller item",async()=>{
  const r=await exercise("related","404-related");
  assert.equal(r.response.status,200);
  assert.equal(r.body.found,false);
  assert.equal(r.body.reason,"exact_item_not_found");
});

test("upstream 429 stays fail-closed and exposes status only, not credentials",async()=>{
  const r=await exercise("rate-limit","429-failure");
  assert.equal(r.response.status,502);
  assert.equal(r.body.found,false);
  assert.equal(r.body.error,"rakuten_api_error");
  assert.equal(r.body.upstream_status,429);
  assert.equal(JSON.stringify(r.body).includes("app"),false);
});
