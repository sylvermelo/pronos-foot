# Module buteurs — mise en œuvre du 19 octobre 2026

## Ce qui est livré

La demande utilisateur autorise récupération des buteurs, apprentissage, intégration et publication. Un onglet Buteurs est ajouté au robot et aux sélections de la vitrine. Cinq championnats : Premier League, Liga, Serie A, Bundesliga, Ligue 1. Les passes décisives et tirs sont conservés comme observations ; aucun modèle passeur n'est annoncé comme opérationnel.

Le robot conserve les statistiques individuelles de chaque match, apprend sur les résultats terminés et produit des probabilités de marquer au moins une fois, conditionnelles à une titularisation. Avant composition officielle : liste d'observation. Après composition reçue avant coup d'envoi : les titulaires sont identifiés et une prévision est figée pour le suivi futur. Une estimation sans prix reste une analyse, jamais un coupon forcé.

## Mémoire réellement amorcée

- 320 matchs Big5 terminés, contrôlés contre le score, du 19/08 au 18/10/2026.
- 2 199 identités joueur-équipe-championnat observées ; un transfert dans un autre club constitue un contexte distinct.
- 320 lignes confirmées dans public.joueurs_matchs après sauvegarde initiale. Table et index environ 1 Mo ; base totale environ 14 Mo à ce contrôle, contre 500 Mo en offre Free. Ce n'est pas une mesure de l'egress mensuel réel.
- Tables joueurs_matchs et buteurs_previsions privées : RLS activée, privilèges anon/authenticated retirés, accès de traitement service_role. Aucune clé serveur dans le navigateur.

Le cache Actions accélère les traitements. Supabase permet de restaurer l'historique après perte du cache. Les écritures sont des upserts des seules données nouvelles/corrigées, identifiées par empreinte. Une écriture échouée reste à retenter. Les prévisions utilisent une insertion qui ignore les doublons : elles ne sont pas remplacées par une version entraînée après le match. Le règlement se recalcule depuis les scores joueurs sans modifier la prévision.

## Comment le robot raisonne

1. Il vérifie le match, sa compétition, les deux équipes, onze titulaires de chaque côté et le statut. Les rencontres en prolongations ne sont pas mélangées au périmètre réglementaire.
2. Il conserve buts personnels, buts contre son camp, tirs, tirs cadrés, passes, titularisation et minutes. Les champs manquants restent manquants. Les sommes des buts personnels et des CSC adverses doivent rejoindre le score final avant apprentissage.
3. Les minutes sont des expositions réglementaires reconstruites à partir des remplacements et expulsions : arrêt à 45/90 pour éviter de compter les arrêts de première période comme seconde période. Elles ne sont pas des mesures exactes du temps effectif. Une substitution non documentée ne devient pas arbitrairement un match entier.
4. Il exige au moins cinq apparitions et 180 minutes pour le joueur, trois titularisations antérieures et 60 observations pour sa référence poste/championnat. Les gardiens et postes inconnus ne sont pas proposés.
5. Il mesure un rythme de buts par minute et le rapproche d'une référence poste/championnat, en retirant la contribution du joueur à cette référence. La force de régularisation est choisie parmi 90/450/900/1800 minutes sur la période de validation seulement. Les observations d'autres clubs ne sont pas assimilées automatiquement au nouveau club.
6. Le modèle Gamma-Poisson calcule la probabilité d'au moins un but pour chaque durée de titularisation observée, puis moyenne ces probabilités. Il ne remplace pas cette distribution de durées par une probabilité de match entier. L'intervalle affiché représente l'incertitude du taux dans ce modèle ; ce n'est pas une garantie de calibration ou de résultat.
7. Un résultat nouveau/corrigé change l'empreinte et entraîne une nouvelle estimation. Une simple nouvelle date de téléchargement ne déclenche pas l'apprentissage. Le navigateur reçoit le même export pré-calculé que le serveur ; il n'entraîne pas une autre version du modèle.

Cette version n'ajoute pas de bonus subjectif pour un joueur connu, des penalties présumés ou une défense réputée faible. L'adversaire, la qualité du onze adverse, le rôle actuel sur penalties, les xG individuels et les changements tactiques ne sont pas ajustés séparément faute de validation. Ces limites sont affichées. Les tirs et passes récupérés ne deviennent pas de faux coefficients de performance.

## Vérification chronologique initiale

Découpage par dates : 60 % historique initial, 20 % validation et choix de régularisation, 20 % test ultérieur. Tous les matchs d'un jour sont évalués avant que les données de ce jour soient apprises. Les prédictions de chaque match test utilisent seulement les observations précédentes.

Mesure initiale avant publication :

| Mesure | Modèle buteur | Référence poste/championnat |
|---|---:|---:|
| Prévisions de test | 802 | 802 |
| Matchs distincts de test | 73 | 73 |
| Joueurs ayant marqué dans ces observations | 96 | 96 |
| Brier (plus petit = meilleur) | 0,096384 | 0,097987 |
| Log-loss (plus petit = meilleur) | 0,331233 | 0,334992 |

