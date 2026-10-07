import { coatForPosition, drawCat, hash } from "/cat.js";

const $ = (id) => document.getElementById(id);
const esc = (s) => (s ?? "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

let data = {};
let docsData = { docs: [] };
let mailData = { waiting: [] };
let histData = null;

const timeOf = (iso) => (iso && iso.includes("T") ? iso.slice(11, 16) : "");

async function refresh() {
  try {
    data = await (await fetch("/api/state")).json();
  } catch {
    $("sub").textContent = "backend unreachable";
    return;
  }
  $("date").textContent = data.date || "";
  $("clock").textContent = data.time || "";
  render();
}

async function loadHistory() {
  try {
    histData = await (await fetch("/api/history")).json();
    renderHistory();
  } catch { /* panel just stays empty */ }
}

async function loadMail() {
  try {
    mailData = await (await fetch("/api/mail")).json();
    renderMail();
  } catch { /* panel just stays empty */ }
}

async function loadDocs() {
  try {
    docsData = await (await fetch("/api/docs")).json();
    renderDocs();
  } catch { /* panel just stays empty */ }
}

function render() {
  renderTiles();
  renderPile();
  renderTimeline();
  renderTasks();
  renderDone();
  }

// ---------- tiles ----------

function renderTiles() {
  const t = data.tasks || {};
  const c = data.calendar || {};
  const cats = data.herd?.today || [];
  const done = cats.length;
  const due = (t.due_today || []).length;
  const overdue = (t.overdue || []).length;

  const now = new Date();
  const remaining = (c.events || []).filter((e) => e.end && new Date(e.end) > now);
  const mins = remaining.reduce((sum, e) => {
    const start = new Date(Math.max(new Date(e.start), now));
    return sum + Math.max(0, (new Date(e.end) - start) / 60000);
  }, 0);

  $("sub").textContent = [
    `${done} done`,
    due ? `${due} due` : null,
    overdue ? `${overdue} overdue` : null,
  ].filter(Boolean).join(" · ");

  $("tiles").innerHTML = [
    tile(done, done === 1 ? "cat today" : "cats today", "green"),
    tile(due + overdue, "still to do", overdue ? "orange" : ""),
    tile(remaining.length, remaining.length === 1 ? "meeting left" : "meetings left", ""),
    tile(mins >= 60 ? `${(mins / 60).toFixed(1)}h` : `${Math.round(mins)}m`, "booked ahead", ""),
  ].join("");
}

const tile = (value, label, tone) => `<div class="tile ${tone}">
  <div class="tv">${esc(String(value))}</div><div class="tl">${esc(label)}</div></div>`;

// ---------- pile ----------

const CAT_SIZE = 52;

// Traits worth naming on hover, with the odds each one fires at. Read from
// the stored cat rather than recomputed, so the tooltip cannot drift from the
// picture the way a second seed calculation would.
//
// whiskers is deliberately absent: it fires 2 in 3, so it is the default
// rather than a feature. Anything listed here is at most 1 in 4.
const NOTABLE = [
  ["pixel", "pixel"],           // 1 in 40
  ["accessories", "accessorized"], // 1 in 9
  ["bigEars", "big ears"],      // 1 in 7
  ["bigEyes", "big eyes"],      // 1 in 6
  ["droop", "droopy"],          // 1 in 5
  ["tabby", "tabby"],           // 1 in 5
];

function rareTraits(cat) {
  const out = NOTABLE.filter(([key]) => cat[key]).map(([, label]) => label);
  // head is a string rather than a boolean, and only one of its two values
  // is the uncommon one.
  if (cat.head === "triangular") out.push("triangular head"); // 1 in 4
  return out;
}

// ---- rare cat celebration ------------------------------------------------
// Gold is excluded on purpose: every tenth cat is gold, so it lands several
// times a day and a celebration that frequent stops being one.
const CELEBRATE = {
  rose: { glow: "255,158,196", label: "Rose quartz cat", odds: "1 in 85" },
  emerald: { glow: "31,217,140", label: "Emerald cat", odds: "1 in 340" },
  cosmic: { glow: "181,123,255", label: "Cosmic cat", odds: "1 in 1200" },
};

// Which cats have already been celebrated, keyed by the work they were earned
// for. Persisted so a refresh or a reopened tab does not replay the whole
// day's rare cats every time the page loads.
const SEEN_KEY = "hc-celebrated";
const seenRare = new Set(JSON.parse(localStorage.getItem(SEEN_KEY) || "[]"));
const markSeen = (key) => {
  seenRare.add(key);
  localStorage.setItem(SEEN_KEY, JSON.stringify([...seenRare]));
};

let muted = localStorage.getItem("hc-muted") === "1";

function chime(tier) {
  if (muted) return;
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!Ctx) return;
  try {
    const ctx = new Ctx();
    // An arpeggio rather than one tone, so it reads as a fanfare. Cosmic gets
    // a longer, higher run than the other two.
    const notes = tier === "cosmic"
      ? [523.25, 659.25, 783.99, 1046.5, 1318.5]
      : [523.25, 659.25, 783.99, 1046.5];
    notes.forEach((freq, i) => {
      const at = ctx.currentTime + i * 0.09;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "triangle";
      osc.frequency.value = freq;
      // Ramp rather than a hard stop, or each note ends in an audible click.
      gain.gain.setValueAtTime(0.0001, at);
      gain.gain.exponentialRampToValueAtTime(0.22, at + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.42);
      osc.connect(gain).connect(ctx.destination);
      osc.start(at);
      osc.stop(at + 0.45);
    });
    setTimeout(() => ctx.close(), 1600);
  } catch {
    // Audio is decoration. A blocked autoplay policy must not take the
    // fireworks down with it.
  }
}

