# Mise à jour demandée le 18 octobre 2026

## Demande et état de départ

L'utilisateur a autorisé l'application des corrections, demandé une meilleure réflexion du robot, une mémoire des matchs terminés, le retour des coupes et des résultats exotiques, et un bilan le lendemain matin. Aucun abonnement payant ni changement d'adresse. Au début de l'intervention, les trois branches distantes correspondaient aux clones ; aucune modification utilisateur nouvelle n'a été constatée. Ne pas attribuer à l'utilisateur les modifications décrites ci-dessous.

Adresses conservées :
- Robot : https://sylvermelo.github.io/pronos-foot/
- Vitrine : https://sylvermelo.github.io/vitrine/
- Affiliés : https://sylvermelo.github.io/affilies/

## Ce qui change dans la réflexion du robot

1. Les scores finaux des compétitions couvertes sont collectés avant l'entraînement. Les résultats nouveaux ou corrigés sont conservés dans la table privée `matchs` de Supabase ; une clé unique empêche les doublons. Une restauration quotidienne permet de retrouver ces scores si le cache GitHub disparaît. L'ancien effacement du complément au bout de 45 jours disparaît.
2. Une empreinte des données et une version du moteur déterminent s'il faut réentraîner. Actualiser une page ne déclenche aucun entraînement. Les prédictions archivées conservent leur décision d'origine au lieu de changer de probabilité après coup.
3. Le moteur estime la force offensive et défensive des équipes, leur évolution récente et l'avantage domicile. Les cinq grands championnats utilisent les xG Understat, recalés sur les buts ; ailleurs, les buts alimentent Dixon-Coles. Les nouveaux buts ont donc un effet sur les paramètres futurs, sans règle arbitraire « victoire = bonus ». Le téléchargement xG est tenté quotidiennement ; en cas d'indisponibilité, le cache est conservé.
4. Correction mathématique : la normalisation des forces doit conserver les intensités de buts domicile ET extérieur. Correction également du mélange de modèles et de l'évaluation Over/Under, qui inversait les étiquettes. La distribution secondaire utilisée par le backtest est maintenant cohérente avec le calcul de production.
5. Chaque option respecte d'abord son seuil propre, notamment la marge supplémentaire des unders. Le robot peut ensuite comparer les options réellement cotées par leur avantage estimé `probabilité × prix − 1`. Cet avantage reste une estimation dépendante de la qualité du modèle, jamais une certitude de bénéfice.
6. Sans cote exacte récente : analyse seule. Les combinés exigent des prix provenant du même bookmaker et restent limités à trois jambes. Le rattrapage automatique après une perte est désactivé. Aucun coupon corners/séries n'est fabriqué à partir de `1/p`.

Les matchs de coupe sont mémorisés séparément. Ils ne sont pas artificiellement assimilés à une rencontre de championnat : l'effet inter-ligues n'est pas calibré. Leur utilisation actuelle se limite notamment au calendrier et aux informations de fatigue ; ils ne déclenchent pas de conseils suivis sur une approximation inter-ligues.

## Calendrier et exotiques

- Les équipes inconnues du modèle ne font plus disparaître une rencontre de coupe : le match reste visible, avec analyse indisponible si nécessaire.
- Les correspondances d'équipes privilégient leur championnat actuel. La jointure des fixtures inclut la date.
- Un événement de coupe initialement programmé peut être mis à jour lorsqu'il devient final, au lieu de rester gelé dans le cache fatigue.
- Les buts `45+4` restent avant les buts de la seconde période à la 47e minute. L'ordre validé n'est plus retrié incorrectement lors du verdict des séries.
- Un 0–0 validé contient une liste de buts vide : ce n'est pas une donnée absente. Les résultats provisoirement non vérifiables sont retentés.
- Les corners finaux peuvent être lus dans ESPN sans attendre uniquement le CSV. Les valeurs nulles/absentes ne deviennent pas des zéros. Le statut final, le sens domicile/extérieur et la période sont vérifiés ; les prolongations ne sont pas assimilées au temps réglementaire.
- Les réponses HTTP compressées sont explicitement prises en charge.

La requête ESPN du 18 octobre sur la fenêtre 18–25 octobre a renvoyé une réponse JSON valide mais aucun événement UCL/UEL. Cela ne prouve pas l'absence de matchs réels : l'affichage des dates futures dépend encore de la couverture du fournisseur. Le cas d'une coupe avec équipe inconnue est couvert par un test de régression. Les anciennes calibrations de séries doivent encore être réévaluées sur un historique de buts entièrement retraité ; aucun coefficient n'a été inventé pour compenser.

## Cotes et budget gratuit

The Odds API est appelé uniquement par le serveur CI. Marchés ciblés : totaux alternatifs et double chance, pour cinq événements au maximum par jour, une région. Chaque prix conserve l'événement, le bookmaker, le marché, la ligne éventuelle, le sens et les horodatages. Prix âgé de plus de 24 h ou événement déjà commencé : inutilisable pour un nouveau conseil. Les anciennes moyennes CSV ne servent pas de remplacement.

| Opération | Fréquence/plafond configuré |
|---|---|
| Scores, verdicts et publication | Cron souhaité toutes les 15 minutes, soit 96 passages/jour ; GitHub peut retarder/sauter des passages |
| Calendrier complet et compléments lourds | Au plus toutes les 6 heures |
| Vérification des historiques CSV | Au plus toutes les 12 heures lorsque la source répond |
| xG | Actualisation quotidienne ; cache conservé en cas d'échec |
| Entraînement | Seulement si données/version changent |
| Cotes payantes en crédits gratuits | Au plus 10 crédits/jour, 310 sur 31 jours, réserve 80 ; arrêt si quota inconnu |
| Navigateur | Aucun appel au fournisseur de cotes ; aucun entraînement |

