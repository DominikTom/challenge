"""Aplikacja Flask: UI pod '/' + endpointy /api/run, /api/sample, /api/health.

Zaprojektowana pod Vercel (serverless): bezstanowa, pliki w katalogu tymczasowym.
"""

from __future__ import annotations

import os
import tempfile
import traceback
from pathlib import Path

from flask import Flask, jsonify, request
from werkzeug.utils import secure_filename

from ..core.models import Carrier
from ..core.pipeline import CarrierInput
from .service import run_audit
from .ui import INDEX_HTML


def _save_uploads(files, tmp: Path, prefix: str) -> list[str]:
    """Zapisz wgrane pliki do katalogu tymczasowego; zwróć listę ścieżek.

    Nazwy sanityzujemy i prefiksujemy indeksem, żeby uniknąć kolizji i
    wyjścia poza katalog (path traversal)."""
    paths: list[str] = []
    for idx, f in enumerate(files):
        safe = secure_filename(f.filename) or f"plik_{idx}"
        p = tmp / f"{prefix}_{idx}_{safe}"
        f.save(p)
        paths.append(str(p))
    return paths


def _carrier_inputs_from_request(tmp: Path, allow_invoice_only: bool = False) -> list[CarrierInput]:
    """Zbierz CarrierInput z pól multipart (wiele zestawień/faktur per przewoźnik).

    ``allow_invoice_only`` (dla /api/parse): dopuść porcję zawierającą same
    faktury — front wysyła zestawienia i faktury w osobnych żądaniach, żeby
    każde zmieściło się w limicie czasu; łączymy je dopiero po stronie klienta.
    """
    inputs: list[CarrierInput] = []
    for field, carrier in _CARRIER_FIELDS.items():
        spec_files = [f for f in request.files.getlist(f"{field}_spec") if f and f.filename]
        inv_files = [f for f in request.files.getlist(f"{field}_invoice") if f and f.filename]
        if not spec_files and not (allow_invoice_only and inv_files):
            continue
        spec_paths = _save_uploads(spec_files, tmp, f"{field}_spec")
        invoice_paths = _save_uploads(inv_files, tmp, f"{field}_inv")
        inputs.append(CarrierInput(
            carrier=carrier, spec_paths=spec_paths, invoice_paths=invoice_paths))
    return inputs


