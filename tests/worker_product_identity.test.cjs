const test = require('node:test');
const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');
const path = require('node:path');
const source = pathToFileURL(path.join(__dirname, '../cloudflare-api/src/safe-index.js')).href;

test('exact product matcher rejects identity, capacity, pack, form and use mismatches', async () => {
  const { safeMatch } = await import(source);
  const cases = [
    ['スコッティ ティシュー 200W 5コパック(1セット)', 'スコッティ カシミヤ ナチュラル ソフトパック100枚50組', 'スコッティ'],
    ['スコッティ カシミヤ ティシュー キューブ', 'スコッティ カシミヤ ティシュー エレガント', 'スコッティ'],
    ['アタックZERO 本体400g', 'アタックZERO 本体380g', 'アタックZERO'],
    ['アタックZERO 本体400g', 'アタックZERO 本体400g 6個セット', 'アタックZERO'],
    ['アタックZERO 本体400g', 'アタックZERO 詰め替え400g', 'アタックZERO'],
    ['アタックZERO ドラム式専用 本体400g', 'アタックZERO 本体400g', 'アタックZERO'],
    ['アタックZERO 本体400g', 'アタックZERO ドラム式専用 本体400g', 'アタックZERO'],
    ['アタックZERO 部屋干し 本体380g', 'アタックZERO 本体380g', 'アタックZERO'],
    ['キレイキレイ ハンドソープ 本体450ml', 'キレイキレイ 除菌シート450ml', 'キレイキレイ'],
    ['日本製紙クレシア イノアック バソテクトG 30x1200x1250', 'スコッティファン120組', 'スコッティ'],
    ['スコッティ ティッシュ200組', 'スコッティ ティッシュ150組', 'スコッティ'],
    ['スコッティ ティッシュ200組5箱', 'スコッティ ティッシュ200組3箱', 'スコッティ'],
    ['アタックZERO 本体400g', 'アタックZERO 本体400g×6', 'アタックZERO'],
    ['アタックZERO 本体400g', 'アタックZERO 本体400g 1〜6個 選べる', 'アタックZERO'],
  ];
  for (const [name, itemName, brand] of cases) {
    assert.equal(safeMatch(itemName, { name, brand }).accepted, false, name + ' -> ' + itemName);
  }
});

test('bulk offers remove mismatched prices and purchase URLs, preserving confirmation URL', async () => {
  const { attachShipping } = await import(source);
  const product = { name: 'スコッティ ティシュー 200W 5コパック(1セット)', brand: 'スコッティ', url: 'https://product.rakuten.co.jp/product/confirmation/' };
  const wrong = { name: 'スコッティ カシミヤ ナチュラル ソフトパック100枚50組', price: 580, url: 'https://item.rakuten.co.jp/enetroom/7248130/' };
  const rejected = attachShipping([product], [wrong])[0];
  assert.equal(rejected.shipping_included_price, null);
  assert.equal(rejected.shipping_included_url, '');
  assert.equal(rejected.url, product.url);
  const correct = { name: product.name, price: 1000, url: 'https://item.rakuten.co.jp/test/exact/' };
  const accepted = attachShipping([product], [wrong, correct])[0];
  assert.equal(accepted.shipping_included_price, 1000);
  assert.equal(accepted.shipping_included_url, correct.url);
});

test('query relevance requires actual product name, not erroneous brand metadata', async () => {
  const { queryRelevant } = await import(source);
  assert.equal(queryRelevant({ name: 'イノアック バソテクトG 30x1200x1250', brand: 'スコッティ' }, 'スコッティ ティッシュ'), false);
  assert.equal(queryRelevant({ name: 'スコッティ ティシュー 200W 5コパック' }, 'スコッティ ティッシュ'), true);
});

test('JAN fallback applies the same identity guard and never returns a related purchase URL', async () => {
  const worker = (await import(source)).default;
  const original = global.fetch;
  try {
    global.fetch = async () => new Response(JSON.stringify({ Items: [{ Item: { itemName: 'スコッティ カシミヤ ナチュラル ソフトパック100枚50組', itemPrice: 580, postageFlag: 0, itemUrl: 'https://item.rakuten.co.jp/enetroom/7248130/' } }] }));
    const request = new Request('https://test.invalid/api/shipping-lookup?code=4901750417307&name=' + encodeURIComponent('スコッティ ティシュー 200W 5コパック(1セット)') + '&brand=' + encodeURIComponent('スコッティ'));
    const response = await worker.fetch(request, { RAKUTEN_APPLICATION_ID: 'test', RAKUTEN_ACCESS_KEY: 'test' });
    const body = await response.json();
    assert.equal(body.found, false);
    assert.equal(body.shipping_included_url, undefined);
    assert.equal(body.shipping_included_price, undefined);
  } finally { global.fetch = original; }
});

test('verified exact named product and exact quantities remain eligible', async () => {
  const { safeMatch } = await import(source);
  for (const name of ['アタックZERO ドラム式専用 本体400g', 'スコッティ ティッシュ200組5箱', 'キレイキレイ ハンドソープ 本体450ml']) {
    assert.equal(safeMatch('送料無料 ' + name, { name, brand: '' }).accepted, true, name);
  }
});

test('JAN alone and brand alone never establish a same-product offer', async () => {
  const { safeMatch } = await import(source);
  assert.equal(safeMatch('スコッティ別製品', { name: 'スコッティ カシミヤ キューブ', brand: 'スコッティ', product_code: '4901750447076' }).accepted, false);
  assert.equal(safeMatch('4901750447076', { name: 'スコッティ カシミヤ キューブ', product_code: '4901750447076' }).accepted, false);
});
