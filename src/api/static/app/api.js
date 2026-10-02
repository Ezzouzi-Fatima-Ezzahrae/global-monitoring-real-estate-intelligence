// api.js — single source of truth for every real backend call. Every
// function here maps 1:1 to a real FastAPI route in src/api/main.py; none
// of it is invented. Pages/components never call fetch() directly.
"use strict";

async function _req(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    if (body instanceof FormData) {
      opts.body = body;
    } else {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
  }
  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = "HTTP " + res.status;
    try {
      const data = await res.json();
      detail = data.detail || detail;
    } catch (_) { /* not JSON */ }
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.indexOf("application/json") !== -1) return res.json();
  return res;
}

const api = {
  health: () => _req("GET", "/health"),
  notifyStatus: () => _req("GET", "/notify/status"),

  runDigest: () => _req("POST", "/run-digest"),
  runDigestAndNotify: () => _req("POST", "/run-digest-and-notify"),
  notifyTest: () => _req("POST", "/notify/test"),

  listRuns: (limit) => _req("GET", "/runs" + (limit ? "?limit=" + limit : "")),
  getRun: (runId) => _req("GET", "/runs/" + encodeURIComponent(runId)),
  runPdfUrl: (runId) => "/runs/" + encodeURIComponent(runId) + "/pdf",
  getRunTranslation: (runId, lang) => _req("GET", "/runs/" + encodeURIComponent(runId) + "/translation/" + encodeURIComponent(lang)),

  chat: (message, runId, history, lang) => _req("POST", "/chat", { message: message, run_id: runId || null, history: history || [], lang: lang || "en" }),
  setEventNote: (runId, eventId, text) => _req("PUT", "/runs/" + encodeURIComponent(runId) + "/events/" + encodeURIComponent(eventId) + "/note", { text: text }),

  uploadDocument: (file) => {
    const fd = new FormData();
    fd.append("file", file);
    return _req("POST", "/documents/upload", fd);
  },
  listDocuments: () => _req("GET", "/documents"),
  getDocument: (id) => _req("GET", "/documents/" + encodeURIComponent(id)),
  documentPdfUrl: (id) => "/documents/" + encodeURIComponent(id) + "/pdf",
  deleteDocument: (id) => _req("DELETE", "/documents/" + encodeURIComponent(id)),
  getDocumentTranslation: (id, lang) => _req("GET", "/documents/" + encodeURIComponent(id) + "/translation/" + encodeURIComponent(lang)),
};
