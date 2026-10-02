# Marrakech comparable listings: aggregated real market data

Source: `Orchid data/immobilier_maroc_Price/` and `Orchid data/DataScrapingAvito/`, real listings
scraped from four Moroccan property platforms (Agenz, Mubawab, Avito, Yakeey) across the
Marrakech-Safi region. Processed and aggregated on 2026-09-15 from 119,770 individual listing
rows across 258 source files (241 files in the wider folder could not be parsed automatically,
mostly empty exports or files without a recognizable price column, and were skipped rather than
guessed at). These are asking prices from live/recent listings, not confirmed sale prices, and
they were not de-duplicated across platforms, so the same property may appear more than once if
it was listed on several sites. Use the figures below as market context, not as an appraisal.

## Marrakech-wide medians by transaction type and property type (all neighborhoods, n >= 20)

Price per m2 is only computed from listings that stated both a price and a surface area; the
sample size for that column ("n with m2") is smaller than the listing count and is shown
separately.

| Transaction | Property type | Listings (n) | Median price (DH) | Median price/m2 (DH) | n with m2 |
|---|---|---|---|---|---|
| Vente | Villa | 5,400 | 5,200,000 | 13,667 | 4,503 |
| Vente | Maison | 4,983 | 2,500,000 | 13,757 | 3,691 |
| Vente | Appartement | 13,880 | 1,150,000 | 14,545 | 12,492 |
| Vente | Riad | 1,238 | 2,600,000 | 21,277 | 947 |
| Vente | Terrain | 6,115 | 1,300,000 | 5,469 | 2,059 |
| Vente | Studio | 323 | 1,140,000 | 20,930 | 319 |
| Vente | Duplex | 249 | 1,521,000 | 13,559 | 237 |
| Location | Appartement | 23,727 | 5,000 /month | 18,557 | 132 |
| Location | Villa | 3,291 | 30,000 /month | 9,868 | 28 |
| Location | Maison | 369 | 12,000 /month | 12,872 | 6 |

Note the rental price/m2 samples are small (n with m2 under 150 in every row). Treat those
figures as indicative only, not as a reliable benchmark.

## Villa (Vente) price per m2 by neighborhood, Marrakech (n >= 5)

This is the more useful cut for a luxury operator: the citywide villa median above blends
everything from Targa to the Palmeraie, and those markets are not comparable.

| Neighborhood | Listings (n) | Median price (DH) | Median price/m2 (DH) | n with m2 |
|---|---|---|---|---|
| Amelkis | 71 | 16,771,000 | 27,129 | 67 |
| Route Amizmiz / Route d'Amizmiz | 86 | 8,115,000 | 24,577 | 74 |
| Palmeraie | 72 | 24,543,000 | 21,507 | 64 |
| Agdal | 26 | 5,588,950 | 20,693 | 19 |
| Route de l'Ourika | 62 | 6,455,318 | 16,356 | 42 |
| Targa | 137 | 4,200,000 | 10,417 | 115 |
| Route de Fes | 5 | 4,200,000 | 7,000 | 3 |
| Hivernage | 8 | 700,000 | 4,828 | 5 |

Amelkis and the Palmeraie are clearly the top of the Marrakech villa market by price per m2 in
this dataset; Hivernage's low figure here likely reflects a small, non-representative sample
(n=8) rather than an actual soft market, since Hivernage is generally a central, sought-after
area, so treat that row with particular caution.

## Named comparables: Palmeraie luxury villas (Vente), full detail

These 24 listings come from two dedicated files that a previous data-collection pass built
specifically for Palmeraie-area luxury villas: `agenz_palmeraie_villas_structured (1).xlsx`
(12 listings, mostly Ennakhil/Palmeraie) and `yakeey_villas_palmeraie.xlsx` (8 listings with
usable prices, Palmeraie Extension / Ain Iti / Route de Fes). They are kept as named comparables,
not folded into the aggregate above, because they carry much richer detail (bedroom count, pool,
staff quarters, security, plot vs. built-up area) than the bulk-scraped data.

### Agenz, quartier Ennakhil (Palmeraie), Marrakech

Field values below are read directly from the source spreadsheet's own yes/no columns (pool,
heated, garden, terrace, staff room), not inferred from the free-text description, so they should
be reliable.

