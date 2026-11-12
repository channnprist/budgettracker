# Personal Budget Tracker
#
# What it does
#   Tracks income and expenses, money you lent or borrowed, and
#   pay-first advances (จ่ายให้ไปก่อน), where you paid for other
#   people and are waiting to be paid back. It also splits a bill
#   item by item: shared items are divided equally, and a single item
#   can be assigned to one person. VAT and service charge are added
#   to each person in proportion to that person's subtotal.
#
# Data
#   Saved to budget_data.json in the same folder as this file, so it
#   is still there the next time you start the program.
#
# How to run
#   python3 mm.py
#
# The program uses only the Python standard library. Enter 0 in any
# menu to go back (or to leave, from the main menu).

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_PATH = Path(__file__).resolve().parent / "budget_data.json"
CENT = Decimal("0.01")
MONEY_LIMIT = Decimal("999999999.99")

INCOME_CATEGORIES = ["Salary", "Freelance", "Gift", "Investment", "Other"]
EXPENSE_CATEGORIES = [
    "Food",
    "Transport",
    "Utilities",
    "Entertainment",
    "Shopping",
    "Health",
    "Other",
]

KIND_LENT = "lent"
KIND_BORROWED = "borrowed"
KIND_ADVANCE = "advance"
KIND_LABEL = {
    KIND_LENT: "Lent",
    KIND_BORROWED: "Borrowed",
    KIND_ADVANCE: "Pay-first",
}

STATUS_FRIEND_BORROWED = "Friend borrowed"
STATUS_FRIEND_RETURNED = "Friend returned"
STATUS_USER_OWES = "User owes"
STATUS_SETTLED = "Debt settled"


class UserQuit(Exception):
    """The user pressed Ctrl+C or closed the input stream."""


# ---------------------------------------------------------------------------
# Money helpers
# ---------------------------------------------------------------------------

def D(value) -> Decimal:
    """Parse a stored or typed amount into cents.

    Raises InvalidOperation for blank, non-numeric, or non-finite values.
    """
    amount = Decimal(str(value).replace(",", "").strip())
    if not amount.is_finite():
        raise InvalidOperation("amount is not a finite number")
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def S(value) -> str:
    """Store money as a plain two-decimal string, never as a float."""
    return format(D(value), "f")


def fmt(value) -> str:
    """Format money for the screen, with thousands separators."""
    try:
        amount = D(value)
    except (InvalidOperation, ValueError, TypeError):
        return "?"
    return f"{amount:,.2f}"


