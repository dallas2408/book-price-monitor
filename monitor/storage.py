"""Keep run history in SQLite and work out what changed since the previous run."""

from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .scraper import Book

SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
    url        TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    price      TEXT NOT NULL,
    in_stock   INTEGER NOT NULL,
    rating     INTEGER NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS price_history (
    url      TEXT NOT NULL,
    price    TEXT NOT NULL,
    seen_at  TEXT NOT NULL
);
"""


@dataclass
class Changes:
    new: list[Book]
    price_changed: list[tuple[Book, Decimal]]  # (book with new price, old price)
    back_in_stock: list[Book]
    removed: list[str]  # titles that disappeared from the catalog

    @property
    def any(self) -> bool:
        return bool(self.new or self.price_changed or self.back_in_stock or self.removed)


class Store:
    def __init__(self, path: Path | str):
        self.conn = sqlite3.connect(str(path))
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def apply(self, books: list[Book], now: str | None = None) -> Changes:
        """Save this run's books and return what changed compared with the stored state."""
        now = now or datetime.now(timezone.utc).isoformat(timespec="seconds")
        known = {
            row[0]: row
            for row in self.conn.execute("SELECT url, title, price, in_stock FROM books")
        }
        first_run = not known
        changes = Changes(new=[], price_changed=[], back_in_stock=[], removed=[])
        seen: set[str] = set()

        with self.conn:
            for book in books:
                seen.add(book.url)
                old = known.get(book.url)
                if old is None:
                    if not first_run:
                        changes.new.append(book)
                    self.conn.execute(
                        "INSERT INTO books VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (book.url, book.title, str(book.price), int(book.in_stock), book.rating, now, now),
                    )
                    self.conn.execute("INSERT INTO price_history VALUES (?, ?, ?)", (book.url, str(book.price), now))
                    continue

                old_price = Decimal(old[2])
                if old_price != book.price:
                    changes.price_changed.append((book, old_price))
                    self.conn.execute("INSERT INTO price_history VALUES (?, ?, ?)", (book.url, str(book.price), now))
                if book.in_stock and not old[3]:
                    changes.back_in_stock.append(book)
                self.conn.execute(
                    "UPDATE books SET title=?, price=?, in_stock=?, rating=?, last_seen=? WHERE url=?",
                    (book.title, str(book.price), int(book.in_stock), book.rating, now, book.url),
                )

        changes.removed = [row[1] for url, row in known.items() if url not in seen]
        return changes


def export(books: list[Book], out_dir: Path) -> tuple[Path, Path]:
    """Write the current snapshot as CSV and JSON."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = [b.to_row() for b in sorted(books, key=lambda b: b.title.lower())]

    csv_path = out_dir / "books.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["title", "price", "in_stock", "rating", "url"])
        writer.writeheader()
        writer.writerows(rows)

    json_path = out_dir / "books.json"
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return csv_path, json_path
