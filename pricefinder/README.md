# Altron PriceFinder — search the web for the cheapest price

A self-contained, zero-dependency web app that finds the **lowest trusted price**
for goods, hotels, tickets (flights) and car rentals — with live currency,
auto-validated coupons, geo-spoofing and incognito mode.

## Features

| Feature | What it does |
| --- | --- |
| 🛍️ Commodity tabs | **Goods · Hotels · Tickets · Rent-a-Car** — one search bar per category |
| 🔍 Text search | Free-text across the catalogue, with fuzzy scoring |
| 📷 Photo search | Upload / drag & drop / paste (Ctrl+V) a product photo → local perceptual-hash visual match, no image ever leaves your browser |
| 🌐 Live web search | Optional [SerpAPI](https://serpapi.com) key unlocks Google Shopping / Lens / Hotels / Flights / Maps through the local proxy |
| 🏆 Price bar | Top-of-page range bar showing **lowest → highest** with a marker per quote |
| 📅 Price history | "X% below the 12-month peak" badge per quote wherever history is known |
| 🟢🔴 Price colours | Lowest quote **green**, highest **red**, middle amber |
| 💱 6 currencies | **USD · EUR · GBP · AED · PKR · NZD** — live FX feeds (open.er-api.com → Frankfurter → static fallback) |
| 📍 Geo-spoofing | Re-quote prices as if browsing from 10 countries (flights/hotels especially vary by origin) |
| 🕶️ Incognito mode | Strips cookies & personalization; shows the markup retailers would have added for cookie-identified visitors |
| 🛡️ Trusted sources only | Every merchant is scored (trust + monthly footfall); spammy zero-traffic sites are hidden by default and marked when revealed |
| 🏷️ Valid coupons only | Auto-matched, expiry-checked, verified codes with copy buttons; optional live web coupon scan (marked "unverified") |
| 🛒 Buy direct | Every quote links straight to the real retailer with your search pre-filled |

## Run it

Requires **Python 3.11+** (stdlib only — no pip install needed).

```bash
cd pricefinder
python3 server.py            # → http://localhost:8000
```

or with live web search:

```bash
SERPAPI_KEY=your_key python3 server.py
```

That's it. The app works fully in **demo mode** (realistic marketplace data) with
no key; adding a key switches it to **live web search** with automatic demo
fallback whenever the upstream is unreachable.

### Getting a SerpAPI key

1. Create a free account at <https://serpapi.com> (100 free searches/month).
2. Copy the API key from the dashboard.
3. Either `SERPAPI_KEY=... python3 server.py`, or paste the key into the app's
   ⚙️ Settings panel (stored in your browser's localStorage only).

The key only ever travels **browser → your local server → SerpAPI**; it is never
embedded in page code.

## How it works

- **Search** → the orchestrator (`app/search.js`) tries live SerpAPI, then
  falls back to the demo marketplace (`app/demo.js`).
- **Trust filter** (`app/trust.js`) classifies every merchant by reputation and
  monthly visits; spam-looking TLDs (`.top`, `.biz`, `deals-…` etc.) are auto-flagged.
- **Coupons** (`app/coupons.js`) are matched by merchant + product tags and only
  *verified, unexpired* codes are shown.
- **FX** (`app/fx.js`) tries three rate sources in order, always keeping the app
  usable offline.
- **Visual search** (`app/imgmatch.js`) computes an average-hash + dominant-colour
  fingerprint entirely in the browser.

## Project layout

```text
pricefinder/
├── index.html          app shell
├── server.py           static server + privacy proxy (stdlib only)
├── app/
│   ├── main.js         state & wiring
│   ├── ui.js           rendering (cards, price bar, coupons)
│   ├── search.js       live-web orchestrator + SerpAPI parsers
│   ├── demo.js         demo marketplace dataset + search engine
│   ├── trust.js        merchant trust/footfall database + spam filter
│   ├── coupons.js      coupon engine (validity-checked)
│   ├── fx.js           currency conversion (live + fallback)
│   ├── imgmatch.js     perceptual image hashing
│   └── styles.css
└── assets/ref/         reference product photos for visual search
```

## Notes & disclaimers

- Demo prices are illustrative market data bundled into the app; live results
  come from the search engine, not from any retailer directly.
- "Incognito" and "geo-spoofing" here mean the app re-quotes anonymously and
  from other markets — they cannot literally move your browser's IP. Use them
  together with a VPN if you want the full effect.
- This app is not affiliated with any retailer; coupon codes should always be
  verified at the merchant's checkout.
