"""The settings window (Tk/ttk), in Greek."""
from __future__ import annotations

import dataclasses
import re
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import audio, autostart, config, paths, vocabulary
from .hotkey import KEYS, HotkeyError, parse
from .transcriber import MODELS

MODES = [
    ("hold", "Κράτημα: μιλάτε όσο κρατάτε πατημένη τη συντόμευση"),
    ("toggle", "Πάτημα: ένα πάτημα ξεκινά, δεύτερο πάτημα σταματά"),
    ("both", "Και τα δύο: κράτημα ή σύντομο πάτημα"),
]
LANGUAGES = [("el_en", "Ελληνικά με αγγλικές λέξεις και φράσεις (συνιστάται)"), ("el", "Μόνο ελληνικά"),
             ("en", "English"), ("auto", "Αυτόματη αναγνώριση γλώσσας")]
SECOND_PASS = [("auto", "Αυτόματα: μόνο με κάρτα γραφικών"), ("on", "Πάντα (στον επεξεργαστή διπλασιάζει τον χρόνο)"),
               ("off", "Ποτέ")]
DEVICES = [("auto", "Αυτόματα (κάρτα γραφικών NVIDIA αν υπάρχει)"), ("cuda", "Κάρτα γραφικών (CUDA)"),
           ("cpu", "Επεξεργαστής (CPU)")]
TARGETS = [
    ("under_mouse", "Στο παράθυρο που βρίσκεται κάτω από το ποντίκι"),
    ("focused", "Στο ενεργό παράθυρο, εκεί που αναβοσβήνει ο κέρσορας (όπως το Handy)"),
    ("click_at_mouse", "Κλικ στη θέση του ποντικιού και γράψιμο εκεί"),
]
METHODS = [
    ("ctrl_v", "Επικόλληση με Ctrl+V (συνιστάται)"),
    ("shift_insert", "Επικόλληση με Shift+Insert (τερματικά, PowerShell)"),
    ("ctrl_shift_v", "Επικόλληση με Ctrl+Shift+V"),
    ("type", "Πληκτρολόγηση χαρακτήρα-χαρακτήρα (χωρίς πρόχειρο)"),
    ("clipboard", "Μόνο αντιγραφή στο πρόχειρο"),
]
POSITIONS = [("bottom", "Κάτω"), ("top", "Πάνω"), ("none", "Καμία ένδειξη")]
UNLOAD = [(0, "Ποτέ"), (5, "5 λεπτά"), (15, "15 λεπτά"), (30, "30 λεπτά"), (60, "1 ώρα")]
DEFAULT_MIC = "Προεπιλογή των Windows"

KEY_CHOICES = ["Space", "Enter", "Tab", "`", "Insert", "Pause", "ScrollLock", "Apps", "Home", "End",
               "PageUp", "PageDown"] + [f"F{i}" for i in range(1, 25)] + \
              [chr(c) for c in range(ord("A"), ord("Z") + 1)] + [str(d) for d in range(10)] + \
              [f"Num{d}" for d in range(10)]
assert all(k in KEYS for k in KEY_CHOICES)


def _label(pairs, value):
    return next((lbl for v, lbl in pairs if v == value), pairs[0][1])


def _value(pairs, label):
    return next((v for v, lbl in pairs if lbl == label), pairs[0][0])


