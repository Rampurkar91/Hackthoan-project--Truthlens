import React, { useEffect, useMemo, useRef, useState } from "react";
import { api, LEVELS } from "../api.js";
import { File, Eye } from "../icons.jsx";

export default function DocumentViewer({ doc, fields, findings, selFinding, onSelectFinding }) {
  const [page, setPage] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [showFields, setShowFields] = useState(false);
  const [showFindings, setShowFindings] = useState(true);
  const [cw, setCw] = useState(800);
  const scrollRef = useRef();
  const wrapRef = useRef();

  useEffect(() => { setPage(1); setZoom(1); }, [doc?.id]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setCw(el.clientWidth));
    ro.observe(el);
    setCw(el.clientWidth);
    return () => ro.disconnect();
  }, [doc?.id]);

  const pageInfo = doc?.meta?.pages?.find((p) => p.page === page) || doc?.meta?.pages?.[0];
  const W = pageInfo?.width || 1000;
  const H = pageInfo?.height || 1400;
  const baseW = Math.max(200, cw - 36);
  const dispW = baseW * zoom;
  const scale = dispW / W;

  // finding regions on this doc+page
  const regions = useMemo(() => {
    if (!doc) return [];
    const out = [];
    for (const f of findings) {
      for (const ev of f.evidence || []) {
        if (ev.doc_id === doc.id && (ev.page || 1) === page && ev.bbox?.length === 4) {
          out.push({ f, bbox: ev.bbox, label: ev.label });
        }
      }
    }
    return out;
  }, [doc, findings, page]);

  const pageFields = useMemo(
    () => (doc ? fields.filter((f) => (f.page || 1) === page && f.bbox?.length === 4) : []),
    [doc, fields, page]);

  // click-to-trace: scroll the selected finding's region into view
  useEffect(() => {
    if (!selFinding || !doc || !scrollRef.current) return;
    const f = findings.find((x) => x.id === selFinding);
    const ev = f?.evidence?.find((e) => e.doc_id === doc.id && e.bbox?.length === 4);
    if (!ev) return;
    if ((ev.page || 1) !== page) { setPage(ev.page || 1); return; }
    const [x, y, w, h] = ev.bbox;
    const cx = (x + w / 2) * scale - scrollRef.current.clientWidth / 2;
    const cy = (y + h / 2) * scale - scrollRef.current.clientHeight / 2;
    scrollRef.current.scrollTo({ left: Math.max(0, cx), top: Math.max(0, cy), behavior: "smooth" });
  }, [selFinding, doc, page, scale, findings]);

  if (!doc) {
    return (
      <div className="panel viewer">
        <div className="viewer-empty"><Eye size={40} /><div>Select a document to inspect its pages, fields and forensic regions.</div></div>
      </div>
    );
  }

  const selRegions = regions.filter((r) => r.f.id === selFinding);

  return (
    <div className="panel viewer">
      <div className="viewer-toolbar">
        <span className="title"><File size={14} /> {doc.filename}
          {doc.meta?.pages?.length > 1 && (
            <span className="zoomctl">
              <button onClick={() => setPage((p) => Math.max(1, p - 1))}>‹</button>
              <span>{page}/{doc.meta.pages.length}</span>
              <button onClick={() => setPage((p) => Math.min(doc.meta.pages.length, p + 1))}>›</button>
            </span>
          )}
        </span>
        <label className="toggle"><input type="checkbox" checked={showFindings} onChange={(e) => setShowFindings(e.target.checked)} /> Findings</label>
        <label className="toggle"><input type="checkbox" checked={showFields} onChange={(e) => setShowFields(e.target.checked)} /> Fields</label>
        <span className="zoomctl">
          <button onClick={() => setZoom((z) => Math.max(0.4, z - 0.2))}>−</button>
          <span>{Math.round(zoom * 100)}%</span>
          <button onClick={() => setZoom((z) => Math.min(4, z + 0.2))}>+</button>
          <button onClick={() => setZoom(1)} title="Fit width">⤢</button>
        </span>
      </div>
      <div className="page-scroll" ref={scrollRef}>
        <div className="page-wrap" ref={wrapRef} style={{ width: dispW, height: H * scale }}>
          <img src={api.pageUrl(doc.id, page)} alt={`${doc.filename} page ${page}`} width={dispW} height={H * scale} />
          <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
            {showFields && pageFields.map((f) => (
              <g key={f.id}>
                <rect className="region-box field" x={f.bbox[0]} y={f.bbox[1]} width={f.bbox[2]} height={f.bbox[3]} />
              </g>
            ))}
            {showFindings && regions.map((r, i) => (
              <g key={i} onClick={() => onSelectFinding(r.f.id)} style={{ cursor: "pointer" }}>
                <rect className={`region-box ${r.f.level} ${r.f.id === selFinding ? "selected" : ""}`}
                  x={r.bbox[0]} y={r.bbox[1]} width={r.bbox[2]} height={r.bbox[3]} />
                {r.f.id === selFinding && (
                  <text className="region-label" x={r.bbox[0]} y={Math.max(12, r.bbox[1] - 6)}>
                    {LEVELS[r.f.level].label} · {Math.round(r.f.confidence * 100)}%
                  </text>
                )}
              </g>
            ))}
          </svg>
        </div>
      </div>
    </div>
  );
}
