=== bm25 t=0.40 / golden (k=3) ===
MISS [cross_lang] c-01: 'arrivées de touristes au Maroc'
     expected=['tourism_stats'] got=[]
MISS [cross_lang] c-02: 'taux directeur de la banque centrale'
     expected=['macro_morocco'] got=[]
MISS [cross_lang] c-05: 'سعر الفائدة الرئيسي لبنك المغرب'
     expected=['macro_morocco'] got=[]
MISS [cross_lang] c-06: 'عدد السياح الوافدين إلى المغرب'
     expected=['tourism_stats'] got=[]
recall@3=0.73  MRR=0.70  abstention=1.00  (positives=15, negatives=4)
  false hits: 0 (a miss that returned an unrelated chunk instead of nothing)
  recall by kind: cross_lang  0.33
  recall by kind: direct      1.00
  recall by kind: synonym     1.00

=== semantic t=0.40 / golden (k=3) ===
MISS [direct] d-03: 'COVID-19 impact on Moroccan real estate transactions'
     expected=['historical_precedents'] got=['real_estate_market_snapshot.md#Demoted — original pass, kept for the credibility contrast', 'market/marrakech_comparable_listings.md#Data source, method and limitations', 'real_estate_market_snapshot.md#Hotel construction pipeline — now with a named report and hard numbers']
recall@3=0.93  MRR=0.83  abstention=1.00  (positives=15, negatives=4)
  false hits: 1 (a miss that returned an unrelated chunk instead of nothing)
  recall by kind: cross_lang  1.00
  recall by kind: direct      0.80
  recall by kind: synonym     1.00

=== hybrid t=0.40 / golden (k=3) ===
recall@3=1.00  MRR=0.92  abstention=1.00  (positives=15, negatives=4)
  false hits: 0 (a miss that returned an unrelated chunk instead of nothing)
  recall by kind: cross_lang  1.00
  recall by kind: direct      1.00
  recall by kind: synonym     1.00

=== bm25 t=0.40 / held-out (k=3) ===
MISS [cross_lang] h-01: 'nombre de visiteurs étrangers entre janvier et août'
     expected=['tourism_stats'] got=[]
MISS [cross_lang] h-03: 'reprise du marché immobilier après la crise sanitaire'
     expected=['historical_precedents'] got=[]
MISS [cross_lang] h-05: 'rendements des locations de courte durée'
     expected=['real_estate_market_snapshot'] got=[]
MISS [cross_lang] h-06: 'توقعات التضخم والنمو الاقتصادي'
     expected=['macro_morocco'] got=[]
MISS [cross_lang] h-07: 'أثر الجائحة على المعاملات العقارية'
     expected=['historical_precedents'] got=[]
MISS [cross_lang] h-08: 'السفر السياحي في فصل الصيف'
     expected=['tourism_stats'] got=[]
recall@3=0.25  MRR=0.25  abstention=1.00  (positives=8, negatives=2)
  false hits: 0 (a miss that returned an unrelated chunk instead of nothing)
  recall by kind: cross_lang  0.25

=== semantic t=0.40 / held-out (k=3) ===
recall@3=1.00  MRR=0.94  abstention=1.00  (positives=8, negatives=2)
  false hits: 0 (a miss that returned an unrelated chunk instead of nothing)
  recall by kind: cross_lang  1.00

=== hybrid t=0.40 / held-out (k=3) ===
recall@3=1.00  MRR=0.94  abstention=1.00  (positives=8, negatives=2)
  false hits: 0 (a miss that returned an unrelated chunk instead of nothing)
  recall by kind: cross_lang  1.00

=== bm25 t=0.40 / rag_golden_set_extra (k=3) ===
MISS [negative] hn-03: 'luxury property prices in Dubai 2026'
     expected=[] got=['market/marrakech_comparable_listings.md#Data source, method and limitations', 'real_estate_market_snapshot.md#Demoted — original pass, kept for the credibility contrast', 'macro_morocco.md#Growth and Inflation Forecasts']
MISS [negative] hn-04: 'European Central Bank interest rate decision'
     expected=[] got=['macro_morocco.md#Monetary Policy', 'real_estate_market_snapshot.md#Residential market — now backed by an institutional source', 'historical_precedents.md#Why this matters for the Judge / RAG retrieval']
MISS [negative] hn-05: 'tourist arrivals in Spain this summer'
     expected=[] got=['tourism_stats.md#Arrivals and growth, January-August 2026']
MISS [negative] hn-06: "prix de l'immobilier à Paris en 2026"
     expected=[] got=['real_estate_market_snapshot.md#Demoted — original pass, kept for the credibility contrast', 'macro_morocco.md#Growth and Inflation Forecasts', 'tourism_stats.md#Arrivals and growth, January-August 2026']
MISS [negative] hn-08: "impact de la crise financière de 2008 sur l'immobilier améri"
     expected=[] got=['historical_precedents.md#How recovery unfolded']
recall@3=1.00  MRR=1.00  abstention=0.17  (positives=4, negatives=6)
  false hits: 0 (a miss that returned an unrelated chunk instead of nothing)
  recall by kind: cross_lang  1.00
  recall by kind: direct      1.00