class SettingsWindow:
    def __init__(self, app):
        self.app = app
        s = app.settings
        self.alive = True
        self.win = tk.Toplevel(app.root)
        self.win.title(f"{paths.APP_TITLE} — Ρυθμίσεις")
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.minsize(int(560 * app.scale), int(440 * app.scale))
        style = ttk.Style(self.win)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Hint.TLabel", foreground="#57606a")
        style.configure("Error.TLabel", foreground="#cf222e")
        style.configure("Status.TLabel", foreground="#1a7f37")

        pad = {"padx": 10, "pady": 4}
        outer = ttk.Frame(self.win, padding=8)
        outer.pack(fill="both", expand=True)
        nb = self.notebook = ttk.Notebook(outer)
        nb.pack(fill="both", expand=True)

        # ---- Γενικά -------------------------------------------------------------
        tab = ttk.Frame(nb, padding=10)
        nb.add(tab, text="Γενικά")
        try:
            mods, _vk, normal = parse(s.hotkey)
            parts = normal.split("+")
        except HotkeyError:
            parts = ["Ctrl", "Space"]
        self.v_mods = {m: tk.BooleanVar(value=m in parts[:-1]) for m in ("Ctrl", "Alt", "Shift", "Win")}
        self.v_key = tk.StringVar(value=parts[-1])
        ttk.Label(tab, text="Συντόμευση υπαγόρευσης").grid(row=0, column=0, sticky="w", **pad)
        hk = ttk.Frame(tab)
        hk.grid(row=0, column=1, sticky="w", **pad)
        for i, m in enumerate(("Ctrl", "Alt", "Shift", "Win")):
            ttk.Checkbutton(hk, text=m, variable=self.v_mods[m]).grid(row=0, column=i, padx=(0, 6))
        ttk.Label(hk, text="+").grid(row=0, column=4, padx=4)
        ttk.Combobox(hk, textvariable=self.v_key, values=KEY_CHOICES, width=10, state="readonly").grid(
            row=0, column=5)
        self.hotkey_label = ttk.Label(tab, text="", style="Hint.TLabel")
        self.hotkey_label.grid(row=1, column=1, sticky="w", padx=10)

        ttk.Label(tab, text="Τρόπος").grid(row=2, column=0, sticky="nw", **pad)
        self.v_mode = tk.StringVar(value=s.mode)
        fr = ttk.Frame(tab)
        fr.grid(row=2, column=1, sticky="w", **pad)
        for v, lbl in MODES:
            ttk.Radiobutton(fr, text=lbl, value=v, variable=self.v_mode).pack(anchor="w")

        ttk.Label(tab, text="Μικρόφωνο").grid(row=3, column=0, sticky="w", **pad)
        fr = ttk.Frame(tab)
        fr.grid(row=3, column=1, sticky="we", **pad)
        self.v_mic = tk.StringVar(value=s.microphone or DEFAULT_MIC)
        self.mic_box = ttk.Combobox(fr, textvariable=self.v_mic, width=46, state="readonly")
        self.mic_box.pack(side="left")
        ttk.Button(fr, text="Ανανέωση", command=self._refresh_mics).pack(side="left", padx=6)
        self._fill_mics()

        self.v_sounds = tk.BooleanVar(value=s.sounds)
        ttk.Checkbutton(tab, text="Ήχος στην αρχή και στο τέλος της ηχογράφησης",
                        variable=self.v_sounds).grid(row=4, column=1, sticky="w", **pad)
        self.v_autostart = tk.BooleanVar(value=autostart.is_enabled())
        ttk.Checkbutton(tab, text="Εκκίνηση μαζί με τα Windows", variable=self.v_autostart).grid(
            row=5, column=1, sticky="w", **pad)

        ttk.Label(tab, text="Δοκιμή").grid(row=6, column=0, sticky="nw", **pad)
        test = tk.Text(tab, height=4, width=56, wrap="word", font=("Segoe UI", 10), relief="solid", bd=1)
        test.grid(row=6, column=1, sticky="nsew", **pad)
        ttk.Label(tab, text="Κάντε κλικ στο πλαίσιο, κρατήστε πατημένη τη συντόμευση και μιλήστε.",
                  style="Hint.TLabel").grid(row=7, column=1, sticky="w", padx=10)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(6, weight=1)

        # ---- Αναγνώριση -------------------------------------------------------------
        tab = ttk.Frame(nb, padding=10)
        nb.add(tab, text="Αναγνώριση")
        self.model_pairs = [(name, label) for name, label, _mb in MODELS]
        if s.model not in [n for n, _ in self.model_pairs]:
            self.model_pairs.append((s.model, s.model))
        self.v_model = tk.StringVar(value=_label(self.model_pairs, s.model))
        ttk.Label(tab, text="Μοντέλο").grid(row=0, column=0, sticky="w", **pad)
        ttk.Combobox(tab, textvariable=self.v_model, values=[l for _, l in self.model_pairs], width=50,
                     state="readonly").grid(row=0, column=1, sticky="w", **pad)
        ttk.Label(tab, text="Η πρώτη χρήση κάθε μοντέλου το κατεβάζει μία φορά (Large v3 Turbo: ~1,6 GB).",
                  style="Hint.TLabel").grid(row=1, column=1, sticky="w", padx=10)

        self.v_lang = tk.StringVar(value=_label(LANGUAGES, s.language))
        ttk.Label(tab, text="Γλώσσα").grid(row=2, column=0, sticky="w", **pad)
        ttk.Combobox(tab, textvariable=self.v_lang, values=[l for _, l in LANGUAGES], width=50,
                     state="readonly").grid(row=2, column=1, sticky="w", **pad)

        ttk.Label(tab, text="Λεξιλόγιο").grid(row=3, column=0, sticky="nw", **pad)
        fr = ttk.Frame(tab)
        fr.grid(row=3, column=1, sticky="w", **pad)
        self.v_medical = tk.BooleanVar(value=s.medical_vocabulary)
        ttk.Checkbutton(fr, text="Ιατρικό και φαρμακευτικό λεξιλόγιο (σκευάσματα, δραστικές ουσίες, παθήσεις)",
                        variable=self.v_medical).pack(anchor="w")
        ttk.Label(fr, text="Π.χ. «λίπιτορ» γράφεται Lipitor, «αμοξικιλίνη» διορθώνεται σε αμοξικιλλίνη. "
                           "Δικές σας λέξεις: καρτέλα «Κείμενο».", style="Hint.TLabel",
                  wraplength=int(440 * app.scale)).pack(anchor="w")

        self.v_second = tk.StringVar(value=_label(SECOND_PASS, s.second_pass))
        ttk.Label(tab, text="Δεύτερη ανάγνωση").grid(row=4, column=0, sticky="w", **pad)
        ttk.Combobox(tab, textvariable=self.v_second, values=[l for _, l in SECOND_PASS], width=50,
                     state="readonly").grid(row=4, column=1, sticky="w", **pad)

        self.v_device = tk.StringVar(value=_label(DEVICES, s.device))
        ttk.Label(tab, text="Επεξεργασία σε").grid(row=5, column=0, sticky="w", **pad)
        ttk.Combobox(tab, textvariable=self.v_device, values=[l for _, l in DEVICES], width=50,
                     state="readonly").grid(row=5, column=1, sticky="w", **pad)

        self.v_beam = tk.IntVar(value=s.beam_size)
        ttk.Label(tab, text="Ακρίβεια (beam)").grid(row=6, column=0, sticky="w", **pad)
        fr = ttk.Frame(tab)
        fr.grid(row=6, column=1, sticky="w", **pad)
        ttk.Spinbox(fr, from_=1, to=10, textvariable=self.v_beam, width=5).pack(side="left")
        ttk.Label(fr, text="  5 = ακριβέστερο, 1 = λίγο πιο γρήγορο", style="Hint.TLabel").pack(side="left")

        self.v_unload = tk.StringVar(value=_label(UNLOAD, s.unload_after_minutes))
        ttk.Label(tab, text="Αποδέσμευση μνήμης").grid(row=7, column=0, sticky="w", **pad)
        fr = ttk.Frame(tab)
        fr.grid(row=7, column=1, sticky="w", **pad)
        ttk.Combobox(fr, textvariable=self.v_unload, values=[l for _, l in UNLOAD], width=12,
                     state="readonly").pack(side="left")
        ttk.Label(fr, text="  χωρίς χρήση (Ποτέ = άμεση απόκριση)", style="Hint.TLabel").pack(side="left")

        ttk.Label(tab, text="Κατάσταση").grid(row=8, column=0, sticky="nw", **pad)
        self.model_status = ttk.Label(tab, text="", wraplength=int(440 * app.scale))
        self.model_status.grid(row=8, column=1, sticky="w", **pad)
        tab.columnconfigure(1, weight=1)

        # ---- Κείμενο -------------------------------------------------------------------
        tab = ttk.Frame(nb, padding=10)
        nb.add(tab, text="Κείμενο")
        fr = ttk.Frame(tab)
        fr.grid(row=0, column=0, sticky="we", **pad)
        ttk.Label(fr, text="Δικό σας λεξιλόγιο, μία λέξη ή φράση ανά γραμμή (φάρμακα, επώνυμα, όροι, "
                           "αγγλικές λέξεις), γραμμένο όπως θέλετε να εμφανίζεται.",
                  wraplength=int(430 * app.scale)).pack(side="left", anchor="w")
        ttk.Button(fr, text="Εισαγωγή από αρχείο…", command=self._import_words).pack(side="right")
        self.t_words = tk.Text(tab, height=6, width=60, font=("Segoe UI", 10), relief="solid", bd=1)
        self.t_words.grid(row=1, column=0, sticky="nsew", **pad)
        self.t_words.insert("1.0", "\n".join(s.custom_words))
        ttk.Label(tab, text="Αντικαταστάσεις: μία ανά γραμμή, «από => σε». Το \\n σημαίνει νέα γραμμή.").grid(
            row=2, column=0, sticky="w", **pad)
        self.t_repl = tk.Text(tab, height=5, width=60, font=("Segoe UI", 10), relief="solid", bd=1)
        self.t_repl.grid(row=3, column=0, sticky="nsew", **pad)
        self.t_repl.insert("1.0", "\n".join(s.replacements))
        self.v_spoken = tk.BooleanVar(value=s.spoken_punctuation)
        ttk.Checkbutton(tab, text="Φωνητική στίξη: «τελεία», «κόμμα», «ερωτηματικό», «νέα γραμμή»…",
                        variable=self.v_spoken).grid(row=4, column=0, sticky="w", **pad)
        self.v_space = tk.BooleanVar(value=s.trailing_space)
        ttk.Checkbutton(tab, text="Κενό στο τέλος κάθε υπαγόρευσης (για συνεχή υπαγόρευση)",
                        variable=self.v_space).grid(row=5, column=0, sticky="w", **pad)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        tab.rowconfigure(3, weight=1)

        # ---- Εισαγωγή ----------------------------------------------------------------------
        tab = ttk.Frame(nb, padding=10)
        nb.add(tab, text="Εισαγωγή")
        ttk.Label(tab, text="Πού γράφεται το κείμενο").grid(row=0, column=0, sticky="nw", **pad)
        self.v_target = tk.StringVar(value=s.target)
        fr = ttk.Frame(tab)
        fr.grid(row=0, column=1, sticky="w", **pad)
        for v, lbl in TARGETS:
            ttk.Radiobutton(fr, text=lbl, value=v, variable=self.v_target).pack(anchor="w")

        ttk.Label(tab, text="Τρόπος εισαγωγής").grid(row=1, column=0, sticky="nw", **pad)
        self.v_method = tk.StringVar(value=s.paste_method)
        fr = ttk.Frame(tab)
        fr.grid(row=1, column=1, sticky="w", **pad)
        for v, lbl in METHODS:
            ttk.Radiobutton(fr, text=lbl, value=v, variable=self.v_method).pack(anchor="w")

        self.v_restore = tk.BooleanVar(value=s.restore_clipboard)
        ttk.Checkbutton(tab, text="Επαναφορά του προηγούμενου προχείρου μετά την επικόλληση",
                        variable=self.v_restore).grid(row=2, column=1, sticky="w", **pad)
        self.v_enter = tk.BooleanVar(value=s.auto_enter)
        ttk.Checkbutton(tab, text="Πάτημα Enter μετά το κείμενο", variable=self.v_enter).grid(
            row=3, column=1, sticky="w", **pad)

        ttk.Label(tab, text="Ένδειξη στην οθόνη").grid(row=4, column=0, sticky="w", **pad)
        self.v_pos = tk.StringVar(value=_label(POSITIONS, s.overlay_position))
        ttk.Combobox(tab, textvariable=self.v_pos, values=[l for _, l in POSITIONS], width=16,
                     state="readonly").grid(row=4, column=1, sticky="w", **pad)

        ttk.Label(tab, text="Πλωτό κουμπί").grid(row=5, column=0, sticky="nw", **pad)
        fr = ttk.Frame(tab)
        fr.grid(row=5, column=1, sticky="we", **pad)
        self.v_button = tk.BooleanVar(value=s.mic_button)
        ttk.Checkbutton(fr, text="Κουμπί μικροφώνου πάνω από όλα τα παράθυρα (κλικ = έναρξη/λήξη)",
                        variable=self.v_button).pack(anchor="w")
        ttk.Label(fr, text="Μόνο πάνω από παράθυρα με τίτλο (κόμμα ανάμεσα, κενό = παντού):").pack(
            anchor="w", pady=(6, 0))
        self.v_only = tk.StringVar(value=s.mic_button_only_over)
        ttk.Entry(fr, textvariable=self.v_only, width=56).pack(anchor="w")
        ttk.Label(fr, text="π.χ. Διοσκουρίδης, FARMAKON, Word", style="Hint.TLabel").pack(anchor="w")
        tab.columnconfigure(1, weight=1)

        # ---- Ιστορικό --------------------------------------------------------------------------
        tab = ttk.Frame(nb, padding=10)
        nb.add(tab, text="Ιστορικό")
        fr = ttk.Frame(tab)
        fr.pack(fill="both", expand=True)
        self.hist = tk.Listbox(fr, font=("Segoe UI", 10), activestyle="none")
        sb = ttk.Scrollbar(fr, orient="vertical", command=self.hist.yview)
        self.hist.configure(yscrollcommand=sb.set)
        self.hist.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._hist_texts: list[str] = []
        fr = ttk.Frame(tab)
        fr.pack(fill="x", pady=(8, 0))
        ttk.Button(fr, text="Αντιγραφή", command=self._copy_history).pack(side="left")
        ttk.Button(fr, text="Διαγραφή ιστορικού", command=self._clear_history).pack(side="left", padx=6)
        ttk.Label(fr, text="Κράτα τις τελευταίες").pack(side="left", padx=(18, 4))
        self.v_hist = tk.IntVar(value=s.history_limit)
        ttk.Spinbox(fr, from_=0, to=5000, textvariable=self.v_hist, width=6).pack(side="left")
        ttk.Label(fr, text="(0 = χωρίς ιστορικό · μόνο σε αυτόν τον υπολογιστή, χωρίς ήχο)",
                  style="Hint.TLabel").pack(side="left", padx=6)
        self.refresh_history()

        # ---- bottom bar ----------------------------------------------------------------------
        bar = ttk.Frame(outer)
        bar.pack(fill="x", pady=(8, 0))
        self.status = ttk.Label(bar, text="", style="Status.TLabel")
        self.status.pack(side="left")
        ttk.Button(bar, text="Κλείσιμο", command=self.close).pack(side="right")
        ttk.Button(bar, text="Αποθήκευση", command=self.save).pack(side="right", padx=6)

        self.refresh_status()
        self.focus()

    # -- helpers ------------------------------------------------------------------------------
    def focus(self) -> None:
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()

    def _fill_mics(self) -> None:
        try:
            names = audio.input_devices()
        except Exception:
            names = []
        current = self.v_mic.get()
        values = [DEFAULT_MIC] + names
        if current not in values:
            values.append(current)
        self.mic_box.configure(values=values)

    def _refresh_mics(self) -> None:
        if self.app.recorder.active:
            return
        audio.refresh_devices()
        self._fill_mics()

    def refresh_status(self) -> None:
        if not self.alive:
            return
        a = self.app
        text = a.model_message
        if a.model_state == "ready" and a.transcriber.loaded:
            text += f" · φορτώθηκε σε {a.transcriber.load_seconds:.1f} s"
        if a.transcriber.last_error and a.model_state == "error":
            text += f"\n{a.transcriber.last_error[:300]}"
        self.model_status.configure(text=text)
        if a.hotkey_ok:
            self.hotkey_label.configure(text=f"Ενεργή: {a.settings.hotkey}", style="Hint.TLabel")
        elif a.hotkey_message:
            self.hotkey_label.configure(text=a.hotkey_message, style="Error.TLabel")

    def refresh_history(self) -> None:
        if not self.alive:
            return
        entries = list(reversed(self.app.history.entries()))
        self.hist.delete(0, "end")
        self._hist_texts = []
        for e in entries:
            text = e.get("text", "")
            self._hist_texts.append(text)
            self.hist.insert("end", f"{e.get('ts', '')[5:16]}   {' '.join(text.split())}")

    def _import_words(self) -> None:
        """Add words from a .txt (one per line) or the first column of a .csv."""
        path = filedialog.askopenfilename(parent=self.win, title="Εισαγωγή λεξιλογίου",
                                          filetypes=[("Κείμενο ή CSV", "*.txt *.csv"), ("Όλα τα αρχεία", "*.*")])
        if not path:
            return
        raw = Path(path).read_bytes()
        for enc in ("utf-8-sig", "cp1253", "latin-1"):  # cp1253: files saved by Greek Windows programs
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        existing = [l.strip() for l in self.t_words.get("1.0", "end").splitlines() if l.strip()]
        seen = {vocabulary.fold(w) for w in existing}
        added = []
        for line in text.splitlines():
            word = re.split(r"[;\t]|,(?=\S)", line, maxsplit=1)[0].strip().strip('"')
            if word and not word.startswith("#") and vocabulary.fold(word) not in seen:
                seen.add(vocabulary.fold(word))
                added.append(word)
        if added:
            self.t_words.delete("1.0", "end")
            self.t_words.insert("1.0", "\n".join(existing + added))
        self.status.configure(text=f"Προστέθηκαν {len(added)} λέξεις · πατήστε Αποθήκευση")

    def _copy_history(self) -> None:
        sel = self.hist.curselection()
        if not sel:
            return
        self.win.clipboard_clear()
        self.win.clipboard_append(self._hist_texts[sel[0]])
        self.status.configure(text="Αντιγράφηκε στο πρόχειρο")

    def _clear_history(self) -> None:
        if messagebox.askyesno(paths.APP_TITLE, "Διαγραφή όλου του ιστορικού;", parent=self.win):
            self.app.history.clear()
            self.refresh_history()

    def _collect(self) -> config.Settings | None:
        mods = [m for m in ("Ctrl", "Alt", "Shift", "Win") if self.v_mods[m].get()]
        combo = "+".join(mods + [self.v_key.get()])
        try:
            _m, _vk, combo = parse(combo)
        except HotkeyError as e:
            messagebox.showerror(paths.APP_TITLE, f"Μη έγκυρη συντόμευση: {e}", parent=self.win)
            return None
        s = self.app.settings.copy()
        s.hotkey = combo
        s.mode = self.v_mode.get()
        mic = self.v_mic.get()
        s.microphone = "" if mic == DEFAULT_MIC else mic
        s.sounds = self.v_sounds.get()
        s.start_with_windows = self.v_autostart.get()
        s.model = _value(self.model_pairs, self.v_model.get())
        s.language = _value(LANGUAGES, self.v_lang.get())
        s.medical_vocabulary = self.v_medical.get()
        s.second_pass = _value(SECOND_PASS, self.v_second.get())
        s.device = _value(DEVICES, self.v_device.get())
        try:
            s.beam_size = max(1, min(10, int(self.v_beam.get())))
        except (tk.TclError, ValueError):
            pass
        s.unload_after_minutes = _value(UNLOAD, self.v_unload.get())
        s.custom_words = [l.strip() for l in self.t_words.get("1.0", "end").splitlines() if l.strip()]
        s.replacements = [l.strip() for l in self.t_repl.get("1.0", "end").splitlines() if l.strip()]
        s.spoken_punctuation = self.v_spoken.get()
        s.trailing_space = self.v_space.get()
        s.target = self.v_target.get()
        s.paste_method = self.v_method.get()
        s.restore_clipboard = self.v_restore.get()
        s.auto_enter = self.v_enter.get()
        s.overlay_position = _value(POSITIONS, self.v_pos.get())
        s.mic_button = self.v_button.get()
        s.mic_button_only_over = self.v_only.get().strip()
        try:
            s.history_limit = max(0, min(5000, int(self.v_hist.get())))
        except (tk.TclError, ValueError):
            pass
        return config.from_dict(dataclasses.asdict(s))  # same validation as the file

    def save(self) -> None:
        s = self._collect()
        if s is None:
            return
        self.app.apply_settings(s)
        self.status.configure(text="Αποθηκεύτηκε ✓")
        self.win.after(2500, lambda: self.alive and self.status.configure(text=""))

    def close(self) -> None:
        self.alive = False
        self.win.destroy()
        self.app.settings_closed()
