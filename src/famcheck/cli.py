"""famcheck - command line interface.

    famcheck demo                 # run on the 14 bundled sample invoices (offline)
    famcheck review ./invoices    # check your own invoices
    famcheck eval                 # golden-set accuracy report
    famcheck rules                # list every rule with its legal basis
    famcheck serve                # start the web app
    famcheck record ./invoices    # live Claude extraction, saved to the replay cache
"""

from __future__ import annotations

import webbrowser
from datetime import date
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from famcheck import config
from famcheck.core.models import BatchResult, ReviewContext
from famcheck.core.pipeline import collect_files, review_paths

config.load_dotenv()

app = typer.Typer(add_completion=False, no_args_is_help=True, help="FAM Invoice Checker - UAE VAT invoice compliance & e-invoicing readiness (EN/AR).")
console = Console()

STATUS_STYLE = {"green": "bold green", "amber": "bold yellow", "red": "bold red"}
STATUS_LABEL = {"green": "VALID", "amber": "REVIEW", "red": "PROBLEM"}


def _print_batch(batch: BatchResult, lang: str = "en") -> None:
    table = Table(title=f"Batch {batch.batch_id}", show_lines=False, header_style="bold cyan")
    table.add_column("File", overflow="fold")
    table.add_column("Supplier", overflow="fold")
    table.add_column("Invoice", overflow="fold")
    table.add_column("VAT", justify="right")
    table.add_column("Status")
    table.add_column("E-inv")
    table.add_column("Issues", overflow="fold")
    for r in batch.results:
        inv = r.invoice
        issues = [
            f"{f.rule_id} {f.title_ar if lang == 'ar' else f.title_en}"
            for f in r.findings if f.severity.value != "info" and f.impact.value != "einvoice_gap"
        ]
        table.add_row(
            r.file_name, inv.supplier_name or "—", inv.invoice_number or "—",
            f"{inv.vat_amount:,.2f} {inv.currency or ''}" if inv.vat_amount is not None else "—",
            f"[{STATUS_STYLE[r.status.value]}]{STATUS_LABEL[r.status.value]}[/]",
            "[green]ready[/]" if r.einvoice_ready else "[yellow]gaps[/]",
            "\n".join(issues) or "—",
        )
    console.print(table)
    s = batch.summary
    console.print(Panel.fit(
        f"[bold]{s.total}[/] invoices   [green]{s.green} valid[/]   [yellow]{s.amber} needs review[/]   [red]{s.red} problem[/]\n"
        f"Input VAT at risk: [bold red]AED {s.vat_at_risk_aed:,.2f}[/]  (of AED {s.vat_reviewed_aed:,.2f} reviewed)\n"
        f"E-invoicing ready: [bold]{s.einvoice_ready}/{s.total} ({s.einvoice_ready_pct}%)[/]",
        title="Summary", border_style="cyan",
    ))
    sources = sorted({r.extraction_source for r in batch.results})
    console.print(f"[dim]Extraction source: {', '.join(sources)}[/]")
    if any("seed" in x for x in sources):
        console.print("[dim]  'seed' = hand-checked demo data shipped with the samples. Run `famcheck record fixtures/invoices` "
                      "with an API key to replace it with real Claude extractions.[/]")


def _write(batch: BatchResult, out: Path, open_report: bool, lang: str) -> None:
    from famcheck.report.writers import write_all

    paths = write_all(batch, out)
    console.print("\n[bold]Reports written:[/]")
    for k, p in paths.items():
        console.print(f"  {k:<10} {p}")
    if open_report:
        webbrowser.open(paths[f"report_{lang}"].resolve().as_uri())


def _run(inputs: list[Path], mode: str, client_name: str | None, client_trn: str | None,
         today: str | None, out: Path, lang: str, open_report: bool) -> BatchResult:
    files = collect_files(inputs)
    if not files:
        console.print("[red]No PDF/PNG/JPG files found.[/]")
        raise typer.Exit(2)
    ctx = ReviewContext(client_name=client_name, client_trn=client_trn,
                        today=date.fromisoformat(today) if today else date.today())
    with console.status("Reviewing invoices...") as st:
        batch = review_paths(files, ctx, mode=mode,
                             on_progress=lambda i, n, name: st.update(f"[{i}/{n}] {name}"))
    _print_batch(batch, lang)
    _write(batch, out, open_report, lang)
    return batch


@app.command()
def review(
    inputs: List[Path] = typer.Argument(..., help="Invoice files or folders"),
    mode: str = typer.Option(config.mode(), help="auto | replay | live | record"),
    client_name: Optional[str] = typer.Option(None, help="Client the invoices belong to"),
    client_trn: Optional[str] = typer.Option(None, help="Client TRN - flags invoices addressed to someone else"),
    today: Optional[str] = typer.Option(None, help="Override today's date (YYYY-MM-DD)"),
    out: Path = typer.Option(Path("reports/latest"), help="Output folder"),
    lang: str = typer.Option("en", help="en | ar (terminal + report to open)"),
    open_report: bool = typer.Option(False, "--open", help="Open the client report in a browser"),
):
    """Check invoices and write Excel / Zoho CSV / JSON / client reports (EN + AR)."""
    _run(inputs, mode, client_name, client_trn, today, out, lang, open_report)


