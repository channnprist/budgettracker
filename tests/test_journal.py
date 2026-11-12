"""Tests for finance journal core behavior."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from finance_journal.journal import FinanceJournal
from finance_journal.models import Entry, EntryType, parse_date
from finance_journal.storage import JournalStore


@pytest.fixture
def journal(tmp_path: Path) -> FinanceJournal:
    return FinanceJournal(JournalStore(tmp_path / "entries.json"))


def test_add_and_balance(journal: FinanceJournal) -> None:
    journal.add(
        Entry(
            amount=1000,
            category="salary",
            note="January",
            entry_type=EntryType.INCOME,
            entry_date=date(2026, 1, 1),
        )
    )
    journal.add(
        Entry(
            amount=250.5,
            category="food",
            note="lunch",
            entry_type=EntryType.EXPENSE,
            entry_date=date(2026, 1, 2),
        )
    )
    summary = journal.summarize()
    assert summary.income == 1000
    assert summary.expense == 250.5
    assert summary.balance == 749.5
    assert summary.count == 2
    assert summary.by_category["food"] == -250.5


def test_filter_by_month(journal: FinanceJournal) -> None:
    journal.add(
        Entry(500, "side-gig", "", EntryType.INCOME, date(2026, 1, 10))
    )
    journal.add(
        Entry(80, "transport", "", EntryType.EXPENSE, date(2026, 2, 3))
    )
    jan = journal.list_entries(month="2026-01")
    assert len(jan) == 1
    assert jan[0].category == "side-gig"
    feb = journal.summarize(month="2026-02")
    assert feb.balance == -80


def test_delete_and_persist(tmp_path: Path) -> None:
    path = tmp_path / "entries.json"
    j1 = FinanceJournal(JournalStore(path))
    entry = j1.add(
        Entry(40, "coffee", "morning", EntryType.EXPENSE, date(2026, 3, 1))
    )
    assert j1.delete(entry.id) is True
    assert j1.delete("missing") is False

    j2 = FinanceJournal(JournalStore(path))
    assert j2.entries == []


def test_reject_invalid_amount() -> None:
    with pytest.raises(ValueError):
        Entry(0, "x", "", EntryType.INCOME, date.today())
    with pytest.raises(ValueError):
        Entry(-1, "x", "", EntryType.INCOME, date.today())


def test_parse_date_defaults_today() -> None:
    assert parse_date("") == date.today()
    assert parse_date("2026-11-12") == date(2026, 11, 12)
