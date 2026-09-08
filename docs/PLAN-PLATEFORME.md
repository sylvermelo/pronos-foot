# Feuille de route — du site perso à la plateforme connectée

_Réflexion de fond, septembre 2026. Rien n'est pressé : ce document pose la
logique complète pour (1) les résultats gratuits et les fréquences de mise à
jour, (2) la base de données sécurisée et la plateforme SaaS, (3) l'extension
à de nouvelles ligues. Tout est pensé pour rester à **0 FCFA** jusqu'à la
monétisation éventuelle._

---

## 1. Les résultats gratuits — bonne nouvelle : c'est déjà en place

### Ce qui existe déjà aujourd'hui

| Besoin | Source | Clé / compte | Quota | Fréquence actuelle |
|---|---|---|---|---|
| **Résultats des matchs joués** | **ESPN** (API publique) | aucune | aucun quota officiel | **toutes les heures** (runner GitHub) |
| Calendrier + heures | ESPN + TheSportsDB + OpenLigaDB | aucune (TheSportsDB : clé test) | TheSportsDB : 30 req/min | toutes les heures |
| Résultats historiques + cotes moyennes | football-data.co.uk (CSV) | aucune | aucun (mais le site tombe parfois — vu le 05/09) | vérifié toutes les heures, publié ~2×/semaine |
| xG réels (Big 5) | Understat | aucune | aucun | tous les 7 jours |
| Cotes Pinnacle en direct | The Odds API | compte gratuit | **500 crédits/mois** | 1×/jour (cache 20 h, ≈14 crédits/jour) |

**Donc : oui, il existe des sites qui donnent les résultats gratuitement — et
le système les utilise déjà.** ESPN est la meilleure source gratuite au monde
pour ça : pas de clé, pas de compte, pas de quota, scores finaux fiables.
C'est elle qui alimente l'onglet **« Pronos vs Résultats »** : à chaque
exécution (toutes les heures), le runner :

1. archive les sélections et combinés du jour (avant les matchs),
2. récupère les scores ESPN de tous les matchs archivés non résolus,
3. calcule les verdicts (✓/✗), le taux de réussite par marché, le gain simulé,
4. régénère et republie le site.

Le comparatif prédiction ↔ résultat se met donc **déjà** à jour tout seul,
1 h maximum après la fin d'un match.

### Répartition logique 1 h / 24 h / 7 jours (ta question sur les quotas)

C'est exactement le principe déjà appliqué, à garder :

- **Toutes les 3 h** (sources illimitées, sans quota) : calendrier ESPN,
  **résultats**, archivage, résolution des verdicts, publication.
- **Toutes les ~24 h** (sources à quota) : cotes Pinnacle (The Odds API,
  500 crédits/mois → 1 vraie téléchargement/jour + réserve de 80 crédits),
  cotes co.uk (publiées quotidiennement par la source de toute façon).
- **Tous les 7 jours** (sans quota mais lourd) : xG Understat (30 pages).
- **~2×/semaine** : historiques co.uk (la source ne publie que dimanche et
  mercredi soir — inutile d'insister plus).

Le mécanisme : chaque module a son **cache daté** dans `data/` ; le runner
tourne toutes les heures mais chaque source n'est réellement interrogée que si
son cache a dépassé son âge limite. C'est ça qui protège les quotas.

### Options d'amélioration (si tu veux, plus tard)

- **Passer le cron à toutes les heures** (`30 * * * *`) : les verdicts
  tomberaient ≤ 1 h après les matchs. Gratuit (repo public = minutes
  illimitées), mais 8× plus d'exécutions — bénéfice modeste, à voir.
- **Scores en direct pendant les matchs** : possible via ESPN (statut
  « in play »), mais ce n'est pas utile au comparatif (qui juge le résultat
  final) et ça donnerait envie de « parier en direct » — hors périmètre.
