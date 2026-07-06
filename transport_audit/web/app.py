"""Aplikacja Flask: UI pod '/' + endpointy /api/run, /api/sample, /api/health.

Zaprojektowana pod Vercel (serverless): bezstanowa, pliki w katalogu tymczasowym.
"""

from __future__ import annotations

import tempfile
import traceback
from pathlib import Path

from flask import Flask, jsonify, request

from ..core.models import Carrier
from ..core.pipeline import CarrierInput
from .service import run_audit
from .ui import INDEX_HTML

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

    @app.post("/api/run")
    def run():
        try:
            if "erp" not in request.files:
                return jsonify({"error": "Brak pliku ERP (pole 'erp')."}), 400
            period = (request.form.get("period") or "2026-02").strip()
            tmp = Path(tempfile.mkdtemp(prefix="ta_in_"))

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

            summary = run_audit(str(erp_path), carrier_inputs, period)
            return jsonify(summary)
        except Exception as exc:  # noqa: BLE001 — zwracamy błąd do UI, nie 500 goły
            return jsonify({"error": f"{type(exc).__name__}: {exc}",
                            "trace": traceback.format_exc()[-1500:]}), 500

    @app.post("/api/sample")
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
