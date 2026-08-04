/* Altron PriceFinder — visual search.
   Computes a perceptual fingerprint (average-hash + dominant colors) of an
   uploaded photo and matches it against the bundled reference catalogue.
   Used in demo mode; live Google Lens search runs when a SerpAPI key is set. */

/** Load an image element from a data URL / object URL. */
export function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = (e) => reject(e);
    img.src = src;
  });
}

/** Resize to a small square bitmap via canvas. */
function toSmall(img, size) {
  const canvas = document.createElement("canvas");
  canvas.width = size; canvas.height = size;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(img, 0, 0, size, size);
  return ctx.getImageData(0, 0, size, size);
}

/** Average-hash: 64-bit perceptual hash as a hex string. */
export function averageHash(img, size = 8) {
  const { data } = toSmall(img, size);
  const grey = [];
  let sum = 0;
  for (let i = 0; i < data.length; i += 4) {
    const g = Math.round(data[i] * 0.299 + data[i + 1] * 0.587 + data[i + 2] * 0.114);
    grey.push(g); sum += g;
  }
  const avg = sum / grey.length;
  let hex = "";
  for (let i = 0; i < grey.length; i += 4) {
    let bits = 0;
    for (let j = 0; j < 4; j++) bits = (bits << 1) | (grey[i + j] >= avg ? 1 : 0);
    hex += bits.toString(16);
  }
  return hex;
}

/** Hamming distance between two hex hashes. */
export function hamming(a, b) {
  let d = 0;
  for (let i = 0; i < a.length; i++) {
    const x = parseInt(a[i], 16) ^ parseInt(b[i], 16);
    d += (x & 1) + ((x >> 1) & 1) + ((x >> 2) & 1) + ((x >> 3) & 1);
  }
  return d;
}

/** Dominant color signature (top-3 HSV buckets). */
export function dominantColors(img, buckets = 12) {
  const { data } = toSmall(img, 32);
  const counts = new Map();
  for (let i = 0; i < data.length; i += 4) {
    const r = data[i], g = data[i + 1], b = data[i + 2];
    if (r > 245 && g > 245 && b > 245) continue; // skip near-white background
    const h = Math.round(hue(r, g, b) / 30) % buckets;
    const s = Math.round(sat(r, g, b) * 100 / 25);
    const v = Math.round(val(r, g, b) * 100 / 25);
    const key = `${h}-${s}-${v}`;
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5).map(([k, n]) => k);
}
function hue(r, g, b) {
  const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
  if (d === 0) return 0;
  let h;
  if (max === r) h = ((g - b) / d) % 6;
  else if (max === g) h = (b - r) / d + 2;
  else h = (r - g) / d + 4;
  return (h * 60 + 360) % 360;
}
function sat(r, g, b) { const max = Math.max(r, g, b); return max === 0 ? 0 : (max - Math.min(r, g, b)) / max; }
function val(r, g, b) { return Math.max(r, g, b) / 255; }

function colorSimilarity(a, b) {
  const setA = new Set(a), setB = new Set(b);
  let hit = 0;
  for (const k of setA) if (setB.has(k)) hit++;
  return hit / Math.max(1, Math.min(a.length, b.length));
}

/** Overall perceptual similarity 0..1 between two images. */
export function similarity(imgA, imgB) {
  const h1 = averageHash(imgA), h2 = averageHash(imgB);
  const hd = hamming(h1, h2);            // 0..64
  const hashScore = 1 - hd / 64;
  const colScore = colorSimilarity(dominantColors(imgA), dominantColors(imgB));
  return 0.7 * hashScore + 0.3 * colScore;
}

/** Match an uploaded image against reference images. */
export async function matchImage(uploaded, refs) {
  const results = [];
  for (const ref of refs) {
    try {
      const img = await loadImage(ref.src);
      const s = similarity(uploaded, img);
      results.push({ ...ref, score: Math.round(s * 100) / 100 });
    } catch (_) { /* skip broken ref */ }
  }
  results.sort((a, b) => b.score - a.score);
  return results;
}

export function readFileAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onload = () => resolve(fr.result);
    fr.onerror = reject;
    fr.readAsDataURL(file);
  });
}
