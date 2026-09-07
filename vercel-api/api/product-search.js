const PRODUCT_API_URL = "https://openapi.rakuten.co.jp/ichibaproduct/api/Product/Search/20250801";
const ITEM_API_URL = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701";
const ALLOWED_ORIGIN = "https://stusaurus.github.io";
const SITE_URL = "https://stusaurus.github.io/daily-cost-jp/";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function safeInt(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? Math.trunc(n) : fallback;
}

function safeFloat(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function normalize(value) {
  return String(value || "")
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[\s\u3000]/g, " ")
    .trim();
}

function compact(value) {
  return normalize(value).replace(/[\s\u3000\-_/・.,!！?？()（）［］\[\]【】]/g, "");
}

const GENERIC_WORDS = new Set([
  "楽天", "公式", "正規品", "送料無料", "送料込", "送料込み", "セール", "sale",
  "トイレットペーパー", "ティッシュ", "ティッシュペーパー", "洗剤", "シャンプー",
  "コンディショナー", "ボディソープ", "ハンドソープ", "マウスウォッシュ",
  "セット", "まとめ買い", "詰め替え", "詰替", "本体", "無香料", "ダブル", "シングル",
]);

function wordTokens(name, brand) {
  const brandKey = compact(brand);
  return normalize(name)
    .replace(/[()（）\[\]【】/／・,，:：;；!！?？+＋×✕]/g, " ")
    .split(/\s+/)
    .map((token) => token.trim())
    .filter(Boolean)
    .filter((token) => token.length >= 2)
    .filter((token) => !/^\d+(?:\.\d+)?(?:ml|l|g|kg|m|cm|mm|枚|個|本|箱|袋|ロール|巻|パック)?$/i.test(token))
    .filter((token) => !GENERIC_WORDS.has(token))
    .filter((token) => compact(token) !== brandKey);
}

function specTokens(name) {
  const text = normalize(name).replace(/[＊*×✕]/g, "x");
  const found = text.match(/\d+(?:\.\d+)?\s*(?:ml|l|g|kg|m|cm|mm|枚|個|本|箱|袋|ロール|巻|パック)/gi) || [];
  return Array.from(new Set(found.map((token) => compact(token).replace(/巻/g, "ロール"))));
}

function normalizeProduct(raw) {
  const productId = String(raw.productId || "").trim();
  const name = String(raw.productName || "").trim();
  if (!productId || !name) return null;

  return {
    product_id: productId,
    product_code: String(raw.productCode || ""),
    name,
    product_no: String(raw.productNo || ""),
    brand: String(raw.brandName || ""),
    genre: String(raw.genreName || ""),
    seller_count: safeInt(raw.salesItemCount),
    review_count: safeInt(raw.reviewCount),
    review_average: safeFloat(raw.reviewAverage),
    image: String(raw.mediumImageUrl || "").replace("http://", "https://"),
    url: String(raw.affiliateUrl || raw.productUrlPC || ""),
  };
}

function normalizeItem(raw) {
  const item = raw && typeof raw === "object" && raw.Item && typeof raw.Item === "object"
    ? raw.Item
    : raw && typeof raw === "object" && raw.item && typeof raw.item === "object"
      ? raw.item
      : raw;
  if (!item || typeof item !== "object") return null;
  const price = safeInt(item.itemPrice);
  if (price <= 0) return null;
  return {
    name: String(item.itemName || ""),
    price,
    shop: String(item.shopName || ""),
    url: String(item.affiliateUrl || item.itemUrl || ""),
    postage_flag: safeInt(item.postageFlag, -1),
  };
}

function relevanceScore(product, query) {
  const q = compact(query);
  const name = compact(product.name);
  const brand = compact(product.brand);
  const code = compact(product.product_code);
  let score = 0;
  if (code && code === q) score += 10000;
  if (name === q) score += 2200;
  if (name.startsWith(q)) score += 1400;
  if (brand === q) score += 1200;
  const ni = name.indexOf(q);
  if (ni >= 0) score += 800 - Math.min(ni, 300);
  const bi = brand.indexOf(q);
  if (bi >= 0) score += 500 - Math.min(bi, 200);
  score += Math.min(150, Math.log10(product.review_count + 1) * 35);
  score += Math.min(80, Math.log10(product.seller_count + 1) * 20);
  return score;
}

function matchScore(itemName, product) {
  const item = compact(itemName).replace(/巻/g, "ロール");
  const productName = compact(product.name).replace(/巻/g, "ロール");
  const brandKey = compact(product.brand);
  const words = wordTokens(product.name, product.brand);
  const specs = specTokens(product.name);

  let score = 0;
  if (brandKey && item.includes(brandKey)) score += 10;
  if (productName && item.includes(productName)) score += 40;

  let wordMatches = 0;
  for (const word of words.slice(0, 6)) {
    if (item.includes(compact(word))) {
      score += 6;
      wordMatches += 1;
    }
  }

  let specMatches = 0;
  for (const spec of specs) {
    if (item.includes(spec)) {
      score += 14;
      specMatches += 1;
    } else {
      score -= 18;
    }
  }

  const specOk = specs.length === 0 || specMatches >= Math.max(1, Math.ceil(specs.length * 0.67));
  const wordsOk = words.length === 0 || wordMatches >= Math.min(2, words.length);
  return { score, specOk, wordsOk };
}

