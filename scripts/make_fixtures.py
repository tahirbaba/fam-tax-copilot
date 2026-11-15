"""Generate the synthetic sample invoices, their ground truth, and the seeded replay cache.

All companies, TRNs and amounts are FICTITIOUS. Each invoice carries one planted
defect (or none) so every rule can be demonstrated and regression-tested.

Usage (from repo root):
    python scripts/make_fixtures.py          # writes HTML + jobs.json into fixtures/_build
    node scripts/render_fixtures.js          # renders PDFs / PNG into fixtures/invoices
    python scripts/make_fixtures.py --seal   # hashes rendered files -> golden + replay
"""

from __future__ import annotations

import hashlib
import html
import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from famcheck.core.models import ExtractedField, ExtractedInvoice, ExtractedLine  # noqa: E402

FIX = ROOT / "fixtures"
BUILD = FIX / "_build"
INVOICES = FIX / "invoices"
GOLDEN = FIX / "golden"
REPLAY = FIX / "replay"

CLIENT = {
    "name_en": "Al Noor Restaurants LLC",
    "name_ar": "مطاعم النور ذ.م.م",
    "address_en": "Shop 12, Al Wasl Road, Jumeirah 1, Dubai, UAE",
    "address_ar": "محل 12، شارع الوصل، جميرا 1، دبي، الإمارات العربية المتحدة",
    "trn": "100345678900003",
}
EVAL_TODAY = "2026-11-15"

AR_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def D(x: str) -> Decimal:
    return Decimal(x)


def money(v: Decimal) -> str:
    return f"{v.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,.2f}"


