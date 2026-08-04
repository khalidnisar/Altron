/* Altron PriceFinder — merchant trust & footfall database.
   Every source is scored on reputation (0-100) and monthly footfall.
   Low-footfall / spam-looking merchants are filtered by default so the
   "cheapest price" never comes from a sketchy zero-traffic site. */

export const MERCHANTS = {
  // ---------- goods ----------
  amazon:       { name: "Amazon",        domain: "amazon.com",    trust: 92, footfall: 3100, rating: 4.7, color: "#f59e0b" },
  walmart:      { name: "Walmart",       domain: "walmart.com",   trust: 88, footfall: 820,  rating: 4.5, color: "#2563eb" },
  bestbuy:      { name: "Best Buy",      domain: "bestbuy.com",   trust: 89, footfall: 240,  rating: 4.6, color: "#facc15" },
  target:       { name: "Target",        domain: "target.com",    trust: 87, footfall: 460,  rating: 4.5, color: "#dc2626" },
  ebay:         { name: "eBay",          domain: "ebay.com",      trust: 80, footfall: 1600, rating: 4.4, color: "#1f2937" },
  apple:        { name: "Apple",         domain: "apple.com",     trust: 95, footfall: 900,  rating: 4.8, color: "#111827" },
  samsung:      { name: "Samsung",       domain: "samsung.com",   trust: 90, footfall: 310,  rating: 4.6, color: "#2563eb" },
  newegg:       { name: "Newegg",        domain: "newegg.com",    trust: 84, footfall: 95,   rating: 4.5, color: "#dc2626" },
  bhp:          { name: "B&H Photo",     domain: "bhphotovideo.com", trust: 88, footfall: 62, rating: 4.7, color: "#111827" },
  costco:       { name: "Costco",        domain: "costco.com",    trust: 90, footfall: 280,  rating: 4.6, color: "#1d4ed8" },
  aliexpress:   { name: "AliExpress",    domain: "aliexpress.com", trust: 58, footfall: 700, rating: 3.9, color: "#e11d48" },
  dhgate:       { name: "DHgate",        domain: "dhgate.com",    trust: 45, footfall: 110,  rating: 3.7, color: "#0f766e" },
  currys:       { name: "Currys",        domain: "currys.co.uk",  trust: 83, footfall: 70,   rating: 4.3, color: "#dc2626" },
  argos:        { name: "Argos",         domain: "argos.co.uk",   trust: 84, footfall: 90,   rating: 4.4, color: "#991b1b" },
  carrefour:    { name: "Carrefour",     domain: "carrefour.com", trust: 81, footfall: 130,  rating: 4.2, color: "#2563eb" },
  noon:         { name: "Noon",          domain: "noon.com",      trust: 76, footfall: 55,   rating: 4.1, color: "#f97316" },
  emax:         { name: "Sharaf DG",     domain: "sharafdg.com",  trust: 74, footfall: 18,   rating: 4.1, color: "#e11d48" },
  daraz:        { name: "Daraz",         domain: "daraz.pk",      trust: 68, footfall: 85,   rating: 3.9, color: "#f59e0b" },
  telemart:     { name: "Telemart",      domain: "telemart.pk",   trust: 62, footfall: 4,    rating: 3.8, color: "#0ea5e9" },
  thewarehouse: { name: "The Warehouse", domain: "thewarehouse.co.nz", trust: 82, footfall: 12, rating: 4.3, color: "#e11d48" },
  noelleeming:  { name: "Noel Leeming",  domain: "noelleeming.co.nz", trust: 81, footfall: 9,  rating: 4.3, color: "#7c3aed" },
  jbhifi:       { name: "JB Hi-Fi",      domain: "jbhifi.co.nz",  trust: 80, footfall: 6,    rating: 4.2, color: "#dc2626" },
  // demo spam merchants (would be filtered out)
  megadeals:    { name: "MegaDeals USA", domain: "megadeals-usa.biz", trust: 12, footfall: 0.004, rating: 1.8, color: "#6b7280", spam: true },
  electrobarg:  { name: "ElectroBargainZone", domain: "electrobargain-zone.top", trust: 8, footfall: 0.001, rating: 1.5, color: "#6b7280", spam: true },
  phonedeals:   { name: "PhoneDeals4U",  domain: "phonedeals4u.ru", trust: 15, footfall: 0.002, rating: 2.0, color: "#6b7280", spam: true },
  // ---------- hotels ----------
  booking:      { name: "Booking.com",   domain: "booking.com",   trust: 90, footfall: 920,  rating: 4.6, color: "#003580" },
  expedia:      { name: "Expedia",       domain: "expedia.com",   trust: 87, footfall: 350,  rating: 4.5, color: "#fdb913" },
  agoda:        { name: "Agoda",         domain: "agoda.com",     trust: 83, footfall: 180,  rating: 4.4, color: "#e11d48" },
  hotelsdotcom: { name: "Hotels.com",    domain: "hotels.com",    trust: 85, footfall: 120,  rating: 4.4, color: "#d11111" },
  kayak:        { name: "Kayak",         domain: "kayak.com",     trust: 84, footfall: 90,   rating: 4.5, color: "#ff690f" },
  tripcom:      { name: "Trip.com",      domain: "trip.com",      trust: 80, footfall: 260,  rating: 4.3, color: "#2875de" },
  makemytrip:   { name: "MakeMyTrip",    domain: "makemytrip.com", trust: 79, footfall: 130, rating: 4.3, color: "#01a982" },
  // ---------- flights ----------
  skyscanner:   { name: "Skyscanner",    domain: "skyscanner.net", trust: 86, footfall: 150, rating: 4.4, color: "#00a3e0" },
  kiwi:         { name: "Kiwi.com",      domain: "kiwi.com",      trust: 74, footfall: 60,   rating: 4.0, color: "#f37f13" },
  emirates:     { name: "Emirates",      domain: "emirates.com",  trust: 91, footfall: 80,   rating: 4.7, color: "#d71921" },
  etihad:       { name: "Etihad",        domain: "etihad.com",    trust: 88, footfall: 40,   rating: 4.6, color: "#7f1d0c" },
  british:      { name: "British Airways", domain: "britishairways.com", trust: 87, footfall: 70, rating: 4.5, color: "#1e40af" },
  qatar:        { name: "Qatar Airways", domain: "qatarairways.com", trust: 89, footfall: 55, rating: 4.6, color: "#7c0a02" },
  flydubai:     { name: "flydubai",      domain: "flydubai.com",  trust: 80, footfall: 25,   rating: 4.2, color: "#f59e0b" },
  pia:          { name: "PIA",           domain: "piac.com.pk",   trust: 66, footfall: 8,    rating: 3.6, color: "#16a34a" },
  airnewzealand:{ name: "Air New Zealand", domain: "airnewzealand.co.nz", trust: 88, footfall: 18, rating: 4.6, color: "#111827" },
  // ---------- car rental ----------
  hertz:        { name: "Hertz",         domain: "hertz.com",     trust: 82, footfall: 60,   rating: 4.2, color: "#facc15" },
  avis:         { name: "Avis",          domain: "avis.com",      trust: 81, footfall: 50,   rating: 4.1, color: "#dc2626" },
  enterprise:   { name: "Enterprise",    domain: "enterprise.com", trust: 84, footfall: 90, rating: 4.3, color: "#16a34a" },
  sixt:         { name: "Sixt",          domain: "sixt.com",      trust: 83, footfall: 40,   rating: 4.2, color: "#e11d48" },
  budget:       { name: "Budget",        domain: "budget.com",    trust: 78, footfall: 30,   rating: 4.0, color: "#f97316" },
  europcar:     { name: "Europcar",      domain: "europcar.com",  trust: 77, footfall: 35,   rating: 4.0, color: "#eab308" },
  // travel metasearch defaults
  gflights:     { name: "Google Flights", domain: "google.com/travel/flights", trust: 93, footfall: 4000, rating: 4.7, color: "#4285f4" },
  ghotels:      { name: "Google Hotels", domain: "google.com/travel/hotels", trust: 93, footfall: 4000, rating: 4.7, color: "#4285f4" },
};

