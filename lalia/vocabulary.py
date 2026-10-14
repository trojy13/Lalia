"""Pharmacy and personal vocabulary: prompt words and sound-alike correction.

Whisper writes a brand it does not know the way it hears it, in Greek letters
(«λίπιτορ» for Lipitor), and garbles long substance names («αμοξικιλίνη»). Each
word of the result is compared by sound with the lexicon (the built-in pharmacy
terms plus the user's own words): Greek letters are transliterated, so «λίπιτορ»
and "Lipitor" get the same sound key. Ordinary Greek and English words (from the
wordfreq lists in data/) are never changed.

The prompt can carry only ~223 tokens (a Greek drug name costs ~10), so a long
list cannot go in it. Instead the words that sound like lexicon terms are put in
the prompt of a second reading, when the GPU makes that cheap, and the model
itself checks them against the audio.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz, process

DATA = Path(__file__).with_name("data")
MEDICAL_FILE = DATA / "medical_el.txt"

# Greek with English clauses: tells the model that switching language happens,
# so an English phrase inside Greek speech is written instead of dropped.
MIXED_PROMPT = ("Ο πελάτης ρωτάει if you have it in stock, και θα περάσει αύριο. "
                "Please call the supplier για την παραγγελία.")
# Brand names in Latin letters and units as symbols, the way a pharmacy writes them.
MEDICAL_PROMPT = "Ο ασθενής παίρνει Depon 500 mg και Augmentin 1 g, δύο φορές την ημέρα."
PROMPT_BUDGET = 200  # tokens; faster-whisper keeps only the last 223

LATIN_CUTOFF = 84  # a Latin-letter word is replaced by a term this similar (0-100)
GREEK_CUTOFF = 90  # a Greek-letter word needs more: ordinary words look alike more often
CANDIDATE_CUTOFF = 72  # similar enough to be checked by the second reading

WORD_RE = re.compile(r"[^\W\d_]+(?:[-'][^\W\d_]+)*")


def fold(text: str) -> str:
    """Lower case without accents: the form used for lookups."""
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def is_greek(text: str) -> bool:
    return any("Ͱ" <= c <= "Ͽ" or "ἀ" <= c <= "῿" for c in text)


def load_terms(path: Path) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    return [l.strip() for l in lines if l.strip() and not l.lstrip().startswith("#")]


# --- sound keys ---------------------------------------------------------------
# «ντ» and «μπ» are d and b at the start of a word (Ντεπόν = Depon) but nt and mp
# inside one (Βεντολίν = Ventolin), which is also how the Latin names are spelled.
_GREEK_START = (("ντ", "d"), ("μπ", "b"))
_GREEK_DIGRAPHS = (("ου", "u"), ("αι", "e"), ("ει", "i"), ("οι", "i"), ("υι", "i"), ("αυ", "av"),
                   ("ευ", "ev"), ("μπ", "mp"), ("ντ", "nt"), ("γκ", "g"), ("γγ", "g"), ("γχ", "nch"),
                   ("τσ", "ts"), ("τζ", "tz"))
_GREEK_LETTERS = str.maketrans({
    "α": "a", "β": "v", "γ": "g", "δ": "d", "ε": "e", "ζ": "z", "η": "i", "θ": "th", "ι": "i",
    "κ": "k", "λ": "l", "μ": "m", "ν": "n", "ξ": "x", "ο": "o", "π": "p", "ρ": "r", "σ": "s",
    "ς": "s", "τ": "t", "υ": "i", "φ": "f", "χ": "ch", "ψ": "ps", "ω": "o",
})
_LATIN_RULES = (("ph", "f"), ("ou", "u"), ("eu", "ev"), ("au", "av"), ("ae", "e"), ("oe", "e"),
                ("ee", "i"), ("ck", "k"), ("qu", "kv"), ("w", "v"), ("y", "i"), ("j", "tz"), ("q", "k"))


def _finish(key: str) -> str:
    key = re.sub(r"[^a-z]", "", key)
    key = re.sub(r"(?<![tcps])h", "", key)  # keep th, ch, ph-like pairs, drop a silent h
    return re.sub(r"(.)\1+", r"\1", key)  # double letters sound single


def sound_key(word: str) -> str:
    """Roughly how a word sounds, in Latin letters, whichever alphabet it is in."""
    w = fold(word)
    if is_greek(w):
        for a, b in _GREEK_START:
            if w.startswith(a):
                w = b + w[len(a):]
        for a, b in _GREEK_DIGRAPHS:
            w = w.replace(a, b)
        return _finish(w.translate(_GREEK_LETTERS))
    for a, b in _LATIN_RULES:
        w = w.replace(a, b)
    w = re.sub(r"c(?=[ei])", "s", w).replace("c", "k")
    return _finish(w)


def sound_keys(term: str) -> set[str]:
    """The key, plus how Greek speakers usually say Latin spellings:
    Augmentin as «Ογκμεντίν» (au as o), Glucophage as «Γλουκοφάζ» (final ge as z)."""
    key = sound_key(term)
    keys = {key}
    if not is_greek(term):
        f = fold(term)
        if "au" in f:
            keys.add(sound_key(f.replace("au", "o")))
        if f.endswith("ge"):
            keys.add(sound_key(f[:-2] + "z"))
        if f.endswith("e") and len(f) > 5:
            keys.add(sound_key(f[:-1]))
    return {k for k in keys if k}


@lru_cache(maxsize=1)
def common_words() -> frozenset[str]:
    words = set()
    for name in ("common_el.txt", "common_en.txt"):
        words.update(load_terms(DATA / name))
    return frozenset(words)


# --- the lexicon ------------------------------------------------------------------
@dataclass(frozen=True)
class Term:
    text: str
    greek: bool


class Lexicon:
    def __init__(self, terms: list[str]):
        self._exact: dict[str, Term] = {}
        self._keys: list[str] = []
        self._key_terms: list[Term] = []
        for raw in terms:
            text = " ".join(raw.split())
            f = fold(text)
            if not text or f in self._exact:
                continue
            term = Term(text, is_greek(text))
            self._exact[f] = term
            self._exact.setdefault(f.replace(" ", ""), term)
            for key in sound_keys(text.replace(" ", "")):
                if len(key) >= 4:
                    self._keys.append(key)
                    self._key_terms.append(term)

    def __len__(self) -> int:
        return len({t.text for t in self._exact.values()})

    def _best(self, key: str, cutoff: float):
        if not self._keys:
            return None
        hit = process.extractOne(key, self._keys, scorer=fuzz.ratio, score_cutoff=cutoff)
        return (self._key_terms[hit[2]], hit[1]) if hit else None

    def _lookup(self, word: str, *, candidate: bool):
        """(term, score) for one word or joined word pair, or None."""
        f = fold(word)
        exact = self._exact.get(f)
        if exact:
            if f in common_words() and word.islower() and not exact.text.islower():
                return None  # an ordinary word that is also a brand ("foster", not Foster)
            return exact, 100.0
        if f in common_words():
            return None
        key = sound_key(word)
        if len(key) < 4 or len(f) < 4:
            return None
        greek = is_greek(word)
        cutoff = CANDIDATE_CUTOFF if candidate else (GREEK_CUTOFF if greek else LATIN_CUTOFF)
        hit = self._best(key, cutoff)
        if not hit:
            return None
        term, score = hit
        if greek and not candidate and len(f) < (5 if not term.greek else 6):
            return None  # short Greek words collide too easily
        return term, score

    def candidates(self, text: str, limit: int = 12) -> list[str]:
        """Terms that some word in the text may be: checked by the second reading."""
        scored: dict[str, float] = {}
        words = list(WORD_RE.finditer(text))
        for i, m in enumerate(words):
            spans = [m.group()]
            if i + 1 < len(words) and not text[m.end():words[i + 1].start()].strip():
                spans.append(m.group() + words[i + 1].group())
            for span in spans:
                if fold(span) in self._exact:
                    continue  # already written right
                hit = self._lookup(span, candidate=True)
                if hit:
                    term, score = hit
                    scored[term.text] = max(scored.get(term.text, 0.0), score)
        return [t for t, _ in sorted(scored.items(), key=lambda kv: -kv[1])][:limit]

    def correct(self, text: str) -> str:
        """Replace words that sound like a lexicon term with the term."""
        words = list(WORD_RE.finditer(text))
        out, pos, i = [], 0, 0
        while i < len(words):
            m = words[i]
            replacement, used = None, 1
            single = self._lookup(m.group(), candidate=False)
            # Whisper sometimes splits an unknown name in two ("ξαρέλ το" for Xarelto).
            # The first half must be an unknown word of 3+ letters, so "η υπόταση"
            # is never glued together.
            first = fold(m.group())
            if (i + 1 < len(words) and not text[m.end():words[i + 1].start()].strip()
                    and len(first) >= 3 and first not in common_words() and first not in self._exact
                    and fold(words[i + 1].group()) not in self._exact):
                pair = self._lookup(m.group() + words[i + 1].group(), candidate=False)
                if pair and pair[1] >= GREEK_CUTOFF and (not single or pair[1] > single[1]):
                    replacement, used = pair[0].text, 2
            if replacement is None and single:
                replacement = single[0].text
            end = words[i + used - 1].end()
            out.append(text[pos:m.start()])
            original = text[m.start():end]
            if replacement is None:
                out.append(original)
            else:
                if original[:1].isupper() and replacement[:1].islower():
                    replacement = replacement[:1].upper() + replacement[1:]
                out.append(replacement)
            pos = end
            i += used
        out.append(text[pos:])
        return "".join(out)


def build_lexicon(user_words: list[str], medical: bool) -> Lexicon:
    terms = list(user_words)
    if medical:
        terms += load_terms(MEDICAL_FILE)
    return Lexicon(terms)


def build_prompt(words: list[str], *, medical: bool, mixed: bool, count_tokens=None,
                 budget: int = PROMPT_BUDGET) -> str | None:
    """Style sentences, then as many vocabulary words as fit in the token budget
    (the list's first words first: second-reading candidates, then the user's)."""
    count = count_tokens or (lambda s: len(s) // 2)
    parts = []
    if mixed:
        parts.append(MIXED_PROMPT)
    if medical:
        parts.append(MEDICAL_PROMPT)
    base = " ".join(parts)
    chosen: list[str] = []
    seen = set()
    for w in words:
        w = " ".join(w.split())
        if not w or fold(w) in seen:
            continue
        trial = (base + " " if base else "") + "Λεξιλόγιο: " + ", ".join(chosen + [w]) + "."
        if count(trial) > budget:
            break
        chosen.append(w)
        seen.add(fold(w))
    if chosen:
        return (base + " " if base else "") + "Λεξιλόγιο: " + ", ".join(chosen) + "."
    return base or None
