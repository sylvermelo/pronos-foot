# SPÉC — « BUTS D'AFFILÉE » (séries de buts consécutifs d'une même équipe)

Statut : PHASE 1 TERMINÉE et poussée le 10/09/2026 (`6b61d50`) — 1 751
matchs des 5 grands championnats (saison 2025-26) collectés via ESPN
commentary, 0 rejeté après corrections (own goals, noms accentués/traduits,
noms à chiffres allemands). Résultats clés : P(série 2+) = 57,0 %
(D1 67,3 % → SP1/I1 53,7 %) ; P(série 3+) = 21,2 % ; MOMENTUM = AUCUN effet
détecté (52,7 % mesuré vs 52,2 % attendu sans mémoire, ±0,9) ; modèle
Poisson exact à 0,6 pt du réel en agrégé.
**PHASE 2 (feu vert utilisateur « oui » du 10/09) : CONSTRUITE ET CALIBRÉE
EN LOCAL — voir section 8. NON poussée : démo locale montrée, feu vert de
mise en ligne séparé attendu.**
Rien ne va sur le site sans : mesures ≥ 60 matchs/palier, calibration
walk-forward, parité Python↔JS et feu vert utilisateur (REGLES.md).

## 1. Définition exacte

Une « série de k buts d'affilée » = k buts consécutifs de la MÊME équipe dans
le match, sans but de l'adversaire entre-temps. L'ordre compte.
- Le marché évoqué (1xBet, inaccessible) : « l'équipe X marquera-t-elle
  2 (ou 3) buts d'affilée dans le match ? ».
- Un but contre son camp compte pour l'équipe qui en BÉNÉFICE (attribution
  par le score qui progresse dans le texte ESPN, pas par l'équipe du joueur).
- Prolongations : exclues en v1 (matchs de championnat à 90 min seulement ;
  les coupes viendront plus tard, minute > 90 simplement conservée).

## 2. Position produit (honnêteté)

Aucune cote de marché gratuite n'existe pour cet évènement (The Odds API ne
le propose pas ; 1xBet = impasse définitive). Donc : PAS de « conseil » au
sens des sélections (pas de comparaison cote juste / marché possible).
Livrable visé = information chiffrée : « probabilité mesurée qu'une série de
2+ buts survienne dans ce match », comme le niveau de confiance, affichée à
titre informatif. Toute promesse de gain reste interdite.

## 3. Données

- **Source v1 : ESPN `summary.keyEvents`** (sans clé, via curl — REGLES §4).
  Chaque but : minute (`clock.displayValue`, ex. `45'+1'`), type (`Goal -
  Free-kick`, `Goal - Penalty`, …), texte avec le score après le but
  (`Goal! AEK Athens 1, LASK 0.`). Profondeur historique vérifiée le 10/09 :
  matchs de janvier 2025 accessibles (et au-delà, à confirmer en collectant).
- Couverture : les 21 ligues + 8 coupes déjà mappées (calendrier.ESPN_SLUGS).
- **Cache incrémental** : `data/buts_minutes.json` — une entrée par match
  (`div:id`), jamais re-collectée. Un match dont la séquence est incohérente
  (but manquant dans keyEvents, score final ≠ score reconstitué) est marqué
  `rejete` et EXCLU des mesures (principe conservateur : pas de donnée
  approximative).
- Source v2 (plus tard) : Understat `getLeagueData` + pages matchs (5 grands
  championnats depuis 2014) pour la profondeur historique. xg.py connaît déjà
  le point d'entrée ligue.

## 4. Mesures (phase 1 — ce que fait `buts_affilee.py rapport`)

Par ligue et global, sur les matchs valides :
1. P(série 2+ dans le match) — équipe domicile / extérieure / n'importe ;
2. P(série 3+ dans le match) — n'importe ;
3. Répartition par total de buts du match (0-1, 2-3, 4-5, 6+) ;
4. **Test de momentum** : P(le but suivant est de la même équipe | l'équipe
   vient de marquer) vs l'attente du modèle sans mémoire. C'est LA mesure qui
   dira si « l'élan » existe ou si le processus est sans mémoire (nul).
   ≥ 60 événements par palier avant toute conclusion (REGLES §1).
5. Écart en minutes entre deux buts d'une même série (distribution).

## 5. Modèle théorique (exact, sans simulation)

