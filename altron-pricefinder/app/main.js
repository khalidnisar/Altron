/* Altron PriceFinder — application entry point & state wiring. */

import { CURRENCIES, state as fxState, loadRates } from "./fx.js";
import { GEO, QUICK_CHIPS, IMAGE_REFS } from "./demo.js";
import { runSearch } from "./search.js";
import { el, toast, renderQuickChips, renderResults, showSkeleton, wireCardCoupons, renderEmptySearch, refreshCouponsForCard } from "./ui.js";
import { loadImage, matchImage, readFileAsDataURL } from "./imgmatch.js";

const LS = {
  currency: "pf_currency", geo: "pf_geo", incognito: "pf_incognito",
  serpKey: "pf_serpkey", trustFilter: "pf_trust", scanCoupons: "pf_scan", defaultGeo: "pf_defgeo", defaultIncognito: "pf_defincog",
};

const app = {
  commodity: "goods",
  geo: localStorage.getItem(LS.geo) || "us",
  incognito: localStorage.getItem(LS.incognito) === "1",
  currency: localStorage.getItem(LS.currency) || "USD",
  settings: {
    serpKey: localStorage.getItem(LS.serpKey) || "",
    trustFilter: localStorage.getItem(LS.trustFilter) !== "0",
    scanCoupons: localStorage.getItem(LS.scanCoupons) !== "0",
    defaultGeo: localStorage.getItem(LS.defaultGeo) || "us",
    defaultIncognito: localStorage.getItem(LS.defaultIncognito) === "1",
  },
  lastImage: null,          // { dataUrl, name, match }
  lastResult: null,         // last rendered set (for currency re-render)
};

/* ---------------- boot ---------------- */
async function boot() {
  populateSelects();
  fxState.currency = app.currency;
  loadRates(el("fxStatus")).then(() => {
    if (app.lastResult) rerenderResults();
  });

  el("currencySelect").value = app.currency;
  el("geoSelect").value = app.geo;
  setIncognitoUI(app.incognito);

  el("settingsBtn").onclick = () => openModal("settingsModal");
  el("aboutBtn").onclick = () => openModal("aboutModal");
  el("brandLink").onclick = (e) => { e.preventDefault(); renderEmptySearch(); app.lastResult = null; };

  wireSearch();
  wireImageUpload();
  wireTabs();
  wireControls();
  wireModals();
  wireQuickChips();
  wireSettings();

  renderQuickChips(app.commodity, QUICK_CHIPS[app.commodity]);
  renderEmptySearch();

  window.addEventListener("paste", (e) => {
    const items = e.clipboardData?.items || [];
    for (const item of items) {
      if (item.type.startsWith("image/")) {
        const file = item.getAsFile();
        if (file) { handleImageFile(file); toast("📸 Photo pasted — running visual search"); break; }
      }
    }
  });

  checkHealth();
}

function populateSelects() {
  const geoSel = el("geoSelect");
  geoSel.innerHTML = GEO.map((g) => `<option value="${g.id}">${g.label}</option>`).join("");
  const curSel = el("currencySelect");
  curSel.innerHTML = CURRENCIES.map((c) => `<option value="${c.code}">${c.flag} ${c.code} — ${c.label}</option>`).join("");
}

/* ---------------- commodity tabs ---------------- */
function wireTabs() {
  el("commodityTabs").querySelectorAll(".tab").forEach((tab) => {
    tab.onclick = () => {
      el("commodityTabs").querySelectorAll(".tab").forEach((t) => t.classList.remove("is-active"));
      tab.classList.add("is-active");
      app.commodity = tab.dataset.commodity;
      renderQuickChips(app.commodity, QUICK_CHIPS[app.commodity]);
      updatePlaceholder();
      if (app.lastResult) { renderEmptySearch(); app.lastResult = null; }
    };
  });
}

function updatePlaceholder() {
  const map = {
    goods: "Try “iPhone 16 Pro”, “Sony headphones”, “Nike Air Force 1”…",
    hotels: "Try “hotels in Dubai”, “hotels in London”, “hotels in Lahore”…",
    flights: "Try “flight London to Dubai”, “flight New York to Dubai”…",
    cars: "Try “rent a car in Dubai”, “rent a car in Auckland”…",
  };
  el("searchInput").placeholder = map[app.commodity];
}

/* ---------------- controls ---------------- */
function wireControls() {
  el("currencySelect").onchange = (e) => {
    app.currency = e.target.value;
    fxState.currency = app.currency;
    localStorage.setItem(LS.currency, app.currency);
    if (app.lastResult) rerenderResults();
  };
  el("geoSelect").onchange = (e) => {
    app.geo = e.target.value;
    localStorage.setItem(LS.geo, app.geo);
    toast(`📍 Geo-spoofing: ${GEO.find((g) => g.id === app.geo)?.label} — quotes re-quoted for this market`, "ok");
  };
  el("incognitoBtn").onclick = () => {
    app.incognito = !app.incognito;
    setIncognitoUI(app.incognito);
    localStorage.setItem(LS.incognito, app.incognito ? "1" : "0");
    toast(app.incognito
      ? "🕶️ Incognito ON — cookies cleared, personalization stripped. Retailers can't markup your history."
      : "Incognito OFF — standard session.", app.incognito ? "ok" : "");
    updateStatusStrip();
  };
}

