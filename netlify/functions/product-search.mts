const PRODUCT_API_URL = "https://openapi.rakuten.co.jp/ichibaproduct/api/Product/Search/20250801";
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
  };
}

function relevanceScore(product: ReturnType<typeof normalizeProduct>, query: string) {
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

export default async (req: Request) => {
  const origin = req.headers.get("origin");
  const headers = corsHeaders(origin);

  if (origin && origin !== ALLOWED_ORIGIN) {
    return new Response(JSON.stringify({ error: "origin_not_allowed" }), { status: 403, headers });
  }

  if (req.method === "OPTIONS") {
    return new Response(null, { status: 204, headers });
  }

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
        "User-Agent": "daily-cost-jp-realtime/1.1",
      },
    });

    if (!response.ok) {
      const body = await response.text();
      console.error("Rakuten API error", response.status, body.slice(0, 500));
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
      .filter(Boolean)
      .sort((a, b) => relevanceScore(b, q) - relevanceScore(a, q));

    headers.set("Cache-Control", "public, s-maxage=300, stale-while-revalidate=1800");
    return new Response(JSON.stringify({
      query: q,
      page,
      hits,
      count: products.length,
      page_count: safeInt(payload.pageCount),
      total_count: safeInt(payload.count),
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
