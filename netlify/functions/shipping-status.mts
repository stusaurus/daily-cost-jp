const ITEM_API_URL = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701";
const ALLOWED_ORIGIN = "https://stusaurus.github.io";
const SITE_URL = "https://stusaurus.github.io/daily-cost-jp/";

function corsHeaders(origin: string | null) {
  const headers = new Headers({
    "Content-Type": "application/json; charset=utf-8",
    "Vary": "Origin",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  });
  if (!origin || origin === ALLOWED_ORIGIN) headers.set("Access-Control-Allow-Origin", ALLOWED_ORIGIN);
  return headers;
}

function safeInt(value: unknown, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? Math.trunc(n) : fallback;
}

function normalize(value: string) {
  return String(value || "").normalize("NFKC").toLowerCase().trim();
}

const GENERIC_WORDS = new Set([
  "楽天", "公式", "正規品", "送料無料", "送料込", "送料込み", "セール", "sale",
  "トイレットペーパー", "ティッシュ", "ティッシュペーパー", "洗剤", "シャンプー",
  "コンディショナー", "ボディソープ", "ハンドソープ", "マウスウォッシュ",
  "セット", "まとめ買い", "詰め替え", "詰替", "本体",
]);

function distinctiveKeyword(name: string, brand: string) {
  const brandKey = normalize(brand).replace(/\s+/g, "");
  const tokens = normalize(name)
    .replace(/[()（）\[\]【】/／・,，:：;；!！?？+＋×✕]/g, " ")
    .split(/\s+/)
    .map((token) => token.trim())
    .filter(Boolean)
    .filter((token) => token.length >= 2)
    .filter((token) => !/^\d+(?:\.\d+)?(?:ml|l|g|kg|m|枚|個|本|箱|袋|ロール|巻|パック)?$/i.test(token))
    .filter((token) => !GENERIC_WORDS.has(token))
    .filter((token) => token.replace(/\s+/g, "") !== brandKey);

  if (tokens.length) return tokens[0];
  const fallback = normalize(name).replace(/[()（）\[\]【】]/g, " ").split(/\s+/).find((token) => token.length >= 2);
  return fallback || "";
}

function normalizeItem(raw: Record<string, unknown>) {
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
    postage_flag: safeInt(item.postageFlag, -1),
  };
}

async function searchItems(
  keyword: string,
  expectedPrice: number,
  applicationId: string,
  accessKey: string,
  affiliateId: string,
) {
  const params = new URLSearchParams({
    applicationId,
    keyword,
    hits: "30",
    format: "json",
    formatVersion: "2",
    availability: "1",
    field: "0",
    sort: "+itemPrice",
    elements: "itemName,itemPrice,shopName,postageFlag",
  });
  // Rakuten requires maxPrice > minPrice. We still filter to the exact integer price below.
  if (expectedPrice > 0) {
    params.set("minPrice", String(expectedPrice));
    params.set("maxPrice", String(expectedPrice + 1));
  }
  if (affiliateId) params.set("affiliateId", affiliateId);

  const response = await fetch(`${ITEM_API_URL}?${params.toString()}`, {
    headers: {
      accessKey,
      Origin: ALLOWED_ORIGIN,
      Referer: SITE_URL,
      "User-Agent": "daily-cost-jp-shipping-status/1.1",
    },
  });
  if (!response.ok) return [];

  const payload = await response.json() as Record<string, unknown>;
  const rawItems = Array.isArray(payload.items) ? payload.items : [];
  return rawItems
    .map((row) => normalizeItem(row as Record<string, unknown>))
    .filter(Boolean) as Array<{name:string;price:number;shop:string;postage_flag:number}>;
}

function decideStatus(items: Array<{name:string;price:number;shop:string;postage_flag:number}>, expectedPrice: number) {
  const exact = expectedPrice > 0 ? items.filter((item) => item.price === expectedPrice) : items;
  if (!exact.length) return {status: "unknown", exact};

  const flags = exact.map((item) => item.postage_flag).filter((flag) => flag === 0 || flag === 1);
  if (!flags.length) return {status: "unknown", exact};
  // If even one offer at the displayed minimum price includes shipping, don't warn the user.
  if (flags.includes(0)) return {status: "included", exact};
  // Warn only when every known offer at the displayed price is shipping-extra.
  if (flags.every((flag) => flag === 1)) return {status: "separate", exact};
  return {status: "unknown", exact};
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

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
  const jan = (url.searchParams.get("jan") || "").trim();
  const name = (url.searchParams.get("name") || "").trim();
  const brand = (url.searchParams.get("brand") || "").trim();
  const expectedPrice = Math.max(0, safeInt(url.searchParams.get("price"), 0));

  if (!name && !/^\d{8,14}$/.test(jan)) {
    return new Response(JSON.stringify({ shipping_status: "unknown", reason: "no_product_identity" }), { status: 200, headers });
  }

  const applicationId = Netlify.env.get("RAKUTEN_APPLICATION_ID");
  const accessKey = Netlify.env.get("RAKUTEN_ACCESS_KEY");
  const affiliateId = Netlify.env.get("RAKUTEN_AFFILIATE_ID") || "";
  if (!applicationId || !accessKey) {
    return new Response(JSON.stringify({ error: "server_not_configured" }), { status: 503, headers });
  }

  try {
    const keyword = distinctiveKeyword(name, brand);
    let items: Array<{name:string;price:number;shop:string;postage_flag:number}> = [];
    let matchedBy = "none";

    // Product-name search is more reliable than treating a JAN code as a free-text keyword.
    if (keyword) {
      items = await searchItems(keyword, expectedPrice, applicationId, accessKey, affiliateId);
      if (items.length) matchedBy = "name_price";
    }

    // JAN remains a fallback. Space calls to respect the Rakuten API rate limit.
    if (!items.length && /^\d{8,14}$/.test(jan)) {
      if (keyword) await sleep(1100);
      items = await searchItems(jan, expectedPrice, applicationId, accessKey, affiliateId);
      if (items.length) matchedBy = "jan_price";
    }

    const decision = decideStatus(items, expectedPrice);
    headers.set("Cache-Control", "public, s-maxage=180, stale-while-revalidate=900");
    return new Response(JSON.stringify({
      shipping_status: decision.status,
      matched_by: matchedBy,
      exact_offer_count: decision.exact.length,
      included_offer_count: decision.exact.filter((item) => item.postage_flag === 0).length,
      separate_offer_count: decision.exact.filter((item) => item.postage_flag === 1).length,
    }), { status: 200, headers });
  } catch (error) {
    console.error("shipping-status failed", error);
    return new Response(JSON.stringify({ shipping_status: "unknown", reason: "internal_error" }), { status: 200, headers });
  }
};

export const config = { path: "/api/shipping-status" };
