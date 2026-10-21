=== baseline / golden (k=3) ===
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

=== alias / golden (k=3) ===
recall@3=1.00  MRR=1.00  abstention=1.00  (positives=15, negatives=4)
  false hits: 0 (a miss that returned an unrelated chunk instead of nothing)
  recall by kind: cross_lang  1.00
  recall by kind: direct      1.00
  recall by kind: synonym     1.00

=== baseline / held-out (k=3) ===
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

=== alias / held-out (k=3) ===
MISS [cross_lang] h-01: 'nombre de visiteurs étrangers entre janvier et août'
     expected=['tourism_stats'] got=[]
MISS [cross_lang] h-05: 'rendements des locations de courte durée'
     expected=['real_estate_market_snapshot'] got=[]
MISS [cross_lang] h-06: 'توقعات التضخم والنمو الاقتصادي'
     expected=['macro_morocco'] got=[]
MISS [cross_lang] h-07: 'أثر الجائحة على المعاملات العقارية'
     expected=['historical_precedents'] got=[]
MISS [cross_lang] h-08: 'السفر السياحي في فصل الصيف'
     expected=['tourism_stats'] got=[]
recall@3=0.38  MRR=0.31  abstention=1.00  (positives=8, negatives=2)
  false hits: 0 (a miss that returned an unrelated chunk instead of nothing)
  recall by kind: cross_lang  0.38

| Run | recall@k | MRR | abstention | false hits |
|---|---|---|---|---|
| baseline / golden | 0.73 | 0.70 | 1.00 | 0 |
| alias / golden | 1.00 | 1.00 | 1.00 | 0 |
| baseline / held-out | 0.25 | 0.25 | 1.00 | 0 |
| alias / held-out | 0.38 | 0.31 | 1.00 | 0 |
