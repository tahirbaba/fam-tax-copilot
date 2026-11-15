"""End-to-end pipeline: load -> extract (Claude or replay) -> verify evidence ->
normalise -> rules -> status. Only the extract step touches a language model."""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Iterable, Optional

from famcheck import config
from famcheck.core.build import build_invoice
from famcheck.core.models import (
    BatchResult,
    BatchSummary,
    Extraction,
    Impact,
    InvoiceResult,
    ReviewContext,
    Severity,
    Status,
)
from famcheck.extract.evidence import check_extraction
from famcheck.extract.replay import ReplayStore
from famcheck.ingest.loader import SourceDoc, UnsupportedFile, load
from famcheck.rules.checks import RuleInput, full_invoice_required
from famcheck.rules.engine import evaluate, load_packs, rule_by_id


class Extractor:
    """Chooses replay vs live Claude extraction according to the mode."""

    def __init__(self, mode: str | None = None, passes: int | None = None):
        self.mode = mode or config.mode()
        self.passes = passes or config.passes()
        self.seed = ReplayStore(config.SEED_REPLAY_DIR)
        self.cache = ReplayStore(config.USER_CACHE_DIR)
        self._claude = None

    def _lookup(self, sha: str):
        return self.cache.get(sha) or self.seed.get(sha)

    def _live(self, doc: SourceDoc) -> Extraction:
        if self._claude is None:
            from famcheck.extract.claude import ClaudeExtractor

            self._claude = ClaudeExtractor()
        passes = self._claude.extract(doc, self.passes)
        source = self._claude.model
        if self.mode in ("record", "auto"):
            target = self.seed if doc.path.resolve().parent == config.SAMPLE_INVOICES.resolve() else self.cache
            target.put(doc.sha256, source, passes, doc.name)
        return Extraction(source=source, passes=passes)

    def extract(self, doc: SourceDoc) -> Extraction:
        if self.mode in ("replay", "auto"):
            hit = self._lookup(doc.sha256)
            if hit:
                source, passes = hit
                return Extraction(source=f"replay:{source}", passes=passes)
            if self.mode == "replay":
                return Extraction(source="none", passes=[], error="not in replay cache (run with --mode live or record)")
            if not config.has_credentials():
                return Extraction(
                    source="none", passes=[],
                    error="no ANTHROPIC_API_KEY configured - cannot read a new invoice (demo invoices still work)",
                )
        try:
            return self._live(doc)
        except Exception as e:  # surfaced as a GUARD-003 finding, never silently dropped
            return Extraction(source="none", passes=[], error=f"{type(e).__name__}: {e}")


def _status(result: InvoiceResult) -> Status:
    vat_relevant = [f for f in result.findings if f.impact != Impact.EINVOICE_GAP]
    if any(f.severity == Severity.ERROR and f.impact == Impact.INPUT_VAT_AT_RISK for f in vat_relevant):
        return Status.RED
    if any(f.severity in (Severity.ERROR, Severity.WARNING) for f in vat_relevant):
        return Status.AMBER
    if result.extraction_error:
        return Status.AMBER
    return Status.GREEN


def _vat_aed(result: InvoiceResult) -> Decimal:
    inv = result.invoice
    if inv.currency in (None, "AED") and inv.vat_amount is not None:
        return inv.vat_amount
    if inv.vat_amount_aed is not None:
        return inv.vat_amount_aed
    return Decimal("0")


def review_document(doc: SourceDoc, extractor: Extractor, ctx: ReviewContext) -> InvoiceResult:
    extraction = extractor.extract(doc)
    result = InvoiceResult(
        file_name=doc.name, sha256=doc.sha256, kind=doc.kind, language=doc.language,
        extraction_source=extraction.source,
    )
    if extraction.error or not extraction.passes:
        result.extraction_error = extraction.error or "no extraction"
        result.findings.append(rule_by_id("GUARD-003").make_finding({"found": result.extraction_error}))
        result.status = _status(result)
        return result

    fields, lines = check_extraction(extraction, doc)
    inv = build_invoice(fields, lines)
    full_required = full_invoice_required(inv)
    ri = RuleInput(inv=inv, fields=fields, lines=lines, ctx=ctx, kind=doc.kind, full_invoice_required=full_required)
    result.fields = fields
    result.line_fields = lines
    result.invoice = inv
    result.full_invoice_required = full_required
    result.findings = evaluate(ri)
    if doc.language == "unknown":
        result.language = "image"
    return result


def _finalise(results: list[InvoiceResult]) -> None:
    # batch-level: duplicates (same supplier TRN + invoice number)
    seen: dict[tuple[str, str], str] = {}
    for r in results:
        inv = r.invoice
        if inv.supplier_trn and inv.invoice_number:
            key = (inv.supplier_trn, inv.invoice_number.strip().upper())
            if key in seen:
                r.findings.append(rule_by_id("GUARD-004").make_finding({"found": seen[key], "field": "invoice_number"}))
            else:
                seen[key] = r.file_name
    for r in results:
        r.status = _status(r)
        r.einvoice_ready = (
            r.status == Status.GREEN
            and not r.extraction_error
            and not any(f.impact == Impact.EINVOICE_GAP for f in r.findings)
        )
        r.vat_at_risk_aed = _vat_aed(r) if r.status == Status.RED else Decimal("0")


def summarise(results: list[InvoiceResult]) -> BatchSummary:
    s = BatchSummary(total=len(results))
    gap_counter: Counter[str] = Counter()
    for r in results:
        setattr(s, r.status.value, getattr(s, r.status.value) + 1)
        s.vat_at_risk_aed += r.vat_at_risk_aed
        s.vat_reviewed_aed += _vat_aed(r)
        s.einvoice_ready += int(r.einvoice_ready)
        for rid in {f.rule_id for f in r.findings if f.impact == Impact.EINVOICE_GAP}:
            gap_counter[rid] += 1
    s.einvoice_ready_pct = round(100 * s.einvoice_ready / s.total) if s.total else 0
    for rid, n in gap_counter.most_common(5):
        rule = rule_by_id(rid)
        s.top_gaps.append({"rule_id": rid, "count": n, "title_en": rule.title_en, "title_ar": rule.title_ar})
    return s


def review_paths(
    paths: Iterable[Path | str],
    ctx: Optional[ReviewContext] = None,
    mode: str | None = None,
    names: Optional[list[str]] = None,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> BatchResult:
    ctx = ctx or ReviewContext()
    extractor = Extractor(mode=mode)
    files = [Path(p) for p in paths]
    results: list[InvoiceResult] = []
    for i, p in enumerate(files):
        name = names[i] if names else p.name
        if on_progress:
            on_progress(i + 1, len(files), name)
        try:
            doc = load(p, display_name=name)
        except UnsupportedFile as e:
            r = InvoiceResult(file_name=name, sha256="", kind="unsupported", language="unknown",
                              extraction_source="none", extraction_error=str(e))
            r.findings.append(rule_by_id("GUARD-003").make_finding({"found": str(e)}))
            results.append(r)
            continue
        results.append(review_document(doc, extractor, ctx))
    _finalise(results)
    return BatchResult(
        batch_id=uuid.uuid4().hex[:10],
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        context=ctx,
        results=results,
        summary=summarise(results),
        rule_packs=[p.meta() for p in load_packs()],
    )


def collect_files(inputs: Iterable[Path | str]) -> list[Path]:
    out: list[Path] = []
    for item in inputs:
        p = Path(item)
        if p.is_dir():
            out.extend(sorted(x for x in p.iterdir() if x.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg", ".webp"}))
        else:
            out.append(p)
    return out
