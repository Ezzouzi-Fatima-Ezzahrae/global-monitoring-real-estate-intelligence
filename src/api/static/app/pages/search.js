// pages/search.js — global search across real reports, events, sources
// and documents. Client-side substring match over already-real data
// (recent runs + documents); nothing is sent to any search index that
// doesn't exist, and results are only ever real events/reports/documents.
"use strict";

Pages.search = {
  async render(container, params, isStale) {
    const q = (params.query && params.query.q) || "";
    container.innerHTML = '<div class="page-head"><div><div class="page-title">' + escapeHtml(q ? t("searchResultsTitle", q) : t("searchTitle")) + '</div></div></div>' +
      '<div class="panel panel-pad">' + skeletonLines(6, ["w-full"]) + "</div>";

    if (!q.trim()) {
      container.innerHTML = '<div class="page-head"><div><div class="page-title">' + escapeHtml(t("searchTitle")) + '</div><div class="page-desc">' + escapeHtml(t("searchDesc")) + '</div></div></div>' +
        emptyState({ icon: "search", title: t("searchNoResults"), desc: "" });
      return;
    }

    let runs = [], docs = [];
    try {
      runs = await loadRecentRuns(15);
      docs = await loadDocuments();
    } catch (exc) {
      if (!isStale()) container.innerHTML = errorState({ title: t("runFailedTitle"), desc: String((exc && exc.message) || exc), detail: exc && exc.stack });
      return;
    }
    if (isStale()) return;

    const needle = q.trim().toLowerCase();
    const eventHits = [];
    runs.forEach(function (run) {
      const impactList = (run.report && run.report.impact_analysis) || [];
      (run.events || []).forEach(function (e) {
        const hay = (e.headline + " " + e.summary + " " + (e.source_name || "") + " " + e.agent).toLowerCase();
        if (hay.indexOf(needle) !== -1) eventHits.push({ event: e, impact: impactForEvent(e.id, impactList) });
      });
    });
    const reportHits = runs.filter(function (r) {
      const hay = ((r.report && r.report.headline) || "" + " " + r.run_date).toLowerCase();
      return hay.indexOf(needle) !== -1;
    });
    const docHits = docs.filter(function (d) { return (d.filename || "").toLowerCase().indexOf(needle) !== -1; });

    let html = '<div class="page-head"><div><div class="page-title">' + escapeHtml(t("searchResultsTitle", q)) + '</div></div></div>';
    const totalHits = eventHits.length + reportHits.length + docHits.length;
    if (!totalHits) {
      html += emptyState({ icon: "search", title: t("searchNoResults"), desc: "" });
      container.innerHTML = html;
      return;
    }

    if (eventHits.length) {
      html += '<div class="panel panel-pad" style="margin-bottom:18px"><div class="section-head"><div class="section-title">' + escapeHtml(t("searchEvents")) + '</div><span class="section-count">' + eventHits.length + '</span></div>' +
        eventHits.map(function (h) { return intelItemHtml(h.event, h.impact); }).join("") + "</div>";
    }
    if (reportHits.length) {
      html += '<div class="panel panel-pad" style="margin-bottom:18px"><div class="section-head"><div class="section-title">' + escapeHtml(t("searchReportsGroup")) + '</div><span class="section-count">' + reportHits.length + '</span></div>';
      reportHits.forEach(function (r) {
        html += '<div class="intel-item"><div class="intel-headline"><a href="#/briefings/' + encodeURIComponent(r.run_id) + '">' + escapeHtml((r.report && r.report.headline) || t("dailyBriefingTitle")) + '</a></div>' +
          '<div class="intel-meta"><span>' + escapeHtml(fmtDate(r.generated_at, localeTag())) + '</span></div></div>';
      });
      html += "</div>";
    }
    if (docHits.length) {
      html += '<div class="panel panel-pad"><div class="section-head"><div class="section-title">' + escapeHtml(t("searchDocumentsGroup")) + '</div><span class="section-count">' + docHits.length + '</span></div>';
      docHits.forEach(function (d) {
        html += '<div class="intel-item"><div class="intel-headline">' + escapeHtml(d.filename) + '</div>' +
          '<div class="intel-meta"><span>' + escapeHtml(fmtDate(d.uploaded_at, localeTag())) + '</span><a href="#/documents">' + escapeHtml(t("navDocuments")) + '</a></div></div>';
      });
      html += "</div>";
    }
    container.innerHTML = html;
  },
};
