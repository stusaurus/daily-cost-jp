const assert = require('node:assert/strict');
const {test} = require('node:test');
const {offer, compare} = require('../scripts/assets/laundry-per-wash.js');

test('Two laundry offers compare cost per wash, monthly and yearly difference', () => {
  const a = {price:598, shipping:0, content:1000, packs:1, dose:30};
  const b = {price:1880, shipping:0, content:900, packs:2, dose:15};
  const result = compare(a, b, 20);
  assert.equal(result.winner, 'B');
  assert.ok(Math.abs(result.a.perWash - 17.94) < 1e-9);
  assert.ok(Math.abs(result.b.perWash - (1880*15/1800)) < 1e-9);
  assert.ok(Math.abs(result.monthlyDifference -
    Math.abs(result.a.perWash-result.b.perWash)*20) < 1e-9);
  assert.ok(Math.abs(result.annualDifference - result.monthlyDifference*12) < 1e-8);
});
test('Shipping added once to total bundle, not per packet', () => {
  const v = offer({price:1000, shipping:500, content:400, packs:2, dose:20}, '洗剤A');
  assert.equal(v.total, 1500);
  assert.equal(v.washes, 40);
  assert.equal(v.perWash, 37.5);
});
test('Tie and A winner are distinct', () => {
  const a = {price:500, shipping:'', content:1000, packs:1, dose:20};
  const b = {price:1000, shipping:0, content:2000, packs:1, dose:20};
  assert.equal(compare(a, b, 20).winner, 'same');
  assert.equal(compare({...a, price:450}, b, 20).winner, 'A');
});
test('Missing/negative/zero or impossible inputs never emit a comparison', () => {
  const normal = {price:500, shipping:0, content:1000, packs:1, dose:20};
  for (const field of ['price','content','packs','dose']) {
    assert.throws(() => offer({...normal, [field]:''}, 'A'));
    assert.throws(() => offer({...normal, [field]:0}, 'A'));
    assert.throws(() => offer({...normal, [field]:-1}, 'A'));
  }
  assert.throws(() => offer({...normal, shipping:-1}, 'A'));
  assert.throws(() => offer({...normal, dose:1001}, 'A'));
  assert.throws(() => offer({...normal, packs:1.5}, 'A'));
  assert.throws(() => compare(normal, normal, ''));
  assert.throws(() => compare(normal, normal, 1001));
  assert.throws(() => compare({...normal, price:'Infinity'}, normal, 1));
});