function celebrate(cat, tier) {
  const spec = CELEBRATE[tier];
  if (!spec) return;

  const layer = document.createElement("div");
  layer.className = "fw";
  layer.style.setProperty("--glow", spec.glow);
  // Three staggered bursts read as fireworks; one reads as a popped balloon.
  for (let burst = 0; burst < 3; burst++) {
    const ox = 25 + Math.random() * 50;
    const oy = 25 + Math.random() * 30;
    setTimeout(() => {
      for (let i = 0; i < 26; i++) {
        const p = document.createElement("i");
        p.className = "fw-p";
        const angle = (Math.PI * 2 * i) / 26 + Math.random() * 0.2;
        const dist = 70 + Math.random() * 130;
        p.style.left = `${ox}%`;
        p.style.top = `${oy}%`;
        p.style.setProperty("--dx", `${Math.cos(angle) * dist}px`);
        p.style.setProperty("--dy", `${Math.sin(angle) * dist + 60}px`);
        p.style.setProperty("--dur", `${1200 + Math.random() * 500}ms`);
        layer.appendChild(p);
      }
    }, burst * 260);
  }
  document.body.appendChild(layer);

  const banner = document.createElement("div");
  banner.className = "fw-banner";
  banner.style.setProperty("--glow", spec.glow);
  banner.innerHTML =
    `<b>${esc(spec.label)}</b><span>${esc(cat.name || "")} · ${spec.odds}</span>`;
  document.body.appendChild(banner);

  chime(tier);
  setTimeout(() => { layer.remove(); banner.remove(); }, 2800);
}

