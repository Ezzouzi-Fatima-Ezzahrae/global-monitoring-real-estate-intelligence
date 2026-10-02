// shell.js — sidebar + top header: built once at boot, then updated in
// place (active nav item, header title, status footer) as the route/lang
// change. Mirrors the "components/layout" separation asked for, just
// without a build step.
"use strict";

const NAV_ITEMS = [
  { key: "overview", path: "overview", icon: "overview", labelKey: "navOverview" },
  { key: "feed", path: "intelligence-feed", icon: "feed", labelKey: "navFeed" },
  { key: "briefings", path: "briefings", icon: "briefings", labelKey: "navBriefings" },
  { key: "market", path: "market-intelligence", icon: "market", labelKey: "navMarket" },
  { key: "realestate", path: "real-estate", icon: "realestate", labelKey: "navRealEstate" },
  { key: "mena", path: "mena-morocco", icon: "mena", labelKey: "navMena" },
  { key: "agents", path: "agents", icon: "agents", labelKey: "navAgents" },
  { key: "documents", path: "documents", icon: "documents", labelKey: "navDocuments" },
  { key: "alerts", path: "alerts", icon: "alerts", labelKey: "navAlerts" },
  { key: "reports", path: "reports", icon: "reports", labelKey: "navReports" },
];

const PAGE_HEADER = {
  overview: { titleKey: "navOverview", subKey: "overviewDesc" },
  feed: { titleKey: "navFeed", subKey: "feedDesc" },
  briefings: { titleKey: "navBriefings", subKey: "briefingsDesc" },
  market: { titleKey: "navMarket", subKey: "marketDesc" },
  realestate: { titleKey: "navRealEstate", subKey: "realEstateDesc" },
  mena: { titleKey: "navMena", subKey: "menaDesc" },
  agents: { titleKey: "navAgents", subKey: "agentsDesc" },
  documents: { titleKey: "navDocuments", subKey: "documentsDesc" },
  alerts: { titleKey: "navAlerts", subKey: "alertsDesc" },
  reports: { titleKey: "navReports", subKey: "reportsDesc" },
  settings: { titleKey: "navSettings", subKey: "settingsDesc" },
  search: { titleKey: "searchTitle", subKey: "searchDesc" },
};

function renderSidebar() {
  const groups = [
    NAV_ITEMS.slice(0, 6),
    NAV_ITEMS.slice(6),
  ];
  let html = '<div class="brand-block">' +
    '<div class="brand-mark"><img src="/static/logo.png?v=4" alt=""></div>' +
    '<div class="brand-text"><div class="brand-name">' + escapeHtml(t("appName")) + '</div>' +
    '<div class="brand-sub">' + escapeHtml(t("appSub")) + '</div></div></div>' +
    '<nav class="nav-scroll" id="navScroll" aria-label="Primary">';
  groups.forEach(function (group, gi) {
    html += '<div class="nav-group">';
    group.forEach(function (item) {
      html += '<a class="nav-item" data-nav="' + item.key + '" data-path="' + item.path + '" href="#/' + item.path + '">' +
        '<span class="nav-icon">' + icon(item.icon) + '</span><span>' + escapeHtml(t(item.labelKey)) + '</span></a>';
    });
    html += '</div>';
  });
  html += '</nav>' +
    '<div class="sidebar-foot">' +
    '<div class="status-line"><span class="status-dot" id="sysStatusDot"></span><span id="sysStatusText">' + escapeHtml(t("systemOperational")) + '</span></div>' +
    '<div class="status-sub"><span id="lastUpdateText">' + escapeHtml(t("lastUpdateLabel")) + ': ' + escapeHtml(t("never")) + '</span></div>' +
    '<div class="profile-row"><div class="profile-avatar">OI</div>' +
    '<div class="profile-meta"><div class="profile-name">' + escapeHtml(t("profileName")) + '</div>' +
    '<div class="profile-role">' + escapeHtml(t("profileRole")) + '</div></div></div>' +
    '</div>';
  document.getElementById("sidebar").innerHTML = html;

  Array.prototype.forEach.call(document.querySelectorAll(".nav-item"), function (a) {
    a.addEventListener("click", function () { closeSidebarOnMobile(); });
  });
}

