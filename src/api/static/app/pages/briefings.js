// pages/briefings.js — Daily Briefings: a browsing list of recent real
// runs, and the full report reader restructured into named sections. Every
// section is a real reorganization of one run's real GET /runs/{id}
// payload (events grouped by their real `agent` field, or real report
// fields) -- see the comment above _SECTION_AGENTS for exactly which real
// agent output maps to which named section. No section invents narrative
// text the backend didn't produce.
"use strict";

Pages.briefingsList = {
  async render(container, params, isStale) {
    container.innerHTML = '<div class="page-head"><div><div class="page-eyebrow">' + escapeHtml(t("briefingsEyebrow")) + '</div>' +
      '<div class="page-title">' + escapeHtml(t("briefingsTitle")) + '</div><div class="page-desc">' + escapeHtml(t("briefingsDesc")) + '</div></div></div>' +
      skeletonCards(4);
    let runs = [];
    try { runs = await loadRunsList(30); } catch (exc) {
      if (!isStale()) container.innerHTML = errorState({ title: t("runFailedTitle"), desc: String((exc && exc.message) || exc), detail: exc && exc.stack });
      return;
    }
    if (isStale()) return;

    let html = '<div class="page-head"><div><div class="page-eyebrow">' + escapeHtml(t("briefingsEyebrow")) + '</div>' +
      '<div class="page-title">' + escapeHtml(t("briefingsTitle")) + '</div><div class="page-desc">' + escapeHtml(t("briefingsDesc")) + '</div></div>' +
      '<a class="btn btn-secondary" href="#/reports">' + escapeHtml(t("reportsTitle")) + '</a></div>';

    if (!runs.length) {
      html += emptyState({ icon: "briefings", title: t("noReportsTitle"), desc: t("noReportsDesc") });
      container.innerHTML = html;
      return;
    }

    html += '<div class="stack">';
    runs.slice(0, 14).forEach(function (r) {
      const statusTag = r.failed_steps && r.failed_steps.length
        ? '<span class="tag tone-warn">' + escapeHtml(t("statusPartial", r.failed_steps.length)) + '</span>'
        : r.no_significant_events ? '<span class="tag tone-neutral">' + escapeHtml(t("statusNoSignificant")) + '</span>'
        : '<span class="tag tone-good">' + escapeHtml(t("statusCompleted")) + '</span>';
      html += '<div class="panel panel-pad">' +
        '<div class="intel-top">' + statusTag + '<span class="tag">' + escapeHtml(fmtDate(r.generated_at, localeTag())) + '</span>' +
        '<span class="tag">' + r.event_count + ' ' + escapeHtml(t("kpiEvents")).toLowerCase() + '</span></div>' +
        '<div class="intel-headline" style="margin-top:8px;font-size:16px"><a href="#/briefings/' + encodeURIComponent(r.run_id) + '">' + escapeHtml(r.headline || t("dailyBriefingTitle")) + '</a></div>' +
        '<div style="margin-top:10px"><a class="btn btn-primary btn-sm" href="#/briefings/' + encodeURIComponent(r.run_id) + '">' + escapeHtml(t("openBriefing")) + '</a></div>' +
        '</div>';
    });
    html += "</div>";
    container.innerHTML = html;
  },
};

// Which real monitoring agent(s) feed each named section -- grounded in
// AGENT_ROSTER (data.js), copied directly from src/agents/monitoring_agent.py.
const _SECTION_AGENTS = {
  sectionGlobalPolitical: ["Global Political News Agent"],
  sectionEconomic: ["Global Economic & Markets Agent", "Expert Commentary Agent"],
  sectionMenaSection: ["Regional MENA & Morocco Agent"],
  sectionRealEstateImplications: ["Real Estate Sector Agent", "YouTube Video Monitoring Agent"],
};

