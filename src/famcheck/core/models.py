"""Domain models shared by every layer.

Design rule: the language model only ever produces `ExtractedInvoice`
(verbatim strings + the evidence quote they came from). Everything after that
(numbers, dates, decisions) is computed by deterministic code into the models
below.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------
# 1. What the extractor (Claude, or the replay cache) returns
# --------------------------------------------------------------------------


class ExtractedField(BaseModel):
    """A single value copied from the document, plus the exact text it came from."""

    value: Optional[str] = Field(
        default=None,
        description="The value exactly as printed on the document. null if not present.",
    )
    evidence: Optional[str] = Field(
        default=None,
        description="A short verbatim quote from the document that contains the value "
        "(e.g. the label and the value). null if value is null.",
    )


class ExtractedLine(BaseModel):
    description: ExtractedField = Field(default_factory=ExtractedField)
    quantity: ExtractedField = Field(default_factory=ExtractedField)
    unit_price: ExtractedField = Field(default_factory=ExtractedField)
    net_amount: ExtractedField = Field(default_factory=ExtractedField)
    vat_rate: ExtractedField = Field(default_factory=ExtractedField)
    vat_amount: ExtractedField = Field(default_factory=ExtractedField)


HEADER_FIELDS: tuple[str, ...] = (
    "document_title",
    "invoice_number",
    "issue_date",
    "supply_date",
    "currency",
    "supplier_name",
    "supplier_address",
    "supplier_trn",
    "customer_name",
    "customer_address",
    "customer_trn",
    "subtotal",
    "discount",
    "vat_rate",
    "vat_amount",
    "total_amount",
    "vat_amount_aed",
    "exchange_rate",
)

LINE_FIELDS: tuple[str, ...] = (
    "description",
    "quantity",
    "unit_price",
    "net_amount",
    "vat_rate",
    "vat_amount",
)


class ExtractedInvoice(BaseModel):
    """Schema the extractor must fill. All values are raw strings - no maths."""

    document_title: ExtractedField = Field(default_factory=ExtractedField)
    invoice_number: ExtractedField = Field(default_factory=ExtractedField)
    issue_date: ExtractedField = Field(default_factory=ExtractedField)
    supply_date: ExtractedField = Field(default_factory=ExtractedField)
    currency: ExtractedField = Field(default_factory=ExtractedField)
    supplier_name: ExtractedField = Field(default_factory=ExtractedField)
    supplier_address: ExtractedField = Field(default_factory=ExtractedField)
    supplier_trn: ExtractedField = Field(default_factory=ExtractedField)
    customer_name: ExtractedField = Field(default_factory=ExtractedField)
    customer_address: ExtractedField = Field(default_factory=ExtractedField)
    customer_trn: ExtractedField = Field(default_factory=ExtractedField)
    line_items: list[ExtractedLine] = Field(default_factory=list)
    subtotal: ExtractedField = Field(default_factory=ExtractedField)
    discount: ExtractedField = Field(default_factory=ExtractedField)
    vat_rate: ExtractedField = Field(default_factory=ExtractedField)
    vat_amount: ExtractedField = Field(default_factory=ExtractedField)
    total_amount: ExtractedField = Field(default_factory=ExtractedField)
    vat_amount_aed: ExtractedField = Field(default_factory=ExtractedField)
    exchange_rate: ExtractedField = Field(default_factory=ExtractedField)


# --------------------------------------------------------------------------
# 2. Verified + normalised invoice (produced by code)
# --------------------------------------------------------------------------


class FieldStatus(str, Enum):
    VERIFIED = "verified"  # evidence quote found in the document text
    VISUAL = "visual"  # source has no text layer (photo) - cannot be machine-verified
    UNVERIFIED = "unverified"  # evidence not found -> value discarded
    DISPUTED = "disputed"  # extraction passes disagree -> value discarded
    INVALID = "invalid"  # verified text but cannot be parsed (e.g. bad date)
    ABSENT = "absent"  # not on the document


class CheckedField(BaseModel):
    name: str
    raw: Optional[str] = None
    evidence: Optional[str] = None
    status: FieldStatus = FieldStatus.ABSENT
    note: Optional[str] = None

    @property
    def usable(self) -> bool:
        return self.status in (FieldStatus.VERIFIED, FieldStatus.VISUAL) and self.raw is not None


class LineItem(BaseModel):
    description: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    net_amount: Optional[Decimal] = None
    vat_rate: Optional[Decimal] = None
    vat_amount: Optional[Decimal] = None


class Invoice(BaseModel):
    """Normalised, typed view used by the rules engine. Only usable fields are filled."""

    document_title: Optional[str] = None
    invoice_number: Optional[str] = None
    issue_date: Optional[date] = None
    supply_date: Optional[date] = None
    currency: Optional[str] = None  # ISO 4217 code when recognised
    supplier_name: Optional[str] = None
    supplier_address: Optional[str] = None
    supplier_trn: Optional[str] = None  # digits only
    customer_name: Optional[str] = None
    customer_address: Optional[str] = None
    customer_trn: Optional[str] = None
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: Optional[Decimal] = None
    discount: Optional[Decimal] = None
    vat_rate: Optional[Decimal] = None
    vat_amount: Optional[Decimal] = None
    total_amount: Optional[Decimal] = None
    vat_amount_aed: Optional[Decimal] = None
    exchange_rate: Optional[Decimal] = None


# --------------------------------------------------------------------------
# 3. Rule findings and results
# --------------------------------------------------------------------------


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Impact(str, Enum):
    INPUT_VAT_AT_RISK = "input_vat_at_risk"
    EINVOICE_GAP = "einvoice_gap"
    NEEDS_REVIEW = "needs_review"
    DATA_QUALITY = "data_quality"


class Status(str, Enum):
    GREEN = "green"  # all checks passed on machine-verified data
    AMBER = "amber"  # a human must look (uncertain / unverifiable / warning)
    RED = "red"  # a definite compliance problem was found


class Finding(BaseModel):
    rule_id: str
    pack: str
    severity: Severity
    impact: Impact
    title_en: str
    title_ar: str
    message_en: str
    message_ar: str
    citation: Optional[str] = None
    field: Optional[str] = None


class Extraction(BaseModel):
    """What came back from the extractor, with provenance."""

    source: str  # e.g. "claude-opus-5-5", "replay:claude-opus-5-5", "replay:seed"
    passes: list[ExtractedInvoice]
    error: Optional[str] = None


class InvoiceResult(BaseModel):
    file_name: str
    sha256: str
    kind: str  # pdf-text | pdf-scanned | image
    language: str  # en | ar | mixed | unknown
    extraction_source: str
    fields: dict[str, CheckedField] = Field(default_factory=dict)
    line_fields: list[dict[str, CheckedField]] = Field(default_factory=list)
    invoice: Invoice = Field(default_factory=Invoice)
    findings: list[Finding] = Field(default_factory=list)
    status: Status = Status.AMBER
    full_invoice_required: Optional[bool] = None
    einvoice_ready: bool = False
    vat_at_risk_aed: Decimal = Decimal("0")
    extraction_error: Optional[str] = None

    def finding_ids(self) -> list[str]:
        return sorted({f.rule_id for f in self.findings})


class BatchSummary(BaseModel):
    total: int = 0
    green: int = 0
    amber: int = 0
    red: int = 0
    vat_at_risk_aed: Decimal = Decimal("0")
    vat_reviewed_aed: Decimal = Decimal("0")
    einvoice_ready: int = 0
    einvoice_ready_pct: int = 0
    top_gaps: list[dict[str, Any]] = Field(default_factory=list)


class ReviewContext(BaseModel):
    client_name: Optional[str] = None
    client_trn: Optional[str] = None
    today: date = Field(default_factory=date.today)


class BatchResult(BaseModel):
    batch_id: str
    created_at: str
    context: ReviewContext
    results: list[InvoiceResult]
    summary: BatchSummary
    rule_packs: list[dict[str, Any]] = Field(default_factory=list)
