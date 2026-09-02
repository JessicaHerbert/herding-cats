// Cats come from Beau Gunderson's cat-snacks generator, bundled as
// window.CatSnacks. Every cat is procedurally drawn, so no two match.
// https://github.com/beaugunderson/cat-snacks

export const COATS = [
  { name: "ginger", coat: "#FFA24C", eye: "#0B1420" },
  { name: "cyan", coat: "#02E3FB", eye: "#0B1420" },
  { name: "lilac", coat: "#8041D0", eye: "#55F7A9" },
  { name: "mint", coat: "#55F7A9", eye: "#0B1420" },
  { name: "slate", coat: "#8496AA", eye: "#01A4FF" },
  { name: "blue", coat: "#01A4FF", eye: "#0B1420" },
  { name: "void", coat: "#2A3344", eye: "#55F7A9" },
  { name: "cream", coat: "#EBD9B4", eye: "#01A4FF" },
];

export const GOLD = { name: "gold", coat: "#FFC94C", eye: "#5B3A00", rare: "gold" };

// Rolled per cat rather than granted on a schedule, so a rare one can turn up
// at any moment. Odds are deliberately steep enough that a cosmic is a story.
// Tuned against a ~17-cat day: roughly one rose a week, one emerald a month,
// one cosmic a quarter. Loose odds make the guaranteed gold feel unearned.
export const SPECIALS = [
  { name: "rose quartz", coat: "#FF9EC4", eye: "#7A1F4B", rare: "rose", odds: 85 },
  { name: "emerald", coat: "#1FD98C", eye: "#04331F", rare: "emerald", odds: 340 },
  { name: "cosmic", coat: "#B57BFF", eye: "#FFE86B", rare: "cosmic", odds: 1200 },
];

export function coatFor(index) {
  return COATS[Math.abs(index) % COATS.length];
}

// The roll must be a pure function of the cat, or a refresh rerolls it and a
// rare cat you already saw vanishes.
const MIX = [0x9e3779b9, 0x85ebca6b, 0xc2b2ae35];

function rollSpecial(seed) {
  // Rarest first. Checking common-first would let a 1-in-85 tier swallow every
  // seed that also satisfies a 1-in-340 tier, since the odds share factors and
  // the rarer tier would never fire at all.
  for (let i = SPECIALS.length - 1; i >= 0; i--) {
    const s = SPECIALS[i];
    // Each tier re-mixes the seed with its own constant so the tiers are
    // independent draws rather than nested multiples of one another.
    const mixed = Math.abs(Math.imul(seed ^ MIX[i], 2654435761));
    if (mixed % s.odds === 0) return s;
  }
  return null;
}

// Every tenth cat of the day is gold, guaranteed. Anything else can roll a
// rare coat. The guarantee gives a floor; the roll gives a surprise.
export function coatForPosition(position, seed) {
  if ((position + 1) % 10 === 0) return GOLD;
  return rollSpecial(seed) || coatFor(seed);
}

// A seeded hash so the same task always draws the same cat rather than
// rerolling on every refresh.
export function hash(str) {
  let h = 2166136261;
  for (let i = 0; i < (str || "").length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return Math.abs(h);
}

let patched = false;

function patchRandom(seed) {
  // cat-snacks uses Math.random throughout. Swapping in a seeded generator
  // for the duration of one draw makes each cat stable across refreshes.
  const original = Math.random;
  let s = seed || 1;
  Math.random = () => {
    s = (s * 1664525 + 1013904223) % 4294967296;
    return s / 4294967296;
  };
  return () => { Math.random = original; };
}

export function drawCat(size, seed, coat) {
  if (!window.CatSnacks) return null;
  const restore = patchRandom(seed);
  let src;
  try {
    src = window.CatSnacks.cat(size, {
      catColor: coat.coat,
      eyeColor: coat.eye,
      // The generator always paints a background, and "transparent" is not a
      // color it can parse. Painting the sidebar color and knocking it out
      // afterwards is simpler than patching the upstream part.
      backgroundColor: KNOCKOUT,
      whiskers: seed % 3 !== 0,
      accessories: seed % 9 === 0,
      pixelate: false,
    });
  } catch (err) {
    console.warn("cat draw failed", err);
    return null;
  } finally {
    restore();
  }
  return knockout(src);
}

const KNOCKOUT = "#FF00FF";

function knockout(src) {
  // Drop every pixel close to the knockout color so the cat sits on the
  // sidebar rather than in a colored tile.
  const out = document.createElement("canvas");
  out.width = src.width;
  out.height = src.height;
  const ctx = out.getContext("2d");
  ctx.drawImage(src, 0, 0);

  const img = ctx.getImageData(0, 0, out.width, out.height);
  const d = img.data;
  for (let i = 0; i < d.length; i += 4) {
    // magenta-ish: high red, high blue, low green
    if (d[i] > 150 && d[i + 2] > 150 && d[i + 1] < 110) d[i + 3] = 0;
  }
  ctx.putImageData(img, 0, 0);
  return out;
}
