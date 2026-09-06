const PRODUCT_API_URL = "https://openapi.rakuten.co.jp/ichibaproduct/api/Product/Search/20250801";
const ITEM_API_URL = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701";
const ALLOWED_ORIGIN = "https://stusaurus.github.io";
const SITE_URL = "https://stusaurus.github.io/daily-cost-jp/";

function safeInt(value: unknown, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? Math.trunc(n) : fallback;
}

function safeFloat(value: unknown, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function normalizeText(value: unknown) {
  return String(value || "")
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[\s\u3000\-_/・.,!！?？()（）［］\[\]【】]/g, "");
}

function normalizeLoose(value: unknown) {
  return String(value || "")
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[＊*×✕]/g, "x")
    .replace(/[()（）\[\]【】/／・,，:：;；!！?？+＋]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function specTokens(value: unknown) {
  const text = normalizeLoose(value);
  const matches = text.match(/\d+(?:\.\d+)?\s*(?:ml|l|g|kg|m|cm|mm|枚|個|本|箱|袋|ロール|巻|パック)/gi) || [];
  return Array.from(new Set(matches.map((token) => normalizeText(token))));
}

const GENERIC_WORDS = new Set([
  "楽天", "公式", "正規品", "送料無料", "送料込", "送料込み", "セール", "sale",
  "トイレットペーパー", "トイレットロール", "ティッシュ", "ティッシュペーパー",
  "洗剤", "シャンプー", "コンディショナー", "ボディソープ", "ハンドソープ",
  "マウスウォッシュ", "セット", "まとめ買い", "本体", "無香料",
]);

function wordTokens(name: unknown, brand: unknown) {
  const brandKey = normalizeText(brand);
  return normalizeLoose(name)
    .split(/\s+/)
    .map((token) => token.trim())
    .filter(Boolean)
    .filter((token) => token.length >= 2)
    .filter((token) => !/^\d+(?:\.\d+)?(?:ml|l|g|kg|m|cm|mm|枚|個|本|箱|袋|ロール|巻|パック)?$/i.test(token))
    .filter((token) => !GENERIC_WORDS.has(token))
    .filter((token) => normalizeText(token) !== brandKey);
}

function normalizeProduct(raw: Record<string, unknown>) {
  const productId = String(raw.productId || "").trim();
  const name = String(raw.productName || "").trim();
  if (!productId || !name) return null;

  const minPrice = safeInt(raw.usedExcludeSalesMinPrice) || safeInt(raw.salesMinPrice);
  if (minPrice <= 0) return null;

  return {
    product_id: productId,
    product_code: String(raw.productCode || ""),
    name,
    product_no: String(raw.productNo || ""),
    brand: String(raw.brandName || ""),
    genre: String(raw.genreName || ""),
    min_price: minPrice,
    average_price: safeInt(raw.averagePrice),
    seller_count: safeInt(raw.salesItemCount),
    review_count: safeInt(raw.reviewCount),
    review_average: safeFloat(raw.reviewAverage),
    image: String(raw.mediumImageUrl || "").replace("http://", "https://"),
    url: String(raw.affiliateUrl || raw.productUrlPC || ""),
    shipping_included_price: 0,
    shipping_included_url: "",
    shipping_included_shop: "",
    shipping_match: "none",
  };
}

type Product = NonNullable<ReturnType<typeof normalizeProduct>>;

type MarketItem = {
  name: string;
  price: number;
  shop: string;
  url: string;
  postage_flag: number;
};

function relevanceScore(product: Product | null, query: string) {
  if (!product) return -1;
  const q = normalizeText(query);
  const name = normalizeText(product.name);
  const brand = normalizeText(product.brand);
  const code = normalizeText(product.product_code);
  const no = normalizeText(product.product_no);
  let score = 0;

  if (code && code === q) score += 10000;
  if (no && no === q) score += 9000;
  if (brand && brand === q) score += 1800;
  if (name === q) score += 2000;
  if (name.startsWith(q)) score += 1200;
  if (brand.startsWith(q)) score += 900;

  const nameIndex = name.indexOf(q);
  if (nameIndex >= 0) score += 700 - Math.min(nameIndex, 300);
  const brandIndex = brand.indexOf(q);
  if (brandIndex >= 0) score += 500 - Math.min(brandIndex, 200);

  score += Math.min(150, Math.log10(product.review_count + 1) * 35);
  score += Math.min(80, Math.log10(product.seller_count + 1) * 20);
  return score;
}

function normalizeMarketItem(raw: Record<string, unknown>) {
  const item = (raw.item && typeof raw.item === "object"
    ? raw.item
    : raw.Item && typeof raw.Item === "object"
      ? raw.Item
      : raw) as Record<string, unknown>;
  const price = safeInt(item.itemPrice);
  if (price <= 0) return null;
  return {
    name: String(item.itemName || ""),
    price,
    shop: String(item.shopName || ""),
    url: String(item.affiliateUrl || item.itemUrl || ""),
    postage_flag: safeInt(item.postageFlag, -1),
  } as MarketItem;
}

function marketMatchScore(product: Product, item: MarketItem) {
  const itemKey = normalizeText(item.name);
  const productKey = normalizeText(product.name);
  const brandKey = normalizeText(product.brand);
  const words = wordTokens(product.name, product.brand);
  const requiredSpecs = specTokens(product.name);
  const itemSpecs = specTokens(item.name);

  let score = 0;
  let wordHits = 0;

  if (brandKey && itemKey.includes(brandKey)) score += 8;
  for (const word of words.slice(0, 7)) {
    const key = normalizeText(word);
    if (key && itemKey.includes(key)) {
      score += 6;
      wordHits += 1;
    }
  }

  let missingSpec = false;
  for (const spec of requiredSpecs) {
    if (itemKey.includes(spec)) score += 12;
    else {
      score -= 30;
      missingSpec = true;
    }
  }

  const extraSpecs = itemSpecs.filter((spec) => !requiredSpecs.includes(spec));
  if (requiredSpecs.length && extraSpecs.length) score -= extraSpecs.length * 18;
  if (productKey && itemKey.includes(productKey)) score += 25;

  const strongIdentity = wordHits >= 1 || (!!brandKey && itemKey.includes(brandKey));
  const acceptable = !missingSpec && strongIdentity && score >= (requiredSpecs.length ? 14 : 12);
  return { score, acceptable, extra_specs: extraSpecs.length, word_hits: wordHits };
}

function enrichWithShipping(products: Product[], items: MarketItem[]) {
  for (const product of products) {
    const matches = items
      .map((item) => ({ item, ...marketMatchScore(product, item) }))
      .filter((row) => row.acceptable)
      .sort((a, b) => (a.item.price - b.item.price) || (b.score - a.score));

    const best = matches[0];
    if (!best) continue;

    product.shipping_included_price = best.item.price;
    product.shipping_included_url = best.item.url;
    product.shipping_included_shop = best.item.shop;
    product.shipping_match = "batch_item_search";
  }
}

function corsHeaders(origin: string | null) {
  const headers = new Headers({
    "Content-Type": "application/json; charset=utf-8",
    "Vary": "Origin",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  });
  if (!origin || origin === ALLOWED_ORIGIN) {
    headers.set("Access-Control-Allow-Origin", ALLOWED_ORIGIN);
  }
  return headers;
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function fetchShippingIncludedItems(
  q: string,
  applicationId: string,
  accessKey: string,
  affiliateId: string,
) {
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
      "User-Agent": "daily-cost-jp-realtime/2.0",
    },
  });

  if (!response.ok) {
    const body = await response.text();
    console.error("Rakuten Item API error", response.status, body.slice(0, 300));
    return [];
  }

  const payload = await response.json() as Record<string, unknown>;
  const rawItems = Array.isArray(payload.items) ? payload.items : [];
  return rawItems
    .map((row) => normalizeMarketItem(row as Record<string, unknown>))
    .filter((row): row is MarketItem => !!row)
    .filter((row) => row.postage_flag === 0);
}

