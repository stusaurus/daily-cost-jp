const { test } = require('node:test');
const assert = require('node:assert/strict');
const { JSDOM } = require('jsdom');
const fs = require('node:fs');
const w = new JSDOM('',{runScripts:'outside-only'}).window;
w.eval(fs.readFileSync('scripts/offer_validation.js','utf8'));
test('selectable capacities/pack counts never claim one confirmed price',()=>{
  for(const name of ['【選べる1～4個】アタックZERO 2100g','2580g×6袋 4袋 2袋','【1個/3個/6個】アタックZERO 2100g','アタックZERO 2100g 部屋干し2000g 3種から1つ']) {
    const p=w.dailyCostVerifiedOffer({shipping_match_name:name,shipping_included_price:2750,shipping_included_url:'https://shop.example/',url:'https://product.example/'});
    assert.equal(p.shipping_included_price,null,name);
    assert.equal(p.url,'https://product.example/');
  }
});
test('fixed sale quantities and the affiliate URL are preserved',()=>{
  for(const name of ['アタックZERO 2100g','【6個セット】さらさ1490g','水500ml×24本']) {
    const p=w.dailyCostVerifiedOffer({shipping_match_name:name,shipping_included_price:2980,shipping_included_url:'https://hb.afl.rakuten.co.jp/hgc/test'});
    assert.equal(p.shipping_included_price,2980,name);
    assert.equal(p.shipping_included_url,'https://hb.afl.rakuten.co.jp/hgc/test');
  }
});
