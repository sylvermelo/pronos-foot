# ORGANISATION — LA CARTE COMPLÈTE DU ROBOT

À lire avec REGLES.md. Dernière mise à jour : 8 septembre 2026.

Le code reste à plat à la racine : **tous les modules s'appellent par leur
nom** (`import calendrier`, `import fatigue`…) et la CI exécute des chemins
fixes (`python maj.py`, `python genere_app.py`). Les déplacer physiquement
casserait la chaîne horaire — c'est voulu. Cette carte remplace les dossiers.

## 📖 RÈGLES ET DOCUMENTS
| Fichier | Rôle |
|---|---|
| **REGLES.md** | ⚠️ À LIRE AVANT CHAQUE SESSION — interdits, règles métier, technique |
| **ORGANISATION.md** | ce fichier — la carte de tout |
| GUIDE.md | guide utilisateur (publié sur le site par la CI) |
| RAPPORT-BACKTEST.md | honesteté du moteur : bugs attrapés, calibration (publié sur le site) |
| docs/ | documents de travail : conception, installation, déploiement, plan plateforme, recherches, prompts design, guide Supabase |

## ⚽ CHAMPIONNATS (ligues)
| Fichier | Rôle |
|---|---|
| data/2*.csv | résultats bruts football-data.co.uk : 21 divisions × 6 saisons (buts FTHG/FTAG, corners HC/AC, cartons, fautes, tirs) — versionnés (le site source est en 503) |
| entraine.py | entraînement : lit les CSV → écrit data/modeles.json (forces attaque/défense par équipe, gamma, rho, xG réels pour les 5 grands) |
| moteur_v3.py | le moteur mathématique (Dixon-Coles, fit_goals / fit_xg / combine) |
| data/modeles.json | le modèle entraîné (forces par division + marchés secondaires + arbitres) |
| analyse_divisions.py | mesure de fiabilité PAR division (walk-forward) → data/analyse_divisions.json — a justifié la règle des divisions instables |

## 🏆 COUPES (Ligue des champions, Europa, Conference, coupes nationales)
| Fichier | Rôle |
|---|---|
| coupes.py | la liste des coupes (pseudo-divisions UCL/UEL/UECL/Carabao/Copa/DFB/Coupe de France/Coppa) + slugs ESPN |
| serveur.py (section coupes) | forces approximées inter-ligues — jamais dans les sélections suivies |

## 🔎 RECHERCHE DES MATCHS (calendrier, résultats, horaires)
| Fichier | Rôle |
|---|---|
| calendrier.py | calendrier multi-sources : ESPN (principal), TheSportsDB, OpenLigaDB (secours) ; traduction des noms ESPN → co.uk (Mappeur) |
| maj_calendrier.py | reconstruction horaire du calendrier + il enchaîne : corners 1re MT → fatigue européenne → compositions H−1. C'est LE point d'entrée de la CI pour tout ce qui est « frais » |
| maj.py | télécharge les CSV co.uk quand ils changent, ré-entraîne si utile, régénère l'app ; code 2 = source injoignable (non bloquant) |
| resultats.py | résolution des résultats (scores finaux) |
| db.py | double écriture Supabase (sélections, combinés, journal) — upsert, jamais de doublon |
| data/calendrier.json | le calendrier courant (matchs à venir avec dates/heures/arbitres) |
| data/resultats_espn.json | résultats récents capturés par ESPN (boucle rapide, avant publication co.uk) |

## 🥱 FATIGUE EUROPÉENNE (étape ③)
| Fichier | Rôle |
|---|---|
| fatigue.py | équipe jouant C1/C2/C3 < 7 jours avant le championnat → multiplicateurs MESURÉS (barème par jours de repos : 3 j = rien, 4 j = −6 % attaque/+4 % défense encaissée…) |
| data/fatigue_coupes.json | 1 098+ matchs de coupes d'Europe collectés (3 saisons) |
| data/fatigue_mesuree.json | le barème mesuré (2 793 apparitions) |

## 👥 COMPOSITIONS ET ABSENCES (étape ④)
| Fichier | Rôle |
|---|---|
| compos.py | collecte les compositions ESPN (terminés + matchs à ~1 h du coup d'envoi), détecte les absents/banc vs onze attendu (titulaire = ≥ 60 % des matchs), mesure l'impact dès 60 matchs par niveau — information seule jusque-là |
| data/compos.json | compositions stockées (60 derniers jours) |
| data/absences_mesuree.json | barème d'impact (vide jusqu'à assez de données — voulu) |

