# Morocco Macroeconomic Context

> Real, sourced content collected via live web search on 2026-09-09. This is
> genuine reference material for the RAG knowledge base (Phase 4) — not
> fixture/mock data. Update on the cadence noted in the Concept & Architecture
> Report (Section 6: monthly/quarterly as new releases appear).

## Monetary Policy

Bank Al-Maghrib kept its benchmark interest rate unchanged at **2.25%**
during its Q1 2026 meeting — the fifth consecutive hold. Cited reasons:
sustained growth in non-agricultural sectors, moderate inflation
projections, and heightened geopolitical uncertainty (notably Middle East
tensions). The bank also noted this reflects "the ongoing transmission of
earlier monetary easing" — previous rate cuts still filtering through the
economy. Policy stance is explicitly data-driven with "no predefined path
for tightening or easing," reviewed meeting-by-meeting.

Source (updated 2026-09-09, swapped to a second outlet plus the bank's own
release per "use other sources"): [Bank Al-Maghrib holds rate at 2.25% as
growth forecast rises to 5.2% — Hespress](https://en.hespress.com/140505-bank-al-maghrib-holds-interest-rate-at-2-25-for-fifth-meeting.html)

Primary/official source (found via search, not fetchable directly — the PDF
returned a 403 to automated retrieval, so it is cited but not the basis for
the figures above; a human can open it directly):
[Bank Al-Maghrib board meeting — official press release (PDF), March 2026](https://www.bkam.ma/en/content/download/840993/9118882/EN%20communiqu%C3%A9%20mars%202026.pdf)

Corroborating sources:
- [Bank Al-Maghrib Keeps Interest Rate Steady at 2.25% Amid Global Uncertainty — Morocco World News](https://www.moroccoworldnews.com/2026/03/283028/bank-al-maghrib-keeps-interest-rate-steady-at-2-25-amid-global-uncertainty/) (original primary source in this file, kept for cross-checking)
- [Morocco Interest Rate — Trading Economics](https://tradingeconomics.com/morocco/interest-rate)

## Growth and Inflation Forecasts

- **GDP growth:** Hespress reports **5.2%** for 2026 (up from 4.9% in 2025)
  and **3.1%** for 2027 (a base-effect decline), with non-agricultural
  growth averaging **4.2%** across 2026–2027. The earlier Morocco World News
  citation put 2026 growth at 5.6%; treat 5.2–5.6% as the credible range
  pending the next BAM release — this range itself is a useful example of
  the kind of cross-source discrepancy the debate stage is designed to
  surface once implemented.
- **Agricultural output:** projected to surge **+16%** in 2026 on an
  estimated 90-million-quintal cereal harvest, before falling **-7.6%** in
  2027 as production normalizes — a swing factor behind the growth forecast
  that the earlier source did not mention.
- **Inflation:** expected to remain subdued at **0.8%** in 2026, rising
  modestly to **1.4%** in 2027, aided by easing food and fuel prices.
- **Energy costs:** oil prices are anticipated to rise in 2026, a risk to
  the current account deficit and import costs — directly relevant to
  Morocco's energy-import exposure flagged in the Concept & Architecture
  Report's Global Economic & Markets Agent design.

## Why this matters for the Judge / RAG retrieval

Any monitoring-agent event mentioning Moroccan interest rates, inflation, or
growth should retrieve this document so the Judge can compare a new claim
(e.g., a news article citing a different growth number) against these
sourced, dated baseline figures rather than reasoning about it from model
memory alone.
