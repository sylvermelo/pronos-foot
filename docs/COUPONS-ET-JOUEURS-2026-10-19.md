# Coupons, buteurs et passes décisives — 19 octobre 2026

## Modification autorisée

Cote 2 : un ou deux matchs, fourchette 1,90–2,35. Cote 5 : trois ou quatre matchs, fourchette 4,60–5,90. Aucun seuil de sélection abaissé. Aucune obligation de publier un coupon.

Les options éligibles sont comparées par une recherche des combinaisons, plutôt que prises dans l'ordre. Priorité : probabilité combinée estimée maximale, puis moins de matchs, puis proximité du milieu de la fourchette. Une seule option par rencontre et un même bookmaker. Les options sans prix réel ou sans avantage estimé positif restent exclues. Les seuils renforcés des divisions instables restent actifs.

Les matchs du SAFE sont réadmis dans les coupons cibles et l'interface du robot signale ce partage. Cela concentre le risque entre coupons ; ne pas interpréter deux coupons partageant une rencontre comme deux essais indépendants. La nouvelle recherche s'applique aussi au FUN, toujours plafonné à trois matchs. Aucun changement du modèle de probabilités ou des archives des anciens coupons.

Quatre matchs ne sont pas automatiquement plus sûrs que trois. À titre d'illustration, sous indépendance, trois paris à 80 % donnent 51,2 % de réussite ensemble et quatre donnent 40,96 %. Pour un prix total fixé, les probabilités de chaque jambe changent : il faut comparer les coupons complets, pas seulement leur longueur. Les produits du modèle restent des approximations à valider ; l'optimisation peut amplifier une mauvaise calibration.

## Vérifications

25 tests unitaires, dont oracle exhaustif indépendant sur 40 pools synthétiques de dix rencontres, comparaison Python/JavaScript sur ces pools non vides, cas où l'ancienne recherche échoue, réadmission SAFE, trois/quatre matchs, abstention, bookmaker unique et doublons. Pas de nouvelle mesure de rentabilité : les archives auditées sans prix bookmaker ne permettent pas un backtest de cette stratégie à prix réels. Aucun pourcentage d'amélioration revendiqué.

## État réel de la base joueurs

Le cache local examiné contient 549 compositions. Le module compos.py conserve seulement identifiant, nom, poste et statut titulaire, avec une rétention de 60 jours. Cela ne constitue pas un historique joueur par match pour apprendre les buts et passes. Les forces et xG du modèle actuel sont des données d'équipes : elles ne désignent pas un buteur.

Contrôle réseau effectué le 19/10 : résumé ESPN eng.1, événement 401879291. Les entrées roster contiennent notamment des statistiques nommées totalGoals, goalAssists, totalShots et shotsOnTarget, en plus des informations de remplacement. L'extracteur actuel les abandonne. C'est une piste concrète de collecte mutualisée, pas une garantie de complétude sur toutes les compétitions ou de stabilité du service. Ne pas remplacer un champ absent par zéro. Ne pas assimiler une statistique cumulée de saison à une statistique du match sans contrôler son périmètre. Comparer les sommes joueurs au score, isoler les buts contre son camp et vérifier les passes avec les événements.

## Méthode recommandée pour les buteurs

1. Construire un historique durable par identifiant joueur et événement : date, équipe, adversaire, titulaire, minutes réellement jouées, buts hors penalty, penalties, tirs, tirs cadrés ; xG individuels seulement si une source complète est validée. Documenter les absences de données et changements de club.
2. Estimer la participation et le temps de jeu. Distinguer estimation avant composition et estimation après composition officielle. Un attaquant susceptible de ne jouer que vingt minutes ne doit pas recevoir une probabilité de match entier.
3. Estimer son rythme de buts par minute, en rapprochant les petits échantillons d'un niveau de référence validé. Estimer les paramètres et la pondération temporelle sur l'entraînement, sans coefficients inventés. Distinguer rôle sur penalty et rendement hors penalty.
4. Relier cette part individuelle aux buts attendus de l'équipe contre cet adversaire. Ne pas appliquer deux fois la force de l'adversaire. Pour une base Poisson à tester, P(au moins un but | temps de jeu) = 1 − exp(−lambda_joueur). Intégrer ensuite l'incertitude de participation et de minutes ; ne pas substituer automatiquement la moyenne des minutes dans la formule.
5. Comparer aux vraies cotes « marque à tout moment » du même événement ; archiver le prix, sa date et les conditions de règlement. Sans cote ou données suffisantes : analyse seulement. Aucun mélange automatique dans les coupons d'équipes.

