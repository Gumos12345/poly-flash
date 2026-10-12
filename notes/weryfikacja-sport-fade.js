// Dokladna replikacja ich metody: wejscie przy PIERWSZYM wejsciu ceny YES w pasmo, HOLD do
// rozstrzygniecia (bez oplaty wyjscia, spread 2c, fee 0.05). Podzial wg plynnosci rynku.
const GAMMA = "https://gamma-api.polymarket.com/markets";
const CLOB = "https://clob.polymarket.com/prices-history";
const FEE = 0.05, SPREAD = 0.02;
const BANDS = [[0.15, 0.50], [0.15, 0.30], [0.30, 0.50], [0.02, 0.10], [0.05, 0.20]];
const VOLS = [200, 2000, 10000, 50000];

async function getClosed(pages) {
  const out = [];
  const now = Math.floor(Date.now() / 1000);
  const from = new Date((now - 25 * 86400) * 1000).toISOString().slice(0, 10);
  const to = new Date(now * 1000).toISOString().slice(0, 10);
  for (let i = 0; i < pages; i++) {
    const r = await fetch(`${GAMMA}?tag_id=1&closed=true&limit=100&offset=${i * 100}&end_date_min=${from}&end_date_max=${to}`);
    if (!r.ok) break;
    const j = await r.json();
    if (!Array.isArray(j) || !j.length) break;
    out.push(...j);
  }
  return out;
}
async function hist(tok) {
  const r = await fetch(`${CLOB}?market=${tok}&interval=max&fidelity=1`);
  if (!r.ok) return null;
  const j = await r.json();
  return j && Array.isArray(j.history) ? j.history : null;
}
function stat(list) {
  if (!list.length) return null;
  const n = list.length;
  const mean = list.reduce((a, b) => a + b.pnl, 0) / n;
  const sd = Math.sqrt(list.reduce((a, b) => a + (b.pnl - mean) ** 2, 0) / n);
  const t = sd > 0 ? mean / (sd / Math.sqrt(n)) : 0;
  const wr = list.filter((x) => x.yesWon).length / n;
  const avgP = list.reduce((a, b) => a + b.p, 0) / n;
  return { n, mean, t, wr, avgP };
}
(async () => {
  const mkts = await getClosed(12);
  const rows = [];
  for (const m of mkts) {
    let toks = [], pr = [], outs = [];
    try { toks = JSON.parse(m.clobTokenIds || "[]"); pr = JSON.parse(m.outcomePrices || "[]").map(Number); outs = JSON.parse(m.outcomes || "[]"); } catch (e) {}
    if (!toks.length || pr.length < 2 || !/yes/i.test(outs[0] || "")) continue;
    rows.push({ slug: m.slug, tok: toks[0], vol: Number(m.volumeNum || 0), yesWon: pr[0] >= 0.99 ? 1 : 0 });
  }
  const histMap = new Map();
  const queue = [...rows];
  async function worker() {
    while (queue.length) {
      const m = queue.shift();
      const h = await hist(m.tok);
      if (h && h.length > 10) histMap.set(m.tok, h);
    }
  }
  await Promise.all(Array.from({ length: 6 }, () => worker()));
  console.log("rynkow sportowych z historia:", histMap.size, "z", rows.length);

  for (const volMin of VOLS) {
    console.log(`\n=== vol >= ${volMin} ===`);
    const sub = rows.filter((m) => m.vol >= volMin && histMap.has(m.tok));
    console.log("rynkow w grupie:", sub.length);
    for (const [lo, hi] of BANDS) {
      const list = [];
      for (const m of sub) {
        const h = histMap.get(m.tok);
        const first = h.find((x) => x.p >= lo && x.p <= hi);
        if (!first) continue;
        const cost = 1 - first.p + FEE * (1 - first.p) * (1 - first.p) + SPREAD / 2;
        const payout = m.yesWon ? 0 : 1;
        list.push({ p: first.p, yesWon: m.yesWon, pnl: (payout - cost) / cost });
      }
      const s = stat(list);
      if (!s) { console.log(`pasmo ${lo}-${hi}: brak sygnalow`); continue; }
      console.log(
        `pasmo ${lo.toFixed(2)}-${hi.toFixed(2)}: n=${String(s.n).padStart(4)}  YES_wygral=${(100 * s.wr).toFixed(1).padStart(5)}%  sr.cena=${s.avgP.toFixed(3)}  EV/kupno NO=${(100 * s.mean).toFixed(2).padStart(7)}%  t=${s.t.toFixed(2)}`
      );
    }
  }
})();
