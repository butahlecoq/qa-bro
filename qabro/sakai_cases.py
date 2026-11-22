"""Generate synthetic, repeatable inputs for the Sakai CRUD scenarios."""

import re
from dataclasses import dataclass
from random import Random
from string import ascii_letters, digits


@dataclass(frozen=True)
class Product:
    name: str
    description: str
    price_cents: int
    updated_price_cents: int


def product_for(seed: int, series: str, pair: int) -> Product:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", series) or pair < 0:
        raise ValueError("Expected a synthetic series ID and nonnegative pair number")
    rng = Random(seed)
    price, updated = rng.sample(range(100, 10000), 2)
    return Product(
        f"qa_{series}_{pair}",
        "".join(rng.choices(ascii_letters + digits, k=100)),
        price,
        updated,
    )


CREATE_CHECKS = (
    "dialog_open", "entered_fields", "saved", "exact_row_and_price", "saved_fields", "record_remains",
)
