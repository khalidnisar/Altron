/* Altron PriceFinder — demo marketplace dataset + search engine.
   Fully realistic offline mode: goods, hotels, flights and car rentals
   with trusted merchants, price history (yearly max), geo pricing and
   cookie-markup simulation. Prices are stored in USD. */

import { MERCHANTS, classify, merchantUrl } from "./trust.js";

/* ---------------- geo spoofing ---------------- */
export const GEO = [
  { id: "us", label: "🇺🇸 United States",  currency: "USD", mult: 1.0 },
  { id: "uk", label: "🇬🇧 United Kingdom", currency: "GBP", mult: 1.06 },
  { id: "ae", label: "🇦🇪 UAE / Dubai",     currency: "AED", mult: 1.05 },
  { id: "pk", label: "🇵🇰 Pakistan",        currency: "PKR", mult: 0.93 },
  { id: "nz", label: "🇳🇿 New Zealand",     currency: "NZD", mult: 1.12 },
  { id: "de", label: "🇩🇪 Germany",         currency: "EUR", mult: 1.07 },
  { id: "in", label: "🇮🇳 India",           currency: "INR", mult: 0.91 },
  { id: "sg", label: "🇸🇬 Singapore",       currency: "SGD", mult: 1.13 },
  { id: "au", label: "🇦🇺 Australia",       currency: "AUD", mult: 1.1 },
  { id: "jp", label: "🇯🇵 Japan",           currency: "JPY", mult: 1.04 },
];
export const GEO_BY_ID = Object.fromEntries(GEO.map((g) => [g.id, g]));

/* Merchants that quietly bump prices for repeat/cookie-identified visitors. */
const COOKIE_MARKUP = { amazon: 0.08, "booking.com": 0.1, "expedia.com": 0.09, "ebay.com": 0.06, "aliexpress.com": 0.12, "daraz.pk": 0.07, "noon.com": 0.09, "kiwi.com": 0.06 };

/* Deterministic pseudo-random so the same search looks stable. */
function seed(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}
function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const jitter = (s, lo, hi) => { const r = mulberry32(seed(s)); return lo + r() * (hi - lo); };

/* ---------------- goods catalog ---------------- */
const G = (key, name, emoji, ref, base, yearMax, yearAvg, cats, merchants) => ({
  key, name, emoji, ref, base, yearMax, yearAvg, cats, merchants,
});

