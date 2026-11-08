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
  const a = {price:500, shipping:0, content:1000, packs:1, dose:20};
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
  assert.throws(() => offer({...normal, shipping:''}, 'A'), /送料/);
  assert.throws(() => offer({...normal, shipping:undefined}, 'A'), /送料/);
  assert.throws(() => offer({...normal, dose:1001}, 'A'));
  assert.throws(() => offer({...normal, packs:1.5}, 'A'));
  assert.throws(() => compare(normal, normal, ''));
  assert.throws(() => compare(normal, normal, 1001));
  assert.throws(() => compare({...normal, price:'Infinity'}, normal, 1));
});

test('A low per-wash cost can require higher cash outlay over three months', () => {
  const a = {price:2000, shipping:0, orderShipping:0, content:4000, packs:1, dose:20};
  const b = {price:350, shipping:0, orderShipping:0, content:400, packs:1, dose:20};
  const short = compare(a, b, 20, 3);
  assert.equal(short.winner, 'A');
  assert.equal(short.washesNeeded, 60);
  assert.equal(short.purchaseWinner, 'B');
  assert.deepEqual(short.purchaseA, {sets:1, payment:2000, unused:2800});
  assert.deepEqual(short.purchaseB, {sets:3, payment:1050, unused:0});
  const year = compare(a, b, 20, 12);
  assert.equal(year.purchaseWinner, 'A');
  assert.equal(year.purchaseA.payment, 4000);
  assert.equal(year.purchaseB.payment, 4200);
});
test('Shipping is counted once per combined order, while packs are rounded up', () => {
  const a = {price:600, shipping:550, orderShipping:550, content:1000, packs:1, dose:20};
  const b = {price:1000, shipping:0, content:1500, packs:1, dose:20};
  const result = compare(a, b, 30, 3);
  assert.equal(result.purchaseA.sets, 2);
  assert.equal(result.purchaseA.payment, 1750);
  assert.equal(result.purchaseA.unused, 200);
  assert.equal(result.purchaseB.sets, 2);
});
test('Purchase horizon rejects invalid months, overflow and impossible purchases', () => {
  const a = {price:600, shipping:0, content:1000, packs:1, dose:20};
  for (const months of ['', 0, -1, 1.5, 13, 'Infinity']) {
    assert.throws(() => compare(a, a, 20, months));
  }
  const impossible = {price:1000000000, shipping:0, content:1, packs:1, dose:1};
  assert.throws(() => compare(impossible, impossible, 1000, 12));
});

test('Unverified multi-set shipping never becomes a checkout winner or price', () => {
 const a={price:600,shipping:0,content:1000,packs:1,dose:20};
 let r=compare(a,a,30,3);
 assert.equal(r.purchaseA.sets,2);assert.equal(r.purchaseA.payment,null);
 assert.equal(r.purchaseWinner,null);assert.equal(r.purchaseDifference,null);
 r=compare({...a,orderShipping:900},{...a,orderShipping:0},30,3);
 assert.equal(r.purchaseA.payment,2100);assert.equal(r.purchaseB.payment,1200);
 assert.equal(r.purchaseWinner,'B');
 assert.throws(()=>compare({...a,orderShipping:-1},a,30,3));
});
