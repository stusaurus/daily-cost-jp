const test=require("node:test");
const assert=require("node:assert/strict");
const {pathToFileURL}=require("node:url");
const path=require("node:path");

const workerUrl=pathToFileURL(path.join(__dirname,"..","cloudflare-api","src","safe-index.js")).href;
const env={
  RAKUTEN_APPLICATION_ID:"app",
  RAKUTEN_ACCESS_KEY:"key",
  RAKUTEN_AFFILIATE_ID:"aff"
};
const allowedOrigin="https://stusaurus.github.io";

function htmlFor(itemId){
  const info={itemId,purchaseInfo:{purchaseBySellType:{purchaseCondition:"enabled"}}};
  return "<html><script>\"itemInfoSku\":"+JSON.stringify(info)+"</script></html>";
}

test("exact item lookup returns only the requested Rakuten item",async()=>{
  const original=global.fetch;
  const direct="https://item.rakuten.co.jp/hobbyman/exact/";
  const affiliate="https://hb.afl.rakuten.co.jp/hgc/x/?pc="+encodeURIComponent(direct);
  try{
    global.fetch=async(input)=>{
      const url=String(input);
      if(url===direct)return new Response(htmlFor(123),{status:200,headers:{"content-type":"text/html"}});
      if(url.startsWith("https://openapi.rakuten.co.jp/")){
        return new Response(JSON.stringify({items:[{
          itemName:"N-BOX JF5 JF6 サンシェード フルセット",
          itemCode:"hobbyman:123",
          itemPrice:7980,
          itemUrl:direct,
          affiliateUrl:affiliate,
          shopName:"趣味職人",
          shopCode:"hobbyman",
          availability:1,
          mediumImageUrls:["https://example.com/item.jpg"]
        }]}),{status:200,headers:{"content-type":"application/json"}});
      }
      throw new Error("unexpected fetch "+url);
    };
    const worker=(await import(workerUrl+"?t=exact")).default;
    const request=new Request("https://example.workers.dev/api/item-lookup?url="+encodeURIComponent(direct)+"&q="+encodeURIComponent("N-BOX JF5 JF6"),{headers:{Origin:allowedOrigin}});
    const response=await worker.fetch(request,env);
    assert.equal(response.status,200);
    const body=await response.json();
    assert.equal(body.found,true);
    assert.equal(body.item_url,direct);
    assert.equal(body.affiliate_url,affiliate);
    assert.equal(body.price,7980);
    assert.equal(body.lookup_method,"item_url_item_code");
  }finally{global.fetch=original;}
});

test("item lookup rejects non-Rakuten URLs before any upstream fetch",async()=>{
  const original=global.fetch;
  let called=false;
  try{
    global.fetch=async()=>{called=true;throw new Error("should not fetch");};
    const worker=(await import(workerUrl+"?t=invalid")).default;
    const request=new Request("https://example.workers.dev/api/item-lookup?url="+encodeURIComponent("https://example.com/item"),{headers:{Origin:allowedOrigin}});
    const response=await worker.fetch(request,env);
    assert.equal(response.status,400);
    assert.equal(called,false);
    const body=await response.json();
    assert.equal(body.error,"invalid_rakuten_item_url");
  }finally{global.fetch=original;}
});

test("item lookup never substitutes a different same-shop item",async()=>{
  const original=global.fetch;
  const direct="https://item.rakuten.co.jp/hobbyman/exact/";
  const other="https://item.rakuten.co.jp/hobbyman/related/";
  try{
    global.fetch=async(input)=>{
      const url=String(input);
      if(url===direct)return new Response(htmlFor(123),{status:200});
      if(url.startsWith("https://openapi.rakuten.co.jp/")){
        return new Response(JSON.stringify({items:[{
          itemName:"N-BOX JF5 JF6 サンシェード",
          itemCode:"hobbyman:999",
          itemPrice:5980,
          itemUrl:other,
          affiliateUrl:"https://hb.afl.rakuten.co.jp/hgc/x/?pc="+encodeURIComponent(other),
          shopName:"趣味職人",
          shopCode:"hobbyman",
          availability:1,
          mediumImageUrls:["https://example.com/other.jpg"]
        }]}),{status:200,headers:{"content-type":"application/json"}});
      }
      throw new Error("unexpected fetch "+url);
    };
    const worker=(await import(workerUrl+"?t=related")).default;
    const request=new Request("https://example.workers.dev/api/item-lookup?url="+encodeURIComponent(direct)+"&q="+encodeURIComponent("N-BOX JF5 JF6"),{headers:{Origin:allowedOrigin}});
    const response=await worker.fetch(request,env);
    const body=await response.json();
    assert.equal(response.status,200);
    assert.equal(body.found,false);
    assert.equal(body.reason,"exact_item_not_found");
  }finally{global.fetch=original;}
});


