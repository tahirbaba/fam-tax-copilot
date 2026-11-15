from datetime import date
from decimal import Decimal

import pytest

from famcheck.ingest.normalize import (
    ParseError, detect_language, norm_text, parse_amount, parse_currency, parse_date, parse_rate, parse_trn,
)


@pytest.mark.parametrize("raw,expected", [
    ("1,234.50", "1234.50"), ("AED 1,234.50", "1234.50"), ("1234.5 درهم", "1234.5"),
    ("١٬٢٣٤٫٥٠", "1234.50"), ("(50.00)", "-50.00"), ("Dhs. 99", "99"), ("0.00", "0.00"),
])
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == Decimal(expected)


@pytest.mark.parametrize("raw", ["1.234,50", "12 34", "abc", "", "1,23", "10 and 20"])
def test_parse_amount_rejects_ambiguous(raw):
    with pytest.raises(ParseError):
        parse_amount(raw)


@pytest.mark.parametrize("raw,expected", [("5%", 5), ("5 %", 5), ("٥٪", 5), ("0.05", 5), ("15%", 15), ("0%", 0)])
def test_parse_rate(raw, expected):
    assert parse_rate(raw) == Decimal(expected)


def test_parse_trn():
    assert parse_trn("TRN: 100-2345-6789-0003") == "100234567890003"
    assert parse_trn("١٠٠٤٥٦٧٨٩٠١٢٣٤٥") == "100456789012345"
    with pytest.raises(ParseError):
        parse_trn("10023A")


@pytest.mark.parametrize("raw,expected", [
    ("12/10/2026", date(2026, 10, 12)), ("2026-10-12", date(2026, 10, 12)), ("15 Oct 2026", date(2026, 10, 15)),
    ("October 5, 2026", date(2026, 10, 5)), ("٠٨/١٠/٢٠٢٦", date(2026, 10, 8)), ("5 أكتوبر 2026", date(2026, 10, 5)),
    ("25.10.2026", date(2026, 10, 25)),
])
def test_parse_date(raw, expected):
    assert parse_date(raw)[0] == expected


def test_parse_date_flags_ambiguity_and_rejects_impossible():
    assert parse_date("03/04/2026")[1] is not None  # 3 April (DD/MM) assumed, noted
    assert parse_date("25/10/2026")[1] is None
    with pytest.raises(ParseError):
        parse_date("31/02/2026")
    with pytest.raises(ParseError):
        parse_date("next tuesday")


@pytest.mark.parametrize("raw,code", [("AED", "AED"), ("درهم", "AED"), ("د.إ", "AED"), ("USD", "USD"), ("$", "USD"), ("£", "GBP")])
def test_parse_currency(raw, code):
    assert parse_currency(raw) == code


def test_norm_text_folds_arabic_presentation_forms():
    # what pypdf emits for "فاتورة ضريبية"
    assert norm_text("ﻓﺎﺗﻮرة ﺿﺮﻳﺒﻴﺔ") == norm_text("فاتورة ضريبية")


def test_detect_language():
    assert detect_language("Tax Invoice total") == "en"
    assert detect_language("فاتورة ضريبية الإجمالي") == "ar"
    assert detect_language("Tax Invoice فاتورة ضريبية") == "mixed"
