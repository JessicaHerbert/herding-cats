"""Coat assignment, ported from web/cat.js.

The coat used to be computed in the browser at render time and never stored,
so a cosmic cat left no record that it happened. Worse, it was only stable as
long as the tables never changed: adding a coat or retuning the odds would
silently repaint every cat that had ever been earned.

Rolling here and storing the result means a rare cat stays rare in the record.
The arithmetic mirrors cat.js exactly so backfilled cats keep the coat they
were actually shown with.
"""

COATS = [
    {"name": "ginger", "coat": "#FFA24C", "eye": "#0B1420"},
    {"name": "cyan", "coat": "#02E3FB", "eye": "#0B1420"},
    {"name": "lilac", "coat": "#8041D0", "eye": "#55F7A9"},
    {"name": "mint", "coat": "#55F7A9", "eye": "#0B1420"},
    {"name": "slate", "coat": "#8496AA", "eye": "#01A4FF"},
    {"name": "blue", "coat": "#01A4FF", "eye": "#0B1420"},
    {"name": "void", "coat": "#2A3344", "eye": "#55F7A9"},
    {"name": "cream", "coat": "#EBD9B4", "eye": "#01A4FF"},
]

GOLD = {"name": "gold", "coat": "#FFC94C", "eye": "#5B3A00", "rare": "gold"}

SPECIALS = [
    {"name": "rose quartz", "coat": "#FF9EC4", "eye": "#7A1F4B", "rare": "rose", "odds": 85},
    {"name": "emerald", "coat": "#1FD98C", "eye": "#04331F", "rare": "emerald", "odds": 340},
    {"name": "cosmic", "coat": "#B57BFF", "eye": "#FFE86B", "rare": "cosmic", "odds": 1200},
]

MIX = [0x9E3779B9, 0x85EBCA6B, 0xC2B2AE35]

_U32 = 0xFFFFFFFF


def _imul(a: int, b: int) -> int:
    """JavaScript Math.imul: 32-bit signed multiply."""
    r = (a * b) & _U32
    return r - 0x100000000 if r >= 0x80000000 else r


def hash_text(text: str) -> int:
    """FNV-1a as cat.js computes it, including its 32-bit wrap and abs."""
    h = 2166136261
    for ch in text or "":
        h ^= ord(ch)
        h = _imul(h, 16777619) & _U32
    return abs(h - 0x100000000 if h >= 0x80000000 else h)


def _roll_special(seed: int) -> dict | None:
    # Rarest first: checking common-first lets a 1-in-85 tier swallow seeds
    # that also satisfy the rarer tiers, so those would never fire.
    for i in range(len(SPECIALS) - 1, -1, -1):
        s = SPECIALS[i]
        mixed = abs(_imul(seed ^ MIX[i], 2654435761))
        if mixed % s["odds"] == 0:
            return s
    return None


def traits_for(text: str) -> dict:
    """Every visible trait a cat carries, stored rather than recomputed.

    Colour alone made every cat read as the same animal in a different shade.
    The generator already varies head shape, ears, eyes, and stripes; these
    just pick from its own documented ranges so the differences are legible
    and countable.

    Each trait takes its own slice of the seed, so they vary independently
    rather than all flipping together.
    """
    seed = hash_text(text)
    return {
        "whiskers": seed % 3 != 0,
        "accessories": seed % 9 == 0,
        # HEAD_SHAPES in cat-snacks is exactly ['ellipse', 'triangular'].
        "head": "triangular" if (seed // 7) % 4 == 0 else "ellipse",
        "droop": (seed // 11) % 5 == 0,
        "bigEyes": (seed // 13) % 6 == 0,
        # earFactor ranges 0.9-1.15 upstream; 1.15 is the visible end of it.
        "bigEars": (seed // 17) % 7 == 0,
        # tabbyFactor ranges 0.9-1.2.
        "tabby": (seed // 19) % 5 == 0,
        # The rarest of the shape traits, and the most visually distinct.
        "pixel": (seed // 23) % 40 == 0,
    }


def for_position(position: int, text: str) -> dict:
    """The coat for the Nth cat of a day, earned for `text`."""
    if (position + 1) % 10 == 0:
        return dict(GOLD)
    seed = hash_text(text)
    special = _roll_special(seed)
    if special:
        return {k: v for k, v in special.items() if k != "odds"}
    return dict(COATS[abs(seed) % len(COATS)])
