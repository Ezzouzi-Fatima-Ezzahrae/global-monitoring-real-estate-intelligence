// data.js — a small in-memory cache over api.js plus honest derivations
// (grouping/filtering/sorting real data). Nothing here invents facts: every
// function either returns what the backend returned, or a deterministic
// reorganization of it (e.g. "risks" = real impact_analysis entries whose
// real direction is negative/mixed, sorted by their real magnitude).
"use strict";

// Real roster, from src/agents/monitoring_agent.py's MONITORING_AGENTS list
// (verified directly against that file, not guessed) -- descriptive copy
// only; every number shown against an agent in the UI comes from a real
// run's trace/events, never from this table.
const AGENT_ROSTER = [
  {
    key: "Global Political News Agent",
    purpose: "Tracks diplomatic tensions, conflicts, sanctions and negotiations worldwide that could carry through to safe-haven capital flows, energy costs or tourist-source-market risk.",
    sources: ["Reuters", "AP News", "Al Jazeera", "Foreign Policy", "BBC", "CNN", "The Guardian", "The New York Times", "DW", "France24", "The Economist", "Middle East Eye", "Financial Times"],
  },
  {
    key: "Global Economic & Markets Agent",
    purpose: "Follows central bank decisions, interest rates and commodity markets — the channel through which global conditions reach Moroccan financing costs and construction material prices.",
    sources: ["Reuters", "Bloomberg", "IMF", "World Bank", "Trading Economics", "EIA", "S&P Global", "Financial Times", "CNBC"],
  },
  {
    key: "Expert Commentary Agent",
    purpose: "Reads written economic analysis and commentary from research institutions, for the reasoning behind market moves, not just the headline numbers.",
    sources: ["Project Syndicate", "VoxEU", "Brookings", "Council on Foreign Relations", "McKinsey"],
  },
  {
    key: "Regional MENA & Morocco Agent",
    purpose: "Monitors Morocco's economy, tourism and real estate news directly, plus wider MENA context.",
    sources: ["Hespress", "Morocco World News", "Medias24", "The Arab Weekly", "Arab News", "The National", "Le360"],
  },
  {
    key: "Real Estate Sector Agent",
    purpose: "Tracks the global real-estate and hospitality-investment sector specifically, including Morocco-focused coverage from major property advisories.",
    sources: ["Knight Frank", "JLL", "CBRE", "Hotel News Now", "Global Property Guide", "Skift"],
  },
  {
    key: "YouTube Video Monitoring Agent",
    purpose: "Covers video coverage (news segments, interviews, market analysis) of Marrakech real-estate investment that text search alone misses, including French/Arabic-language content.",
    sources: ["YouTube"],
  },
];

function agentRosterEntry(name) {
  return AGENT_ROSTER.find(function (a) { return a.key === name; }) || null;
}

// Maps each real agent key (event.agent / AGENT_ROSTER[].key -- always
// English, since it has to match what the Python backend actually writes)
// to the i18n key suffix that carries its translated display name/purpose.
// Never used for matching/filtering -- only for what's shown on screen.
const _AGENT_I18N_SUFFIX = {
  "Global Political News Agent": "Political",
  "Global Economic & Markets Agent": "Economic",
  "Expert Commentary Agent": "Expert",
  "Regional MENA & Morocco Agent": "Mena",
  "Real Estate Sector Agent": "RealEstate",
  "YouTube Video Monitoring Agent": "Youtube",
  "Uploaded Document Agent": "Document",
};
function agentDisplayName(key) {
  const suffix = _AGENT_I18N_SUFFIX[key];
  return suffix ? t("agentName" + suffix) : key;
}
function agentDisplayPurpose(key) {
  const suffix = _AGENT_I18N_SUFFIX[key];
  if (suffix) return t("agentPurpose" + suffix);
  const entry = agentRosterEntry(key);
  return entry ? entry.purpose : "";
}

// ---------------------------------------------------------------------
// Cache + loaders
// ---------------------------------------------------------------------
const _cache = { health: null, notifyStatus: null, runsList: null, runsById: {}, documents: null, runTranslations: {}, documentTranslations: {} };

