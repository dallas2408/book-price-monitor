"""Command-line entry point: python -m monitor"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .notify import build_report, send_telegram
from .scraper import START_URL, Fetcher, scrape_catalog
from .storage import Store, export


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape the books.toscrape.com catalog and report changes.")
    parser.add_argument("--out", type=Path, default=Path("data"), help="folder for books.csv, books.json and history.db")
    parser.add_argument("--max-pages", type=int, default=None, help="stop after N catalog pages (default: all)")
    parser.add_argument("--delay", type=float, default=0.5, help="seconds to wait between requests")
    parser.add_argument("--notify", action="store_true", help="send the report to Telegram if it has changes")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    books = scrape_catalog(Fetcher(delay=args.delay), START_URL, args.max_pages)
    if not books:
        logging.error("No books found - the site layout may have changed")
        return 1

    csv_path, json_path = export(books, args.out)
    store = Store(args.out / "history.db")
    try:
        changes = store.apply(books)
    finally:
        store.close()

    report = build_report(changes, len(books))
    print(report)
    print(f"\nSaved: {csv_path}, {json_path}")

    if args.notify and changes.any:
        send_telegram(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
