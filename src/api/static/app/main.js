// main.js — boot sequence for the whole console.
"use strict";

// Remembers the last real health/latest-run values boot() fetched, purely
// so a language switch (which re-renders the sidebar from scratch) can put
// the real "System operational" / "Last update" text straight back rather
// than letting renderSidebar()'s own placeholder default ("never") show
// until the next full boot.
let _lastHealth = null;
let _lastLatestRun = null;

function applyLanguage(lang) {
  setLang(lang);
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  try { localStorage.setItem("oi_lang", lang); } catch (_) { /* private mode etc. */ }
  renderSidebar();
  renderHeader();
  if (_lastHealth) updateSystemStatus(_lastHealth, _lastLatestRun);
  const fab = document.getElementById("chatFab");
  if (fab) fab.setAttribute("aria-label", t("chatFabLabel"));
  if (typeof setChatContext === "function") setChatContext(_chatRunId, _chatContextLabel);
  rerenderCurrentRoute();
}

function initialLanguage() {
  try {
    const saved = localStorage.getItem("oi_lang");
    if (saved && I18N[saved]) return saved;
  } catch (_) { /* ignore */ }
  const nav = (navigator.language || "en").slice(0, 2);
  return I18N[nav] ? nav : "en";
}

async function boot() {
  setLang(initialLanguage());
  document.documentElement.lang = getLang();
  document.documentElement.dir = getLang() === "ar" ? "rtl" : "ltr";

  renderSidebar();
  renderHeader();

  const fab = document.getElementById("chatFab");
  if (fab) fab.setAttribute("aria-label", t("chatFabLabel"));
  if (typeof setChatContext === "function") setChatContext(null, null);

  document.getElementById("sidebarScrim").addEventListener("click", closeSidebarOnMobile);
  document.getElementById("drawerScrim").addEventListener("click", closeDrawer);
  document.getElementById("drawerCloseBtn").addEventListener("click", closeDrawer);

  // 2026-09-24 addition: one delegated listener for every "View All Sources"
  // button any page's intelItemHtml() renders (app/ui.js) -- delegated on
  // the single #app content root rather than wired per-page, since the same
  // shared event-card markup is re-rendered by many different pages.
  document.getElementById("app").addEventListener("click", function (evt) {
    const btn = evt.target.closest("[data-view-sources]");
    if (btn) showSourcesDrawer(btn.getAttribute("data-view-sources"));
  });

  initRouter();

  try {
    const health = await loadHealth();
    let latest = null;
    try { latest = await loadLatestRun(); } catch (_) { /* no runs yet is fine */ }
    _lastHealth = health;
    _lastLatestRun = latest;
    updateSystemStatus(health, latest);
  } catch (exc) {
    const text = document.getElementById("sysStatusText");
    if (text) { text.textContent = t("systemUnreachable"); document.getElementById("sysStatusDot").className = "status-dot bad"; }
  }

  try {
    const ns = await loadNotifyStatus();
    const anyOff = !ns.whatsapp.configured || !ns.telegram.configured || !ns.email.configured;
    document.getElementById("notifyDot").hidden = !anyOff;
  } catch (_) { /* status endpoint optional for badge purposes */ }
}

document.addEventListener("DOMContentLoaded", boot);
