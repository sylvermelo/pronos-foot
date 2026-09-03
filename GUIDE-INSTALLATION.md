# Installation de la mise à jour automatique

Objectif : que tes données se rafraîchissent **toutes seules chaque matin**, et que
ton Mac, ton PC Windows et ton téléphone voient tous la même version à jour.

Compte environ **15 minutes**, une seule fois.

---

## Le principe en une image

```
   [ Un seul ordinateur fait le travail chaque matin ]
                        │
        1. télécharge les nouveaux résultats
        2. ré-entraîne les modèles
        3. régénère pronos-foot-autonome.html
        4. le dépose dans ton dossier cloud
                        │
                        ▼
              [ Google Drive / iCloud / OneDrive ]
                        │
         ┌──────────────┼──────────────┐
         ▼              ▼              ▼
      ton Mac      ton PC Windows    ton téléphone
```

**Un seul ordinateur** doit être configuré pour la mise à jour — celui qui est
allumé le matin. Choisis celui que tu laisses allumé le plus souvent.
Les autres appareils n'ont **rien à installer** : ils ouvrent le fichier
depuis le cloud.

---

## Étape 1 — Choisir le dossier cloud

Sur l'ordinateur qui fera la mise à jour, vérifie que tu as l'un de ces dossiers
(gratuits, il en faut un seul) :

| Service | Emplacement habituel | Sur téléphone |
|---|---|---|
| **Google Drive** | `Google Drive` dans ton dossier personnel | app Google Drive (Android + iPhone) |
| **iCloud** | automatique sur Mac | app Fichiers (iPhone) |
| **OneDrive** | `OneDrive` dans ton dossier personnel | app OneDrive (Android + iPhone) |
| **Dropbox** | `Dropbox` dans ton dossier personnel | app Dropbox |

Si tu n'en as aucun, crée un compte Google Drive : c'est gratuit, 15 Go, et ça
marche sur tous les téléphones.

---

## Étape 2 — Installer Python

### Sur Mac

Ouvre **Terminal** (dans Applications → Utilitaires) et tape :

```bash
python3 --version
```

- Si tu vois `Python 3.9` ou plus récent : **c'est bon**, passe à l'étape 3.
- Si un message te propose d'installer les outils en ligne de commande : accepte.
- Si rien ne s'installe : va sur <https://www.python.org/downloads/>, télécharge,
  double-clique sur le paquet, suis les étapes.

### Sur Windows

1. Va sur <https://www.python.org/downloads/>
2. Clique sur le gros bouton jaune **Download Python 3.x**
3. Lance le téléchargement
4. ⚠️ **Sur la première fenêtre d'installation, coche la case
   « Add python.exe to PATH »** en bas — c'est indispensable, ne l'oublie pas
5. Clique sur **Install Now**

Vérifie : ouvre **Invite de commandes** (tape `cmd` dans le menu Démarrer) :

```bat
python --version
```

Tu dois voir `Python 3.x.x`.

---

## Étape 3 — Installer les bibliothèques de calcul

Dans le dossier de l'application, tape :

**Mac :**
```bash
cd ~/pronos-foot          # adapte le chemin si tu l'as mis ailleurs
python3 -m pip install numpy scipy pandas
```

**Windows :**
```bat
cd %USERPROFILE%\pronos-foot
python -m pip install numpy scipy pandas
```

Ça télécharge environ 100 Mo. Une seule fois.

Si tu vois `Requirement already satisfied`, c'est qu'elles sont déjà là.

---

## Étape 4 — Choisir où déposer le fichier

```bash
python3 maj.py --config       # Mac
python maj.py --config        # Windows
```

Le script **détecte tout seul** tes dossiers cloud et te les liste. Tu tapes
simplement le numéro. À partir de là, chaque mise à jour déposera une copie du
fichier HTML dans ce dossier.

---

## Étape 5 — Installer la mise à jour automatique

### Sur Mac

```bash
cd ~/pronos-foot
./installer_auto.sh 07:00
```

L'heure est modifiable : `./installer_auto.sh 06:30` par exemple.

**Avantage du Mac** : si ton ordinateur est éteint ou endormi à 7 h, la mise à
jour sera **rattrapée au réveil**. Tu ne perds jamais une journée.

### Sur Windows

Dans le dossier de l'application, **double-clique** sur :

