"""The last N dictations, one JSON object per line, on this PC only. No audio is kept."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path

from . import paths

log = logging.getLogger(__name__)


class History:
    def __init__(self, path: Path | None = None):
        self.path = Path(path or paths.HISTORY_FILE)
        self._lock = threading.Lock()

    def add(self, text: str, limit: int, **extra) -> None:
        if limit <= 0 or not text.strip():
            return
        entry = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "text": text.strip(), **extra}
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                entries = self._read()
                if len(entries) > limit:
                    self._write(entries[-limit:])
            except OSError as e:
                log.warning("history not saved: %s", e)

    def entries(self) -> list[dict]:
        with self._lock:
            return self._read()

    def clear(self) -> None:
        with self._lock:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass

    def _read(self) -> list[dict]:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []
        out = []
        for line in lines:
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                out.append(item)
        return out

    def _write(self, entries: list[dict]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries), encoding="utf-8")
        os.replace(tmp, self.path)