test("explicit itemCode resolves the exact URL without scraping the Rakuten page",async()=>{
  const original=global.fetch;
  const direct="https://item.rakuten.co.jp/hobbyman/n-van-kurumat/";
  const affiliate="https://hb.afl.rakuten.co.jp/hgc/x/?pc="+encodeURIComponent(direct);
  const explicit="hobbyman:02k-a005-ca";
  let pageFetched=false;
  try{
    global.fetch=async(input)=>{
      const url=String(input);
      if(url===direct){pageFetched=true;throw new Error("page should not be needed");}
      if(url.startsWith("https://openapi.rakuten.co.jp/")){
        const parsed=new URL(url);
        assert.equal(parsed.searchParams.get("itemCode"),explicit);
        return new Response(JSON.stringify({items:[{
          itemName:"N-VAN JJ1/2系 車中泊ベッド マット",
          itemCode:explicit,
          itemPrice:19800,
          itemUrl:direct,
          affiliateUrl:affiliate,
          shopName:"趣味職人",
          shopCode:"hobbyman",
          availability:1,
          mediumImageUrls:["https://example.com/nvan.jpg"]
        }]}),{status:200,headers:{"content-type":"application/json"}});
      }
      throw new Error("unexpected fetch "+url);
    };
    const worker=(await import(workerUrl+"?t=explicit-code")).default;
    const request=new Request(
      "https://example.workers.dev/api/item-lookup?url="+encodeURIComponent(direct)+"&itemCode="+encodeURIComponent(explicit)+"&q="+encodeURIComponent("N-VAN JJ1/2"),
      {headers:{Origin:allowedOrigin}}
    );
    const response=await worker.fetch(request,env);
    assert.equal(response.status,200);
    const body=await response.json();
    assert.equal(body.found,true);
    assert.equal(body.lookup_method,"item_url_explicit_item_code");
    assert.equal(body.item_url,direct);
    assert.equal(body.affiliate_url,affiliate);
    assert.equal(pageFetched,false);
  }finally{global.fetch=original;}
});

test("explicit itemCode from another shop is rejected before upstream fetch",async()=>{
  const original=global.fetch;
  let called=false;
  try{
    global.fetch=async()=>{called=true;throw new Error("should not fetch");};
    const worker=(await import(workerUrl+"?t=wrong-shop-code")).default;
    const direct="https://item.rakuten.co.jp/hobbyman/exact/";
    const request=new Request(
      "https://example.workers.dev/api/item-lookup?url="+encodeURIComponent(direct)+"&itemCode="+encodeURIComponent("other-shop:123"),
      {headers:{Origin:allowedOrigin}}
    );
    const response=await worker.fetch(request,env);
    const body=await response.json();
    assert.equal(response.status,200);
    assert.equal(body.found,false);
    assert.equal(body.reason,"item_code_shop_mismatch");
    assert.equal(called,false);
  }finally{global.fetch=original;}
});


test("exact item lookup uses the requested page title to recover the exact listing",async()=>{
  const original=global.fetch;
  const direct="https://item.rakuten.co.jp/hobbyman/n-van-kurumat/";
  const affiliate="https://hb.afl.rakuten.co.jp/hgc/x/?pc="+encodeURIComponent(direct);
  const pageInfo={itemId:321,purchaseInfo:{purchaseBySellType:{purchaseCondition:"enabled"}}};
  const html='<html><head><meta property="og:title" content="N-VAN JJ1/2系 車中泊ベッド くるマット"></head><script>"itemInfoSku":'+JSON.stringify(pageInfo)+'</script></html>';
  const seenKeywords=[];
  try{
    global.fetch=async(input)=>{
      const url=String(input);
      if(url===direct)return new Response(html,{status:200,headers:{"content-type":"text/html"}});
      if(url.startsWith("https://openapi.rakuten.co.jp/")){
        const parsed=new URL(url);
        const keyword=parsed.searchParams.get("keyword")||"";
        const itemCode=parsed.searchParams.get("itemCode")||"";
        if(keyword)seenKeywords.push(keyword);
        if(itemCode)return new Response(JSON.stringify({items:[]}),{status:200,headers:{"content-type":"application/json"}});
        if(keyword.includes("N-VAN JJ1/2系")){
          return new Response(JSON.stringify({items:[{
            itemName:"N-VAN JJ1/2系 車中泊ベッド くるマット",
            itemCode:"hobbyman:actual",
            itemPrice:19800,
            itemUrl:direct,
            affiliateUrl:affiliate,
            shopName:"趣味職人",
            shopCode:"hobbyman",
            availability:1,
            mediumImageUrls:["https://example.com/nvan.jpg"]
          }]}),{status:200,headers:{"content-type":"application/json"}});
        }
        return new Response(JSON.stringify({items:[]}),{status:200,headers:{"content-type":"application/json"}});
      }
      throw new Error("unexpected fetch "+url);
    };
    const worker=(await import(workerUrl+"?t=page-title-recovery")).default;
    const request=new Request(
      "https://example.workers.dev/api/item-lookup?url="+encodeURIComponent(direct)+"&q="+encodeURIComponent("02k-a005-ca"),
      {headers:{Origin:allowedOrigin}}
    );
    const response=await worker.fetch(request,env);
    assert.equal(response.status,200);
    const body=await response.json();
    assert.equal(body.found,true);
    assert.equal(body.item_url,direct);
    assert.equal(body.affiliate_url,affiliate);
    assert.equal(body.lookup_method,"item_url_page_title_search");
    assert.ok(seenKeywords.some(q=>q.includes("N-VAN JJ1/2系")));
  }finally{global.fetch=original;}
});

