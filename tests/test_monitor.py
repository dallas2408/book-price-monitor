"""Offline tests: parsing uses markup copied from the real site, storage uses a temp SQLite file."""

from decimal import Decimal

from monitor.notify import build_report
from monitor.scraper import Book, parse_page
from monitor.storage import Store, export

PAGE_URL = "https://books.toscrape.com/catalogue/page-1.html"

CARD = """
<article class="product_pod">
  <div class="image_container"><a href="{slug}/index.html"><img src="x.jpg" alt="{title}" class="thumbnail"></a></div>
  <p class="star-rating {rating}"><i class="icon-star"></i></p>
  <h3><a href="{slug}/index.html" title="{title}">{short}</a></h3>
  <div class="product_price">
    <p class="price_color">£{price}</p>
    <p class="{stock_class} availability"><i class="icon-ok"></i> {stock_text} </p>
  </div>
</article>
"""


def page(cards: str, next_href: str | None = "page-2.html") -> str:
    pager = f'<ul class="pager"><li class="next"><a href="{next_href}">next</a></li></ul>' if next_href else ""
    return f"<html><body><ol class='row'>{cards}</ol>{pager}</body></html>"


def card(title="A Light in the Attic", slug="a-light-in-the-attic_1000", price="51.77",
         rating="Three", in_stock=True) -> str:
    return CARD.format(
        title=title, slug=slug, short=title[:15] + " ...", price=price, rating=rating,
        stock_class="instock" if in_stock else "outofstock",
        stock_text="In stock" if in_stock else "Out of stock",
    )


def test_parse_page_reads_all_fields():
    books, next_url = parse_page(page(card()), PAGE_URL)
    assert next_url == "https://books.toscrape.com/catalogue/page-2.html"
    assert books == [Book(
        title="A Light in the Attic",  # full title from the attribute, not the truncated link text
        price=Decimal("51.77"),
        in_stock=True,
        rating=3,
        url="https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
    )]


def test_last_page_has_no_next_and_out_of_stock_is_detected():
    books, next_url = parse_page(page(card(in_stock=False, rating="Five"), next_href=None), PAGE_URL)
    assert next_url is None
    assert books[0].in_stock is False
    assert books[0].rating == 5


def test_broken_card_is_skipped_not_fatal():
    broken = '<article class="product_pod"><h3>no link here</h3></article>'
    books, _ = parse_page(page(broken + card()), PAGE_URL)
    assert len(books) == 1


def make_book(slug, price, in_stock=True):
    return Book(title=slug.title(), price=Decimal(price), in_stock=in_stock, rating=4,
                url=f"https://books.toscrape.com/catalogue/{slug}/index.html")


def test_first_run_reports_nothing_then_changes_are_detected(tmp_path):
    store = Store(tmp_path / "history.db")
    first = store.apply([make_book("alpha", "10.00"), make_book("beta", "20.00", in_stock=False),
                         make_book("gamma", "30.00")], now="2026-10-01T00:00:00")
    assert not first.any  # the first run only builds the baseline

    second = store.apply([make_book("alpha", "8.50"), make_book("beta", "20.00", in_stock=True),
                          make_book("delta", "5.00")], now="2026-10-02T00:00:00")
    assert [(b.title, old) for b, old in second.price_changed] == [("Alpha", Decimal("10.00"))]
    assert [b.title for b in second.back_in_stock] == ["Beta"]
    assert [b.title for b in second.new] == ["Delta"]
    assert second.removed == ["Gamma"]

    history = store.conn.execute(
        "SELECT price FROM price_history WHERE url LIKE '%alpha%' ORDER BY seen_at").fetchall()
    assert [p for (p,) in history] == ["10.00", "8.50"]
    store.close()


def test_report_and_export(tmp_path):
    store = Store(tmp_path / "h.db")
    store.apply([make_book("alpha", "10.00")])
    changes = store.apply([make_book("alpha", "12.00")])
    report = build_report(changes, total=1)
    assert "Alpha: £10.00 -> £12.00" in report

    csv_path, json_path = export([make_book("alpha", "12.00")], tmp_path / "out")
    assert csv_path.read_text(encoding="utf-8").splitlines()[1].startswith("Alpha,12.00,True,4,")
    assert '"price": "12.00"' in json_path.read_text(encoding="utf-8")
