# RÈGLES — À LIRE OBLIGATOIREMENT AVANT CHAQUE SESSION DE TRAVAIL

Ce fichier existe à la demande de l'utilisateur (08/09/2026) :
« un dossier que tu dois te rappeler de lire à chaque fois, pour éviter des
bêtises ». Toute intervention sur le robot ou la vitrine commence ICI.
Voir aussi ORGANISATION.md (la carte complète des fichiers).

## 1. LES INTERDITS ABSOLUS

- **Le mot « trêve » est BANNI.** Ne jamais dire qu'il n'y a pas de matchs
  sans l'avoir vérifié. Même quand les championnats semblent arrêtés, il
  reste : Ligue des champions, Europa League, Conference League, Carabao,
  Copa del Rey, DFB-Pokal, Coupe de France, Coppa Italia, qualifications,
  matchs reportés. Vérification : interroger les scoreboards ESPN des
  coupes (slugs dans calendrier.py et coupes.py) ou lancer
  `python3 maj_calendrier.py` qui reconstruit tout.
  Erreur commise le 08/09/2026 : « trêve internationale » annoncée alors
  qu'il y avait 18 matchs de Ligue des champions le soir même.
- **Jamais de coefficient inventé.** Tout effet (fatigue, absences, corners,
  arbitres) doit être MESURÉ sur nos données, ≥ 60 matchs par palier, et
  appliqué uniquement dans le sens défavorable (principe conservateur).
  Tant que ce n'est pas mesuré : information affichée, calcul inchangé.
- **Aucune promesse de gain.** Probabilités ≠ certitudes. Limites et bugs
  documentés honnêtement.
- **Jamais le jeton GitHub ni aucune clé dans un fichier du dépôt** —
  uniquement en variable d'environnement ou dans les Secrets GitHub.
- **Ne jamais appeler The Odds API côté navigateur** (la clé doit rester
  secrète, elle ne vit que dans la CI).

## 2. RÈGLES MÉTIER (décisions de l'utilisateur)

- **Divisions instables** (2es/3es échelons : E1, E2, E3, SP2, I2, D2, F2,
  SC1, SC2, SC3 — liste dans `serveur.DIVS_INSTABLES`) : exclues des
  conseils sous **85 %**, exclues des SAFE/combinés sous **90 %**, toujours
  visibles dans « matchs à venir ». Décision du 08/09/2026 après mesure :
  le modèle s'y surestime de 4 à 8 points (analyse_divisions.py,
  walk-forward ≈ 20 000 matchs). Les 1res divisions ne changent pas.
- **SAFE CORNERS** : le handicap le PLUS PÉNALISANT que le réel soutient
  (≥ 85 % mesurés ET cote juste ≥ 1,05). La 1re mi-temps n'entre JAMAIS
  dans le safe (mesuré sur 2 931 matchs : victoire sèche 54 % en moyenne,
  63 % max). Coupon montante : tous les bons matchs du jour, cote totale
  1,20 → l'infini, même jour uniquement, jamais de report.
- **Combinés** : SAFE/RISQUE 2-3 évènements ; SAFE WEEK-END jusqu'à 9
  (3 par jour max) ; SAFE DU JOUR = même jour uniquement ; seul le SAFE
  renaît en « SAFE 2 » (rattrapage). Un match passé affiche son résultat,
  jamais supprimé.
- **Coupes** : visibles dans les matchs, JAMAIS dans les sélections suivies
  (approximation inter-ligues non calibrée).
- **SÉRIES « BUTS D'AFFILÉE »** (10/09) : onglet dédié = information
  chiffrée, JAMAIS dans le coupon ni le suivi (aucun marché bookmaker dans
  nos sources → cotes justes 1/p seulement). SAFE séries = « 2+ match »
  ≥ 75 % (79,3 % mesuré, n=115) ou « 2+ domicile » ≥ 70 % (75,6 %, n=82),
  Big 5 hors coupes uniquement, 3 jambes max, même jour, jamais forcé.
  Grosse cote séries = jambes « 3+ » ≥ 10 % (paliers mesurés exacts),
  cote juste cible 20-50, 5 jambes max. Détails : docs/SPEC-BUTS-AFFILEE.md §8.6.
- **Unders durcis** : marges +13/+5/+2 pts au-dessus du seuil (le modèle
  surestime les unders — mesuré).