const GOODS = [
  G("iphone16pro", "Apple iPhone 16 Pro (128GB)", "📱", "phone", 929, 1099, 1019, ["phone", "iphone", "apple", "smartphone", "mobile", "electronics"],
    [["amazon", -0.01, "Free 2-day · Prime"], ["bestbuy", 0.02, "Free next-day"], ["apple", 0.06, "Free engraving"], ["walmart", 0.03, "Free delivery"], ["ebay", -0.05, "eBay Refurbished"], ["noon", -0.02, "UAE stock"], ["daraz", -0.04, "PKR pricing"], ["megadeals", -0.38, "???"]]),
  G("sonyxm5", "Sony WH-1000XM5 Headphones", "🎧", "headphones", 328, 399, 359, ["headphones", "sony", "audio", "wireless", "electronics"],
    [["amazon", 0.0, "Free 2-day · Prime"], ["bestbuy", 0.04, "Free next-day"], ["bhp", 0.03, "Free shipping"], ["walmart", 0.02, "Free delivery"], ["ebay", -0.06, "Open-box deals"], ["noon", -0.03, "UAE stock"], ["daraz", -0.05, "PKR pricing"], ["electrobarg", -0.4, "???"]]),
  G("af1", "Nike Air Force 1 '07 (White)", "👟", "sneakers", 115, 130, 118, ["sneakers", "shoes", "nike", "trainers", "fashion"],
    [["amazon", 0.0, "Free 2-day"], ["ebay", -0.05, "Verified sellers"], ["walmart", 0.03, "Free delivery"], ["target", 0.02, "Store pickup"], ["daraz", -0.06, "PKR pricing"], ["noon", -0.02, "UAE stock"], ["phoned", -0.35, "???"]]),
  G("watch9", "Apple Watch Series 9 (45mm GPS)", "⌚", "smartwatch", 359, 429, 394, ["watch", "apple", "smartwatch", "wearable", "electronics"],
    [["amazon", 0.01, "Free 2-day"], ["apple", 0.04, "Free engraving"], ["bestbuy", 0.0, "Free next-day"], ["walmart", 0.02, "Free delivery"], ["ebay", -0.04, "Open-box deals"], ["noon", -0.03, "UAE stock"], ["megadeals", -0.36, "???"]]),
  G("macair", "MacBook Air 13\" (M3, 16GB/256GB)", "💻", null, 999, 1199, 1099, ["laptop", "macbook", "apple", "computer", "electronics"],
    [["amazon", 0.01, "Free 2-day"], ["apple", 0.0, "Free engraving"], ["bestbuy", 0.03, "Free next-day"], ["bhp", 0.02, "Free shipping"], ["walmart", 0.04, "Free delivery"], ["ebay", -0.04, "Certified refurb"], ["noon", -0.03, "UAE stock"]]),
  G("qled65", "Samsung 65\" Neo QLED 4K TV (QN90D)", "📺", null, 1398, 1899, 1649, ["tv", "samsung", "television", "electronics", "screen"],
    [["amazon", 0.01, "Free delivery"], ["bestbuy", 0.0, "Free next-day"], ["samsung", 0.03, "Direct"], ["walmart", 0.02, "Free delivery"], ["costco", 0.05, "2-yr warranty"], ["currys", 0.06, "UK stock"], ["noon", -0.02, "UAE stock"]]),
  G("dysonv15", "Dyson V15 Detect Cordless Vacuum", "🌀", null, 549, 749, 649, ["vacuum", "dyson", "home", "appliance"],
    [["amazon", 0.0, "Free 2-day"], ["bestbuy", 0.03, "Free next-day"], ["walmart", 0.02, "Free delivery"], ["costco", 0.04, "Includes kit"], ["argos", 0.07, "UK stock"], ["noon", -0.03, "UAE stock"]]),
  G("mxmaster", "Logitech MX Master 3S Mouse", "🖱️", null, 89, 99, 93, ["mouse", "logitech", "computer", "peripherals", "electronics"],
    [["amazon", 0.0, "Free 2-day"], ["bestbuy", 0.03, "Free next-day"], ["bhp", 0.02, "Free shipping"], ["walmart", 0.04, "Free delivery"], ["newegg", -0.02, "Free shipping"], ["noon", -0.04, "UAE stock"]]),
  G("kindle", "Kindle Paperwhite (16GB, 2024)", "📚", null, 149, 159, 154, ["kindle", "ebook", "amazon", "reading", "electronics"],
    [["amazon", 0.0, "Free 2-day"], ["bestbuy", 0.02, "Free next-day"], ["walmart", 0.04, "Free delivery"], ["target", 0.03, "Store pickup"], ["ebay", -0.03, "Like-new deals"]]),
  G("ps5", "Sony PlayStation 5 Slim (Disc)", "🎮", null, 449, 499, 474, ["playstation", "ps5", "gaming", "console", "electronics"],
    [["amazon", 0.01, "Free 2-day"], ["bestbuy", 0.0, "Free next-day"], ["walmart", 0.02, "Free delivery"], ["target", 0.03, "Store pickup"], ["ebay", -0.03, "Bundle deals"], ["noon", -0.02, "UAE stock"]]),
  G("boseqc", "Bose QuietComfort Ultra Headphones", "🎧", null, 349, 429, 389, ["headphones", "bose", "audio", "noise cancelling", "electronics"],
    [["amazon", 0.0, "Free 2-day"], ["bestbuy", 0.03, "Free next-day"], ["bhp", 0.02, "Free shipping"], ["walmart", 0.04, "Free delivery"], ["ebay", -0.05, "Open-box deals"], ["noon", -0.03, "UAE stock"]]),
  G("backpack", "Samsonite Paradigm 2.0 Backpack (15.6\")", "🎒", "backpack", 118, 140, 129, ["backpack", "bag", "samsonite", "travel", "luggage"],
    [["amazon", 0.0, "Free 2-day"], ["walmart", 0.03, "Free delivery"], ["target", 0.02, "Store pickup"], ["ebay", -0.06, "Verified sellers"], ["noon", -0.03, "UAE stock"], ["daraz", -0.05, "PKR pricing"]]),
  G("aviator", "Ray-Ban Aviator Classic (Gold/Green)", "🕶️", "sunglasses", 153, 165, 158, ["sunglasses", "rayban", "aviator", "fashion", "eyewear"],
    [["amazon", 0.0, "Free 2-day"], ["ebay", -0.07, "Authenticity check"], ["walmart", 0.04, "Free delivery"], ["target", 0.03, "Store pickup"], ["noon", -0.02, "UAE stock"], ["daraz", -0.06, "PKR pricing"], ["phoned", -0.32, "???"]]),
];

