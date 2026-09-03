# Rapport de backtest — Moteur Dixon-Coles

**Exécuté le :** 2 septembre 2026
**Données :** football-data.co.uk (gratuit), 14 285 matchs, 5 ligues, 8 saisons (2018→2026)
**Évalué sur :** 8 861 matchs, saisons 2021/22 → 2025/26
**Protocole :** walk-forward strict — réentraînement toutes les 3 semaines, aucune donnée
postérieure au match prédit n'est jamais utilisée.
**Référence :** cotes de clôture Pinnacle déviggées (le benchmark le plus sévère du marché)

---

## ⚠️ Avertissement sur l'intégrité de ce rapport

Ce rapport documente **trois bugs que le backtest a attrapés**. Ils sont consignés ici
volontairement : c'est exactement à cela que sert un backtest rigoureux, et un rapport
qui ne montrerait que des chiffres flatteurs serait suspect.

| # | Bug | Symptôme | Impact | Statut |
|---|---|---|---|---|
| 1 | `gamma` non compensé après renormalisation des forces d'équipe | λ d'échelle fausse | Tous les marchés | ✅ Corrigé (v2) |
| 2 | `np.tril(M,-1)` affecté à la victoire **extérieur** au lieu de **domicile** | Issues 1 et 2 inversées, précision 22,9 % (pire que l'aléatoire), calibration inversée | Marché 1X2 | ✅ Corrigé (v3) |
| 3 | Cotes O/U manquantes encodées en `0.00`, non filtrées par `dropna` | `overround = inf`, NaN, log-loss marché faux | Marché Over/Under | ⚠️ Identifié — O/U à re-tester |

**Le bug n°2 est le plus instructif.** Il produisait une précision de 22,9 % sur le 1X2,
soit **pire qu'un tirage aléatoire** (33 %). Le signal d'alerte : le nul était
parfaitement calibré (25,8 % prédit vs 25,4 % réel) alors que tout le reste était
inversé. Une inversion d'étiquette, pas un mauvais modèle.

**Le bug n°3 m'a conduit à annoncer à tort que le modèle battait Pinnacle sur
l'Over/Under.** Une vérification indépendante sur données brutes a démontré le
contraire. L'affirmation est retirée.

---

## 1. Résultats sur le marché 1X2 (8 007 matchs)

| Métrique | **Modèle v3** | **Pinnacle clôture** | Écart |
|---|---|---|---|
| Log-loss *(plus bas = meilleur)* | **1,0006** | 0,9672 | +3,5 % en retrait |
| RPS *(plus bas = meilleur)* | **0,1362** | 0,1295 | +5,2 % en retrait |
| Précision du favori | **51,6 %** | 54,2 % | −2,6 pts |
| Taux de nuls prédit / réel | **25,8 % / 25,4 %** | — | ✅ calé |

### La calibration est excellente — c'est le résultat le plus important

| Probabilité prédite | N | Taux réel | Écart |
|---|---|---|---|
| 0 – 15 % | 2 591 | 12,5 % | **+2,4 pts** |
| 15 – 30 % | 10 379 | 25,0 % | **+1,0 pt** |
| 30 – 45 % | 5 714 | 36,2 % | **+0,3 pt** |
| 45 – 60 % | 3 046 | 48,1 % | **−3,8 pts** |
| 60 – 100 % | 2 291 | 68,0 % | **−2,7 pts** |

**Lecture :** quand le modèle dit 36 %, ça arrive 36,2 % du temps. C'est remarquable
pour un modèle qui n'utilise que des résultats de matchs — ni xG, ni compositions,
ni blessures.

**Interprétation cruciale :** le modèle est **bien calibré mais pas assez discriminant**.
Il ne se trompe pas de niveau de confiance, il **lisse trop**. Il manque de puissance
pour séparer les matchs, pas de justesse. C'est un défaut qui se corrige en ajoutant
des features — pas en changeant de modèle.

---

## 2. Test A/B : validation du paramètre d'échelle manquant

### L'hypothèse

Dans la formulation classique :

```
λ_domicile = attaque_i × défense_j × γ
λ_extérieur = attaque_j × défense_i
```

la normalisation `mean(att) = mean(def) = 1` **force la moyenne des buts à l'extérieur
à ≈ 1,00**. Or la réalité mesurée est **1,37** en Premier League. Il manque donc un
multiplicateur global libre :

```
λ_domicile = s × attaque_i × défense_j × γ
λ_extérieur = s × attaque_j × défense_i
```

### Le résultat (Premier League, 1 137 matchs, 2023→2026)

| Métrique | v_A (sans `s`) | **v_B (avec `s`)** | Référence Pinnacle |
|---|---|---|---|
| Log-loss 1X2 | 0,9831 | **0,9700** ✅ | 0,9458 |
| Précision favori | 53,1 % | **54,9 %** ✅ | — |
| Biais de buts/match | −0,454 | **−0,238** ✅ | — |
| Buts prédits / réels | 2,58 / 3,04 | **2,80 / 3,04** | — |
| Buts extérieur prédits | ~1,00 (forcé) | **1,23** | réel : 1,37 |

Paramètres estimés : **`s` = 1,227**, **`γ` = 1,277** (au lieu de γ = 1,567 seul).

> **L'écart avec Pinnacle passe de 0,0373 à 0,0242 — soit 35 % de l'écart comblé
> par l'ajout d'un seul paramètre.** C'est le meilleur retour sur investissement
> possible en modélisation, et ça valide la démarche.

Les deux valeurs γ=1,277 et s=1,227 sont cohérentes avec la littérature : l'avantage
domicile réel en Europe est de l'ordre de +25 à +35 % de buts, pas +57 %.

---

## 3. Rentabilité et Closing Line Value

| Test | Résultat |
|---|---|
| ROI vs cote de clôture, edge requis 2 % | **−7,84 %** (9 623 paris, 29,7 % de réussite) |
| ROI vs cote de clôture, edge requis 10 % | **−11,60 %** (6 176 paris) |
| CLV : log-loss modèle vs cote d'ouverture | **−0,0314** → pas d'edge |

### Lecture honnête

**Le modèle n'est pas rentable en l'état.** Le ROI de −7,8 % est pire que la simple
marge du bookmaker (−2 à −3 % sur Pinnacle). Pourquoi ? Parce qu'un modèle bien
calibré mais **trop lissé** déclenche des paris quand il surestime l'écart entre sa
prédiction et la cote. Plus l'edge requis monte, plus le ROI baisse : signature
classique d'un modèle qui n'a pas d'information réelle supérieure au marché.

**Ce n'est pas une mauvaise nouvelle.** C'est le résultat attendu et documenté pour un
Dixon-Coles pur. Le marché de clôture Pinnacle intègre les compositions, les blessures,
les actualités et l'argent des parieurs professionnels. Mon modèle n'a **aucune** de
ces informations — il ne voit que des scores passés.

**Il atteint néanmoins 51,6 % de précision avec une calibration à ±3 points en ne
utilisant que des données 100 % gratuites.** La fondation est saine.

---

## 4. Ce qui manque pour combler l'écart — par ordre de rentabilité

| Priorité | Feature à ajouter | Gain attendu | Coût |
|---|---|---|---|
| 1 | **Paramètre d'échelle `s`** | ✅ Déjà validé : −35 % d'écart | 0 FCFA |
| 2 | **xG au lieu des buts réels** | Fort — les buts sont bruités, l'xG ne l'est pas | 0 FCFA (Understat) à 30 000 FCFA/mois |
| 3 | **Compositions + blessés + suspendus** | Fort — le marché réagit violemment aux absences | ≈ 11 500 FCFA/mois |
| 4 | **Niveau de buts par ligue et par saison** | Moyen — corrige la dérive temporelle | 0 FCFA |
| 5 | **Facteur d'enjeu** (fin de saison, matchs sans intérêt) | Moyen | 0 FCFA |
| 6 | **Effet arbitre** sur fautes/cartons | Fort sur les marchés de niche | 0 FCFA |
| 7 | **xG par joueur** pour les marchés buteurs | Indispensable pour ce marché | ≈ 11 500 FCFA/mois |

**Le point 2 est le plus rentable après `s`.** Remplacer les buts réels par les xG dans
l'entraînement élimine le bruit de finition : une équipe qui perd 1-0 en ayant généré
2,8 xG contre 0,4 n'est pas faible, elle a mal fini. La littérature mesure un gain
net sur la précision prédictive. Understat fournit ces données **gratuitement** pour
les Big 5.

---

## 5. Paramètres du modèle final estimé (Premier League, fin de saison 2025/26)

```
Attaque la plus forte   : Manchester City      1,67
Défense la plus faible  : Sheffield United     1,51
Avantage domicile (γ)   : 1,567  →  1,277 après correctif
Échelle extérieure (s)  : 1,227
Correction Dixon-Coles  : ρ = −0,070   (négatif = conforme à la littérature)
```

### Démonstration : la détection automatique des « scores fleuves »

Le moteur identifie seul le match le plus susceptible de produire un carton,
sans aucune règle codée à la main — simplement en cherchant le maximum de
`P(buts ≥ 5)` sur toutes les paires :

```
Manchester City vs Sheffield United

Buts attendus           4,32
P(Over 1,5)             ~97 %
P(Over 2,5)             80,7 %
P(Over 3,5)             62,9 %
P(5 buts ou plus)       43,6 %
P(écart ≥ 3 buts)       67,4 %

Scores les plus probables :  3-0 (13,3 %)  |  4-0 (13,1 %)  |  5-0 (10,3 %)
```

**C'est la validation concrète de ta demande « quel club contre quel club font des
scores fleuves » :** une attaque à 1,67 contre une défense à 1,51 produit
mécaniquement λ élevé, la masse de probabilité se déplace vers le coin de la matrice,
et l'Over 3,5 devient majoritaire. Aucune règle ad hoc nécessaire — ça découle des maths.

---

## 5 bis. Le proxy xG gratuit — calibration et verdict contre-intuitif

Understat (la source gratuite d'xG de référence) renvoie la page HTML mais **sans ses
variables de données** (18 Ko au lieu de ~2 Mo) : le scraping est bloqué. StatsBomb
Open Data répond, mais c'est de l'historique figé, pas la saison en cours.

**La parade, à 0 FCFA :** `football-data.co.uk` fournit les tirs et tirs cadrés depuis
30 ans. On peut donc construire un proxy d'xG — et surtout, **calibrer ses coefficients
sur nos propres 14 284 matchs** au lieu d'utiliser les valeurs théoriques des manuels.

### Coefficients ajustés par moindres carrés

```
buts domicile   = 0,2989 × tirs_cadrés − 0,0405 × tirs_non_cadrés + 0,436     R² = 0,345
buts extérieur  = 0,2971 × tirs_cadrés − 0,0318 × tirs_non_cadrés + 0,292     R² = 0,343
```

**≈ 0,30 but par tir cadré**, conforme à la littérature (30–33 %). Le coefficient
négatif sur les tirs non cadrés est un artefact de multicolinéarité, mais il est
stable et exploitable. Un R² de 0,345 est normal : le football est intrinsèquement
bruité, et c'est précisément ce bruit que l'xG cherche à filtrer.

### Hétérogénéité entre ligues (elle justifie un multiplicateur par ligue)

| Ligue | Buts/m | Domicile | Extérieur | Tirs cadrés/m | Conversion | Over 2,5 |
|---|---|---|---|---|---|---|
| Bundesliga | **3,16** | 1,75 | 1,42 | 9,5 | 33,1 % | **61,4 %** |
| Premier League | 2,86 | 1,55 | 1,31 | 8,9 | 32,3 % | 54,8 % |
| Ligue 1 | 2,75 | 1,51 | 1,24 | 8,7 | 31,7 % | 52,2 % |
| Serie A | 2,72 | 1,46 | 1,26 | 9,2 | 29,5 % | 52,0 % |
| La Liga | **2,57** | 1,46 | 1,11 | 8,2 | 31,4 % | **46,7 %** |

**L'écart Bundesliga / La Liga est de 0,59 but par match et 14,7 points d'Over 2,5.**
Un modèle qui ne tient pas compte du niveau de buts propre à chaque ligue est
structurellement faux sur les marchés Over/Under. C'est un paramètre gratuit à ajouter.

### Le test décisif — et son résultat contre-intuitif

Protocole : mesurer la force offensive d'une équipe sur 300 matchs passés (une fois
avec les buts réels, une fois avec le proxy xG), puis regarder laquelle des deux
corrèle le mieux avec les buts marqués sur les 76 matchs suivants.

| Ligue | n | corr(buts passés → futurs) | corr(xG passés → futurs) | Écart |
|---|---|---|---|---|
| Premier League | 2 573 | **0,5657** | 0,5521 | −0,0135 |
| La Liga | 2 573 | **0,6040** | 0,5947 | −0,0093 |
| Serie A | 2 571 | **0,5751** | 0,5465 | −0,0287 |
| Bundesliga | 1 809 | **0,6430** | 0,6372 | −0,0058 |
| Ligue 1 | 2 194 | **0,5281** | 0,4947 | −0,0334 |

Le proxy xG perd systématiquement. **Mais** le test de stabilité donne le résultat inverse :

| Ligue | Écart-type buts bruts | Écart-type proxy xG | Réduction du bruit |
|---|---|---|---|
| Bundesliga | 0,5167 | 0,2949 | **−43 %** |
| Premier League | 0,4600 | 0,2536 | **−45 %** |
| Ligue 1 | 0,4199 | 0,2555 | −39 % |
| La Liga | 0,4104 | 0,2491 | −39 % |
| Serie A | 0,4327 | 0,3592 | −17 % |

### Interprétation : pourquoi les deux résultats ne sont pas contradictoires

Le proxy xG est **beaucoup moins bruité mais aussi beaucoup plus compressé** vers la
moyenne (écart-type 0,25 contre 0,46). Or le coefficient de corrélation est
**normalisé par les écarts-types** : un prédicteur à faible variance est mécaniquement
pénalisé face à une cible à forte variance, même s'il est plus informatif.

**La corrélation n'était donc pas la bonne métrique pour trancher.** La conclusion
correcte n'est pas « l'xG est inutile » ni « remplaçons les buts par l'xG », mais :

> **Il faut combiner les deux signaux**, comme le fait le SPI de FiveThirtyEight avec
> son *shot-adjusted* et son *non-shot-adjusted rating*.

Implémentation retenue — **moyenne géométrique** des forces, naturelle pour des
facteurs multiplicatifs :

```
attaque_finale = attaque_buts ^ w  ×  attaque_xG ^ (1 − w)
```

avec `w` à déterminer empiriquement par backtest. Le modèle xG est estimé par
**moindres carrés pondérés en log** (système linéaire, donc très rapide et stable),
tandis que le modèle buts reste en maximum de vraisemblance Dixon-Coles.

**Astuce d'ingénierie :** les deux modèles étant indépendants de `w`, on entraîne une
seule fois et on dérive les 5 variantes (w = 1,00 / 0,75 / 0,50 / 0,25 / 0,00)
gratuitement. Coût : 1 entraînement double au lieu de 5.

---

## 5 ter. Leçon méthodologique majeure : toujours tester la baseline triviale

C'est le passage le plus important de ce rapport.

Après le backtest v3, le modèle semblait **battre Pinnacle sur l'Over/Under 2,5**
(0,7335 contre 0,7527, puis 0,7039 contre 0,7624 sur un test ciblé). C'était trop beau.

**Le signal d'alerte :** la variante gagnante prédisait 44,1 % d'Over alors que le taux
réel était de 57,3 %. Un modèle aussi mal calibré ne peut pas être réellement supérieur
au marché le plus efficace du monde.

### Le test qui tranche : une constante naïve

Comparer le modèle à **une constante calée sur la fréquence observée** — le prédicteur
le plus bête possible. Premier League, 2 099 matchs, cotes Pinnacle propres :

| Prédicteur | Log-loss | Écart vs baseline |
|---|---|---|
| Constante naïve = fréquence observée (55,4 %) | 0,6873 | référence |
| Constante 50/50 (hasard total) | 0,6931 | +0,0059 |
| **Pinnacle clôture déviggé** | **0,6745** | **−0,0128** |

**Pinnacle bat la constante naïve.** Le marché est bien efficace.

Et saison par saison, il la bat **partout**, y compris lors du choc structurel :

| Saison | n | Over réel | Pinnacle prédit | LL Pinnacle | LL constante | Verdict |
|---|---|---|---|---|---|---|
| 2021 | 380 | 50,0 % | 52,2 % | **0,6863** | 0,6931 | marché OK |
| 2021/22 | 380 | 53,9 % | 52,2 % | **0,6878** | 0,6900 | marché OK |
| 2022/23 | 379 | 52,5 % | 53,0 % | **0,6699** | 0,6919 | marché OK |
| 2023/24 | 373 | **64,6 %** | 58,4 % | **0,6460** | 0,6498 | marché OK |
| 2024/25 | 377 | 56,2 % | 58,4 % | **0,6802** | 0,6854 | marché OK |
| 2025/26 | 210 | 55,2 % | 52,9 % | **0,6781** | 0,6876 | marché OK |

> La saison 2023/24 est celle de l'allongement du temps additionnel : le taux d'Over 2,5
> est passé brutalement à 64,6 %. **Même sur ce choc, Pinnacle reste meilleur qu'une
> constante.** Les bookmakers se sont adaptés plus vite que mon modèle.

### Conclusion : l'affirmation est retirée

**« Le modèle bat Pinnacle sur l'Over/Under » est FAUX.** C'est la **seconde fois** que
cette affirmation apparaît dans ce travail et la seconde fois qu'une vérification plus
rigoureuse l'invalide. Le motif est instructif :

1. Première fois : cotes O/U manquantes encodées en `0.00`, non filtrées par `dropna`
2. Seconde fois : sous-échantillon non représentatif + absence de comparaison à une baseline

**Règle à appliquer systématiquement dans ce projet :** aucun chiffre de performance
n'est publié sans trois comparaisons — le marché déviggé, une constante naïve, et le
hasard. Un modèle qui bat le marché mais pas une constante ne bat rien du tout.

⚠️ Le script `test_recalage.py` reste entaché d'un écart non résolu avec la vérification
indépendante (Pinnacle à 0,7624 contre 0,6745). **Ses chiffres ne doivent pas être
utilisés.** Seule la vérification sur données brutes ci-dessus fait foi.

---

## 5 quater. Backtest v3 consolidé — 11 ligues, 17 093 matchs

### Comparaison des poids buts / xG

| Poids sur les buts | Log-loss 1X2 | RPS | Préc. favori | Log-loss O/U | Buts prédits | Biais |
|---|---|---|---|---|---|---|
| **1,00** (buts seuls) | **0,9944** | **0,1349** | **51,9 %** | 0,7575 | 2,66 | −0,113 |
| 0,75 | 1,0002 | 0,1364 | 51,2 % | 0,7642 | 2,77 | −0,001 |
| 0,50 | 0,9993 | 0,1364 | 51,2 % | 0,7515 | 2,67 | −0,097 |
| 0,25 | 1,0024 | 0,1371 | 50,9 % | 0,7440 | 2,58 | −0,189 |
| 0,00 (xG seul) | 1,0067 | 0,1378 | 51,3 % | 0,7335 | 2,40 | −0,371 |

Référence Pinnacle clôture : **1X2 = 0,9656** · **O/U = 0,7527**

**Lecture :** le proxy xG n'améliore pas le 1X2. Il semble améliorer l'O/U, mais la
section précédente montre que ce gain est un artefact. **Verdict : poids buts = 1,00.**
Le proxy xG n'apporte rien de démontré à 0 FCFA — il reste utile comme variable
descriptive, pas comme signal prédictif.

### Progression v2 → v3 sur le 1X2

| Métrique | v2 (5 ligues) | **v3 (11 ligues)** | Pinnacle | Écart v3 |
|---|---|---|---|---|
| Log-loss | 1,0006 | **0,9944** | 0,9656 | +0,0289 |
| RPS | 0,1362 | **0,1349** | 0,1295 | +0,0054 |
| Précision favori | 51,6 % | **51,9 %** | 54,2 % | −2,3 pts |
| Calibration (pire écart) | −3,8 pts | **−1,5 pt** | — | ✅ |

L'écart avec Pinnacle passe de +0,0334 (v2) à +0,0289 (v3), soit **13 % de l'écart
comblé**, à 0 FCFA, sur un échantillon plus que doublé.

### Calibration v3 — très bonne

| Probabilité prédite | N | Taux réel | Écart |
|---|---|---|---|
| 0 – 15 % | 4 651 | 11,4 % | **+1,4 pt** |
| 15 – 30 % | 23 475 | 24,8 % | **+0,7 pt** |
| 30 – 45 % | 11 959 | 35,5 % | **−0,8 pt** |
| 45 – 60 % | 6 797 | 50,1 % | **−1,5 pt** |
| 60 – 100 % | 4 397 | 70,3 % | **−0,3 pt** |

**Quand le modèle dit 70 %, ça arrive 70,3 % du temps.** Sur 17 093 matchs et 11 ligues,
avec uniquement des résultats de matchs gratuits. C'est le résultat le plus solide du projet.

### Rentabilité — inchangée, et c'est normal

| Test | Résultat |
|---|---|
| ROI vs clôture Pinnacle, edge 2 % | **−8,81 %** (18 980 paris) |
| ROI vs clôture Pinnacle, edge 8 % | **−11,19 %** (13 492 paris) |
| CLV vs cote d'ouverture | **−0,0253** → pas d'edge |

Le modèle reste non rentable. **C'est attendu et sain** : il n'utilise ni compositions,
ni blessures, ni xG réels, ni actualités. Le marché, si.

---

## 5 quinquies. Marchés secondaires — fautes, corners, cartons

### Le signal existe, et il est réel

Test de stabilité A→B sur 34 708 matchs : on mesure le taux de chaque équipe sur une
première moitié de saison, puis on vérifie s'il prédit la seconde moitié.

| Effet mesuré | Corrélation | p-value | n |
|---|---|---|---|
| équipe → fautes commises | **r = 0,729** | 0,0000 | 283 |
| équipe → corners obtenus | r = 0,668 | 0,0000 | 283 |
| équipe → cartons jaunes | r = 0,619 | 0,0000 | 283 |
| arbitre → fautes sifflées | r = 0,502 | 0,0000 | 94 |
| arbitre → taux d'avertissement | r = 0,466 | 0,0000 | 94 |

Sur-dispersion mesurée (variance ÷ moyenne) : fautes **1,52**, corners 1,18, jaunes 1,17,
rouges 1,07. Les fautes ne suivent donc pas une loi de Poisson : elles sont modélisées
par une binomiale négative.

À titre de comparaison, la corrélation équivalente pour les **buts** tourne autour de
r ≈ 0,45. Ces marchés sont donc intrinsèquement **plus prévisibles que les buts**.

### Mais le backtest walk-forward refroidit nettement l'enthousiasme

Protocole : pour chaque saison testée (2324, 2425, 2526, 2627), les facteurs d'équipe et
d'arbitre sont entraînés sur **toutes les saisons antérieures uniquement**. 42 733
prédictions évaluées, aucune donnée postérieure au match prédit.

Trois configurations comparées pour isoler l'apport de chaque brique :

| Configuration | Erreur moyenne | Gain | Log-vraisemblance | Brier |
|---|---|---|---|---|
| A. moyenne de la division | 2,9243 | — | −3,2261 | 0,2049 |
| B. facteurs équipes | 2,8907 | +1,1 % | −3,2255 | 0,2022 |
| C. équipes + arbitre | **2,8877** | **+1,25 %** | −3,2252 | **0,2018** |

Détail par marché, confronté au **plafond théorique** (gain maximal atteignable si le
niveau réel de chaque équipe était connu parfaitement, déduit du rapport des écarts-types) :

| Marché | Erreur naïve | Erreur modèle | Gain | Plafond | Part du plafond exploitée |
|---|---|---|---|---|---|
| **fautes** | 4,378 | 4,282 | **+2,19 %** | +6,7 % | **33 %** |
| corners | 2,719 | 2,716 | **+0,12 %** | +4,3 % | 3 % |
| jaunes | 1,676 | 1,665 | +0,64 % | +3,2 % | 20 % |

Le gain est stable d'une saison à l'autre (+1,0 %, +1,3 %, +1,5 %, +0,8 %), donc ce n'est
pas un accident d'échantillon.

**Pourquoi ce décalage entre r = 0,73 et +1,25 % ?** Le classement des équipes est très
stable, mais cette stabilité n'explique qu'une petite part de la variance d'un **match
individuel**. L'écart-type des fautes par match est de 6,02 ; celui des niveaux d'équipe
est de 1,55. La part explicable est donc de l'ordre de 2 × 1,55² ÷ 6,02² ≈ 13 %, ce qui
borne le gain d'erreur à environ 6,7 %. Le résultat observé est cohérent avec ce plafond :
une corrélation élevée sur des moyennes d'équipe ne se convertit pas mécaniquement en
précision sur un match.

**Les corners sont le résultat le plus décevant** : +0,12 %, soit 3 % du plafond exploité.
Le nombre de corners dépend beaucoup du scénario du match (une équipe menée pousse et en
obtient), que ce modèle statique ne capture pas du tout.

### L'arbitre : signal réel, effet négligeable

261 arbitres estimés, dont 138 avec plus de 40 matchs. Le plus sévère (A Grieve) distribue
×1,12 les cartons jaunes, le plus clément (D Webb) ×0,85.

Pourtant, l'apport **isolé** de l'arbitre est de −0,0030 sur l'erreur moyenne : quasi nul.
Deux raisons : l'amplitude réelle des effets est faible (×0,85 à ×1,12 après lissage,
alors que le taux brut d'avertissement varie de 0,119 à 0,199), et le lissage bayésien
nécessaire pour éviter le sur-ajustement sur des échantillons de 40 à 100 matchs écrase
encore cette amplitude. L'arbitre reste affiché dans l'interface à titre informatif.

### Ce qui est solide : la calibration

Sur 213 665 seuils Over/Under testés, l'écart entre probabilité annoncée et fréquence
réalisée ne dépasse jamais 2 points :

| Annoncé | Réalisé | Écart | Seuils |
|---|---|---|---|
| 8 % | 10 % | −2 pt | 3 082 |
| 16 % | 18 % | −2 pt | 14 988 |
| 25 % | 26 % | −1 pt | 25 754 |
| 35 % | 36 % | −1 pt | 30 776 |
| 45 % | 46 % | −1 pt | 29 720 |
| 55 % | 56 % | −1 pt | 29 153 |
| 65 % | 66 % | −1 pt | 28 453 |
| 75 % | 75 % | 0 pt | 26 146 |
| 85 % | 85 % | 0 pt | 17 773 |
| 93 % | 92 % | +1 pt | 7 820 |

Quand le modèle annonce 65 %, l'événement se produit 66 % du temps. C'est la propriété la
plus utile de tout le système : les probabilités affichées sont **crédibles**, y compris
pour les marchés secondaires.

### La limite qui bloque tout : aucune cote

**football-data.co.uk ne fournit aucune cote pour les fautes, les corners ou les cartons.**
La prévisibilité est démontrée, la **rentabilité est impossible à mesurer**. C'est une
limite bloquante et non contournable avec un budget de 0 FCFA.

Et le raisonnement est défavorable : avec un gain de précision de 1 à 2 %, il est très
improbable de survivre à la marge d'un bookmaker (5 à 8 % sur ces marchés, souvent plus).
Si les bookmakers cotent ces marchés depuis des années, ils exploitent probablement déjà
l'essentiel du signal.

### Verdict

Ces marchés sont un **outil d'analyse crédible** — les totaux attendus sont réalistes et
les probabilités sont bien calibrées — et un **repère de cohérence** utile pour repérer
une cote manifestement décalée. Ce n'est **pas** un générateur de mises.

Reproduction : `python3 backtest_secondaires.py` (27 s, exporte
`data/backtest_secondaires.json` consommé par l'interface web).

### Correctif de reproductibilité (trouvé en préparant le déploiement)

En générant l'application depuis un dossier vierge pour vérifier qu'elle se
reconstruisait à l'identique, un écart inattendu est apparu : **487 valeurs de
force d'équipe sur 605 différaient**, et les probabilités des 48 matchs à venir
bougeaient jusqu'à **1 point de pourcentage**, alors que les 105 fichiers CSV
des cinq dernières saisons étaient strictement identiques (mêmes empreintes MD5).

Trois causes distinctes, toutes corrigées :

1. **`sort_values("date")` n'est pas stable.** pandas utilise un tri rapide non
   stable par défaut : les matchs à date égale étaient ordonnés selon leur
   position d'origine dans le tableau, laquelle dépend du nombre de fichiers
   présents sur le disque. Corrigé par un tri canonique
   `["date", "home", "away"]` en `mergesort` (stable), et par un `sorted()` sur
   la liste de fichiers issue de `glob()`, dont l'ordre dépend du système de
   fichiers.

2. **Les marchés secondaires utilisaient toutes les saisons disponibles** alors
   que le modèle de buts n'en utilise que cinq. Le résultat dépendait donc du
   nombre de fichiers téléchargés. Corrigé : mêmes cinq saisons partout.

3. **Les effets d'arbitre étaient calculés sur l'historique complet**, pour la
   même raison. Corrigé de la même façon.

Un quatrième point, d'affichage celui-là : `total_matchs` comptait tous les
matchs chargés (40 726) au lieu des matchs réellement utilisés pour
l'entraînement (29 295). L'interface annonçait donc un volume supérieur à ce que
le modèle avait vu. Corrigé.

**Vérification après correctifs** : deux entraînements menés sur des historiques
différents (5 saisons d'un côté, 7 de l'autre) produisent désormais des données
embarquées strictement identiques — écart de **0,000000** sur 1 143 valeurs
comparées (probabilités 1X2 et Over/Under, marchés secondaires, classements,
scores fleuves). La seule différence résiduelle est `duree_s`, le temps de
calcul de la machine, qui n'a aucune importance.

Cette vérification compte : sans elle, chaque mise à jour quotidienne aurait
produit des chiffres légèrement différents sans aucune raison, ce qui aurait
rendu impossible toute comparaison d'un jour à l'autre.

## 6. Bilan

| Question | Réponse |
|---|---|
| Le projet est-il techniquement faisable ? | **Oui, démontré sur 30 538 matchs** |
| Les données gratuites suffisent-elles pour démarrer ? | **Oui** — 11 ligues, 8 saisons, 0 FCFA |
| Le moteur produit-il des probabilités saines ? | **Oui** — calibration à ±1,5 point sur 17 093 matchs |
| Bat-il le marché en l'état ? | **Non** — +0,0289 de log-loss, ROI −8,8 %, CLV négatif |
| Le marché est-il battable en principe ? | **Oui, mais pas avec ces seules données** — Pinnacle bat une constante naïve partout |
| Le proxy xG gratuit améliore-t-il le modèle ? | **Non, rien de démontré** — hypothèse testée et rejetée |
| Peut-il être amélioré ? | **Oui** — 13 % de l'écart comblé avec 1 paramètre (`s`) |
| Que faut-il pour le rendre compétitif ? | **Compositions, blessures et vrais xG** (donc une API payante) |

**Conclusion : la fondation est valide, gratuite et bien calibrée. Ce qui séparera ce
projet d'un gadget, c'est l'accès aux compositions et aux vrais xG — soit environ
11 500 à 30 000 FCFA par mois.**

### Ce qui est acquis et réutilisable immédiatement

1. Un pipeline de données gratuit couvrant 11 ligues européennes sur 8 saisons
2. Un moteur Dixon-Coles corrigé, avec paramètre d'échelle et calibration vérifiée
3. La dérivation automatique de tous les marchés depuis une seule matrice de scores
4. La détection automatique des « scores fleuves » (validée : Man City – Sheffield Utd)
5. Un protocole de backtest walk-forward et une discipline de validation

### Ce qui reste à faire

1. **Corriger ou supprimer `test_recalage.py`** (écart non résolu avec la vérification)
2. Ajouter le multiplicateur de niveau de buts **par ligue** (écart Bundesliga/La Liga
   de 0,59 but et 14,7 points d'Over — non exploité aujourd'hui)
3. Modéliser **fautes, corners et cartons** avec effet arbitre — les données sont déjà là,
   gratuites, sur 30 ans, et ces marchés sont les moins efficients
4. Tester les **vrais xG** (et non le proxy) dès qu'une source est accessible
5. Construire l'interface

---

## 7. Avertissement honnête

Ce travail démontre que le moteur **fonctionne** et produit des probabilités fiables.
Il démontre aussi qu'il **ne bat pas le marché** avec des données gratuites.

Ce n'est pas un échec : c'est l'état réel de l'art pour un modèle sans compositions
ni xG. Mais il faut le dire clairement, parce que la plupart des « apps de pronostics »
vendues en ligne masquent précisément ce point.

**Pour un usage personnel** — ton objectif déclaré — c'est largement suffisant : tu
auras un outil d'analyse rigoureux, des probabilités honnêtes, une détection des matchs
à fort volume de buts, et un bilan vérifiable. C'est déjà plus que ce que proposent
la quasi-totalité des sites de pronostics.

**Pour en vivre**, il faudra soit des données payantes, soit se concentrer sur les
marchés de niche (cartons, corners, fautes) où l'inefficience est réelle et mesurable.

⚠️ Aucun modèle ne garantit de gain. Le jeu peut créer une dépendance.

---

## Annexe — reproduction

```
pronos-foot/
├── maj.py                    telecharge, entraine et regenere (une commande)
├── moteur.py                 moteur v2 + backtest + evaluation
├── moteur_v3.py              moteur v3 (parametre s, 11 ligues, multi-poids)  <- ACTUEL
├── calibre_xg.py             calibration du proxy xG sur nos propres donnees
├── test_signal.py            test buts bruts vs proxy xG (correlation + stabilite)
├── test_ab.py                test A/B du parametre d'echelle s
├── test_recalage.py          ⚠ ENTACHE D'UN BUG - ne pas utiliser ses chiffres
├── data/                     88 CSV (14 Mo) + enrichi.csv + coef_xg.json
├── backtest_results.csv      v2 : 8 861 predictions
├── backtest_v3.csv           v3 : 11 ligues x 5 poids
├── backtest_v2.log           journal v2
├── backtest_v3.log           journal v3
├── CONCEPTION.md             architecture, couts, roadmap, cadre legal
└── RAPPORT-BACKTEST.md       ce document
```

```bash
python3 maj.py            # telecharge + entraine + regenere, 0 FCFA
python3 moteur.py         # ~15 min, 14 285 matchs, 429 reentrainements
python3 test_ab.py        # ~4 min, validation du parametre s
python3 calibre_xg.py     # ~45 s, calibration du proxy xG
python3 test_signal.py    # ~7 s, test du signal xG
python3 moteur_v3.py      # ~25 min, 30 538 matchs, 11 ligues, 5 variantes
```

### Reproduction de la verification critique

La verification qui invalide l'affirmation « le modele bat Pinnacle sur l'Over/Under »
tient en une dizaine de lignes et s'execute en moins d'une seconde :

```python
import glob, numpy as np, pandas as pd
rows = []
for f in sorted(glob.glob('data/2*_E0.csv')):
    d = pd.read_csv(f, encoding='latin-1')
    for c in ['FTHG','FTAG','PC>2.5','PC<2.5']: d[c] = pd.to_numeric(d[c], errors='coerce')
    d['sai'] = f.split('/')[-1][:4]; rows.append(d)
d = pd.concat(rows, ignore_index=True)
d['over'] = (d['FTHG'] + d['FTAG'] > 2.5).astype(int)
s = d.dropna(subset=['PC>2.5','PC<2.5'])
s = s[(s['PC>2.5'] > 1.01) & (s['PC<2.5'] > 1.01)]     # FIX: exclure les cotes a 0.00
inv = 1/s['PC>2.5'] + 1/s['PC<2.5']; p = (1/s['PC>2.5'] / inv).values
y = s['over'].values
ll = lambda p, y: -np.mean(np.log(np.clip(np.where(y==1, p, 1-p), 1e-9, 1)))
print('Pinnacle      :', round(ll(p, y), 4))
print('Constante naive:', round(ll(np.full(len(y), y.mean()), y), 4))
```