function renderPile() {
  const list = data.herd?.today || [];
  $("pile-total").textContent = `${data.herd?.total ?? 0} all time`;
  $("pilec").textContent = list.length
    ? `${list.length} today`
    : "Nothing yet. Finish something.";

  const pile = $("pile");
  pile.innerHTML = "";
  if (!list.length) return;

  const PER_ROW = Math.max(4, Math.floor((pile.clientWidth || 520) / 42));
  const pending = [];
  const indexed = list.map((c, position) => ({ ...c, position }));
  const rows = [];
  for (let end = indexed.length; end > 0; end -= PER_ROW) {
    rows.push(indexed.slice(Math.max(0, end - PER_ROW), end));
  }

  for (const [r, row] of rows.entries()) {
    const el = document.createElement("div");
    el.className = "prow";
    el.style.setProperty("--inset", `${Math.min(r * 3, 12)}px`);
    for (const c of row) {
      const seed = hash(c.for);
      const coat = coatForPosition(c.position, seed);
      const wrap = document.createElement("span");
      wrap.className = coat.rare ? `pcat rare rare-${coat.rare}` : "pcat";
      wrap.style.setProperty("--tilt", `${(seed % 15) - 7}deg`);
      wrap.style.setProperty("--lift", `${seed % 6}px`);
      // Name, plus anything about this cat that is actually uncommon. The
      // work it was earned for is already listed above the pile, so
      // repeating it on hover just made the tooltip long. Common traits stay
      // unnamed so the words that do appear always mean "this one is odd".
      wrap.title = [c.name, coat.rare && coat.name, ...rareTraits(c)]
        .filter(Boolean)
        .join(" · ");
      // Queue rather than fire here: renderPile runs inside a loop that is
      // still building the DOM, and a celebration per cat would stack.
      if (CELEBRATE[coat.rare] && !seenRare.has(c.for)) {
        markSeen(c.for);
        pending.push([c, coat.rare]);
      }
      const canvas = drawCat(CAT_SIZE, seed + r, coat);
      if (canvas) {
        canvas.style.width = `${CAT_SIZE}px`;
        canvas.style.height = `${CAT_SIZE}px`;
        // Without this the canvas eats the hover and the wrapper's title,
        // which carries the cat's name, never shows.
        canvas.style.pointerEvents = "none";
        wrap.appendChild(canvas);
      }
      if (coat.rare) {
        for (let s = 0; s < 4; s++) {
          const spark = document.createElement("i");
          spark.className = "spark";
          spark.style.setProperty("--i", s);
          wrap.appendChild(spark);
        }
      }
      el.appendChild(wrap);
    }
    pile.appendChild(el);
  }

  // One at a time, spaced out. Two rare cats landing in the same refresh is
  // vanishingly unlikely, but overlapping fireworks would look like a bug.
  pending.forEach(([cat, tier], i) => {
    setTimeout(() => celebrate(cat, tier), i * 3200);
  });
}

// ---------- timeline ----------

function renderTimeline() {
  const c = data.calendar || {};
  const events = c.events || [];
  $("day-cc").textContent = c.now ? "in a meeting" : `${events.length} events`;

  if (!events.length) {
    $("timeline").innerHTML = '<div class="empty">Nothing on the calendar.</div>';
    return;
  }

  const rows = events.map((e) => `
    <div class="ev ${e.live ? "live" : e.past ? "past" : ""}">
      <span class="evt">${timeOf(e.start)}</span>
      <span class="evn">${esc(e.summary)}</span>
      ${e.live ? '<span class="evnow">now</span>' : ""}
    </div>`).join("");

  const collisions = (c.collisions || []).map((x) => `
    <div class="warn">${esc(x.a)} overlaps ${esc(x.b)} at ${esc(x.at)}</div>`).join("");

  $("timeline").innerHTML = rows + collisions;
}

// ---------- tasks ----------

function renderTasks() {
  const t = data.tasks || {};
  const picked = t.picked || [];
  const overdue = t.overdue || [];
  const due = t.due_today || [];
  const undated = t.undated || [];
  $("task-cc").textContent = `${picked.length + overdue.length + due.length} active`;

  const row = (task, late) => `<div class="row${task.picked ? " picked" : ""}">
    <button class="cb" data-done="${esc(task.id)}" title="Complete" aria-label="Complete"></button>
    <button class="star${task.picked ? " on" : ""}" data-pick="${esc(task.id)}"
      title="${task.picked ? "Not today" : "Do this today"}" aria-label="Pick for today">★</button>
    <span class="rt">${esc(task.title)}</span>
    ${late ? '<span class="pill">late</span>' : ""}
    <button class="note" data-note="${esc(task.title)}" title="Leave a note for Claude"
      aria-label="Leave a note">✎</button>
  </div>`;

  const parts = [];
  if (picked.length) {
    parts.push('<div class="sublab today">Today</div>',
      picked.map((x) => row(x, false)).join(""));
  }
  if (overdue.length || due.length) {
    if (picked.length) parts.push('<div class="sublab">Due</div>');
    parts.push(overdue.map((x) => row(x, true)).join(""));
    parts.push(due.map((x) => row(x, false)).join(""));
  }
  if (!parts.length) parts.push('<div class="empty">Nothing due today.</div>');
  if (undated.length) {
    parts.push(`<div class="sublab">No date (${undated.length})</div>`,
      undated.slice(0, 8).map((x) => row(x, false)).join(""));
  }
  $("tasks").innerHTML = parts.join("");
}

