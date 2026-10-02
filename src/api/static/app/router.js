// router.js — tiny hash router. Each route maps to a page module under
// window.Pages (plain objects with a render(container, params) function;
// no build step, so no ES module import/export — everything hangs off
// window, loaded in order by <script> tags in index.html).
"use strict";

const Pages = {};

const ROUTES = [
  { path: "overview", nav: "overview", page: "overview" },
  { path: "intelligence-feed", nav: "feed", page: "feed" },
  { path: "briefings", nav: "briefings", page: "briefingsList" },
  { path: "briefings/:id", nav: "briefings", page: "briefingDetail" },
  { path: "market-intelligence", nav: "market", page: "market" },
  { path: "real-estate", nav: "realestate", page: "realEstate" },
  { path: "mena-morocco", nav: "mena", page: "mena" },
  { path: "agents", nav: "agents", page: "agents" },
  { path: "documents", nav: "documents", page: "documents" },
  { path: "alerts", nav: "alerts", page: "alerts" },
  { path: "reports", nav: "reports", page: "reports" },
  { path: "search", nav: "search", page: "search" },
  { path: "settings", nav: "settings", page: "settings" },
];

function _parseHash() {
  let h = window.location.hash.replace(/^#\/?/, "");
  if (!h) return { path: "overview", parts: ["overview"], query: {} };
  const qIdx = h.indexOf("?");
  let query = {};
  if (qIdx !== -1) {
    const qs = h.slice(qIdx + 1);
    h = h.slice(0, qIdx);
    qs.split("&").forEach(function (pair) {
      if (!pair) return;
      const eq = pair.indexOf("=");
      const k = decodeURIComponent(eq === -1 ? pair : pair.slice(0, eq));
      const v = eq === -1 ? "" : decodeURIComponent(pair.slice(eq + 1));
      query[k] = v;
    });
  }
  const parts = h.split("/").filter(Boolean);
  return { path: parts[0] || "overview", parts: parts, query: query };
}

function _matchRoute(parts) {
  for (const r of ROUTES) {
    const rp = r.path.split("/");
    if (rp.length !== parts.length) continue;
    const params = {};
    let ok = true;
    for (let i = 0; i < rp.length; i++) {
      if (rp[i].charAt(0) === ":") params[rp[i].slice(1)] = parts[i];
      else if (rp[i] !== parts[i]) { ok = false; break; }
    }
    if (ok) return { route: r, params: params };
  }
  return null;
}

let _currentRender = 0;

async function _renderRoute() {
  const parsed = _parseHash();
  const matched = _matchRoute(parsed.parts) || _matchRoute(["overview"]);
  const container = document.getElementById("app");
  setActiveNav(matched.route.nav);
  const myRender = ++_currentRender;
  const pageMod = Pages[matched.route.page];
  if (!pageMod || typeof pageMod.render !== "function") {
    container.innerHTML = '<div class="state-block"><div class="state-title">Page not found</div></div>';
    return;
  }
  try {
    await pageMod.render(container, Object.assign({}, matched.params, { query: parsed.query }), function () { return myRender !== _currentRender; });
  } catch (exc) {
    if (myRender !== _currentRender) return;
    console.error(exc);
    container.innerHTML = errorState({
      title: t("runFailedTitle"),
      desc: String((exc && exc.message) || exc),
      detail: exc && exc.stack ? exc.stack : null,
    });
  }
  closeSidebarOnMobile();
  window.scrollTo(0, 0);
}

function navigate(path) { window.location.hash = "#/" + path; }

function initRouter() {
  window.addEventListener("hashchange", _renderRoute);
  _renderRoute();
}

function rerenderCurrentRoute() { _renderRoute(); }