def _supabase_configured() -> bool:
    url = os.environ.get("SUPABASE_URL")
    key = (os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY")
           or os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY"))
    return bool(url and key)

SAMPLE_DIR = Path(__file__).resolve().parent / "sample"

# mapowanie pól formularza -> przewoźnik
_CARRIER_FIELDS = {
    "SPT": Carrier.SPT,
    "ZADBANO": Carrier.ZADBANO,
    "DM_TRANS": Carrier.DM_TRANS,
}


def build_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024  # 40 MB (uwaga: Vercel ~4.5MB/req)

    @app.get("/")
    def index():
        return INDEX_HTML

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/api/config")
    def config():
        return jsonify({"supabase_configured": _supabase_configured()})

    @app.get("/api/tariffs")
    def tariffs():
        from ..core.tariff_official import all_tariffs
        return jsonify(all_tariffs())

    @app.get("/api/glossary")
    def glossary():
        from ..core.audit_glossary import GLOSSARY, OUTPUT_FILES
        return jsonify({"tabs": GLOSSARY, "files": OUTPUT_FILES})

    @app.get("/api/supabase-check")
    def supabase_check():
        """Diagnostyka połączenia: tani probe RPC audit_erp (kilka rdzeni)."""
        if not _supabase_configured():
            return jsonify({"configured": False,
                            "error": "Brak SUPABASE_URL / SUPABASE_KEY w środowisku."}), 400
        try:
            from ..core.config import load_config
            from ..core.supabase_io import SupabaseClient, _erp_order_from_row
            cfg = load_config()
            client = SupabaseClient()
            # p_start == p_end => okno puste, dociągamy tylko po rdzeniach (tanio)
            rows = client.rpc_all("audit_erp", {
                "p_cores": ["25476", "25502"],
                "p_start": "2026-02-01", "p_end": "2026-02-01"})
            orders = [_erp_order_from_row(r, cfg) for r in rows]
            sample = [{"number": o.number, "core": o.core,
                       "service_level": o.service_level.value,
                       "products": o.products[:2]} for o in orders[:3]]
            return jsonify({"configured": True, "ok": True,
                            "orders_probed": len(orders), "sample": sample})
        except Exception as exc:  # noqa: BLE001
            return jsonify({"configured": True, "ok": False,
                            "error": f"{type(exc).__name__}: {exc}"}), 500

    @app.post("/api/parse")
    def parse_route():
        """Sparsuj JEDNĄ porcję zestawień/faktur (bez ERP) -> mały pakiet JSON.

        Klient wywołuje to wielokrotnie (duże dane porcjami, każda < ~4,5 MB),
        zbiera pakiety i wysyła złożoną całość do /api/run (pole 'parsed')."""
        try:
            period = (request.form.get("period") or "").strip()
            tmp = Path(tempfile.mkdtemp(prefix="ta_parse_"))
            carrier_inputs = _carrier_inputs_from_request(tmp, allow_invoice_only=True)
            if not carrier_inputs:
                return jsonify({"error": "Brak plików zestawień/faktur do sparsowania."}), 400
            from .service import parse_batch
            return jsonify(parse_batch(carrier_inputs, period))
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": f"{type(exc).__name__}: {exc}",
                            "trace": traceback.format_exc()[-1500:]}), 500

    @app.post("/api/run")
    def run():
        try:
            period = (request.form.get("period") or "").strip()  # puste => auto z dokumentów
            erp_source = (request.form.get("erp_source") or "file").strip()
            save_supabase = (request.form.get("save_supabase") or "").lower() in ("1", "true", "on", "yes")
            parsed_raw = request.form.get("parsed")  # tryb „na raty": gotowe sparsowane porcje
            gz = request.files.get("parsed_gz")       # albo skompresowany pakiet (duże okresy)
            if gz and gz.filename:
                import gzip as _gzip
                try:
                    parsed_raw = _gzip.decompress(gz.read()).decode("utf-8")
                except (OSError, EOFError, UnicodeDecodeError):
                    return jsonify({"error": "Nie udało się rozpakować pakietu 'parsed_gz'."}), 400
            tmp = Path(tempfile.mkdtemp(prefix="ta_in_"))

            erp_path = None
            if erp_source == "supabase":
                if not _supabase_configured():
                    return jsonify({"error": "Import z Supabase wymaga zmiennych "
                                    "SUPABASE_URL i SUPABASE_KEY w środowisku Vercel."}), 400
            else:
                if "erp" not in request.files or not request.files["erp"].filename:
                    return jsonify({"error": "Brak pliku ERP (pole 'erp')."}), 400
                erp_path = tmp / "erp.csv"
                request.files["erp"].save(erp_path)

            # --- tryb „na raty": audyt z gotowych, złożonych porcji ------------
            if parsed_raw:
                import json as _json
                try:
                    parsed_bundle = _json.loads(parsed_raw)
                except (ValueError, TypeError):
                    return jsonify({"error": "Nieprawidłowy pakiet 'parsed' (nie-JSON)."}), 400
                if not (parsed_bundle.get("carriers") if isinstance(parsed_bundle, dict) else None):
                    return jsonify({"error": "Pakiet 'parsed' nie zawiera żadnych zestawień."}), 400
                summary = run_audit(str(erp_path) if erp_path else None, [], period,
                                    erp_source=erp_source, save_supabase=save_supabase,
                                    parsed_bundle=parsed_bundle)
                return jsonify(summary)

            # --- tryb plikowy: zestawienia+faktury w tym żądaniu --------------
            carrier_inputs = _carrier_inputs_from_request(tmp)
            if not carrier_inputs:
                return jsonify({"error": "Wgraj co najmniej jedno zestawienie przewoźnika."}), 400

            summary = run_audit(str(erp_path) if erp_path else None, carrier_inputs,
                                period, erp_source=erp_source, save_supabase=save_supabase)
            return jsonify(summary)
        except Exception as exc:  # noqa: BLE001 — zwracamy błąd do UI, nie 500 goły
            return jsonify({"error": f"{type(exc).__name__}: {exc}",
                            "trace": traceback.format_exc()[-1500:]}), 500

    @app.route("/api/sample", methods=["GET", "POST"])
    def sample():
        try:
            summary = run_audit(
                str(SAMPLE_DIR / "erp_demo.csv"),
                [
                    CarrierInput(Carrier.SPT, str(SAMPLE_DIR / "spt_demo.pdf"),
                                 str(SAMPLE_DIR / "invoice_spt.pdf")),
                    CarrierInput(Carrier.ZADBANO, str(SAMPLE_DIR / "zadbano_demo.xlsx"),
                                 str(SAMPLE_DIR / "invoice_zadbano.pdf")),
                    CarrierInput(Carrier.DM_TRANS, str(SAMPLE_DIR / "dm_demo.pdf"),
                                 str(SAMPLE_DIR / "invoice_dm.pdf")),
                ],
                "2026-02",
            )
            summary["demo"] = True
            return jsonify(summary)
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": f"{type(exc).__name__}: {exc}",
                            "trace": traceback.format_exc()[-1500:]}), 500

    return app


app = build_app()
