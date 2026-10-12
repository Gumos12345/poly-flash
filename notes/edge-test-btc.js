// Test "kup Up po spadku" na realnych 1-min swiecach BTC (Binance daily klines, 30 dni).
const fs = require("fs");
const dir = "/tmp/pm/kl";
const rows = [];
for (const f of fs.readdirSync(dir).filter((x) => x.endsWith(".csv"))) {
  for (const line of fs.readFileSync(dir + "/" + f, "utf8").split("\n")) {
    if (!line) continue;
    const p = line.split(",");
    const t = Number(p[0]) / 1e6; // mikrosekundy -> sekundy
    rows.push({ t, o: +p[1], c: +p[4] });
  }
}
rows.sort((a, b) => a.t - b.t);
const byT = new Map(rows.map((r) => [r.t, r]));
console.log("swiece 1m:", rows.length, new Date(rows[0].t * 1000).toISOString().slice(0, 16), "->", new Date(rows[rows.length - 1].t * 1000).toISOString().slice(0, 16));

function absMove(sec) {
  let s = 0, n = 0;
  for (const r of rows) {
    if (r.t % sec) continue;
    const e = byT.get(r.t + sec);
    if (!e) continue;
    s += Math.abs(e.c / r.o - 1); n++;
  }
  return ((100 * s) / n).toFixed(3) + "%";
}
console.log("srednia |zmiana| w oknie: 5m =", absMove(300), ", 1h =", absMove(3600));

function test(winSec, ks, ths, label) {
  console.log(`\n== okna ${label} (rozliczenie: close okna > open okna) ==`);
  const out = [];
  for (const X of ths) {
    for (const k of ks) {
      let n = 0, win = 0, sig = 0;
      for (const r of rows) {
        if (r.t % winSec) continue;
        const e = byT.get(r.t + winSec - 60) || byT.get(r.t + winSec);
        const at = byT.get(r.t + k * 60);
        if (!e || !at) continue;
        const d = at.c / r.o - 1;
        if (d <= -X) { sig++; n++; if (e.c > r.o) win++; }
      }
      if (n === 0) continue;
      const w = win / n;
      out.push({
        prog: (X * 100).toFixed(2) + "%",
        min: k,
        sygnaly: sig,
        "winrate": (100 * w).toFixed(1) + "%",
        "EV(+40%/-90%)": (w * 0.4 - (1 - w) * 0.9).toFixed(3),
        "EV(+30%/-90%)": (w * 0.3 - (1 - w) * 0.9).toFixed(3),
      });
    }
  }
  console.table(out);
}
let base5 = 0, n5 = 0, base1h = 0, n1h = 0;
for (const r of rows) {
  if (r.t % 300 === 0) { const e = byT.get(r.t + 240); if (e) { n5++; if (e.c > r.o) base5++; } }
  if (r.t % 3600 === 0) { const e = byT.get(r.t + 3540); if (e) { n1h++; if (e.c > r.o) base1h++; } }
}
console.log(`baseline bez sygnalu: 5m P(up)=${(100 * base5 / n5).toFixed(1)}% (n=${n5}), 1h P(up)=${(100 * base1h / n1h).toFixed(1)}% (n=${n1h})`);
test(300, [1, 2, 3, 4], [0.0005, 0.001, 0.002, 0.003, 0.005], "5-minutowe (rynki up/down 5m)");
test(3600, [15, 30, 45], [0.003, 0.005, 0.01, 0.015, 0.02], "1-godzinne (rynki up/down 1h)");
console.log("\nwymagany winrate do break-even: +40%/-90% ->", (0.9 / 1.3 * 100).toFixed(1) + "%", "| +30%/-90% ->", (0.9 / 1.2 * 100).toFixed(1) + "%");
