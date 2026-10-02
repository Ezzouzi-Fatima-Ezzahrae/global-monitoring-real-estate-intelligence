// pages/documents.js — Document Intelligence: upload one or several PDFs,
// get real AI-extracted events grounded in each file (src/agents/
// document_agent.py via POST /documents/upload, called once per file --
// there is no batch endpoint, so multiple files are uploaded one at a time
// from here). The table below it is the Document Library: every real
// document GET /documents returns, with a client-side filename search and
// status filter (same "reorganize real data, never invent it" pattern as
// pages/feed.js and pages/search.js), plus multi-select + bulk delete.
"use strict";

Pages.documents = {
  async render(container, params, isStale) {
    container.innerHTML = '<div class="page-head"><div><div class="page-eyebrow">' + escapeHtml(t("documentsEyebrow")) + '</div>' +
      '<div class="page-title">' + escapeHtml(t("documentsTitle")) + '</div><div class="page-desc">' + escapeHtml(t("documentsDesc")) + '</div></div></div>' +
      '<div class="panel panel-pad">' + skeletonLines(4, ["w-full"]) + "</div>";

    let docs = [];
    try { docs = await loadDocuments(); } catch (exc) {
      if (!isStale()) container.querySelector(".panel").outerHTML = errorState({ title: t("runFailedTitle"), desc: String((exc && exc.message) || exc), detail: exc && exc.stack });
      return;
    }
    if (isStale()) return;
    _renderDocuments(container, docs, isStale);
  },
};

function _renderDocuments(container, docs, isStale) {
  // Local, per-render state: which real documents are selected, and the
  // current search/status filter -- reset every time the library list is
  // re-rendered (e.g. after an upload or a delete) since a filtered-out or
  // now-deleted selection would otherwise be stale.
  const state = { selected: new Set(), search: "", status: "" };

  let html = '<div class="page-head"><div><div class="page-eyebrow">' + escapeHtml(t("documentsEyebrow")) + '</div>' +
    '<div class="page-title">' + escapeHtml(t("documentsTitle")) + '</div><div class="page-desc">' + escapeHtml(t("documentsDesc")) + '</div></div></div>';

  html += '<div class="panel panel-pad" style="margin-bottom:18px">' +
    '<div class="dropzone" id="docDropzone" tabindex="0" role="button">' + icon("upload") +
    '<div>' + escapeHtml(t("uploadDocumentBtn")) + '</div></div>' +
    '<div class="upload-actions-row">' +
    '<div class="hint-text">' + escapeHtml(t("dropMultipleHint")) + '</div>' +
    '<button type="button" class="btn btn-ghost btn-sm" id="docUploadFolderBtn">' + icon("folder") + '<span>' + escapeHtml(t("uploadFolderBtn")) + '</span></button>' +
    '</div>' +
    '<input type="file" id="docFileInput" accept="application/pdf" multiple style="display:none">' +
    '<input type="file" id="docFolderInput" webkitdirectory directory multiple style="display:none">' +
    '<div id="docUploadStatus"></div></div>';

  html += '<div class="panel">' +
    '<div class="filter-row" id="docsFilterRow">' +
    '<form class="search-box" id="docsSearchForm" role="search">' + icon("search") +
    '<input type="text" id="docsSearchInput" placeholder="' + escapeHtml(t("searchDocumentsPlaceholder")) + '" autocomplete="off"></form>' +
    '<select class="filter-select" id="docsStatusFilter"><option value="">' + escapeHtml(t("filterAllStatus")) + '</option>' +
    '<option value="ok">' + escapeHtml(t("docStatusAnalyzed")) + '</option>' +
    '<option value="error">' + escapeHtml(t("docStatusFailed")) + '</option></select>' +
    '<span class="section-count" id="docsCount"></span>' +
    '</div>' +
    '<div class="filter-row" id="docsBulkToolbar" style="display:none">' +
    '<span class="section-count" id="docsSelectedCount"></span>' +
    '<button type="button" class="btn btn-danger-ghost btn-sm" id="docsDeleteSelectedBtn">' + icon("trash") + '<span id="docsDeleteSelectedLabel"></span></button>' +
    '</div>' +
    '<div class="table-wrap"><table class="data-table"><thead><tr>' +
    '<th style="width:36px"><input type="checkbox" id="docsSelectAll" aria-label="' + escapeHtml(t("selectAllDocuments")) + '"></th>' +
    '<th>' + escapeHtml(t("colDocument")) + '</th><th>' + escapeHtml(t("colType")) + '</th>' +
    '<th>' + escapeHtml(t("colUploaded")) + '</th><th>' + escapeHtml(t("colStatusDoc")) + '</th>' +
    '<th>' + escapeHtml(t("colEventsExtracted")) + '</th><th>' + escapeHtml(t("colActions")) + '</th></tr></thead>' +
    '<tbody id="docsBody"></tbody></table></div></div>';

  container.innerHTML = html;

  if (!docs.length) {
    document.getElementById("docsFilterRow").style.display = "none";
    document.getElementById("docsBody").innerHTML = '<tr><td colspan="7">' + emptyState({ icon: "documents", title: t("noDocumentsTitle"), desc: t("noDocumentsDesc") }) + "</td></tr>";
  } else {
    _wireLibrary(container, docs, state, isStale);
  }

  _wireUpload(container, isStale);
}

