// pages/feed.js — Intelligence Feed: every real event across recent
// briefings, most recent first, filterable by real agent and by the real
// relevance_to_real_estate field Judge/agents already assign.
"use strict";

Pages.feed = {
  _allItems: null,

  async render(container, params, isStale) {
    container.innerHTML = '<div class="page-head"><div><div class="page-eyebrow">' + escapeHtml(t("feedEyebrow")) + '</div>' +
      '<div class="page-title">' + escapeHtml(t("feedTitle")) + '</div><div class="page-desc">' + escapeHtml(t("feedDesc")) + '</div></div></div>' +
      '<div class="panel panel-pad">' + skeletonLines(8, ["w-full"]) + "</div>";

    let runs = [];
    try {
      runs = await loadRecentRuns(10);
      const lang = getLang();
      if (lang !== "en") runs = await Promise.all(runs.map(function (r) { return loadTranslatedRun(r.run_id, lang); }));
    } catch (exc) {
      if (!isStale()) container.querySelector(".panel").outerHTML = errorState({ title: t("runFailedTitle"), desc: String((exc && exc.message) || exc), detail: exc && exc.stack });
      return;
    }
    if (isStale()) return;

    const items = [];
    runs.forEach(function (run) {
      const impactList = (run.report && run.report.impact_analysis) || [];
      (run.events || []).forEach(function (e) {
        items.push({ event: e, impact: impactForEvent(e.id, impactList), runId: run.run_id, runDate: run.generated_at });
      });
    });
    items.sort(function (a, b) {
      const ta = new Date(a.event.published_at || a.event.collected_at).getTime();
      const tb = new Date(b.event.published_at || b.event.collected_at).getTime();
      return tb - ta;
    });
    Pages.feed._allItems = items;

    const agentSet = Array.from(new Set(items.map(function (i) { return i.event.agent; }))).sort();

    let html = '<div class="page-head"><div><div class="page-eyebrow">' + escapeHtml(t("feedEyebrow")) + '</div>' +
      '<div class="page-title">' + escapeHtml(t("feedTitle")) + '</div><div class="page-desc">' + escapeHtml(t("feedDesc")) + '</div></div></div>';
    html += '<div class="filter-row">' +
      '<select class="filter-select" id="feedAgentFilter"><option value="">' + escapeHtml(t("filterAllAgents")) + '</option>' +
      agentSet.map(function (a) { return '<option value="' + escapeHtml(a) + '">' + escapeHtml(agentDisplayName(a)) + '</option>'; }).join("") + '</select>' +
      '<select class="filter-select" id="feedImpactFilter"><option value="">' + escapeHtml(t("filterAllImpact")) + '</option>' +
      '<option value="high">' + escapeHtml(t("impactHigh")) + '</option>' +
      '<option value="medium">' + escapeHtml(t("impactMedium")) + '</option>' +
      '<option value="low">' + escapeHtml(t("impactLow")) + '</option></select>' +
      '<span class="section-count" id="feedCount"></span>' +
      '</div><div class="panel panel-pad" id="feedList"></div>';
    container.innerHTML = html;

    function applyFilters() {
      const agentVal = document.getElementById("feedAgentFilter").value;
      const impactVal = document.getElementById("feedImpactFilter").value;
      const filtered = items.filter(function (i) {
        if (agentVal && i.event.agent !== agentVal) return false;
        if (impactVal && i.event.relevance_to_real_estate !== impactVal) return false;
        return true;
      });
      const listEl = document.getElementById("feedList");
      document.getElementById("feedCount").textContent = filtered.length;
      listEl.innerHTML = filtered.length
        ? filtered.map(function (i) { return intelItemHtml(i.event, i.impact); }).join("")
        : emptyState({ icon: "inbox", title: t("noEventsTitle"), desc: t("noEventsDesc") });
    }

    document.getElementById("feedAgentFilter").addEventListener("change", applyFilters);
    document.getElementById("feedImpactFilter").addEventListener("change", applyFilters);
    applyFilters();
  },
};
