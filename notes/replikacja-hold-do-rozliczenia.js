// Replikacja backtestu ("6h okno, -30%/-40% spadek -> TP +30/+40%, SL -90%, time-exit 2h")
// na realnych historiach cen z CLOB (prices-history) dla rynkow tagu 120 (Finance).
const GAMMA = "https://gamma-api.polymarket.com/markets";
const CLOB = "https://clob.polymarket.com/prices-history";

async function getMarkets(tagId, closed, pages) {
  const out = [];
  for (let i = 0; i < pages; i++) {
    const r = await fetch(`${GAMMA}?tag_id=${tagId}&closed=${closed}&limit=100&offset=${i * 100}`);
    if (!r.ok) break;
    const j = await r.json();
    if (!Array.isArray(j) || j.length === 0) break;
    out.push(...j);
  }
  return out;
}

async function history(token) {
  const r = await fetch(`${CLOB}?market=${token}&interval=max&fidelity=1`);
  if (!r.ok) return null;
  const j = await r.json();
  return j && Array.isArray(j.history) ? j.history : null;
}

function simulate(h, dropTh, tp, sl, lookbackH, exitH) {
  const evts = [];
  const H = 3600;
  for (let i = 0; i < h.length; i++) {
    const p0 = h[i].p;
    if (!(p0 > 0.02) || p0 > 0.98) continue;
    // szukamy spadku o dropTh w ciagu lookbackH godzin (dowolny moment w oknie)
    let dropRef = null;
    for (let k = i - 1; k >= 0 && h[k].t >= h[i].t - lookbackH * H; k--) {
      if (h[k].p >= p0 / (1 - dropTh)) { dropRef = h[k]; break; }
    }
    if (!dropRef) continue;
    const entry = p0;
    let res = null;
    for (let k = i + 1; k < h.length && h[k].t <= h[i].t + exitH * H; k++) {
      if (h[k].p >= entry * (1 + tp)) { res = { kind: "TP", pnl: tp }; break; }
      if (h[k].p <= entry * (1 - sl)) { res = { kind: "SL", pnl: -sl }; break; }
    }
    if (!res) {
      const last = h.filter((x) => x.t <= h[i].t + exitH * H).pop();
      res = { kind: "EXIT", pnl: last ? (last.p - entry) / entry : 0 };
    }
    evts.push({ t: h[i].t, entry, ...res });
  }
  return evts;
}

(async () => {
  const open = await getMarkets(120, false, 5);
  const closed = await getMarkets(120, true, 10);
  const all = [...closed, ...open];
  console.log("rynkow tag120:", all.length, "(zamknietych:", closed.length, ", otwartych:", open.length, ")");

  const todo = all
    .map((m) => {
      let tok = null;
      try { tok = JSON.parse(m.clobTokenIds || "[]")[0]; } catch (e) {}
      return { q: m.question, slug: m.slug, tok, vol: Number(m.volumeNum || m.volume || 0), end: m.endDate };
    })
    .filter((m) => m.tok && m.vol > 100);
  console.log("z historia do testu:", todo.length);

  const configs = [
    { name: "6h, drop -40%, TP +40%", dropTh: 0.40, tp: 0.40, lookbackH: 6 },
    { name: "6h, drop -30%, TP +30%", dropTh: 0.30, tp: 0.30, lookbackH: 6 },
  ];
  const agg = configs.map(() => ({ n: 0, win: 0, sumPnl: 0, sl: 0, tp: 0, ex: 0, minT: Infinity, maxT: 0 }));

  let done = 0;
  const queue = [...todo];
  async function worker() {
    while (queue.length) {
      const m = queue.shift();
      const h = await history(m.tok);
      if (h && h.length > 10) {
        configs.forEach((c, ci) => {
          for (const e of simulate(h, c.dropTh, c.tp, 0.90, c.lookbackH, 100000)) {
            const a = agg[ci];
            a.n++; if (e.pnl > 0) a.win++; a.sumPnl += e.pnl;
            if (e.kind === "SL") a.sl++; else if (e.kind === "TP") a.tp++; else a.ex++;
            a.minT = Math.min(a.minT, e.t); a.maxT = Math.max(a.maxT, e.t);
          }
        });
      }
      done++;
      if (done % 50 === 0) console.log("  ...przetworzono", done, "/", todo.length);
    }
  }
  await Promise.all([worker(), worker(), worker(), worker(), worker(), worker()]);

  console.log("\n=== Wynik replikacji (dane CLOB, 1h swiece, bez oplat, BEZ time-exit (hold do rozliczenia)) ===");
  configs.forEach((c, ci) => {
    const a = agg[ci];
    if (!a.n) return console.log(c.name, "-> 0 sygnalow");
    console.log(
      `${c.name}: sygnalow=${a.n} win=${((100 * a.win) / a.n).toFixed(1)}% ROI/pozycja=${(100 * a.sumPnl / a.n).toFixed(2)}%  [TP=${a.tp} SL=${a.sl} EXIT=${a.ex}]`
    );
  });
})();
