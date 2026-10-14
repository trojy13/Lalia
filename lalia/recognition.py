"""One dictation from audio to text: prompt, first reading, optional second
reading with the sound-alike vocabulary terms, then correction."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import vocabulary
from .config import Settings
from .transcriber import Transcriber


@dataclass
class Recognition:
    text: str
    seconds_audio: float
    seconds_taken: float
    second_reading: bool
    candidates: int


def recognise(transcriber: Transcriber, audio: np.ndarray, s: Settings,
              lexicon: vocabulary.Lexicon | None) -> Recognition:
    mixed = s.language == "el_en"
    language = "el" if mixed else s.language
    medical = s.medical_vocabulary

    def read(words: list[str]):
        prompt = vocabulary.build_prompt(words, medical=medical, mixed=mixed,
                                         count_tokens=transcriber.count_tokens)
        return transcriber.transcribe(audio, language=language, beam_size=s.beam_size, initial_prompt=prompt)

    first = read(s.custom_words)
    text, taken, second, found = first.text, first.seconds_taken, False, 0
    use_second = s.second_pass == "on" or (s.second_pass == "auto" and transcriber.on_gpu)
    if lexicon is not None and use_second and text:
        candidates = lexicon.candidates(text)
        found = len(candidates)
        if candidates:
            again = read(candidates + s.custom_words)
            taken += again.seconds_taken
            # A second reading that lost much of the text is not trusted.
            if again.text and len(again.text) >= 0.6 * len(text):
                text, second = again.text, True
    if lexicon is not None:
        text = lexicon.correct(text)
    return Recognition(text, first.seconds_audio, taken, second, found)
