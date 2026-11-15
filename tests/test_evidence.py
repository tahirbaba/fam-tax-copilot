from pathlib import Path

from famcheck import config
from famcheck.core.models import ExtractedField, ExtractedInvoice, Extraction, FieldStatus
from famcheck.extract.evidence import check_extraction
from famcheck.ingest.loader import SourceDoc, load


def _doc(text: str, kind: str = "pdf-text") -> SourceDoc:
    return SourceDoc(path=Path("x.pdf"), name="x.pdf", data=b"", media_type="application/pdf",
                     sha256="0", kind=kind, text=text, language="en")


def _check(doc, **fields):
    inv = ExtractedInvoice(**{k: ExtractedField(**v) for k, v in fields.items()})
    f, _ = check_extraction(Extraction(source="t", passes=[inv]), doc)
    return f


def test_value_with_matching_evidence_is_verified():
    f = _check(_doc("TAX INVOICE\nTRN: 100234567890003"), supplier_trn={"value": "100234567890003", "evidence": "TRN: 100234567890003"})
    assert f["supplier_trn"].status == FieldStatus.VERIFIED


def test_fabricated_value_is_discarded():
    f = _check(_doc("TAX INVOICE\nTRN: 100234567890003"), supplier_trn={"value": "100234567890099", "evidence": "TRN: 100234567890099"})
    assert f["supplier_trn"].status == FieldStatus.UNVERIFIED
    assert not f["supplier_trn"].usable


def test_value_not_inside_its_evidence_is_discarded():
    # model quotes real text but returns a different value
    f = _check(_doc("Subtotal 2,400.00\nVAT 120.00"), vat_amount={"value": "125.00", "evidence": "VAT 120.00"})
    assert f["vat_amount"].status == FieldStatus.UNVERIFIED


def test_absent_field():
    f = _check(_doc("TAX INVOICE"), customer_trn={"value": None, "evidence": None})
    assert f["customer_trn"].status == FieldStatus.ABSENT


def test_arabic_reversed_digit_run_is_accepted_but_wrong_digits_are_not():
    # pypdf output for an RTL line: presentation forms + digits in visual (reversed) order
    text = "ﻓﺎﺗﻮرة ﺿﺮﻳﺒﻴﺔ\n٥٤٣٢١٠٩٨٧٦٥٤٠٠١اﻟﺮﻗﻢ اﻟﻀﺮﻳﺒﻲ: "
    good = _check(_doc(text), supplier_trn={"value": "١٠٠٤٥٦٧٨٩٠١٢٣٤٥", "evidence": "الرقم الضريبي: ١٠٠٤٥٦٧٨٩٠١٢٣٤٥"})
    assert good["supplier_trn"].status == FieldStatus.VERIFIED
    bad = _check(_doc(text), supplier_trn={"value": "١٠٠٤٥٦٧٨٩٠١٢٣٤٩", "evidence": "الرقم الضريبي: ١٠٠٤٥٦٧٨٩٠١٢٣٤٩"})
    assert bad["supplier_trn"].status == FieldStatus.UNVERIFIED


def test_photo_is_visual_never_verified():
    f = _check(_doc("", kind="image"), supplier_name={"value": "ACME", "evidence": "ACME"})
    assert f["supplier_name"].status == FieldStatus.VISUAL


def test_disagreeing_passes_are_disputed():
    doc = _doc("VAT 120.00 Total 2,520.00")
    p1 = ExtractedInvoice(vat_amount=ExtractedField(value="120.00", evidence="VAT 120.00"))
    p2 = ExtractedInvoice(vat_amount=ExtractedField(value="2,520.00", evidence="Total 2,520.00"))
    f, _ = check_extraction(Extraction(source="t", passes=[p1, p2]), doc)
    assert f["vat_amount"].status == FieldStatus.DISPUTED
    same = ExtractedInvoice(vat_amount=ExtractedField(value="120.00", evidence="VAT 120.00"))
    f, _ = check_extraction(Extraction(source="t", passes=[p1, same]), doc)
    assert f["vat_amount"].status == FieldStatus.VERIFIED


def test_real_arabic_fixture_text_layer_verifies():
    doc = load(config.SAMPLE_INVOICES / "inv02_ar_valid.pdf")
    assert doc.kind == "pdf-text" and doc.language in ("ar", "mixed")
    f = _check(doc, supplier_name={"value": "شركة النخيل للتجارة العامة ذ.م.م", "evidence": "شركة النخيل للتجارة العامة ذ.م.م"},
               customer_name={"value": "شركة الأمل للتجارة", "evidence": "شركة الأمل للتجارة"})
    assert f["supplier_name"].status == FieldStatus.VERIFIED
    assert f["customer_name"].status == FieldStatus.UNVERIFIED  # not on the document
