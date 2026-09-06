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

function norm(value: string) {
  return String(value || "")
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[×✕]/g, "x")
    .replace(/\s+/g, " ")
    .trim();
}

function compact(value: string) {
  return norm(value).replace(/[\s\-‐‑–—_.,，、/／|｜・:：;；!！?？'"“”‘’()（）\[\]【】]/g, "");
}

const STOP_WORDS = new Set([
  "送料無料", "送料込", "送料込み", "楽天", "楽天市場", "公式", "正規品", "国内正規品",
  "新品", "お買い得", "ポイント", "限定", "セール", "sale", "まとめ買い", "セット",
]);

function isQuantityToken(token: string) {
  return /^\d+(?:\.\d+)?(?:ml|l|g|kg|m|枚|個|本|箱|袋|ロール|巻|パック|包|錠|回分)?$/i.test(token);
}

function words(value: string) {
  return norm(value)
    .replace(/[\-‐‑–—_.,，、/／|｜・:：;；!！?？'"“”‘’()（）\[\]【】]/g, " ")
    .split(/\s+/)
    .map((v) => v.trim())
    .filter((v) => v.length >= 2 && !STOP_WORDS.has(v) && !/^\d+$/.test(v));
}

function quantityTokens(value: string) {
  const text = norm(value).replace(/\s+/g, "");
  const matches = text.match(/\d+(?:\.\d+)?(?:ml|kg|g|l|m|枚|個|本|箱|袋|ロール|巻|パック|包|錠|回分)/gi) || [];
  return Array.from(new Set(matches.map((v) => v.toLowerCase())));
}

function meaningfulWords(name: string, brand: string) {
  const brandCompact = compact(brand);
  const result: string[] = [];
  for (const token of words(name)) {
    if (isQuantityToken(token)) continue;
    const tokenCompact = compact(token);
    if (!tokenCompact || tokenCompact === brandCompact) continue;
    if (!result.some((v) => compact(v) === tokenCompact)) result.push(token);
  }
  return result;
}

function buildQueries(jan: string, name: string, brand: string, productNo: string) {
  const queries: Array<{kind: string; keyword: string}> = [];
  const seen = new Set<string>();
  const add = (kind: string, keyword: string) => {
    const clean = norm(keyword);
    if (clean.length < 2 || seen.has(clean)) return;
    seen.add(clean);
    queries.push({kind, keyword: clean});
  };

  if (/^\d{8,14}$/.test(jan)) add("jan", jan);
  if (productNo && productNo.length >= 4 && compact(productNo) !== compact(jan)) add("product_no", productNo);

  const main = meaningfulWords(name, brand);
  const brandWord = norm(brand);
  if (brandWord && main.length >= 2) add("brand_core", [brandWord, ...main.slice(0, 2)].join(" "));
  if (main.length >= 3) add("core3", main.slice(0, 3).join(" "));
  if (brandWord && main.length >= 1) add("brand_product", [brandWord, main[0]].join(" "));
  if (main.length >= 2) add("core2", main.slice(0, 2).join(" "));
  if (main.length >= 1) add("product", main[0]);
  return queries.slice(0, 7);
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
      "User-Agent": "daily-cost-jp-best-offer/1.1",
    },
  });
  if (!response.ok) return [];
  const payload = await response.json() as Record<string, unknown>;
  const raw = Array.isArray(payload.items) ? payload.items : [];
  return raw.map((row) => normalizeItem(row as Record<string, unknown>)).filter(Boolean) as Array<{
    name: string; price: number; shop: string; url: string; image: string; review_count: number; review_average: number; point_rate: number;
  }>;
}

function selectMatchingOffers(offers: Array<{name: string; price: number; shop: string; url: string; image: string; review_count: number; review_average: number; point_rate: number}>, targetName: string, brand: string, queryKind: string) {
  if (queryKind === "jan" || queryKind === "product_no") return offers;

  const targetWords = meaningfulWords(targetName, brand).slice(0, 6);
  const targetQuantities = quantityTokens(targetName);
  const brandKey = compact(brand);

  const scored = offers.map((offer) => {
    const hay = compact(offer.name);
    let matchedWords = 0;
    let score = 0;
    targetWords.forEach((word, index) => {
      if (hay.includes(compact(word))) {
        matchedWords += 1;
        score += index === 0 ? 6 : 3;
      }
    });
    if (brandKey && hay.includes(brandKey)) score += 4;

    const offerQuantities = new Set(quantityTokens(offer.name));
    const quantityMatches = targetQuantities.filter((q) => offerQuantities.has(q)).length;
    score += quantityMatches * 4;

    const requiredWords = targetWords.length >= 2 ? 2 : 1;
    const enoughWords = matchedWords >= requiredWords;
    const quantityOkay = targetQuantities.length === 0 || offerQuantities.size === 0 || quantityMatches > 0;
    return {offer, score, enoughWords, quantityOkay};
  }).filter((row) => row.enoughWords && row.quantityOkay);

  if (!scored.length) return [];
  const maxScore = Math.max(...scored.map((row) => row.score));
  return scored
    .filter((row) => row.score >= Math.max(3, maxScore - 3))
    .map((row) => row.offer)
    .sort((a, b) => a.price - b.price || b.review_count - a.review_count);
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
  const brand = (url.searchParams.get("brand") || "").trim();
  const productNo = (url.searchParams.get("product_no") || "").trim();
  if (!jan && name.length < 2) return new Response(JSON.stringify({ error: "query_required" }), { status: 400, headers });

  const applicationId = Netlify.env.get("RAKUTEN_APPLICATION_ID");
  const accessKey = Netlify.env.get("RAKUTEN_ACCESS_KEY");
  const affiliateId = Netlify.env.get("RAKUTEN_AFFILIATE_ID") || "";
  if (!applicationId || !accessKey) return new Response(JSON.stringify({ error: "server_not_configured" }), { status: 503, headers });

  try {
    const queries = buildQueries(jan, name, brand, productNo);
    let matched: Array<{name: string; price: number; shop: string; url: string; image: string; review_count: number; review_average: number; point_rate: number}> = [];
    let matchedBy = "none";
    let usedQuery = "";

    for (const query of queries) {
      const offers = await search(query.keyword, applicationId, accessKey, affiliateId);
      const filtered = selectMatchingOffers(offers, name, brand, query.kind);
      if (filtered.length) {
        matched = filtered;
        matchedBy = query.kind;
        usedQuery = query.keyword;
        break;
      }
    }

    const best = matched[0] || null;
    headers.set("Cache-Control", "public, s-maxage=180, stale-while-revalidate=900");
    return new Response(JSON.stringify({
      matched_by: matchedBy,
      query_used: usedQuery,
      count: matched.length,
      best,
      offers: matched.slice(0, 5),
    }), { status: 200, headers });
  } catch (error) {
    console.error("best-offer failed", error);
    return new Response(JSON.stringify({ error: "internal_error" }), { status: 500, headers });
  }
};

export const config = { path: "/api/best-offer" };
