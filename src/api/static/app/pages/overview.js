// pages/overview.js — Executive Overview, the default landing page.
// Every number and line of text here comes from a real GET /runs /
// GET /runs/{id} response via data.js's loaders/derivations; nothing is
// invented. When no run exists yet, the page shows a real empty state
// with the "Generate today's briefing" action, not sample data.
"use strict";

Pages.overview = {
  async render(container, params, isStale) {
    container.innerHTML = '<div class="overview-hero"><div class="skel skel-line w-40" style="height:24px"></div></div>' + skeletonKpis() +
      '<div class="stack" style="margin-top:22px">' + skeletonCards(3) + "</div>";

    let health = null, runsList = [], latestRun = null, previousRun = null;
    try {
      health = await loadHealth();
      runsList = await loadRunsList(30);
      if (runsList.length) {
        latestRun = await loadTranslatedRun(runsList[0].run_id, getLang());
        if (runsList.length > 1) previousRun = await loadRun(runsList[1].run_id);
      }
    } catch (exc) {
      if (!isStale()) container.innerHTML = errorState({
        title: t("runFailedTitle"), desc: String((exc && exc.message) || exc),
        detail: exc && exc.stack, actionHtml: '<button class="btn btn-secondary btn-sm" id="ovRetry">' + escapeHtml(t("retry")) + "</button>",
      });
      if (!isStale()) { const b = document.getElementById("ovRetry"); if (b) b.addEventListener("click", function () { Pages.overview.render(container, params, isStale); }); }
      return;
    }
    if (isStale()) return;
    setChatContext(latestRun ? latestRun.run_id : null, latestRun ? fmtDate(latestRun.generated_at, localeTag()) : null);
    _renderOverview(container, health, runsList, latestRun, previousRun, isStale);
  },
};

function _greetingKey() {
  const h = new Date().getHours();
  return h < 12 ? "greetingMorning" : h < 18 ? "greetingAfternoon" : "greetingEvening";
}

