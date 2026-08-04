/* Altron PriceFinder — search orchestrator.
   Tries live web search (SerpAPI proxied through the local server) and
   falls back to the rich demo marketplace when no key is set or the
   upstream is unreachable. Every result card is normalized into the same
   { cards: [{ title, offers: [{ domain, priceUSD, url, ... }] }] } shape. */

import { searchDemo, GEO_BY_ID } from "./demo.js";
import { classify, isReliable, merchantUrl, footfallLabel } from "./trust.js";

export const COMMODITIES = {
  goods:   { serpEngine: "google_shopping", label: "Goods" },
  hotels:  { serpEngine: "google_hotels",   label: "Hotels" },
  flights: { serpEngine: "google_flights",  label: "Tickets" },
  cars:    { serpEngine: "google_maps",     label: "Rent-a-Car" },
};

const LIVE_FILTER_TRUST = 45;
const LIVE_FILTER_FOOTFALL = 0.05;

/**
 * Run a search.
 * @param {object} p { commodity, q, geo, incognito, image (dataURL|null), settings }
 * @returns {Promise<{cards, source, live:boolean, ...}>}
 */
export async function runSearch({ commodity, q, geo, incognito, image, settings }) {
  const live = await tryLive({ commodity, q, geo, incognito, image, settings });
  if (live) return live;
  const demo = searchDemo({ commodity, q, geo, incognito, imageMatch: image && image.match ? image.match : null });
  return { ...demo, live: false, geo: GEO_BY_ID[geo] || GEO_BY_ID.us };
}

async function tryLive({ commodity, q, geo, incognito, image, settings }) {
  const apiKey = (settings && settings.serpKey || "").trim();
  if (!apiKey) return null;
  const engine = COMMODITIES[commodity].serpEngine;
  const gl = GEO_BY_ID[geo]?.id === "us" ? "us" : (GEO_BY_ID[geo]?.id || "us");

  const params = new URLSearchParams({ engine, api_key: apiKey, num: "12", gl, hl: "en" });
  let query = q || "";
  let lens = null;

  if (commodity === "cars") {
    // Google Maps place search for car rental agencies in the city
    query = `${q} car rental`;
    params.set("type", "search");
  }
  if (image && image.dataUrl) {
    // google_lens needs the image binary — not available via simple proxy;
    // so for image queries we search text derived from the visual match.
    params.set("engine", engine);
    params.set("q", (image.match?.query || q || "product").trim());
    lens = { used: true, via: "visual-match-text" };
  }
  params.set("q", query || "product");

  const url = "/api/search?" + params.toString();
  let resp;
  try {
    const r = await fetch(url);
    const j = await r.json();
    if (j.error === "no_api_key" || j.error === "proxy_upstream_failed" || j.error?.includes("Invalid API key")) return null;
    resp = j;
  } catch (_) {
    return null;
  }

  try {
    let parsed = null;
    if (engine === "google_shopping") parsed = parseShopping(resp);
    if (engine === "google_hotels") parsed = parseHotels(resp);
    if (engine === "google_flights") parsed = parseFlights(resp);
    if (engine === "google_maps") parsed = parseMaps(resp);
    if (!parsed || !parsed.cards.length) return null;
    parsed.source = "live";
    parsed.live = true;
    parsed.lens = lens;
    parsed.geo = GEO_BY_ID[geo] || GEO_BY_ID.us;
    parsed.title = parsed.title || `Live web results for “${query}”`;
    parsed.subtitle = parsed.subtitle || `${parsed.cards.reduce((n, c) => n + c.offers.length, 0)} offers · filtered to trusted sources`;
    parsed.yearlyMaxKnown = false;
    return parsed;
  } catch (_) {
    return null;
  }
}

/* ---------- normalization helpers ---------- */
function normOffer(o) {
  const m = classify(o.domain || o.name);
  const reliable = isReliable(m, LIVE_FILTER_TRUST, LIVE_FILTER_FOOTFALL);
  return {
    ...o,
    name: o.name || m.name,
    trust: o.trust ?? m.trust,
    footfall: o.footfall ?? m.footfall,
    rating: o.rating ?? m.rating,
    tier: !reliable ? "low" : m.trust >= 80 ? "high" : m.trust >= 60 ? "med" : "low",
    spam: !reliable,
    blockedReason: !reliable ? `low trust / low footfall (${footfallLabel(m.footfall)} visits/mo)` : null,
    priceUSD: Number.isFinite(o.priceUSD ?? (o.price ? parseFloat(String(o.price).replace(/[^0-9.]/g, "")) : NaN)) ? (o.priceUSD ?? parseFloat(String(o.price).replace(/[^0-9.]/g, ""))) : null,
  };
}

