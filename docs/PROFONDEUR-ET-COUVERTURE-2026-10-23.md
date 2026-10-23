# Pourquoi des matchs manquaient et ce qui change

Le chiffre 549 était celui du test indépendant NHL, et non celui de tout l'apprentissage. La première version utilisait 2 285 rencontres historiques. Les bilans sont désormais explicites : historique total, apprentissage initial, validation pour choisir les réglages, test distinct, suivi futur.

## Horaires

Les rencontres NHL de la soirée américaine du 23 octobre commencent à 01:00 et 02:00 le 24 au Bénin. L'ancien écran affichait uniquement la date béninoise. Chaque carte montre maintenant la soirée NHL et la date/heure au Bénin ; le filtre permet de choisir son référentiel. Le coup d'envoi UTC ne change pas. La journée officielle `gameDate` est prioritaire ; le calendrier new-yorkais sert de repli.

## NHL : données et évaluation

- Équipes : 8 675 matchs, saisons 2019/20 à 2026/27. Scores 60 minutes séparés des scores finaux, tirs au but artificiels exclus des 60 minutes.
- Modèle équipes v2 : attaque, défense, domicile et repos appris. Repos désormais calculé en jours de calendrier NHL, car les anciens rapports n'ont pas tous l'heure exacte.
- Découpage initial : 5 128 matchs apprentissage, 1 705 validation, 1 794 test. Réentraînement historique par blocs, passé seul. Dernier ajustement sur tout l'historique pour les nouvelles prévisions.
- Test vainqueur final : erreur logarithmique 0,6829 contre 0,6900 pour la fréquence domicile. Réussite 55,85 %. Intervalle bootstrap du gain de précision [-0,0011 ; 0,0167] : zéro reste inclus, donc preuve insuffisante d'un avantage robuste. Le résultat 60 minutes est légèrement moins bon que la référence sur ce test.
- Joueurs : 147 598 observations joueur-match, 4 101 matchs, 1 222 joueurs, trois saisons closes et la saison courante. Ce ne sont pas 147 598 matchs différents.
- Marchés individuels : au moins un but, une passe, un point (but ou passe), prolongation incluse, tirs au but exclus. Temps de glace estimé sur les dix dernières apparitions, jamais le temps réellement joué dans le futur. Identité NHL stable entre clubs.
- Réglage chronologique Gamma-Poisson ; pour les buts, mélange facultatif avec tirs et conversion, retenu seulement par validation. Aucun bonus arbitraire d'adversaire ou de blessure.
- Test joueurs : 856 matchs / 30 010 observations ; erreur buteur 0,3966 vs 0,4161, passeur 0,5215 vs 0,5562, point 0,5951 vs 0,6426. Référence : fréquence historique au même poste.
- Les profils sont conditionnels à la participation. Les absences, lignes futures, avantage numérique futur et gardien adverse confirmé ne sont pas intégrés. L'équipe est celle de la dernière apparition observée. Fenêtre de publication joueurs : 48 h ; source de plus de 48 h : profils suspendus.
- Prévisions figées avant match, version conservée ; pas de réécriture des anciennes prévisions avec le nouveau modèle. Résultats absents jamais transformés en zéro, changement de calendrier signalé.

Sources : calendriers `api-web.nhle.com/v1`, rapports officiels `api.nhle.com/stats/rest/en`. Rapports individuels mensuels contrôlés contre la troncature 10 000 lignes. Collecte initiale exceptionnelle bornée à 100 appels ; routine supplémentaire une fois/jour, deux rapports récents, dans le plafond NHL commun de 40 appels/jour. Cache local/Actions ; aucun appel fournisseur depuis les visiteurs. Ce plafond interne n'est pas une affirmation de quota ou de licence commerciale du fournisseur.

## UEFA : un modèle séparé

L'ancien écran empruntait les modèles domestiques ; un club absent de ces championnats restait sans analyse. Désormais : API officielle UEFA paginée, identifiants stables, contrôle de l'identifiant de compétition (UCL 1, UEL 14, UECL 2019), uniquement score réglementaire, jamais score cumulé/prolongation/tirs au but.

4 098 matchs terminés, saisons finissant de 2023 à 2027, qualifications incluses. Attaques/défenses de clubs et références par pays apprises, régularisation et ancienneté choisies sur validation. Découpage initial 2 462 apprentissage / 857 validation / 779 test. Parmi les 779 matchs du test, 564 étaient analysables avec au moins six rencontres passées par club : erreur 0,9495 vs 1,0417, réussite de l'issue la plus probable 55,85 %. La couverture du test est partielle : les clubs nouveaux ne sont pas assimilés artificiellement aux autres.

Au moment du contrôle : 54 prochains matchs affichés, dont 47 analyses UEFA, contre 22 analyses inter-ligues dans l'ancienne vue. Pour les sept autres, nombres de rencontres par club et minimum nécessaire affichés. Une journée UEFA partielle ne masque pas les matchs du calendrier ESPN de secours. Les calendriers fermés sont mis en cache ; saison actuelle toutes les six heures au plus, pagination bornée et deux connexions. Une erreur de source est conservée explicitement.

Modèle expérimental ; finales sur terrain neutre non ajustées séparément, compositions/blessures non intégrées. Prévisions UEFA archivées avant match ; aucun coupon automatique.

## Buteurs football : faiblesse encore présente

L'ancien apprentissage utilisait environ 325 matchs individuels récents. L'ajout de 8 326 bilans joueur-saison Understat, sur trois saisons closes des cinq grandes ligues, ne transforme pas ces bilans en milliers de matchs individuels. Ils apportent buts, xG, tirs, minutes et passes ; identité stricte par nom normalisé et identifiant unique, homonymes refusés. Une saison ne devient disponible qu'après sa clôture, jamais pour prédire ses propres matchs.

Les références sont évaluées avec plusieurs poids et mélanges buts/xG. Sur le test local final (339 matchs individuels valides, après 320 résumés collectés/recontrôlés), le réglage de validation préfère un poids de référence nul. On n'impose donc pas cet enrichissement. Test : 1 070 observations sur 87 matchs, Brier 0,09753 vs 0,09742, erreur logarithmique 0,33479 vs 0,33293. Le modèle ne bat pas la référence sur ce test : statut expérimental, aucune supériorité annoncée. Les nombres du site évolueront selon la mémoire privée CI, plus récente que le clone local.

Corrections de collecte : limite de 90 jours remplacée par une cible de trois ans ; journées échouées conservées pour reprise ; miroir officiel ESPN pour scoreboards et résumés ; budgets existants conservés (16 résumés/passage, 160 historiques + 80 récents/jour, amorçage exceptionnel 320). Ce rattrapage est progressif, pas trois années déjà complètes. Les bilans de saisons Understat sont versionnés ; la mémoire brute ESPN et les prévisions restent privées dans les mécanismes existants.

L'adversaire, les penalties, les passes décisives football et les compositions futures ne bénéficient pas encore d'un modèle individuel validé. Ces limites restent visibles. Aucune meilleure rentabilité n'est démontrée.

## Publication et contrôles

Les amorçages versionnés sont préservés avant la restauration du cache Actions puis réappliqués sans remplacer les mémoires live. Aucun crédit Odds API supplémentaire. Sans prix bookmaker reçu et exact : analyse seule. Les sources publiques ne signifient pas autorisation commerciale illimitée.

Tests : 56 tests Python, filtres/échappement/tri et dates dans les vues JS, parité serveur/app autonome, parcours des onglets, sept pages vitrine. Le test DOM ne remplace pas un contrôle visuel dans un navigateur réel.
