/* Altron PriceFinder — UI rendering. Pure DOM, no framework. */

import { fmt, state as fxState } from "./fx.js";
import { findCoupons } from "./coupons.js";
import { trustTier, footfallLabel } from "./trust.js";

export const el = (id) => document.getElementById(id);

export function toast(msg, kind = "") {
  const host = el("toastHost");
  const t = document.createElement("div");
  t.className = "toast " + kind;
  t.textContent = msg;
  host.appendChild(t);
  setTimeout(() => t.remove(), 3200);
}

export function showSkeleton(resultsEl) {
  resultsEl.innerHTML = `
    <div class="skel-card"><div class="skel-line w40"></div><div class="skel-line w70"></div><div class="skel-line w90"></div></div>
    <div class="skel-card"><div class="skel-line w40"></div><div class="skel-line w70"></div><div class="skel-line w90"></div></div>
    <div class="skel-card"><div class="skel-line w40"></div><div class="skel-line w70"></div><div class="skel-line w90"></div></div>`;
}

export function renderQuickChips(commodity, chips) {
  const host = el("quickChips");
  host.innerHTML = chips.map((c) => `<button class="qchip" data-q="${c}">${c}</button>`).join("");
}

export function renderResults(resultsEl, set, app) {
  const cards = set.cards || [];
  const allOffers = [];
  for (const c of cards) for (const o of c.offers || []) if (o.priceUSD) allOffers.push({ card: c, offer: o });
  if (!allOffers.length) return renderEmpty(resultsEl, set);

  const min = Math.min(...allOffers.map((x) => x.offer.priceUSD));
  const max = Math.max(...allOffers.map((x) => x.offer.priceUSD));
  const sorted = [...allOffers].sort((a, b) => a.offer.priceUSD - b.offer.priceUSD);
  const best = sorted[0];

  const sourceClass = set.live ? "source-live" : "source-demo";
  const sourceLabel = set.live ? "Live web" : "Demo marketplace";

  const save = max - min;
  const priceBarMarkers = allOffers.map(({ card, offer }) => {
    const pct = max > min ? Math.min(98, Math.max(2, ((offer.priceUSD - min) / (max - min)) * 100)) : 50;
    const isBest = offer === best.offer;
    const isWorst = offer.priceUSD === max;
    return `<span class="price-marker ${isBest ? "is-best" : ""} ${isWorst ? "is-worst" : ""}" style="left:${pct}%" title="${offer.name}: ${fmt(offer.priceUSD, app.currency)}"></span>`;
  }).join("");

  // yearly-max insights (per card best offer, where known)
  const yearStrips = cards
    .filter((c) => c.yearMaxUSD && c.offers?.length)
    .slice(0, 4)
    .map((c) => {
      const cheapest = [...c.offers].sort((a, b) => a.priceUSD - b.priceUSD)[0];
      if (!cheapest.priceUSD) return "";
      const below = Math.round((1 - cheapest.priceUSD / c.yearMaxUSD) * 100);
      if (below <= 0) return "";
      return `<span><b>${c.title}</b>: lowest ${fmt(cheapest.priceUSD, app.currency)} ≈ <b>${below}% below</b> the 12-month peak (${fmt(c.yearMaxUSD, app.currency)})</span>`;
    })
    .filter(Boolean);

  const cardsHtml = cards.map((card) => renderCard(card, set, app, { min, max, best, allOffers })).join("");

  resultsEl.innerHTML = `
    <div class="result-header">
      <div>
        <h2 class="result-title">${esc(set.title || "Results")}</h2>
        <div class="result-meta">${esc(set.subtitle || "")}</div>
      </div>
      <span class="source-badge ${sourceClass}">${sourceLabel}</span>
    </div>

    <div class="price-bar-card">
      <div class="price-bar-head">
        <span class="price-bar-title">📊 Price range on this page — lowest to highest</span>
        <span class="price-bar-sub">${allOffers.length} quotes · best deal <b style="color:var(--green)">${fmt(min, app.currency)}</b> · highest ${fmt(max, app.currency)}</span>
      </div>
      <div class="price-track">${priceBarMarkers}</div>
      <div class="price-bar-labels">
        <span class="price-bar-low">▲ ${fmt(min, app.currency)} · lowest</span>
        <span class="price-bar-high">highest · ${fmt(max, app.currency)} ▲</span>
      </div>
      ${yearStrips.length ? `<div class="year-max-strip">📅 ${yearStrips.join(" · ")}</div>` : `<div class="year-max-strip">📅 No reliable 12-month price history for these listings — showing live quotes.</div>`}
    </div>

    <div class="result-toolbar">
      <span class="tool-chip">🔢 ${allOffers.length} offers</span>
      <span class="tool-chip">✅ ${set.live ? "trusted sources only" : "spam-filter active"}</span>
      <span class="tool-chip" title="Geo-spoofed location">📍 ${esc(set.geo?.label || "")}</span>
      ${app.incognito ? '<span class="tool-chip is-on">🕶️ Incognito · cookie markups stripped</span>' : ""}
      <span class="spacer"></span>
      <label class="tool-chip" style="gap:6px;cursor:pointer"><span>Sort:</span>
        <select class="select" id="sortSelect" style="padding:2px 22px 2px 8px;font-size:12px">
          <option value="low">Price: low → high</option>
          <option value="high">Price: high → low</option>
          <option value="trust">Trust score</option>
        </select>
      </label>
    </div>

    <div id="cardsHost">${cardsHtml}</div>

    <div class="results-summary">
      <span>💡 Buying at the <b>lowest quote</b> saves you <span class="big">${fmt(save, app.currency)}</span> vs the highest on this page</span>
      <span>🔁 Sorted <b>lowest → highest</b>, best deal pinned to the top</span>
    </div>`;

  wireSorting(resultsEl, cards, set, app, { min, max, best });
}

