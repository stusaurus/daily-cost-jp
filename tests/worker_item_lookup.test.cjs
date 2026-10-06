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


test("item lookup continues to shop search when explicit code and page fetch both fail",async()=>{
  const original=global.fetch;
  const direct="https://item.rakuten.co.jp/suwariba/o023/";
  const affiliate="https://hb.afl.rakuten.co.jp/hgc/x/?pc="+encodeURIComponent(direct);
  let shopSearches=0;
  try{
    global.fetch=async(input)=>{
      const url=String(input);
      if(url===direct)throw new TypeError("page timeout");
      if(url.startsWith("https://openapi.rakuten.co.jp/")){
        const parsed=new URL(url);
        if(parsed.searchParams.get("itemCode"))throw new TypeError("bad explicit item code");
        assert.equal(parsed.searchParams.get("shopCode"),"suwariba");
        shopSearches+=1;
        return new Response(JSON.stringify({items:[{
          itemName:"N-VAN JJ1 JJ2 全席用 車中泊マット",
          itemCode:"suwariba:12345678",
          itemPrice:19800,
          itemUrl:direct,
          affiliateUrl:affiliate,
          shopName:"NOMAD BASE",
          shopCode:"suwariba",
          availability:1,
          mediumImageUrls:["https://example.com/nvan.jpg"]
        }]}),{status:200,headers:{"content-type":"application/json"}});
      }
      throw new Error("unexpected fetch "+url);
    };
    const worker=(await import(workerUrl+"?t=page-code-fallback")).default;
    const request=new Request(
      "https://example.workers.dev/api/item-lookup?url="+encodeURIComponent(direct)+"&itemCode="+encodeURIComponent("suwariba:o023")+"&q="+encodeURIComponent("N-VAN JJ1 JJ2"),
      {headers:{Origin:allowedOrigin}}
    );
    const response=await worker.fetch(request,env);
    assert.equal(response.status,200);
    const body=await response.json();
    assert.equal(body.found,true);
    assert.equal(body.lookup_method,"item_url_shop_search");
    assert.equal(body.item_url,direct);
    assert.ok(shopSearches>=1);
  }finally{global.fetch=original;}
});

test("item lookup continues across one failed shop query",async()=>{
  const original=global.fetch;
  const direct="https://item.rakuten.co.jp/hobbyman/n-box-jf56-set/";
  const affiliate="https://hb.afl.rakuten.co.jp/hgc/x/?pc="+encodeURIComponent(direct);
  let searches=0;
  try{
    global.fetch=async(input)=>{
      const url=String(input);
      if(url===direct)throw new TypeError("page blocked");
      if(url.startsWith("https://openapi.rakuten.co.jp/")){
        const parsed=new URL(url);
        if(parsed.searchParams.get("itemCode"))return new Response(JSON.stringify({items:[]}),{status:200});
        searches+=1;
        if(searches===1)throw new TypeError("transient search failure");
        return new Response(JSON.stringify({items:[{
          itemName:"N-BOX JF5 JF6 JOY サンシェード フルセット",
          itemCode:"hobbyman:actual",
          itemPrice:15900,
          itemUrl:direct,
          affiliateUrl:affiliate,
          shopName:"趣味職人",
          shopCode:"hobbyman",
          availability:1,
          mediumImageUrls:["https://example.com/nbox.jpg"]
        }]}),{status:200});
      }
      throw new Error("unexpected fetch "+url);
    };
    const worker=(await import(workerUrl+"?t=shop-query-fallback")).default;
    const request=new Request(
      "https://example.workers.dev/api/item-lookup?url="+encodeURIComponent(direct)+"&q="+encodeURIComponent("02s-c034-sa"),
      {headers:{Origin:allowedOrigin}}
    );
    const response=await worker.fetch(request,env);
    const body=await response.json();
    assert.equal(response.status,200);
    assert.equal(body.found,true);
    assert.equal(body.item_url,direct);
    assert.ok(searches>=2);
  }finally{global.fetch=original;}
});
