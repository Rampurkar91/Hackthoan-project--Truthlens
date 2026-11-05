import React, { useState } from "react";
import { api, shortHash, timeAgo } from "../api.js";
import { Shield, Check, X } from "../icons.jsx";

export default function AuditTrail({ caseId, entries, chain }) {
  const [verify, setVerify] = useState(chain);
  const [checking, setChecking] = useState(false);

  const reverify = async () => {
    setChecking(true);
    try { const r = await api.verifyAudit(caseId); setVerify(r.chain); }
    catch {}
    setChecking(false);
  };

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
        <span className={`chain-badge ${verify?.valid ? "ok" : "bad"}`}>
          {verify?.valid ? <Check size={13} /> : <X size={13} />}
          {verify?.valid ? "Chain verified" : "Chain broken"}
        </span>
        <span className="small muted">{verify?.entries ?? entries.length} entries</span>
        <button className="btn sm ghost" style={{ marginLeft: "auto" }} onClick={reverify} disabled={checking}>
          {checking ? <span className="spinner" /> : <Shield size={13} />} Re-verify
        </button>
      </div>
      <div className="small muted" style={{ marginBottom: 12 }}>
        Every upload, run, finding and decision is appended to a SHA-256 hash chain.
        Head: <span className="mono">{shortHash(verify?.head_hash)}</span>
      </div>
      {[...entries].reverse().map((e) => (
        <div className="audit-item" key={e.seq}>
          <span className="seq">#{e.seq}</span>
          <div style={{ flex: 1 }}>
            <div className="ev">{e.event}</div>
            <div className="ts">{timeAgo(e.ts)}</div>
            <div className="hh">prev {shortHash(e.prev_hash)} → {shortHash(e.hash)}</div>
          </div>
        </div>
      ))}
    </div>
  );
}
