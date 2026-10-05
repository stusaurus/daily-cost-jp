const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { pathToFileURL } = require('node:url');
const path = require('node:path');

const coreUrl = pathToFileURL(path.resolve('cloudflare-api/src/item-lookup-core.mjs')).href;
const worker = fs.readFileSync('cloudflare-api/src/safe-index.js','utf8');

test('exact Rakuten item URL parser accepts only one item.rakuten.co.jp listing', async()=>{
  const {parseRakutenItemUrl}=await import(coreUrl);
  assert.deepEqual(parseRakutenItemUrl('https://item.rakuten.co.jp/suwariba/o017/'),{
    shopCode:'suwariba',itemId:'o017',itemCode:'suwariba:o017',
    canonicalUrl:'https://item.rakuten.co.jp/suwariba/o017/'
  });
  for(const url of [
    'http://item.rakuten.co.jp/suwariba/o017/',
    'https://evil.example/suwariba/o017/',
    'https://item.rakuten.co.jp.evil.example/suwariba/o017/',
    'https://item.rakuten.co.jp/suwariba/o017/extra/',
    'https://item.rakuten.co.jp/suwariba/'
  ]) assert.equal(parseRakutenItemUrl(url),null,url);
});

test('affiliate target must resolve to the exact requested Rakuten item', async()=>{
  const {affiliateTargetsItem}=await import(coreUrl);
  const exact='https://item.rakuten.co.jp/suwariba/o017/';
  const good='https://hb.afl.rakuten.co.jp/hgc/x/?pc='+encodeURIComponent(exact);
  const bad='https://hb.afl.rakuten.co.jp/hgc/x/?pc='+encodeURIComponent('https://item.rakuten.co.jp/suwariba/other/');
  assert.equal(affiliateTargetsItem(good,exact),true);
  assert.equal(affiliateTargetsItem(bad,exact),false);
  assert.equal(affiliateTargetsItem('https://rakuten.example/?pc='+encodeURIComponent(exact),exact),false);
});

test('Worker exact lookup uses itemCode and fails closed on item identity and affiliate destination',()=>{
  assert.match(worker,/url\.pathname === "\/api\/item-by-url"/);
  assert.match(worker,/itemCode: identity\.itemCode/);
  assert.match(worker,/availability: "1"/);
  assert.match(worker,/returnedIdentity\.canonicalUrl !== identity\.canonicalUrl/);
  assert.match(worker,/affiliateTargetsItem\(affiliateUrl, identity\.canonicalUrl\)/);
  assert.match(worker,/source\.length !== 1/);
});
