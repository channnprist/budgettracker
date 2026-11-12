# The Harness — Ruins of Harness

Every prompt given to the coding agent, in order, and how the output was checked.  
Project: **Finance Journal**  
Agent: Cursor Cloud Agent (Composer)

---

## Goal set before starting

Build a Python CLI that journals income and expenses, stores data in JSON,  
supports monthly summaries, and ships with tests.

Agreed scope (so the spirit does not do more than asked):
- No GUI / no web app
- No real bank integrations
- No database server — JSON file only
- Extra dependency allowed: pytest only

---

## Prompt 1 — Task and boundaries

```text
Build a Python finance journal program.
Requirements:
1) CLI to add income/expense (amount, category, note, date)
2) List entries; filter by month / category / type
3) Summarize income, expense, balance, and totals by category
4) Persist to a JSON file
5) Include unit tests

Constraints:
- Do not build a web app or GUI
- Do not add dependencies other than pytest for tests
- Package name must be finance_journal
```

**Harness / check:**
- Confirm a package was created, not one messy script
- Confirm no Flask/Django/SQLite server appeared
- Read `models.py` and verify amount must be > 0

---

## Prompt 2 — Lock the CLI contract

```text
Design the CLI to support only these commands:
  python -m finance_journal add income|expense|in|out AMOUNT CATEGORY [-n NOTE] [-d YYYY-MM-DD]
  python -m finance_journal list [-t income|expense] [-c CATEGORY] [-m YYYY-MM]
  python -m finance_journal summary [-m YYYY-MM] [--start DATE] [--end DATE]
  python -m finance_journal delete ID
  python -m finance_journal categories
  python -m finance_journal balance
  --db PATH to choose the store file

Do not add other commands without asking first.
```

**Harness / check:**
- Run `python3 -m finance_journal --help` and confirm only the listed commands
- Try `add` without a category — argparse must error

---

## Prompt 3 — Require tests before trusting output

```text
Write pytest coverage for at least:
- add income + expense, then balance is correct
- filter by month
- delete an entry and persist to disk
- amount <= 0 raises ValueError
- CLI smoke: add → list → summary → balance → categories

Run the full suite and report the pytest result.
```

**Harness / check:**
```bash
python3 -m pytest -q
```
Expected: all tests pass

---

## Prompt 4 — Reduce guessing

```text
Do not hardcode paths under /tmp.
Default --db to ~/.finance_journal/entries.json
User-facing messages in English; error lines must start with "error:"
Do not add budget goals / recurring payments / charts in this round.
```

**Harness / check:**
- Grep for budget, chart, recurring in core logic — should not appear
- Confirm `DEFAULT_DB` in `cli.py`

---

## Prompt 5 — Manual harness

```text
Use a temporary file and run this demo:
1) add salary income 15000
2) add food expense 320
3) add transport expense 80
4) summary for that month
5) delete the food entry, then summary again
Show the real output.
```

**Harness / check:** verify the math by hand
- Before delete: balance = 15000 - 320 - 80 = 14600
- After deleting food: balance = 15000 - 80 = 14920

---

## Where the spirit overreaches (lesson from this ruin)

| Spirit habit | How to harness it |
|---|---|
| Wants a web dashboard | Lock scope in Prompt 1: “no web app” |
| Guesses the file schema | Require `Entry.to_dict` / `from_dict` plus a persist test |
| Forgets amount = 0 edge case | Ask for an explicit negative test |
| Adds too many CLI commands | Send a closed allow-list of commands |

---

## Verification evidence (submission run)

```text
$ python3 -m pytest -q
.......                                                                  [100%]
7 passed in 0.03s

summary for 2026-11 (before delete)
income:   15,000.00 USD
expense:  400.00 USD
balance:  14,600.00 USD   # = 15000 - 320 - 80

summary for 2026-11 (after deleting food)
income:   15,000.00 USD
expense:  80.00 USD
balance:  14,920.00 USD   # = 15000 - 80
```

## Checklist before submit

- [x] Program delivered as `.py` files
- [x] Harness doc (this file) lists prompts in order
- [x] Tests pass
- [x] Manual CLI demo math checked by hand
- [x] No out-of-scope features

---

## Short takeaway

The spirit writes fast, but needs a harness: **clear scope + tests + hand-checked numbers**.  
The result is an English CLI finance journal that records income/expenses, summarizes them, and stores JSON.
