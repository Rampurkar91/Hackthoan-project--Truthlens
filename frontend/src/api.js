const BASE = "/api";

async function req(path, opts = {}) {
  const res = await fetch(BASE + path, {
    headers: opts.body && !(opts.body instanceof FormData)
      ? { "Content-Type": "application/json" } : undefined,
    ...opts,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  health: () => req("/health"),
  listCases: () => req("/cases"),
  createCase: (name) => req("/cases", { method: "POST", body: JSON.stringify({ name }) }),
  getCase: (id) => req(`/cases/${id}`),
  deleteCase: (id) => req(`/cases/${id}`, { method: "DELETE" }),
  upload: (id, files) => {
    const fd = new FormData();
    for (const f of files) fd.append("files", f);
    return req(`/cases/${id}/documents`, { method: "POST", body: fd });
  },
  loadDemo: (id, variant) => req(`/cases/${id}/demo?variant=${variant}`, { method: "POST" }),
  analyze: (id) => req(`/cases/${id}/analyze`, { method: "POST" }),
  getDocument: (id) => req(`/documents/${id}`),
  pageUrl: (docId, page) => `${BASE}/documents/${docId}/pages/${page}.png`,
  originalUrl: (docId) => `${BASE}/documents/${docId}/original`,
  dossierUrl: (caseId) => `${BASE}/cases/${caseId}/dossier.pdf`,
  decide: (fid, decision, note, reviewer) =>
    req(`/findings/${fid}/decision`, {
      method: "POST",
      body: JSON.stringify({ decision, note, reviewer }),
    }),
  verifyAudit: (id) => req(`/cases/${id}/audit`),
};

export const LEVELS = {
  observed: { label: "Observed", color: "#38bdf8", rank: 2 },
  inconsistent: { label: "Inconsistent", color: "#f59e0b", rank: 1 },
  potential_manipulation: { label: "Potential manipulation", color: "#fb7185", rank: 0 },
};

export const DOC_TYPES = {
  application_form: "Application form",
  id_proof: "ID proof",
  bank_statement: "Bank statement",
  unknown: "Unclassified",
};

export function shortHash(h) {
  return h ? `${h.slice(0, 10)}…${h.slice(-6)}` : "";
}

export function timeAgo(iso) {
  if (!iso) return "";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
  return d.toLocaleString();
}
