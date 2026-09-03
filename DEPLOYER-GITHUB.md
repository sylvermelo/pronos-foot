# Déployer sur GitHub — l'application se mettra à jour toute seule

Après ça, tu auras **une adresse web fixe**, ouverte depuis ton Mac, ton PC ou ton
téléphone, rafraîchie automatiquement chaque matin à 07:30 (heure du Bénin).

Aucun ordinateur à laisser allumé. Aucun abonnement. Aucune carte bancaire.

Compte **20 minutes**, une seule fois.

---

## Étape 0 — Récupérer le dossier

L'application complète vit dans l'espace de travail Arena. Télécharge l'archive
**`pronos-foot-github.zip`** (à la racine de l'espace de travail) : elle contient
exactement les 31 fichiers à publier, et rien d'autre.

1. Télécharge le ZIP puis décompresse-le (double-clic)
2. Tu obtiens un dossier nommé `pronos-foot`
3. Pose-le où tu veux (Bureau, Documents…) — c'est lui que tu enverras sur GitHub
4. Suis la méthode A ou la méthode B ci-dessous

---

## Ce qui va être publié

Seulement **31 fichiers, 0,8 Mo** : le code, la documentation, et les 4 Ko de
chiffres de fiabilité. Les 175 fichiers de données (31 Mo) ne sont **pas** publiés :
GitHub les retéléchargera tout seul, puis les conservera dans son cache.

⚠️ **Ton dépôt sera public.** C'est la condition pour que ce soit gratuit et
illimité. Ton code sera donc visible par tout le monde. Il ne contient aucun mot
de passe, aucune donnée personnelle, aucun historique de paris. Si ça te gêne,
dis-le-moi et on cherchera une autre solution.

---

## Méthode A — GitHub Desktop (recommandée, sans ligne de commande)

### 1. Créer le dépôt sur GitHub

1. Va sur <https://github.com/new>
2. **Repository name** : `pronos-foot` (ou ce que tu veux)
3. Laisse **Public** coché
4. **Ne coche pas** « Add a README » — le dossier en contient déjà un
5. Clique **Create repository**

### 2. Installer GitHub Desktop

1. Va sur <https://desktop.github.com>
2. Télécharge et installe
3. Connecte-toi avec ton compte GitHub

### 3. Envoyer le dossier

1. Dans GitHub Desktop : **File → Add Local Repository**
2. Choisis le dossier `pronos-foot`
3. S'il propose « create a repository », accepte
4. En bas à gauche tu verras la liste des fichiers : **elle doit faire environ
   30 lignes**. Si tu en vois 200, le fichier `.gitignore` n'a pas été pris en
   compte — arrête-toi et dis-le-moi
5. Écris un message (par exemple `Premier envoi`) et clique **Commit to main**
6. Clique **Publish repository** en haut

C'est envoyé.

---

## Méthode B — Ligne de commande

Si tu préfères, ou si GitHub Desktop ne te convient pas.

**Sur Mac** (git est déjà installé) :
```bash
cd ~/pronos-foot
git init
git add .
git status          # ⚠️ vérifie : environ 30 fichiers, pas 200
git commit -m "Premier envoi"
git branch -M main
git remote add origin https://github.com/TON_PSEUDO/pronos-foot.git
git push -u origin main
```

**Sur Windows** : installe d'abord git depuis <https://git-scm.com/download/win>,
puis ouvre « Git Bash » dans le dossier du projet et tape les mêmes commandes.

Il te demandera ton identifiant GitHub. Depuis 2021 le mot de passe ne suffit
plus : il faut un **jeton d'accès personnel**. Crée-le sur
<https://github.com/settings/tokens> (coche la permission `repo`).

---

## Activer la publication du site

C'est l'étape qui rend l'application visible sur internet. **Une seule fois.**

1. Sur ton dépôt GitHub, clique sur **Settings** (l'engrenage, en haut à droite)
2. Dans le menu de gauche, clique sur **Pages**
3. À la ligne **Build and deployment**, cherche **Source**
4. Choisis **GitHub Actions** dans la liste déroulante

   ⚠️ Ne choisis pas « Deploy from a branch » — c'est l'ancienne méthode,
   elle ne fonctionnerait pas avec ce projet.

5. C'est tout, il n'y a rien à enregistrer

---

## Lancer la première mise à jour

Plutôt que d'attendre demain matin 07:30, lance-la maintenant.

1. Clique sur l'onglet **Actions** de ton dépôt
2. Si un bandeau jaune te demande d'activer les workflows, clique
   **« I understand my workflows, go ahead and enable them »**
3. Dans la liste de gauche, clique sur **« Mise à jour quotidienne »**
4. À droite, clique le bouton **Run workflow** puis encore **Run workflow**
5. Une ligne apparaît. Clique dessus pour voir le détail en direct

La première exécution dure **3 à 5 minutes** (elle télécharge les 31 Mo de
données). Les suivantes dureront **1 à 2 minutes**.

Pendant l'exécution, tu verras un point jaune. Quand il devient vert ✅, c'est fini.
S'il devient rouge ❌, clique dessus et copie-moi le message d'erreur.

---

## Récupérer ton adresse web

Une fois la première exécution terminée en vert :

1. Va dans **Settings → Pages**
2. En haut tu verras : **« Your site is live at https://TON-PSEUDO.github.io/pronos-foot/ »**
3. C'est ton adresse. Clique dessus.

Cette adresse est **permanente**. Ajoute-la en favori sur ton Mac, ton PC et ton
téléphone.

### Sur ton téléphone

Ouvre l'adresse dans Chrome ou Safari, puis :
- **iPhone** : bouton Partager → **Sur l'écran d'accueil**
- **Android** : menu ⋮ → **Ajouter à l'écran d'accueil**

Tu auras une icône qui lance l'application comme une vraie appli.

---

## Changer l'heure de la mise à jour

Le fichier `.github/workflows/maj.yml` contient cette ligne :

```yaml
    - cron: '30 6 * * *'
```

⚠️ **GitHub utilise l'heure UTC, pas l'heure du Bénin.** Le Bénin est à UTC+1.

| Heure voulue à Cotonou | Ligne à écrire |
|---|---|
| 06:00 | `- cron: '0 5 * * *'` |
| **07:30** (réglage actuel) | `- cron: '30 6 * * *'` |
| 12:00 | `- cron: '0 11 * * *'` |
| 18:00 | `- cron: '0 17 * * *'` |

Le format est `minute heure * * *`. Modifie la ligne, enregistre, et GitHub
relancera tout seul.

💡 Les tâches planifiées de GitHub peuvent avoir **jusqu'à 15 minutes de retard**
aux heures de forte affluence. C'est normal, ce n'est pas une panne.

---

## Vérifier que ça tourne

Dans l'onglet **Actions** de ton dépôt, tu verras une ligne par exécution.
Clique sur la dernière : en bas de la page, un récapitulatif affiche les
dernières lignes du journal, par exemple :

```
historiques : 3 téléchargés, 103 déjà à jour, 0 échecs
→ entraine.py (≈35 s)
mise à jour terminée avec succès
```

Si tu vois `aucune nouveauté sur la source : rien à faire`, c'est normal en
pleine semaine : il n'y a pas eu de match.

---

## Dépannage

**Le workflow est rouge ❌**
Clique dessus, puis sur l'étape rouge, et regarde la dernière ligne. Les causes
courantes : le site source était momentanément inaccessible (relance avec
« Re-run jobs »), ou GitHub a dépassé son délai (rare).

**« Your site is live » n'apparaît pas**
Vérifie que Settings → Pages → Source est bien sur **GitHub Actions**. C'est
l'oubli le plus fréquent.

**L'adresse affiche une page 404**
La première publication met 1 à 2 minutes après la fin du workflow. Attends un
peu et rafraîchis. Vérifie aussi que l'adresse se termine bien par `/` .

**Les données ne changent jamais**
Normal en été : les championnats européens sont en pause de mi-mai à début août.
Le journal affichera « aucune nouveauté sur la source » pendant des semaines.

**Je veux tout arrêter**
Settings → Pages → Source : remets **None**. Puis supprime le dépôt si tu veux.

---

## Ce que ça ne change pas

Pour être clair : automatiser la mise à jour rend l'application **plus pratique**,
pas **plus rentable**.

Les tests donnent toujours un rendement de **−6 à −13 %**. Des données fraîches
chaque matin ne transforment pas un modèle qui perd face au marché en un modèle
qui gagne. Ce que tu y gagnes, c'est de ne plus analyser des matchs périmés et
d'avoir ton outil sous la main, partout, sans rien installer.
