"""Aplikacja Flask: UI pod '/' + endpointy /api/run, /api/sample, /api/health.

Zaprojektowana pod Vercel (serverless): bezstanowa, pliki w katalogu tymczasowym.
"""

from __future__ import annotations

import os
import tempfile
import traceback
from pathlib import Path

from flask import Flask, jsonify, request

from ..core.models import Carrier
from ..core.pipeline import CarrierInput
from .service import run_audit
from .ui import INDEX_HTML


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

    @app.post("/api/run")
    def run():
        try:
            period = (request.form.get("period") or "2026-02").strip()
            erp_source = (request.form.get("erp_source") or "file").strip()
            save_supabase = (request.form.get("save_supabase") or "").lower() in ("1", "true", "on", "yes")
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

            carrier_inputs: list[CarrierInput] = []
            for field, carrier in _CARRIER_FIELDS.items():
                spec_file = request.files.get(f"{field}_spec")
                if not spec_file or not spec_file.filename:
                    continue
                spec_path = tmp / f"{field}_spec_{spec_file.filename}"
                spec_file.save(spec_path)
                invoice_path = None
                inv_file = request.files.get(f"{field}_invoice")
                if inv_file and inv_file.filename:
                    invoice_path = tmp / f"{field}_inv_{inv_file.filename}"
                    inv_file.save(invoice_path)
                    invoice_path = str(invoice_path)
                carrier_inputs.append(CarrierInput(
                    carrier=carrier, spec_path=str(spec_path), invoice_path=invoice_path))

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
