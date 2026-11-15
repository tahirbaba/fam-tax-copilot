"""Golden-set evaluation.

Two independent scores:

1. Decision accuracy - does every invoice get the expected status, findings and
   e-invoicing verdict? (tests the deterministic rules engine)
2. Extraction accuracy - comparing every extracted value with hand-made ground
   truth. The headline number is *auto-approved precision*: of the values the
   tool marked VERIFIED (and therefore used without a human), how many are right.
   Wrong values that the guardrails caught are counted separately.

When the replay cache is the hand-written seed, extraction accuracy is trivially
100% except for the deliberately corrupted inv14. Run `famcheck record` with an
API key to measure real Claude extractions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from famcheck import config
from famcheck.core.models import HEADER_FIELDS, LINE_FIELDS, ExtractedInvoice, FieldStatus, ReviewContext
from famcheck.core.pipeline import Extractor, _finalise, review_document
from famcheck.extract.evidence import _canon
from famcheck.ingest.loader import load


@dataclass
class EvalReport:
    rows: list[dict] = field(default_factory=list)
    decisions_ok: int = 0
    decisions_total: int = 0
    fields_total: int = 0
    verified_total: int = 0
    verified_correct: int = 0
    wrong_caught: int = 0
    wrong_missed: int = 0
    sources: set[str] = field(default_factory=set)

    @property
    def decision_accuracy(self) -> float:
        return self.decisions_ok / self.decisions_total if self.decisions_total else 0.0

    @property
    def auto_precision(self) -> float:
        return self.verified_correct / self.verified_total if self.verified_total else 0.0

    @property
    def coverage(self) -> float:
        return self.verified_correct / self.fields_total if self.fields_total else 0.0


def _pairs(truth: ExtractedInvoice, res) -> list[tuple[str, str | None, object]]:
    out = []
    for name in HEADER_FIELDS:
        out.append((name, getattr(truth, name).value, res.fields.get(name)))
    for i, tl in enumerate(truth.line_items):
        row = res.line_fields[i] if i < len(res.line_fields) else {}
        for name in LINE_FIELDS:
            out.append((f"line{i + 1}.{name}", getattr(tl, name).value, row.get(name)))
    return out


def run(golden_dir: Path | None = None, mode: str = "replay") -> EvalReport:
    gdir = golden_dir or config.GOLDEN_DIR
    ctx_data = json.loads((gdir / "_context.json").read_text(encoding="utf-8"))
    ctx = ReviewContext(
        client_name=ctx_data["client_name"], client_trn=ctx_data["client_trn"],
        today=date.fromisoformat(ctx_data["today"]),
    )
    extractor = Extractor(mode=mode)
    goldens = sorted(p for p in gdir.glob("*.json") if not p.name.startswith("_"))
    results, metas = [], []
    for gp in goldens:
        g = json.loads(gp.read_text(encoding="utf-8"))
        doc = load(config.SAMPLE_INVOICES / g["file"])
        results.append(review_document(doc, extractor, ctx))
        metas.append(g)
    _finalise(results)

    rep = EvalReport()
    for res, g in zip(results, metas):
        exp = g["expected"]
        got_findings = sorted({f.rule_id for f in res.findings if f.severity.value != "info"})
        ok = (res.status.value == exp["status"] and got_findings == sorted(exp["findings"])
              and res.einvoice_ready == exp["einvoice_ready"])
        rep.decisions_total += 1
        rep.decisions_ok += int(ok)
        rep.sources.add(res.extraction_source)

        truth = ExtractedInvoice.model_validate(g["truth"])
        wrong_fields = []
        for name, tv, cf in _pairs(truth, res):
            if tv is None:
                continue
            rep.fields_total += 1
            if cf is None:
                continue
            correct = _canon(cf.raw) == _canon(tv)
            if cf.status in (FieldStatus.VERIFIED, FieldStatus.VISUAL):
                rep.verified_total += 1
                if correct:
                    rep.verified_correct += 1
                else:
                    rep.wrong_missed += 1
                    wrong_fields.append(f"{name} (MISSED)")
            elif not correct and cf.raw is not None:
                rep.wrong_caught += 1
                wrong_fields.append(f"{name} (caught)")
        rep.rows.append({
            "file": g["file"], "expected": exp["status"], "got": res.status.value, "ok": ok,
            "expected_findings": sorted(exp["findings"]), "got_findings": got_findings,
            "wrong_fields": wrong_fields, "source": res.extraction_source,
        })
    return rep
