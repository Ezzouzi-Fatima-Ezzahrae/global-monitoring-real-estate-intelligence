// ui.js — small reusable UI primitives shared by every page: toasts, the
// drawer, skeleton/empty/error state markup. No page re-implements these.
"use strict";

// ---------------- Toast ----------------
function toast(message, tone) {
  const stack = document.getElementById("toastStack");
  if (!stack) return;
  const el = document.createElement("div");
  el.className = "toast" + (tone ? " tone-" + tone : "");
  el.textContent = message;
  stack.appendChild(el);
  setTimeout(function () {
    el.style.opacity = "0";
    el.style.transition = "opacity .2s ease";
    setTimeout(function () { el.remove(); }, 220);
  }, 3400);
}

// ---------------- Drawer ----------------
function openDrawer(titleHtml, bodyHtml) {
  const scrim = document.getElementById("drawerScrim");
  const drawer = document.getElementById("drawer");
  document.getElementById("drawerTitle").innerHTML = titleHtml;
  document.getElementById("drawerBody").innerHTML = bodyHtml;
  scrim.classList.add("show");
  drawer.classList.add("show");
}
function closeDrawer() {
  document.getElementById("drawerScrim").classList.remove("show");
  document.getElementById("drawer").classList.remove("show");
}

// ---------------- Skeletons ----------------
function skeletonLines(n, widths) {
  widths = widths || ["w-full", "w-80", "w-60"];
  let html = "";
  for (let i = 0; i < n; i++) html += '<div class="skel skel-line ' + widths[i % widths.length] + '"></div>';
  return html;
}
function skeletonCards(n) {
  let html = "";
  for (let i = 0; i < n; i++) html += '<div class="skel skel-card"></div>';
  return html;
}
function skeletonKpis() {
  let html = '<div class="kpi-grid">';
  for (let i = 0; i < 4; i++) {
    html += '<div class="kpi-card"><div class="skel skel-line w-60" style="height:9px"></div>' +
      '<div class="skel skel-line w-40" style="height:26px;margin-top:10px"></div>' +
      '<div class="skel skel-line w-80" style="height:9px;margin-top:6px"></div></div>';
  }
  return html + "</div>";
}

// ---------------- Empty / error states ----------------
function emptyState(opts) {
  return (
    '<div class="state-block">' +
    '<div class="state-icon">' + icon(opts.icon || "inbox") + "</div>" +
    '<div class="state-title">' + escapeHtml(opts.title) + "</div>" +
    '<div class="state-desc">' + escapeHtml(opts.desc || "") + "</div>" +
    (opts.actionHtml || "") +
    "</div>"
  );
}
function errorState(opts) {
  return (
    '<div class="error-block">' +
    '<div class="error-title">' + escapeHtml(opts.title) + "</div>" +
    '<div class="error-desc">' + escapeHtml(opts.desc || "") + "</div>" +
    (opts.detail
      ? '<details class="error-details"><summary>' + escapeHtml(t("technicalDetails")) + "</summary><pre>" + escapeHtml(opts.detail) + "</pre></details>"
      : "") +
    (opts.actionHtml || "") +
    "</div>"
  );
}

function demoFlag() { return '<span class="demo-flag">' + escapeHtml(t("demoDataFlag")) + "</span>"; }

function sentimentTone(s) { return s === "positive" ? "good" : s === "negative" ? "bad" : s === "mixed" ? "warn" : "neutral"; }
function relevanceTone(r) { return r === "high" ? "accent" : r === "medium" ? "warn" : "neutral"; }
function directionTone(d) { return d === "positive" ? "good" : d === "negative" ? "bad" : d === "mixed" ? "warn" : "neutral"; }
function magnitudeTone(m) { return m === "high" ? "accent" : m === "medium" ? "warn" : "neutral"; }

function priorityFlagHtml(level) {
  const label = level === "high" ? t("impactHigh") : level === "medium" ? t("impactMedium") : t("impactLow");
  return '<span class="priority-flag p-' + level + '">' + escapeHtml(label) + "</span>";
}

// Shared enum -> translated-label mappers for the small fixed value sets
// the backend actually returns (Relevance/Magnitude are "high"/"medium"/
// "low"; Sentiment/Direction are "positive"/"negative"/"neutral"/"mixed")
// -- reuses the impactHigh/Medium/Low keys already shown in the feed
// filter, so a level always reads the same word everywhere it appears.
function levelLabel(level) {
  return level === "high" ? t("impactHigh") : level === "medium" ? t("impactMedium") : t("impactLow");
}
function sentimentLabel(s) {
  return s === "positive" ? t("sentimentPositive")
    : s === "negative" ? t("sentimentNegative")
    : s === "mixed" ? t("sentimentMixed")
    : t("sentimentNeutral");
}
function timeHorizonLabel(h) {
  return h === "immediate" ? t("timeHorizonImmediate")
    : h === "short_term" ? t("timeHorizonShortTerm")
    : t("timeHorizonMediumTerm");
}

