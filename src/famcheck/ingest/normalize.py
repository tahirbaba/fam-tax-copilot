"""Deterministic text / number / date normalisation (English + Arabic).

Nothing here guesses. Every parser either returns a value it is certain of,
or raises `ParseError` with the reason - the caller turns that into a finding.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional


class ParseError(ValueError):
    pass


# Arabic-Indic (U+0660..) and Eastern Arabic-Indic / Persian (U+06F0..) digits -> ASCII
_DIGIT_MAP = {ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}
_DIGIT_MAP.update({ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")})
_DIGIT_MAP[ord("٫")] = "."  # Arabic decimal separator
_DIGIT_MAP[ord("٬")] = ","  # Arabic thousands separator
_DIGIT_MAP[ord("٪")] = "%"  # Arabic percent sign

_ARABIC_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")  # incl. tatweel
_ARABIC_CHARS = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
_WS = re.compile(r"\s+")


def has_arabic(text: str | None) -> bool:
    return bool(text) and bool(_ARABIC_CHARS.search(text))


def ascii_digits(text: str) -> str:
    return text.translate(_DIGIT_MAP)


def norm_text(text: str | None) -> str:
    """Canonical form used for evidence matching.

    - NFKC folds Arabic presentation forms (what PDF extractors emit) back to base letters
    - Arabic/Persian digits -> ASCII, diacritics and tatweel removed
    - case-folded, whitespace collapsed
    """
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = ascii_digits(t)
    t = _ARABIC_DIACRITICS.sub("", t)
    # unify alef / ya / ta-marbuta variants that differ between fonts and typists
    t = t.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"}))
    t = t.replace("‏", "").replace("‎", "").replace("؜", "")
    t = t.casefold()
    return _WS.sub(" ", t).strip()


def detect_language(text: str) -> str:
    if not text.strip():
        return "unknown"
    arabic = len(_ARABIC_CHARS.findall(text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if arabic and latin:
        ratio = arabic / (arabic + latin)
        if ratio > 0.8:
            return "ar"
        if ratio < 0.2:
            return "en"
        return "mixed"
    return "ar" if arabic else "en"


# --------------------------------------------------------------------------
# Amounts
# --------------------------------------------------------------------------

_CURRENCY_TOKENS = re.compile(
    r"(aed|dhs?\.?|dirhams?|usd|eur|gbp|sar|us\$|\$|€|£|درهم|دراهم|د\.?\s?إ|ريال|دولار)",
    re.IGNORECASE,
)


def parse_amount(raw: str | None) -> Decimal:
    """Parse a printed money amount. Accepts '1,234.50', 'AED 1,234.50', '١٬٢٣٤٫٥٠', '(50.00)'.

    Rejects anything ambiguous (e.g. '1.234,50' European style, or two numbers).
    """
    if raw is None or not str(raw).strip():
        raise ParseError("empty amount")
    t = ascii_digits(unicodedata.normalize("NFKC", str(raw)))
    t = _CURRENCY_TOKENS.sub("", t).strip()
    negative = False
    if t.startswith("(") and t.endswith(")"):
        negative, t = True, t[1:-1].strip()
    if t.startswith("-"):
        negative, t = True, t[1:].strip()
    if re.search(r"\d\s+\d", t):
        raise ParseError(f"digits separated by spaces are ambiguous: {raw!r}")
    t = t.replace(" ", "")
    if not re.fullmatch(r"\d{1,3}(,\d{3})*(\.\d+)?|\d+(\.\d+)?", t):
        raise ParseError(f"not a single unambiguous amount: {raw!r}")
    try:
        value = Decimal(t.replace(",", ""))
    except InvalidOperation as e:  # pragma: no cover - regex guards this
        raise ParseError(str(e)) from e
    return -value if negative else value


def parse_rate(raw: str | None) -> Decimal:
    """'5%', '5 %', '٥٪', '0.05' -> Decimal('5')."""
    if raw is None or not str(raw).strip():
        raise ParseError("empty rate")
    t = ascii_digits(unicodedata.normalize("NFKC", str(raw))).replace(" ", "")
    m = re.fullmatch(r"%?(\d+(?:\.\d+)?)%?", t)
    if not m:
        raise ParseError(f"not a rate: {raw!r}")
    v = Decimal(m.group(1))
    if "%" not in t and v < 1:
        v = v * 100
    return v.normalize() if v != v.to_integral() else v.quantize(Decimal("1"))


# --------------------------------------------------------------------------
# TRN
# --------------------------------------------------------------------------


def parse_trn(raw: str | None) -> str:
    """Return the digit string of a TRN (spaces / dashes removed). Length is checked by rules."""
    if raw is None or not str(raw).strip():
        raise ParseError("empty TRN")
    t = ascii_digits(unicodedata.normalize("NFKC", str(raw)))
    t = re.sub(r"(?i)\b(trn|tax\s*registration\s*(number|no\.?))\b[:\s]*", "", t)
    digits = re.sub(r"[\s\-./]", "", t)
    if not digits.isdigit():
        raise ParseError(f"TRN contains non-digits: {raw!r}")
    return digits


# --------------------------------------------------------------------------
# Currency
# --------------------------------------------------------------------------

_CURRENCY_MAP = {
    "aed": "AED", "dhs": "AED", "dh": "AED", "dirham": "AED", "dirhams": "AED",
    "uae dirham": "AED", "درهم": "AED", "دراهم": "AED", "درهم اماراتي": "AED", "د.ا": "AED", "د ا": "AED",
    "usd": "USD", "us$": "USD", "$": "USD", "us dollar": "USD", "دولار": "USD", "دولار امريكي": "USD",
    "eur": "EUR", "€": "EUR", "euro": "EUR",
    "gbp": "GBP", "£": "GBP", "pound sterling": "GBP",
    "sar": "SAR", "saudi riyal": "SAR", "ريال": "SAR", "ريال سعودي": "SAR",
}


def parse_currency(raw: str | None) -> str:
    if raw is None or not str(raw).strip():
        raise ParseError("empty currency")
    key = norm_text(raw).replace(".", "").strip()
    key2 = norm_text(raw).strip()
    for k in (key2, key):
        if k in _CURRENCY_MAP:
            return _CURRENCY_MAP[k]
    if re.fullmatch(r"[a-z]{3}", key):
        return key.upper()
    raise ParseError(f"unrecognised currency: {raw!r}")


# --------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10, "nov": 11, "november": 11,
    "dec": 12, "december": 12,
    # Arabic (Levantine/Gulf month names as commonly printed on UAE invoices)
    "يناير": 1, "فبراير": 2, "مارس": 3, "ابريل": 4, "مايو": 5, "يونيو": 6, "يوليو": 7,
    "اغسطس": 8, "سبتمبر": 9, "اكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12,
}


def parse_date(raw: str | None) -> tuple[date, Optional[str]]:
    """Return (date, note). UAE convention: numeric dates are DD/MM/YYYY.

    The note records an assumption when the numeric form was ambiguous.
    """
    if raw is None or not str(raw).strip():
        raise ParseError("empty date")
    t = norm_text(raw)
    t = re.sub(r"(?<=\d)(st|nd|rd|th)\b", "", t)

    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", t)
    if m:
        y, mo, d = map(int, m.groups())
        return _mk(y, mo, d, raw), None

    m = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", t)
    if m:
        d, mo, y = map(int, m.groups())
        note = None
        if d <= 12 and mo <= 12 and d != mo:
            note = "ambiguous numeric date - read as DD/MM/YYYY (UAE convention)"
        return _mk(y, mo, d, raw), note

    m = re.fullmatch(r"(\d{1,2})[\s\-]+([^\d\s,\-]+)[\s,\-]+(\d{4})", t)
    if m and m.group(2).rstrip(".") in _MONTHS:
        return _mk(int(m.group(3)), _MONTHS[m.group(2).rstrip(".")], int(m.group(1)), raw), None

    m = re.fullmatch(r"([^\d\s,\-]+)[\s\-]+(\d{1,2}),?[\s\-]+(\d{4})", t)
    if m and m.group(1).rstrip(".") in _MONTHS:
        return _mk(int(m.group(3)), _MONTHS[m.group(1).rstrip(".")], int(m.group(2)), raw), None

    raise ParseError(f"unrecognised date format: {raw!r}")


def _mk(y: int, mo: int, d: int, raw: str) -> date:
    try:
        return date(y, mo, d)
    except ValueError as e:
        raise ParseError(f"impossible date {raw!r}: {e}") from e


def digits_only(text: str | None) -> str:
    return re.sub(r"\D", "", ascii_digits(text or ""))
