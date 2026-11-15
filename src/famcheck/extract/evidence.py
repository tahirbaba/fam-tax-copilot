"""Zero-hallucination guardrails.

1. Evidence check - every extracted value must (a) appear inside its own evidence
   quote and (b) that quote must be found in the document's own text layer.
   A value that fails is discarded (never "best-guessed").
2. Consensus check - when the extractor ran more than once, every field must
   agree across passes. A disagreement discards the value.

PDF text extractors emit Arabic in presentation forms and sometimes reverse
digit runs (visual order). `norm_text` folds the forms; for Arabic documents a
reversed digit run is also accepted as a match.
"""

from __future__ import annotations

import re
from decimal import Decimal

from famcheck.core.models import (
    HEADER_FIELDS,
    LINE_FIELDS,
    CheckedField,
    ExtractedField,
    ExtractedInvoice,
    Extraction,
    FieldStatus,
)
from famcheck.ingest.loader import SourceDoc
from famcheck.ingest.normalize import ParseError, has_arabic, norm_text, parse_amount

_SPLIT = re.compile(r"[\s:،,;|()\[\]]+")


class _DocIndex:
    def __init__(self, doc: SourceDoc):
        self.verifiable = doc.kind == "pdf-text"
        self.norm = norm_text(doc.text)
        self.compact = self.norm.replace(" ", "")
        self.tokens = set(t for t in _SPLIT.split(self.norm) if t)
        self.arabic = has_arabic(doc.text)

    def contains(self, needle: str) -> bool:
        n = norm_text(needle)
        if not n:
            return False
        if n in self.norm or n.replace(" ", "") in self.compact:
            return True
        if self.arabic:
            # digit runs may come out of the PDF in visual (reversed) order
            for tok in (t for t in _SPLIT.split(n) if t):
                if not self._token_found(tok):
                    return False
            return True
        return False

    def _token_found(self, tok: str) -> bool:
        if tok in self.compact:
            return True
        if re.fullmatch(r"[\d.,]+", tok) and tok[::-1] in self.compact:
            return True
        return False


def _value_in_evidence(value: str, evidence: str) -> bool:
    v, e = norm_text(value), norm_text(evidence)
    if v in e or v.replace(" ", "") in e.replace(" ", ""):
        return True
    dv = re.sub(r"\D", "", v)
    if dv and len(dv) >= 3 and dv in re.sub(r"\D", "", e):
        return True
    return False


def check_field(name: str, f: ExtractedField, idx: _DocIndex) -> CheckedField:
    if f.value is None or not str(f.value).strip():
        return CheckedField(name=name, status=FieldStatus.ABSENT)
    value = str(f.value).strip()
    evidence = (f.evidence or value).strip()
    if not idx.verifiable:
        return CheckedField(
            name=name, raw=value, evidence=evidence, status=FieldStatus.VISUAL,
            note="no text layer (photo/scan) - read visually, needs human confirmation",
        )
    if not _value_in_evidence(value, evidence):
        return CheckedField(
            name=name, raw=value, evidence=evidence, status=FieldStatus.UNVERIFIED,
            note="value does not appear inside its own evidence quote - discarded",
        )
    if not (idx.contains(evidence) and idx.contains(value)):
        return CheckedField(
            name=name, raw=value, evidence=evidence, status=FieldStatus.UNVERIFIED,
            note="evidence quote not found in the document text - discarded",
        )
    return CheckedField(name=name, raw=value, evidence=evidence, status=FieldStatus.VERIFIED)


def _canon(value: str | None) -> str:
    if value is None or not str(value).strip():
        return ""
    try:
        return str(parse_amount(value).normalize())
    except ParseError:
        return norm_text(value).replace(" ", "")


def _apply_consensus(cf: CheckedField, others: list[ExtractedField]) -> CheckedField:
    if cf.status in (FieldStatus.UNVERIFIED,):
        return cf
    mine = _canon(cf.raw)
    for o in others:
        if _canon(o.value) != mine:
            return CheckedField(
                name=cf.name, raw=cf.raw, evidence=cf.evidence, status=FieldStatus.DISPUTED,
                note=f"extraction passes disagree ({cf.raw!r} vs {o.value!r}) - discarded",
            )
    return cf


def check_extraction(
    extraction: Extraction, doc: SourceDoc
) -> tuple[dict[str, CheckedField], list[dict[str, CheckedField]]]:
    idx = _DocIndex(doc)
    first: ExtractedInvoice = extraction.passes[0]
    rest = extraction.passes[1:]

    fields: dict[str, CheckedField] = {}
    for name in HEADER_FIELDS:
        cf = check_field(name, getattr(first, name), idx)
        if rest:
            cf = _apply_consensus(cf, [getattr(p, name) for p in rest])
        fields[name] = cf

    lines: list[dict[str, CheckedField]] = []
    counts_agree = all(len(p.line_items) == len(first.line_items) for p in rest)
    for i, line in enumerate(first.line_items):
        row: dict[str, CheckedField] = {}
        for name in LINE_FIELDS:
            cf = check_field(name, getattr(line, name), idx)
            if rest:
                if not counts_agree:
                    if cf.status != FieldStatus.ABSENT:
                        cf = CheckedField(
                            name=name, raw=cf.raw, evidence=cf.evidence,
                            status=FieldStatus.DISPUTED,
                            note="extraction passes found a different number of line items",
                        )
                else:
                    cf = _apply_consensus(cf, [getattr(p.line_items[i], name) for p in rest])
            row[name] = cf
        lines.append(row)
    return fields, lines


def to_decimal(cf: CheckedField) -> Decimal | None:
    if not cf.usable:
        return None
    return parse_amount(cf.raw)
