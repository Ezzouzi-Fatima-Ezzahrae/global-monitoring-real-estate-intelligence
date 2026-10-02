// pages/market.js — Market Intelligence, Real Estate, and MENA & Morocco:
// three category pages, all built from the same real event/impact data as
// every other page, filtered by which real monitoring agent produced each
// event (src/agents/monitoring_agent.py). No fabricated sub-categories
// (investment/development/tourism/infrastructure) are invented here --
// that would require a classification the backend doesn't do -- instead
// each page shows a real Overview count, the real filtered signal feed,
// and the real Judge impact assessments that touch this category's events.
"use strict";

function _renderCategoryPage(container, isStale, opts) {
  return (async function () {
    container.innerHTML = '<div class="page-head"><div><div class="page-eyebrow">' + escapeHtml(t(opts.eyebrowKey)) + '</div>' +
      '<div class="page-title">' + escapeHtml(t(opts.titleKey)) + '</div><div class="page-desc">' + escapeHtml(t(opts.descKey)) + '</div></div></div>' +
      skeletonKpis() + '<div class="panel panel-pad" style="margin-top:18px">' + skeletonLines(6, ["w-full"]) + "</div>";

    let latestRun = null;
    try {
      const runsList = await loadRunsList(30);
      if (runsList.length) latestRun = await loadTranslatedRun(runsList[0].run_id, getLang());
    } catch (exc) {
      if (!isStale()) container.innerHTML = errorState({ title: t("runFailedTitle"), desc: String((exc && exc.message) || exc), detail: exc && exc.stack });
      return;
    }
    if (isStale()) return;

    const events = latestRun ? (latestRun.events || []).filter(function (e) { return opts.agents.indexOf(e.agent) !== -1; }) : [];
    const impactList = latestRun && latestRun.report ? (latestRun.report.impact_analysis || []) : [];
    const eventIds = new Set(events.map(function (e) { return e.id; }));
    const relatedImpact = impactList.filter(function (ia) { return eventIds.has(ia.event_id); });
    const highImpact = relatedImpact.filter(function (ia) { return ia.magnitude === "high"; }).length;

    let html = '<div class="page-head"><div><div class="page-eyebrow">' + escapeHtml(t(opts.eyebrowKey)) + '</div>' +
      '<div class="page-title">' + escapeHtml(t(opts.titleKey)) + '</div><div class="page-desc">' + escapeHtml(t(opts.descKey)) + '</div></div></div>';

    html += '<div class="section-head"><div class="section-title">' + escapeHtml(t("sectionOverviewLabel")) + '</div></div>' +
      '<div class="kpi-grid" style="grid-template-columns:repeat(3,1fr)">' +
      '<div class="kpi-card"><div class="kpi-label">' + escapeHtml(t("categoryEventsLabel")) + '</div><div class="kpi-value ltr-num">' + events.length + '</div></div>' +
      '<div class="kpi-card" data-tone="' + (highImpact > 0 ? "warn" : "") + '"><div class="kpi-label">' + escapeHtml(t("categoryHighImpactLabel")) + '</div><div class="kpi-value ltr-num">' + highImpact + '</div></div>' +
      '<div class="kpi-card"><div class="kpi-label">' + escapeHtml(t("categoryAgentsLabel")) + '</div><div class="kpi-value" style="font-size:13px;line-height:1.5">' + opts.agents.map(function (a) { return escapeHtml(agentDisplayName(a)); }).join("<br>") + '</div></div>' +
      '</div>';

    html += '<div class="panel panel-pad" style="margin-top:18px"><div class="section-head"><div class="section-title">' + escapeHtml(t("sectionSignals")) + '</div>' +
      '<span class="section-count">' + events.length + '</span></div>';
    html += events.length
      ? events.map(function (e) { return intelItemHtml(e, impactForEvent(e.id, impactList)); }).join("")
      : '<div class="hint-text">' + escapeHtml(t("noSignalsYet")) + "</div>";
    html += "</div>";

    if (relatedImpact.length) {
      html += '<div class="panel panel-pad" style="margin-top:18px"><div class="section-head"><div class="section-title">' + escapeHtml(t("sectionAiInsights")) + '</div></div>';
      relatedImpact.forEach(function (ia) {
        html += '<div class="impact-card"><div class="impact-card-head"><b>' + escapeHtml(ia.sector_or_market_affected) + '</b>' +
          '<span class="tag tone-' + directionTone(ia.direction) + '">' + escapeHtml(sentimentLabel(ia.direction)) + ' · ' + escapeHtml(levelLabel(ia.magnitude)) + '</span></div>' +
          '<div class="briefing-body">' + escapeHtml(ia.rationale || "") + '</div>' +
          '<div class="hint-text" style="margin-top:6px">' + escapeHtml(ia.recommended_action) + '</div></div>';
      });
      html += "</div>";
    }

    container.innerHTML = html;
  })();
}

Pages.market = {
  render(container, params, isStale) {
    return _renderCategoryPage(container, isStale, {
      eyebrowKey: "marketEyebrow", titleKey: "marketTitle", descKey: "marketDesc",
      agents: ["Global Political News Agent", "Global Economic & Markets Agent", "Expert Commentary Agent"],
    });
  },
};
Pages.realEstate = {
  render(container, params, isStale) {
    return _renderCategoryPage(container, isStale, {
      eyebrowKey: "realEstateEyebrow", titleKey: "realEstateTitle", descKey: "realEstateDesc",
      agents: ["Real Estate Sector Agent", "YouTube Video Monitoring Agent"],
    });
  },
};
Pages.mena = {
  render(container, params, isStale) {
    return _renderCategoryPage(container, isStale, {
      eyebrowKey: "menaEyebrow", titleKey: "menaTitle", descKey: "menaDesc",
      agents: ["Regional MENA & Morocco Agent"],
    });
  },
};
