import React, { useCallback, useEffect, useRef, useState } from "react";
import { api, DOC_TYPES, LEVELS, shortHash } from "./api.js";
import { Lens, Upload, File, Download, Plus, Refresh, Shield, Trash, Eye } from "./icons.jsx";
import DocumentViewer from "./components/DocumentViewer.jsx";
import FindingsPanel from "./components/FindingsPanel.jsx";
import MatrixTable from "./components/MatrixTable.jsx";
import AuditTrail from "./components/AuditTrail.jsx";
import FieldsPanel from "./components/FieldsPanel.jsx";

const PIPELINE = ["Ingest", "OCR", "Fields", "Forensics", "Context", "Correlate", "Dossier"];

export default function App() {
  const [cases, setCases] = useState([]);
  const [caseId, setCaseId] = useState(null);
  const [data, setData] = useState(null);
  const [tab, setTab] = useState("findings");
  const [selDoc, setSelDoc] = useState(null);
  const [selFinding, setSelFinding] = useState(null);
  const [toast, setToast] = useState(null);
  const [busy, setBusy] = useState(false);
  const pollRef = useRef(null);

  const notify = (msg, err = false) => {
    setToast({ msg, err });
    setTimeout(() => setToast(null), 3800);
  };

  const refreshCases = useCallback(async () => {
    try { setCases(await api.listCases()); } catch (e) { /* backend waking */ }
  }, []);

  const loadCase = useCallback(async (id) => {
    try {
      const d = await api.getCase(id);
      setData(d);
      setSelDoc((prev) => {
        if (prev && d.documents.some((x) => x.id === prev)) return prev;
        return d.documents[0]?.id || null;
      });
      return d;
    } catch (e) { notify(e.message, true); }
  }, []);

  useEffect(() => { refreshCases(); }, [refreshCases]);

  // poll while analyzing
  useEffect(() => {
    clearInterval(pollRef.current);
    if (!caseId || !data) return;
    const analyzing = data.case.status === "analyzing" ||
      data.documents.some((d) => d.status === "processing" || d.status === "ingested");
    if (analyzing) {
      pollRef.current = setInterval(async () => {
        const d = await loadCase(caseId);
        if (d && d.case.status !== "analyzing" &&
            !d.documents.some((x) => x.status === "processing" || x.status === "ingested")) {
          clearInterval(pollRef.current);
          refreshCases();
        }
      }, 1600);
    }
    return () => clearInterval(pollRef.current);
  }, [caseId, data, loadCase, refreshCases]);

  const openCase = async (id) => { setCaseId(id); setSelFinding(null); await loadCase(id); };

  const newCase = async (name) => {
    const c = await api.createCase(name || `Case ${new Date().toLocaleDateString()}`);
    await refreshCases();
    await openCase(c.id);
    return c;
  };

  const startDemo = async (variant) => {
    setBusy(true);
    try {
      const c = await newCase(variant === "tampered" ? "Demo — tampered documents" : "Demo — genuine documents");
      await api.loadDemo(c.id, variant);
      await loadCase(c.id);
      notify(`Loading ${variant} sample case — analysis running…`);
    } catch (e) { notify(e.message, true); }
    setBusy(false);
  };

  const onUpload = async (files) => {
    if (!files?.length) return;
    let id = caseId;
    if (!id) { const c = await newCase("Uploaded documents"); id = c.id; }
    setBusy(true);
    try {
      await api.upload(id, files);
      await loadCase(id);
      notify(`Uploaded ${files.length} file(s) — analysis running…`);
    } catch (e) { notify(e.message, true); }
    setBusy(false);
  };

  const reanalyze = async () => {
    if (!caseId) return;
    await api.analyze(caseId); await loadCase(caseId); notify("Re-running analysis…");
  };

  const removeCase = async () => {
    if (!caseId || !confirm("Delete this case and all its evidence?")) return;
    await api.deleteCase(caseId);
    setCaseId(null); setData(null); setSelDoc(null); setSelFinding(null);
    await refreshCases();
  };

  const traceTo = (docId, findingId) => {
    setSelDoc(docId);
    if (findingId) setSelFinding(findingId);
    setTab("findings");
  };

  const analyzing = data && (data.case.status === "analyzing" ||
    data.documents.some((d) => d.status === "processing" || d.status === "ingested"));

  return (
    <>
      <header className="header">
        <div className="brand">
          <span className="logo"><Lens /></span>
          <div>
            <h1>Truth<span>Lens</span></h1>
            <div className="tag"><b>Observe</b> → <b>Correlate</b> → <b>Explain</b></div>
          </div>
        </div>
        <div className="spacer" />
        {cases.length > 0 && (
          <select className="case-select" value={caseId || ""} onChange={(e) => e.target.value && openCase(e.target.value)}>
            <option value="">Select case…</option>
            {cases.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.documents} docs)</option>)}
          </select>
        )}
        <button className="btn" onClick={() => newCase()}><Plus size={15} /> New case</button>
        {caseId && (
          <a className="btn primary" href={api.dossierUrl(caseId)} target="_blank" rel="noreferrer">
            <Download size={15} /> Dossier
          </a>
        )}
      </header>

      <div className="main">
        {!data ? (
          <Hero onDemo={startDemo} onUpload={onUpload} busy={busy} />
        ) : (
          <>
            <div className="statusbar">
              <span className={`dot ${analyzing ? "busy" : data.case.status === "error" ? "err" : ""}`} />
              <span>{data.case.name}</span>
              <span className="mono" style={{ color: "var(--faint)" }}>{data.case.id}</span>
              {analyzing && (
                <span className="steps">
                  {PIPELINE.map((s, i) => <span key={s} className={`step ${i < 4 ? "active" : ""}`}>{s}</span>)}
                </span>
              )}
              <div className="right">
                <span className="small muted">{data.documents.length} docs · {data.findings.length} findings</span>
                <button className="btn sm ghost" onClick={reanalyze} disabled={analyzing}><Refresh size={13} /> Re-run</button>
                <button className="btn sm ghost danger" onClick={removeCase}><Trash size={13} /></button>
              </div>
            </div>

            <div className="workspace">
              {/* left: documents + upload */}
              <div className="col">
                <div className="panel" style={{ flex: "none" }}>
                  <div className="panel-head"><Upload size={14} /> Add documents</div>
                  <div className="panel-body">
                    <Dropzone onUpload={onUpload} busy={busy} />
                    <div className="demo-row">
                      <button className="btn sm" onClick={() => startDemo("tampered")} disabled={busy}>Tampered demo</button>
                      <button className="btn sm" onClick={() => startDemo("genuine")} disabled={busy}>Genuine demo</button>
                    </div>
                  </div>
                </div>
                <div className="panel" style={{ flex: 1 }}>
                  <div className="panel-head"><File size={14} /> Documents <span className="count">{data.documents.length}</span></div>
                  <div className="panel-body">
                    {data.documents.length === 0 && <div className="empty-note">No documents yet. Upload files or load a demo.</div>}
                    {data.documents.map((d) => (
                      <div key={d.id} className={`doc-item ${selDoc === d.id ? "active" : ""}`} onClick={() => setSelDoc(d.id)}>
                        <div className="name"><File size={14} /> {d.filename}</div>
                        <div className="meta">
                          <span className="chip type">{DOC_TYPES[d.doc_type] || d.doc_type}</span>
                          <span className={`chip ${d.status === "ready" ? "ok" : d.status === "error" ? "err" : "busy"}`}>
                            {d.status === "ready" ? "analyzed" : d.status}
                          </span>
                          <span className="chip">{d.pages}p</span>
                        </div>
                        <div className="hash">sha256 {shortHash(d.sha256)}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* center: viewer */}
              <div className="col">
                <DocumentViewer
                  doc={data.documents.find((d) => d.id === selDoc)}
                  fields={data.fields.filter((f) => f.doc_id === selDoc)}
                  findings={data.findings}
                  selFinding={selFinding}
                  onSelectFinding={setSelFinding}
                />
              </div>

              {/* right: tabs */}
              <div className="col">
                <div className="panel" style={{ flex: 1 }}>
                  <div className="tabs">
                    <button className={`tab ${tab === "findings" ? "active" : ""}`} onClick={() => setTab("findings")}>
                      Findings <span className="badge">{data.findings.length}</span>
                    </button>
                    <button className={`tab ${tab === "matrix" ? "active" : ""}`} onClick={() => setTab("matrix")}>Matrix</button>
                    <button className={`tab ${tab === "fields" ? "active" : ""}`} onClick={() => setTab("fields")}>Fields</button>
                    <button className={`tab ${tab === "audit" ? "active" : ""}`} onClick={() => setTab("audit")}>Audit</button>
                  </div>
                  <div className="panel-body" style={{ flex: 1 }}>
                    {tab === "findings" && (
                      <FindingsPanel findings={data.findings} documents={data.documents}
                        selFinding={selFinding} onSelect={setSelFinding} onTrace={traceTo}
                        onDecision={async (fid, dec, note) => {
                          try { await api.decide(fid, dec, note, "reviewer"); await loadCase(caseId); notify("Decision recorded in audit trail"); }
                          catch (e) { notify(e.message, true); }
                        }} />
                    )}
                    {tab === "matrix" && <MatrixTable matrix={data.matrix} documents={data.documents} onTrace={traceTo} />}
                    {tab === "fields" && <FieldsPanel fields={data.fields} documents={data.documents} onTrace={traceTo} />}
                    {tab === "audit" && <AuditTrail caseId={caseId} entries={data.audit} chain={data.chain} />}
                  </div>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
      {toast && <div className={`toast ${toast.err ? "err" : ""}`}>{toast.msg}</div>}
    </>
  );
}

function Hero({ onDemo, onUpload, busy }) {
  return (
    <div className="hero">
      <span className="big-logo"><Lens size={76} /></span>
      <h2>Truth<span>Lens</span></h2>
      <p className="sub">
        AI-powered document forensics &amp; contextual intelligence. OCR reads documents —
        TruthLens <b>verifies</b> them: visual tampering signals, cross-document conflicts,
        and an evidence trail that traces every finding back to the exact pixels.
      </p>
      <div className="pipeline">
        {["Ingest & Classify", "OCR & Extract", "Structure Fields", "Visual Forensics", "Contextual Checks", "Cross-Doc Correlation", "Evidence & Dossier"].map((s) => (
          <span className="pstep" key={s}>{s}</span>
        ))}
      </div>
      <div className="actions">
        <button className="btn primary" onClick={() => onDemo("tampered")} disabled={busy}>
          <Eye size={17} /> Load tampered demo
        </button>
        <button className="btn" onClick={() => onDemo("genuine")} disabled={busy}>
          <Shield size={17} /> Load genuine demo
        </button>
        <label className="btn" style={{ cursor: "pointer" }}>
          <Upload size={17} /> Upload documents
          <input type="file" multiple hidden accept=".pdf,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff"
            onChange={(e) => onUpload(Array.from(e.target.files || []))} />
        </label>
      </div>
      <p className="fineprint">
        Findings are labelled <b style={{ color: "var(--observed)" }}>Observed</b>,{" "}
        <b style={{ color: "var(--inconsistent)" }}>Inconsistent</b> or{" "}
        <b style={{ color: "var(--potential)" }}>Potential manipulation</b> — never “confirmed fraud”.
        A human reviewer makes the final call. Demo documents are synthetic and fictional.
      </p>
    </div>
  );
}

function Dropzone({ onUpload, busy }) {
  const [over, setOver] = useState(false);
  const ref = useRef();
  return (
    <div className={`dropzone ${over ? "over" : ""}`}
      onClick={() => ref.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); onUpload(Array.from(e.dataTransfer.files)); }}>
      <Upload size={22} />
      {busy ? "Uploading…" : "Drop PDF / scans / images here, or click to browse"}
      <input ref={ref} type="file" multiple hidden accept=".pdf,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff"
        onChange={(e) => onUpload(Array.from(e.target.files || []))} />
    </div>
  );
}