const SPAM_KEY = { megadeals: "megadeals", electrobarg: "electrobarg", phoned: "phoned" };
const REF_IMAGE = { phone: "assets/ref/phone.png", sneakers: "assets/ref/sneakers.png", headphones: "assets/ref/headphones.png", smartwatch: "assets/ref/smartwatch.png", backpack: "assets/ref/backpack.png", sunglasses: "assets/ref/sunglasses.png" };

/* ---------------- hotels ---------------- */
const HOTEL_DESTINATIONS = {
  dubai: { name: "Dubai", aliases: ["dubai", "dxb", "uae", "emirates"], properties: [
    { name: "Atlantis The Palm", area: "Palm Jumeirah", emoji: "🏛️", stars: 5, rating: 4.7, reviews: 12300, base: 385, yearMax: 720, perks: ["Private beach", "Aquaventure access", "Free breakfast"], otas: [["booking", 0.0], ["agoda", -0.04], ["expedia", 0.05], ["hotelsdotcom", 0.02], ["kayak", -0.02]] },
    { name: "Burj Al Arab Jumeirah", area: "Jumeirah Beach", emoji: "⛵", stars: 5, rating: 4.9, reviews: 6400, base: 1450, yearMax: 2600, perks: ["Private butler", "Helipad tours", "Full-board"], otas: [["booking", 0.02], ["expedia", 0.06], ["kayak", -0.03], ["tripcom", -0.05]] },
    { name: "Rove Downtown", area: "Downtown Dubai", emoji: "🏨", stars: 3, rating: 4.5, reviews: 8900, base: 118, yearMax: 210, perks: ["Free WiFi", "Burj Khalifa view", "Late checkout"], otas: [["booking", 0.0], ["agoda", -0.06], ["expedia", 0.03], ["hotelsdotcom", 0.01]] },
    { name: "Citymax Bur Dubai", area: "Bur Dubai", emoji: "🛎️", stars: 3, rating: 4.3, reviews: 5100, base: 82, yearMax: 150, perks: ["Metro 5 min", "24/7 gym", "Free parking"], otas: [["booking", 0.01], ["agoda", -0.05], ["makemytrip", -0.04], ["expedia", 0.04]] },
  ]},
  london: { name: "London", aliases: ["london", "lon", "uk", "britain"], properties: [
    { name: "The Ritz London", area: "Mayfair", emoji: "👑", stars: 5, rating: 4.8, reviews: 4200, base: 890, yearMax: 1450, perks: ["Michelin dining", "Afternoon tea", "Concierge"], otas: [["booking", 0.01], ["expedia", 0.05], ["kayak", -0.02], ["hotelsdotcom", 0.03]] },
    { name: "The Savoy", area: "Strand", emoji: "🏰", stars: 5, rating: 4.8, reviews: 3800, base: 645, yearMax: 1100, perks: ["River view", "Spa access", "Luxury toiletries"], otas: [["booking", 0.0], ["expedia", 0.04], ["kayak", -0.03]] },
    { name: "Premier Inn London City", area: "Aldgate", emoji: "🏨", stars: 3, rating: 4.4, reviews: 15600, base: 142, yearMax: 260, perks: ["Free WiFi", "Family rooms", "Air conditioning"], otas: [["booking", 0.0], ["agoda", -0.05], ["expedia", 0.03], ["hotelsdotcom", 0.02]] },
    { name: "Travelodge Central Southwark", area: "Southwark", emoji: "🛏️", stars: 2, rating: 4.1, reviews: 9800, base: 96, yearMax: 190, perks: ["24h reception", "Free WiFi", "Near Tube"], otas: [["booking", 0.02], ["agoda", -0.04], ["kayak", -0.01]] },
  ]},
  lahore: { name: "Lahore", aliases: ["lahore", "lhe", "pakistan"], properties: [
    { name: "Pearl Continental Lahore", area: "Mall Road", emoji: "🏨", stars: 5, rating: 4.6, reviews: 7200, base: 168, yearMax: 250, perks: ["Free breakfast", "Pool & gym", "Airport shuttle"], otas: [["booking", 0.0], ["agoda", -0.05], ["makemytrip", -0.03], ["tripcom", -0.04]] },
    { name: "Avari Towers Lahore", area: "Shahrah-e-Quaid-e-Azam", emoji: "🏢", stars: 5, rating: 4.5, reviews: 5300, base: 142, yearMax: 220, perks: ["Skyline views", "24h room service", "Free parking"], otas: [["booking", 0.01], ["agoda", -0.06], ["expedia", 0.04]] },
    { name: "Heritage Luxury Suites", area: "Gulberg", emoji: "🛎️", stars: 4, rating: 4.4, reviews: 1900, base: 74, yearMax: 120, perks: ["Kitchenette", "Free WiFi", "Gym"], otas: [["booking", 0.02], ["agoda", -0.04], ["makemytrip", 0.0]] },
    { name: "Faletti's Hotel Lahore", area: "Egerton Road", emoji: "🏛️", stars: 4, rating: 4.3, reviews: 2600, base: 88, yearMax: 140, perks: ["Heritage property", "Gardens", "Restaurant"], otas: [["booking", 0.01], ["expedia", 0.03], ["kayak", -0.02]] },
  ]},
  newyork: { name: "New York", aliases: ["new york", "nyc", "new york city", "manhattan", "usa", "america"], properties: [
    { name: "The Plaza Hotel", area: "Fifth Avenue", emoji: "🏛️", stars: 5, rating: 4.7, reviews: 9800, base: 780, yearMax: 1400, perks: ["Central Park view", "Spa", "Gilded-era rooms"], otas: [["booking", 0.02], ["expedia", 0.05], ["kayak", -0.03], ["hotelsdotcom", 0.04]] },
    { name: "The Ludlow Hotel", area: "Lower East Side", emoji: "🏨", stars: 4, rating: 4.6, reviews: 3200, base: 340, yearMax: 520, perks: ["Rooftop bar", "Pet friendly", "Neo-industrial rooms"], otas: [["booking", 0.0], ["agoda", -0.04], ["expedia", 0.04]] },
    { name: "Row NYC Times Square", area: "Midtown", emoji: "🏢", stars: 3, rating: 4.0, reviews: 14500, base: 210, yearMax: 380, perks: ["Times Square 2 min", "Free WiFi", "On-site dining"], otas: [["booking", 0.01], ["agoda", -0.05], ["expedia", 0.03], ["hotelsdotcom", 0.02]] },
  ]},
  islamabad: { name: "Islamabad", aliases: ["islamabad", "isb", "rawalpindi"], properties: [
    { name: "Serena Hotel Islamabad", area: "F-5", emoji: "🏨", stars: 5, rating: 4.7, reviews: 4100, base: 195, yearMax: 300, perks: ["Mountains view", "Free breakfast", "Spa"], otas: [["booking", 0.0], ["agoda", -0.05], ["makemytrip", -0.03]] },
    { name: "Islamabad Marriott", area: "Agha Khan Road", emoji: "🏢", stars: 5, rating: 4.5, reviews: 3600, base: 155, yearMax: 240, perks: ["Pool", "Steakhouse", "Business lounge"], otas: [["booking", 0.01], ["expedia", 0.04], ["tripcom", -0.04]] },
  ]},
};

