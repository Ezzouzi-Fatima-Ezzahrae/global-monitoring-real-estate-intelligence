# Knowledge Base — Real, Sourced Content

Everything in this folder is real, sourced content, not generated or invented, and Phase 4
retrieval (src/services/knowledge_base.py) is now live: every `##` section of every `.md` file
here (except this README) is chunked and made searchable, and the Judge stage (Phase 5,
src/agents/judge_agent.py) retrieves from it for every event it assesses. Retrieval is real,
lexical (BM25 keyword) search, not embeddings — there is no embedding endpoint configured
anywhere in this project, and this small a corpus does not need one. Its honest limit: it matches
on shared words, not meaning, so it will miss a relevant section that happens to use different
wording than the event being assessed. When a chunk is retrieved and used, it shows up in that
event's `ImpactAssessment.supporting_evidence` field as `<file>#<heading>`.

## Public-data seed (2026-09-09)

The four files below were collected via live web search and page retrieval on 2026-09-09. Each
cites its sources with working URLs so it can be independently checked.

| File | Content |
|---|---|
| `macro_morocco.md` | Bank Al-Maghrib rate decision, growth/inflation forecasts |
| `tourism_stats.md` | 2026 tourist arrival figures and trend |
| `historical_precedents.md` | COVID-19 real estate impact and recovery (2020-2022) |
| `real_estate_market_snapshot.md` | Current market commentary, sourced to Knight Frank and W Hospitality Group |

This seed still does not include primary government statistics accessed directly (Bank
Al-Maghrib, HCP bulletins are sourced through news coverage of those releases, not the bulletins
themselves) or a source-market breakdown for tourism (which countries send how many visitors) —
both flagged as open gaps in `tourism_stats.md` and the original version of this file.

## Company data (added 2026-09-15)

`company/` holds real, OCR-extracted content from scanned documents found in the project's
`Orchid data/data-orchide-scanné/` folder, cleaned up and cited back to their source file and
page count. Several of these describe opportunities that were under evaluation, not confirmed
Orchid Island holdings — each file says explicitly which is which, and flags open questions for
Fatima to confirm (current deal status, exact figures the OCR could not read reliably, and so
on). Treat anything marked "open question" in these files as unconfirmed until she answers.

| File | Content |
|---|---|
| `orchid_island_listing_sidi_ghanem.md` | Orchid Island's own branded listing: a professional building with shops/offices, Sidi Ghanem industrial zone, Marrakech |
| `land_parcels_route_de_casablanca.md` | Two real land title (Titre Foncier) records on the Marrakech-Casablanca road, near Marjane/Afriquia |
| `investment_opportunity_tingis_plaza.md` | Financial model and due-diligence request list for a "Tingis Plaza" wellness investment opportunity |
| `investment_opportunity_atlas_golf_marrakech.md` | Sales dossier for an existing, operating 20-hectare golf resort seeking a buyer/investor |
| `market_precedent_desert_agafay_2008.md` | 2008 Cushman & Wakefield pre-feasibility study for a different developer's desert resort project (historical precedent, not an Orchid Island asset) |

Three files found in the same `Orchid data/` folder were checked and excluded as fabricated, not
real: `data_CRI/dataset_registre_commerce_synthetique.csv`, `hcp_data/dataset_hcp_socio_eco_synthetique.csv`,
and `tourisme_data/tourisme_etablissements.csv` (invented company registry records, invented
socio-economic figures, and establishment names following an obvious generated pattern like
"Hotel Ocean_5", "Hotel Ocean_7"). None of their content was used anywhere in this project. A
fourth file, `data-orchide-scanné/contrat de cession .pdf`, is a real but unrelated confidential
legal document (a medical-clinic share sale, nothing to do with real estate) that appears to have
landed in this folder by accident — it was not used either.

## Market data (added 2026-09-15)

`market/marrakech_comparable_listings.md` aggregates 119,770 real scraped listing rows (Agenz,
Mubawab, Avito, Yakeey, collected as of the source files' own scrape dates) into Marrakech-wide
and neighborhood-level median price and price-per-m2 figures by property type, plus 24 fully
detailed named comparables for Palmeraie-area luxury villas. These are asking prices from
listings, not confirmed sale prices, and are not de-duplicated across platforms.

## What is still missing

- **Confirmed deal status** for the three "under evaluation" company files (Tingis Plaza, Atlas
  Golf Marrakech, and the two Route de Casablanca land parcels) — each file lists its own open
  questions.
- **Primary government statistics accessed directly** (Bank Al-Maghrib, HCP bulletins) — still
  sourced through news coverage, not the bulletins themselves.
- **Source-market breakdown for tourism** — still not available.
- **A fuller extraction of the 2008 Agafay study** — only its first ~8 pages (of 115) were OCR'd;
  its market-data and financial-estimate sections were not.
- **Confirmed, closed transaction prices** for any Orchid Island properties, to sit alongside the
  asking-price market data as a higher-trust comparable set.
- **Riad-specific comparable detail** at the same depth as the Palmeraie villa data — the
  aggregate Riad figures exist, but there is no named-comparable file for riads yet.

## How this gets used

For every event Judge assesses, it builds a search query from the event's headline, summary and
agent interpretation, retrieves up to 3 matching sections from everything in this folder, and (if
anything matched closely enough) includes that real, cited material in its prompt, instructing
the model to ground its rationale in it and name the source file when it actually relies on it.
An event that matches nothing here is a normal, honest outcome, not an error — Judge simply
reasons from the event's own content and general knowledge in that case, exactly as it always
has.
