from fastapi.testclient import TestClient
from typer.testing import CliRunner

from famcheck import config
from famcheck.cli import app as cli_app
from famcheck.web.app import app


def test_web_demo_flow():
    c = TestClient(app)
    assert c.get("/").status_code == 200
    r = c.post("/demo", follow_redirects=False)
    assert r.status_code == 303
    url = r.headers["location"]
    page = c.get(url)
    assert page.status_code == 200 and "Al Noor Restaurants LLC" in page.text
    ar = c.get(url + "?lang=ar")
    assert 'dir="rtl"' in ar.text and "تحتاج مراجعة" in ar.text
    assert c.get(url + "/invoice/13").status_code == 200
    assert c.get(url + "/file/0").headers["content-type"] == "application/pdf"
    assert c.get(url + "/report?lang=ar").status_code == 200
    xl = c.get(url + "/excel")
    assert xl.status_code == 200 and xl.content[:2] == b"PK"
    csv = c.get(url + "/zoho.csv").text
    assert "GF-2026-0412" in csv and "PAW-88213" not in csv  # only valid invoices are exported
    assert c.get("/rules").status_code == 200


def test_web_upload_without_key_is_routed_to_review(tmp_path):
    c = TestClient(app)
    pdf = (config.SAMPLE_INVOICES / "inv01_en_valid.pdf").read_bytes()
    unknown = pdf + b"\n%changed"  # different hash -> not in cache, and no API key in tests
    r = c.post("/review", files=[("files", ("new.pdf", unknown, "application/pdf"))], follow_redirects=True)
    assert r.status_code == 200 and "Needs review" in r.text


def test_cli_demo_and_eval(tmp_path):
    runner = CliRunner()
    res = runner.invoke(cli_app, ["demo", "--out", str(tmp_path)])
    assert res.exit_code == 0, res.output
    assert (tmp_path / "client_report_ar.html").exists() and (tmp_path / "invoice_review.xlsx").exists()
    res = runner.invoke(cli_app, ["eval"])
    assert res.exit_code == 0, res.output
