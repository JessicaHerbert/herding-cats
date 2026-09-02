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
// Seeds chosen so each example actually carries the trait it illustrates:
// whiskers is seed % 3 !== 0 and accessories is seed % 9 === 0.
$("traits").innerHTML = [
  ["whiskers", tr.whiskers || 0, 1],
  ["glasses or hat", tr.accessories || 0, 9],
].map(([name, n, seed]) => `<div class="swatch big">
  <span class="catslot" data-seed="${seed}"></span>
  <span class="sbody">
    <span class="sname">${esc(name)}</span>
    <span class="srate">${pct(n, h.total)} of all cats</span>
  </span>
  <span class="scount">${n}</span>
</div>`).join("");

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