function _renderOverview(container, health, runsList, latestRun, previousRun, isStale) {
  const kpis = computeKpis(latestRun, runsList, previousRun);
  const today = new Date().toISOString().slice(0, 10);
  const ranToday = latestRun && latestRun.generated_at && latestRun.generated_at.slice(0, 10) === today;

  let html = '<div class="overview-hero"><div><div class="overview-greeting">' + escapeHtml(t(_greetingKey())) + ', Orchid Island</div>' +
    '<div class="overview-greeting-sub">' + escapeHtml(t("overviewDesc")) + '</div></div>' +
    '<div class="generate-bar">' +
    '<label class="generate-check"><input type="checkbox" id="ovAlsoNotify"> ' + escapeHtml(t("alsoNotify")) + '</label>' +
    '<button class="btn btn-primary" id="ovGenerateBtn">' + icon("refresh") + escapeHtml(t("generateBriefing")) + '</button>' +
    '</div></div>';

  if (!latestRun) {
    container.innerHTML = html + emptyState({
      icon: "compass", title: t("noBriefingYetTitle"), desc: t("noBriefingYetDesc"),
    });
    _wireGenerate(container, isStale);
    return;
  }

  // ---- KPI cards (all real) ----
  const trendPct = kpis.prevEventCount ? Math.round(((kpis.eventCount - kpis.prevEventCount) / Math.max(kpis.prevEventCount, 1)) * 100) : null;
  html += '<div class="kpi-grid">' +
    '<div class="kpi-card" data-tone="accent"><div class="kpi-label">' + escapeHtml(t("kpiEvents")) + '</div>' +
    '<div class="kpi-value ltr-num">' + kpis.eventCount + '</div>' +
    '<div class="kpi-foot' + (trendPct === null ? "" : trendPct >= 0 ? " up" : " down") + '">' +
    (trendPct === null ? escapeHtml(t("kpiEventsFootToday")) : escapeHtml(t("vsYesterday", trendPct))) + '</div></div>' +

    '<div class="kpi-card" data-tone="' + (kpis.highPriority > 0 ? "warn" : "good") + '"><div class="kpi-label">' + escapeHtml(t("kpiHighPriority")) + '</div>' +
    '<div class="kpi-value ltr-num">' + kpis.highPriority + '</div>' +
    '<div class="kpi-foot">' + escapeHtml(kpis.highPriority > 0 ? t("kpiHighPriorityFoot") : t("kpiHighPriorityFootNone")) + '</div></div>' +

    '<div class="kpi-card"><div class="kpi-label">' + escapeHtml(t("kpiMarkets")) + '</div>' +
    '<div class="kpi-value ltr-num">' + kpis.marketsMonitored + '</div>' +
    '<div class="kpi-foot">' + escapeHtml(t("kpiMarketsFoot")) + '</div></div>' +

    '<div class="kpi-card" data-tone="' + (ranToday ? "good" : "") + '"><div class="kpi-label">' + escapeHtml(t("kpiAiStatus")) + '</div>' +
    '<div class="kpi-value" style="font-size:19px">' + escapeHtml(ranToday ? t("kpiAiStatusComplete") : t("kpiAiStatusIdle")) + '</div>' +
    '<div class="kpi-foot">' + escapeHtml(t("kpiAiStatusFoot")) + ': ' + escapeHtml(fmtRelative(latestRun.generated_at, t)) + '</div></div>' +
    '</div>';

  const events = latestRun.events || [];
  const impactList = (latestRun.report && latestRun.report.impact_analysis) || [];
  const byId = {}; events.forEach(function (e) { byId[e.id] = e; });
  const ranked = events.slice().sort(function (a, b) { return (a.priority_rank || 999) - (b.priority_rank || 999); });

  // ---- Today's Intelligence ----
  html += '<div class="panel panel-pad" style="margin-top:22px"><div class="section-head">' +
    '<div class="section-title">' + escapeHtml(t("todaysIntelligence")) + '</div>' +
    '<a class="section-link" href="#/intelligence-feed">' + escapeHtml(t("viewAll")) + '</a></div>' +
    '<div class="hint-text" style="margin-bottom:8px">' + escapeHtml(t("todaysIntelligenceDesc")) + '</div>';
  if (!ranked.length) {
    html += emptyState({ icon: "inbox", title: t("noEventsTitle"), desc: t("noEventsDesc") });
  } else {
    ranked.slice(0, 6).forEach(function (e) { html += intelItemHtml(e, impactForEvent(e.id, impactList)); });
  }
  html += "</div>";

  // ---- What matters for Orchid Island (chain) ----
  const chainEvents = ranked.slice(0, 4);
  if (chainEvents.length) {
    html += '<div class="panel panel-pad" style="margin-top:22px"><div class="section-head">' +
      '<div class="section-title">' + escapeHtml(t("whatMattersTitle")) + '</div></div>' +
      '<div class="hint-text" style="margin-bottom:6px">' + escapeHtml(t("whatMattersDesc")) + '</div>';
    chainEvents.forEach(function (e) {
      const impact = impactForEvent(e.id, impactList);
      html += '<div class="chain">' +
        '<div class="chain-step"><div class="chain-label">' + escapeHtml(t("chainEvent")) + '</div><div class="chain-body"><b>' + escapeHtml(e.headline) + '</b><br>' + escapeHtml(e.summary) + '</div></div>';
      if (impact) {
        html += '<div class="chain-step"><div class="chain-label is-impact">' + escapeHtml(t("chainImpact")) + '</div><div class="chain-body">' +
          '<span class="tag tone-' + magnitudeTone(impact.magnitude) + '">' + escapeHtml(levelLabel(impact.magnitude)) + ' · ' + escapeHtml(sentimentLabel(impact.direction)) + '</span> ' +
          escapeHtml(impact.rationale || "") + '</div></div>' +
          '<div class="chain-step"><div class="chain-label">' + escapeHtml(t("chainImplication")) + '</div><div class="chain-body"><b>' + escapeHtml(impact.sector_or_market_affected) + '.</b> ' +
          escapeHtml(impact.recommended_action) + '</div></div>';
      } else {
        html += '<div class="chain-step"><div class="chain-label">' + escapeHtml(t("chainImplication")) + '</div><div class="chain-body hint-text">—</div></div>';
      }
      html += '<div class="chain-step"><div class="chain-label">' + escapeHtml(t("chainWatch")) + '</div><div class="chain-body">' +
        sourceBadgeHtml(e) + ' <span>' + escapeHtml(e.source_name || "") + '</span> ' + readSourceButtonHtml(e) + '</div></div>' +
        (e.hook ? hookCardHtml(e.hook) : "") +
        '</div><hr class="divider">';
    });
    html += "</div>";
  }

  // ---- Risks & Opportunities ----
  const ro = computeRisksAndOpportunities(latestRun);
  html += '<div class="two-col" style="margin-top:22px">' +
    '<div class="panel panel-pad"><div class="section-head"><div class="section-title">' + escapeHtml(t("risksToWatch")) + '</div></div>';
  html += ro.risks.length
    ? '<div class="ro-grid" style="grid-template-columns:1fr">' + ro.risks.slice(0, 5).map(_roItemHtml.bind(null, "risk")).join("") + "</div>"
    : '<div class="hint-text">' + escapeHtml(t("noRisksToday")) + "</div>";
  html += '</div><div class="panel panel-pad"><div class="section-head"><div class="section-title">' + escapeHtml(t("opportunitiesTitle")) + '</div></div>';
  html += ro.opportunities.length
    ? '<div class="ro-grid" style="grid-template-columns:1fr">' + ro.opportunities.slice(0, 5).map(_roItemHtml.bind(null, "opportunity")).join("") + "</div>"
    : '<div class="hint-text">' + escapeHtml(t("noOpportunitiesToday")) + "</div>";
  html += "</div></div>";

  // ---- Market Signals (real impact_analysis, all directions) ----
  if (impactList.length) {
    html += '<div class="panel panel-pad" style="margin-top:22px"><div class="section-head"><div class="section-title">' + escapeHtml(t("marketSignalsTitle")) + '</div></div>' +
      '<div style="display:flex;flex-wrap:wrap;gap:8px">' +
      impactList.slice(0, 12).map(function (ia) {
        return '<span class="tag tone-' + directionTone(ia.direction) + '">' + escapeHtml(ia.sector_or_market_affected) + ' · ' + escapeHtml(levelLabel(ia.magnitude)) + "</span>";
      }).join("") + "</div></div>";
  }

  // ---- Recent Briefings ----
  html += '<div class="panel panel-pad" style="margin-top:22px"><div class="section-head">' +
    '<div class="section-title">' + escapeHtml(t("recentBriefingsTitle")) + '</div>' +
    '<a class="section-link" href="#/reports">' + escapeHtml(t("viewAll")) + '</a></div>';
  runsList.slice(0, 5).forEach(function (r) {
    html += '<div class="intel-item"><div class="intel-top"><span class="tag">' + escapeHtml(fmtDate(r.generated_at, localeTag())) + '</span>' +
      (r.no_significant_events ? '<span class="tag tone-neutral">' + escapeHtml(t("statusNoSignificant")) + '</span>' : '<span class="tag tone-good">' + escapeHtml(t("statusCompleted")) + '</span>') +
      '<span class="tag">' + r.event_count + ' ' + escapeHtml(t("kpiEvents")).toLowerCase() + '</span></div>' +
      '<div class="intel-headline"><a href="#/briefings/' + encodeURIComponent(r.run_id) + '">' + escapeHtml(r.headline || t("dailyBriefingTitle")) + '</a></div></div>';
  });
  html += "</div>";

  container.innerHTML = html;
  _wireGenerate(container, isStale);
}

