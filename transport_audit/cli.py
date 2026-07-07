"""CLI audytu kosztów transportu (§8).

Przykład:
    python -m transport_audit run \\
      --erp Eksport.csv \\
      --carrier SPT:invoice=FS_38.pdf,spec=MYBED_LUTY_II.pdf \\
      --carrier ZADBANO:invoice=307_02_2026_TR.pdf,spec=307_02_2026_TR_specyfikacja.xlsx \\
      --carrier DM_TRANS:invoice=FS_24_02_2026.pdf,spec=MYBED_07_02_2026.pdf \\
      --period 2026-02 --out ./out [--load-supabase]
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .core.config import load_config
from .core.models import Carrier
from .core.pipeline import CarrierInput, run_pipeline
from .report import generate_reports

app = typer.Typer(add_completion=False, help="Atrybucja i audyt kosztów transportu MyBed.")
console = Console()

_CARRIER_ALIASES = {
    "SPT": Carrier.SPT,
    "ZADBANO": Carrier.ZADBANO,
    "DM_TRANS": Carrier.DM_TRANS,
    "DM": Carrier.DM_TRANS,
    "D&M": Carrier.DM_TRANS,
    "DMTRANS": Carrier.DM_TRANS,
}


def parse_carrier_spec(spec: str) -> CarrierInput:
    """Sparsuj 'CARRIER:invoice=...,spec=...,settlement=...' -> CarrierInput."""
    if ":" not in spec:
        raise typer.BadParameter(
            f"Zły format --carrier: {spec!r}. Oczekiwano 'CARRIER:invoice=...,spec=...'")
    carrier_raw, rest = spec.split(":", 1)
    carrier_key = carrier_raw.strip().upper()
    if carrier_key not in _CARRIER_ALIASES:
        raise typer.BadParameter(
            f"Nieznany przewoźnik {carrier_raw!r}. Dozwolone: {sorted(set(_CARRIER_ALIASES))}")
    carrier = _CARRIER_ALIASES[carrier_key]

    params: dict[str, str] = {}
    for part in rest.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise typer.BadParameter(f"Zły fragment {part!r} w --carrier {spec!r}")
        k, v = part.split("=", 1)
        params[k.strip().lower()] = v.strip()

    if "spec" not in params:
        raise typer.BadParameter(f"Brak 'spec=' w --carrier {spec!r}")
    # wiele zestawień/faktur jednego przewoźnika: 'spec=a.pdf|b.pdf'
    spec_paths = [s.strip() for s in params["spec"].split("|") if s.strip()]
    invoice_paths = [s.strip() for s in params.get("invoice", "").split("|") if s.strip()]
    return CarrierInput(
        carrier=carrier,
        spec_path=spec_paths[0] if len(spec_paths) == 1 else None,
        invoice_path=invoice_paths[0] if len(invoice_paths) == 1 else None,
        settlement_no=params.get("settlement"),
        spec_paths=spec_paths if len(spec_paths) > 1 else [],
        invoice_paths=invoice_paths if len(invoice_paths) > 1 else [],
    )


@app.command()
def run(
    carrier: list[str] = typer.Option(
        ..., "--carrier", help="CARRIER:invoice=...,spec=... (można wiele razy)."),
    period: str = typer.Option(..., "--period", help="Okres 'YYYY-MM'."),
    erp: Path = typer.Option(None, "--erp", help="Ścieżka do Eksport.csv (dla --erp-source file)."),
    erp_source: str = typer.Option(
        "file", "--erp-source", help="Źródło ERP: 'file' (Eksport.csv) lub 'supabase'."),
    out: Path = typer.Option(Path("./out"), "--out", help="Katalog wyjściowy."),
    config: Path = typer.Option(None, "--config", help="Ścieżka do config.yaml."),
    load_supabase: bool = typer.Option(
        False, "--load-supabase", help="Zapisz wyniki do Supabase (fallback: JSONL)."),
) -> None:
    """Uruchom pełny pipeline: atrybucja + audyt + uzgodnienie + raporty."""
    cfg = load_config(str(config)) if config else load_config()
    carrier_inputs = [parse_carrier_spec(c) for c in carrier]
    if erp_source == "file" and erp is None:
        raise typer.BadParameter("--erp-source file wymaga --erp <Eksport.csv>")

    console.print(f"[bold]Audyt transportu[/bold] — okres {period}, "
                  f"{len(carrier_inputs)} przewoźnik(ów), źródło ERP: {erp_source}")
    result = run_pipeline(erp, carrier_inputs, period, cfg, erp_source=erp_source)

    _print_reconciliation(result)
    _print_audit_summary(result)
    _print_backtest(result)

    paths = generate_reports(result, out, cfg)
    if load_supabase:
        from .core.supabase_loader import load_to_supabase
        status = load_to_supabase(result, out)
        console.print(f"[cyan]Supabase:[/cyan] {status}")

    console.print("\n[bold green]Gotowe.[/bold green] Pliki wyjściowe:")
    for name, p in paths.items():
        console.print(f"  • {name}: {p}")


def _print_reconciliation(result) -> None:
    table = Table(title="Uzgodnienie z fakturami (§9)")
    for col in ["Przewoźnik", "FV", "Rozliczenie", "Σ koszt netto",
                "Netto FV", "Delta", "OK"]:
        table.add_column(col)
    for r in result.recon_results:
        ok = "✓" if r.within_tolerance else "✗"
        style = "green" if r.within_tolerance else "red"
        table.add_row(
            r.carrier, r.invoice_no, r.settlement_no or "-",
            f"{r.actual_sum:,.2f}",
            f"{r.expected_net:,.2f}" if r.expected_net is not None else "-",
            f"{r.delta:+.2f}" if r.delta is not None else "-",
            f"[{style}]{ok}[/{style}]")
    console.print(table)


def _print_audit_summary(result) -> None:
    from collections import Counter
    from .core.models import Severity

    counts = Counter((f.rule, f.severity.value) for f in result.audit.flags)
    table = Table(title="Ustalenia audytowe (§6)")
    table.add_column("Reguła")
    table.add_column("FLAG", justify="right")
    table.add_column("WARN", justify="right")
    table.add_column("INFO", justify="right")
    rules = sorted({r for r, _ in counts})
    for rule in rules:
        table.add_row(
            rule,
            str(counts.get((rule, "FLAG"), 0)),
            str(counts.get((rule, "WARN"), 0)),
            str(counts.get((rule, "INFO"), 0)))
    console.print(table)

    total_flags = sum(1 for f in result.audit.flags if f.severity is Severity.FLAG)
    recoverable = sum(f.recoverable or 0 for f in result.audit.flags
                      if f.rule in ("CROSS_CARRIER", "DOUBLE_INTRA", "FAILED_CHARGED"))
    console.print(f"[bold red]FLAG-i łącznie: {total_flags}[/bold red] | "
                  f"szac. kwota do odzyskania: [bold]{recoverable:,.2f} zł[/bold]")


def _print_backtest(result) -> None:
    bt = result.backtest
    console.print(
        f"[cyan]Backtest matchera:[/cyan] zgodność przewoźnika "
        f"{bt.agreement_rate:.2%} na {bt.total_with_manual} dopasowanych "
        f"(cel ≥98%) — niezgodne: {bt.disagreements}")


@app.command("make-fixtures")
def make_fixtures(
    out: Path = typer.Option(None, "--out", help="Katalog na fikstury (domyślnie tests/fixtures).")
) -> None:
    """Wygeneruj syntetyczne fikstury (golden cases) do testów / demo."""
    from .tests.fixtures.generate import generate_all
    manifest = generate_all(out)
    console.print(f"[green]Wygenerowano fikstury[/green]: {manifest['erp_orders']} zamówień ERP")


if __name__ == "__main__":
    app()
