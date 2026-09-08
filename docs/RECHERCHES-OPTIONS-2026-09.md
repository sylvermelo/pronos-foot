# RECHERCHES — options d'amélioration de la vitrine et du moteur
_7 septembre 2026 · rien n'est codé ni déployé : ce document sert à décider ensemble._

---

## 1. Audit : est-ce que le robot « réapprend » avec les résultats de la veille ?

**Réponse honnête : oui, mais seulement 2 fois par semaine.**

Ce qui existe déjà (vérifié dans le code) :
- La CI tourne **toutes les heures** : elle télécharge les CSV de football-data.co.uk
  **seulement s'ils ont changé**, puis ré-entraîne les modèles (`entraine.py`, ~35 s).
- Or co.uk ne publie les résultats que **dimanche et mercredi soir** (ligues principales,
  21 divisions) et ≥ 2×/semaine pour les 16 pays « extra leagues ».
- Les xG réels Understat (Big 5) sont rafraîchis dans la CI (`xg.py`) — fichier à jour au 05/09 ✓.
- Les scores ESPN résolus chaque heure alimentent le **suivi** (bilan, SAFE 2, coupons)
  mais **PAS la base d'entraînement**.

**Le trou** : un résultat de jeudi/vendredi/samedi n'entre dans les forces des équipes que
dimanche soir. Entre-temps, le modèle travaille avec des forces périmées de 1 à 4 jours.

**Ce qui existe déjà contre les « périodes mortes » et les promus** :
- Pondération temporelle exponentielle (demi-vie ≈ 58 semaines) : les matchs récents comptent
  plus, mais la mémoire est LONGUE — une équipe en chute libre met du temps à être rattrapée.
- Régularisation adaptative des équipes avec peu d'historique (promus) : évite les forces
  absurdes après 2 journées (cas Hull documenté dans le code).

**Proposition A — « boucle rapide »** : chaque heure, la CI injecte les scores FINAUX déjà
résolus par ESPN dans un fichier d'entraînement complémentaire (dédoublonné par
division+date+équipes, pour ne jamais compter deux fois un match quand co.uk le publie à son
tour), puis ré-entraîne s'il y a du nouveau. Coût : 0 FCFA, ~35 s de calcul par CI.
Variante à tester ensuite : une demi-vie plus courte (ex. 30 semaines) — uniquement si le
backtest prouve que c'est mieux, pas avant.

---

## 2. Compositions d'équipes / liste des joueurs AVANT le match

**Découverte testée et validée aujourd'hui** : l'API ESPN `summary` (la même famille d'API
gratuite et sans clé que le robot utilise déjà) fournit :
- `rosters` : **le XI de départ officiel** (11 joueurs marqués `starter: true`) + le banc
  (~20 joueurs), avec les noms — vérifié sur Chelsea–Arsenal d'hier (XI complets des 2 côtés) ;
- mais **seulement ~1 h avant le coup d'envoi** (75 min en Premier League) : c'est le moment
  de publication OFFICIEL des compositions dans tous les grands championnats.
  Testé sur un match à 4 h du coup d'envoi : effectif publié = 0. Normal.

**Avant 1 h** : aucune source GRATUITE fiable. Les compositions « projetées » existent chez
les bookmakers/presse (payant ou scraping fragile). Les blessés/suspendus : API-Football
(compte gratuit, 100 req/jour) a des endpoints blessures + suspensions + compositions ;
Sofascore (API non officielle, sans clé mais surveillée, ~1 req/2 s) est le plus riche
(compositions, stats par joueur, xG, stats par période).

**Ce qu'on peut en faire (proposition B)** :
- Le jour du match, afficher dans la vitrine le **XI officiel** dès sa publication ;
- Alerte **« absence clé »** : un joueur titulaire lors de ≥ 5 des 10 derniers matchs n'est
  pas dans le XI du jour → drapeau rouge sur le match ;
- Nécessite un petit workflow supplémentaire toutes les 15 min en soirée de matchs
  (repo public = Actions gratuites et illimitées).

**Limite honnête** : les compositions sortent APRÈS la fabrication des sélections du jour
(le matin). Elles ne peuvent donc PAS modifier le SAFE du jour — elles servent d'information
de dernière minute pour toi et tes abonnés, et elles nourriront les sélections du lendemain.

---

## 3. Fatigue « coupe d'Europe » — ta règle de l'écart < 5 jours

**Ce que dit la littérature (résumé)** :
- Étude UEFA sur 11 saisons de Champions League (Ekstrand) : peu d'effet global des jours de
  repos sur les résultats, SAUF en Europa League : plus de défaites avec récupération ≤ 3 jours.
- Verheijen (2012) : l'effet fort est **ASYMÉTRIQUE** — une équipe à récupération courte face
  à une équipe reposée gagne nettement moins (jusqu'à −40 % de victoires avec 2 jours de prépa
  contre 3). Quand les DEUX équipes ont joué en semaine, l'effet s'annule presque.
