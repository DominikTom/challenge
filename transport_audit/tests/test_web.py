"""Testy warstwy web (Flask) — endpointy UI, demo, upload, obsługa błędów."""

from pathlib import Path

import pytest

flask_app = pytest.importorskip("flask")  # web wymaga flask
from transport_audit.web.app import app as flask_application  # noqa: E402

SAMPLE = Path(__file__).resolve().parent.parent / "web" / "sample"


@pytest.fixture()
def client():
    flask_application.config["TESTING"] = True
    return flask_application.test_client()


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"Audyt koszt" in r.data


def test_health(client):
    assert client.get("/api/health").get_json() == {"status": "ok"}


def test_sample_demo_end_to_end(client):
    d = client.post("/api/sample").get_json()
    assert d["reconcile_ok"] is True
    # golden reconciliation
    by = {r["carrier"]: r for r in d["reconciliation"]}
    assert by["SPT"]["actual_sum"] == pytest.approx(29225.96, abs=0.01)
    assert by["ZADBANO"]["actual_sum"] == pytest.approx(98172.50, abs=0.01)
    assert by["DM_TRANS"]["actual_sum"] == pytest.approx(5445.00, abs=0.01)
    # golden cross-carrier 47559 obecny
    assert any(f["order_core"] == "47559" for f in d["findings"]["cross_carrier"])
    # pliki do pobrania
    assert set(d["files"]) == {"audit_report", "enriched_orders", "reference_tariff"}
    assert d["files"]["audit_report"]["base64"]


def test_upload_run(client):
    data = {
        "period": "2026-02",
        "erp": (open(SAMPLE / "erp_demo.csv", "rb"), "erp.csv"),
        "SPT_spec": (open(SAMPLE / "spt_demo.pdf", "rb"), "spt.pdf"),
        "SPT_invoice": (open(SAMPLE / "invoice_spt.pdf", "rb"), "inv_spt.pdf"),
        "ZADBANO_spec": (open(SAMPLE / "zadbano_demo.xlsx", "rb"), "z.xlsx"),
        "ZADBANO_invoice": (open(SAMPLE / "invoice_zadbano.pdf", "rb"), "inv_z.pdf"),
        "DM_TRANS_spec": (open(SAMPLE / "dm_demo.pdf", "rb"), "dm.pdf"),
        "DM_TRANS_invoice": (open(SAMPLE / "invoice_dm.pdf", "rb"), "inv_dm.pdf"),
    }
    r = client.post("/api/run", data=data, content_type="multipart/form-data")
    d = r.get_json()
    assert r.status_code == 200
    assert d["reconcile_ok"] is True
    assert d["total_flags"] > 0


def test_upload_multiple_specs_and_invoices_pool(client):
    """Wiele zestawień + faktur jednego przewoźnika: sumy pulowane (§4).

    Dwa te same zestawienia SPT + dwie te same faktury -> actual i expected
    podwojone, więc uzgodnienie nadal się zgadza.
    """
    data = {
        "period": "2026-02",
        "erp": (open(SAMPLE / "erp_demo.csv", "rb"), "erp.csv"),
        "SPT_spec": [(open(SAMPLE / "spt_demo.pdf", "rb"), "a.pdf"),
                     (open(SAMPLE / "spt_demo.pdf", "rb"), "b.pdf")],
        "SPT_invoice": [(open(SAMPLE / "invoice_spt.pdf", "rb"), "i1.pdf"),
                        (open(SAMPLE / "invoice_spt.pdf", "rb"), "i2.pdf")],
    }
    r = client.post("/api/run", data=data, content_type="multipart/form-data")
    d = r.get_json()
    assert r.status_code == 200
    spt = next(x for x in d["reconciliation"] if x["carrier"] == "SPT")
    assert spt["actual_sum"] == pytest.approx(2 * 29225.96, abs=0.01)
    assert spt["expected_net"] == pytest.approx(2 * 29225.96, abs=0.01)
    assert spt["within_tolerance"] is True


def test_upload_run_without_invoice_still_computes(client):
    # bez faktury: audyt liczy koszty, ale nie ma czego uzgadniać (expected_net=None)
    data = {
        "period": "2026-02",
        "erp": (open(SAMPLE / "erp_demo.csv", "rb"), "erp.csv"),
        "SPT_spec": (open(SAMPLE / "spt_demo.pdf", "rb"), "spt.pdf"),
    }
    r = client.post("/api/run", data=data, content_type="multipart/form-data")
    d = r.get_json()
    assert r.status_code == 200
    spt = next(x for x in d["reconciliation"] if x["carrier"] == "SPT")
    assert spt["actual_sum"] == pytest.approx(29225.96, abs=0.01)
    assert spt["expected_net"] is None


def test_run_requires_erp(client):
    r = client.post("/api/run", data={"period": "2026-02"},
                    content_type="multipart/form-data")
    assert r.status_code == 400
    assert "ERP" in r.get_json()["error"]


def test_run_requires_carrier(client):
    data = {"period": "2026-02", "erp": (open(SAMPLE / "erp_demo.csv", "rb"), "erp.csv")}
    r = client.post("/api/run", data=data, content_type="multipart/form-data")
    assert r.status_code == 400


def test_config_endpoint(client, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    assert client.get("/api/config").get_json() == {"supabase_configured": False}


def test_supabase_source_requires_creds(client, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    data = {"period": "2026-02", "erp_source": "supabase",
            "SPT_spec": (open(SAMPLE / "spt_demo.pdf", "rb"), "spt.pdf")}
    r = client.post("/api/run", data=data, content_type="multipart/form-data")
    assert r.status_code == 400
    assert "SUPABASE" in r.get_json()["error"]


def test_erp_source_reported_in_summary(client):
    data = {"period": "2026-02", "erp_source": "file",
            "erp": (open(SAMPLE / "erp_demo.csv", "rb"), "erp.csv"),
            "SPT_spec": (open(SAMPLE / "spt_demo.pdf", "rb"), "spt.pdf"),
            "SPT_invoice": (open(SAMPLE / "invoice_spt.pdf", "rb"), "i.pdf")}
    d = client.post("/api/run", data=data, content_type="multipart/form-data").get_json()
    assert d["erp_source"] == "file"