/* ---------- google_shopping ---------- */
function parseShopping(json) {
  const cards = (json.shopping_results || []).slice(0, 10).map((sr) => {
    const domain = (sr.source || sr.domain || "").toLowerCase().replace(/^www\./, "").split("/")[0];
    const priceUSD = parseFloat((sr.price || "").replace(/[^0-9.]/g, "")) || 0;
    return {
      id: "live-" + (sr.product_id || seedOf(sr.title)),
      type: "goods",
      title: sr.title,
      subtitle: `${sr.thumbnail ? "Image available" : "Live listing"} · ${sr.delivery || "Check shipping"}`,
      emoji: "🛍️",
      refImage: sr.thumbnail || null,
      yearMaxUSD: null, yearAvgUSD: null,
      cats: ["live web"],
      match: null,
      offers: [normOffer({
        domain, name: sr.source || domain,
        priceUSD, url: sr.link,
        meta: sr.delivery || null,
        rating: sr.rating,
        reviews: sr.reviews,
      })],
    };
  });
  return { kind: "goods", cards };
}

function seedOf(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (Math.imul(h, 31) + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

/* ---------- google_hotels ---------- */
function parseHotels(json) {
  const cards = (json.hotels || []).slice(0, 8).map((h) => ({
    id: "live-h-" + seedOf(h.name),
    type: "hotels",
    title: h.name,
    subtitle: `${h.stars ? "★".repeat(Math.min(5, h.stars)) : ""} ${h.rating ? h.rating + "/5" : ""} ${h.location ? "· " + h.location : ""}`.trim(),
    emoji: "🏨", refImage: h.thumbnail || null,
    yearMaxUSD: null, yearAvgUSD: null, cats: ["live web"],
    match: null,
    offers: [normOffer({
      domain: "google.com/travel/hotels", name: "Google Hotels",
      priceUSD: h.price ? parseFloat(h.price.replace(/[^0-9.]/g, "")) : 0,
      url: h.link || "https://www.google.com/travel/hotels",
      meta: h.price_rate_per_night ? "per night" : null,
      rating: h.rating, reviews: h.reviews,
    })],
  }));
  return { kind: "hotels", cards };
}

/* ---------- google_flights ---------- */
function parseFlights(json) {
  const flights = (json.best_flights || []).slice(0, 5);
  const cards = flights.map((f) => {
    const priceUSD = f.price || 0;
    const fl = (f.flights || [])[0] || {};
    const title = fl.departure_airport && fl.arrival_airport ? `${fl.departure_airport.name || fl.departure_airport.code} → ${fl.arrival_airport.name || fl.arrival_airport.code}` : "Flight";
    return {
      id: "live-f-" + seedOf(title + priceUSD),
      type: "flights", title,
      subtitle: `${f.duration ? Math.round(f.duration / 60) + "h " + (f.duration % 60) + "m" : ""} · ${(f.flights || []).length > 1 ? (f.flights.length - 1) + " stop(s)" : "Non-stop"} · ${f.airline || "Economy"}`.trim(),
      emoji: "✈️", refImage: null, yearMaxUSD: null, yearAvgUSD: null, cats: ["live web"],
      match: null,
      offers: [normOffer({
        domain: "google.com/travel/flights", name: "Google Flights",
        priceUSD, url: f.link || "https://www.google.com/travel/flights",
        meta: f.airline || null, rating: 4.7,
      })],
    };
  });
  return { kind: "flights", cards };
}

/* ---------- google_maps (car rental) ---------- */
function parseMaps(json) {
  const cards = (json.local_results || []).slice(0, 8).map((r) => ({
    id: "live-c-" + seedOf(r.title),
    type: "cars",
    title: r.title,
    subtitle: `${r.address || ""} · ${r.rating ? r.rating + "/5" : ""} ${r.reviews ? "(" + r.reviews + ")" : ""}`.trim(),
    emoji: "🚗", refImage: r.thumbnail || null,
    yearMaxUSD: null, yearAvgUSD: null, cats: ["live web"],
    match: null,
    offers: [normOffer({
      domain: r.domain || "google.com/maps", name: r.title,
      priceUSD: null, url: r.link || "#", meta: "Contact for rates", rating: r.rating,
    })],
  }));
  return { kind: "cars", cards };
}
