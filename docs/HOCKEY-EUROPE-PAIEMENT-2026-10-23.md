# Hockey, Europe et paiement — 23 octobre 2026

## Résultat et limites

Le robot NHL est implémenté et relié à un onglet dédié dans le robot et à hockey.html dans la vitrine. Le calendrier européen a sa page europe.html, avec raccourcis persistants. La migration de la vitrine vers Cloudflare est préparée ; aucun compte Cloudflare connecté n’est disponible, donc aucune nouvelle adresse n’est annoncée. Les paiements automatiques ne sont pas activés : un changement d’hébergement ne suffit pas, et FedaPay exige un accord écrit préalable pour les prévisions sportives. Les détails d’installation et le circuit de paiement sûr sont dans vitrine/HEBERGEMENT-ET-PAIEMENT.md.

## NHL : modèle et données

- Périmètre initial : saison régulière NHL. Pré-saison, playoffs, matchs reportés/annulés ou scores incomplets exclus de l’apprentissage. Les identifiants NHL remplacent les rapprochements approximatifs de noms.
- Collecte initiale : 75 calendriers de clubs disponibles sur 96, avec déduplication. 2 285 rencontres terminées utilisables ; saison 2025/26 complète dans l’échantillon, saison 2024/25 partielle, saison courante amorcée. Les sources manquantes ne deviennent pas des scores zéro.
- Modèle Poisson attaque/défense régularisé, avantage domicile, différence de repos et enchaînement à moins de 36 heures. Tous les coefficients sont ajustés aux observations. Décroissance temporelle et régularisation choisies parmi neuf candidats, sur validation chronologique.
- Un modèle logistique séparé apprend le gagnant conditionnel après égalité à 60 minutes. Les scores officiels de prolongation/tirs au but sont séparés des scores de temps réglementaire. Aucun but de départage artificiel dans l’apprentissage des buts à 60 minutes.
- Calibration prudente par mélange à une référence empirique, poids choisis sur la validation seule et pouvant devenir zéro. La référence peut remplacer le modèle lorsqu’il n’apporte rien sur la validation.
- Aucun effet de gardien, blessure, composition ou xG inventé. Ce premier modèle n’est pas une IA générale et ne dispose pas encore de ces données.

## Évaluation chronologique

Répartition par dates : 60 % entraînement, 20 % validation, 20 % test. Dans validation et test, chaque réentraînement par bloc de 28 jours ne voit que les dates antérieures au bloc. Les observations du test ne règlent ni les candidats ni le mélange. Embargo de huit heures et statut final avant admission des résultats à l’apprentissage.

Premier test : 549 rencontres du 28/02/2026 au 23/10/2026, favori final touché à 56,83 %, log-loss 0,67945 contre 0,69074 pour la référence simple ; Brier 0,24320. Les estimations du favori se concentrent entre 50 et 70 %. Ne pas annoncer des taux de réussite de 80–90 % ou une supériorité face au robot football : marchés et difficultés différents. Aucun ROI sans prix de décision.

La période et les résultats évoluent avec l’historique lors des réentraînements. Le suivi prospectif, distinct, conserve la première prévision avant coup d’envoi, sans remplacer sa probabilité après le résultat. Les reports devenus antérieurs au gel invalident la prévision au lieu de la compter comme une réussite.

## Mémoire et ressources

Historique compact et modèle seed versionnés pour un redémarrage sain. Les résultats nouveaux, modèles, sorties et prévisions sont conservés dans data/ via le cache CI existant. Le cache n’est pas une sauvegarde permanente : sa perte peut faire perdre le suivi prospectif, qui ne sera jamais reconstitué artificiellement après match. Une sauvegarde durable dédiée reste une amélioration à prévoir.

Collecte routine : trois semaines de calendrier au plus toutes les deux heures, deux connexions, plafond 40 appels/jour, zéro appel fournisseur au clic utilisateur. Amorçage explicite : plafond 100 appels, quatre connexions. Ce sont des plafonds internes, pas un quota contractuel NHL. Entraînement uniquement si données/version changent, au plus une fois toutes les six heures. Zéro crédit The Odds API supplémentaire. Les cotes NHL présentes dans certaines réponses ne sont pas reprises comme des prix vérifiés ; aucun coupon hockey automatique.

Droits de réutilisation commerciale NHL à clarifier avant commercialisation ; aucun accès public n’est présenté comme une licence : https://www.nhl.com/info/terms-of-service .

## Europe

Accès visible Ligue des champions, Europa League et Conference League. Les équipes absentes du modèle restent au calendrier sans probabilité inventée. Les coupes demeurent exclues des conseils/coupons automatiques. Réutilisation du calendrier déjà collecté par fatigue.py jusqu’à J+21, sans nouvelle tournée réseau. Le cache de calendrier est invalidé une fois pour appliquer la correction. Les scoreboards essaient le domaine web ESPN puis l’ancien domaine seulement si la réponse est invalide ; une vraie liste vide ne déclenche pas de deuxième appel.

## Contrôles

51 tests Python validés. Tests de période NHL, tirs au but, score zéro/absent, date béninoise, distribution, gel de prévision, absence de fuite temporelle, convergence, repos, coupes inconnues, filtres et tri JS. Harnais des sept pages vitrine, tous les onglets du robot et parité des exports Python/navigateur. Pas d’achat réel ni de parcours visuel complet sur appareil.