- Physique (Harper 2020) : moins de sprints et de courses à haute intensité avec < 4 jours
  entre les matchs ; plus de marche/trot. Les blessures musculaires augmentent avec la congestion.
- Les bookmakers CONNAISSENT le calendrier : une partie de l'effet est déjà dans les cotes.
  Le gain réaliste est sur l'**asymétrie de repos** et les ligues moins efficaces.

**Ta règle « < 5 jours = perte de force »** : la littérature supporte plutôt un gradient
≤ 3 jours (fort), 4 jours (modéré), ≥ 5 jours (référence). Je propose de la calibrer par
backtest au lieu de la coder à l'aveugle.

**Proposition C — module « repos »** :
1. Pour chaque équipe, calculer `jours_de_repos` = jours depuis son dernier match joué,
   TOUTES compétitions (le robot récupère déjà UCL/UEL/UECL/Carabao/Copa/Coppa/DFB/Coupe de
   France via `coupes.py` — les scores passés ESPN sont récupérables par date, backtest possible).
2. Drapeau d'affichage dans la vitrine : « ⚠️ A joué l'Europa jeudi (3 j de repos) —
   adversaire reposé (7 j) ».
3. Pénalité modèle (baisse d'attaque / confiance réduite / exclusion SAFE) appliquée
   SEULEMENT si le backtest walk-forward montre un gain mesuré — même discipline que pour
   les corners calibrés.

---

## 4. Corners — la découverte qui débloque le lot gelé

**Le blocage n°1 du lot corners gelé était : « aucune source gratuite ne fournit les corners
en direct → résolution automatique impossible ». C'est devenu FAUX.**

Testé aujourd'hui sur ESPN `summary` → `boxscore.teams.statistics` :
`wonCorners` **est présent sur les matchs terminés** (Chelsea 3 – Arsenal 5 vérifié), avec
aussi fautes, jaunes, rouges, tirs, tirs cadrés, possession, passes, centres, tacles.
→ **La résolution automatique quotidienne des coupons corners devient possible** (et même
celle des marchés fautes/cartons si tu veux un jour).

Le reste de l'édifice corners existe déjà et est sain :
- Historique d'entraînement : colonnes HC/AC des CSV co.uk (21 divisions × 5 saisons, déjà
  dans `data/`) ;
- Modèle : facteurs émission/réception par équipe, decay temporel, lissage Bayes empirique ;
- Calibration honnête : probabilités recalées sur backtest walk-forward de 16 408 matchs
  (le modèle brut se trompait de 4 à 13 points sur les handicaps — la calibration corrige) ;
- Ce qui reste VRAI : corners de 1re mi-temps non calibrables gratuitement, aucun live.

