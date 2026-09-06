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

function normalizeItem(raw: Record<string, unknown>) {
  const item = (raw.Item && typeof raw.Item === "object" ? raw.Item : raw) as Record<string, unknown>;
  const price = safeInt(item.itemPrice);
  if (price <= 0) return null;
  const postage = safeInt(item.postageFlag, -1);
  return {
    name: String(item.itemName || ""),
    price,
    shop: String(item.shopName || ""),
    url: String(item.affiliateUrl || item.itemUrl || ""),
    postage_flag: postage,
  };
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
  const jan = (url.searchParams.get("jan") || "").trim();
  const expectedPrice = Math.max(0, safeInt(url.searchParams.get("price"), 0));

  if (!/^\d{8,14}$/.test(jan)) {
    return new Response(JSON.stringify({ shipping_status: "unknown", reason: "no_valid_jan" }), { status: 200, headers });
  }

  const applicationId = Netlify.env.get("RAKUTEN_APPLICATION_ID");
  const accessKey = Netlify.env.get("RAKUTEN_ACCESS_KEY");
  const affiliateId = Netlify.env.get("RAKUTEN_AFFILIATE_ID") || "";
  if (!applicationId || !accessKey) {
    return new Response(JSON.stringify({ error: "server_not_configured" }), { status: 503, headers });
  }

  const params = new URLSearchParams({
    applicationId,
    keyword: jan,
    hits: "30",
    format: "json",
    formatVersion: "2",
    availability: "1",
    field: "0",
    sort: "+itemPrice",
    elements: "itemName,itemPrice,itemUrl,affiliateUrl,shopName,postageFlag",
  });
  if (affiliateId) params.set("affiliateId", affiliateId);

  try {
    const response = await fetch(`${ITEM_API_URL}?${params.toString()}`, {
      headers: {
        accessKey,
        Origin: ALLOWED_ORIGIN,
        Referer: SITE_URL,
        "User-Agent": "daily-cost-jp-shipping-status/1.0",
      },
    });

    if (!response.ok) {
      return new Response(JSON.stringify({ shipping_status: "unknown", reason: "rakuten_api_error" }), { status: 200, headers });
    }

    const payload = await response.json() as Record<string, unknown>;
    const rawItems = Array.isArray(payload.items) ? payload.items : [];
    const items = rawItems
      .map((row) => normalizeItem(row as Record<string, unknown>))
      .filter(Boolean) as Array<{name:string;price:number;shop:string;url:string;postage_flag:number}>;

    if (!items.length) {
      headers.set("Cache-Control", "public, s-maxage=180, stale-while-revalidate=900");
      return new Response(JSON.stringify({ shipping_status: "unknown", reason: "no_matching_item" }), { status: 200, headers });
    }

    const exactPrice = expectedPrice > 0 ? items.find((item) => item.price === expectedPrice) : null;
    const selected = exactPrice || items[0];
    const shippingStatus = selected.postage_flag === 0
      ? "included"
      : selected.postage_flag === 1
        ? "separate"
        : "unknown";

    headers.set("Cache-Control", "public, s-maxage=180, stale-while-revalidate=900");
    return new Response(JSON.stringify({
      shipping_status: shippingStatus,
      matched_price: selected.price,
      price_matches_product_min: Boolean(exactPrice),
      shop: selected.shop,
    }), { status: 200, headers });
  } catch (error) {
    console.error("shipping-status failed", error);
    return new Response(JSON.stringify({ shipping_status: "unknown", reason: "internal_error" }), { status: 200, headers });
  }
};

export const config = { path: "/api/shipping-status" };