async function loadHealth(force) {
  if (_cache.health && !force) return _cache.health;
  _cache.health = await api.health();
  return _cache.health;
}
async function loadNotifyStatus(force) {
  if (_cache.notifyStatus && !force) return _cache.notifyStatus;
  _cache.notifyStatus = await api.notifyStatus();
  return _cache.notifyStatus;
}
async function loadRunsList(limit, force) {
  if (_cache.runsList && !force) return _cache.runsList;
  _cache.runsList = await api.listRuns(limit || 30);
  return _cache.runsList;
}
async function loadRun(runId, force) {
  if (_cache.runsById[runId] && !force) return _cache.runsById[runId];
  const run = await api.getRun(runId);
  _cache.runsById[runId] = run;
  return run;
}
async function loadLatestRun() {
  const list = await loadRunsList(30);
  if (!list.length) return null;
  return loadRun(list[0].run_id);
}
async function loadRecentRuns(n) {
  const list = await loadRunsList(Math.max(n, 30));
  const slice = list.slice(0, n);
  return Promise.all(slice.map(function (r) { return loadRun(r.run_id); }));
}
async function loadDocuments(force) {
  if (_cache.documents && !force) return _cache.documents;
  _cache.documents = await api.listDocuments();
  return _cache.documents;
}
function invalidateDocuments() { _cache.documents = null; }
function invalidateRuns() { _cache.runsList = null; _cache.runsById = {}; }

// ---------------------------------------------------------------------
// On-demand translation (2026-09-22 addition): GET /runs/{id}/translation/
// {lang} and GET /documents/{id}/translation/{lang} translate a run's or
// document's real content the first time it's asked for and cache the
// result server-side (src/services/translation.py) -- this layer adds a
// second, client-side cache on top so switching back and forth between
// pages in the same session never re-fetches a translation already seen.
// Never called for "en" -- that is just the content as generated.
// ---------------------------------------------------------------------
async function loadRunTranslation(runId, lang, force) {
  const key = runId + "|" + lang;
  if (_cache.runTranslations[key] && !force) return _cache.runTranslations[key];
  const trans = await api.getRunTranslation(runId, lang);
  _cache.runTranslations[key] = trans;
  return trans;
}
async function loadDocumentTranslation(docId, lang, force) {
  const key = docId + "|" + lang;
  if (_cache.documentTranslations[key] && !force) return _cache.documentTranslations[key];
  const trans = await api.getDocumentTranslation(docId, lang);
  _cache.documentTranslations[key] = trans;
  return trans;
}

// Returns a NEW run object with headline/recommended_actions/
// debate_highlights, every event's headline/summary, every impact
// assessment's rationale/recommended_action/sector_or_market_affected, and
// (2026-09-24 addition) every hook-bearing event's hook.headline/
// why_it_matters/evidence/suggested_action, swapped for their translated
// versions -- ids, numbers, dates, source URLs, enum values (direction/
// magnitude/sentiment/relevance, already handled by app/ui.js's own
// i18n-backed labels) and hook.potential_requirements (a small fixed-
// vocabulary key list, handled by app/ui.js's requirementLabel(), never
// sent through AI translation -- see src/services/translation.py's
// docstring) are left untouched. The original `run` is never mutated, so a
// failed/partial translation can never corrupt the cached original.
function applyRunTranslation(run, trans) {
  if (!run || !trans) return run;
  const eventTrans = {};
  (trans.events || []).forEach(function (e) { eventTrans[e.id] = e; });
  const impactTrans = {};
  (trans.impact_assessments || []).forEach(function (ia) { impactTrans[ia.event_id] = ia; });
  const hookTrans = {};
  (trans.hooks || []).forEach(function (h) { hookTrans[h.event_id] = h; });

  const events = (run.events || []).map(function (e) {
    const te = eventTrans[e.id];
    let next = te ? Object.assign({}, e, { headline: te.headline, summary: te.summary }) : e;
    const th = hookTrans[e.id];
    if (th && next.hook) {
      next = Object.assign({}, next, { hook: Object.assign({}, next.hook, {
        headline: th.headline, why_it_matters: th.why_it_matters,
        evidence: th.evidence, suggested_action: th.suggested_action,
      }) });
    }
    return next;
  });

  let report = run.report;
  if (report) {
    const impact_analysis = (report.impact_analysis || []).map(function (ia) {
      const ti = impactTrans[ia.event_id];
      return ti ? Object.assign({}, ia, {
        sector_or_market_affected: ti.sector_or_market_affected,
        rationale: ti.rationale,
        recommended_action: ti.recommended_action,
      }) : ia;
    });
    report = Object.assign({}, report, {
      headline: trans.report_headline || report.headline,
      recommended_actions: (trans.recommended_actions && trans.recommended_actions.length) ? trans.recommended_actions : report.recommended_actions,
      debate_highlights: (trans.debate_highlights && trans.debate_highlights.length) ? trans.debate_highlights : report.debate_highlights,
      impact_analysis: impact_analysis,
    });
  }

  return Object.assign({}, run, { events: events, report: report });
}

