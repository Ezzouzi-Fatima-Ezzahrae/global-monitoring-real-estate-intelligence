// pages/settings.js — read-only summary of what's configured (GET
// /health). No form here edits credentials -- they live in .env on the
// machine this runs on, per health()'s own docstring ("no mock mode to
// fall back to"), so this page only ever reflects real configured state.
"use strict";

Pages.settings = {
  async render(container, params, isStale) {
    container.innerHTML = '<div class="page-head"><div><div class="page-eyebrow">' + escapeHtml(t("settingsEyebrow")) + '</div>' +
      '<div class="page-title">' + escapeHtml(t("settingsTitle")) + '</div><div class="page-desc">' + escapeHtml(t("settingsDesc")) + '</div></div></div>' +
      '<div class="panel panel-pad">' + skeletonLines(4, ["w-full"]) + "</div>";

    let health = null;
    try { health = await loadHealth(true); } catch (exc) {
      if (!isStale()) container.querySelector(".panel").outerHTML = errorState({ title: t("runFailedTitle"), desc: String((exc && exc.message) || exc), detail: exc && exc.stack });
      return;
    }
    if (isStale()) return;

    let html = '<div class="page-head"><div><div class="page-eyebrow">' + escapeHtml(t("settingsEyebrow")) + '</div>' +
      '<div class="page-title">' + escapeHtml(t("settingsTitle")) + '</div><div class="page-desc">' + escapeHtml(t("settingsDesc")) + '</div></div></div>';

    html += '<div class="panel panel-pad">';
    html += '<div class="cred-row"><div><div class="cred-name">' + escapeHtml(t("credentialLlm")) + '</div>' +
      '<div class="cred-sub">' + escapeHtml((health.llm_provider || "") + (health.llm_model ? " · " + health.llm_model : "")) + '</div></div>' +
      '<span class="tag tone-' + (health.llm_api_key_configured ? "good" : "bad") + '">' + escapeHtml(health.llm_api_key_configured ? t("configuredLabel") : t("missingLabel")) + '</span></div>';
    html += '<div class="cred-row"><div><div class="cred-name">' + escapeHtml(t("credentialSearch")) + '</div></div>' +
      '<span class="tag tone-' + (health.web_search_api_key_configured ? "good" : "bad") + '">' + escapeHtml(health.web_search_api_key_configured ? t("configuredLabel") : t("missingLabel")) + '</span></div>';
    html += '<div class="cred-row"><div><div class="cred-name">' + escapeHtml(t("credentialGroq")) + '</div></div>' +
      '<span class="tag tone-' + (health.groq_api_key_configured ? "good" : "bad") + '">' + escapeHtml(health.groq_api_key_configured ? t("configuredLabel") : t("missingLabel")) + '</span></div>';
    html += "</div>";

    html += '<div class="panel panel-pad" style="margin-top:18px"><div class="section-title">' + escapeHtml(t("navAlerts")) + '</div>' +
      '<div class="hint-text" style="margin-top:6px">' + escapeHtml(t("alertsDesc")) + ' <a href="#/alerts">' + escapeHtml(t("navAlerts")) + " →</a></div></div>";

    html += '<div class="hint-text" style="margin-top:22px;text-align:center">' + escapeHtml(t("poweredByLocal")) + "</div>";

    container.innerHTML = html;
  },
};
