"""Generated cat names, from a character-level Markov chain.

Trained on 4,959 real cat names from Seattle's pet license register. Order-3
because order-2 produces mush and order-4 mostly memorizes the corpus, which
defeats the point: the fun is in names that ALMOST exist.

A generated name is rejected if it appears in the training data, so every cat
gets something genuinely new rather than a name someone in Seattle already used.
"""

import json
import random
from pathlib import Path

MODEL = Path(__file__).parent.parent / "data" / "catnames.json"

_model: dict | None = None
_known: set[str] = set()


def _load() -> dict:
    global _model, _known
    if _model is None:
        _model = json.loads(MODEL.read_text())
        _known = set(_model.get("known", []))
    return _model


def legendary(rare: str, seed: int | None = None) -> str | None:
    """A real, absurd name for a rare coat.

    The Markov chain invents plausible names, which is the wrong register for
    a 1-in-1,200 cat. Seattle's register already contains better ones than any
    model would produce, so the rare tiers draw from those instead. Cosmic is
    always Beauregard Brown Baddest Cat in Town.
    """
    pool = _load().get("legendary", {}).get(rare or "")
    if not pool:
        return None
    return pool[random.Random(seed).randrange(len(pool))]


def generate(seed: int | None = None, tries: int = 60) -> str:
    """One name. Pass a seed to make it stable for a given cat."""
    model = _load()
    order, chain = model["order"], model["chain"]
    rng = random.Random(seed)

    for _ in range(tries):
        state = "^" * order
        out = []
        while len(out) < 12:
            options = chain.get(state)
            if not options:
                break
            chars = list(options)
            char = rng.choices(chars, weights=[options[c] for c in chars])[0]
            if char == "$":
                break
            out.append(char)
            state = (state + char)[-order:]

        name = "".join(out)
        if 3 <= len(name) <= 11 and name not in _known:
            return name.capitalize()

    # Every try collided or came out malformed, which the length bounds make
    # unlikely. Better a real name than an empty string.
    return "Mittens"


def for_cat(text: str, rare: str | None = None, seed: int | None = None) -> str:
    """The name a cat gets: legendary if its coat is rare, generated otherwise."""
    if rare:
        found = legendary(rare, seed)
        if found:
            return found
    return generate(seed)


def sample(n: int = 20, seed: int | None = None) -> list[str]:
    rng = random.Random(seed)
    return [generate(rng.randrange(2**31)) for _ in range(n)]
