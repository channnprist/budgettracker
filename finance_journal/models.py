"""Data models for finance journal entries."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import uuid4


class EntryType(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"


@dataclass
class Entry:
    """One money journal line: income or expense."""

    amount: float
    category: str
    note: str
    entry_type: EntryType
    entry_date: date
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = uuid4().hex[:12]
        if isinstance(self.entry_type, str):
            self.entry_type = EntryType(self.entry_type)
        if isinstance(self.entry_date, str):
            self.entry_date = date.fromisoformat(self.entry_date)
        if self.amount <= 0:
            raise ValueError("amount must be greater than zero")
        if not self.category.strip():
            raise ValueError("category is required")

    def signed_amount(self) -> float:
        """Positive for income, negative for expense."""
        if self.entry_type is EntryType.INCOME:
            return self.amount
        return -self.amount

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["entry_type"] = self.entry_type.value
        payload["entry_date"] = self.entry_date.isoformat()
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Entry:
        return cls(
            id=data.get("id", ""),
            amount=float(data["amount"]),
            category=str(data["category"]),
            note=str(data.get("note", "")),
            entry_type=EntryType(data["entry_type"]),
            entry_date=date.fromisoformat(str(data["entry_date"])),
        )


def parse_date(value: str | None) -> date:
    """Parse YYYY-MM-DD or return today when blank."""
    if value is None or not value.strip():
        return date.today()
    return date.fromisoformat(value.strip())


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
