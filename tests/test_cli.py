"""CLI smoke tests."""

from __future__ import annotations

from pathlib import Path

from finance_journal.cli import run


def test_cli_add_list_summary(tmp_path: Path, capsys) -> None:
    db = tmp_path / "db.json"

    assert (
        run(
            [
                "--db",
                str(db),
                "add",
                "income",
                "5000",
                "salary",
                "-n",
                "November",
                "-d",
                "2026-11-01",
            ]
        )
        == 0
    )
    assert (
        run(
            [
                "--db",
                str(db),
                "add",
                "out",
                "120",
                "food",
                "-d",
                "2026-11-02",
            ]
        )
        == 0
    )
    assert run(["--db", str(db), "list", "-m", "2026-11"]) == 0
    assert run(["--db", str(db), "summary", "-m", "2026-11"]) == 0
    assert run(["--db", str(db), "balance"]) == 0
    assert run(["--db", str(db), "categories"]) == 0

    out = capsys.readouterr().out
    assert "salary" in out
    assert "food" in out
    assert "4,880.00" in out or "4880.00" in out
    assert "balance:" in out


def test_cli_delete_missing(tmp_path: Path) -> None:
    db = tmp_path / "db.json"
    assert run(["--db", str(db), "delete", "nope"]) == 1
