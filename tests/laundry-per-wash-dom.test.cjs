const {test} = require('node:test');
const assert = require('node:assert/strict');
const {JSDOM} = require('jsdom');
const fs = require('node:fs');
const {execFileSync} = require('node:child_process');

function calculator(picks='') {
  const html = execFileSync('python', ['-c',
    'from scripts.build_laundry_cost_page import PAGE; print(PAGE)'], {encoding:'utf8'})
    .replace('<!-- verified laundry presets -->', picks);
  const dom = new JSDOM(html, {runScripts:'outside-only'});
  dom.window.eval(fs.readFileSync('scripts/assets/laundry-per-wash.js','utf8'));
  return dom;
}

test('Editing a sample keeps fictional provenance visible until reset', () => {
  const dom = calculator(), d = dom.window.document;
  try {
    d.getElementById('wash-sample').click();
    assert.equal(d.getElementById('wash-example-note').hidden,false);
    const price = d.getElementById('wash-a-price');
    price.value='600'; price.dispatchEvent(new dom.window.Event('input'));
    assert.equal(d.getElementById('wash-result').hidden,true);
    assert.equal(d.getElementById('wash-b-price').value,'1880');
    assert.equal(d.getElementById('wash-example-note').hidden,false);
    d.getElementById('wash-calc').reset();
    assert.equal(d.getElementById('wash-example-note').hidden,true);
  } finally {dom.window.close();}
});

test('Changing unit invalidates the old comparison and requests shipping reconfirmation', () => {
  const dom = calculator(), d = dom.window.document;
  try {
    d.getElementById('wash-sample').click();
    assert.equal(d.getElementById('wash-result').hidden,false);
    d.getElementById('wash-error').textContent='previous error';
    const unit = d.getElementById('wash-a-unit');
    unit.value='個'; unit.dispatchEvent(new dom.window.Event('change'));
    assert.equal(d.getElementById('wash-result').hidden,true);
    assert.equal(d.getElementById('wash-a-order-shipping').value,'');
    assert.match(d.getElementById('wash-error').textContent,/送料合計を再確認/);
  } finally {dom.window.close();}
});

test('Purchase result shows both cash outlay and leftovers; edits invalidate it', () => {
  const dom = calculator(), d = dom.window.document;
  try {
    d.getElementById('wash-sample').click();
    assert.equal(d.getElementById('wash-result').hidden, false);
    assert.equal(d.getElementById('wash-purchase-count').textContent, '3か月・60回分');
    assert.match(d.getElementById('wash-a-payment').textContent, /円/);
    assert.match(d.getElementById('wash-b-unused').textContent, /mL/);
    assert.match(d.getElementById('wash-purchase-tradeoff').textContent, /逆転/);
    const period=d.getElementById('wash-period');
    period.value='12'; period.dispatchEvent(new dom.window.Event('input'));
    assert.equal(d.getElementById('wash-result').hidden,true);
    d.getElementById('wash-calc').requestSubmit();
    assert.equal(d.getElementById('wash-purchase-count').textContent, '12か月・240回分');
  } finally {dom.window.close();}
});

test('Analytics emits only completion flags and product-navigation intent', () => {
  const dom = calculator(), d = dom.window.document;
  try {
    const events = [];
    dom.window.gtag = (command, name, params) => events.push({command, name, params});
    d.getElementById('wash-sample').click();
    assert.equal(events.filter(x => x.name === 'laundry_purchase_plan_complete').length,1);
    const last = events[events.length-1];
    assert.equal(last.params.example_mode, '1');
    assert.equal(last.params.purchase_winner_reversed, '1');
    assert.deepEqual(Object.keys(last.params).sort(),
      ['category_id','example_mode','purchase_winner_reversed','tool_id'].sort());
    d.querySelector('.purchase-horizon a[href="/daily-cost-jp/categories/laundry/"]')
      .dispatchEvent(new dom.window.Event('click'));
    assert.equal(events.at(-1).name, 'laundry_purchase_plan_to_products');
    assert.deepEqual(Object.keys(events.at(-1).params).sort(), ['category_id','tool_id']);
  } finally {dom.window.close();}
});

