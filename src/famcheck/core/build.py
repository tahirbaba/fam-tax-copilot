"""Turn verified raw strings into a typed `Invoice`. Unparseable values become INVALID."""

from __future__ import annotations

from typing import Callable

from famcheck.core.models import CheckedField, FieldStatus, Invoice, LineItem
from famcheck.ingest.normalize import (
    ParseError,
    parse_amount,
    parse_currency,
    parse_date,
    parse_rate,
    parse_trn,
)

_AMOUNT_FIELDS = {"subtotal", "discount", "vat_amount", "total_amount", "vat_amount_aed", "exchange_rate"}
_TEXT_FIELDS = {"document_title", "invoice_number", "supplier_name", "supplier_address", "customer_name", "customer_address"}


def _parser(name: str) -> Callable:
    if name in _AMOUNT_FIELDS or name in {"quantity", "unit_price", "net_amount"}:
        return parse_amount
    if name == "vat_rate":
        return parse_rate
    if name in {"supplier_trn", "customer_trn"}:
        return parse_trn
    if name == "currency":
        return parse_currency
    if name in {"issue_date", "supply_date"}:
        return lambda raw: parse_date(raw)[0]
    return lambda raw: " ".join(str(raw).split())


def _convert(cf: CheckedField):
    if not cf.usable:
        return None
    try:
        value = _parser(cf.name)(cf.raw)
    except ParseError as e:
        cf.status = FieldStatus.INVALID
        cf.note = str(e)
        return None
    if cf.name in {"issue_date", "supply_date"}:
        _, note = parse_date(cf.raw)
        if note:
            cf.note = note
    return value


def build_invoice(fields: dict[str, CheckedField], lines: list[dict[str, CheckedField]]) -> Invoice:
    data = {name: _convert(cf) for name, cf in fields.items()}
    items = []
    for row in lines:
        items.append(LineItem(**{name: _convert(cf) for name, cf in row.items()}))
    data["line_items"] = items
    return Invoice(**data)