```
installer_auto.bat
```

Ou pour une autre heure, en invite de commandes :

```bat
installer_auto.bat 06:30
```

Aucune fenêtre ne s'ouvrira le matin : tout se passe en arrière-plan.

⚠️ **Limite de Windows** : contrairement au Mac, si le PC est éteint à l'heure
prévue, la mise à jour est **perdue** pour la journée. Choisis une heure où il
est allumé, ou active le réveil programmé dans les options d'alimentation.

---

## Étape 6 — Vérifier que ça marche

Ne reste pas jusqu'à demain pour savoir si c'est bon. Teste tout de suite :

```bash
python3 maj.py --check      # regarde s'il y a du neuf (ne modifie rien)
python3 maj.py              # fait la mise à jour pour de vrai
```

Puis consulte le journal :

```bash
tail -30 data/maj.log       # Mac
notepad data\maj.log        # Windows
```

Tu dois voir des lignes horodatées avec `INFO`. Si tu vois `ERROR` ou `WARN`,
le message explique quoi.

---

## Sur ton téléphone

Aucune installation. Ouvre ton app cloud et touche le fichier
**`pronos-foot-autonome.html`** :

- **iPhone** : app Fichiers → iCloud Drive ou Google Drive → touche le fichier.
  Il s'ouvre dans Safari. Si rien ne se passe, touche longuement puis
  « Partager » → Safari.
- **Android** : app Google Drive → touche le fichier → s'il propose de
  télécharger, accepte, puis ouvre-le avec Chrome.

💡 **Ajoute-le à l'écran d'accueil** pour le lancer comme une vraie application :
dans le navigateur, menu ⋮ ou Partager → « Sur l'écran d'accueil ».

---

## Utilisation courante

| Tu veux… | Commande |
|---|---|
| Voir s'il y a du neuf | `python3 maj.py --check` |
| Mettre à jour maintenant | `python3 maj.py` |
| Forcer un ré-entraînement | `python3 maj.py --force` |
| Changer le dossier cloud | `python3 maj.py --config` |
| Lire le journal | `tail -30 data/maj.log` |
| **Tout désinstaller** | `./installer_auto.sh --retirer` (Mac) ou `installer_auto.bat --retirer` (Windows) |

---

## Combien de temps ça prend ?

Le script est économe : il ne télécharge que ce qui a vraiment changé.

| Situation | Durée |
|---|---|
| Rien de neuf sur la source | **8 secondes** |
| Liste des matchs à venir changée | ~15 s (pas de ré-entraînement) |
| Nouveaux résultats de matchs | **~45 secondes** (téléchargement + ré-entraînement + régénération) |

En semaine il n'y a généralement rien à faire. Le gros de l'activité a lieu le
**lundi matin**, après les matchs du week-end.

---

## Dépannage

**« python3 est introuvable » (Mac) / « python n'est pas reconnu » (Windows)**
Python n'est pas installé, ou pas dans le PATH. Sur Windows, réinstalle en
cochant bien « Add python.exe to PATH ».

**« les bibliothèques numpy / scipy / pandas manquent »**
Relance l'étape 3.

**La tâche ne s'est pas lancée ce matin**
Ouvre `data/maj.log`. S'il n'y a aucune ligne à l'heure prévue, l'ordinateur
était éteint (Windows ne rattrape pas, Mac si).

**Le téléphone affiche une vieille version**
Le cloud n'a pas encore synchronisé. Ouvre l'app cloud manuellement et attends
quelques secondes. Vérifie aussi que `maj.py --config` pointe bien vers le bon
dossier.

**Pas d'internet ce jour-là**
Ce n'est pas grave : le script détecte la coupure, n'écrase rien, et réessaiera
le lendemain. Tes données existantes restent utilisables.

---

## Ce que la mise à jour NE fait PAS

Par honnêteté :

- **Elle n'améliore pas les résultats du moteur.** Les tests donnent toujours
  −6 à −13 % de rendement. Des données fraîches ne changent rien à ça.
- **Elle n'ajoute pas de nouvelles sources.** Elle reste sur
  football-data.co.uk, gratuit mais limité : pas de compositions d'équipe,
  pas de blessés, pas de statistiques de joueurs.
- **Elle ne couvre pas tous les championnats du monde.** 21 divisions
  européennes. Pas de championnat africain, asiatique ou américain.