test('One-tap offer prefill copies only verified listed price and quantity, not dosage', () => {
  const picks = '<section id="wash-verified-picks">' +
    '<button data-pick-target="a" data-pick-price="850" data-pick-total="850" ' +
    'data-pick-unit="g" data-pick-name="アタック850g">Aに入力</button></section>';
  const dom = calculator(picks), d = dom.window.document;
  try {
    const events=[];
    dom.window.gtag = (command,name,params) => events.push({command,name,params});
    d.getElementById('wash-sample').click();
    d.querySelector('#wash-verified-picks button').click();
    assert.equal(d.getElementById('wash-a-price').value, '850');
    assert.equal(d.getElementById('wash-a-content').value, '850');
    assert.equal(d.getElementById('wash-a-packs').value, '1');
    assert.equal(d.getElementById('wash-a-shipping').value, '0');
    assert.equal(d.getElementById('wash-a-unit').value, 'g');
    assert.equal(d.getElementById('wash-a-dose').value, '');
    assert.equal(d.getElementById('wash-result').hidden, true);
    assert.equal(d.getElementById('wash-example-note').hidden, true);
    assert.match(d.getElementById('wash-picked-note').textContent, /製品ラベル/);
    assert.deepEqual(JSON.parse(JSON.stringify(events.at(-1))), {
      command:'event', name:'laundry_verified_offer_prefill',
      params:{category_id:'laundry',tool_id:'laundry_per_wash',slot:'A'}
    });
  } finally {dom.window.close();}
});

test('Real product prefill does not inherit fictional comparisons or unconfirmed order shipping', () => {
  const picks = '<section id="wash-verified-picks">' +
    '<button data-pick-target="a" data-pick-price="850" data-pick-total="850" ' +
    'data-pick-unit="g" data-pick-name="実在商品">Aに入力</button></section>';
  const dom=calculator(picks),d=dom.window.document;
  try {
    d.getElementById('wash-sample').click();
    assert.equal(d.getElementById('wash-a-order-shipping').value,'0');
    assert.equal(d.getElementById('wash-b-price').value,'1880');
    d.querySelector('#wash-verified-picks button').click();
    assert.equal(d.getElementById('wash-a-order-shipping').value,'');
    assert.equal(d.getElementById('wash-a-shipping').value,'0');
    assert.equal(d.getElementById('wash-b-price').value,'');
    assert.equal(d.getElementById('wash-b-shipping').value,'');
    assert.equal(d.getElementById('wash-b-content').value,'');
    assert.equal(d.getElementById('wash-b-dose').value,'');
    assert.equal(d.getElementById('wash-example-note').hidden,true);
    assert.equal(d.getElementById('wash-result').hidden,true);
    // The selected product intentionally has no inferred dosage.
    // Confirm a dosage before asserting that the fictional B input is unavailable.
    d.getElementById('wash-a-dose').value='20';
    d.getElementById('wash-calc').requestSubmit();
    assert.match(d.getElementById('wash-error').textContent,/洗剤B/);
  } finally { dom.window.close(); }
});

test('Changing order size or product terms clears stale combined-order shipping', () => {
  const dom=calculator(),d=dom.window.document;
  try {
    d.getElementById('wash-sample').click();
    const aOrder=d.getElementById('wash-a-order-shipping');
    const bOrder=d.getElementById('wash-b-order-shipping');
    assert.equal(aOrder.value,'0');
    assert.equal(bOrder.value,'0');
    const period=d.getElementById('wash-period');
    period.value='6';period.dispatchEvent(new dom.window.Event('input',{bubbles:true}));
    assert.equal(aOrder.value,'');
    assert.equal(bOrder.value,'');
    assert.match(d.getElementById('wash-error').textContent,/送料合計を再確認/);
    assert.equal(d.getElementById('wash-result').hidden,true);
    aOrder.value='500';bOrder.value='0';
    const dose=d.getElementById('wash-a-dose');
    dose.value='35';dose.dispatchEvent(new dom.window.Event('input',{bubbles:true}));
    assert.equal(aOrder.value,'');
    assert.equal(bOrder.value,'0');
  } finally { dom.window.close(); }
});

test('Unknown order shipping hides price, winner and reversal analytics until confirmation',()=>{
 const dom=calculator(),d=dom.window.document;
 try{
  const completionEvents=[];
  dom.window.gtag=(command,name,params)=>{
   if(command==='event'&&name==='laundry_purchase_plan_complete')completionEvents.push(params);
  };
  d.getElementById('wash-sample').click();
  const shipping=d.getElementById('wash-a-order-shipping');
  d.getElementById('wash-period').value='12';
  shipping.value='';shipping.dispatchEvent(new dom.window.Event('input'));
  assert.equal(d.getElementById('wash-result').hidden,true);
  d.getElementById('wash-calc').requestSubmit();
  assert.match(d.getElementById('wash-a-payment').textContent,/未算出/);
  assert.match(d.getElementById('wash-purchase-verdict').textContent,/送料合計/);
  assert.equal(d.getElementById('wash-purchase-tradeoff').textContent,'');
  assert.equal(completionEvents.at(-1).purchase_winner_reversed,'0',
   'Unknown shipping must not be counted as a reversed checkout winner');
  shipping.value='800';d.getElementById('wash-calc').requestSubmit();
  assert.match(d.getElementById('wash-a-payment').textContent,/円/);
 }finally{dom.window.close();}
});
