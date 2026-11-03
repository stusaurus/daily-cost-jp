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