function attachShipping(products, items) {
  return products.map((product) => {
    const ranked = items
      .map((item) => ({ item, ...matchScore(item.name, product) }))
      .filter((x) => x.specOk && x.wordsOk && x.score >= 10)
      .sort((a, b) => (b.score - a.score) || (a.item.price - b.item.price));

    if (!ranked.length) {
      return {
        ...product,
        shipping_included_price: null,
        shipping_included_url: "",
        shipping_included_shop: "",
      };
    }

    const bestScore = ranked[0].score;
    const best = ranked
      .filter((x) => x.score >= bestScore - 4)
      .sort((a, b) => a.item.price - b.item.price)[0];

    return {
      ...product,
      shipping_included_price: best.item.price,
      shipping_included_url: best.item.url,
      shipping_included_shop: best.item.shop,
      shipping_match_score: best.score,
    };
  });
}

async function fetchProductCandidates(q, page, hits, applicationId, accessKey, affiliateId) {
  const params = new URLSearchParams({
    applicationId,
    keyword: q,
    hits: String(hits),
    page: String(page),
    format: "json",
    formatVersion: "2",
    elements: [
      "productId", "productCode", "productName", "productNo", "brandName",
      "productUrlPC", "affiliateUrl", "mediumImageUrl", "salesItemCount",
      "reviewCount", "reviewAverage", "genreName"
    ].join(","),
  });
  if (affiliateId) params.set("affiliateId", affiliateId);

  const response = await fetch(`${PRODUCT_API_URL}?${params.toString()}`, {
    headers: {
      accessKey,
      Origin: ALLOWED_ORIGIN,
      Referer: SITE_URL,
      "User-Agent": "daily-cost-jp-vercel/1.0",
    },
  });
  if (!response.ok) throw new Error(`product_api_${response.status}`);
  const payload = await response.json();
  const source = Array.isArray(payload.Products)
    ? payload.Products
    : Array.isArray(payload.items)
      ? payload.items
      : [];
  const products = source
    .map((row) => row && typeof row === "object" && row.Product ? row.Product : row)
    .filter((row) => row && typeof row === "object")
    .map(normalizeProduct)
    .filter(Boolean)
    .sort((a, b) => relevanceScore(b, q) - relevanceScore(a, q));
  return { products, pageCount: safeInt(payload.pageCount), totalCount: safeInt(payload.count) };
}

async function fetchIncludedItems(q, applicationId, accessKey, affiliateId) {
  const params = new URLSearchParams({
    applicationId,
    keyword: q,
    hits: "30",
    format: "json",
    formatVersion: "2",
    availability: "1",
    field: "0",
    sort: "+itemPrice",
    postageFlag: "1",
    elements: "itemName,itemPrice,itemUrl,affiliateUrl,shopName,postageFlag",
  });
  if (affiliateId) params.set("affiliateId", affiliateId);

  const response = await fetch(`${ITEM_API_URL}?${params.toString()}`, {
    headers: {
      accessKey,
      Origin: ALLOWED_ORIGIN,
      Referer: SITE_URL,
      "User-Agent": "daily-cost-jp-vercel-shipping/1.0",
    },
  });
  if (!response.ok) throw new Error(`item_api_${response.status}`);
  const payload = await response.json();
  const source = Array.isArray(payload.items) ? payload.items : [];
  return source
    .map(normalizeItem)
    .filter(Boolean)
    .filter((item) => item.postage_flag === 0);
}

export default async function handler(req, res) {
  const origin = req.headers.origin || "";
  res.setHeader("Vary", "Origin");
  res.setHeader("Access-Control-Allow-Methods", "GET, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  if (!origin || origin === ALLOWED_ORIGIN) {
    res.setHeader("Access-Control-Allow-Origin", ALLOWED_ORIGIN);
  }

  if (req.method === "OPTIONS") return res.status(204).end();
  if (req.method !== "GET") return res.status(405).json({ error: "method_not_allowed" });
  if (origin && origin !== ALLOWED_ORIGIN) return res.status(403).json({ error: "origin_not_allowed" });

  const q = String(req.query.q || "").trim();
  const page = Math.max(1, Math.min(100, safeInt(req.query.page, 1)));
  const hits = Math.max(1, Math.min(30, safeInt(req.query.hits, 20)));
  if (q.length < 2) return res.status(400).json({ error: "query_too_short", message: "2文字以上で検索してください。" });

  const applicationId = process.env.RAKUTEN_APPLICATION_ID;
  const accessKey = process.env.RAKUTEN_ACCESS_KEY;
  const affiliateId = process.env.RAKUTEN_AFFILIATE_ID || "";
  if (!applicationId || !accessKey) return res.status(503).json({ error: "server_not_configured" });

  try {
    const productResult = await fetchProductCandidates(q, page, hits, applicationId, accessKey, affiliateId);
    await sleep(1100);

    let includedItems = [];
    try {
      includedItems = await fetchIncludedItems(q, applicationId, accessKey, affiliateId);
    } catch (err) {
      console.error("included item lookup failed", err);
    }

    const products = attachShipping(productResult.products, includedItems);
    res.setHeader("Cache-Control", "s-maxage=300, stale-while-revalidate=1800");
    return res.status(200).json({
      query: q,
      page,
      hits,
      count: products.length,
      page_count: productResult.pageCount,
      total_count: productResult.totalCount,
      shipping_lookup_count: includedItems.length,
      products,
    });
  } catch (error) {
    console.error("product-search failed", error);
    return res.status(502).json({ error: "rakuten_api_error" });
  }
}
