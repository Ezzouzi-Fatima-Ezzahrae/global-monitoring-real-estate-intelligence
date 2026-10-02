// pages/alerts.js — notification channel management, moved off the main
// dashboard. Reads real configured/not-configured state from the new
// read-only GET /notify/status (additive endpoint, main.py) and can fire a
// real connectivity test via POST /notify/test. There is deliberately no
// per-topic alert-rules UI here: the backend has no rules engine (every
// briefing generated with "Also send to notification channels" just goes
// to every configured channel below) -- inventing Create/Edit-alert forms
// for a feature that doesn't exist would violate the "never fabricate"
// rule, so that's stated plainly instead (see automationDesc).
"use strict";

Pages.alerts = {
  async render(container, params, isStale) {
    container.innerHTML = '<div class="page-head"><div><div class="page-eyebrow">' + escapeHtml(t("alertsEyebrow")) + '</div>' +
      '<div class="page-title">' + escapeHtml(t("alertsTitle")) + '</div><div class="page-desc">' + escapeHtml(t("alertsDesc")) + '</div></div></div>' +
      '<div class="panel panel-pad">' + skeletonLines(4, ["w-full"]) + "</div>";

    let status = null, statusError = null;
    try { status = await loadNotifyStatus(true); } catch (exc) { statusError = exc; }
    if (isStale()) return;

    let html = '<div class="page-head"><div><div class="page-eyebrow">' + escapeHtml(t("alertsEyebrow")) + '</div>' +
      '<div class="page-title">' + escapeHtml(t("alertsTitle")) + '</div><div class="page-desc">' + escapeHtml(t("alertsDesc")) + '</div></div></div>';

    html += '<div class="panel panel-pad" style="margin-bottom:18px"><div class="section-title">' + escapeHtml(t("activeAlertsTitle")) + '</div>' +
      '<div class="hint-text" style="margin-top:6px">' + escapeHtml(t("automationDesc")) + '</div></div>';

    html += '<div class="panel panel-pad">' +
      '<div class="section-head"><div class="section-title">' + escapeHtml(t("notificationChannelsTitle")) + '</div>' +
      '<button type="button" class="btn btn-secondary btn-sm" id="alertsTestBtn">' + escapeHtml(t("testNotificationBtn")) + '</button></div>';

    if (statusError) {
      html += errorState({ title: t("runFailedTitle"), desc: String((statusError && statusError.message) || statusError), detail: statusError && statusError.stack });
    } else {
      const rows = [
        { key: "whatsapp", name: "WhatsApp", sub: status.whatsapp.provider ? "Provider: " + status.whatsapp.provider : "" },
        { key: "telegram", name: "Telegram", sub: "" },
        { key: "email", name: "Email", sub: "" },
      ];
      rows.forEach(function (r) {
        const cfg = status[r.key];
        html += '<div class="cred-row"><div><div class="cred-name">' + escapeHtml(r.name) + '</div>' +
          (r.sub ? '<div class="cred-sub">' + escapeHtml(r.sub) + '</div>' : "") +
          (!cfg.configured ? '<div class="cred-sub">' + escapeHtml(t("setupInEnv")) + '</div>' : "") + '</div>' +
          '<span class="tag tone-' + (cfg.configured ? "good" : "neutral") + '">' + escapeHtml(cfg.configured ? t("channelConfigured") : t("channelNotConfigured")) + '</span></div>';
      });
    }
    html += '<div id="alertsTestResult"></div></div>';

    container.innerHTML = html;

    const testBtn = document.getElementById("alertsTestBtn");
    if (testBtn) {
      testBtn.addEventListener("click", async function () {
        testBtn.disabled = true;
        const original = testBtn.textContent;
        testBtn.textContent = t("testSending");
        const resultEl = document.getElementById("alertsTestResult");
        try {
          const result = await api.notifyTest();
          resultEl.innerHTML = '<div style="margin-top:14px;display:flex;flex-direction:column;gap:8px">' +
            Object.keys(result).map(function (ch) {
              const r = result[ch];
              if (r && r.sent_to && r.sent_to.length) return '<div class="tag tone-good">' + escapeHtml(ch) + ': sent</div>';
              if (r && r.skipped_reason) return '<div class="tag tone-neutral">' + escapeHtml(ch) + ': ' + escapeHtml(r.skipped_reason) + '</div>';
              if (r && r.error) return '<div class="tag tone-bad">' + escapeHtml(ch) + ': ' + escapeHtml(r.error) + '</div>';
              return '<div class="tag tone-neutral">' + escapeHtml(ch) + ': —</div>';
            }).join("") + "</div>";
        } catch (exc) {
          resultEl.innerHTML = errorState({ title: t("runFailedTitle"), desc: String((exc && exc.message) || exc), detail: exc && exc.stack });
        } finally {
          testBtn.disabled = false;
          testBtn.textContent = original;
        }
      });
    }
  },
};