function setIncognitoUI(on) {
  el("incognitoBtn").classList.toggle("is-on", on);
  el("incognitoState").textContent = on ? "on" : "off";
  updateStatusStrip();
}

function updateStatusStrip() {
  const strip = el("statusStrip");
  const parts = [];
  if (app.incognito) parts.push("<b>🕶️ Incognito mode</b> — cookies cleared · no personalized pricing · anonymous query params");
  parts.push(`<b>📍 Geo-spoofed:</b> ${GEO.find((g) => g.id === app.geo)?.label} — rates re-quoted as if browsing from there`);
  if (parts.length) {
    strip.innerHTML = parts.join(" &nbsp;·&nbsp; ");
    strip.hidden = false;
  } else strip.hidden = true;
}

/* ---------------- search ---------------- */
function wireSearch() {
  const doSearch = () => run();
  el("searchBtn").onclick = doSearch;
  el("searchInput").addEventListener("keydown", (e) => { if (e.key === "Enter") doSearch(); });
  el("sampleSearchBtn").onclick = () => {
    const samples = QUICK_CHIPS[app.commodity];
    const q = samples[Math.floor(Math.random() * samples.length)];
    el("searchInput").value = q;
    run();
  };
}

async function run() {
  const q = el("searchInput").value.trim();
  if (!q && !app.lastImage) { toast("Type what you're looking for, or upload a photo 📷"); return; }
  // An uploaded photo only drives the search when the user hasn't typed
  // (or re-typed) a text query of their own.
  const imgQuery = (app.lastImage?.match?.query || "").toLowerCase();
  const useImage = !!app.lastImage && (!q || (imgQuery && q.toLowerCase() === imgQuery));
  const resultsEl = el("results");
  showSkeleton(resultsEl);
  const t0 = performance.now();
  try {
    const set = await runSearch({
      commodity: app.commodity,
      q: q || (app.lastImage?.match?.query || app.lastImage?.name || ""),
      geo: app.geo,
      incognito: app.incognito,
      image: useImage ? { dataUrl: app.lastImage.dataUrl, match: app.lastImage.match } : null,
      settings: app.settings,
    });
    app.lastResult = set;
    renderResults(resultsEl, set, app);
    wireCardCoupons();
    maybeScanLiveCoupons(set);
    const ms = Math.round(performance.now() - t0);
    toast(set.live
      ? `🌐 Live web search complete in ${ms}ms`
      : `✅ Compared ${set.cards?.reduce((n, c) => n + c.offers.length, 0) || 0} quotes in ${ms}ms`, "ok");
    resultsEl.scrollIntoView?.({ behavior: "smooth", block: "start" });
  } catch (err) {
    console.error(err);
    resultsEl.innerHTML = `<div class="empty-state"><div class="big-emoji">😵</div><h3>Something went wrong</h3><p>${escMsg(err.message)}</p></div>`;
  }
}

function rerenderResults() {
  if (!app.lastResult) return;
  renderResults(el("results"), app.lastResult, app);
  wireCardCoupons();
}

/* ---------------- image upload ---------------- */
function wireImageUpload() {
  const dz = el("dropzone");
  const input = el("imageInput");
  dz.onclick = (e) => { e.preventDefault(); input.click(); };
  dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("is-dragging"); });
  dz.addEventListener("dragleave", () => dz.classList.remove("is-dragging"));
  dz.addEventListener("drop", (e) => {
    e.preventDefault(); dz.classList.remove("is-dragging");
    const file = e.dataTransfer.files?.[0];
    if (file?.type.startsWith("image/")) handleImageFile(file);
  });
  input.onchange = () => { if (input.files?.[0]) handleImageFile(input.files[0]); input.value = ""; };
  el("removeImageBtn").onclick = () => {
    app.lastImage = null;
    el("imagePreview").hidden = true;
    el("searchInput").focus();
  };
}