// ---------- done ----------

function renderDone() {
  const cats = data.herd?.today || [];
  const doneTasks = data.tasks?.done_today || [];
  $("done-cc").textContent = `${cats.length} today`;
  // Match a cat back to the task that earned it, so undo can reopen the task
  // rather than only removing the cat.
  const idFor = (label) => doneTasks.find((d) => d.title === label)?.id || "";

  // Newest first by clock time. Insertion order alone put a just-finished
  // item below older ones, which made a completion look like it never landed.
  const ordered = [...cats].sort((a, b) => (b.at || "").localeCompare(a.at || ""));

  $("done").innerHTML = cats.length
    ? ordered.map((c) => `<div class="doneitem">
        <span class="tick">✓</span><span class="dt">${esc(c.for)}${
          c.name ? `<span class="cname">${esc(c.name)}</span>` : ""}</span>
        ${c.at ? `<span class="dtime">${esc(c.at)}</span>` : ""}
        <button class="undo" data-undo="${esc(idFor(c.for))}"
          data-title="${esc(c.for)}" title="Undo" aria-label="Undo">↩</button>
      </div>`).join("")
    : '<div class="empty">Nothing logged yet.</div>';
}

// ---------- history ----------

function renderHistory() {
  const h = histData;
  if (!h) return;
  $("hist-cc").textContent = `${h.total} all time · see the herd →`;

  const max = Math.max(1, h.best);
  const rows = h.days.slice(0, 7).map((d) => {
    const label = new Date(d.day + "T12:00:00").toLocaleDateString("en-US",
      { weekday: "short", month: "short", day: "numeric" });
    const pct = Math.round((d.count / max) * 100);
    return `<div class="hrow">
      <span class="hday">${esc(label)}</span>
      <span class="hbar"><i style="width:${pct}%"></i></span>
      <span class="hn">${d.count}${d.rare ? `<b> ${d.rare}◆</b>` : ""}</span>
    </div>`;
  }).join("");

  const rares = Object.entries(h.rares || {});
  const rareLine = rares.length
    ? `<div class="hrare">${rares.map(([k, v]) =>
        `<span class="rtag ${esc(k)}">◆ ${esc(k)} ${v}</span>`).join("")}</div>`
    : "";

  $("history").innerHTML = rows + `<div class="hstat">best ${h.best} · avg ${h.average}
    · ${h.streak} day streak</div>` + rareLine;
}

// ---------- mail ----------

function renderMail() {
  const list = mailData.waiting || [];
  $("mail-cc").textContent = list.length ? `${list.length} to answer` : "clear";
  if (!list.length) {
    $("mail").innerHTML = '<div class="empty">Nothing waiting on a reply.</div>';
    return;
  }
  $("mail").innerHTML = list.map((m) => `<div class="mailrow">
    <div class="mh">
      <span class="mfrom">${esc(m.from)}</span>
      <span class="mwhen">${esc(m.when)}</span>
      <button class="maildone" data-archive="${esc(m.id)}" title="Archive and mark read">done</button>
    </div>
    <div class="msub"><a href="#" data-open="${esc(m.url)}">${esc(m.subject)}</a></div>
    <div class="msnip">${esc(m.snippet)}</div>
  </div>`).join("");
}

// ---------- documents ----------

function renderDocs() {
  const list = docsData.docs || [];
  $("docs-cc").textContent = `${docsData.total ?? list.length} in ${docsData.days ?? 7} days`;
  if (!list.length) {
    $("docs").innerHTML = '<div class="empty">No documents touched recently.</div>';
    return;
  }
  $("docs").innerHTML = `<div class="docgrid">${list.slice(0, 18).map((d) => `
    <div class="doc">
      <span class="dn"><a href="#" data-open="${esc(d.url || d.path)}"
        title="${esc(d.dir || d.path)}">${esc(d.name)}</a></span>
      <span class="dp">${d.kind === "notion" ? "notion" : esc(d.project)}</span>
      <span class="de">${d.edits}x</span>
      <span class="dw">${esc(d.when)}</span>
    </div>`).join("")}</div>`;
}

// ---------- events ----------

