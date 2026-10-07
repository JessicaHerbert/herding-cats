import { COATS, GOLD, SPECIALS, drawCat, hash } from "/cat.js";

const $ = (id) => document.getElementById(id);
const esc = (s) => (s ?? "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const BY_NAME = {};
for (const c of [...COATS, GOLD, ...SPECIALS]) BY_NAME[c.name] = c;
const SWATCH = Object.fromEntries(Object.entries(BY_NAME).map(([k, v]) => [k, v.coat]));

// One drawn cat per coat, at a fixed seed, so the swatch shows the actual
// animal rather than a color dot. Fixed seed keeps the reference image stable
// while the real cats in each day keep their own.
function catFor(coatName, seed, size) {
  const coat = BY_NAME[coatName];
  if (!coat) return null;
  const canvas = drawCat(size, seed, coat);
  if (canvas) {
    canvas.style.width = `${size}px`;
    canvas.style.height = `${size}px`;
    canvas.style.pointerEvents = "none";
  }
  return canvas;
}

function mount(el, canvas) {
  if (el && canvas) el.replaceChildren(canvas);
}

const pct = (n, total) => total ? `${((n / total) * 100).toFixed(1)}%` : "0%";
const tile = (v, l, tone = "") =>
  `<div class="tile ${tone}"><div class="tv">${esc(String(v))}</div>
   <div class="tl">${esc(l)}</div></div>`;

const h = await (await fetch("/api/history")).json();

$("sub").textContent =
  `${h.days_kept} days on record · ${h.streak} day streak · best ${h.best}`;

const rareTotal = Object.values(h.rares || {}).reduce((a, b) => a + b, 0);
$("tiles").innerHTML = [
  tile(h.total, "cats all time", "green"),
  tile(h.best, "best day", ""),
  tile(h.average, "average day", ""),
  tile(rareTotal, rareTotal === 1 ? "rare coat" : "rare coats", rareTotal ? "orange" : ""),
].join("");

// Every coat that exists, including the ones never seen, so the collection
// shows what is still missing rather than only what has turned up.
const allCoats = [...COATS.map((c) => c.name), GOLD.name, ...SPECIALS.map((s) => s.name)];
const seen = h.coats || {};
$("coat-cc").textContent =
  `${allCoats.filter((n) => seen[n]).length} of ${allCoats.length} collected`;
$("coats").innerHTML = allCoats.map((name) => {
  const n = seen[name] || 0;
  return `<div class="swatch big" style="${n ? "" : "opacity:.35"}">
    <span class="catslot" data-coat="${esc(name)}"></span>
    <span class="sbody">
      <span class="sname">${esc(name)}</span>
      <span class="srate">${n ? pct(n, h.total) : "none yet"}</span>
    </span>
    <span class="scount">${n}</span>
  </div>`;
}).join("");

for (const slot of document.querySelectorAll("#days .dcat")) {
  mount(slot, catFor(slot.dataset.coat, Number(slot.dataset.seed), 44));
}

for (const slot of document.querySelectorAll("#coats .catslot")) {
  mount(slot, catFor(slot.dataset.coat, 20260902, 46));
}

const tr = h.traits || {};
// Seeds chosen so each example visibly carries the trait it illustrates.
const TRAITS = [
  ["whiskers", "whiskers", 1],
  ["accessories", "glasses or hat", 9],
  ["head", "pointed head", 7],
  ["droop", "droopy ears", 11],
  ["bigEyes", "big eyes", 13],
  ["bigEars", "big ears", 17],
  ["tabby", "heavy stripes", 19],
  ["pixel", "pixelated", 23],
];
$("traits").innerHTML = TRAITS.map(([key, label, seed]) => {
  const n = tr[key] || 0;
  return `<div class="swatch big" style="${n ? "" : "opacity:.4"}">
    <span class="catslot" data-seed="${seed}"></span>
    <span class="sbody">
      <span class="sname">${esc(label)}</span>
      <span class="srate">${n ? pct(n, h.total) + " of all cats" : "none yet"}</span>
    </span>
    <span class="scount">${n}</span>
  </div>`;
}).join("");

for (const slot of document.querySelectorAll("#traits .catslot")) {
  mount(slot, catFor("ginger", Number(slot.dataset.seed), 46));
}

$("days-cc").textContent = `${h.days.length} shown`;
$("days").innerHTML = h.days.map((d) => {
  const label = new Date(d.day + "T12:00:00").toLocaleDateString("en-US",
    { weekday: "long", month: "long", day: "numeric" });
  const chips = d.cats.map((c) => `<span class="dcatwrap"
      title="${esc(c.name || "")} · ${esc(c.for)}${c.at ? " · " + c.at : ""} · ${
        esc(c.coat || c.breed)}${c.accessories ? " · accessorized" : ""}">
      <span class="dcat ${c.rare ? "rare" : ""}"
        data-coat="${esc(c.coat || "")}" data-seed="${hash(c.for)}"></span>
      <span class="dname">${esc(c.name || "")}</span>
    </span>`).join("");
  return `<div class="dayblock">
    <div class="dayhead"><span class="dayname">${esc(label)}</span>
      <span class="daymeta">${d.count} cats${d.rare ? ` · ${d.rare} rare` : ""}</span></div>
    <div class="daycats">${chips}</div>
  </div>`;
}).join("");

for (const slot of document.querySelectorAll("#days .dcat")) {
  mount(slot, catFor(slot.dataset.coat, Number(slot.dataset.seed), 44));
}

// --- Tabs -----------------------------------------------------------------
// All four views were stacked on one long page. Tabs split them without
// changing what each one renders, and the counter tiles stay above the tabs
// because they are the at-a-glance numbers rather than a view of their own.
//
// Everything is already in the DOM by the time this runs, so switching is a
// hidden toggle rather than a re-render. That keeps the drawn cats, which are
// canvases mounted once and would have to be redrawn on every tab change.

const TABS = [...document.querySelectorAll("#tabs .tab")];
const REMEMBER = "herd-tab";

function showTab(name) {
  const known = TABS.some((t) => t.dataset.tab === name);
  const target = known ? name : "herd";
  for (const t of TABS) {
    t.setAttribute("aria-selected", String(t.dataset.tab === target));
  }
  for (const p of document.querySelectorAll("[data-panel]")) {
    p.hidden = p.id !== `panel-${target}`;
  }
  try { localStorage.setItem(REMEMBER, target); } catch { /* private mode */ }
}

for (const t of TABS) {
  t.addEventListener("click", () => showTab(t.dataset.tab));
}

// Reopen on whichever tab was last used. Landing back on the herd every time
// is the kind of small friction that stops the other views being looked at.
let initial = "herd";
try { initial = localStorage.getItem(REMEMBER) || "herd"; } catch { /* ignore */ }
showTab(initial);