function _roItemHtml(kind, item) {
  return '<div class="ro-item ' + kind + '"><div class="ro-marker"></div><div class="ro-text">' +
    '<div class="ro-title">' + escapeHtml(item.event.headline) + '</div>' +
    '<div class="ro-explain">' + escapeHtml(item.impact.recommended_action) + '</div>' +
    '<div class="ro-meta">' + escapeHtml(item.impact.sector_or_market_affected) + ' · ' + escapeHtml(levelLabel(item.impact.magnitude)) + ' · ' + Math.round((item.impact.confidence || 0) * 100) + '%</div>' +
    '</div></div>';
}

function _wireGenerate(container, isStale) {
  const btn = document.getElementById("ovGenerateBtn");
  if (!btn) return;
  btn.addEventListener("click", async function () {
    const alsoNotify = document.getElementById("ovAlsoNotify");
    const wantsNotify = alsoNotify && alsoNotify.checked;
    btn.disabled = true;
    const originalLabel = btn.innerHTML;
    btn.innerHTML = icon("refresh") + escapeHtml(t("generatingBriefing"));
    const pipelineHtml = '<div class="panel panel-pad" id="ovPipelinePanel" style="margin-top:16px">' +
      '<div class="pipeline-steps">' +
      ["pipelineCollecting", "pipelineExtracting", "pipelineAnalyzing", "pipelineAssessing"].map(function (k, i, arr) {
        return '<div class="pipeline-step active"><div class="pipeline-node">' + (i + 1) + '</div><div class="pipeline-label">' + escapeHtml(t(k)) + '</div></div>' +
          (i < arr.length - 1 ? '<div class="pipeline-line"></div>' : "");
      }).join("") + "</div><div class=\"hint-text\" style=\"margin-top:10px\">" + escapeHtml(t("generatingBriefing")) + "</div></div>";
    const hero = container.querySelector(".overview-hero");
    const holder = document.createElement("div");
    holder.innerHTML = pipelineHtml;
    if (hero) hero.insertAdjacentElement("afterend", holder.firstElementChild);
    try {
      if (wantsNotify) await api.runDigestAndNotify(); else await api.runDigest();
      invalidateRuns();
      if (isStale()) return;
      toast(t("pipelineBriefing"), "good");
      Pages.overview.render(container, {}, isStale);
    } catch (exc) {
      const panel = document.getElementById("ovPipelinePanel");
      if (panel) panel.outerHTML = errorState({
        title: t("runFailedTitle"), desc: String((exc && exc.message) || exc), detail: exc && exc.stack,
      });
      btn.disabled = false;
      btn.innerHTML = originalLabel;
    }
  });
}