// ---------------- Source traceability + opportunity hooks (2026-09-24) ----------------
// Every mapper below is a small, fixed lookup over a real enum value the
// backend already computed (src/models/event.py's SourceType/SourceQuality,
// src/agents/judge_agent.py's OpportunityHook.potential_requirements) --
// never a guess and never sent through AI translation (see
// src/services/translation.py's own docstring on why potential_requirements
// specifically is excluded from that pipeline).
function sourceQualityTone(quality) {
  return quality === "primary" ? "good"
    : quality === "credible_secondary" ? "jewel"
    : quality === "secondary" ? "warn"
    : quality === "early_unconfirmed" ? "accent"
    : "neutral"; // not_verified, or an unrecognized/missing value
}
const _SOURCE_TYPE_I18N = {
  official_company: "sourceTypeOfficialCompany", government: "sourceTypeGovernment", news: "sourceTypeNews",
  business_media: "sourceTypeBusinessMedia", linkedin: "sourceTypeLinkedin", pdf: "sourceTypePdf",
  report: "sourceTypeReport", other: "sourceTypeOther",
};
const _SOURCE_QUALITY_I18N = {
  primary: "sourceQualityPrimary", credible_secondary: "sourceQualityCredibleSecondary",
  secondary: "sourceQualitySecondary", early_unconfirmed: "sourceQualityEarlyUnconfirmed",
  not_verified: "sourceQualityNotVerified",
};
function sourceTypeLabel(sourceType) { return t(_SOURCE_TYPE_I18N[sourceType] || "sourceTypeOther"); }
function sourceQualityLabel(quality) { return t(_SOURCE_QUALITY_I18N[quality] || "sourceQualityNotVerified"); }

const _REQUIREMENT_I18N = {
  hotel_resort_property: "reqHotelResortProperty", land_hospitality_dev: "reqLandHospitalityDev",
  industrial_site: "reqIndustrialSite", factory_land: "reqFactoryLand",
  warehouse_logistics_land: "reqWarehouseLogisticsLand", land: "reqLand",
  residential_dev_site: "reqResidentialDevSite", commercial_property: "reqCommercialProperty",
  retail_location: "reqRetailLocation", office: "reqOffice", headquarters: "reqHeadquarters",
  local_partner: "reqLocalPartner",
};
// Falls back to the raw key itself (never invented text) if a future backend
// key is added here before this table is -- an untranslated real key beats a
// silently wrong or blank label.
function requirementLabel(key) { return _REQUIREMENT_I18N[key] ? t(_REQUIREMENT_I18N[key]) : key; }

function sourceBadgeHtml(event) {
  const quality = event.source_quality || "not_verified";
  return '<span class="tag tone-' + sourceQualityTone(quality) + ' source-badge" title="' + escapeHtml(sourceQualityLabel(quality)) + '">' +
    escapeHtml(sourceTypeLabel(event.source_type || "other")) + "</span>";
}

// A real link to the real source -- for a PDF-derived event this is the
// document's own GET /documents/{id}/pdf URL (src/services/document_store.py's
// own docstring on why that's always the real source_url for such an event),
// deep-linked to the real, independently-verified page number when one
// exists (src/agents/document_agent.py's _verify_page_reference -- an
// unverified page is never shown as if confirmed, so pdf_reference.page is
// only ever present here when it's real).
function readSourceButtonHtml(event) {
  if (!event.source_url) return "";
  const isPdf = event.source_type === "pdf";
  const page = event.pdf_reference && event.pdf_reference.page;
  const href = event.source_url + (isPdf && page ? "#page=" + encodeURIComponent(page) : "");
  const label = isPdf ? t("openPdfSource") : t("readSource");
  return '<a class="btn btn-ghost btn-sm" href="' + escapeHtml(href) + '" target="_blank" rel="noopener">' +
    icon("external") + escapeHtml(label) + (isPdf && page ? ' <span class="hint-text">' + escapeHtml(t("pdfPageLabel", page)) + "</span>" : "") +
    "</a>";
}

// Registry backing the "View All Sources" drawer -- keyed by event id so the
// button itself only needs to carry that id, not the whole (possibly long)
// supporting_sources list, through a data-* attribute. Supporting sources are
// real corroborating citations (src/models/event.py's SupportingSource);
// there is no code path today that populates them, so this renders nothing
// until a future phase adds one -- never a placeholder standing in for real
// corroboration.
const _sourcesRegistry = {};
function viewAllSourcesButtonHtml(event) {
  if (!event.supporting_sources || !event.supporting_sources.length) return "";
  _sourcesRegistry[event.id] = event.supporting_sources;
  return '<button type="button" class="btn btn-ghost btn-sm" data-view-sources="' + escapeHtml(event.id) + '">' +
    icon("layers") + escapeHtml(t("viewAllSources")) + "</button>";
}
function showSourcesDrawer(eventId) {
  const sources = _sourcesRegistry[eventId] || [];
  const body = sources.length
    ? sources.map(function (s) {
        return '<div class="source-item"><a href="' + escapeHtml(s.source_url) + '" target="_blank" rel="noopener">' +
          escapeHtml(s.source_name || s.source_url) + "</a>" +
          (s.published_at ? '<div class="source-item-meta">' + escapeHtml(fmtDate(s.published_at, localeTag())) + "</div>" : "") +
          "</div>";
      }).join("")
    : emptyState({ icon: "inbox", title: t("noEventsTitle") });
  openDrawer(escapeHtml(t("allSourcesTitle")), body);
}

