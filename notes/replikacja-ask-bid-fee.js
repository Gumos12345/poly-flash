// Realistyczny test strategii Finance: wejscie po ASK, wyjscie po BID, oplata 0.04 na strone
// (fee = C*rate*p*(1-p)), sweep horyzontu trzymania. Filtr min. rozmiaru zlecenia (5 share'ow).
const GAMMA = "https://gamma-api.polymarket.com/markets";
const CLOB = "https://clob.polymarket.com/prices-history";
const RATE = 0.04;          // Finance taker fee rate
const STAKE = 1.0;          // stawka na pozycje [$]
const MIN_SHARES = 5.0;     // orderMinSize na CLOB
const SPREAD = Number(process.argv[2] || 0.02);

async function getMarkets(tagId, closed, pages) {
  const out = [];
  for (let i = 0; i < pages; i++) {
    const r = await fetch(`${GAMMA}?tag_id=${tagId}&closed=${closed}&limit=100&offset=${i * 100}`);
    if (!r.ok) break;
    const j = await r.json();
    if (!Array.isArray(j) || !j.length) break;
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
// wejscie: mid -> ask (+s/2); wyjscie: mid -> bid (-s/2); fee= shares*RATE*p*(1-p)
function sim(h, dropTh, tp, lookbackH, exitH, enforceMin) {
  const evs = [];
  const H = 3600, half = SPREAD / 2;
  for (let i = 1; i < h.length; i++) {
    const mid = h[i].p;
    if (!(mid > 0.16) || mid > 0.90) continue;
    const ask = Math.min(0.999, mid + half);
    const shares = STAKE / ask;
    if (enforceMin && shares < MIN_SHARES) continue;      // zlecenie odpadnie
    let dropRef = null;
    for (let k = i - 1; k >= 0 && h[k].t >= h[i].t - lookbackH * H; k--) {
      if (h[k].p >= ask / (1 - dropTh)) { dropRef = h[k]; break; }
    }
    if (!dropRef) continue;
    const tpLevel = ask * (1 + tp);
    const slLevel = ask * (1 - 0.90);
    let exitBid = null, reason = "TIME";
    for (let k = i + 1; k < h.length; k++) {
      if (h[k].t > h[i].t + exitH * H) break;
      const bid = Math.max(0.001, h[k].p - half);
      if (bid >= tpLevel) { exitBid = bid; reason = "TP"; break; }
      if (bid <= slLevel) { exitBid = bid; reason = "SL"; break; }
    }
    if (exitBid === null) {
      const endT = h[i].t + exitH * H;
      let j = i + 1;
      while (j + 1 < h.length && h[j + 1].t <= endT) j++;
      const midExit = h[Math.min(j, h.length - 1)].p;
      exitBid = Math.max(0.001, midExit - half);
    }
    const cost = shares * ask + shares * RATE * ask * (1 - ask);
    const proceeds = shares * exitBid - shares * RATE * exitBid * (1 - exitBid);
    evs.push({ pnl: (proceeds - cost) / cost, reason });
  }
  return evs;
}
(async () => {
  const all = [...(await getMarkets(120, true, 10)), ...(await getMarkets(120, false, 5))];
  const todo = all
    .map((m) => { let t = null; try { t = JSON.parse(m.clobTokenIds || "[]")[0]; } catch (e) {} return { tok: t, vol: Number(m.volumeNum || 0) }; })
    .filter((m) => m.tok && m.vol > 100);
  const hist = new Map();
  const queue = [...todo];
  async function worker() {
    while (queue.length) {
      const m = queue.shift();
      const h = await history(m.tok);
      if (h && h.length > 20) hist.set(m.tok, h);
    }
  }
  await Promise.all(Array.from({ length: 6 }, worker));

  console.log(`rynkow z historia: ${hist.size}, spread=${SPREAD}, stawka=${STAKE}$ (min ${MIN_SHARES} share), rate=${RATE}`);
  const strats = [
    { name: "-40/+40", drop: 0.40, tp: 0.40 },
    { name: "-30/+30", drop: 0.30, tp: 0.30 },
  ];
  for (const minFilter of [false, true]) {
    console.log(`\n=== ${minFilter ? "z filtrem min. rozmiaru (ask <= 0.20)" : "bez filtra min. rozmiaru"} ===`);
    const rows = [];
    for (const s of strats) {
      for (const exitH of [2, 6, 12, 24, 72, 720]) {
        let n = 0, win = 0, sum = 0, sl = 0, tp = 0;
        for (const h of hist.values()) {
          for (const e of sim(h, s.drop, s.tp, 6, exitH, minFilter)) {
            n++; if (e.pnl > 0) win++; sum += e.pnl;
            if (e.reason === "SL") sl++; else if (e.reason === "TP") tp++;
          }
        }
        if (n > 20) rows.push({ strategia: s.name, "hold[h]": exitH, sygnalow: n, win: (100 * win / n).toFixed(1) + "%", "ROI netto/poz": (100 * sum / n).toFixed(2) + "%", TP: tp, SL: sl });
      }
    }
    console.table(rows);
  }
})();