## 3. GITHUB ET MISE EN LIGNE

- **TOUJOURS `git fetch` + rebase avant de pousser** — l'utilisateur édite
  parfois des fichiers directement sur GitHub.
- Pousser = publier (le site se régénère dans les ~3 minutes). **Feu vert
  de l'utilisateur avant chaque déploiement**, sauf plan déjà validé et
  bugs signalés par l'utilisateur (corrigés et poussés directement).
- Commit : `git -c user.name="sylvermelo" -c user.email="sylvermelo@users.noreply.github.com"`.
- Le dépôt est PRIVÉ : fetch/push avec le jeton fourni en séance (jamais
  stocké nulle part).
- CI toutes les heures à :07 UTC. Les crons GitHub peuvent être retardés
  ou sautés aux heures de pointe — ne pas conclure à un bug trop vite.
- `data/suivi.json` dans git ≠ état live (mémoire live = cache CI +
  Supabase). Ne pas « corriger » l'un avec l'autre.
- `pkill -f serveur.py` tue le shell lui-même : utiliser `fuser -k 8000/tcp`.

## 4. DONNÉES ET SOURCES (budget 0 FCFA)

- **Gratuit et utilisé** : ESPN (sans clé, via curl — urllib renvoie 403),
  football-data.co.uk (CSV versionnés dans data/ — site en 503 depuis le
  05/09/2026, la CI continue sans lui), Understat (xG des 5 grands
  championnats, hors CI), The Odds API (clé en Secret GitHub, 500
  crédits/mois ≈ 14 requêtes/jour, 1 crédit par marché).
- **ABANDONNÉS — ne JAMAIS reproposer** : Sofascore (403 définitif),
  API-Football (compte suspendu), SoccerSAPI, Sportmonks, footballdata.io
  (payant), TotalCorner (403).
- **ESPN, règles techniques** : plages de dates ≤ 42 jours (au-delà :
  troncature) ; les summary conservent les compositions APRÈS les matchs ;
  les compositions des matchs à venir ne sortent qu'à ~1 h du coup d'envoi
  (jamais la veille) ; les qualifications européennes de juillet-août ne
  sont PAS diffusées ; corners 1re MT = texte du commentary
  (« Corner, X. Conceded by », période 1 ou avant la mi-temps), le champ
  `play.team` n'est PAS fiable.
- **CSV co.uk** : colonnes buts = FTHG/FTAG, équipes = HomeTeam/AwayTeam,
  corners = HC/AC, dates en %d/%m/%Y ou %d/%m/%y, encodage latin-1.

## 5. CODE

- **Parité obligatoire Python ↔ JS** : chaque calcul du serveur a un miroir
  exact dans l'app autonome. Après toute modification :
  `python3 genere_app.py` puis `node test_app_autonome.js` (serveur lancé
  sur le port 8000) → « identique au serveur, 0 avertissement ».
- Arrondis : Python `round(x, 4)` ↔ JS `Math.round(x*1e4)/1e4`.
- Ne jamais comparer les mtime (non fiables en CI) — comparer les
  horodatages internes `genere_le`.
- Service Worker : network-first ; bump du CACHE obligatoire à chaque
  changement de l'app.
- Fichier autonome : garde-fou CI entre 300 Ko et 3 Mo.
- math.lgamma sur un tableau numpy = TypeError → passer par
  modeles_secondaires.pmf_marche (scipy).

## 6. RELATION AVEC L'UTILISATEUR

- Non technique : explications SIMPLES, courtes, sans jargon, en français.
- Honnêteté d'abord : limites avant les réussites.
- Cadre Bénin (LNB) avant toute monétisation.
- Vitrine : conseils = abonnement actif 30 jours ; code secret opérateur ;
  téléphone SANS OTP (impossible en plan gratuit Supabase) ; page Méthode
  supprimée ; numéros WhatsApp remplis par l'utilisateur LUI-MÊME.
- Deux sites distincts : robot (sylvermelo.github.io/pronos-foot) et
  vitrine (sylvermelo.github.io/vitrine). Pas de Vercel. URLs conservées.
- Supabase : ref xqogordfcqymkmvzhrby ; les fichiers RLS sont dans
  supabase/ (déjà collés par l'utilisateur dans l'éditeur SQL).