Sous l'hypothèse « processus de Poisson + buts indépendants » :
- nombre total de buts N ~ Poisson(λh + λa) ;
- chaque but est de l'équipe à domicile avec probabilité p = λh/(λh+λa),
  indépendamment (propriété classique de la fusion de deux processus de
  Poisson) ;
- donc P(série ≥ 2) = Σ_N P(N) × [1 − P(aucune série ≥ 2 | N)] où les
  séquences sans série sont exactement les 2 séquences alternées :
  P(aucune série ≥2 | N) = p^⌈N/2⌉(1−p)^⌊N/2⌋ + (1−p)^⌈N/2⌉ p^⌊N/2⌋ ;
- séries ≥ 3 : petite programmation dynamique sur (dernière équipe, longueur
  du run), N ≤ 20 (queue de Poisson négligeable).
- λh, λa : sortis du moteur existant (moteur_v3.score_matrix :
  λ = att·dfn·gamma, μ = att·dfn·s). La correction rho (Dixon-Coles) ne
  change pas l'INDÉPENDANCE des étiquettes de buts ; écart documenté.

Ce modèle est la référence « sans mémoire ». Tout écart MESURÉ (point 4.4)
est le seul candidat à un ajustement — jamais un coefficient inventé.

## 6. Critères d'acceptation pour passer en phase 2 (site)

- ≥ 1 500 matchs valides collectés sur ≥ 3 ligues (échantillon actuel : à
  construire — la collecte est incrémentale et reprenable) ;
- calibration walk-forward (pattern entraine.py) des P(série 2+) par décile :
  écart mesuré/attendu documenté ;
- si effet momentum mesuré (≥ 60 matchs/palier) : application uniquement dans
  le sens défavorable ou affichage informatif, jamais de coefficient magique ;
- parité Python ↔ JS + test app autonome + feu vert utilisateur.

## 7. Limites honnêtes (v1)

- keyEvents ESPN incomplet sur certains vieux matchs → match rejeté, pas
  d'imputation ;
- arrêts de jeu non modélisés (les minutes réelles importent peu pour le
  drapeau « série », l'ordre des buts suffit) ;
- pas de cote marché → pas de valeur/edge calculable : information seulement ;
- l'anachronisme des λ (modèle courant appliqué au passé) est évité en phase 1
  (pas de λ par match publié : uniquement des taux empiriques + test de
  momentum) ; la phase 2 utilisera le walk-forward.


## 8. PHASE 2 — probabilité par match (10/09, LOCAL, non poussé)

### 8.1 Ce qui a été construit

- `series_buts.py` = source unique Python (`p_no_run`, `p_serie`,
  `CORRECTION_SERIE2`, `p_serie2` corrigée) ; miroir JS identique généré
  par `genere_app.py` dans l'autonome (mêmes points, mêmes opérations).
- `serveur.py` : `/api/pronostic` et `/api/matchs` exposent `serie2`
  (CORRIGÉE) et `serie3` (brute), arrondis 4 décimales.
- `static/index.html` : fiche match = ligne « Buts d'affilée » (après
  « Score fleuve / écart ») + sous-libellé preuve actualisé.
- `test_app_autonome.js` : `serie2`/`serie3` comparés champ par champ —
  parité VALIDÉE (0 avertissement).
- `buts_affilee.py calibrer [--corriger]` : joint `backtest_results.csv`
  (colonnes `exp_h`/`exp_a` ajoutées au moteur) au cache ESPN par
  date + ligue + matching flou des équipes + vérification du score exact ;
  produit `data/buts_affilee_calibration.json`.
- Collecte étendue : Big 5 **2024-25 + 2025-26** = 3 502 matchs minutés.

### 8.2 Calibration walk-forward (n = 2 923 matchs joints, 2 saisons)

| Mesure | P(série 2+) | P(série 3+) |
|---|---|---|
| Modèle brut (λ backtest) | 52,5 % | 20,3 % |
| Réel observé (ESPN) | 57,3 % | 21,0 % |
| Écart | **+4,8 pts (biais)** | +0,7 pt (bruit) |

- Cause : le moteur de backtest sous-estime les totaux de buts (2,47
  prédits vs 2,72 réels/match sur les joints). Biais STABLE par saison :
  +4,6 pts (2024-25, n=1 464) et +4,9 pts (2025-26, n=1 459).