## Méthode recommandée pour les passes décisives

Historique distinct par joueur et match : passes attribuées, minutes, rôle sur coups de pied arrêtés, occasions créées/passes clés et xA si réellement disponibles. Les tirs et buts seuls ne mesurent pas correctement la création d'occasions. Le talent de finition des partenaires, la composition et le rôle tactique comptent ; mesurer leur apport plutôt qu'inventer un bonus.

Construire un modèle de fréquence des passes par minute avec régularisation, tester une base Poisson puis une alternative si la dispersion le justifie. Définir l'événement « au moins une passe » et le périmètre réglementaire. Archiver la source et le verdict bookmaker : une passe attribuée par un fournisseur peut ne pas répondre à ses règles. But et passe d'un joueur dans le même match sont dépendants ; ne pas multiplier leurs probabilités pour fabriquer un « buteur OU passeur ».

## Données et cotes gratuites

The Odds API documente pour le football player_goal_scorer_anytime et player_assists. Couverture annoncée : EPL, Ligue 1, Bundesliga, Serie A, Liga, MLS ; bookmakers US uniquement. Pas de couverture européenne universelle ou Champions League garantie. Notre collecteur actuel demande la région eu et les marchés alternate_totals,double_chance : il ne collecte ni ces cotes individuelles ni les prix US. Tester les marchés et bookmakers réellement renvoyés avant intégration.

https://the-odds-api.com/sports-odds-data/betting-markets.html#soccer-player-props-api
https://the-odds-api.com/liveapi/guides/v4/

Les 500 crédits et la réserve de 80 restent communs au robot. Un marché joueur supplémentaire ne doit pas être ajouté à toutes les rencontres sans arbitrage : à titre nominal, deux marchés × un événement/jour × une région représentent 62 crédits sur 31 jours pour une collecte quotidienne, à vérifier dans les en-têtes réels et à prélever dans le budget global. Aucun appel ajouté par cette modification. Pas de rafraîchissement de cotes à chaque visite. La couverture d'une région US n'implique pas qu'un bookmaker utilisé par le client au Bénin propose le même marché ou prix.

football-data.org : le plan gratuit publié liste calendriers, classements et scores différés, dix appels/minute. Les buteurs/compositions détaillés sont listés dans Free + Deep Data à 29 €/mois : ce n'est pas une solution gratuite démontrée pour l'historique individuel nécessaire. Aucun compte ou abonnement créé.

https://www.football-data.org/pricing

## Ordre de mise en œuvre proposé

Commencer par conserver les statistiques joueurs issues des résumés déjà mutualisés, en mode observation et sans nouveau coupon. Contrôler plusieurs championnats, les minutes, les zéros et données manquantes, les remplaçants, les penalties et les corrections. Puis tester les buteurs sur un découpage chronologique strict ; développer les passeurs après validation des données de création. Comparer calibration, Brier/log-loss et couverture, puis ROI seulement avec prix réellement archivés avant match. Geler chaque prédiction avant le coup d'envoi. Un classement de joueurs ne suffit pas à valider un modèle.

Aucune sélection nominative aujourd'hui : aucun match précis demandé, et aucun historique individuel complet validé. Cette analyse décrit la faisabilité et la logique à construire ; elle n'annonce pas un module joueurs opérationnel.
