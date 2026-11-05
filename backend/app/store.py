"""Evidence store: SQLite persistence + hash-chained audit log.

Every upload, pipeline run, finding and reviewer decision is appended to a
per-case hash chain:  hash_n = SHA256(hash_{n-1} || timestamp || event || payload)
so any later edit of the history is detectable.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from .config import DB_PATH

_LOCK = threading.RLock()
_CONN: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ready',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    doc_type TEXT NOT NULL DEFAULT 'unknown',
    type_confidence REAL NOT NULL DEFAULT 0,
    pages INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'ingested',
    meta TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fields (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    key TEXT NOT NULL,
    label TEXT NOT NULL,
    value TEXT NOT NULL,
    normalized TEXT NOT NULL DEFAULT '',
    page INTEGER NOT NULL DEFAULT 1,
    bbox TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    doc_id TEXT,
    level TEXT NOT NULL,
    category TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL,
    explanation TEXT NOT NULL,
    verification TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 0,
    evidence TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'open',
    auto INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    finding_id TEXT NOT NULL REFERENCES findings(id),
    decision TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    reviewer TEXT NOT NULL DEFAULT 'reviewer',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    event TEXT NOT NULL,
    payload TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_documents_case ON documents(case_id);
CREATE INDEX IF NOT EXISTS idx_fields_case ON fields(case_id);
CREATE INDEX IF NOT EXISTS idx_findings_case ON findings(case_id);
CREATE INDEX IF NOT EXISTS idx_audit_case ON audit(case_id, seq);
"""


def _conn() -> sqlite3.Connection:
    global _CONN
    if _CONN is None:
        _CONN = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _CONN.row_factory = sqlite3.Row
        _CONN.execute("PRAGMA journal_mode=WAL")
        _CONN.executescript(SCHEMA)
        _CONN.commit()
    return _CONN


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


def _decode(row: dict, keys: tuple[str, ...]) -> dict:
    for k in keys:
        if k in row and isinstance(row[k], str):
            try:
                row[k] = json.loads(row[k])
            except json.JSONDecodeError:
                pass
    return row


# ---------------------------------------------------------------- cases ----
def create_case(name: str) -> dict:
    cid = new_id("case")
    with _LOCK:
        _conn().execute(
            "INSERT INTO cases (id, name, status, created_at) VALUES (?,?,?,?)",
            (cid, name, "ready", now()),
        )
        _conn().commit()
    audit(cid, "case.created", {"name": name})
    return get_case(cid)


def get_case(case_id: str) -> dict | None:
    with _LOCK:
        r = _conn().execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
    return dict(r) if r else None


def list_cases() -> list[dict]:
    with _LOCK:
        rows = _rows(_conn().execute("SELECT * FROM cases ORDER BY created_at DESC"))
        for r in rows:
            r["documents"] = _conn().execute(
                "SELECT COUNT(*) c FROM documents WHERE case_id=?", (r["id"],)
            ).fetchone()["c"]
            r["findings"] = _conn().execute(
                "SELECT COUNT(*) c FROM findings WHERE case_id=?", (r["id"],)
            ).fetchone()["c"]
    return rows


def set_case_status(case_id: str, status: str) -> None:
    with _LOCK:
        _conn().execute("UPDATE cases SET status=? WHERE id=?", (status, case_id))
        _conn().commit()


# ------------------------------------------------------------ documents ----
def add_document(case_id: str, filename: str, sha256: str, pages: int, meta: dict) -> dict:
    did = new_id("doc")
    with _LOCK:
        _conn().execute(
            "INSERT INTO documents (id, case_id, filename, sha256, pages, status, meta, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (did, case_id, filename, sha256, pages, "ingested", json.dumps(meta), now()),
        )
        _conn().commit()
    audit(case_id, "document.ingested", {"doc_id": did, "filename": filename, "sha256": sha256, "pages": pages})
    return get_document(did)


def get_document(doc_id: str) -> dict | None:
    with _LOCK:
        r = _conn().execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    return _decode(dict(r), ("meta",)) if r else None


def list_documents(case_id: str) -> list[dict]:
    with _LOCK:
        rows = _rows(_conn().execute(
            "SELECT * FROM documents WHERE case_id=? ORDER BY created_at", (case_id,)))
    return [_decode(r, ("meta",)) for r in rows]


def update_document(doc_id: str, **kw) -> None:
    if not kw:
        return
    if "meta" in kw:
        kw["meta"] = json.dumps(kw["meta"])
    sets = ", ".join(f"{k}=?" for k in kw)
    with _LOCK:
        _conn().execute(f"UPDATE documents SET {sets} WHERE id=?", (*kw.values(), doc_id))
        _conn().commit()


# --------------------------------------------------------------- fields ----
def replace_fields(doc_id: str, case_id: str, fields: list[dict]) -> None:
    with _LOCK:
        _conn().execute("DELETE FROM fields WHERE doc_id=?", (doc_id,))
        for f in fields:
            _conn().execute(
                "INSERT INTO fields (id, case_id, doc_id, key, label, value, normalized, page, bbox, confidence)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (new_id("fld"), case_id, doc_id, f["key"], f["label"], f["value"],
                 f.get("normalized", ""), f.get("page", 1), json.dumps(f.get("bbox", [])),
                 f.get("confidence", 0)),
            )
        _conn().commit()


def list_fields(case_id: str, doc_id: str | None = None) -> list[dict]:
    q = "SELECT * FROM fields WHERE case_id=?"
    args: list[Any] = [case_id]
    if doc_id:
        q += " AND doc_id=?"
        args.append(doc_id)
    with _LOCK:
        rows = _rows(_conn().execute(q + " ORDER BY page, key", args))
    return [_decode(r, ("bbox",)) for r in rows]