test("page-title recovery still refuses a related URL from the same shop",async()=>{
  const original=global.fetch;
  const direct="https://item.rakuten.co.jp/hobbyman/exact/";
  const related="https://item.rakuten.co.jp/hobbyman/related/";
  const pageInfo={itemId:654,purchaseInfo:{purchaseBySellType:{purchaseCondition:"enabled"}}};
  const html='<html><head><meta property="og:title" content="ハスラー MR52S MR92S 車中泊マット"></head><script>"itemInfoSku":'+JSON.stringify(pageInfo)+'</script></html>';
  try{
    global.fetch=async(input)=>{
      const url=String(input);
      if(url===direct)return new Response(html,{status:200});
      if(url.startsWith("https://openapi.rakuten.co.jp/")){
        const parsed=new URL(url);
        if(parsed.searchParams.get("itemCode"))return new Response(JSON.stringify({items:[]}),{status:200});
        return new Response(JSON.stringify({items:[{
          itemName:"ハスラー MR52S MR92S 車中泊マット",
          itemCode:"hobbyman:related",
          itemPrice:9800,
          itemUrl:related,
          affiliateUrl:"https://hb.afl.rakuten.co.jp/hgc/x/?pc="+encodeURIComponent(related),
          shopName:"趣味職人",
          shopCode:"hobbyman",
          availability:1,
          mediumImageUrls:["https://example.com/related.jpg"]
        }]}),{status:200});
      }
      throw new Error("unexpected fetch "+url);
    };
    const worker=(await import(workerUrl+"?t=page-title-related")).default;
    const request=new Request(
      "https://example.workers.dev/api/item-lookup?url="+encodeURIComponent(direct)+"&q="+encodeURIComponent("MR52S"),
      {headers:{Origin:allowedOrigin}}
    );
    const response=await worker.fetch(request,env);
    const body=await response.json();
    assert.equal(response.status,200);
    assert.equal(body.found,false);
    assert.equal(body.reason,"exact_item_not_found");
  }finally{global.fetch=original;}
});


test("explicit itemCode falls back to same-shop keyword search using the merchant code tail",async()=>{
  const original=global.fetch;
  const direct="https://item.rakuten.co.jp/hobbyman/n-van-kurumat-9/";
  const affiliate="https://hb.afl.rakuten.co.jp/hgc/x/?pc="+encodeURIComponent(direct);
  const explicit="hobbyman:02k-a005-ca";
  const seen=[];
  try{
    global.fetch=async(input)=>{
      const url=String(input);
      if(url===direct)throw new Error("Rakuten page blocked");
      if(url.startsWith("https://openapi.rakuten.co.jp/")){
        const parsed=new URL(url);
        const itemCode=parsed.searchParams.get("itemCode")||"";
        const keyword=parsed.searchParams.get("keyword")||"";
        seen.push({itemCode,keyword});
        if(itemCode)return new Response(JSON.stringify({items:[]}),{status:200,headers:{"content-type":"application/json"}});
        if(keyword==="02k-a005-ca"){
          return new Response(JSON.stringify({items:[{
            itemName:"N-VAN JJ1/2系 車中泊ベッド くるマット",
            itemCode:"hobbyman:actual",
            itemPrice:19800,
            itemUrl:direct,
            affiliateUrl:affiliate,
            shopName:"趣味職人",
            shopCode:"hobbyman",
            availability:1,
            mediumImageUrls:["https://example.com/nvan.jpg"]
          }]}),{status:200,headers:{"content-type":"application/json"}});
        }
        return new Response(JSON.stringify({items:[]}),{status:200,headers:{"content-type":"application/json"}});
      }
      throw new Error("unexpected fetch "+url);
    };
    const worker=(await import(workerUrl+"?t=code-tail-search")).default;
    const request=new Request(
      "https://example.workers.dev/api/item-lookup?url="+encodeURIComponent(direct)+"&itemCode="+encodeURIComponent(explicit)+"&q="+encodeURIComponent("N-VAN JJ1/2 車中泊ベッド"),
      {headers:{Origin:allowedOrigin}}
    );
    const response=await worker.fetch(request,env);
    assert.equal(response.status,200);
    const body=await response.json();
    assert.equal(body.found,true);
    assert.equal(body.item_url,direct);
    assert.equal(body.affiliate_url,affiliate);
    assert.equal(body.lookup_method,"item_url_shop_search");
    assert.ok(seen.some(entry=>entry.keyword==="02k-a005-ca"));
  }finally{global.fetch=original;}
});