async function handleImageFile(file) {
  const dataUrl = await readFileAsDataURL(file);
  const preview = el("imagePreview");
  const img = el("imagePreviewImg");
  img.src = dataUrl;
  el("imagePreviewName").textContent = file.name || "paste.png";
  el("imagePreviewStatus").textContent = "Analyzing visual fingerprint…";
  preview.hidden = false;

  try {
    const uploaded = await loadImage(dataUrl);
    const results = await matchImage(uploaded, IMAGE_REFS);
    const top = results[0];
    app.lastImage = {
      dataUrl, name: file.name || "paste.png",
      match: top && top.score >= 0.42
        ? { productKey: top.productKey, query: top.name, score: top.score, viaImage: true }
        : { query: "", score: 0, viaImage: false },
    };
    if (top && top.score >= 0.42) {
      el("imagePreviewStatus").textContent = `Visual match: ${top.name} (${Math.round(top.score * 100)}% similarity) — ready to search`;
      toast(`🔎 Best visual match: ${top.name} — ${Math.round(top.score * 100)}%`, "ok");
      // auto-run the search for the matched product
      el("searchInput").value = top.name;
      run();
    } else {
      el("imagePreviewStatus").textContent = "No strong catalogue match — will search with best guess";
      toast("🔎 No strong match — searching text from image metadata");
      run();
    }
  } catch (err) {
    console.error(err);
    el("imagePreviewStatus").textContent = "Could not analyze image";
    toast("Image analysis failed — searching by filename", "err");
    app.lastImage = { dataUrl, name: file.name || "image", match: null };
    run();
  }
}

/* ---------------- live coupon scanning (optional) ---------------- */
async function maybeScanLiveCoupons(set) {
  if (!set.live || !app.settings.scanCoupons || !app.settings.serpKey) return;
  const card = (set.cards || [])[0];
  if (!card) return;
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 15000);
    const url = `/api/search?engine=google&q=${encodeURIComponent(card.title + " coupon code")}&num=10`;
    const r = await fetch(url, { signal: ctrl.signal });
    clearTimeout(t);
    const j = await r.json();
    const organic = j.organic_results || [];
    const found = [];
    for (const res of organic) {
      const hay = `${res.title || ""} ${res.snippet || ""}`;
      const codes = hay.match(/\b[A-Z][A-Z0-9]{5,13}\b/g) || [];
      for (const code of codes) {
        if (/^(COUPON|PROMO|SAVE|DEAL|CODE|GET|USE)$/i.test(code)) continue;
        if (!found.find((f) => f.code === code)) {
          found.push({ code, pct: null, domain: (res.domain || ""), expiry: null });
        }
      }
      if (found.length >= 4) break;
    }
    if (found.length) {
      card.scannedCoupons = found;
      refreshCouponsForCard(card.id, card, set.kind, found);
    }
  } catch (_) { /* optional — silently ignore */ }
}

/* ---------------- quick chips ---------------- */
function wireQuickChips() {
  el("quickChips").onclick = (e) => {
    const chip = e.target.closest(".qchip");
    if (!chip) return;
    el("searchInput").value = chip.dataset.q;
    run();
  };
}

/* ---------------- modals & settings ---------------- */
function wireModals() {
  document.querySelectorAll(".modal-backdrop").forEach((backdrop) => {
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop || e.target.closest("[data-close]")) closeModal(backdrop.id);
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !backdrop.hidden) closeModal(backdrop.id);
    });
  });
}

function openModal(id) { el(id).hidden = false; }
function closeModal(id) { el(id).hidden = true; }

function wireSettings() {
  el("serpKeyInput").value = app.settings.serpKey;
  el("trustFilterInput").checked = app.settings.trustFilter;
  el("scanCouponsInput").checked = app.settings.scanCoupons;
  el("defaultGeoInput").innerHTML = GEO.map((g) => `<option value="${g.id}">${g.label}</option>`).join("");
  el("defaultGeoInput").value = app.settings.defaultGeo;
  el("defaultIncognitoInput").checked = app.settings.defaultIncognito;

  el("serpKeyInput").onchange = (e) => { app.settings.serpKey = e.target.value.trim(); localStorage.setItem(LS.serpKey, app.settings.serpKey); };
  el("trustFilterInput").onchange = (e) => { app.settings.trustFilter = e.target.checked; localStorage.setItem(LS.trustFilter, e.target.checked ? "1" : "0"); };
  el("scanCouponsInput").onchange = (e) => { app.settings.scanCoupons = e.target.checked; localStorage.setItem(LS.scanCoupons, e.target.checked ? "1" : "0"); };
  el("defaultGeoInput").onchange = (e) => { app.settings.defaultGeo = e.target.value; localStorage.setItem(LS.defaultGeo, e.target.value); };
  el("defaultIncognitoInput").onchange = (e) => {
    app.settings.defaultIncognito = e.target.checked;
    localStorage.setItem(LS.defaultIncognito, e.target.checked ? "1" : "0");
    if (e.target.checked) { app.incognito = true; setIncognitoUI(true); localStorage.setItem(LS.incognito, "1"); }
  };
}

async function checkHealth() {
  try {
    const r = await fetch("/api/health");
    const j = await r.json();
    if (j.ok && j.serpapi_key_set) {
      const strip = el("statusStrip");
      strip.innerHTML = `<b>🌐 Live web search armed</b> — SerpAPI key detected (server-side)`;
      strip.hidden = false;
    }
  } catch (_) {}
}

function escMsg(s) {
  return String(s || "Unknown error").replace(/[&<>"']/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));
}

boot();
