const test=require("node:test");
const assert=require("node:assert/strict");
const path=require("node:path");
const {pathToFileURL}=require("node:url");
const url=pathToFileURL(path.join(__dirname,"..","cloudflare-api","src","safe-index.js")).href;
const env={RAKUTEN_APPLICATION_ID:"app",RAKUTEN_ACCESS_KEY:"key",RAKUTEN_AFFILIATE_ID:"aff"};
const headers={Origin:"https://stusaurus.github.io"};
const json=data=>new Response(JSON.stringify(data),{status:200,headers:{"Content-Type":"application/json"}});
async function exercise(label,endpoint,upstreamHandler){
  const old=global.fetch;
  try{
    global.fetch=async input=>{
      const requestUrl=String(input);
      if(requestUrl.startsWith("https://openapi.rakuten.co.jp/"))return upstreamHandler(new URL(requestUrl));
      throw Error("Unexpected upstream URL");
    };
    const worker=(await import(url+"?rate-limit="+label)).default;
    const response=await worker.fetch(new Request("https://fake.worker.dev"+endpoint,{headers}),env);
    return {response,payload:await response.json()};
  }finally{global.fetch=old;}
}

test("product search propagates postage Item API 429 rather than claiming zero shipping results",async()=>{
  const r=await exercise("product-postage","/api/product-search?q=ST-310",upstream=>{
    if(upstream.pathname.includes("/Product/Search/"))return json({Products:[],pageCount:0,count:0});
    if(upstream.pathname.includes("IchibaItem"))return new Response(null,{status:429});
    throw Error("Unexpected API endpoint "+upstream.pathname);
  });
  assert.equal(r.response.status,502);
  assert.equal(r.payload.error,"rakuten_api_error");
  assert.equal(r.payload.upstream_status,429);
  assert.equal(JSON.stringify(r.payload).includes("key"),false);
});

test("shipping lookup exposes rate-limit status without shopper secrets",async()=>{
  const r=await exercise("shipping-rate","/api/shipping-lookup?code=4953571073101&name=ST-310",upstream=>{
    if(upstream.pathname.includes("IchibaItem"))return new Response(null,{status:429});
    throw Error("Unexpected API endpoint");
  });
  assert.equal(r.response.status,502);
  assert.equal(r.payload.found,false);
  assert.equal(r.payload.upstream_status,429);
  assert.equal(JSON.stringify(r.payload).includes("app"),false);
});

test("successful product search retains its existing response shape",async()=>{
  const r=await exercise("empty-success","/api/product-search?q=ST-310",upstream=>{
    if(upstream.pathname.includes("/Product/Search/"))return json({Products:[],pageCount:0,count:0});
    if(upstream.pathname.includes("IchibaItem"))return json({Items:[]});
    throw Error("Unexpected API endpoint");
  });
  assert.equal(r.response.status,200);
  assert.deepEqual(r.payload.products,[]);
  assert.equal(r.payload.shipping_lookup_count,0);
});
