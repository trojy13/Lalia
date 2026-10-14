"""Compare recognition settings on mixed Greek/English and pharmacy sentences.

Speaks tools/eval_sentences.json with the Windows voices (cached in samples/eval),
transcribes every sentence under each setting, and counts the key terms that come
out spelled as expected, and any term that must not appear ('forbid').

    .venv\\Scripts\\python tools\\vocab_eval.py [--device cpu] [--only app,app-no-second]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from bench import read_wav  # noqa: E402

from lalia import vocabulary  # noqa: E402
from lalia.config import Settings  # noqa: E402
from lalia.recognition import recognise  # noqa: E402
from lalia.transcriber import SAMPLE_RATE, Transcriber  # noqa: E402

SPEC = ROOT / "tools" / "eval_sentences.json"
CACHE = ROOT / "samples" / "eval"
TTS = ROOT / "tools" / "make_greek_sample.ps1"

# The settings compared: what the app did before, and the new modes.
CONFIGS = {
    "greek-only": Settings(language="el", medical_vocabulary=False, second_pass="off"),
    "el_en": Settings(language="el_en", medical_vocabulary=False, second_pass="off"),
    "el_en+medical": Settings(language="el_en", medical_vocabulary=True, second_pass="off"),
    "el_en+medical+2nd": Settings(language="el_en", medical_vocabulary=True, second_pass="on"),
}


def speak(lang: str, text: str, out: Path) -> None:
    if out.exists():
        return
    args = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(TTS), "-Out", str(out), "-Text", text]
    if lang == "en":
        args.append("-English")
    subprocess.run(args, check=True, capture_output=True)


def sentence_audio(item: dict) -> np.ndarray:
    CACHE.mkdir(parents=True, exist_ok=True)
    pieces = []
    for i, (lang, text) in enumerate(item["parts"]):
        f = CACHE / f"{item['id']}_{i}.wav"
        speak(lang, text, f)
        pieces.append(read_wav(str(f)))
        pieces.append(np.zeros(int(0.15 * SAMPLE_RATE), dtype=np.float32))
    return np.concatenate(pieces)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="auto")
    ap.add_argument("--model", default="large-v3-turbo")
    ap.add_argument("--only", default="", help="comma-separated config names")
    args = ap.parse_args()

    spec = json.loads(SPEC.read_text(encoding="utf-8"))["sentences"]
    audios = {item["id"]: sentence_audio(item) for item in spec}
    t = Transcriber()
    t.load(args.model, args.device)
    out = sys.stdout.buffer
    out.write(f"model {args.model} on {t.device_label}\n".encode())
    summary = []
    for name, s in CONFIGS.items():
        if args.only and name not in args.only.split(","):
            continue
        lexicon = vocabulary.build_lexicon(s.custom_words, s.medical_vocabulary) if s.medical_vocabulary else None
        hits = total = bad = 0
        t0 = time.monotonic()
        out.write(f"\n=== {name}\n".encode())
        for item in spec:
            r = recognise(t, audios[item["id"]], s, lexicon)
            text = r.text
            found = [x for x in item.get("terms", []) if x.casefold() in text.casefold()]
            wrong = [x for x in item.get("forbid", []) if x.casefold() in text.casefold()]
            hits += len(found)
            total += len(item.get("terms", []))
            bad += len(wrong)
            missing = [x for x in item.get("terms", []) if x not in found]
            note = ("   [missing: " + ", ".join(missing) + "]" if missing else "") + \
                   ("   [WRONG: " + ", ".join(wrong) + "]" if wrong else "") + ("  (2nd)" if r.second_reading else "")
            out.write(f"  {item['id']:8} {len(found)}/{len(item.get('terms', []))}  {text}{note}\n".encode("utf-8"))
        summary.append((name, hits, total, bad, time.monotonic() - t0))
    out.write(b"\n--- summary: terms right / total, wrong insertions, time for all sentences\n")
    for name, hits, total, bad, secs in summary:
        out.write(f"  {name:24} {hits:2}/{total}   wrong {bad}   {secs:.1f}s\n".encode())


if __name__ == "__main__":
    main()