Pages.briefingDetail = {
  async render(container, params, isStale) {
    container.innerHTML = '<div class="panel panel-pad">' + skeletonLines(10, ["w-full"]) + "</div>";
    let run;
    try {
      run = await loadRun(params.id);
      const lang = getLang();
      if (lang !== "en") {
        if (!isStale()) container.innerHTML = '<div class="panel panel-pad">' + skeletonLines(3, ["w-40"]) +
          '<div class="hint-text" style="margin-top:10px">' + escapeHtml(t("translatingLabel")) + '</div></div>';
        run = await loadTranslatedRun(params.id, lang);
      }
    } catch (exc) {
      if (!isStale()) container.innerHTML = errorState({
        title: t("runFailedTitle"), desc: String((exc && exc.message) || exc), detail: exc && exc.stack,
        actionHtml: '<a class="btn btn-secondary btn-sm" href="#/briefings">' + escapeHtml(t("backToBriefings")) + '</a>',
      });
      return;
    }
    if (isStale()) return;
    setChatContext(run.run_id, fmtDate(run.generated_at, localeTag()));

    const report = run.report;
    const events = run.events || [];
    const impactList = (report && report.impact_analysis) || [];
    const byId = {}; events.forEach(function (e) { byId[e.id] = e; });
    const sourceCount = new Set(events.map(function (e) { return e.source_name || e.source_url; })).size;

    const head = '<div class="page-head"><div>' +
      '<a class="section-link" href="#/briefings">' + escapeHtml(t("backToBriefings")) + '</a>' +
      '<div class="page-title" style="margin-top:6px">' + escapeHtml(report && report.headline ? report.headline : t("dailyBriefingTitle")) + '</div>' +
      '<div class="briefing-meta-row"><span>' + escapeHtml(t("generatedAtLabel")) + ': ' + escapeHtml(fmtDateTime(run.generated_at, localeTag())) + '</span>' +
      '<span>' + escapeHtml(t("eventsAnalyzedLabel")) + ': ' + events.length + '</span>' +
      '<span>' + escapeHtml(t("sourcesLabel")) + ': ' + sourceCount + '</span></div></div>' +
      '<a class="btn btn-secondary" href="' + api.runPdfUrl(run.run_id) + '" target="_blank">' + icon("download") + escapeHtml(t("downloadPdf")) + '</a>' +
      '</div>';

    if (!report || report.no_significant_events) {
      container.innerHTML = head + emptyState({ icon: "briefings", title: t("noEventsTitle"), desc: t("noEventsDesc") });
      return;
    }

    let html = "";
    // Executive Summary
    html += _section("sectionExecSummary",
      '<div class="briefing-body"><p>' + escapeHtml(report.headline) + '</p><p class="hint-text">' + escapeHtml(t("priorityExplanation")) + '</p></div>');

    // Global Political / Economic & Markets / MENA / Real Estate Implications
    ["sectionGlobalPolitical", "sectionEconomic", "sectionMenaSection", "sectionRealEstateImplications"].forEach(function (key) {
      const agents = _SECTION_AGENTS[key];
      const inSection = events.filter(function (e) { return agents.indexOf(e.agent) !== -1; });
      let body = "";
      if (!inSection.length) {
        body = '<div class="hint-text">' + escapeHtml(t("noEventsInSection")) + '</div>';
      } else {
        agents.forEach(function (agentName) {
          const agentEvents = inSection.filter(function (e) { return e.agent === agentName; });
          if (!agentEvents.length) return;
          body += '<div class="briefing-agent-block"><div class="briefing-agent-name">' + escapeHtml(agentDisplayName(agentName)) + '</div>';
          agentEvents.forEach(function (e) { body += intelItemHtml(e, impactForEvent(e.id, impactList)); });
          body += "</div>";
        });
      }
      if (key === "sectionRealEstateImplications" && impactList.length) {
        body += '<div style="margin-top:14px">' + impactList.map(_impactCardHtml).join("") + "</div>";
      }
      html += _section(key, body);
    });

    // Risks / Opportunities
    const ro = computeRisksAndOpportunities({ report: report, events: events });
    html += _section("sectionRisksSection", ro.risks.length
      ? '<div class="ro-grid" style="grid-template-columns:1fr">' + ro.risks.map(function (it) { return _roRow("risk", it); }).join("") + "</div>"
      : '<div class="hint-text">' + escapeHtml(t("noRisksToday")) + "</div>");
    html += _section("sectionOpportunitiesSection", ro.opportunities.length
      ? '<div class="ro-grid" style="grid-template-columns:1fr">' + ro.opportunities.map(function (it) { return _roRow("opportunity", it); }).join("") + "</div>"
      : '<div class="hint-text">' + escapeHtml(t("noOpportunitiesToday")) + "</div>");

    // What to Watch Tomorrow (real recommended_actions)
    html += _section("sectionWatch", report.recommended_actions && report.recommended_actions.length
      ? '<ul style="margin:0;padding-inline-start:20px;display:flex;flex-direction:column;gap:8px">' +
        report.recommended_actions.map(function (a) { return '<li class="briefing-body">' + escapeHtml(a) + "</li>"; }).join("") + "</ul>"
      : '<div class="hint-text">—</div>');

    // AI Conclusion (real debate_highlights + limitations)
    let conclusionBody = "";
    if (report.debate_highlights && report.debate_highlights.length) {
      conclusionBody += '<ul style="margin:0 0 10px;padding-inline-start:20px;display:flex;flex-direction:column;gap:6px">' +
        report.debate_highlights.map(function (d) { return '<li class="briefing-body">' + escapeHtml(d) + "</li>"; }).join("") + "</ul>";
    }
    if (report.limitations && report.limitations.length) {
      conclusionBody += '<div class="drawer-section-title" style="margin-top:8px">' + escapeHtml(t("technicalDetails")) + '</div>' +
        '<ul style="margin:0;padding-inline-start:20px;display:flex;flex-direction:column;gap:5px">' +
        report.limitations.map(function (l) { return '<li class="hint-text">' + escapeHtml(l) + "</li>"; }).join("") + "</ul>";
    }
    html += _section("sectionAiConclusion", conclusionBody || '<div class="hint-text">—</div>');

    container.innerHTML = head + '<div class="panel panel-pad" style="margin-top:18px">' + html + "</div>";
  },
};

