"""Clean-up of the recognised text before it is typed: subtitle-credit
hallucinations, the user's replacements, optional spoken punctuation."""
from __future__ import annotations

import re
import unicodedata

# Whisper learned from subtitled video, so near-silence sometimes comes back as a
# subtitle credit. A sentence equal to one of these (ignoring case, accents and
# punctuation) is dropped. Only phrases nobody dictates on purpose belong here.
BLOCKED_SENTENCES = [
    "Υπότιτλοι AUTHORWAVE",
    "Υποτιτλισμός AUTHORWAVE",
    "Ευχαριστούμε που παρακολουθήσατε",
    "Ευχαριστώ που παρακολουθήσατε",
    "Ευχαριστώ για την παρακολούθηση",
    "Ευχαριστούμε για την παρακολούθηση",
    "Μην ξεχάσετε να κάνετε like και subscribe",
    "Subtitles by the Amara.org community",
    "Thank you for watching",
    "Thanks for watching",
]

# Spoken punctuation (opt-in). Longest phrases first so "άνω κάτω τελεία" wins
# over "τελεία".
SPOKEN_PUNCTUATION = [
    ("νέα παράγραφος", "\n\n"),
    ("νέα γραμμή", "\n"),
    ("άνω κάτω τελεία", ":"),
    ("άνω τελεία", "·"),
    ("ερωτηματικό", ";"),
    ("θαυμαστικό", "!"),
    ("τελεία", "."),
    ("κόμμα", ","),
    ("new paragraph", "\n\n"),
    ("new line", "\n"),
    ("question mark", "?"),
    ("full stop", "."),
    ("comma", ","),
]

# ASCII marks plus the Greek ano teleia (U+00B7, U+0387) and question mark (U+037E).
_P = ".,;:!?··;"
_PC = "[" + re.escape(_P) + "]"
_SENTENCE_SPLIT = re.compile("(?<=[.!?;;…])\\s+")


def normalize(text: str) -> str:
    """Lower case, no accents, no punctuation, single spaces."""
    decomposed = unicodedata.normalize("NFD", text.casefold())
    no_marks = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    letters = "".join(c if (c.isalnum() or c.isspace()) else " " for c in no_marks)
    return " ".join(letters.split())


_BLOCKED_NORMALIZED = {normalize(s) for s in BLOCKED_SENTENCES}


def drop_blocked(text: str) -> str:
    kept = [s for s in _SENTENCE_SPLIT.split(text) if normalize(s) not in _BLOCKED_NORMALIZED]
    return " ".join(s for s in kept if s.strip())


def parse_replacements(lines: list[str]) -> list[tuple[str, str]]:
    """'from => to' lines; '\\n' in the target means a new line."""
    pairs = []
    for line in lines:
        if "=>" not in line:
            continue
        src, dst = line.split("=>", 1)
        src = src.strip()
        if not src:
            continue
        pairs.append((src, dst.strip().replace("\\n", "\n").replace("\\t", "\t")))
    return pairs


def _accent_insensitive_pattern(phrase: str) -> str:
    """Regex for a phrase that matches with or without Greek accents."""
    out = []
    for ch in phrase:
        base = "".join(c for c in unicodedata.normalize("NFD", ch) if unicodedata.category(c) != "Mn")
        if ch.isspace():
            out.append(r"\s+")
        elif base and base != ch:
            out.append(f"[{re.escape(ch)}{re.escape(base)}]")
        elif ch.isalpha():
            # also accept the accented forms of an unaccented letter
            variants = {ch} | {v for v in _ACCENTED.get(ch.lower(), "")}
            out.append("[" + "".join(re.escape(v) for v in sorted(variants)) + "]")
        else:
            out.append(re.escape(ch))
    return "".join(out)


_ACCENTED = {
    "α": "ά", "ε": "έ", "η": "ή", "ι": "ίϊΐ", "ο": "ό", "υ": "ύϋΰ", "ω": "ώ",
}


def apply_replacements(text: str, pairs: list[tuple[str, str]]) -> tuple[str, bool]:
    changed = False
    for src, dst in pairs:
        pattern = re.compile(r"(?<!\w)" + _accent_insensitive_pattern(src) + r"(?!\w)", re.IGNORECASE)
        text, n = pattern.subn(lambda _m, d=dst: d, text)
        changed = changed or n > 0
    return text, changed


def tidy_punctuation(text: str) -> str:
    """After replacements: no space before punctuation, no doubled marks Whisper
    added itself ('κόμμα' heard as ', κόμμα,' becomes ',,'), one space after."""
    text = re.sub(r"[ \t]+(" + _PC + ")", r"\1", text)
    text = re.sub("(" + _PC + r")(?:[ \t]*" + _PC + ")+", r"\1", text)
    text = re.sub("(" + _PC + r")(?=[^\s\d" + re.escape(_P) + "\"'»)\\]])", r"\1 ", text)
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip(" \t")


def finalize(text: str, *, replacements: list[str], spoken_punctuation: bool, trailing_space: bool) -> str:
    text = " ".join(text.split())
    text = drop_blocked(text)
    if not text:
        return ""
    pairs = parse_replacements(replacements)
    if spoken_punctuation:
        pairs += SPOKEN_PUNCTUATION
    if pairs:
        text, changed = apply_replacements(text, pairs)
        if changed:
            text = tidy_punctuation(text)
    text = text.strip(" \t")
    if not text:
        return ""
    if trailing_space and not text.endswith(("\n", " ")):
        text += " "
    return text
