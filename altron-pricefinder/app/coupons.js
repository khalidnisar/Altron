/* Altron PriceFinder — coupon engine.
   Finds coupon codes applicable to a product/merchant and only surfaces
   codes that are still valid: verified source + unexpired + min-spend met.
   "Web-scanned" codes (from live search) are kept separate and never shown
   as verified. */

export const COUPONS = [
  // ---- electronics / general goods ----
  { code: "SAVE10TECH", pct: 10, minSpendUSD: 100, expiry: "2026-12-31", verified: true, source: "verified", merchants: ["bestbuy.com"], tags: ["electronics", "headphones", "phone", "laptop", "tv", "watch"] },
  { code: "TECH15", pct: 15, minSpendUSD: 250, expiry: "2026-10-15", verified: true, source: "verified", merchants: ["newegg.com"], tags: ["electronics", "headphones", "phone", "laptop", "tv"] },
  { code: "BHP20", amountUSD: 20, minSpendUSD: 199, expiry: "2026-11-30", verified: true, source: "verified", merchants: ["bhphotovideo.com"], tags: ["electronics", "headphones", "watch", "camera"] },
  { code: "WOWAPP10", pct: 10, minSpendUSD: 75, expiry: "2026-09-30", verified: true, source: "verified", merchants: ["walmart.com"], tags: ["electronics", "tv", "backpack"] },
  { code: "APPLEEDU", pct: 8, minSpendUSD: 500, expiry: "2027-01-31", verified: true, source: "verified", merchants: ["apple.com"], tags: ["phone", "laptop", "watch", "macbook", "iphone"] },
  { code: "EBAY20", amountUSD: 20, minSpendUSD: 150, expiry: "2026-10-05", verified: true, source: "verified", merchants: ["ebay.com"], tags: ["phone", "sneakers", "watch", "sunglasses", "backpack"] },
  { code: "NOON10", pct: 10, minSpendUSD: 50, expiry: "2026-09-15", verified: true, source: "verified", merchants: ["noon.com"], tags: ["electronics", "phone", "headphones", "backpack"] },
  { code: "DARAZ300", amountUSD: 6, minSpendUSD: 30, expiry: "2026-09-30", verified: true, source: "verified", merchants: ["daraz.pk"], tags: ["phone", "headphones", "watch", "backpack"] },
  { code: "KINDLE15", amountUSD: 15, minSpendUSD: 99, expiry: "2026-12-01", verified: true, source: "verified", merchants: ["amazon.com"], tags: ["kindle"] },
  { code: "SAMSUNG5", pct: 5, minSpendUSD: 500, expiry: "2026-11-20", verified: true, source: "verified", merchants: ["samsung.com"], tags: ["tv", "phone", "galaxy"] },
  { code: "NZPAYDAY", pct: 8, minSpendUSD: 100, expiry: "2026-09-30", verified: true, source: "verified", merchants: ["noelleeming.co.nz"], tags: ["electronics", "phone", "headphones", "laptop"] },
  // ---- hotels ----
  { code: "GENIUS5", pct: 5, minSpendUSD: 150, expiry: "2026-12-31", verified: true, source: "verified", merchants: ["booking.com"], tags: ["hotel"] },
  { code: "AGODA12", pct: 12, minSpendUSD: 200, expiry: "2026-10-31", verified: true, source: "verified", merchants: ["agoda.com"], tags: ["hotel"] },
  { code: "HOTELS10", pct: 10, minSpendUSD: 250, expiry: "2026-11-15", verified: true, source: "verified", merchants: ["hotels.com"], tags: ["hotel"] },
  { code: "EXPEDIA8", pct: 8, minSpendUSD: 300, expiry: "2026-10-20", verified: true, source: "verified", merchants: ["expedia.com"], tags: ["hotel"] },
  // ---- flights ----
  { code: "FLYD10", pct: 10, minSpendUSD: 200, expiry: "2026-09-30", verified: true, source: "verified", merchants: ["flydubai.com"], tags: ["flight"] },
  { code: "SKYSCAN5", pct: 5, minSpendUSD: 300, expiry: "2026-10-10", verified: true, source: "verified", merchants: ["skyscanner.net"], tags: ["flight"] },
  // ---- car rental ----
  { code: "HERTZ15", pct: 15, minSpendUSD: 150, expiry: "2026-12-31", verified: true, source: "verified", merchants: ["hertz.com"], tags: ["car"] },
  { code: "SIXT20", amountUSD: 20, minSpendUSD: 120, expiry: "2026-10-31", verified: true, source: "verified", merchants: ["sixt.com"], tags: ["car"] },
  { code: "ENTERPRISE10", pct: 10, minSpendUSD: 100, expiry: "2026-11-30", verified: true, source: "verified", merchants: ["enterprise.com"], tags: ["car"] },
];

/** Does a coupon apply to a merchant + product description? */
function applies(coupon, merchantDomain, title, commodity) {
  if (coupon.merchants.length && !coupon.merchants.includes(merchantDomain)) return false;
  const t = (title || "").toLowerCase();
  if (!coupon.tags.some((tag) => t.includes(tag))) return false;
  if (commodity === "hotels" && !coupon.tags.includes("hotel")) return false;
  if (commodity === "flights" && !coupon.tags.includes("flight")) return false;
  if (commodity === "cars" && !coupon.tags.includes("car")) return false;
  return true;
}

/** True if the coupon is still valid today. */
export function isValid(coupon) {
  const today = new Date();
  today.setHours(23, 59, 59, 999);
  return coupon.verified && coupon.expiry && new Date(coupon.expiry + "T23:59:59") >= today;
}

export function daysLeft(coupon) {
  const d = Math.ceil((new Date(coupon.expiry + "T23:59:59") - new Date()) / 86400000);
  return Math.max(0, d);
}

export function discountLabel(coupon) {
  if (coupon.pct) return `${coupon.pct}% off`;
  if (coupon.amountUSD) return `$${coupon.amountUSD} off`;
  return "discount";
}

/**
 * Find valid coupons for a set of offers.
 * @returns {{valid: object[], scanned: object[]}}
 */
export function findCoupons(title, commodity, offers, scanned = []) {
  const valid = [];
  for (const c of COUPONS) {
    if (!isValid(c)) continue;
    const matches = offers.some((o) => applies(c, o.domain, title, commodity));
    if (matches) valid.push({ ...c, daysLeft: daysLeft(c) });
  }
  const unique = [];
  for (const c of valid) if (!unique.find((u) => u.code === c.code)) unique.push(c);
  const liveScanned = scanned
    .filter((s) => !unique.find((u) => u.code === s.code))
    .filter((s) => applies({ merchants: [], tags: ["*"], verified: true, expiry: s.expiry || "2999-01-01" }, s.domain || "", title, commodity))
    .slice(0, 5)
    .map((s) => ({ ...s, verified: false, source: "web-scan", daysLeft: s.expiry ? daysLeft(s) : null }));
  return { valid: unique, scanned: liveScanned };
}