/* ---------------- flights ---------------- */
const FLIGHT_ROUTES = [
  { id: "lhr-dxb", from: "London (LHR)", to: "Dubai (DXB)", emoji: "✈️", duration: "7h 10m", stops: "Non-stop", baggage: "Cabin bag + 23kg hold", base: 468, yearMax: 940, airlines: [["emirates", 0.08], ["british", 0.12], ["flydubai", -0.06], ["etihad", 0.16]], otas: [["skyscanner", -0.04], ["kayak", -0.06], ["kiwi", -0.1], ["expedia", 0.03], ["gflights", -0.02]] },
  { id: "jfk-dxb", from: "New York (JFK)", to: "Dubai (DXB)", emoji: "🛫", duration: "12h 35m", stops: "Non-stop", baggage: "Cabin bag + 23kg hold", base: 712, yearMax: 1400, airlines: [["emirates", 0.05], ["etihad", 0.14], ["qatar", 0.18]], otas: [["skyscanner", -0.05], ["kayak", -0.06], ["kiwi", -0.09], ["expedia", 0.04], ["gflights", -0.03]] },
  { id: "isb-dxb", from: "Islamabad (ISB)", to: "Dubai (DXB)", emoji: "🛬", duration: "3h 20m", stops: "Non-stop", baggage: "Cabin bag + 30kg hold", base: 238, yearMax: 480, airlines: [["pia", -0.05], ["emirates", 0.12], ["flydubai", -0.02], ["etihad", 0.18]], otas: [["skyscanner", -0.06], ["kayak", -0.08], ["kiwi", -0.11], ["gflights", -0.04]] },
  { id: "akl-syd", from: "Auckland (AKL)", to: "Sydney (SYD)", emoji: "🦘", duration: "3h 05m", stops: "Non-stop", baggage: "Cabin bag + 23kg hold", base: 262, yearMax: 520, airlines: [["airnewzealand", 0.06], ["qatar", 0.2]], otas: [["skyscanner", -0.05], ["kayak", -0.07], ["kiwi", -0.1], ["gflights", -0.03]] },
  { id: "lhr-jfk", from: "London (LHR)", to: "New York (JFK)", emoji: "🗽", duration: "8h 05m", stops: "Non-stop", baggage: "Cabin bag + 23kg hold", base: 620, yearMax: 1250, airlines: [["british", 0.1], ["emirates", 0.2]], otas: [["skyscanner", -0.05], ["kayak", -0.07], ["kiwi", -0.1], ["expedia", 0.04], ["gflights", -0.02]] },
];

