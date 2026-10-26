"""Read price, sale price and stock from a store's product page.

All four stores embed schema.org Product data (JSON-LD) for search engines; it
holds the current price and availability. The regular price during a sale is
only in the visible HTML, as a crossed-out number, in a different place per store.
"""

import json
import re
from dataclasses import dataclass
from decimal import Decimal

from bs4 import BeautifulSoup

from app.db.models import Availability

# Where each store shows the crossed-out regular price on a product page.
# The main price block is targeted so prices of "related products" are ignored.
REGULAR_PRICE_SELECTOR = {
    "xstore": ".price-ctx .x-old",
    "neocomputer": ".price_bar .price__old",
    "darwin": ".block-price .text-decoration-line-through",
    "ultra": ".product-purchase-card__old-price",
}

_AVAILABILITY = {
    "instock": Availability.IN_STOCK,
    "instoreonly": Availability.IN_STOCK,
    "limitedavailability": Availability.IN_STOCK,
    "onlineonly": Availability.IN_STOCK,
    "preorder": Availability.ON_ORDER,
    "presale": Availability.ON_ORDER,
    "backorder": Availability.ON_ORDER,
    "outofstock": Availability.OUT_OF_STOCK,
    "soldout": Availability.OUT_OF_STOCK,
    "discontinued": Availability.OUT_OF_STOCK,
}


class PageParseError(ValueError):
    """The page doesn't contain the data we expect (e.g. the store changed its layout)."""


@dataclass(frozen=True)
class PageData:
    price: Decimal
    regular_price: Decimal | None  # set only when it's above the current price, i.e. on sale
    availability: Availability


def _price(text: str) -> Decimal:
    """'3 979 lei' / '3979' / '3799.00' -> Decimal. Thousands are separated by spaces."""
    match = re.search(r"\d[\d\s  ]*(?:[.,]\d{1,2})?", str(text))
    if not match:
        raise PageParseError(f"No number in {text!r}")
    number = re.sub(r"[\s  ]", "", match.group()).replace(",", ".")
    return Decimal(number)


def _product_offer(soup: BeautifulSoup) -> dict:
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            nodes = data.get("@graph", [data])
        elif isinstance(data, list):
            nodes = data
        else:
            continue  # valid JSON but not an object, e.g. a bare number
        if not isinstance(nodes, list):
            continue
        for node in nodes:
            if isinstance(node, dict) and node.get("@type") == "Product":
                offer = node.get("offers")
                offer = offer[0] if isinstance(offer, list) and offer else offer
                if isinstance(offer, dict):
                    return offer
    raise PageParseError("No schema.org Product offer on the page")


def parse_product_page(store_slug: str, html: str) -> PageData:
    if store_slug not in REGULAR_PRICE_SELECTOR:
        raise PageParseError(f"No parser for store {store_slug!r}")
    soup = BeautifulSoup(html, "html.parser")
    offer = _product_offer(soup)

    if "price" not in offer:
        raise PageParseError("Product offer has no price")
    price = _price(offer["price"])
    if price <= 0:
        raise PageParseError(f"Price {price} is not positive")

    status = str(offer.get("availability", "")).rsplit("/", 1)[-1].lower()
    if status not in _AVAILABILITY:
        raise PageParseError(f"Unknown availability {offer.get('availability')!r}")

    regular = None
    old = soup.select_one(REGULAR_PRICE_SELECTOR[store_slug])
    if old is not None and re.search(r"\d", old.get_text()):
        candidate = _price(old.get_text(" ", strip=True))
        if candidate > price:
            regular = candidate
    return PageData(price=price, regular_price=regular, availability=_AVAILABILITY[status])
