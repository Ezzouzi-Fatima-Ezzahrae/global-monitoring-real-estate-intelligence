// pages/reports.js — full report history: searchable, filterable, and the
// primary way to reach any past briefing (replaces the old run-picker
// dropdown). Built entirely from GET /runs summaries (run_id, generated_at,
// run_date, headline, event_count, no_significant_events, failed_steps) --
// no field is shown here that summary doesn't actually provide, so nothing
// is guessed or padded in.
"use strict";

Pages.reports = {
  async render(container, params, isStale) {
    container.innerHTML = '<div class="page-head"><div><div class="page-eyebrow">' + escapeHtml(t("reportsEyebrow")) + '</div>' +
      '<div class="page-title">' + escapeHtml(t("reportsTitle")) + '</div><div class="page-desc">' + escapeHtml(t("reportsDesc")) + '</div></div></div>' +
      '<div class="panel panel-pad">' + skeletonLines(6, ["w-full"]) + "</div>";

    let runs = [];
    try {
      runs = await loadRunsList(200);
    } catch (exc) {
      if (!isStale()) container.querySelector(".panel").outerHTML = errorState({ title: t("runFailedTitle"), desc: String((exc && exc.message) || exc), detail: exc && exc.stack });
      return;
    }
    if (isStale()) return;

    if (!runs.length) {
      container.innerHTML = '<div class="page-head"><div><div class="page-eyebrow">' + escapeHtml(t("reportsEyebrow")) + '</div>' +
        '<div class="page-title">' + escapeHtml(t("reportsTitle")) + '</div></div></div>' +
        emptyState({ icon: "reports", title: t("noReportsTitle"), desc: t("noReportsDesc") });
      return;
    }

    let html = '<div class="page-head"><div><div class="page-eyebrow">' + escapeHtml(t("reportsEyebrow")) + '</div>' +
      '<div class="page-title">' + escapeHtml(t("reportsTitle")) + '</div><div class="page-desc">' + escapeHtml(t("reportsDesc")) + '</div></div></div>' +
      '<div class="filter-row">' +
      '<input type="text" class="filter-select" id="reportsSearch" style="min-width:220px" placeholder="' + escapeHtml(t("searchReportsPlaceholder")) + '">' +
      '<select class="filter-select" id="reportsStatusFilter"><option value="">' + escapeHtml(t("filterAllStatus")) + '</option>' +
      '<option value="completed">' + escapeHtml(t("statusCompleted")) + '</option>' +
      '<option value="none">' + escapeHtml(t("statusNoSignificant")) + '</option>' +
      '<option value="partial">' + escapeHtml(t("statusPartialLabel")) + '</option></select>' +
      '</div>' +
      '<div class="panel"><div class="table-wrap"><table class="data-table"><thead><tr>' +
      '<th>' + escapeHtml(t("colDate")) + '</th><th>' + escapeHtml(t("reportsTitle")) + '</th>' +
      '<th>' + escapeHtml(t("colEvents")) + '</th><th>' + escapeHtml(t("colStatus")) + '</th>' +
      '<th>' + escapeHtml(t("colActions")) + '</th></tr></thead><tbody id="reportsBody"></tbody></table></div></div>';
    container.innerHTML = html;

    function statusOf(r) {
      if (r.failed_steps && r.failed_steps.length) return "partial";
      if (r.no_significant_events) return "none";
      return "completed";
    }
    function statusChip(r) {
      const s = statusOf(r);
      if (s === "partial") return '<span class="tag tone-warn">' + escapeHtml(t("statusPartial", r.failed_steps.length)) + '</span>';
      if (s === "none") return '<span class="tag tone-neutral">' + escapeHtml(t("statusNoSignificant")) + '</span>';
      return '<span class="tag tone-good">' + escapeHtml(t("statusCompleted")) + '</span>';
    }

    function renderRows() {
      const q = document.getElementById("reportsSearch").value.trim().toLowerCase();
      const statusFilter = document.getElementById("reportsStatusFilter").value;
      const filtered = runs.filter(function (r) {
        if (statusFilter && statusOf(r) !== statusFilter) return false;
        if (!q) return true;
        const hay = (fmtDate(r.generated_at, localeTag()) + " " + (r.headline || "") + " " + r.run_date).toLowerCase();
        return hay.indexOf(q) !== -1;
      });
      const body = document.getElementById("reportsBody");
      if (!filtered.length) {
        body.innerHTML = '<tr><td colspan="5">' + emptyState({ icon: "inbox", title: t("noReportsTitle"), desc: t("noReportsDesc") }) + "</td></tr>";
        return;
      }
      body.innerHTML = filtered.map(function (r) {
        return '<tr>' +
          '<td data-label="' + escapeHtml(t("colDate")) + '" class="num">' + escapeHtml(fmtDateTime(r.generated_at, localeTag())) + '</td>' +
          '<td data-label="' + escapeHtml(t("reportsTitle")) + '"><a href="#/briefings/' + encodeURIComponent(r.run_id) + '">' + escapeHtml(r.headline || t("dailyBriefingTitle")) + '</a></td>' +
          '<td data-label="' + escapeHtml(t("colEvents")) + '" class="num ltr-num">' + r.event_count + '</td>' +
          '<td data-label="' + escapeHtml(t("colStatus")) + '">' + statusChip(r) + '</td>' +
          '<td data-label="' + escapeHtml(t("colActions")) + '"><a class="btn btn-ghost btn-sm" href="#/briefings/' + encodeURIComponent(r.run_id) + '">' + escapeHtml(t("openBriefing")) + '</a> ' +
          '<a class="btn btn-ghost btn-sm" href="' + api.runPdfUrl(r.run_id) + '" target="_blank">' + icon("download") + '</a></td>' +
          '</tr>';
      }).join("");
    }
    document.getElementById("reportsSearch").addEventListener("input", renderRows);
    document.getElementById("reportsStatusFilter").addEventListener("change", renderRows);
    renderRows();
  },
};
