"""Command-line interface for Finance Journal."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .journal import FinanceJournal
from .models import Entry, EntryType, parse_date
from .storage import JournalStore

DEFAULT_DB = Path.home() / ".finance_journal" / "entries.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="finance-journal",
        description="Finance Journal — simple income and expense tracker",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help=f"path to JSON store (default: {DEFAULT_DB})",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    add_p = sub.add_parser("add", help="add an entry")
    add_p.add_argument("entry_type", choices=["income", "expense", "in", "out"])
    add_p.add_argument("amount", type=float)
    add_p.add_argument("category")
    add_p.add_argument("-n", "--note", default="")
    add_p.add_argument("-d", "--date", default=None, help="YYYY-MM-DD (default: today)")

    list_p = sub.add_parser("list", help="list entries")
    list_p.add_argument("-t", "--type", choices=["income", "expense"], dest="entry_type")
    list_p.add_argument("-c", "--category")
    list_p.add_argument("-m", "--month", help="YYYY-MM")

    sum_p = sub.add_parser("summary", help="summarize income and expenses")
    sum_p.add_argument("-m", "--month", help="YYYY-MM")
    sum_p.add_argument("--start", help="YYYY-MM-DD")
    sum_p.add_argument("--end", help="YYYY-MM-DD")

    del_p = sub.add_parser("delete", help="delete an entry by id")
    del_p.add_argument("id")

    sub.add_parser("categories", help="list all categories")
    sub.add_parser("balance", help="show current balance")

    return parser


def _normalize_type(value: str) -> EntryType:
    mapping = {
        "income": EntryType.INCOME,
        "in": EntryType.INCOME,
        "expense": EntryType.EXPENSE,
        "out": EntryType.EXPENSE,
    }
    return mapping[value]


def _format_entry(entry: Entry) -> str:
    sign = "+" if entry.entry_type is EntryType.INCOME else "-"
    kind = "income" if entry.entry_type is EntryType.INCOME else "expense"
    note = f" | {entry.note}" if entry.note else ""
    return (
        f"{entry.id}  {entry.entry_date.isoformat()}  {kind:7}"
        f"  {sign}{entry.amount:,.2f}  [{entry.category}]{note}"
    )


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    journal = FinanceJournal(JournalStore(args.db))

    if args.command == "add":
        try:
            entry = Entry(
                amount=args.amount,
                category=args.category,
                note=args.note,
                entry_type=_normalize_type(args.entry_type),
                entry_date=parse_date(args.date),
            )
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        journal.add(entry)
        print("saved:")
        print(_format_entry(entry))
        return 0

    if args.command == "list":
        entry_type = EntryType(args.entry_type) if args.entry_type else None
        rows = journal.list_entries(
            entry_type=entry_type,
            category=args.category,
            month=args.month,
        )
        if not rows:
            print("no entries yet")
            return 0
        for row in rows:
            print(_format_entry(row))
        return 0

    if args.command == "summary":
        start = parse_date(args.start) if args.start else None
        end = parse_date(args.end) if args.end else None
        summary = journal.summarize(month=args.month, start=start, end=end)
        title = f"summary for {args.month}" if args.month else "summary (all)"
        print(title)
        for line in summary.to_lines():
            print(line)
        return 0

    if args.command == "delete":
        ok = journal.delete(args.id)
        if not ok:
            print(f"error: id not found: {args.id}", file=sys.stderr)
            return 1
        print(f"deleted: {args.id}")
        return 0

    if args.command == "categories":
        cats = journal.categories()
        if not cats:
            print("no categories yet")
            return 0
        for name in cats:
            print(name)
        return 0

    if args.command == "balance":
        summary = journal.summarize()
        print(f"balance: {summary.balance:,.2f} USD")
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