/* ---------------- car rentals ---------------- */
const CAR_CITIES = {
  dubai: { name: "Dubai", aliases: ["dubai", "dxb"], classes: [
    { name: "Economy — Kia Picanto / similar", emoji: "🚙", base: 34, yearMax: 58, perks: ["Unlimited mileage", "Free cancellation", "Basic insurance"], agencies: [["hertz", 0.02], ["sixt", 0.0], ["enterprise", 0.06], ["budget", -0.03], ["kayak", -0.07], ["europcar", 0.04]] },
    { name: "SUV — Toyota RAV4 / similar", emoji: "🚘", base: 71, yearMax: 120, perks: ["Unlimited mileage", "Free cancellation", "Full insurance"], agencies: [["hertz", 0.04], ["sixt", 0.0], ["avis", 0.06], ["enterprise", 0.08], ["kayak", -0.06]] },
    { name: "Luxury — Mercedes C-Class / similar", emoji: "🏎️", base: 148, yearMax: 260, perks: ["Unlimited mileage", "Premium insurance", "Delivery to hotel"], agencies: [["sixt", 0.0], ["hertz", 0.08], ["avis", 0.1], ["kayak", -0.05]] },
  ]},
  lahore: { name: "Lahore", aliases: ["lahore", "lhe"], classes: [
    { name: "Economy — Suzuki Alto / similar", emoji: "🚙", base: 22, yearMax: 40, perks: ["Per day + fuel", "Chauffeur available", "AC"], agencies: [["hertz", 0.05], ["budget", -0.02], ["enterprise", 0.08], ["kayak", -0.08]] },
    { name: "Sedan — Toyota Corolla / similar", emoji: "🚗", base: 41, yearMax: 72, perks: ["Per day + fuel", "Chauffeur available", "AC"], agencies: [["hertz", 0.03], ["budget", 0.0], ["avis", 0.06], ["kayak", -0.07]] },
  ]},
  auckland: { name: "Auckland", aliases: ["auckland", "akl", "new zealand"], classes: [
    { name: "Economy — Toyota Yaris / similar", emoji: "🚙", base: 39, yearMax: 68, perks: ["Unlimited mileage", "Free cancellation", "Full insurance"], agencies: [["hertz", 0.02], ["avis", 0.05], ["budget", -0.02], ["europcar", 0.06], ["kayak", -0.07]] },
    { name: "SUV — Mitsubishi Outlander / similar", emoji: "🚘", base: 79, yearMax: 130, perks: ["Unlimited mileage", "Free cancellation", "Roadside assist"], agencies: [["hertz", 0.04], ["avis", 0.06], ["enterprise", 0.03], ["kayak", -0.06]] },
  ]},
  london: { name: "London", aliases: ["london", "uk"], classes: [
    { name: "Economy — VW Polo / similar", emoji: "🚙", base: 41, yearMax: 74, perks: ["Unlimited mileage", "Free cancellation", "Breakdown cover"], agencies: [["hertz", 0.03], ["sixt", 0.0], ["enterprise", 0.05], ["budget", -0.02], ["europcar", 0.04], ["kayak", -0.06]] },
    { name: "Estate — VW Golf Estate / similar", emoji: "🚗", base: 63, yearMax: 110, perks: ["Unlimited mileage", "Free cancellation", "Extra boot space"], agencies: [["hertz", 0.04], ["sixt", 0.01], ["avis", 0.06], ["kayak", -0.05]] },
  ]},
};

