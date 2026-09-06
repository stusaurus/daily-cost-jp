const PRODUCT_API_URL = 'https://openapi.rakuten.co.jp/ichibaproduct/api/Product/Search/20250801';
const ALLOWED_ORIGIN = 'https://stusaurus.github.io';

function safeInt(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? Math.trunc(n) : fallback;
}

function safeFloat(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function normalizeProduct(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const productId = String(raw.productId || '').trim();
  const name = String(raw.productName || '').trim();
  if (!productId || !name) return null;

  const minPrice = safeInt(raw.usedExcludeSalesMinPrice) || safeInt(raw.salesMinPrice);
  if (minPrice <= 0) return null;

  return {
    product_id: productId,
    product_code: String(raw.productCode || ''),
    name,
    product_no: String(raw.productNo || ''),
    brand: String(raw.brandName || ''),
    genre: String(raw.genreName || ''),
    min_price: minPrice,
    average_price: safeInt(raw.averagePrice),
    seller_count: safeInt(raw.salesItemCount),
    review_count: safeInt(raw.reviewCount),
    review_average: safeFloat(raw.reviewAverage),
    image: String(raw.mediumImageUrl || '').replace('http://', 'https://'),
    url: String(raw.affiliateUrl || raw.productUrlPC || ''),
  };
}

export default async function handler(req, res) {
  const origin = req.headers.origin;
  if (origin && origin !== ALLOWED_ORIGIN) {
    return res.status(403).json({ error: 'origin_not_allowed' });
  }

  res.setHeader('Access-Control-Allow-Origin', ALLOWED_ORIGIN);
  res.setHeader('Vary', 'Origin');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method !== 'GET') return res.status(405).json({ error: 'method_not_allowed' });

  const q = String(req.query.q || '').trim();
  const page = Math.max(1, Math.min(100, safeInt(req.query.page, 1)));
  const hits = Math.max(1, Math.min(30, safeInt(req.query.hits, 30)));

  if (q.length < 2) {
    return res.status(400).json({ error: 'query_too_short', message: '2文字以上で検索してください。' });
  }

  const applicationId = process.env.RAKUTEN_APPLICATION_ID;
  const accessKey = process.env.RAKUTEN_ACCESS_KEY;
  const affiliateId = process.env.RAKUTEN_AFFILIATE_ID || '';

  if (!applicationId || !accessKey) {
    return res.status(503).json({ error: 'server_not_configured' });
  }

  const params = new URLSearchParams({
    applicationId,
    keyword: q,
    hits: String(hits),
    page: String(page),
    format: 'json',
    formatVersion: '2',
    elements: [
      'productId', 'productCode', 'productName', 'productNo', 'brandName',
      'productUrlPC', 'affiliateUrl', 'mediumImageUrl', 'salesItemCount',
      'usedExcludeSalesMinPrice', 'salesMinPrice', 'averagePrice',
      'reviewCount', 'reviewAverage', 'genreName'
    ].join(','),
  });

  if (affiliateId) params.set('affiliateId', affiliateId);

  try {
    const response = await fetch(`${PRODUCT_API_URL}?${params.toString()}`, {
      headers: {
        accessKey,
        Origin: ALLOWED_ORIGIN,
        Referer: 'https://stusaurus.github.io/daily-cost-jp/',
        'User-Agent': 'daily-cost-jp-realtime/1.0',
      },
    });

    if (!response.ok) {
      const body = await response.text();
      console.error('Rakuten API error', response.status, body.slice(0, 500));
      return res.status(502).json({ error: 'rakuten_api_error', status: response.status });
    }

    const payload = await response.json();
    const products = (payload.items || []).map(normalizeProduct).filter(Boolean);

    res.setHeader('Cache-Control', 'public, s-maxage=300, stale-while-revalidate=1800');
    return res.status(200).json({
      query: q,
      page,
      hits,
      count: products.length,
      page_count: safeInt(payload.pageCount),
      total_count: safeInt(payload.count),
      products,
    });
  } catch (error) {
    console.error('product-search failed', error);
    return res.status(500).json({ error: 'internal_error' });
  }
}