- Les autres API gratuites de résultats en 2026 (football-data.org : 12
  compétitions mais scores **retardés** ; TheSportsDB : crowdsourcé, fiabilité
  moyenne ; API-Football : 100 requêtes/**jour** seulement) n'apportent rien
  de mieux qu'ESPN pour cet usage. On garde ESPN en principal, TheSportsDB en
  secours — comme maintenant.

---

## 2. Base de données sécurisée + plateforme SaaS — la logique complète

### Le principe directeur

> **Le robot reste sur GitHub Actions (calcul gratuit), la mémoire passe dans
> une vraie base de données (Postgres gratuit), et l'interface ne montre que
> l'essentiel.**

Aujourd'hui, toute la « mémoire » du projet tient dans des fichiers JSON
(`suivi.json`, `modeles.json`…) versionnés dans git. Ça marche pour un usage
personnel, mais pour une plateforme avec comptes utilisateurs il faut une
base de données : historique propre, requêtes rapides, droits d'accès par
utilisateur, et pas de risque qu'un fichier écrase l'autre.

### Le choix recommandé : Supabase (plan gratuit)

| Besoin | Solution gratuite | Pourquoi |
|---|---|---|
| Base Postgres | **Supabase Free** : 500 Mo, illimité en requêtes raisonnables | Postgres complet + API REST automatique + authentification incluse, tout-en-un |
| Authentification (comptes) | Supabase Auth (inclus, gratuit jusqu'à 50 000 utilisateurs actifs/mois) | e-mail/mot de passe ou Google, sans écrire de code serveur |
| Droits d'accès | Row Level Security (RLS) de Postgres | « Untel ne voit QUE les lignes autorisées » — au niveau de la base, pas du site |
| Hébergement interface | GitHub Pages (actuel) puis Vercel/Cloudflare Pages si besoin | 0 FCFA, HTTPS automatique |
| Calcul / robot | GitHub Actions (déjà en place) | repo public = minutes illimitées |
| Sauvegardes | `pg_dump` quotidien poussé vers un dépôt privé OU Cloudflare R2 (10 Go gratuits) | le plan gratuit Supabase n'a pas de restauration automatique dans le temps — on la fait nous-mêmes |
| Paiement (plus tard) | KkiaPay / FedaPay (Mobile Money Bénin + cartes) | agréés pour la zone UEMOA ; LNB à voir avant toute monétisation |

Alternative : **Neon** (Postgres gratuit 0,5 Go) si tu préfères séparer, mais
il faudrait alors ajouter l'authentification à la main — plus de travail pour
le même résultat. Cloudflare D1 existe aussi mais sans auth intégrée.
**Supabase = le moins de code pour une vraie plateforme.**

Nos volumes sont minuscules : ~200 matchs + ~150 sélections + 3 combinés par
jour ≈ quelques centaines de Ko/jour en base. Le plan gratuit de 500 Mo tient
**plusieurs années**.

### L'architecture cible

```
┌────────────────────────── GitHub (dépôt + Actions) ─────────────────────────┐
│                                                                             │
│  ROBOT (toutes les heures, gratuit)                                            │
│  ├─ ESPN          → calendrier + RÉSULTATS                                  │
│  ├─ co.uk         → historiques + cotes moyennes (~2×/semaine)              │
│  ├─ The Odds API  → cotes Pinnacle (1×/jour, quota 500/mois)                │
│  ├─ Understat     → xG réels (1×/7 jours)                                   │
│  ├─ entraînement du moteur (Dixon-Coles + xG)                               │
│  └─ ÉCRIT dans la base ↓                        (clés en GitHub Secrets)    │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              │ écriture (clé « service », secrète)
                              ▼
┌──────────────── SUPABASE (plan gratuit) ────────────────┐
│  Postgres : matchs, prédictions, sélections, combinés,  │
│  résultats, cotes, stats cartons/corners, utilisateurs  │
│  Auth : comptes abonnés          RLS : chaque abonné    │
│  ne lit que ce que son abonnement autorise              │
│  Sauvegarde : dump quotidien → dépôt privé / R2         │
└─────────────────────────────┬───────────────────────────┘
                              │ lecture seule (clé publique « anon », bridée par RLS)
                              ▼
┌─────────────── INTERFACE (site actuel, puis appli) ───────────────┐
│  L'ESSENTIEL, rien d'autre :                                      │
│  · Sélections conseillées du jour                                 │
│  · SAFE du jour (3 max, du jour uniquement)                       │
│  · SAFE week-end (ven/sam/dim, 9 max)                             │
│  · RISQUE du jour                                                 │
│  · Pronos vs Résultats (taux réel, par marché, verdicts)          │
│  · Analyses secondaires : cartons, corners, fautes                │
│  Connexion automatique : l'abonné ouvre, tout est déjà à jour     │
└───────────────────────────────────────────────────────────────────┘
```

### Le schéma de base (tables principales)

- `matchs` : division, date, heure, équipes, saison, statut (à venir / fini),
  score final.
- `predictions` : pour chaque match et chaque génération du modèle —
  probabilités 1X2, over/under 1.5-3.5, BTTS, double chance, buts attendus,
  carton/corners attendus. On garde TOUTES les générations → traçabilité
  honnête (impossible de « tricher » après coup).
- `selections` : la sélection conseillée archivée AVANT le match (option,
  probabilité, cote juste, cote marché, source de la cote), puis son verdict.
- `combines` : safe / safe_weekend / risque du jour, jambes, probabilité
  combinée, cote, verdict.
- `cotes` : historique des cotes par match et bookmaker (Pinnacle, moyennes)
  — permettra plus tard de mesurer le « closing line value » sérieusement.
- `stats_equipes` : formes, xG pour/contre, cartons, corners (ce qui alimente
  les analyses secondaires).
- `utilisateurs` + `abonnements` (gérés par Supabase Auth) : qui a accès,
  jusqu'à quand, quel plan.
- `journal_pipeline` : chaque exécution du robot y écrit son statut — tu vois
  d'un coup d'œil si tout tourne (et moi aussi pour le débogage).

### La logique de sécurité (les 7 règles)

1. **Aucun secret dans le dépôt** — clés API, mot de passe base, clé
   « service » Supabase : uniquement en **GitHub Secrets** (comme
   `ODDS_API_KEY` déjà en place). Le code les lit via l'environnement.
2. **Deux clés, deux mondes** : le robot écrit avec la clé secrète (côté
   GitHub) ; les visiteurs lisent avec la clé publique `anon` qui ne donne
   accès à RIEN d'autre que ce que les règles RLS autorisent.
3. **RLS (droits ligne par ligne)** : table `selections` lisible seulement par
   un compte authentifié avec abonnement actif ; `journal_pipeline` lisible
   seulement par toi (admin) ; etc. Même si quelqu'un récupère la clé
   publique, il ne voit rien sans compte valide.
4. **Moindre privilège** : un compte « robot » qui ne fait qu'écrire, des
   comptes « abonnés » qui ne font que lire. Jamais de compte admin partagé.
5. **Sauvegardes automatiques et testées** : dump quotidien chiffré vers un
   dépôt privé (ou R2), + les JSON git actuels conservés comme deuxième
   ceinture. Une sauvegarde jamais testée n'est pas une sauvegarde : on teste
   la restauration 1×/mois.
6. **HTTPS partout** (GitHub, Supabase, Vercel : natif) + aucune donnée
   sensible côté navigateur.
7. **Journal d'audit** : chaque écriture du robot est horodatée ; chaque
   connexion passe par Supabase Auth (tentatives incluses).

### Les étapes dans l'ordre (chacune apporte sa valeur, aucune n'est bloquante)

- **Phase 0 — aujourd'hui (fait)** : site statique + JSON dans git.
  Gratuit, fonctionne, mais « mémoire » fragile et pas de comptes.
- **Phase 1 — la mémoire (½ journée de travail)** : créer le projet Supabase
  gratuit, ajouter les tables, brancher le robot pour qu'il écrive
  sélections/combinaisons/résultats en base EN PLUS des JSON (double écriture
  = zéro risque). Le site continue de fonctionner exactement comme avant.
- **Phase 2 — la lecture (1 journée)** : le site lit la base au lieu des
  JSON embarqués → historique illimité, page « Pronos vs Résultats » enrichie
  (filtres par mois, par marché, par ligue), aucune régénération nécessaire
  pour afficher les dernières données.
- **Phase 3 — les comptes (1-2 journées)** : Supabase Auth + RLS. Zone
  gratuite (résultats + historiques, pour la confiance) / zone abonné
  (sélections du jour, combinés, analyses cartons-corners). C'est là que ça
  devient un « SaaS auto-connecté » : l'utilisateur se connecte une fois,
  tout est à jour tout seul.
- **Phase 4 — la monétisation (quand tu veux, si tu veux)** :
  ⚠️ Cadre légal béninois : encaisser des abonnés = activité commerciale →
  statut à créer, et la vente de « pronostics » touche à la réglementation des
  jeux (LNB). À faire proprement AVANT le premier franc encaissé.
  Paiements : KkiaPay ou FedaPay (MTN Money / Moov Money + cartes).
  Éthique non négociable (c'est aussi ton intérêt commercial) : afficher les
  VRAIS taux de réussite comme on le fait déjà, ne jamais promettre de gains —
  le backtest dit que le modèle ne bat pas les bookmakers (ROI −8,8 %). Le
  produit honnête = un outil d'analyse transparent, pas une machine à rêves.

### Coûts réels

| Poste | Phase 1-3 | Phase 4 |
|---|---|---|
| Base + Auth (Supabase) | 0 FCFA | 0 FCFA (puis ~13 000 FCFA/mois si >50 000 utilisateurs — très hypothétique) |
| Hébergement | 0 FCFA (Pages/Vercel) | 0 FCFA |
| Robot | 0 FCFA (repo public) | 0 FCFA |
| Données | 0 FCFA (quotas gratuits actuels) | idem |
| Nom de domaine (optionnel, crédibilité) | — | ~6 500 FCFA/an |
| Formalités LNB/statut | — | à chiffrer avec un conseiller local |

---

## 3. Nouvelles ligues gratuites — ce qui existe vraiment

### La meilleure piste : les « EXTRA LEAGUES » de football-data.co.uk

**La même source gratuite déjà intégrée** publie 16 pays supplémentaires :
Argentine, Autriche, Brésil, Chine, Danemark, Finlande, Irlande, Japon,
Mexique, Norvège, Pologne, Roumanie, Russie, Suède, Suisse, USA.

- Fichiers CSV « toutes saisons en un seul fichier » (ex. `SWE.csv`),
  mis à jour ~2×/semaine, + un fichier `fixtures` des matchs à venir avec
  les meilleures cotes du marché (publié vendredi et mardi matin).
- **Contenu : buts, résultats et cotes (dont Pinnacle) — mais PAS les tirs,
  corners et cartons.** Conséquence honnête :
  - moteur principal (1X2, over/under, BTTS, double chance, scores fleuves) :
    **compatible directement** — il ne mange que des buts ;
  - marchés secondaires (fautes/corners/cartons) et proxy xG : **non
    disponibles** pour ces ligues (pas de colonnes tirs) ;
  - xG réels Understat : non disponibles hors Big 5 de toute façon.
- Calendrier/résultats 3 h : ESPN a des slugs pour la plupart de ces ligues
  (Autriche, Suisse, Danemark, Suède, Norvège, Pologne, MLS, Liga MX,
  Brésil…) → même tuyauterie que maintenant.
- Effort : ajouter les codes divisions (SWE, NOR, DNK…) au téléchargement
  maj.py + slugs ESPN + noms d'équipes. ~1 journée de travail, 0 FCFA.
  Le site passerait de 21 à ~35 divisions.

### Les autres options gratuites (pour mémoire)

| Source | Apport | Limite |
|---|---|---|
| **API-Football** (compte gratuit) | 1 200+ ligues dont **africaines** (si un jour tu veux le championnat béninois ou les coupes CAF) | **100 requêtes/jour** — à réserver aux ligues que rien d'autre ne couvre ; clé en GitHub Secrets comme The Odds API |
| football-data.org | 12 compétitions majeures, propre | scores **retardés**, saison en cours seulement → rien de mieux que ce qu'on a |
| TheSportsDB | 600+ ligues, calendrier | crowdsourcé (fiabilité variable), déjà utilisé en secours |
| OpenLigaDB | Allemagne (dont divisions inférieures) | déjà utilisé en secours |
| StatsBomb Open Data | xG événementiel historique | données figées, pas la saison en cours — inutilisable pour le hebdo |

**Recommandation** : commencer par les EXTRA LEAGUES co.uk (mêmes tuyaux,
mêmes garanties, 0 FCFA), et ne prendre un compte API-Football que le jour
où tu veux une ligue vraiment exotique (Afrique, Asie mineure).

---

## 4. Ce que je te propose concrètement (dans l'ordre, sans urgence)

1. **Rien à changer cette semaine** — le système actuel tourne, les verdicts
   tombent toutes les heures, les cotes Pinnacle sont en place.
2. **Quand tu veux : Phase 1 base de données** — tu crées le compte gratuit
   Supabase (je te guide pas à pas comme pour The Odds API), je branche le
   robot en double écriture. Aucune casse possible.
3. **Ensuite : ligues étendues** (16 pays co.uk) — gros gain de couverture
   pour 0 FCFA.
4. **Ensuite seulement : comptes abonnés + interface essentielle**, puis
   réflexion monétisation avec le cadre LNB.

Chaque étape est réversible, testée localement avant mise en ligne, et avec
ton feu vert explicite — comme d'habitude.