/* ---------------- search scoring ---------------- */
function tokens(s) {
  return (s || "").toLowerCase().replace(/[^a-z0-9\s]/g, " ").split(/\s+/).filter(Boolean);
}
function overlapScore(query, text) {
  const q = new Set(tokens(query));
  const t = tokens(text);
  if (!q.size || !t.length) return 0;
  let hits = 0;
  for (const tok of q) if (t.some((w) => w === tok || w.startsWith(tok) || tok.startsWith(w))) hits++;
  return hits / q.size;
}
function cityInQuery(query) {
  const q = query.toLowerCase();
  const all = { ...HOTEL_DESTINATIONS, ...CAR_CITIES };
  let best = null; let bestScore = 0;
  for (const [id, c] of Object.entries(all)) {
    for (const a of [c.name, ...(c.aliases || [])]) {
      if (q.includes(a.toLowerCase()) && a.length > bestScore) { best = id; bestScore = a.length; }
    }
  }
  return best;
}

/* ---------------- offer builder ---------------- */
function buildOffers(kind, title, base, merchantSpecs, geo, incognito, seedStr, query) {
  const g = GEO_BY_ID[geo] || GEO_BY_ID.us;
  const rng = mulberry32(seed(seedStr));
  return merchantSpecs.map(([key, spread, meta]) => {
    const m = MERCHANTS[key] || classify(key);
    const priceUSD = Math.round(base * (1 + spread) * g.mult * (1 + jitter(seedStr + key, -0.015, 0.015)) * 100) / 100;
    const markup = incognito ? (COOKIE_MARKUP[m.domain] || 0) : 0;
    return {
      merchantKey: key, domain: m.domain, name: m.name,
      priceUSD,
      wasUSD: markup ? Math.round(priceUSD * (1 + markup) * 100) / 100 : null,
      url: merchantUrl(m.domain, query || title),
      trust: m.trust, footfall: m.footfall, rating: m.rating, tier: m.spam ? "low" : m.trust >= 80 ? "high" : m.trust >= 60 ? "med" : "low",
      color: m.color, spam: !!m.spam, meta: meta || null,
    };
  });
}

/* ---------------- main search ---------------- */
export function searchDemo({ commodity, q, geo = "us", incognito = false, imageMatch = null }) {
  const query = (q || "").trim();
  if (commodity === "goods") return searchGoods(query, geo, incognito, imageMatch);
  if (commodity === "hotels") return searchHotels(query, geo, incognito);
  if (commodity === "flights") return searchFlights(query, geo, incognito);
  if (commodity === "cars") return searchCars(query, geo, incognito);
  return searchGoods(query, geo, incognito, imageMatch);
}

function searchGoods(query, geo, incognito, imageMatch) {
  let cards = [];
  if (imageMatch) {
    const prod = GOODS.find((p) => p.key === imageMatch.productKey);
    if (prod) {
      cards = [productCard(prod, geo, incognito, query || prod.name, { viaImage: true, score: imageMatch.score })];
    }
  }
  if (!cards.length) {
    const scored = GOODS.map((p) => ({ p, s: Math.max(overlapScore(query, p.name + " " + p.cats.join(" ")), imageMatch && imageMatch.queryHints && overlapScore(query, p.name) ? 0.2 : 0) }))
      .filter((x) => x.s > 0)
      .sort((a, b) => b.s - a.s)
      .slice(0, 5);
    cards = scored.map(({ p, s }) => productCard(p, geo, incognito, query, { viaImage: false, score: Math.round(s * 100) / 100 }));
  }
  if (!cards.length) {
    cards = [genericCard(query, geo, incognito)];
  }
  const g = GEO_BY_ID[geo] || GEO_BY_ID.us;
  return {
    kind: "goods", source: "demo", title: cards.length === 1 ? cards[0].title : `Best prices for “${query}”`,
    subtitle: `${cards.length} product${cards.length > 1 ? "s" : ""} · ${cards.reduce((n, c) => n + c.offers.length, 0)} trusted quotes compared`,
    geo: g, cards, yearlyMaxKnown: true,
  };
}

function productCard(p, geo, incognito, query, match) {
  const specs = p.merchants.map(([k, s, meta]) => [k, s, meta]);
  const offers = buildOffers("goods", p.name, p.base, specs, geo, incognito, "g:" + p.key, query || p.name);
  return {
    id: "g-" + p.key, type: "goods", title: p.name, subtitle: "In stock now",
    emoji: p.emoji, refImage: p.ref ? REF_IMAGE[p.ref] : null,
    yearMaxUSD: p.yearMax, yearAvgUSD: p.yearAvg,
    cats: p.cats.slice(0, 3),
    match,
    offers,
  };
}