// Loads a run and, if `lang` isn't English, its cached/fetched
// translation applied on top -- a translation failure (rate limit, no LLM
// key configured, etc.) is logged and swallowed here so the page still
// renders with the real original-language content rather than erroring
// out entirely over a nice-to-have.
async function loadTranslatedRun(runId, lang) {
  const run = await loadRun(runId);
  if (!run || !lang || lang === "en") return run;
  try {
    const trans = await loadRunTranslation(runId, lang);
    return applyRunTranslation(run, trans);
  } catch (exc) {
    console.error("Translation failed for run " + runId + ":", exc);
    return run;
  }
}

function applyDocumentTranslation(doc, trans) {
  if (!doc || !trans) return doc;
  const eventTrans = {};
  (trans.events || []).forEach(function (e) { eventTrans[e.id] = e; });
  const events = (doc.events || []).map(function (e) {
    const te = eventTrans[e.id];
    return te ? Object.assign({}, e, { headline: te.headline, summary: te.summary }) : e;
  });
  return Object.assign({}, doc, { events: events });
}

// ---------------------------------------------------------------------
// Derivations (real data, reorganized -- never fabricated)
// ---------------------------------------------------------------------

function impactForEvent(eventId, impactAnalysis) {
  if (!impactAnalysis) return null;
  return impactAnalysis.filter(function (ia) { return ia.event_id === eventId; })[0] || null;
}

// Risks = real impact assessments whose real direction is negative/mixed.
// Opportunities = real impact assessments whose real direction is positive.
// Sorted by magnitude (high>medium>low) then confidence -- deterministic,
// not re-ranked by any model call.
const _MAG_ORDER = { high: 3, medium: 2, low: 1 };
function computeRisksAndOpportunities(run) {
  const report = run && run.report;
  const impact = (report && report.impact_analysis) || [];
  const events = (run && run.events) || [];
  const byId = {};
  events.forEach(function (e) { byId[e.id] = e; });
  const risks = [];
  const opportunities = [];
  impact.forEach(function (ia) {
    const ev = byId[ia.event_id];
    if (!ev) return;
    const item = { impact: ia, event: ev };
    if (ia.direction === "negative" || ia.direction === "mixed") risks.push(item);
    else if (ia.direction === "positive") opportunities.push(item);
  });
  function sorter(a, b) {
    const ma = _MAG_ORDER[a.impact.magnitude] || 0, mb = _MAG_ORDER[b.impact.magnitude] || 0;
    if (mb !== ma) return mb - ma;
    return (b.impact.confidence || 0) - (a.impact.confidence || 0);
  }
  risks.sort(sorter);
  opportunities.sort(sorter);
  return { risks: risks, opportunities: opportunities };
}

function eventsByAgent(events) {
  const map = {};
  (events || []).forEach(function (e) {
    if (!map[e.agent]) map[e.agent] = [];
    map[e.agent].push(e);
  });
  return map;
}

// High-priority = ranked in the report's own top 3, OR judged high-magnitude
// impact -- both are real fields the backend already computed.
function isHighPriority(event, run) {
  if (event.priority_rank && event.priority_rank <= 3) return true;
  const impact = impactForEvent(event.id, run && run.report && run.report.impact_analysis);
  return !!(impact && impact.magnitude === "high");
}

function computeKpis(latestRun, runsList, previousRun) {
  const events = (latestRun && latestRun.events) || [];
  const highPriority = events.filter(function (e) { return isHighPriority(e, latestRun); }).length;
  const countries = new Set();
  events.forEach(function (e) { (e.entities && e.entities.countries || []).forEach(function (c) { countries.add(c); }); });
  const agentsRun = new Set(events.map(function (e) { return e.agent; }));
  const prevCount = previousRun ? (previousRun.events || []).length : null;
  return {
    eventCount: events.length,
    highPriority: highPriority,
    marketsMonitored: Math.max(countries.size, agentsRun.size),
    prevEventCount: prevCount,
    latestGeneratedAt: latestRun ? latestRun.generated_at : null,
    latestFailedSteps: latestRun ? (latestRun.trace || []).filter(function (s) { return s.status === "failed"; }).length : 0,
  };
}

// Trace + events, per real agent, for the Agents page -- a run's trace
// entry gives status/duration/error; its events (filtered by agent name)
// give the real count found that run.
function agentStats(run) {
  const trace = (run && run.trace) || [];
  const byAgent = eventsByAgent(run && run.events);
  return AGENT_ROSTER.map(function (a) {
    const step = trace.filter(function (s) { return s.agent === a.key; })[0] || null;
    return {
      key: a.key,
      purpose: a.purpose,
      sources: a.sources,
      status: step ? step.status : "idle",
      durationMs: step ? step.duration_ms : null,
      error: step ? step.error : null,
      eventCount: (byAgent[a.key] || []).length,
    };
  });
}