// The opportunity-hook block (src/agents/judge_agent.py's build_hook) --
// every field here is either copied verbatim from an already-hedged,
// already-real string (why_it_matters/evidence/suggested_action) or a
// small fixed template (headline/stage/potential_requirements), never a
// fresh claim invented for display -- see that function's own docstring.
function hookCardHtml(hook) {
  if (!hook) return "";
  const isConfirmed = hook.stage === "confirmed";
  const stageLabel = isConfirmed ? t("hookStageConfirmed") : t("hookStageEarlySignal");
  const stageTone = isConfirmed ? "good" : "accent";
  const reqs = (hook.potential_requirements || [])
    .map(function (k) { return '<span class="tag tone-neutral">' + escapeHtml(requirementLabel(k)) + "</span>"; })
    .join("");
  return (
    '<div class="hook-card' + (isConfirmed ? " is-confirmed" : "") + '">' +
    '<div class="hook-eyebrow">' + icon("flag") + escapeHtml(t("hookEyebrow")) +
    '<span class="tag tone-' + stageTone + ' hook-stage">' + escapeHtml(stageLabel) + " · " + escapeHtml(levelLabel(hook.confidence_label)) + "</span>" +
    "</div>" +
    '<div class="hook-headline">' + escapeHtml(hook.headline) + "</div>" +
    '<div class="hook-row"><b>' + escapeHtml(t("hookWhyItMatters")) + ":</b> " + escapeHtml(hook.why_it_matters) + "</div>" +
    '<div class="hook-row"><b>' + escapeHtml(t("hookEvidence")) + ":</b> " + escapeHtml(hook.evidence) + "</div>" +
    '<div class="hook-row"><b>' + escapeHtml(t("hookSuggestedAction")) + ":</b> " + escapeHtml(hook.suggested_action) + "</div>" +
    (reqs ? '<div class="hook-row">' + escapeHtml(t("hookPotentialRequirements")) + ":</div><div class=\"hook-reqs\">" + reqs + "</div>" : "") +
    "</div>"
  );
}

// ---------------- Shared intelligence-item renderer ----------------
// Used by Overview ("Today's Intelligence"), the Intelligence Feed, and the
// Market/Real Estate/MENA category pages -- one real Event (+ its real
// ImpactAssessment, if Judge has assessed it) rendered identically
// everywhere so the same event always looks the same across pages.
function intelItemHtml(event, impact) {
  const rankBadge = event.priority_rank && event.priority_rank <= 3
    ? '<span class="tag tone-solid">#' + event.priority_rank + '</span>' : "";
  const relTag = '<span class="tag tone-' + relevanceTone(event.relevance_to_real_estate) + '">' +
    escapeHtml(levelLabel(event.relevance_to_real_estate || "low")) + "</span>";
  const sentTag = '<span class="tag tone-' + sentimentTone(event.sentiment) + '">' + escapeHtml(sentimentLabel(event.sentiment || "neutral")) + "</span>";
  const impactTag = impact
    ? '<span class="tag tone-' + magnitudeTone(impact.magnitude) + '">' + escapeHtml(levelLabel(impact.magnitude)) + " " + escapeHtml(sentimentLabel(impact.direction)) + "</span>"
    : "";
  const geo = (event.entities && event.entities.countries && event.entities.countries.length)
    ? event.entities.countries.slice(0, 3).map(function (c) { return '<span class="geo-tag">' + escapeHtml(c) + "</span>"; }).join("")
    : "";
  const when = event.published_at ? fmtDate(event.published_at, localeTag()) : fmtRelative(event.collected_at, t);
  return (
    '<div class="intel-item">' +
    '<div class="intel-top">' + rankBadge + relTag + sentTag + impactTag + sourceBadgeHtml(event) + geo + "</div>" +
    '<div class="intel-headline">' + escapeHtml(event.headline) + "</div>" +
    '<div class="intel-summary">' + escapeHtml(event.summary) + "</div>" +
    '<div class="intel-meta">' +
    "<span>" + escapeHtml(agentDisplayName(event.agent)) + "</span>" +
    "<span>" + escapeHtml(event.source_name || "") + "</span>" +
    "<span>" + escapeHtml(when) + "</span>" +
    '<span class="source-actions">' + readSourceButtonHtml(event) + viewAllSourcesButtonHtml(event) + "</span>" +
    "</div>" +
    hookCardHtml(event.hook) +
    "</div>"
  );
}
