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

test('same capacity cannot hide a different detergent type or container',()=>{
  for(const [name,shipping_match_name] of [
    ['アタックZERO 洗濯洗剤 ドラム式専用 本体(400g)', 'アタック ZERO(ゼロ) 洗濯洗剤 液体 ワンハンドプッシュ 本体 400g'],
    ['アタックZERO 洗濯洗剤 本体(400g)', 'アタックZERO ドラム式専用 本体400g'],
    ['アタックZERO 部屋干し 本体380g', 'アタックZERO 本体380g'],
    ['アタックZERO 本体380g', 'アタックZERO 部屋干し 本体380g'],
    ['キレイキレイ ハンドソープ つめかえ450ml', 'キレイキレイ ハンドソープ 本体450ml'],
    ['キレイキレイ ハンドソープ 本体450ml', 'キレイキレイ ハンドソープ 詰替450ml'],
    ['アタックZERO 本体400g', 'アタックZERO 本体400g+詰め替え400gセット'],
  ]) {
    const input={name,shipping_match_name,shipping_included_price:1522,shipping_included_url:'https://wrong.example/',shipping_included_image:'wrong.jpg',sale_quantity_label:'400g',url:'https://product.example/'};
    const result=w.dailyCostVerifiedOffer(input);
    assert.equal(result.shipping_included_price,null,name);
    assert.equal(result.shipping_included_url,'',name);
    assert.equal(result.shipping_included_image,'',name);
    assert.equal(result.sale_quantity_label,'',name);
    assert.equal(result.offer_type_mismatch,true,name);
    assert.equal(result.url,input.url,'keep original product affiliate destination');
    assert.equal(input.shipping_included_price,1522,'do not mutate API input');
  }
});

test('matching types keep verified affiliate offers, including after fallback',()=>{
  for(const [name,shipping_match_name] of [
    ['アタックZERO ドラム式専用 本体400g', '花王 アタックZERO ドラム式 本体400g'],
    ['アタックZERO 本体400g', '花王 アタックZERO ワンハンド 本体400g'],
    ['アタックZERO 部屋干し 詰替2100g', 'アタックZERO 部屋干し つめかえ2100g'],
    ['キレイキレイ 本体450ml','キレイキレイ ハンドソープ 本体450ml'],
  ]) {
    const result=w.dailyCostVerifiedOffer({name,shipping_match_name,shipping_included_price:2000,shipping_included_url:'https://hb.afl.rakuten.co.jp/hgc/test',offer_type_mismatch:true,offer_needs_selection:true});
    assert.equal(result.shipping_included_price,2000,name);
    assert.equal(result.shipping_included_url,'https://hb.afl.rakuten.co.jp/hgc/test',name);
    assert.equal(result.offer_type_mismatch,false,name);
    assert.equal(result.offer_needs_selection,false,name);
  }
});
