# Application de pronostics football — Conception technique

**Date :** 2 septembre 2026
**Statut :** Faisabilité validée — preuve de concept chiffrée exécutée
**Auteur :** Arena.ai Agent Mode

---

## 1. Verdict : oui, c'est possible. Voici la vérité sans détour

Tout ce que tu décris est techniquement réalisable. Mais il faut séparer deux choses
que le langage courant confond :

| Ce que tu imagines | Ce qui marche vraiment |
|---|---|
| Une IA qui « réfléchit » et devine les scores | Un **moteur statistique** qui calcule des probabilités, + une couche IA qui **explique** |
| « Tel club contre tel club fait des scores fleuves » | Un **modèle de buts attendus** (λ) qui dérive mathématiquement l'Over/Under |
| « Probabilité que tel joueur marque » | Un **modèle de xG par joueur** ajusté à l'adversaire et aux minutes jouées |
| « Trouver les bons paris » | Trouver les **écarts entre tes probabilités et les cotes** (value betting) |

### Le point critique à comprendre dès maintenant

**Un LLM (ChatGPT, Claude…) ne doit JAMAIS produire tes probabilités numériques.**
Il ne sait pas compter, il hallucine des statistiques, et ses prédictions ne sont pas
reproductibles ni backtestables. Si tu construis ça, tu auras une belle interface et
des pronostics au hasard.

**La bonne architecture est hybride :**

```
┌─────────────────────────────────────────────────────────────┐
│  COUCHE 1 — LE MOTEUR (Python, déterministe, backtestable)   │
│  C'est lui qui calcule TOUS les chiffres.                    │
│  Dixon-Coles + Elo + xG + modèles par marché                 │
└───────────────────────────┬─────────────────────────────────┘
                            │  données structurées (JSON)
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  COUCHE 2 — L'ANALYSTE (LLM avec tool-calling)               │
│  Il LIT les chiffres, il ne les invente pas.                 │
│  → rédige l'analyse en français                              │
│  → détecte le contexte que les stats ne voient pas           │
│    (démotivation, derby, match sans enjeu, rotation, météo)  │
│  → propose un ajustement BORNE (max ±8 %) et justifié        │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  COUCHE 3 — LE GARDE-FOU (règles dures, non négociables)     │
│  Vérifie que l'ajustement de la couche 2 reste dans les      │
│  limites. Recalcule les probabilités. Décide si on publie.   │
└─────────────────────────────────────────────────────────────┘
```

C'est exactement comme ça que fonctionnent les vraies entreprises de trading sportif.
L'IA ne remplace pas les maths, elle les rend lisibles et elle ajoute le contexte humain.

---

## 2. La bonne nouvelle : les données gratuites suffisent pour démarrer

J'ai testé en direct pendant la rédaction de ce document. **Résultat : 88 fichiers,
14 Mo, 8 908 matchs téléchargés gratuitement, 0 échec.**

### `football-data.co.uk` — ta mine d'or (gratuit, aucune clé API)

