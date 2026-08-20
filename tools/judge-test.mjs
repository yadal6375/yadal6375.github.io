// くみたてる — 判定の検証（仕様書 9-2）
// node tools/judge-test.mjs [閾値] [大きさの係数]

import fs from "node:fs";

const D = JSON.parse(fs.readFileSync("data/kumitateru.json", "utf8"));
const PARTS = D.parts, KANJI = D.kanji;

const OK = Number(process.argv[2] ?? 14);
const WS = Number(process.argv[3] ?? 0.25);   // 大きさのずれの重み

// 部品の集合 → その集合になる漢字たち
const byKey = new Map();
for (const [ch, v] of Object.entries(KANJI)) {
  if (v.parts.length < 2) continue;           // 1部品の字は組み立てられない
  const k = [...v.parts].sort().join("");
  (byKey.get(k) ?? byKey.set(k, []).get(k)).push(ch);
}
const buildable = Object.keys(KANJI).filter(ch => KANJI[ch].parts.length >= 2);

function layoutError(ch, placed) {
  const t = KANJI[ch];
  const ref = t.parts.map((el, i) => {
    const b = t.layout[i];
    return { el, x: (b[0] + b[2]) / 2, y: (b[1] + b[3]) / 2, w: b[2] - b[0], h: b[3] - b[1] };
  });
  const used = new Array(placed.length).fill(false);
  let total = 0;
  for (const r of ref) {
    let bi = -1, bd = Infinity;
    placed.forEach((m, i) => {
      if (used[i] || m.el !== r.el) return;
      const d = Math.hypot(m.x - r.x, m.y - r.y)
              + WS * (Math.abs(m.w * m.s - r.w) + Math.abs(m.h * m.s - r.h));
      if (d < bd) { bd = d; bi = i; }
    });
    if (bi < 0) return Infinity;
    used[bi] = true; total += bd;
  }
  return total / ref.length;
}

// いま置いてある配置から、いちばん近い漢字を選ぶ
function judge(placed) {
  const key = placed.map(p => p.el).sort().join("");
  const cands = byKey.get(key);
  if (!cands) return { hit: null, err: Infinity, cands: 0 };
  let best = null, bestErr = Infinity;
  for (const c of cands) {
    const e = layoutError(c, placed);
    if (e < bestErr) { bestErr = e; best = c; }
  }
  return { hit: bestErr <= OK ? best : null, err: bestErr, best, cands: cands.length };
}

// 正解どおりに置いた状態を作る
function perfect(ch) {
  return KANJI[ch].parts.map((el, i) => {
    const b = KANJI[ch].layout[i];
    const n = PARTS[el].box;
    const nw = n[2] - n[0] || 1, nh = n[3] - n[1] || 1;
    return {
      el, x: (b[0] + b[2]) / 2, y: (b[1] + b[3]) / 2, w: nw, h: nh,
      s: ((b[2] - b[0]) / nw + (b[3] - b[1]) / nh) / 2,
    };
  });
}

// 乱数（毎回同じ結果が出るように自前で持つ）
let seed = 12345;
const rnd = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
const jitter = (p, r) => p.map(m => ({ ...m, x: m.x + (rnd() * 2 - 1) * r, y: m.y + (rnd() * 2 - 1) * r }));

console.log(`── 判定の検証  閾値=${OK}  大きさの係数=${WS} ──`);
console.log(`   組み立てられる字 ${buildable.length} / ${Object.keys(KANJI).length}`);

// ① 正解の配置をそのまま入れて、必ず当たること
let pass = 0, wrong = [], errs = [];
for (const ch of buildable) {
  const r = judge(perfect(ch));
  errs.push(r.err);
  if (r.hit === ch) pass++;
  else wrong.push([ch, r.err.toFixed(1), r.hit ?? "—"]);
}
errs.sort((a, b) => a - b);
const pct = q => errs[Math.floor(errs.length * q)].toFixed(1);
console.log(`\n① 正解どおりに置く  ${pass}/${buildable.length} (${(100 * pass / buildable.length).toFixed(1)}%)`);
console.log(`   誤差の分布  中央値 ${pct(.5)}  上位25% ${pct(.75)}  上位10% ${pct(.9)}  上位1% ${pct(.99)}  最大 ${errs[errs.length - 1].toFixed(1)}`);
if (wrong.length) {
  console.log(`   通らなかった字 ${wrong.length}（誤差の大きい順に20）`);
  wrong.sort((a, b) => b[1] - a[1]).slice(0, 20)
    .forEach(([c, e, h]) => console.log(`     ${c}  誤差${e}  → ${h}`));
}

// ② ずらしたときの通過率
console.log("\n② ずらしたときに通る割合（仕様書の期待値: ±8→70%以上 / ±18→20%以下）");
for (const r of [5, 8, 12, 18, 25]) {
  let ok = 0;
  for (const ch of buildable) if (judge(jitter(perfect(ch), r)).hit === ch) ok++;
  const exp = r === 8 ? "  期待 70%以上" : r === 18 ? "  期待 20%以下" : "";
  console.log(`   ±${String(r).padStart(2)}  ${(100 * ok / buildable.length).toFixed(1).padStart(5)}%${exp}`);
}

// ③ でたらめに置く（仕様書の期待値: 1%以下）
let acc = 0, tries = 0;
for (const ch of buildable) {
  const p = perfect(ch).map(m => ({ ...m, x: 15 + rnd() * 79, y: 15 + rnd() * 79, s: 0.35 + rnd() * 0.65 }));
  tries++;
  if (judge(p).hit) acc++;
}
console.log(`\n③ でたらめに置く  ${(100 * acc / tries).toFixed(2)}% しか通らない  期待 1%以下`);

// ④ 部品が同じでぶつかる組の取り違え
const clashes = [...byKey.values()].filter(g => g.length > 1);
console.log(`\n④ 部品がぶつかる ${clashes.length}組の取り違え`);
let mis = 0, tot = 0;
for (const g of clashes) {
  const res = g.map(ch => { const r = judge(perfect(ch)); tot++; if (r.hit !== ch) mis++; return `${ch}→${r.hit ?? "×"}`; });
  console.log(`   ${g.join("/")}  ${res.join("  ")}`);
}
console.log(`   取り違え ${mis}/${tot}  期待 0`);