function _section(titleKey, bodyHtml) {
  return '<div class="briefing-section"><div class="briefing-section-title">' + escapeHtml(t(titleKey)) + '</div>' + bodyHtml + "</div>";
}

function _impactCardHtml(ia) {
  return '<div class="impact-card"><div class="impact-card-head">' +
    '<b>' + escapeHtml(ia.sector_or_market_affected) + '</b>' +
    '<span class="tag tone-' + directionTone(ia.direction) + '">' + escapeHtml(sentimentLabel(ia.direction)) + " · " + escapeHtml(levelLabel(ia.magnitude)) + '</span></div>' +
    (ia.contested ? '<span class="tag tone-warn" style="margin-bottom:6px">' + escapeHtml(t("contestedLabel")) + '</span><br>' : "") +
    '<div class="briefing-body">' + escapeHtml(ia.rationale || "") + '</div>' +
    '<div class="hint-text" style="margin-top:6px">' + escapeHtml(ia.recommended_action) + " · " + Math.round((ia.confidence || 0) * 100) + "% · " + escapeHtml(timeHorizonLabel(ia.time_horizon)) + '</div></div>';
}

function _roRow(kind, item) {
  return '<div class="ro-item ' + kind + '"><div class="ro-marker"></div><div class="ro-text">' +
    '<div class="ro-title">' + escapeHtml(item.event.headline) + '</div>' +
    '<div class="ro-explain">' + escapeHtml(item.impact.recommended_action) + '</div>' +
    '<div class="ro-meta">' + escapeHtml(item.impact.sector_or_market_affected) + ' · ' + escapeHtml(levelLabel(item.impact.magnitude)) + '</div></div></div>';
}
