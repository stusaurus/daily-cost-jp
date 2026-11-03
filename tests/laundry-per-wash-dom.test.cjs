const {test} = require('node:test');
const assert = require('node:assert/strict');
const {JSDOM} = require('jsdom');
const fs = require('node:fs');
const {execFileSync} = require('node:child_process');

function calculator() {
  const html = execFileSync('python', ['-c',
    'from scripts.build_laundry_cost_page import PAGE; print(PAGE)'], {encoding:'utf8'});
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

test('Changing unit invalidates the old comparison and clears old errors', () => {
  const dom = calculator(), d = dom.window.document;
  try {
    d.getElementById('wash-sample').click();
    assert.equal(d.getElementById('wash-result').hidden,false);
    d.getElementById('wash-error').textContent='previous error';
    const unit = d.getElementById('wash-a-unit');
    unit.value='個'; unit.dispatchEvent(new dom.window.Event('change'));
    assert.equal(d.getElementById('wash-result').hidden,true);
    assert.equal(d.getElementById('wash-error').textContent,'');
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