Validation séparée : 113 prévisions dans 15 matchs. Régularisation choisie : 450 minutes. Le test débute le 09/10/2026, après la validation débutant le 14/09. Le statut automatique est « validation_initiale » parce que les seuils minimaux et les deux comparaisons sont satisfaits. Cela ne démontre ni une amélioration statistiquement significative ni une rentabilité. Les joueurs d'un même match sont dépendants ; 802 observations ne correspondent pas à 802 matchs indépendants. Le suivi prospectif commence avec les prochaines compositions capturées avant match.

Les données d'archives n'ont pas les prix bookmaker des buteurs à la décision : aucun ROI historique inventé. Aucun combiné de buteurs, aucun ajout automatique aux SAFE/cote 2/cote 5.

## Cotes bookmakers

The Odds API documente player_goal_scorer_anytime et les passes, mais sa couverture football individuelle annoncée est limitée aux bookmakers US sur les cinq grands championnats et MLS. Notre module demande exclusivement le marché buteur à tout moment, un événement/jour maximum, région US, en réutilisant les identifiants des matchs déjà cotés par le robot. Un prix US ne signifie pas qu'un bookmaker utilisé au Bénin propose le même pari ou prix.

Nom complet normalisé, événement, heure, marché, sens, ligne, bookmaker et horodatages doivent correspondre. Les homonymes sont rejetés. Aucun prix déduit de 1/p, des tirs ou d'un autre marché. Sans clé, sans quota fiable, sans match correspondant ou sans prix : « cote indisponible ». Les prix expirés sont retirés de l'affichage courant. Les prix reçus avant le gel restent archivés avec la décision.

Budget commun : 500 crédits par cycle, réserve 80. Maximum nominal 310 crédits/31 jours pour les cinq événements × deux marchés d'équipes, plus 31 pour le marché buteur quotidien = 341. Les en-têtes réels restent prioritaires, le crédit est réservé dans le ledger avant la requête et aucune multiplication d'appels n'a lieu en cas de quota inconnu. Aucun appel bookmaker depuis les visiteurs.

## Collectes et gratuité

- Cache HTTP partagé avec les compositions. Les résumés déjà collectés sont réutilisés.
- Quatre connexions simultanées maximum. Par passage habituel : 16 résumés maximum ; par jour : 160 historiques et une réserve de 80 récents/compositions. L'amorçage manuel exceptionnel est plafonné à 320 historiques. Les plafonds sont des règles internes, pas des quotas ESPN officiels.
- Les scoreboards hier/aujourd'hui et trois jours historiques supplémentaires sont consultés toutes les six heures au maximum. Une composition proche du coup d'envoi peut être retentée à quinze minutes. Les appels résultats récents restent possibles après l'amorçage historique.
- Fenêtre progressive de rattrapage de 90 jours ; pas de suppression des matchs déjà conservés. Une seconde lecture après 24 h permet un contrôle des corrections de matchs valides. Les statistiques manquantes sont reprises, au maximum toutes les six heures pour un résultat invalide.
- Restauration Supabase au plus quotidienne, puis deltas par curseur ; pages sans lecture directe de ces tables. Le visiteur charge un petit JSON publié sur Pages et non les historiques complets.
- 500 Mo de base et 5 Go d'egress Free recontrôlés dans la tarification officielle le 19/10. Marge de 30 % conservée dans les règles de projet ; surveiller la croissance réelle, aucun volume illimité promis. Pas de service ou plan payant activé.

## Défaut corrigé dans l'ancien collecteur

compos.collecter ignorait un match fini dès qu'une composition existait, même si elle avait été reçue avant match. Il doit désormais actualiser une composition pré-match avec le résumé final. Le test de régression reproduit cette transition et vérifie l'intégration dans la mémoire individuelle.

## Vérifications et déploiement

40 tests unitaires passent, dont : zéros/manquants, CSC, substitutions, prolongations, petits échantillons, chronologie, correction des scores, empreinte, immutabilité des prévisions, reprises de sauvegarde et quota inconnu. Parité de l'export buteur et tests des onglets du robot réussis. Tests des cinq pages de la vitrine réussis.

Les tables ont été contrôlées après création : anon/authenticated n'ont aucun accès et service_role peut insérer. L'advisor signale l'absence de politiques publiques, intentionnelle pour ces tables privées : https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy . Les anciens avertissements de l'infrastructure d'affiliation ne sont pas modifiés par cette livraison.

Le déploiement réel est contrôlé via GitHub Actions et la réponse des sites. Les nombres de matchs et mesures peuvent augmenter après publication au rythme des nouvelles données. Le suivi des prévisions futures n'est pas présenté comme déjà rempli.

## Fichiers

- buteurs_collecte.py : extraction, contrôle, collecte, mémoire privée et synchronisation.
- buteurs_modele.py : apprentissage et validation chronologique.
- buteurs_cotes.py : vrai marché buteur, rapprochement exact et budget partagé.
- buteurs.py : orchestration, gel, résultats et export.
- compos.py, db.py, serveur.py, genere_app.py, static/index.html et workflow : intégrations.
- supabase/buteurs.sql : schéma privé, tests/test_buteurs.py : régressions.
- Vitrine : docs/assets/app.js et docs/sw.js, onglet Buteurs dans Sélections.

Sources officielles :
https://the-odds-api.com/sports-odds-data/betting-markets.html#soccer-player-props-api
https://the-odds-api.com/liveapi/guides/v4/
https://supabase.com/pricing
https://supabase.com/docs/guides/database/postgres/row-level-security