function wireSorting(resultsEl, cards, set, app, range) {
  const sortEl = el("sortSelect");
  if (!sortEl) return;
  sortEl.addEventListener("change", () => {
    const cardsHost = el("cardsHost");
    const order = sortEl.value;
    let sortedCards = [...cards];
    if (order === "trust") {
      sortedCards.sort((a, b) => {
        const ta = Math.max(...a.offers.map((o) => o.trust || 0));
        const tb = Math.max(...b.offers.map((o) => o.trust || 0));
        return tb - ta;
      });
    } else {
      sortedCards.sort((a, b) => {
        const pa = Math.min(...a.offers.map((o) => o.priceUSD || Infinity));
        const pb = Math.min(...b.offers.map((o) => o.priceUSD || Infinity));
        return order === "high" ? pb - pa : pa - pb;
      });
    }
    cardsHost.innerHTML = sortedCards.map((card) => renderCard(card, set, app, range)).join("");
    wireCardCoupons();
  });
}

function renderCard(card, set, app, range) {
  const offers = (card.offers || [])
    .filter((o) => o.priceUSD)
    .sort((a, b) => a.priceUSD - b.priceUSD);
  if (!offers.length) return "";

  const coupons = findCoupons(card.title, set.kind, offers, card.scannedCoupons || []);
  const trustOn = app.settings.trustFilter !== false;
  const visible = offers.filter((o) => trustOn ? !o.spam : true);
  const blocked = offers.filter((o) => trustOn && o.spam);
  const unpriced = visible.filter((o) => !o.priceUSD);

  const matchBanner = card.match?.viaImage
    ? `<div class="match-banner">🔎 <span>Visual match:</span> <b>${esc(card.title)}</b> — <span class="match-pct">${Math.round(card.match.score * 100)}% similarity</span> · photo analysed locally, no upload to servers</div>`
    : "";

  const offersHtml = visible.filter((o) => o.priceUSD).map((o) => renderOfferRow(o, card, set, app, range)).join("");
  const unpricedHtml = unpriced.map((o) => `
    <div class="offer-row">
      <div class="offer-merchant">
        <span class="merchant-avatar" style="background:${o.color || "#64748b"}">${esc((o.name || "?").charAt(0).toUpperCase())}</span>
        <span>
          <span class="merchant-name">${esc(o.name)}</span>
          <div class="merchant-domain">${esc(o.domain || "")}</div>
        </span>
      </div>
      <div class="offer-info">${o.meta ? `<div class="oi-line">${esc(o.meta)}</div>` : ""}${o.rating ? `<div class="oi-line">⭐ ${o.rating}/5</div>` : ""}</div>
      <div class="offer-price"><span class="price-val" style="color:var(--ink-faint);font-size:14px">rates on request</span></div>
      <a class="btn-buy" href="${esc(o.url || "#")}" target="_blank" rel="noopener noreferrer">Check <span class="ext">↗</span></a>
    </div>`).join("");
  const blockedHtml = blocked.length
    ? `<div class="offer-row" style="opacity:.55">
         <div class="offer-merchant"><span class="merchant-name" style="color:var(--ink-faint)">🚫 ${blocked.length} low-trust / spam-looking source${blocked.length > 1 ? "s" : ""} hidden</span></div>
         <div class="offer-info" style="min-width:0;flex:1">${blocked.map((b) => esc(b.name)).slice(0, 4).join(", ")}…</div>
         <div><span class="trust-pill trust-blocked">filtered · zero footfall</span></div>
       </div>`
    : "";

  const couponHtml = renderCoupons(card, coupons);

  const thumb = card.refImage
    ? `<img src="${esc(card.refImage)}" alt="" />`
    : (card.emoji || "📦");

  return `
    <article class="card" data-card="${esc(card.id)}">
      ${matchBanner}
      <div class="card-head">
        <div class="card-thumb">${thumb}</div>
        <div class="card-title-wrap">
          <h3 class="card-title">${esc(card.title)}</h3>
          <div class="card-sub">${esc(card.subtitle || "")}</div>
          <div class="card-tags">
            ${(card.cats || []).map((c) => `<span class="tag">${esc(c)}</span>`).join("")}
            ${card.match && !card.match.viaImage ? `<span class="tag indigo">${Math.round(card.match.score * 100)}% match</span>` : ""}
          </div>
        </div>
      </div>
      <div class="offer-list">${offersHtml}${unpricedHtml}${blockedHtml}</div>
      ${couponHtml}
      <div class="card-foot">
        <span>⭐ ${esc((card.subtitle || "").split("·")[0] || "—")}</span>
        ${card.perks ? `<span>${card.perks.slice(0, 3).map(esc).join(" · ")}</span>` : ""}
        <span>🛡️ All sources screened for trust &amp; footfall</span>
      </div>
    </article>`;
}

