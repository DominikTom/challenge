"""Testy modelu cennika referencyjnego (§5.6/§6.5)."""

import json

import pytest

from transport_audit.core.tariff_model import TariffModel


def test_clusters_learned(pipeline_result):
    tariff = pipeline_result.tariff
    assert tariff.clusters
    # istnieje klaster z >= 5 obserwacjami (do flagowania przepłaceń)
    assert any(c.count >= 5 for c in tariff.clusters.values())


def test_overpay_detected_above_threshold(pipeline_result):
    tariff = pipeline_result.tariff
    # znajdź linię przepłaty 48120 (Transport 600) i sprawdź werdykt
    over = None
    for m in pipeline_result.outcome.matches:
        if m.delivery.order_core == "48120":
            over = tariff.evaluate(m.delivery, m.erp_order)
            break
    assert over is not None
    assert over["verdict"] == "above_tariff"
    assert over["ratio"] and over["ratio"] > 1.20


def test_save_and_load_roundtrip(pipeline_result, tmp_path):
    p = tmp_path / "tariff.json"
    pipeline_result.tariff.save(p)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "clusters" in data and data["min_observations"] == 5
    reloaded = TariffModel.load(p)
    assert len(reloaded.clusters) == len(pipeline_result.tariff.clusters)


def test_no_reference_for_rare_cluster(pipeline_result):
    tariff = pipeline_result.tariff
    # orphan-podobny rzadki klaster -> no_reference
    counts = [c.count for c in tariff.clusters.values()]
    assert min(counts) < 5   # istnieją klastry z <5 obs (INFO no_reference)
