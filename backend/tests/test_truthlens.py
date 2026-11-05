"""TruthLens test suite.

Run:  cd backend && PYTHONPATH=. python3 -m pytest tests/test_truthlens.py -q

The end-to-end tests generate the synthetic sample sets, run the full
pipeline, and assert the forensic + correlation behaviour. A temporary data
directory is used so the real evidence store is untouched.
"""
import os
import tempfile

os.environ["TRUTHLENS_DATA"] = tempfile.mkdtemp(prefix="truthlens_test_")

import pytest  # noqa: E402

from app import store  # noqa: E402
from app.pipeline import correlate, normalize  # noqa: E402


# ------------------------------------------------------------ normalize ----
def test_names_tolerate_initials():
    ok, _ = normalize.names_match("Rahul K. Sharma", "Rahul Sharma")
    assert ok
    ok, _ = normalize.names_match("Rahul Kumar Sharma", "Rahul Sharma")
    assert ok


def test_names_flag_real_difference():
    ok, _ = normalize.names_match("Rahul Sharma", "Amit Verma")
    assert not ok


def test_date_and_amount_parsing():
    assert normalize.parse_date("12-04-1991") == "1991-04-12"
    assert normalize.parse_date("12/04/1991") == "1991-04-12"
    assert normalize.parse_amount("Rs. 9,60,000") == 960000.0
    assert normalize.parse_amount("₹4,10,000") == 410000.0


def test_pincode_city():
    assert normalize.extract_pincode("Pune411038") == "411038"
    assert normalize.extract_city("Mumbai 400001") == "mumbai"


# ---------------------------------------------------------------- audit ----
def test_audit_chain_integrity():
    case = store.create_case("audit-test")
    cid = case["id"]
    store.audit(cid, "test.event", {"n": 1})
    store.audit(cid, "test.event", {"n": 2})
    assert store.verify_audit(cid)["valid"] is True
    # tamper with a stored payload -> chain must break
    with store._LOCK:
        store._conn().execute(
            "UPDATE audit SET payload=? WHERE case_id=? AND seq=(SELECT MIN(seq) FROM audit WHERE case_id=?)",
            ('{"n":999}', cid, cid))
        store._conn().commit()
    assert store.verify_audit(cid)["valid"] is False


# ----------------------------------------------------------- correlation ---
def test_income_check_logic():
    docs = [{"id": "d1", "filename": "form"}, {"id": "d2", "filename": "stmt"}]
    fields = [
        {"id": "f1", "doc_id": "d1", "key": "income", "label": "Annual income",
         "value": "Rs. 9,60,000", "normalized": "960000", "page": 1, "bbox": [0, 0, 10, 10]},
        {"id": "f2", "doc_id": "d2", "key": "avg_salary", "label": "Avg",
         "value": "₹34,167", "normalized": "34167", "page": 1, "bbox": [0, 0, 10, 10]},
    ]
    res = correlate.correlate(docs, fields, {})
    income_row = next(r for r in res["matrix"] if r["key"] == "income")
    assert income_row["status"] == "check"


# ------------------------------------------------------------- end-to-end --
def _run_case(variant):
    from app.pipeline import runner
    from app.pipeline.ingest import ingest_file
    from app.samples.generate import build_set
    from app.store import new_id
    import json
    from pathlib import Path

    case = store.create_case(f"e2e-{variant}")
    cid = case["id"]
    for f in build_set(variant):
        did = new_id("doc")
        meta = ingest_file(cid, did, Path(f["path"]), f["name"])
        with store._LOCK:
            store._conn().execute(
                "INSERT INTO documents (id, case_id, filename, sha256, pages, status, meta, created_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (did, cid, f["name"], meta["sha256"], len(meta["pages"]),
                 "ingested", json.dumps(meta), store.now()))
            store._conn().commit()
    runner.analyze_case(cid)
    return cid


@pytest.fixture(scope="module")
def tampered_case():
    return _run_case("tampered")


@pytest.fixture(scope="module")
def genuine_case():
    return _run_case("genuine")


def test_tampered_classification_and_fields(tampered_case):
    docs = store.list_documents(tampered_case)
    types = {d["doc_type"] for d in docs}
    assert {"application_form", "id_proof", "bank_statement"} <= types
    fields = store.list_fields(tampered_case)
    assert any(f["key"] == "dob" and f["normalized"] == "1991-04-21" for f in fields)
    assert any(f["key"] == "name" for f in fields)


def test_tampered_has_conflicts_and_escalation(tampered_case):
    findings = store.list_findings(tampered_case)
    assert any(f["kind"] == "x_dob" for f in findings), "DOB conflict expected"
    assert any(f["level"] == "potential_manipulation" for f in findings), \
        "visual + cross-doc agreement should escalate"
    assert any(f["category"] == "visual_forensic" for f in findings)
    assert all(f["level"] != "fraud" for f in findings)


def test_genuine_is_clean(genuine_case):
    findings = store.list_findings(genuine_case)
    assert not any(f["level"] == "potential_manipulation" for f in findings)
    assert not any(f["category"] == "cross_document" and f["kind"].startswith("x_")
                   and "conflict" in f["title"].lower() for f in findings)
    from app.config import CASES_DIR
    import json
    matrix = json.loads((CASES_DIR / genuine_case / "matrix.json").read_text())
    for row in matrix:
        assert row["status"] in ("consistent", "n/a"), f"{row['key']} should be consistent, got {row['status']}"


def test_dossier_and_chain(tampered_case):
    from app.pipeline import dossier
    out = dossier.build_dossier(tampered_case)
    assert out.exists() and out.stat().st_size > 5000
    assert store.verify_audit(tampered_case)["valid"] is True


def test_reviewer_decision_recorded(tampered_case):
    f = store.list_findings(tampered_case)[0]
    updated = store.record_decision(f["id"], "dismissed", "benign re-save", "tester")
    assert updated["status"] == "dismissed"
    assert updated["decisions"][-1]["note"] == "benign re-save"
    assert store.verify_audit(tampered_case)["valid"] is True
