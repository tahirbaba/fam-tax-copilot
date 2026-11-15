"""Claude extraction - the ONLY place a language model is used.

The model is asked to *copy*, never to compute or judge: every value must be
verbatim, paired with an evidence quote, or null. Output is constrained by a
JSON schema (structured outputs), then independently verified by
`famcheck.extract.evidence`.
"""

from __future__ import annotations

import base64
import os

from famcheck.core.models import ExtractedInvoice
from famcheck.ingest.loader import SourceDoc

DEFAULT_MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """You are a meticulous data-entry clerk at a UAE audit and tax firm.
You transcribe fields from ONE supplier invoice into a fixed schema. The invoice may be
in English, Arabic, or both.

Rules - follow all of them:
1. Copy values EXACTLY as printed (same digits, same language, same punctuation).
   Never translate, convert currency, reformat dates or fix spelling.
2. NEVER calculate, infer or fill in a value that is not printed on the document.
   If a field is not printed, return null for both value and evidence.
   Example: if VAT amount is not printed, do not compute 5% - return null.
3. For every non-null value also return `evidence`: a short verbatim quote from the
   document (usually the label plus the value, e.g. "TRN: 100234567890003" or
   "الرقم الضريبي: ١٠٠٢٣٤٥٦٧٨٩٠٠٠٣") that contains the value.
4. document_title is the heading that names the document type (e.g. "Tax Invoice",
   "INVOICE", "فاتورة ضريبية", "Receipt").
5. supplier = the business that issued the invoice; customer = the business billed.
6. line_items: one entry per printed line, in printed order. Use the line's own
   printed numbers only.
7. currency: the currency label as printed (e.g. "AED", "درهم", "USD").
8. vat_amount_aed / exchange_rate: only if the invoice separately prints the VAT in
   AED or an exchange rate.
If you are unsure whether something is the requested field, return null - a missing
value is reviewed by a human, a wrong value causes a compliance error."""

USER_PROMPT = "Transcribe this invoice into the schema. Remember: verbatim values with evidence, null when not printed."


class ExtractionRefused(RuntimeError):
    pass


class ClaudeExtractor:
    def __init__(self, model: str | None = None, effort: str = "high"):
        import anthropic  # imported lazily so replay/demo mode works without credentials

        self.model = model or os.environ.get("FAMCHECK_MODEL", DEFAULT_MODEL)
        self.effort = effort
        self.client = anthropic.Anthropic()

    def _content(self, doc: SourceDoc) -> list[dict]:
        b64 = base64.standard_b64encode(doc.data).decode("ascii")
        if doc.media_type == "application/pdf":
            block = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}
        else:
            block = {"type": "image", "source": {"type": "base64", "media_type": doc.media_type, "data": b64}}
        return [block, {"type": "text", "text": USER_PROMPT}]

    def extract_once(self, doc: SourceDoc) -> ExtractedInvoice:
        response = self.client.beta.messages.parse(
            model=self.model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": self._content(doc)}],
            output_format=ExtractedInvoice,
            output_config={"effort": self.effort},
            # On a safety-classifier decline, the API re-runs on a fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            raise ExtractionRefused("the model declined to process this document")
        if response.stop_reason == "max_tokens":
            raise RuntimeError("extraction output was truncated (max_tokens)")
        parsed = response.parsed_output
        if parsed is None:
            raise RuntimeError("model returned no structured output")
        return ExtractedInvoice.model_validate(parsed.model_dump())

    def extract(self, doc: SourceDoc, passes: int = 2) -> list[ExtractedInvoice]:
        return [self.extract_once(doc) for _ in range(max(1, passes))]