function setActiveNav(navKey) {
  Array.prototype.forEach.call(document.querySelectorAll(".nav-item"), function (a) {
    a.classList.toggle("active", a.getAttribute("data-nav") === navKey);
  });
  const meta = PAGE_HEADER[navKey] || PAGE_HEADER.overview;
  document.getElementById("headerTitle").textContent = t(meta.titleKey);
  document.getElementById("headerSub").textContent = t(meta.subKey);
}

function renderHeader() {
  let html =
    '<div class="header-left" style="display:flex;align-items:center;gap:12px;min-width:0">' +
    '<button type="button" class="icon-btn menu-btn" id="menuBtn" aria-label="Menu">' + icon("menu") + '</button>' +
    '<div class="header-titles" style="min-width:0"><div class="header-title" id="headerTitle"></div><div class="header-sub" id="headerSub"></div></div>' +
    '</div>' +
    '<div class="header-actions">' +
    '<form class="search-box" id="headerSearchForm" role="search">' + icon("search") +
    '<input type="text" id="headerSearchInput" placeholder="' + escapeHtml(t("searchPlaceholder")) + '" autocomplete="off"></form>' +
    '<button type="button" class="icon-btn mobile-search-btn" id="mobileSearchBtn" aria-label="' + escapeHtml(t("searchPlaceholder")) + '">' + icon("search") + '</button>' +
    '<button type="button" class="icon-btn" id="notifyIconBtn" title="' + escapeHtml(t("navAlerts")) + '">' + icon("bell") + '<span class="dot-badge" id="notifyDot" hidden></span></button>' +
    '<select class="lang-select" id="headerLangSelect" aria-label="' + escapeHtml(t("langLabel")) + '">' +
    '<option value="en">EN</option><option value="fr">FR</option><option value="ar">AR</option></select>' +
    '<button type="button" class="icon-btn" id="settingsIconBtn" title="' + escapeHtml(t("navSettings")) + '">' + icon("user") + '</button>' +
    '</div>';
  document.getElementById("topheader").innerHTML = html;

  document.getElementById("headerLangSelect").value = getLang();
  document.getElementById("headerLangSelect").addEventListener("change", function (e) { applyLanguage(e.target.value); });
  document.getElementById("menuBtn").addEventListener("click", toggleSidebarMobile);
  document.getElementById("settingsIconBtn").addEventListener("click", function () { navigate("settings"); });
  document.getElementById("notifyIconBtn").addEventListener("click", function () { navigate("alerts"); });
  document.getElementById("headerSearchForm").addEventListener("submit", function (e) {
    e.preventDefault();
    const q = document.getElementById("headerSearchInput").value.trim();
    if (q) { navigate("search?q=" + encodeURIComponent(q)); document.getElementById("headerSearchForm").classList.remove("mobile-open"); }
  });
  document.getElementById("mobileSearchBtn").addEventListener("click", function () {
    const form = document.getElementById("headerSearchForm");
    form.classList.toggle("mobile-open");
    if (form.classList.contains("mobile-open")) document.getElementById("headerSearchInput").focus();
  });
}

function toggleSidebarMobile() {
  document.getElementById("sidebar").classList.toggle("open");
  document.getElementById("sidebarScrim").classList.toggle("show");
}
function closeSidebarOnMobile() {
  document.getElementById("sidebar").classList.remove("open");
  document.getElementById("sidebarScrim").classList.remove("show");
}

function updateSystemStatus(health, latestRun) {
  const dot = document.getElementById("sysStatusDot");
  const text = document.getElementById("sysStatusText");
  if (!dot || !text) return;
  const allOk = health && health.llm_api_key_configured && health.web_search_api_key_configured;
  dot.className = "status-dot" + (allOk ? "" : " warn");
  text.textContent = allOk ? t("systemOperational") : t("systemDegraded");
  const lastEl = document.getElementById("lastUpdateText");
  if (lastEl) {
    const when = latestRun ? fmtTime(latestRun.generated_at, localeTag()) + ", " + fmtDate(latestRun.generated_at, localeTag()) : t("never");
    lastEl.textContent = t("lastUpdateLabel") + ": " + when;
  }
}