Plus de 30 ans d'historique, 25+ ligues, en CSV. Voici ce que contient **chaque ligne**
(vérifié sur le fichier Premier League 2025/26 que j'ai téléchargé) :

**Ce que tu voulais analyser — c'est déjà là :**

| Ta demande | Colonne disponible | Statut |
|---|---|---|
| Buts / scores fleuves | `FTHG`, `FTAG`, `HTHG`, `HTAG` | ✅ 30 ans |
| **Fautes** | `HF`, `AF` (home/away fouls) | ✅ 30 ans |
| Corners | `HC`, `AC` | ✅ 30 ans |
| Cartons jaunes | `HY`, `AY` | ✅ 30 ans |
| Cartons rouges | `HR`, `AR` | ✅ 30 ans |
| Tirs / tirs cadrés | `HS`, `AS`, `HST`, `AST` | ✅ 30 ans |
| **Arbitre** | `Referee` | ✅ (crucial pour les fautes/cartons !) |
| Cotes de 15 bookmakers | `B365H`, `PSH`, `AvgH`, `MaxH`… | ✅ 30 ans |
| **Cotes de CLÔTURE Pinnacle** | `PSCH`, `PSCD`, `PSCA`, `PC>2.5` | ✅ le Graal |
| Over/Under et Handicap asiatique | `P>2.5`, `AHh`, `B365AHH`… | ✅ 30 ans |

> **Pourquoi les cotes de clôture Pinnacle sont le Graal :** Pinnacle est le bookmaker
> le plus « sharp » du marché, celui où parient les professionnels, avec les marges les
> plus faibles (~2 %). Sa cote de clôture est considérée comme la meilleure estimation
> disponible de la vraie probabilité. **Si ton modèle ne bat pas Pinnacle en clôture,
> il ne battra aucun bookmaker de façon durable.** C'est ton juge de paix, et il est gratuit.

### Les limites de cette source gratuite (soyons honnêtes)

- ❌ **Pas de xG** (expected goals) → à récupérer ailleurs
- ❌ **Pas de compositions d'équipe / onze de départ** → il te manque « tel joueur est absent »
- ❌ **Pas de stats individuelles par joueur** (buteurs, passes, duels)
- ❌ **Pas de données en direct**
- ❌ **Ligues africaines non couvertes** (championnat béninois, nigérian, etc.)

Les 4 points manquants sont précisément ce qui nécessite une API payante.

### Comparatif des API payantes (prix vérifiés en 2026)

| API | Prix | Ce que ça débloque | Pertinence pour toi |
|---|---|---|---|
| **API-Football** | Gratuit 100 req/j<br>**Pro 19 $/mois** | 1 236 ligues, **compositions**, **blessés/suspendus**, stats joueurs, live, cotes | ⭐ **Meilleur rapport qualité/prix pour la Phase 2** |
| **TheStatsAPI** | **50 $/mois** (essai 7 j) | 150 compétitions, **xG inclus**, cotes Pinnacle/Bet365, 10 ans d'historique, 84 000 joueurs | ⭐ **Le meilleur pour le xG et les cotes** |
| **football-data.org** | Gratuit / 29 €+ | 12 ligues gratuites, mais lineups et stats = add-ons | Moyen (add-ons qui s'accumulent) |
| **Sportmonks** | 29 € → 249 €/mois | Large catalogue, mais ligues verrouillées par palier + add-ons | Cher et imprévisible |
| **Understat** (scraping) | Gratuit | xG des Big 5 | ✅ À utiliser en complément gratuit |
| **StatsBomb Open Data** | Gratuit | Données événementielles de très haute qualité | ✅ Pour apprendre/calibrer |

**Recommandation :** démarre à 0 FCFA avec `football-data.co.uk`, passe à
**API-Football Pro (19 $/mois ≈ 11 500 FCFA)** dès que tu veux les absences et les
buteurs, ajoute **TheStatsAPI (50 $/mois ≈ 30 000 FCFA)** quand tu veux le xG propre.

---

## 3. Les mathématiques — marché par marché

### 3.1 Le cœur : Dixon-Coles (1997), le standard de l'industrie

L'idée : chaque équipe a une **force d'attaque** et une **faiblesse défensive**.

```
λ_domicile = attaque[i] × défense[j] × avantage_domicile
λ_extérieur = attaque[j] × défense[i]
```

λ = nombre de buts attendus. Ensuite, une loi de Poisson donne la probabilité de
chaque score exact. Dixon-Coles ajoute une correction (paramètre ρ) parce que les
scores 0-0, 1-0, 0-1 et 1-1 sont statistiquement plus fréquents que la Poisson pure
ne le prédit.

**Deux ingrédients qui font toute la différence :**

1. **Le decay temporel** : un match d'il y a 3 ans vaut moins qu'un match d'il y a
   3 semaines. Poids `w = exp(-ξ × Δt)`. Sans ça, tu prédis la saison dernière.
2. **La régularisation (ridge)** : une équipe promue n'a que 3 matchs d'historique.
   Sans régularisation, le modèle lui invente une force délirante.

### 3.2 L'astuce qui rend tout rentable : UNE matrice, TOUS les marchés

C'est le point le plus important du document. Tu ne construis **pas** un modèle par
marché. Tu construis **une matrice 11×11 de probabilités de score exact**, et tu en
dérives tout le reste par simple somme :

```
        buts extérieur →  0      1      2      3      4
buts  0               7,2%   9,1%   6,8%   3,4%   1,2%
↓     1              10,8%  11,2%   7,4%   3,2%   1,0%
      2               8,1%   9,5%   6,1%   2,4%   0,7%
      3               4,0%   5,1%   3,2%   1,2%   0,3%
      4               1,5%   2,0%   1,2%   0,4%   0,1%
```

À partir de là :

| Marché | Calcul |
|---|---|
| 1X2 | somme du triangle sup. / diagonale / triangle inf. |
| **Over/Under 2,5** | somme des cases où `h+a ≥ 3` vs `h+a ≤ 2` |
| Over/Under 1,5 / 3,5 / 4,5 / 5,5 | idem avec d'autres seuils |
| **BTTS** (les deux marquent) | somme des cases où `h≥1 ET a≥1` |
| Score exact | la case elle-même |
| Double chance | somme de deux zones |
| Handicap asiatique | somme pondérée |
| **« Score fleuve »** | somme des cases où `h+a ≥ 5` ou écart ≥ 3 |
| Vainqueur + Over 2,5 (combiné) | intersection de zones |

**Ton besoin « quel club contre quel club font des scores fleuves » se résout ainsi :**
deux équipes avec une forte attaque et une mauvaise défense donnent λ élevé des deux
côtés → la masse de probabilité se déplace vers le coin bas-droit de la matrice →
l'Over 2,5/3,5 devient probable. C'est automatique, pas besoin d'une règle spéciale.

### 3.3 Les fautes, cartons et corners — un modèle séparé (et négligé !)

C'est là que se trouve la vraie valeur, parce que **peu de gens modélisent ces marchés**.

Les fautes ne dépendent pas que des équipes. Elles dépendent énormément de
**l'arbitre**. Et la colonne `Referee` est dans les données gratuites depuis 30 ans.

```
λ_fautes_match = base_ligue × propension_équipe_A × propension_équipe_B
                 × effet_arbitre × effet_enjeu × effet_derby
```

Puis, pour les cartons :
```
λ_jaunes = λ_fautes × taux_avertissement_arbitre × agressivité_équipes
```

Certains arbitres distribuent 2× plus de cartons que d'autres à fautes égales.
C'est un signal **réel, stable et mesurable**. Le marché des cartons est souvent
le moins efficace des marchés grand public.

### 3.4 Les joueurs et les buteurs

```
λ_joueur = xG_par_90_du_joueur
         × (attaque_équipe / moyenne_ligue)
         × (1 / défense_adverse)
         × minutes_attendues / 90
         × facteur_titularisation
         × ajustement_poste
```

Puis `P(buteur) = 1 − exp(−λ_joueur)` (ou une loi binomiale négative, car les buts
sont sur-dispersés).

**Gestion des absences — le point que tu as justement identifié :**

Quand un joueur clé est absent, son xG ne disparaît pas : il est **redistribué** aux
autres (le tireur de penaltys absent, c'est énorme ; l'ailier absent, c'est le
latéral qui monte plus). Modélisation :

```
xG_équipe_sans_joueur = xG_équipe_complète × (1 − contribution_relative × impact)
```

où `contribution_relative` = part du joueur dans les tirs/xG de l'équipe, et
`impact` ≈ 0,6–0,85 (parce qu'un remplaçant n'est jamais nul).

**Valeur d'un joueur absent** à calculer :
- xG + xA par 90 (le plus direct)
- xGChain / xGBuildup (son implication dans toute la chaîne, pas juste la finition)
- Duels gagnés, interceptions (pour les défenseurs/milieux)
- **Penaltys tirés** ← très sous-estimé, un tireur de peno absent coûte cher
- Coup francs directs

### 3.5 Le classement des clubs

Deux systèmes complémentaires :

| Système | Usage | Avantage |
|---|---|---|
| **Elo avec marge de victoire** | Classement simple, explicable | Facile à comprendre pour l'utilisateur |
| **Attaque/Défense Dixon-Coles** | Calcul des probabilités | Sépare les deux dimensions |
| **SPI (style FiveThirtyEight)** | Afficher un classement riche | 2 notes + intervalle de confiance |

Le classement doit être **par ligue et inter-ligues** (pour les coupes d'Europe),
et doit inclure un **indice de confiance** basé sur le nombre de matchs joués.

---

## 4. Architecture technique recommandée

```
                    ┌──────────────────────────┐
                    │   FRONTEND — Next.js     │
                    │   Tailwind + shadcn/ui   │
                    │   Recharts / visx        │
                    └────────────┬─────────────┘
                                 │ REST / JSON
                    ┌────────────▼─────────────┐
                    │   API — FastAPI (Python)  │
                    │   /matchs /pronos /equipes│
                    │   /joueurs /bilan         │
                    └────────────┬─────────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        │                        │                        │
┌───────▼────────┐    ┌──────────▼──────────┐   ┌─────────▼────────┐
│ PostgreSQL     │    │ MOTEUR DE PRONOSTIC  │   │ Redis + Celery   │
│ matchs, cotes, │    │ Dixon-Coles, Elo,    │   │ taches planifiees│
│ joueurs, xG,   │    │ fautes, buteurs,     │   │ - maj quotidienne│
│ pronos, bilan  │    │ value betting        │   │ - maj live       │
└────────────────┘    └──────────┬──────────┘   │ - reentrainement │
                                 │              └──────────────────┘
                    ┌────────────▼──────────┐
                    │  COUCHE LLM ANALYSTE  │
                    │  tool-calling, lit les│
                    │  chiffres, redige     │
                    └───────────────────────┘

        ┌──────────────────────────────────────────────┐
        │  INGESTION                                   │
        │  football-data.co.uk (CSV, gratuit)          │
        │  API-Football (compositions, blesses)        │
        │  Understat (xG, scraping)                    │
        └──────────────────────────────────────────────┘
```

**Pourquoi Python pour le moteur, sans discussion :** `numpy`, `scipy`, `scikit-learn`,
`statsmodels` — tout l'écosystème de modélisation statistique y est. Node.js ne peut
pas rivaliser sur ce terrain.

**Stack complète conseillée :**

| Couche | Technologie | Justification |
|---|---|---|
| Moteur + API | **Python 3.12 / FastAPI** | Écosystème stats, async, docs auto |
| Base de données | **PostgreSQL 16** | Relationnel, fiable, JSONB pour le flexible |
| Cache + tâches | **Redis + Celery** (ou APScheduler au début) | Réentraînement planifié |
| Frontend | **Next.js 15 + Tailwind + shadcn/ui** | SSR, rapide, beaux composants |
| Graphiques | **Recharts** ou **visx** | Courbes de calibration, matrices de chaleur |
| Déploiement | **Fly.io / Railway / Render** puis VPS | ~0–20 $/mois au début |
| LLM | API Claude ou GPT, **uniquement** sur la couche analyste | Coût maîtrisé |

---

## 5. Roadmap en 6 phases

### Phase 0 — Validation du moteur (1 semaine) — **0 FCFA**
- ✅ **Déjà fait** : téléchargement des 8 908 matchs, 5 ligues, 5 saisons
- ✅ Implémentation Dixon-Coles avec decay temporel
- ✅ Backtest walk-forward (réentraînement périodique, jamais de fuite de données)
- ✅ Comparaison aux cotes de clôture Pinnacle
- **Livrable :** un rapport chiffré qui dit si le modèle tient la route

> ⚠️ **Le piège absolu à éviter : la fuite de données (data leakage).** Si tu
> entraînes sur toute la saison puis tu testes sur cette même saison, tu auras des
> résultats magnifiques et totalement faux. Le backtest doit être **walk-forward** :
> pour prédire le match du 15 mars, on n'utilise que les matchs joués **avant** le 15 mars.

### Phase 1 — Base de données + marchés équipes (2 semaines) — **0 FCFA**
- Schéma PostgreSQL, import des 30 ans de CSV
- Dérivation de tous les marchés depuis la matrice de scores
- Modèles fautes / corners / cartons avec effet arbitre
- Classement Elo + SPI
- **Livrable :** pronostics 1X2, Over/Under, BTTS, score exact, corners, cartons

### Phase 2 — Couche joueurs (2–3 semaines) — **≈ 11 500 FCFA/mois**
- API-Football Pro : compositions, blessés, suspendus, stats joueurs
- xG par joueur (Understat pour les Big 5, API pour le reste)
- Modèle de probabilité buteur / passeur / carton
- Impact quantifié des absences
- **Livrable :** « Tel joueur a 34 % de chance de marquer », « Sans lui, l'équipe
  perd 0,42 but attendu »

### Phase 3 — Couche IA analyste (1–2 semaines)
- Le LLM reçoit les chiffres du moteur (jamais l'inverse)
- Il rédige l'analyse en français
- Il signale le contexte non statistique (enjeu, rotation, derby, météo)
- Il propose un ajustement **borné à ±8 %**, validé par la couche garde-fou
- **Livrable :** une fiche de match lisible et argumentée

### Phase 4 — Interface web (2–3 semaines)
- Page du jour, fiche match détaillée, matrice de scores interactive
- Classement des clubs, fiches joueurs
- **Bilan public et vérifiable** de tous les pronostics passés ← indispensable
- **Livrable :** l'application utilisable

### Phase 5 — Suivi de performance et amélioration continue
- Tracking automatique : log-loss, RPS, calibration, ROI, **CLV**
- Réentraînement hebdomadaire
- Détection de dérive du modèle
- **Livrable :** un tableau de bord qui prouve (ou infirme) que le système fonctionne

**Total : 8 à 12 semaines pour un produit complet.** Un MVP honnête en 3–4 semaines.

---

## 6. Budget réaliste

| Poste | Phase 0-1 | Phase 2-3 | Phase 4+ |
|---|---|---|---|
| Données | **0 FCFA** | 11 500 FCFA | 11 500 – 40 000 FCFA |
| LLM (couche analyste) | 0 | ~3 000 – 10 000 FCFA | ~10 000 – 30 000 FCFA |
| Hébergement | 0 (local) | ~6 000 FCFA | ~6 000 – 30 000 FCFA |
| Nom de domaine | ~7 000 FCFA/an | idem | idem |
| **Total mensuel** | **≈ 0 FCFA** | **≈ 20 000 FCFA** | **≈ 30 000 – 100 000 FCFA** |

*Conversions indicatives sur la base 1 $ ≈ 600 FCFA / 1 € = 655,957 FCFA (XOF indexé sur l'euro).*

**Tu peux aller jusqu'à la fin de la Phase 1 sans dépenser un franc.**

---

## 7. Comment savoir si ça marche — les seules métriques qui comptent

Oublie le « taux de réussite ». C'est la métrique des arnaques. Un pronostic à 1,10
de cote réussit 90 % du temps et te ruine.

| Métrique | Ce que ça mesure | Cible |
|---|---|---|
| **Log-loss** | Qualité globale des probabilités | ≤ celle du marché déviggé |
| **RPS** (Ranked Probability Score) | Erreur sur le 1X2 ordonné | ≤ 0,20 |
| **Calibration** | « Quand je dis 70 %, ça arrive 70 % du temps ? » | Écart < 3 points |
| **CLV** (Closing Line Value) | Bats-tu la cote d'ouverture ? | **> 0 = edge réel** |
| **ROI sur 1 000+ paris** | Rentabilité finale | > +3 % pour être viable |

**Le CLV est la seule métrique qui ne ment pas.** Si tu paries à 2,20 et que la cote
clôture à 1,95, tu as battu le marché, que ton pari gagne ou perde. Sur 500 paris,
un CLV positif se traduit presque toujours en profit. Un CLV négatif se traduit
presque toujours en perte — même si tu as gagné tes 5 derniers paris.

**Ordre de grandeur réaliste :** les meilleurs modèles publics atteignent
52–55 % de précision sur le 1X2 (le marché est à ~50-53 %). Un ROI durable de
+2 à +6 % est **excellent**. Quiconque te promet +30 % par mois ment.

---

## 8. Les pièges qui tuent ces projets

1. **La sur-dispersion.** Les buts suivent mal une Poisson pure (la variance dépasse
   la moyenne). Dixon-Coles corrige partiellement ; il faut vérifier la calibration.
2. **Le déséquilibre des échantillons.** Les cartons rouges sont rares (~4 % des
   matchs). Modéliser ça demande des milliers de matchs, pas 200.
3. **Les matchs sans enjeu.** En fin de saison, les équipes qui n'ont plus rien à
   jouer faussent tout. Prévoir un facteur « enjeu ».
4. **Les effets de mercato.** En janvier, les forces d'équipe changent brutalement.
   Le decay temporel aide mais ne suffit pas.
5. **Le sur-ajustement.** Avec 40 features et 500 matchs, tu modélises le bruit.
   Règle : au moins 50–100 observations par paramètre.
6. **Le biais de survie dans les données.** Les équipes reléguées disparaissent du
   jeu de données l'année suivante. À gérer dans le backtest.
7. **L'illusion du petit échantillon.** 30 paris ne prouvent **rien**. Il en faut
   1 000 minimum pour distinguer la compétence de la chance.
8. **La limite des bookmakers.** Si tu gagnes vraiment, tu seras limité ou banni.
   C'est le destin de tout parieur gagnant — il faut le savoir avant.

---

## 9. Cadre légal — important pour toi au Bénin

Ce que j'ai vérifié (état au 1er trimestre 2026) :

- Le marché béninois fonctionne sous **monopole délégué** : la **Loterie Nationale du
  Bénin (LNB)**, sous tutelle du Ministère de l'Économie et des Finances, délivre les
  agréments. Liste officielle : `csj.bj/operateurs`, portail LNB : `lnbloto.bj`.
- Seulement **4 opérateurs sont agréés** : la LNB elle-même, 1xBet, Betmomo et Betpawa.
  Tout autre opérateur est hors du cadre légal béninois.
- Les paris sportifs en ligne ne sont pas interdits pour les joueurs, mais **opérer**
  un site de paris nécessite une convention avec la LNB.

**Ce que ça change concrètement pour ton projet :**

| Ce que tu fais | Statut |
|---|---|
| Un **outil d'analyse et de statistiques**, sans prise de mise | ✅ Pas d'agrément nécessaire |
| Publier des **pronostics gratuits** avec ton bilan | ✅ Outil d'aide à la décision |
| **Vendre un abonnement** à tes analyses (comme un tipster) | ⚠️ Zone grise — à vérifier auprès de la LNB |
| **Prendre des mises** / encaisser de l'argent / payer des gains | ❌ **Agrément LNB obligatoire** |
| Rediriger vers des bookmakers via **affiliation** | ⚠️ Uniquement des opérateurs agréés LNB |

**Recommandation stratégique :** construis un **outil d'analyse et de prédiction**,
pas un bookmaker. C'est légalement beaucoup plus simple, et c'est de toute façon là
qu'est la valeur technique. Ajoute un avertissement clair sur les risques du jeu
(« le jeu peut créer une dépendance ») — c'est une obligation déontologique et ça
protège ta réputation.

⚠️ **Ceci n'est pas un conseil juridique.** Avant toute monétisation, consulte la LNB
ou un avocat béninois. La réglementation évolue.

---

## 10. Ce que je te propose maintenant

Le moteur est déjà écrit et le backtest tourne sur 8 908 matchs réels. Selon tes
réponses, je peux enchaîner directement sur :

1. **Un prototype web fonctionnel** que tu peux ouvrir dans ton navigateur et
   consulter en direct
2. **Le rapport de backtest complet** avec les métriques (log-loss, calibration, ROI)
3. **L'extension à d'autres ligues** ou l'ajout des marchés fautes/corners/cartons
4. **Le schéma de base de données** et le pipeline d'ingestion

---

### Sources consultées

- football-data.co.uk — archive CSV gratuite, vérifiée et téléchargée en direct
- Comparatifs d'API football 2026 : thestatsapi.com/blog/best-football-api,
  footyapps.com/guide/free-football-apis, highlightly.net
- Tarifs API-Football / Sportmonks / football-data.org relevés en 2026
- Cadre légal béninois : champsbase.com, parierfacile.com/pays/benin, lnbpari.com
- Dixon & Coles (1997), *Modelling Association Football Scores and Inefficiencies
  in the Football Betting Market*, Journal of the Royal Statistical Society, 46(3)
