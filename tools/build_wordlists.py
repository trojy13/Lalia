"""Build lalia/data/common_el.txt and common_en.txt from the wordfreq project.

A word in these lists is an ordinary Greek or English word, which the sound-alike
correction must never turn into a drug name ("αέριο" is not "Aerius", "order" is
not a brand). Run once when the vocabulary changes:

    uv run --no-project --with wordfreq python tools/build_wordlists.py

Word frequencies: wordfreq by Robyn Speer, data CC BY-SA 4.0.
"""
from __future__ import annotations

import sys
from pathlib import Path

import wordfreq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lalia.vocabulary import fold, is_greek  # noqa: E402

DATA = ROOT / "lalia" / "data"


def build(lang: str, min_zipf: float, keep, limit: int) -> list[str]:
    # Lexicon terms that are also everyday words stay in ("foster", "άσθμα"): the
    # lookup still matches them exactly, but never fuzzily turns them into a brand.
    out, seen = [], set()
    for word in wordfreq.iter_wordlist(lang, wordlist="best"):
        if wordfreq.zipf_frequency(word, lang) < min_zipf or len(out) >= limit:
            break
        f = fold(word)
        if len(f) < 3 or not keep(f) or f in seen:
            continue
        seen.add(f)
        out.append(f)
    return out


def main() -> None:
    el = build("el", 2.0, lambda w: is_greek(w) and w.isalpha(), 120_000)
    en = build("en", 3.0, lambda w: w.isascii() and w.isalpha(), 40_000)
    header = "# Built by tools/build_wordlists.py from wordfreq (data CC BY-SA 4.0). Folded: lower case, no accents.\n"
    (DATA / "common_el.txt").write_text(header + "\n".join(el) + "\n", encoding="utf-8")
    (DATA / "common_en.txt").write_text(header + "\n".join(en) + "\n", encoding="utf-8")
    print("common_el", len(el), "common_en", len(en))


if __name__ == "__main__":
    main()
