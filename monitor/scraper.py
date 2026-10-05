"""Fetch and parse the catalog of books.toscrape.com (a public sandbox built for scraping practice)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, asdict
from decimal import Decimal
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

BASE_URL = "https://books.toscrape.com/"
START_URL = urljoin(BASE_URL, "catalogue/page-1.html")
RATINGS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


@dataclass(frozen=True)
class Book:
    title: str
    price: Decimal
    in_stock: bool
    rating: int
    url: str

    def to_row(self) -> dict:
        row = asdict(self)
        row["price"] = str(self.price)
        return row


def parse_page(html: str, page_url: str) -> tuple[list[Book], str | None]:
    """Return the books found on one catalog page and the absolute URL of the next page (or None)."""
    soup = BeautifulSoup(html, "html.parser")
    books: list[Book] = []

    for card in soup.select("article.product_pod"):
        link = card.select_one("h3 a")
        price_tag = card.select_one("p.price_color")
        if link is None or price_tag is None:
            log.warning("Skipping a card with unexpected markup on %s", page_url)
            continue

        price_text = price_tag.get_text(strip=True).lstrip("Â").lstrip("£")
        rating_tag = card.select_one("p.star-rating")
        rating_word = next((c for c in (rating_tag.get("class", []) if rating_tag else []) if c in RATINGS), None)
        stock_tag = card.select_one("p.availability")

        books.append(
            Book(
                title=link.get("title") or link.get_text(strip=True),
                price=Decimal(price_text),
                in_stock=bool(stock_tag and "in stock" in stock_tag.get_text(" ", strip=True).lower()),
                rating=RATINGS.get(rating_word, 0),
                url=urljoin(page_url, link["href"]),
            )
        )

    next_link = soup.select_one("li.next a")
    next_url = urljoin(page_url, next_link["href"]) if next_link else None
    return books, next_url


class Fetcher:
    """HTTP client with a polite delay, timeouts and simple retries."""

    def __init__(self, delay: float = 0.5, retries: int = 3, timeout: float = 15.0):
        self.delay = delay
        self.retries = retries
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "book-price-monitor/1.0 (portfolio demo)"

    def get(self, url: str) -> str:
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                resp = self.session.get(url, timeout=self.timeout)
                resp.raise_for_status()
                resp.encoding = "utf-8"
                time.sleep(self.delay)
                return resp.text
            except requests.RequestException as exc:
                last_error = exc
                wait = 2 ** attempt
                log.warning("Attempt %d/%d failed for %s: %s (retrying in %ss)", attempt, self.retries, url, exc, wait)
                time.sleep(wait)
        raise RuntimeError(f"Giving up on {url}") from last_error


def scrape_catalog(fetcher: Fetcher, start_url: str = START_URL, max_pages: int | None = None) -> list[Book]:
    """Walk the paginated catalog and return every book."""
    books: list[Book] = []
    url: str | None = start_url
    page = 0
    while url and (max_pages is None or page < max_pages):
        page += 1
        page_books, url = parse_page(fetcher.get(url), url)
        log.info("Page %d: %d books", page, len(page_books))
        books.extend(page_books)
    return books
