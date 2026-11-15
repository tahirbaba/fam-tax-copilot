"""Web app for demos and day-to-day use. Same pipeline as the CLI.

Run:  famcheck serve   ->  http://127.0.0.1:8000
"""

from __future__ import annotations

import shutil
import tempfile
from collections import OrderedDict
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from famcheck import config
from famcheck.core.models import BatchResult, ReviewContext
from famcheck.core.pipeline import collect_files, review_paths
from famcheck.i18n import LANGS, field_label, strings
from famcheck.ingest.loader import SUPPORTED
from famcheck.report import writers

config.load_dotenv()

HERE = Path(__file__).parent
app = FastAPI(title="FAM Invoice Checker", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
templates.env.filters["money"] = lambda v: "—" if v is None else f"{Decimal(v):,.2f}"

MAX_BATCHES = 20
MAX_FILES = 200
_BATCHES: "OrderedDict[str, tuple[BatchResult, dict[str, Path]]]" = OrderedDict()
_UPLOAD_ROOT = Path(tempfile.mkdtemp(prefix="famcheck_"))


def _lang(request: Request) -> str:
    lang = request.query_params.get("lang") or request.cookies.get("lang") or "en"
    return lang if lang in LANGS else "en"


def _render(request: Request, name: str, **ctx) -> HTMLResponse:
    lang = _lang(request)
    resp = templates.TemplateResponse(
        request, name,
        {"t": strings(lang), "lang": lang, "field_label": field_label, "demo_mode": not config.has_credentials(), **ctx},
    )
    resp.set_cookie("lang", lang, max_age=60 * 60 * 24 * 365, samesite="lax")
    return resp


def _store(batch: BatchResult, files: dict[str, Path]) -> None:
    _BATCHES[batch.batch_id] = (batch, files)
    while len(_BATCHES) > MAX_BATCHES:
        _, (_, old_files) = _BATCHES.popitem(last=False)
        for p in old_files.values():
            if _UPLOAD_ROOT in p.parents:
                shutil.rmtree(p.parent, ignore_errors=True)
                break


def _get(batch_id: str) -> tuple[BatchResult, dict[str, Path]]:
    if batch_id not in _BATCHES:
        raise HTTPException(404, "Batch not found (batches are kept in memory only)")
    return _BATCHES[batch_id]


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return _render(request, "index.html", recent=list(reversed(_BATCHES.values()))[:5])


@app.post("/demo")
def run_demo(request: Request):
    files = collect_files([config.SAMPLE_INVOICES])
    ctx = ReviewContext(client_name="Al Noor Restaurants LLC", client_trn="100345678900003", today=date(2026, 11, 15))
    batch = review_paths(files, ctx, mode="replay")
    _store(batch, {p.name: p for p in files})
    return RedirectResponse(f"/batch/{batch.batch_id}", status_code=303)


@app.post("/review")
async def review(
    request: Request,
    files: list[UploadFile] = File(...),
    client_name: Optional[str] = Form(None),
    client_trn: Optional[str] = Form(None),
):
    if not files or len(files) > MAX_FILES:
        raise HTTPException(400, f"Upload between 1 and {MAX_FILES} files")
    folder = Path(tempfile.mkdtemp(dir=_UPLOAD_ROOT))
    paths, names = [], []
    for i, uf in enumerate(files):
        name = Path(uf.filename or f"file{i}").name
        if Path(name).suffix.lower() not in SUPPORTED:
            continue
        dest = folder / f"{i:03d}_{name}"
        dest.write_bytes(await uf.read())
        paths.append(dest)
        names.append(name)
    if not paths:
        raise HTTPException(400, "No PDF/PNG/JPG/WEBP files in the upload")
    ctx = ReviewContext(client_name=(client_name or None), client_trn=(client_trn or None))
    batch = review_paths(paths, ctx, names=names)
    _store(batch, dict(zip(names, paths)))
    return RedirectResponse(f"/batch/{batch.batch_id}", status_code=303)


@app.get("/batch/{batch_id}", response_class=HTMLResponse)
def batch_view(request: Request, batch_id: str):
    batch, _ = _get(batch_id)
    return _render(request, "batch.html", b=batch, s=batch.summary)


@app.get("/batch/{batch_id}/invoice/{idx}", response_class=HTMLResponse)
def invoice_view(request: Request, batch_id: str, idx: int):
    batch, _ = _get(batch_id)
    if not 0 <= idx < len(batch.results):
        raise HTTPException(404)
    r = batch.results[idx]
    return _render(request, "invoice.html", b=batch, r=r, idx=idx,
                   prev_idx=idx - 1 if idx > 0 else None,
                   next_idx=idx + 1 if idx + 1 < len(batch.results) else None)


@app.get("/batch/{batch_id}/file/{idx}")
def source_file(batch_id: str, idx: int):
    batch, files = _get(batch_id)
    if not 0 <= idx < len(batch.results):
        raise HTTPException(404)
    p = files.get(batch.results[idx].file_name)
    if not p or not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type=SUPPORTED.get(p.suffix.lower(), "application/octet-stream"),
                        headers={"Content-Disposition": "inline"})


@app.get("/batch/{batch_id}/report", response_class=HTMLResponse)
def client_report(request: Request, batch_id: str):
    batch, _ = _get(batch_id)
    return HTMLResponse(writers.to_client_html(batch, _lang(request)))


@app.get("/batch/{batch_id}/excel")
def excel(batch_id: str):
    batch, _ = _get(batch_id)
    return Response(
        writers.to_excel(batch),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="invoice_review_{batch_id}.xlsx"'},
    )


@app.get("/batch/{batch_id}/zoho.csv")
def zoho(batch_id: str):
    batch, _ = _get(batch_id)
    return Response(
        "﻿" + writers.to_zoho_csv(batch), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="zoho_bills_{batch_id}.csv"'},
    )


@app.get("/batch/{batch_id}/json")
def as_json(batch_id: str):
    batch, _ = _get(batch_id)
    return Response(writers.to_json(batch), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="results_{batch_id}.json"'})


@app.get("/rules", response_class=HTMLResponse)
def rules_view(request: Request):
    from famcheck.rules.engine import load_packs

    return _render(request, "rules.html", packs=load_packs())


@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    return "ok"