function renderOfferRow(o, card, set, app, range) {
  const { min, max, best } = range;
  const tone = priceTone(o.priceUSD, min, max);
  const isBest = o === best.offer;
  const tier = trustTier(o);
  const trustCls = tier === "high" ? "trust-high" : tier === "med" ? "trust-med" : "trust-low";
  const trustLabel = tier === "high" ? `★ ${o.trust}/100 trust` : tier === "med" ? `◆ ${o.trust}/100 trust` : `! ${o.trust}/100 trust`;

  let yearChip = "";
  if (card.yearMaxUSD && o.priceUSD) {
    const below = Math.round((1 - o.priceUSD / card.yearMaxUSD) * 100);
    if (below > 0) yearChip = `<div class="price-year"><b>▼ ${below}% below</b> 12-mo peak</div>`;
  }

  const couponForMerchant = validCouponsFor(card, set, o);
  const couponChip = couponForMerchant
    ? `<button class="coupon-chip" data-code="${couponForMerchant.code}" title="Copy coupon code ${couponForMerchant.code}">🏷️ <code>${couponForMerchant.code}</code> ${couponForMerchant.pct ? couponForMerchant.pct + "%" : "$" + (couponForMerchant.amountUSD || 0)}</button>`
    : "";

  const was = o.wasUSD && app.incognito
    ? `<div class="price-year" style="color:var(--green)">was ${fmt(o.wasUSD, app.currency)} with cookies</div>`
    : "";

  const meta = o.meta ? `<div class="oi-line">📦 ${esc(o.meta)}</div>` : "";
  const rating = o.rating ? `<div class="oi-line">⭐ ${o.rating}/5</div>` : "";

  const avatarBg = (o.color || merchantColor(o.domain)) || "#64748b";

  return `
    <div class="offer-row ${isBest ? "is-best" : ""}">
      <div class="offer-merchant">
        <span class="merchant-avatar" style="background:${avatarBg}">${esc((o.name || "?").charAt(0).toUpperCase())}</span>
        <span>
          <span class="merchant-name">${esc(o.name)}</span>
          <div class="merchant-domain">${esc(o.domain || "")}</div>
          <span class="trust-pill ${trustCls}" title="${esc(o.blockedReason || "Verified merchant")}">${trustLabel} · ${footfallLabel(o.footfall || 0)} visits/mo</span>
        </span>
      </div>
      <div class="offer-info">
        ${rating}${meta}
        ${o.ship ? `<div class="oi-line">🚚 ${esc(o.ship)}</div>` : ""}
      </div>
      <div class="offer-price">
        ${isBest ? '<span class="offer-badge" style="color:var(--green)">🏆 Lowest on page</span>' : ""}
        <div class="price-val ${tone}">${fmt(o.priceUSD, app.currency)}</div>
        ${yearChip}${was}
        ${couponChip}
      </div>
      <a class="btn-buy" href="${esc(o.url || "#")}" target="_blank" rel="noopener noreferrer">Buy <span class="ext">↗</span></a>
    </div>`;
}

