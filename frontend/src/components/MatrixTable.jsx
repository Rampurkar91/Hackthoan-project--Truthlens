import React from "react";

export default function MatrixTable({ matrix, documents, onTrace }) {
  if (!matrix?.length) {
    return <div className="empty-note">The cross-document matrix appears after analysis. It compares name, date of birth, address and income across every document, tolerating harmless variation.</div>;
  }
  return (
    <div>
      <div className="matrix-wrap">
        <table className="matrix">
          <thead>
            <tr>
              <th>Field</th>
              {documents.map((d) => <th key={d.id}>{d.filename}</th>)}
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {matrix.map((row) => (
              <tr key={row.key}>
                <td style={{ fontWeight: 600 }}>{row.label}</td>
                {row.cells.map((c, i) => (
                  <td key={i} className="val" onClick={() => c.field_id && onTrace(c.doc_id, null)}
                    title={c.field_id ? "Click to trace to source" : ""}>
                    {c.value || <span className="muted">—</span>}
                    {c.derived && <div className="derived">derived from credits</div>}
                  </td>
                ))}
                <td><span className={`status-pill ${row.status}`}>{row.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {matrix.filter((r) => r.note).map((r) => (
        <div className="matrix-note" key={r.key}><b>{r.label}:</b> {r.note}</div>
      ))}
      <div className="matrix-note" style={{ marginTop: 12 }}>
        Entity matching tolerates initials, spacing and date formats. “Check” means a value
        needs explanation (e.g. declared income vs bank credits); “Conflict” means values disagree.
      </div>
    </div>
  );
}
