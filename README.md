# Book Price Monitor

A small web scraper that runs on a schedule, keeps history, and tells you what changed.

It crawls the full catalog of [books.toscrape.com](https://books.toscrape.com) (a public sandbox site made for scraping practice, 1,000 books across 50 pages), saves a clean snapshot as CSV and JSON, and compares it with the previous run:

- price changes (with full price history in SQLite)
- new items
- items back in stock
- items removed from the catalog

If anything changed, it can send a short report to Telegram. GitHub Actions runs it every day for free and commits the fresh data back to this repo, so `data/` always holds the latest snapshot.

The same pattern fits real jobs: competitor prices, product availability, event calendars, job boards, listings.

## Report format

The sandbox site's prices rarely change, so most daily runs end with "No changes since the last run." When something does change, the report looks like this (generated from test data):

```
Book catalog check: 1000 books scanned.

Price changes (2):
- A Light in the Attic: £51.77 -> £47.50
- Soumission: £50.10 -> £52.00

Back in stock (1):
- Tipping the Velvet
```

## Run it locally

```bash
pip install -r requirements.txt
python -m monitor --out data -v          # full catalog
python -m monitor --max-pages 2 -v       # quick test run
```

Output in `data/`:

| File | What's inside |
|---|---|
| `books.csv` | title, price, in_stock, rating, url — opens in Excel / Google Sheets |
| `books.json` | the same data for other programs |
| `history.db` | SQLite: current state + price history for every book |

## Telegram alerts (optional)

Set two environment variables (or repository secrets for GitHub Actions) and add `--notify`:

```bash
export TELEGRAM_BOT_TOKEN=...   # from @BotFather
export TELEGRAM_CHAT_ID=...     # your chat or group id
python -m monitor --notify
```

Without them the report is just printed.

## How it's built

- `monitor/scraper.py` — fetching with timeouts, retries and a polite delay; parsing with BeautifulSoup; follows pagination until the last page
- `monitor/storage.py` — SQLite state, change detection, CSV/JSON export
- `monitor/notify.py` — readable report, Telegram Bot API
- `tests/` — offline tests on markup copied from the real site (parsing, broken cards, change detection, export)
- `.github/workflows/monitor.yml` — daily run: tests → scrape → commit data

A broken card is logged and skipped instead of crashing the run, and an empty result exits with an error, so a layout change on the site shows up as a failed run instead of silently empty data.

## Tests

```bash
pip install pytest
python -m pytest -q
```