GitHub : dépôts publics et runners standard, donc pas de plafond de 2 000 minutes pour ces exécutions. Le stockage/cache et les conditions Pages restent distincts. Supabase Free : 500 Mo de base, 5 Go d'egress non caché/mois ; conserver 30 % de marge. Ne pas activer de facturation. Les compteurs mensuels réels d'egress ne sont pas disponibles dans cette intervention : un nombre garanti de visiteurs ou de rafraîchissements serait inventé.

La vitrine ne charge plus les gros champs JSON `brut` en double. Son bilan saisonnier utilise une fonction SQL qui agrège toutes les lignes visibles selon les protections existantes, sans limite arbitraire de 400/1 000 paris. Test anonyme réel : 420 sélections résolues, identiques au comptage direct ; résultat d'environ 9,3 Ko en représentation PostgreSQL (ce n'est pas une mesure réseau compressée). Les exotiques ne téléchargent plus l'historique SQL inutile. Leur bilan indique « période publiée » au lieu de faire passer quelques jours pour une saison complète. Les service workers des deux sites n'effacent plus les caches du voisin.

La disponibilité effective des cotes et des bookmakers doit être observée dans les prochaines publications : le code ne garantit pas que le fournisseur propose un prix pour tous les matchs, ni pour les séries/corners demandés. Sans couverture, l'abstention est normale.

## Validation chronologique

Le fichier `VALIDATION-2026-10-18.json` et le script `validation_modele.py` rendent la comparaison reproductible. Les derniers 120 matchs de chaque championnat sont réservés au test, l'entraînement est strictement antérieur ; 2 045 rencontres disposant d'équipes couvertes sont évaluées. Données locales disponibles jusqu'en septembre 2026, pas une évaluation des résultats futurs d'octobre.

| Mesure, modèle buts | Avant | Corrigé | Lecture |
|---|---:|---:|---|
| Log-loss 1X2, plus faible = mieux | 1,021424 | 1,023414 | légère dégradation |
| Log-loss Over/Under 2,5 | 0,686478 | 0,685508 | légère amélioration |
| Brier Over/Under 2,5 | 0,246678 | 0,246215 | légère amélioration |
| Favori 1X2 correct | 47,92 % | 48,02 % | écart faible, pas une preuve de gain |

Le sous-ensemble xG contient 462 matchs et ne se compare pas directement au total de 2 045. Ces mesures vérifient le cœur probabiliste, pas toute la stratégie avec fatigue, absences, choix et cotes historiques. Elles ne démontrent ni hausse générale du taux de réussite ni rentabilité. L'ancien taux de 81,9 % concernait 344 succès sur 420 sélections résolues, une autre population : il ne faut pas le comparer au taux de victoire du favori 1X2.

Vérifications : tests de régression des erreurs mathématiques et des données, compilation Python, réentraînement complet des 21 championnats, parité Python/JavaScript, harnais des onglets du robot et des cinq pages de vitrine, syntaxe des service workers, comptage SQL anonyme avec protections maintenues. La parité est désormais une étape bloquante avant publication du robot. Aucun historique live n'est remplacé par les JSON du clone.

## Alternative proposée et limites restantes

La meilleure prochaine étape est de mesurer cette version en conditions réelles avec des décisions figées, des probabilités, de vraies cotes datées et des résultats. Comparer ensuite, chronologiquement et par championnat/marché, le modèle actuel à une combinaison des probabilités du bookmaker corrigées de sa marge et du modèle sportif. Le poids de cette combinaison doit être appris sur une période séparée, pas choisi pour embellir le passé. Privilégier les paris simples et l'abstention ; augmenter le nombre de jambes ne rend pas le robot plus intelligent.

La base historique sportive existe, mais la mémoire Supabase était vide dans `matchs` au moment de l'audit. Le nouveau pipeline rend durable le complément de scores qu'il collecte ; il ne prétend pas avoir importé rétroactivement tous les CSV et tous les événements mondiaux. Les archives exotiques dépendent encore du cache CI et des fichiers publiés : leur sauvegarde privée exhaustive et la réévaluation historique des séries restent à traiter. Les xG n'arrivent pas nécessairement dès le coup de sifflet final. Un match manquant chez toutes les sources ne peut pas être inventé.

Les copies publiques du robot restent accessibles à l'URL demandée. Cette mise à jour ne transforme pas GitHub Pages en contrôle d'accès payant : la protection complète des analyses nécessiterait une autre architecture. Les sujets commerciaux et les règles de commission des affiliés ne sont pas modifiés ici. Aucun fournisseur abandonné n'est réactivé et aucun compte payant n'est créé.

Compte rendu programmé le 19 octobre à 08:00, heure de Porto-Novo : vérifier les commits et les workflows effectifs avant d'annoncer une publication réussie.

## Références de quotas consultées
- https://docs.github.com/en/billing/concepts/product-billing/github-actions
- https://supabase.com/docs/guides/platform/billing-on-supabase
- https://supabase.com/docs/guides/platform/manage-your-usage/egress
- https://the-odds-api.com/liveapi/guides/v4/
- https://the-odds-api.com/sports-odds-data/betting-markets.html

Le contrôle de sécurité Supabase a été relancé après ajout du bilan : la nouvelle fonction utilise les droits de l’appelant. Les alertes préexistantes (vue codes_promo, fonctions privilégiées, protection des mots de passe) ne sont pas déclarées résolues par cette mise à jour. Référence : https://supabase.com/docs/guides/database/database-linter?lint=0010_security_definer_view