# ------------------------------------------------------------- findings ----
def add_finding(case_id: str, **f) -> dict:
    fid = new_id("fnd")
    with _LOCK:
        _conn().execute(
            "INSERT INTO findings (id, case_id, doc_id, level, category, kind, title, explanation,"
            " verification, confidence, evidence, status, auto, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (fid, case_id, f.get("doc_id"), f["level"], f["category"], f.get("kind", ""),
             f["title"], f["explanation"], json.dumps(f.get("verification", [])),
             f.get("confidence", 0.5), json.dumps(f.get("evidence", [])), "open", 1, now()),
        )
        _conn().commit()
    audit(case_id, "finding.created", {
        "finding_id": fid, "level": f["level"], "category": f["category"], "title": f["title"]})
    return get_finding(fid)


def get_finding(fid: str) -> dict | None:
    with _LOCK:
        r = _conn().execute("SELECT * FROM findings WHERE id=?", (fid,)).fetchone()
        if not r:
            return None
        row = _decode(dict(r), ("verification", "evidence"))
        row["decisions"] = _rows(_conn().execute(
            "SELECT * FROM decisions WHERE finding_id=? ORDER BY created_at", (fid,)))
    return row


def list_findings(case_id: str) -> list[dict]:
    with _LOCK:
        rows = _rows(_conn().execute(
            "SELECT * FROM findings WHERE case_id=? ORDER BY"
            " CASE level WHEN 'potential_manipulation' THEN 0 WHEN 'inconsistent' THEN 1 ELSE 2 END,"
            " confidence DESC", (case_id,)))
        out = []
        for r in rows:
            r = _decode(r, ("verification", "evidence"))
            r["decisions"] = _rows(_conn().execute(
                "SELECT * FROM decisions WHERE finding_id=? ORDER BY created_at", (r["id"],)))
            out.append(r)
    return out


def clear_auto_findings(case_id: str, doc_id: str | None = None, categories: list[str] | None = None) -> None:
    """Remove machine-generated findings that have no reviewer decision yet."""
    q = "SELECT id FROM findings WHERE case_id=? AND auto=1"
    args: list[Any] = [case_id]
    if doc_id:
        q += " AND doc_id=?"
        args.append(doc_id)
    if categories:
        q += f" AND category IN ({','.join('?' * len(categories))})"
        args += categories
    with _LOCK:
        ids = [r["id"] for r in _conn().execute(q, args).fetchall()]
        for fid in ids:
            has = _conn().execute(
                "SELECT 1 FROM decisions WHERE finding_id=? LIMIT 1", (fid,)).fetchone()
            if not has:
                _conn().execute("DELETE FROM findings WHERE id=?", (fid,))
        _conn().commit()


def record_decision(fid: str, decision: str, note: str, reviewer: str) -> dict | None:
    f = get_finding(fid)
    if not f:
        return None
    status = {"confirmed": "confirmed_by_reviewer", "dismissed": "dismissed",
              "needs_review": "needs_review"}.get(decision, decision)
    with _LOCK:
        _conn().execute(
            "INSERT INTO decisions (id, finding_id, decision, note, reviewer, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (new_id("dec"), fid, decision, note, reviewer, now()),
        )
        _conn().execute("UPDATE findings SET status=? WHERE id=?", (status, fid))
        _conn().commit()
    audit(f["case_id"], "reviewer.decision", {
        "finding_id": fid, "decision": decision, "note": note, "reviewer": reviewer})
    return get_finding(fid)


# ---------------------------------------------------------------- audit ----
def _hash(prev: str, ts: str, event: str, payload: str) -> str:
    return hashlib.sha256(f"{prev}|{ts}|{event}|{payload}".encode()).hexdigest()


def audit(case_id: str, event: str, payload: dict) -> dict:
    payload_s = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    ts = now()
    with _LOCK:
        last = _conn().execute(
            "SELECT hash FROM audit WHERE case_id=? ORDER BY seq DESC LIMIT 1", (case_id,)
        ).fetchone()
        prev = last["hash"] if last else "0" * 64
        h = _hash(prev, ts, event, payload_s)
        cur = _conn().execute(
            "INSERT INTO audit (case_id, ts, event, payload, prev_hash, hash) VALUES (?,?,?,?,?,?)",
            (case_id, ts, event, payload_s, prev, h),
        )
        _conn().commit()
        return {"seq": cur.lastrowid, "case_id": case_id, "ts": ts, "event": event,
                "payload": payload, "prev_hash": prev, "hash": h}


def list_audit(case_id: str) -> list[dict]:
    with _LOCK:
        rows = _rows(_conn().execute(
            "SELECT * FROM audit WHERE case_id=? ORDER BY seq", (case_id,)))
    return [_decode(r, ("payload",)) for r in rows]


def verify_audit(case_id: str) -> dict:
    rows = list_audit(case_id)
    prev = "0" * 64
    for i, r in enumerate(rows):
        payload_s = json.dumps(r["payload"], sort_keys=True, separators=(",", ":"))
        if r["prev_hash"] != prev:
            return {"valid": False, "entries": len(rows), "broken_at": r["seq"],
                    "reason": "previous-hash link mismatch"}
        if _hash(prev, r["ts"], r["event"], payload_s) != r["hash"]:
            return {"valid": False, "entries": len(rows), "broken_at": r["seq"],
                    "reason": "entry hash mismatch (content altered)"}
        prev = r["hash"]
    return {"valid": True, "entries": len(rows), "head_hash": prev}