function genericCard(query, geo, incognito) {
  const title = query ? query.replace(/\b(buy|cheap|cheapest|price|best|new|online)\b/gi, "").trim() || query : "Product";
  const seedStr = "gen:" + query;
  const base = Math.round(jitter(seedStr, 20, 900));
  const specs = [["amazon", -0.02, "Free 2-day · Prime"], ["walmart", 0.02, "Free delivery"], ["ebay", -0.05, "Verified sellers"], ["bestbuy", 0.04, "Free next-day"], ["noon", -0.04, "UAE stock"], ["daraz", -0.06, "PKR pricing"]];
  const offers = buildOffers("goods", title, base, specs, geo, incognito, seedStr, query);
  return {
    id: "g-gen-" + seed(seedStr), type: "goods", title: title.length ? title : "Product", subtitle: "Estimated market quotes (demo data)",
    emoji: "📦", refImage: null, yearMaxUSD: Math.round(base * 1.35), yearAvgUSD: Math.round(base * 1.15),
    cats: ["generic"], match: null, offers,
  };
}

function searchHotels(query, geo, incognito) {
  const cityId = cityInQuery(query);
  const dest = cityId ? HOTEL_DESTINATIONS[cityId] : null;
  let props = [];
  if (dest) props = dest.properties;
  else {
    const scored = Object.values(HOTEL_DESTINATIONS).flatMap((d) => d.properties.map((p) => ({ p, s: overlapScore(query, p.name + " " + d.name + " " + p.area) })))
      .filter((x) => x.s > 0).sort((a, b) => b.s - a.s);
    props = scored.slice(0, 3).map((x) => x.p);
  }
  const g = GEO_BY_ID[geo] || GEO_BY_ID.us;
  if (!props.length) {
    return {
      kind: "hotels", source: "demo", title: `Hotels near “${query}”`,
      subtitle: "No exact match in catalog — showing top-rated properties across popular destinations",
      geo: g, yearlyMaxKnown: true,
      cards: Object.values(HOTEL_DESTINATIONS).slice(0, 3).flatMap((d) => d.properties.slice(0, 1).map((p) => hotelCard(d, p, geo, incognito, query))),
    };
  }
  const destName = dest ? dest.name : "your destination";
  return {
    kind: "hotels", source: "demo", title: `Hotels in ${destName}`, subtitle: `per night, room only · ${props.length} properties · rates re-quoted for ${g.label}`,
    geo: g, yearlyMaxKnown: true,
    cards: props.map((p) => hotelCard(dest || { name: destName }, p, geo, incognito, query)),
  };
}

function hotelCard(dest, p, geo, incognito, query) {
  const offers = buildOffers("hotels", p.name, p.base, p.otas.map(([k, s]) => [k, s, p.perks[0]]), geo, incognito, "h:" + p.name, `${p.name} ${dest.name}`);
  return {
    id: "h-" + p.name.replace(/\W+/g, "-").toLowerCase(), type: "hotels",
    title: p.name, subtitle: `${p.area} · ${"★".repeat(p.stars)} · ${p.rating}/5 from ${p.reviews.toLocaleString()} reviews`,
    emoji: p.emoji, refImage: null, yearMaxUSD: p.yearMax, yearAvgUSD: Math.round(p.base * 1.35),
    cats: ["hotel", "per night"], match: null, offers, perks: p.perks,
  };
}

function searchFlights(query, geo, incognito) {
  const q = query.toLowerCase();
  const scored = FLIGHT_ROUTES.map((r) => {
    const fromCity = r.from.match(/\(([A-Z]+)\)/)[1].toLowerCase();
    const toCity = r.to.match(/\(([A-Z]+)\)/)[1].toLowerCase();
    const hay = (r.from + " " + r.to).toLowerCase();
    let s = 0;
    const toks = tokens(query).filter((t) => t.length > 2);
    for (const t of toks) {
      if (hay.includes(t)) s += 1;
      if (q.includes(fromCity) && q.includes(toCity) && q.indexOf(fromCity) < q.indexOf(toCity)) s += 3;
      else if (q.includes(fromCity) || q.includes(toCity)) s += 1;
    }
    if (toks.length === 0) s = 0;
    return { r, s };
  }).sort((a, b) => b.s - a.s);
  let routes = scored.filter((x) => x.s > 0).map((x) => x.r);
  const g = GEO_BY_ID[geo] || GEO_BY_ID.us;
  if (!routes.length) routes = FLIGHT_ROUTES.slice(0, 2);
  routes = routes.slice(0, 3);
  return {
    kind: "flights", source: "demo", title: routes.length === 1 ? `Flights ${routes[0].from} → ${routes[0].to}` : `Flights matching “${query}”`,
    subtitle: `round-trip, economy, 1 traveller · dates flexible · quotes re-quoted for ${g.label}`,
    geo: g, yearlyMaxKnown: true,
    cards: routes.map((r) => flightCard(r, geo, incognito, query)),
  };
}

