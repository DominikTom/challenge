"""Wspólne fikstury pytest. Syntetyczne dane wejściowe generujemy w locie
(są w .gitignore, bo w pełni odtwarzalne z `fixtures/generate.py`).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from transport_audit.core.erp import load_erp
from transport_audit.core.matcher import Matcher
from transport_audit.core.pipeline import CarrierInput, run_pipeline
from transport_audit.core.models import Carrier
from .fixtures import generate as gen

FIX = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    if not (FIX / "manifest.json").exists():
        gen.generate_all(FIX)
    return FIX


@pytest.fixture(scope="session")
def manifest(fixtures_dir: Path) -> dict:
    return json.loads((fixtures_dir / "manifest.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def erp(fixtures_dir: Path):
    return load_erp(fixtures_dir / "Eksport.csv")


@pytest.fixture(scope="session")
def spt_deliveries(fixtures_dir: Path):
    from transport_audit.adapters.spt import SptAdapter
    return SptAdapter("FS/38/02/2026", "2026-02").parse(fixtures_dir / "spt_spec.pdf")


@pytest.fixture(scope="session")
def zadbano_deliveries(fixtures_dir: Path):
    from transport_audit.adapters.zadbano import ZadbanoAdapter
    return ZadbanoAdapter("307/02/2026/TR", "2026-02",
                          settlement_no="307/02/2026/TR").parse(
                              fixtures_dir / "zadbano_spec.xlsx")


@pytest.fixture(scope="session")
def dm_deliveries(fixtures_dir: Path):
    from transport_audit.adapters.dm_trans import DmTransAdapter
    return DmTransAdapter("FS/24/02/2026", "2026-02",
                          settlement_no="07/02/2026").parse(
                              fixtures_dir / "dm_settlement.pdf")


@pytest.fixture(scope="session")
def pipeline_result(fixtures_dir: Path):
    carrier_inputs = [
        CarrierInput(Carrier.SPT, str(fixtures_dir / "spt_spec.pdf"),
                     str(fixtures_dir / "invoice_spt.pdf")),
        CarrierInput(Carrier.ZADBANO, str(fixtures_dir / "zadbano_spec_broken.xlsx"),
                     str(fixtures_dir / "invoice_zadbano.pdf")),
        CarrierInput(Carrier.DM_TRANS, str(fixtures_dir / "dm_settlement.pdf"),
                     str(fixtures_dir / "invoice_dm.pdf")),
    ]
    return run_pipeline(fixtures_dir / "Eksport.csv", carrier_inputs, "2026-02")


@pytest.fixture(scope="session")
def outcome(pipeline_result):
    return pipeline_result.outcome