- Pire décile brut : +13,8 pts (les matchs à faible probabilité prédite
  produisent plus de séries que prévu — cohérent avec la sous-estimation
  des λ faibles).

### 8.3 Correction figée (biais mesuré puis corrigé, précédent corners)

- **Validation holdout** : correction ajustée sur 2024-25 SEULE →
  résidu −1,1 pt sur 2025-26 (saison non vue) ⇒ la correction se
  transfère ; sans correction le résidu serait +4,9 pts.
- Correction = interpolation linéaire par morceaux sur les déciles
  mesurés (292 matchs/décile ≥ minimum REGLES de 60), monotonisée.
  Constante `CORRECTION_SERIE2` dans `series_buts.py` + miroir JS.
- Résidus après correction (pool des deux saisons) : −0,1 pt / +0,1 pt.
- `serie3` NON corrigée volontairement (biais brut +0,7 pt dans le
  bruit). Recalibrer à chaque nouvelle saison collectée, puis mettre à
  jour les constantes des DEUX côtés (Python + JS) et relancer
  `test_app_autonome.js`.

### 8.4 Honnêteté

- La correction est un biais MESURÉ en walk-forward puis corrigé — pas un
  coefficient inventé. Afficher le brut serait afficher des probabilités
  ~5 pts trop basses : moins honnête, pas plus.
- La non-monotonie de `p_serie` en λ pour λ < 0,14 est une propriété
  exacte du modèle de Poisson fusionné (documentée dans `series_buts.py`),
  sans effet pratique : le moteur ne produit jamais λ < 0,3.
- Toujours aucune cote marché pour cet évènement ⇒ information chiffrée
  seulement, jamais « conseil », jamais dans les sélections suivies.


### 8.5 Séries PAR ÉQUIPE (ajout du 10/09, demande utilisateur)

L'utilisateur veut aussi : « 2 buts d'affilée oui/non, 3 buts d'affilée
oui/non » POUR CHAQUE ÉQUIPE (domicile, extérieur) en plus du match entier.

Formules : DP exacte sur le run de l'équipe visée (`p_no_run_team`,
`p_serie_team` dans `series_buts.py`) — vérifiée EXHAUSTIVEMENT contre
l'énumération de toutes les séquences (N ≤ 12, k = 2/3, p = 0,3/0,5/0,72,
les deux équipes : écarts < 1e-12).

Mesures walk-forward (mêmes 2 923 matchs joints) :

| Série | Modèle brut | Réel | Écart | 2024-25 | 2025-26 | Décision |
|---|---|---|---|---|---|---|
| 2+ DOMICILE | 36,8 % | 35,8 % | −1,0 pt | −2,4 | +0,3 | **BRUTE** (biais non stable ; correction holdout pire : +2,4 vs +0,3) |
| 2+ EXTÉRIEUR | 19,9 % | 28,2 % | **+8,3 pts** | +9,2 | +7,4 | **CORRIGÉE** (holdout : 7,4 → 2,4) |
| 3+ DOMICILE | 15,0 % | 12,9 % | −2,1 pts | −2,8 | −1,4 | **CORRIGÉE** (pool ±0,8) |
| 3+ EXTÉRIEUR | 5,5 % | 8,6 % | +3,1 pts | +4,0 | +2,2 | **CORRIGÉE** (pool +0,5/−1,3) |

- L'asymétrie RÉELLE dom ≈ 36-37 % / ext ≈ 27-28 % (séries 2+) est
  confirmée par deux échantillons indépendants : phase 1 (1 751 matchs
  2025-26, mesure directe) et calibration (2 923 joints, 2 saisons).
  Le modèle brut la ratait (36,8 / 19,9) → les corrections la rétablissent.
- Constantes figées : `CORRECTION_SERIE2_EXT`, `CORRECTION_SERIE3_DOM`,
  `CORRECTION_SERIE3_EXT` (+ miroir JS identique, vérifié point par point).
- Décile ≥ 292 matchs partout (≥ 60 exigés). Champs API : `serie2_dom`,
  `serie2_ext`, `serie3_dom`, `serie3_ext` ; UI = 3 lignes « oui / non »
  (match entier, domicile, extérieur). Parité serveur↔autonome VALIDÉE
  avec les 6 champs séries.