function _matchesFilters(doc, state) {
  if (state.status === "ok" && doc.error) return false;
  if (state.status === "error" && !doc.error) return false;
  if (state.search && (doc.filename || "").toLowerCase().indexOf(state.search) === -1) return false;
  return true;
}

function _wireLibrary(container, docs, state, isStale) {
  function currentFiltered() { return docs.filter(function (d) { return _matchesFilters(d, state); }); }

  function renderRows() {
    const filtered = currentFiltered();
    document.getElementById("docsCount").textContent = filtered.length;

    const body = document.getElementById("docsBody");
    if (!filtered.length) {
      body.innerHTML = '<tr><td colspan="7">' + emptyState({ icon: "search", title: t("noDocumentsMatchTitle"), desc: t("noDocumentsMatchDesc") }) + "</td></tr>";
    } else {
      body.innerHTML = filtered.map(function (d) {
        const statusHtml = d.error
          ? '<button type="button" class="btn btn-ghost btn-sm" data-doc-error="' + escapeHtml(d.document_id) + '"><span class="tag tone-bad">' + escapeHtml(t("docStatusFailed")) + '</span></button>'
          : '<span class="tag tone-good">' + escapeHtml(t("docStatusAnalyzed")) + '</span>';
        return '<tr>' +
          '<td data-label=""><input type="checkbox" class="doc-row-check" data-doc-check="' + escapeHtml(d.document_id) + '"' + (state.selected.has(d.document_id) ? " checked" : "") + '></td>' +
          '<td data-label="' + escapeHtml(t("colDocument")) + '">' + escapeHtml(d.filename) + '</td>' +
          '<td data-label="' + escapeHtml(t("colType")) + '"><span class="geo-tag">' + escapeHtml(t("docTypePdf")) + '</span></td>' +
          '<td data-label="' + escapeHtml(t("colUploaded")) + '" class="num">' + escapeHtml(fmtDateTime(d.uploaded_at, localeTag())) + '</td>' +
          '<td data-label="' + escapeHtml(t("colStatusDoc")) + '">' + statusHtml + '</td>' +
          '<td data-label="' + escapeHtml(t("colEventsExtracted")) + '" class="num ltr-num">' + (d.event_count || 0) + '</td>' +
          '<td data-label="' + escapeHtml(t("colActions")) + '">' +
          '<a class="btn btn-ghost btn-sm" href="' + api.documentPdfUrl(d.document_id) + '" target="_blank">' + escapeHtml(t("viewPdf")) + '</a> ' +
          '<button type="button" class="btn btn-ghost btn-sm" data-doc-view="' + escapeHtml(d.document_id) + '">' + escapeHtml(t("viewDocumentDetails")) + '</button> ' +
          '<button type="button" class="btn btn-danger-ghost btn-sm" data-doc-del="' + escapeHtml(d.document_id) + '">' + icon("trash") + '</button>' +
          '</td></tr>';
      }).join("");
    }

    Array.prototype.forEach.call(body.querySelectorAll("[data-doc-error]"), function (btn) {
      btn.addEventListener("click", function () {
        const d = docs.filter(function (x) { return x.document_id === btn.getAttribute("data-doc-error"); })[0];
        openDrawer(escapeHtml(d.filename), errorState({ title: t("documentFailedLabel"), desc: "", detail: d.error }));
      });
    });
    Array.prototype.forEach.call(body.querySelectorAll("[data-doc-view]"), function (btn) {
      btn.addEventListener("click", async function () {
        const id = btn.getAttribute("data-doc-view");
        openDrawer(escapeHtml(t("loading")), skeletonLines(4, ["w-full"]));
        try {
          let full = await api.getDocument(id);
          const lang = getLang();
          if (lang !== "en" && (full.events || []).length) {
            openDrawer(escapeHtml(full.filename), skeletonLines(3, ["w-40"]) +
              '<div class="hint-text" style="margin-top:10px">' + escapeHtml(t("translatingLabel")) + '</div>');
            try {
              const trans = await loadDocumentTranslation(id, lang);
              full = applyDocumentTranslation(full, trans);
            } catch (exc) {
              console.error("Document translation failed for " + id + ":", exc);
            }
          }
          let dbody = '<div><div class="drawer-section-title">' + escapeHtml(t("colUploaded")) + '</div><div class="briefing-body">' + escapeHtml(fmtDateTime(full.uploaded_at, localeTag())) + ' · ' + (full.page_count || 0) + ' pages</div></div>';
          if (full.limitations && full.limitations.length) {
            dbody += '<div><div class="drawer-section-title">' + escapeHtml(t("technicalDetails")) + '</div><ul style="margin:0;padding-inline-start:18px">' +
              full.limitations.map(function (l) { return '<li class="hint-text">' + escapeHtml(l) + "</li>"; }).join("") + "</ul></div>";
          }
          dbody += '<div><div class="drawer-section-title">' + escapeHtml(t("colEventsExtracted")) + ' (' + (full.events || []).length + ')</div>';
          dbody += (full.events || []).length ? full.events.map(function (e) { return intelItemHtml(e, null); }).join("") : '<div class="hint-text">' + escapeHtml(t("noEventsTitle")) + "</div>";
          dbody += "</div>";
          openDrawer(escapeHtml(full.filename), dbody);
        } catch (exc) {
          openDrawer(escapeHtml(t("documentFailedLabel")), errorState({ title: t("runFailedTitle"), desc: String((exc && exc.message) || exc) }));
        }
      });
    });
    Array.prototype.forEach.call(body.querySelectorAll("[data-doc-del]"), function (btn) {
      btn.addEventListener("click", async function () {
        const id = btn.getAttribute("data-doc-del");
        btn.disabled = true;
        try {
          await api.deleteDocument(id);
          invalidateDocuments();
          toast(t("deleteDocument") + " ✓", "good");
          const fresh = await loadDocuments(true);
          if (!isStale()) _renderDocuments(container, fresh, isStale);
        } catch (exc) {
          toast(String((exc && exc.message) || exc), "bad");
          btn.disabled = false;
        }
      });
    });
    Array.prototype.forEach.call(body.querySelectorAll("[data-doc-check]"), function (cb) {
      cb.addEventListener("change", function () {
        const id = cb.getAttribute("data-doc-check");
        if (cb.checked) state.selected.add(id); else state.selected.delete(id);
        renderToolbar();
        syncSelectAll();
      });
    });
    syncSelectAll();
  }

  function syncSelectAll() {
    const filtered = currentFiltered();
    const selectAll = document.getElementById("docsSelectAll");
    if (!filtered.length) { selectAll.checked = false; selectAll.indeterminate = false; return; }
    const selectedVisible = filtered.filter(function (d) { return state.selected.has(d.document_id); }).length;
    selectAll.checked = selectedVisible === filtered.length;
    selectAll.indeterminate = selectedVisible > 0 && selectedVisible < filtered.length;
  }

  function renderToolbar() {
    const toolbar = document.getElementById("docsBulkToolbar");
    const n = state.selected.size;
    toolbar.style.display = n ? "" : "none";
    if (n) {
      document.getElementById("docsSelectedCount").textContent = t("selectedCountLabel", n);
      document.getElementById("docsDeleteSelectedLabel").textContent = t("deleteSelectedBtn", n);
    }
  }

  document.getElementById("docsSearchInput").addEventListener("input", function (e) {
    state.search = e.target.value.trim().toLowerCase();
    renderRows();
  });
  document.getElementById("docsSearchForm").addEventListener("submit", function (e) { e.preventDefault(); });
  document.getElementById("docsStatusFilter").addEventListener("change", function (e) {
    state.status = e.target.value;
    renderRows();
  });
  document.getElementById("docsSelectAll").addEventListener("change", function (e) {
    const filtered = currentFiltered();
    if (e.target.checked) filtered.forEach(function (d) { state.selected.add(d.document_id); });
    else filtered.forEach(function (d) { state.selected.delete(d.document_id); });
    renderRows();
    renderToolbar();
  });
  document.getElementById("docsDeleteSelectedBtn").addEventListener("click", async function () {
    const ids = Array.from(state.selected);
    if (!ids.length) return;
    if (!window.confirm(t("confirmDeleteSelected", ids.length))) return;
    const btn = this;
    btn.disabled = true;
    let failed = 0;
    for (const id of ids) {
      try { await api.deleteDocument(id); } catch (exc) { failed++; console.error("Failed to delete document " + id + ":", exc); }
    }
    invalidateDocuments();
    if (failed) toast(String(failed) + " / " + ids.length + " failed to delete", "bad");
    else toast(t("deleteDocument") + " ✓", "good");
    try {
      const fresh = await loadDocuments(true);
      if (!isStale()) _renderDocuments(container, fresh, isStale);
    } catch (exc) {
      if (!isStale()) container.querySelector(".panel").outerHTML = errorState({ title: t("runFailedTitle"), desc: String((exc && exc.message) || exc) });
    }
  });

  renderRows();
  renderToolbar();
}

