from datetime import date
from decimal import Decimal

from famcheck.core.models import CheckedField, FieldStatus, Invoice, LineItem, ReviewContext, HEADER_FIELDS, LINE_FIELDS
from famcheck.rules.checks import REGISTRY, RuleInput, full_invoice_required
from famcheck.rules.engine import evaluate, load_packs


def _ri(inv: Invoice, present=(), client_trn=None, kind="pdf-text"):
    fields = {n: CheckedField(name=n, status=FieldStatus.VERIFIED if n in present else FieldStatus.ABSENT,
                              raw="x" if n in present else None) for n in HEADER_FIELDS}
    lines = [{n: CheckedField(name=n, status=FieldStatus.VERIFIED, raw="1") for n in LINE_FIELDS} for _ in inv.line_items]
    return RuleInput(inv=inv, fields=fields, lines=lines, ctx=ReviewContext(client_trn=client_trn, today=date(2026, 11, 15)),
                     kind=kind, full_invoice_required=full_invoice_required(inv))


def test_packs_load_and_reference_real_checks():
    packs = load_packs()
    assert {p.pack for p in packs} == {"vat_tax_invoice", "arithmetic", "review_guardrails", "einvoicing_readiness"}
    for p in packs:
        for r in p.rules:
            assert r.check in REGISTRY
            assert r.title_ar and r.message_ar, f"{r.id} needs Arabic text"


def test_simplified_threshold():
    assert full_invoice_required(Invoice(currency="AED", total_amount=Decimal("10000.00"))) is False
    assert full_invoice_required(Invoice(currency="AED", total_amount=Decimal("10000.01"))) is True
    assert full_invoice_required(Invoice(currency="USD", total_amount=Decimal("100"))) is True
    assert full_invoice_required(Invoice(currency="AED")) is True  # unknown total -> conservative


def _ids(findings):
    return {f.rule_id for f in findings}


def test_vat_math_tolerance_and_error():
    lines = [LineItem(quantity=Decimal(1), unit_price=Decimal("2400"), net_amount=Decimal("2400.00"))]
    ok = Invoice(subtotal=Decimal("2400.00"), vat_rate=Decimal(5), vat_amount=Decimal("120.01"), total_amount=Decimal("2520.01"), line_items=lines)
    assert "MATH-003" not in _ids(evaluate(_ri(ok)))
    bad = ok.model_copy(update={"vat_amount": Decimal("125.00"), "total_amount": Decimal("2525.00")})
    assert "MATH-003" in _ids(evaluate(_ri(bad)))


def test_line_and_total_math():
    lines = [LineItem(quantity=Decimal(3), unit_price=Decimal("10.00"), net_amount=Decimal("31.00"))]
    inv = Invoice(subtotal=Decimal("31.00"), vat_rate=Decimal(5), vat_amount=Decimal("1.55"), total_amount=Decimal("40.00"), line_items=lines)
    ids = _ids(evaluate(_ri(inv)))
    assert {"MATH-001", "MATH-004"} <= ids


def test_wrong_rate_and_customer_mismatch():
    inv = Invoice(vat_rate=Decimal(15), customer_trn="100998877665544")
    ids = _ids(evaluate(_ri(inv, client_trn="100345678900003")))
    assert {"VAT-010", "VAT-015"} <= ids
    same = Invoice(vat_rate=Decimal(5), customer_trn="100345678900003")
    assert not {"VAT-010", "VAT-015"} & _ids(evaluate(_ri(same, client_trn="100-345678900003")))


def test_unverified_value_is_never_reported_as_missing():
    inv = Invoice()
    ri = _ri(inv)
    ri.fields["supplier_trn"] = CheckedField(name="supplier_trn", raw="123", status=FieldStatus.UNVERIFIED, note="n")
    ids = _ids(evaluate(ri))
    assert "VAT-004" not in ids and "GUARD-001" in ids