export const SPAM_SIGNALS = [
  /\.top$/, /\.biz$/, /\.xyz$/, /\.ru$/, /\.cc$/, /\.tk$/, /\.ml$/, /\.ga$/,
  /deals?[-_]/i, /bargain/i, /discount[-_]/i, /cheap[-_]/i, /sale[-_]/i,
];

/** Look up a merchant by domain/key, else classify from the URL. */
export function classify(domainOrKey) {
  const d = (domainOrKey || "").toLowerCase().replace(/^www\./, "").split("/")[0];
  const hit = Object.values(MERCHANTS).find((m) => m.domain === d || m.name.toLowerCase() === d);
  if (hit) return { ...hit };
  const spam = SPAM_SIGNALS.some((re) => re.test(d));
  return {
    name: (domainOrKey || "Unknown store").split(".")[0].replace(/^www\./, ""),
    domain: d,
    trust: spam ? 10 : 55,           // unknown domains: cautiously trusted
    footfall: spam ? 0.001 : 0.12,
    rating: spam ? 1.9 : 4.0,
    color: "#64748b",
    spam,
    unknown: true,
  };
}

export function isReliable(merchant, minTrust = 45, minFootfall = 0.05) {
  return !merchant.spam && merchant.trust >= minTrust && merchant.footfall >= minFootfall;
}