function _wireUpload(container, isStale) {
  const dropzone = document.getElementById("docDropzone");
  const input = document.getElementById("docFileInput");
  const folderInput = document.getElementById("docFolderInput");
  const folderBtn = document.getElementById("docUploadFolderBtn");
  const statusEl = document.getElementById("docUploadStatus");
  if (!dropzone || !input) return;

  dropzone.addEventListener("click", function () { input.click(); });
  dropzone.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
  ["dragenter", "dragover"].forEach(function (evt) {
    dropzone.addEventListener(evt, function (e) { e.preventDefault(); dropzone.classList.add("drag-over"); });
  });
  ["dragleave", "drop"].forEach(function (evt) {
    dropzone.addEventListener(evt, function (e) { e.preventDefault(); dropzone.classList.remove("drag-over"); });
  });
  // A drop can be plain files, or a whole folder (and folders within it).
  // Chromium/WebKit browsers expose each dropped item's real filesystem
  // entry via webkitGetAsEntry() -- when present, walk it recursively so
  // dropping a folder collects every real PDF inside it, the same as
  // picking one with the folder button below. A browser without that API
  // (per-item fallback inside _filesFromDataTransferItems) just gets
  // whatever plain files were dropped, same as before this addition.
  dropzone.addEventListener("drop", function (e) {
    if (e.dataTransfer.items && e.dataTransfer.items.length) {
      _filesFromDataTransferItems(e.dataTransfer.items).then(function (files) {
        if (files.length) _doUpload(files);
      });
    } else {
      const files = e.dataTransfer.files;
      if (files && files.length) _doUpload(Array.prototype.slice.call(files));
    }
  });
  input.addEventListener("change", function () {
    const files = input.files;
    if (files && files.length) _doUpload(Array.prototype.slice.call(files));
    input.value = "";
  });

  if (folderBtn && folderInput) {
    folderBtn.addEventListener("click", function () { folderInput.click(); });
    folderInput.addEventListener("change", function () {
      const files = folderInput.files;
      if (files && files.length) _doUpload(Array.prototype.slice.call(files));
      folderInput.value = "";
    });
  }

  function _isPdf(file) {
    return file.type === "application/pdf" || /\.pdf$/i.test(file.name || "");
  }

  // Recursively walks whatever was dropped (real File objects and/or real
  // FileSystemEntry objects for folders) into a flat list of real Files --
  // never invents entries, just collects what the OS/browser actually
  // reports. readEntries() can return entries in batches, so each
  // directory is read until it reports an empty batch.
  function _filesFromDataTransferItems(items) {
    const top = [];
    for (let i = 0; i < items.length; i++) {
      const it = items[i];
      const entry = it.webkitGetAsEntry && it.webkitGetAsEntry();
      if (entry) top.push(entry);
      else {
        const f = it.getAsFile && it.getAsFile();
        if (f) top.push(f);
      }
    }

    function readAllEntries(dirReader) {
      return new Promise(function (resolve) {
        const all = [];
        (function readBatch() {
          dirReader.readEntries(function (batch) {
            if (!batch.length) { resolve(all); return; }
            all.push.apply(all, batch);
            readBatch();
          }, function () { resolve(all); });
        })();
      });
    }

    function walk(entry) {
      if (entry instanceof File) return Promise.resolve([entry]);
      if (entry.isFile) {
        return new Promise(function (resolve) { entry.file(resolve, function () { resolve(null); }); })
          .then(function (f) { return f ? [f] : []; });
      }
      if (entry.isDirectory) {
        return readAllEntries(entry.createReader()).then(function (children) {
          return Promise.all(children.map(walk)).then(function (lists) {
            return lists.reduce(function (a, b) { return a.concat(b); }, []);
          });
        });
      }
      return Promise.resolve([]);
    }

    return Promise.all(top.map(walk)).then(function (lists) {
      return lists.reduce(function (a, b) { return a.concat(b); }, []);
    });
  }

  // Uploads every real selected/dropped file one at a time -- there is no
  // batch endpoint (POST /documents/upload takes exactly one file), and
  // going one at a time avoids hammering the same LLM credential with
  // concurrent document-analysis calls. Each file gets its own live status
  // row so a failure on file 2 of 5 is visible without losing the other
  // four's real results.
  async function _doUpload(files) {
    const pdfFiles = files.filter(_isPdf);
    const skipped = files.length - pdfFiles.length;
    if (skipped > 0) toast(t("skippedNonPdfToast", skipped), "bad");
    if (!pdfFiles.length) return;

    const rows = pdfFiles.map(function (f) { return { file: f, status: "queued" }; });

    function renderQueue() {
      statusEl.innerHTML = '<div class="upload-queue" style="margin-top:14px">' + rows.map(function (r, i) {
        const label = r.status === "done" ? t("docStatusAnalyzed")
          : r.status === "error" ? t("docStatusFailed")
          : r.status === "uploading" ? t("uploadingLabel")
          : t("queuedLabel");
        const tone = r.status === "done" ? "tone-good" : r.status === "error" ? "tone-bad" : "tone-neutral";
        return '<div class="upload-queue-row" data-row="' + i + '">' +
          '<span class="upload-queue-name">' + escapeHtml(r.file.webkitRelativePath || r.file.name) + '</span>' +
          '<span class="tag ' + tone + '">' + escapeHtml(label) + '</span>' +
          (r.status === "error" && r.errorMessage ? '<div class="hint-text" style="width:100%">' + escapeHtml(r.errorMessage) + '</div>' : '') +
          '</div>';
      }).join("") + '</div>';
    }

    renderQueue();

    let successCount = 0;
    for (let i = 0; i < rows.length; i++) {
      rows[i].status = "uploading";
      renderQueue();
      try {
        await api.uploadDocument(rows[i].file);
        rows[i].status = "done";
        successCount++;
      } catch (exc) {
        rows[i].status = "error";
        rows[i].errorMessage = String((exc && exc.message) || exc);
      }
      renderQueue();
    }

    invalidateDocuments();
    toast(t("uploadSummary", successCount, rows.length), successCount === rows.length ? "good" : "bad");
    try {
      const fresh = await loadDocuments(true);
      if (!isStale()) _renderDocuments(container, fresh, isStale);
    } catch (exc) {
      if (!isStale()) container.querySelector(".panel").outerHTML = errorState({ title: t("runFailedTitle"), desc: String((exc && exc.message) || exc), detail: exc && exc.stack });
    }
  }
}