**Proposition D — corners, nouvelle version** :
1. **Résolution auto quotidienne** via ESPN (1 requête `summary` par match terminé, ~30/jour) ;
2. Recalibration continue : chaque mois, rejouer le backtest avec les nouveaux résultats et
   mettre à jour les probabilités calibrées (le système s'auto-corrige) ;
3. Piste d'amélioration du modèle à tester : utiliser la « domination attendue » (force
   d'attaque, écart de cotes marché) comme facteur — une grosse favorite qui assiège prend
   plus de corners ; le repos/rotation (proposition C) joue aussi ;
4. Avant tout : me dire ce qui te gênait dans la version gelée (« c'est pas encore comme je
   veux ») pour que la v2 vise juste.

---

## 5. Inventaire des sources gratuites (état septembre 2026)

| Source | Clé | Ce qu'elle donne | État dans le robot |
|---|---|---|---|
| ESPN (site.api) | aucune | calendrier, scores, **XI officiel (H−1)**, **stats finales (corners, cartons, fautes, tirs, possession)**, cotes fournisseur, coupes européennes, scores passés par date | utilisé (calendrier+scores) — **XI et stats finales = nouveau** |
| football-data.co.uk | aucune | historique 21 div. × 5 saisons (buts, tirs, **corners HC/AC**, fautes, cartons, arbitres) + cotes clôture ; extra leagues 16 pays ; màj dim+mer | utilisé, ré-entraîné auto |
| Understat | aucune | xG réels Big 5 (9 015 matchs) | utilisé, rafraîchi en CI |
| The Odds API | clé gratuite 500 crédits/mois | cotes Pinnacle live h2h+totals | utilisé (budget ≤ 430/mois) |
| API-Football | compte gratuit 100 req/jour | blessés, suspendus, compos (H−15), stats arbitres détaillées | NON utilisé — tu avais proposé de créer le compte |
| Sofascore (non officiel) | aucune (mais surveillé, ~1 req/2 s) | le plus riche : compos + stats par joueur + xG + stats **par période** (donc corners 1re MT !) | NON utilisé — zone grise, à doser avec parcimonie |
| TheSportsDB / OpenLigaDB | test / aucune | calendriers complémentaires | utilisé en secours calendrier |

---

## 6. Ordre proposé (chaque étape attend ton feu vert)

1. **Proposition A** — boucle rapide résultats → ré-entraînement quotidien. (fondation :
   tout le reste profite de forces à jour)
2. **Proposition D1+D2** — résolution auto des corners + recalibration continue.
3. **Proposition C** — module repos/fatigue : drapeaux d'affichage d'abord, pénalité modèle
   seulement si le backtest prouve.
4. **Proposition B** — XI officiel + alerte absence clé le jour du match (workflow 15 min).
5. Optionnel : compte API-Football gratuit (blessés/suspendus à J−2, utile AVANT le jour J).

Rien ne casse l'existant : chaque phase est additive, testable, et documentée avec ses limites.

---

## 7. ADDITIF (même jour) — Sofascore, corners 1re mi-temps, API-Football

### 7.1 Sofascore : verdict après test réel — INUTILISABLE par le robot
Testé depuis le sandbox (même classe de serveurs que GitHub Actions) : **403 Forbidden sur
tous les endpoints** (api.sofascore.com et www.sofascore.com), avec et sans headers,
User-Agent navigateur ou non. Sofascore bloque les adresses IP de datacenter — c'est
verrouillé côté serveur, pas contournable proprement. L'API marche très bien depuis TON
téléphone/PC (IP résidentielle), d'où ton expérience fluide. Conclusion honnête :
**Sofascore reste ta appli de consultation ; le robot ne peut pas s'en servir.**
(Zone grise juridique en plus — aucun regret à avoir.)

### 7.2 LA découverte : le « commentary » ESPN contient chaque corner horodaté
L'API ESPN `summary` (gratuite, sans clé, déjà utilisée par le robot) inclut un flux
d'événements façon Opta : **chaque corner avec l'équipe, la mi-temps (`period.number`)
et la minute** — plus buts, cartons, changements, tirs, et même les coordonnées sur le
terrain. Vérifié sur Chelsea–Arsenal du 06/09 :
- reconstruction MT1 : Arsenal 2 – Chelsea 0 ; MT2 : Arsenal 3 – Chelsea 3 ;
- total = 5–3 = **exactement** le boxscore officiel ✓.

Conséquences pour ton besoin « qui aura le plus de corners en 1re mi-temps » :
1. **Historique** : backfill progressif en CI (scoreboard par date → 1 requête summary par
   match) pour les ligues prioritaires, 2-3 saisons → base d'entraînement corners 1MT ;
2. **Résolution automatique quotidienne** des sélections corners 1MT ET match complet ;
3. **Entraînement** : modèle Poisson par équipe (émission/réception 1MT), mêmes méthodes
   que `modeles_secondaires.py`, calibration walk-forward comme le lot corners actuel ;
4. Bonus : le flux contient aussi tirs/tirs cadrés/fautes/cartons par minute → utilisable
   plus tard pour d'autres marchés secondaires, et les 16 ligues « extra » + coupes sont
   couvertes par ESPN (pas seulement les 21 divisions co.uk).

Rien de gratuit ne donnait les corners par mi-temps avant ça (co.uk : match complet ;
API-Football : match complet ; TotalCorner et footballdata.io : bloqué ou payant).

### 7.3 API-Football (compte créé par l'utilisateur) — ce qu'elle apporte en complément
Plan gratuit : 100 requêtes/jour. Endpoints utiles ici :
- **blessés + suspendus** dès J−2 (avant la publication des compos, seule source gratuite) ;
- **compositions officielles** (H−15 min, un peu plus tôt qu'ESPN H−1) ;
- **statistiques arbitres** détaillées (jaunes/match, penaltys) — utile au marché cartons ;
- prédictions bookmakers agrégées (à ignorer : on fait mieux nous-mêmes).
Usage proposé : 1 appel blessés/suspendus par match du jour (~30/jour) + compos en secours.
La clé ira dans GitHub Secrets (`API_FOOTBALL_KEY`), jamais dans un fichier du dépôt.

### 7.4 Produit corners v2 proposé (le lot gelé refondu)
- Onglet Corners de la vitrine : « **1MT — qui obtient le plus de corners ?** » avec
  P(domicile) / P(égalité) / P(extérieur) calibrées + total corners 1MT (over/under) ;
- Coupon corners existant : résolution **automatique** (finie la résolution hebdo manuelle) ;
- Tout est étiqueté honnêtement : probabilités calibrées sur backtest, jamais de promesse.

Ordre d'exécution proposé : A (boucle rapide) → D (corners 1MT : backfill + modèle +
résolution auto) → C (repos/fatigue) → B (compos + absences, ESPN H−1 + API-Football J−2).
