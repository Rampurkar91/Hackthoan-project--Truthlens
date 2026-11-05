import React from "react";

export default function FieldsPanel({ fields, documents, onTrace }) {
  if (!fields?.length) {
    return <div className="empty-note">Structured fields (name, DOB, address, income, PAN, account…) appear here after OCR. Each keeps its page, bounding box and confidence.</div>;
  }
  const byDoc = documents.map((d) => ({ d, fields: fields.filter((f) => f.doc_id === d.id) })).filter((g) => g.fields.length);
  return (
    <div>
      {byDoc.map(({ d, fields }) => (
        <div key={d.id} style={{ marginBottom: 16 }}>
          <div className="small" style={{ fontWeight: 600, color: "var(--accent)", marginBottom: 4 }}>{d.filename}</div>
          {fields.map((f) => (
            <div className="field-row" key={f.id} onClick={() => onTrace(d.id, null)} title="Trace to source pixels">
              <span className="k">{f.label}</span>
              <span className="v">{f.value}</span>
              <span className="c">p{f.page} · {Math.round(f.confidence * 100)}%</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