def plain_number(value) -> str:
    text = format(D(value), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def fmt_rate(value) -> str:
    return f"{plain_number(value)}%"


def clip(text, width: int) -> str:
    value = "" if text is None else str(text)
    if len(value) <= width:
        return value
    if width <= 3:
        return value[:width]
    return value[: width - 3] + "..."


def today_iso() -> str:
    return date.today().isoformat()


def fmt_date(iso_value) -> str:
    try:
        parsed = datetime.strptime(str(iso_value), "%Y-%m-%d")
    except (TypeError, ValueError):
        return "?"
    return parsed.strftime("%d %b %Y")


def same_name(left, right) -> bool:
    return str(left).casefold() == str(right).casefold()


def status_for(kind: str, remaining: Decimal) -> str:
    """Map a balance to one of the four repayment statuses.

    Loans and pay-first advances are money other people owe the user.
    Borrowed records are money the user still has to repay.
    """
    if remaining > 0:
        if kind == KIND_BORROWED:
            return STATUS_USER_OWES
        return STATUS_FRIEND_BORROWED
    if kind == KIND_BORROWED:
        return STATUS_SETTLED
    return STATUS_FRIEND_RETURNED


def allocate_by_weight(total, weights: dict, order: list[str]) -> dict[str, Decimal]:
    """Split ``total`` across ``order`` in proportion to ``weights``.

    Shares are whole cents. The largest-remainder method keeps every
    share at or above zero and makes the shares add up to ``total``,
    including awkward cases such as 0.01 split across several people.
    A person whose weight is zero receives nothing unless every weight
    is zero, in which case the whole amount is returned as zeros when
    ``total`` is also zero.
    """
    amount = D(total)
    if amount < 0:
        raise InvalidOperation("cannot allocate a negative amount")
    names = list(order)
    if amount == 0 or not names:
        return {name: Decimal("0.00") for name in names}

    weight_sum = Decimal("0")
    clean_weights = {}
    for name in names:
        weight = D(weights.get(name, 0))
        if weight < 0:
            raise InvalidOperation("weight cannot be negative")
        clean_weights[name] = weight
        weight_sum += weight
    if weight_sum == 0:
        return {name: Decimal("0.00") for name in names}

    total_cents = int((amount * 100).to_integral_value(rounding=ROUND_HALF_UP))
    portions = []
    used = 0
    for name in names:
        exact = Decimal(total_cents) * clean_weights[name] / weight_sum
        base = int(exact.to_integral_value(rounding=ROUND_DOWN))
        portions.append((name, base, exact - Decimal(base)))
        used += base

    cents = {name: base for name, base, _fraction in portions}
    leftover = total_cents - used
    ranked = sorted(
        range(len(portions)),
        key=lambda index: (portions[index][2], -index),
        reverse=True,
    )
    cursor = 0
    while leftover > 0:
        name = portions[ranked[cursor % len(ranked)]][0]
        cents[name] += 1
        leftover -= 1
        cursor += 1

    return {name: (Decimal(cents[name]) / Decimal(100)) for name in names}


def calculate_split(people: list[str], items: list[dict], vat_rate, service_rate):
    """Build per-person subtotals, then add VAT and service on top.

    Each item is divided equally among the people assigned to it.
    Tax and service follow the subtotals, not a flat split, so someone
    who ordered more also covers more of the VAT and service charge.
    """
    if not people:
        raise ValueError("a split needs at least one person")
    if not items:
        raise ValueError("a split needs at least one item")

    subtotals = {person: Decimal("0.00") for person in people}
    detailed_items = []
    for item in items:
        price = D(item["price"])
        if price <= 0:
            raise ValueError("item price must be greater than zero")
        assigned = list(item["people"])
        if not assigned:
            raise ValueError("each item needs at least one person")
        unknown = [name for name in assigned if name not in subtotals]
        if unknown:
            raise ValueError("an item is assigned to someone not on the bill")
        shares = allocate_by_weight(
            price,
            {name: Decimal(1) for name in assigned},
            assigned,
        )
        for name, share in shares.items():
            subtotals[name] += share
        detailed_items.append(
            {
                "name": item["name"],
                "price": S(price),
                "people": assigned,
                "shares": {name: S(share) for name, share in shares.items()},
            }
        )

    subtotal = sum(subtotals.values(), Decimal("0.00"))
    vat_total = (subtotal * D(vat_rate) / Decimal(100)).quantize(
        CENT, rounding=ROUND_HALF_UP
    )
    service_total = (subtotal * D(service_rate) / Decimal(100)).quantize(
        CENT, rounding=ROUND_HALF_UP
    )
    vat_shares = allocate_by_weight(vat_total, subtotals, people)
    service_shares = allocate_by_weight(service_total, subtotals, people)

    rows = []
    for person in people:
        sub = subtotals[person]
        vat = vat_shares[person]
        service = service_shares[person]
        rows.append(
            {
                "person": person,
                "subtotal": S(sub),
                "vat": S(vat),
                "service": S(service),
                "total": S(sub + vat + service),
            }
        )
    grand = {
        "subtotal": S(subtotal),
        "vat": S(vat_total),
        "service": S(service_total),
        "total": S(subtotal + vat_total + service_total),
    }
    return detailed_items, rows, grand


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

class BudgetStore:
    """Load and save the tracker. Amounts are strings so JSON stays exact."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.data = self._empty()
        self.load()

    @staticmethod
    def _empty() -> dict:
        return {
            "version": 1,
            "transactions": [],
            "debts": [],
            "bills": [],
            "next_ids": {"transaction": 1, "debt": 1, "bill": 1},
        }

    def load(self) -> None:
        if not self.path.exists():
            self.data = self._empty()
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self.data = self._normalize(raw)
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            self._park_unreadable_file()
            self.data = self._empty()

    def _normalize(self, raw) -> dict:
        if not isinstance(raw, dict):
            raise ValueError("the save file is not a JSON object")
        data = self._empty()
        buckets = {
            "transaction": "transactions",
            "debt": "debts",
            "bill": "bills",
        }
        for bucket in buckets.values():
            value = raw.get(bucket, [])
            if not isinstance(value, list):
                raise ValueError(f"{bucket} must be a list")
            data[bucket] = value
        next_ids = raw.get("next_ids", {})
        if next_ids is None:
            next_ids = {}
        if not isinstance(next_ids, dict):
            raise ValueError("next_ids must be an object")
        for key, bucket in buckets.items():
            highest = 0
            for item in data[bucket]:
                if isinstance(item, dict) and isinstance(item.get("id"), int):
                    highest = max(highest, item["id"])
            stored = next_ids.get(key, 1)
            try:
                stored = int(stored)
            except (TypeError, ValueError):
                stored = 1
            data["next_ids"][key] = max(stored, highest + 1, 1)
        return data

    def _park_unreadable_file(self) -> None:
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        backup = self.path.with_name(f"{self.path.stem}.corrupt-{stamp}{self.path.suffix}")
        try:
            self.path.replace(backup)
        except OSError as err:
            print()
            print(f"  Could not read {self.path.name} ({err}).")
            print("  The file was left unchanged. Fix it, then run the program again.")
            raise SystemExit(1) from err
        print()
        print(f"  {self.path.name} could not be read.")
        print(f"  It was moved to {backup.name}, and a new empty tracker is starting.")

    def save(self) -> bool:
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            temporary.write_text(
                json.dumps(self.data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            temporary.replace(self.path)
            return True
        except OSError as err:
            print(f"  Warning: could not save data ({err}).")
            try:
                if temporary.exists():
                    temporary.unlink()
            except OSError:
                pass
            return False

    def new_id(self, kind: str) -> int:
        current = int(self.data["next_ids"][kind])
        self.data["next_ids"][kind] = current + 1
        return current

    def add_transaction(self, tx_type, category, amount, when, note, save=True) -> dict:
        record = {
            "id": self.new_id("transaction"),
            "type": tx_type,
            "category": category,
            "amount": S(amount),
            "note": note,
            "date": when,
        }
        self.data["transactions"].append(record)
        if save:
            self.save()
        return record

    def add_debt(self, kind, person, amount, when, note, save=True) -> dict:
        value = D(amount)
        record = {
            "id": self.new_id("debt"),
            "kind": kind,
            "person": person,
            "amount": S(value),
            "remaining": S(value),
            "status": status_for(kind, value),
            "note": note,
            "date": when,
            "payments": [],
        }
        self.data["debts"].append(record)
        if save:
            self.save()
        return record

    def add_bill(self, bill, save=True) -> dict:
        bill = dict(bill)
        bill["id"] = self.new_id("bill")
        self.data["bills"].append(bill)
        if save:
            self.save()
        return bill

    def valid_transactions(self):
        for record in self.data["transactions"]:
            parsed = _valid_transaction(record)
            if parsed is not None:
                yield parsed

    def valid_debts(self):
        for record in self.data["debts"]:
            parsed = _valid_debt(record)
            if parsed is not None:
                yield parsed

    def balance(self) -> Decimal:
        total = Decimal("0.00")
        for record, amount in self.valid_transactions():
            if record["type"] == "income":
                total += amount
            else:
                total -= amount
        return total.quantize(CENT, rounding=ROUND_HALF_UP)

    def debt_totals(self) -> dict[str, Decimal]:
        you_owe = Decimal("0.00")
        pending = Decimal("0.00")
        lent_out = Decimal("0.00")
        for record, _original, remaining in self.valid_debts():
            if remaining <= 0:
                continue
            if record["kind"] == KIND_BORROWED:
                you_owe += remaining
            elif record["kind"] == KIND_ADVANCE:
                pending += remaining
            elif record["kind"] == KIND_LENT:
                lent_out += remaining
        return {
            "you_owe": you_owe,
            "pending": pending,
            "lent_out": lent_out,
        }


def _valid_transaction(record):
    if not isinstance(record, dict):
        return None
    if record.get("type") not in ("income", "expense"):
        return None
    try:
        amount = D(record.get("amount"))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if amount < 0:
        return None
    return record, amount


def _valid_debt(record):
    if not isinstance(record, dict):
        return None
    if record.get("kind") not in KIND_LABEL:
        return None
    try:
        original = D(record.get("amount"))
        remaining = D(record.get("remaining"))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if original < 0 or remaining < 0:
        return None
    return record, original, remaining


def find_by_id(records, record_id: int):
    for record in records:
        if isinstance(record, dict) and record.get("id") == record_id:
            return record
    return None


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------

def prompt(text: str) -> str:
    try:
        return input(text).strip()
    except EOFError:
        print()
        raise UserQuit() from None
    except KeyboardInterrupt:
        print()
        raise UserQuit() from None


def pause() -> None:
    if sys.stdin.isatty():
        prompt("  Press Enter to continue. ")


def prompt_money(label: str) -> Decimal:
    while True:
        raw = prompt(label)
        if raw == "":
            print("  Please enter an amount, for example 150 or 150.50.")
            continue
        try:
            amount = Decimal(raw.replace(",", ""))
        except InvalidOperation:
            print("  That is not a number. Use digits, for example 250 or 99.50.")
            continue
        if not amount.is_finite():
            print("  That is not a usable amount.")
            continue
        if amount <= 0:
            print("  Amount must be greater than zero.")
            continue
        quantized = amount.quantize(CENT, rounding=ROUND_HALF_UP)
        if quantized <= 0:
            print("  Amount must be at least 0.01.")
            continue
        if quantized > MONEY_LIMIT:
            print("  That amount is too large.")
            continue
        return quantized


def prompt_rate(label: str, default: Decimal) -> Decimal:
    while True:
        raw = prompt(f"  {label} [{plain_number(default)}]: ")
        if raw == "":
            return D(default)
        try:
            rate = Decimal(raw.replace(",", "").rstrip("%"))
        except InvalidOperation:
            print("  Please enter a percent, for example 7 or 10.5.")
            continue
        if not rate.is_finite() or rate < 0 or rate > 100:
            print("  Enter a percent from 0 to 100.")
            continue
        return rate.quantize(CENT, rounding=ROUND_HALF_UP)


def prompt_date(label="  Date [today]: ") -> str:
    while True:
        raw = prompt(label)
        if raw == "":
            return today_iso()
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date().isoformat()
        except ValueError:
            print("  Use the form YYYY-MM-DD, for example 2026-11-07.")


def prompt_note() -> str:
    note = prompt("  Note (optional): ")
    if len(note) > 200:
        print("  The note was trimmed to 200 characters.")
        return note[:200]
    return note


def prompt_text(label: str, limit: int = 40) -> str:
    while True:
        value = prompt(label)
        if not value:
            print("  Please enter a value.")
            continue
        if len(value) > limit:
            print(f"  Please use {limit} characters or fewer.")
            continue
        return value


def prompt_id(label="  ID (0 to cancel): ") -> int | None:
    while True:
        raw = prompt(label)
        if raw == "" or raw == "0":
            return None
        if not raw.isdigit():
            print("  Please enter a numeric ID, or 0 to cancel.")
            continue
        value = int(raw)
        if value == 0:
            return None
        if value > 1_000_000_000:
            print("  That ID is not valid.")
            continue
        return value


def ask_yes_no(question: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    while True:
        raw = prompt(f"  {question} ({hint}): ").lower()
        if raw == "":
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("  Please answer y or n.")


def choose_category(presets: list[str], default: str) -> str:
    print()
    print("  Category")
    for index, name in enumerate(presets, start=1):
        print(f"    {index}  {name}")
    print(f"    {len(presets) + 1}  Custom")
    while True:
        raw = prompt(f"  Category [{default}]: ")
        if raw == "":
            return default
        if raw.isdigit():
            number = int(raw)
            if 1 <= number <= len(presets):
                return presets[number - 1]
            if number == len(presets) + 1:
                return prompt_text("  Custom category: ")
            print("  That number is not in the list.")
            continue
        if len(raw) > 40:
            print("  Please use 40 characters or fewer.")
            continue
        return raw


def read_person(label: str, existing: list[str], allow_blank: bool = False, default=None):
    while True:
        raw = prompt(label)
        if raw == "":
            if allow_blank:
                return ""
            if default is not None:
                raw = default
            else:
                print("  Please enter a name.")
                continue
        if "," in raw:
            print("  Enter one name, without a comma.")
            continue
        if len(raw) > 40:
            print("  Please use 40 characters or fewer.")
            continue
        if any(same_name(raw, name) for name in existing):
            print("  That person is already on the list.")
            continue
        return raw


def show_menu(options: list[tuple[str, str]]) -> str:
    print()
    for key, label in options:
        print(f"  {key:>2}   {label}")
    print()
    return prompt("  Choose: ")


# ---------------------------------------------------------------------------
# Screen pieces
# ---------------------------------------------------------------------------

def header(text: str) -> None:
    print()
    print(f"  {text}")
    print(f"  {'-' * len(text)}")


def print_kv(label: str, value: str) -> None:
    print(f"  {label:<32}{value:>14}")


def sorted_transactions(store: BudgetStore):
    rows = [record for record, _amount in store.valid_transactions()]
    return sorted(rows, key=lambda record: (record.get("date", ""), record.get("id", 0)), reverse=True)


def signed_amount(tx_type, amount) -> str:
    """Keep the sign against the number so columns line up."""
    sign = "+" if tx_type == "income" else "-"
    return f"{sign}{fmt(amount)}"


def print_transaction_row(record, amount=None) -> None:
    if amount is None:
        amount = record.get("amount")
    note = record.get("note") or ""
    note_text = f"  {clip(note, 22)}" if note else ""
    print(
        f"  {record.get('id', '?'):>4}  "
        f"{fmt_date(record.get('date')):<12}"
        f"{str(record.get('type', '')).capitalize():<9}"
        f"{clip(record.get('category', ''), 14):<14}"
        f"{signed_amount(record.get('type'), amount):>13}"
        f"{note_text}"
    )


def print_transactions(records) -> None:
    print()
    print(f"  {'ID':>4}  {'Date':<12}{'Type':<9}{'Category':<14}{'Amount':>13}  Note")
    print(f"  {'-' * 68}")
    if not records:
        print("  No transactions to show.")
        return
    income = Decimal("0.00")
    expense = Decimal("0.00")
    for record in records:
        try:
            amount = D(record.get("amount"))
        except (InvalidOperation, ValueError, TypeError):
            print(f"  {record.get('id', '?'):>4}  This record has an invalid amount and was skipped.")
            continue
        print_transaction_row(record, amount)
        if record.get("type") == "income":
            income += amount
        elif record.get("type") == "expense":
            expense += amount
    print(f"  {'-' * 68}")
    print_kv("Income in this list", fmt(income))
    print_kv("Expenses in this list", fmt(expense))
    print_kv("Net in this list", fmt(income - expense))


def print_debt_table(rows) -> None:
    print()
    print(f"  {'ID':>4}  {'Kind':<10} {'Person':<16} {'Remaining':>12}  Status")
    print(f"  {'-' * 62}")
    if not rows:
        print("  No records to show.")
        return
    for record, _original, remaining in rows:
        print(
            f"  {record.get('id', '?'):>4}  "
            f"{KIND_LABEL.get(record.get('kind'), '?'):<10} "
            f"{clip(record.get('person', ''), 16):<16} "
            f"{fmt(remaining):>12}  "
            f"{record.get('status', '')}"
        )


def print_status_guide() -> None:
    print()
    print("  Status")
    print("    Friend borrowed   Someone still owes you")
    print("    Friend returned   A loan or advance was paid back")
    print("    User owes         You still owe someone")
    print("    Debt settled      You finished paying what you owed")


def category_totals(store: BudgetStore, tx_type: str) -> list[tuple[str, Decimal]]:
    totals: dict[str, Decimal] = {}
    labels: dict[str, str] = {}
    for record, amount in store.valid_transactions():
        if record["type"] != tx_type:
            continue
        category = str(record.get("category") or "Other")
        key = category.casefold()
        labels.setdefault(key, category)
        totals[key] = totals.get(key, Decimal("0.00")) + amount
    ranked = sorted(totals, key=lambda key: (-totals[key], labels[key].casefold()))
    return [(labels[key], totals[key]) for key in ranked]


def print_breakdown(title: str, pairs: list[tuple[str, Decimal]]) -> None:
    print()
    print(f"  {title}")
    if not pairs:
        print("    None yet.")
        return
    for name, amount in pairs:
        print(f"    {clip(name, 22):<22}{fmt(amount):>14}")


def grouped_open_debts(store: BudgetStore, kinds: set[str]) -> list[tuple[str, Decimal]]:
    totals: dict[str, Decimal] = {}
    labels: dict[str, str] = {}
    for record, _original, remaining in store.valid_debts():
        if remaining <= 0 or record["kind"] not in kinds:
            continue
        person = str(record.get("person") or "Unknown")
        key = person.casefold()
        labels.setdefault(key, person)
        totals[key] = totals.get(key, Decimal("0.00")) + remaining
    names = sorted(labels, key=lambda key: labels[key].casefold())
    return [(labels[key], totals[key]) for key in names]


def print_people_totals(title: str, pairs: list[tuple[str, Decimal]]) -> None:
    print()
    print(f"  {title}")
    if not pairs:
        print("    None.")
        return
    for name, amount in pairs:
        print(f"    {clip(name, 22):<22}{fmt(amount):>14}")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def show_dashboard(store: BudgetStore, detailed: bool = False) -> None:
    totals = store.debt_totals()
    header("Summary" if not detailed else "Full report")
    print()
    print_kv("Balance", fmt(store.balance()))
    print_kv("Active debts (you owe)", fmt(totals["you_owe"]))
    print_kv("Pending reimbursements", fmt(totals["pending"]))
    print_kv("Lent out, not returned", fmt(totals["lent_out"]))

    if detailed:
        print_breakdown("Income by category", category_totals(store, "income"))
        print_breakdown("Expenses by category", category_totals(store, "expense"))
        print_people_totals(
            "Who still owes you",
            grouped_open_debts(store, {KIND_LENT, KIND_ADVANCE}),
        )
        print_people_totals(
            "Who you still owe",
            grouped_open_debts(store, {KIND_BORROWED}),
        )

    recent = sorted_transactions(store)
    limit = 10 if detailed else 5
    print()
    print("  Recent transactions")
    if not recent:
        print("    No transactions yet.")
        return
    shown = recent[:limit]
    for record in shown:
        print_transaction_row(record)
    hidden = len(recent) - len(shown)
    if hidden > 0:
        print(f"    {hidden} older transaction{'s' if hidden != 1 else ''} not shown.")


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

def add_money(store: BudgetStore, tx_type: str) -> None:
    income = tx_type == "income"
    header("Add income" if income else "Add expense")
    presets = INCOME_CATEGORIES if income else EXPENSE_CATEGORIES
    category = choose_category(presets, presets[0])
    amount = prompt_money("  Amount: ")
    when = prompt_date()
    note = prompt_note()
    record = store.add_transaction(tx_type, category, amount, when, note)
    print()
    print(f"  Saved transaction #{record['id']}.")
    print(f"  Balance is now {fmt(store.balance())}.")
    pause()


def show_one_transaction(record) -> None:
    header(f"Transaction #{record.get('id')}")
    print()
    print_kv("Type", str(record.get("type", "")).capitalize())
    print_kv("Category", clip(record.get("category", ""), 24))
    print_kv("Amount", signed_amount(record.get("type"), record.get("amount")))
    print_kv("Date", fmt_date(record.get("date")))
    print_kv("Note", clip(record.get("note") or "-", 24))


def browse_transactions(store: BudgetStore) -> None:
    while True:
        header("Transactions")
        choice = show_menu(
            [
                ("1", "All"),
                ("2", "Income only"),
                ("3", "Expenses only"),
                ("4", "One category"),
                ("0", "Back"),
            ]
        )
        if choice == "0":
            return
        records = sorted_transactions(store)
        if choice == "1":
            selected = records
            title = "All transactions"
        elif choice == "2":
            selected = [record for record in records if record["type"] == "income"]
            title = "Income"
        elif choice == "3":
            selected = [record for record in records if record["type"] == "expense"]
            title = "Expenses"
        elif choice == "4":
            category = prompt_text("  Category name: ")
            selected = [
                record
                for record in records
                if same_name(record.get("category", ""), category)
            ]
            title = f"Category: {category}"
        else:
            print("  Please choose a number from the menu.")
            continue

        header(title)
        print_transactions(selected)
        print()
        print("  Enter an ID to view it, or 0 to go back.")
        while True:
            selected_id = prompt_id()
            if selected_id is None:
                break
            record = find_by_id(store.data["transactions"], selected_id)
            if _valid_transaction(record) is None:
                print("  No transaction uses that ID.")
                continue
            show_one_transaction(record)
            pause()
            break


# ---------------------------------------------------------------------------
# Debts, loans, and pay-first advances
# ---------------------------------------------------------------------------

def add_debt_flow(store: BudgetStore, kind: str) -> None:
    if kind == KIND_LENT:
        header("Lend money")
        print()
        print("  A friend is borrowing from you and still has to pay it back.")
        person_label = "  Friend's name: "
        cash_question = "Subtract this from your balance as an expense?"
        cash_type = "expense"
        cash_category = "Lent"
        note_default = "Loan"
    elif kind == KIND_BORROWED:
        header("Borrow money")
        print()
        print("  You are borrowing, so this stays open until you pay it back.")
        person_label = "  Friend's name: "
        cash_question = "Add this to your balance as income?"
        cash_type = "income"
        cash_category = "Borrowed"
        note_default = "Borrowed"
    else:
        header("Pay-first / advance")
        print()
        print("  จ่ายให้ไปก่อน: you paid the full amount for someone else")
        print("  and you are waiting for them to pay you back.")
        person_label = "  Who owes you?: "
        cash_question = "Subtract this from your balance as an expense?"
        cash_type = "expense"
        cash_category = "Advance"
        note_default = "Paid first"

    person = read_person(person_label, [])
    amount = prompt_money("  Amount: ")
    when = prompt_date()
    note = prompt_note()
    if not note:
        note = note_default
    print()
    print("  Answer n if this cash movement is already in your transactions.")
    record_cash = ask_yes_no(cash_question, default=True)

    debt = store.add_debt(kind, person, amount, when, note, save=False)
    if record_cash:
        cash_note = f"{note} ({person})"
        store.add_transaction(cash_type, cash_category, amount, when, cash_note, save=False)
    store.save()

    print()
    print(f"  Saved {KIND_LABEL[kind].lower()} #{debt['id']} for {person}.")
    print(f"  Status: {debt['status']}. Remaining {fmt(debt['remaining'])}.")
    print(f"  Balance is now {fmt(store.balance())}.")
    pause()


def show_debt_detail(record) -> None:
    parsed = _valid_debt(record)
    if parsed is None:
        print("  This record is incomplete and cannot be shown.")
        return
    record, original, remaining = parsed
    header(f"{KIND_LABEL[record['kind']]} #{record['id']}")
    print()
    print_kv("Person", clip(record.get("person", ""), 24))
    print_kv("Status", str(record.get("status", "")))
    print_kv("Original", fmt(original))
    print_kv("Remaining", fmt(remaining))
    print_kv("Opened", fmt_date(record.get("date")))
    print_kv("Note", clip(record.get("note") or "-", 24))
    payments = record.get("payments")
    print()
    print("  Repayments")
    if not isinstance(payments, list) or not payments:
        print("    None yet.")
        return
    for payment in payments:
        if not isinstance(payment, dict):
            print("    One repayment could not be read.")
            continue
        moved = "added to balance" if payment.get("in_balance") else "status only"
        note = payment.get("note") or ""
        suffix = f"  {clip(note, 20)}" if note else ""
        print(
            f"    {fmt_date(payment.get('date')):<12}"
            f"{fmt(payment.get('amount')):>12}  {moved}{suffix}"
        )


def record_repayment(store: BudgetStore) -> None:
    header("Record a repayment")
    open_rows = [
        (record, original, remaining)
        for record, original, remaining in store.valid_debts()
        if remaining > 0
    ]
    print_debt_table(open_rows)
    if not open_rows:
        pause()
        return
    print()
    selected_id = prompt_id("  Debt ID (0 to cancel): ")
    if selected_id is None:
        return
    record = find_by_id(store.data["debts"], selected_id)
    parsed = _valid_debt(record)
    if parsed is None:
        print("  No debt, loan, or advance uses that ID.")
        pause()
        return
    record, _original, remaining = parsed
    if remaining <= 0:
        print(f"  #{record['id']} is already {record.get('status', 'settled')}.")
        pause()
        return

    print()
    print(f"  {record.get('person')}  |  remaining {fmt(remaining)}  |  {record.get('status')}")
    while True:
        amount = prompt_money("  Amount received or paid: ")
        if amount > remaining:
            print(f"  That is more than the remaining {fmt(remaining)}.")
            continue
        break
    when = prompt_date()
    note = prompt_note()
    print()
    if record["kind"] == KIND_BORROWED:
        print("  This is money leaving you, to pay back what you owe.")
    else:
        print("  This is money coming back to you.")
    in_balance = ask_yes_no("Add this cash movement to the balance?", default=True)

    new_remaining = (remaining - amount).quantize(CENT, rounding=ROUND_HALF_UP)
    record["remaining"] = S(new_remaining)
    record["status"] = status_for(record["kind"], new_remaining)
    if not isinstance(record.get("payments"), list):
        record["payments"] = []
    record["payments"].append(
        {
            "date": when,
            "amount": S(amount),
            "note": note,
            "in_balance": in_balance,
        }
    )
    if in_balance:
        person = record.get("person") or "someone"
        if record["kind"] == KIND_BORROWED:
            store.add_transaction(
                "expense",
                "Debt payment",
                amount,
                when,
                note or f"Repayment to {person}",
                save=False,
            )
        else:
            store.add_transaction(
                "income",
                "Reimbursement",
                amount,
                when,
                note or f"Repayment from {person}",
                save=False,
            )
    store.save()
    print()
    print(f"  Updated #{record['id']}. Status: {record['status']}.")
    print(f"  Remaining {fmt(record['remaining'])}. Balance {fmt(store.balance())}.")
    pause()


def list_debts(store: BudgetStore) -> None:
    header("All debts and advances")
    print_debt_table(list(store.valid_debts()))
    print_status_guide()
    print()
    print("  Enter an ID to view its history, or 0 to go back.")
    while True:
        selected_id = prompt_id()
        if selected_id is None:
            return
        record = find_by_id(store.data["debts"], selected_id)
        if _valid_debt(record) is None:
            print("  No debt, loan, or advance uses that ID.")
            continue
        show_debt_detail(record)
        pause()
        return


def show_who_owes(store: BudgetStore) -> None:
    header("Who owes whom")
    print_people_totals(
        "Friends who owe you (loans)",
        grouped_open_debts(store, {KIND_LENT}),
    )
    print_people_totals(
        "Waiting to be reimbursed (pay-first)",
        grouped_open_debts(store, {KIND_ADVANCE}),
    )
    print_people_totals(
        "People you owe",
        grouped_open_debts(store, {KIND_BORROWED}),
    )
    print_status_guide()

    print()
    print("  Open records")
    open_rows = [
        row for row in store.valid_debts() if row[2] > 0
    ]
    print_debt_table(open_rows)
    settled = [row for row in store.valid_debts() if row[2] <= 0]
    print()
    print(f"  Settled records: {len(settled)}")
    pause()


def debts_menu(store: BudgetStore) -> None:
    while True:
        header("Debts and advances")
        choice = show_menu(
            [
                ("1", "Lend money  (friend borrowed)"),
                ("2", "Borrow money  (you owe)"),
                ("3", "Pay-first / advance  (จ่ายให้ไปก่อน)"),
                ("4", "Record a repayment"),
                ("5", "List all records"),
                ("6", "Who owes whom"),
                ("0", "Back"),
            ]
        )
        if choice == "0":
            return
        if choice == "1":
            add_debt_flow(store, KIND_LENT)
        elif choice == "2":
            add_debt_flow(store, KIND_BORROWED)
        elif choice == "3":
            add_debt_flow(store, KIND_ADVANCE)
        elif choice == "4":
            record_repayment(store)
        elif choice == "5":
            list_debts(store)
        elif choice == "6":
            show_who_owes(store)
        else:
            print("  Please choose a number from the menu.")


# ---------------------------------------------------------------------------
# Bill splitting
# ---------------------------------------------------------------------------

def choose_item_people(people: list[str]) -> list[str]:
    print()
    print("  Who shares this item?")
    print("    1  Everyone, split equally")
    print("    2  Only some people (one person, or a chosen group)")
    while True:
        choice = prompt("  Choose: ")
        if choice == "1":
            return list(people)
        if choice == "2":
            return pick_people(people)
        print("  Please enter 1 or 2.")


def pick_people(people: list[str]) -> list[str]:
    print()
    for index, name in enumerate(people, start=1):
        print(f"    {index}  {name}")
    print("  Enter numbers separated by commas. Example: 1,3")
    while True:
        raw = prompt("  People: ")
        parts = [part.strip() for part in raw.split(",") if part.strip()]
        if not parts:
            print("  Choose at least one person.")
            continue
        chosen = []
        invalid = False
        for part in parts:
            if not part.isdigit() or int(part) < 1 or int(part) > len(people):
                print(f"  '{part}' is not a person number on this list.")
                invalid = True
                break
            name = people[int(part) - 1]
            if name not in chosen:
                chosen.append(name)
        if invalid:
            continue
        return chosen


def print_items(items: list[dict]) -> None:
    print()
    if not items:
        print("  No items yet.")
        return
    print(f"  {'#':>3}  {'Item':<22}{'Price':>12}  Shared by")
    print(f"  {'-' * 58}")
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            print(f"  {index:>3}  This item could not be read.")
            continue
        people = item.get("people") or []
        if not isinstance(people, list):
            people = [people]
        names = ", ".join(str(name) for name in people)
        print(
            f"  {index:>3}  "
            f"{clip(item.get('name', ''), 22):<22}"
            f"{fmt(item.get('price', '0')):>12}  "
            f"{names}"
        )


def add_item(people: list[str]) -> dict:
    name = prompt_text("  Item name: ")
    price = prompt_money("  Price: ")
    assigned = choose_item_people(people)
    return {"name": name, "price": S(price), "people": assigned}


def remove_item(items: list[dict]) -> None:
    print_items(items)
    selected = prompt_id("  Item number to remove (0 to cancel): ")
    if selected is None:
        return
    if selected < 1 or selected > len(items):
        print("  No item uses that number.")
        return
    removed = items.pop(selected - 1)
    print(f"  Removed {removed['name']}.")


def collect_items(people: list[str]) -> list[dict] | None:
    items: list[dict] = []
    while True:
        print_items(items)
        options = [("a", "Add an item")]
        if items:
            options.append(("d", "Remove an item"))
            options.append(("c", "Calculate the split"))
        options.append(("q", "Cancel"))
        choice = show_menu(options).lower()
        if choice == "a":
            items.append(add_item(people))
        elif choice == "d" and items:
            remove_item(items)
        elif choice == "c" and items:
            return items
        elif choice == "q":
            print("  Split cancelled. Nothing was saved.")
            return None
        else:
            print("  Please choose one of the letters above.")


def print_split_result(title, when, vat_rate, service_rate, items, rows, grand) -> None:
    header(title)
    print()
    print(f"  {fmt_date(when)}    VAT {fmt_rate(vat_rate)}    Service {fmt_rate(service_rate)}")
    print_items(items)
    print()
    print(f"  {'Person':<16}{'Subtotal':>12}{'VAT':>12}{'Service':>12}{'Total':>12}")
    print(f"  {'-' * 64}")
    try:
        for row in rows:
            print(
                f"  {clip(row['person'], 16):<16}"
                f"{fmt(row['subtotal']):>12}"
                f"{fmt(row['vat']):>12}"
                f"{fmt(row['service']):>12}"
                f"{fmt(row['total']):>12}"
            )
        share_sum = sum((D(row["total"]) for row in rows), Decimal("0.00"))
        grand_total = D(grand["total"])
    except (InvalidOperation, ValueError, TypeError, KeyError):
        print("  This split has a row that could not be read.")
        return
    print(f"  {'-' * 64}")
    print(
        f"  {'Total':<16}"
        f"{fmt(grand.get('subtotal', '0')):>12}"
        f"{fmt(grand.get('vat', '0')):>12}"
        f"{fmt(grand.get('service', '0')):>12}"
        f"{fmt(grand.get('total', '0')):>12}"
    )
    if share_sum != grand_total:
        print("  Warning: the shares do not add up to the grand total.")
    else:
        print()
        print("  Shared items are divided equally among the people on that item.")
        print("  VAT and service follow each person's subtotal.")


def apply_split_to_budget(store, bill, your_name, rows, grand, when) -> None:
    print()
    print("  1   I paid the full bill")
    print("      The total becomes an expense. Each other person gets")
    print("      a pay-first record until they reimburse you.")
    print("  2   Record only my share as an expense")
    print("  3   Save the split only")
    print()
    while True:
        choice = prompt("  Choose: ")
        if choice in ("1", "2", "3"):
            break
        print("  Please enter 1, 2, or 3.")

    bill["recorded"] = choice
    if choice == "3":
        print("  Split saved. Your balance was not changed.")
        return

    your_row = next((row for row in rows if same_name(row["person"], your_name)), None)
    if your_row is None:
        print("  Could not find your share, so no expense was added.")
        bill["recorded"] = "3"
        return

    category = choose_category(EXPENSE_CATEGORIES, "Food")
    note = prompt_note()
    title = bill["title"]
    if choice == "1":
        expense_amount = D(grand["total"])
        expense_note = note or f"{title} (paid in full)"
    else:
        expense_amount = D(your_row["total"])
        expense_note = note or f"{title} (my share)"

    if expense_amount > 0:
        expense = store.add_transaction(
            "expense",
            category,
            expense_amount,
            when,
            expense_note,
            save=False,
        )
        bill["expense_id"] = expense["id"]
        print()
        print(f"  Expense #{expense['id']} recorded for {fmt(expense_amount)}.")
    else:
        print()
        print("  Your share is 0.00, so no expense was added.")

    if choice == "1":
        opened = []
        for row in rows:
            if same_name(row["person"], your_name):
                continue
            owed = D(row["total"])
            if owed <= 0:
                continue
            debt = store.add_debt(
                KIND_ADVANCE,
                row["person"],
                owed,
                when,
                note or f"Pay-first for {title}",
                save=False,
            )
            opened.append(debt)
        bill["debt_ids"] = [debt["id"] for debt in opened]
        if opened:
            print("  Reimbursements opened:")
            for debt in opened:
                print(f"    #{debt['id']}  {debt['person']} owes {fmt(debt['remaining'])}")
        else:
            print("  Nobody else owes a share, so no reimbursement was opened.")
    print(f"  Balance is now {fmt(store.balance())}.")


def new_split(store: BudgetStore) -> None:
    header("Split a bill")
    print()
    print("  Enter items one by one.")
    print("  Share an item with everyone, or assign it to specific people.")
    print("  A shared item is split equally. Tax and service are proportional.")
    title = prompt_text("  Bill name: ", limit=60)
    when = prompt_date()
    print()
    print("  Who is on this bill? Include yourself first.")
    your_name = read_person("  Your name [Me]: ", [], default="Me")
    people = [your_name]
    while True:
        name = read_person("  Add a person (Enter to finish): ", people, allow_blank=True)
        if name == "":
            if len(people) < 2:
                print("  Add at least one other person.")
                continue
            break
        people.append(name)
        print(f"  On the bill: {', '.join(people)}")

    vat_rate = prompt_rate("VAT %", Decimal("7"))
    service_rate = prompt_rate("Service charge %", Decimal("10"))
    items = collect_items(people)
    if items is None:
        pause()
        return

    try:
        detailed_items, rows, grand = calculate_split(people, items, vat_rate, service_rate)
    except (InvalidOperation, ValueError) as err:
        print(f"  The split could not be calculated ({err}).")
        pause()
        return

    print_split_result(title, when, vat_rate, service_rate, detailed_items, rows, grand)
    print()
    if not ask_yes_no("Save this split?", default=True):
        print("  Discarded. Nothing was saved.")
        pause()
        return

    bill = {
        "title": title,
        "date": when,
        "your_name": your_name,
        "vat_rate": S(vat_rate),
        "service_rate": S(service_rate),
        "people": people,
        "items": detailed_items,
        "shares": rows,
        "grand": grand,
        "recorded": "3",
    }
    apply_split_to_budget(store, bill, your_name, rows, grand, when)
    saved = store.add_bill(bill)
    print(f"  Split #{saved['id']} saved.")
    pause()


def show_saved_bill(bill) -> None:
    if not isinstance(bill, dict) or not isinstance(bill.get("shares"), list):
        print("  This saved split is incomplete and cannot be shown.")
        return
    grand = bill.get("grand") if isinstance(bill.get("grand"), dict) else {}
    items = bill.get("items") if isinstance(bill.get("items"), list) else []
    print_split_result(
        f"#{bill.get('id')}  {bill.get('title', 'Split')}",
        bill.get("date"),
        bill.get("vat_rate", "0"),
        bill.get("service_rate", "0"),
        items,
        bill.get("shares"),
        {
            "subtotal": grand.get("subtotal", "0"),
            "vat": grand.get("vat", "0"),
            "service": grand.get("service", "0"),
            "total": grand.get("total", "0"),
        },
    )
    recorded = str(bill.get("recorded", "3"))
    meaning = {
        "1": "You paid the full bill and opened reimbursements.",
        "2": "Only your share was recorded as an expense.",
        "3": "Saved as a calculation only.",
    }
    print()
    print(f"  {meaning.get(recorded, 'Saved.')}")


def view_splits(store: BudgetStore) -> None:
    header("Saved splits")
    bills = [bill for bill in store.data["bills"] if isinstance(bill, dict)]
    print()
    if not bills:
        print("  No saved splits yet.")
        pause()
        return
    print(f"  {'ID':>4}  {'Date':<12}{'Title':<24}{'Total':>12}")
    print(f"  {'-' * 56}")
    for bill in bills:
        grand = bill.get("grand") if isinstance(bill.get("grand"), dict) else {}
        print(
            f"  {bill.get('id', '?'):>4}  "
            f"{fmt_date(bill.get('date')):<12}"
            f"{clip(bill.get('title', ''), 24):<24}"
            f"{fmt(grand.get('total', '0')):>12}"
        )
    print()
    selected_id = prompt_id("  Split ID (0 to cancel): ")
    if selected_id is None:
        return
    bill = find_by_id(store.data["bills"], selected_id)
    if bill is None:
        print("  No saved split uses that ID.")
        pause()
        return
    show_saved_bill(bill)
    pause()


def bills_menu(store: BudgetStore) -> None:
    while True:
        header("Split a bill")
        choice = show_menu(
            [
                ("1", "New itemized split"),
                ("2", "View a saved split"),
                ("0", "Back"),
            ]
        )
        if choice == "0":
            return
        if choice == "1":
            new_split(store)
        elif choice == "2":
            view_splits(store)
        else:
            print("  Please choose a number from the menu.")


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------

def run_app(store: BudgetStore) -> None:
    header("Personal Budget Tracker")
    print()
    print("  Income, expenses, loans, and shared bills.")
    print("  Pay-first (จ่ายให้ไปก่อน) stays open until you are repaid.")
    print("  Enter 0 to go back. Amounts must be greater than zero.")
    while True:
        show_dashboard(store)
        choice = show_menu(
            [
                ("1", "Full report"),
                ("2", "Add income"),
                ("3", "Add expense"),
                ("4", "Transactions"),
                ("5", "Debts and advances"),
                ("6", "Split a bill"),
                ("0", "Exit"),
            ]
        )
        if choice == "0":
            return
        if choice == "1":
            show_dashboard(store, detailed=True)
            pause()
        elif choice == "2":
            add_money(store, "income")
        elif choice == "3":
            add_money(store, "expense")
        elif choice == "4":
            browse_transactions(store)
        elif choice == "5":
            debts_menu(store)
        elif choice == "6":
            bills_menu(store)
        else:
            print("  Please choose a number from the menu.")


def main() -> None:
    store = BudgetStore(DATA_PATH)
    try:
        run_app(store)
    except UserQuit:
        print("  Stopping.")
    store.save()
    print(f"  Data saved to {store.path.name}.")
    print("  Goodbye.")


if __name__ == "__main__":
    main()
