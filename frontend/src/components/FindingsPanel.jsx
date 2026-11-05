import React, { useState } from "react";
import { LEVELS } from "../api.js";
import { Check, X, Alert, Link } from "../icons.jsx";

export default function FindingsPanel({ findings, documents, selFinding, onSelect, onTrace, onDecision }) {
  const [filter, setFilter] = useState("all");
  const counts = {
    all: findings.length,
    potential_manipulation: findings.filter((f) => f.level === "potential_manipulation").length,
    inconsistent: findings.filter((f) => f.level === "inconsistent").length,
    observed: findings.filter((f) => f.level === "observed").length,
  };
  const shown = filter === "all" ? findings : findings.filter((f) => f.level === filter);

  if (!findings.length) {
    return <div className="empty-note">No findings yet. Once analysis completes, observations, inconsistencies and potential manipulations appear here — each traceable to source pixels.</div>;
  }

  return (
    <div>
      <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
        {[["all", "All"], ["potential_manipulation", "Potential"], ["inconsistent", "Inconsistent"], ["observed", "Observed"]].map(([k, label]) => (
          <button key={k} className={`btn sm ${filter === k ? "primary" : ""}`} onClick={() => setFilter(k)}>
            {label} ({counts[k]})
          </button>
        ))}
      </div>
      {shown.map((f) => (
        <FindingCard key={f.id} f={f} documents={documents} selected={selFinding === f.id}
          onSelect={onSelect} onTrace={onTrace} onDecision={onDecision} />
      ))}
    </div>
  );
}

function FindingCard({ f, documents, selected, onSelect, onTrace, onDecision }) {
  const [noteMode, setNoteMode] = useState(null);
  const [note, setNote] = useState("");
  const lvl = LEVELS[f.level];
  const docName = (id) => documents.find((d) => d.id === id)?.filename || "document";

  const decide = (dec) => {
    if (noteMode === dec) { onDecision(f.id, dec, note); setNoteMode(null); setNote(""); }
    else { setNoteMode(dec); setNote(""); }
  };

  return (
    <div className={`finding ${f.level} ${selected ? "selected" : ""}`} onClick={() => onSelect(f.id)}>
      <div className="top">
        <span className={`level-badge ${f.level}`}>{lvl.label}</span>
        <span className="conf">{Math.round(f.confidence * 100)}%</span>
      </div>
      <h4>{f.title}</h4>
      <div className="conf-bar"><i style={{ width: `${f.confidence * 100}%`, background: lvl.color }} /></div>
      <p className="expl">{f.explanation}</p>

      {f.verification?.length > 0 && (
        <details className="verify" onClick={(e) => e.stopPropagation()}>
          <summary>What to verify next</summary>
          <ul>{f.verification.map((v, i) => <li key={i}>{v}</li>)}</ul>
        </details>
      )}

      {f.evidence?.length > 0 && (
        <div className="evidence-row" onClick={(e) => e.stopPropagation()}>
          {f.evidence.filter((e) => e.bbox?.length === 4).slice(0, 4).map((ev, i) => (
            <button key={i} className="ev-chip" title="Trace to source pixels"
              onClick={() => onTrace(ev.doc_id, f.id)}>
              <Link size={10} /> {docName(ev.doc_id)} · p{ev.page || 1}
            </button>
          ))}
        </div>
      )}

      <div className="decision-row" onClick={(e) => e.stopPropagation()}>
        {f.status !== "open" && <span className={`decision-status ${f.status}`}>{f.status.replace(/_/g, " ")}</span>}
        <button className="btn sm" onClick={() => decide("confirmed")} title="Agree — needs action"><Check size={12} /> Confirm</button>
        <button className="btn sm" onClick={() => decide("needs_review")} title="Flag for senior review"><Alert size={12} /> Review</button>
        <button className="btn sm" onClick={() => decide("dismissed")} title="Benign explanation"><X size={12} /> Dismiss</button>
      </div>
      {noteMode && (
        <div style={{ marginTop: 8 }} onClick={(e) => e.stopPropagation()}>
          <input value={note} onChange={(e) => setNote(e.target.value)} autoFocus
            placeholder={`Note for "${noteMode}" (optional)…`}
            style={{ width: "100%", background: "var(--bg)", border: "1px solid var(--border-2)", color: "var(--text)", borderRadius: 7, padding: "6px 9px", fontSize: 12 }}
            onKeyDown={(e) => { if (e.key === "Enter") { onDecision(f.id, noteMode, note); setNoteMode(null); } }} />
          <div className="small muted" style={{ marginTop: 4 }}>Press Enter to record — timestamped in the audit trail.</div>
        </div>
      )}
    </div>
  );
}