function flightCard(r, geo, incognito, query) {
  const airlineOffers = buildOffers("flights", r.from + " " + r.to, r.base, r.airlines.map(([k, s]) => [k, s, `${r.duration} · ${r.stops}`]), geo, incognito, "f:" + r.id, r.from + " to " + r.to);
  const otaOffers = buildOffers("flights", r.from + " " + r.to, r.base, r.otas.map(([k, s]) => [k, s, "Compare all airlines"]), geo, incognito, "fo:" + r.id, r.from + " to " + r.to);
  return {
    id: "f-" + r.id, type: "flights", title: `${r.from} → ${r.to}`,
    subtitle: `${r.duration} · ${r.stops} · Economy round-trip`,
    emoji: r.emoji, refImage: null, yearMaxUSD: r.yearMax, yearAvgUSD: Math.round(r.base * 1.35),
    cats: ["round-trip", r.baggage], match: null,
    offers: [...airlineOffers, ...otaOffers],
  };
}

function searchCars(query, geo, incognito) {
  const cityId = cityInQuery(query);
  const city = cityId ? CAR_CITIES[cityId] : null;
  const g = GEO_BY_ID[geo] || GEO_BY_ID.us;
  let cards = [];
  let title = `Rent a car`;
  if (city) {
    title = `Rent a car in ${city.name}`;
    cards = city.classes.map((c) => carCard(city, c, geo, incognito, query));
  } else {
    const scored = Object.values(CAR_CITIES).flatMap((c) => c.classes.map((k) => ({ k, c, s: overlapScore(query, c.name + " " + k.name) })))
      .filter((x) => x.s > 0).sort((a, b) => b.s - a.s);
    cards = scored.slice(0, 3).map(({ k, c }) => carCard(c, k, geo, incognito, query));
    if (!cards.length) {
      const c = CAR_CITIES.dubai;
      title = "Rent a car (popular options)";
      cards = c.classes.map((k) => carCard(c, k, geo, incognito, query));
    }
  }
  return {
    kind: "cars", source: "demo", title, subtitle: `per day · rates re-quoted for ${g.label}`,
    geo: g, yearlyMaxKnown: true, cards,
  };
}

function carCard(city, cls, geo, incognito, query) {
  const offers = buildOffers("cars", cls.name, cls.base, cls.agencies.map(([k, s]) => [k, s, cls.perks[0]]), geo, incognito, "c:" + city.name + cls.name, `car rental ${city.name}`);
  return {
    id: "c-" + city.name.toLowerCase() + "-" + seed(cls.name), type: "cars",
    title: cls.name, subtitle: `in ${city.name} · ${cls.perks.join(" · ")}`,
    emoji: cls.emoji, refImage: null, yearMaxUSD: cls.yearMax, yearAvgUSD: Math.round(cls.base * 1.3),
    cats: ["per day", "car rental"], match: null, offers, perks: cls.perks,
  };
}

/* ---------------- image-search support ---------------- */
export const IMAGE_REFS = [
  { productKey: "iphone16pro", name: "Smartphone", src: REF_IMAGE.phone },
  { productKey: "af1", name: "White sneakers", src: REF_IMAGE.sneakers },
  { productKey: "sonyxm5", name: "Headphones", src: REF_IMAGE.headphones },
  { productKey: "watch9", name: "Smartwatch", src: REF_IMAGE.smartwatch },
  { productKey: "backpack", name: "Backpack", src: REF_IMAGE.backpack },
  { productKey: "aviator", name: "Sunglasses", src: REF_IMAGE.sunglasses },
];

export const QUICK_CHIPS = {
  goods: ["iPhone 16 Pro", "Sony WH-1000XM5 headphones", "Nike Air Force 1", "MacBook Air M3", "PS5 Slim"],
  hotels: ["hotels in Dubai", "hotels in London", "hotels in Lahore", "hotels in New York"],
  flights: ["flight London to Dubai", "flight New York to Dubai", "flight Islamabad to Dubai", "flight Auckland to Sydney"],
  cars: ["rent a car in Dubai", "rent a car in Lahore", "rent a car in Auckland", "rent a car in London"],
};