| Price (DH) | Plot (m2) | Built (m2) | Beds | Baths | Pool | Garden | Terrace | Staff room | Age |
|---|---|---|---|---|---|---|---|---|---|
| 14,000,000 | 2,400 | 550 | 5 | 3 | Yes, heated | Yes | Yes | Yes | n/a |
| 9,500,000 | n/a | 400 | 5 | 4 | Yes | Yes | Yes | Yes | n/a |
| 5,650,000 | 485 | 280 | 4 | 4 | Yes | No | No | Yes | n/a |
| 14,000,000 | 2,100 | 690 | 4 | 5 | Yes | Yes | No | No | n/a |
| 5,200,000 | 1,096 | 288 | 3 | 2 | Yes | Yes | Yes | Yes | 6-10 years |
| 5,500,000 | 1,000 | 300 | 4 | 4 | Yes | Yes | Yes | No | n/a |
| 9,000,000 | 8,000 | 650 | 5 | 5 | See note | No | Yes | No | n/a |
| 5,500,000 | n/a | 200 | 6 | 4 | Yes | Yes | Yes | No | n/a |
| 4,700,000 | n/a | 280 | 5 | 4 | Yes | Yes | Yes | Yes | n/a |
| 17,000,000 | 4,000 | 350 | 5 | 6 | No | No | Yes | No | n/a |
| 3,800,000 | n/a | 450 | 3 | 3 | Yes | Yes | No | No | 1-5 years |

Note on the 9,000,000 DH row: the source spreadsheet marks its own "piscine" (has a pool) column
as No but its "piscine_chauffee" (pool is heated) column as Yes, which is self-contradictory. The
listing's free text separately describes a 14x5m heated pool, so a pool is very likely present;
this is flagged here as a data-quality issue in the source file rather than silently corrected.
"n/a" in Plot or Age means the source spreadsheet left that field blank for that listing, not that
the value is zero.

### Yakeey, Palmeraie Extension / Ain Iti / Route de Fes, Marrakech

| Reference | Price (DH) | Plot (m2) | Built (m2) | Beds | Baths | Quartier |
|---|---|---|---|---|---|---|
| MI177676 | 2,400,000 | 172 | 120 | 2 | 2 | Palmeraie Extension |
| MI090793 | 3,600,000 | 425 | 580 | 6 | 5 | Palmeraie Extension |
| MI118494 | 5,200,000 | 1,000 | 400 | 4 | 3 | Ain Iti |
| MI179350 | 5,200,000 | 1,094 | 300 | 3 | 2 | Palmeraie Extension |
| MI170948 | 3,400,000 | 2,685 | 300 | 4 | 3 | Palmeraie Extension |
| MI116047 | 100,000,000 | 8,936 | 2,500 | 12 | 6 | Palmeraie |
| MI174605 | 18,000,000 | 11,878 | 1,100 | 5 | 4 | Palmeraie |
| MI048356 | 70,250,000 | 39,188 | 4,457 | 48 | 0 (unlisted) | Route de Fes - Douar Tamasna |

The last three rows (100M, 70.25M, 18M DH) are large estate-scale properties, not typical
single-family villas, and pull any naive average sharply upward. This is exactly why the
median (not mean) figures earlier in this document are the safer number to quote.

## How Judge should use this

When an event concerns Marrakech villa demand, pricing, or a specific neighborhood named above,
this file gives real, dated (2026-09-15 collection) comparable figures to ground a
sector-or-market-affected call and a magnitude estimate, instead of reasoning from general
knowledge alone. It does not give transaction-confirmed prices (only asking prices), does not
cover every neighborhood Orchid Island might care about, and should not be treated as
professional appraisal advice. Say so if a Judge assessment leans heavily on a single named
comparable.

## Open questions for Fatima

- Which specific neighborhoods or property types should get this treatment next (Riad
  medina-quality data, for instance, is much thinner than villa data here)?
- Is there a preferred data refresh cadence (this snapshot reflects whatever was scraped as of
  the files' own collection dates, not necessarily today)?
- Would confirmed (closed) transaction prices, if Orchid Island has any internally, be worth
  adding as a separate, higher-trust comparable set?