## 🚩 CORNERS
| Fichier | Rôle |
|---|---|
| corners.py | calibration SAFE (fréquences réelles walk-forward) + choisir_jambe : handicap le plus pénalisant ≥ 85 % ET cote ≥ 1,05 |
| corners_mt.py | corners de 1re MI-TEMPS (collecte commentary ESPN, 8 divisions, 5 750 matchs) — informatif, jamais dans le safe |
| backtest_corners.py / analyse_corners.py | les backtests qui ont produit la calibration |
| data/corners_mt.json | corners MT1 match par match |
| data/backtest_corners.json / analyse_corners.json | cellules de calibration mesurées |
| data/mt1_mesure.json | pourquoi la 1re MT n'est jamais « safe » (chiffres mesurés) |

## ⚽ BUTS D'AFFILÉE (10/09 — phase 2 locale, non poussée)
| Fichier | Rôle |
|---|---|
| buts_affilee.py | collecte ESPN des buts minutés (commentary complet, attribution par équipe structurée) + rapport de validation + commande `calibrer [--corriger]` (jointure backtest ↔ cache) |
| series_buts.py | source unique du modèle : formules exactes `p_serie`, correction walk-forward figée `CORRECTION_SERIE2` / `p_serie2`. Miroir JS généré dans l'autonome (genere_app.py) — jamais dupliquer |
| data/buts_minutes.json | cache des buts minutés (Big 5 2024-25 + 2025-26, ~3 500 matchs, commité) |
| data/buts_affilee_stats.json / data/buts_affilee_calibration.json | mesures phase 1 + calibration walk-forward phase 2 |
| docs/SPEC-BUTS-AFFILEE.md | définition, méthode, chiffres, critères d'acceptation |

## 🟨 CARTONS, FAUTES (et totaux corners) — marchés secondaires
| Fichier | Rôle |
|---|---|
| modeles_secondaires.py | fautes / corners / cartons par équipe + effet arbitre + confrontation corners |
| backtest_secondaires.py / test_marches_secondaires.py | calibration de ces marchés |
| data/modeles.json (section « secondaires ») | facteurs par équipe et par arbitre |

## 🎯 SÉLECTIONS, COMBINÉS, SUIVI
| Fichier | Rôle |
|---|---|
| serveur.py | API locale : pronostics (matrice_scores), conseils du jour (api_conseils + DIVS_INSTABLES), combinés (_combinaisons : SAFE, SAFE 2, week-end, risque, cote 2/5, fun), coupons |
| suivi.py | archivage des sélections + résolution des résultats + bilan |
| data/suivi.json | l'historique des sélections (dans git ≠ état live : la mémoire live = cache CI + Supabase) |
| backfill_suivi.py / rattrapage | reconstruction de l'historique |
| cotes_live.py | cotes Pinnacle via The Odds API (clé en Secret CI uniquement) |

## 📱 INTERFACE
| Fichier | Rôle |
|---|---|
| static/index.html | l'écran unique (onglets : matchs, conseils, suivi, coupon, sim, fleuves, secondaires, corners, classement, bilan, admin) — partagé serveur ET app autonome |
| genere_app.py | fabrique pronos-foot-autonome.html : embarque les données + miroirs JS exacts du serveur (matriceScores, pronosticJS, secondairesJS, fatigueCoeffsJS, confrontationCornersJS…) |
| pronos-foot-autonome.html | LE fichier publié (GitHub Pages le sert comme index.html) |
| test_app_autonome.js | test de parité : l'app autonome doit répondre comme le serveur (0 écart) |

## ⚙️ AUTOMATISATION
| Fichier | Rôle |
|---|---|
| .github/workflows/maj.yml | CI horaire (:07 UTC) : maj.py → maj_calendrier.py → db.py --sync → genere_app.py → garde-fous → publication Pages |
| supabase/ | schema.sql + RLS (admin, partenaires, vitrine) — déjà collés dans Supabase |

## 🧪 XG ET TESTS DIVERS
| Fichier | Rôle |
|---|---|
| xg.py / calibre_xg.py / data/xg_understat.json / coef_xg.json | xG réels Understat (5 grands championnats) |
| test_ab.py, test_recalage.py, test_signal.py, test_xg_reel.py | tests A/B historiques |
| analyse_coupon.py, simule_coupon.py | simulations de coupons |
| moteur.py | ancienne version du moteur (historique — ne pas utiliser) |

## 🛍️ LA VITRINE (autre dépôt : ~/vitrine)
| Fichier | Rôle |
|---|---|
| src/*.html | les pages sources (accueil, sélections, bilan, coins, inscription, connexion, activation, paiement, accès) |
| assemble.py | construit docs/ depuis src/ (injecte Supabase + config + app.js) |
| docs/ | le site publié (sylvermelo.github.io/vitrine) |
| docs/assets/app.js | la logique : connexion, abonnement 30 j, codes promo, verdicts des sélections (lit les tables `selections`, `combines`, `abonnements` écrites par db.py côté robot) |
| docs/assets/config.js | URL + clé anon Supabase (publique, protégée par RLS) |
