# SPÉC — « BUTS D'AFFILÉE » (séries de buts consécutifs d'une même équipe)

Statut : PHASE 1 TERMINÉE le 10/09/2026 — 1 751 matchs des 5 grands
championnats (saison 2025-26) collectés via ESPN commentary, 0 rejeté après
corrections (own goals, noms accentués/traduits, noms à chiffres allemands).
Résultats clés : P(série 2+) = 57,0 % (D1 67,3 % → SP1/I1 53,7 %) ;
P(série 3+) = 21,2 % ; MOMENTUM = AUCUN effet détecté (52,7 % mesuré vs
52,2 % attendu sans mémoire, ±0,9) ; modèle Poisson exact à 0,6 pt du réel
en agrégé. Phase 2 (calibration walk-forward par match avec les λ du moteur,
puis affichage) : en attente feu vert utilisateur.
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