def line(desc, qty, unit, rate="5"):
    qty, unit, rate = D(str(qty)), D(unit), D(rate)
    net = (qty * unit).quantize(Decimal("0.01"))
    vat = (net * rate / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {"desc": desc, "qty": qty, "unit": unit, "net": net, "rate": rate, "vat": vat}


def totals(lines, vat_override=None):
    sub = sum((li["net"] for li in lines), Decimal("0"))
    rate = lines[0]["rate"]
    vat = vat_override if vat_override is not None else (sub * rate / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return sub, rate, vat, sub + vat


def qty_str(q: Decimal) -> str:
    return str(int(q)) if q == q.to_integral() else format(q.normalize(), "f")


# ---------------------------------------------------------------------------
# Invoice specifications
# ---------------------------------------------------------------------------

SPECS: list[dict] = []


def spec(**kw):
    kw.setdefault("lang", "en")
    kw.setdefault("render", "pdf")
    kw.setdefault("title", "TAX INVOICE")
    kw.setdefault("currency", "AED")
    kw.setdefault("customer", {"name": CLIENT["name_en"], "address": CLIENT["address_en"], "trn": CLIENT["trn"]})
    kw.setdefault("seed_overrides", {})
    sub, rate, vat, total = totals(kw["lines"], kw.pop("vat_override", None))
    if "total_override" in kw:
        total = kw.pop("total_override")
    kw.update(subtotal=sub, rate=rate, vat=vat, total=total)
    SPECS.append(kw)


spec(
    id="inv01_en_valid",
    supplier={"name": "Gulf Fresh Produce Trading LLC", "address": "Warehouse 7, Al Aweer Central Market, Dubai, UAE", "trn": "100234567890003"},
    number="GF-2026-0412", date="12/10/2026",
    lines=[line("Tomatoes (kg)", 120, "4.50"), line("Red onions (kg)", 200, "2.25"), line("Fresh herbs bundle", 30, "6.00")],
    expected={"status": "green", "findings": [], "einvoice_ready": True},
    note="Clean English tax invoice.",
)
spec(
    id="inv02_ar_valid", lang="ar", title="فاتورة ضريبية", currency="درهم",
    supplier={"name": "شركة النخيل للتجارة العامة ذ.م.م", "address": "ديرة، شارع المكتوم، دبي، الإمارات العربية المتحدة",
              "trn": "100456789012345", "trn_display": "100456789012345".translate(AR_DIGITS)},
    customer={"name": CLIENT["name_ar"], "address": CLIENT["address_ar"], "trn": CLIENT["trn"]},
    number="NK-2026-077", date="08/10/2026",
    lines=[line("أرز بسمتي (كيس 25 كجم)", 10, "145.00"), line("زيت دوار الشمس (20 لتر)", 6, "210.00")],
    expected={"status": "green", "findings": [], "einvoice_ready": True},
    note="Arabic tax invoice; supplier TRN printed in Arabic-Indic digits.",
)
spec(
    id="inv03_bi_valid", lang="bi", title="TAX INVOICE / فاتورة ضريبية",
    supplier={"name": "Emirates Kitchen Equipment LLC", "address": "Plot 22, Al Quoz Industrial Area 3, Dubai, UAE", "trn": "100567890123456"},
    number="EKE/INV/2026/1189", date="15 Oct 2026",
    lines=[line("Commercial combi oven", 1, "18500.00"), line("Stainless steel prep table", 2, "2350.00"), line("Installation service", 1, "1200.00")],
    expected={"status": "green", "findings": [], "einvoice_ready": True},
    note="Bilingual invoice above AED 10,000 - full tax invoice requirements apply and are met.",
)
spec(
    id="inv04_en_vat_wrong",
    supplier={"name": "Pure Aqua Water Supplies LLC", "address": "Unit 4, Dubai Investments Park 1, Dubai, UAE", "trn": "100678901234567"},
    number="PAW-88213", date="03/10/2026",
    lines=[line("5 gallon water bottles", 300, "7.00"), line("Water dispenser rental (monthly)", 4, "75.00")],
    vat_override=D("125.00"),
    expected={"status": "red", "findings": ["MATH-003"], "einvoice_ready": False},
    note="VAT printed as 125.00; 5% of 2,400.00 is 120.00.",
)
spec(
    id="inv05_en_no_tax_title", title="INVOICE",
    supplier={"name": "Sparkle Cleaning Services LLC", "address": "Office 305, Al Barsha Business Centre, Dubai, UAE", "trn": "100789012345678"},
    number="SCS-1022", date="20/10/2026",
    lines=[line("Deep kitchen cleaning", 1, "1800.00"), line("Grease trap service", 2, "350.00")],
    expected={"status": "red", "findings": ["VAT-001"], "einvoice_ready": False},
    note='Titled "INVOICE", not "Tax Invoice".',
)
spec(
    id="inv06_en_bad_trn",
    supplier={"name": "Dubai Meat Traders LLC", "address": "Al Ras Area, Deira, Dubai, UAE", "trn": "10089012345678"},
    number="DMT-55410", date="10/10/2026",
    lines=[line("Lamb leg (kg)", 80, "38.00"), line("Chicken breast (kg)", 150, "21.50")],
    expected={"status": "red", "findings": ["VAT-005"], "einvoice_ready": False},
    note="Supplier TRN has 14 digits.",
)
spec(
    id="inv07_ar_missing_customer_trn", lang="ar", title="فاتورة ضريبية", currency="درهم",
    supplier={"name": "مؤسسة الواحة للتجهيزات الفندقية", "address": "القوز الصناعية 4، دبي، الإمارات العربية المتحدة", "trn": "100901234567890"},
    customer={"name": CLIENT["name_ar"], "address": CLIENT["address_ar"], "trn": None},
    number="WH-3391", date="22/10/2026",
    lines=[line("أطباق خزفية", 400, "22.00"), line("أكواب زجاجية", 600, "6.50")],
    expected={"status": "red", "findings": ["EINV-002", "VAT-013"], "einvoice_ready": False},
    note="Arabic invoice above AED 10,000 without the customer's TRN.",
)
spec(
    id="inv08_en_usd_no_aed", currency="USD",
    supplier={"name": "CloudPOS Systems FZ-LLC", "address": "Building 9, Dubai Internet City, Dubai, UAE", "trn": "100112233445566"},
    number="CPOS-2026-3307", date="01/10/2026",
    lines=[line("POS software subscription (annual, per terminal)", 3, "1200.00")],
    expected={"status": "red", "findings": ["VAT-016"], "einvoice_ready": False},
    note="Invoice in USD without the VAT amount in AED.",
)
spec(
    id="inv09_en_duplicate",
    supplier={"name": "Gulf Fresh Produce Trading LLC", "address": "Warehouse 7, Al Aweer Central Market, Dubai, UAE", "trn": "100234567890003"},
    number="GF-2026-0412", date="12/10/2026", watermark="COPY",
    lines=[line("Tomatoes (kg)", 120, "4.50"), line("Red onions (kg)", 200, "2.25"), line("Fresh herbs bundle", 30, "6.00")],
    expected={"status": "red", "findings": ["GUARD-004"], "einvoice_ready": False},
    note="Same supplier TRN and invoice number as inv01 (re-sent copy).",
)
spec(
    id="inv10_en_simplified", title="TAX INVOICE",
    supplier={"name": "Al Manara Bakery", "address": "Shop 3, Al Satwa Road, Dubai, UAE", "trn": "100223344556677"},
    customer={"name": None, "address": None, "trn": None},
    number="AMB-77120", date="25/10/2026",
    lines=[line("Arabic bread (pack)", 200, "1.50"), line("Butter croissants", 120, "3.00")],
    expected={"status": "green", "findings": ["EINV-002", "EINV-003", "EINV-004"], "einvoice_ready": False},
    note="Simplified tax invoice under AED 10,000 - valid for VAT, but lacks buyer data for e-invoicing.",
)
spec(
    id="inv11_en_wrong_customer",
    supplier={"name": "Prime Linen Supplies LLC", "address": "Warehouse 15, Al Qusais Industrial Area 2, Dubai, UAE", "trn": "100334455667788"},
    customer={"name": "Al Noor Catering Services LLC", "address": "Office 1102, Business Bay, Dubai, UAE", "trn": "100998877665544"},
    number="PLS-40918", date="18/10/2026",
    lines=[line("Table linen rental (monthly)", 1, "4200.00"), line("Chef uniforms", 25, "95.00")],
    expected={"status": "red", "findings": ["VAT-015"], "einvoice_ready": False},
    note="Addressed to a different legal entity (different TRN).",
)
spec(
    id="inv12_img_receipt", render="png",
    supplier={"name": "Quick Gas Cylinders Trading", "address": "Al Quoz 1, Dubai, UAE", "trn": "100445566778899"},
    customer={"name": CLIENT["name_en"], "address": None, "trn": None},
    number="QG-5521", date="14/10/2026",
    lines=[line("LPG cylinder refill", 10, "85.00")],
    expected={"status": "amber", "findings": ["EINV-002", "EINV-003", "GUARD-002"], "einvoice_ready": False},
    note="Photo of a receipt - no text layer, so it is never auto-approved.",
)
spec(
    id="inv13_en_wrong_rate",
    supplier={"name": "Saffron & Spice Imports LLC", "address": "Spice Souk, Deira, Dubai, UAE", "trn": "100556677889900"},
    number="SSI-2026-208", date="09/10/2026",
    lines=[line("Saffron (100 g tin)", 2, "950.00", rate="15"), line("Green cardamom (kg)", 10, "85.00", rate="15")],
    expected={"status": "red", "findings": ["VAT-010"], "einvoice_ready": False},
    note="VAT charged at 15% (not a UAE rate).",
)
spec(
    id="inv14_en_misread_guardrail",
    supplier={"name": "Golden Fork Packaging LLC", "address": "Warehouse 2, Jebel Ali Industrial Area 1, Dubai, UAE", "trn": "100778899001122"},
    number="GFP-6603", date="27/10/2026",
    lines=[line("Takeaway containers (carton of 500)", 12, "165.00"), line("Paper bags (carton of 1000)", 8, "120.00")],
    seed_overrides={"supplier_trn": {"value": "100778899001133", "evidence": "TRN: 100778899001133"}},
    expected={"status": "amber", "findings": ["GUARD-001"], "einvoice_ready": False},
    note="SIMULATED AI ERROR: the cached extraction misreads the supplier TRN. The evidence check "
         "cannot find that TRN in the document, discards it and routes the invoice to a human.",
)


# ---------------------------------------------------------------------------
# Rendering (HTML) - labels per language
# ---------------------------------------------------------------------------

LABELS = {
    "en": {
        "trn": "TRN:", "bill_to": "Bill To:", "inv_no": "Invoice No:", "inv_date": "Invoice Date:", "currency": "Currency:",
        "cols": ["#", "Description", "Qty", "Unit Price", "Net Amount", "VAT %", "VAT Amount"],
        "subtotal": "Subtotal", "vat": "VAT", "total": "Total Amount Due", "thanks": "Thank you for your business.",
    },
    "ar": {
        "trn": "الرقم الضريبي:", "bill_to": "فاتورة إلى:", "inv_no": "رقم الفاتورة:", "inv_date": "تاريخ الفاتورة:", "currency": "العملة:",
        "cols": ["#", "الوصف", "الكمية", "سعر الوحدة", "المبلغ الصافي", "نسبة الضريبة", "مبلغ الضريبة"],
        "subtotal": "المجموع الفرعي", "vat": "ضريبة القيمة المضافة", "total": "المبلغ الإجمالي المستحق", "thanks": "شكراً لتعاملكم معنا.",
    },
    "bi": {
        "trn": "TRN / الرقم الضريبي:", "bill_to": "Bill To / فاتورة إلى:", "inv_no": "Invoice No / رقم الفاتورة:",
        "inv_date": "Date / التاريخ:", "currency": "Currency / العملة:",
        "cols": ["#", "Description / الوصف", "Qty / الكمية", "Unit Price / سعر الوحدة", "Net / الصافي", "VAT %", "VAT / الضريبة"],
        "subtotal": "Subtotal / المجموع الفرعي", "vat": "VAT / الضريبة", "total": "Total / الإجمالي", "thanks": "Thank you / شكراً لكم",
    },
}

CSS = """
body{font-family:'DejaVu Sans',sans-serif;font-size:11px;color:#1d2433;margin:36px}
h1{font-size:22px;letter-spacing:1px;margin:0 0 18px;color:#0b3d5c}
.row{display:flex;justify-content:space-between;gap:24px;margin-bottom:16px}
.box p{margin:2px 0}
table{width:100%;border-collapse:collapse;margin-top:8px}
th,td{border:1px solid #c9d2dc;padding:5px 6px;text-align:start}
th{background:#eef3f7}
td.n{text-align:end}
.tot{width:46%;margin-inline-start:auto;margin-top:12px}
.tot td{border:none;border-bottom:1px solid #e3e8ee}
.wm{position:fixed;top:40%;left:25%;font-size:110px;color:rgba(200,0,0,.12);transform:rotate(-25deg)}
.foot{margin-top:28px;color:#667}
"""


def esc(s) -> str:
    return html.escape(str(s))


def render_html(s: dict) -> str:
    L = LABELS[s["lang"]]
    d = "rtl" if s["lang"] == "ar" else "ltr"
    sup, cus = s["supplier"], s["customer"]
    trn_disp = sup.get("trn_display", sup["trn"])
    rows = []
    for i, li in enumerate(s["lines"], start=1):
        rows.append(
            f"<tr><td>{i}</td><td>{esc(li['desc'])}</td><td class=n>{qty_str(li['qty'])}</td>"
            f"<td class=n>{money(li['unit'])}</td><td class=n>{money(li['net'])}</td>"
            f"<td class=n>{li['rate']}%</td><td class=n>{money(li['vat'])}</td></tr>"
        )
    cust = []
    if any(cus.values()):
        cust.append(f"<p><b>{esc(L['bill_to'])}</b></p>")
        if cus.get("name"):
            cust.append(f"<p>{esc(cus['name'])}</p>")
        if cus.get("address"):
            cust.append(f"<p>{esc(cus['address'])}</p>")
        if cus.get("trn"):
            cust.append(f"<p>{esc(L['trn'])} {esc(cus['trn'])}</p>")
    wm = f"<div class=wm>{esc(s['watermark'])}</div>" if s.get("watermark") else ""
    return f"""<!doctype html><html dir="{d}"><head><meta charset="utf-8"><style>{CSS}</style></head><body>{wm}
<h1>{esc(s['title'])}</h1>
<div class=row>
 <div class=box><p><b>{esc(sup['name'])}</b></p><p>{esc(sup['address'])}</p><p>{esc(L['trn'])} {esc(trn_disp)}</p></div>
 <div class=box><p>{esc(L['inv_no'])} {esc(s['number'])}</p><p>{esc(L['inv_date'])} {esc(s['date'])}</p><p>{esc(L['currency'])} {esc(s['currency'])}</p></div>
</div>
<div class=box>{''.join(cust)}</div>
<table><thead><tr>{''.join(f'<th>{esc(c)}</th>' for c in L['cols'])}</tr></thead><tbody>{''.join(rows)}</tbody></table>
<table class=tot>
<tr><td>{esc(L['subtotal'])}</td><td class=n>{money(s['subtotal'])}</td></tr>
<tr><td>{esc(L['vat'])} {s['rate']}%</td><td class=n>{money(s['vat'])}</td></tr>
<tr><td><b>{esc(L['total'])}</b></td><td class=n><b>{money(s['total'])}</b></td></tr>
</table>
<p class=foot>{esc(L['thanks'])}</p>
</body></html>"""


# ---------------------------------------------------------------------------
# Ground truth + seeded extraction
# ---------------------------------------------------------------------------


def F(value, evidence=None) -> ExtractedField:
    if value is None:
        return ExtractedField()
    return ExtractedField(value=value, evidence=evidence or value)


def truth_extraction(s: dict) -> ExtractedInvoice:
    L = LABELS[s["lang"]]
    sup, cus = s["supplier"], s["customer"]
    trn_disp = sup.get("trn_display", sup["trn"])
    lines = [
        ExtractedLine(
            description=F(li["desc"]), quantity=F(qty_str(li["qty"])), unit_price=F(money(li["unit"])),
            net_amount=F(money(li["net"])), vat_rate=F(f"{li['rate']}%"), vat_amount=F(money(li["vat"])),
        )
        for li in s["lines"]
    ]
    return ExtractedInvoice(
        document_title=F(s["title"]),
        invoice_number=F(s["number"], f"{L['inv_no']} {s['number']}"),
        issue_date=F(s["date"], f"{L['inv_date']} {s['date']}"),
        currency=F(s["currency"], f"{L['currency']} {s['currency']}"),
        supplier_name=F(sup["name"]),
        supplier_address=F(sup["address"]),
        supplier_trn=F(trn_disp, f"{L['trn']} {trn_disp}"),
        customer_name=F(cus.get("name")),
        customer_address=F(cus.get("address")),
        customer_trn=F(cus.get("trn"), f"{L['trn']} {cus['trn']}" if cus.get("trn") else None),
        line_items=lines,
        subtotal=F(money(s["subtotal"]), f"{L['subtotal']} {money(s['subtotal'])}"),
        vat_rate=F(f"{s['rate']}%", f"{L['vat']} {s['rate']}%"),
        vat_amount=F(money(s["vat"])),
        total_amount=F(money(s["total"]), f"{L['total']} {money(s['total'])}"),
    )


def seed_extraction(s: dict) -> ExtractedInvoice:
    ex = truth_extraction(s)
    for field, v in s["seed_overrides"].items():
        setattr(ex, field, ExtractedField(**v))
    return ex


def build() -> None:
    BUILD.mkdir(parents=True, exist_ok=True)
    jobs = []
    for s in SPECS:
        h = BUILD / f"{s['id']}.html"
        h.write_text(render_html(s), encoding="utf-8")
        ext = "png" if s["render"] == "png" else "pdf"
        jobs.append({"html": str(h), "out": str(INVOICES / f"{s['id']}.{ext}"), "type": s["render"]})
    (BUILD / "jobs.json").write_text(json.dumps(jobs, indent=2), encoding="utf-8")
    print(f"wrote {len(jobs)} HTML files -> {BUILD}")


def seal() -> None:
    GOLDEN.mkdir(parents=True, exist_ok=True)
    REPLAY.mkdir(parents=True, exist_ok=True)
    for old in REPLAY.glob("*.json"):
        old.unlink()
    manifest = []
    for s in SPECS:
        ext = "png" if s["render"] == "png" else "pdf"
        f = INVOICES / f"{s['id']}.{ext}"
        sha = hashlib.sha256(f.read_bytes()).hexdigest()
        seed = seed_extraction(s)
        source = "seed:simulated-error" if s["seed_overrides"] else "seed"
        (REPLAY / f"{sha}.json").write_text(json.dumps(
            {"file_name": f.name, "source": source, "passes": [seed.model_dump()]}, ensure_ascii=False, indent=2,
        ), encoding="utf-8")
        golden = {
            "file": f.name, "sha256": sha, "note": s["note"],
            "expected": s["expected"],
            "truth": truth_extraction(s).model_dump(),
        }
        (GOLDEN / f"{s['id']}.json").write_text(json.dumps(golden, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest.append({"id": s["id"], "file": f.name, "status": s["expected"]["status"], "note": s["note"]})
    (GOLDEN / "_context.json").write_text(json.dumps({
        "client_name": CLIENT["name_en"], "client_trn": CLIENT["trn"], "today": EVAL_TODAY,
    }, indent=2), encoding="utf-8")
    (FIX / "MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"sealed {len(SPECS)} invoices -> golden + replay")


if __name__ == "__main__":
    seal() if "--seal" in sys.argv else build()
