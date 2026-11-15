"""Report writers: JSON audit trail, Excel workbook, Zoho Books CSV, client HTML report."""

from __future__ import annotations

import csv
import io
import json
from decimal import Decimal
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from famcheck.core.models import BatchResult, Status
from famcheck.i18n import field_label, strings

TEMPLATES = Path(__file__).parent / "templates"
DEADLINES = [
    # Source: public reporting of the MoF/FTA phased timeline (verify on mof.gov.ae before client use)
    {"en": "Businesses with revenue of AED 50M or more: e-invoicing mandatory from 1 January 2027",
     "ar": "المنشآت التي تبلغ إيراداتها 50 مليون درهم أو أكثر: الفوترة الإلكترونية إلزامية اعتباراً من 1 يناير 2027"},
    {"en": "All other businesses: appoint an Accredited Service Provider by 31 March 2027; mandatory from 1 July 2027",
     "ar": "جميع المنشآت الأخرى: تعيين مزود خدمة معتمد بحلول 31 مارس 2027، والإلزام اعتباراً من 1 يوليو 2027"},
]

_FILLS = {
    Status.GREEN: PatternFill("solid", fgColor="D7F2E3"),
    Status.AMBER: PatternFill("solid", fgColor="FFF1CC"),
    Status.RED: PatternFill("solid", fgColor="FADBD8"),
}


def _d(v) -> float | None:
    return float(v) if isinstance(v, Decimal) else v


def to_json(batch: BatchResult) -> str:
    return batch.model_dump_json(indent=2)


def to_excel(batch: BatchResult, path: Path | None = None) -> bytes:
    wb = Workbook()
    bold = Font(bold=True)

    ws = wb.active
    ws.title = "Summary"
    s = batch.summary
    rows = [
        ("FAM Invoice Checker - batch", batch.batch_id),
        ("Created (UTC)", batch.created_at),
        ("Client", batch.context.client_name or ""),
        ("Client TRN", batch.context.client_trn or ""),
        ("Invoices", s.total),
        ("Valid (green)", s.green),
        ("Needs review (amber)", s.amber),
        ("Problem found (red)", s.red),
        ("VAT reviewed (AED)", _d(s.vat_reviewed_aed)),
        ("Input VAT at risk (AED)", _d(s.vat_at_risk_aed)),
        ("E-invoicing ready", f"{s.einvoice_ready} / {s.total} ({s.einvoice_ready_pct}%)"),
    ]
    for r in rows:
        ws.append(r)
        ws.cell(ws.max_row, 1).font = bold
    ws.append([])
    ws.append(["Rule pack", "Version", "Reviewed by"])
    for p in batch.rule_packs:
        ws.append([p["title_en"], p["version"], p["reviewed_by"] or "PENDING FAM REVIEW"])
    ws.column_dimensions["A"].width = 52
    ws.column_dimensions["B"].width = 40

    wi = wb.create_sheet("Invoices")
    head = ["File", "Status", "Supplier", "Supplier TRN", "Invoice no.", "Issue date", "Currency",
            "Subtotal", "VAT", "Total", "VAT at risk (AED)", "E-invoice ready", "Issues", "Extraction source"]
    wi.append(head)
    for r in batch.results:
        inv = r.invoice
        wi.append([
            r.file_name, r.status.value.upper(), inv.supplier_name, inv.supplier_trn, inv.invoice_number,
            inv.issue_date.isoformat() if inv.issue_date else None, inv.currency,
            _d(inv.subtotal), _d(inv.vat_amount), _d(inv.total_amount), _d(r.vat_at_risk_aed),
            "YES" if r.einvoice_ready else "NO",
            "; ".join(f"{f.rule_id} {f.title_en}" for f in r.findings if f.severity.value != "info"),
            r.extraction_source,
        ])
        wi.cell(wi.max_row, 2).fill = _FILLS[r.status]

    wf = wb.create_sheet("Findings")
    wf.append(["File", "Rule", "Severity", "Impact", "Finding", "Detail", "Detail (Arabic)", "Legal basis"])
    for r in batch.results:
        for f in r.findings:
            wf.append([r.file_name, f.rule_id, f.severity.value, f.impact.value, f.title_en, f.message_en, f.message_ar, f.citation])

    wv = wb.create_sheet("Fields & evidence")
    wv.append(["File", "Field", "Value", "Check", "Evidence (verbatim)", "Note"])
    for r in batch.results:
        for name, cf in r.fields.items():
            wv.append([r.file_name, field_label(name), cf.raw, cf.status.value, cf.evidence, cf.note])
        for i, row in enumerate(r.line_fields, start=1):
            for name, cf in row.items():
                wv.append([r.file_name, f"Line {i} {field_label(name).lower()}", cf.raw, cf.status.value, cf.evidence, cf.note])

    for sheet in (wi, wf, wv):
        for c in sheet[1]:
            c.font = bold
        sheet.freeze_panes = "A2"
        for i, col in enumerate(sheet.columns, start=1):
            width = max(len(str(c.value or "")) for c in col)
            sheet.column_dimensions[get_column_letter(i)].width = min(max(10, width + 2), 60)
            for c in col:
                c.alignment = Alignment(wrap_text=True, vertical="top")

    buf = io.BytesIO()
    wb.save(buf)
    data = buf.getvalue()
    if path:
        path.write_bytes(data)
    return data


ZOHO_COLUMNS = ["Bill Date", "Bill Number", "Vendor Name", "Vendor TRN", "Currency Code", "Item Name",
                "Quantity", "Rate", "Tax Percentage", "Item Total", "Tax Amount", "Bill Total", "Source File"]


def to_zoho_csv(batch: BatchResult) -> str:
    """One row per line item, GREEN invoices only (amber/red never flow into the books).
    Column names follow Zoho Books' bill import; confirm the mapping in Zoho's import wizard."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(ZOHO_COLUMNS)
    for r in batch.results:
        if r.status != Status.GREEN:
            continue
        inv = r.invoice
        for li in inv.line_items:
            w.writerow([
                inv.issue_date.isoformat() if inv.issue_date else "", inv.invoice_number, inv.supplier_name,
                inv.supplier_trn, inv.currency or "AED", li.description,
                li.quantity, li.unit_price, li.vat_rate if li.vat_rate is not None else inv.vat_rate,
                li.net_amount, li.vat_amount, inv.total_amount, r.file_name,
            ])
    return out.getvalue()


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))
    env.filters["money"] = lambda v: "—" if v is None else f"{Decimal(v):,.2f}"
    return env


def to_client_html(batch: BatchResult, lang: str = "en") -> str:
    t = strings(lang)
    return _env().get_template("client_report.html.j2").render(
        b=batch, s=batch.summary, t=t, lang=lang, deadlines=DEADLINES, field_label=field_label,
    )


def write_all(batch: BatchResult, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": out_dir / "results.json",
        "excel": out_dir / "invoice_review.xlsx",
        "zoho": out_dir / "zoho_bills_import.csv",
        "report_en": out_dir / "client_report_en.html",
        "report_ar": out_dir / "client_report_ar.html",
    }
    paths["json"].write_text(to_json(batch), encoding="utf-8")
    to_excel(batch, paths["excel"])
    paths["zoho"].write_text(to_zoho_csv(batch), encoding="utf-8-sig")
    paths["report_en"].write_text(to_client_html(batch, "en"), encoding="utf-8")
    paths["report_ar"].write_text(to_client_html(batch, "ar"), encoding="utf-8")
    return paths


def batch_from_json(path: Path) -> BatchResult:
    return BatchResult.model_validate(json.loads(path.read_text(encoding="utf-8")))
