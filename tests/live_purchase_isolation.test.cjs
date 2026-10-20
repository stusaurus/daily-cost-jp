'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {isolate,inspectAffiliateLink}=require('../scripts/live_purchase_qa.cjs');

test('context isolation rejects analytics, affiliate destinations and unrelated origins',async()=>{
 let handler; const receipt={blocked_requests:0};
 await isolate({route:async(pattern,fn)=>{assert.equal(pattern,'**/*');handler=fn;}},receipt);
 const examples=[
  ['https://www.googletagmanager.com/gtag/js?id=G-TEST','script','abort'],
  ['https://region1.google-analytics.com/g/collect','fetch','abort'],
  ['https://analytics.google.com/g/collect','ping','abort'],
  ['https://hb.afl.rakuten.co.jp/hgc/test','document','abort'],
  ['https://item.rakuten.co.jp/shop/item/','document','abort'],
  ['https://example.com/popup','document','abort'],
  ['https://stusaurus.github.io/other-site/','document','abort'],
  ['https://stusaurus.github.io/daily-cost-jp/products/','document','continue'],
  ['https://thumbnail.image.rakuten.co.jp/test','image','continue'],
  ['https://thumbnail.image.rakuten.co.jp/test','document','abort'],
  ['https://daily-cost-api.kiyo0625puma.workers.dev/api/product-search?q=test','fetch','continue'],
  ['https://daily-cost-api.kiyo0625puma.workers.dev/other','fetch','abort'],
 ];
 for(const [url,type,expected] of examples){
  let action;await handler({request:()=>({url:()=>url,resourceType:()=>type}),abort:()=>{action='abort'},continue:()=>{action='continue'}});
  assert.equal(action,expected,url);
 }
 assert.equal(receipt.blocked_requests,9);
});

test('purchase URL inspection never activates the supplied link',async()=>{
 let clicks=0;
 const link={getAttribute:async()=> 'https://hb.afl.rakuten.co.jp/hgc/test',click:async()=>{clicks++}};
 assert.deepEqual(await inspectAffiliateLink(link),{href:await link.getAttribute(),status:'URL_VALIDATED_NO_CLICK',destination:'NOT_REQUESTED'});
 assert.equal(clicks,0);
 for(const href of ['javascript:alert(1)','https://rakuten.co.jp.evil.test/','http://item.rakuten.co.jp/shop/item/']){
  await assert.rejects(inspectAffiliateLink({getAttribute:async()=>href}),/Invalid Rakuten/);
 }
});
