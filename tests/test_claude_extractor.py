"""The Claude extractor is tested with a fake client - no network, no key."""
from types import SimpleNamespace

import pytest

from famcheck import config
from famcheck.core.models import ExtractedField, ExtractedInvoice
from famcheck.extract import claude as claude_mod
from famcheck.ingest.loader import load


class FakeMessages:
    def __init__(self, stop_reason="end_turn"):
        self.calls = []
        self.stop_reason = stop_reason

    def parse(self, **kw):
        self.calls.append(kw)
        inv = ExtractedInvoice(document_title=ExtractedField(value="TAX INVOICE", evidence="TAX INVOICE"))
        return SimpleNamespace(stop_reason=self.stop_reason, parsed_output=inv)


def _extractor(stop_reason="end_turn"):
    ex = claude_mod.ClaudeExtractor.__new__(claude_mod.ClaudeExtractor)
    ex.model, ex.effort = "claude-opus-5-5", "high"
    ex.client = SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages(stop_reason)))
    return ex


def test_request_shape():
    ex = _extractor()
    doc = load(config.SAMPLE_INVOICES / "inv01_en_valid.pdf")
    out = ex.extract(doc, passes=2)
    calls = ex.client.beta.messages.calls
    assert len(out) == 2 and len(calls) == 2
    kw = calls[0]
    assert kw["model"] == "claude-opus-5-5"
    assert kw["output_format"] is ExtractedInvoice
    assert kw["messages"][0]["content"][0]["type"] == "document"
    assert "NEVER calculate" in kw["system"]


def test_refusal_raises():
    ex = _extractor("refusal")
    doc = load(config.SAMPLE_INVOICES / "inv01_en_valid.pdf")
    with pytest.raises(claude_mod.ExtractionRefused):
        ex.extract_once(doc)