@app.command()
def demo(
    lang: str = typer.Option("en", help="en | ar"),
    out: Path = typer.Option(Path("reports/demo"), help="Output folder"),
    open_report: bool = typer.Option(False, "--open", help="Open the client report in a browser"),
):
    """Run on the 14 bundled sample invoices for the fictitious client 'Al Noor Restaurants LLC' (offline)."""
    _run([config.SAMPLE_INVOICES], "replay", "Al Noor Restaurants LLC", "100345678900003", "2026-11-15", out, lang, open_report)


@app.command()
def record(
    inputs: List[Path] = typer.Argument(..., help="Invoice files or folders"),
):
    """Extract with Claude (live) and save to the replay cache - then demos/evals replay it offline."""
    if not config.has_credentials():
        console.print("[red]ANTHROPIC_API_KEY is not set.[/] Copy .env.example to .env and add your key.")
        raise typer.Exit(2)
    files = collect_files(inputs)
    with console.status("Extracting with Claude...") as st:
        batch = review_paths(files, mode="record", on_progress=lambda i, n, name: st.update(f"[{i}/{n}] {name}"))
    _print_batch(batch)
    errors = [r for r in batch.results if r.extraction_error]
    for r in errors:
        console.print(f"[red]{r.file_name}: {r.extraction_error}[/]")
    console.print(f"Recorded {len(files) - len(errors)} of {len(files)} files.")


@app.command("eval")
def eval_cmd(
    mode: str = typer.Option("replay", help="replay (offline) | live (calls Claude, costs money)"),
    min_decision: float = typer.Option(1.0, help="Fail if decision accuracy is below this"),
    min_precision: float = typer.Option(0.99, help="Fail if auto-approved precision is below this"),
):
    """Run the golden set: decision accuracy + extraction precision."""
    from famcheck.evaluate import run

    rep = run(mode=mode)
    t = Table(title="Golden set", header_style="bold cyan")
    for c in ("File", "Expected", "Got", "OK", "Notes"):
        t.add_column(c, overflow="fold")
    for r in rep.rows:
        notes = []
        if r["expected_findings"] != r["got_findings"]:
            notes.append(f"expected {r['expected_findings']} got {r['got_findings']}")
        if r["wrong_fields"]:
            notes.append("wrong values: " + ", ".join(r["wrong_fields"]))
        t.add_row(r["file"], r["expected"], r["got"], "[green]✓[/]" if r["ok"] else "[red]✗[/]", "; ".join(notes))
    console.print(t)
    console.print(Panel.fit(
        f"Decision accuracy:           [bold]{rep.decisions_ok}/{rep.decisions_total} = {rep.decision_accuracy:.1%}[/]\n"
        f"Auto-approved precision:     [bold]{rep.verified_correct}/{rep.verified_total} = {rep.auto_precision:.1%}[/]  "
        f"(values used without a human that were correct)\n"
        f"Coverage:                    {rep.verified_correct}/{rep.fields_total} = {rep.coverage:.1%} of ground-truth values verified\n"
        f"Wrong values caught:         [green]{rep.wrong_caught}[/]   Wrong values missed: [red]{rep.wrong_missed}[/]\n"
        f"Extraction source:           {', '.join(sorted(rep.sources))}",
        title="Accuracy", border_style="cyan",
    ))
    if rep.decision_accuracy < min_decision or rep.auto_precision < min_precision:
        raise typer.Exit(1)


@app.command()
def rules(lang: str = typer.Option("en", help="en | ar")):
    """List every rule, its severity and legal basis."""
    from famcheck.rules.engine import load_packs

    for p in load_packs():
        t = Table(title=f"{p.title_ar if lang == 'ar' else p.title_en}  (v{p.version}, reviewed: {p.reviewed_by or 'PENDING'})",
                  header_style="bold cyan", title_justify="left")
        for c in ("ID", "Severity", "Applies", "Rule", "Legal basis"):
            t.add_column(c, overflow="fold")
        for r in p.rules:
            t.add_row(r.id, r.severity.value, r.when, r.title_ar if lang == "ar" else r.title_en, r.citation or "—")
        console.print(t)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8000),
):
    """Start the web app (http://127.0.0.1:8000)."""
    import uvicorn

    console.print(f"FAM Invoice Checker running on [bold]http://{host}:{port}[/]  (Ctrl+C to stop)")
    uvicorn.run("famcheck.web.app:app", host=host, port=port, log_level="warning")


if __name__ == "__main__":
    app()
