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
  return String(value || "")
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[\s\u3000]/g, " ")
    .trim();
}

function compact(value: string) {
  return normalize(value).replace(/[\s\u3000\-_/・.,!！?？()（）［］\[\]【】]/g, "");
}

const GENERIC_WORDS = new Set([
  "楽天", "公式", "正規品", "送料無料", "送料込", "送料込み", "セール", "sale",
  "トイレットペーパー", "ティッシュ", "ティッシュペーパー", "洗剤", "シャンプー",
  "コンディショナー", "ボディソープ", "ハンドソープ", "マウスウォッシュ",
  "セット", "まとめ買い", "詰め替え", "詰替", "本体", "無香料",
]);

function wordTokens(name: string, brand: string) {
  const brandKey = compact(brand);
  return normalize(name)
    .replace(/[()（）\[\]【】/／・,，:：;；!！?？+＋×✕]/g, " ")
    .split(/\s+/)
    .map((token) => token.trim())
    .filter(Boolean)
    .filter((token) => token.length >= 2)
    .filter((token) => !/^\d+(?:\.\d+)?(?:ml|l|g|kg|m|枚|個|本|箱|袋|ロール|巻|パック)?$/i.test(token))
    .filter((token) => !GENERIC_WORDS.has(token))
    .filter((token) => compact(token) !== brandKey);
}

function specTokens(name: string) {
  const text = normalize(name).replace(/[＊*×✕]/g, "x");
  const found = text.match(/\d+(?:\.\d+)?\s*(?:ml|l|g|kg|m|cm|mm|枚|個|本|箱|袋|ロール|巻|パック)/gi) || [];
  return Array.from(new Set(found.map((token) => compact(token))));
}

function searchKeyword(name: string, brand: string) {
  const words = wordTokens(name, brand);
  if (words.length) return words[0];
  if (brand.trim().length >= 2) return brand.trim();
  return normalize(name).split(/\s+/).find((token) => token.length >= 2) || "";
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
    url: String(item.affiliateUrl || item.itemUrl || ""),
    postage_flag: safeInt(item.postageFlag, -1),
  };
}

function matchScore(itemName: string, productName: string, brand: string) {
  const item = compact(itemName);
  const product = compact(productName);
  const brandKey = compact(brand);
  const words = wordTokens(productName, brand);
  const specs = specTokens(productName);

  let score = 0;
  if (brandKey && item.includes(brandKey)) score += 8;
  for (const word of words.slice(0, 6)) {
    if (item.includes(compact(word))) score += 5;
  }
  for (const spec of specs) {
    if (item.includes(spec)) score += 7;
    else score -= 6;
  }
  if (product && item.includes(product)) score += 20;
  return { score, words, specs };
}

async function searchIncludedItems(
  keyword: string,
  productName: string,
  brand: string,
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
    postageFlag: "1",
    elements: "itemName,itemPrice,itemUrl,affiliateUrl,shopName,postageFlag",
  });
  if (affiliateId) params.set("affiliateId", affiliateId);

  const response = await fetch(`${ITEM_API_URL}?${params.toString()}`, {
    headers: {
      accessKey,
      Origin: ALLOWED_ORIGIN,
      Referer: SITE_URL,
      "User-Agent": "daily-cost-jp-shipping-included/1.0",
    },
  });
  if (!response.ok) return [];

  const payload = await response.json() as Record<string, unknown>;
  const rawItems = Array.isArray(payload.items) ? payload.items : [];
  const items = rawItems
    .map((row) => normalizeItem(row as Record<string, unknown>))
    .filter(Boolean) as Array<{name:string;price:number;shop:string;url:string;postage_flag:number}>;

  return items
    .map((item) => ({ ...item, ...matchScore(item.name, productName, brand) }))
    .filter((item) => item.postage_flag === 0)
    .sort((a, b) => (b.score - a.score) || (a.price - b.price));
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
    const keyword = searchKeyword(name, brand);
    let candidates: Array<{name:string;price:number;shop:string;url:string;postage_flag:number;score:number;words:string[];specs:string[]}> = [];
    let matchedBy = "none";

    if (keyword) {
      candidates = await searchIncludedItems(keyword, name, brand, applicationId, accessKey, affiliateId);
      if (candidates.length) matchedBy = "name_included";
    }

    if (!candidates.length && /^\d{8,14}$/.test(jan)) {
      if (keyword) await sleep(1100);
      candidates = await searchIncludedItems(jan, name, brand, applicationId, accessKey, affiliateId);
      if (candidates.length) matchedBy = "jan_included";
    }

    const productSpecs = specTokens(name);
    const minAcceptableScore = productSpecs.length ? 5 : 5;
    const plausible = candidates.filter((item) => item.score >= minAcceptableScore);
    const bestScore = plausible.length ? Math.max(...plausible.map((item) => item.score)) : -Infinity;
    const closeMatches = plausible.filter((item) => item.score >= bestScore - 4);
    const best = closeMatches.sort((a, b) => a.price - b.price)[0] || null;

    const includedMin = best?.price || 0;
    const shippingStatus = includedMin > 0 && expectedPrice > 0 && includedMin === expectedPrice
      ? "included"
      : includedMin > 0 && expectedPrice > 0 && includedMin > expectedPrice
        ? "separate"
        : includedMin > 0
          ? "included_available"
          : "unknown";

    headers.set("Cache-Control", "public, s-maxage=300, stale-while-revalidate=1800");
    return new Response(JSON.stringify({
      shipping_status: shippingStatus,
      matched_by: matchedBy,
      included_min_price: includedMin || null,
      included_offer_url: best?.url || "",
      included_shop: best?.shop || "",
      included_offer_name: best?.name || "",
      match_score: best?.score || 0,
      candidate_count: plausible.length,
      note: "included_min_price is the cheapest matched Rakuten item that the API marks as postage included/free shipping; it is not guaranteed to be the absolute lowest price+shipping total among postage-extra offers because the API does not return postage amounts.",
    }), { status: 200, headers });
  } catch (error) {
    console.error("shipping-status failed", error);
    return new Response(JSON.stringify({ shipping_status: "unknown", reason: "internal_error" }), { status: 200, headers });
  }
};

export const config = { path: "/api/shipping-status" };
