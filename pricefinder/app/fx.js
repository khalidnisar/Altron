/* Altron PriceFinder — currency engine.
   All internal prices are stored in USD. Display prices are converted
   using live public FX rates (open.er-api.com → frankfurter → static fallback). */

export const CURRENCIES = [
  { code: "USD", label: "US Dollar",    symbol: "$",   flag: "🇺🇸" },
  { code: "EUR", label: "Euro",         symbol: "€",   flag: "🇪🇺" },
  { code: "GBP", label: "British Pound",symbol: "£",   flag: "🇬🇧" },
  { code: "AED", label: "UAE Dirham",   symbol: "AED ", flag: "🇦🇪" },
  { code: "PKR", label: "Pakistani Rupee", symbol: "₨", flag: "🇵🇰" },
  { code: "NZD", label: "New Zealand Dollar", symbol: "NZ$", flag: "🇳🇿" },
];

/* Static fallback rates per 1 USD (approx, used only when live feeds unreachable). */
const STATIC = { USD: 1, EUR: 0.92, GBP: 0.79, AED: 3.6725, PKR: 278.5, NZD: 1.64 };

export const state = {
  rates: null,        // { CODE: number } per 1 USD
  source: "static",   // "live" | "static"
  asOf: null,         // ISO date when live rates were fetched
  currency: "USD",
  statusEl: null,
};

export function getRates() {
  return state.rates && Object.keys(state.rates).length ? state.rates : STATIC;
}

export function isLive() {
  return state.source === "live";
}

export async function loadRates(statusEl = null) {
  state.statusEl = statusEl;
  const attempts = [
    async () => {
      const r = await fetch("https://open.er-api.com/v6/latest/USD");
      if (!r.ok) throw new Error("er-api " + r.status);
      const j = await r.json();
      if (j.result !== "success") throw new Error("er-api result");
      return { rates: j.rates, date: j.time_last_update_utc ? j.time_last_update_utc.slice(0, 10) : null };
    },
    async () => {
      const r = await fetch("/api/fx");
      if (!r.ok) throw new Error("proxy " + r.status);
      const j = await r.json();
      if (j.rates) return { rates: j.rates, date: j.time_last_update_utc ? j.time_last_update_utc.slice(0, 10) : null };
      throw new Error("proxy payload");
    },
    async () => {
      const r = await fetch("https://api.frankfurter.app/latest?from=USD");
      if (!r.ok) throw new Error("frankfurter " + r.status);
      const j = await r.json();
      return { rates: { ...j.rates, USD: 1 }, date: j.date || null };
    },
  ];
  for (const attempt of attempts) {
    try {
      const { rates, date } = await attempt();
      if (!rates || typeof rates.USD === "undefined") continue;
      state.rates = rates;
      state.source = "live";
      state.asOf = date || new Date().toISOString().slice(0, 10);
      break;
    } catch (_) { /* try next */ }
  }
  if (!state.rates) {
    state.rates = { ...STATIC };
    state.source = "static";
    state.asOf = null;
  }
  renderStatus();
  return state;
}

function renderStatus() {
  if (!state.statusEl) return;
  if (state.source === "live") {
    state.statusEl.className = "fx-status live";
    state.statusEl.textContent = `Exchange rates: live · ${state.asOf} (ECB/central-bank feeds)`;
  } else {
    state.statusEl.className = "fx-status cached";
    state.statusEl.textContent = "Exchange rates: offline — using built-in reference rates";
  }
}

/** Convert a USD amount into the display currency. */
export function convert(usd, code = state.currency) {
  const rates = getRates();
  const rate = rates[code] ?? 1;
  return usd * rate;
}

/** Format a USD amount as the display currency. */
export function fmt(usd, code = state.currency, opts = {}) {
  const c = CURRENCIES.find((x) => x.code === code) || CURRENCIES[0];
  const val = convert(usd, code);
  const decimals = code === "PKR" || code === "AED" ? 0 : 2;
  let s;
  try {
    s = new Intl.NumberFormat("en-US", { style: "currency", currency: code, minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(val);
  } catch (_) {
    s = `${c.symbol}${val.toFixed(decimals)}`;
  }
  if (opts.compact && Math.abs(val) >= 100000) {
    const big = Math.round(val / 1000);
    s = `${c.symbol}${big}k`;
  }
  return s;
}
