// format.js — shared display formatting helpers.
"use strict";

function fmtDateTime(iso, localeTag) {
  if (!iso) return "";
  try { return new Date(iso).toLocaleString(localeTag || "en-US", { dateStyle: "medium", timeStyle: "short" }); }
  catch (_) { return iso; }
}
function fmtDate(iso, localeTag) {
  if (!iso) return "";
  try { return new Date(iso).toLocaleDateString(localeTag || "en-US", { dateStyle: "medium" }); }
  catch (_) { return iso; }
}
function fmtTime(iso, localeTag) {
  if (!iso) return "";
  try { return new Date(iso).toLocaleTimeString(localeTag || "en-US", { timeStyle: "short" }); }
  catch (_) { return iso; }
}
function fmtRelative(iso, t) {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (isNaN(then)) return "";
  const diffMs = Date.now() - then;
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return t("timeJustNow");
  if (mins < 60) return t("timeMinutesAgo", mins);
  const hours = Math.round(mins / 60);
  if (hours < 24) return t("timeHoursAgo", hours);
  const days = Math.round(hours / 24);
  return t("timeDaysAgo", days);
}
function escapeHtml(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
function clamp01(n) { return Math.max(0, Math.min(1, n || 0)); }