export function trustTier(merchant) {
  if (merchant.spam || merchant.trust < 40) return "low";
  if (merchant.trust >= 80) return "high";
  if (merchant.trust >= 60) return "med";
  return "low";
}

/** Short human footfall label, e.g. "3.1B visits/mo". */
export function footfallLabel(millions) {
  if (millions >= 1000) return (millions / 1000).toFixed(1) + "B";
  if (millions >= 100) return Math.round(millions) + "M";
  if (millions >= 1) return (Math.round(millions * 10) / 10) + "M";
  return Math.round(millions * 1000) + "K";
}

/** Build a search URL for a merchant (demo mode: go to their real site with query pre-filled). */
export function merchantUrl(domain, query) {
  const q = encodeURIComponent(query);
  const map = {
    "amazon.com": `https://www.amazon.com/s?k=${q}`,
    "walmart.com": `https://www.walmart.com/search?q=${q}`,
    "bestbuy.com": `https://www.bestbuy.com/site/searchpage.jsp?st=${q}`,
    "target.com": `https://www.target.com/s?searchTerm=${q}`,
    "ebay.com": `https://www.ebay.com/sch/i.html?_nkw=${q}`,
    "newegg.com": `https://www.newegg.com/p/pl?d=${q}`,
    "bhphotovideo.com": `https://www.bhphotovideo.com/c/search?q=${q}`,
    "costco.com": `https://www.costco.com/CatalogSearch?keyword=${q}`,
    "aliexpress.com": `https://www.aliexpress.com/wholesale?SearchText=${q}`,
    "noon.com": `https://www.noon.com/uae-en/search/?q=${q}`,
    "sharafdg.com": `https://www.sharafdg.com/catalogsearch/result/?q=${q}`,
    "daraz.pk": `https://www.daraz.pk/catalog/?q=${q}`,
    "telemart.pk": `https://www.telemart.pk/catalogsearch/result/?q=${q}`,
    "thewarehouse.co.nz": `https://www.thewarehouse.co.nz/search?q=${q}`,
    "noelleeming.co.nz": `https://www.noelleeming.co.nz/search?q=${q}`,
    "jbhifi.co.nz": `https://www.jbhifi.co.nz/search?q=${q}`,
    "booking.com": `https://www.booking.com/searchresults.en-gb.html?ss=${q}`,
    "expedia.com": `https://www.expedia.com/Hotel-Search?destination=${q}`,
    "agoda.com": `https://www.agoda.com/search?city=${q}`,
    "hotels.com": `https://www.hotels.com/search.do?destination=${q}`,
    "kayak.com": `https://www.kayak.com/hotels/${q}`,
    "trip.com": `https://www.trip.com/hotels/list?city=${q}`,
    "makemytrip.com": `https://www.makemytrip.com/hotels/hotel-listings?city=${q}`,
    "skyscanner.net": `https://www.skyscanner.net/transport/flights/${q}`,
    "kiwi.com": `https://www.kiwi.com/en/search/results/${q}`,
    "emirates.com": `https://www.emirates.com/book/`, 
    "etihad.com": `https://www.etihad.com/en-us/book`,
    "britishairways.com": `https://www.britishairways.com/travel/home/public/en_gb/`,
    "qatarairways.com": `https://www.qatarairways.com/en-us/book-a-flight.html`,
    "flydubai.com": `https://www.flydubai.com/en/booking`,
    "piac.com.pk": `https://www.piac.com.pk/`,
    "airnewzealand.co.nz": `https://www.airnewzealand.co.nz/`,
    "hertz.com": `https://www.hertz.com/rentacar/reservation/`,
    "avis.com": `https://www.avis.com/en/home`,
    "enterprise.com": `https://www.enterprise.com/en/car-rental.html`,
    "sixt.com": `https://www.sixt.com/`,
    "budget.com": `https://www.budget.com/en/home`,
    "europcar.com": `https://www.europcar.com/en-us`,
    "google.com/travel/flights": `https://www.google.com/travel/flights?q=${q}`,
    "google.com/travel/hotels": `https://www.google.com/travel/hotels?q=${q}`,
  };
  return map[domain] || `https://${domain}/search?q=${q}`;
}
