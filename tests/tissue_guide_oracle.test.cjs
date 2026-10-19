const {test}=require('node:test');
const assert=require('node:assert/strict');
const {step5SmallTissue}=require('../scripts/check_search_conversion.cjs');

function offer(boxes,id){return {name:`ボックスティッシュ 200組 ${boxes}箱`,price:boxes*100,
 unit_price:100,metric:'box',confidence:.99,postage:'送料込み',item_code:`shop:${id}`,
 url:`https://item.rakuten.co.jp/shop/${id}/`};}
function category(extra=offer(5,'small')){return {items:[offer(60,'bulk')],purpose_candidates:[extra]};}

test('browser oracle recognizes an existing strict STEP5 small pack without a legacy supplement',()=>{
 const data=category();const before=JSON.stringify(data);const chosen=step5SmallTissue(data);
 assert.equal(chosen.quantity,5);assert.equal(chosen.offer.price,500);
 assert.equal(chosen.offer.url,data.purpose_candidates[0].url);
 assert.equal(JSON.stringify(data),before);
});
test('browser oracle never authorizes unsafe shipping, identity, quantity or units',()=>{
 for(const change of [{postage:'送料別'},{item_code:'shop:wrong'},{metric:'pack'},
  {name:'ボックスティッシュ 200組 5箱×12パック'}]){
  assert.equal(step5SmallTissue(category({...offer(5,'small'),...change})),null);
 }
});
test('browser oracle keeps missing small candidates unknown instead of inventing a direct offer',()=>{
 assert.equal(step5SmallTissue({items:[offer(60,'bulk')],purpose_candidates:[]}),null);
});