function renderCoupons(card, coupons) {
  const valid = coupons.valid;
  if (!valid.length && !coupons.scanned.length) {
    return `<div class="coupon-panel">
      <div class="coupon-panel-title">🏷️ Coupon check <span style="color:var(--green);font-weight:700;font-size:11px">· auto-validated</span></div>
      <div class="no-coupons">✓ No valid, unexpired coupon codes found for this product right now. Nothing fake, nothing expired.</div>
    </div>`;
  }
  const cards = valid.map((c) => `
    <div class="coupon-card">
      <div class="c-code">${esc(c.code)}<button class="copy-btn" data-code="${esc(c.code)}">Copy</button></div>
      <div class="c-desc">${c.pct ? c.pct + "% off" : "$" + (c.amountUSD || 0) + " off"}${c.minSpendUSD ? " · min spend " + fmt(c.minSpendUSD, fxState.currency) : ""}</div>
      <div class="c-meta">✅ Verified valid · ${c.daysLeft} day${c.daysLeft === 1 ? "" : "s"} left (exp ${c.expiry})</div>
    </div>`).join("");
  const scanned = coupons.scanned.map((c) => `
    <div class="coupon-card" style="opacity:.8">
      <div class="c-code">${esc(c.code)}<button class="copy-btn" data-code="${esc(c.code)}">Copy</button></div>
      <div class="c-desc">Found on the web · ${c.pct ? c.pct + "% off" : "discount"}</div>
      <div class="c-meta" style="color:var(--amber)">⚠ Web-scanned — verify before checkout</div>
    </div>`).join("");
  return `<div class="coupon-panel">
    <div class="coupon-panel-title">🏷️ Valid coupons for ${esc(card.title)}</div>
    <div class="coupon-grid">${cards}${scanned}</div>
  </div>`;
}

export function validCouponsFor(card, set, offer) {
  const coupons = findCoupons(card.title, set.kind, [offer], card.scannedCoupons || []);
  return coupons.valid.find((c) => c.merchants.includes(offer.domain)) || null;
}

/** Re-render only the coupon panel of one card (used after a live web coupon scan). */
export function refreshCouponsForCard(cardId, card, kind, scanned) {
  const cardEl = document.querySelector(`[data-card="${CSS.escape(cardId)}"]`);
  if (!cardEl) return;
  const panel = cardEl.querySelector(".coupon-panel");
  if (!panel) return;
  const coupons = findCoupons(card.title, kind, card.offers || [], scanned);
  panel.outerHTML = renderCoupons(card, coupons);
}

export function wireCardCoupons() {
  document.querySelectorAll(".copy-btn, .coupon-chip").forEach((btn) => {
    btn.onclick = (e) => {
      e.preventDefault(); e.stopPropagation();
      const code = btn.dataset.code;
      navigator.clipboard?.writeText(code).then(() => toast(`Copied coupon ${code} 🎉`, "ok")).catch(() => toast(code));
    };
  });
  document.querySelectorAll(".coupon-chip").forEach((chip) => {
    chip.title = "Copy coupon code — apply at the retailer's checkout";
  });
}

function renderEmpty(resultsEl, set) {
  resultsEl.innerHTML = `<div class="empty-state">
    <div class="big-emoji">🔎</div>
    <h3>No trusted quotes found</h3>
    <p>Try a different search term, or widen the location — we only show sources with real footfall.</p>
  </div>`;
}

export function renderEmptySearch() {
  const resultsEl = el("results");
  resultsEl.innerHTML = `<div class="empty-state">
    <div class="big-emoji">🛒</div>
    <h3>Search for anything</h3>
    <p>Type a product, hotel, flight route or rental city — or upload a photo of the product you want.</p>
  </div>`;
}

function priceTone(price, min, max) {
  if (max <= min) return "p-low";
  const t = (price - min) / (max - min);
  if (t <= 0.25) return "p-low";
  if (t >= 0.75) return "p-high";
  return "p-mid";
}

const COLOR_PALETTE = ["#4f46e5", "#0ea5e9", "#16a34a", "#d97706", "#dc2626", "#7c3aed", "#0891b2", "#db2777"];
function merchantColor(domain) {
  let h = 0;
  for (let i = 0; i < domain.length; i++) h = (Math.imul(h, 31) + domain.charCodeAt(i)) | 0;
  return COLOR_PALETTE[Math.abs(h) % COLOR_PALETTE.length];
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));
}
