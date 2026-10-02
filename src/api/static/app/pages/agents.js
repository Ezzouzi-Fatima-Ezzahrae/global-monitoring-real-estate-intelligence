// pages/agents.js — AI Agents: cards for the 6 real monitoring agents
// (src/agents/monitoring_agent.py's MONITORING_AGENTS, mirrored in
// data.js's AGENT_ROSTER) plus a detail drawer with real per-run trace.
// This is where the technical agent trace belongs -- not the homepage.
"use strict";

Pages.agents = {
  async render(container, params, isStale) {
    container.innerHTML = '<div class="page-head"><div><div class="page-eyebrow">' + escapeHtml(t("agentsEyebrow")) + '</div>' +
      '<div class="page-title">' + escapeHtml(t("agentsTitle")) + '</div><div class="page-desc">' + escapeHtml(t("agentsDesc")) + '</div></div></div>' +
      '<div class="agent-grid">' + skeletonCards(6) + "</div>";

    let latestRun = null;
    try {
      const runsList = await loadRunsList(30);
      if (runsList.length) latestRun = await loadTranslatedRun(runsList[0].run_id, getLang());
    } catch (exc) {
      if (!isStale()) container.innerHTML = errorState({ title: t("runFailedTitle"), desc: String((exc && exc.message) || exc), detail: exc && exc.stack });
      return;
    }
    if (isStale()) return;

    const stats = agentStats(latestRun);
    let html = '<div class="page-head"><div><div class="page-eyebrow">' + escapeHtml(t("agentsEyebrow")) + '</div>' +
      '<div class="page-title">' + escapeHtml(t("agentsTitle")) + '</div><div class="page-desc">' + escapeHtml(t("agentsDesc")) + '</div></div></div>' +
      '<div class="agent-grid">';
    stats.forEach(function (a, idx) {
      const statusKey = a.status === "completed" ? "s-completed" : a.status === "failed" ? "s-error" : a.status === "skipped" ? "s-idle" : "s-idle";
      const statusLabel = a.status === "completed" ? t("statusAgentCompleted") : a.status === "failed" ? t("statusError") : a.status === "skipped" ? t("statusSkipped") : t("statusIdle");
      html += '<div class="agent-card" data-agent-idx="' + idx + '">' +
        '<div class="agent-card-head"><div class="agent-card-name">' + escapeHtml(agentDisplayName(a.key)) + '</div>' +
        '<span class="status-chip ' + statusKey + '"><span class="dot"></span>' + escapeHtml(statusLabel) + '</span></div>' +
        '<div class="agent-card-purpose">' + escapeHtml(agentDisplayPurpose(a.key)) + '</div>' +
        '<div class="agent-stat-row">' +
        '<div class="agent-stat"><div class="n ltr-num">' + a.sources.length + '</div><div class="l">' + escapeHtml(t("sourcesTrackedLabel")) + '</div></div>' +
        '<div class="agent-stat"><div class="n ltr-num">' + a.eventCount + '</div><div class="l">' + escapeHtml(t("eventsFoundLabel")) + '</div></div>' +
        (a.durationMs != null ? '<div class="agent-stat"><div class="n ltr-num">' + (a.durationMs / 1000).toFixed(1) + 's</div><div class="l">' + escapeHtml(t("processingTimeLabel")) + '</div></div>' : "") +
        '</div></div>';
    });
    html += "</div>";
    container.innerHTML = html;

    Array.prototype.forEach.call(container.querySelectorAll(".agent-card"), function (card) {
      card.addEventListener("click", function () {
        const a = stats[Number(card.getAttribute("data-agent-idx"))];
        _openAgentDrawer(a, latestRun);
      });
    });
  },
};

function _openAgentDrawer(a, latestRun) {
  const statusLabel = a.status === "completed" ? t("statusAgentCompleted") : a.status === "failed" ? t("statusError") : a.status === "skipped" ? t("statusSkipped") : t("statusIdle");
  let body = '<div><div class="drawer-section-title">' + escapeHtml(t("drawerPurpose")) + '</div><div class="briefing-body">' + escapeHtml(agentDisplayPurpose(a.key)) + '</div></div>';
  body += '<div><div class="drawer-section-title">' + escapeHtml(t("drawerSources")) + '</div><div style="display:flex;flex-wrap:wrap;gap:6px">' +
    a.sources.map(function (s) { return '<span class="geo-tag">' + escapeHtml(s) + '</span>'; }).join("") + "</div></div>";
  body += '<div><div class="drawer-section-title">' + escapeHtml(t("drawerLastExecution")) + '</div>' +
    '<div class="briefing-body">' + (latestRun ? escapeHtml(fmtDateTime(latestRun.generated_at, localeTag())) : "—") + ' — ' +
    '<span class="status-chip s-' + (a.status === "completed" ? "completed" : a.status === "failed" ? "error" : "idle") + '"><span class="dot"></span>' + escapeHtml(statusLabel) + '</span></div>';
  if (a.error) body += '<div class="error-block" style="margin-top:8px"><div class="error-title">' + escapeHtml(t("drawerErrorLabel")) + '</div><div class="error-desc">' + escapeHtml(a.error) + '</div></div>';
  body += "</div>";
  body += '<div><div class="drawer-section-title">' + escapeHtml(t("drawerEventsCollected")) + ' (' + a.eventCount + ')</div>';
  const events = latestRun ? (latestRun.events || []).filter(function (e) { return e.agent === a.key; }) : [];
  const impactList = latestRun && latestRun.report ? latestRun.report.impact_analysis || [] : [];
  body += events.length
    ? events.map(function (e) { return intelItemHtml(e, impactForEvent(e.id, impactList)); }).join("")
    : '<div class="hint-text">' + escapeHtml(a.status === "idle" || a.status === "skipped" ? t("noAgentRunsYet") : t("noEventsThisRun")) + "</div>";
  body += "</div>";
  openDrawer(escapeHtml(agentDisplayName(a.key)), body);
}
