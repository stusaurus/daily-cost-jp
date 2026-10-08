// Public product/listing evidence only. Never persist keys or upstream URLs.
import fs from 'node:fs/promises';
import { safeMatch } from '../cloudflare-api/src/safe-index.js';
const origin = 'https://stusaurus.github.io';
const endpoints = ['https://daily-cost-api.kiyo0625puma.workers.dev', 'https://daily-cost-api.stuffedsaurus.workers.dev'];
const evidence = { at: new Date().toISOString(), public: [], upstream: [] };
const pause = () => new Promise(r => setTimeout(r, 1200));
async function json(url, options = {}) {
  const res = await fetch(url, { ...options, signal: AbortSignal.timeout(45000) });
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return res.json();
}
await fs.mkdir('qa-evidence', { recursive: true });
for (const base of endpoints) {
  for (const query of ['アリエール', 'スコッティ ティッシュペーパー']) {
    try {
      const data = await json(base + '/api/product-search?q=' + encodeURIComponent(query) + '&hits=10', { headers: { Origin: origin } });
      evidence.public.push({ base, query, data });
      console.log(base + ' ' + query + ': products=' + data.products?.length + ' priced=' + data.products?.filter(p => p.shipping_included_price > 0).length + ' shipping_items=' + data.shipping_lookup_count);
    } catch (e) { evidence.public.push({ base, query, error: e.message }); }
    await pause();
  }
}
if (process.env.RAKUTEN_APPLICATION_ID && process.env.RAKUTEN_ACCESS_KEY) {
  const query = 'アリエール';
  async function upstream(kind, keyword, extras = {}) {
    const route = kind === 'product' ? 'ichibaproduct/api/Product/Search/20250801' : 'ichibams/api/IchibaItem/Search/20260701';
    const params = new URLSearchParams({ applicationId: process.env.RAKUTEN_APPLICATION_ID, keyword, hits: '30', format: 'json', formatVersion: '2', ...extras });
    return json('https://openapi.rakuten.co.jp/' + route + '?' + params, { headers: { accessKey: process.env.RAKUTEN_ACCESS_KEY, Origin: origin, Referer: origin + '/daily-cost-jp/' } });
  }
  try {
    const result = await upstream('product', query);
    const products = (result.Products || result.items || []).map(p => p.Product || p).map(p => ({name:p.productName,brand:p.brandName,product_code:p.productCode,product_id:p.productId}));
    await pause();
    const raw = await upstream('item', query, { availability:'1',field:'0',sort:'+itemPrice',postageFlag:'1' });
    const items = (raw.Items || raw.items || []).map(p => p.Item || p).map(p => ({name:p.itemName,price:p.itemPrice,postage_flag:p.postageFlag,url:p.itemUrl}));
    evidence.upstream.push({ query, products, items, matches: products.map(p => ({ product:p, candidates:items.map(i=>({item:i,match:safeMatch(i.name,p)})) })) });
    for (const product of products.slice(0, 5)) {
      await pause();
      const rawExact = await upstream('item', product.product_code);
      const exactItems = (rawExact.Items || rawExact.items || []).map(p => p.Item || p).map(p => ({name:p.itemName,price:p.itemPrice,postage_flag:p.postageFlag,url:p.itemUrl}));
      evidence.upstream.push({ query:product.product_code, product, items:exactItems, matches:exactItems.map(i=>({item:i,match:safeMatch(i.name,product)})) });
    }
  } catch (e) { evidence.upstream.push({ error:e.message }); }
} else evidence.upstream.push({ error:'Configured upstream credentials not available; public API evidence only.' });
await fs.writeFile('qa-evidence/search-diagnostic.json', JSON.stringify(evidence, null, 2));
