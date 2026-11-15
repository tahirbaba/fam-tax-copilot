"""Deterministic rule checks. Each check returns a list of violations; each
violation is a dict of template variables (and optionally `field`).

All money arithmetic uses Decimal with an explicit rounding tolerance.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable

from famcheck.core.models import CheckedField, FieldStatus, Invoice, ReviewContext
from famcheck.i18n import field_label, status_note_ar
from famcheck.ingest.normalize import norm_text

CENT = Decimal("0.01")
SIMPLIFIED_LIMIT_AED = Decimal("10000")
VALID_UAE_RATES = {Decimal("5"), Decimal("0")}
ISO_CURRENCIES = {"AED", "USD", "EUR", "GBP", "SAR", "INR", "PKR", "CNY", "JPY", "CHF", "OMR", "QAR", "KWD", "BHD"}


def money(v: Decimal) -> str:
    return f"{v.quantize(CENT, rounding=ROUND_HALF_UP):,.2f}"


def r2(v: Decimal) -> Decimal:
    return v.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class RuleInput:
    inv: Invoice
    fields: dict[str, CheckedField]
    lines: list[dict[str, CheckedField]]
    ctx: ReviewContext
    kind: str
    full_invoice_required: bool


Violation = dict
CheckFn = Callable[[RuleInput, dict], list[Violation]]
REGISTRY: dict[str, CheckFn] = {}


def check(name: str):
    def deco(fn: CheckFn) -> CheckFn:
        REGISTRY[name] = fn
        return fn

    return deco


# ------------------------------------------------------------------ applicability


def full_invoice_required(inv: Invoice) -> bool:
    """A simplified tax invoice is acceptable only when the consideration is
    AED 10,000 or less (the client - the recipient - is VAT-registered).
    If the total is unknown or not in AED we are conservative: full invoice required."""
    if inv.currency in (None, "AED") and inv.total_amount is not None:
        return inv.total_amount > SIMPLIFIED_LIMIT_AED
    return True


CONDITIONS: dict[str, Callable[[RuleInput], bool]] = {
    "always": lambda ri: True,
    "full_invoice_required": lambda ri: ri.full_invoice_required,
    "foreign_currency": lambda ri: ri.inv.currency is not None and ri.inv.currency != "AED",
    "client_trn_given": lambda ri: bool(ri.ctx.client_trn),
}


# ------------------------------------------------------------------ field checks


@check("never")
def _never(ri: RuleInput, p: dict) -> list[Violation]:
    return []  # raised explicitly by the pipeline (batch-level / extraction errors)


@check("field_present")
def _field_present(ri: RuleInput, p: dict) -> list[Violation]:
    cf = ri.fields[p["field"]]
    # Only flag as missing when it is genuinely absent. Unverified / disputed values
    # are handled by GUARD-001 (needs a human), never treated as "missing".
    if cf.status == FieldStatus.ABSENT:
        return [{"field": p["field"]}]
    return []


@check("title_is_tax_invoice")
def _title(ri: RuleInput, p: dict) -> list[Violation]:
    cf = ri.fields["document_title"]
    if cf.status not in (FieldStatus.ABSENT, FieldStatus.VERIFIED, FieldStatus.VISUAL):
        return []  # unverifiable -> GUARD-001
    title = norm_text(cf.raw)
    if "tax invoice" in title or "فاتوره ضريبيه" in title:
        return []
    return [{"field": "document_title", "found": cf.raw or "—"}]


@check("trn_format")
def _trn_format(ri: RuleInput, p: dict) -> list[Violation]:
    trn = getattr(ri.inv, p["field"])
    if trn is not None and len(trn) != 15:
        return [{"field": p["field"], "found": trn, "length": len(trn)}]
    return []


@check("trn_prefix")
def _trn_prefix(ri: RuleInput, p: dict) -> list[Violation]:
    trn = getattr(ri.inv, p["field"])
    if trn is not None and len(trn) == 15 and not trn.startswith("100"):
        return [{"field": p["field"], "found": trn}]
    return []


@check("customer_is_client")
def _customer_is_client(ri: RuleInput, p: dict) -> list[Violation]:
    trn = ri.inv.customer_trn
    expected = "".join(ch for ch in (ri.ctx.client_trn or "") if ch.isdigit())
    if trn is not None and expected and trn != expected:
        return [{"field": "customer_trn", "found": trn, "expected": expected}]
    return []


@check("supplier_not_customer")
def _supplier_not_customer(ri: RuleInput, p: dict) -> list[Violation]:
    if ri.inv.supplier_trn and ri.inv.supplier_trn == ri.inv.customer_trn:
        return [{"field": "customer_trn", "found": ri.inv.supplier_trn}]
    return []


@check("lines_present")
def _lines_present(ri: RuleInput, p: dict) -> list[Violation]:
    has_desc = any(row["description"].status != FieldStatus.ABSENT for row in ri.lines)
    return [] if has_desc else [{}]


def _effective_rate(inv: Invoice) -> Decimal | None:
    if inv.vat_rate is not None:
        return inv.vat_rate
    rates = {li.vat_rate for li in inv.line_items if li.vat_rate is not None}
    return rates.pop() if len(rates) == 1 else None


@check("vat_rate_valid")
def _vat_rate_valid(ri: RuleInput, p: dict) -> list[Violation]:
    rates = set()
    if ri.inv.vat_rate is not None:
        rates.add(ri.inv.vat_rate)
    rates |= {li.vat_rate for li in ri.inv.line_items if li.vat_rate is not None}
    return [{"field": "vat_rate", "found": str(r)} for r in sorted(rates) if r not in VALID_UAE_RATES]


@check("foreign_currency_has_aed_vat")
def _foreign_currency(ri: RuleInput, p: dict) -> list[Violation]:
    if ri.fields["vat_amount_aed"].status == FieldStatus.ABSENT:
        return [{"field": "vat_amount_aed", "found": ri.inv.currency}]
    return []


@check("date_not_future")
def _date_not_future(ri: RuleInput, p: dict) -> list[Violation]:
    d = ri.inv.issue_date
    if d is not None and d > ri.ctx.today:
        return [{"field": "issue_date", "found": d.isoformat(), "expected": ri.ctx.today.isoformat()}]
    return []


@check("currency_is_iso")
def _currency_is_iso(ri: RuleInput, p: dict) -> list[Violation]:
    cf = ri.fields["currency"]
    if cf.status == FieldStatus.ABSENT:
        return [{"field": "currency", "found": "—"}]
    if cf.usable and ri.inv.currency is not None and ri.inv.currency not in ISO_CURRENCIES:
        return [{"field": "currency", "found": cf.raw}]
    return []  # unparseable values are raised by GUARD-001


@check("lines_structured")
def _lines_structured(ri: RuleInput, p: dict) -> list[Violation]:
    out = []
    for i, row in enumerate(ri.lines, start=1):
        missing = [n for n in ("quantity", "unit_price", "net_amount", "vat_rate") if row[n].status == FieldStatus.ABSENT]
        if missing:
            out.append({"line": i, "missing": ", ".join(field_label(m) for m in missing)})
    return out


# ------------------------------------------------------------------ arithmetic


@check("line_math")
def _line_math(ri: RuleInput, p: dict) -> list[Violation]:
    out = []
    for i, li in enumerate(ri.inv.line_items, start=1):
        if None in (li.quantity, li.unit_price, li.net_amount):
            continue
        expected = r2(li.quantity * li.unit_price)
        if abs(expected - li.net_amount) > CENT:
            out.append({
                "line": i, "quantity": str(li.quantity.normalize()), "unit_price": money(li.unit_price),
                "expected": money(expected), "found": money(li.net_amount),
            })
    return out


@check("lines_sum_subtotal")
def _lines_sum(ri: RuleInput, p: dict) -> list[Violation]:
    inv = ri.inv
    nets = [li.net_amount for li in inv.line_items]
    if inv.subtotal is None or not nets or any(n is None for n in nets):
        return []
    total = sum(nets, Decimal("0"))
    if abs(total - inv.subtotal) > CENT:
        return [{"field": "subtotal", "expected": money(total), "found": money(inv.subtotal)}]
    return []


@check("vat_math")
def _vat_math(ri: RuleInput, p: dict) -> list[Violation]:
    inv = ri.inv
    rate = _effective_rate(inv)
    if inv.subtotal is None or inv.vat_amount is None or rate is None:
        return []
    base = inv.subtotal - (inv.discount or Decimal("0"))
    expected = r2(base * rate / Decimal("100"))
    # tolerance: 1 fils per line when VAT is rounded line-by-line
    tolerance = CENT * max(1, len(inv.line_items))
    diff = inv.vat_amount - expected
    if abs(diff) > tolerance:
        return [{
            "field": "vat_amount", "rate": str(rate), "base": money(base), "expected": money(expected),
            "found": money(inv.vat_amount), "diff": money(diff),
        }]
    return []


@check("total_math")
def _total_math(ri: RuleInput, p: dict) -> list[Violation]:
    inv = ri.inv
    if None in (inv.subtotal, inv.vat_amount, inv.total_amount):
        return []
    discount = inv.discount or Decimal("0")
    expected = r2(inv.subtotal - discount + inv.vat_amount)
    if abs(expected - inv.total_amount) > CENT:
        return [{
            "field": "total_amount", "subtotal": money(inv.subtotal), "discount": money(discount),
            "vat": money(inv.vat_amount), "expected": money(expected), "found": money(inv.total_amount),
        }]
    return []


# ------------------------------------------------------------------ guardrails


@check("field_unusable")
def _field_unusable(ri: RuleInput, p: dict) -> list[Violation]:
    bad = (FieldStatus.UNVERIFIED, FieldStatus.DISPUTED, FieldStatus.INVALID)
    out = []
    for name, cf in ri.fields.items():
        if cf.status in bad:
            out.append({
                "field": name, "field_label": field_label(name, "en"), "field_label_ar": field_label(name, "ar"),
                "note": cf.note or cf.status.value, "note_ar": status_note_ar(cf.status.value),
            })
    for i, row in enumerate(ri.lines, start=1):
        for name, cf in row.items():
            if cf.status in bad:
                out.append({
                    "field": f"line{i}.{name}",
                    "field_label": f"Line {i} {field_label(name, 'en').lower()}",
                    "field_label_ar": f"البند {i} - {field_label(name, 'ar')}",
                    "note": cf.note or cf.status.value, "note_ar": status_note_ar(cf.status.value),
                })
    return out


@check("visual_source")
def _visual_source(ri: RuleInput, p: dict) -> list[Violation]:
    return [{}] if ri.kind != "pdf-text" else []
