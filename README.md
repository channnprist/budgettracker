# Finance Journal

A simple CLI for logging income and expenses to a JSON file.  
**Ruins of Harness** submission — the program plus the agent harness notes.

## Quick start

```bash
# add income
python3 -m finance_journal add income 15000 salary -n "November" -d 2026-11-01

# add expense
python3 -m finance_journal add expense 320 food -n "dinner"

# list / summarize / balance
python3 -m finance_journal list
python3 -m finance_journal summary -m 2026-11
python3 -m finance_journal balance
```

Default store: `~/.finance_journal/entries.json`  
Override with `--db path/to/file.json`

## Commands

| Command | Purpose |
|---|---|
| `add` | Add an income/expense entry (`in`/`out` aliases work) |
| `list` | List entries; filter with `-t`, `-c`, `-m` |
| `summary` | Income, expense, balance, and totals by category |
| `delete` | Delete by id |
| `categories` | List category names |
| `balance` | Show current balance |

## Tests

```bash
python3 -m pip install -r requirements.txt
python3 -m pytest -q
```

## Harness docs

Prompts given to the agent, in order, plus how each result was checked:

- [`docs/HARNESS.md`](docs/HARNESS.md)
- [`docs/HARNESS.txt`](docs/HARNESS.txt)
