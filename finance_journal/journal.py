"""Business logic for the finance journal."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from .models import Entry, EntryType
from .storage import JournalStore


@dataclass
class Summary:
    income: float
    expense: float
    balance: float
    by_category: dict[str, float]
    count: int

    def to_lines(self, currency: str = "USD") -> list[str]:
        lines = [
            f"entries:  {self.count}",
            f"income:   {self.income:,.2f} {currency}",
            f"expense:  {self.expense:,.2f} {currency}",
            f"balance:  {self.balance:,.2f} {currency}",
        ]
        if self.by_category:
            lines.append("by category:")
            for name, total in sorted(self.by_category.items(), key=lambda x: -abs(x[1])):
                lines.append(f"  - {name}: {total:,.2f} {currency}")
        return lines


class FinanceJournal:
    """Add, list, summarize, and delete money journal entries."""

    def __init__(self, store: JournalStore) -> None:
        self.store = store
        self._entries = store.load()

    @property
    def entries(self) -> list[Entry]:
        return list(self._entries)

    def add(self, entry: Entry) -> Entry:
        self._entries.append(entry)
        self._persist()
        return entry

    def delete(self, entry_id: str) -> bool:
        before = len(self._entries)
        self._entries = [e for e in self._entries if e.id != entry_id]
        if len(self._entries) == before:
            return False
        self._persist()
        return True

    def clear(self) -> int:
        count = len(self._entries)
        self._entries = []
        self._persist()
        return count

    def list_entries(
        self,
        *,
        entry_type: EntryType | None = None,
        category: str | None = None,
        month: str | None = None,
    ) -> list[Entry]:
        result = self._entries
        if entry_type is not None:
            result = [e for e in result if e.entry_type is entry_type]
        if category:
            needle = category.strip().lower()
            result = [e for e in result if e.category.lower() == needle]
        if month:
            result = [e for e in result if e.entry_date.strftime("%Y-%m") == month]
        return sorted(result, key=lambda e: (e.entry_date, e.id))

    def summarize(
        self,
        *,
        month: str | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> Summary:
        rows = self._entries
        if month:
            rows = [e for e in rows if e.entry_date.strftime("%Y-%m") == month]
        if start is not None:
            rows = [e for e in rows if e.entry_date >= start]
        if end is not None:
            rows = [e for e in rows if e.entry_date <= end]

        income = sum(e.amount for e in rows if e.entry_type is EntryType.INCOME)
        expense = sum(e.amount for e in rows if e.entry_type is EntryType.EXPENSE)
        by_category: dict[str, float] = defaultdict(float)
        for entry in rows:
            by_category[entry.category] += entry.signed_amount()
        return Summary(
            income=income,
            expense=expense,
            balance=income - expense,
            by_category=dict(by_category),
            count=len(rows),
        )

    def categories(self) -> list[str]:
        return sorted({e.category for e in self._entries}, key=str.lower)

    def _persist(self) -> None:
        self.store.save(self._entries)