=== semantic t=0.40 / rag_golden_set_extra (k=3) ===
MISS [negative] hn-03: 'luxury property prices in Dubai 2026'
     expected=[] got=['market/marrakech_comparable_listings.md#Villa (Vente) price per m2 by neighborhood, Marrakech (n >= 5)', 'real_estate_market_snapshot.md#Demoted — original pass, kept for the credibility contrast', 'real_estate_market_snapshot.md#Residential market — now backed by an institutional source']
MISS [negative] hn-04: 'European Central Bank interest rate decision'
     expected=[] got=['macro_morocco.md#Monetary Policy']
MISS [negative] hn-05: 'tourist arrivals in Spain this summer'
     expected=[] got=['tourism_stats.md#Arrivals and growth, January-August 2026']
MISS [negative] hn-06: "prix de l'immobilier à Paris en 2026"
     expected=[] got=['real_estate_market_snapshot.md#Residential market — now backed by an institutional source', 'market/marrakech_comparable_listings.md#Villa (Vente) price per m2 by neighborhood, Marrakech (n >= 5)', 'real_estate_market_snapshot.md#Demoted — original pass, kept for the credibility contrast']
MISS [negative] hn-07: "taux d'occupation des hôtels de luxe à Dubaï"
     expected=[] got=['real_estate_market_snapshot.md#Hotel construction pipeline — now with a named report and hard numbers', 'market/marrakech_comparable_listings.md#Villa (Vente) price per m2 by neighborhood, Marrakech (n >= 5)', 'real_estate_market_snapshot.md#Demoted — original pass, kept for the credibility contrast']
MISS [negative] hn-08: "impact de la crise financière de 2008 sur l'immobilier améri"
     expected=[] got=['historical_precedents.md#What happened', 'real_estate_market_snapshot.md#Residential market — now backed by an institutional source', 'historical_precedents.md#How recovery unfolded']
recall@3=1.00  MRR=0.88  abstention=0.00  (positives=4, negatives=6)
  false hits: 0 (a miss that returned an unrelated chunk instead of nothing)
  recall by kind: cross_lang  1.00
  recall by kind: direct      1.00

=== hybrid t=0.40 / rag_golden_set_extra (k=3) ===
MISS [negative] hn-03: 'luxury property prices in Dubai 2026'
     expected=[] got=['real_estate_market_snapshot.md#Demoted — original pass, kept for the credibility contrast', 'market/marrakech_comparable_listings.md#Villa (Vente) price per m2 by neighborhood, Marrakech (n >= 5)', 'real_estate_market_snapshot.md#Residential market — now backed by an institutional source']
MISS [negative] hn-04: 'European Central Bank interest rate decision'
     expected=[] got=['macro_morocco.md#Monetary Policy', 'real_estate_market_snapshot.md#Residential market — now backed by an institutional source', 'historical_precedents.md#Why this matters for the Judge / RAG retrieval']
MISS [negative] hn-05: 'tourist arrivals in Spain this summer'
     expected=[] got=['tourism_stats.md#Arrivals and growth, January-August 2026']
MISS [negative] hn-06: "prix de l'immobilier à Paris en 2026"
     expected=[] got=['real_estate_market_snapshot.md#Demoted — original pass, kept for the credibility contrast', 'real_estate_market_snapshot.md#Residential market — now backed by an institutional source', 'macro_morocco.md#Growth and Inflation Forecasts']
MISS [negative] hn-07: "taux d'occupation des hôtels de luxe à Dubaï"
     expected=[] got=['real_estate_market_snapshot.md#Hotel construction pipeline — now with a named report and hard numbers', 'market/marrakech_comparable_listings.md#Villa (Vente) price per m2 by neighborhood, Marrakech (n >= 5)', 'real_estate_market_snapshot.md#Demoted — original pass, kept for the credibility contrast']
MISS [negative] hn-08: "impact de la crise financière de 2008 sur l'immobilier améri"
     expected=[] got=['historical_precedents.md#How recovery unfolded', 'historical_precedents.md#What happened', 'real_estate_market_snapshot.md#Residential market — now backed by an institutional source']
recall@3=1.00  MRR=1.00  abstention=0.00  (positives=4, negatives=6)
  false hits: 0 (a miss that returned an unrelated chunk instead of nothing)
  recall by kind: cross_lang  1.00
  recall by kind: direct      1.00

| Run | recall@k | MRR | abstention | false hits |
|---|---|---|---|---|
| bm25 t=0.40 / golden | 0.73 | 0.70 | 1.00 | 0 |
| semantic t=0.40 / golden | 0.93 | 0.83 | 1.00 | 1 |
| hybrid t=0.40 / golden | 1.00 | 0.92 | 1.00 | 0 |
| bm25 t=0.40 / held-out | 0.25 | 0.25 | 1.00 | 0 |
| semantic t=0.40 / held-out | 1.00 | 0.94 | 1.00 | 0 |
| hybrid t=0.40 / held-out | 1.00 | 0.94 | 1.00 | 0 |
| bm25 t=0.40 / rag_golden_set_extra | 1.00 | 1.00 | 0.17 | 0 |
| semantic t=0.40 / rag_golden_set_extra | 1.00 | 0.88 | 0.00 | 0 |
| hybrid t=0.40 / rag_golden_set_extra | 1.00 | 1.00 | 0.00 | 0 |
