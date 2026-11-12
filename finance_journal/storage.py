"""JSON file storage for journal entries."""

from __future__ import annotations

import json
from pathlib import Path

from .models import Entry


class JournalStore:
    """Load and save entries from a JSON file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> list[Entry]:
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError(f"invalid journal file: {self.path}")
        return [Entry.from_dict(item) for item in raw]

    def save(self, entries: list[Entry]) -> None:
        payload = [entry.to_dict() for entry in entries]
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
