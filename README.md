# Λαλιά (Lalia)

Offline push-to-talk dictation for Windows 11, Greek first. Hold a shortcut,
speak, let go: the words are typed into the window you are working in. It does
what [Handy](https://github.com/cjpais/handy) does, with Whisper
**large-v3-turbo** running on this PC (nothing is sent anywhere), and adds a
few things for a pharmacy desk: typing into the window under the mouse, a
floating microphone button that can appear only over chosen programs, and
Greek-aware text clean-up.

Separate from PharmacyControlBoard. It borrows two ideas from PCB's
notification panel and tray companion: windows that stay on top without taking
the focus, and showing only over windows whose title matches (PCB's "only over
the ERP").

## Install

Needs Python 3.10–3.13 (`py` launcher) and Windows 10/11. No administrator rights.

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1            # Start-menu shortcut "Λαλιά"
powershell -ExecutionPolicy Bypass -File setup.ps1 -Desktop -Autostart -DownloadModel
```

`setup.ps1` makes `.venv`, installs Lalia, and on a PC with an NVIDIA GPU also
installs the CUDA 12 cuBLAS/cuDNN 9 libraries as pip wheels (no CUDA Toolkit
needed). The model (~1.6 GB) downloads on first use, or at setup with
`-DownloadModel`. After that Lalia works offline.

Start it from the Start menu, or with `Lalia.cmd`. Starting it again while it
runs opens its settings. `pythonw -m lalia --background` starts in the tray only
(that is what "start with Windows" uses).

## Use

| Action | How |
| --- | --- |
| Dictate | Hold **Ctrl+Space**, speak, release |
| Cancel | **Esc** while recording or transcribing |
| Dictate with the mouse | Tray menu → «Πλωτό κουμπί μικροφώνου», click the button to start and again to stop |
| Settings, history | Left-click the tray icon (green microphone) |

The pill at the bottom of the screen shows the level meter while recording,
then «Μεταγραφή…», then the start of what was typed. It is click-through and
never takes the focus.

### Where the text goes («Εισαγωγή» tab)

- **Κάτω από το ποντίκι** (default): the window under the mouse pointer when you
  release the shortcut. If that is the window you are typing in, nothing
  changes. If it is another window, Lalia brings it to the front and types where
  its caret was. Over the desktop or taskbar it falls back to the active window.
- **Ενεργό παράθυρο**: where the caret is, like Handy.
- **Κλικ στη θέση του ποντικιού**: clicks at the pointer first, so the text lands
  exactly where the mouse points. Avoid it over buttons.

Insertion is by paste (Ctrl+V, default; Shift+Insert for terminals;
Ctrl+Shift+V), or by typing each character as a Unicode key event. Unlike
Handy's direct input, that works with any keyboard layout. The previous clipboard is restored after a paste, and
the dictated text is kept out of Windows clipboard history (Win+V). If the
target runs as administrator, Windows blocks typed input, so the text stays on
the clipboard and the pill says so. For such a program (some pharmacy software
runs elevated), start Lalia as administrator too, or use the toggle mode
(«Πάτημα»), which does not depend on seeing the key held.

### Greek with English, and medical vocabulary («Αναγνώριση» tab)

- **Γλώσσα: Ελληνικά με αγγλικές λέξεις και φράσεις** (default). Greek is the
  main language, and English words or phrases inside it are kept as English. With
  plain Greek, Whisper leaves out an English clause («ο πελάτης ρωτάει *if we have
  the new flu vaccine in stock*, και…» lost the English part); this mode keeps it.
  A dictation that *starts* in English and goes on in Greek can still lose the
  English start: dictate the two parts separately.
- **Ιατρικό και φαρμακευτικό λεξιλόγιο** (default on): 419 terms in
  [lalia/data/medical_el.txt](lalia/data/medical_el.txt): Greek-market brand
  names, Greek substance names, conditions, dosage forms, units, vaccines.
  Whisper writes brands it hears in Greek letters («λίπιτορ», «πλάβιξ»); each
  word is compared by sound with the lexicon, Greek letters transliterated, and
  replaced by the term («λίπιτορ» becomes Lipitor, «αμοξικιλίνη» becomes
  αμοξικιλλίνη, «DEPON» becomes Depon). Ordinary Greek and English words are never
  changed: a list of ~39,000 common Greek and ~28,000 common English words
  protects them («αέριο» stays, "concert" stays).
- **Δεύτερη ανάγνωση**: on a GPU, when some words sound like lexicon terms, the
  audio is read again with those terms in the prompt, and the model checks them
  against the sound. It costs ~0.3 s on the GPU. On the CPU it would double the
  time, so "Αυτόματα" uses it only with a GPU.
- **Your own words** («Κείμενο» → Λεξιλόγιο, or «Εισαγωγή από αρχείο…» for a
  .txt with one name per line, or a .csv whose first column is the name): used
  the same way, and the first ones also go in the prompt. Whisper reads only
  ~223 prompt tokens and a Greek drug name costs ~10, so a long list works
  through the sound matching, not the prompt.

Measured with [tools/vocab_eval.py](tools/vocab_eval.py) on 14 test sentences
(Windows voices; brands spoken the way a Greek pharmacist says them; ordinary
sentences that must not change), large-v3-turbo on the GPU:

| Setting | Key terms right | Wrong insertions |
| --- | --- | --- |
| Greek only (before) | 19 / 42 | 0 (an English-only sentence came out as a subtitle hallucination) |
| Greek with English | 24 / 42 | 0 |
| + medical vocabulary | 36 / 42 | 0 |
| + second reading (GPU) | 38 / 42 | 0 |

### Settings worth knowing

- **Λεξιλόγιο** («Κείμενο»): see above. In testing, "αμοξικιλλίνη" came out as
  "άμοξικιλίνη" without any vocabulary and correctly with it.
- **Αντικαταστάσεις**: `from => to`, one per line, accent- and case-insensitive.
- **Φωνητική στίξη**: say «τελεία», «κόμμα», «ερωτηματικό», «νέα γραμμή».
  Off by default, because Whisper punctuates by itself.
- **Μοντέλο / Επεξεργασία σε**: large-v3-turbo on the GPU is the default. On a PC
  without an NVIDIA GPU it runs on the CPU. For weak PCs, pick Medium or Small.
- **Πλωτό κουμπί → μόνο πάνω από**: e.g. `Διοσκουρίδης, FARMAKON`; the button
  shows only while such a window is in front (case and accents ignored).
- **Τρόπος**: hold (push-to-talk), toggle, or both (hold, or tap once to keep recording).

Everything is stored in `%LOCALAPPDATA%\Lalia`: `settings.json`,
`history.jsonl` (the last 100 texts; set 0 to keep none; audio is never kept),
`models\`, `logs\lalia.log` (timings only, never the dictated text).

## Measured on the dev PC (RTX 4090, Ryzen 7 5800X3D)

11.2 s of Greek speech (Windows "Stefanos" voice), large-v3-turbo, beam 5:

| Device | Load | Recognition | Stop → text in window |
| --- | --- | --- | --- |
| GPU, float16 | 2.7–6 s once | 0.3 s | 0.57 s |
| CPU, int8, 8 threads | 8.5 s once | 5.5–6 s | — |

Laptop (Zenbook, i5-1240P, Intel Iris Xe, no NVIDIA), CPU int8: load 11.5–20 s,
recognition 17.5 s with 8 or 12 threads (26 s with 4). That is slower than the
speech itself, so on such PCs pick a smaller model or a GPU backend.

## Tools

```powershell
.venv\Scripts\python -m pytest                       # unit tests
.venv\Scripts\python tools\selftest.py               # live Windows checks, ~5 s, moves focus and mouse
.venv\Scripts\python tools\apptest.py samples\el.wav # the whole app, a WAV instead of the microphone
powershell -File tools\make_greek_sample.ps1 -Out samples\el.wav -Text "..."   # Greek test speech
.venv\Scripts\python tools\bench.py samples\el.wav --device cpu
.venv\Scripts\python tools\vocab_eval.py [--device cpu] [--only el_en+medical]   # Greek/English + vocabulary test
uv run --no-project --with wordfreq python tools\build_wordlists.py              # rebuild the common-word lists
```

The common-word lists in `lalia/data/common_*.txt` come from
[wordfreq](https://github.com/rspeer/wordfreq) by Robyn Speer (data CC BY-SA 4.0).

## How it is built

| Module | Job |
| --- | --- |
| `hotkey.py` | `RegisterHotKey` on its own thread (no keyboard hook, so it cannot slow typing); release found by polling `GetAsyncKeyState` |
| `audio.py` | sounddevice, 16 kHz mono, microphone open only while dictating |
| `transcriber.py` | faster-whisper / CTranslate2; CUDA float16 or CPU int8; Silero VAD; warm-up run checks the GPU really works |
| `recognition.py` | one dictation: prompt, first reading, optional second reading, correction |
| `vocabulary.py` | sound keys across Greek/Latin letters, lexicon matching (rapidfuzz), prompt within the token budget |
| `textproc.py` | drops Whisper's subtitle-credit hallucinations, applies replacements and spoken punctuation |
| `output.py` | clipboard save/paste/restore, Unicode typing, window under the mouse, foreground switching, elevation check |
| `overlay.py`, `micbutton.py` | Tk windows with `WS_EX_NOACTIVATE`, shown with `SW_SHOWNOACTIVATE` and the click-activation of Tk suppressed |
| `tray.py` | pystray icon and menu; Windows 11 tray promotion like PCB's companion |
| `app.py` | the state machine; one worker thread recognises and types, in order |

## Not done yet

- A single `.exe` (PyInstaller) for PCs without Python.
- Muting other audio while recording, and a "translate to English" mode
  (large-v3-turbo was not trained for translation).
- A modifier-only shortcut (e.g. right Ctrl alone) or a mouse side button; those need a low-level hook.
- Tested on one PC (Windows 11, NVIDIA). Not yet tried on a pharmacy till.
