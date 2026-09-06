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

function firstImage(item: Record<string, unknown>) {
  const value = item.mediumImageUrls;
  if (!Array.isArray(value) || !value.length) return "";
  const first = value[0] as unknown;
  if (typeof first === "string") return first.replace("http://", "https://");
  if (first && typeof first === "object") {
    const row = first as Record<string, unknown>;
    return String(row.imageUrl || row.url || "").replace("http://", "https://");
  }
  return "";
}

function normalizeItem(raw: Record<string, unknown>) {
  const item = (raw.Item && typeof raw.Item === "object" ? raw.Item : raw) as Record<string, unknown>;
  const price = Number(item.itemPrice || item.itemPriceMin3 || 0);
  if (!Number.isFinite(price) || price <= 0) return null;
  return {
    name: String(item.itemName || ""),
    price: Math.trunc(price),
    shop: String(item.shopName || ""),
    url: String(item.affiliateUrl || item.itemUrl || ""),
    image: firstImage(item),
    review_count: Number(item.reviewCount || 0),
    review_average: Number(item.reviewAverage || 0),
    point_rate: Number(item.pointRate || 1),
  };
}

async function search(keyword: string, applicationId: string, accessKey: string, affiliateId: string) {
  const params = new URLSearchParams({
    applicationId,
    keyword,
    hits: "30",
    format: "json",
    formatVersion: "2",
    availability: "1",
    postageFlag: "1",
    sort: "+itemPrice",
    field: "0",
  });
  if (affiliateId) params.set("affiliateId", affiliateId);

  const response = await fetch(`${ITEM_API_URL}?${params.toString()}`, {
    headers: {
      accessKey,
      Origin: ALLOWED_ORIGIN,
      Referer: SITE_URL,
      "User-Agent": "daily-cost-jp-best-offer/1.0",
    },
  });
  if (!response.ok) return [];
  const payload = await response.json() as Record<string, unknown>;
  const raw = Array.isArray(payload.items) ? payload.items : [];
  return raw.map((row) => normalizeItem(row as Record<string, unknown>)).filter(Boolean);
}

export default async (req: Request) => {
  const origin = req.headers.get("origin");
  const headers = corsHeaders(origin);
  if (origin && origin !== ALLOWED_ORIGIN) return new Response(JSON.stringify({ error: "origin_not_allowed" }), { status: 403, headers });
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers });
  if (req.method !== "GET") return new Response(JSON.stringify({ error: "method_not_allowed" }), { status: 405, headers });

  const url = new URL(req.url);
  const jan = (url.searchParams.get("jan") || "").trim();
  const name = (url.searchParams.get("name") || "").trim();
  if (!jan && name.length < 2) return new Response(JSON.stringify({ error: "query_required" }), { status: 400, headers });

  const applicationId = Netlify.env.get("RAKUTEN_APPLICATION_ID");
  const accessKey = Netlify.env.get("RAKUTEN_ACCESS_KEY");
  const affiliateId = Netlify.env.get("RAKUTEN_AFFILIATE_ID") || "";
  if (!applicationId || !accessKey) return new Response(JSON.stringify({ error: "server_not_configured" }), { status: 503, headers });

  try {
    let offers = jan ? await search(jan, applicationId, accessKey, affiliateId) : [];
    let matched_by = jan && offers.length ? "jan" : "name";
    if (!offers.length && name) offers = await search(name, applicationId, accessKey, affiliateId);
    const best = offers[0] || null;
    headers.set("Cache-Control", "public, s-maxage=180, stale-while-revalidate=900");
    return new Response(JSON.stringify({ matched_by, count: offers.length, best, offers: offers.slice(0, 5) }), { status: 200, headers });
  } catch (error) {
    console.error("best-offer failed", error);
    return new Response(JSON.stringify({ error: "internal_error" }), { status: 500, headers });
  }
};

export const config = { path: "/api/best-offer" };
