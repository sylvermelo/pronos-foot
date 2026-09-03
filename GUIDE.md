# Guide d'utilisation — en 2 minutes

## Ouvrir l'application

Tu as **deux fichiers** qui font exactement la même chose. Prends celui qui t'arrange.

### Solution 1 — le fichier autonome (la plus simple)

**`pronos-foot-autonome.html`** (391 Ko)

1. Copie ce fichier sur ton ordinateur (ou ton téléphone)
2. **Double-clique dessus**
3. L'application s'ouvre dans ton navigateur

C'est tout. **Aucune installation, aucun Python, aucune connexion internet nécessaire.**
Toutes les données des 21 championnats et tout le moteur de calcul sont à l'intérieur du fichier.

Tu peux le mettre sur une clé USB, l'envoyer par WhatsApp à un ami, le garder
dans tes téléchargements : il fonctionnera toujours, même hors ligne.

### Solution 2 — le serveur local (si tu veux les données fraîches)

```bash
cd pronos-foot
./lancer.sh
```
Puis ouvre `http://localhost:8000` dans ton navigateur.

Cette version télécharge les dernières données et ré-entraîne les modèles.
Elle a besoin de Python. **Pour un usage courant, la solution 1 suffit largement.**

---

## À quoi sert chaque onglet

| Onglet | Ce que tu y fais |
|---|---|
| **Matchs à venir** | La liste des 48 prochains matchs. Le moteur donne ses probabilités à côté des cotes des bookmakers. L'écart entre les deux est affiché. Tu peux ajouter un match à ton coupon avec les petits boutons 1 / X / 2. |
| **Mon coupon** | Tu construis ton combiné, l'application le simule 20 000 fois et te dit ce que ça donne vraiment. |
| **Simulateur** | Tu choisis n'importe quelle ligue et n'importe quelles équipes — même un match qui n'existe pas encore. Tu obtiens la matrice complète des 121 scores possibles. |
| **Scores fleuves** | Les confrontations les plus ouvertes (pour « plus de buts ») et les plus fermées (pour « moins de buts »). |
| **Fautes & cartons** | Les totaux attendus de fautes, corners et cartons jaunes, avec l'arbitre du match. |
| **Classement** | La puissance réelle de chaque club : force d'attaque, faiblesse défensive, forme récente, fiabilité de l'estimation. |
| **Bilan honnête** | Les vrais résultats des tests, y compris les échecs. À lire une fois. |

---

## Comment lire les chiffres

**Les pourcentages sont fiables.** C'est le point fort du système, vérifié sur
213 665 cas : quand l'application annonce 65 %, l'événement se produit environ
66 % du temps. Jamais plus de 2 points d'écart.

**Un écart positif ne veut pas dire « bon pari ».** Dans l'onglet Matchs, tu vois
l'écart entre la probabilité du moteur et celle du bookmaker. Un écart positif
signifie seulement que le moteur est plus optimiste que le marché. Sur les tests,
**le marché a eu raison plus souvent que le moteur.**

**« Fiabilité » dans le classement** indique combien de matchs servent de base au
calcul : haute (40+), moyenne (20-40), faible (moins de 20). Une équipe promue
aura toujours une fiabilité faible — méfie-toi de ses chiffres.

---

## Ce que cette application ne fait PAS

Soyons clairs, parce que c'est important :

- **Elle ne prédit pas les résultats.** Elle donne des probabilités, qui sont
  souvent fausses sur un match précis.
- **Elle ne dit pas quoi parier.** Les tests complets donnent un rendement de
  **−6 % à −13 %** : sur la durée, on perd de l'argent en suivant le moteur.
- **Elle ne connaît ni les compositions, ni les blessés, ni les suspendus.**
  L'absence d'un joueur majeur change tout, et l'application ne le voit pas.
- **Les marchés fautes/corners/cartons n'ont aucune cote disponible** dans la
  source gratuite. Leur rentabilité est donc impossible à vérifier. Le gain de
  précision mesuré est de +1,25 % — trop faible pour battre la marge d'un
  bookmaker (5 à 8 %).

**À quoi elle sert vraiment** : analyser un match en 10 secondes, vérifier qu'une
cote n'est pas manifestement absurde, comparer ta propre intuition à un calcul
froid, et préparer un combiné en connaissant ses vraies chances.

C'est un outil d'analyse, pas une machine à gains.

---

## Rafraîchir les données

Le fichier autonome est une **photo figée** : il ne peut pas se mettre à jour
tout seul, car les navigateurs web bloquent tout téléchargement lancé depuis un
fichier HTML local. C'est une mesure de sécurité des navigateurs, pas un défaut
contournable.

Pour avoir des données fraîches en continu, une commande fait tout :

```bash
python3 maj.py            # Mac
python maj.py             # Windows
```

Elle télécharge seulement ce qui a changé, ré-entraîne les modèles si nécessaire,
et régénère le fichier autonome. Durée : **8 secondes** s'il n'y a rien de neuf,
**45 secondes** après un week-end de matchs.

Et surtout, tu peux l'automatiser pour qu'elle tourne **toute seule chaque matin**,
puis déposer le fichier dans ton cloud pour le retrouver sur ton téléphone.
La marche à suivre complète est dans **`GUIDE-INSTALLATION.md`** (15 minutes,
une seule fois).

Au quotidien, tu peux aussi vérifier sans rien modifier :

```bash
python3 maj.py --check    # y a-t-il du neuf sur la source ?
tail -30 data/maj.log     # qu'est-ce qui s'est passé ?
```

---

## Vérifier que tout fonctionne

```bash
./lancer.sh test                # 25 contrôles sur l'interface serveur
node test_app_autonome.js       # vérifie que le fichier autonome calcule
                                # exactement comme le serveur (2 200 valeurs)
```

Les deux suites doivent se terminer par « TOUS LES TESTS PASSENT » et
« FICHIER AUTONOME VALIDÉ ».