$("refresh").onclick = async () => {
  const btn = $("refresh");
  btn.classList.remove("spin");
  void btn.offsetWidth;
  btn.classList.add("spin");
  await Promise.all([refresh(), loadDocs(), loadMail(), loadHistory()]);
};

// Links go to the real default browser rather than the app's isolated Chrome
// profile, which is signed into nothing.
document.addEventListener("click", (e) => {
  const done = e.target.closest("button[data-archive]");
  if (done) {
    e.preventDefault();
    const id = done.dataset.archive;
    done.disabled = true;
    fetch("/api/mail/archive", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ id }),
    }).then((r) => r.json()).then((res) => {
      if (res.ok) {
        mailData.waiting = (mailData.waiting || []).filter((m) => m.id !== id);
        renderMail();
      } else {
        done.disabled = false;
      }
    });
    return;
  }
  const a = e.target.closest("a[data-open], a[href^='http']");
  if (e.target.closest("a[data-open-page]")) return;
  if (!a) return;
  e.preventDefault();
  const target = a.dataset.open || a.href;
  fetch("/api/open", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ url: target }),
  }).then((r) => {
    if (!r.ok) a.classList.add("deadlink");
  });
});

const post = (url, body) => fetch(url, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify(body || {}),
});

// Completing needs a second click to confirm. A single stray click used to
// complete a task in Google Tasks with no way back from the UI.
let arming = null;
const disarm = () => {
  if (!arming) return;
  arming.el.classList.remove("arm");
  clearTimeout(arming.timer);
  arming = null;
};

document.addEventListener("click", async (e) => {
  const el = e.target;

  const doneId = el.dataset?.done;
  if (doneId) {
    const title = el.parentElement?.querySelector(".rt")?.textContent?.trim() || "a task";
    if (arming?.id !== doneId) {
      disarm();
      el.classList.add("arm");
      arming = { id: doneId, el, timer: setTimeout(disarm, 3000) };
      return;
    }
    disarm();
    el.classList.add("on");
    await post(`/api/task/${doneId}/complete`, { title });
    setTimeout(refresh, 700);
    return;
  }
  disarm();

  const pickId = el.dataset?.pick;
  if (pickId) {
    el.classList.toggle("on");
    await post(`/api/task/${pickId}/pick`);
    refresh();
    return;
  }

  const undoId = el.dataset?.undo;
  if (undoId !== undefined && el.classList.contains("undo")) {
    const title = el.dataset.title || "";
    // "none" when the cat came from the day file and has no task behind it.
    await post(`/api/task/${undoId || "none"}/uncomplete`, { title });
    refresh();
    return;
  }

  const noteFor = el.dataset?.note;
  if (noteFor !== undefined && el.classList.contains("note")) {
    const text = prompt(`Note for Claude about "${noteFor}":`);
    if (text && text.trim()) {
      await post("/api/note", { text: text.trim(), about: noteFor });
      el.classList.add("noted");
    }
    return;
  }
});

document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === "r") { e.preventDefault(); $("refresh").click(); }
});

const paintMute = () => {
  const b = $("mute");
  if (!b) return;
  b.textContent = muted ? "🔇" : "🔊";
  b.title = muted ? "Rare cat sound is off" : "Rare cat sound is on";
};
$("mute")?.addEventListener("click", () => {
  muted = !muted;
  localStorage.setItem("hc-muted", muted ? "1" : "0");
  paintMute();
  // Play on unmute so the toggle proves itself, rather than leaving her to
  // wait for a 1-in-85 cat to find out whether it worked.
  if (!muted) chime("rose");
});
paintMute();

$("log-done")?.addEventListener("click", async () => {
  const text = prompt("What did you finish?");
  if (!text || !text.trim()) return;
  await post("/api/done", { text: text.trim() });
  $("refresh").click();
});

$("add-task")?.addEventListener("click", async () => {
  const title = prompt("What needs doing?");
  if (!title || !title.trim()) return;
  await post("/api/task", { title: title.trim() });
  $("refresh").click();
});


refresh();
loadDocs();
loadMail();
loadHistory();
setInterval(refresh, 60000);
setInterval(loadDocs, 300000);
// Mail shells out per thread, so it rides the slow timer, not the 60s one.
setInterval(loadMail, 300000);
setInterval(loadHistory, 300000);