export default async (req: Request) => {
  const origin = req.headers.get("origin");
  const headers = corsHeaders(origin);

  if (origin && origin !== ALLOWED_ORIGIN) {
    return new Response(JSON.stringify({ error: "origin_not_allowed" }), { status: 403, headers });
  }

  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers });
  if (req.method !== "GET") {
    return new Response(JSON.stringify({ error: "method_not_allowed" }), { status: 405, headers });
  }

  const url = new URL(req.url);
  const q = (url.searchParams.get("q") || "").trim();
  const page = Math.max(1, Math.min(100, safeInt(url.searchParams.get("page"), 1)));
  const hits = Math.max(1, Math.min(30, safeInt(url.searchParams.get("hits"), 30)));

  if (q.length < 2) {
    return new Response(JSON.stringify({ error: "query_too_short", message: "2文字以上で検索してください。" }), { status: 400, headers });
  }

  const applicationId = Netlify.env.get("RAKUTEN_APPLICATION_ID");
  const accessKey = Netlify.env.get("RAKUTEN_ACCESS_KEY");
  const affiliateId = Netlify.env.get("RAKUTEN_AFFILIATE_ID") || "";

  if (!applicationId || !accessKey) {
    return new Response(JSON.stringify({ error: "server_not_configured" }), { status: 503, headers });
  }

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
      "usedExcludeSalesMinPrice", "salesMinPrice", "averagePrice",
      "reviewCount", "reviewAverage", "genreName"
    ].join(","),
  });
  if (affiliateId) params.set("affiliateId", affiliateId);

  try {
    const response = await fetch(`${PRODUCT_API_URL}?${params.toString()}`, {
      headers: {
        accessKey,
        Origin: ALLOWED_ORIGIN,
        Referer: SITE_URL,
        "User-Agent": "daily-cost-jp-realtime/2.0",
      },
    });

    if (!response.ok) {
      const body = await response.text();
      console.error("Rakuten Product API error", response.status, body.slice(0, 500));
      return new Response(JSON.stringify({ error: "rakuten_api_error", status: response.status }), { status: 502, headers });
    }

    const payload = await response.json() as Record<string, unknown>;
    const rawItemsSource = Array.isArray(payload.Products)
      ? payload.Products
      : Array.isArray(payload.items)
        ? payload.items
        : [];
    const rawItems = rawItemsSource
      .map((item) => {
        if (item && typeof item === "object" && "Product" in (item as Record<string, unknown>)) {
          return (item as Record<string, unknown>).Product;
        }
        return item;
      })
      .filter((item) => item && typeof item === "object") as Record<string, unknown>[];

    const products = rawItems
      .map((item) => normalizeProduct(item))
      .filter((item): item is Product => !!item)
      .sort((a, b) => relevanceScore(b, q) - relevanceScore(a, q));

    // Rakuten's app-level rate limit is intentionally respected: one product lookup,
    // then one postage-included market lookup for the whole visible result set.
    await sleep(1100);
    const shippingItems = await fetchShippingIncludedItems(q, applicationId, accessKey, affiliateId);
    enrichWithShipping(products, shippingItems);

    headers.set("Cache-Control", "public, s-maxage=300, stale-while-revalidate=1800");
    return new Response(JSON.stringify({
      query: q,
      page,
      hits,
      count: products.length,
      page_count: safeInt(payload.pageCount),
      total_count: safeInt(payload.count),
      shipping_lookup: "batch",
      shipping_candidate_count: shippingItems.length,
      products,
    }), { status: 200, headers });
  } catch (error) {
    console.error("product-search failed", error);
    return new Response(JSON.stringify({ error: "internal_error" }), { status: 500, headers });
  }
};

export const config = {
  path: "/api/product-search",
};
